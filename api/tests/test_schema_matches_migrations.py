"""schema.sql and the migrations describe the same database.

Two descriptions of one thing drift. This applies schema.sql to one database
and the migrations to another, then compares what PostgreSQL actually built:
columns, constraints, indexes, triggers and functions.

Any difference fails the test.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import psycopg
from psycopg.rows import tuple_row

PROJECT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = PROJECT / "schema.sql"

TABLES = {
    "users",
    "oauth_accounts",
    "sessions",
    "models",
    "conversations",
    "runs",
    "run_events",
    "files",
    "messages",
    "cells",
    "cell_outputs",
}


def alembic(dsn: str, *args: str) -> None:
    env = {"PATH": "/opt/venv/bin:/usr/bin:/bin", "DATABASE_URL": dsn}
    command = ["alembic", *args]

    result = subprocess.run(command, cwd=PROJECT, env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


def describe(dsn: str) -> list[tuple[str, str, str]]:
    sql = """
        SELECT 'column' AS kind,
               c.table_name || '.' || c.column_name AS name,
               c.data_type
                 || coalesce('(' || c.character_maximum_length || ')', '')
                 || ' null=' || c.is_nullable
                 || ' default=' || coalesce(c.column_default, '-') AS definition
          FROM information_schema.columns c
         WHERE c.table_schema = 'public'
           AND c.table_name <> 'alembic_version'
        UNION ALL
        SELECT 'constraint',
               con.conrelid::regclass::text || '.' || con.conname,
               pg_get_constraintdef(con.oid)
          FROM pg_constraint con
         WHERE con.connamespace = 'public'::regnamespace
           AND con.conrelid::regclass::text <> 'alembic_version'
        UNION ALL
        SELECT 'index',
               i.indexname,
               i.indexdef
          FROM pg_indexes i
         WHERE i.schemaname = 'public'
           AND i.tablename <> 'alembic_version'
        UNION ALL
        SELECT 'trigger',
               tg.tgname,
               pg_get_triggerdef(tg.oid)
          FROM pg_trigger tg
         WHERE NOT tg.tgisinternal
        UNION ALL
        SELECT 'function',
               p.proname,
               pg_get_functiondef(p.oid)
          FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
         ORDER BY 1, 2, 3
    """

    with psycopg.connect(dsn) as conn, conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql)
        return cur.fetchall()


def tables(dsn: str) -> set[str]:
    sql = """
        SELECT t.tablename
          FROM pg_tables t
         WHERE t.schemaname = 'public'
           AND t.tablename <> 'alembic_version'
    """

    with psycopg.connect(dsn) as conn, conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return {row[0] for row in rows}


def test_schema_sql_matches_the_migrations(scratch_db: Callable[[str], str]) -> None:
    target = scratch_db("drift_target")
    migrated = scratch_db("drift_migrated")

    with psycopg.connect(target, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text())

    alembic(migrated, "upgrade", "head")

    expected = describe(target)
    actual = describe(migrated)

    missing = [row for row in expected if row not in actual]
    extra = [row for row in actual if row not in expected]
    assert not missing and not extra, (
        "schema.sql and the migrations disagree.\n"
        + "".join(f"  only in schema.sql: {row}\n" for row in missing)
        + "".join(f"  only in migrations: {row}\n" for row in extra)
    )


def test_migrations_go_up_and_down(scratch_db: Callable[[str], str]) -> None:
    dsn = scratch_db("migration_cycle")

    alembic(dsn, "upgrade", "head")
    assert tables(dsn) == TABLES

    alembic(dsn, "downgrade", "base")
    assert tables(dsn) == set()
    assert describe(dsn) == []
