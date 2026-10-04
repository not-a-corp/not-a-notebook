from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
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
