"""/models: the instance's models from .env, and the ones users configure.

The key never comes back — only a hint — and the instance's models are the
operator's: listed for everyone, changed by no one through the API.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from app.config import Settings, get_settings
from app.main import app
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tests.conftest import Run
from tests.support.auth import ANA, RAFAEL, bearer, sign_up_and_in

MODELS = "/api/v1/models"
CONVERSATIONS = "/api/v1/conversations"

QWEN = {
    "name": "Local Qwen",
    "adapter": "openai_compatible",
    "base_url": "http://host.docker.internal:11434/v1",
    "model": "qwen3:14b",
    "dialect": "text",
}

CLAUDE_KEY = "sk-ant-api03-secretsecret-x9Qa"
OWN_KEY = "sk-own-secretsecretsecret-a3f9"


@pytest.fixture
def token(client: TestClient) -> str:
    return sign_up_and_in(client, RAFAEL)


def add(client: TestClient, token: str, **overrides: Any) -> dict[str, Any]:
    body = dict(QWEN)
    for field, value in overrides.items():
        body[field] = value

    response = client.post(MODELS, headers=bearer(token), json=body)
    assert response.status_code == 201, response.text

    created: dict[str, Any] = response.json()
    return created


@pytest.fixture
def restart(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Starts the API again with these environment variables, as an operator
    editing .env and restarting would."""

    def start(**variables: str) -> TestClient:
        for name, value in variables.items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()

        return TestClient(app, base_url="https://testserver")

    yield start
    get_settings.cache_clear()


# ── the user's own ───────────────────────────────────────────────────────────


def test_adds_a_model_and_never_shows_its_key(client: TestClient, token: str) -> None:
    body = add(client, token, api_key=OWN_KEY)

    assert set(body) == {
        "id",
        "name",
        "source",
        "adapter",
        "base_url",
        "model",
        "dialect",
        "key_hint",
    }
    assert body["source"] == "user"
    assert body["key_hint"] == "…a3f9"
    assert OWN_KEY not in str(body)


def test_the_key_is_stored_encrypted(client: TestClient, token: str, sql: Run) -> None:
    add(client, token, api_key=OWN_KEY)

    stored = sql("SELECT m.api_key_encrypted FROM models m")[0][0]

    assert stored.startswith("v1.")
    assert OWN_KEY not in stored


