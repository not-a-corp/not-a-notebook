"""A conversation's cells, as the agent's runs write them and the screen reads them.

Cells are addressed by their external id here: the run that writes them was
started by the conversation's owner, who was checked then, and the screen reads
them through a conversation already scoped to its owner.

Outputs belong to the cell's last execution only (see schema.sql): every attempt
replaces them, in the same transaction that records how it ended.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.agent.outputs import fields_of, flattened, kind_of
from app.domain.agent import CellRef, CellStatus
from app.domain.runtime import Output


async def create_agent_cell(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    run_row_id: int,
    source: str,
) -> CellRef:
    # At the end. One run at a time per conversation, so nothing else is adding
    # an agent cell meanwhile.
    sql = """
        INSERT INTO cells AS c (conversation_id, run_id, position, origin, source, status,
                                attempts)
        SELECT %(conversation_id)s,
               %(run_id)s,
               coalesce(max(existing.position), 0) + 1,
               'agent',
               %(source)s,
               'running',
               1
          FROM cells existing
         WHERE existing.conversation_id = %(conversation_id)s
        RETURNING c.external_id,
                  c.position
    """

    params: dict[str, Any] = {
        "conversation_id": conversation_row_id,
        "run_id": run_row_id,
        "source": source,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    assert row is not None  # INSERT ... SELECT max() always yields one row

    return CellRef(id=row["external_id"], position=row["position"])


async def rewrite_cell(
    conn: AsyncConnection[Any], cell: CellRef, source: str, attempt: int
) -> None:
    update_sql = """
        UPDATE cells c
           SET source = %(source)s,
               attempts = %(attempts)s,
               status = 'running'
         WHERE c.external_id = %(cell_id)s
    """

    update_params: dict[str, Any] = {
        "source": source,
        "attempts": attempt,
        "cell_id": cell.id,
    }

    clear_sql = """
        DELETE FROM cell_outputs o
         USING cells c
         WHERE c.id = o.cell_id
           AND c.external_id = %(cell_id)s
    """

    clear_params = {"cell_id": cell.id}

    async with conn.transaction():
        await conn.execute(update_sql, update_params)
        await conn.execute(clear_sql, clear_params)


async def finish_attempt(
    conn: AsyncConnection[Any],
    cell: CellRef,
    outputs: Sequence[Output],
    status: CellStatus,
    execution_count: int | None,
    duration_ms: int,
) -> None:
    clear_sql = """
        DELETE FROM cell_outputs o
         USING cells c
         WHERE c.id = o.cell_id
           AND c.external_id = %(cell_id)s
    """

    clear_params = {"cell_id": cell.id}

    insert_sql = """
        INSERT INTO cell_outputs AS o (cell_id, ordinal, kind, payload)
        SELECT c.id,
               %(ordinal)s,
               %(kind)s,
               %(payload)s
          FROM cells c
         WHERE c.external_id = %(cell_id)s
    """

    update_sql = """
        UPDATE cells c
           SET status = %(status)s,
               execution_count = %(execution_count)s,
               executed_at = now(),
               duration_ms = %(duration_ms)s,
               stale = false
         WHERE c.external_id = %(cell_id)s
    """

    update_params: dict[str, Any] = {
        "status": status,
        "execution_count": execution_count,
        "duration_ms": duration_ms,
        "cell_id": cell.id,
    }

    async with conn.transaction():
        await conn.execute(clear_sql, clear_params)

        for ordinal, output in enumerate(outputs, start=1):
            insert_params: dict[str, Any] = {
                "cell_id": cell.id,
                "ordinal": ordinal,
                "kind": kind_of(output),
                "payload": Jsonb(fields_of(output)),
            }
            await conn.execute(insert_sql, insert_params)

        await conn.execute(update_sql, update_params)


async def conversation_cells(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
) -> list[dict[str, Any]]:
    """Every cell, in order, as GET /conversations/{id} shows it."""
    cells_sql = """
        SELECT c.id AS row_id,
               c.external_id AS id,
               c.position,
               c.origin,
               r.external_id AS run_id,
               c.source,
               c.status,
               c.stale,
               c.attempts,
               c.execution_count,
               c.executed_at,
               c.duration_ms
          FROM cells c
          LEFT JOIN runs r
            ON r.id = c.run_id
         WHERE c.conversation_id = %(conversation_id)s
         ORDER BY c.position
    """

    outputs_sql = """
        SELECT o.cell_id,
               o.kind,
               o.payload
          FROM cell_outputs o
          JOIN cells c
            ON c.id = o.cell_id
         WHERE c.conversation_id = %(conversation_id)s
         ORDER BY o.cell_id,
                  o.ordinal
    """

    params = {"conversation_id": conversation_row_id}

    async with conn.cursor() as cur:
        await cur.execute(cells_sql, params)
        rows = await cur.fetchall()

        await cur.execute(outputs_sql, params)
        output_rows = await cur.fetchall()

    outputs: dict[int, list[dict[str, Any]]] = {}
    for output in output_rows:
        shown = flattened(output["kind"], output["payload"])
        outputs.setdefault(output["cell_id"], []).append(shown)

    cells = []
    for row in rows:
        cell = cell_shape(row, outputs.get(row["row_id"], []))
        cells.append(cell)

    return cells


async def describe_cell(conn: AsyncConnection[Any], cell: CellRef) -> dict[str, Any]:
    sql = """
        SELECT c.id AS row_id,
               c.external_id AS id,
               c.position,
               c.origin,
               r.external_id AS run_id,
               c.source,
               c.status,
               c.stale,
               c.attempts,
               c.execution_count,
               c.executed_at,
               c.duration_ms
          FROM cells c
          LEFT JOIN runs r
            ON r.id = c.run_id
         WHERE c.external_id = %(cell_id)s
    """

    params = {"cell_id": cell.id}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    assert row is not None  # the run that asks just created it

    return cell_shape(row, [])


def cell_shape(row: dict[str, Any], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    """api.md's cell, JSON-ready: ids as strings, times as ISO-8601."""
    run_id = None
    if row["run_id"] is not None:
        run_id = str(row["run_id"])

    executed_at = None
    if row["executed_at"] is not None:
        executed_at = iso(row["executed_at"])

    return {
        "id": str(row["id"]),
        "position": row["position"],
        "origin": row["origin"],
        "run_id": run_id,
        "source": row["source"],
        "status": row["status"],
        "stale": row["stale"],
        "attempts": row["attempts"],
        "execution_count": row["execution_count"],
        "outputs": outputs,
        "executed_at": executed_at,
        "duration_ms": row["duration_ms"],
    }


def iso(moment: Any) -> str:
    """UTC, ending in Z — what api.md promises for every date."""
    text: str = moment.isoformat()

    return text.replace("+00:00", "Z")
