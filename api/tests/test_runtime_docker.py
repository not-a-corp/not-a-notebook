"""The Docker runtime against real containers: Phase 3's list, item by item.

Needs the Docker socket, which compose mounts into the api service. Tests that
only read share one kernel; the ones that break, limit or kill a kernel get
their own.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import uuid4

import pytest
import pytest_asyncio
from app.config import get_settings
from app.domain.errors import SandboxUnavailable
from app.domain.runtime import (
    ErrorOutput,
    ExecutionResult,
    ImageOutput,
    KernelDied,
    Output,
    PlotlyOutput,
    StreamOutput,
    TableOutput,
    TextOutput,
)
from app.runtime.docker_engine import DockerEngine, DockerError
from app.runtime.docker_runtime import PORTS, DockerKernel, DockerRuntime, SandboxLimits

pytestmark = pytest.mark.asyncio(loop_scope="module")


class Recorder:
    """An on_output that keeps everything, in the order it came."""

    def __init__(self) -> None:
        self.outputs: list[Output] = []

    async def __call__(self, output: Output) -> None:
        self.outputs.append(output)

    def printed(self, name: str = "stdout") -> str:
        text = ""

        for output in self.outputs:
            if isinstance(output, StreamOutput) and output.name == name:
                text += output.text

        return text


async def run(kernel: DockerKernel, code: str) -> tuple[ExecutionResult, Recorder]:
    recorder = Recorder()
    result = await kernel.execute(code, recorder)

    return result, recorder


def default_limits() -> SandboxLimits:
    settings = get_settings()

    return SandboxLimits(
        image=settings.sandbox_image,
        container_runtime=settings.sandbox_runtime,
        memory_mb=settings.kernel_memory_mb,
        cpus=settings.kernel_cpus,
        pids=settings.kernel_pids,
        execution_timeout_seconds=settings.execution_timeout_seconds,
    )


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def engine() -> AsyncIterator[DockerEngine]:
    docker = DockerEngine.over_socket()
    yield docker
    await docker.close()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def runtime(engine: DockerEngine) -> DockerRuntime:
    return DockerRuntime(engine, default_limits(), get_settings().api_container)


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def kernel(runtime: DockerRuntime) -> AsyncIterator[DockerKernel]:
    started = await runtime.start(uuid4())
    yield started
    await started.shutdown()


async def address_of(engine: DockerEngine, kernel: DockerKernel) -> str:
    inspected = await engine.inspect_container(kernel.container)
    networks = inspected["NetworkSettings"]["Networks"]
    endpoint = next(iter(networks.values()))

    return str(endpoint["IPAddress"])


# ── what comes out ───────────────────────────────────────────────────────────


async def test_state_survives_between_executions(kernel: DockerKernel) -> None:
    await run(kernel, "x = 41")
    await run(kernel, "x += 1")

    result, recorder = await run(kernel, "print(x)")

    assert result.status == "ok"
    assert recorder.printed() == "42\n"


async def test_stdout_and_stderr_arrive_apart_and_in_order(kernel: DockerKernel) -> None:
    code = "import sys\nprint('one')\nprint('two', file=sys.stderr)\nprint('three')"

    _, recorder = await run(kernel, code)

    assert recorder.printed("stdout") == "one\nthree\n"
    assert recorder.printed("stderr") == "two\n"

    names = []
    for output in recorder.outputs:
        assert isinstance(output, StreamOutput)
        names.append(output.name)
    assert names[0] == "stdout"


async def test_an_error_comes_back_structured(kernel: DockerKernel) -> None:
    result, recorder = await run(kernel, "{'a': 1}['region']")

    assert result.status == "error"
    error = recorder.outputs[-1]
    assert isinstance(error, ErrorOutput)
    assert error.name == "KeyError"
    assert error.value == "'region'"
    assert not any("\x1b" in line for line in error.traceback)


async def test_a_plotly_figure_arrives_as_a_spec(kernel: DockerKernel) -> None:
    code = "import plotly.express as px\npx.bar(x=['N', 'S'], y=[3, 1]).show()"

    _, recorder = await run(kernel, code)

    assert len(recorder.outputs) == 1
    figure = recorder.outputs[0]
    assert isinstance(figure, PlotlyOutput)
    assert figure.spec["data"][0]["type"] == "bar"


async def test_a_dataframe_arrives_as_a_table(kernel: DockerKernel) -> None:
    code = "import pandas as pd\npd.DataFrame({'region': ['N', 'S'], 'sales': [3, 1]})"

    result, recorder = await run(kernel, code)

    assert recorder.outputs == [
        TableOutput(columns=["region", "sales"], rows=[["N", 3], ["S", 1]], total_rows=2)
    ]
    assert result.execution_count is not None


async def test_matplotlib_arrives_as_an_image(kernel: DockerKernel) -> None:
    code = "import matplotlib.pyplot as plt\nplt.plot([1, 2])\nplt.show()"

    _, recorder = await run(kernel, code)

    assert len(recorder.outputs) == 1
    assert isinstance(recorder.outputs[0], ImageOutput)


async def test_a_plain_value_arrives_as_text(kernel: DockerKernel) -> None:
    _, recorder = await run(kernel, "6 * 7")

    assert recorder.outputs == [TextOutput(text="42")]


async def test_input_fails_instead_of_waiting(kernel: DockerKernel) -> None:
    result, _ = await asyncio.wait_for(run(kernel, "input('name? ')"), timeout=30)

    assert result.status == "error"


# ── what the kernel cannot do ────────────────────────────────────────────────


async def test_egress_is_blocked_measured_as_a_transfer(kernel: DockerKernel) -> None:
    """Not "the connection failed" — a TLS error after a successful connect would
    pass that. What matters is that no byte of a response came back."""
    code = """
