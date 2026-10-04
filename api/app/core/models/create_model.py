"""Adding a model of your own. Its key is encrypted before it reaches the SQL."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.models import to_model_config
from app.domain.errors import Unauthenticated
from app.domain.model_configs import CreateModelRequest, ModelConfig
from app.security.secrets import Cipher


async def create_model(
    conn: AsyncConnection[Any],
    user_id: UUID,
    request: CreateModelRequest,
    cipher: Cipher,
    environment_keys: Mapping[str, str | None],
) -> ModelConfig:
    sql = """
        INSERT INTO models AS m (user_id, name, adapter, base_url, model, dialect,
                                 api_key_encrypted)
        SELECT u.id,
               %(name)s,
               %(adapter)s,
               %(base_url)s,
               %(model)s,
               %(dialect)s,
               %(api_key_encrypted)s
          FROM users u
         WHERE u.external_id = %(user_id)s
        RETURNING m.external_id AS id,
                  m.name,
                  m.env_name,
                  m.adapter,
                  m.base_url,
                  m.model,
                  m.dialect,
                  m.api_key_encrypted
    """

    encrypted = None
    if request.api_key is not None:
        encrypted = cipher.encrypt(request.api_key)

    params: dict[str, Any] = {
        "user_id": user_id,
        "name": request.name,
        "adapter": request.adapter,
        "base_url": request.base_url,
        "model": request.model,
        "dialect": request.dialect,
        "api_key_encrypted": encrypted,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    # The token's user is gone.
    if row is None:
        raise Unauthenticated

    return to_model_config(row, cipher, environment_keys)
