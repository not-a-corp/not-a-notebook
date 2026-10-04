from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from app.config import get_settings
from app.main import app
from fastapi.testclient import TestClient
from psycopg.sql import SQL, Identifier


def with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    path = f"/{name}"

    return urlunsplit(parts._replace(path=path))


def drop_database(admin: str, name: str) -> None:
    sql = SQL("""
        DROP DATABASE IF EXISTS {name}
        WITH (FORCE)
    """).format(name=Identifier(name))

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql)


def create_database(admin: str, name: str) -> None:
    sql = SQL("""
        CREATE DATABASE {name}
    """).format(name=Identifier(name))

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql)


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ["DATABASE_URL"]


@pytest.fixture
def scratch_db(base_url: str) -> Iterator[Callable[[str], str]]:
    """Hands out empty throwaway databases, dropped afterwards."""
    admin = with_database(base_url, "postgres")
    created: list[str] = []

    def make(name: str) -> str:
        drop_database(admin, name)
        create_database(admin, name)
        created.append(name)

        return with_database(base_url, name)

    yield make

    for name in created:
        drop_database(admin, name)


TEST_DATABASE = "notebook_test"


@pytest.fixture(scope="session")
def migrated_database(base_url: str) -> Iterator[str]:
    """A database with the migrations applied, shared by the whole run."""
    admin = with_database(base_url, "postgres")
    dsn = with_database(base_url, TEST_DATABASE)

    drop_database(admin, TEST_DATABASE)
    create_database(admin, TEST_DATABASE)

    env = {"PATH": "/opt/venv/bin:/usr/bin:/bin", "DATABASE_URL": dsn}
    command = ["alembic", "upgrade", "head"]
    project = Path(__file__).resolve().parents[1]

    result = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    yield dsn

    drop_database(admin, TEST_DATABASE)


@pytest.fixture
def client(migrated_database: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real application, pointed at an empty migrated database.

    Over https, because the refresh cookie is Secure: on plain http the client
    would receive it and never send it back.
    """
    sql = """
        TRUNCATE users
        RESTART IDENTITY CASCADE
    """

    with psycopg.connect(migrated_database, autocommit=True) as conn:
        conn.execute(sql)

    monkeypatch.setenv("DATABASE_URL", migrated_database)
    get_settings.cache_clear()
    try:
        with TestClient(app, base_url="https://testserver") as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def closed_registration(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRATION_OPEN", "false")
    get_settings.cache_clear()


Run = Callable[..., list[tuple[Any, ...]]]


@pytest.fixture
def sql(migrated_database: str) -> Run:
    """Run a query against the test database and get its rows back."""

    def run(query: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        with psycopg.connect(migrated_database, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(query, params)  # type: ignore[arg-type]

            # UPDATE and DELETE without RETURNING produce no rows to fetch.
            if cur.description is None:
                return []

            return cur.fetchall()

    return run
