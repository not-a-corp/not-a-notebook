"""The database answers a query."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection


async def check_database(conn: AsyncConnection[Any]) -> None:
    sql = """
        SELECT 1
    """

    await conn.execute(sql)
