"""Trading a refresh token for a new access token — and a new refresh token.

Rotation replaces token_hash in place, so the old token stops matching the
moment the new one exists. Two refreshes racing with the same token serialise on
the row lock: the second one finds the hash already replaced, and gets nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg import AsyncConnection

from app.core.sessions import SLIDING_LIFETIME
from app.domain.auth import SignedIn
from app.domain.errors import Unauthenticated
from app.security.access_tokens import issue_access_token
from app.security.refresh_tokens import new_refresh_token, refresh_token_digest


async def refresh_session(
    conn: AsyncConnection[Any],
    refresh_token: str,
    jwt_secret: str,
) -> SignedIn:
    # LEAST keeps the sliding deadline from overtaking the absolute one, which
    # the table's CHECK forbids: near the end of the ninety days a plain
    # now() + 30 days would fail the write.
    sql = """
        UPDATE sessions s
           SET token_hash = %(new_hash)s,
               expires_at = LEAST(now() + %(sliding)s, s.absolute_expires_at)
          FROM users u
         WHERE u.id = s.user_id
           AND s.token_hash = %(old_hash)s
           AND s.expires_at > now()
           AND s.absolute_expires_at > now()
        RETURNING u.external_id,
                  s.expires_at
    """

    new_token = new_refresh_token()
    params: dict[str, Any] = {
        "new_hash": refresh_token_digest(new_token),
        "old_hash": refresh_token_digest(refresh_token),
        "sliding": SLIDING_LIFETIME,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        raise Unauthenticated

    now = datetime.now(UTC)
    access = issue_access_token(row["external_id"], jwt_secret, now)

    return SignedIn(
        access=access,
        refresh_token=new_token,
        refresh_expires_at=row["expires_at"],
    )
