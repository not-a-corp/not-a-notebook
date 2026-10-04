"""Removing kernels nobody will use again.

Kernels outlive the process that started them: a crash, a `docker kill`, a
deploy. Their containers keep holding memory and their networks keep holding
address space, and nothing in the database knows about them — whether a kernel
is running is deliberately not stored (see schema.sql). So they are found the
way the POC learned to: by label.

**Whose kernels these are** is the owner label, the API container that created
them. Several APIs can share one Docker daemon — the running service and a test
run, today; more processes, one day — and each must only ever reap its own or the
dead's:

| Owner | On startup | On shutdown |
| --- | --- | --- |
| this container | reaped: the process that made them is gone | reaped |
| a container that is not running | reaped: orphans | left |
| another running container | left: they are in use | left |

"This container" still holds after a crash: `docker restart` keeps the container
id, so the new process finds its predecessor's kernels under its own name.

Idle kernels are not this file's concern: reaping them belongs with telling the
conversation its kernel restarted (decision 3, Phase 6).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.runtime.docker_engine import DockerEngine, DockerError
from app.runtime.docker_runtime import KERNEL_LABEL, OWNER_LABEL, quietly

log = logging.getLogger(__name__)

type ShouldReap = Callable[[str], Awaitable[bool]]


async def reap_orphans(engine: DockerEngine, api_container: str) -> int:
    """On startup: this container's kernels and those of APIs that are gone.
    Returns how many kernels were removed."""

    async def should_reap(owner: str) -> bool:
        # No owner label: made before kernels carried one, so nobody claims it.
        if owner == "" or owner == api_container:
            return True

        running = await is_running(engine, owner)
        return not running

    return await reap(engine, should_reap)


async def reap_own(engine: DockerEngine, api_container: str) -> int:
    """On shutdown: every kernel this container started."""

    async def should_reap(owner: str) -> bool:
        return owner == api_container

    return await reap(engine, should_reap)


async def reap(engine: DockerEngine, should_reap: ShouldReap) -> int:
    # Containers before networks: a network cannot be removed while a container
    # is still on it.
    containers = await engine.list_containers(KERNEL_LABEL)
    removed = 0

    for container in containers:
        owner = container["Labels"].get(OWNER_LABEL, "")
        if not await should_reap(owner):
            continue

        await quietly(engine.remove_container(container["Id"]))
        removed += 1

    networks = await engine.list_networks(KERNEL_LABEL)

    for network in networks:
        owner = network["Labels"].get(OWNER_LABEL, "")
        if not await should_reap(owner):
            continue

        await remove_network(engine, network["Id"])

    if removed > 0:
        log.info("reaped %(removed)s kernels", {"removed": removed})

    return removed


async def remove_network(engine: DockerEngine, network: str) -> None:
    """Disconnects whatever is still attached — the owning API, alive or a
    stopped husk — and removes the network."""
    try:
        inspected = await engine.inspect_network(network)
    except DockerError:
        return

    attached = inspected.get("Containers") or {}

    for container in attached:
        await quietly(engine.disconnect_network(network, container))

    await quietly(engine.remove_network(network))


async def is_running(engine: DockerEngine, container: str) -> bool:
    try:
        inspected = await engine.inspect_container(container)
    except DockerError as exc:
        if exc.status == 404:
            return False

        raise

    running: bool = inspected["State"]["Running"]
    return running
