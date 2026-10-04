"""A run, as its owner reads it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.domain.errors import RunNotFound
from app.domain.runs import RunView


@dataclass(frozen=True)
class FoundRun:
    row_id: int
    view: RunView


async def find_run(conn: AsyncConnection[Any], user_id: UUID, run_id: UUID) -> FoundRun:
    sql = """
        SELECT r.id AS row_id,
               r.external_id AS id,
               c.external_id AS conversation_id,
               r.kind,
               r.status,
               r.model_name,
               r.tokens_in,
               r.tokens_out,
               r.tokens_reasoning,
               r.started_at,
               r.finished_at,
               (extract(epoch FROM r.finished_at - r.started_at) * 1000)::int AS wall_ms
          FROM runs r
          JOIN conversations c
            ON c.id = r.conversation_id
          JOIN users u
            ON u.id = c.user_id
         WHERE u.external_id = %(user_id)s
           AND r.external_id = %(run_id)s
    """

    params = {
        "user_id": user_id,
        "run_id": run_id,
    }

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    if row is None:
        raise RunNotFound

    view = RunView(
        id=row["id"],
        conversation_id=row["conversation_id"],
        kind=row["kind"],
        status=row["status"],
        model=row["model_name"],
        tokens_in=row["tokens_in"],
        tokens_out=row["tokens_out"],
        tokens_reasoning=row["tokens_reasoning"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        wall_ms=row["wall_ms"],
    )

    return FoundRun(row_id=row["row_id"], view=view)
