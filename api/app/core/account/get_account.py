"""The signed-in user's own account."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.auth import Account
from app.domain.errors import Unauthenticated


async def get_account(conn: AsyncConnection[Any], user_id: UUID) -> Account:
    sql = """
        SELECT u.external_id AS id,
               u.email,
               u.password_hash IS NOT NULL AS has_password,
               ARRAY(
                   SELECT o.provider
                     FROM oauth_accounts o
                    WHERE o.user_id = u.id
                    ORDER BY o.provider
               ) AS oauth,
               u.created_at
          FROM users u
         WHERE u.external_id = %(user_id)s
    """

    params = {"user_id": user_id}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    # A valid token for an account that no longer exists.
    if row is None:
        raise Unauthenticated

    return Account(
        id=row["id"],
        email=row["email"],
        has_password=row["has_password"],
        oauth=row["oauth"],
        created_at=row["created_at"],
    )
