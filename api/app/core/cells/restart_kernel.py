"""Throwing the kernel's state away without running anything. The next run starts
a fresh kernel and tells the model the state is gone — `kernel.restarted`,
reason `requested`."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db.conversations import find_conversation
from app.domain.errors import ConversationBusy
from app.runtime.registry import KernelRegistry


async def restart_kernel(
    conn: AsyncConnection[Any],
    kernels: KernelRegistry,
    user_id: UUID,
    conversation_id: UUID,
) -> None:
    conversation = await find_conversation(conn, user_id, conversation_id)

    # A run is using the kernel; it has to be cancelled first.
    if conversation.busy:
        raise ConversationBusy

    await kernels.stop(conversation_id, reason="requested")
