"""Shared route dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

import httpx2
from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import AsyncConnection

from app.config import Settings, get_settings
from app.domain.errors import Unauthenticated
from app.security.access_tokens import read_access_token

REFRESH_COOKIE = "nan_refresh"
OAUTH_COOKIE = "nan_oauth"

# auto_error=False so a missing header raises our Unauthenticated rather than
# FastAPI's own 403, which would leave through a different shape.
bearer = HTTPBearer(auto_error=False)


async def db(request: Request) -> AsyncIterator[AsyncConnection[Any]]:
    """A connection from the pool, returned to it when the request is done.

    It commits as it goes (see `create_pool`); this dependency does not own the
    commit, because its teardown runs after the response has been sent.
    """
    async with request.app.state.pool.connection() as conn:
        yield conn


Db = Annotated[AsyncConnection[Any], Depends(db)]

Config = Annotated[Settings, Depends(get_settings)]


async def http(request: Request) -> httpx2.AsyncClient:
    """The process-wide client for calls out, opened and closed by the lifespan."""
    client: httpx2.AsyncClient = request.app.state.http
    return client


Http = Annotated[httpx2.AsyncClient, Depends(http)]


async def caller(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    settings: Config,
) -> UUID:
    """The signed-in user's external id, read from the access token alone.

    No database lookup: the signature and the expiry are the whole check. The
    use cases take this UUID and join `users` on it, so whose rows they touch is
    still decided in the WHERE.
    """
    if credentials is None:
        raise Unauthenticated

    user_id = read_access_token(credentials.credentials, settings.jwt_secret)
    if user_id is None:
        raise Unauthenticated

    return user_id


Caller = Annotated[UUID, Depends(caller)]


async def refresh_token(
    token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> str:
    if token is None:
        raise Unauthenticated

    return token


RefreshToken = Annotated[str, Depends(refresh_token)]
