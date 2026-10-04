"""Talking to a model: the history it reads, the reply it gives, the protocol every
provider adapter implements (decision 4).

The agent loop sees only this. Whether the model called a tool or wrote a fenced
code block (the two dialects), and whether it speaks the Messages API, the
Responses API or Chat Completions, is the adapter's business; the loop gets a
Reply with `code` set or not.

**The history is append-only.** Models that think return signed thinking blocks
(Anthropic) or encrypted reasoning items (OpenAI) that must go back unchanged on
the next turn, and editing an earlier turn invalidates them. Nothing rewrites an
item once it is in the history — a retried cell is rewritten in the notebook
(decision 18), never here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class UserText:
    text: str


@dataclass(frozen=True)
class AssistantTurn:
    """What a model said, twice over.

    `text`, `code` and `call_id` are the portable reading — enough for any other
    model to be shown this turn if the conversation switches models. `raw` is the
    provider's own record of it, thinking and signatures included, and is replayed
    only to the `source` that produced it.
    """

    text: str
    code: str | None
    # The tool call the next ToolResult answers. None in the text dialect.
    call_id: str | None
    # adapter:model — e.g. "anthropic:claude-sonnet-5-5".
    source: str
    raw: Any
    # Extra tool calls in the same turn. Only one runs; the others are answered
    # as not run, because every call needs an answer.
    extra_call_ids: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class ToolResult:
    """What running the turn's code produced, as the model reads it."""

    call_id: str | None
    content: str
    is_error: bool = False


type Item = UserText | AssistantTurn | ToolResult


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0


# code: the model wants code run. answer: it is done. max_tokens: it was cut
# off. refusal: a safety classifier declined (Anthropic's stop reason; OpenAI's
# refusal content part).
type StopReason = Literal["code", "answer", "max_tokens", "refusal"]


@dataclass(frozen=True)
class Reply:
    turn: AssistantTurn
    usage: Usage
    stop: StopReason


type OnDelta = Callable[[str], Awaitable[None]]


class Model(Protocol):
    async def complete(self, system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        """on_delta receives the visible text as it streams."""
        ...


type ProviderErrorKind = Literal[
    "auth",
    "rate_limit",
    "overloaded",
    "bad_request",
    "unavailable",
    "network",
    "protocol",
]


class ProviderError(Exception):
    """The provider could not give a reply. `kind` is for code to branch on;
    the message is the provider's own words, for the person reading the log —
    never anything that holds the key."""

    def __init__(self, kind: ProviderErrorKind, message: str, status: int | None = None) -> None:
        self.kind = kind
        self.status = status
        super().__init__(message)
