"""WSO2 Asgardeo OIDC authorization-code flow with PKCE.

The client secret, when one is configured, is sent only from this module.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from jwt import InvalidTokenError, PyJWKClient

from .config import settings
from .db import pop_oauth_state, save_oauth_state, utcnow

logger = logging.getLogger("portal.asgardeo")

_discovery: dict | None = None
_jwks: PyJWKClient | None = None


class AsgardeoError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def clear_discovery_cache() -> None:
    global _discovery, _jwks
    _discovery = None
    _jwks = None


def get_discovery() -> dict:
    global _discovery
    if not settings.asgardeo_configured:
        raise AsgardeoError("not_configured")
    if _discovery is not None:
        return _discovery
    url = f"{settings.base_url}/oauth2/token/.well-known/openid-configuration"
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("Asgardeo discovery failed: %s", type(exc).__name__)
        raise AsgardeoError("not_configured") from exc
    missing = [
        key
        for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
        if not data.get(key)
    ]
    if missing:
        logger.warning("Asgardeo discovery missing %s", ", ".join(missing))
        raise AsgardeoError("not_configured")
    _discovery = data
    return data


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def begin_authorization() -> tuple[str, str]:
    """Return the Asgardeo redirect URL and the state value stored for this browser."""
    discovery = get_discovery()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    save_oauth_state(state, verifier, nonce, utcnow() + timedelta(minutes=10))
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.client_id,
            "redirect_uri": settings.redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{discovery['authorization_endpoint']}?{query}", state


def take_state(state: str) -> tuple[str, str] | None:
    row = pop_oauth_state(state)
    if row is None:
        return None
    from .db import parse_iso

    if parse_iso(row["expires_at"]) <= utcnow():
        return None
    return row["code_verifier"], row["nonce"]


def exchange_code(code: str, code_verifier: str) -> dict:
    discovery = get_discovery()
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
        "client_id": settings.client_id,
        "code_verifier": code_verifier,
    }
    if settings.client_secret:
        form["client_secret"] = settings.client_secret
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(discovery["token_endpoint"], data=form)
    except Exception as exc:
        logger.warning("Asgardeo token request failed: %s", type(exc).__name__)
        raise AsgardeoError("token_exchange_failed") from exc
    if response.status_code != 200:
        logger.warning("Asgardeo token endpoint returned HTTP %s", response.status_code)
        raise AsgardeoError("token_exchange_failed")
    body = response.json()
    if not body.get("id_token"):
        logger.warning("Asgardeo token response did not include an ID token")
        raise AsgardeoError("token_exchange_failed")
    return body


def validate_id_token(id_token: str, nonce: str) -> dict:
    if id_token.count(".") != 2:
        raise AsgardeoError("invalid_callback")
    discovery = get_discovery()
    global _jwks
    if _jwks is None:
        _jwks = PyJWKClient(discovery["jwks_uri"])
    try:
        key = _jwks.get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=settings.client_id,
            issuer=discovery["issuer"],
            leeway=120,
            options={"require": ["exp", "iat", "sub"]},
        )
    except InvalidTokenError:
        logger.warning("Asgardeo ID token was rejected")
        raise AsgardeoError("invalid_callback") from None
    except Exception as exc:
        logger.warning("Asgardeo JWKS validation failed: %s", type(exc).__name__)
        raise AsgardeoError("invalid_callback") from exc

    token_nonce = str(claims.get("nonce") or "")
    if len(token_nonce) != len(nonce) or not secrets.compare_digest(token_nonce, nonce):
        raise AsgardeoError("invalid_callback")
    return claims


def email_from_claims(claims: dict) -> str | None:
    email = str(claims.get("email") or "").strip().lower()
    if "@" not in email:
        return None
    return email


def amr_from_claims(claims: dict) -> list[str]:
    raw = claims.get("amr") or []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def email_verified_flag(claims: dict) -> str:
    value = claims.get("email_verified", None)
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "not_asserted"


def logout_url(id_token: str) -> str | None:
    try:
        discovery = get_discovery()
    except AsgardeoError:
        return None
    endpoint = discovery.get("end_session_endpoint")
    if not endpoint:
        return None
    query = urlencode(
        {
            "id_token_hint": id_token,
            "post_logout_redirect_uri": settings.post_logout_redirect_uri,
            "state": secrets.token_urlsafe(18),
        }
    )
    return f"{endpoint}?{query}"
