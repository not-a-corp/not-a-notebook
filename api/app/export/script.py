"""The conversation as a Python script: the cells in order, in the `# %%`
percent format editors run cell by cell, with the chat as comments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.domain.messages import Message
from app.export.arrange import Ran, Said, arrange
from app.export.notebook import header, said


def commented(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line == "":
            lines.append("#")
        else:
            lines.append(f"# {line}")

    return "\n".join(lines)


def script(
    title: str,
    file_names: Sequence[str],
    cells: Sequence[dict[str, Any]],
    messages: Sequence[Message],
) -> str:
    blocks = [commented(header(title, file_names))]

    for entry in arrange(cells, messages):
        if isinstance(entry, Said):
            blocks.append(commented(said(entry.message)))
        if isinstance(entry, Ran):
            blocks.append("# %%\n" + entry.cell["source"])

    return "\n\n".join(blocks) + "\n"
