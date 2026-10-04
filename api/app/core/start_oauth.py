"""Sending the browser to the provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.errors import OAuthProviderNotEnabled
from app.oauth.pending import code_challenge, new_pending_sign_in, seal_pending
from app.oauth.providers import PROVIDERS, OAuthApp, authorize_url, callback_url


@dataclass(frozen=True)
class OAuthStart:
    redirect_to: str
    pending_cookie: str


def start_oauth(
    provider_name: str,
    oauth_app: OAuthApp | None,
    public_url: str,
    jwt_secret: str,
) -> OAuthStart:
    provider = PROVIDERS.get(provider_name)
    if provider is None or oauth_app is None:
        raise OAuthProviderNotEnabled

    pending = new_pending_sign_in(provider.name)
    challenge = code_challenge(pending.verifier)
    redirect_uri = callback_url(public_url, provider)

    redirect_to = authorize_url(provider, oauth_app, redirect_uri, pending.state, challenge)

    now = datetime.now(UTC)
    pending_cookie = seal_pending(pending, jwt_secret, now)

    return OAuthStart(redirect_to=redirect_to, pending_cookie=pending_cookie)
