"""Settings, read once from the environment.

`jwt_secret` is checked on the way in, so a missing or short secret stops the
service at startup instead of signing tokens anyone could forge.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# HS256 signs with HMAC-SHA256, and a key shorter than the hash's 32 bytes is the
# weakest link in it.
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    registration_open: bool = True

    @field_validator("jwt_secret")
    @classmethod
    def check_jwt_secret(cls, value: str) -> str:
        if len(value) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters")

        return value


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings fills the fields from the environment, which mypy cannot
    # see: to it, this is a call missing a required argument.
    return Settings()  # type: ignore[call-arg]
