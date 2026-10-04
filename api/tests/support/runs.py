"""Sending a message through the API, and watching its run settle and its events."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient
from tests.conftest import Run
from tests.support.auth import bearer

CONVERSATIONS = "/api/v1/conversations"


def send(client: TestClient, token: str, conversation: str, text: str) -> Any:
    url = f"{CONVERSATIONS}/{conversation}/messages"

    return client.post(url, headers=bearer(token), json={"text": text})


def settled(sql: Run, run_id: str) -> str:
    deadline = time.monotonic() + 30

    while time.monotonic() < deadline:
        rows = sql("SELECT r.status FROM runs r WHERE r.external_id = %(id)s", {"id": run_id})
        if rows[0][0] != "running":
            return str(rows[0][0])
        time.sleep(0.05)

    raise AssertionError("the run never finished")


def events_of(sql: Run, run_id: str) -> list[dict[str, Any]]:
    rows = sql(
        """
        SELECT e.event
          FROM run_events e
          JOIN runs r
            ON r.id = e.run_id
         WHERE r.external_id = %(id)s
         ORDER BY e.seq
        """,
        {"id": run_id},
    )

    return [row[0] for row in rows]
