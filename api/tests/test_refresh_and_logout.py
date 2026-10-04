"""POST /auth/refresh and POST /auth/logout: the session behind the cookie."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.conftest import Run
from tests.support.auth import (
    ACCOUNT,
    COOKIE,
    LOGIN,
    LOGOUT,
    RAFAEL,
    REFRESH,
    REGISTER,
    bearer,
    only_cookie,
    sign_up_and_in,
)


def sign_in_for_cookie(client: TestClient) -> str:
    client.post(REGISTER, json=RAFAEL)
    response = client.post(LOGIN, json=RAFAEL)

    return response.cookies[COOKIE]


def test_refresh_returns_a_working_access_token(client: TestClient) -> None:
    sign_up_and_in(client)

    response = client.post(REFRESH)

    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "expires_at"}

    token = response.json()["access_token"]
    assert client.get(ACCOUNT, headers=bearer(token)).status_code == 200


def test_refresh_rotates_the_cookie(client: TestClient) -> None:
    old = sign_in_for_cookie(client)

    response = client.post(REFRESH, headers=only_cookie(client, old))

    new = response.cookies[COOKIE]
    assert new != old


def test_the_old_refresh_token_stops_working_once_rotated(client: TestClient) -> None:
    old = sign_in_for_cookie(client)
    client.post(REFRESH, headers=only_cookie(client, old))

    response = client.post(REFRESH, headers=only_cookie(client, old))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_the_new_refresh_token_keeps_working(client: TestClient) -> None:
    old = sign_in_for_cookie(client)
    first = client.post(REFRESH, headers=only_cookie(client, old))
    new = first.cookies[COOKIE]

    response = client.post(REFRESH, headers=only_cookie(client, new))

    assert response.status_code == 200


def test_refresh_without_a_cookie_is_unauthenticated(client: TestClient) -> None:
    response = client.post(REFRESH)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_an_unknown_cookie_is_unauthenticated(client: TestClient) -> None:
    sign_up_and_in(client)

    response = client.post(REFRESH, headers=only_cookie(client, "made-up"))

    assert response.status_code == 401


def test_refresh_after_thirty_idle_days_is_unauthenticated(client: TestClient, sql: Run) -> None:
    sign_up_and_in(client)
    sql("""
        UPDATE sessions s
           SET expires_at = now() - interval '1 second'
    """)

    assert client.post(REFRESH).status_code == 401


def test_refresh_pushes_the_idle_deadline_forward(client: TestClient, sql: Run) -> None:
    sign_up_and_in(client)
    sql("""
        UPDATE sessions s
           SET expires_at = now() + interval '1 day'
    """)

    client.post(REFRESH)

    rows = sql("""
        SELECT s.expires_at - now() > interval '29 days'
          FROM sessions s
    """)
    assert rows[0][0] is True


def test_refresh_never_moves_past_the_absolute_deadline(client: TestClient, sql: Run) -> None:
    """Near the end of the ninety days, a plain now() + 30 days would break the CHECK."""
    sign_up_and_in(client)
    sql("""
        UPDATE sessions s
           SET expires_at = now() + interval '30 minutes',
               absolute_expires_at = now() + interval '1 hour'
    """)

    assert client.post(REFRESH).status_code == 200

    rows = sql("""
        SELECT s.expires_at = s.absolute_expires_at
          FROM sessions s
    """)
    assert rows[0][0] is True


def test_refresh_after_the_absolute_deadline_is_unauthenticated(
    client: TestClient, sql: Run
) -> None:
    sign_up_and_in(client)
    sql("""
        UPDATE sessions s
           SET expires_at = now() - interval '1 second',
               absolute_expires_at = now() - interval '1 second'
    """)

    assert client.post(REFRESH).status_code == 401


def test_logout_ends_the_session(client: TestClient, sql: Run) -> None:
    refresh_token = sign_in_for_cookie(client)

    response = client.post(LOGOUT, headers=only_cookie(client, refresh_token))

    assert response.status_code == 204
    assert sql("SELECT s.id FROM sessions s") == []

    again = client.post(REFRESH, headers=only_cookie(client, refresh_token))
    assert again.status_code == 401


def test_logout_clears_the_cookie(client: TestClient) -> None:
    sign_up_and_in(client)

    response = client.post(LOGOUT)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f'{COOKIE}=""') or cookie.startswith(f"{COOKIE}=;")
    assert "Path=/api/v1/auth" in cookie


def test_logout_only_ends_this_device(client: TestClient, sql: Run) -> None:
    laptop = sign_in_for_cookie(client)
    phone = client.post(LOGIN, json=RAFAEL).cookies[COOKIE]

    client.post(LOGOUT, headers=only_cookie(client, laptop))

    response = client.post(REFRESH, headers=only_cookie(client, phone))
    assert response.status_code == 200


def test_logout_without_a_cookie_is_unauthenticated(client: TestClient) -> None:
    response = client.post(LOGOUT)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
