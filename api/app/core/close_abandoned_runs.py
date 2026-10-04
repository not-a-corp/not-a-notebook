"""Closing the runs a dead process left running.

A run executes as a task inside the API process (decision 12). If the process
dies, its runs stay 'running' in the table, and the one-run-per-conversation
index would keep those conversations busy forever. On startup, before any
request, they are closed as failed (see schema.sql).

This assumes one API process per database, which is the design until it is not —
the day there are several, each closes only its own (decision 12's "revisit").
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection


async def close_abandoned_runs(conn: AsyncConnection[Any]) -> int:
    sql = """
        UPDATE runs r
           SET status = 'failed',
               finished_at = now()
         WHERE r.status = 'running'
        RETURNING r.id
    """

    async with conn.cursor() as cur:
        await cur.execute(sql)
        rows = await cur.fetchall()

    return len(rows)
