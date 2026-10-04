"""A kernel registry that answers every profile at once, without a container.

For the upload tests that are about the route — limits, names, conflicts — and
not about profiling, which costs a real kernel's start. The real path has tests
of its own in test_files.py.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from app.domain.runtime import ExecutionResult, OnOutput, StreamOutput

CANNED_PROFILE = {"format": "csv", "readable": True, "tables": [], "canned": True}


class FakeKernel:
    async def execute(
        self,
        code: str,
        on_output: OnOutput,
        store_history: bool = True,
    ) -> ExecutionResult:
        printed = json.dumps(CANNED_PROFILE)
        await on_output(StreamOutput(name="stdout", text=printed))

        return ExecutionResult(status="ok", execution_count=None, duration_ms=1)

    async def interrupt(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class FakeKernels:
    def __init__(self) -> None:
        self.kernels: dict[UUID, FakeKernel] = {}
        self.reasons: dict[UUID, str] = {}
        self.interrupted: list[UUID] = []

    async def kernel_for(self, session: UUID, files: str) -> FakeKernel:
        kernel = self.kernels.setdefault(session, FakeKernel())
        return kernel

    def running(self) -> set[UUID]:
        return set(self.kernels)

    async def stop(self, session: UUID, reason: str | None = None) -> None:
        self.kernels.pop(session, None)
        if reason is not None:
            self.reasons[session] = reason

    @asynccontextmanager
    async def hold(self, session: UUID) -> AsyncIterator[None]:
        yield

    def take_reason(self, session: UUID) -> str | None:
        return self.reasons.pop(session, None)

    async def interrupt(self, session: UUID) -> None:
        self.interrupted.append(session)

    async def stop_all(self) -> None:
        self.kernels.clear()
