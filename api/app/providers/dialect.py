"""The two dialects (decision 4): how a model hands over code to run.

**tools** — native tool calling: the model calls `run_python(code=...)`.
**text** — the model writes a fenced ```python block and the harness takes it.
Small and local models that stumble on tool calling write markdown fine.

Both produce the same `Reply.code`; the loop never knows which ran. The pieces
here are what every adapter shares: the tool's definition, how code is found in
text, and how a turn or a result is shown to a model of the other dialect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.domain.llm import AssistantTurn, ProviderError, StopReason, ToolResult

# ── the tools dialect's two tools ──────────────────────────────────────────────

TOOL_NAME = "run_python"

TOOL_DESCRIPTION = (
    "Run Python in the conversation's Jupyter kernel. State persists between runs: "
    "variables, imports and loaded DataFrames are still there next time. The user's "
    "files are read-only at /data. Returns what the code printed, the value of its "
    "last expression, and any error with its traceback."
)

TOOL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {
            "type": "string",
            "description": "The Python to run, as one cell.",
        },
    },
    "required": ["code"],
    "additionalProperties": False,
}

ASK_NAME = "ask_user"

ASK_DESCRIPTION = (
    "Ask the user a question and stop. Use it when the question is ambiguous, or when "
    "the data cannot answer it as asked — a period the file does not cover, a column "
    "that could mean two things — instead of guessing."
)

ASK_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "The question, in the user's language.",
        },
    },
    "required": ["question"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


TOOLS = [
    ToolSpec(name=TOOL_NAME, description=TOOL_DESCRIPTION, parameters=TOOL_PARAMETERS),
    ToolSpec(name=ASK_NAME, description=ASK_DESCRIPTION, parameters=ASK_PARAMETERS),
]

# The text dialect's way to ask: a reply that starts with this.
QUESTION_MARKER = "QUESTION:"

# The first ```python block. A bare ``` fence counts only when nothing else does:
# models write ```text and ```json for things that are not code.
PYTHON_FENCE = re.compile(r"```(?:python|py)[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)
BARE_FENCE = re.compile(r"```[ \t]*\n(.*?)```", re.DOTALL)

NOT_RUN = (
    "Not run: only one run_python call per turn is executed. "
    "Send the next one after reading this result."
)


def extract_code(text: str) -> str | None:
    """The code a text-dialect reply asks to run, or None when it asks for none."""
    match = PYTHON_FENCE.search(text) or BARE_FENCE.search(text)
    if match is None:
        return None

    code = match.group(1).strip("\n")
    if not code.strip():
        return None

    return code


def code_as_markdown(code: str) -> str:
    return f"```python\n{code}\n```"


def turn_as_text(turn: AssistantTurn) -> str:
    """A turn as a text-dialect model would have written it: its words, then its
    code in a fence — unless the words already hold that fence."""
    if turn.code is None or turn.code in turn.text:
        return turn.text

    fence = code_as_markdown(turn.code)
    if not turn.text:
        return fence

    return f"{turn.text}\n\n{fence}"


def result_as_text(result: ToolResult) -> str:
    """A result as a text-dialect model reads it: a user message."""
    heading = "Output of your code:"
    if result.is_error:
        heading = "Your code raised an error:"

    return f"{heading}\n\n{result.content}"


# ── reading a reply ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Call:
    """A tool call in no provider's shape: what every adapter's calls become."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Reading:
    code: str | None
    question: str | None
    # The call the next ToolResult answers; None in the text dialect.
    call_id: str | None
    extra_call_ids: tuple[str, ...]


def read_reply(dialect: str, text: str, calls: list[Call]) -> Reading:
    """What a reply asks for: code to run, a question for the user, or neither.

    In the tools dialect only the first call counts — one kernel runs one cell at
    a time — and the rest are answered as not run.
    """
    if dialect == "text":
        code = extract_code(text)
        question = None
        if code is None:
            question = question_in(text)

        return Reading(code=code, question=question, call_id=None, extra_call_ids=())

    if not calls:
        return Reading(code=None, question=None, call_id=None, extra_call_ids=())

    first = calls[0]
    extra = tuple(call.id for call in calls[1:])

    if first.name == ASK_NAME:
        question = first.arguments.get("question")
        if not isinstance(question, str):
            raise ProviderError("protocol", "an ask_user call without a question string")

        return Reading(code=None, question=question, call_id=first.id, extra_call_ids=extra)

    if first.name != TOOL_NAME:
        raise ProviderError("protocol", f"a call to a tool that does not exist: {first.name}")

    code = first.arguments.get("code")
    if not isinstance(code, str):
        raise ProviderError("protocol", "a run_python call without a code string")

    return Reading(code=code, question=None, call_id=first.id, extra_call_ids=extra)


def question_in(text: str) -> str | None:
    stripped = text.lstrip()
    if not stripped.upper().startswith(QUESTION_MARKER):
        return None

    question = stripped[len(QUESTION_MARKER) :].strip()
    if not question:
        return None

    return question


def stop_of(reading: Reading, refused: bool, cut_off: bool) -> StopReason:
    """The same order for every adapter: what the provider says first, then what
    the reply asks for."""
    if refused:
        return "refusal"

    if cut_off:
        return "max_tokens"

    if reading.code is not None:
        return "code"

    if reading.question is not None:
        return "question"

    return "answer"
