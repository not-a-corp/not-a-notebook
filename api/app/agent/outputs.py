"""A cell's outputs, two ways: as an event payload, and as text for the model.

The model reads what the code produced as text. Tables come back cut, charts as
a line saying what was drawn, images as a line saying one was drawn: the model
needs to know what happened, not to receive the bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.domain.runtime import (
    ErrorOutput,
    ExecutionResult,
    ImageOutput,
    Output,
    PlotlyOutput,
    StreamOutput,
    TableOutput,
    TextOutput,
)

# What the model reads of one execution. Past this, the middle is cut: the start
# says what began, the end holds the error or the result.
MAX_RESULT_CHARACTERS = 12_000

# Rows of a table the model sees. The client gets up to 100; the model rarely
# needs more than a glance to check its own work.
MODEL_TABLE_ROWS = 20

# A traceback's last lines carry the error; the frames above it are noise.
TRACEBACK_LINES = 15


def kind_of(output: Output) -> str:
    kinds: dict[type, str] = {
        StreamOutput: "stream",
        ErrorOutput: "error",
        PlotlyOutput: "plotly",
        TableOutput: "table",
        TextOutput: "text",
        ImageOutput: "image",
    }

    return kinds[type(output)]


def fields_of(output: Output) -> dict[str, Any]:
    """An output's fields, as api.md lists them for its kind — what cell_outputs
    stores as the payload and events flatten after `kind`."""
    if isinstance(output, StreamOutput):
        return {"name": output.name, "text": output.text}

    if isinstance(output, ErrorOutput):
        return {"name": output.name, "value": output.value, "traceback": output.traceback}

    if isinstance(output, PlotlyOutput):
        return {"spec": output.spec}

    if isinstance(output, TableOutput):
        return {"columns": output.columns, "rows": output.rows, "total_rows": output.total_rows}

    if isinstance(output, TextOutput):
        return {"text": output.text}

    return {"png": output.png}


def as_text(outputs: Sequence[Output], result: ExecutionResult | None) -> str:
    """What the model reads back after its code ran."""
    parts = []

    for output in outputs:
        parts.append(output_as_text(output))

    if result is not None and result.status == "timed_out":
        parts.append("[Interrupted: the code ran past the time limit. The kernel's state is kept.]")

    text = "\n".join(part for part in parts if part)
    if not text:
        text = "[The code ran and printed nothing.]"

    return shortened(text)


def output_as_text(output: Output) -> str:
    if isinstance(output, StreamOutput):
        return output.text.rstrip("\n")

    if isinstance(output, ErrorOutput):
        lines = output.traceback[-TRACEBACK_LINES:]
        return "\n".join(lines)

    if isinstance(output, TableOutput):
        return table_as_text(output)

    if isinstance(output, TextOutput):
        return output.text

    if isinstance(output, PlotlyOutput):
        return chart_as_text(output)

    return "[An image was displayed.]"


def table_as_text(table: TableOutput) -> str:
    lines = [" | ".join(table.columns)]

    for row in table.rows[:MODEL_TABLE_ROWS]:
        cells = []
        for value in row:
            cells.append(cell_as_text(value))
        lines.append(" | ".join(cells))

    shown = min(len(table.rows), MODEL_TABLE_ROWS)
    lines.append(f"[{shown} of {table.total_rows} rows shown]")

    return "\n".join(lines)


def cell_as_text(value: Any) -> str:
    # An empty cell reads as null, not as an empty string the model could take
    # for a value.
    if value is None:
        return "null"

    return str(value)


def chart_as_text(chart: PlotlyOutput) -> str:
    data = chart.spec.get("data") or []
    layout = chart.spec.get("layout") or {}

    title = layout.get("title")
    if isinstance(title, dict):
        title = title.get("text")

    kinds = set()
    for trace in data:
        if isinstance(trace, dict):
            kinds.add(str(trace.get("type", "scatter")))

    drawn = ", ".join(sorted(kinds))
    if not drawn:
        drawn = "empty"

    described = f"[A Plotly chart was displayed: {len(data)} trace(s), {drawn}"
    if title:
        described += f', titled "{title}"'

    return described + ".]"


def shortened(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARACTERS:
        return text

    half = MAX_RESULT_CHARACTERS // 2
    cut = len(text) - MAX_RESULT_CHARACTERS

    return f"{text[:half]}\n[… {cut} characters cut …]\n{text[-half:]}"


def from_stored(kind: str, payload: dict[str, Any]) -> Output:
    """An output as cell_outputs stores it — kind beside its fields — back into
    the domain's shape."""
    if kind == "stream":
        return StreamOutput(name=payload["name"], text=payload["text"])

    if kind == "error":
        return ErrorOutput(
            name=payload["name"], value=payload["value"], traceback=payload["traceback"]
        )

    if kind == "plotly":
        return PlotlyOutput(spec=payload["spec"])

    if kind == "table":
        return TableOutput(
            columns=payload["columns"], rows=payload["rows"], total_rows=payload["total_rows"]
        )

    if kind == "text":
        return TextOutput(text=payload["text"])

    return ImageOutput(png=payload["png"])


def flattened(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """An output as api.md shows it: its kind, then its fields."""
    shown: dict[str, Any] = {"kind": kind}

    for name, value in payload.items():
        shown[name] = value

    return shown
