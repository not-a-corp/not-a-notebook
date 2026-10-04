"""Liveness: the service is up and can reach the database."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.check_database import check_database

router = APIRouter(tags=["operations"])

# Short on purpose. A health check that hangs is worse than one that fails: the
# caller is asking whether the database is reachable *now*, not waiting for the
# pool to exhaust its own patience. That is also why this route takes its
# connection by hand instead of through `Db`, which waits as long as the pool does.
CONNECT_TIMEOUT_SECONDS = 2.0


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    pool = request.app.state.pool

    async with pool.connection(timeout=CONNECT_TIMEOUT_SECONDS) as conn:
        await check_database(conn)

    return {"status": "ok"}
