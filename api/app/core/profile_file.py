"""Profiling a file in its conversation's kernel, and recording the outcome.

The profiler lives in the sandbox image (sandbox/kernel/not_a_notebook_profile.py)
and runs next to the data; what comes back is the profile, never the rows. It is
run with store_history=False: the user's execution counter and In/Out stay as if
nothing happened.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.domain.runtime import Kernel, Output, StreamOutput


class ProfilingFailed(Exception):
    """The profiler itself broke — not the file, which is a profile like any other."""


async def read_profile(kernel: Kernel, name: str) -> dict[str, Any]:
    # repr() quotes the path for Python whatever the name holds; names are checked
    # on upload, this is the second line.
    path = f"/data/{name}"
    code = f"__import__('not_a_notebook_profile').emit({path!r})"

    printed: list[str] = []

    async def keep_stdout(output: Output) -> None:
        if isinstance(output, StreamOutput) and output.name == "stdout":
            printed.append(output.text)

    result = await kernel.execute(code, keep_stdout, store_history=False)

    if result.status != "ok":
        raise ProfilingFailed(f"the profiler ended with {result.status}")

    try:
        profile: dict[str, Any] = json.loads("".join(printed))
    except json.JSONDecodeError as exc:
        raise ProfilingFailed("the profiler printed something other than JSON") from exc

    return profile


async def finish_profile_run(
    conn: AsyncConnection[Any],
    run_id: int,
    file_id: int,
    profile: dict[str, Any] | None,
    status: Literal["succeeded", "failed"],
) -> None:
    profile_sql = """
        UPDATE files f
           SET profile = %(profile)s
         WHERE f.id = %(file_id)s
    """

    profile_params: dict[str, Any] = {
        "profile": Jsonb(profile),
        "file_id": file_id,
    }

    # Only a run still running is closed: one closed already — as abandoned, by a
    # restart — keeps the status it was given.
    run_sql = """
        UPDATE runs r
           SET status = %(status)s,
               finished_at = now()
         WHERE r.id = %(run_id)s
           AND r.status = 'running'
    """

    run_params: dict[str, Any] = {
        "status": status,
        "run_id": run_id,
    }

    async with conn.transaction():
        if profile is not None:
            await conn.execute(profile_sql, profile_params)

        await conn.execute(run_sql, run_params)