def test_a_model_without_a_key_has_no_hint(client: TestClient, token: str) -> None:
    assert add(client, token)["key_hint"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"base_url": None},
        {"base_url": "ftp://somewhere/v1"},
        {"base_url": "not a url"},
        {"adapter": "llama_cpp"},
        {"dialect": "json"},
        {"name": ""},
    ],
)
def test_a_malformed_model_is_a_validation_error(
    client: TestClient, token: str, change: dict[str, Any]
) -> None:
    body = dict(QWEN)
    for field, value in change.items():
        body[field] = value

    response = client.post(MODELS, headers=bearer(token), json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_rejected_key_is_not_echoed_back(client: TestClient, token: str) -> None:
    body = dict(QWEN)
    body["api_key"] = OWN_KEY
    body["dialect"] = "json"

    response = client.post(MODELS, headers=bearer(token), json=body)

    assert response.status_code == 422
    assert OWN_KEY not in response.text


def test_only_the_fields_sent_change(client: TestClient, token: str) -> None:
    created = add(client, token, api_key=OWN_KEY)

    response = client.patch(
        f"{MODELS}/{created['id']}", headers=bearer(token), json={"name": "Qwen, local"}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Qwen, local"
    assert body["model"] == "qwen3:14b"
    assert body["key_hint"] == "…a3f9"


def test_a_null_key_removes_the_key(client: TestClient, token: str, sql: Run) -> None:
    created = add(client, token, api_key=OWN_KEY)

    body = client.patch(
        f"{MODELS}/{created['id']}", headers=bearer(token), json={"api_key": None}
    ).json()

    assert body["key_hint"] is None
    assert sql("SELECT m.api_key_encrypted FROM models m") == [(None,)]


def test_a_change_that_leaves_a_compatible_model_without_a_url_is_refused(
    client: TestClient, token: str
) -> None:
    created = add(client, token, adapter="anthropic", base_url=None, model="claude-sonnet-5-5")

    response = client.patch(
        f"{MODELS}/{created['id']}",
        headers=bearer(token),
        json={"adapter": "openai_compatible"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_deleting_leaves_its_conversations_without_a_model(client: TestClient, token: str) -> None:
    model = add(client, token)
    conversation = client.post(
        CONVERSATIONS, headers=bearer(token), json={"model_id": model["id"]}
    ).json()

    response = client.delete(f"{MODELS}/{model['id']}", headers=bearer(token))

    assert response.status_code == 204
    after = client.get(f"{CONVERSATIONS}/{conversation['id']}", headers=bearer(token)).json()
    assert after["model_id"] is None


def test_someone_elses_model_is_not_found(client: TestClient, token: str) -> None:
    rafaels = add(client, token)
    ana = sign_up_and_in(client, ANA)
    url = f"{MODELS}/{rafaels['id']}"

    listed = client.get(MODELS, headers=bearer(ana)).json()["data"]
    changed = client.patch(url, headers=bearer(ana), json={"name": "mine"})
    deleted = client.delete(url, headers=bearer(ana))

    assert listed == []
    for response in (changed, deleted):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"


def test_an_unknown_model_is_not_found(client: TestClient, token: str) -> None:
    response = client.delete(f"{MODELS}/{uuid4()}", headers=bearer(token))

    assert response.status_code == 404


# ── the instance's, from .env ────────────────────────────────────────────────


def test_environment_models_are_listed_first_for_everyone(
    client: TestClient, token: str, restart: Any
) -> None:
    add(client, token, name="A local one")

    with restart(ANTHROPIC_API_KEY=CLAUDE_KEY) as again:
        listed = again.get(MODELS, headers=bearer(token)).json()["data"]
        ana = sign_up_and_in(again, ANA)
        for_ana = again.get(MODELS, headers=bearer(ana)).json()["data"]

    assert [(m["name"], m["source"]) for m in listed] == [
        ("Claude", "environment"),
        ("A local one", "user"),
    ]
    assert listed[0]["key_hint"] == "…x9Qa"
    assert listed[0]["model"] == "claude-sonnet-5-5"
    assert [m["name"] for m in for_ana] == ["Claude"]


def test_an_environment_models_key_never_reaches_the_database(
    client: TestClient, restart: Any, sql: Run
) -> None:
    with restart(ANTHROPIC_API_KEY=CLAUDE_KEY):
        pass

    assert sql("SELECT m.env_name, m.api_key_encrypted FROM models m") == [("ANTHROPIC", None)]


def test_an_environment_model_keeps_its_id_across_restarts(
    client: TestClient, token: str, restart: Any
) -> None:
    with restart(ANTHROPIC_API_KEY=CLAUDE_KEY) as first:
        before = first.get(MODELS, headers=bearer(token)).json()["data"][0]

    with restart(ANTHROPIC_MODEL="claude-opus-5-5") as second:
        after = second.get(MODELS, headers=bearer(token)).json()["data"][0]

    assert after["id"] == before["id"]
    assert after["model"] == "claude-opus-5-5"


def test_an_environment_model_taken_out_of_env_is_gone_and_its_conversations_lose_it(
    client: TestClient, token: str, restart: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with restart(ANTHROPIC_API_KEY=CLAUDE_KEY) as first:
        claude = first.get(MODELS, headers=bearer(token)).json()["data"][0]
        conversation = first.post(
            CONVERSATIONS, headers=bearer(token), json={"model_id": claude["id"]}
        ).json()

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with restart() as second:
        listed = second.get(MODELS, headers=bearer(token)).json()["data"]
        opened = second.get(f"{CONVERSATIONS}/{conversation['id']}", headers=bearer(token)).json()

    assert listed == []
    assert opened["model_id"] is None


def test_an_environment_model_cannot_be_changed_or_deleted(
    client: TestClient, token: str, restart: Any
) -> None:
    with restart(ANTHROPIC_API_KEY=CLAUDE_KEY) as again:
        claude = again.get(MODELS, headers=bearer(token)).json()["data"][0]
        url = f"{MODELS}/{claude['id']}"

        changed = again.patch(url, headers=bearer(token), json={"name": "Mine now"})
        deleted = again.delete(url, headers=bearer(token))

    for response in (changed, deleted):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "MODEL_MANAGED_BY_ENVIRONMENT"


def test_all_three_environment_models_at_once(client: TestClient, token: str, restart: Any) -> None:
    variables = {
        "ANTHROPIC_API_KEY": CLAUDE_KEY,
        "OPENAI_API_KEY": "sk-openai-secretsecret-b7c1",
        "OPENAI_MODEL": "gpt-5.5",
        "OPENAI_COMPATIBLE_BASE_URL": "http://host.docker.internal:11434/v1",
        "OPENAI_COMPATIBLE_MODEL": "qwen3:14b",
    }

    with restart(**variables) as again:
        listed = again.get(MODELS, headers=bearer(token)).json()["data"]

    summary = [(m["name"], m["adapter"], m["dialect"], m["key_hint"]) for m in listed]
    assert summary == [
        ("Claude", "anthropic", "tools", "…x9Qa"),
        ("OpenAI", "openai_responses", "tools", "…b7c1"),
        ("qwen3:14b", "openai_compatible", "text", None),
    ]


# ── half a configuration stops the service ───────────────────────────────────

BASE = {
    "database_url": "postgresql://unused",
    "jwt_secret": "x" * 32,
    "secrets_key": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
}


@pytest.mark.parametrize(
    ("extra", "complaint"),
    [
        ({"openai_api_key": "sk-x"}, "OPENAI_MODEL"),
        ({"openai_compatible_base_url": "http://ollama:11434/v1"}, "OPENAI_COMPATIBLE_MODEL"),
        ({"openai_compatible_model": "qwen3"}, "OPENAI_COMPATIBLE_BASE_URL"),
        ({"secrets_key": "c2hvcnQ="}, "32 bytes"),
    ],
)
def test_half_a_configuration_stops_the_service(extra: dict[str, str], complaint: str) -> None:
    values = dict(BASE)
    for field, value in extra.items():
        values[field] = value

    with pytest.raises(ValidationError, match=complaint):
        Settings(**values)  # type: ignore[arg-type]


# ── testing a model ──────────────────────────────────────────────────────────


def recorded(adapter: str, case: str) -> httpx2.Response:
    path = Path(__file__).parent / "fixtures" / "providers" / adapter / f"{case}.json"
    fixture = json.loads(path.read_text())
    headers = {"content-type": fixture["content_type"]}

    return httpx2.Response(fixture["status"], headers=headers, content=fixture["body"])


@pytest.fixture
def provider(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    """The app's outbound client, answering with recorded streams. Append the
    responses the next calls should get; requests seen are kept beside them."""
    answers: list[httpx2.Response] = []
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return answers.pop(0)

    transport = httpx2.MockTransport(handle)
    monkeypatch.setattr(app.state, "http", httpx2.AsyncClient(transport=transport))

    yield [answers, seen]


def claude_via_router(client: TestClient, token: str) -> dict[str, Any]:
    return add(
        client,
        token,
        name="Claude",
        adapter="anthropic",
        base_url="https://router.example/v1",
        model="anthropic/claude-sonnet-5.5",
        dialect="tools",
        api_key=OWN_KEY,
    )


def test_a_model_that_calls_the_tool_passes(
    client: TestClient, token: str, provider: list[Any]
) -> None:
    answers, seen = provider
    answers.append(recorded("anthropic", "tool_call"))
    model = claude_via_router(client, token)

    response = client.post(f"{MODELS}/{model['id']}/test", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert isinstance(body["latency_ms"], int)
    # The stored key, decrypted, went to the provider — and only there.
    assert seen[0].headers["x-api-key"] == OWN_KEY
    assert str(seen[0].url) == "https://router.example/v1/messages"


def test_a_model_that_answers_in_words_fails_and_says_so(
    client: TestClient, token: str, provider: list[Any]
) -> None:
    answers, _ = provider
    answers.append(recorded("anthropic", "text"))
    model = claude_via_router(client, token)

    body = client.post(f"{MODELS}/{model['id']}/test", headers=bearer(token)).json()

    assert body["ok"] is False
    assert body["error"] == "the model answered without calling the tool"


def test_a_provider_error_is_a_failed_test_not_a_failed_request(
    client: TestClient, token: str, provider: list[Any]
) -> None:
    answers, _ = provider
    answers.append(recorded("anthropic", "error"))
    model = claude_via_router(client, token)

    response = client.post(f"{MODELS}/{model['id']}/test", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "not a valid model" in response.json()["error"]


def test_a_text_dialect_model_is_tested_for_a_fence(
    client: TestClient, token: str, provider: list[Any]
) -> None:
    answers, seen = provider
    answers.append(recorded("openai_compatible", "text_dialect"))
    model = add(client, token, model="qwen/qwen3.7-flash", base_url="https://router.example/v1")

    body = client.post(f"{MODELS}/{model['id']}/test", headers=bearer(token)).json()

    assert body["ok"] is True
    assert "tools" not in json.loads(seen[0].content)


def test_testing_someone_elses_model_is_not_found(client: TestClient, token: str) -> None:
    rafaels = add(client, token)
    ana = sign_up_and_in(client, ANA)

    response = client.post(f"{MODELS}/{rafaels['id']}/test", headers=bearer(ana))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MODEL_NOT_FOUND"
