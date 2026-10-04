"""Cells you write, edit, delete and run — the notebook's half of decision 10.

Jupyter semantics: editing or running a cell touches that cell only. Every cell
below it that already ran is marked **stale** — what it shows may no longer follow
from the code above it. Run all is what clears the marks, by running everything
again from a fresh kernel.

Every cell is reached through its conversation's owner; someone else's cell is
CELL_NOT_FOUND. Changing a cell while a run is in progress is CONVERSATION_BUSY:
the run may be executing it, or one above it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, errors

from app.core.cells import cell_shape, describe_cell
from app.domain.agent import CellRef
from app.domain.errors import CellNotFound, ConversationBusy, ConversationNotFound


@dataclass(frozen=True)
class OwnedCell:
    ref: CellRef
    source: str
    conversation_row_id: int
    conversation_id: UUID
    busy: bool


async def find_cell(conn: AsyncConnection[Any], user_id: UUID, cell_id: UUID) -> OwnedCell:
    sql = """
        SELECT c.external_id,
               c.position,
               c.source,
               v.id AS conversation_row_id,
               v.external_id AS conversation_id,
               EXISTS (
                   SELECT 1
                     FROM runs r
                    WHERE r.conversation_id = v.id
                      AND r.status = 'running'
               ) AS busy
          FROM cells c
          JOIN conversations v
            ON v.id = c.conversation_id
          JOIN users u
            ON u.id = v.user_id
         WHERE u.external_id = %(user_id)s
           AND c.external_id = %(cell_id)s
    """

    params = {
        "user_id": user_id,
        "cell_id": cell_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        raise CellNotFound

    return OwnedCell(
        ref=CellRef(id=row["external_id"], position=row["position"]),
        source=row["source"],
        conversation_row_id=row["conversation_row_id"],
        conversation_id=row["conversation_id"],
        busy=row["busy"],
    )


async def create_user_cell(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
    source: str,
    after: UUID | None,
    at_end: bool,
) -> dict[str, Any]:
    """A cell you wrote: at the end (at_end), first (after None), or right after
    another. It does not run."""
    conversation_sql = """
        SELECT v.id
          FROM conversations v
          JOIN users u
            ON u.id = v.user_id
         WHERE u.external_id = %(user_id)s
           AND v.external_id = %(conversation_id)s
    """

    conversation_params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }

    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(conversation_sql, conversation_params)
        conversation = await cur.fetchone()

        if conversation is None:
            raise ConversationNotFound

        position = await position_for(conn, conversation["id"], after, at_end)
        cell = await insert_at(conn, conversation["id"], position, source)

    return cell


async def position_for(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    after: UUID | None,
    at_end: bool,
) -> int:
    """The new cell's position, with room made for it."""
    if at_end:
        end_sql = """
            SELECT coalesce(max(c.position), 0) + 1 AS position
              FROM cells c
             WHERE c.conversation_id = %(conversation_id)s
        """

        end_params = {"conversation_id": conversation_row_id}

        async with conn.cursor() as cur:
            await cur.execute(end_sql, end_params)
            row = await cur.fetchone()

        assert row is not None  # an aggregate always returns its one row
        position: int = row["position"]
        return position

    if after is None:
        position = 1
    else:
        position = await position_after(conn, conversation_row_id, after)

    # Everything from there down moves one place. For a moment two cells share a
    # position; the unique constraint is DEFERRABLE for exactly this (schema.sql).
    shift_sql = """
        UPDATE cells c
           SET position = c.position + 1
         WHERE c.conversation_id = %(conversation_id)s
           AND c.position >= %(position)s
    """

    shift_params = {
        "conversation_id": conversation_row_id,
        "position": position,
    }

    await conn.execute(shift_sql, shift_params)

    return position


