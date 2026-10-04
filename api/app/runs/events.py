"""A run's events, numbered, timed and stored as they happen (events.md).

Every event is written to run_events before the next one is numbered, so the
stored stream never has a gap. Serving it live and replaying it is the stream's
job; this only makes sure there is something to serve.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.core.run_records import record_event


class RunEvents:
    def __init__(self, pool: AsyncConnectionPool, run_row_id: int) -> None:
        self.pool = pool
        self.run_row_id = run_row_id
        self.seq = 0
        self.started = time.monotonic()
        # Deltas and outputs can arrive from different tasks; seq must still count
        # one at a time.
        self.lock = asyncio.Lock()

    async def __call__(self, event_type: str, payload: dict[str, Any]) -> None:
        async with self.lock:
            self.seq += 1
            elapsed = round(time.monotonic() - self.started, 2)

            # The envelope first, then the payload: the order events.md shows.
            event: dict[str, Any] = {"seq": self.seq, "t": elapsed, "type": event_type}
            for name, value in payload.items():
                event[name] = value

            async with self.pool.connection() as conn:
                await record_event(conn, self.run_row_id, self.seq, event_type, event)
