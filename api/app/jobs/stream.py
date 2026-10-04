"""A run as Server-Sent Events: what is stored, then what happens, until
run.finished (events.md).

No event is lost between the two: the stream subscribes to the live events
*before* reading the stored ones, so an event written in between arrives both
ways, and the second copy is dropped by its seq. Replay and live are one sequence
with no gap and no repeat.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.db.runs import events_after
from app.jobs.broadcast import Broadcast

# Proxies drop a connection that stays silent; the model can think for longer.
KEEPALIVE_SECONDS = 15.0

LAST = "run.finished"


async def stream(
    pool: AsyncConnectionPool,
    broadcast: Broadcast,
    run_row_id: int,
    after_seq: int,
) -> AsyncIterator[str]:
    live = broadcast.subscribe(run_row_id)

    try:
        async with pool.connection() as conn:
            stored = await events_after(conn, run_row_id, after_seq)

        last = after_seq
        for event in stored:
            yield as_sse(event)
            last = event["seq"]

            if event["type"] == LAST:
                return

        while True:
            try:
                event = await asyncio.wait_for(live.get(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue

            if event["seq"] <= last:
                continue

            yield as_sse(event)
            last = event["seq"]

            if event["type"] == LAST:
                return
    finally:
        broadcast.unsubscribe(run_row_id, live)


def as_sse(event: dict[str, Any]) -> str:
    """`event:` and `type` both carry the name, `id:` is the seq that
    Last-Event-ID resumes after."""
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))

    return f"event: {event['type']}\nid: {event['seq']}\ndata: {data}\n\n"


def resume_after(last_event_id: str | None) -> int:
    """The seq to resume after. A header that is not a number is a fresh start —
    replaying from the beginning loses nothing."""
    if last_event_id is None:
        return 0

    try:
        seq = int(last_event_id)
    except ValueError:
        return 0

    return max(seq, 0)
