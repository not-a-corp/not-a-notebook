"""The caller's conversations."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.create_conversation import create_conversation
from app.core.delete_conversation import delete_conversation
from app.core.get_conversation import get_conversation
from app.core.list_conversations import list_conversations
from app.core.update_conversation import update_conversation
from app.dependencies import Caller, Db, Kernels, Store
from app.domain.conversations import (
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
    MAX_TITLE_LENGTH,
    Conversation,
    ConversationDetail,
    ConversationPage,
    CreateConversationRequest,
    UpdateConversationRequest,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_(
    caller: Caller,
    conn: Db,
    kernels: Kernels,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = DEFAULT_PER_PAGE,
    q: Annotated[str | None, Query(min_length=1, max_length=MAX_TITLE_LENGTH)] = None,
) -> ConversationPage:
    return await list_conversations(
        conn,
        caller,
        page=page,
        per_page=per_page,
        query=q,
        running=kernels.running(),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(payload: CreateConversationRequest, caller: Caller, conn: Db) -> Conversation:
    return await create_conversation(conn, caller, payload)


@router.get("/{conversation_id}")
async def get(
    conversation_id: UUID,
    caller: Caller,
    conn: Db,
    kernels: Kernels,
) -> ConversationDetail:
    return await get_conversation(conn, caller, conversation_id, running=kernels.running())


@router.patch("/{conversation_id}")
async def update(
    conversation_id: UUID,
    payload: UpdateConversationRequest,
    caller: Caller,
    conn: Db,
    kernels: Kernels,
) -> Conversation:
    return await update_conversation(
        conn,
        caller,
        conversation_id,
        payload,
        running=kernels.running(),
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    conversation_id: UUID,
    caller: Caller,
    conn: Db,
    store: Store,
    kernels: Kernels,
) -> Response:
    await delete_conversation(conn, store, kernels, caller, conversation_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
