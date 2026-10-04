"""Records real provider streams as test fixtures (decision 4's first defence).

Each adapter is run against a live API through a transport that saves the raw
response exactly as it came — status, content type, every byte of the stream —
next to the request that produced it. The tests replay them with no key and no
cost, so a change in how an adapter reads a stream is caught by a real one.

    docker compose run --rm \\
      -e RECORD_BASE_URL=https://openrouter.ai/api/v1 -e RECORD_API_KEY \\
      api python -m tests.record_provider_fixtures

RECORD_BASE_URL is an endpoint that speaks all three APIs with one key — a
router. Unset, each adapter goes to its own provider; since that takes one key per
provider, pick the adapter with RECORD_ADAPTERS (e.g. `anthropic` and an
Anthropic key). Models default to cheap ones and can be overridden:
RECORD_ANTHROPIC_MODEL, RECORD_RESPONSES_MODEL, RECORD_COMPATIBLE_MODEL.

Never saved: the key (the recorder refuses a fixture that contains it) and the
account's user id, which some routers put in error bodies.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx2
from app.domain.llm import Item, ProviderError, ToolResult, UserText
from app.domain.model_configs import Adapter, Dialect
from app.providers.endpoint import Endpoint
from app.providers.factory import model_for

FIXTURES = Path(__file__).parent / "fixtures" / "providers"

SYSTEM = "You are a terse assistant in a data analysis tool. Answer in as few words as possible."

TEXT_QUESTION = "Reply with exactly one word: hello"
CODE_QUESTION = "Use the run_python tool to compute 6 * 7. Do not answer before running it."
FENCE_QUESTION = (
    "Write Python that prints 6 * 7, in a single ```python fenced block, and nothing else."
)

USER_ID = re.compile(r'"user_id"\s*:\s*"[^"]*"')


class RecordingTransport(httpx2.AsyncBaseTransport):
    """Passes requests through and keeps the last response's raw bytes."""

    def __init__(self) -> None:
        self.inner = httpx2.AsyncHTTPTransport()
        self.last: dict[str, Any] = {}

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        await response.aclose()

        self.last = {
            "request": json.loads(request.content),
            "status": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "body": body.decode(),
        }

        headers = {"content-type": response.headers.get("content-type", "")}
        return httpx2.Response(response.status_code, headers=headers, content=body)


async def ignore(text: str) -> None:
    pass


async def record_case(
    transport: RecordingTransport,
    endpoint: Endpoint,
    case: str,
    history: list[Item],
    key: str,
    through: str,
) -> Any:
    async with httpx2.AsyncClient(transport=transport) as http:
        model = model_for(endpoint, http)

        try:
            reply = await model.complete(SYSTEM, history, ignore)
        except ProviderError as exc:
            reply = exc

    fixture = {
        "note": (
            f"Recorded from a live API through {through}. Replayed by "
            "tests/test_provider_adapters.py; regenerate with tests/record_provider_fixtures.py."
        ),
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "adapter": endpoint.adapter,
        "model": endpoint.model,
        "dialect": endpoint.dialect,
        "case": case,
        "request": transport.last["request"],
        "status": transport.last["status"],
        "content_type": transport.last["content_type"],
        "body": USER_ID.sub('"user_id": "redacted"', transport.last["body"]),
    }

    encoded = json.dumps(fixture, indent=2, ensure_ascii=False)
    if key in encoded:
        raise SystemExit(f"refusing to save {case}: the key is in it")

    folder = FIXTURES / endpoint.adapter
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{case}.json").write_text(encoded + "\n")
    print(f"recorded {endpoint.adapter}/{case}: {transport.last['status']}")

    return reply


async def record_adapter(
    adapter: Adapter,
    model: str,
    base_url: str | None,
    key: str,
    through: str,
) -> None:
    def endpoint(dialect: Dialect, name: str = model) -> Endpoint:
        return Endpoint(
            adapter=adapter,
            model=name,
            dialect=dialect,
            base_url=base_url,
            api_key=key,
            max_tokens=2_000,
        )

    transport = RecordingTransport()
    tools = endpoint("tools")

    await record_case(transport, tools, "text", [UserText(TEXT_QUESTION)], key, through)

    question = UserText(CODE_QUESTION)
    called = await record_case(transport, tools, "tool_call", [question], key, through)
    if isinstance(called, ProviderError):
        raise SystemExit(f"{adapter}: the tool call failed to parse: {called}")

    if called.turn.call_id is None:
        raise SystemExit(f"{adapter}: the model did not call the tool; cannot record a follow-up")

    # The turn goes back as the adapter replays it — thinking and reasoning
    # included — which is the part most worth having a real recording of.
    result = ToolResult(call_id=called.turn.call_id, content="42\n")
    followup: list[Item] = [question, called.turn, result]
    await record_case(transport, tools, "tool_result", followup, key, through)

    await record_case(
        transport, endpoint("text"), "text_dialect", [UserText(FENCE_QUESTION)], key, through
    )

    missing = endpoint("tools", name="not-a-notebook/does-not-exist")
    await record_case(transport, missing, "error", [UserText(TEXT_QUESTION)], key, through)


async def main() -> None:
    key = os.environ["RECORD_API_KEY"]
    base_url = os.environ.get("RECORD_BASE_URL")

    through = "each provider's own API"
    if base_url is not None:
        through = urlsplit(base_url).netloc

    models: dict[Adapter, str] = {
        "anthropic": os.environ.get("RECORD_ANTHROPIC_MODEL", "anthropic/claude-sonnet-5.5"),
        "openai_responses": os.environ.get("RECORD_RESPONSES_MODEL", "openai/gpt-5-nano"),
        "openai_compatible": os.environ.get("RECORD_COMPATIBLE_MODEL", "qwen/qwen3.7-flash"),
    }

    chosen = os.environ.get("RECORD_ADAPTERS", ",".join(models)).split(",")

    for adapter, model in models.items():
        if adapter in chosen:
            await record_adapter(adapter, model, base_url, key, through)


if __name__ == "__main__":
    asyncio.run(main())
