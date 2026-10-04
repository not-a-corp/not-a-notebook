"""Creating an account.

The password is hashed here and never stored, not even encrypted: nothing in the
system needs to read it back.

With registration closed, the door still opens for the first account, so a
self-hoster can close it from the first boot and still get in. "The first" is a
count of zero that two requests could both see at once; the advisory lock makes
them take turns, so exactly one of them finds the instance empty.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection, errors

from app.domain.auth import User
from app.domain.errors import EmailAlreadyRegistered, RegistrationClosed
from app.security.passwords import hash_password

# Any constant works, as long as nothing else in the application takes the same
# advisory lock for another purpose.
REGISTRATION_LOCK = 1


async def register_user(
    conn: AsyncConnection[Any],
    email: str,
    password: str,
    registration_open: bool,
) -> User:
    lock_sql = """
        SELECT pg_advisory_xact_lock(%(lock)s)
    """

    lock_params = {"lock": REGISTRATION_LOCK}

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
        RETURNING u.external_id AS id,
                  u.email,
                  u.created_at
    """

    params: dict[str, Any] = {
        "email": email,
        "password_hash": hash_password(password),
        "registration_open": registration_open,
    }

    try:
        async with conn.transaction():
            await conn.execute(lock_sql, lock_params)

            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
    except errors.UniqueViolation as exc:
        raise EmailAlreadyRegistered from exc

    if row is None:
        raise RegistrationClosed

    return User(
        id=row["id"],
        email=row["email"],
        created_at=row["created_at"],
    )
