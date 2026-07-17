from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://littleduck:local-only@127.0.0.1:5432/littleduck"
    public_origin: str = "http://localhost:5173"
    admin_origin: str = "http://localhost:5174"
    user_session_cookie: str = "ld_user_session"
    admin_session_cookie: str = "ld_admin_session"
    api_key_encryption_key: str | None = Field(default=None, repr=False)
    generation_backend: str = "demo"
    model_context_window_tokens: int = 8192
    model_max_output_tokens: int = 1024
    prompt_overhead_tokens: int = 256
    recovery_retry_seconds: float = 1.0
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = Field(default="admin", repr=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
