"""Sending a message through the API and watching its run, with the kernel
registry swapped for one that hands out a scripted kernel."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from tests.agent_fakes import ScriptedKernel
from tests.auth_helpers import bearer
from tests.conftest import Run

CONVERSATIONS = "/api/v1/conversations"


class ScriptedRegistry:
    """The kernel registry, handing out one scripted kernel."""

    def __init__(self, kernel: ScriptedKernel) -> None:
        self.kernel = kernel
        self.started: set[UUID] = set()
        self.reasons: dict[UUID, str] = {}
        self.interrupted: list[UUID] = []

    async def kernel_for(self, session: UUID, files: str) -> ScriptedKernel:
        self.started.add(session)
        return self.kernel

    def running(self) -> set[UUID]:
        return set(self.started)

    async def stop(self, session: UUID, reason: str | None = None) -> None:
        self.started.discard(session)
        if reason is not None:
            self.reasons[session] = reason

    @asynccontextmanager
    async def hold(self, session: UUID) -> AsyncIterator[None]:
        yield

    def take_reason(self, session: UUID) -> str | None:
        return self.reasons.pop(session, None)

    async def interrupt(self, session: UUID) -> None:
        self.interrupted.append(session)
        await self.kernel.interrupt()

    async def stop_all(self) -> None:
        self.started.clear()


def send(client: TestClient, token: str, conversation: str, text: str) -> Any:
    url = f"{CONVERSATIONS}/{conversation}/messages"

    return client.post(url, headers=bearer(token), json={"text": text})


def settled(sql: Run, run_id: str) -> str:
    deadline = time.monotonic() + 30

    while time.monotonic() < deadline:
        rows = sql("SELECT r.status FROM runs r WHERE r.external_id = %(id)s", {"id": run_id})
        if rows[0][0] != "running":
            return str(rows[0][0])
        time.sleep(0.05)

    raise AssertionError("the run never finished")


def events_of(sql: Run, run_id: str) -> list[dict[str, Any]]:
    rows = sql(
        """
        SELECT e.event
          FROM run_events e
          JOIN runs r
            ON r.id = e.run_id
         WHERE r.external_id = %(id)s
         ORDER BY e.seq
        """,
        {"id": run_id},
    )

    return [row[0] for row in rows]
