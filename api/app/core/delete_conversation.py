"""Deleting a conversation. There is no trash.

Its files, runs, events, messages and cells go with it, by ON DELETE CASCADE.
Stopping its kernel and removing its files from disk join this use case when the
kernel registry and the FileStore exist.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.errors import ConversationNotFound


async def delete_conversation(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    sql = """
        DELETE FROM conversations c
         USING users u
         WHERE u.id = c.user_id
           AND u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
        RETURNING c.id
    """

    params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        raise ConversationNotFound
