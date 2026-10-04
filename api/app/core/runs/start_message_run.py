"""A user's message: stored, and the run that answers it started.

The run is an INSERT that the one-running-run index can refuse — CONVERSATION_BUSY
with no SELECT first. It copies the model's name, so the record keeps saying who
answered after the model is edited or deleted. A conversation with no model is
NO_MODEL_SELECTED: nothing would answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, errors

from app.db.messages import message_shape
from app.domain.errors import ConversationBusy, ConversationNotFound, NoModelSelected
from app.domain.messages import Message


@dataclass(frozen=True)
class MessageRun:
    run_row_id: int
    run_id: UUID
    conversation_row_id: int
    model_id: UUID
    model_name: str
    message: Message


async def start_message_run(
    conn: AsyncConnection[Any],
    user_id: UUID,
    conversation_id: UUID,
    text: str,
) -> MessageRun:
    conversation_sql = """
        SELECT c.id,
               m.id AS model_row_id,
               m.external_id AS model_id,
               m.model AS model_name
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
          LEFT JOIN models m
            ON m.id = c.model_id
         WHERE u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
    """

    conversation_params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }

    run_sql = """
        INSERT INTO runs AS r (conversation_id, kind, model_id, model_name)
        VALUES (%(conversation_id)s, 'message', %(model_row_id)s, %(model_name)s)
        RETURNING r.id,
                  r.external_id
    """

    message_sql = """
        INSERT INTO messages AS m (conversation_id, run_id, role, text)
        VALUES (%(conversation_id)s, %(run_id)s, 'user', %(text)s)
        RETURNING m.external_id,
                  m.created_at
    """

    touch_sql = """
        UPDATE conversations c
           SET updated_at = now()
         WHERE c.id = %(conversation_id)s
    """

    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(conversation_sql, conversation_params)
        conversation = await cur.fetchone()

        if conversation is None:
            raise ConversationNotFound

        if conversation["model_row_id"] is None:
            raise NoModelSelected

        run_params: dict[str, Any] = {
            "conversation_id": conversation["id"],
            "model_row_id": conversation["model_row_id"],
            "model_name": conversation["model_name"],
        }

        try:
            await cur.execute(run_sql, run_params)
        except errors.UniqueViolation as exc:
            raise ConversationBusy from exc

        run = await cur.fetchone()
        assert run is not None  # RETURNING on a successful INSERT

        message_params: dict[str, Any] = {
            "conversation_id": conversation["id"],
            "run_id": run["id"],
            "text": text,
        }
        await cur.execute(message_sql, message_params)
        stored = await cur.fetchone()
        assert stored is not None

        touch_params = {"conversation_id": conversation["id"]}
        await cur.execute(touch_sql, touch_params)

    message = message_shape(
        stored["external_id"], "user", run["external_id"], text, stored["created_at"]
    )

    return MessageRun(
        run_row_id=run["id"],
        run_id=run["external_id"],
        conversation_row_id=conversation["id"],
        model_id=conversation["model_id"],
        model_name=conversation["model_name"],
        message=message,
    )
