"""SSO demo API. Authentication can use Asgardeo; product access is local."""

from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .asgardeo import (
    AsgardeoError,
    amr_from_claims,
    begin_authorization,
    email_from_claims,
    email_verified_flag,
    exchange_code,
    get_discovery,
    is_email_otp,
    logout_url,
    take_state,
    validate_id_token,
)
from .config import settings
from .identity import (
    IdentityError,
    create_invited_user,
    find_user,
    force_password_reset,
    recovery_url,
    set_account_disabled,
    terminate_sessions,
)
from .db import (
    create_company_account,
    create_user,
    delete_sessions_for_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_subject,
    init_db,
    list_audit,
    list_users,
    record_audit,
    save_entitlement,
    set_password,
    update_subject,
    update_user_flags,
    user_public,
    verify_password,
)
from .sessions import (
    clear_session_cookie,
    end_session,
    expire_current_session,
    http_error,
    issue_session,
    read_auth,
    session_view,
)

logger = logging.getLogger("portal")

FMS_SUMMARY = {
    "application": "FMS",
    "description": "Dummy facilities work orders. No production data.",
    "records": [
        {"id": "WO-1042", "site": "Demo Warehouse A", "status": "Open", "summary": "Inspection"},
        {"id": "WO-1048", "site": "Demo Plant B", "status": "Scheduled", "summary": "Generator service"},
        {"id": "WO-1051", "site": "Demo Depot C", "status": "Closed", "summary": "Lighting check"},
    ],
}

POS_SUMMARY = {
    "application": "POS",
    "description": "Dummy point-of-sale receipts. No production data.",
    "records": [
        {"id": "INV-2201", "lane": "Lane 1", "total": "4500 LKR", "status": "Paid"},
        {"id": "INV-2204", "lane": "Lane 2", "total": "1250 LKR", "status": "Paid"},
        {"id": "INV-2209", "lane": "Lane 1", "total": "8900 LKR", "status": "Void"},
    ],
}

ECOMMERCE_SUMMARY = {
    "application": "E-Commerce",
    "description": "Dummy online orders. No production data.",
    "records": [
        {"id": "EC-310", "channel": "Web", "total": "6400 LKR", "status": "Packed"},
    ],
}

EMS_SUMMARY = {
    "application": "EMS",
    "description": "Dummy employee records. No production data.",
    "records": [
        {"id": "EM-18", "site": "Demo Office", "status": "Active"},
    ],
}

