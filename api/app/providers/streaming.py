"""The HTTP every adapter shares: one streaming POST, retried only while nothing
has been read, and Server-Sent Events parsed out of it.

A retry after the first byte would replay a reply the user has partly seen, so
there is none: a stream that breaks halfway is a ProviderError, and the run
decides what to do with it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx2

from app.domain.llm import ProviderError, ProviderErrorKind

# Thinking models can be silent for minutes before the first token; the read
# timeout is per chunk, not for the whole reply.
TIMEOUT = httpx2.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

RETRIES = 2

DONE = "[DONE]"
RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_RETRY_AFTER_SECONDS = 20.0


@dataclass(frozen=True)
class Event:
    """One Server-Sent Event. `name` is the `event:` line, empty when there was none."""

    name: str
    data: str

    def json(self) -> dict[str, Any]:
        try:
            parsed: dict[str, Any] = json.loads(self.data)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "protocol", f"an event that is not JSON: {self.data[:200]}"
            ) from exc

        return parsed


@asynccontextmanager
async def open_stream(
    http: httpx2.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
) -> AsyncIterator[httpx2.Response]:
    """A response whose status was 2xx, ready to be read as it arrives."""
    attempt = 0

    while True:
        attempt += 1
        request = http.build_request("POST", url, headers=headers, json=body, timeout=TIMEOUT)

        try:
            response = await http.send(request, stream=True)
        except httpx2.HTTPError as exc:
            if attempt <= RETRIES:
                await asyncio.sleep(backoff(attempt, None))
                continue

            raise ProviderError("network", f"could not reach {url}: {exc!r}") from exc

        if response.status_code < 300:
            break

        body_text = (await response.aread()).decode(errors="replace")
        await response.aclose()

        if response.status_code in RETRY_STATUSES and attempt <= RETRIES:
            retry_after = response.headers.get("retry-after")
            await asyncio.sleep(backoff(attempt, retry_after))
            continue

        raise error_from(response.status_code, body_text)

    try:
        yield response
    finally:
        await response.aclose()


async def events(response: httpx2.Response) -> AsyncIterator[Event]:
    """The stream as events: `event:` and `data:` lines up to each blank line.

    Comments (`: keepalive`) are skipped, and a multi-line `data:` is joined the
    way the SSE specification says — with newlines. `data: [DONE]` ends the
    stream: Chat Completions sends it, and routers append it to the other APIs'
    streams too, where the provider's own API would just stop.
    """
    name = ""
    data: list[str] = []

    try:
        async for line in response.aiter_lines():
            if line == "":
                joined = "\n".join(data)
                if joined == DONE:
                    return
                if data:
                    yield Event(name=name, data=joined)
                name = ""
                data = []
                continue

            if line.startswith(":"):
                continue

            field, _, value = line.partition(":")
            value = value.removeprefix(" ")

            if field == "event":
                name = value
            elif field == "data":
                data.append(value)
    except httpx2.HTTPError as exc:
        raise ProviderError("network", f"the stream broke: {exc!r}") from exc

    joined = "\n".join(data)
    if data and joined != DONE:
        yield Event(name=name, data=joined)


def backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None:
        try:
            seconds = float(retry_after)
        except ValueError:
            seconds = 0.0

        if 0 < seconds <= MAX_RETRY_AFTER_SECONDS:
            return seconds

    return float(2 ** (attempt - 1))


def error_from(status: int, body: str) -> ProviderError:
    """The provider's own message, as close to its words as can be found."""
    message = body[:500]

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message = error["message"]
        elif isinstance(error, str):
            message = error

    return ProviderError(kind_of(status), message, status=status)


def kind_of(status: int) -> ProviderErrorKind:
    if status in (401, 403):
        return "auth"

    if status == 429:
        return "rate_limit"

    if status == 529:
        return "overloaded"

    if status >= 500:
        return "unavailable"

    return "bad_request"
