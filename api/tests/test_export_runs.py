"""The export's promise, as a test (PLAN, Phase 8): a notebook exported from a
conversation runs top to bottom with nbclient in a fresh sandbox, with no edits.

Real containers: the cells run in a kernel, their outputs become the export, and
a new container from the same image — no network, the same files read-only at
/data — executes it."""

from __future__ import annotations

import asyncio
import json
import struct
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from app.config import get_settings
from app.domain.outputs import fields_of, flattened, kind_of
from app.domain.runtime import Output
from app.export.notebook import notebook
from app.runtime.docker_engine import DockerEngine
from app.storage.local import LocalFileStore
from tests.test_runtime_docker import default_limits, make_runtime

pytestmark = pytest.mark.asyncio(loop_scope="module")

CSV = "região;faturamento\nSudeste;4218340.5\nSul;2701115.2\nSudeste;100\n"

CELLS = [
    'import pandas as pd\n\nvendas = pd.read_csv("/data/vendas.csv", sep=";")\nprint(vendas.shape)',
    'por_regiao = vendas.groupby("região")["faturamento"].sum()\n'
    "print(por_regiao.idxmax())\n"
    "por_regiao",
    "import plotly.express as px\n"
    'fig = px.bar(por_regiao.reset_index(), x="região", y="faturamento")\n'
    "fig",
]

# Runs inside the fresh container: execute the notebook it is handed, and say
# what came out, as one line of JSON.
EXECUTE = """
import json, os, nbformat, nbclient
nb = nbformat.reads(os.environ["NOTEBOOK"], as_version=4)
nbformat.validate(nb)
nbclient.NotebookClient(nb, kernel_name="python3", timeout=120).execute()
outputs = [
    [o.get("output_type") + ":" + (o.get("text") or o.get("ename") or ",".join(o.get("data", {})))
     for o in cell.outputs]
    for cell in nb.cells if cell.cell_type == "code"
]
print("RESULT " + json.dumps(outputs))
"""


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def engine() -> AsyncIterator[DockerEngine]:
    docker = DockerEngine.over_socket()
    yield docker
    await docker.close()
    await LocalFileStore(get_settings().files_root).delete_folder("tests-export")


def frames(raw: bytes) -> str:
    """Docker's log stream: 8-byte headers, each before its chunk of output."""
    text = ""
    while len(raw) >= 8:
        size = struct.unpack(">I", raw[4:8])[0]
        text += raw[8 : 8 + size].decode()
        raw = raw[8 + size :]
    return text


async def run_fresh(engine: DockerEngine, folder: str, document: str) -> tuple[int, str]:
    settings = get_settings()
    config: dict[str, Any] = {
        "Image": settings.sandbox_image,
        "Cmd": ["python", "-c", EXECUTE],
        "Env": [f"NOTEBOOK={document}", "JUPYTER_RUNTIME_DIR=/tmp/jupyter"],
        "Labels": {"not-a-notebook.kernel": "export-test"},
        "HostConfig": {
            "NetworkMode": "none",
            "Tmpfs": {"/tmp": "size=256m", "/home/analyst": "size=64m,uid=1000,gid=1000"},
            "Mounts": [
                {
                    "Type": "volume",
                    "Source": settings.files_volume,
                    "Target": "/data",
                    "ReadOnly": True,
                    "VolumeOptions": {"Subpath": folder},
                }
            ],
        },
    }
    container = await engine.create_container(f"nan-export-test-{uuid4().hex[:8]}", config)
    try:
        await engine.start_container(container)
        # Polled rather than POST /wait, which outlasts the client's timeout.
        state: dict[str, Any] = {}
        for _ in range(240):
            state = (await engine.inspect_container(container))["State"]
            if not state["Running"]:
                break
            await asyncio.sleep(0.5)
        logs = await engine.http.get(
            f"/containers/{container}/logs", params={"stdout": "1", "stderr": "1"}
        )
        return int(state["ExitCode"]), frames(logs.content)
    finally:
        await engine.remove_container(container)


async def test_an_exported_notebook_runs_in_a_fresh_sandbox(engine: DockerEngine) -> None:
    settings = get_settings()
    folder = f"tests-export/{uuid4()}"
    store = LocalFileStore(settings.files_root)
    await store.prepare_folder(folder)
    (Path(settings.files_root) / folder / "vendas.csv").write_text(CSV, encoding="utf-8")

    # The conversation's cells, run in a real kernel, outputs kept as api.md shows them.
    kernel = await make_runtime(engine, default_limits()).start(uuid4(), folder)
    cells: list[dict[str, Any]] = []
    try:
        for count, source in enumerate(CELLS, start=1):
            produced: list[Output] = []

            async def keep(output: Output, into: list[Output] = produced) -> None:
                into.append(output)

            result = await kernel.execute(source, keep)
            assert result.status == "ok", produced
            shown = [flattened(kind_of(output), fields_of(output)) for output in produced]
            cells.append(
                {
                    "id": str(uuid4()),
                    "run_id": None,
                    "source": source,
                    "execution_count": count,
                    "outputs": shown,
                }
            )
    finally:
        await kernel.shutdown()

    document = notebook("Vendas", ["vendas.csv"], cells, [])
    # What the kernel produced travels in the export: the chart's spec, the table.
    kinds = [[output["kind"] for output in cell["outputs"]] for cell in cells]
    assert kinds == [["stream"], ["stream", "table"], ["plotly"]]

    status, logs = await run_fresh(engine, folder, document)

    assert status == 0, logs
    result_line = next(line for line in logs.splitlines() if line.startswith("RESULT "))
    rerun = json.loads(result_line.removeprefix("RESULT "))
    assert rerun[0] == ["stream:(3, 2)\n"]
    assert rerun[1][0] == "stream:Sudeste\n"
    assert "application/vnd.plotly.v1+json" in rerun[2][0]
    assert json.loads(document)["cells"][1]["source"] == CELLS[0]
