"""A conversation's kernel, as one run sees it — and the events about it.

kernel.starting / kernel.ready     none was running; one is starting
kernel.restarted (lost)            …and cells had run before, in a kernel that
                                   no longer exists: the model must be told
kernel.restarted (died)            emitted by the loop, which notices
"""

from __future__ import annotations

import time
from uuid import UUID

from app.domain.agent import Emit
from app.domain.runtime import Kernel
from app.runtime.registry import KernelRegistry


class ConversationKernels:
    def __init__(
        self,
        registry: KernelRegistry,
        conversation_id: UUID,
        folder: str,
        emit: Emit,
        cells_have_run: bool,
    ) -> None:
        self.registry = registry
        self.conversation_id = conversation_id
        self.folder = folder
        self.emit = emit
        self.cells_have_run = cells_have_run
        # Set when this run had to start a kernel for cells that ran in another.
        self.lost = False

    async def current(self) -> Kernel:
        if self.conversation_id in self.registry.running():
            return await self.registry.kernel_for(self.conversation_id, self.folder)

        kernel = await self.start()

        if self.cells_have_run:
            self.lost = True
            await self.emit("kernel.restarted", {"reason": "lost"})

        return kernel

    async def replace(self) -> Kernel:
        """After the kernel died — `kernel.restarted (died)` is already out."""
        await self.registry.stop(self.conversation_id)

        return await self.start()

    async def start(self) -> Kernel:
        await self.emit("kernel.starting", {})
        started = time.monotonic()

        kernel = await self.registry.kernel_for(self.conversation_id, self.folder)

        startup_ms = int((time.monotonic() - started) * 1000)
        await self.emit("kernel.ready", {"startup_ms": startup_ms})

        return kernel
