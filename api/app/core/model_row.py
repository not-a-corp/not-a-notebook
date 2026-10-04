"""A models row, as the API shows it — with a hint of its key, never the key.

Every query that feeds this selects id (the external one), name, env_name,
adapter, base_url, model, dialect and api_key_encrypted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.model_configs import ModelConfig, Source
from app.security.secrets import Cipher, key_hint


def to_model_config(
    row: dict[str, Any],
    cipher: Cipher,
    environment_keys: Mapping[str, str | None],
) -> ModelConfig:
    """environment_keys: each .env model's key by env_name — the only place an
    environment model's key exists."""
    env_name = row["env_name"]
    source: Source

    if env_name is not None:
        source = "environment"
        key = environment_keys.get(env_name)
    else:
        source = "user"
        key = stored_key(row, cipher)

    return ModelConfig(
        id=row["id"],
        name=row["name"],
        source=source,
        adapter=row["adapter"],
        base_url=row["base_url"],
        model=row["model"],
        dialect=row["dialect"],
        key_hint=key_hint(key),
    )


def stored_key(row: dict[str, Any], cipher: Cipher) -> str | None:
    encrypted = row["api_key_encrypted"]
    if encrypted is None:
        return None

    key: str = cipher.decrypt(encrypted)
    return key
