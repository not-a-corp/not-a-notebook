"""What a run leaves in the database as it goes and when it ends: its events,
the assistant's message, and its final status and token counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.core.start_message_run import message_shape
from app.domain.llm import Usage
from app.domain.messages import Message

type RunStatus = Literal["succeeded", "awaiting_user", "failed", "cancelled", "timed_out"]


async def record_event(
    conn: AsyncConnection[Any],
    run_row_id: int,
    seq: int,
    event_type: str,
    event: dict[str, Any],
) -> None:
    """The whole envelope, exactly as it goes down the wire (see schema.sql)."""
    sql = """
        INSERT INTO run_events AS e (run_id, seq, type, event)
        VALUES (%(run_id)s, %(seq)s, %(type)s, %(event)s)
    """

    params: dict[str, Any] = {
        "run_id": run_row_id,
        "seq": seq,
        "type": event_type,
        "event": Jsonb(event),
    }

    await conn.execute(sql, params)


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


@dataclass(frozen=True)
class Finished:
    wall_ms: int


async def finish_run(
    conn: AsyncConnection[Any],
    run_row_id: int,
    status: RunStatus,
    usage: Usage,
) -> Finished:
    """Closes the run — only if it is still running: one closed already, as
    abandoned by a restart, keeps the status it was given."""
    sql = """
        UPDATE runs r
           SET status = %(status)s,
               finished_at = now(),
               tokens_in = %(tokens_in)s,
               tokens_out = %(tokens_out)s,
               tokens_reasoning = %(tokens_reasoning)s
         WHERE r.id = %(run_id)s
           AND r.status = 'running'
        RETURNING (extract(epoch FROM r.finished_at - r.started_at) * 1000)::int AS wall_ms
    """

    params: dict[str, Any] = {
        "status": status,
        "tokens_in": usage.input_tokens,
        "tokens_out": usage.output_tokens,
        "tokens_reasoning": usage.reasoning_tokens,
        "run_id": run_row_id,
    }

    touch_sql = """
        UPDATE conversations c
           SET updated_at = now()
          FROM runs r
         WHERE r.id = %(run_id)s
           AND c.id = r.conversation_id
    """

    touch_params = {"run_id": run_row_id}

    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()
        await cur.execute(touch_sql, touch_params)

    wall_ms = 0
    if row is not None:
        wall_ms = row["wall_ms"]

    return Finished(wall_ms=wall_ms)
