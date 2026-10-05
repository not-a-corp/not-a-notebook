"""Phase 6, cells as objects: write, edit, delete and run them; stale marks; Run
all; restart; cancel — through the API, with a scripted kernel."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from app.main import app
from fastapi.testclient import TestClient
from tests.conftest import Run as Sql
from tests.support.agent import Run, ScriptedKernel, fails, prints
from tests.support.auth import ANA, RAFAEL, bearer, sign_up_and_in
from tests.support.kernels import FakeRegistry
from tests.support.runs import events_of, settled

CONVERSATIONS = "/api/v1/conversations"
CELLS = "/api/v1/cells"


@pytest.fixture
def token(client: TestClient) -> str:
    return sign_up_and_in(client, RAFAEL)


@pytest.fixture
def conversation(client: TestClient, token: str) -> str:
    return str(client.post(CONVERSATIONS, headers=bearer(token), json={}).json()["id"])


@pytest.fixture
def kernel(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Call with the kernel's runs; returns the registry handing it out."""

    def set_up(runs: list[Run]) -> FakeRegistry:
        registry = FakeRegistry.scripted(ScriptedKernel(runs))
        monkeypatch.setattr(app.state, "kernels", registry)
        return registry

    yield set_up


def add(client: TestClient, token: str, conversation: str, source: str, **where: Any) -> Any:
    body: dict[str, Any] = {"source": source}
    for field, value in where.items():
        body[field] = value

    response = client.post(
        f"{CONVERSATIONS}/{conversation}/cells", headers=bearer(token), json=body
    )
    assert response.status_code == 201, response.text

    return response.json()


def cells(client: TestClient, token: str, conversation: str) -> list[dict[str, Any]]:
    body = client.get(f"{CONVERSATIONS}/{conversation}", headers=bearer(token)).json()
    found: list[dict[str, Any]] = body["cells"]
    return found


def run(client: TestClient, token: str, cell_id: str, sql: Sql) -> str:
    response = client.post(f"{CELLS}/{cell_id}/run", headers=bearer(token))
    assert response.status_code == 202, response.text

    run_id: str = response.json()["run_id"]
    settled(sql, run_id)
    return run_id


def sources(client: TestClient, token: str, conversation: str) -> list[str]:
    return [cell["source"] for cell in cells(client, token, conversation)]


# ── writing cells ────────────────────────────────────────────────────────────


def test_a_new_cell_goes_at_the_end_and_does_not_run(
    client: TestClient, token: str, conversation: str
) -> None:
    add(client, token, conversation, "a = 1")
    cell = add(client, token, conversation, "b = 2")

    assert cell["origin"] == "user"
    assert cell["status"] == "new"
    assert cell["run_id"] is None
    assert cell["execution_count"] is None
    assert sources(client, token, conversation) == ["a = 1", "b = 2"]


def test_null_puts_a_cell_first_and_an_id_puts_it_after_that_cell(
    client: TestClient, token: str, conversation: str
) -> None:
    first = add(client, token, conversation, "first")
    add(client, token, conversation, "last")

    add(client, token, conversation, "top", after_cell_id=None)
    add(client, token, conversation, "middle", after_cell_id=first["id"])

    assert sources(client, token, conversation) == ["top", "first", "middle", "last"]
    positions = [cell["position"] for cell in cells(client, token, conversation)]
    assert positions == [1, 2, 3, 4]


