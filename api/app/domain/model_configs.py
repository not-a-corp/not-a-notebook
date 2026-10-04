"""A configured model: a provider, an endpoint, a model name and a dialect.

From one of two places (decision 6):

| `source` | Scope | Who sets it |
| --- | --- | --- |
| `environment` | every user on the instance | the operator, in `.env` |
| `user` | that user only | the user, through /models |

The key is never returned — `key_hint` shows its last four characters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

type Adapter = Literal["anthropic", "openai_responses", "openai_compatible"]
type Dialect = Literal["tools", "text"]
type Source = Literal["environment", "user"]

# The models table's columns.
MAX_NAME_LENGTH = 100
MAX_MODEL_LENGTH = 255
MAX_URL_LENGTH = 2000
MAX_KEY_LENGTH = 1000


def check_base_url(value: str | None) -> str | None:
    if value is None:
        return None

    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("base_url must be an http or https URL")

    return value


class CreateModelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    adapter: Adapter
    base_url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    model: str = Field(min_length=1, max_length=MAX_MODEL_LENGTH)
    dialect: Dialect
    api_key: str | None = Field(default=None, min_length=1, max_length=MAX_KEY_LENGTH)

    _check_base_url = field_validator("base_url")(check_base_url)

    @model_validator(mode="after")
    def compatible_needs_a_base_url(self) -> Self:
        if self.adapter == "openai_compatible" and self.base_url is None:
            raise ValueError("an openai_compatible model needs a base_url")

        return self


class UpdateModelRequest(BaseModel):
    """Only the fields sent change. `api_key: null` removes the key; `base_url:
    null` removes the URL, which an openai_compatible model refuses."""

    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    adapter: Adapter | None = None
    base_url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    model: str | None = Field(default=None, min_length=1, max_length=MAX_MODEL_LENGTH)
    dialect: Dialect | None = None
    api_key: str | None = Field(default=None, min_length=1, max_length=MAX_KEY_LENGTH)

    _check_base_url = field_validator("base_url")(check_base_url)

    @model_validator(mode="after")
    def required_fields_are_never_null(self) -> Self:
        for field in ("name", "adapter", "model", "dialect"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class ModelConfig(BaseModel):
    id: UUID
    name: str
    source: Source
    adapter: Adapter
    base_url: str | None
    model: str
    dialect: Dialect
    key_hint: str | None


class ModelList(BaseModel):
    data: list[ModelConfig]


@dataclass(frozen=True)
class EnvironmentModel:
    """A model the operator declared in .env. Upserted by env_name on startup, so
    it keeps one id that conversations can point at; its key stays in the
    environment and is read from there on every call, never copied to a row."""

    env_name: str
    name: str
    adapter: Adapter
    base_url: str | None
    model: str
    dialect: Dialect
    api_key: str | None
