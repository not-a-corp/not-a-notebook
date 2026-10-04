"""What the sign-in screen should offer."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from app.domain.auth import AuthOptions


async def get_auth_options(conn: AsyncConnection[Any], registration_open: bool) -> AuthOptions:
    # A closed instance with no accounts yet still lets the first one in, so the
    # screen has to offer it.
    sql = """
        SELECT NOT EXISTS (
                   SELECT 1
                     FROM users u
               ) AS empty
    """

    async with conn.cursor() as cur:
        await cur.execute(sql)
        row = await cur.fetchone()

    assert row is not None  # a SELECT with no FROM always returns its one row

    can_register = registration_open or row["empty"]

    # No OAuth provider is wired in yet.
    return AuthOptions(registration_open=can_register, oauth=[])
