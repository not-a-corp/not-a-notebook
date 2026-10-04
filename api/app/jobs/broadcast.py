"""Events as they happen, to whoever is streaming the run — in this process.

Decision 12: runs execute in the API process, so a run's live events only need to
reach streams in the same process. The day there is more than one process,
LISTEN/NOTIFY is the bridge; the stored events, which every stream replays first,
already are the source of truth.
"""

from __future__ import annotations

import asyncio
from typing import Any


class Broadcast:
    def __init__(self) -> None:
        self.listeners: dict[int, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, run_row_id: int) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.listeners.setdefault(run_row_id, set()).add(queue)

        return queue

    def unsubscribe(self, run_row_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
        queues = self.listeners.get(run_row_id)
        if queues is None:
            return

        queues.discard(queue)
        if not queues:
            del self.listeners[run_row_id]

    def publish(self, run_row_id: int, event: dict[str, Any]) -> None:
        for queue in self.listeners.get(run_row_id, set()):
            queue.put_nowait(event)
