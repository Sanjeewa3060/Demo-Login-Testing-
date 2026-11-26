"""Server-side sessions. A valid JWT is not enough for product access."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, Response
from jwt import ExpiredSignatureError, InvalidTokenError

from .config import settings
from .db import (
    create_session,
    delete_session,
    expire_session,
    get_session,
    get_user_by_id,
    parse_iso,
    user_public,
    utcnow,
)
from .tokens import decode_token, encode_token


def http_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def apply_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.cookie_name,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.session_minutes * 60,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.cookie_name, path="/")


def issue_session(
    response: Response,
    user,
    auth_mode: str,
    amr: list[str],
    email_verified: str,
    id_token: str | None = None,
) -> None:
    expires_at = utcnow() + timedelta(minutes=settings.session_minutes)
    jti = secrets.token_urlsafe(24)
    token = encode_token(user["id"], jti, auth_mode, expires_at)
    create_session(
        jti=jti,
        user_id=user["id"],
        expires_at=expires_at,
        auth_mode=auth_mode,
        amr_json=json.dumps(amr),
        email_verified=email_verified,
        id_token=id_token,
    )
    apply_session_cookie(response, token)


def session_view(user, session) -> dict:
    try:
        amr = json.loads(session["amr"] or "[]")
    except json.JSONDecodeError:
        amr = []
    if not isinstance(amr, list):
        amr = []
    public = user_public(user)
    public.update(
        {
            "auth_mode": session["auth_mode"],
            "server_mode": "mock" if settings.mock_mode else "asgardeo",
            "session_expires_at": session["expires_at"],
            "amr": [str(item) for item in amr],
            "email_verified": session["email_verified"],
        }
    )
    return public


def read_auth(request: Request) -> dict:
    token = request.cookies.get(settings.cookie_name, "")
    if not token:
        raise http_error(401, "invalid_session", "Sign-in is required.")
    try:
        claims = decode_token(token)
    except ExpiredSignatureError:
        raise http_error(401, "session_expired", "The session has expired.") from None
    except InvalidTokenError:
        raise http_error(401, "invalid_token", "The session token is not valid.") from None

    session = get_session(str(claims.get("jti")))
    if session is None:
        raise http_error(401, "invalid_session", "The session is no longer active.")
    try:
        subject_id = int(claims["sub"])
    except (TypeError, ValueError):
        raise http_error(401, "invalid_token", "The session token is not valid.") from None
    if session["user_id"] != subject_id:
        raise http_error(401, "invalid_token", "The session token is not valid.")
    if parse_iso(session["expires_at"]) <= utcnow():
        raise http_error(401, "session_expired", "The session has expired.")

    user = get_user_by_id(session["user_id"])
    if user is None or not user["active"]:
        raise http_error(403, "account_inactive", "This account is deactivated.")
    return {"user": user, "session": session, "claims": claims}


def end_session(request: Request) -> str | None:
    """Delete the server session and return an Asgardeo ID token if one was stored."""
    token = request.cookies.get(settings.cookie_name, "")
    id_token = None
    if token:
        try:
            claims = decode_token(token)
        except ExpiredSignatureError:
            claims = None
            try:
                import jwt

                claims = jwt.decode(
                    token,
                    settings.session_secret,
                    algorithms=["HS256"],
                    audience=settings.jwt_audience,
                    issuer=settings.jwt_issuer,
                    options={"verify_exp": False, "require": ["sub", "jti"]},
                )
            except InvalidTokenError:
                claims = None
        except InvalidTokenError:
            claims = None
        if claims and claims.get("jti"):
            row = get_session(str(claims["jti"]))
            if row is not None:
                id_token = row["id_token"]
                delete_session(str(claims["jti"]))
    return id_token


def expire_current_session(request: Request) -> None:
    auth = read_auth(request)
    expire_session(auth["session"]["jti"], utcnow() - timedelta(seconds=5))
