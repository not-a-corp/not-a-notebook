"""Changing a model of your own. Only the fields sent change.

The instance's models are the operator's: they change in .env, never here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn
from uuid import UUID

from psycopg import AsyncConnection, errors

from app.core.model_row import to_model_config
from app.domain.errors import InvalidInput, ModelManagedByEnvironment, ModelNotFound
from app.domain.model_configs import ModelConfig, UpdateModelRequest
from app.security.secrets import Cipher


async def update_model(
    conn: AsyncConnection[Any],
    user_id: UUID,
    model_id: UUID,
    changes: UpdateModelRequest,
    cipher: Cipher,
    environment_keys: Mapping[str, str | None],
) -> ModelConfig:
    # A field not sent keeps its value through the CASE, so one statement covers
    # every combination. Only the caller's own rows match: the instance's rows
    # have no user_id, and someone else's have theirs.
    sql = """
        UPDATE models m
           SET name = CASE WHEN %(set_name)s THEN %(name)s ELSE m.name END,
               adapter = CASE WHEN %(set_adapter)s THEN %(adapter)s ELSE m.adapter END,
               base_url = CASE WHEN %(set_base_url)s THEN %(base_url)s ELSE m.base_url END,
               model = CASE WHEN %(set_model)s THEN %(model)s ELSE m.model END,
               dialect = CASE WHEN %(set_dialect)s THEN %(dialect)s ELSE m.dialect END,
               api_key_encrypted = CASE WHEN %(set_key)s THEN %(api_key_encrypted)s
                                        ELSE m.api_key_encrypted END
          FROM users u
         WHERE u.id = m.user_id
           AND u.external_id = %(user_id)s
           AND m.external_id = %(model_id)s
        RETURNING m.external_id AS id,
                  m.name,
                  m.env_name,
                  m.adapter,
                  m.base_url,
                  m.model,
                  m.dialect,
                  m.api_key_encrypted
    """

    fields = changes.model_fields_set

    encrypted = None
    if changes.api_key is not None:
        encrypted = cipher.encrypt(changes.api_key)

    params: dict[str, Any] = {
        "user_id": user_id,
        "model_id": model_id,
        "set_name": "name" in fields,
        "name": changes.name,
        "set_adapter": "adapter" in fields,
        "adapter": changes.adapter,
        "set_base_url": "base_url" in fields,
        "base_url": changes.base_url,
        "set_model": "model" in fields,
        "model": changes.model,
        "set_dialect": "dialect" in fields,
        "dialect": changes.dialect,
        "set_key": "api_key" in fields,
        "api_key_encrypted": encrypted,
    }

    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
    except errors.CheckViolation as exc:
        # models_compatible_has_base_url: the result of the change, not any one
        # field, is what is wrong — an openai_compatible model with no URL.
        raise InvalidInput("An openai_compatible model needs a base_url.") from exc

    if row is None:
        await explain_no_model(conn, model_id)

    return to_model_config(row, cipher, environment_keys)


async def explain_no_model(conn: AsyncConnection[Any], model_id: UUID) -> NoReturn:
    """Not the caller's: the instance's model is managed by the environment and
    says so — it is visible to everyone anyway. Anything else is not found."""
    sql = """
        SELECT 1
          FROM models m
         WHERE m.external_id = %(model_id)s
           AND m.user_id IS NULL
    """

    params = {"model_id": model_id}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        environment = await cur.fetchone()

    if environment is not None:
        raise ModelManagedByEnvironment

    raise ModelNotFound
