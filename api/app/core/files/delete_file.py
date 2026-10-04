"""Removing a file from a conversation, and from disk.

Cells that read it keep their code and outputs, and will fail the next time they
run. Refused while a run is in progress: that run may be reading it.
"""

from __future__ import annotations

from typing import Any, NoReturn
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.errors import ConversationBusy, ConversationNotFound, FileNotFound
from app.domain.files import FileStore


async def delete_file(
    conn: AsyncConnection[Any],
    store: FileStore,
    user_id: UUID,
    conversation_id: UUID,
    file_id: UUID,
) -> None:
    sql = """
        DELETE FROM files f
         USING conversations c,
               users u
         WHERE c.id = f.conversation_id
           AND u.id = c.user_id
           AND u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
           AND f.external_id = %(file_id)s
           AND NOT EXISTS (
                   SELECT 1
                     FROM runs r
                    WHERE r.conversation_id = c.id
                      AND r.status = 'running'
               )
        RETURNING f.storage_key
    """

    params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "file_id": file_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        await explain_nothing_deleted(conn, user_id, conversation_id, file_id)

    await store.delete(row["storage_key"])


async def explain_nothing_deleted(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
    file_id: UUID,
) -> NoReturn:
    """Zero rows has three readings; the outermost wrong thing is the answer."""
    sql = """
        SELECT EXISTS (
                   SELECT 1
                     FROM files f
                    WHERE f.conversation_id = c.id
                      AND f.external_id = %(file_id)s
               ) AS file_exists,
               EXISTS (
                   SELECT 1
                     FROM runs r
                    WHERE r.conversation_id = c.id
                      AND r.status = 'running'
               ) AS busy
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
         WHERE u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
    """

    params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "file_id": file_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        found = await cur.fetchone()

    if found is None:
        raise ConversationNotFound

    if not found["file_exists"]:
        raise FileNotFound

    raise ConversationBusy
