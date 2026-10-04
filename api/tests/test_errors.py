"""Every failure leaves through the envelope, and only through it."""

from __future__ import annotations

import uuid

import pytest
from app.domain.errors import DomainError
from app.main import register_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel


class Body(BaseModel):
    password: str
    retries: int


class ThingNotFound(DomainError):
    code = "THING_NOT_FOUND"
    status = 404
    message = "No such thing."


@pytest.fixture
def bare() -> TestClient:
    """A bare app with only the error handlers and routes that raise on purpose."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/thing")
    async def thing() -> None:
        raise ThingNotFound

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("the password is hunter2")

    @app.post("/body")
    async def body(payload: Body) -> Body:
        return payload

    return TestClient(app, raise_server_exceptions=False)


def test_a_domain_error_maps_to_its_code_and_status(bare: TestClient) -> None:
    response = bare.get("/thing")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "THING_NOT_FOUND", "message": "No such thing."}}


def test_a_missing_body_is_a_validation_error(bare: TestClient) -> None:
    response = bare.post("/body")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_rejected_value_is_not_echoed_back(bare: TestClient) -> None:
    payload = {"password": "hunter2", "retries": "hunter2-is-not-a-number"}

    response = bare.post("/body", json=payload)

    assert response.status_code == 422
    assert set(response.json()) == {"error"}
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "hunter2" not in response.text


def test_an_unhandled_error_says_nothing_about_what_broke(
    bare: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = bare.get("/boom")

    assert response.status_code == 500
    assert "hunter2" not in response.text

    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["message"] == "Something went wrong."
    assert set(error) == {"code", "message", "request_id"}

    # The id is what joins the response to the traceback in the log.
    request_id = str(uuid.UUID(error["request_id"]))
    assert request_id in caplog.text
    assert "hunter2" in caplog.text


def test_an_unknown_route_still_uses_the_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_the_wrong_method_still_uses_the_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
