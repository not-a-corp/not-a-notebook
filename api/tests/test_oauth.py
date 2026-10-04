"""GET /auth/oauth/{provider}/start and /callback, against fake providers."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from app.config import Settings, get_settings
from app.main import app
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tests.auth_helpers import ACCOUNT, OPTIONS, RAFAEL, REFRESH, REGISTER, bearer
from tests.conftest import Run
from tests.fake_providers import FakeProviders

PUBLIC_URL = "https://notebook.example"


@pytest.fixture
def providers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeProviders]:
    """Both providers enabled and answering from memory."""
    monkeypatch.setenv("PUBLIC_URL", PUBLIC_URL)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "github-client")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "github-secret")
    get_settings.cache_clear()

    fake = FakeProviders()
    monkeypatch.setattr(app.state, "http", fake.client())

    yield fake


def start(client: TestClient, provider: str) -> dict[str, str]:
    """Begins a sign-in; returns the query the browser is sent to the provider with."""
    response = client.get(f"/api/v1/auth/oauth/{provider}/start", follow_redirects=False)
    assert response.status_code == 302, response.text

    location = urlsplit(response.headers["location"])
    query = parse_qs(location.query)

    return {name: values[0] for name, values in query.items()}


def callback(client: TestClient, provider: str, **query: str) -> httpx2.Response:
    url = f"/api/v1/auth/oauth/{provider}/callback"

    return client.get(url, params=query, follow_redirects=False)


def come_back(client: TestClient, provider: str) -> httpx2.Response:
    """The whole round trip: start, consent at the provider, callback."""
    sent = start(client, provider)

    return callback(client, provider, code="the-code", state=sent["state"])


def error_of(response: httpx2.Response) -> str:
    assert response.status_code == 302

    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{PUBLIC_URL}/login"

    query = parse_qs(location.query)
    return query["error"][0]


# ── the screen ───────────────────────────────────────────────────────────────


def test_options_lists_only_the_enabled_providers(client: TestClient) -> None:
    assert client.get(OPTIONS).json()["oauth"] == []


def test_options_lists_both_when_both_are_configured(
    client: TestClient, providers: FakeProviders
) -> None:
    assert client.get(OPTIONS).json()["oauth"] == ["google", "github"]


def test_half_an_oauth_app_stops_the_service_at_startup() -> None:
    with pytest.raises(ValidationError, match="GITHUB_CLIENT_SECRET"):
        Settings(
            database_url="postgresql://unused",
            jwt_secret="x" * 32,
            github_client_id="only-the-id",
        )


# ── start ────────────────────────────────────────────────────────────────────


def test_start_is_404_when_the_provider_is_not_configured(client: TestClient) -> None:
    response = client.get("/api/v1/auth/oauth/google/start", follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OAUTH_PROVIDER_NOT_ENABLED"


def test_start_is_404_for_a_provider_that_does_not_exist(
    client: TestClient, providers: FakeProviders
) -> None:
    response = client.get("/api/v1/auth/oauth/myspace/start", follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "OAUTH_PROVIDER_NOT_ENABLED"


def test_start_sends_the_browser_to_the_consent_screen(
    client: TestClient, providers: FakeProviders
) -> None:
    response = client.get("/api/v1/auth/oauth/google/start", follow_redirects=False)

    location = urlsplit(response.headers["location"])
    query = parse_qs(location.query)
    assert response.status_code == 302
    assert f"{location.netloc}{location.path}" == "accounts.google.com/o/oauth2/v2/auth"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["google-client"]
    assert query["redirect_uri"] == [f"{PUBLIC_URL}/api/v1/auth/oauth/google/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0]
    assert query["code_challenge"][0]


def test_start_keeps_the_pending_sign_in_in_a_lax_cookie(
    client: TestClient, providers: FakeProviders
) -> None:
    response = client.get("/api/v1/auth/oauth/github/start", follow_redirects=False)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("nan_oauth=")
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/v1/auth/oauth" in cookie


def test_the_pending_cookie_is_not_an_access_token(
    client: TestClient, providers: FakeProviders
) -> None:
    response = client.get("/api/v1/auth/oauth/github/start", follow_redirects=False)
    pending = response.cookies["nan_oauth"]

    assert client.get(ACCOUNT, headers=bearer(pending)).status_code == 401


# ── a first sign-in ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("provider", ["google", "github"])
def test_a_new_identity_creates_an_account_and_signs_in(
    client: TestClient, providers: FakeProviders, provider: str
) -> None:
    response = come_back(client, provider)

    assert response.status_code == 302
    assert response.headers["location"] == f"{PUBLIC_URL}/"

    # What the web app does on load: the cookie set by the callback answers.
    refreshed = client.post(REFRESH)
    assert refreshed.status_code == 200

    token = refreshed.json()["access_token"]
    account = client.get(ACCOUNT, headers=bearer(token)).json()
    assert account["email"] == "rafael@example.com"
    assert account["has_password"] is False
    assert account["oauth"] == [provider]


def test_the_code_is_exchanged_with_the_verifier_behind_the_challenge(
    client: TestClient, providers: FakeProviders
) -> None:
    sent = start(client, "google")

    callback(client, "google", code="the-code", state=sent["state"])

    form = providers.token_requests()[0]
    verifier = form["code_verifier"][0]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert challenge == sent["code_challenge"]
    assert form["code"] == ["the-code"]
    assert form["redirect_uri"] == [sent["redirect_uri"]]
    assert form["client_secret"] == ["google-secret"]


def test_the_callback_clears_the_pending_cookie(
    client: TestClient, providers: FakeProviders
) -> None:
    response = come_back(client, "google")

    set_cookies = response.headers.get_list("set-cookie")
    cleared = [c for c in set_cookies if c.startswith("nan_oauth=")]
    assert len(cleared) == 1
    assert "Max-Age=0" in cleared[0] or 'nan_oauth=""' in cleared[0]


def test_a_returning_identity_signs_into_the_same_account(
    client: TestClient, providers: FakeProviders, sql: Run
) -> None:
    come_back(client, "github")
    providers.github_emails[0]["email"] = "rafael@new-address.example"

    response = come_back(client, "github")

    assert response.headers["location"] == f"{PUBLIC_URL}/"
    assert sql("SELECT u.id FROM users u") == [(1,)]
    assert len(sql("SELECT s.id FROM sessions s")) == 2


def test_github_signs_in_with_the_verified_primary_email(
    client: TestClient, providers: FakeProviders, sql: Run
) -> None:
    providers.github_emails = [
        {"email": "old@example.com", "primary": False, "verified": True},
        {"email": "typo@example.com", "primary": False, "verified": False},
        {"email": "rafael@example.com", "primary": True, "verified": True},
    ]

    come_back(client, "github")

    assert sql("SELECT u.email FROM users u") == [("rafael@example.com",)]


# ── never joining an existing account ────────────────────────────────────────


def test_an_email_with_a_password_account_is_not_joined(
    client: TestClient, providers: FakeProviders, sql: Run
) -> None:
    client.post(REGISTER, json=RAFAEL)

    response = come_back(client, "google")

    assert error_of(response) == "EMAIL_ALREADY_REGISTERED"
    assert sql("SELECT o.provider FROM oauth_accounts o") == []
    assert len(sql("SELECT u.id FROM users u")) == 1


def test_an_email_from_another_provider_is_not_joined(
    client: TestClient, providers: FakeProviders
) -> None:
    come_back(client, "google")

    response = come_back(client, "github")

    assert error_of(response) == "EMAIL_ALREADY_REGISTERED"


# ── registration closed ──────────────────────────────────────────────────────


def test_closed_registration_keeps_new_identities_out(
    client: TestClient, providers: FakeProviders, closed_registration: None
) -> None:
    client.post(REGISTER, json={"email": "owner@example.com", "password": "a good password"})

    response = come_back(client, "google")

    assert error_of(response) == "REGISTRATION_CLOSED"


def test_closed_registration_still_lets_the_first_account_in_through_oauth(
    client: TestClient, providers: FakeProviders, closed_registration: None
) -> None:
    response = come_back(client, "google")

    assert response.headers["location"] == f"{PUBLIC_URL}/"


def test_closed_registration_still_lets_an_existing_identity_in(
    client: TestClient, providers: FakeProviders, monkeypatch: pytest.MonkeyPatch
) -> None:
    come_back(client, "google")
    monkeypatch.setenv("REGISTRATION_OPEN", "false")
    get_settings.cache_clear()

    response = come_back(client, "google")

    assert response.headers["location"] == f"{PUBLIC_URL}/"


# ── everything that is OAUTH_FAILED ──────────────────────────────────────────


def test_a_state_that_does_not_match_fails(client: TestClient, providers: FakeProviders) -> None:
    start(client, "google")

    response = callback(client, "google", code="the-code", state="someone-elses-state")

    assert error_of(response) == "OAUTH_FAILED"
    assert providers.requests == []


def test_a_callback_this_browser_never_started_fails(
    client: TestClient, providers: FakeProviders
) -> None:
    """Login CSRF: someone else's code and state, finished in your browser."""
    sent = start(client, "google")
    client.cookies.clear()

    response = callback(client, "google", code="their-code", state=sent["state"])

    assert error_of(response) == "OAUTH_FAILED"


