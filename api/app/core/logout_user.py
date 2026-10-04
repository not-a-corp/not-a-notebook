"""Signing out: the session behind the refresh token stops existing."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from app.domain.errors import Unauthenticated
from app.security.refresh_tokens import refresh_token_digest


async def logout_user(conn: AsyncConnection[Any], refresh_token: str) -> None:
    sql = """
        DELETE FROM sessions s
         WHERE s.token_hash = %(token_hash)s
        RETURNING s.id
    """

    params = {"token_hash": refresh_token_digest(refresh_token)}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        raise Unauthenticated
