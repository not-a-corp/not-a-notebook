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
from typing import Any

from app.domain.llm import AssistantTurn, ToolResult

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
