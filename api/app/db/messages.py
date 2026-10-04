"""A conversation's messages: stored, and shown as api.md shows them."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.domain.messages import GroundingResult, Message, MessageKind


async def store_reply(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    run_row_id: int,
    run_id: UUID,
    text: str,
    kind: MessageKind,
    grounding: GroundingResult | None,
) -> Message:
    """The answer, or the question, as the conversation's next message."""
    sql = """
        INSERT INTO messages AS m (conversation_id, run_id, role, text, kind, grounding)
        VALUES (%(conversation_id)s, %(run_id)s, 'assistant', %(text)s, %(kind)s, %(grounding)s)
        RETURNING m.external_id,
                  m.created_at
    """

    params: dict[str, Any] = {
        "conversation_id": conversation_row_id,
        "run_id": run_row_id,
        "text": text,
        "kind": kind,
        "grounding": stored_grounding(grounding),
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    assert row is not None  # RETURNING on a successful INSERT

    return message_shape(
        row["external_id"], "assistant", run_id, text, kind, grounding, row["created_at"]
    )


def stored_grounding(grounding: GroundingResult | None) -> Jsonb | None:
    if grounding is None:
        return None

    return Jsonb(grounding.model_dump())


def grounding_of(stored: dict[str, Any] | None) -> GroundingResult | None:
    if stored is None:
        return None

    return GroundingResult.model_validate(stored)


def message_shape(
    message_id: UUID,
    role: Literal["user", "assistant"],
    run_id: UUID | None,
    text: str,
    kind: MessageKind | None,
    grounding: GroundingResult | None,
    created_at: datetime,
) -> Message:
    return Message(
        id=message_id,
        role=role,
        run_id=run_id,
        text=text,
        kind=kind,
        grounding=grounding,
        created_at=created_at,
    )