LOGIN_ERROR_CODES = {
    "mock_mode",
    "not_configured",
    "asgardeo_denied",
    "invalid_callback",
    "token_exchange_failed",
    "no_email",
    "email_unverified",
    "account_inactive",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    init_db()
    logger.info("Auth mode: %s", "mock" if settings.mock_mode else "asgardeo")
    if settings.session_secret_is_placeholder:
        logger.warning("SESSION_SECRET is still a placeholder. Set a long random value in .env.")
    if settings.mock_mode_setting == "false" and not settings.asgardeo_configured:
        logger.error("MOCK_MODE=false, but Asgardeo client settings are incomplete.")
    yield


app = FastAPI(title="SSO Demo", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def api_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


class MockLoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class AccountPatch(BaseModel):
    fms_access: bool | None = None
    pos_access: bool | None = None
    ecommerce_access: bool | None = None
    ems_access: bool | None = None
    active: bool | None = None


class CompanyCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    fms_paid: bool = False
    pos_paid: bool = False
    ecommerce_paid: bool = False
    ems_paid: bool = False


class EmailOtpChallenge(BaseModel):
    kind: str = Field(pattern="^(create|permission|active)$")
    company_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, max_length=200)
    plan: str | None = Field(default=None, pattern="^(pos|fms|both|product1|product2)$")
    product1: bool | None = None
    product2: bool | None = None
    user_id: int | None = None
    active: bool | None = None


def frontend(path: str) -> str:
    return f"{settings.frontend_url}{path}"


def login_redirect(code: str) -> RedirectResponse:
    safe = code if code in LOGIN_ERROR_CODES else "invalid_callback"
    response = RedirectResponse(frontend(f"/?error={safe}"), status_code=302)
    response.delete_cookie(settings.oauth_cookie_name, path="/")
    return response


def same_value(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return secrets.compare_digest(left, right)


def require_admin(auth: dict) -> None:
    if auth["user"]["role"] != "admin":
        raise http_error(403, "forbidden", "Administrator access is required.")


def plan_flags(plan: str) -> tuple[bool, bool]:
    product1 = plan in {"fms", "product1", "both"}
    product2 = plan in {"pos", "product2", "both"}
    return product1, product2


def chosen_products(body: EmailOtpChallenge) -> tuple[bool, bool] | None:
    if body.product1 is None and body.product2 is None:
        if body.plan not in {"pos", "fms", "both", "product1", "product2"}:
            return None
        return plan_flags(body.plan)
    return bool(body.product1), bool(body.product2)


def checked_challenge(body: EmailOtpChallenge, auth: dict) -> dict:
    """Validate an admin change before Asgardeo is asked for an email OTP."""
    if body.kind == "create":
        email = (body.email or "").strip().lower()
        name = (body.company_name or "").strip()
        products = chosen_products(body)
        if len(name) < 2 or "@" not in email or products is None or not any(products):
            raise http_error(400, "invalid_company", "Enter the company, email, and at least one product.")
        password = (body.password or "").strip()
        if get_user_by_email(email) is None and len(password) < 8:
            raise http_error(400, "invalid_company", "Set a password of at least 8 characters for this company.")
        fms_paid, pos_paid = products
        return {
            "kind": "create",
            "company_name": name,
            "email": email,
            "password": password,
            "fms_paid": fms_paid,
            "pos_paid": pos_paid,
            "ecommerce_paid": False,
            "ems_paid": False,
        }
    existing = get_user_by_id(body.user_id or -1)
    if existing is None:
        raise http_error(404, "not_found", "Account was not found.")
    if body.kind == "permission":
        products = chosen_products(body)
        if existing["role"] != "customer" or products is None or not any(products):
            raise http_error(400, "invalid_permission", "Choose Product 1, Product 2, or both for this company.")
        fms_access, pos_access = products
        return {"kind": "permission", "user_id": existing["id"], "fms_access": fms_access, "pos_access": pos_access}
    if body.active is None:
        raise http_error(400, "no_changes", "No changes were submitted.")
    if body.active is False and existing["id"] == auth["user"]["id"]:
        raise http_error(
            400,
            "cannot_deactivate_self",
            "You cannot deactivate the account you are signed in with.",
        )
    return {"kind": "active", "user_id": existing["id"], "active": body.active}


def apply_admin_payload(payload: dict, auth: dict) -> None:
    kind = payload.get("kind")
    if kind == "create":
        email = str(payload["email"])
        password = str(payload.get("password") or "")
        existing = get_user_by_email(email)
        if existing is not None:
            update_user_flags(
                existing["id"],
                fms_access=bool(payload["fms_paid"]),
                pos_access=bool(payload["pos_paid"]),
            )
            if password:
                set_password(existing["id"], password)
            record_audit(auth["user"]["email"], "entitlement", email, "products updated after email verification")
            return
        if len(password) < 8:
            raise http_error(400, "invalid_company", "Set a password of at least 8 characters for this company.")
        created = create_company_account(
            email,
            str(payload["company_name"]),
            password,
            bool(payload["fms_paid"]),
            bool(payload["pos_paid"]),
        )
        if created is None:
            raise http_error(409, "email_taken", "A customer with this email already exists.")
        record_audit(auth["user"]["email"], "create_company", email, "company login created after email verification")
        return
    if kind == "permission":
        update_user_flags(
            int(payload["user_id"]),
            fms_access=bool(payload["fms_access"]),
            pos_access=bool(payload["pos_access"]),
        )
        return
    if kind == "active":
        user_id = int(payload["user_id"])
        active = bool(payload["active"])
        if active is False and user_id == auth["user"]["id"]:
            raise http_error(
                400,
                "cannot_deactivate_self",
                "You cannot deactivate the account you are signed in with.",
            )
        if get_user_by_id(user_id) is None:
            raise http_error(404, "not_found", "Account was not found.")
        update_user_flags(user_id, active=active)
        return
    raise http_error(400, "no_changes", "No changes were submitted.")


def finish_admin_change(request: Request, claims: dict, stored: dict) -> RedirectResponse:
    """Apply one admin change only after this callback's email code."""
    response = RedirectResponse(frontend("/admin?error=otp_missing"), status_code=302)
    response.delete_cookie(settings.oauth_cookie_name, path="/")
    if not is_email_otp(claims):
        logger.warning("Admin change was not saved. Email OTP was not in amr=%s", amr_from_claims(claims))
        return response
    try:
        auth = read_auth(request)
    except HTTPException:
        response.headers["location"] = frontend("/admin?error=otp_session")
        return response
    if stored.get("user_id") != auth["user"]["id"] or auth["user"]["role"] != "admin":
        response.headers["location"] = frontend("/admin?error=otp_session")
        return response
    try:
        apply_admin_payload(json.loads(stored.get("payload") or ""), auth)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = detail.get("code") if detail.get("code") in {
            "email_taken",
            "not_found",
            "cannot_deactivate_self",
            "no_changes",
        } else "otp_failed"
        response.headers["location"] = frontend(f"/admin?error={code}")
        return response
    except json.JSONDecodeError:
        response.headers["location"] = frontend("/admin?error=otp_failed")
        return response
    response.headers["location"] = frontend("/admin?notice=saved")
    return response


def set_oauth_cookie(response, state: str) -> None:
    response.set_cookie(
        settings.oauth_cookie_name,
        state,
        httponly=True,
        max_age=600,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def require_product(auth: dict, flag: str, label: str) -> None:
    if not auth["user"][flag]:
        raise http_error(403, "product_denied", f"{label} access is not enabled for this account.")


def upsert_asgardeo_user(email: str, claims: dict):
    subject = str(claims.get("sub") or "")
    display_name = str(claims.get("name") or email).strip()[:120] or email
    user = get_user_by_email(email)
    if user is None:
        is_admin = email in settings.admin_emails
        return create_user(
            email=email,
            display_name=display_name,
            role="admin" if is_admin else "customer",
            fms_access=is_admin,
            pos_access=is_admin,
            active=is_admin,
            subject=subject or None,
        )
    if subject and user["subject"] != subject:
        update_subject(user["id"], subject)
        user = get_user_by_id(user["id"])
    return user


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "server_mode": "mock" if settings.mock_mode else "asgardeo"}


@app.get("/api/auth/config")
def auth_config() -> dict:
    payload: dict = {
        "server_mode": "mock" if settings.mock_mode else "asgardeo",
        "mock_mode_setting": settings.mock_mode_setting,
        "mock_login_enabled": settings.mock_mode,
        "asgardeo_configured": settings.asgardeo_configured,
        "session_minutes": settings.session_minutes,
        "discovery_ok": None,
        "discovery_error": None,
        "issuer": None,
        "client_id_set": bool(settings.client_id),
        "organization_set": bool(settings.base_url),
        "sign_in": "asgardeo",
        "identity_admin": "configured" if settings.identity_admin_configured else "not_configured",
        "password_recovery_url": recovery_url(),
    }
    if settings.mock_mode:
        if settings.asgardeo_configured:
            payload["discovery_error"] = (
                "Asgardeo settings are present, but MOCK_MODE forces the local dummy sign-in."
            )
        return payload

    if not settings.asgardeo_configured:
        payload["discovery_ok"] = False
        payload["discovery_error"] = "Asgardeo client id or organization base URL is not set."
        return payload

    try:
        discovery = get_discovery()
    except AsgardeoError:
        payload["discovery_ok"] = False
        payload["discovery_error"] = "The Asgardeo discovery document could not be loaded."
        return payload
    payload["discovery_ok"] = True
    payload["issuer"] = discovery.get("issuer")
    return payload


@app.post("/api/auth/mock-login")
def mock_login(body: MockLoginBody):
    if not settings.mock_mode:
        raise http_error(404, "mock_disabled", "Mock sign-in is turned off.")
    email = body.email.strip().lower()
    user = get_user_by_email(email)
    password_ok = bool(
        user
        and user["password_hash"]
        and user["password_salt"]
        and verify_password(body.password, user["password_salt"], user["password_hash"])
    )
    if not password_ok:
        raise http_error(401, "invalid_credentials", "Invalid email or password.")
    if not user["active"]:
        raise http_error(403, "account_inactive", "This account is deactivated.")
    from fastapi.responses import JSONResponse

    response = JSONResponse({"ok": True, "auth_mode": "mock"})
    issue_session(response, user, "mock", [], "not_applicable")
    return response


@app.post("/api/auth/company-login")
def company_login(body: MockLoginBody):
    """Company login uses the email and password issued for the products they bought."""
    email = body.email.strip().lower()
    user = get_user_by_email(email)
    password_ok = bool(
        user
        and user["password_hash"]
        and user["password_salt"]
        and verify_password(body.password, user["password_salt"], user["password_hash"])
    )
    if not password_ok:
        raise http_error(401, "invalid_credentials", "Invalid email or password.")
    if not user["active"]:
        raise http_error(403, "account_inactive", "This account is deactivated.")
    response = JSONResponse({"ok": True})
    issue_session(response, user, "company", [], "not_applicable")
    return response


@app.get("/api/auth/passkey")
def passkey_login():
    """Company side sign-in. WSO2 asks for the passkey, not an email and password."""
    if settings.mock_mode:
        return login_redirect("mock_mode")
    if not settings.asgardeo_configured:
        return login_redirect("not_configured")
    try:
        url, state = begin_authorization("passkey")
    except AsgardeoError:
        return login_redirect("not_configured")
    response = RedirectResponse(url, status_code=302)
    set_oauth_cookie(response, state)
    return response


@app.post("/api/auth/passkey-confirm")
def passkey_confirm(body: EmailOtpChallenge, request: Request):
    """Confirm a company-side change with the passkey. Nothing is saved until that succeeds."""
    auth = read_auth(request)
    require_admin(auth)
    payload = checked_challenge(body, auth)
    if settings.mock_mode or not settings.asgardeo_configured:
        raise http_error(
            409,
            "passkey_unavailable",
            "Passkey confirmation is handled by WSO2. Nothing was saved.",
        )
    try:
        url, state = begin_authorization(
            "passkey_confirm",
            user_id=auth["user"]["id"],
            payload=json.dumps(payload),
            login_hint=auth["user"]["email"],
        )
    except AsgardeoError:
        raise http_error(503, "not_configured", "WSO2 could not start the passkey check. Nothing was saved.")
    response = JSONResponse({"ok": True, "redirect": url})
    set_oauth_cookie(response, state)
    return response


@app.get("/api/auth/login")
def asgardeo_login():
    if settings.mock_mode:
        return login_redirect("mock_mode")
    if not settings.asgardeo_configured:
        return login_redirect("not_configured")
    try:
        url, state = begin_authorization("login")
    except AsgardeoError:
        return login_redirect("not_configured")
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        settings.oauth_cookie_name,
        state,
        httponly=True,
        max_age=600,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return response


@app.get("/api/auth/callback")
def asgardeo_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        stored = take_state(state) if state else None
        if stored and stored.get("purpose") == "admin_change":
            response = RedirectResponse(frontend("/admin?error=asgardeo_denied"), status_code=302)
            response.delete_cookie(settings.oauth_cookie_name, path="/")
            return response
        return login_redirect("asgardeo_denied")
    cookie_state = request.cookies.get(settings.oauth_cookie_name, "")
    if not code or not state or not same_value(cookie_state, state):
        return login_redirect("invalid_callback")
    if settings.mock_mode:
        return login_redirect("mock_mode")
    if not settings.asgardeo_configured:
        return login_redirect("not_configured")

    stored = take_state(state)
    if stored is None:
        return login_redirect("invalid_callback")
    try:
        token_set = exchange_code(code, stored["code_verifier"])
        claims = validate_id_token(token_set["id_token"], stored["nonce"])
    except AsgardeoError as exc:
        if stored.get("purpose") == "admin_change":
            response = RedirectResponse(frontend(f"/admin?error={exc.code}"), status_code=302)
            response.delete_cookie(settings.oauth_cookie_name, path="/")
            return response
        return login_redirect(exc.code)

    if stored.get("purpose") == "admin_change":
        return finish_admin_change(request, claims, stored)

    email = email_from_claims(claims)
    if email is None:
        for key in ("preferred_username", "username"):
            value = str(claims.get(key) or "").strip().lower()
            if "@" in value:
                email = value
                break
    subject = str(claims.get("sub") or "")
    user = get_user_by_subject(subject) if subject else None
    if user is None and email:
        user = upsert_asgardeo_user(email, claims)
    if user is None:
        return login_redirect("no_email")
    verified = email_verified_flag(claims)
    if verified == "false":
        return login_redirect("email_unverified")
    if not user["active"]:
        return login_redirect("account_inactive")

    landing = "/admin" if user["role"] == "admin" else "/home"
    response = RedirectResponse(frontend(landing), status_code=302)
    response.delete_cookie(settings.oauth_cookie_name, path="/")
    issue_session(
        response,
        user,
        "asgardeo",
        amr_from_claims(claims),
        verified,
        id_token=token_set["id_token"],
    )
    return response


@app.get("/api/auth/logout")
def logout(request: Request):
    id_token = end_session(request)
    target = frontend("/")
    if id_token and not settings.mock_mode:
        remote = logout_url(id_token)
        if remote:
            target = remote
    response = RedirectResponse(target, status_code=302)
    clear_session_cookie(response)
    response.delete_cookie(settings.oauth_cookie_name, path="/")
    return response


@app.post("/api/auth/expire")
def expire_session(request: Request) -> dict:
    expire_current_session(request)
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request) -> dict:
    auth = read_auth(request)
    return session_view(auth["user"], auth["session"])


def raise_identity(exc: IdentityError):
    status = 503 if exc.code == "not_configured" else 400 if exc.code == "invalid_email" else 502
    raise http_error(status, exc.code, exc.message)


def provision_customer(
    auth: dict,
    email: str,
    company_name: str,
    fms: bool,
    pos: bool,
    ecommerce: bool,
    ems: bool,
) -> dict:
    """One WSO2 identity per email. KAIONEX stores only the product entitlements."""
    email = email.strip().lower()
    if "@" not in email or '"' in email:
        raise http_error(400, "invalid_email", "Enter a valid email for this company.")
    if not any((fms, pos, ecommerce, ems)):
        raise http_error(400, "nothing_paid", "Choose at least one product this company paid for.")
    subject = None
    invitation = "not_configured"
    if not settings.mock_mode:
        try:
            found = find_user(email)
            if found is None:
                created = create_invited_user(email, company_name)
                subject = str(created.get("id"))
                invitation = "sent"
            else:
                subject = str(found.get("id") or "")
                invitation = "existing_identity"
        except IdentityError as exc:
            raise_identity(exc)
    saved = save_entitlement(
        email=email,
        display_name=company_name,
        subject=subject,
        fms_access=fms,
        pos_access=pos,
        ecommerce_access=ecommerce,
        ems_access=ems,
    )
    if saved is None:
        raise http_error(409, "email_taken", "A customer with this email already exists.")
    record_audit(
        auth["user"]["email"],
        "link_identity" if invitation == "existing_identity" else "create_identity",
        email,
        invitation,
    )
    public = user_public(saved)
    public["invitation"] = invitation
    return public


def change_account_state(auth: dict, existing: dict, active: bool) -> dict:
    if active is False and existing["id"] == auth["user"]["id"]:
        raise http_error(
            400,
            "cannot_deactivate_self",
            "You cannot deactivate the account you are signed in with.",
        )
    if not settings.mock_mode:
        subject = existing.get("subject")
        if not subject:
            raise http_error(
                409,
                "not_linked",
                "This customer is not linked to a WSO2 identity, so the account was not changed.",
            )
        try:
            set_account_disabled(str(subject), disabled=not active)
            if not active:
                terminate_sessions(str(subject))
        except IdentityError as exc:
            raise_identity(exc)
        delete_sessions_for_user(existing["id"])
    updated = update_user_flags(existing["id"], active=active)
    record_audit(
        auth["user"]["email"],
        "activate" if active else "deactivate",
        existing["email"],
        "asgardeo" if not settings.mock_mode else "local_entitlement",
    )
    return user_public(updated)


@app.post("/api/auth/email-otp")
def start_email_otp(body: EmailOtpChallenge, request: Request):
    """Ask Asgardeo for a fresh email OTP. The change is stored and not applied yet."""
    auth = read_auth(request)
    require_admin(auth)
    payload = checked_challenge(body, auth)
    if settings.mock_mode or not settings.asgardeo_configured:
        raise http_error(
            409,
            "otp_unavailable",
            "Email OTP is sent by Asgardeo. Add the organization name in the environment file. Nothing was saved.",
        )
    try:
        url, state = begin_authorization(
            "email_otp",
            user_id=auth["user"]["id"],
            payload=json.dumps(payload),
            login_hint=auth["user"]["email"] if auth["user"].get("subject") else None,
        )
    except AsgardeoError:
        raise http_error(503, "not_configured", "Asgardeo could not start the email OTP. Nothing was saved.")
    response = JSONResponse({"ok": True, "redirect": url})
    set_oauth_cookie(response, state)
    return response


PRODUCT1_SUMMARY = {
    "application": "Product 1",
    "description": "Included with this company login.",
    "records": [
        {"id": "P1-1042", "item": "Workspace A", "status": "Open"},
        {"id": "P1-1048", "item": "Workspace B", "status": "Scheduled"},
    ],
}

PRODUCT2_SUMMARY = {
    "application": "Product 2",
    "description": "Included with this company login.",
    "records": [
        {"id": "P2-2201", "item": "Order 2201", "status": "Paid"},
        {"id": "P2-2204", "item": "Order 2204", "status": "Paid"},
    ],
}


@app.get("/api/product-1/summary")
def product_one_summary(request: Request) -> dict:
    auth = read_auth(request)
    require_product(auth, "fms_access", "Product 1")
    return PRODUCT1_SUMMARY


@app.get("/api/product-2/summary")
def product_two_summary(request: Request) -> dict:
    auth = read_auth(request)
    require_product(auth, "pos_access", "Product 2")
    return PRODUCT2_SUMMARY


@app.get("/api/fms/summary")
def fms_summary(request: Request) -> dict:
    auth = read_auth(request)
    require_product(auth, "fms_access", "FMS")
    return FMS_SUMMARY


@app.get("/api/pos/summary")
def pos_summary(request: Request) -> dict:
    auth = read_auth(request)
    require_product(auth, "pos_access", "POS")
    return POS_SUMMARY


@app.get("/api/ecommerce/summary")
def ecommerce_summary(request: Request) -> dict:
    auth = read_auth(request)
    require_product(auth, "ecommerce_access", "E-Commerce")
    return ECOMMERCE_SUMMARY


@app.get("/api/ems/summary")
def ems_summary(request: Request) -> dict:
    auth = read_auth(request)
    require_product(auth, "ems_access", "EMS")
    return EMS_SUMMARY


@app.post("/api/admin/company-access")
def save_company_access(body: EmailOtpChallenge, request: Request) -> dict:
    """Refuse a direct save. Adding a company or changing products requires the email code."""
    auth = read_auth(request)
    require_admin(auth)
    del body
    raise http_error(
        409,
        "email_verification_required",
        "Confirm the email code before this access is saved. Nothing was saved.",
    )


@app.post("/api/admin/companies")
def admin_create_company(body: CompanyCreate, request: Request) -> dict:
    auth = read_auth(request)
    require_admin(auth)
    return provision_customer(
        auth,
        email=body.email,
        company_name=body.company_name.strip(),
        fms=body.fms_paid,
        pos=body.pos_paid,
        ecommerce=body.ecommerce_paid,
        ems=body.ems_paid,
    )


@app.get("/api/admin/customers")
def admin_customers(request: Request) -> dict:
    auth = read_auth(request)
    require_admin(auth)
    return {
        "accounts": [user_public(row) for row in list_users()],
        "audit": list_audit(),
        "identity_admin": "configured" if settings.identity_admin_configured else "not_configured",
    }


@app.post("/api/admin/customers/{user_id}/password-reset")
def admin_password_reset(user_id: int, request: Request) -> dict:
    auth = read_auth(request)
    require_admin(auth)
    existing = get_user_by_id(user_id)
    if existing is None or not existing.get("subject"):
        raise http_error(409, "not_linked", "This customer is not linked to a WSO2 identity.")
    if settings.mock_mode:
        raise http_error(503, "not_configured", "Password reset is a WSO2 flow and is not available in mock mode.")
    try:
        force_password_reset(str(existing["subject"]))
    except IdentityError as exc:
        raise_identity(exc)
    record_audit(auth["user"]["email"], "password_reset", existing["email"], "forcePasswordReset")
    return {"ok": True}


@app.patch("/api/admin/customers/{user_id}")
def admin_update_customer(user_id: int, body: AccountPatch, request: Request) -> dict:
    auth = read_auth(request)
    require_admin(auth)
    if (
        body.fms_access is None
        and body.pos_access is None
        and body.ecommerce_access is None
        and body.ems_access is None
        and body.active is None
    ):
        raise http_error(400, "no_changes", "No changes were submitted.")
    existing = get_user_by_id(user_id)
    if existing is None:
        raise http_error(404, "not_found", "Account was not found.")
    if body.active is not None:
        return change_account_state(auth, existing, body.active)
    if not settings.mock_mode:
        raise http_error(
            409,
            "email_verification_required",
            "Verify with email before changing product access. Nothing was saved.",
        )
    updated = update_user_flags(
        user_id,
        fms_access=body.fms_access,
        pos_access=body.pos_access,
        ecommerce_access=body.ecommerce_access,
        ems_access=body.ems_access,
    )
    if updated is None:
        raise http_error(404, "not_found", "Account was not found.")
    record_audit(auth["user"]["email"], "entitlement", existing["email"], "products updated")
    return user_public(updated)


@app.get("/api/security/report")
def security_report() -> dict:
    if not settings.report_path.exists():
        raise http_error(
            404,
            "report_missing",
            "No security report has been generated yet. Run backend/run_security_tests.py.",
        )
    try:
        return json.loads(settings.report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise http_error(500, "report_invalid", "The security report file could not be read.") from exc
