"""Stopping a run on request (POST /runs/{id}/cancel).

A run in progress has a control: cancelling sets it and interrupts the kernel. The
loop stops between steps and abandons a model call in flight; code running in
the kernel gets KeyboardInterrupt, and keeps every variable it had (decision 3:
an interrupt is not a restart). The run ends `cancelled`, with `run.finished` last
as always.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from app.runtime.registry import KernelRegistry


@dataclass
class RunControl:
    conversation_id: UUID
    stop: asyncio.Event = field(default_factory=asyncio.Event)


class RunControls:
    def __init__(self) -> None:
        self.active: dict[UUID, RunControl] = {}

    def open(self, run_id: UUID, conversation_id: UUID) -> RunControl:
        control = RunControl(conversation_id=conversation_id)
        self.active[run_id] = control

        return control

    def close(self, run_id: UUID) -> None:
        self.active.pop(run_id, None)

    async def cancel(self, run_id: UUID, kernels: KernelRegistry) -> None:
        """Does nothing for a run that already finished: cancelling it is a 202 that
        changes nothing (api.md)."""
        control = self.active.get(run_id)
        if control is None:
            return

        control.stop.set()
        await kernels.interrupt(control.conversation_id)
