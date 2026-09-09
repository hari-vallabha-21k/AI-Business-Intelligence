"""Application settings, loaded from the environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BI_", extra="ignore")

    # SQLite by default so the stack runs with no external services; point this at
    # postgresql+psycopg://... in any deployed environment.
    database_url: str = "sqlite:///./bi.db"
    secret_key: str = "dev-secret-change-me"
    access_token_minutes: int = 60 * 12

    max_upload_bytes: int = 50 * 1024 * 1024
    max_rows_per_dataset: int = 500_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
