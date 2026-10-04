"""Everything a model turn reads about its conversation, read in one place: the
messages before this one, the files and their profiles, the cells as they are.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection

from app.agent.context import CellSummary, FileSummary, PastMessage
from app.agent.outputs import as_text, from_stored
from app.core.cells import conversation_cells


@dataclass(frozen=True)
class TurnContext:
    messages: list[PastMessage]
    files: list[FileSummary]
    cells: list[CellSummary]
    # Some cell has run before — so a kernel starting now is a restart, and the
    # model must be told its variables are gone.
    cells_have_run: bool


async def turn_context(
    conn: AsyncConnection[Any],
    conversation_row_id: int,
    run_row_id: int,
) -> TurnContext:
    # Messages of earlier runs only: this run's own user message is the question,
    # and goes last, after the briefing.
    messages_sql = """
        SELECT m.role,
               m.text
          FROM messages m
         WHERE m.conversation_id = %(conversation_id)s
           AND (m.run_id IS NULL OR m.run_id <> %(run_id)s)
         ORDER BY m.created_at,
                  m.id
    """

    files_sql = """
        SELECT f.name,
               f.bytes,
               f.profile
          FROM files f
         WHERE f.conversation_id = %(conversation_id)s
         ORDER BY f.created_at,
                  f.id
    """

    params = {
        "conversation_id": conversation_row_id,
        "run_id": run_row_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(messages_sql, params)
        message_rows = await cur.fetchall()

        await cur.execute(files_sql, params)
        file_rows = await cur.fetchall()

    cells = await conversation_cells(conn, conversation_row_id)

    messages = []
    for row in message_rows:
        messages.append(PastMessage(role=row["role"], text=row["text"]))

    files = []
    for row in file_rows:
        files.append(FileSummary(name=row["name"], bytes=row["bytes"], profile=row["profile"]))

    summaries = []
    cells_have_run = False
    for cell in cells:
        summaries.append(summary_of(cell))
        if cell["execution_count"] is not None:
            cells_have_run = True

    return TurnContext(
        messages=messages,
        files=files,
        cells=summaries,
        cells_have_run=cells_have_run,
    )


def summary_of(cell: dict[str, Any]) -> CellSummary:
    outputs = []
    for shown in cell["outputs"]:
        payload = {}
        for name, value in shown.items():
            if name != "kind":
                payload[name] = value
        outputs.append(from_stored(shown["kind"], payload))

    outputs_text = ""
    if outputs:
        outputs_text = as_text(outputs, None)

    return CellSummary(
        position=cell["position"],
        origin=cell["origin"],
        source=cell["source"],
        status=cell["status"],
        stale=cell["stale"],
        outputs_text=outputs_text,
    )
