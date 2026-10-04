"""OpenAI models through the Responses API — the ones that refuse tools with
reasoning on chat/completions (the POC's measured 400, decision 4).

`store: false`: the conversation is not kept at the provider. The reasoning a
model did comes back encrypted (`include: reasoning.encrypted_content`) inside
its output items, and the turn's `raw` is those items, sent back unchanged on the
next request — the model picks its reasoning up without the provider holding it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx2

from app.domain.llm import (
    AssistantTurn,
    Item,
    OnDelta,
    ProviderError,
    Reply,
    StopReason,
    ToolResult,
    Usage,
    UserText,
)
from app.providers.dialect import (
    NOT_RUN,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    TOOL_PARAMETERS,
    extract_code,
    result_as_text,
    turn_as_text,
)
from app.providers.endpoint import Endpoint
from app.providers.streaming import events, open_stream

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class ResponsesModel:
    def __init__(self, endpoint: Endpoint, http: httpx2.AsyncClient) -> None:
        self.endpoint = endpoint
        self.http = http

    async def complete(self, system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        base_url = self.endpoint.base_url or DEFAULT_BASE_URL
        url = f"{base_url.rstrip('/')}/responses"

        headers = {"content-type": "application/json"}
        if self.endpoint.api_key is not None:
            headers["authorization"] = f"Bearer {self.endpoint.api_key}"

        body = self.request_body(system, history)

        async with open_stream(self.http, url, headers, body) as response:
            streamed = StreamedResponse()

            async for event in events(response):
                await streamed.take(event.json(), on_delta)

        return streamed.reply(self.endpoint)

    def request_body(self, system: str, history: Sequence[Item]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.endpoint.model,
            "instructions": system,
            "input": self.input_items(history),
            "max_output_tokens": self.endpoint.max_tokens,
            "stream": True,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }

        if self.endpoint.dialect == "tools":
            tool = {
                "type": "function",
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "parameters": TOOL_PARAMETERS,
            }
            body["tools"] = [tool]
            body["tool_choice"] = "auto"
            body["parallel_tool_calls"] = False

        return body

    def input_items(self, history: Sequence[Item]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for item in history:
            if isinstance(item, UserText):
                items.append(message("user", "input_text", item.text))
            elif isinstance(item, AssistantTurn):
                items.extend(self.assistant_items(item))
            else:
                items.extend(self.result_items(item, history))

        return items

    def assistant_items(self, turn: AssistantTurn) -> list[dict[str, Any]]:
        if turn.source == self.endpoint.source:
            raw: list[dict[str, Any]] = turn.raw
            return raw

        if self.endpoint.dialect == "text" or turn.call_id is None:
            return [message("assistant", "output_text", turn_as_text(turn))]

        items = []
        if turn.text:
            items.append(message("assistant", "output_text", turn.text))

        call = {
            "type": "function_call",
            "call_id": turn.call_id,
            "name": TOOL_NAME,
            "arguments": json.dumps({"code": turn.code}),
        }
        items.append(call)

        return items

    def result_items(self, result: ToolResult, history: Sequence[Item]) -> list[dict[str, Any]]:
        if self.endpoint.dialect == "text" or result.call_id is None:
            return [message("user", "input_text", result_as_text(result))]

        items = [
            {"type": "function_call_output", "call_id": result.call_id, "output": result.content}
        ]

        for item in history:
            if isinstance(item, AssistantTurn) and item.call_id == result.call_id:
                for extra in item.extra_call_ids:
                    items.append(
                        {"type": "function_call_output", "call_id": extra, "output": NOT_RUN}
                    )

        return items


def message(role: str, part: str, text: str) -> dict[str, Any]:
    return {"role": role, "content": [{"type": part, "text": text}]}


@dataclass
class StreamedResponse:
    """A response assembled from its stream: the output items as each completes."""

    items: list[dict[str, Any]] = field(default_factory=list)
    status: str | None = None
    incomplete_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    refused: bool = False

    async def take(self, event: dict[str, Any], on_delta: OnDelta) -> None:
        kind = event.get("type")

        if kind == "response.output_text.delta":
            await on_delta(event["delta"])

        elif kind == "response.refusal.delta":
            self.refused = True

        elif kind == "response.output_item.done":
            self.items.append(event["item"])

        elif kind in ("response.completed", "response.incomplete"):
            response = event["response"]
            self.status = response.get("status")
            self.usage = response.get("usage") or {}
            details = response.get("incomplete_details") or {}
            self.incomplete_reason = details.get("reason")

        elif kind in ("response.failed", "error"):
            raise ProviderError("unavailable", failure_message(event))

    def reply(self, endpoint: Endpoint) -> Reply:
        text_parts = []
        calls = []

        for item in self.items:
            if item.get("type") == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "output_text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "refusal":
                        self.refused = True
            elif item.get("type") == "function_call":
                calls.append(item)

        text = "".join(text_parts)
        code, call_id, extra = code_of(endpoint, text, calls)

        turn = AssistantTurn(
            text=text,
            code=code,
            call_id=call_id,
            source=endpoint.source,
            raw=self.items,
            extra_call_ids=extra,
        )

        details = self.usage.get("output_tokens_details") or {}
        usage = Usage(
            input_tokens=self.usage.get("input_tokens", 0),
            output_tokens=self.usage.get("output_tokens", 0),
            reasoning_tokens=details.get("reasoning_tokens", 0) or 0,
        )

        return Reply(turn=turn, usage=usage, stop=self.stop(code))

    def stop(self, code: str | None) -> StopReason:
        if self.refused:
            return "refusal"

        if self.incomplete_reason == "max_output_tokens":
            return "max_tokens"

        if code is not None:
            return "code"

        return "answer"


def failure_message(event: dict[str, Any]) -> str:
    response = event.get("response") or {}
    error = response.get("error") or event.get("error") or {}

    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return str(error["message"])

    message = event.get("message")
    if isinstance(message, str):
        return message

    return "the response failed"


def code_of(
    endpoint: Endpoint,
    text: str,
    calls: list[dict[str, Any]],
) -> tuple[str | None, str | None, tuple[str, ...]]:
    if endpoint.dialect == "text":
        return extract_code(text), None, ()

    if not calls:
        return None, None, ()

    first = calls[0]
    try:
        arguments = json.loads(first.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        raise ProviderError("protocol", "a function call whose arguments are not JSON") from exc

    code = arguments.get("code")
    if not isinstance(code, str):
        raise ProviderError("protocol", "a run_python call without a code string")

    extra = tuple(call["call_id"] for call in calls[1:])

    return code, first["call_id"], extra