def test_a_pending_sign_in_is_used_once(client: TestClient, providers: FakeProviders) -> None:
    sent = start(client, "google")
    callback(client, "google", code="the-code", state=sent["state"])

    response = callback(client, "google", code="the-code", state=sent["state"])

    assert error_of(response) == "OAUTH_FAILED"


def test_a_sign_in_started_with_one_provider_cannot_finish_with_another(
    client: TestClient, providers: FakeProviders
) -> None:
    sent = start(client, "google")

    # The cookie path covers both callbacks, so the cookie does reach this one.
    response = callback(client, "github", code="the-code", state=sent["state"])

    assert error_of(response) == "OAUTH_FAILED"


def test_consent_denied_fails(client: TestClient, providers: FakeProviders) -> None:
    sent = start(client, "google")

    response = callback(client, "google", error="access_denied", state=sent["state"])

    assert error_of(response) == "OAUTH_FAILED"


def test_a_provider_that_is_not_enabled_fails_at_the_callback(client: TestClient) -> None:
    response = callback(client, "google", code="the-code", state="whatever")

    assert response.status_code == 302
    assert "error=OAUTH_FAILED" in response.headers["location"]


def test_a_refused_code_fails(client: TestClient, providers: FakeProviders) -> None:
    providers.token_status = 400
    providers.token_body = {"error": "invalid_grant"}

    assert error_of(come_back(client, "google")) == "OAUTH_FAILED"


