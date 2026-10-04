"""A conversations row, as the API shows it."""

from __future__ import annotations

from collections.abc import Set
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.conversations import Conversation, KernelState
from app.domain.errors import ConversationNotFound


def kernel_state(conversation_id: UUID, running: Set[UUID]) -> KernelState:
    # Whether a kernel runs is not stored (see schema.sql): the kernel registry
    # knows, and the route hands its answer down as `running`.
    if conversation_id in running:
        return "running"

    return "stopped"


def to_conversation(row: dict[str, Any], running: Set[UUID]) -> Conversation:
    return Conversation(
        id=row["id"],
        title=row["title"],
        model_id=row["model_id"],
        kernel=kernel_state(row["id"], running),
        active_run_id=row["active_run_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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
