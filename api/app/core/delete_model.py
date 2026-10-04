"""Removing a model of your own.

Conversations that used it keep their history and lose their model (ON DELETE
SET NULL): their next message answers NO_MODEL_SELECTED until another is picked.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.core.update_model import explain_no_model


async def delete_model(conn: AsyncConnection[Any], user_id: UUID, model_id: UUID) -> None:
    sql = """
        DELETE FROM models m
         USING users u
         WHERE u.id = m.user_id
           AND u.external_id = %(user_id)s
           AND m.external_id = %(model_id)s
        RETURNING m.id
    """

    params = {
        "user_id": user_id,
        "model_id": model_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        await explain_no_model(conn, model_id)
