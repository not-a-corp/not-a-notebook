"""One conversation, with everything its screen shows."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.core.conversation_row import kernel_state
from app.domain.conversations import ConversationDetail
from app.domain.errors import ConversationNotFound


async def get_conversation(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
) -> ConversationDetail:
    # At most one run is 'running' per conversation — a unique index says so —
    # so the subquery returns one row or none.
    sql = """
        SELECT c.external_id AS id,
               c.title,
               m.external_id AS model_id,
               (
                   SELECT r.external_id
                     FROM runs r
                    WHERE r.conversation_id = c.id
                      AND r.status = 'running'
               ) AS active_run_id
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
          LEFT JOIN models m
            ON m.id = c.model_id
         WHERE u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
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

    return ConversationDetail(
        id=row["id"],
        title=row["title"],
        model_id=row["model_id"],
        kernel=kernel_state(),
        active_run_id=row["active_run_id"],
        files=[],
        messages=[],
        cells=[],
    )
