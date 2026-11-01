import re, os, json
from urllib.parse import urlparse
from typing import Any, List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

STRICT_FIREBASE_HOST_REGEX = re.compile(
    r"^[a-z][a-z0-9-]{4,28}[a-z0-9](-default-rtdb)?\.(firebaseio\.com|[a-z0-9-]+\.firebasedatabase\.app)$",
    re.IGNORECASE
)

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Bot Token")
    BOT_USERNAME: str = Field("AllInOneDownloaderBot")
    ADMIN_TELEGRAM_IDS: List[int] = Field(default_factory=list)
    FIREBASE_DATABASE_URL: str = Field(...)
    FIREBASE_CREDENTIALS_PATH: Optional[str] = Field(None)
    FIREBASE_CREDENTIALS_RAW_JSON: Optional[str] = Field(None)
    ENVIRONMENT: str = Field("production")
    LOG_LEVEL: str = Field("INFO")
    DEFAULT_REQUEST_TIMEOUT: int = Field(15, ge=5, le=60)
    MAX_CONCURRENT_JOBS_PER_USER: int = Field(2, ge=1, le=5)
    USER_RATE_LIMIT_PER_MINUTE: int = Field(6, ge=1, le=60)
    CACHE_TTL_SECONDS: int = Field(60, ge=5, le=600)

    @field_validator("TELEGRAM_BOT_TOKEN")
    @classmethod
    def validate_token(cls, v: str) -> str:
        v = v.strip()
        if ":" not in v: raise ValueError("Invalid bot token.")
        return v

    @field_validator("FIREBASE_DATABASE_URL")
    @classmethod
    def validate_firebase_url(cls, v: str) -> str:
        cleaned = v.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme.lower() != "https": raise ValueError("Scheme must be HTTPS.")
        hostname = parsed.hostname
        if not hostname or not STRICT_FIREBASE_HOST_REGEX.match(hostname):
            raise ValueError(f"Untrusted host: {hostname}")
        if parsed.username or parsed.password or parsed.port is not None or parsed.query or parsed.fragment:
            raise ValueError("URL must not contain credentials, ports, query, or fragments.")
        if parsed.path not in ("", "/"): raise ValueError("URL must not contain custom paths.")
        return f"https://{hostname}/"

    def get_firebase_credentials(self) -> dict:
        if self.FIREBASE_CREDENTIALS_RAW_JSON: return json.loads(self.FIREBASE_CREDENTIALS_RAW_JSON)
        if self.FIREBASE_CREDENTIALS_PATH and os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
            with open(self.FIREBASE_CREDENTIALS_PATH, "r", encoding="utf-8") as f: return json.load(f)
        raise ValueError("Firebase credentials missing.")

settings = None
def get_settings() -> AppSettings:
    global settings
    if settings is None: settings = AppSettings()
    return settings