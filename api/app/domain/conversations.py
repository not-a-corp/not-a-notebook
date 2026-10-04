"""The shapes of a conversation, as api.md defines them."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.files import FileInfo
from app.domain.messages import Message

# The conversations.title column.
MAX_TITLE_LENGTH = 200

# The column's own default. Repeated here because an INSERT cannot ask for a
# column's default through a parameter.
DEFAULT_TITLE = "Untitled"

MAX_PER_PAGE = 200
DEFAULT_PER_PAGE = 50


class CreateConversationRequest(BaseModel):
    title: str = Field(default=DEFAULT_TITLE, min_length=1, max_length=MAX_TITLE_LENGTH)
    model_id: UUID | None = None


class UpdateConversationRequest(BaseModel):
    """Only the fields sent change. `model_id: null` takes the model away; a
    title cannot be taken away, only replaced."""

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    model_id: UUID | None = None

    @model_validator(mode="after")
    def title_is_never_null(self) -> Self:
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")

        return self


type KernelState = Literal["running", "stopped"]


class Conversation(BaseModel):
    id: UUID
    title: str
    model_id: UUID | None
    kernel: KernelState
    created_at: datetime
    updated_at: datetime


class PageMeta(BaseModel):
    page: int
    per_page: int
    total: int
    pages: int


class ConversationPage(BaseModel):
    data: list[Conversation]
    meta: PageMeta


class ConversationDetail(BaseModel):
    """Everything the conversation screen needs, in one call (decision 19)."""

    id: UUID
    title: str
    model_id: UUID | None
    kernel: KernelState
    active_run_id: UUID | None
    files: list[FileInfo]
    messages: list[Message]
    # api.md's cell, outputs flattened after their kind.
    cells: list[dict[str, Any]]
