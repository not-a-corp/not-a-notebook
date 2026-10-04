"""What an access token is worth, checked through a route that requires one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from app.config import get_settings
from app.security.access_tokens import issue_access_token
from fastapi.testclient import TestClient
from tests.auth_helpers import ACCOUNT, RAFAEL, bearer, sign_up_and_in


def user_id_of(client: TestClient, token: str) -> UUID:
    body = client.get(ACCOUNT, headers=bearer(token)).json()

    return UUID(body["id"])


def test_a_fresh_token_reaches_an_authenticated_route(client: TestClient) -> None:
    token = sign_up_and_in(client)

    response = client.get(ACCOUNT, headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["email"] == RAFAEL["email"]


def test_the_token_carries_the_public_id_and_nothing_else(client: TestClient) -> None:
    token = sign_up_and_in(client)

    claims = jwt.decode(token, options={"verify_signature": False})

    assert set(claims) == {"sub", "type", "iat", "exp"}
    assert claims["type"] == "access"
    assert UUID(claims["sub"]) == user_id_of(client, token)


def test_no_header_is_unauthenticated(client: TestClient) -> None:
    response = client.get(ACCOUNT)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Bearer nonsense"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic cmFmYWVsOnB3"},
        {"Authorization": "nonsense"},
    ],
)
def test_a_malformed_header_is_unauthenticated(client: TestClient, header: dict[str, str]) -> None:
    sign_up_and_in(client)

    response = client.get(ACCOUNT, headers=header)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_an_expired_token_is_unauthenticated(client: TestClient) -> None:
    token = sign_up_and_in(client)
    user_id = user_id_of(client, token)
    sixteen_minutes_ago = datetime.now(UTC) - timedelta(minutes=16)

    expired = issue_access_token(user_id, get_settings().jwt_secret, sixteen_minutes_ago)
    response = client.get(ACCOUNT, headers=bearer(expired.access_token))

    assert response.status_code == 401


def test_a_token_signed_with_another_secret_is_unauthenticated(client: TestClient) -> None:
    token = sign_up_and_in(client)
    user_id = user_id_of(client, token)

    forged = issue_access_token(user_id, "x" * 64, datetime.now(UTC))
    response = client.get(ACCOUNT, headers=bearer(forged.access_token))

    assert response.status_code == 401


def test_an_unsigned_token_is_unauthenticated(client: TestClient) -> None:
    """alg: none — the classic way past a verifier that trusts the token's header."""
    token = sign_up_and_in(client)
    claims = jwt.decode(token, options={"verify_signature": False})

    unsigned = jwt.encode(claims, key=None, algorithm="none")
    response = client.get(ACCOUNT, headers=bearer(unsigned))

    assert response.status_code == 401


def test_a_token_of_another_type_is_unauthenticated(client: TestClient) -> None:
    token = sign_up_and_in(client)
    claims = jwt.decode(token, options={"verify_signature": False})
    claims["type"] = "oauth_state"

    other = jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")
    response = client.get(ACCOUNT, headers=bearer(other))

    assert response.status_code == 401


def test_a_token_for_an_account_that_is_gone_is_unauthenticated(client: TestClient) -> None:
    token = sign_up_and_in(client)
    user_id = user_id_of(client, token)

    someone_else = UUID(int=user_id.int ^ 1)
    secret = get_settings().jwt_secret

    nobody = issue_access_token(someone_else, secret, datetime.now(UTC))
    response = client.get(ACCOUNT, headers=bearer(nobody.access_token))

    assert response.status_code == 401
