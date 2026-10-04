"""Proves the image does its job: a kernel starts, and what generated code needs
comes out of it in the shapes the API expects.

Runs inside the image, against a real kernel started on loopback. It needs no
network, and is meant to run with none:

    docker compose run --rm sandbox

Each check prints its name when it passes; the first failure stops the run with
a non-zero exit.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jupyter_client.blocking.client import BlockingKernelClient
from jupyter_client.manager import start_new_kernel

TIMEOUT_SECONDS = 60

PACKAGES = [
    "duckdb",
    "matplotlib",
    "numpy",
    "openpyxl",
    "pandas",
    "pdfplumber",
    "plotly",
    "polars",
    "pyarrow",
    "xlrd",
]

PLOTLY_MIME = "application/vnd.plotly.v1+json"


@dataclass(frozen=True)
class Output:
    kind: str
    content: dict[str, Any]


@dataclass(frozen=True)
class Execution:
    status: str
    outputs: list[Output]


def run(client: BlockingKernelClient, code: str) -> Execution:
    """Executes code and collects what it produced, until the kernel is idle again."""
    msg_id = client.execute(code)
    outputs = []

    while True:
        message = client.get_iopub_msg(timeout=TIMEOUT_SECONDS)
        if message["parent_header"].get("msg_id") != msg_id:
            continue

        kind = message["msg_type"]
        content = message["content"]

        if kind == "status" and content["execution_state"] == "idle":
            break

        if kind in ("stream", "display_data", "execute_result", "error"):
            output = Output(kind=kind, content=content)
            outputs.append(output)

    while True:
        reply = client.get_shell_msg(timeout=TIMEOUT_SECONDS)
        if reply["parent_header"].get("msg_id") == msg_id:
            break

    return Execution(status=reply["content"]["status"], outputs=outputs)


def only(outputs: list[Output], kind: str) -> list[dict[str, Any]]:
    """The content of every output of one kind, in the order they came."""
    matching = []

    for output in outputs:
        if output.kind == kind:
            matching.append(output.content)

    return matching


def check_runs_unprivileged(client: BlockingKernelClient) -> None:
    result = run(client, "import os; print(os.getuid())")
    uid = only(result.outputs, "stream")[0]["text"].strip()

    assert uid != "0", "the kernel runs as root"


def check_every_package_imports(client: BlockingKernelClient) -> None:
    code = "import " + ", ".join(PACKAGES)
    result = run(client, code)

    assert result.status == "ok", result.outputs


def check_state_survives_between_executions(client: BlockingKernelClient) -> None:
    run(client, "x = 41")
    run(client, "x += 1")
    result = run(client, "print(x)")

    assert only(result.outputs, "stream")[0]["text"] == "42\n"


def check_stdout_and_stderr_arrive_apart(client: BlockingKernelClient) -> None:
    code = "import sys\nprint('to out')\nprint('to err', file=sys.stderr)"
    result = run(client, code)

    names = {}
    for stream in only(result.outputs, "stream"):
        names[stream["name"]] = names.get(stream["name"], "") + stream["text"]

    assert names == {"stdout": "to out\n", "stderr": "to err\n"}, names


def check_an_error_comes_back_structured(client: BlockingKernelClient) -> None:
    result = run(client, "1 / 0")
    error = only(result.outputs, "error")[0]

    assert result.status == "error"
    assert error["ename"] == "ZeroDivisionError"
    assert error["evalue"] == "division by zero"
    assert error["traceback"]


def check_a_plotly_figure_arrives_as_a_spec(client: BlockingKernelClient) -> None:
    code = "import plotly.express as px\npx.bar(x=['a', 'b'], y=[1, 2]).show()"
    result = run(client, code)
    displays = only(result.outputs, "display_data")

    assert len(displays) == 1, result.outputs

    bundle = displays[0]["data"]
    assert PLOTLY_MIME in bundle, list(bundle)
    assert "text/html" not in bundle, "the figure also came as HTML"
    assert set(bundle[PLOTLY_MIME]) >= {"data", "layout"}


def check_a_dataframe_arrives_as_a_table(client: BlockingKernelClient) -> None:
    code = "import pandas as pd\npd.DataFrame({'region': ['N', 'S'], 'sales': [1, 2]})"
    result = run(client, code)
    value = only(result.outputs, "execute_result")[0]["data"]

    assert "text/html" in value, list(value)
    assert "<table" in value["text/html"]


def check_matplotlib_arrives_as_an_image(client: BlockingKernelClient) -> None:
    code = "import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.show()"
    result = run(client, code)
    displays = only(result.outputs, "display_data")

    assert len(displays) == 1, result.outputs
    assert "image/png" in displays[0]["data"]


CHECKS: list[Callable[[BlockingKernelClient], None]] = [
    check_runs_unprivileged,
    check_every_package_imports,
    check_state_survives_between_executions,
    check_stdout_and_stderr_arrive_apart,
    check_an_error_comes_back_structured,
    check_a_plotly_figure_arrives_as_a_spec,
    check_a_dataframe_arrives_as_a_table,
    check_matplotlib_arrives_as_an_image,
]


def main() -> None:
    assert os.getuid() != 0, "the image runs as root"

    manager, client = start_new_kernel(kernel_name="python3", startup_timeout=TIMEOUT_SECONDS)
    try:
        for check in CHECKS:
            check(client)
            print(f"ok  {check.__name__}")
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)


if __name__ == "__main__":
    main()
