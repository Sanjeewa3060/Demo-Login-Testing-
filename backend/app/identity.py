"""WSO2 Asgardeo SCIM and session APIs.

The management client secret stays in this process. React never receives it.
Official operations used here:
- POST /oauth2/token with client_credentials
- GET/POST /scim2/Users and PATCH /scim2/Users/{id}
- DELETE /api/users/v1/{user-id}/sessions
"""

from __future__ import annotations

import logging
import time

import httpx

from .config import settings

logger = logging.getLogger("portal.identity")

USER_SCOPES = " ".join(
    (
        "internal_user_mgt_list",
        "internal_user_mgt_view",
        "internal_user_mgt_create",
        "internal_user_mgt_update",
        "internal_session_delete",
    )
)

NOT_CONFIGURED = (
    "WSO2 user management is not configured. Create a confidential Asgardeo application, "
    "authorize the SCIM user scopes, and set ASGARDEO_MANAGEMENT_CLIENT_ID and "
    "ASGARDEO_MANAGEMENT_CLIENT_SECRET. No identity was created and no password was stored."
)

_token: str | None = None
_token_until = 0.0


class IdentityError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def recovery_url() -> str | None:
    if not settings.organization or not settings.base_url:
        return None
    if "api.eu.asgardeo.io" in settings.base_url:
        host = "https://accounts.eu.asgardeo.io"
    else:
        host = "https://accounts.asgardeo.io"
    return f"{host}/t/{settings.organization}/accountrecoveryendpoint/recoveraccountrouter.do"


def _require_admin_app() -> None:
    if not settings.identity_admin_configured:
        raise IdentityError("not_configured", NOT_CONFIGURED)


def _token_value() -> str:
    global _token, _token_until
    _require_admin_app()
    now = time.time()
    if _token and now < _token_until:
        return _token
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{settings.base_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.management_client_id,
                    "client_secret": settings.management_client_secret,
                    "scope": USER_SCOPES,
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Asgardeo token request failed: %s", type(exc).__name__)
        raise IdentityError(
            "asgardeo_unavailable",
            "WSO2 Asgardeo could not be reached. Nothing was saved.",
        ) from exc
    if response.status_code != 200:
        logger.warning("Asgardeo management token returned HTTP %s", response.status_code)
        raise IdentityError(
            "not_configured",
            "WSO2 rejected the management application token. Check the client id, secret, and "
            "SCIM scopes. Nothing was saved.",
        )
    body = response.json()
    access = str(body.get("access_token") or "")
    if not access:
        raise IdentityError("not_configured", "WSO2 did not return a management access token.")
    expires_in = int(body.get("expires_in") or 60)
    _token = access
    _token_until = now + max(expires_in - 30, 15)
    return access


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token_value()}",
        "Accept": "application/scim+json",
    }


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    text = body.get("detail") or body.get("description") or body.get("error_description") or body.get("error")
    if not text and isinstance(body.get("schemas"), list):
        text = body.get("detail") or body.get("status")
    return f"HTTP {response.status_code}" + (f": {text}" if text else "")


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    headers = _headers()
    extra = kwargs.pop("headers", None)
    if extra:
        headers.update(extra)
    try:
        with httpx.Client(timeout=20) as client:
            return client.request(method, f"{settings.base_url}{path}", headers=headers, **kwargs)
    except IdentityError:
        raise
    except httpx.HTTPError as exc:
        logger.warning("Asgardeo %s %s failed: %s", method, path, type(exc).__name__)
        raise IdentityError(
            "asgardeo_unavailable",
            "WSO2 Asgardeo could not be reached. Nothing was saved.",
        ) from exc


def _safe_email(email: str) -> str:
    cleaned = email.strip().lower()
    if "@" not in cleaned or '"' in cleaned or "\\" in cleaned or " " in cleaned:
        raise IdentityError("invalid_email", "Enter one email address.")
    return cleaned


