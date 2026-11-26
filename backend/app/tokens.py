"""Application session JWTs. Product permissions are not stored in the token."""

from __future__ import annotations

from datetime import datetime, timezone

import jwt

from .config import settings


def encode_token(user_id: int, jti: str, auth_mode: str, expires_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(user_id),
        "jti": jti,
        "mode": auth_mode,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.session_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "jti"]},
    )
