"""The models a user can pick: the instance's, then their own, each by name."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.core.model_row import to_model_config
from app.domain.model_configs import ModelList
from app.security.secrets import Cipher


async def list_models(
    conn: AsyncConnection[Any],
    user_id: UUID,
    cipher: Cipher,
    environment_keys: Mapping[str, str | None],
) -> ModelList:
    # Not paginated: nobody configures fifty (api.md).
    sql = """
        SELECT m.external_id AS id,
               m.name,
               m.env_name,
               m.adapter,
               m.base_url,
               m.model,
               m.dialect,
               m.api_key_encrypted
          FROM models m
          LEFT JOIN users u
            ON u.id = m.user_id
         WHERE m.user_id IS NULL
            OR u.external_id = %(user_id)s
         ORDER BY m.user_id IS NOT NULL,
                  lower(m.name),
                  m.id
    """

    params = {"user_id": user_id}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    data = []
    for row in rows:
        model = to_model_config(row, cipher, environment_keys)
        data.append(model)

    return ModelList(data=data)
