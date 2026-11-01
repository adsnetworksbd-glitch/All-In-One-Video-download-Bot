import json
import os
import re
from typing import Any, List, Optional
from urllib.parse import urlparse
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

STRICT_FIREBASE_HOST_REGEX = re.compile(
    r"^[a-z][a-z0-9-]{4,28}[a-z0-9](-default-rtdb)?\.(firebaseio\.com|[a-z0-9-]+\.firebasedatabase\.app)$",
    re.IGNORECASE
)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram bot API token")
    BOT_USERNAME: str = Field("AllInOneDownloaderBot", description="Bot Telegram handle")
    ADMIN_TELEGRAM_IDS: List[int] = Field(default_factory=list, description="Admin Telegram IDs")

    FIREBASE_DATABASE_URL: str = Field(..., description="Firebase Realtime Database URL")
    FIREBASE_CREDENTIALS_PATH: Optional[str] = Field(None, description="Path to service account JSON")
    FIREBASE_CREDENTIALS_RAW_JSON: Optional[str] = Field(None, description="Raw JSON string")

    ENVIRONMENT: str = Field("production")
    LOG_LEVEL: str = Field("INFO")
    DEFAULT_REQUEST_TIMEOUT: int = Field(15, ge=5, le=60)
    MAX_CONCURRENT_JOBS_PER_USER: int = Field(2, ge=1, le=5)
    USER_RATE_LIMIT_PER_MINUTE: int = Field(6, ge=1, le=60)
    CACHE_TTL_SECONDS: int = Field(60, ge=5, le=600)

    @field_validator("TELEGRAM_BOT_TOKEN")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        v = v.strip()
        if not v or ":" not in v:
            raise ValueError("TELEGRAM_BOT_TOKEN must be in format '123456:ABC-DEF...'")
        return v

    @field_validator("FIREBASE_DATABASE_URL")
    @classmethod
    def validate_firebase_url(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("FIREBASE_DATABASE_URL cannot be empty.")

        cleaned = v.strip()
        parsed = urlparse(cleaned)

        if parsed.scheme.lower() != "https":
            raise ValueError("FIREBASE_DATABASE_URL must strictly use HTTPS scheme.")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("FIREBASE_DATABASE_URL has an invalid or missing hostname.")

        if not STRICT_FIREBASE_HOST_REGEX.match(hostname):
            raise ValueError(
                f"Untrusted or malformed Firebase RTDB hostname: '{hostname}'. "
                "Must be an authentic Google Firebase domain (*.firebaseio.com or *.<region>.firebasedatabase.app)."
            )

        if parsed.username or parsed.password:
            raise ValueError("FIREBASE_DATABASE_URL must not contain embedded user credentials.")

        if parsed.port is not None:
            raise ValueError("FIREBASE_DATABASE_URL must not specify custom network ports.")

        if parsed.query:
            raise ValueError("FIREBASE_DATABASE_URL must not contain query parameters.")

        if parsed.fragment:
            raise ValueError("FIREBASE_DATABASE_URL must not contain URL fragments.")

        if parsed.path not in ("", "/"):
            raise ValueError(f"FIREBASE_DATABASE_URL must not contain custom paths: '{parsed.path}'")

        return f"https://{hostname}/"

    @field_validator("ADMIN_TELEGRAM_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        if v is None:
            return []
        if isinstance(v, list):
            return [int(x) for x in v if str(x).strip().isdigit()]
        if isinstance(v, (int, float)):
            return [int(v)]
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                return []
            if v_clean.isdigit() or (v_clean.startswith("-") and v_clean[1:].isdigit()):
                return [int(v_clean)]
            parts = [p.strip() for p in v_clean.split(",") if p.strip()]
            return [int(p) for p in parts if p.isdigit() or (p.startswith("-") and p[1:].isdigit())]
        return []

    def get_firebase_credentials(self) -> dict:
        if self.FIREBASE_CREDENTIALS_RAW_JSON:
            try:
                return json.loads(self.FIREBASE_CREDENTIALS_RAW_JSON)
            except Exception as e:
                raise ValueError(f"Invalid FIREBASE_CREDENTIALS_RAW_JSON: {e}")
        if self.FIREBASE_CREDENTIALS_PATH and os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
            with open(self.FIREBASE_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        raise ValueError("Firebase service account credentials missing.")


settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    global settings
    if settings is None:
        settings = AppSettings()
    return settings