def test_after_a_cell_of_another_conversation_is_not_found(
    client: TestClient, token: str, conversation: str
) -> None:
    other = client.post(CONVERSATIONS, headers=bearer(token), json={}).json()["id"]
    elsewhere = add(client, token, other, "x")

    response = client.post(
        f"{CONVERSATIONS}/{conversation}/cells",
        headers=bearer(token),
        json={"source": "y", "after_cell_id": elsewhere["id"]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CELL_NOT_FOUND"


def test_someone_elses_cells_are_not_found_by_any_route(
    client: TestClient, token: str, conversation: str
) -> None:
    cell = add(client, token, conversation, "mine")
    ana = sign_up_and_in(client, ANA)

    edited = client.patch(f"{CELLS}/{cell['id']}", headers=bearer(ana), json={"source": "x"})
    ran = client.post(f"{CELLS}/{cell['id']}/run", headers=bearer(ana))
    deleted = client.delete(f"{CELLS}/{cell['id']}", headers=bearer(ana))
    added = client.post(
        f"{CONVERSATIONS}/{conversation}/cells", headers=bearer(ana), json={"source": "x"}
    )

    for response in (edited, ran, deleted):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CELL_NOT_FOUND"
    assert added.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


# ── running one ──────────────────────────────────────────────────────────────


def test_running_a_cell_streams_its_outputs_and_keeps_them(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    kernel([prints("42\n")])
    cell = add(client, token, conversation, "print(42)")

    run_id = run(client, token, cell["id"], sql)

    events = events_of(sql, run_id)
    assert [e["type"] for e in events] == [
        "run.started",
        "kernel.starting",
        "kernel.ready",
        "cell.started",
        "cell.output",
        "cell.finished",
        "run.finished",
    ]
    assert events[0]["kind"] == "cell"
    assert events[3]["cell_id"] == cell["id"]
    assert events[4]["attempt"] is None
    assert events[4]["text"] == "42\n"
    assert events[-1]["status"] == "succeeded"

    shown = cells(client, token, conversation)[0]
    assert shown["status"] == "ok"
    assert shown["execution_count"] == 1
    assert shown["outputs"] == [{"kind": "stream", "name": "stdout", "text": "42\n"}]


def test_running_a_cell_marks_the_ones_below_that_ran_stale(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    kernel([prints("a"), prints("b"), prints("a again")])
    a = add(client, token, conversation, "a")
    b = add(client, token, conversation, "b")
    add(client, token, conversation, "never ran")
    run(client, token, a["id"], sql)
    run(client, token, b["id"], sql)

    run_id = run(client, token, a["id"], sql)

    stale = [e for e in events_of(sql, run_id) if e["type"] == "cells.stale"]
    assert stale == [stale[0]] and stale[0]["cell_ids"] == [b["id"]]
    assert [c["stale"] for c in cells(client, token, conversation)] == [False, True, False]


def test_code_that_raises_is_the_cells_error_not_the_runs(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    kernel([fails("ZeroDivisionError", "division by zero")])
    cell = add(client, token, conversation, "1 / 0")

    run_id = run(client, token, cell["id"], sql)

    assert events_of(sql, run_id)[-1]["status"] == "succeeded"
    shown = cells(client, token, conversation)[0]
    assert shown["status"] == "error"
    assert shown["outputs"][0]["name"] == "ZeroDivisionError"


# ── editing and deleting ─────────────────────────────────────────────────────


def test_editing_changes_the_source_and_stales_what_ran_below(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    kernel([prints("a"), prints("b")])
    a = add(client, token, conversation, "a")
    b = add(client, token, conversation, "b")
    run(client, token, a["id"], sql)
    run(client, token, b["id"], sql)

    response = client.patch(f"{CELLS}/{a['id']}", headers=bearer(token), json={"source": "a2"})

    assert response.status_code == 200
    assert response.json()["source"] == "a2"
    assert [c["stale"] for c in cells(client, token, conversation)] == [False, True]


def test_deleting_stales_what_ran_below(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    kernel([prints("a"), prints("b")])
    a = add(client, token, conversation, "a")
    b = add(client, token, conversation, "b")
    run(client, token, a["id"], sql)
    run(client, token, b["id"], sql)

    response = client.delete(f"{CELLS}/{a['id']}", headers=bearer(token))

    assert response.status_code == 204
    remaining = cells(client, token, conversation)
    assert [c["id"] for c in remaining] == [b["id"]]
    assert remaining[0]["stale"] is True


def test_cells_cannot_change_while_a_run_is_in_progress(
    client: TestClient, token: str, conversation: str, sql: Sql
) -> None:
    cell = add(client, token, conversation, "x")
    sql(
        "INSERT INTO runs AS r (conversation_id, kind) "
        "SELECT c.id, 'cell' FROM conversations c WHERE c.external_id = %(id)s",
        {"id": conversation},
    )

    edited = client.patch(f"{CELLS}/{cell['id']}", headers=bearer(token), json={"source": "y"})
    deleted = client.delete(f"{CELLS}/{cell['id']}", headers=bearer(token))
    ran = client.post(f"{CELLS}/{cell['id']}/run", headers=bearer(token))

    for response in (edited, deleted, ran):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONVERSATION_BUSY"


# ── Run all ──────────────────────────────────────────────────────────────────


def test_run_all_restarts_and_runs_everything_in_order_clearing_stale(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    registry = kernel([prints("a"), prints("b"), prints("a"), prints("b"), prints("c")])
    a = add(client, token, conversation, "a")
    b = add(client, token, conversation, "b")
    add(client, token, conversation, "c")
    run(client, token, b["id"], sql)
    run(client, token, a["id"], sql)  # b is stale now

    response = client.post(f"{CONVERSATIONS}/{conversation}/run-all", headers=bearer(token))
    run_id = response.json()["run_id"]
    settled(sql, run_id)

    events = events_of(sql, run_id)
    assert events[0]["kind"] == "run_all"
    restarted = [e["reason"] for e in events if e["type"] == "kernel.restarted"]
    assert restarted == ["run_all"]
    assert registry.kernel.executed[-3:] == ["a", "b", "c"]
    started = [e["cell_id"] for e in events if e["type"] == "cell.started"]
    assert started == [c["id"] for c in cells(client, token, conversation)]
    assert [c["stale"] for c in cells(client, token, conversation)] == [False, False, False]
    assert [c["status"] for c in cells(client, token, conversation)] == ["ok", "ok", "ok"]


def test_run_all_stops_at_the_first_error(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    registry = kernel([prints("c"), prints("a"), fails()])
    add(client, token, conversation, "a")
    add(client, token, conversation, "b")
    c = add(client, token, conversation, "c")
    run(client, token, c["id"], sql)

    run_id = client.post(f"{CONVERSATIONS}/{conversation}/run-all", headers=bearer(token)).json()[
        "run_id"
    ]
    settled(sql, run_id)

    assert registry.kernel.executed == ["c", "a", "b"]
    shown = cells(client, token, conversation)
    assert [cell["status"] for cell in shown] == ["ok", "error", "ok"]
    # c ran in the old kernel, before b failed in the new one.
    assert shown[2]["stale"] is True


# ── restart and cancel ───────────────────────────────────────────────────────


def test_a_restart_is_announced_by_the_next_run(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    kernel([prints("1"), prints("2")])
    cell = add(client, token, conversation, "x = 1")
    run(client, token, cell["id"], sql)

    response = client.post(f"{CONVERSATIONS}/{conversation}/kernel/restart", headers=bearer(token))
    run_id = run(client, token, cell["id"], sql)

    assert response.status_code == 204
    restarted = [e for e in events_of(sql, run_id) if e["type"] == "kernel.restarted"]
    assert [e["reason"] for e in restarted] == ["requested"]


def test_a_cancelled_run_stops_the_code_and_keeps_the_kernel(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    registry = kernel([Run(blocks=True)])
    cell = add(client, token, conversation, "while True: pass")

    run_id = client.post(f"{CELLS}/{cell['id']}/run", headers=bearer(token)).json()["run_id"]
    deadline = time.monotonic() + 10
    while not registry.kernel.running.is_set():
        assert time.monotonic() < deadline
        time.sleep(0.02)

    response = client.post(f"/api/v1/runs/{run_id}/cancel", headers=bearer(token))
    status = settled(sql, run_id)

    assert response.status_code == 202
    assert status == "cancelled"
    assert events_of(sql, run_id)[-1]["status"] == "cancelled"
    assert cells(client, token, conversation)[0]["status"] == "cancelled"
    assert registry.running()  # an interrupt is not a restart


def test_cancelling_a_finished_run_changes_nothing(
    client: TestClient, token: str, conversation: str, kernel: Any, sql: Sql
) -> None:
    kernel([prints("1")])
    cell = add(client, token, conversation, "1")
    run_id = run(client, token, cell["id"], sql)

    response = client.post(f"/api/v1/runs/{run_id}/cancel", headers=bearer(token))

    assert response.status_code == 202
    assert events_of(sql, run_id)[-1]["status"] == "succeeded"


def test_a_conversation_with_no_files_still_gets_a_real_kernel(
    client: TestClient, token: str, conversation: str, sql: Sql
) -> None:
    """No doubles here: the real registry, a real container. A conversation that has
    had no upload has no folder in the files volume, and the kernel mounts it — so
    the folder must be made first. The scripted kernels could not have caught it."""
    cell = add(client, token, conversation, "print(6 * 7)")

    run_id = run(client, token, cell["id"], sql)

    events = events_of(sql, run_id)
    assert events[-1]["status"] == "succeeded", events
    assert cells(client, token, conversation)[0]["outputs"] == [
        {"kind": "stream", "name": "stdout", "text": "42\n"}
    ]
