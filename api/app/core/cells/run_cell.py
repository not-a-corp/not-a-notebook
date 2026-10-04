"""Starting the run that executes one cell in the live kernel. Refused, by the
one-running-run index, while another run is in progress."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.cells import OwnedCell, find_cell
from app.db.runs import StartedRun, start_run


@dataclass(frozen=True)
class CellRun:
    run: StartedRun
    cell: OwnedCell


async def start_cell_run(conn: AsyncConnection[Any], user_id: UUID, cell_id: UUID) -> CellRun:
    cell = await find_cell(conn, user_id, cell_id)
    started = await start_run(conn, cell.conversation_row_id, "cell")

    return CellRun(run=started, cell=cell)
