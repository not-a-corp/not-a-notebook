"""Opening a session: the refresh token and the access token that come with it.

A session dies at whichever comes first: thirty days without a refresh, or ninety
days from sign-in. The first deadline is pushed forward by every refresh; the
second never moves.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.auth import SignedIn
from app.security.access_tokens import issue_access_token
from app.security.refresh_tokens import new_refresh_token, refresh_token_digest

SLIDING_LIFETIME = timedelta(days=30)
ABSOLUTE_LIFETIME = timedelta(days=90)


async def open_session(
    conn: AsyncConnection[Any],
    user_id: int,
    external_id: UUID,
    jwt_secret: str,
) -> SignedIn:
    """Both ids, because the session row points at the internal one and the
    access token may only ever carry the external one."""
    sql = """
        INSERT INTO sessions AS s (token_hash, user_id, expires_at, absolute_expires_at)
        VALUES (%(token_hash)s, %(user_id)s, now() + %(sliding)s, now() + %(absolute)s)
        RETURNING s.expires_at
    """

    refresh_token = new_refresh_token()
    params: dict[str, Any] = {
        "token_hash": refresh_token_digest(refresh_token),
        "user_id": user_id,
        "sliding": SLIDING_LIFETIME,
        "absolute": ABSOLUTE_LIFETIME,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    assert row is not None  # RETURNING on a successful INSERT

    now = datetime.now(UTC)
    access = issue_access_token(external_id, jwt_secret, now)

    return SignedIn(
        access=access,
        refresh_token=refresh_token,
        refresh_expires_at=row["expires_at"],
    )
