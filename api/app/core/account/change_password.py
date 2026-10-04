"""Setting or changing the account password.

The current password is required even though the caller holds a valid token:
without it, a stolen token turns into a stolen account. An account made through
OAuth has no current password, and this is how it gets its first one.

Every session is dropped, the caller's included. Changing the password is what
someone does when they suspect a stranger is inside, and leaving the other
devices signed in would empty the gesture.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.errors import InvalidCredentials, Unauthenticated
from app.security.passwords import hash_password, verify_password


async def change_password(
    conn: AsyncConnection[Any],
    user_id: UUID,
    current_password: str | None,
    new_password: str,
) -> None:
    sql = """
        SELECT u.id,
               u.password_hash
          FROM users u
         WHERE u.external_id = %(user_id)s
    """

    params: dict[str, Any] = {"user_id": user_id}

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    # A valid token for an account that no longer exists.
    if row is None:
        raise Unauthenticated

    stored_hash = row["password_hash"]
    if stored_hash is not None:
        check_current_password(current_password, stored_hash)

    update_sql = """
        UPDATE users u
           SET password_hash = %(password_hash)s
         WHERE u.id = %(id)s
    """

    update_params: dict[str, Any] = {
        "password_hash": hash_password(new_password),
        "id": row["id"],
    }

    delete_sql = """
        DELETE FROM sessions s
         WHERE s.user_id = %(id)s
    """

    delete_params = {"id": row["id"]}

    # The two writes are one gesture. The connection is in autocommit, so
    # without this the new password could stand while the sessions it was meant
    # to end stayed open — the exact opposite of the point.
    async with conn.transaction():
        await conn.execute(update_sql, update_params)
        await conn.execute(delete_sql, delete_params)


def check_current_password(current_password: str | None, stored_hash: str) -> None:
    if current_password is None:
        raise InvalidCredentials

    if not verify_password(current_password, stored_hash):
        raise InvalidCredentials
