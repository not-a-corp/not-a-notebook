"""Shared route dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from psycopg import AsyncConnection


async def db(request: Request) -> AsyncIterator[AsyncConnection[Any]]:
    """A connection from the pool, returned to it when the request is done.

    It commits as it goes (see `create_pool`); this dependency does not own the
    commit, because its teardown runs after the response has been sent.
    """
    async with request.app.state.pool.connection() as conn:
        yield conn


Db = Annotated[AsyncConnection[Any], Depends(db)]
