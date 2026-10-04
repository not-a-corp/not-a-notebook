"""Settings, read once from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings fills the fields from the environment, which mypy cannot
    # see: to it, this is a call missing a required argument.
    return Settings()  # type: ignore[call-arg]
