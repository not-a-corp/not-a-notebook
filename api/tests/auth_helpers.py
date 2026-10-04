"""Signing up and in from tests, the way a client would."""

from __future__ import annotations

from fastapi.testclient import TestClient

OPTIONS = "/api/v1/auth/options"
REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ACCOUNT = "/api/v1/account"
PASSWORD = "/api/v1/account/password"

COOKIE = "nan_refresh"

RAFAEL = {"email": "rafael@example.com", "password": "a good password"}
ANA = {"email": "ana@example.com", "password": "another good password"}


def sign_up_and_in(client: TestClient, account: dict[str, str] = RAFAEL) -> str:
    """Registers and signs in; returns the access token. The cookie stays in the jar."""
    client.post(REGISTER, json=account)
    response = client.post(LOGIN, json=account)
    assert response.status_code == 200, response.text

    body = response.json()
    return str(body["access_token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def only_cookie(client: TestClient, refresh_token: str) -> dict[str, str]:
    """Headers that send exactly this refresh token, with the jar emptied so
    nothing else rides along."""
    client.cookies.clear()

    return {"Cookie": f"{COOKIE}={refresh_token}"}
