"""POST /conversations/{id}/messages, and the run that answers — end to end
through the API, with a scripted model and kernel standing in for real ones."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from app.domain.llm import ProviderError, Reply, UserText
from app.main import app
from fastapi.testclient import TestClient
from tests.agent_fakes import ScriptedKernel, ScriptedModel, answers, asks, prints, wants
from tests.auth_helpers import ANA, RAFAEL, bearer, sign_up_and_in
from tests.conftest import Run
from tests.message_helpers import ScriptedRegistry, events_of, send, settled

CONVERSATIONS = "/api/v1/conversations"


@pytest.fixture
def token(client: TestClient) -> str:
    return sign_up_and_in(client, RAFAEL)


@pytest.fixture
def conversation(client: TestClient, token: str) -> str:
    model = client.post(
        "/api/v1/models",
        headers=bearer(token),
        json={
            "name": "Scripted",
            "adapter": "openai_compatible",
            "base_url": "http://scripted.example/v1",
            "model": "scripted",
            "dialect": "tools",
        },
    ).json()
    created = client.post(CONVERSATIONS, headers=bearer(token), json={"model_id": model["id"]})

    return str(created.json()["id"])


@pytest.fixture
def script(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Call with the model's replies and the kernel's runs; returns the model."""

    def set_up(replies: list[Reply], runs: list[Any]) -> ScriptedModel:
        model = ScriptedModel(replies)
        monkeypatch.setattr("app.runs.message.model_for", lambda endpoint, http: model)
        monkeypatch.setattr(app.state, "kernels", ScriptedRegistry(ScriptedKernel(runs)))
        return model

    yield set_up


# ── the request ──────────────────────────────────────────────────────────────


def test_a_message_is_accepted_with_its_run(
    client: TestClient, token: str, conversation: str, script: Any
) -> None:
    script([answers("Hi.")], [])

    response = send(client, token, conversation, "Hello?")

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"message", "run_id"}
    assert body["message"]["role"] == "user"
    assert body["message"]["text"] == "Hello?"
    assert body["message"]["run_id"] == body["run_id"]


def test_a_conversation_without_a_model_cannot_be_asked(client: TestClient, token: str) -> None:
    bare = client.post(CONVERSATIONS, headers=bearer(token), json={}).json()

    response = send(client, token, bare["id"], "Hello?")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_MODEL_SELECTED"


def test_a_busy_conversation_cannot_be_asked(
    client: TestClient, token: str, conversation: str, sql: Run
) -> None:
    sql(
        """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id, 'cell' FROM conversations c WHERE c.external_id = %(id)s
        """,
        {"id": conversation},
    )

    response = send(client, token, conversation, "Hello?")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONVERSATION_BUSY"
    assert sql("SELECT m.id FROM messages m") == []


def test_an_empty_message_is_a_validation_error(
    client: TestClient, token: str, conversation: str
) -> None:
    assert send(client, token, conversation, "").status_code == 422


def test_someone_elses_conversation_is_not_found(
    client: TestClient, token: str, conversation: str
) -> None:
    ana = sign_up_and_in(client, ANA)

    response = send(client, ana, conversation, "Hello?")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


# ── the run ──────────────────────────────────────────────────────────────────


