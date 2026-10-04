"""Starting Run all: a fresh kernel, every cell in order — the reproducibility
button (decision 10). Refused while another run is in progress."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.conversations import find_conversation
from app.db.runs import StartedRun, start_run


async def start_run_all(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
) -> StartedRun:
    conversation = await find_conversation(conn, user_id, conversation_id)

    return await start_run(conn, conversation.row_id, "run_all")
