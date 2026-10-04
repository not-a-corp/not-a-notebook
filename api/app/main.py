"""FastAPI application entrypoint.

Owns the lifespan: the PostgreSQL pool opens on startup and closes on shutdown.
Mounts the routers under /api/v1 and maps every failure to the one envelope:

    {"error": {"code": "CONVERSATION_NOT_FOUND", "message": "No such conversation."}}

``code`` is the contract and its text never changes; ``message`` is for humans.
Nothing else may reach the client: an unhandled exception becomes a generic
INTERNAL_ERROR with a ``request_id``, and the traceback goes to the log under that
id, never into the response.

Migrations are *not* run here. ``alembic upgrade head`` is a separate command, so
two instances starting at once cannot race each other through the same revisions.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import health
from app.config import get_settings
from app.db.pool import create_pool
from app.domain.errors import DomainError

API_PREFIX = "/api/v1"

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

    await pool.open(wait=True)

    app.state.pool = pool
    try:
        yield
    finally:
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
app.include_router(health.router, prefix=API_PREFIX)
