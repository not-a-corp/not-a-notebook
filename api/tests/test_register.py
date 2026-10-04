"""POST /auth/register, and GET /auth/options that announces it."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.conftest import Run
from tests.support.auth import ANA, OPTIONS, RAFAEL, REGISTER


def test_creates_an_account(client: TestClient) -> None:
    response = client.post(REGISTER, json=RAFAEL)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "created_at"}
    assert body["email"] == RAFAEL["email"]


def test_dates_are_utc_and_end_in_z(client: TestClient) -> None:
    body = client.post(REGISTER, json=RAFAEL).json()

    assert body["created_at"].endswith("Z")


def test_does_not_sign_in(client: TestClient) -> None:
    response = client.post(REGISTER, json=RAFAEL)

    assert "access_token" not in response.json()
    assert "set-cookie" not in response.headers


def test_the_same_email_twice_is_a_conflict(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)
    response = client.post(REGISTER, json=RAFAEL)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_the_same_email_in_another_case_is_still_a_conflict(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)
    payload = {"email": "Rafael@Example.com", "password": RAFAEL["password"]}

    response = client.post(REGISTER, json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_passwords_are_8_to_128_characters(client: TestClient) -> None:
    too_short = {"email": "a@example.com", "password": "x" * 7}
    shortest = {"email": "b@example.com", "password": "x" * 8}
    longest = {"email": "c@example.com", "password": "x" * 128}
    too_long = {"email": "d@example.com", "password": "x" * 129}

    assert client.post(REGISTER, json=too_short).status_code == 422
    assert client.post(REGISTER, json=shortest).status_code == 201
    assert client.post(REGISTER, json=longest).status_code == 201
    assert client.post(REGISTER, json=too_long).status_code == 422


def test_a_malformed_email_is_rejected(client: TestClient) -> None:
    payload = {"email": "not-an-email", "password": RAFAEL["password"]}

    response = client.post(REGISTER, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_the_password_is_never_stored(client: TestClient, sql: Run) -> None:
    client.post(REGISTER, json=RAFAEL)

    rows = sql("""
        SELECT u.password_hash
          FROM users u
    """)

    stored = rows[0][0]
    assert RAFAEL["password"] not in stored
    assert stored.startswith("$argon2id$")


def test_the_id_is_the_public_uuid_not_the_row_id(client: TestClient, sql: Run) -> None:
    body = client.post(REGISTER, json=RAFAEL).json()

    rows = sql("""
        SELECT u.id,
               u.external_id::text
          FROM users u
    """)

    row_id, external_id = rows[0]
    assert body["id"] == external_id
    assert body["id"] != str(row_id)


def test_options_while_open(client: TestClient) -> None:
    client.post(REGISTER, json=RAFAEL)

    response = client.get(OPTIONS)

    assert response.status_code == 200
    assert response.json() == {"registration_open": True, "oauth": []}


def test_closed_still_lets_the_first_account_in(
    client: TestClient, closed_registration: None
) -> None:
    assert client.get(OPTIONS).json()["registration_open"] is True

    response = client.post(REGISTER, json=RAFAEL)

    assert response.status_code == 201


def test_closed_keeps_everyone_after_the_first_out(
    client: TestClient, closed_registration: None
) -> None:
    client.post(REGISTER, json=RAFAEL)

    response = client.post(REGISTER, json=ANA)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REGISTRATION_CLOSED"
    assert client.get(OPTIONS).json()["registration_open"] is False


def test_closed_does_not_say_whether_an_email_exists(
    client: TestClient, closed_registration: None
) -> None:
    """A taken email on a closed instance is closed, not a conflict — the
    conflict would confirm the address has an account."""
    client.post(REGISTER, json=RAFAEL)

    response = client.post(REGISTER, json=RAFAEL)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REGISTRATION_CLOSED"
