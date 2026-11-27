"""SQLite storage for dummy accounts, sessions, and short-lived OIDC state."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

PBKDF2_ITERATIONS = 100_000

SEEDED_USERS = (
    ("customer.a@demo.local", "Customer A", "customer", 1, 0, 1),
    ("customer.b@demo.local", "Customer B", "customer", 1, 1, 1),
    ("customer.c@demo.local", "Customer C", "customer", 0, 1, 1),
    ("admin@demo.local", "Portal Admin", "admin", 1, 1, 1),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return secrets.compare_digest(digest.hex(), digest_hex)


def user_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "fms_access": bool(row["fms_access"]),
        "pos_access": bool(row["pos_access"]),
        "product1_access": bool(row["fms_access"]),
        "product2_access": bool(row["pos_access"]),
        "ecommerce_access": bool(row.get("ecommerce_access")),
        "ems_access": bool(row.get("ems_access")),
        "active": bool(row["active"]),
        "subject": row.get("subject"),
        "identity": "asgardeo" if row.get("subject") else "not_linked",
    }


@contextmanager
def connect():
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_salt TEXT,
                password_hash TEXT,
                role TEXT NOT NULL,
                fms_access INTEGER NOT NULL,
                pos_access INTEGER NOT NULL,
                active INTEGER NOT NULL,
                subject TEXT,
                ecommerce_access INTEGER NOT NULL DEFAULT 0,
                ems_access INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                jti TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                auth_mode TEXT NOT NULL,
                amr TEXT NOT NULL,
                email_verified TEXT NOT NULL,
                id_token TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                code_verifier TEXT NOT NULL,
                nonce TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT 'login',
                payload TEXT,
                user_id INTEGER
            )
            """
        )
        _ensure_column(conn, "oauth_states", "purpose", "TEXT NOT NULL DEFAULT 'login'")
        _ensure_column(conn, "oauth_states", "payload", "TEXT")
        _ensure_column(conn, "oauth_states", "user_id", "INTEGER")
        _ensure_column(conn, "users", "ecommerce_access", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "ems_access", "INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_email TEXT NOT NULL,
                action TEXT NOT NULL,
                target_email TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            now = iso(utcnow())
            for email, name, role, fms, pos, active in SEEDED_USERS:
                salt, digest = hash_password(settings.demo_password)
                conn.execute(
                    """
                    INSERT INTO users (
                        email, display_name, password_salt, password_hash, role,
                        fms_access, pos_access, active, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (email, name, salt, digest, role, fms, pos, active, now),
                )


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _copy(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def get_user_by_subject(subject: str) -> dict | None:
    if not subject:
        return None
    with connect() as conn:
        return _copy(conn.execute("SELECT * FROM users WHERE subject = ?", (subject,)).fetchone())


def get_user_by_email(email: str) -> dict | None:
    with connect() as conn:
        return _copy(conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone())


def get_user_by_id(user_id: int) -> dict | None:
    with connect() as conn:
        return _copy(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def list_users() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM users
            ORDER BY CASE role WHEN 'customer' THEN 0 ELSE 1 END, id
            """
        ).fetchall()
        return [_copy(row) for row in rows]


def create_company_account(
    email: str,
    display_name: str,
    password: str,
    fms_access: bool,
    pos_access: bool,
) -> dict | None:
    """Create a company login. Access flags are the products that company paid for."""
    salt, digest = hash_password(password)
    try:
        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (
                    email, display_name, password_salt, password_hash, role,
                    fms_access, pos_access, active, created_at
                ) VALUES (?, ?, ?, ?, 'customer', ?, ?, 1, ?)
                """,
                (
                    email.strip().lower(),
                    display_name.strip(),
                    salt,
                    digest,
                    int(fms_access),
                    int(pos_access),
                    iso(utcnow()),
                ),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    created = get_user_by_id(int(user_id))
    if created is None:
        raise RuntimeError("Company account insert did not persist.")
    return created


def create_user(
    email: str,
    display_name: str,
    role: str,
    fms_access: bool,
    pos_access: bool,
    active: bool,
    subject: str | None = None,
) -> dict:
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO users (
                email, display_name, role, fms_access, pos_access, active, subject, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email.strip().lower(),
                display_name,
                role,
                int(fms_access),
                int(pos_access),
                int(active),
                subject,
                iso(utcnow()),
            ),
        )
        user_id = cur.lastrowid
    created = get_user_by_id(int(user_id))
    if created is None:
        raise RuntimeError("User insert did not persist.")
    return created


def set_password(user_id: int, password: str) -> None:
    salt, digest = hash_password(password)
    with connect() as conn:
        conn.execute(
            "UPDATE users SET password_salt = ?, password_hash = ? WHERE id = ?",
            (salt, digest, user_id),
        )


def update_subject(user_id: int, subject: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET subject = ? WHERE id = ?", (subject, user_id))


def save_entitlement(
    email: str,
    display_name: str,
    subject: str | None,
    fms_access: bool,
    pos_access: bool,
    ecommerce_access: bool,
    ems_access: bool,
) -> dict | None:
    """Store KAIONEX product entitlements. This does not store a password."""
    email = email.strip().lower()
    existing = get_user_by_email(email)
    if existing is not None:
        with connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET display_name = ?, subject = COALESCE(?, subject),
                    fms_access = ?, pos_access = ?, ecommerce_access = ?, ems_access = ?
                WHERE id = ?
                """,
                (
                    display_name.strip(),
                    subject,
                    int(fms_access),
                    int(pos_access),
                    int(ecommerce_access),
                    int(ems_access),
                    existing["id"],
                ),
            )
        return get_user_by_id(existing["id"])
    try:
        with connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (
                    email, display_name, role, fms_access, pos_access,
                    ecommerce_access, ems_access, active, subject, created_at
                ) VALUES (?, ?, 'customer', ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    email,
                    display_name.strip(),
                    int(fms_access),
                    int(pos_access),
                    int(ecommerce_access),
                    int(ems_access),
                    subject,
                    iso(utcnow()),
                ),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    return get_user_by_id(int(user_id))


