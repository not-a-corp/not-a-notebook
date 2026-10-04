"""Inserting a user, under the registration rule. Shared by the password and the
OAuth sign-ups, so the rule lives in one place.

With registration closed, the door still opens for the first account, so a
self-hoster can close it from the first boot and still get in. "The first" is a
count of zero that two requests could both see at once; the advisory lock makes
them take turns, so exactly one of them finds the instance empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, errors

from app.domain.errors import EmailAlreadyRegistered, RegistrationClosed

# Any constant works, as long as nothing else in the application takes the same
# advisory lock for another purpose.
REGISTRATION_LOCK = 1


@dataclass(frozen=True)
class NewUser:
    id: int
    external_id: UUID
    email: str
    created_at: datetime


async def insert_user(
    conn: AsyncConnection[Any],
    email: str,
    password_hash: str | None,
    registration_open: bool,
) -> NewUser:
    """Must run inside `conn.transaction()`: the lock is held until it ends."""
    lock_sql = """
        SELECT pg_advisory_xact_lock(%(lock)s)
    """

    lock_params = {"lock": REGISTRATION_LOCK}

    await conn.execute(lock_sql, lock_params)

    # INSERT ... SELECT so that "closed, and someone already has an account"
    # inserts nothing: zero rows back is REGISTRATION_CLOSED. It is decided before
    # the email is compared, so a closed instance never says which emails exist.
    sql = """
        INSERT INTO users AS u (email, password_hash)
        SELECT %(email)s,
               %(password_hash)s
         WHERE %(registration_open)s
            OR NOT EXISTS (
                   SELECT 1
                     FROM users existing
               )
        RETURNING u.id,
                  u.external_id,
                  u.email,
                  u.created_at
    """

    params: dict[str, Any] = {
        "email": email,
        "password_hash": password_hash,
        "registration_open": registration_open,
    }

    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
    except errors.UniqueViolation as exc:
        raise EmailAlreadyRegistered from exc

    if row is None:
        raise RegistrationClosed

    return NewUser(
        id=row["id"],
        external_id=row["external_id"],
        email=row["email"],
        created_at=row["created_at"],
    )