def test_a_question_becomes_cells_and_an_answer(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    script(
        [wants("print(1840231.5)", text="Let me add it up."), answers("Sudeste: 1840231.5.")],
        [prints("1840231.5\n")],
    )

    run_id = send(client, token, conversation, "Which region?").json()["run_id"]

    assert settled(sql, run_id) == "succeeded"
    body = client.get(f"{CONVERSATIONS}/{conversation}", headers=bearer(token)).json()

    assert [(m["role"], m["text"]) for m in body["messages"]] == [
        ("user", "Which region?"),
        ("assistant", "Sudeste: 1840231.5."),
    ]
    assert len(body["cells"]) == 1
    cell = body["cells"][0]
    assert cell["origin"] == "agent"
    assert cell["source"] == "print(1840231.5)"
    assert cell["status"] == "ok"
    assert cell["run_id"] == run_id
    assert cell["outputs"] == [{"kind": "stream", "name": "stdout", "text": "1840231.5\n"}]
    assert body["active_run_id"] is None


def test_every_event_is_stored_in_order_without_gaps(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    script([wants("print(2)"), answers("2.")], [prints("2\n")])

    run_id = send(client, token, conversation, "Two?").json()["run_id"]
    settled(sql, run_id)
    events = events_of(sql, run_id)

    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "run.started"
    assert events[0]["kind"] == "message"
    assert events[0]["model"] == "scripted"
    assert events[-1]["type"] == "run.finished"
    assert events[-1]["status"] == "succeeded"
    assert events[-1]["tokens_in"] == 200

    types = [e["type"] for e in events]
    assert types.index("kernel.ready") < types.index("llm.started")
    assert types[-3:] == ["answer", "grounding.checked", "run.finished"]
    for event in events:
        assert isinstance(event["t"], float | int)


def test_the_run_records_its_tokens(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    script([answers("Hi.")], [])

    run_id = send(client, token, conversation, "Hi?").json()["run_id"]
    settled(sql, run_id)

    rows = sql(
        "SELECT r.tokens_in, r.tokens_out, r.model_name FROM runs r WHERE r.external_id = %(id)s",
        {"id": run_id},
    )
    assert rows == [(100, 30, "scripted")]


def test_a_question_back_leaves_the_run_awaiting_the_user(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    script([asks("2024 or 2025?")], [])

    run_id = send(client, token, conversation, "Sales this year?").json()["run_id"]

    assert settled(sql, run_id) == "awaiting_user"
    events = events_of(sql, run_id)
    assert events[-2]["type"] == "question"
    assert events[-2]["message"]["text"] == "2024 or 2025?"
    assert events[-1]["status"] == "awaiting_user"


def test_a_provider_failure_is_a_run_error_then_a_failed_run(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    model = script([], [])

    async def broken(system: str, history: Any, on_delta: Any) -> Reply:
        raise ProviderError("overloaded", "Overloaded")

    model.complete = broken

    run_id = send(client, token, conversation, "Hi?").json()["run_id"]

    assert settled(sql, run_id) == "failed"
    events = events_of(sql, run_id)
    assert events[-2]["type"] == "run.error"
    assert events[-2]["code"] == "MODEL_UNAVAILABLE"
    assert "Overloaded" in events[-2]["message"]
    assert events[-1]["type"] == "run.finished"


def test_the_model_is_briefed_with_files_and_notebook(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    first = script([wants("x = 41"), answers("Set.")], [prints("")])
    run_id = send(client, token, conversation, "Set x.").json()["run_id"]
    settled(sql, run_id)

    second = script([answers("It is 41.")], [])
    run_id = send(client, token, conversation, "What is x?").json()["run_id"]
    settled(sql, run_id)

    history = second.seen[0]
    assert [type(item).__name__ for item in history] == ["UserText", "AssistantTurn", "UserText"]
    briefing = history[-1]
    assert isinstance(briefing, UserText)
    assert "<notebook>" in briefing.text
    assert "x = 41" in briefing.text
    assert briefing.text.endswith("What is x?")
    assert first.seen[0][-1].text.endswith("Set x.")  # type: ignore[union-attr]


def test_a_kernel_lost_since_the_cells_ran_is_announced(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    script([wants("x = 41"), answers("Set.")], [prints("")])
    settled(sql, send(client, token, conversation, "Set x.").json()["run_id"])

    # A new registry: as after the API restarted and every kernel was reaped.
    second = script([answers("Gone.")], [])
    run_id = send(client, token, conversation, "What is x?").json()["run_id"]
    settled(sql, run_id)

    assert {"reason": "lost"} in [
        {"reason": e["reason"]} for e in events_of(sql, run_id) if e["type"] == "kernel.restarted"
    ]
    assert "The kernel was restarted" in second.seen[0][-1].text  # type: ignore[union-attr]
