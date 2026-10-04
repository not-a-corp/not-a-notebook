"""A conversation's kernel, as one run sees it — and the events about it.

kernel.starting / kernel.ready     none was running; one is starting
kernel.restarted (idle, requested,  …and cells had run before, in a kernel that
                 run_all, lost)    no longer exists: the model must be told. The
                                   reason is the registry's, or `lost` when it
                                   has none — the API restarted
kernel.restarted (died)            emitted by the loop, which notices
"""

from __future__ import annotations

import time
from uuid import UUID

from app.domain.agent import Emit
from app.domain.files import FileStore
from app.domain.runtime import Kernel
from app.runtime.registry import KernelRegistry


class ConversationKernels:
    def __init__(
        self,
        registry: KernelRegistry,
        store: FileStore,
        conversation_id: UUID,
        folder: str,
        emit: Emit,
        cells_have_run: bool,
    ) -> None:
        self.registry = registry
        self.store = store
        self.conversation_id = conversation_id
        self.folder = folder
        self.emit = emit
        self.cells_have_run = cells_have_run
        # Set when this run had to start a kernel for cells that ran in another.
        self.lost = False

    async def current(self) -> Kernel:
        if self.conversation_id in self.registry.running():
            return await self.registry.kernel_for(self.conversation_id, self.folder)

        # Taken whether or not it is announced: a reason left behind would be
        # announced by some later run, wrongly.
        reason = self.registry.take_reason(self.conversation_id)
        kernel = await self.start()

        if self.cells_have_run:
            self.lost = True
            await self.emit("kernel.restarted", {"reason": reason or "lost"})

        return kernel

    async def replace(self) -> Kernel:
        """After the kernel died — `kernel.restarted (died)` is already out."""
        await self.registry.stop(self.conversation_id)

        return await self.start()

    async def start(self) -> Kernel:
        await self.emit("kernel.starting", {})
        started = time.monotonic()

        # The kernel mounts the conversation's folder; a conversation that has had
        # no upload yet has none, and Docker refuses to mount what is not there.
        await self.store.prepare_folder(self.folder)
        kernel = await self.registry.kernel_for(self.conversation_id, self.folder)

        startup_ms = int((time.monotonic() - started) * 1000)
        await self.emit("kernel.ready", {"startup_ms": startup_ms})

        return kernel
