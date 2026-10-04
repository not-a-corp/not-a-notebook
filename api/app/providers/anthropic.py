"""Claude, through the Messages API — streamed, with httpx2 and nothing else.

What the current models require, and this file does:

- **No thinking parameter.** Sonnet 5.5 and Opus 5.5 think adaptively by default
  and refuse `{"type": "disabled"}`; older models simply do not think.
- **Thinking blocks go back unchanged**, signature and all, in the next request
  of the same conversation — the turn's `raw` is the response's content blocks
  exactly as they arrived. To any other model they are not sent: they are bound
  to the model that wrote them.
- **`tool_choice` is `auto`**: forcing a tool is a 400 on the current models. The
  prompt asks for the tool instead. Parallel calls are switched off, since one
  kernel runs one cell at a time.
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

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"


class AnthropicModel:
    def __init__(self, endpoint: Endpoint, http: httpx2.AsyncClient) -> None:
        self.endpoint = endpoint
        self.http = http

    async def complete(self, system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        base_url = self.endpoint.base_url or DEFAULT_BASE_URL
        url = f"{base_url.rstrip('/')}/messages"

        headers = {
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        if self.endpoint.api_key is not None:
            headers["x-api-key"] = self.endpoint.api_key

        body = self.request_body(system, history)

        async with open_stream(self.http, url, headers, body) as response:
            message = StreamedMessage()

            async for event in events(response):
                parsed = event.json()
                await message.take(parsed, on_delta)

                if parsed.get("type") == "message_stop":
                    break

        return message.reply(self.endpoint)

    def request_body(self, system: str, history: Sequence[Item]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.endpoint.model,
            "max_tokens": self.endpoint.max_tokens,
            "system": system,
            "messages": self.messages(history),
            "stream": True,
        }

        if self.endpoint.dialect == "tools":
            tool = {
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "input_schema": TOOL_PARAMETERS,
            }
            body["tools"] = [tool]
            body["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}

        return body

    def messages(self, history: Sequence[Item]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        for item in history:
            if isinstance(item, UserText):
                append(messages, "user", [{"type": "text", "text": item.text}])
            elif isinstance(item, AssistantTurn):
                append(messages, "assistant", self.assistant_content(item))
            else:
                append(messages, "user", self.result_content(item, history))

        return messages

    def assistant_content(self, turn: AssistantTurn) -> list[dict[str, Any]]:
        if turn.source == self.endpoint.source:
            raw: list[dict[str, Any]] = turn.raw
            return raw

        # Another model's turn, shown in this one's terms. Its thinking, if it
        # had any, stays behind.
        if self.endpoint.dialect == "text" or turn.call_id is None:
            text = turn_as_text(turn)
            return [{"type": "text", "text": text}]

        content: list[dict[str, Any]] = []
        if turn.text:
            content.append({"type": "text", "text": turn.text})

        call = {
            "type": "tool_use",
            "id": turn.call_id,
            "name": TOOL_NAME,
            "input": {"code": turn.code},
        }
        content.append(call)

        return content

    def result_content(self, result: ToolResult, history: Sequence[Item]) -> list[dict[str, Any]]:
        if self.endpoint.dialect == "text" or result.call_id is None:
            return [{"type": "text", "text": result_as_text(result)}]

        content: list[dict[str, Any]] = [
            {
                "type": "tool_result",
                "tool_use_id": result.call_id,
                "content": result.content,
                "is_error": result.is_error,
            }
        ]

        # Every tool_use needs its tool_result, the ones that were not run too.
        for extra in extra_calls_answered_by(result, history):
            content.append(
                {"type": "tool_result", "tool_use_id": extra, "content": NOT_RUN, "is_error": True}
            )

        return content


def extra_calls_answered_by(result: ToolResult, history: Sequence[Item]) -> tuple[str, ...]:
    for item in history:
        if isinstance(item, AssistantTurn) and item.call_id == result.call_id:
            return item.extra_call_ids

    return ()


def append(messages: list[dict[str, Any]], role: str, content: list[dict[str, Any]]) -> None:
    """Consecutive messages of one role become one: the API wants them alternating."""
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"].extend(content)
        return

    messages.append({"role": role, "content": content})


@dataclass
class StreamedMessage:
    """A message assembled from its stream, block by block."""

    blocks: dict[int, dict[str, Any]] = field(default_factory=dict)
    partial_json: dict[int, str] = field(default_factory=dict)
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0

    async def take(self, event: dict[str, Any], on_delta: OnDelta) -> None:
        kind = event.get("type")

        if kind == "message_start":
            usage = event["message"].get("usage") or {}
            self.input_tokens = usage.get("input_tokens", 0)
            self.output_tokens = usage.get("output_tokens", 0)

        elif kind == "content_block_start":
            index = event["index"]
            self.blocks[index] = dict(event["content_block"])

        elif kind == "content_block_delta":
            await self.take_delta(event["index"], event["delta"], on_delta)

        elif kind == "content_block_stop":
            self.finish_block(event["index"])

        elif kind == "message_delta":
            self.stop_reason = event["delta"].get("stop_reason") or self.stop_reason
            usage = event.get("usage") or {}
            self.output_tokens = usage.get("output_tokens", self.output_tokens)
            # Part of output_tokens, not on top of it.
            details = usage.get("output_tokens_details") or {}
            self.thinking_tokens = details.get("thinking_tokens", self.thinking_tokens) or 0

        elif kind == "error":
            error = event.get("error") or {}
            kind_name = error.get("type", "")
            message = error.get("message", "the stream reported an error")
            if kind_name == "overloaded_error":
                raise ProviderError("overloaded", message)
            raise ProviderError("unavailable", message)

    async def take_delta(self, index: int, delta: dict[str, Any], on_delta: OnDelta) -> None:
        block = self.blocks[index]
        kind = delta.get("type")

        if kind == "text_delta":
            block["text"] = block.get("text", "") + delta["text"]
            await on_delta(delta["text"])
        elif kind == "thinking_delta":
            block["thinking"] = block.get("thinking", "") + delta["thinking"]
        elif kind == "signature_delta":
            block["signature"] = block.get("signature", "") + delta["signature"]
        elif kind == "input_json_delta":
            self.partial_json[index] = self.partial_json.get(index, "") + delta["partial_json"]

    def finish_block(self, index: int) -> None:
        block = self.blocks[index]
        if block.get("type") != "tool_use":
            return

        text = self.partial_json.pop(index, "")
        if not text:
            block["input"] = {}
            return

        try:
            block["input"] = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("protocol", "a tool call whose input is not JSON") from exc

    def reply(self, endpoint: Endpoint) -> Reply:
        content = [self.blocks[index] for index in sorted(self.blocks)]

        text_parts = []
        calls = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(block)

        text = "".join(text_parts)
        code, call_id, extra = code_of(endpoint, text, calls)

        turn = AssistantTurn(
            text=text,
            code=code,
            call_id=call_id,
            source=endpoint.source,
            raw=content,
            extra_call_ids=extra,
        )
        usage = Usage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            reasoning_tokens=self.thinking_tokens,
        )

        return Reply(turn=turn, usage=usage, stop=self.stop(code))

    def stop(self, code: str | None) -> StopReason:
        if self.stop_reason == "refusal":
            return "refusal"

        if self.stop_reason == "max_tokens":
            return "max_tokens"

        if code is not None:
            return "code"

        return "answer"


def code_of(
    endpoint: Endpoint,
    text: str,
    calls: list[dict[str, Any]],
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """The code to run, the call it answers, and any calls that will not run."""
    if endpoint.dialect == "text":
        return extract_code(text), None, ()

    if not calls:
        return None, None, ()

    first = calls[0]
    code = first.get("input", {}).get("code")
    extra = tuple(call["id"] for call in calls[1:])

    if not isinstance(code, str):
        raise ProviderError("protocol", "a run_python call without a code string")

    return code, first["id"], extra
