"""Signing in through Google or GitHub.

Both routes are browser navigations, not fetches. The callback never answers
with JSON — there is no client on the other end to read it — so its failures
leave as a redirect to the login page carrying the error code.
"""

from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie
from fastapi.responses import RedirectResponse

from app.api.cookies import clear_oauth_cookie, set_oauth_cookie, set_refresh_cookie
from app.core.finish_oauth import finish_oauth
from app.core.start_oauth import start_oauth
from app.dependencies import OAUTH_COOKIE, Config, Db, Http
from app.domain.errors import DomainError

router = APIRouter(prefix="/auth/oauth", tags=["auth"])

log = logging.getLogger(__name__)


@router.get("/{provider}/start")
async def oauth_start(provider: str, settings: Config) -> RedirectResponse:
    started = start_oauth(
        provider,
        oauth_app=settings.oauth_app(provider),
        public_url=settings.public_url,
        jwt_secret=settings.jwt_secret,
    )

    response = RedirectResponse(started.redirect_to, status_code=302)
    set_oauth_cookie(response, started.pending_cookie)

    return response


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    conn: Db,
    http: Http,
    settings: Config,
    code: str | None = None,
    state: str | None = None,
    pending: Annotated[str | None, Cookie(alias=OAUTH_COOKIE)] = None,
) -> RedirectResponse:
    try:
        signed_in = await finish_oauth(
            conn,
            http,
            provider,
            oauth_app=settings.oauth_app(provider),
            code=code,
            state=state,
            pending_cookie=pending,
            public_url=settings.public_url,
            jwt_secret=settings.jwt_secret,
            registration_open=settings.registration_open,
        )
    except DomainError as exc:
        details = {"provider": provider, "code": exc.code, "reason": exc.message}
        log.warning("oauth sign-in failed on %(provider)s: %(code)s, %(reason)s", details)

        query = urlencode({"error": exc.code})
        failed = RedirectResponse(f"{settings.public_url}/login?{query}", status_code=302)
        clear_oauth_cookie(failed)

        return failed

    # The web app takes it from here: on load it calls /auth/refresh, and the
    # cookie set below is what answers.
    response = RedirectResponse(f"{settings.public_url}/", status_code=302)
    set_refresh_cookie(response, signed_in.refresh_token, signed_in.refresh_expires_at)
    clear_oauth_cookie(response)

    return response
