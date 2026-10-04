"""Anything that speaks /v1/chat/completions: Ollama, vLLM, LM Studio,
OpenRouter, DeepSeek, Qwen, Groq...

The de facto standard, which is why what breaks is not the protocol but each new
model's quirks. Defended by recorded streams (tests/fixtures/providers) and,
mostly, by the text dialect: the model that stumbles on tool calls writes a
fenced block fine.

No `max_tokens` is sent: servers disagree on its name and its ceiling, and each
one's default is safer than a guess.
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
    ToolResult,
    Usage,
    UserText,
)
from app.providers.dialect import (
    NOT_RUN,
    TOOL_NAME,
    TOOLS,
    Call,
    read_reply,
    result_as_text,
    stop_of,
    turn_as_text,
)
from app.providers.endpoint import Endpoint
from app.providers.streaming import events, open_stream


class ChatCompletionsModel:
    def __init__(self, endpoint: Endpoint, http: httpx2.AsyncClient) -> None:
        self.endpoint = endpoint
        self.http = http

    async def complete(self, system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        if self.endpoint.base_url is None:
            raise ProviderError("bad_request", "an openai_compatible model needs a base_url")

        url = f"{self.endpoint.base_url.rstrip('/')}/chat/completions"

        headers = {"content-type": "application/json"}
        if self.endpoint.api_key is not None:
            headers["authorization"] = f"Bearer {self.endpoint.api_key}"

        body = self.request_body(system, history)

        async with open_stream(self.http, url, headers, body) as response:
            streamed = StreamedCompletion()

            async for event in events(response):
                await streamed.take(event.json(), on_delta)

        return streamed.reply(self.endpoint)

    def request_body(self, system: str, history: Sequence[Item]) -> dict[str, Any]:
        messages = [{"role": "system", "content": system}]
        messages.extend(self.messages(history))

        body: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if self.endpoint.dialect == "tools":
            tools = []
            for spec in TOOLS:
                function = {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                }
                tools.append({"type": "function", "function": function})

            body["tools"] = tools
            body["tool_choice"] = "auto"
            body["parallel_tool_calls"] = False

        return body

    def messages(self, history: Sequence[Item]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        for item in history:
            if isinstance(item, UserText):
                messages.append({"role": "user", "content": item.text})
            elif isinstance(item, AssistantTurn):
                messages.append(self.assistant_message(item))
            else:
                messages.extend(self.result_messages(item, history))

        return messages

    def assistant_message(self, turn: AssistantTurn) -> dict[str, Any]:
        if turn.source == self.endpoint.source:
            raw: dict[str, Any] = turn.raw
            return raw

        if self.endpoint.dialect == "text" or turn.call_id is None:
            return {"role": "assistant", "content": turn_as_text(turn)}

        call = {
            "id": turn.call_id,
            "type": "function",
            "function": {"name": TOOL_NAME, "arguments": json.dumps({"code": turn.code})},
        }

        return {"role": "assistant", "content": turn.text or None, "tool_calls": [call]}

    def result_messages(self, result: ToolResult, history: Sequence[Item]) -> list[dict[str, Any]]:
        if self.endpoint.dialect == "text" or result.call_id is None:
            return [{"role": "user", "content": result_as_text(result)}]

        messages = [{"role": "tool", "tool_call_id": result.call_id, "content": result.content}]

        for item in history:
            if isinstance(item, AssistantTurn) and item.call_id == result.call_id:
                for extra in item.extra_call_ids:
                    messages.append({"role": "tool", "tool_call_id": extra, "content": NOT_RUN})

        return messages


@dataclass
class StreamedCompletion:
    """A completion assembled from its chunks."""

    text: str = ""
    calls: dict[int, dict[str, Any]] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    refused: bool = False

    async def take(self, chunk: dict[str, Any], on_delta: OnDelta) -> None:
        # OpenRouter and others report a failure mid-stream as a chunk.
        if "error" in chunk:
            error = chunk["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ProviderError("unavailable", message or "the stream reported an error")

        if chunk.get("usage"):
            self.usage = chunk["usage"]

        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}

            content = delta.get("content")
            if content:
                self.text += content
                await on_delta(content)

            if delta.get("refusal"):
                self.refused = True

            for call in delta.get("tool_calls") or []:
                self.take_call(call)

            if choice.get("finish_reason"):
                self.finish_reason = choice["finish_reason"]

    def take_call(self, call: dict[str, Any]) -> None:
        """Tool calls arrive in pieces keyed by index: the id and name once, the
        arguments as a string in fragments."""
        index = call.get("index", 0)
        assembled = self.calls.setdefault(index, {"id": None, "name": None, "arguments": ""})

        if call.get("id"):
            assembled["id"] = call["id"]

        function = call.get("function") or {}
        if function.get("name"):
            assembled["name"] = function["name"]
        if function.get("arguments"):
            assembled["arguments"] += function["arguments"]

    def reply(self, endpoint: Endpoint) -> Reply:
        assembled = [self.calls[index] for index in sorted(self.calls)]

        calls = []
        tool_calls = []
        for piece in assembled:
            if piece["id"] is None or piece["name"] is None:
                raise ProviderError("protocol", "a tool call without an id or a name")

            arguments = parsed_arguments(piece["arguments"])
            calls.append(Call(id=piece["id"], name=piece["name"], arguments=arguments))

            function = {"name": piece["name"], "arguments": piece["arguments"]}
            tool_calls.append({"id": piece["id"], "type": "function", "function": function})

        reading = read_reply(endpoint.dialect, self.text, calls)

        raw: dict[str, Any] = {"role": "assistant", "content": self.text or None}
        if tool_calls:
            raw["tool_calls"] = tool_calls

        turn = AssistantTurn(
            text=self.text,
            code=reading.code,
            call_id=reading.call_id,
            source=endpoint.source,
            raw=raw,
            extra_call_ids=reading.extra_call_ids,
        )

        details = self.usage.get("completion_tokens_details") or {}
        usage = Usage(
            input_tokens=self.usage.get("prompt_tokens", 0) or 0,
            output_tokens=self.usage.get("completion_tokens", 0) or 0,
            reasoning_tokens=details.get("reasoning_tokens", 0) or 0,
        )
        stop = stop_of(
            reading,
            refused=self.refused,
            cut_off=self.finish_reason == "length",
        )

        return Reply(turn=turn, usage=usage, stop=stop, question=reading.question)


def parsed_arguments(text: str | None) -> dict[str, Any]:
    """A tool call's arguments: a JSON object sent as a string."""
    try:
        arguments = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise ProviderError("protocol", "a tool call whose arguments are not JSON") from exc

    if not isinstance(arguments, dict):
        raise ProviderError("protocol", "a tool call whose arguments are not an object")

    return arguments
