"""The models a user can pick, and the ones they configure themselves."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from app.core.create_model import create_model
from app.core.delete_model import delete_model
from app.core.list_models import list_models
from app.core.update_model import update_model
from app.dependencies import Caller, Crypto, Db, EnvironmentKeys
from app.domain.model_configs import (
    CreateModelRequest,
    ModelConfig,
    ModelList,
    UpdateModelRequest,
)

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_(caller: Caller, conn: Db, cipher: Crypto, keys: EnvironmentKeys) -> ModelList:
    return await list_models(conn, caller, cipher, keys)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    payload: CreateModelRequest,
    caller: Caller,
    conn: Db,
    cipher: Crypto,
    keys: EnvironmentKeys,
) -> ModelConfig:
    return await create_model(conn, caller, payload, cipher, keys)


@router.patch("/{model_id}")
async def update(
    model_id: UUID,
    payload: UpdateModelRequest,
    caller: Caller,
    conn: Db,
    cipher: Crypto,
    keys: EnvironmentKeys,
) -> ModelConfig:
    return await update_model(conn, caller, model_id, payload, cipher, keys)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(model_id: UUID, caller: Caller, conn: Db) -> Response:
    await delete_model(conn, caller, model_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
