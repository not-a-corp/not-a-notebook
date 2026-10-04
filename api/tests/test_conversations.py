"""/conversations: create, list, open, change, delete — and only your own."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from tests.conftest import Run
from tests.support.auth import ANA, RAFAEL, bearer, sign_up_and_in

CONVERSATIONS = "/api/v1/conversations"


def create(client: TestClient, token: str, **body: Any) -> dict[str, Any]:
    response = client.post(CONVERSATIONS, headers=bearer(token), json=body)
    assert response.status_code == 201, response.text

    created: dict[str, Any] = response.json()
    return created


def a_model(sql: Run, owner_email: str | None) -> str:
    """A model row: the user's when an email is given, the instance's otherwise."""
    if owner_email is None:
        rows = sql("""
            INSERT INTO models AS m (env_name, name, adapter, model, dialect)
            VALUES ('CLAUDE', 'Claude', 'anthropic', 'claude-sonnet-5-5', 'tools')
            RETURNING m.external_id::text
        """)
        return str(rows[0][0])

    rows = sql(
        """
        INSERT INTO models AS m (user_id, name, adapter, base_url, model, dialect)
        SELECT u.id, 'Local Qwen', 'openai_compatible', 'http://ollama:11434/v1', 'qwen3', 'text'
          FROM users u
         WHERE u.email = %(email)s
        RETURNING m.external_id::text
        """,
        {"email": owner_email},
    )
    return str(rows[0][0])


def start_a_run(sql: Run, conversation_id: str) -> str:
    rows = sql(
        """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id, 'cell'
          FROM conversations c
         WHERE c.external_id = %(id)s
        RETURNING r.external_id::text
        """,
        {"id": conversation_id},
    )
    return str(rows[0][0])


@pytest.fixture
def token(client: TestClient) -> str:
    return sign_up_and_in(client, RAFAEL)


# ── create ───────────────────────────────────────────────────────────────────


def test_creates_an_untitled_conversation_with_no_model(client: TestClient, token: str) -> None:
    body = create(client, token)

    assert set(body) == {
        "id",
        "title",
        "model_id",
        "kernel",
        "active_run_id",
        "created_at",
        "updated_at",
    }
    assert body["title"] == "Untitled"
    assert body["active_run_id"] is None
    assert body["model_id"] is None
    assert body["kernel"] == "stopped"
    UUID(body["id"])


def test_creates_with_a_title(client: TestClient, token: str) -> None:
    body = create(client, token, title="Sales 2025 by region")

    assert body["title"] == "Sales 2025 by region"


@pytest.mark.parametrize("title", ["", "x" * 201])
def test_a_title_must_be_1_to_200_characters(client: TestClient, token: str, title: str) -> None:
    response = client.post(CONVERSATIONS, headers=bearer(token), json={"title": title})

    assert response.status_code == 422


def test_creates_with_the_instances_model(client: TestClient, token: str, sql: Run) -> None:
    model_id = a_model(sql, owner_email=None)

    body = create(client, token, model_id=model_id)

    assert body["model_id"] == model_id


def test_creates_with_your_own_model(client: TestClient, token: str, sql: Run) -> None:
    model_id = a_model(sql, owner_email=RAFAEL["email"])

    body = create(client, token, model_id=model_id)

    assert body["model_id"] == model_id


def test_a_model_that_does_not_exist_is_not_found(client: TestClient, token: str) -> None:
    payload = {"model_id": str(uuid4())}

    response = client.post(CONVERSATIONS, headers=bearer(token), json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_someone_elses_model_is_not_found(client: TestClient, token: str, sql: Run) -> None:
    sign_up_and_in(client, ANA)
    anas_model = a_model(sql, owner_email=ANA["email"])

    response = client.post(CONVERSATIONS, headers=bearer(token), json={"model_id": anas_model})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"
    assert sql("SELECT c.id FROM conversations c") == []


def test_creating_requires_a_token(client: TestClient) -> None:
    assert client.post(CONVERSATIONS, json={}).status_code == 401


# ── list ─────────────────────────────────────────────────────────────────────


def test_lists_newest_activity_first(client: TestClient, token: str) -> None:
    first = create(client, token, title="first")
    create(client, token, title="second")
    client.patch(f"{CONVERSATIONS}/{first['id']}", headers=bearer(token), json={"title": "touched"})

    body = client.get(CONVERSATIONS, headers=bearer(token)).json()

    titles = [conversation["title"] for conversation in body["data"]]
    assert titles == ["touched", "second"]


def test_the_list_says_which_conversation_has_a_run_in_progress(
    client: TestClient, token: str, sql: Run
) -> None:
    busy = create(client, token, title="busy")
    create(client, token, title="idle")
    run_id = start_a_run(sql, busy["id"])

    body = client.get(CONVERSATIONS, headers=bearer(token)).json()

    active = {conversation["title"]: conversation["active_run_id"] for conversation in body["data"]}
    assert active == {"busy": run_id, "idle": None}


def test_a_finished_run_is_not_active(client: TestClient, token: str, sql: Run) -> None:
    created = create(client, token)
    run_id = start_a_run(sql, created["id"])
    sql(
        """
        UPDATE runs r
           SET status = 'succeeded',
               finished_at = now()
         WHERE r.external_id = %(run_id)s
        """,
        {"run_id": run_id},
    )

    body = client.get(CONVERSATIONS, headers=bearer(token)).json()

    assert body["data"][0]["active_run_id"] is None


def test_pages_come_wrapped_with_meta(client: TestClient, token: str) -> None:
    for n in range(5):
        create(client, token, title=f"conversation {n}")

    response = client.get(CONVERSATIONS, headers=bearer(token), params={"per_page": 2, "page": 3})

    body = response.json()
    assert set(body) == {"data", "meta"}
    assert len(body["data"]) == 1
    assert body["data"][0]["title"] == "conversation 0"
    assert body["meta"] == {"page": 3, "per_page": 2, "total": 5, "pages": 3}


def test_a_page_past_the_end_is_empty_not_an_error(client: TestClient, token: str) -> None:
    create(client, token)

    response = client.get(CONVERSATIONS, headers=bearer(token), params={"page": 9})

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["total"] == 1


def test_no_conversations_is_an_empty_page(client: TestClient, token: str) -> None:
    body = client.get(CONVERSATIONS, headers=bearer(token)).json()

    assert body == {"data": [], "meta": {"page": 1, "per_page": 50, "total": 0, "pages": 0}}


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"per_page": 0}, {"per_page": 201}, {"page": "two"}]
)
def test_paging_out_of_range_is_a_validation_error(
    client: TestClient, token: str, params: dict[str, Any]
) -> None:
    response = client.get(CONVERSATIONS, headers=bearer(token), params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_q_searches_titles_in_any_case(client: TestClient, token: str) -> None:
    create(client, token, title="Sales by region")
    create(client, token, title="Churn 2025")

    body = client.get(CONVERSATIONS, headers=bearer(token), params={"q": "SALES"}).json()

    assert [c["title"] for c in body["data"]] == ["Sales by region"]
    assert body["meta"]["total"] == 1


def test_q_takes_wildcards_literally(client: TestClient, token: str) -> None:
    create(client, token, title="100% of target")
    create(client, token, title="1000 rows")
    create(client, token, title="a_b")
    create(client, token, title="axb")

    percent = client.get(CONVERSATIONS, headers=bearer(token), params={"q": "100%"}).json()
    underscore = client.get(CONVERSATIONS, headers=bearer(token), params={"q": "a_b"}).json()

    assert [c["title"] for c in percent["data"]] == ["100% of target"]
    assert [c["title"] for c in underscore["data"]] == ["a_b"]


# ── open ─────────────────────────────────────────────────────────────────────


def test_opens_a_conversation_with_everything_its_screen_needs(
    client: TestClient, token: str
) -> None:
    created = create(client, token, title="Sales")

    response = client.get(f"{CONVERSATIONS}/{created['id']}", headers=bearer(token))

    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "title": "Sales",
        "model_id": None,
        "kernel": "stopped",
        "active_run_id": None,
        "files": [],
        "messages": [],
        "cells": [],
    }


def test_a_run_in_progress_is_the_active_run(client: TestClient, token: str, sql: Run) -> None:
    created = create(client, token)
    rows = sql(
        """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id, 'cell'
          FROM conversations c
         WHERE c.external_id = %(id)s
        RETURNING r.external_id::text
        """,
        {"id": created["id"]},
    )

    body = client.get(f"{CONVERSATIONS}/{created['id']}", headers=bearer(token)).json()

    assert body["active_run_id"] == rows[0][0]


def test_a_conversation_that_does_not_exist_is_not_found(client: TestClient, token: str) -> None:
    response = client.get(f"{CONVERSATIONS}/{uuid4()}", headers=bearer(token))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_an_id_that_is_not_a_uuid_is_a_validation_error(client: TestClient, token: str) -> None:
    response = client.get(f"{CONVERSATIONS}/42", headers=bearer(token))

    assert response.status_code == 422


# ── change ───────────────────────────────────────────────────────────────────


def test_renames(client: TestClient, token: str) -> None:
    created = create(client, token)

    response = client.patch(
        f"{CONVERSATIONS}/{created['id']}", headers=bearer(token), json={"title": "Churn"}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Churn"
    assert response.json()["updated_at"] > created["updated_at"]


def test_only_the_fields_sent_change(client: TestClient, token: str, sql: Run) -> None:
    model_id = a_model(sql, owner_email=None)
    created = create(client, token, title="Sales", model_id=model_id)
    url = f"{CONVERSATIONS}/{created['id']}"

    renamed = client.patch(url, headers=bearer(token), json={"title": "Sales 2025"}).json()

    assert renamed["model_id"] == model_id

    other_model = a_model(sql, owner_email=RAFAEL["email"])
    switched = client.patch(url, headers=bearer(token), json={"model_id": other_model}).json()

    assert switched["title"] == "Sales 2025"
    assert switched["model_id"] == other_model


def test_a_null_model_takes_the_model_away(client: TestClient, token: str, sql: Run) -> None:
    created = create(client, token, model_id=a_model(sql, owner_email=None))

    response = client.patch(
        f"{CONVERSATIONS}/{created['id']}", headers=bearer(token), json={"model_id": None}
    )

    assert response.json()["model_id"] is None


def test_a_null_title_is_a_validation_error(client: TestClient, token: str) -> None:
    created = create(client, token)

    response = client.patch(
        f"{CONVERSATIONS}/{created['id']}", headers=bearer(token), json={"title": None}
    )

    assert response.status_code == 422


def test_an_unknown_model_changes_nothing(client: TestClient, token: str) -> None:
    created = create(client, token, title="Sales")
    url = f"{CONVERSATIONS}/{created['id']}"

    response = client.patch(
        url, headers=bearer(token), json={"title": "Renamed", "model_id": str(uuid4())}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"
    assert client.get(url, headers=bearer(token)).json()["title"] == "Sales"


def test_an_unknown_conversation_wins_over_an_unknown_model(client: TestClient, token: str) -> None:
    response = client.patch(
        f"{CONVERSATIONS}/{uuid4()}", headers=bearer(token), json={"model_id": str(uuid4())}
    )

    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


# ── delete ───────────────────────────────────────────────────────────────────


def test_deletes_for_good(client: TestClient, token: str, sql: Run) -> None:
    created = create(client, token)
    url = f"{CONVERSATIONS}/{created['id']}"

    response = client.delete(url, headers=bearer(token))

    assert response.status_code == 204
    assert client.get(url, headers=bearer(token)).status_code == 404
    assert sql("SELECT c.id FROM conversations c") == []


def test_deleting_twice_is_not_found(client: TestClient, token: str) -> None:
    created = create(client, token)
    url = f"{CONVERSATIONS}/{created['id']}"
    client.delete(url, headers=bearer(token))

    assert client.delete(url, headers=bearer(token)).status_code == 404


# ── only your own (Phase 2: a second user's token gets 404) ──────────────────


def test_someone_elses_conversation_is_not_found_by_any_route(
    client: TestClient, token: str, sql: Run
) -> None:
    rafaels = create(client, token, title="Rafael's")
    url = f"{CONVERSATIONS}/{rafaels['id']}"
    ana = sign_up_and_in(client, ANA)

    opened = client.get(url, headers=bearer(ana))
    changed = client.patch(url, headers=bearer(ana), json={"title": "mine now"})
    deleted = client.delete(url, headers=bearer(ana))

    for response in (opened, changed, deleted):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    still = client.get(url, headers=bearer(token)).json()
    assert still["title"] == "Rafael's"


def test_the_list_holds_only_your_own(client: TestClient, token: str) -> None:
    create(client, token, title="Rafael's")
    ana = sign_up_and_in(client, ANA)
    create(client, ana, title="Ana's")

    body = client.get(CONVERSATIONS, headers=bearer(ana)).json()

    assert [c["title"] for c in body["data"]] == ["Ana's"]
    assert body["meta"]["total"] == 1
