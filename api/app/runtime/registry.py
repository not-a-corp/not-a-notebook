"""The kernels this API process has running, one per conversation.

Whether a conversation's kernel runs is known here and nowhere else — not in the
database, by design (see schema.sql): every kernel dies with the process anyway,
and the reaper removes what a dead process left behind.

Works over the Runtime protocol, so it does not know it is Docker underneath.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.domain.runtime import Kernel, Runtime


class KernelRegistry:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.kernels: dict[UUID, Kernel] = {}
        # One lock per conversation, so two runs asking for the same cold kernel
        # at once start it once — and runs of different conversations never wait
        # on each other.
        self.locks: dict[UUID, asyncio.Lock] = {}

    async def kernel_for(self, session: UUID, files: str) -> Kernel:
        """The conversation's kernel, started on first use."""
        lock = self.locks.setdefault(session, asyncio.Lock())

        async with lock:
            kernel = self.kernels.get(session)
            if kernel is None:
                kernel = await self.runtime.start(session, files)
                self.kernels[session] = kernel

        return kernel

    def running(self) -> set[UUID]:
        return set(self.kernels)

    async def stop(self, session: UUID) -> None:
        """Shuts the kernel down, if there is one. Also how a dead kernel is
        forgotten: its container is removed and the next use starts afresh."""
        kernel = self.kernels.pop(session, None)
        self.locks.pop(session, None)

        if kernel is not None:
            await kernel.shutdown()

    async def stop_all(self) -> None:
        sessions = list(self.kernels)

        for session in sessions:
            await self.stop(session)
