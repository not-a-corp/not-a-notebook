"""From a model the user can pick to an endpoint an adapter can call.

The key comes out in the clear here, and only here: an instance model's from the
environment, a user model's decrypted. The endpoint lives for one call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.models import stored_key
from app.domain.errors import ModelNotFound
from app.providers.endpoint import Endpoint
from app.security.secrets import Cipher


async def resolve_endpoint(
    conn: AsyncConnection[Any],
    user_id: UUID,
    model_id: UUID,
    cipher: Cipher,
    environment_keys: Mapping[str, str | None],
) -> Endpoint:
    sql = """
        SELECT m.env_name,
               m.adapter,
               m.base_url,
               m.model,
               m.dialect,
               m.api_key_encrypted
          FROM models m
          LEFT JOIN users u
            ON u.id = m.user_id
         WHERE m.external_id = %(model_id)s
           AND (m.user_id IS NULL OR u.external_id = %(user_id)s)
    """

    params = {
        "user_id": user_id,
        "model_id": model_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        raise ModelNotFound

    if row["env_name"] is not None:
        key = environment_keys.get(row["env_name"])
    else:
        key = stored_key(row, cipher)

    return Endpoint(
        adapter=row["adapter"],
        model=row["model"],
        dialect=row["dialect"],
        base_url=row["base_url"],
        api_key=key,
    )
