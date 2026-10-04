"""The agent's Notebook protocol over the cells table — a connection per write,
none held while the model thinks or the kernel runs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.db import cells
from app.domain.agent import CellRef, CellStatus
from app.domain.runtime import Output


class StoredNotebook:
    def __init__(
        self, pool: AsyncConnectionPool, conversation_row_id: int, run_row_id: int
    ) -> None:
        self.pool = pool
        self.conversation_row_id = conversation_row_id
        self.run_row_id = run_row_id

    async def create_cell(self, source: str) -> CellRef:
        async with self.pool.connection() as conn:
            return await cells.create_agent_cell(
                conn, self.conversation_row_id, self.run_row_id, source
            )

    async def rewrite_cell(self, cell: CellRef, source: str, attempt: int) -> None:
        async with self.pool.connection() as conn:
            await cells.rewrite_cell(conn, cell, source, attempt)

    async def finish_attempt(
        self,
        cell: CellRef,
        outputs: Sequence[Output],
        status: CellStatus,
        execution_count: int | None,
        duration_ms: int,
    ) -> None:
        async with self.pool.connection() as conn:
            await cells.finish_attempt(conn, cell, outputs, status, execution_count, duration_ms)

    async def describe(self, cell: CellRef) -> dict[str, Any]:
        async with self.pool.connection() as conn:
            return await cells.describe_cell(conn, cell)
