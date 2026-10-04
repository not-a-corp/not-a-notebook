"""New source for a cell; nothing runs (Jupyter semantics, decision 10). The cells
below it that had run are marked stale: what they show may no longer follow from
the code above them."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.cells import describe_cell, find_cell, mark_stale_below
from app.domain.agent import CellRef
from app.domain.errors import ConversationBusy


async def edit_cell(
    conn: AsyncConnection[Any],
    user_id: UUID,
    cell_id: UUID,
    source: str,
) -> dict[str, Any]:
    """New source; nothing runs. The cells below that ran go stale (api.md). The
    edited cell keeps its outputs until it runs again."""
    cell = await find_cell(conn, user_id, cell_id)
    if cell.busy:
        raise ConversationBusy

    update_sql = """
        UPDATE cells c
           SET source = %(source)s
         WHERE c.external_id = %(cell_id)s
    """

    update_params = {
        "source": source,
        "cell_id": cell_id,
    }

    async with conn.transaction():
        await conn.execute(update_sql, update_params)
        await mark_stale_below(conn, cell.conversation_row_id, cell.ref.position)

    # describe_cell reads the cell by its id; the position is not consulted.
    return await describe_cell(conn, CellRef(id=cell_id, position=0))
