"""The conversation as a Jupyter notebook (nbformat 4.5)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from html import escape
from typing import Any

from app.domain.messages import Message
from app.export.arrange import Ran, Said, arrange

PLOTLY_MIME = "application/vnd.plotly.v1+json"


def notebook(
    title: str,
    file_names: Sequence[str],
    cells: Sequence[dict[str, Any]],
    messages: Sequence[Message],
) -> str:
    notebook_cells = [markdown_cell("header", header(title, file_names))]

    for entry in arrange(cells, messages):
        if isinstance(entry, Said):
            notebook_cells.append(markdown_cell(str(entry.message.id), said(entry.message)))
        if isinstance(entry, Ran):
            notebook_cells.append(code_cell(entry.cell))

    document = {
        "cells": notebook_cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    return json.dumps(document, ensure_ascii=False, indent=1) + "\n"


def header(title: str, file_names: Sequence[str]) -> str:
    """The note at the top (api.md): where the files are expected, so running it
    elsewhere means putting them there or changing one line."""
    lines = [f"# {title}", "", "Exported from not-a-notebook."]

    if file_names:
        listed = ", ".join(f"`/data/{name}`" for name in file_names)
        lines.append("")
        lines.append(
            f"The code reads its files from `/data/`: {listed}. "
            "Put them there, or change the paths."
        )

    return "\n".join(lines)


def said(message: Message) -> str:
    if message.role == "user":
        return f"**You:** {message.text}"

    if message.kind == "question":
        return f"**The analyst asks:** {message.text}"

    return f"**Analyst:**\n\n{message.text}"


def cell_id(raw: str) -> str:
    # nbformat cell ids: 1 to 64 letters, digits, - and _.
    return raw.replace(":", "-")[:64]


def markdown_cell(raw_id: str, text: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "id": cell_id(raw_id),
        "metadata": {},
        "source": text,
    }


def code_cell(cell: dict[str, Any]) -> dict[str, Any]:
    execution_count = cell.get("execution_count")

    outputs = []
    for output in cell.get("outputs", []):
        converted = jupyter_output(output, execution_count)
        outputs.append(converted)

    return {
        "cell_type": "code",
        "id": cell_id(str(cell["id"])),
        "metadata": {},
        "execution_count": execution_count,
        "source": cell["source"],
        "outputs": outputs,
    }


def jupyter_output(output: dict[str, Any], execution_count: int | None) -> dict[str, Any]:
    """An output as api.md shows it, back in Jupyter's own shape."""
    kind = output["kind"]

    if kind == "stream":
        return {"output_type": "stream", "name": output["name"], "text": output["text"]}

    if kind == "error":
        return {
            "output_type": "error",
            "ename": output["name"],
            "evalue": output["value"],
            "traceback": output["traceback"],
        }

    if kind == "text" and execution_count is not None:
        return {
            "output_type": "execute_result",
            "execution_count": execution_count,
            "data": {"text/plain": output["text"]},
            "metadata": {},
        }

    return {"output_type": "display_data", "data": display_data(output), "metadata": {}}


def display_data(output: dict[str, Any]) -> dict[str, Any]:
    kind = output["kind"]

    if kind == "plotly":
        return {PLOTLY_MIME: output["spec"], "text/plain": "<plotly figure>"}

    if kind == "table":
        return {"text/html": table_html(output), "text/plain": table_text(output)}

    if kind == "image":
        return {"image/png": output["png"], "text/plain": "<image>"}

    return {"text/plain": output["text"]}


def shown(value: Any) -> str:
    if value is None:
        return "null"

    return str(value)


def table_html(output: dict[str, Any]) -> str:
    head = "".join(f"<th>{escape(str(column))}</th>" for column in output["columns"])

    body = []
    for row in output["rows"]:
        cells = "".join(f"<td>{escape(shown(value))}</td>" for value in row)
        body.append(f"<tr>{cells}</tr>")

    note = ""
    if output["total_rows"] > len(output["rows"]):
        note = f"<p>{len(output['rows'])} of {output['total_rows']} rows</p>"

    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>{note}"


def table_text(output: dict[str, Any]) -> str:
    lines = ["\t".join(str(column) for column in output["columns"])]
    for row in output["rows"]:
        lines.append("\t".join(shown(value) for value in row))

    return "\n".join(lines)
