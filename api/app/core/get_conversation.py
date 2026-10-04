"""One conversation, with everything its screen shows."""

from __future__ import annotations

from collections.abc import Set
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.core.cells import conversation_cells
from app.core.conversation_row import kernel_state
from app.core.start_message_run import message_shape
from app.domain.conversations import ConversationDetail
from app.domain.errors import ConversationNotFound
from app.domain.files import FileInfo


async def get_conversation(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
    running: Set[UUID],
) -> ConversationDetail:
    # At most one run is 'running' per conversation — a unique index says so —
    # so the subquery returns one row or none.
    sql = """
        SELECT c.id AS row_id,
               c.external_id AS id,
               c.title,
               m.external_id AS model_id,
               (
                   SELECT r.external_id
                     FROM runs r
                    WHERE r.conversation_id = c.id
                      AND r.status = 'running'
               ) AS active_run_id
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
          LEFT JOIN models m
            ON m.id = c.model_id
         WHERE u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
    """

    params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }

    # Already scoped by the query above: these only run once it found the
    # conversation, and they ask by its internal id.
    files_sql = """
        SELECT f.external_id AS id,
               f.name,
               f.bytes,
               f.profile,
               f.created_at
          FROM files f
         WHERE f.conversation_id = %(conversation_row_id)s
         ORDER BY f.created_at,
                  f.id
    """

    messages_sql = """
        SELECT m.external_id AS id,
               m.role,
               r.external_id AS run_id,
               m.text,
               m.created_at
          FROM messages m
          LEFT JOIN runs r
            ON r.id = m.run_id
         WHERE m.conversation_id = %(conversation_row_id)s
         ORDER BY m.created_at,
                  m.id
    """

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

        if row is None:
            raise ConversationNotFound

        files_params = {"conversation_row_id": row["row_id"]}
        await cur.execute(files_sql, files_params)
        file_rows = await cur.fetchall()

        await cur.execute(messages_sql, files_params)
        message_rows = await cur.fetchall()

    cells = await conversation_cells(conn, row["row_id"])

    messages = []
    for message_row in message_rows:
        message = message_shape(
            message_row["id"],
            message_row["role"],
            message_row["run_id"],
            message_row["text"],
            message_row["created_at"],
        )
        messages.append(message)

    files = []
    for file_row in file_rows:
        file = FileInfo(
            id=file_row["id"],
            name=file_row["name"],
            bytes=file_row["bytes"],
            profile=file_row["profile"],
            created_at=file_row["created_at"],
        )
        files.append(file)

    return ConversationDetail(
        id=row["id"],
        title=row["title"],
        model_id=row["model_id"],
        kernel=kernel_state(row["id"], running),
        active_run_id=row["active_run_id"],
        files=files,
        messages=messages,
        cells=cells,
    )
