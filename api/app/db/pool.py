"""The PostgreSQL connection pool.

Created closed so the caller decides when to connect; ``app.main`` opens it on
startup and closes it on shutdown.
"""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


def create_pool(dsn: str) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=10,
        open=False,
        # Autocommit, so a write lands while the route is still running.
        # FastAPI tears a dependency with `yield` down *after* the response has
        # gone out, so committing there is too late: a client that fires its
        # next request immediately could reach a different pooled connection
        # and not see the row yet.
        #
        # Whatever needs more than one statement to land together says so with
        # `conn.transaction()` in the use case.
        kwargs={"row_factory": dict_row, "autocommit": True},
    )
