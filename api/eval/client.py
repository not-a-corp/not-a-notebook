"""The API, as a user's browser uses it — the minimum the eval needs of it."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx2


class EvalError(Exception):
    pass


class Api:
    def __init__(self, base_url: str) -> None:
        self.http = httpx2.Client(base_url=base_url, timeout=60)
        self.headers: dict[str, str] = {}

    def sign_in(self, email: str, password: str) -> None:
        response = self.http.post("/auth/login", json={"email": email, "password": password})
        self.check(response)

        self.use_token(response.json()["access_token"])

    def use_token(self, token: str) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}

    def check(self, response: httpx2.Response) -> None:
        if response.status_code >= 400:
            raise EvalError(f"{response.request.method} {response.request.url}: {response.text}")

    def model_id(self, name: str) -> str:
        response = self.http.get("/models", headers=self.headers)
        self.check(response)

        for model in response.json()["data"]:
            if name in (model["id"], model["name"]):
                return str(model["id"])

        raise EvalError(f"no model called {name!r}")

    def create_conversation(self, title: str, model_id: str) -> str:
        body = {"title": title, "model_id": model_id}
        response = self.http.post("/conversations", headers=self.headers, json=body)
        self.check(response)

        return str(response.json()["id"])

    def delete_conversation(self, conversation_id: str) -> None:
        response = self.http.delete(f"/conversations/{conversation_id}", headers=self.headers)
        self.check(response)

    def upload(self, conversation_id: str, path: Path) -> str:
        files = {"file": (path.name, path.read_bytes())}
        response = self.http.post(
            f"/conversations/{conversation_id}/files", headers=self.headers, files=files
        )
        self.check(response)

        return str(response.json()["run_id"])

    def ask(self, conversation_id: str, text: str) -> str:
        response = self.http.post(
            f"/conversations/{conversation_id}/messages",
            headers=self.headers,
            json={"text": text},
        )
        self.check(response)

        return str(response.json()["run_id"])

    def wait(self, run_id: str, seconds: float) -> str:
        deadline = time.monotonic() + seconds

        while time.monotonic() < deadline:
            response = self.http.get(f"/runs/{run_id}", headers=self.headers)
            self.check(response)

            status = str(response.json()["status"])
            if status != "running":
                return status

            time.sleep(2)

        return "timed_out"

    def events(self, run_id: str) -> list[dict[str, Any]]:
        """A finished run's events, replayed whole: the stream closes after
        run.finished."""
        events: list[dict[str, Any]] = []

        with self.http.stream("GET", f"/runs/{run_id}/events", headers=self.headers) as response:
            for line in response.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data:")))

        return events
