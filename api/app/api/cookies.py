"""The two cookies this API sets, each set and cleared the same way everywhere.

Both are HttpOnly, so page scripts never see them, and Secure, so they never
cross plain HTTP. Each is scoped to the only path that reads it.

**`nan_refresh`** is SameSite=Strict: no other site can make the browser send it.

**`nan_oauth`** holds a sign-in in flight, and is SameSite=Lax because the
provider sends the browser back with a cross-site redirect — a Strict cookie
would not come along, and every callback would fail.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

from app.dependencies import OAUTH_COOKIE, REFRESH_COOKIE
from app.oauth.pending import PENDING_LIFETIME

REFRESH_COOKIE_PATH = "/api/v1/auth"
OAUTH_COOKIE_PATH = "/api/v1/auth/oauth"


def set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        expires=expires_at,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def set_oauth_cookie(response: Response, pending: str) -> None:
    max_age = int(PENDING_LIFETIME.total_seconds())

    response.set_cookie(
        key=OAUTH_COOKIE,
        value=pending,
        max_age=max_age,
        path=OAUTH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_oauth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=OAUTH_COOKIE,
        path=OAUTH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )
