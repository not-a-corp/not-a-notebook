"""An output in the contract's shape: its kind, and the fields api.md lists for it.

The same shape everywhere an output leaves the kernel: the cell_outputs table
stores it (kind beside a payload of fields), cell.output events flatten it, and
GET /conversations/{id} shows it. Converted here, once, both ways.
"""

from __future__ import annotations

from typing import Any

from app.domain.runtime import (
    ErrorOutput,
    ImageOutput,
    Output,
    PlotlyOutput,
    StreamOutput,
    TableOutput,
    TextOutput,
)


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
