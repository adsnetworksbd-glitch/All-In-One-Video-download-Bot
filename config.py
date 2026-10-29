import os, json
from typing import List, Optional, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
        if ":" not in v: raise ValueError("Invalid Telegram bot token format.")
        return v

    @field_validator("ADMIN_TELEGRAM_IDS", mode="before")
    @classmethod
    def parse_admins(cls, v: Any) -> List[int]:
        if isinstance(v, list): return [int(x) for x in v]
        if isinstance(v, str): return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int): return [v]
        return []

    def get_firebase_credentials(self) -> dict:
        if self.FIREBASE_CREDENTIALS_RAW_JSON:
            return json.loads(self.FIREBASE_CREDENTIALS_RAW_JSON)
        if self.FIREBASE_CREDENTIALS_PATH and os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
            with open(self.FIREBASE_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        raise ValueError("Firebase credentials missing.")

settings = None
def get_settings() -> AppSettings:
    global settings
    if settings is None: settings = AppSettings()
    return settings