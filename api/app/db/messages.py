"""A conversation's messages: stored, and shown as api.md shows them."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.messages import Message


async def store_reply(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    run_row_id: int,
    run_id: UUID,
    text: str,
) -> Message:
    """The answer, or the question, as the conversation's next message."""
    sql = """
        INSERT INTO messages AS m (conversation_id, run_id, role, text)
        VALUES (%(conversation_id)s, %(run_id)s, 'assistant', %(text)s)
        RETURNING m.external_id,
                  m.created_at
    """

    params: dict[str, Any] = {
        "conversation_id": conversation_row_id,
        "run_id": run_row_id,
        "text": text,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    assert row is not None  # RETURNING on a successful INSERT

    return message_shape(row["external_id"], "assistant", run_id, text, row["created_at"])


def message_shape(
    message_id: UUID,
    role: Literal["user", "assistant"],
    run_id: UUID | None,
    text: str,
    created_at: datetime,
) -> Message:
    return Message(id=message_id, role=role, run_id=run_id, text=text, created_at=created_at)