def test_githubs_refusal_inside_a_200_fails(client: TestClient, providers: FakeProviders) -> None:
    providers.token_body = {"error": "bad_verification_code"}

    assert error_of(come_back(client, "github")) == "OAUTH_FAILED"


def test_an_unreachable_provider_fails(client: TestClient, providers: FakeProviders) -> None:
    providers.unreachable = True

    assert error_of(come_back(client, "google")) == "OAUTH_FAILED"


def test_an_unverified_google_email_fails(
    client: TestClient, providers: FakeProviders, sql: Run
) -> None:
    providers.google_user["email_verified"] = False

    assert error_of(come_back(client, "google")) == "OAUTH_FAILED"
    assert sql("SELECT u.id FROM users u") == []


def test_github_without_a_verified_primary_email_fails(
    client: TestClient, providers: FakeProviders
) -> None:
    providers.github_emails = [
        {"email": "rafael@example.com", "primary": True, "verified": False},
        {"email": "other@example.com", "primary": False, "verified": True},
    ]

    assert error_of(come_back(client, "github")) == "OAUTH_FAILED"


def test_a_malformed_answer_from_the_provider_fails(
    client: TestClient, providers: FakeProviders
) -> None:
    providers.google_user = {"unexpected": "shape"}

    assert error_of(come_back(client, "google")) == "OAUTH_FAILED"
