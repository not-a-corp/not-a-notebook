"""Runs that execute cells with no model: one cell you run, or Run all.

    run.started → kernel → cell.output… → cell.finished → cells.stale → run.finished

Running a cell runs that cell only, in the live kernel — Jupyter semantics
(decision 10) — and marks the cells below it that had run as stale. Run all
restarts the kernel and runs every cell in order, stopping at the first error;
the cells it gets past are fresh again, the ones after an error are stale.

A cell's own code raising is not the run failing: the run did its job, and the
error is the cell's output. The run fails only for what is not the code's fault.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agent.loop import Meter, output_event
from app.db.cells import (
    begin_execution,
    cells_have_run,
    cells_in_order,
    describe_cell,
    finish_attempt,
    mark_stale_below,
)
from app.db.runs import RunStatus, StartedRun
from app.domain.agent import CellRef, CellStatus, Emit
from app.domain.runtime import ErrorOutput, KernelDied, Output
from app.jobs.kernels import ConversationKernels
from app.jobs.run import RunJob, RunKind, run_job
from app.jobs.services import Services

log = logging.getLogger(__name__)

DIED = ErrorOutput(
    name="KernelDied",
    value="The kernel died while running this cell — out of memory, most likely.",
    traceback=[],
)


@dataclass(frozen=True)
class CellJob:
    run: StartedRun
    conversation_id: UUID
    folder: str
    # The cell to run; None for Run all.
    cell: CellRef | None = None
    source: str = ""


@dataclass(frozen=True)
class Executed:
    """How one cell's execution ended, in the run's terms."""

    status: CellStatus
    run_status: RunStatus


async def run_cells_in_background(services: Services, job: CellJob) -> None:
    kind: RunKind = "cell"
    if job.cell is None:
        kind = "run_all"

    frame = RunJob(
        run_row_id=job.run.run_row_id,
        run_id=job.run.run_id,
        conversation_id=job.conversation_id,
        kind=kind,
    )

    async def work(emit: Emit, stop: asyncio.Event, meter: Meter) -> RunStatus:
        if job.cell is None:
            return await run_all(services, job, emit, stop)

        return await run_one(services, job, job.cell, emit)

    await run_job(services, frame, work)


async def run_one(services: Services, job: CellJob, cell: CellRef, emit: Emit) -> RunStatus:
    kernels = await conversation_kernels(services, job, emit)

    executed = await execute(services, kernels, cell, job.source, emit)
    await announce_stale(services, job, cell, emit)

    return executed.run_status


async def run_all(
    services: Services,
    job: CellJob,
    emit: Emit,
    stop: asyncio.Event,
) -> RunStatus:
    # From nothing: the reproducibility button (decision 10). The kernel's
    # restart is announced as run_all by the kernels that start the next one.
    await services.kernels.stop(job.conversation_id, reason="run_all")
    kernels = await conversation_kernels(services, job, emit)

    async with services.pool.connection() as conn:
        cells = await cells_in_order(conn, job.run.conversation_row_id)

    for cell, source in cells:
        if stop.is_set():
            return "cancelled"

        executed = await execute(services, kernels, cell, source, emit)

        if executed.status != "ok":
            await announce_stale(services, job, cell, emit)
            return executed.run_status

    return "succeeded"


async def conversation_kernels(services: Services, job: CellJob, emit: Emit) -> ConversationKernels:
    async with services.pool.connection() as conn:
        have_run = await cells_have_run(conn, job.run.conversation_row_id)

    kernels = ConversationKernels(
        services.kernels,
        services.store,
        job.conversation_id,
        job.folder,
        emit,
        have_run,
    )
    await kernels.current()

    return kernels


async def execute(
    services: Services,
    kernels: ConversationKernels,
    cell: CellRef,
    source: str,
    emit: Emit,
) -> Executed:
    async with services.pool.connection() as conn:
        await begin_execution(conn, cell)

    # A cell you run — or one of Run all's — has no attempt.started; this is
    # what tells a screen which cell is running now, and that its old outputs
    # are about to be replaced, even when it prints nothing.
    await emit("cell.started", {"cell_id": str(cell.id)})

    outputs: list[Output] = []

    async def collect(output: Output) -> None:
        outputs.append(output)
        await emit("cell.output", output_event(cell, None, output))

    kernel = await kernels.current()
    started = time.monotonic()

    try:
        result = await kernel.execute(source, collect)
    except KernelDied:
        await emit("kernel.restarted", {"reason": "died"})
        await services.kernels.stop(kernels.conversation_id)
        await collect(DIED)
        result = None

    duration_ms = int((time.monotonic() - started) * 1000)
    executed = executed_as(result)

    execution_count = None
    if result is not None:
        execution_count = result.execution_count

    async with services.pool.connection() as conn:
        await finish_attempt(conn, cell, outputs, executed.status, execution_count, duration_ms)
        shown = await describe_cell(conn, cell)

    finished = {
        "cell_id": str(cell.id),
        "status": executed.status,
        "attempts": shown["attempts"],
        "execution_count": execution_count,
        "duration_ms": duration_ms,
    }
    await emit("cell.finished", finished)

    return executed


def executed_as(result: Any) -> Executed:
    if result is None:
        return Executed(status="error", run_status="succeeded")

    if result.status == "ok":
        return Executed(status="ok", run_status="succeeded")

    if result.status == "cancelled":
        return Executed(status="cancelled", run_status="cancelled")

    if result.status == "timed_out":
        return Executed(status="error", run_status="timed_out")

    return Executed(status="error", run_status="succeeded")


async def announce_stale(services: Services, job: CellJob, cell: CellRef, emit: Emit) -> None:
    async with services.pool.connection() as conn:
        stale = await mark_stale_below(conn, job.run.conversation_row_id, cell.position)

    if stale:
        await emit("cells.stale", {"cell_ids": stale})
