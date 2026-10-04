"""A cell gone. The cells below it that had run are marked stale: the deleted cell
may have built something they use."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.cells import find_cell, mark_stale_below
from app.domain.errors import ConversationBusy


async def delete_cell(conn: AsyncConnection[Any], user_id: UUID, cell_id: UUID) -> None:
    """Gone; the cells below that ran go stale — the deleted cell may have built
    something they use."""
    cell = await find_cell(conn, user_id, cell_id)
    if cell.busy:
        raise ConversationBusy

    sql = """
        DELETE FROM cells c
         WHERE c.external_id = %(cell_id)s
    """

    params = {"cell_id": cell_id}

    async with conn.transaction():
        await conn.execute(sql, params)
        await mark_stale_below(conn, cell.conversation_row_id, cell.ref.position)
