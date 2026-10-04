"""The three adapters, against streams recorded from real models.

Each fixture in tests/fixtures/providers is a live response, byte for byte, with
the request that produced it. Replaying it checks both directions: the adapter
still reads the stream as it really arrives, and still builds the request that
was accepted. The cases after the recordings cover what a recording cannot:
retries, failures halfway, and a conversation that changes model.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from app.domain.llm import AssistantTurn, Item, ProviderError, Reply, ToolResult, UserText
from app.domain.model_configs import Adapter
from app.providers.dialect import NOT_RUN, extract_code
from app.providers.endpoint import Endpoint
from app.providers.factory import model_for
from tests.record_provider_fixtures import (
    CODE_QUESTION,
    FENCE_QUESTION,
    SYSTEM,
    TEXT_QUESTION,
)

FIXTURES = Path(__file__).parent / "fixtures" / "providers"
ADAPTERS: list[Adapter] = ["anthropic", "openai_responses", "openai_compatible"]
BASE_URL = "https://router.example/v1"

Handler = Callable[[httpx2.Request], httpx2.Response]


def fixture(adapter: str, case: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / adapter / f"{case}.json").read_text())
    return loaded


def endpoint_of(recorded: dict[str, Any]) -> Endpoint:
    return Endpoint(
        adapter=recorded["adapter"],
        model=recorded["model"],
        dialect=recorded["dialect"],
        base_url=BASE_URL,
        api_key="test-key",
        max_tokens=2_000,
    )


def serving(recorded: dict[str, Any], sent: list[dict[str, Any]]) -> Handler:
    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        headers = {"content-type": recorded["content_type"]}

        return httpx2.Response(recorded["status"], headers=headers, content=recorded["body"])

    return handle


async def complete(endpoint: Endpoint, history: list[Item], handler: Handler) -> tuple[Reply, str]:
    streamed: list[str] = []

    async def keep(text: str) -> None:
        streamed.append(text)

    transport = httpx2.MockTransport(handler)
    async with httpx2.AsyncClient(transport=transport) as http:
        reply = await model_for(endpoint, http).complete(SYSTEM, history, keep)

    return reply, "".join(streamed)


async def replay(adapter: str, case: str, history: list[Item]) -> tuple[Reply, dict[str, Any]]:
    """The recorded reply, and checks the adapter sent the recorded request."""
    recorded = fixture(adapter, case)
    sent: list[dict[str, Any]] = []

    reply, streamed = await complete(endpoint_of(recorded), history, serving(recorded, sent))

    assert sent == [recorded["request"]], "the adapter no longer builds the recorded request"
    assert streamed == reply.turn.text

    return reply, recorded


# ── replaying real streams ───────────────────────────────────────────────────


@pytest.mark.parametrize("adapter", ADAPTERS)
async def test_a_plain_answer(adapter: str) -> None:
    reply, _ = await replay(adapter, "text", [UserText(TEXT_QUESTION)])

    assert reply.stop == "answer"
    assert reply.turn.code is None
    assert "hello" in reply.turn.text.lower()
    assert reply.usage.input_tokens > 0
    assert reply.usage.output_tokens > 0


@pytest.mark.parametrize("adapter", ADAPTERS)
async def test_a_tool_call_is_code_to_run(adapter: str) -> None:
    reply, _ = await replay(adapter, "tool_call", [UserText(CODE_QUESTION)])

    assert reply.stop == "code"
    assert reply.turn.code is not None
    assert "6" in reply.turn.code and "7" in reply.turn.code
    assert reply.turn.call_id


@pytest.mark.parametrize("adapter", ADAPTERS)
async def test_the_turn_goes_back_as_it_came_and_the_result_is_read(adapter: str) -> None:
    """The follow-up the provider accepted when recorded: the model's own turn,
    thinking or reasoning included, and the tool's result."""
    question = UserText(CODE_QUESTION)
    called, _ = await replay(adapter, "tool_call", [question])
    result = ToolResult(call_id=called.turn.call_id, content="42\n")

    reply, _ = await replay(adapter, "tool_result", [question, called.turn, result])

    assert reply.stop == "answer"
    assert "42" in reply.turn.text


