"""The provider sent the browser back: sign the person in, or create their account.

**An OAuth sign-in never joins an existing account**, even with the same email.
Emails registered with a password are not verified, so someone could register
your address first and wait for you to arrive through Google (pre-account
hijacking). A new identity whose email already has an account is
EMAIL_ALREADY_REGISTERED — and that is not a check here: it is the users.email
unique index refusing the INSERT.
"""

from __future__ import annotations

import hmac
from typing import Any

import httpx2
from psycopg import AsyncConnection

from app.core.new_user import NewUser, insert_user
from app.core.sessions import open_session
from app.domain.auth import SignedIn
from app.domain.errors import OAuthFailed
from app.oauth.pending import open_pending
from app.oauth.providers import PROVIDERS, Identity, OAuthApp, callback_url, exchange_code


async def finish_oauth(
    conn: AsyncConnection[Any],
    http: httpx2.AsyncClient,
    provider_name: str,
    oauth_app: OAuthApp | None,
    code: str | None,
    state: str | None,
    pending_cookie: str | None,
    public_url: str,
    jwt_secret: str,
    registration_open: bool,
) -> SignedIn:
    provider = PROVIDERS.get(provider_name)
    if provider is None or oauth_app is None:
        raise OAuthFailed(f"{provider_name} is not enabled")

    # No code means the provider sent an error instead: consent denied, most
    # often.
    if code is None or state is None:
        raise OAuthFailed(f"{provider_name} came back without a code")

    if pending_cookie is None:
        raise OAuthFailed("no sign-in was started in this browser")

    pending = open_pending(pending_cookie, jwt_secret)
    if pending is None:
        raise OAuthFailed("the pending sign-in is invalid or expired")

    if pending.provider != provider.name:
        raise OAuthFailed("the sign-in was started with another provider")

    if not hmac.compare_digest(pending.state, state):
        raise OAuthFailed("state does not match")

    redirect_uri = callback_url(public_url, provider)
    access_token = await exchange_code(
        http,
        provider,
        oauth_app,
        redirect_uri,
        code,
        pending.verifier,
    )
    identity = await provider.fetch_identity(http, access_token)

    return await sign_in(conn, provider.name, identity, jwt_secret, registration_open)


async def sign_in(
    conn: AsyncConnection[Any],
    provider: str,
    identity: Identity,
    jwt_secret: str,
    registration_open: bool,
) -> SignedIn:
    # Identity is (provider, subject), never the email: the user may have
    # changed it at the provider since the last time.
    sql = """
        SELECT u.id,
               u.external_id
          FROM oauth_accounts o
          JOIN users u
            ON u.id = o.user_id
         WHERE o.provider = %(provider)s
           AND o.subject = %(subject)s
    """

    params = {
        "provider": provider,
        "subject": identity.subject,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is not None:
        return await open_session(conn, row["id"], row["external_id"], jwt_secret)

    user = await create_account(conn, provider, identity, registration_open)

    return await open_session(conn, user.id, user.external_id, jwt_secret)


async def create_account(
    conn: AsyncConnection[Any],
    provider: str,
    identity: Identity,
    registration_open: bool,
) -> NewUser:
    """A user with no password and one linked provider, or neither."""
    sql = """
        INSERT INTO oauth_accounts AS o (user_id, provider, subject, email)
        VALUES (%(user_id)s, %(provider)s, %(subject)s, %(email)s)
    """

    async with conn.transaction():
        user = await insert_user(conn, identity.email, None, registration_open)

        params: dict[str, Any] = {
            "user_id": user.id,
            "provider": provider,
            "subject": identity.subject,
            "email": identity.email,
        }
        await conn.execute(sql, params)

    return user
