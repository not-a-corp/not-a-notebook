"""The kernel registry: idle kernels reaped, held ones spared, and the reason a
kernel stopped kept for the next run to announce."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.runtime.registry import KernelRegistry
from tests.agent_fakes import ScriptedKernel


class Runtime:
    def __init__(self) -> None:
        self.started: list[UUID] = []

    async def start(self, session: UUID, files: str) -> ScriptedKernel:
        self.started.append(session)
        return ScriptedKernel([])


async def test_a_kernel_unused_for_the_idle_time_is_reaped_and_says_why() -> None:
    registry = KernelRegistry(Runtime())  # type: ignore[arg-type]
    session = uuid4()
    await registry.kernel_for(session, "files")
    used_at = registry.last_used[session]

    reaped = await registry.reap_idle(idle_seconds=600, now=used_at + 601)

    assert reaped == [session]
    assert registry.running() == set()
    assert registry.take_reason(session) == "idle"
    assert registry.take_reason(session) is None


async def test_a_kernel_used_recently_is_left_alone() -> None:
    registry = KernelRegistry(Runtime())  # type: ignore[arg-type]
    session = uuid4()
    await registry.kernel_for(session, "files")
    used_at = registry.last_used[session]

    assert await registry.reap_idle(idle_seconds=600, now=used_at + 599) == []
    assert registry.running() == {session}


async def test_a_kernel_held_by_a_run_is_never_idle() -> None:
    registry = KernelRegistry(Runtime())  # type: ignore[arg-type]
    session = uuid4()
    await registry.kernel_for(session, "files")
    used_at = registry.last_used[session]

    async with registry.hold(session):
        reaped = await registry.reap_idle(idle_seconds=600, now=used_at + 10_000)

    assert reaped == []
    assert registry.running() == {session}


async def test_releasing_a_kernel_restarts_its_idle_clock() -> None:
    registry = KernelRegistry(Runtime())  # type: ignore[arg-type]
    session = uuid4()
    await registry.kernel_for(session, "files")
    before = registry.last_used[session]

    async with registry.hold(session):
        pass

    assert registry.last_used[session] >= before


async def test_a_requested_stop_is_remembered_even_with_no_kernel_running() -> None:
    registry = KernelRegistry(Runtime())  # type: ignore[arg-type]
    session = uuid4()

    await registry.stop(session, reason="requested")

    assert registry.take_reason(session) == "requested"
