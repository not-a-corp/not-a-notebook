"""One conversation as a file to keep: a notebook or a script."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection

from app.core.conversations.get_conversation import get_conversation
from app.export.notebook import notebook
from app.export.script import script

ExportFormat = Literal["ipynb", "py"]

MEDIA_TYPES: dict[ExportFormat, str] = {
    "ipynb": "application/x-ipynb+json",
    "py": "text/x-python; charset=utf-8",
}


@dataclass(frozen=True)
class Export:
    filename: str
    media_type: str
    content: str


def file_stem(title: str) -> str:
    """The title as a file name: words kept, everything else a dash."""
    stem = re.sub(r"[^\w]+", "-", title, flags=re.UNICODE).strip("-_")
    if not stem:
        return "conversation"

    return stem[:100]


async def export_conversation(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
    export_format: ExportFormat,
) -> Export:
    # Whether a kernel runs does not change what is exported: no running set.
    shown = await get_conversation(conn, user_id, conversation_id, frozenset())

    file_names = [file.name for file in shown.files]

    if export_format == "ipynb":
        content = notebook(shown.title, file_names, shown.cells, shown.messages)
    else:
        content = script(shown.title, file_names, shown.cells, shown.messages)

    filename = f"{file_stem(shown.title)}.{export_format}"

    return Export(filename=filename, media_type=MEDIA_TYPES[export_format], content=content)
