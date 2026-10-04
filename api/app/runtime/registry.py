"""The kernels this API process has running, one per conversation.

Whether a conversation's kernel runs is known here and nowhere else — not in the
database, by design (see schema.sql): every kernel dies with the process anyway,
and the reaper removes what a dead process left behind.

It also knows two things the next run needs to tell the model honestly:

- **when each kernel was last used**, so an idle one can be reaped — it costs RAM
  while nobody looks at it (decision 3). A kernel a run is holding is never idle.
- **why a kernel was stopped**, so the next run's `kernel.restarted` says `idle`,
  `requested` or `run_all` rather than the `lost` it would otherwise have to guess.

Works over the Runtime protocol, so it does not know it is Docker underneath.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from app.domain.runtime import Kernel, Runtime

log = logging.getLogger(__name__)

type StopReason = Literal["idle", "requested", "run_all", "died"]

# How often the idle reaper looks. Coarse on purpose: a kernel reaped a minute
# late costs a minute of RAM; one reaped early costs the user their variables.
REAP_INTERVAL_SECONDS = 60.0


class KernelRegistry:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.kernels: dict[UUID, Kernel] = {}
        # One lock per conversation, so two runs asking for the same cold kernel
        # at once start it once — and runs of different conversations never wait
        # on each other.
        self.locks: dict[UUID, asyncio.Lock] = {}
        self.holds: dict[UUID, int] = {}
        self.last_used: dict[UUID, float] = {}
        self.reasons: dict[UUID, StopReason] = {}

    async def kernel_for(self, session: UUID, files: str) -> Kernel:
        """The conversation's kernel, started on first use."""
        lock = self.locks.setdefault(session, asyncio.Lock())

        async with lock:
            kernel = self.kernels.get(session)
            if kernel is None:
                kernel = await self.runtime.start(session, files)
                self.kernels[session] = kernel

        self.last_used[session] = time.monotonic()
        return kernel

    @asynccontextmanager
    async def hold(self, session: UUID) -> AsyncIterator[None]:
        """For the length of a run: the kernel is in use, and not reaped."""
        self.holds[session] = self.holds.get(session, 0) + 1

        try:
            yield
        finally:
            self.holds[session] -= 1
            if self.holds[session] == 0:
                del self.holds[session]
            self.last_used[session] = time.monotonic()

    def running(self) -> set[UUID]:
        return set(self.kernels)

    async def interrupt(self, session: UUID) -> None:
        """KeyboardInterrupt in whatever the kernel runs. Its state survives."""
        kernel = self.kernels.get(session)
        if kernel is not None:
            await kernel.interrupt()

    async def stop(self, session: UUID, reason: StopReason | None = None) -> None:
        """Shuts the kernel down, if there is one — and remembers why, for the
        next run to say. Also how a dead kernel is forgotten."""
        kernel = self.kernels.pop(session, None)
        self.locks.pop(session, None)
        self.last_used.pop(session, None)

        if reason is not None:
            self.reasons[session] = reason

        if kernel is not None:
            await kernel.shutdown()

    def take_reason(self, session: UUID) -> StopReason | None:
        """Why the conversation's last kernel stopped, once: the run that reads it
        announces the restart, and the next run has nothing to announce."""
        return self.reasons.pop(session, None)

    async def stop_all(self) -> None:
        sessions = list(self.kernels)

        for session in sessions:
            await self.stop(session)

    async def reap_idle(self, idle_seconds: float, now: float | None = None) -> list[UUID]:
        """Stops every kernel no run holds and none has used for idle_seconds."""
        moment = now
        if moment is None:
            moment = time.monotonic()

        reaped = []
        for session in list(self.kernels):
            if session in self.holds:
                continue

            idle = moment - self.last_used.get(session, moment)
            if idle >= idle_seconds:
                await self.stop(session, reason="idle")
                reaped.append(session)

        return reaped


async def reap_idle_forever(registry: KernelRegistry, idle_seconds: float) -> None:
    """The lifespan's background reaper. Cancelled on shutdown."""
    while True:
        await asyncio.sleep(REAP_INTERVAL_SECONDS)

        try:
            reaped = await registry.reap_idle(idle_seconds)
        except Exception:
            log.exception("idle reaping failed; trying again next round")
            continue

        if reaped:
            log.info("reaped %(count)s idle kernels", {"count": len(reaped)})
