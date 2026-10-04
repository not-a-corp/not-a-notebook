"""The models a user can pick, and the ones they configure themselves."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from app.core.models.check_model import check_model
from app.core.models.create_model import create_model
from app.core.models.delete_model import delete_model
from app.core.models.list_models import list_models
from app.core.models.resolve_model import resolve_endpoint
from app.core.models.update_model import update_model
from app.dependencies import Caller, Crypto, Db, EnvironmentKeys, Http
from app.domain.model_configs import (
    CreateModelRequest,
    ModelConfig,
    ModelList,
    ModelTestResult,
    UpdateModelRequest,
)
from app.providers.factory import model_for

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


@router.post("/{model_id}/test")
async def test(
    model_id: UUID,
    caller: Caller,
    conn: Db,
    cipher: Crypto,
    keys: EnvironmentKeys,
    http: Http,
) -> ModelTestResult:
    endpoint = await resolve_endpoint(conn, caller, model_id, cipher, keys)
    model = model_for(endpoint, http)

    checked = await check_model(model, endpoint.dialect)

    return ModelTestResult(ok=checked.ok, latency_ms=checked.latency_ms, error=checked.error)