async def position_after(conn: AsyncConnection[Any], conversation_row_id: int, after: UUID) -> int:
    sql = """
        SELECT c.position
          FROM cells c
         WHERE c.conversation_id = %(conversation_id)s
           AND c.external_id = %(cell_id)s
    """

    params = {
        "conversation_id": conversation_row_id,
        "cell_id": after,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    # Not a cell of this conversation — maybe not a cell at all.
    if row is None:
        raise CellNotFound

    position: int = row["position"] + 1
    return position


async def insert_at(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    position: int,
    source: str,
) -> dict[str, Any]:
    sql = """
        INSERT INTO cells AS c (conversation_id, position, origin, source)
        VALUES (%(conversation_id)s, %(position)s, 'user', %(source)s)
        RETURNING c.id AS row_id,
                  c.external_id AS id,
                  c.position,
                  c.origin,
                  NULL::uuid AS run_id,
                  c.source,
                  c.status,
                  c.stale,
                  c.attempts,
                  c.execution_count,
                  c.executed_at,
                  c.duration_ms
    """

    params: dict[str, Any] = {
        "conversation_id": conversation_row_id,
        "position": position,
        "source": source,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    assert row is not None  # RETURNING on a successful INSERT

    return cell_shape(row, [])


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

    return await shown(conn, cell_id)


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


async def mark_stale_below(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    position: int,
) -> list[str]:
    """Marks every cell below `position` that has run, and returns the ones that
    were not stale already — what cells.stale announces."""
    sql = """
        UPDATE cells c
           SET stale = true
         WHERE c.conversation_id = %(conversation_id)s
           AND c.position > %(position)s
           AND c.executed_at IS NOT NULL
           AND NOT c.stale
        RETURNING c.external_id,
                  c.position
    """

    params = {
        "conversation_id": conversation_row_id,
        "position": position,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    ordered = sorted(rows, key=lambda row: row["position"])

    marked = []
    for row in ordered:
        marked.append(str(row["external_id"]))

    return marked


async def shown(conn: AsyncConnection[Any], cell_id: UUID) -> dict[str, Any]:
    # describe_cell reads the cell by its id; the position is not consulted.
    return await describe_cell(conn, CellRef(id=cell_id, position=0))


@dataclass(frozen=True)
class StartedRun:
    run_row_id: int
    run_id: UUID
    conversation_row_id: int


async def start_run(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    kind: str,
) -> StartedRun:
    """A run that executes code but asks no model: a cell, or Run all. Refused by
    the one-running-run index when another is in progress."""
    sql = """
        INSERT INTO runs AS r (conversation_id, kind)
        VALUES (%(conversation_id)s, %(kind)s)
        RETURNING r.id,
                  r.external_id
    """

    params: dict[str, Any] = {
        "conversation_id": conversation_row_id,
        "kind": kind,
    }

    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
    except errors.UniqueViolation as exc:
        raise ConversationBusy from exc

    assert row is not None  # RETURNING on a successful INSERT

    return StartedRun(
        run_row_id=row["id"],
        run_id=row["external_id"],
        conversation_row_id=conversation_row_id,
    )


@dataclass(frozen=True)
class OwnedConversation:
    row_id: int
    busy: bool


async def find_conversation(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
) -> OwnedConversation:
    sql = """
        SELECT v.id,
               EXISTS (
                   SELECT 1
                     FROM runs r
                    WHERE r.conversation_id = v.id
                      AND r.status = 'running'
               ) AS busy
          FROM conversations v
          JOIN users u
            ON u.id = v.user_id
         WHERE u.external_id = %(user_id)s
           AND v.external_id = %(conversation_id)s
    """

    params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        raise ConversationNotFound

    return OwnedConversation(row_id=row["id"], busy=row["busy"])


async def cells_in_order(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
) -> list[tuple[CellRef, str]]:
    """Every cell and its source, top to bottom — what Run all runs."""
    sql = """
        SELECT c.external_id,
               c.position,
               c.source
          FROM cells c
         WHERE c.conversation_id = %(conversation_id)s
         ORDER BY c.position
    """

    params = {"conversation_id": conversation_row_id}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    cells = []
    for row in rows:
        ref = CellRef(id=row["external_id"], position=row["position"])
        cells.append((ref, row["source"]))

    return cells
