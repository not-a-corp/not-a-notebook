"""FastAPI application entrypoint.

Owns the lifespan: the PostgreSQL pool opens on startup and closes on shutdown.
Mounts the routers under /api/v1 and maps every failure to the one envelope:

    {"error": {"code": "CONVERSATION_NOT_FOUND", "message": "No such conversation."}}

``code`` is the contract and its text never changes; ``message`` is for humans.
Nothing else may reach the client: an unhandled exception becomes a generic
INTERNAL_ERROR with a ``request_id``, and the traceback goes to the log under that
id, never into the response.

Owns the kernels' lifecycle at the edges too: orphans are reaped on startup and
this API's own kernels on shutdown.

Migrations are *not* run here. ``alembic upgrade head`` is a separate command, so
two instances starting at once cannot race each other through the same revisions.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    account,
    auth,
    cells,
    conversations,
    files,
    health,
    messages,
    models,
    oauth,
    runs,
)
from app.config import get_settings
from app.core.close_abandoned_runs import close_abandoned_runs
from app.core.sync_environment_models import sync_environment_models
from app.db.pool import create_pool
from app.domain.errors import DomainError
from app.runs.background import Background
from app.runs.broadcast import Broadcast
from app.runs.control import RunControls
from app.runtime.docker_engine import DockerEngine
from app.runtime.docker_runtime import DockerRuntime, SandboxLimits
from app.runtime.reaper import reap_orphans, reap_own
from app.runtime.registry import KernelRegistry, reap_idle_forever
from app.security.secrets import Cipher, decode_key
from app.storage.local import LocalFileStore

API_PREFIX = "/api/v1"
OUTBOUND_TIMEOUT_SECONDS = 10.0

log = logging.getLogger(__name__)

# Failures raised by the framework before a route is reached.
TRANSPORT_CODES = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = create_pool(settings.database_url)

    # One client for every call out (OAuth providers today), so connections to
    # the same host are reused. The timeout is short: a browser is waiting on
    # the other end of the callback.
    http = httpx2.AsyncClient(timeout=OUTBOUND_TIMEOUT_SECONDS)

    await pool.open(wait=True)

    # Kernels left by a previous run of this API, or by one that died, are found
    # and removed before anything new starts (decision 3) — and so are the runs
    # that were executing in it.
    docker = DockerEngine.over_socket()
    await reap_orphans(docker, settings.api_container)

    async with pool.connection() as conn:
        await close_abandoned_runs(conn)
        await sync_environment_models(conn, settings.environment_models())

    limits = SandboxLimits(
        image=settings.sandbox_image,
        container_runtime=settings.sandbox_runtime,
        memory_mb=settings.kernel_memory_mb,
        cpus=settings.kernel_cpus,
        pids=settings.kernel_pids,
        execution_timeout_seconds=settings.execution_timeout_seconds,
    )
    runtime = DockerRuntime(docker, limits, settings.api_container, settings.files_volume)
    kernels = KernelRegistry(runtime)
    background = Background()

    app.state.pool = pool
    app.state.http = http
    app.state.docker = docker
    app.state.store = LocalFileStore(settings.files_root)
    app.state.kernels = kernels
    app.state.background = background
    app.state.broadcast = Broadcast()
    app.state.controls = RunControls()

    idle_reaper = asyncio.create_task(reap_idle_forever(kernels, settings.kernel_idle_minutes * 60))
    app.state.cipher = Cipher(decode_key(settings.secrets_key))
    try:
        yield
    finally:
        idle_reaper.cancel()
        await background.cancel_all()
        await kernels.stop_all()
        await reap_own(docker, settings.api_container)
        await docker.close()
        await http.aclose()
        await pool.close()


def envelope(status: int, code: str, message: str) -> JSONResponse:
    error = {"code": code, "message": message}
    content = {"error": error}

    return JSONResponse(status_code=status, content=content)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return envelope(exc.status, exc.code, exc.message)

    # Pydantic's own report quotes the rejected input back, and that input can be
    # a password. The caller gets the code and nothing about what was in the body.
    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return envelope(422, "VALIDATION_ERROR", "The request is missing or malformed.")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = TRANSPORT_CODES.get(exc.status_code, "INTERNAL_ERROR")

        return envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = str(uuid.uuid4())

        details = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
        log.exception("unhandled error %(request_id)s on %(method)s %(path)s", details)

        error = {
            "code": "INTERNAL_ERROR",
            "message": "Something went wrong.",
            "request_id": request_id,
        }
        content = {"error": error}

        return JSONResponse(status_code=500, content=content)


app = FastAPI(
    title="not-a-notebook",
    description="A self-hosted AI data analyst that shows its work.",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

register_error_handlers(app)
app.include_router(account.router, prefix=API_PREFIX)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(cells.router, prefix=API_PREFIX)
app.include_router(conversations.router, prefix=API_PREFIX)
app.include_router(files.router, prefix=API_PREFIX)
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(messages.router, prefix=API_PREFIX)
app.include_router(models.router, prefix=API_PREFIX)
app.include_router(oauth.router, prefix=API_PREFIX)
app.include_router(runs.router, prefix=API_PREFIX)