@pytest.mark.parametrize("adapter", ADAPTERS)
async def test_the_text_dialect_finds_the_fenced_code(adapter: str) -> None:
    reply, recorded = await replay(adapter, "text_dialect", [UserText(FENCE_QUESTION)])

    assert reply.stop == "code"
    assert reply.turn.code is not None
    assert "print" in reply.turn.code
    assert "tools" not in recorded["request"]


@pytest.mark.parametrize("adapter", ADAPTERS)
async def test_a_refused_request_is_a_provider_error(adapter: str) -> None:
    recorded = fixture(adapter, "error")
    sent: list[dict[str, Any]] = []

    with pytest.raises(ProviderError) as raised:
        await complete(endpoint_of(recorded), [UserText(TEXT_QUESTION)], serving(recorded, sent))

    assert raised.value.kind == "bad_request"
    assert raised.value.status == 400
    assert "does-not-exist" in str(raised.value)
    assert len(sent) == 1, "a 400 is not retried"


@pytest.mark.parametrize("adapter", ADAPTERS)
def test_no_fixture_holds_a_key_or_an_account(adapter: str) -> None:
    for path in (FIXTURES / adapter).glob("*.json"):
        text = path.read_text()

        assert "sk-" not in text, path
        assert '"user_id": "user_' not in text, path


# ── what a recording does not show ───────────────────────────────────────────


def stream_of(adapter: str) -> str:
    body: str = fixture(adapter, "text")["body"]
    return body


def sse(status: int, body: str) -> httpx2.Response:
    return httpx2.Response(status, headers={"content-type": "text/event-stream"}, content=body)


def endpoint(adapter: Adapter, dialect: str = "tools") -> Endpoint:
    return Endpoint(
        adapter=adapter,
        model="some-model",
        dialect=dialect,  # type: ignore[arg-type]
        base_url=BASE_URL,
        api_key="test-key",
    )


