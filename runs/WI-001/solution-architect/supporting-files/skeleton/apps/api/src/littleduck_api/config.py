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


@lru_cache
def get_settings() -> Settings:
    return Settings()
