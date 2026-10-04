"""Runs that outlive the request that started them.

The request answers 202 with the run's id; the work happens in an asyncio task in
this process (decision 12). No queue, no Redis. The tasks are kept here so they
are not garbage-collected mid-flight, and so shutdown can cancel them — a run
cancelled that way stays 'running' and is closed on the next startup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


class Background:
    def __init__(self) -> None:
        self.tasks: set[asyncio.Task[None]] = set()

    def spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def cancel_all(self) -> None:
        tasks = list(self.tasks)

        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