@pytest.mark.parametrize("adapter", ADAPTERS)
async def test_an_overloaded_provider_is_retried(
    adapter: Adapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.providers.streaming.backoff", lambda attempt, retry_after: 0)
    answers = [sse(529, '{"error": {"message": "busy"}}'), sse(200, stream_of(adapter))]

    def handle(request: httpx2.Request) -> httpx2.Response:
        return answers.pop(0)

    reply, _ = await complete(endpoint(adapter), [UserText("hi")], handle)

    assert reply.stop == "answer"
    assert answers == []


async def test_retries_give_up_and_say_why(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.streaming.backoff", lambda attempt, retry_after: 0)
    calls = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return sse(529, '{"type": "error", "error": {"message": "Overloaded"}}')

    with pytest.raises(ProviderError) as raised:
        await complete(endpoint("anthropic"), [UserText("hi")], handle)

    assert raised.value.kind == "overloaded"
    assert str(raised.value) == "Overloaded"
    assert calls == 3


async def test_a_bad_key_is_not_retried() -> None:
    calls = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return sse(401, '{"error": {"message": "invalid x-api-key"}}')

    with pytest.raises(ProviderError) as raised:
        await complete(endpoint("anthropic"), [UserText("hi")], handle)

    assert raised.value.kind == "auth"
    assert calls == 1


async def test_an_error_in_the_middle_of_a_stream_is_a_provider_error() -> None:
    body = (
        'data: {"choices": [{"delta": {"content": "Hel"}}]}\n\n'
        'data: {"error": {"message": "upstream provider died"}}\n\n'
    )

    with pytest.raises(ProviderError, match="upstream provider died"):
        await complete(endpoint("openai_compatible"), [UserText("hi")], lambda r: sse(200, body))


async def test_the_key_goes_in_the_header_each_api_expects() -> None:
    seen: dict[str, str | None] = {}

    def recording(name: str, adapter: str) -> Handler:
        def handle(request: httpx2.Request) -> httpx2.Response:
            seen[name] = request.headers.get("x-api-key") or request.headers.get("authorization")
            return sse(200, stream_of(adapter))

        return handle

    await complete(endpoint("anthropic"), [UserText("hi")], recording("anthropic", "anthropic"))
    await complete(
        endpoint("openai_compatible"),
        [UserText("hi")],
        recording("compatible", "openai_compatible"),
    )

    assert seen == {"anthropic": "test-key", "compatible": "Bearer test-key"}


# ── a conversation that changes model ────────────────────────────────────────


def claude_turn() -> AssistantTurn:
    thinking = {"type": "thinking", "thinking": "", "signature": "sig-only-claude-reads"}
    call = {"type": "tool_use", "id": "toolu_1", "name": "run_python", "input": {"code": "1 + 1"}}

    return AssistantTurn(
        text="",
        code="1 + 1",
        call_id="toolu_1",
        source="anthropic:claude-sonnet-5-5",
        raw=[thinking, call],
    )


async def request_for(adapter: Adapter, dialect: str, history: list[Item]) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return sse(200, stream_of(adapter))

    await complete(endpoint(adapter, dialect), history, handle)

    return sent[0]


async def test_another_models_turn_is_shown_without_its_thinking() -> None:
    history: list[Item] = [UserText("add"), claude_turn(), ToolResult("toolu_1", "2")]

    body = await request_for("openai_compatible", "tools", history)

    assistant = body["messages"][2]
    assert "sig-only-claude-reads" not in json.dumps(body)
    assert assistant["tool_calls"][0]["id"] == "toolu_1"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"code": "1 + 1"}
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "toolu_1", "content": "2"}


async def test_a_tool_call_is_shown_to_a_text_dialect_model_as_a_fence() -> None:
    history: list[Item] = [UserText("add"), claude_turn(), ToolResult("toolu_1", "2")]

    body = await request_for("anthropic", "text", history)

    assistant, result = body["messages"][1], body["messages"][2]
    assert assistant["content"] == [{"type": "text", "text": "```python\n1 + 1\n```"}]
    assert result["content"][0]["text"].startswith("Output of your code:")
    assert "tools" not in body


async def test_the_same_models_turn_goes_back_raw() -> None:
    history: list[Item] = [UserText("add"), claude_turn(), ToolResult("toolu_1", "2")]
    same = Endpoint("anthropic", "claude-sonnet-5-5", "tools", BASE_URL, "test-key")
    sent: list[dict[str, Any]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return sse(200, stream_of("anthropic"))

    await complete(same, history, handle)

    assert sent[0]["messages"][1]["content"] == claude_turn().raw


async def test_calls_beyond_the_first_are_answered_as_not_run() -> None:
    turn = AssistantTurn(
        text="",
        code="1",
        call_id="toolu_1",
        source="other:model",
        raw=None,
        extra_call_ids=("toolu_2",),
    )
    history: list[Item] = [UserText("go"), turn, ToolResult("toolu_1", "1")]

    body = await request_for("anthropic", "tools", history)

    results = body["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_1", "toolu_2"]
    assert results[1]["content"] == NOT_RUN


# ── finding code in text ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Here:\n```python\nprint(1)\n```\nDone.", "print(1)"),
        ("```py\nx = 1\n```", "x = 1"),
        ("```\nx = 2\n```", "x = 2"),
        ("```json\n{}\n```\n```python\nx = 3\n```", "x = 3"),
        ("The answer is 42.", None),
        ("```python\n\n```", None),
    ],
)
def test_code_is_found_in_text(text: str, code: str | None) -> None:
    assert extract_code(text) == code