import json, urllib.request

received = {}
for url in ["http://example.com", "https://example.com", "http://1.1.1.1", "http://8.8.8.8"]:
    try:
        body = urllib.request.urlopen(url, timeout=5).read()
        received[url] = len(body)
    except Exception as exc:
        received[url] = type(exc).__name__

print(json.dumps(received))
"""

    _, recorder = await run(kernel, code)
    received = json.loads(recorder.printed())

    for url, outcome in received.items():
        assert isinstance(outcome, str), f"{url} sent back {outcome} bytes"


async def test_the_kernel_cannot_reach_the_database(kernel: DockerKernel) -> None:
    code = """
import socket
try:
    socket.create_connection(("db", 5432), timeout=3)
    print("connected")
except Exception as exc:
    print(type(exc).__name__)
"""

    _, recorder = await run(kernel, code)

    assert recorder.printed().strip() != "connected"


async def test_one_kernel_cannot_reach_anothers(
    runtime: DockerRuntime, engine: DockerEngine, kernel: DockerKernel
) -> None:
    """The reason for a network per conversation: iopub is a PUB socket, and a
    kernel that could connect to another's could read its outputs."""
    other = await runtime.start(uuid4())
    try:
        address = await address_of(engine, other)
        code = f"""
import socket
try:
    socket.create_connection(("{address}", {PORTS["iopub_port"]}), timeout=3)
    print("connected")
except Exception as exc:
    print(type(exc).__name__)
"""
        _, recorder = await run(kernel, code)
    finally:
        await other.shutdown()

    assert recorder.printed().strip() != "connected"


async def test_the_filesystem_is_read_only_outside_home_and_tmp(kernel: DockerKernel) -> None:
    code = """
import os
for path in ["/opt/x", "/data/x", "/home/analyst/x", "/tmp/x"]:
    try:
        open(path, "w").close()
        print(path, "written")
    except OSError:
        print(path, "refused")
"""

    _, recorder = await run(kernel, code)

    assert recorder.printed().splitlines() == [
        "/opt/x refused",
        "/data/x refused",
        "/home/analyst/x written",
        "/tmp/x written",
    ]


