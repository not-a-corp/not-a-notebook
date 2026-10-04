"""A cell you write: at the end, first, or right after another. It does not run.

Inserting in the middle moves every cell below it down one place; for a moment
two cells share a position, which the DEFERRABLE unique constraint allows until
the transaction ends (schema.sql).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.cells import cell_shape
from app.domain.errors import CellNotFound, ConversationNotFound


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
