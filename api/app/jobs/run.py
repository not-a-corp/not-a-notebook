"""What every run does around its own work: the same frame for a message, a
profile, a cell or Run all (events.md).

    run.started → the job's own work → [run.error] → run.finished

The frame opens the run's control (so it can be cancelled), holds the kernel (so
it is not reaped mid-run), numbers and stores every event, turns whatever breaks
into the run.error that names it, closes the run row, and emits run.finished —
always last, whatever happened. A job only says what it does and how it ended.

The one exception is shutdown: a run cancelled because the process is stopping
emits nothing more, and is closed as failed on the next startup.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.agent.loop import Meter, ModelRefused, RunCancelled, StepLimit
from app.db.runs import RunStatus, finish_run
from app.domain.agent import Emit
from app.domain.errors import ModelNotFound, SandboxUnavailable
from app.domain.llm import ProviderError
from app.jobs.events import RunEvents
from app.jobs.services import Services

log = logging.getLogger(__name__)

type RunKind = Literal["message", "profile", "cell", "run_all"]

# The job's own work: given the stream, the stop signal and the token meter, it
# returns how the run ended. Whatever it raises, the frame turns into run.error.
type Work = Callable[[Emit, asyncio.Event, Meter], Awaitable[RunStatus]]


@dataclass(frozen=True)
class RunJob:
    run_row_id: int
    run_id: UUID
    conversation_id: UUID
    kind: RunKind
    # The model's name for a message run; None for runs that ask no model.
    model: str | None = None


async def run_job(services: Services, job: RunJob, work: Work) -> None:
    emit = RunEvents(services.pool, services.broadcast, job.run_row_id)
    meter = Meter()
    control = services.controls.open(job.run_id, job.conversation_id)

    try:
        async with services.kernels.hold(job.conversation_id):
            started = {
                "run_id": str(job.run_id),
                "conversation_id": str(job.conversation_id),
                "kind": job.kind,
                "model": job.model,
            }
            await emit("run.started", started)

            status = await guarded(work, job, emit, control.stop, meter)
    finally:
        services.controls.close(job.run_id)

    async with services.pool.connection() as conn:
        finished = await finish_run(conn, job.run_row_id, status, meter.usage)

    summary = {
        "status": status,
        "tokens_in": meter.usage.input_tokens,
        "tokens_out": meter.usage.output_tokens,
        "tokens_reasoning": meter.usage.reasoning_tokens,
        "wall_ms": finished.wall_ms,
    }
    await emit("run.finished", summary)


async def guarded(
    work: Work,
    job: RunJob,
    emit: Emit,
    stop: asyncio.Event,
    meter: Meter,
) -> RunStatus:
    """The job's status — or, when it raised, `failed` after the run.error that
    says what is not the code's fault (events.md's table)."""
    details = {"run_id": job.run_id}

    try:
        return await work(emit, stop, meter)
    except RunCancelled:
        return "cancelled"
    except ProviderError as exc:
        log.warning("run %(run_id)s: the provider failed", details)
        await run_error(emit, "MODEL_UNAVAILABLE", f"The provider answered: {exc}")
    except ModelNotFound:
        await run_error(emit, "MODEL_UNAVAILABLE", "The conversation's model was removed.")
    except ModelRefused:
        await run_error(emit, "MODEL_REFUSED", "The model's safety system declined.")
    except StepLimit:
        await run_error(emit, "STEP_LIMIT", "The model kept running code without answering.")
    except SandboxUnavailable:
        await run_error(emit, "SANDBOX_UNAVAILABLE", "A kernel could not be started.")
    except Exception:
        error_id = str(uuid.uuid4())
        failure = {"run_id": job.run_id, "error_id": error_id}
        log.exception("run %(run_id)s failed: %(error_id)s", failure)
        await run_error(emit, "INTERNAL_ERROR", "Something went wrong.", error_id)

    return "failed"


async def run_error(emit: Emit, code: str, message: str, error_id: str | None = None) -> None:
    payload: dict[str, Any] = {"code": code, "message": message, "error_id": error_id}
    await emit("run.error", payload)
