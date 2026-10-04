"""Deleting a conversation. There is no trash.

Its runs, events, messages, cells and file rows go with it, by ON DELETE CASCADE;
its kernel is shut down and its folder removed from disk. Cancelling a run in
progress arrives with the agent's runs — the profiling run left behind finds its
rows gone and its kernel stopped, and ends there.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.errors import ConversationNotFound
from app.domain.files import FileStore, conversation_folder
from app.runtime.registry import KernelRegistry


async def delete_conversation(
    conn: AsyncConnection[Any],
    store: FileStore,
    kernels: KernelRegistry,
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    sql = """
        DELETE FROM conversations c
         USING users u
         WHERE u.id = c.user_id
           AND u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
        RETURNING c.id
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

    await kernels.stop(conversation_id)

    folder = conversation_folder(user_id, conversation_id)
    await store.delete_folder(folder)
