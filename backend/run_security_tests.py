"""Run the demo's security checks and write backend/security-report.json.

API checks use an isolated database and forced mock mode. They do not call
WSO2 Asgardeo and must not be read as proof of Asgardeo OTP, MFA, or SSO.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent


class CheckError(Exception):
    pass


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def detail(response) -> dict:
    body = response.json()
    value = body.get("detail")
    return value if isinstance(value, dict) else {}


def main() -> int:
    temporary = tempfile.NamedTemporaryFile(prefix="sso-sec-", suffix=".db", delete=False)
    temporary.close()
    os.environ["DATABASE_PATH"] = temporary.name
    os.environ["MOCK_MODE"] = "true"
    os.environ["SESSION_SECRET"] = "security-test-secret-with-32-bytes-min"
    os.environ["SESSION_MINUTES"] = "15"
    os.environ["DEMO_PASSWORD"] = "DemoPass123!"
    os.environ["FRONTEND_URL"] = "http://localhost:5173"
    os.environ["ASGARDEO_REDIRECT_URI"] = "http://localhost:5173/api/auth/callback"

    sys.path.insert(0, str(BACKEND_DIR))
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.db import utcnow
    from app.tokens import encode_token
    from app.main import app

    env_file = read_dotenv(PROJECT_ROOT / ".env")
    tests: list[dict] = []

    def cookie(token: str) -> dict[str, str]:
        return {settings.cookie_name: token}

    def add(test_id: str, name: str, scope: str, status: str, evidence: str) -> None:
        tests.append(
            {
                "id": test_id,
                "name": name,
                "scope": scope,
                "status": status,
                "evidence": evidence,
            }
        )

    def check(test_id: str, name: str, scope: str, fn) -> None:
        try:
            add(test_id, name, scope, "pass", fn())
        except Exception as exc:
            add(test_id, name, scope, "fail", f"{type(exc).__name__}: {exc}")

    with TestClient(app) as client:
        def login(email: str, password: str | None = None) -> str:
            chosen = settings.demo_password if password is None else password
            response = client.post(
                "/api/auth/mock-login",
                json={"email": email, "password": chosen},
            )
            if response.status_code != 200:
                raise CheckError(f"{email} sign-in returned {response.status_code}: {response.text}")
            token = response.cookies.get(settings.cookie_name) or client.cookies.get(settings.cookie_name)
            if not token and "set-cookie" in response.headers:
                header = response.headers["set-cookie"]
                prefix = settings.cookie_name + "="
                if prefix in header:
                    token = header.split(prefix, 1)[1].split(";", 1)[0]
            client.cookies.clear()
            if not token:
                raise CheckError(f"{email} sign-in did not set a session cookie")
            return token

        def account_id(admin_token: str, email: str) -> int:
            response = client.get("/api/admin/customers", cookies=cookie(admin_token))
            expect(response.status_code == 200, f"admin list returned {response.status_code}")
            for account in response.json()["accounts"]:
                if account["email"] == email:
                    return account["id"]
            raise CheckError(f"{email} was not in the admin account list")

        def restore(admin_token: str, user_id: int, **flags) -> None:
            response = client.patch(
                f"/api/admin/customers/{user_id}",
                json=flags,
                cookies=cookie(admin_token),
            )
            expect(response.status_code == 200, f"restore returned {response.status_code}: {response.text}")

        def test_invalid_login() -> str:
            wrong = client.post(
                "/api/auth/mock-login",
                json={"email": "customer.a@demo.local", "password": "wrong-password"},
            )
            unknown = client.post(
                "/api/auth/mock-login",
                json={"email": "nobody@demo.local", "password": "wrong-password"},
            )
            expect(wrong.status_code == 401, f"wrong password returned {wrong.status_code}")
            expect(unknown.status_code == 401, f"unknown email returned {unknown.status_code}")
            expect(detail(wrong).get("code") == "invalid_credentials", "wrong password code mismatch")
            expect(detail(unknown).get("code") == "invalid_credentials", "unknown email code mismatch")
            expect(
                detail(wrong).get("message") == detail(unknown).get("message"),
                "the two failures used different messages",
            )
            return (
                "Local mock sign-in rejected a wrong password and an unknown email with the same "
                "401 invalid_credentials response. This did not contact Asgardeo."
            )

        def test_matrix() -> str:
            expected = (
                ("customer.a@demo.local", 200, 403),
                ("customer.b@demo.local", 200, 200),
                ("customer.c@demo.local", 403, 200),
            )
            lines = []
            for email, fms_status, pos_status in expected:
                token = login(email)
                for product, status in (("fms", fms_status), ("pos", pos_status)):
                    response = client.get(
                        f"/api/{product}/summary?{product}_access=true",
                        cookies=cookie(token),
                    )
                    expect(
                        response.status_code == status,
                        f"{email} {product} returned {response.status_code}: {response.text}",
                    )
                    if status == 403:
                        expect(detail(response).get("code") == "product_denied", f"{email} {product} code")
                        expect("WO-1042" not in response.text and "INV-2201" not in response.text, "leak")
                    else:
                        marker = "WO-1042" if product == "fms" else "INV-2201"
                        expect(marker in response.text, f"{email} {product} body missing dummy record")
                lines.append(f"{email} FMS {fms_status} POS {pos_status}")
            return (
                "Each customer signed in and called both product APIs. A query string claiming "
                "access was ignored. Results: " + "; ".join(lines) + "."
            )

        def test_shared_session() -> str:
            token = login("customer.b@demo.local")
            fms = client.get("/api/fms/summary", cookies=cookie(token))
            pos = client.get("/api/pos/summary", cookies=cookie(token))
            expect(fms.status_code == 200, f"FMS returned {fms.status_code}")
            expect(pos.status_code == 200, f"POS returned {pos.status_code}")
            return (
                "Customer B used one local session token for both FMS and POS. "
                "This is the demo's shared application session. It does not show an Asgardeo SSO session."
            )

        def test_invalid_token() -> str:
            garbage = client.get("/api/auth/me", cookies=cookie("not-a-jwt"))
            expect(garbage.status_code == 401, f"garbage token returned {garbage.status_code}")
            expect(detail(garbage).get("code") == "invalid_token", f"garbage code {detail(garbage)}")

            import jwt

            now = datetime.now(timezone.utc)
            forged = jwt.encode(
                {
                    "iss": settings.jwt_issuer,
                    "aud": settings.jwt_audience,
                    "sub": "1",
                    "jti": "forged",
                    "mode": "mock",
                    "iat": int(now.timestamp()),
                    "exp": int((now + timedelta(minutes=5)).timestamp()),
                },
                "wrong-secret",
                algorithm="HS256",
            )
            signed_wrong = client.get("/api/auth/me", cookies=cookie(forged))
            expect(signed_wrong.status_code == 401, "wrong signature status")
            expect(detail(signed_wrong).get("code") == "invalid_token", "wrong signature code")

            unknown = encode_token(1, "missing-session", "mock", utcnow() + timedelta(minutes=5))
            missing = client.get("/api/auth/me", cookies=cookie(unknown))
            expect(missing.status_code == 401, "unknown session status")
            expect(detail(missing).get("code") == "invalid_session", "unknown session code")
            return (
                "A random string and a JWT signed with the wrong secret returned invalid_token. "
                "A correctly signed JWT with no server session returned invalid_session."
            )

        def test_expiration() -> str:
            token = login("customer.a@demo.local")
            expired = client.post("/api/auth/expire", cookies=cookie(token))
            expect(expired.status_code == 200, f"expire returned {expired.status_code}")
            follow = client.get("/api/auth/me", cookies=cookie(token))
            expect(follow.status_code == 401, f"follow-up returned {follow.status_code}")
            expect(detail(follow).get("code") == "session_expired", f"follow-up code {detail(follow)}")

            past = encode_token(1, "already-expired", "mock", utcnow() - timedelta(seconds=30))
            old = client.get("/api/auth/me", cookies=cookie(past))
            expect(old.status_code == 401, "expired jwt status")
            expect(detail(old).get("code") == "session_expired", "expired jwt code")
            return (
                "Setting the server session expiry, while leaving the cookie in place, returned "
                "session_expired. A JWT whose exp is already in the past also returned session_expired."
            )

        def test_logout() -> str:
            token = login("customer.a@demo.local")
            before = client.get("/api/auth/me", cookies=cookie(token))
            expect(before.status_code == 200, "session was not active before logout")
            response = client.get("/api/auth/logout", cookies=cookie(token), follow_redirects=False)
            expect(response.status_code == 302, f"logout returned {response.status_code}")
            location = response.headers.get("location", "")
            expect(location.startswith(settings.frontend_url), f"logout location was {location}")
            after = client.get("/api/auth/me", cookies=cookie(token))
            expect(after.status_code == 401, f"old token returned {after.status_code}")
            expect(detail(after).get("code") == "invalid_session", f"old token code {detail(after)}")
            return (
                "Logout deleted the server session and redirected to the local portal. "
                "The same JWT was then rejected. Asgardeo end-session was not called."
            )

        def test_deactivation() -> str:
            admin = login("admin@demo.local")
            user = login("customer.b@demo.local")
            user_id = account_id(admin, "customer.b@demo.local")
            try:
                opened = client.get("/api/fms/summary", cookies=cookie(user))
                expect(opened.status_code == 200, "FMS was not available before deactivation")
                changed = client.patch(
                    f"/api/admin/customers/{user_id}",
                    json={"active": False},
                    cookies=cookie(admin),
                )
                expect(changed.status_code == 200, f"deactivate returned {changed.status_code}")
                blocked = client.get("/api/fms/summary", cookies=cookie(user))
                expect(blocked.status_code == 403, f"deactivated call returned {blocked.status_code}")
                expect(detail(blocked).get("code") == "account_inactive", "deactivated code")
            finally:
                restore(admin, user_id, active=True)
            return (
                "Customer B's existing JWT was still presented after an administrator deactivated "
                "the account. The API returned account_inactive. The account was activated again."
            )

        def test_deactivated_login() -> str:
            admin = login("admin@demo.local")
            user_id = account_id(admin, "customer.c@demo.local")
            try:
                changed = client.patch(
                    f"/api/admin/customers/{user_id}",
                    json={"active": False},
                    cookies=cookie(admin),
                )
                expect(changed.status_code == 200, "could not deactivate Customer C")
                response = client.post(
                    "/api/auth/mock-login",
                    json={"email": "customer.c@demo.local", "password": settings.demo_password},
                )
                expect(response.status_code == 403, f"login returned {response.status_code}")
                expect(detail(response).get("code") == "account_inactive", "login code")
            finally:
                restore(admin, user_id, active=True)
            return (
                "Customer C's correct dummy password was rejected with account_inactive while the "
                "account was deactivated. This check used the local mock authenticator."
            )

        def test_revocation() -> str:
            admin = login("admin@demo.local")
            user = login("customer.b@demo.local")
            user_id = account_id(admin, "customer.b@demo.local")
            try:
                changed = client.patch(
                    f"/api/admin/customers/{user_id}",
                    json={"fms_access": False},
                    cookies=cookie(admin),
                )
                expect(changed.status_code == 200, "could not revoke FMS")
                fms = client.get("/api/fms/summary", cookies=cookie(user))
                pos = client.get("/api/pos/summary", cookies=cookie(user))
                expect(fms.status_code == 403, f"FMS returned {fms.status_code}")
                expect(detail(fms).get("code") == "product_denied", "FMS code")
                expect(pos.status_code == 200, f"POS returned {pos.status_code}")
            finally:
                restore(admin, user_id, fms_access=True)
            return (
                "Customer B's current session lost FMS access as soon as the account flag changed. "
                "POS remained available. The JWT was not rewritten; the API read the database."
            )

        def test_admin_guard() -> str:
            token = login("customer.a@demo.local")
            listed = client.get("/api/admin/customers", cookies=cookie(token))
            edited = client.patch(
                "/api/admin/customers/1",
                json={"pos_access": True},
                cookies=cookie(token),
            )
            expect(listed.status_code == 403, f"list returned {listed.status_code}")
            expect(detail(listed).get("code") == "forbidden", "list code")
            expect(edited.status_code == 403, f"patch returned {edited.status_code}")
            expect(detail(edited).get("code") == "forbidden", "patch code")
            return "Customer A received forbidden from the admin list and from a product-access update."

        def test_callback_state() -> str:
            response = client.get(
                "/api/auth/callback?code=abc&state=not-the-browser-state",
                follow_redirects=False,
            )
            location = response.headers.get("location", "")
            expect(response.status_code == 302, f"callback returned {response.status_code}")
            expect("error=invalid_callback" in location, f"location was {location}")
            return (
                "The OIDC callback rejected a code whose state cookie was missing. "
                "No token request was sent."
            )

        def test_mock_switch() -> str:
            previous = settings.mock_mode
            settings.mock_mode = False
            try:
                response = client.post(
                    "/api/auth/mock-login",
                    json={"email": "admin@demo.local", "password": settings.demo_password},
                )
                expect(response.status_code == 404, f"mock login returned {response.status_code}")
                expect(detail(response).get("code") == "mock_disabled", "mock disabled code")
            finally:
                settings.mock_mode = previous
            return (
                "With the mock-mode flag turned off for one request, mock sign-in returned 404. "
                "The flag was restored. This does not prove the Asgardeo login succeeds."
            )

        check("invalid_login", "Invalid local sign-in is rejected", "application", test_invalid_login)
        check("product_matrix", "Product access matches the customer matrix", "application", test_matrix)
        check("shared_session", "One session can open both allowed apps", "application", test_shared_session)
        check("invalid_token", "Invalid session tokens are rejected", "application", test_invalid_token)
        check("session_expiration", "Expired sessions are rejected", "application", test_expiration)
        check("logout", "Logout makes the old session token unusable", "application", test_logout)
        check("user_deactivation", "Deactivation blocks an existing session", "application", test_deactivation)
        check(
            "deactivated_login",
            "A deactivated account cannot sign in",
            "application",
            test_deactivated_login,
        )
        check("product_revocation", "Revoked product access is enforced immediately", "application", test_revocation)
        check("admin_guard", "Customers cannot call the admin API", "application", test_admin_guard)
        check("oidc_state", "OIDC callback requires the browser state cookie", "application", test_callback_state)
        check("mock_switch", "Mock sign-in can be disabled", "application", test_mock_switch)

    hosted = (
        (
            "email_verification",
            "Email verification",
            "Asgardeo email verification was not completed. The automated run did not open a verification link or a hosted login page.",
        ),
        (
            "email_otp",
            "Email OTP",
            "Email OTP was not completed. Mock mode does not accept or imitate a one-time code, and no code was sent to Asgardeo.",
        ),
        (
            "totp_mfa",
            "TOTP MFA",
            "TOTP was not completed. The run did not enroll an authenticator or submit a real TOTP code to Asgardeo.",
        ),
        (
            "asgardeo_sso",
            "Asgardeo single sign-on",
            "A live Asgardeo session was not established, so SSO across a second Asgardeo login was not tested. The shared-session result above is only this demo's own cookie.",
        ),
        (
            "asgardeo_invalid_login",
            "Asgardeo rejects an invalid login",
            "A wrong password was not submitted to Asgardeo. The invalid-login result above covers only the local dummy authenticator.",
        ),
        (
            "asgardeo_logout",
            "Asgardeo logout",
            "The Asgardeo end-session endpoint was not called. The logout result above only deleted this demo's session.",
        ),
        (
            "asgardeo_session_expiry",
            "Asgardeo session expiration",
            "Asgardeo's own session lifetime was not observed. The expiration result above covers this demo's JWT and server session.",
        ),
    )
    for test_id, name, evidence in hosted:
        add(test_id, name, "asgardeo", "not_tested", evidence)

    client_id = env_file.get("ASGARDEO_CLIENT_ID", "").strip()
    organization = env_file.get("ASGARDEO_ORGANIZATION", "").strip().strip("/")
    base = env_file.get("ASGARDEO_BASE_URL", "").strip().rstrip("/")
    if not base and organization:
        base = f"https://api.asgardeo.io/t/{organization}"
    if not client_id or not base:
        add(
            "asgardeo_discovery",
            "Asgardeo discovery document",
            "asgardeo",
            "not_tested",
            "ASGARDEO_CLIENT_ID and the organization base URL are not set, so discovery was not requested.",
        )
    else:
        url = base + "/oauth2/token/.well-known/openid-configuration"
        try:
            response = httpx.get(url, timeout=15)
            if response.status_code != 200:
                add(
                    "asgardeo_discovery",
                    "Asgardeo discovery document",
                    "asgardeo",
                    "fail",
                    f"Discovery returned HTTP {response.status_code}. No login was attempted.",
                )
            else:
                document = response.json()
                missing = [
                    key
                    for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
                    if not document.get(key)
                ]
                if missing:
                    add(
                        "asgardeo_discovery",
                        "Asgardeo discovery document",
                        "asgardeo",
                        "fail",
                        "Discovery was missing: " + ", ".join(missing) + ".",
                    )
                else:
                    add(
                        "asgardeo_discovery",
                        "Asgardeo discovery document",
                        "asgardeo",
                        "pass",
                        f"Discovery returned issuer {document['issuer']}. This did not log anyone in and did not test OTP or MFA.",
                    )
        except Exception as exc:
            add(
                "asgardeo_discovery",
                "Asgardeo discovery document",
                "asgardeo",
                "fail",
                f"Discovery could not be reached ({type(exc).__name__}). No login was attempted.",
            )

    counts = {"pass": 0, "fail": 0, "not_tested": 0}
    for item in tests:
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    report = {
        "schema_version": 1,
        "title": "SSO demo security report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Application rows were executed against this demo's API in forced mock mode on an "
            "isolated database. A pass there does not prove WSO2 Asgardeo email verification, "
            "email OTP, TOTP, SSO, logout, or session expiry. Rows marked not_tested were not "
            "treated as passes."
        ),
        "runner": {
            "forced_mock_mode": True,
            "isolated_database": True,
            "asgardeo_login_attempted": False,
        },
        "project_env": {
            "mock_mode_setting": env_file.get("MOCK_MODE", "auto") or "auto",
            "asgardeo_client_configured": bool(client_id),
            "asgardeo_base_configured": bool(base),
        },
        "summary": counts,
        "tests": tests,
    }
    settings.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Report: {settings.report_path}")
    print(
        f"Passed {counts['pass']}, failed {counts['fail']}, not tested {counts['not_tested']}"
    )
    for item in tests:
        print(f"{item['status'].upper():11} {item['name']}")

    try:
        os.unlink(temporary.name)
    except OSError:
        pass
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
