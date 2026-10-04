"""Google and GitHub: where to send the browser, and how to learn who came back.

Everything a provider answers is checked against a model before it is believed,
and every way a provider can fail — a refused code, a network error, a body of
the wrong shape, an email it has not verified — becomes the one OAUTH_FAILED.

Only a **verified** email is accepted. An unverified one would let someone who
typed your address at the provider arrive here as you.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx2
from pydantic import BaseModel, RootModel, ValidationError

from app.domain.errors import OAuthFailed


@dataclass(frozen=True)
class OAuthApp:
    """The client id and secret registered with one provider."""

    client_id: str
    client_secret: str


@dataclass(frozen=True)
class Identity:
    """Who the provider says signed in. `subject` is the provider's own user id,
    which survives the user changing their email there."""

    subject: str
    email: str


type FetchIdentity = Callable[[httpx2.AsyncClient, str], Awaitable[Identity]]


@dataclass(frozen=True)
class Provider:
    name: str
    authorize_url: str
    token_url: str
    scope: str
    fetch_identity: FetchIdentity


class TokenResponse(BaseModel):
    access_token: str


class GoogleUserInfo(BaseModel):
    sub: str
    email: str
    email_verified: bool


class GitHubUser(BaseModel):
    id: int


class GitHubEmail(BaseModel):
    email: str
    primary: bool
    verified: bool


class GitHubEmails(RootModel[list[GitHubEmail]]):
    pass


async def get_json[T: BaseModel](
    http: httpx2.AsyncClient,
    url: str,
    access_token: str,
    model: type[T],
) -> T:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    try:
        response = await http.get(url, headers=headers)
    except httpx2.HTTPError as exc:
        raise OAuthFailed(f"{url} unreachable: {exc!r}") from exc

    if response.status_code != 200:
        raise OAuthFailed(f"{url} answered {response.status_code}")

    try:
        body = model.model_validate_json(response.content)
    except ValidationError as exc:
        raise OAuthFailed(f"{url} answered an unexpected body") from exc

    return body


async def fetch_google_identity(http: httpx2.AsyncClient, access_token: str) -> Identity:
    url = "https://openidconnect.googleapis.com/v1/userinfo"
    user = await get_json(http, url, access_token, GoogleUserInfo)

    if not user.email_verified:
        raise OAuthFailed("google: the email is not verified")

    return Identity(subject=user.sub, email=user.email)


async def fetch_github_identity(http: httpx2.AsyncClient, access_token: str) -> Identity:
    user_url = "https://api.github.com/user"
    user = await get_json(http, user_url, access_token, GitHubUser)

    # /user carries only the email the user chose to make public, if any, and
    # does not say whether it is verified. /user/emails says both.
    emails_url = "https://api.github.com/user/emails"
    emails = await get_json(http, emails_url, access_token, GitHubEmails)

    for candidate in emails.root:
        if candidate.primary and candidate.verified:
            return Identity(subject=str(user.id), email=candidate.email)

    raise OAuthFailed("github: no verified primary email")


GOOGLE = Provider(
    name="google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scope="openid email",
    fetch_identity=fetch_google_identity,
)

GITHUB = Provider(
    name="github",
    authorize_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    scope="read:user user:email",
    fetch_identity=fetch_github_identity,
)

PROVIDERS = {
    GOOGLE.name: GOOGLE,
    GITHUB.name: GITHUB,
}


def callback_url(public_url: str, provider: Provider) -> str:
    """The redirect_uri. It must match, character for character, the one
    registered with the provider and the one sent when exchanging the code."""
    return f"{public_url}/api/v1/auth/oauth/{provider.name}/callback"


def authorize_url(
    provider: Provider,
    oauth_app: OAuthApp,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": oauth_app.client_id,
        "redirect_uri": redirect_uri,
        "scope": provider.scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = urlencode(params)

    return f"{provider.authorize_url}?{query}"


async def exchange_code(
    http: httpx2.AsyncClient,
    provider: Provider,
    oauth_app: OAuthApp,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> str:
    """The provider's access token for this sign-in. Used once, then dropped."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": oauth_app.client_id,
        "client_secret": oauth_app.client_secret,
        "code_verifier": code_verifier,
    }

    # GitHub answers form-encoded unless asked for JSON.
    headers = {"Accept": "application/json"}

    try:
        response = await http.post(provider.token_url, data=data, headers=headers)
    except httpx2.HTTPError as exc:
        raise OAuthFailed(f"{provider.name} token endpoint unreachable: {exc!r}") from exc

    if response.status_code != 200:
        raise OAuthFailed(f"{provider.name} token endpoint answered {response.status_code}")

    # GitHub reports a refused code as a 200 with an "error" field and no
    # access_token, which is exactly what this rejects.
    try:
        token = TokenResponse.model_validate_json(response.content)
    except ValidationError as exc:
        raise OAuthFailed(f"{provider.name} token endpoint gave no access token") from exc

    return token.access_token
