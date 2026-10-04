"""Reaping kernels: the orphans on startup, our own on shutdown, nobody else's.

Most kernels here are stand-ins — a `sleep` container and a network carrying the
same labels a real kernel does — because the reaper looks at labels and nothing
else, and a stand-in starts in a fraction of a real kernel's time. One test uses
a real kernel, abandoned the way a crash would abandon it.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
import pytest_asyncio
from app.config import get_settings
from app.runtime.docker_engine import DockerEngine, DockerError
from app.runtime.docker_runtime import KERNEL_LABEL, OWNER_LABEL, DockerRuntime, SandboxLimits
from app.runtime.reaper import reap_orphans, reap_own

pytestmark = pytest.mark.asyncio(loop_scope="module")


@dataclass(frozen=True)
class StandIn:
    container: str
    network: str


def me() -> str:
    return get_settings().api_container


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def engine() -> AsyncIterator[DockerEngine]:
    docker = DockerEngine.over_socket()
    yield docker
    await docker.close()


async def another_api(engine: DockerEngine) -> str:
    """A running container standing in for some other API process."""
    config = {
        "Image": get_settings().sandbox_image,
        "Cmd": ["sleep", "600"],
        "Labels": {"not-a-notebook.test": "another-api"},
    }
    container = await engine.create_container(f"nan-test-api-{uuid4()}", config)
    await engine.start_container(container)

    return container


async def stand_in_kernel(engine: DockerEngine, owner: str, attach_owner: bool = False) -> StandIn:
    session = str(uuid4())
    name = f"nan-kernel-{session}"
    labels = {KERNEL_LABEL: session, OWNER_LABEL: owner}

    network = await engine.create_network(name, labels)
    if attach_owner:
        await engine.connect_network(network, owner)

    config = {
        "Image": get_settings().sandbox_image,
        "Cmd": ["sleep", "600"],
        "Labels": labels,
        "HostConfig": {"NetworkMode": name},
    }
    container = await engine.create_container(name, config)
    await engine.start_container(container)

    return StandIn(container=container, network=network)


async def container_exists(engine: DockerEngine, container: str) -> bool:
    try:
        await engine.inspect_container(container)
    except DockerError as exc:
        assert exc.status == 404
        return False

    return True


async def network_exists(engine: DockerEngine, network: str) -> bool:
    try:
        await engine.inspect_network(network)
    except DockerError as exc:
        assert exc.status == 404
        return False

    return True


async def remove(engine: DockerEngine, stand_in: StandIn) -> None:
    """Cleanup for kernels a test meant to leave alone."""
    with contextlib.suppress(DockerError):
        await engine.remove_container(stand_in.container)

    with contextlib.suppress(DockerError):
        await engine.remove_network(stand_in.network)


# ── on startup ───────────────────────────────────────────────────────────────


async def test_a_dead_apis_kernels_are_reaped(engine: DockerEngine) -> None:
    owner = await another_api(engine)
    orphan = await stand_in_kernel(engine, owner, attach_owner=True)

    # The API dies; its container stays behind, stopped, still on the network.
    await engine.request("POST", f"/containers/{owner}/stop", params={"t": "0"})
    try:
        await reap_orphans(engine, me())
    finally:
        await engine.remove_container(owner)

    assert not await container_exists(engine, orphan.container)
    assert not await network_exists(engine, orphan.network)


async def test_a_vanished_apis_kernels_are_reaped(engine: DockerEngine) -> None:
    orphan = await stand_in_kernel(engine, owner=f"gone-{uuid4()}")

    await reap_orphans(engine, me())

    assert not await container_exists(engine, orphan.container)
    assert not await network_exists(engine, orphan.network)


async def test_a_live_apis_kernels_are_left_alone(engine: DockerEngine) -> None:
    owner = await another_api(engine)
    in_use = await stand_in_kernel(engine, owner, attach_owner=True)
    try:
        await reap_orphans(engine, me())

        assert await container_exists(engine, in_use.container)
        assert await network_exists(engine, in_use.network)
    finally:
        await remove(engine, in_use)
        await engine.remove_container(owner)


async def test_kernels_without_an_owner_are_reaped(engine: DockerEngine) -> None:
    session = str(uuid4())
    labels = {KERNEL_LABEL: session}
    network = await engine.create_network(f"nan-kernel-{session}", labels)

    await reap_orphans(engine, me())

    assert not await network_exists(engine, network)


async def test_a_real_kernel_abandoned_by_a_crash_is_reaped(engine: DockerEngine) -> None:
    """The process that started it is gone; this one has the same container id,
    as after `docker restart`."""
    settings = get_settings()
    limits = SandboxLimits(
        image=settings.sandbox_image,
        container_runtime=settings.sandbox_runtime,
        memory_mb=settings.kernel_memory_mb,
        cpus=settings.kernel_cpus,
        pids=settings.kernel_pids,
        execution_timeout_seconds=settings.execution_timeout_seconds,
    )
    runtime = DockerRuntime(engine, limits, me())
    kernel = await runtime.start(uuid4())

    # No shutdown: the process "died" with the kernel running.
    kernel.client.stop_channels()

    removed = await reap_orphans(engine, me())

    assert removed >= 1
    assert not await container_exists(engine, kernel.container)
    assert not await network_exists(engine, kernel.network)


# ── on shutdown ──────────────────────────────────────────────────────────────


async def test_shutdown_reaps_our_kernels_and_only_ours(engine: DockerEngine) -> None:
    owner = await another_api(engine)
    theirs = await stand_in_kernel(engine, owner, attach_owner=True)
    ours = await stand_in_kernel(engine, me())
    try:
        await reap_own(engine, me())

        assert not await container_exists(engine, ours.container)
        assert not await network_exists(engine, ours.network)
        assert await container_exists(engine, theirs.container)
    finally:
        await remove(engine, theirs)
        await engine.remove_container(owner)
