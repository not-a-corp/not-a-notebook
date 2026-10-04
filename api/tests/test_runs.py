"""GET /runs/{id} and GET /runs/{id}/events: the record, and the stream —
replayed, resumed, followed live, kept alive, and ended even for a run whose
process died."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from app.domain.llm import Item, OnDelta, Reply
from app.main import app
from fastapi.testclient import TestClient
from tests.conftest import Run
from tests.support.agent import ScriptedKernel, ScriptedModel, answers, prints, wants
from tests.support.auth import ANA, RAFAEL, bearer, sign_up_and_in
from tests.support.kernels import FakeRegistry
from tests.support.runs import events_of, send, settled

RUNS = "/api/v1/runs"
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
    def set_up(replies: list[Reply], runs: list[Any]) -> ScriptedModel:
        model = ScriptedModel(replies)
        monkeypatch.setattr("app.jobs.message.model_for", lambda endpoint, http: model)
        monkeypatch.setattr(app.state, "kernels", FakeRegistry.scripted(ScriptedKernel(runs)))
        return model

    yield set_up


def parsed(body: str) -> tuple[list[dict[str, Any]], int]:
    """The stream's events, checking each against its SSE framing, and how many
    keepalive comments came between them."""
    events = []
    keepalives = 0

    for block in body.split("\n\n"):
        if not block:
            continue

        if block == ": keepalive":
            keepalives += 1
            continue

        lines = block.split("\n")
        name = lines[0].removeprefix("event: ")
        seq = int(lines[1].removeprefix("id: "))
        event = json.loads(lines[2].removeprefix("data: "))

        assert event["type"] == name
        assert event["seq"] == seq
        events.append(event)

    return events, keepalives


def stream_of(client: TestClient, token: str, run_id: str, last: int | None = None) -> str:
    headers = bearer(token)
    if last is not None:
        headers["Last-Event-ID"] = str(last)

    with client.stream("GET", f"{RUNS}/{run_id}/events", headers=headers) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return response.read().decode()


def finished_run(client: TestClient, token: str, conversation: str, script: Any, sql: Run) -> str:
    script([wants("print(2)"), answers("2.")], [prints("2\n")])
    run_id: str = send(client, token, conversation, "Two?").json()["run_id"]
    settled(sql, run_id)

    return run_id


# ── the record ───────────────────────────────────────────────────────────────


def test_a_run_shows_its_record(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    run_id = finished_run(client, token, conversation, script, sql)

    response = client.get(f"{RUNS}/{run_id}", headers=bearer(token))

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {
        "id",
        "conversation_id",
        "kind",
        "status",
        "model",
        "tokens_in",
        "tokens_out",
        "tokens_reasoning",
        "started_at",
        "finished_at",
        "wall_ms",
    }
    assert body["conversation_id"] == conversation
    assert body["kind"] == "message"
    assert body["status"] == "succeeded"
    assert body["model"] == "scripted"
    assert body["tokens_in"] == 200
    assert body["wall_ms"] >= 0


def test_someone_elses_run_is_not_found_nor_streamed(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    run_id = finished_run(client, token, conversation, script, sql)
    ana = sign_up_and_in(client, ANA)

    record = client.get(f"{RUNS}/{run_id}", headers=bearer(ana))
    events = client.get(f"{RUNS}/{run_id}/events", headers=bearer(ana))

    for response in (record, events):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


# ── the stream ───────────────────────────────────────────────────────────────


def test_a_finished_run_replays_whole_and_closes(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    run_id = finished_run(client, token, conversation, script, sql)

    events, _ = parsed(stream_of(client, token, run_id))

    assert events == events_of(sql, run_id)
    assert events[0]["type"] == "run.started"
    assert events[-1]["type"] == "run.finished"


def test_last_event_id_resumes_after_it(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    run_id = finished_run(client, token, conversation, script, sql)

    events, _ = parsed(stream_of(client, token, run_id, last=5))

    assert events[0]["seq"] == 6
    assert events == events_of(sql, run_id)[5:]


def test_a_run_in_progress_is_followed_live_without_loss_or_repeat(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    """The stream attaches while the model is still thinking: what was stored is
    replayed, what comes after arrives live, and the seams do not show."""
    model = script([wants("print(2)"), answers("2.")], [prints("2\n")])
    scripted = model.complete

    async def slow(system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        await asyncio.sleep(0.4)
        return await scripted(system, history, on_delta)

    model.complete = slow

    run_id = send(client, token, conversation, "Two?").json()["run_id"]
    events, _ = parsed(stream_of(client, token, run_id))

    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["type"] == "run.finished"
    assert events == events_of(sql, run_id)


def test_silence_is_filled_with_keepalives(
    client: TestClient,
    token: str,
    conversation: str,
    script: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.jobs.stream.KEEPALIVE_SECONDS", 0.05)
    model = ScriptedModel([answers("Done.")])
    scripted = model.complete

    async def thinking(system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        await asyncio.sleep(0.4)
        return await scripted(system, history, on_delta)

    model.complete = thinking
    script([], [])
    monkeypatch.setattr("app.jobs.message.model_for", lambda endpoint, http: model)

    run_id = send(client, token, conversation, "Think.").json()["run_id"]
    events, keepalives = parsed(stream_of(client, token, run_id))

    assert keepalives >= 2
    assert events[-1]["type"] == "run.finished"


def test_a_run_whose_process_died_still_ends_its_stream(
    client: TestClient, token: str, conversation: str, sql: Run, migrated_database: str
) -> None:
    rows = sql(
        """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id, 'cell' FROM conversations c WHERE c.external_id = %(id)s
        RETURNING r.id, r.external_id::text
        """,
        {"id": conversation},
    )
    row_id, run_id = rows[0]
    started = {"seq": 1, "t": 0.0, "type": "run.started", "kind": "cell"}
    sql(
        """
        INSERT INTO run_events AS e (run_id, seq, type, event)
        VALUES (%(run)s, 1, 'run.started', %(event)s)
        """,
        {"run": row_id, "event": json.dumps(started)},
    )

    # The API starts again, as after the crash, and the client reconnects to it.
    with TestClient(app, base_url="https://testserver") as again:
        events, _ = parsed(stream_of(again, token, run_id))

    assert [event["type"] for event in events] == ["run.started", "run.error", "run.finished"]
    assert events[1]["code"] == "INTERNAL_ERROR"
    assert events[2]["status"] == "failed"
    assert [event["seq"] for event in events] == [1, 2, 3]


def test_cancelling_while_the_model_thinks_ends_the_run_cancelled(
    client: TestClient, token: str, conversation: str, script: Any, sql: Run
) -> None:
    model = script([answers("never sent")], [])

    async def forever(system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        await asyncio.sleep(60)
        raise AssertionError("the request should have been abandoned")

    model.complete = forever
    run_id = send(client, token, conversation, "Think forever.").json()["run_id"]

    deadline = time.monotonic() + 10
    while not [e for e in events_of(sql, run_id) if e["type"] == "llm.started"]:
        assert time.monotonic() < deadline
        time.sleep(0.02)

    response = client.post(f"{RUNS}/{run_id}/cancel", headers=bearer(token))

    assert response.status_code == 202
    assert settled(sql, run_id) == "cancelled"
    events = events_of(sql, run_id)
    assert events[-1]["type"] == "run.finished"
    assert events[-1]["status"] == "cancelled"
    assert "run.error" not in [e["type"] for e in events]
