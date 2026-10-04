"""Closing the runs a dead process left running.

A run executes as a task inside the API process (decision 12). If the process
dies, its runs stay 'running' in the table, the one-run-per-conversation index
keeps those conversations busy forever, and their streams never see the
`run.finished` events.md promises is always last. On startup, before any
request, each is closed as failed and its stream is given the ending it never
got: a `run.error`, then `run.finished`, numbered after its last stored event.

This assumes one API process per database, which is the design until it is not —
the day there are several, each closes only its own (decision 12's "revisit").
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection

from app.core.run_records import record_event

GONE = "The API stopped while this run was in progress."


async def close_abandoned_runs(conn: AsyncConnection[Any]) -> int:
    sql = """
        UPDATE runs r
           SET status = 'failed',
               finished_at = now()
         WHERE r.status = 'running'
        RETURNING r.id,
                  r.tokens_in,
                  r.tokens_out,
                  r.tokens_reasoning,
                  (extract(epoch FROM r.finished_at - r.started_at) * 1000)::int AS wall_ms,
                  (
                      SELECT coalesce(max(e.seq), 0)
                        FROM run_events e
                       WHERE e.run_id = r.id
                  ) AS last_seq
    """

    async with conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()

        for row in rows:
            await write_ending(conn, row)

    return len(rows)


async def write_ending(conn: AsyncConnection[Any], row: dict[str, Any]) -> None:
    seconds = round(row["wall_ms"] / 1000, 2)

    error_seq = row["last_seq"] + 1
    error = {
        "seq": error_seq,
        "t": seconds,
        "type": "run.error",
        "code": "INTERNAL_ERROR",
        "message": GONE,
        "error_id": None,
    }
    await record_event(conn, row["id"], error_seq, "run.error", error)

    finished_seq = error_seq + 1
    finished = {
        "seq": finished_seq,
        "t": seconds,
        "type": "run.finished",
        "status": "failed",
        "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"],
        "tokens_reasoning": row["tokens_reasoning"],
        "wall_ms": row["wall_ms"],
    }
    await record_event(conn, row["id"], finished_seq, "run.finished", finished)
