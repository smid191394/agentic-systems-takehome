"""Runtime configuration, loaded from environment / .env (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fixtures_dir: Path = Path("fixtures")


@lru_cache
def get_settings() -> Settings:
    return Settings()
