"""Jupyter messages in, the domain's outputs out.

A display bundle carries the same value in several MIME types. One is picked, in
this order, because each is a richer version of the ones after it:

    Plotly spec  >  table  >  PNG  >  plain text

HTML is never picked. It is the kernel's styling of something the client should
style itself, and anything that offers HTML offers plain text too.
"""

from __future__ import annotations

import re
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

PLOTLY_MIME = "application/vnd.plotly.v1+json"

# Emitted by the sandbox's own display extension (sandbox/kernel/).
TABLE_MIME = "application/vnd.not-a-notebook.table+json"

# IPython colours its tracebacks for a terminal. The model reads them and the
# client renders them, and to both the escape codes are noise.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def from_message(kind: str, content: dict[str, Any]) -> Output | None:
    """The output a message carries, or None for messages that carry none."""
    if kind == "stream":
        return StreamOutput(name=content["name"], text=content["text"])

    if kind == "error":
        return from_error(content)

    if kind in ("execute_result", "display_data"):
        return from_bundle(content["data"])

    return None


def from_error(content: dict[str, Any]) -> ErrorOutput:
    traceback = []
    for line in content["traceback"]:
        plain = ANSI_ESCAPE.sub("", line)
        traceback.append(plain)

    return ErrorOutput(name=content["ename"], value=content["evalue"], traceback=traceback)


def from_bundle(bundle: dict[str, Any]) -> Output | None:
    if PLOTLY_MIME in bundle:
        return PlotlyOutput(spec=bundle[PLOTLY_MIME])

    if TABLE_MIME in bundle:
        table = bundle[TABLE_MIME]
        return TableOutput(
            columns=table["columns"],
            rows=table["rows"],
            total_rows=table["total_rows"],
        )

    if "image/png" in bundle:
        return ImageOutput(png=bundle["image/png"])

    if "text/plain" in bundle:
        return TextOutput(text=bundle["text/plain"])

    return None
