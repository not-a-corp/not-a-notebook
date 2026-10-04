"""Signing up, signing in, staying signed in, signing out."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.refresh_cookie import clear_refresh_cookie, set_refresh_cookie
from app.core.get_auth_options import get_auth_options
from app.core.login_user import login_user
from app.core.logout_user import logout_user
from app.core.refresh_session import refresh_session
from app.core.register_user import register_user
from app.dependencies import Config, Db, RefreshToken
from app.domain.auth import AccessToken, AuthOptions, LoginRequest, RegisterRequest, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/options")
async def options(conn: Db, settings: Config) -> AuthOptions:
    return await get_auth_options(conn, settings.registration_open)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, conn: Db, settings: Config) -> User:
    return await register_user(
        conn,
        email=payload.email,
        password=payload.password,
        registration_open=settings.registration_open,
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    conn: Db,
    settings: Config,
    response: Response,
) -> AccessToken:
    signed_in = await login_user(
        conn,
        email=payload.email,
        password=payload.password,
        jwt_secret=settings.jwt_secret,
    )

    set_refresh_cookie(response, signed_in.refresh_token, signed_in.refresh_expires_at)

    return signed_in.access


@router.post("/refresh")
async def refresh(
    token: RefreshToken,
    conn: Db,
    settings: Config,
    response: Response,
) -> AccessToken:
    signed_in = await refresh_session(conn, token, settings.jwt_secret)

    set_refresh_cookie(response, signed_in.refresh_token, signed_in.refresh_expires_at)

    return signed_in.access


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(token: RefreshToken, conn: Db) -> Response:
    await logout_user(conn, token)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)

    return response
