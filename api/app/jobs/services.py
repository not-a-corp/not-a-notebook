"""What every run takes from the process, as the lifespan built it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import httpx2
from psycopg_pool import AsyncConnectionPool

from app.domain.files import FileStore
from app.jobs.broadcast import Broadcast
from app.jobs.control import RunControls
from app.runtime.registry import KernelRegistry
from app.security.secrets import Cipher


@dataclass(frozen=True)
class Services:
    """What a run takes from the process, as the lifespan built it."""

    pool: AsyncConnectionPool
    broadcast: Broadcast
    kernels: KernelRegistry
    controls: RunControls
    store: FileStore
    http: httpx2.AsyncClient
    cipher: Cipher
    environment_keys: Mapping[str, str | None]
