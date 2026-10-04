"""Creating an account with a password.

The password is hashed here and never stored, not even encrypted: nothing in the
system needs to read it back.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from app.core.new_user import insert_user
from app.domain.auth import User
from app.security.passwords import hash_password


async def register_user(
    conn: AsyncConnection[Any],
    email: str,
    password: str,
    registration_open: bool,
) -> User:
    # Hashed before the transaction, so the registration lock is never held
    # through the slow part.
    password_hash = hash_password(password)

    async with conn.transaction():
        user = await insert_user(conn, email, password_hash, registration_open)

    return User(
        id=user.external_id,
        email=user.email,
        created_at=user.created_at,
    )
