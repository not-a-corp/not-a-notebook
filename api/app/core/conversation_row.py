"""A conversations row, as the API shows it."""

from __future__ import annotations

from typing import Any

from app.domain.conversations import Conversation, KernelState


def kernel_state() -> KernelState:
    # Whether a kernel runs is not stored (see schema.sql): it lives in the
    # runtime. Nothing in the API starts a kernel yet, so the answer is always
    # "stopped" — until the kernel registry arrives with runs.
    return "stopped"


def to_conversation(row: dict[str, Any]) -> Conversation:
    return Conversation(
        id=row["id"],
        title=row["title"],
        model_id=row["model_id"],
        kernel=kernel_state(),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
