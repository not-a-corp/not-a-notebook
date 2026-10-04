"""The notebook, by hand: cells you write, edit, delete and run; Run all; and
throwing the kernel's state away."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.core.cells.create_cell import create_user_cell
from app.core.cells.delete_cell import delete_cell
from app.core.cells.edit_cell import edit_cell
from app.core.cells.restart_kernel import restart_kernel
from app.core.cells.run_all import start_run_all
from app.core.cells.run_cell import start_cell_run
from app.dependencies import Caller, Db, Jobs, Work
from app.domain.cells import CreateCellRequest, EditCellRequest, RunAccepted
from app.domain.files import conversation_folder
from app.jobs.cells import CellJob, run_cells_in_background

router = APIRouter(tags=["cells"])


@router.post("/conversations/{conversation_id}/cells", status_code=status.HTTP_201_CREATED)
async def create(
    conversation_id: UUID,
    payload: CreateCellRequest,
    caller: Caller,
    conn: Db,
) -> dict[str, Any]:
    # Left out and null are two different places: the end, and the top.
    at_end = "after_cell_id" not in payload.model_fields_set

    return await create_user_cell(
        conn,
        caller,
        conversation_id,
        source=payload.source,
        after=payload.after_cell_id,
        at_end=at_end,
    )


@router.patch("/cells/{cell_id}")
async def edit(cell_id: UUID, payload: EditCellRequest, caller: Caller, conn: Db) -> dict[str, Any]:
    return await edit_cell(conn, caller, cell_id, payload.source)


@router.delete("/cells/{cell_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(cell_id: UUID, caller: Caller, conn: Db) -> Response:
    await delete_cell(conn, caller, cell_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/cells/{cell_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run(cell_id: UUID, caller: Caller, conn: Db, work: Work, jobs: Jobs) -> RunAccepted:
    started = await start_cell_run(conn, caller, cell_id)
    cell = started.cell

    job = CellJob(
        run=started.run,
        conversation_id=cell.conversation_id,
        folder=conversation_folder(caller, cell.conversation_id),
        cell=cell.ref,
        source=cell.source,
    )
    jobs.spawn(run_cells_in_background(work, job))

    return RunAccepted(run_id=started.run.run_id)


@router.post("/conversations/{conversation_id}/run-all", status_code=status.HTTP_202_ACCEPTED)
async def run_all(
    conversation_id: UUID,
    caller: Caller,
    conn: Db,
    work: Work,
    jobs: Jobs,
) -> RunAccepted:
    started = await start_run_all(conn, caller, conversation_id)

    job = CellJob(
        run=started,
        conversation_id=conversation_id,
        folder=conversation_folder(caller, conversation_id),
    )
    jobs.spawn(run_cells_in_background(work, job))

    return RunAccepted(run_id=started.run_id)


@router.post(
    "/conversations/{conversation_id}/kernel/restart",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def restart(conversation_id: UUID, caller: Caller, conn: Db, work: Work) -> Response:
    await restart_kernel(conn, work.kernels, caller, conversation_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
