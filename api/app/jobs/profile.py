"""A profiling run's own work, from the stored file to its profile (events.md):

    file.uploaded → kernel → file.profiled

Takes connections from the pool only to read and write: holding one through a
kernel start and a profile would tie up a pool slot for seconds or minutes.
"""

from __future__ import annotations

import asyncio
import logging

from app.agent.loop import Meter
from app.core.files.profile_file import ProfilingFailed, read_profile, store_profile
from app.core.files.upload_file import ProfileJob
from app.db.cells import cells_have_run
from app.db.runs import RunStatus
from app.domain.agent import Emit
from app.domain.runtime import KernelDied
from app.jobs.kernels import ConversationKernels
from app.jobs.run import RunJob, run_job
from app.jobs.services import Services

log = logging.getLogger(__name__)


async def profile_in_background(services: Services, job: ProfileJob) -> None:
    frame = RunJob(
        run_row_id=job.run_id,
        run_id=job.run_external_id,
        conversation_id=job.conversation_id,
        kind="profile",
    )

    async def work(emit: Emit, stop: asyncio.Event, meter: Meter) -> RunStatus:
        return await profile(services, job, emit, stop)

    await run_job(services, frame, work)


async def profile(
    services: Services,
    job: ProfileJob,
    emit: Emit,
    stop: asyncio.Event,
) -> RunStatus:
    await emit("file.uploaded", {"file": job.file.model_dump(mode="json")})

    details = {"run_id": job.run_id}
    registry = services.kernels

    async with services.pool.connection() as conn:
        have_run = await cells_have_run(conn, job.conversation_row_id)

    kernels = ConversationKernels(
        registry, services.store, job.conversation_id, job.folder, emit, have_run
    )
    kernel = await kernels.current()

    try:
        profile = await read_profile(kernel, job.name)
    except ProfilingFailed:
        # Interrupted on request is a cancelled run; anything else is the
        # profiler breaking, which is ours — and the frame says so.
        if stop.is_set():
            return "cancelled"
        raise
    except KernelDied:
        # Forgotten, so the conversation's next run starts a fresh kernel.
        log.warning("run %(run_id)s: the kernel died while profiling", details)
        await emit("kernel.restarted", {"reason": "died"})
        await registry.stop(job.conversation_id)
        return "failed"

    async with services.pool.connection() as conn:
        await store_profile(conn, job.file_id, profile)

    await emit("file.profiled", {"file_id": str(job.file.id), "profile": profile})

    return "succeeded"
