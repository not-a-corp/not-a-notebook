"""The Runtime protocol over Docker: one container, one network, one kernel per
conversation.

**One network per conversation** (decided 3 Oct 2026). Each kernel gets its own
`internal` network, and only it and the API are on it. A kernel's iopub is a PUB
socket — the HMAC key stops forged requests, not reading — so on a shared network
one kernel could subscribe to another's outputs. Here it cannot even route there.

The container is locked down past the network: read-only root filesystem, every
capability dropped, no privilege escalation, an unprivileged user, and limits on
memory, CPU and processes. What must be writable is tmpfs, counted against the
memory limit.

The API writes the kernel's connection file — fixed ports, a fresh HMAC key per
kernel — and hands it over in the environment; the image's command writes it to
a tmpfs and drops the variable before the kernel starts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import secrets
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from jupyter_client.asynchronous.client import AsyncKernelClient
from jupyter_client.connect import KernelConnectionInfo

from app.domain.errors import SandboxUnavailable
from app.domain.runtime import ExecutionResult, ExecutionStatus, KernelDied, OnOutput
from app.runtime.docker_engine import DockerEngine, DockerError
from app.runtime.outputs import from_message

log = logging.getLogger(__name__)

# Every container and network this runtime creates carries this label, with the
# session as its value: it is how the reaper finds them after a crash.
KERNEL_LABEL = "not-a-notebook.kernel"

# Fixed, because each kernel has the container — and the network — to itself.
PORTS = {
    "shell_port": 50001,
    "iopub_port": 50002,
    "stdin_port": 50003,
    "control_port": 50004,
    "hb_port": 50005,
}

STARTUP_TIMEOUT_SECONDS = 60

# How long an interrupted execution gets to wind down before the kernel is
# declared unresponsive.
INTERRUPT_GRACE_SECONDS = 10

# How often a silent kernel is checked for being alive at all.
POLL_SECONDS = 1.0


@dataclass(frozen=True)
class SandboxLimits:
    image: str
    # runc, or runsc for gVisor.
    container_runtime: str
    memory_mb: int
    cpus: float
    pids: int
    execution_timeout_seconds: float


class DockerRuntime:
    def __init__(self, engine: DockerEngine, limits: SandboxLimits, api_container: str) -> None:
        self.engine = engine
        self.limits = limits
        # The container this API runs in. It joins each kernel's network, which is
        # the only way to reach a kernel that has no other network.
        self.api_container = api_container

    async def start(self, session: UUID) -> DockerKernel:
        name = f"nan-kernel-{session}"
        labels = {KERNEL_LABEL: str(session)}
        key = secrets.token_hex(32)

        network = await self.create_network(name, labels)
        container: str | None = None

        try:
            await self.engine.connect_network(network, self.api_container)

            config = self.container_config(name, labels, key)
            container = await self.engine.create_container(name, config)
            await self.engine.start_container(container)

            inspected = await self.engine.inspect_container(container)
            address = inspected["NetworkSettings"]["Networks"][name]["IPAddress"]

            client = await connect(address, key)
        except (DockerError, RuntimeError, KeyError) as exc:
            log.exception("kernel %(session)s did not start", {"session": session})
            await teardown(self.engine, container, network, self.api_container)
            raise SandboxUnavailable from exc

        return DockerKernel(
            engine=self.engine,
            client=client,
            container=container,
            network=network,
            api_container=self.api_container,
            execution_timeout_seconds=self.limits.execution_timeout_seconds,
        )

    async def create_network(self, name: str, labels: dict[str, str]) -> str:
        try:
            network = await self.engine.create_network(name, labels)
        except DockerError as exc:
            log.exception("network %(name)s could not be created", {"name": name})
            raise SandboxUnavailable from exc

        return network

    def container_config(self, name: str, labels: dict[str, str], key: str) -> dict[str, Any]:
        connection = {
            "ip": "0.0.0.0",
            "transport": "tcp",
            "key": key,
            "signature_scheme": "hmac-sha256",
            "kernel_name": "python3",
            "shell_port": PORTS["shell_port"],
            "iopub_port": PORTS["iopub_port"],
            "stdin_port": PORTS["stdin_port"],
            "control_port": PORTS["control_port"],
            "hb_port": PORTS["hb_port"],
        }

        memory = self.limits.memory_mb * 1024 * 1024
        nano_cpus = int(self.limits.cpus * 1_000_000_000)

        host_config = {
            "NetworkMode": name,
            "Runtime": self.limits.container_runtime,
            "Memory": memory,
            # Equal to Memory: no swap, so running out of memory ends the kernel
            # instead of slowing the whole host down.
            "MemorySwap": memory,
            "NanoCpus": nano_cpus,
            "PidsLimit": self.limits.pids,
            "ReadonlyRootfs": True,
            "Tmpfs": {
                "/tmp": "size=512m",
                "/home/analyst": "size=256m,uid=1000,gid=1000",
                "/run/kernel": "size=1m,uid=1000,gid=1000",
            },
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
        }

        return {
            "Image": self.limits.image,
            "Env": [f"KERNEL_CONNECTION={json.dumps(connection)}"],
            "Labels": labels,
            "HostConfig": host_config,
            "NetworkingConfig": {"EndpointsConfig": {name: {}}},
        }


async def connect(address: str, key: str) -> AsyncKernelClient:
    info: KernelConnectionInfo = {
        "ip": address,
        "transport": "tcp",
        "key": key,
        "signature_scheme": "hmac-sha256",
        "shell_port": PORTS["shell_port"],
        "iopub_port": PORTS["iopub_port"],
        "stdin_port": PORTS["stdin_port"],
        "control_port": PORTS["control_port"],
        "hb_port": PORTS["hb_port"],
    }

    client = AsyncKernelClient()
    client.load_connection_info(info)

    # No stdin: generated code that calls input() fails at once instead of
    # waiting for a person who is not there. No heartbeat either: a fresh
    # heartbeat channel reports "not beating" until its first round trip, which
    # wait_for_ready reads as a dead kernel. Liveness comes from the container's
    # state instead (check_alive), which also says *why* a kernel died.
    client.start_channels(stdin=False, hb=False)

    try:
        await client.wait_for_ready(timeout=STARTUP_TIMEOUT_SECONDS)
    except RuntimeError:
        client.stop_channels()
        raise

    return client


async def teardown(
    engine: DockerEngine,
    container: str | None,
    network: str,
    api_container: str,
) -> None:
    """Removes whatever exists of a kernel. Each step is attempted even when an
    earlier one failed: a half-torn-down kernel is what the reaper exists for, and
    it should find as little as possible."""
    if container is not None:
        await quietly(engine.remove_container(container))

    await quietly(engine.disconnect_network(network, api_container))
    await quietly(engine.remove_network(network))


async def quietly(step: Awaitable[None]) -> None:
    try:
        await step
    except DockerError as exc:
        log.warning("kernel teardown step failed: %(error)s", {"error": exc})


class DockerKernel:
    def __init__(
        self,
        engine: DockerEngine,
        client: AsyncKernelClient,
        container: str,
        network: str,
        api_container: str,
        execution_timeout_seconds: float,
    ) -> None:
        self.engine = engine
        self.client = client
        self.container = container
        self.network = network
        self.api_container = api_container
        self.execution_timeout_seconds = execution_timeout_seconds
        self.interrupt_requested = False

    async def execute(self, code: str, on_output: OnOutput) -> ExecutionResult:
        self.interrupt_requested = False
        started = time.monotonic()
        timed_out = False

        msg_id = self.client.execute(code, store_history=True, allow_stdin=False)

        try:
            async with asyncio.timeout(self.execution_timeout_seconds):
                reply = await self.collect(msg_id, on_output)
        except TimeoutError:
            timed_out = True
            reply = await self.wind_down(msg_id, on_output)

        duration_ms = int((time.monotonic() - started) * 1000)

        status = self.status_of(reply)
        if timed_out:
            status = "timed_out"

        return ExecutionResult(
            status=status,
            execution_count=reply.get("execution_count"),
            duration_ms=duration_ms,
        )

    async def interrupt(self) -> None:
        """Raises KeyboardInterrupt in whatever the kernel is running. Its state
        survives — this is not a restart."""
        self.interrupt_requested = True

        message = self.client.session.msg("interrupt_request", content={})
        self.client.control_channel.send(message)

    async def shutdown(self) -> None:
        self.client.stop_channels()

        await teardown(self.engine, self.container, self.network, self.api_container)

    async def wind_down(self, msg_id: str, on_output: OnOutput) -> dict[str, Any]:
        await self.interrupt()

        try:
            async with asyncio.timeout(INTERRUPT_GRACE_SECONDS):
                reply = await self.collect(msg_id, on_output)
        except TimeoutError as exc:
            raise KernelDied("the kernel did not stop when interrupted") from exc

        return reply

    async def collect(self, msg_id: str, on_output: OnOutput) -> dict[str, Any]:
        """Hands every output of this execution to on_output, in order, until the
        kernel is idle again; returns the execution's reply."""
        while True:
            message = await self.next_message(msg_id)
            kind = message["msg_type"]
            content = message["content"]

            if kind == "status" and content["execution_state"] == "idle":
                break

            output = from_message(kind, content)
            if output is not None:
                await on_output(output)

        while True:
            reply = await self.client.get_shell_msg()
            if reply["parent_header"].get("msg_id") == msg_id:
                break

        reply_content: dict[str, Any] = reply["content"]
        return reply_content

    async def next_message(self, msg_id: str) -> dict[str, Any]:
        """The next iopub message about this execution. A kernel that goes quiet is
        checked for being alive, so one killed for its memory is noticed in
        seconds rather than at the wall-time limit."""
        while True:
            try:
                message: dict[str, Any] = await self.client.get_iopub_msg(timeout=POLL_SECONDS)
            except queue.Empty:
                await self.check_alive()
                continue

            if message["parent_header"].get("msg_id") == msg_id:
                return message

    async def check_alive(self) -> None:
        try:
            inspected = await self.engine.inspect_container(self.container)
        except DockerError as exc:
            raise KernelDied("the kernel's container is gone") from exc

        state = inspected["State"]
        if state["OOMKilled"]:
            raise KernelDied("the kernel ran out of memory")

        if not state["Running"]:
            raise KernelDied(f"the kernel exited with {state['ExitCode']}")

    def status_of(self, reply: dict[str, Any]) -> ExecutionStatus:
        if reply["status"] == "ok":
            return "ok"

        interrupted = reply.get("ename") == "KeyboardInterrupt"
        if interrupted and self.interrupt_requested:
            return "cancelled"

        return "error"
