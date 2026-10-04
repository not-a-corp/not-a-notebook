"""POST /auth/login."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from tests.auth_helpers import COOKIE, LOGIN, RAFAEL, REGISTER
from tests.conftest import Run


def test_returns_an_access_token_and_when_it_expires(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)

    response = client.post(LOGIN, json=RAFAEL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "expires_at"}

    expires_at = datetime.fromisoformat(body["expires_at"])
    remaining = expires_at - datetime.now(UTC)
    assert timedelta(minutes=14) < remaining <= timedelta(minutes=15)


def test_sets_the_refresh_cookie_locked_down(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)

    response = client.post(LOGIN, json=RAFAEL)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/api/v1/auth" in cookie


def test_the_refresh_token_is_never_stored(client: TestClient, sql: Run) -> None:
    client.post(REGISTER, json=RAFAEL)
    response = client.post(LOGIN, json=RAFAEL)
    refresh_token = response.cookies[COOKIE]

    rows = sql("""
        SELECT s.token_hash
          FROM sessions s
    """)

    stored = bytes(rows[0][0])
    assert refresh_token.encode() not in stored
    assert len(stored) == 32


def test_the_email_is_matched_in_any_case(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)
    payload = {"email": "RAFAEL@example.com", "password": RAFAEL["password"]}

    response = client.post(LOGIN, json=payload)

    assert response.status_code == 200


def test_a_wrong_password_is_invalid_credentials(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)
    payload = {"email": RAFAEL["email"], "password": "not the password"}

    response = client.post(LOGIN, json=payload)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in response.headers


def test_an_unknown_email_gets_the_same_answer(client: TestClient) -> None:
    payload = {"email": "nobody@example.com", "password": "whatever it is"}

    response = client.post(LOGIN, json=payload)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_an_unknown_email_costs_the_same_time_as_a_wrong_password(client: TestClient) -> None:
    """Otherwise the clock says what the error code refuses to."""
    client.post(REGISTER, json=RAFAEL)
    wrong_password = {"email": RAFAEL["email"], "password": "not the password"}
    unknown_email = {"email": "nobody@example.com", "password": "not the password"}

    started = time.monotonic()
    client.post(LOGIN, json=wrong_password)
    wrong_password_took = time.monotonic() - started

    started = time.monotonic()
    client.post(LOGIN, json=unknown_email)
    unknown_email_took = time.monotonic() - started

    assert unknown_email_took > wrong_password_took / 3


def test_an_account_without_a_password_cannot_sign_in_with_one(
    client: TestClient, sql: Run
) -> None:
    """An OAuth account has no password until one is set."""
    sql("""
        INSERT INTO users AS u (email, password_hash)
        VALUES ('rafael@example.com', NULL)
    """)

    response = client.post(LOGIN, json=RAFAEL)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_a_short_password_is_a_wrong_password_not_a_malformed_one(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)
    payload = {"email": RAFAEL["email"], "password": "x"}

    response = client.post(LOGIN, json=payload)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
