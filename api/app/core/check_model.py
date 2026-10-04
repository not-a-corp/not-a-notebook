"""Does this model work here? One short request for one short piece of code, in
the model's own dialect — the button behind the models screen.

A model that fails is still an answer: the test ran, and its result is what the
user asked for. Only a model that does not exist is an error.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.domain.llm import Model, ProviderError, UserText
from app.domain.model_configs import Dialect

SYSTEM = (
    "You are being checked by a data analysis tool before it relies on you. Do exactly "
    "what the user asks, as briefly as possible."
)

QUESTIONS: dict[Dialect, str] = {
    "tools": "Use the run_python tool to print 6 * 7. Call the tool; do not answer in text.",
    "text": "Write Python that prints 6 * 7, in one ```python fenced block, and nothing else.",
}

MISSES: dict[Dialect, str] = {
    "tools": "the model answered without calling the tool",
    "text": "the model answered without a ```python block",
}


@dataclass(frozen=True)
class ModelCheck:
    ok: bool
    latency_ms: int
    error: str | None


async def check_model(model: Model, dialect: Dialect) -> ModelCheck:
    async def ignore(text: str) -> None:
        pass

    question = UserText(QUESTIONS[dialect])
    started = time.monotonic()

    try:
        reply = await model.complete(SYSTEM, [question], ignore)
    except ProviderError as exc:
        latency_ms = elapsed_ms(started)
        return ModelCheck(ok=False, latency_ms=latency_ms, error=str(exc))

    latency_ms = elapsed_ms(started)

    if reply.stop == "refusal":
        return ModelCheck(ok=False, latency_ms=latency_ms, error="the model refused")

    if reply.turn.code is None:
        return ModelCheck(ok=False, latency_ms=latency_ms, error=MISSES[dialect])

    return ModelCheck(ok=True, latency_ms=latency_ms, error=None)


def elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
