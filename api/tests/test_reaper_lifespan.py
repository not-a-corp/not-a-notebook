"""The API reaps on its own: orphans as it starts, its kernels as it stops.

Kept apart from test_reaper.py because it drives the real lifespan through a
synchronous TestClient, which cannot run inside that module's event loop.
"""

from __future__ import annotations

import asyncio

from app.main import app
from app.runtime.docker_engine import DockerEngine
from fastapi.testclient import TestClient
from tests.test_reaper import StandIn, container_exists, me, stand_in_kernel


def make_stand_in() -> StandIn:
    async def make() -> StandIn:
        docker = DockerEngine.over_socket()
        try:
            return await stand_in_kernel(docker, me())
        finally:
            await docker.close()

    return asyncio.run(make())


def exists(stand_in: StandIn) -> bool:
    async def check() -> bool:
        docker = DockerEngine.over_socket()
        try:
            return await container_exists(docker, stand_in.container)
        finally:
            await docker.close()

    return asyncio.run(check())


def test_the_api_reaps_on_startup_and_on_shutdown() -> None:
    left_by_a_crash = make_stand_in()

    with TestClient(app):
        assert not exists(left_by_a_crash)

        started_while_up = make_stand_in()

    assert not exists(started_while_up)
