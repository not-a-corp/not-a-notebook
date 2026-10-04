"""Fake kernels and a fake kernel registry: the API's runs without a container.

The real path has tests of its own — test_runtime_docker.py, test_reaper.py, and
the tests in test_files.py and test_cells.py that say they use a real kernel.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
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


class FakeRegistry:
    """The kernel registry with fake kernels — for the tests that are about the
    API and the runs, not about Docker.

    `FakeRegistry(FakeKernel)` gives each conversation its own kernel that answers
    every profile at once; `FakeRegistry.scripted(kernel)` hands one scripted kernel
    to every conversation, so a test can say what each execution prints.
    """

    def __init__(self, make_kernel: Callable[[], Any]) -> None:
        self.make_kernel = make_kernel
        self.kernels: dict[UUID, Any] = {}
        self.reasons: dict[UUID, str] = {}
        self.interrupted: list[UUID] = []
        # The scripted kernel, when there is one.
        self.kernel: Any = None

    @classmethod
    def scripted(cls, kernel: Any) -> FakeRegistry:
        registry = cls(lambda: kernel)
        registry.kernel = kernel
        return registry

    async def kernel_for(self, session: UUID, files: str) -> Any:
        if session not in self.kernels:
            self.kernels[session] = self.make_kernel()

        return self.kernels[session]

    def running(self) -> set[UUID]:
        return set(self.kernels)

    @asynccontextmanager
    async def hold(self, session: UUID) -> AsyncIterator[None]:
        yield

    async def interrupt(self, session: UUID) -> None:
        self.interrupted.append(session)

        kernel = self.kernels.get(session)
        if kernel is not None:
            await kernel.interrupt()

    async def stop(self, session: UUID, reason: str | None = None) -> None:
        self.kernels.pop(session, None)
        if reason is not None:
            self.reasons[session] = reason

    def take_reason(self, session: UUID) -> str | None:
        return self.reasons.pop(session, None)

    async def stop_all(self) -> None:
        self.kernels.clear()
