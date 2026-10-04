"""A run, as the API shows it."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class RunView(BaseModel):
    """GET /runs/{id}, as api.md shows it."""

    id: UUID
    conversation_id: UUID
    kind: Literal["message", "profile", "cell", "run_all"]
    status: Literal["running", "awaiting_user", "succeeded", "failed", "cancelled", "timed_out"]
    # The model's name when the run started — the record outlives the model's
    # configuration.
    model: str | None
    tokens_in: int
    tokens_out: int
    tokens_reasoning: int
    started_at: datetime
    finished_at: datetime | None
    wall_ms: int | None