async def test_the_connection_key_is_not_left_in_the_environment(kernel: DockerKernel) -> None:
    _, recorder = await run(kernel, "import os\nprint('KERNEL_CONNECTION' in os.environ)")

    assert recorder.printed() == "False\n"


async def test_the_container_is_locked_down(engine: DockerEngine, kernel: DockerKernel) -> None:
    inspected = await engine.inspect_container(kernel.container)
    host = inspected["HostConfig"]

    assert host["ReadonlyRootfs"] is True
    assert host["CapDrop"] == ["ALL"]
    assert host["SecurityOpt"] == ["no-new-privileges"]
    assert host["Memory"] == get_settings().kernel_memory_mb * 1024 * 1024
    assert host["PidsLimit"] == get_settings().kernel_pids

    network = await engine.inspect_network(host["NetworkMode"])
    assert network["Internal"] is True
    assert len(network["Containers"]) == 2


# ── stopping it ──────────────────────────────────────────────────────────────


async def test_interrupt_stops_a_loop_and_keeps_the_state(kernel: DockerKernel) -> None:
    await run(kernel, "kept = 'still here'")

    running = asyncio.create_task(run(kernel, "while True:\n    pass"))
    await asyncio.sleep(2)
    await kernel.interrupt()
    result, recorder = await asyncio.wait_for(running, timeout=30)

    assert result.status == "cancelled"
    assert isinstance(recorder.outputs[-1], ErrorOutput)

    _, after = await run(kernel, "print(kept)")
    assert after.printed() == "still here\n"


async def test_the_wall_time_limit_interrupts_and_keeps_the_state(
    engine: DockerEngine,
) -> None:
    limits = replace(default_limits(), execution_timeout_seconds=3)
    runtime = DockerRuntime(engine, limits, get_settings().api_container)
    kernel = await runtime.start(uuid4())
    try:
        await run(kernel, "kept = 1")

        result, _ = await asyncio.wait_for(run(kernel, "while True:\n    pass"), timeout=30)
        _, after = await run(kernel, "print(kept)")
    finally:
        await kernel.shutdown()

    assert result.status == "timed_out"
    assert after.printed() == "1\n"


async def test_running_out_of_memory_kills_the_kernel_and_says_so(engine: DockerEngine) -> None:
    limits = replace(default_limits(), memory_mb=256)
    runtime = DockerRuntime(engine, limits, get_settings().api_container)
    kernel = await runtime.start(uuid4())
    try:
        with pytest.raises(KernelDied):
            await asyncio.wait_for(run(kernel, "hog = b'x' * (1024 ** 3)"), timeout=60)
    finally:
        await kernel.shutdown()


async def test_shutdown_leaves_nothing_behind(runtime: DockerRuntime, engine: DockerEngine) -> None:
    kernel = await runtime.start(uuid4())
    inspected = await engine.inspect_container(kernel.container)
    network = inspected["HostConfig"]["NetworkMode"]

    await kernel.shutdown()

    with pytest.raises(DockerError) as container_gone:
        await engine.inspect_container(kernel.container)
    with pytest.raises(DockerError) as network_gone:
        await engine.inspect_network(network)
    assert container_gone.value.status == 404
    assert network_gone.value.status == 404


async def test_a_kernel_that_cannot_start_is_sandbox_unavailable_and_cleaned_up(
    engine: DockerEngine,
) -> None:
    limits = replace(default_limits(), image="not-a-notebook-sandbox:does-not-exist")
    runtime = DockerRuntime(engine, limits, get_settings().api_container)
    session = uuid4()

    with pytest.raises(SandboxUnavailable):
        await runtime.start(session)

    with pytest.raises(DockerError) as network_gone:
        await engine.inspect_network(f"nan-kernel-{session}")
    assert network_gone.value.status == 404
