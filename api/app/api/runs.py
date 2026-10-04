"""A run: its record, and its events as a stream."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Response, status
from fastapi.responses import StreamingResponse

from app.core.runs import find_run
from app.dependencies import Caller, Controls, Db, Kernels, Live, Pool
from app.domain.runs import RunView
from app.runs.stream import resume_after, stream

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}")
async def get(run_id: UUID, caller: Caller, conn: Db) -> RunView:
    found = await find_run(conn, caller, run_id)

    return found.view


@router.get("/{run_id}/events")
async def events(
    run_id: UUID,
    caller: Caller,
    conn: Db,
    pool: Pool,
    live: Live,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    # The owner is checked here, before the stream starts: a 404 must leave as
    # JSON, and nothing can be sent once events are flowing.
    found = await find_run(conn, caller, run_id)
    after = resume_after(last_event_id)

    # Nothing between the API and the client may hold events back to batch them.
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(
        stream(pool, live, found.row_id, after),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel(
    run_id: UUID,
    caller: Caller,
    conn: Db,
    controls: Controls,
    kernels: Kernels,
) -> Response:
    # Found first, so someone else's run is a 404 like everywhere. A run that
    # already finished is a 202 that changes nothing.
    await find_run(conn, caller, run_id)
    await controls.cancel(run_id, kernels)

    return Response(status_code=status.HTTP_202_ACCEPTED)