def find_user(email: str) -> dict | None:
    """Search the Asgardeo user store. Returns the SCIM user or None."""
    cleaned = _safe_email(email)
    for attribute in ("userName", "emails"):
        response = _request(
            "GET",
            "/scim2/Users",
            params={"filter": f'{attribute} eq "{cleaned}"', "count": "2"},
        )
        if response.status_code != 200:
            raise IdentityError("asgardeo_unavailable", f"WSO2 user search failed ({_detail(response)}).")
        resources = response.json().get("Resources") or []
        if resources:
            return resources[0]
    return None


def _name_parts(display_name: str) -> tuple[str, str]:
    parts = [part for part in display_name.strip().split() if part]
    if not parts:
        return "Customer", "Account"
    if len(parts) == 1:
        return parts[0][:60], "Customer"
    return parts[0][:60], " ".join(parts[1:])[:60]


def create_invited_user(email: str, display_name: str) -> dict:
    """Create one Asgardeo user and let WSO2 email the password setup link.

    The request does not include a password.
    """
    cleaned = _safe_email(email)
    given, family = _name_parts(display_name)
    response = _request(
        "POST",
        "/scim2/Users",
        headers={"Content-Type": "application/scim+json"},
        json={
            "schemas": [
                "urn:ietf:params:scim:schemas:core:2.0:User",
                "urn:scim:wso2:schema",
            ],
            "userName": cleaned,
            "name": {"givenName": given, "familyName": family},
            "emails": [{"primary": True, "value": cleaned}],
            "urn:scim:wso2:schema": {"askPassword": "true"},
        },
    )
    if response.status_code not in {200, 201}:
        raise IdentityError(
            "asgardeo_unavailable",
            f"WSO2 did not create the user ({_detail(response)}). No password was stored.",
        )
    body = response.json()
    if not body.get("id"):
        raise IdentityError("asgardeo_unavailable", "WSO2 created a user response without an id.")
    return body


def set_account_disabled(user_id: str, disabled: bool) -> None:
    """Disable or enable the Asgardeo account. Documented SCIM attribute accountDisabled."""
    response = _request(
        "PATCH",
        f"/scim2/Users/{user_id}",
        headers={"Content-Type": "application/scim+json"},
        json={
            "schemas": [
                "urn:ietf:params:scim:api:messages:2.0:PatchOp",
                "urn:scim:wso2:schema",
            ],
            "Operations": [
                {
                    "op": "replace",
                    "value": {"urn:scim:wso2:schema": {"accountDisabled": disabled}},
                }
            ],
        },
    )
    if response.status_code not in {200, 204}:
        code = "not_configured" if response.status_code in {400, 403} else "asgardeo_unavailable"
        raise IdentityError(
            code,
            "WSO2 did not change the account. Account disabling must be enabled for the organization. "
            f"({_detail(response)}) The KAIONEX entitlement was not changed.",
        )


def terminate_sessions(user_id: str) -> None:
    """Terminate Asgardeo sessions for this user. A missing session list is not a failure."""
    response = _request("DELETE", f"/api/users/v1/{user_id}/sessions")
    if response.status_code not in {200, 204, 404}:
        raise IdentityError(
            "asgardeo_unavailable",
            f"WSO2 did not terminate the user's sessions ({_detail(response)}).",
        )


def force_password_reset(user_id: str) -> None:
    """Ask WSO2 to email the user a password reset. No password is chosen here."""
    response = _request(
        "PATCH",
        f"/scim2/Users/{user_id}",
        headers={"Content-Type": "application/scim+json"},
        json={
            "schemas": [
                "urn:ietf:params:scim:api:messages:2.0:PatchOp",
                "urn:scim:wso2:schema",
            ],
            "Operations": [
                {
                    "op": "add",
                    "value": {"urn:scim:wso2:schema": {"forcePasswordReset": True}},
                }
            ],
        },
    )
    if response.status_code not in {200, 204}:
        raise IdentityError(
            "asgardeo_unavailable",
            f"WSO2 did not start the password reset ({_detail(response)}).",
        )