def record_audit(actor_email: str, action: str, target_email: str, detail: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO audit (actor_email, action, target_email, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor_email, action, target_email, detail[:400], iso(utcnow())),
        )


def list_audit(limit: int = 20) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_copy(row) for row in rows]


def delete_sessions_for_user(user_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def update_user_flags(
    user_id: int,
    fms_access: bool | None = None,
    pos_access: bool | None = None,
    ecommerce_access: bool | None = None,
    ems_access: bool | None = None,
    active: bool | None = None,
) -> dict | None:
    sets: list[str] = []
    values: list[object] = []
    if fms_access is not None:
        sets.append("fms_access = ?")
        values.append(int(fms_access))
    if pos_access is not None:
        sets.append("pos_access = ?")
        values.append(int(pos_access))
    if ecommerce_access is not None:
        sets.append("ecommerce_access = ?")
        values.append(int(ecommerce_access))
    if ems_access is not None:
        sets.append("ems_access = ?")
        values.append(int(ems_access))
    if active is not None:
        sets.append("active = ?")
        values.append(int(active))
    if sets:
        values.append(user_id)
        with connect() as conn:
            conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", values)
    return get_user_by_id(user_id)


def create_session(
    jti: str,
    user_id: int,
    expires_at: datetime,
    auth_mode: str,
    amr_json: str,
    email_verified: str,
    id_token: str | None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                jti, user_id, expires_at, created_at, auth_mode, amr, email_verified, id_token
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (jti, user_id, iso(expires_at), iso(utcnow()), auth_mode, amr_json, email_verified, id_token),
        )


def get_session(jti: str) -> dict | None:
    with connect() as conn:
        return _copy(conn.execute("SELECT * FROM sessions WHERE jti = ?", (jti,)).fetchone())


def delete_session(jti: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE jti = ?", (jti,))


def expire_session(jti: str, expires_at: datetime) -> None:
    with connect() as conn:
        conn.execute("UPDATE sessions SET expires_at = ? WHERE jti = ?", (iso(expires_at), jti))


def save_oauth_state(
    state: str,
    code_verifier: str,
    nonce: str,
    expires_at: datetime,
    purpose: str = "login",
    payload: str | None = None,
    user_id: int | None = None,
) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM oauth_states WHERE expires_at < ?", (iso(utcnow()),))
        conn.execute(
            """
            INSERT INTO oauth_states (
                state, code_verifier, nonce, expires_at, purpose, payload, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (state, code_verifier, nonce, iso(expires_at), purpose, payload, user_id),
        )


def pop_oauth_state(state: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM oauth_states WHERE state = ?", (state,)).fetchone()
        if row is not None:
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        return _copy(row)
