"""The signed-in user's own account."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.refresh_cookie import clear_refresh_cookie
from app.core.change_password import change_password
from app.core.get_account import get_account
from app.dependencies import Caller, Db
from app.domain.auth import Account, ChangePasswordRequest

router = APIRouter(prefix="/account", tags=["account"])


@router.get("")
async def account(caller: Caller, conn: Db) -> Account:
    return await get_account(conn, caller)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_password(payload: ChangePasswordRequest, caller: Caller, conn: Db) -> Response:
    await change_password(
        conn,
        user_id=caller,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )

    # Every session just ended, this one included; the cookie that pointed at it
    # is dead weight in the browser.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)

    return response
