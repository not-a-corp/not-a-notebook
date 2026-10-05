"""GET /conversations/{id}/export: the notebook and the script, and where the
chat goes among the cells."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.domain.messages import Message
from app.export.arrange import Ran, Said, arrange
from app.export.notebook import notebook
from app.export.script import script
from fastapi.testclient import TestClient
from tests.conftest import Run
from tests.support.auth import ANA, RAFAEL, bearer, sign_up_and_in

CONVERSATIONS = "/api/v1/conversations"
START = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)


def at(minute: int) -> datetime:
    return START + timedelta(minutes=minute)


def message(role: str, text: str, run_id: UUID | None, minute: int) -> Message:
    kind = None
    if role == "assistant":
        kind = "answer"
    return Message.model_validate(
        {
            "id": uuid4(),
            "role": role,
            "run_id": run_id,
            "text": text,
            "kind": kind,
            "grounding": None,
            "created_at": at(minute),
        }
    )


def cell(
    source: str, run_id: UUID | None, outputs: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "run_id": str(run_id) if run_id is not None else None,
        "source": source,
        "execution_count": 1,
        "outputs": outputs or [],
    }


def shape(entries: list[Any]) -> list[str]:
    shown = []
    for entry in entries:
        if isinstance(entry, Said):
            shown.append(entry.message.text)
        if isinstance(entry, Ran):
            shown.append(entry.cell["source"])
    return shown


# ── where the chat goes ──────────────────────────────────────────────────────


def test_each_question_opens_its_cells_and_its_answer_closes_them() -> None:
    first, second = uuid4(), uuid4()
    cells = [cell("a = 1", first), cell("b = a", first), cell("c = 2", second)]
    messages = [
        message("user", "Q1", first, 0),
        message("assistant", "A1", first, 1),
        message("user", "Q2", second, 2),
        message("assistant", "A2", second, 3),
    ]

    assert shape(arrange(cells, messages)) == ["Q1", "a = 1", "b = a", "A1", "Q2", "c = 2", "A2"]


def test_a_question_with_no_cells_goes_before_the_next_one_asked() -> None:
    asked, coded = uuid4(), uuid4()
    cells = [cell("x = 1", coded)]
    messages = [
        message("user", "Hi?", asked, 0),
        message("assistant", "Hello.", asked, 1),
        message("user", "Q", coded, 2),
        message("assistant", "A", coded, 3),
    ]

    assert shape(arrange(cells, messages)) == ["Hi?", "Hello.", "Q", "x = 1", "A"]


def test_your_own_cells_keep_their_place_and_late_chat_goes_last() -> None:
    run = uuid4()
    cells = [cell("mine = 0", None), cell("x = 1", run)]
    messages = [
        message("user", "Q", run, 0),
        message("assistant", "A", run, 1),
        message("user", "Thanks", uuid4(), 5),
    ]

    assert shape(arrange(cells, messages)) == ["mine = 0", "Q", "x = 1", "A", "Thanks"]


# ── the notebook ─────────────────────────────────────────────────────────────


def test_outputs_go_back_into_jupyters_own_shapes() -> None:
    run = uuid4()
    outputs = [
        {"kind": "stream", "name": "stdout", "text": "42\n"},
        {"kind": "error", "name": "KeyError", "value": "'x'", "traceback": ["KeyError: 'x'"]},
        {"kind": "plotly", "spec": {"data": [], "layout": {}}},
        {"kind": "table", "columns": ["região"], "rows": [["Sudeste"], [None]], "total_rows": 9},
        {"kind": "text", "text": "4"},
        {"kind": "image", "png": "iVBOR"},
    ]

    document = json.loads(notebook("Vendas", [], [cell("x", run, outputs)], []))
    code = document["cells"][1]

    assert document["nbformat"] == 4
    assert document["metadata"]["kernelspec"]["name"] == "python3"
    assert [o["output_type"] for o in code["outputs"]] == [
        "stream",
        "error",
        "display_data",
        "display_data",
        "execute_result",
        "display_data",
    ]
    assert code["outputs"][1]["ename"] == "KeyError"
    assert "application/vnd.plotly.v1+json" in code["outputs"][2]["data"]
    assert "<td>null</td>" in code["outputs"][3]["data"]["text/html"]
    assert "2 of 9 rows" in code["outputs"][3]["data"]["text/html"]
    assert code["outputs"][4]["data"] == {"text/plain": "4"}
    assert code["outputs"][5]["data"]["image/png"] == "iVBOR"


def test_the_top_says_where_the_files_are_expected() -> None:
    document = json.loads(notebook("Vendas 2025", ["vendas.csv"], [], []))
    top = document["cells"][0]

    assert top["cell_type"] == "markdown"
    assert top["source"].startswith("# Vendas 2025")
    assert "`/data/vendas.csv`" in top["source"]


def test_the_script_runs_cell_by_cell_with_the_chat_as_comments() -> None:
    run = uuid4()
    text = script(
        "Vendas",
        ["vendas.csv"],
        [cell("import pandas as pd\nprint(1)", run)],
        [
            message("user", "Qual região?", run, 0),
            message("assistant", "Sudeste.\n\nPronto.", run, 1),
        ],
    )

    assert "# **You:** Qual região?\n\n# %%\nimport pandas as pd\nprint(1)\n\n" in text
    assert "# **Analyst:**\n#\n# Sudeste.\n#\n# Pronto." in text
    compile(text, "export.py", "exec")


# ── the route ────────────────────────────────────────────────────────────────


@pytest.fixture
def token(client: TestClient) -> str:
    return sign_up_and_in(client, RAFAEL)


def conversation_with_a_cell(client: TestClient, token: str, sql: Run) -> str:
    created = client.post(
        CONVERSATIONS, headers=bearer(token), json={"title": "Faturamento é 2025"}
    )
    conversation = created.json()["id"]
    client.post(
        f"{CONVERSATIONS}/{conversation}/cells",
        headers=bearer(token),
        json={"source": "print(42)"},
    )
    sql(
        """
        INSERT INTO messages AS m (conversation_id, role, text)
        SELECT c.id, 'user', 'Quanto?'
          FROM conversations c
         WHERE c.external_id = %(id)s
        """,
        {"id": conversation},
    )
    return str(conversation)


def test_exports_a_notebook_as_an_attachment(client: TestClient, token: str, sql: Run) -> None:
    conversation = conversation_with_a_cell(client, token, sql)

    response = client.get(
        f"{CONVERSATIONS}/{conversation}/export", headers=bearer(token), params={"format": "ipynb"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ipynb+json")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="Faturamento-_-2025.ipynb"')
    assert "filename*=UTF-8''Faturamento-%C3%A9-2025.ipynb" in disposition
    sources = [c["source"] for c in response.json()["cells"]]
    assert "print(42)" in sources
    assert "**You:** Quanto?" in sources


def test_exports_a_script(client: TestClient, token: str, sql: Run) -> None:
    conversation = conversation_with_a_cell(client, token, sql)

    response = client.get(
        f"{CONVERSATIONS}/{conversation}/export", headers=bearer(token), params={"format": "py"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/x-python")
    assert "# %%\nprint(42)" in response.text


def test_an_unknown_format_is_a_validation_error(client: TestClient, token: str, sql: Run) -> None:
    conversation = conversation_with_a_cell(client, token, sql)

    response = client.get(
        f"{CONVERSATIONS}/{conversation}/export", headers=bearer(token), params={"format": "pdf"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_someone_elses_conversation_is_not_found(client: TestClient, token: str, sql: Run) -> None:
    conversation = conversation_with_a_cell(client, token, sql)
    other = sign_up_and_in(client, ANA)

    response = client.get(
        f"{CONVERSATIONS}/{conversation}/export", headers=bearer(other), params={"format": "ipynb"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
