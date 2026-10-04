"""The profiling run, from the stored file to its profile (events.md):

    run.started → file.uploaded → kernel → file.profiled → run.finished

Takes connections from the pool only to read and write: holding one through a
kernel start and a profile would tie up a pool slot for seconds or minutes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.core.profile_file import cells_have_run, read_profile, store_profile
from app.core.run_records import RunStatus, finish_run
from app.core.upload_file import ProfileJob
from app.domain.agent import Emit
from app.domain.errors import SandboxUnavailable
from app.domain.llm import Usage
from app.domain.runtime import KernelDied
from app.runs.events import RunEvents
from app.runs.kernels import ConversationKernels
from app.runtime.registry import KernelRegistry

log = logging.getLogger(__name__)


async def profile_in_background(
    pool: AsyncConnectionPool,
    kernels: KernelRegistry,
    job: ProfileJob,
) -> None:
    emit = RunEvents(pool, job.run_id)

    status = await profile(pool, kernels, job, emit)

    async with pool.connection() as conn:
        finished = await finish_run(conn, job.run_id, status, Usage())

    summary = {
        "status": status,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_reasoning": 0,
        "wall_ms": finished.wall_ms,
    }
    await emit("run.finished", summary)


async def profile(
    pool: AsyncConnectionPool,
    registry: KernelRegistry,
    job: ProfileJob,
    emit: Emit,
) -> RunStatus:
    started = {
        "run_id": str(job.run_external_id),
        "conversation_id": str(job.conversation_id),
        "kind": "profile",
        "model": None,
    }
    await emit("run.started", started)
    await emit("file.uploaded", {"file": job.file.model_dump(mode="json")})

    details = {"run_id": job.run_id}

    try:
        async with pool.connection() as conn:
            have_run = await cells_have_run(conn, job.conversation_row_id)

        kernels = ConversationKernels(registry, job.conversation_id, job.folder, emit, have_run)
        kernel = await kernels.current()
        profile = await read_profile(kernel, job.name)
    except SandboxUnavailable:
        await run_error(emit, "SANDBOX_UNAVAILABLE", "A kernel could not be started.")
        return "failed"
    except KernelDied:
        # Forgotten, so the conversation's next run starts a fresh kernel.
        log.warning("run %(run_id)s: the kernel died while profiling", details)
        await emit("kernel.restarted", {"reason": "died"})
        await registry.stop(job.conversation_id)
        return "failed"
    except Exception:
        error_id = str(uuid.uuid4())
        log.exception("run %(run_id)s: profiling failed", details)
        await run_error(emit, "INTERNAL_ERROR", "Something went wrong.", error_id)
        return "failed"

    async with pool.connection() as conn:
        await store_profile(conn, job.file_id, profile)

    await emit("file.profiled", {"file_id": str(job.file.id), "profile": profile})

    return "succeeded"


async def run_error(emit: Emit, code: str, message: str, error_id: str | None = None) -> None:
    payload: dict[str, Any] = {"code": code, "message": message, "error_id": error_id}
    await emit("run.error", payload)
