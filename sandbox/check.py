"""Proves the image does its job: a kernel starts, and what generated code needs
comes out of it in the shapes the API expects.

Runs inside the image, against a real kernel started on loopback. It needs no
network, and is meant to run with none:

    docker compose run --rm sandbox

Each check prints its name when it passes; the first failure stops the run with
a non-zero exit.
"""

from __future__ import annotations

import json
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
    "nbclient",
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
TABLE_MIME = "application/vnd.not-a-notebook.table+json"


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
    code = "import pandas as pd\npd.DataFrame({'region': ['N', None], 'sales': [1.5, None]})"
    result = run(client, code)
    value = only(result.outputs, "execute_result")[0]["data"]

    assert value[TABLE_MIME] == {
        "columns": ["region", "sales"],
        "rows": [["N", 1.5], [None, None]],
        "total_rows": 2,
    }


def check_a_grouped_result_keeps_its_keys(client: BlockingKernelClient) -> None:
    code = (
        "import pandas as pd\n"
        "df = pd.DataFrame({'region': ['N', 'S', 'N'], 'sales': [1, 2, 3]})\n"
        "df.groupby('region')['sales'].sum()"
    )
    result = run(client, code)
    table = only(result.outputs, "execute_result")[0]["data"][TABLE_MIME]

    assert table["columns"] == ["region", "sales"]
    assert table["rows"] == [["N", 4], ["S", 2]]


def check_a_long_table_travels_cut_but_counted(client: BlockingKernelClient) -> None:
    code = "import polars as pl\npl.DataFrame({'n': range(250)})"
    result = run(client, code)
    table = only(result.outputs, "execute_result")[0]["data"][TABLE_MIME]

    assert len(table["rows"]) == 100
    assert table["total_rows"] == 250


def check_the_namespace_starts_clean(client: BlockingKernelClient) -> None:
    """The display extension must leave nothing behind for the model to trip on."""
    result = run(client, "print(sorted(n for n in dir() if not n.startswith('_')))")
    names = only(result.outputs, "stream")[0]["text"].strip()

    assert names == "['In', 'Out', 'exit', 'get_ipython', 'open', 'quit']", names


def check_a_brazilian_csv_is_profiled(client: BlockingKernelClient) -> None:
    """Semicolons and Latin-1: what a CSV saved by a Brazilian Excel looks like."""
    content = "região;vendas\nSão Paulo;1.234,56\nNordeste;\n".encode("latin-1")
    with open("/tmp/vendas.csv", "wb") as target:
        target.write(content)

    code = "__import__('not_a_notebook_profile').emit('/tmp/vendas.csv')"
    result = run(client, code)
    profile = json.loads(only(result.outputs, "stream")[0]["text"])

    assert profile["readable"] is True, profile
    assert profile["encoding"] == "latin-1"

    table = profile["tables"][0]
    assert table["rows"] == 2
    assert [column["name"] for column in table["columns"]] == ["região", "vendas"]
    assert table["columns"][1]["missing"] == 1


def check_an_unreadable_file_is_still_a_profile(client: BlockingKernelClient) -> None:
    with open("/tmp/broken.parquet", "wb") as target:
        target.write(b"this is not parquet")

    code = "__import__('not_a_notebook_profile').emit('/tmp/broken.parquet')"
    result = run(client, code)
    profile = json.loads(only(result.outputs, "stream")[0]["text"])

    assert profile["readable"] is False
    assert profile["error"]


def check_profiling_leaves_the_namespace_clean(client: BlockingKernelClient) -> None:
    result = run(client, "print('not_a_notebook_profile' in dir())")

    assert only(result.outputs, "stream")[0]["text"] == "False\n"


def check_matplotlib_arrives_as_an_image(client: BlockingKernelClient) -> None:
    code = "import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.show()"
    result = run(client, code)
    displays = only(result.outputs, "display_data")

    assert len(displays) == 1, result.outputs
    assert "image/png" in displays[0]["data"]


CHECKS: list[Callable[[BlockingKernelClient], None]] = [
    check_the_namespace_starts_clean,
    check_runs_unprivileged,
    check_every_package_imports,
    check_state_survives_between_executions,
    check_stdout_and_stderr_arrive_apart,
    check_an_error_comes_back_structured,
    check_a_plotly_figure_arrives_as_a_spec,
    check_a_dataframe_arrives_as_a_table,
    check_a_grouped_result_keeps_its_keys,
    check_a_long_table_travels_cut_but_counted,
    check_matplotlib_arrives_as_an_image,
    check_a_brazilian_csv_is_profiled,
    check_an_unreadable_file_is_still_a_profile,
    check_profiling_leaves_the_namespace_clean,
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
