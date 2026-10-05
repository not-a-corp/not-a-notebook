"""Where the chat goes among the cells.

The cells keep the notebook's order — that is the analysis as it runs. Each
question goes just before the first cell its run wrote, and the analyst's reply
just after the last one, so the notebook reads the way the analysis happened. A
question whose run wrote no cell goes before the next cell asked after it; what
is left at the end goes last, in the order it was said.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.domain.messages import Message


@dataclass(frozen=True)
class Said:
    message: Message


@dataclass(frozen=True)
class Ran:
    cell: dict[str, Any]


Entry = Said | Ran


def run_of(cell: dict[str, Any]) -> UUID | None:
    run_id = cell.get("run_id")
    if run_id is None:
        return None

    return UUID(str(run_id))


def arrange(cells: Sequence[dict[str, Any]], messages: Sequence[Message]) -> list[Entry]:
    last_cell_of: dict[UUID, int] = {}
    for index, cell in enumerate(cells):
        run_id = run_of(cell)
        if run_id is not None:
            last_cell_of[run_id] = index

    # Messages in the order they were said; each is placed once.
    waiting = sorted(messages, key=lambda message: message.created_at)
    placed: set[UUID] = set()
    entries: list[Entry] = []

    def place(message: Message) -> None:
        entries.append(Said(message))
        placed.add(message.id)

    for index, cell in enumerate(cells):
        run_id = run_of(cell)
        opening = [
            m for m in waiting if m.run_id == run_id and m.role == "user" and m.id not in placed
        ]

        if run_id is not None and opening:
            asked_at = opening[0].created_at
            # Whatever was said before this question, with no cell of its own.
            for message in waiting:
                earlier = message.created_at < asked_at
                own_cells = message.run_id is not None and message.run_id in last_cell_of
                if earlier and not own_cells and message.id not in placed:
                    place(message)
            for message in opening:
                place(message)

        entries.append(Ran(cell))

        if run_id is not None and last_cell_of.get(run_id) == index:
            for message in waiting:
                if message.run_id == run_id and message.id not in placed:
                    place(message)

    for message in waiting:
        if message.id not in placed:
            place(message)

    return entries
