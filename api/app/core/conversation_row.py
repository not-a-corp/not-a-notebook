"""A conversations row, as the API shows it."""

from __future__ import annotations

from collections.abc import Set
from typing import Any
from uuid import UUID

from app.domain.conversations import Conversation, KernelState


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
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
