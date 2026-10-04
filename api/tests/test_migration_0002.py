"""0002 fills kind and grounding in for the messages that were there before it,
from what their runs recorded."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.rows import tuple_row
from tests.test_schema_matches_migrations import alembic


def run(dsn: str, sql: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        return cur.fetchall()


def test_existing_messages_get_their_kind_and_grounding(scratch_db: Callable[[str], str]) -> None:
    dsn = scratch_db("migration_0002")
    alembic(dsn, "upgrade", "0001")

    run(
        dsn,
        """
        INSERT INTO users AS u (email) VALUES ('rafael@example.com');
        INSERT INTO conversations AS c (user_id) SELECT u.id FROM users u;
        INSERT INTO runs AS r (conversation_id, kind, model_name, status, finished_at)
        SELECT c.id, 'message', 'scripted', s.status, now()
          FROM conversations c,
               (VALUES ('succeeded'), ('awaiting_user')) AS s (status);
        INSERT INTO run_events AS e (run_id, seq, type, event)
        SELECT r.id, 1, 'grounding.checked',
               '{"seq": 1, "t": 2.5, "type": "grounding.checked",
                 "numbers": 3, "found": 2, "unfound": ["41%"]}'::jsonb
          FROM runs r
         WHERE r.status = 'succeeded';
        INSERT INTO messages AS m (conversation_id, run_id, role, text)
        SELECT r.conversation_id, r.id, 'assistant', r.status
          FROM runs r;
        INSERT INTO messages AS m (conversation_id, run_id, role, text)
        SELECT c.id, NULL, 'user', 'Which region?'
          FROM conversations c;
    """,
    )

    alembic(dsn, "upgrade", "head")

    rows = run(
        dsn,
        """
        SELECT m.text, m.kind, m.grounding
          FROM messages m
         ORDER BY m.id
    """,
    )
    assert rows == [
        ("succeeded", "answer", {"numbers": 3, "found": 2, "unfound": ["41%"]}),
        ("awaiting_user", "question", None),
        ("Which region?", None, None),
    ]
