"""The profiling run, from kernel to recorded outcome.

Takes connections from the pool only to write the result: holding one through
a kernel start and a profile would tie up a pool slot for seconds or minutes.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from psycopg_pool import AsyncConnectionPool

from app.core.profile_file import finish_profile_run, read_profile
from app.core.upload_file import ProfileJob
from app.domain.errors import SandboxUnavailable
from app.domain.runtime import KernelDied
from app.runtime.registry import KernelRegistry

log = logging.getLogger(__name__)


async def profile_in_background(
    pool: AsyncConnectionPool,
    kernels: KernelRegistry,
    job: ProfileJob,
) -> None:
    profile: dict[str, Any] | None = None
    status: Literal["succeeded", "failed"] = "failed"
    details = {"run_id": job.run_id}

    try:
        kernel = await kernels.kernel_for(job.conversation_id, job.folder)
        profile = await read_profile(kernel, job.name)
        status = "succeeded"
    except SandboxUnavailable:
        log.warning("run %(run_id)s: no kernel could be started", details)
    except KernelDied:
        # Forgotten, so the conversation's next run starts a fresh kernel.
        log.warning("run %(run_id)s: the kernel died while profiling", details)
        await kernels.stop(job.conversation_id)
    except Exception:
        log.exception("run %(run_id)s: profiling failed", details)

    async with pool.connection() as conn:
        await finish_profile_run(conn, job.run_id, job.file_id, profile, status)
