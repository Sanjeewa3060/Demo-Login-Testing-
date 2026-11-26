"""SSO demo API. Authentication can use Asgardeo; product access is local."""

from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .asgardeo import (
    AsgardeoError,
    amr_from_claims,
    begin_authorization,
    email_from_claims,
    email_verified_flag,
    exchange_code,
    get_discovery,
    logout_url,
    take_state,
    validate_id_token,
)
from .config import settings
from .db import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
    list_users,
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


@app.get("/api/auth/login")
def asgardeo_login():
    if settings.mock_mode:
        return login_redirect("mock_mode")
    if not settings.asgardeo_configured:
        return login_redirect("not_configured")
    try:
        url, state = begin_authorization()
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
    verifier, nonce = stored
    try:
        token_set = exchange_code(code, verifier)
        claims = validate_id_token(token_set["id_token"], nonce)
    except AsgardeoError as exc:
        return login_redirect(exc.code)

    email = email_from_claims(claims)
    if email is None:
        return login_redirect("no_email")
    verified = email_verified_flag(claims)
    user = upsert_asgardeo_user(email, claims)
    if user is None:
        return login_redirect("invalid_callback")
    if verified == "false":
        return login_redirect("email_unverified")
    if not user["active"]:
        return login_redirect("account_inactive")

    response = RedirectResponse(frontend("/portal"), status_code=302)
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


@app.get("/api/admin/customers")
def admin_customers(request: Request) -> dict:
    auth = read_auth(request)
    require_admin(auth)
    return {"accounts": [user_public(row) for row in list_users()]}


@app.patch("/api/admin/customers/{user_id}")
def admin_update_customer(user_id: int, body: AccountPatch, request: Request) -> dict:
    auth = read_auth(request)
    require_admin(auth)
    if body.fms_access is None and body.pos_access is None and body.active is None:
        raise http_error(400, "no_changes", "No changes were submitted.")
    existing = get_user_by_id(user_id)
    if existing is None:
        raise http_error(404, "not_found", "Account was not found.")
    if body.active is False and user_id == auth["user"]["id"]:
        raise http_error(
            400,
            "cannot_deactivate_self",
            "You cannot deactivate the account you are signed in with.",
        )
    updated = update_user_flags(
        user_id,
        fms_access=body.fms_access,
        pos_access=body.pos_access,
        active=body.active,
    )
    if updated is None:
        raise http_error(404, "not_found", "Account was not found.")
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
