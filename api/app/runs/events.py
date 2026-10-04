"""A run's events, numbered, timed and stored as they happen (events.md).

Every event is written to run_events before the next one is numbered, so the
stored stream never has a gap. Serving it live and replaying it is the stream's
job (stream.py); this stores each event, then hands it to the live streams.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.core.run_records import record_event
from app.runs.broadcast import Broadcast


class RunEvents:
    def __init__(self, pool: AsyncConnectionPool, broadcast: Broadcast, run_row_id: int) -> None:
        self.pool = pool
        self.broadcast = broadcast
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

            # Stored first: a stream that misses this live still finds it replayed.
            self.broadcast.publish(self.run_row_id, event)
