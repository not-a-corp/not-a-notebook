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
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agent.loop import output_event
from app.core.cells import begin_execution, describe_cell, finish_attempt
from app.core.notebook_cells import StartedRun, cells_in_order, mark_stale_below
from app.core.profile_file import cells_have_run
from app.core.run_records import RunStatus, finish_run
from app.domain.agent import CellRef, CellStatus, Emit
from app.domain.errors import SandboxUnavailable
from app.domain.llm import Usage
from app.domain.runtime import ErrorOutput, KernelDied, Output
from app.runs.events import RunEvents
from app.runs.kernels import ConversationKernels
from app.runs.services import Services

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
    emit = RunEvents(services.pool, services.broadcast, job.run.run_row_id)
    control = services.controls.open(job.run.run_id, job.conversation_id)

    try:
        async with services.kernels.hold(job.conversation_id):
            status = await run_cells(services, job, emit, control.stop)
    finally:
        services.controls.close(job.run.run_id)

    async with services.pool.connection() as conn:
        finished = await finish_run(conn, job.run.run_row_id, status, Usage())

    summary = {
        "status": status,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_reasoning": 0,
        "wall_ms": finished.wall_ms,
    }
    await emit("run.finished", summary)


async def run_cells(
    services: Services,
    job: CellJob,
    emit: Emit,
    stop: asyncio.Event,
) -> RunStatus:
    kind = "cell"
    if job.cell is None:
        kind = "run_all"

    started = {
        "run_id": str(job.run.run_id),
        "conversation_id": str(job.conversation_id),
        "kind": kind,
        "model": None,
    }
    await emit("run.started", started)

    try:
        if job.cell is None:
            return await run_all(services, job, emit, stop)

        return await run_one(services, job, job.cell, emit)
    except SandboxUnavailable:
        await run_error(emit, "SANDBOX_UNAVAILABLE", "A kernel could not be started.")
    except Exception:
        error_id = str(uuid.uuid4())
        log.exception(
            "run %(run_id)s failed: %(error_id)s", {"run_id": job.run.run_id, "error_id": error_id}
        )
        await run_error(emit, "INTERNAL_ERROR", "Something went wrong.", error_id)

    return "failed"


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


async def run_error(emit: Emit, code: str, message: str, error_id: str | None = None) -> None:
    payload: dict[str, Any] = {"code": code, "message": message, "error_id": error_id}
    await emit("run.error", payload)
