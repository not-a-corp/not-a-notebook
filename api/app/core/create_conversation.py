"""Starting a conversation. No kernel starts here; the first run starts it."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.core.conversation_row import to_conversation
from app.domain.conversations import Conversation, CreateConversationRequest
from app.domain.errors import ModelNotFound, Unauthenticated


async def create_conversation(
    conn: AsyncConnection[Any],
    user_id: UUID,
    request: CreateConversationRequest,
) -> Conversation:
    # A model is usable when it is the caller's or the instance's (user_id NULL).
    # Someone else's model is not found, the same as one that does not exist. The
    # INSERT happens only when a requested model was found, so a typo never
    # quietly makes a conversation with no model.
    sql = """
        WITH inserted AS (
            INSERT INTO conversations AS c (user_id, model_id, title)
            SELECT u.id,
                   m.id,
                   %(title)s
              FROM users u
              LEFT JOIN models m
                ON m.external_id = %(model_id)s
               AND (m.user_id = u.id OR m.user_id IS NULL)
             WHERE u.external_id = %(user_id)s
               AND (%(model_id)s::uuid IS NULL OR m.id IS NOT NULL)
            RETURNING c.external_id,
                      c.model_id,
                      c.title,
                      c.created_at,
                      c.updated_at
        )
        SELECT i.external_id AS id,
               i.title,
               m.external_id AS model_id,
               i.created_at,
               i.updated_at
          FROM inserted i
          LEFT JOIN models m
            ON m.id = i.model_id
    """

    params: dict[str, Any] = {
        "user_id": user_id,
        "model_id": request.model_id,
        "title": request.title,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None and request.model_id is not None:
        raise ModelNotFound

    # No model asked for, and still nothing inserted: the token's user is gone.
    if row is None:
        raise Unauthenticated

    return to_conversation(row)
