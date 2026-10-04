"""What the model reads before the user's new question: the conversation so far,
rebuilt from what the conversation holds now.

Not a transcript kept from earlier runs. The notebook is the shared truth
(decision 10): a cell the user edited is shown as the user left it, a retried
cell as the version that worked, and nothing a model thought in an earlier run is
sent again — thinking is bound to the run that produced it.

    earlier question → earlier answer → … → [files, notebook, kernel state] + question
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.llm import AssistantTurn, Item, UserText

# What an earlier answer looks like to whichever model reads it now.
HISTORY_SOURCE = "history"

# A cell's outputs, as the model reads them in the notebook's summary. The cells
# that matter for the next step are usually the last few; old ones are context.
CELL_OUTPUT_CHARACTERS = 1_500
CELL_SOURCE_CHARACTERS = 4_000


@dataclass(frozen=True)
class PastMessage:
    role: str
    text: str


@dataclass(frozen=True)
class FileSummary:
    name: str
    bytes: int
    profile: dict[str, Any] | None


@dataclass(frozen=True)
class CellSummary:
    position: int
    origin: str
    source: str
    status: str
    stale: bool
    outputs_text: str


def history_for(
    messages: Sequence[PastMessage],
    files: Sequence[FileSummary],
    cells: Sequence[CellSummary],
    kernel_fresh: bool,
    question: str,
) -> list[Item]:
    history: list[Item] = []

    for message in messages:
        if message.role == "user":
            history.append(UserText(message.text))
        else:
            answer = AssistantTurn(
                text=message.text,
                code=None,
                call_id=None,
                source=HISTORY_SOURCE,
                raw=None,
            )
            history.append(answer)

    briefing = briefing_for(files, cells, kernel_fresh)
    history.append(UserText(f"{briefing}\n\n{question}"))

    return history


def briefing_for(
    files: Sequence[FileSummary],
    cells: Sequence[CellSummary],
    kernel_fresh: bool,
) -> str:
    sections = [files_section(files), notebook_section(cells, kernel_fresh)]

    return "\n\n".join(sections)


def files_section(files: Sequence[FileSummary]) -> str:
    if not files:
        return "<files>\nNo files have been uploaded to this conversation.\n</files>"

    parts = ["<files>"]

    for file in files:
        parts.append(f"/data/{file.name} ({file.bytes:,} bytes)")

        if file.profile is None:
            parts.append("Profile: not ready yet.")
        else:
            profile = json.dumps(file.profile, ensure_ascii=False, separators=(",", ":"))
            parts.append(f"Profile: {profile}")

    parts.append("</files>")

    return "\n".join(parts)


def notebook_section(cells: Sequence[CellSummary], kernel_fresh: bool) -> str:
    if not cells:
        return "<notebook>\nThe notebook is empty.\n</notebook>"

    parts = ["<notebook>"]

    if kernel_fresh:
        parts.append(
            "The kernel was restarted: none of the cells below has run in it. Their "
            "variables do not exist until you run the code again."
        )

    for cell in cells:
        state = cell.status
        if cell.stale:
            state += ", stale: a cell above it changed after it ran"

        source = cell.source[:CELL_SOURCE_CHARACTERS]
        parts.append(f"[{cell.position}] {cell.origin}, {state}")
        parts.append(f"```python\n{source}\n```")

        if cell.outputs_text:
            parts.append(f"Output:\n{cell.outputs_text[:CELL_OUTPUT_CHARACTERS]}")

    parts.append("</notebook>")

    return "\n".join(parts)
