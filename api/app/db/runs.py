"""A run in the database: starting one, its events as they are stored and read,
and its final status and token counts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection, errors
from psycopg.types.json import Jsonb

from app.domain.errors import ConversationBusy
from app.domain.llm import Usage

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


async def events_after(
    conn: AsyncConnection[Any],
    run_row_id: int,
    after_seq: int,
) -> list[dict[str, Any]]:
    """The stored events past a seq, in order — a range scan on the primary key,
    which is why seq is a column and not only inside the JSON (schema.sql)."""
    sql = """
        SELECT e.event
          FROM run_events e
         WHERE e.run_id = %(run_id)s
           AND e.seq > %(after)s
         ORDER BY e.seq
    """

    params = {
        "run_id": run_row_id,
        "after": after_seq,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    events = []
    for row in rows:
        events.append(row["event"])

    return events


@dataclass(frozen=True)
class StartedRun:
    run_row_id: int
    run_id: UUID
    conversation_row_id: int


async def start_run(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    kind: str,
) -> StartedRun:
    """A run that executes code but asks no model: a cell, or Run all. Refused by
    the one-running-run index when another is in progress."""
    sql = """
        INSERT INTO runs AS r (conversation_id, kind)
        VALUES (%(conversation_id)s, %(kind)s)
        RETURNING r.id,
                  r.external_id
    """

    params: dict[str, Any] = {
        "conversation_id": conversation_row_id,
        "kind": kind,
    }

    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
    except errors.UniqueViolation as exc:
        raise ConversationBusy from exc

    assert row is not None  # RETURNING on a successful INSERT

    return StartedRun(
        run_row_id=row["id"],
        run_id=row["external_id"],
        conversation_row_id=conversation_row_id,
    )
