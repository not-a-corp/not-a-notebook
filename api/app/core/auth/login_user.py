"""Signing in with email and password."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from app.db.sessions import open_session
from app.domain.auth import SignedIn
from app.domain.errors import InvalidCredentials
from app.security.passwords import verify_password, waste_time


async def login_user(
    conn: AsyncConnection[Any],
    email: str,
    password: str,
    jwt_secret: str,
) -> SignedIn:
    sql = """
        SELECT u.id,
               u.external_id,
               u.password_hash
          FROM users u
         WHERE lower(u.email) = lower(%(email)s)
    """

    params = {"email": email}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    # No account still costs a verification. Without this, the response time
    # tells a stranger which emails are registered — the same thing separate
    # error codes would tell them.
    if row is None:
        waste_time()
        raise InvalidCredentials

    # An account made through OAuth has no password until one is set. From the
    # outside it is one more wrong password, and it costs the same time.
    stored_hash = row["password_hash"]
    if stored_hash is None:
        waste_time()
        raise InvalidCredentials

    if not verify_password(password, stored_hash):
        raise InvalidCredentials

    return await open_session(conn, row["id"], row["external_id"], jwt_secret)
