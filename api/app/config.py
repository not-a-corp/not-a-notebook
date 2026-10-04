"""Settings, read once from the environment.

Checked on the way in, so a misconfiguration stops the service at startup: a
missing or short `jwt_secret` instead of signing tokens anyone could forge, and
half an OAuth app (an id without its secret, or the reverse) instead of a sign-in
button that fails every time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.oauth.providers import OAuthApp

# HS256 signs with HMAC-SHA256, and a key shorter than the hash's 32 bytes is the
# weakest link in it.
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    registration_open: bool = True

    # Where a browser reaches this instance. OAuth redirect URIs are built from
    # it, so it must be what was registered with each provider.
    public_url: str = "http://localhost:3000"

    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None

    @field_validator("jwt_secret")
    @classmethod
    def check_jwt_secret(cls, value: str) -> str:
        if len(value) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters")

        return value

    @field_validator("public_url")
    @classmethod
    def drop_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    # Compose passes an unset variable through as an empty string.
    @field_validator(
        "google_client_id",
        "google_client_secret",
        "github_client_id",
        "github_client_secret",
        mode="before",
    )
    @classmethod
    def empty_is_unset(cls, value: str | None) -> str | None:
        if value == "":
            return None

        return value

    @model_validator(mode="after")
    def check_oauth_pairs(self) -> Self:
        pairs = {
            "GOOGLE": (self.google_client_id, self.google_client_secret),
            "GITHUB": (self.github_client_id, self.github_client_secret),
        }

        for name, (client_id, client_secret) in pairs.items():
            if (client_id is None) != (client_secret is None):
                raise ValueError(f"set both {name}_CLIENT_ID and {name}_CLIENT_SECRET, or neither")

        return self

    def oauth_app(self, provider: str) -> OAuthApp | None:
        """The provider's credentials, or None when it is not enabled here."""
        pairs = {
            "google": (self.google_client_id, self.google_client_secret),
            "github": (self.github_client_id, self.github_client_secret),
        }

        client_id, client_secret = pairs.get(provider, (None, None))
        if client_id is None or client_secret is None:
            return None

        return OAuthApp(client_id=client_id, client_secret=client_secret)

    def oauth_providers(self) -> list[str]:
        enabled = []

        for provider in ("google", "github"):
            if self.oauth_app(provider) is not None:
                enabled.append(provider)

        return enabled


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings fills the fields from the environment, which mypy cannot
    # see: to it, this is a call missing a required argument.
    return Settings()  # type: ignore[call-arg]
