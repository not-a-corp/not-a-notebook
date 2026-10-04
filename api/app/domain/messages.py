"""A conversation's messages, as api.md shows them."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Long enough for a pasted table or a detailed brief; short enough that a message
# is a message.
MAX_TEXT_LENGTH = 20_000


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


class Message(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    # The run the message started (the user's) or came out of (the assistant's).
    run_id: UUID | None
    text: str
    created_at: datetime


class MessageAccepted(BaseModel):
    message: Message
    run_id: UUID
