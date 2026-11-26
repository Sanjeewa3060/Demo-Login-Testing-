"""Runtime settings. Secrets stay in the environment, not in the React app."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _minutes(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        parsed = 15
    return min(max(parsed, 1), 24 * 60)


class Settings:
    def __init__(self) -> None:
        self.client_id = os.getenv("ASGARDEO_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("ASGARDEO_CLIENT_SECRET", "").strip()
        organization = os.getenv("ASGARDEO_ORGANIZATION", "").strip().strip("/")
        base = os.getenv("ASGARDEO_BASE_URL", "").strip().rstrip("/")
        if not base and organization:
            base = f"https://api.asgardeo.io/t/{organization}"
        self.organization = organization
        self.base_url = base
        self.asgardeo_configured = bool(self.client_id and self.base_url)

        mode = os.getenv("MOCK_MODE", "auto").strip().lower()
        if mode not in {"auto", "true", "false"}:
            mode = "auto"
        self.mock_mode_setting = mode
        if mode == "true":
            self.mock_mode = True
        elif mode == "false":
            self.mock_mode = False
        else:
            self.mock_mode = not self.asgardeo_configured

        self.redirect_uri = os.getenv(
            "ASGARDEO_REDIRECT_URI",
            "http://localhost:5173/api/auth/callback",
        ).strip()
        self.post_logout_redirect_uri = os.getenv(
            "ASGARDEO_POST_LOGOUT_REDIRECT_URI",
            "http://localhost:5173/",
        ).strip()
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").strip().rstrip("/")
        self.admin_emails = {
            item.strip().lower()
            for item in os.getenv("ADMIN_EMAILS", "admin@demo.local").split(",")
            if item.strip()
        }
        self.session_secret = os.getenv("SESSION_SECRET", "").strip() or "dev-only-insecure-secret"
        self.session_secret_is_placeholder = self.session_secret in {
            "dev-only-insecure-secret",
            "replace-with-a-long-random-string",
        }
        self.session_minutes = _minutes(os.getenv("SESSION_MINUTES", "15"))
        self.demo_password = os.getenv("DEMO_PASSWORD", "DemoPass123!")
        raw_db = os.getenv("DATABASE_PATH", "").strip()
        self.database_path = raw_db or str(BACKEND_DIR / "demo.db")
        self.cookie_secure = _flag("COOKIE_SECURE")
        self.cookie_name = "portal_session"
        self.oauth_cookie_name = "portal_oauth_state"
        self.report_path = BACKEND_DIR / "security-report.json"
        self.jwt_issuer = "sso-demo"
        self.jwt_audience = "sso-demo-api"


settings = Settings()
