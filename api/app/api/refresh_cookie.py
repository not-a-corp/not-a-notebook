"""The refresh token's cookie, set and cleared the same way everywhere.

HttpOnly so page scripts never see it, Secure so it never crosses plain HTTP,
SameSite=Strict so no other site can make the browser send it, and scoped to
/api/v1/auth so the only requests that carry it are the ones that need it.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

from app.dependencies import REFRESH_COOKIE

COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        expires=expires_at,
        path=COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
