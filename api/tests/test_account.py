"""GET /account and PUT /account/password."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.auth_helpers import (
    ACCOUNT,
    ANA,
    LOGIN,
    PASSWORD,
    RAFAEL,
    REFRESH,
    bearer,
    sign_up_and_in,
)
from tests.conftest import Run

NEW_PASSWORD = "the new password"


def test_shows_the_callers_own_account(client: TestClient) -> None:
    sign_up_and_in(client, ANA)
    token = sign_up_and_in(client, RAFAEL)

    response = client.get(ACCOUNT, headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "has_password", "oauth", "created_at"}
    assert body["email"] == RAFAEL["email"]
    assert body["has_password"] is True
    assert body["oauth"] == []


def test_lists_the_linked_oauth_providers(client: TestClient, sql: Run) -> None:
    token = sign_up_and_in(client)
    sql("""
        INSERT INTO oauth_accounts AS o (user_id, provider, subject, email)
        SELECT u.id, 'github', '12345', u.email
          FROM users u
    """)

    body = client.get(ACCOUNT, headers=bearer(token)).json()

    assert body["oauth"] == ["github"]


def test_changes_the_password(client: TestClient) -> None:
    token = sign_up_and_in(client)
    payload = {"current_password": RAFAEL["password"], "new_password": NEW_PASSWORD}

    response = client.put(PASSWORD, headers=bearer(token), json=payload)

    assert response.status_code == 204

    with_new = {"email": RAFAEL["email"], "password": NEW_PASSWORD}
    assert client.post(LOGIN, json=with_new).status_code == 200
    assert client.post(LOGIN, json=RAFAEL).status_code == 401


def test_the_current_password_is_required_even_with_a_valid_token(client: TestClient) -> None:
    token = sign_up_and_in(client)
    wrong = {"current_password": "not the password", "new_password": NEW_PASSWORD}
    missing = {"new_password": NEW_PASSWORD}

    wrong_response = client.put(PASSWORD, headers=bearer(token), json=wrong)
    missing_response = client.put(PASSWORD, headers=bearer(token), json=missing)

    assert wrong_response.status_code == 401
    assert wrong_response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert missing_response.status_code == 401
    assert missing_response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert client.post(LOGIN, json=RAFAEL).status_code == 200


def test_an_account_without_a_password_sets_its_first_one(client: TestClient, sql: Run) -> None:
    token = sign_up_and_in(client)
    sql("""
        UPDATE users u
           SET password_hash = NULL
    """)
    assert client.get(ACCOUNT, headers=bearer(token)).json()["has_password"] is False

    response = client.put(PASSWORD, headers=bearer(token), json={"new_password": NEW_PASSWORD})

    assert response.status_code == 204
    with_new = {"email": RAFAEL["email"], "password": NEW_PASSWORD}
    assert client.post(LOGIN, json=with_new).status_code == 200


def test_every_session_ends_the_callers_included(client: TestClient, sql: Run) -> None:
    token = sign_up_and_in(client)
    client.post(LOGIN, json=RAFAEL)
    payload = {"current_password": RAFAEL["password"], "new_password": NEW_PASSWORD}

    response = client.put(PASSWORD, headers=bearer(token), json=payload)

    assert sql("SELECT s.id FROM sessions s") == []
    assert "set-cookie" in response.headers
    assert client.post(REFRESH).status_code == 401


def test_a_short_new_password_is_rejected(client: TestClient) -> None:
    token = sign_up_and_in(client)
    payload = {"current_password": RAFAEL["password"], "new_password": "short"}

    response = client.put(PASSWORD, headers=bearer(token), json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_without_a_token_it_is_unauthenticated(client: TestClient) -> None:
    sign_up_and_in(client)
    payload = {"current_password": RAFAEL["password"], "new_password": NEW_PASSWORD}

    response = client.put(PASSWORD, json=payload)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
