"""Renaming a conversation, or changing its model.

Changing the model mid-conversation is allowed: the new model reads the same
history and the same cells.
"""

from __future__ import annotations

from collections.abc import Set
from typing import Any, NoReturn
from uuid import UUID

from psycopg import AsyncConnection

from app.core.conversation_row import to_conversation
from app.domain.conversations import Conversation, UpdateConversationRequest
from app.domain.errors import ConversationNotFound, ModelNotFound


async def update_conversation(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
    changes: UpdateConversationRequest,
    running: Set[UUID],
) -> Conversation:
    # One statement for every combination of fields: a field not sent keeps its
    # value through the CASE, so the SQL never has to be assembled. The model
    # rule is create_conversation's — the caller's or the instance's, and a
    # requested model that is not found changes nothing.
    sql = """
        WITH updated AS (
            UPDATE conversations c
               SET title = CASE WHEN %(set_title)s THEN %(title)s ELSE c.title END,
                   model_id = CASE WHEN %(set_model)s THEN m.id ELSE c.model_id END
              FROM users u
              LEFT JOIN models m
                ON m.external_id = %(model_id)s
               AND (m.user_id = u.id OR m.user_id IS NULL)
             WHERE u.id = c.user_id
               AND u.external_id = %(user_id)s
               AND c.external_id = %(conversation_id)s
               AND (NOT %(set_model)s OR %(model_id)s::uuid IS NULL OR m.id IS NOT NULL)
            RETURNING c.external_id,
                      c.model_id,
                      c.title,
                      c.created_at,
                      c.updated_at
        )
        SELECT d.external_id AS id,
               d.title,
               m.external_id AS model_id,
               d.created_at,
               d.updated_at
          FROM updated d
          LEFT JOIN models m
            ON m.id = d.model_id
    """

    fields = changes.model_fields_set
    params: dict[str, Any] = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "set_title": "title" in fields,
        "title": changes.title,
        "set_model": "model_id" in fields,
        "model_id": changes.model_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        await explain_nothing_updated(conn, user_id, conversation_id)

    return to_conversation(row, running)


async def explain_nothing_updated(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
) -> NoReturn:
    """Zero rows is either "no such conversation" or "no such model". The
    conversation in the URL is the one the caller asked about, so it is the
    answer when both are wrong."""
    sql = """
        SELECT 1
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
         WHERE u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
    """

    params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        found = await cur.fetchone()

    if found is None:
        raise ConversationNotFound

    raise ModelNotFound
