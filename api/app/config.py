"""Settings, read once from the environment.

Checked on the way in, so a misconfiguration stops the service at startup: a
missing or short `jwt_secret` instead of signing tokens anyone could forge, a
`secrets_key` that is not 32 bytes instead of storing keys no one can read back,
and half an OAuth app or half a model instead of a button that fails every time.
"""

from __future__ import annotations

import socket
from functools import lru_cache
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.model_configs import MAX_NAME_LENGTH, Dialect, EnvironmentModel, check_base_url
from app.oauth.providers import OAuthApp
from app.security.secrets import decode_key

# HS256 signs with HMAC-SHA256, and a key shorter than the hash's 32 bytes is the
# weakest link in it.
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    # 32 bytes, base64. Encrypts the provider keys users store; never in the
    # database, and backed up apart from it (decision 5).
    secrets_key: str
    registration_open: bool = True

    # Where a browser reaches this instance. OAuth redirect URIs are built from
    # it, so it must be what was registered with each provider.
    public_url: str = "http://localhost:3000"

    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None

    # Models the operator offers to every user (decision 6): one per provider,
    # each enabled by its variables. Their keys stay here, never in a row.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_compatible_base_url: str | None = None
    openai_compatible_model: str | None = None
    openai_compatible_api_key: str | None = None
    openai_compatible_dialect: Dialect = "text"

    # The kernels: the image they run, the container runtime (runsc for gVisor),
    # and what each one may use. The wall time is per execution, not per kernel.
    sandbox_image: str = "not-a-notebook-sandbox"
    sandbox_runtime: str = "runc"
    kernel_memory_mb: int = 2048
    kernel_cpus: float = 1.0
    kernel_pids: int = 256
    execution_timeout_seconds: float = 300

    # Uploaded files: where the API keeps them, and the Docker volume that holds
    # that directory — kernels mount their conversation's part of it at /data.
    files_root: str = "/var/lib/not-a-notebook/files"
    files_volume: str = "not-a-notebook-files"
    max_upload_mb: int = 100

    # The container this API runs in, which joins each kernel's network. Inside
    # a container the hostname is its id, so this only needs setting when the
    # hostname has been changed.
    api_container: str = Field(default_factory=socket.gethostname)

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

    @field_validator("secrets_key")
    @classmethod
    def check_secrets_key(cls, value: str) -> str:
        decode_key(value)
        return value

    # Compose passes an unset variable through as an empty string.
    @field_validator(
        "google_client_id",
        "google_client_secret",
        "github_client_id",
        "github_client_secret",
        "anthropic_api_key",
        "openai_api_key",
        "openai_model",
        "openai_compatible_base_url",
        "openai_compatible_model",
        "openai_compatible_api_key",
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

    @model_validator(mode="after")
    def check_environment_models(self) -> Self:
        # Half a model is a typo, not a choice: stop at startup rather than show a
        # model that cannot answer, or silently show none.
        if self.openai_api_key is not None and self.openai_model is None:
            raise ValueError("OPENAI_API_KEY is set: set OPENAI_MODEL too")

        compatible = (self.openai_compatible_base_url, self.openai_compatible_model)
        if (compatible[0] is None) != (compatible[1] is None):
            raise ValueError(
                "set both OPENAI_COMPATIBLE_BASE_URL and OPENAI_COMPATIBLE_MODEL, or neither"
            )

        if self.openai_compatible_base_url is not None:
            check_base_url(self.openai_compatible_base_url)

        return self

    def environment_models(self) -> list[EnvironmentModel]:
        models = []

        if self.anthropic_api_key is not None:
            claude = EnvironmentModel(
                env_name="ANTHROPIC",
                name="Claude",
                adapter="anthropic",
                base_url=None,
                model=self.anthropic_model,
                dialect="tools",
                api_key=self.anthropic_api_key,
            )
            models.append(claude)

        if self.openai_api_key is not None and self.openai_model is not None:
            openai = EnvironmentModel(
                env_name="OPENAI",
                name="OpenAI",
                adapter="openai_responses",
                base_url=None,
                model=self.openai_model,
                dialect="tools",
                api_key=self.openai_api_key,
            )
            models.append(openai)

        base_url = self.openai_compatible_base_url
        model = self.openai_compatible_model
        if base_url is not None and model is not None:
            # Named after the model: "qwen3:14b" says more than "OpenAI-compatible".
            compatible_model = EnvironmentModel(
                env_name="OPENAI_COMPATIBLE",
                name=model[:MAX_NAME_LENGTH],
                adapter="openai_compatible",
                base_url=base_url,
                model=model,
                dialect=self.openai_compatible_dialect,
                api_key=self.openai_compatible_api_key,
            )
            models.append(compatible_model)

        return models

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
