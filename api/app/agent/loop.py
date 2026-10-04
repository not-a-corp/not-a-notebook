"""The agent's turn: ask the model, run its code, show it the result, repeat until
it answers (decision 4).

    for each step:
        the model reads the history → words, code, a question
        code     → a cell runs it; its output goes back into the history
        question → the turn ends, waiting for the user
        words    → the turn ends with the answer

A failed attempt is retried in the same cell (decision 18): code proposed right
after an error rewrites that cell, up to MAX_ATTEMPTS, so the notebook keeps the
version that worked. Every attempt is still in the events.

Pure: it gets the model, the kernel, the notebook and the stream as protocols,
and owns none of them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from app.agent.outputs import as_text, fields_of, kind_of
from app.domain.agent import CellRef, CellStatus, Emit, Kernels, Notebook
from app.domain.llm import Item, Model, Reply, ToolResult, Usage
from app.domain.runtime import ExecutionResult, KernelDied, OnOutput, Output

MAX_STEPS = 25
MAX_ATTEMPTS = 3

DIED = (
    "The kernel died while running this — out of memory, most likely. Everything it "
    "held is gone; the next code runs in a fresh kernel. Load only what you need."
)


class ModelRefused(Exception):
    """The model's safety system declined."""


class StepLimit(Exception):
    """The model kept running code without ever answering."""


@dataclass
class Meter:
    """Tokens spent so far. The caller holds it, so what a turn spent is known
    even when the turn ends in an exception."""

    usage: Usage = field(default_factory=Usage)

    def add(self, more: Usage) -> None:
        self.usage = Usage(
            input_tokens=self.usage.input_tokens + more.input_tokens,
            output_tokens=self.usage.output_tokens + more.output_tokens,
            reasoning_tokens=self.usage.reasoning_tokens + more.reasoning_tokens,
        )


@dataclass
class Outcome:
    kind: Literal["answer", "question"]
    text: str
    # Everything the turn's code produced, as text: what grounding checks the
    # answer's numbers against.
    produced: list[str] = field(default_factory=list)


@dataclass
class Turn:
    """What every step of one turn shares."""

    kernels: Kernels
    notebook: Notebook
    emit: Emit
    history: list[Item]
    produced: list[str] = field(default_factory=list)


@dataclass
class Retry:
    """The cell whose last attempt failed, open for the next one."""

    cell: CellRef
    attempts: int


async def run_turn(
    model: Model,
    kernels: Kernels,
    system: str,
    history: list[Item],
    notebook: Notebook,
    emit: Emit,
    meter: Meter,
) -> Outcome:
    turn = Turn(kernels=kernels, notebook=notebook, emit=emit, history=history)
    retry: Retry | None = None

    for step in range(1, MAX_STEPS + 1):
        reply = await ask(model, system, history, step, emit)
        meter.add(reply.usage)
        history.append(reply.turn)

        if reply.stop == "refusal":
            raise ModelRefused

        if reply.stop == "question" and reply.question is not None:
            return Outcome(kind="question", text=reply.question, produced=turn.produced)

        code = reply.turn.code
        if code is None:
            return Outcome(kind="answer", text=reply.turn.text, produced=turn.produced)

        retry = await attempt(turn, code, reply, step, retry)

    raise StepLimit


async def ask(model: Model, system: str, history: list[Item], step: int, emit: Emit) -> Reply:
    await emit("llm.started", {"step": step})
    started = time.monotonic()

    async def delta(text: str) -> None:
        await emit("llm.delta", {"step": step, "text": text})

    reply = await model.complete(system, history, delta)

    finished = {
        "step": step,
        "stop": reply.stop,
        "tokens_in": reply.usage.input_tokens,
        "tokens_out": reply.usage.output_tokens,
        "tokens_reasoning": reply.usage.reasoning_tokens,
        "ms": elapsed_ms(started),
    }
    await emit("llm.finished", finished)

    return reply


async def attempt(
    turn: Turn,
    code: str,
    reply: Reply,
    step: int,
    retry: Retry | None,
) -> Retry | None:
    """Runs the code in a new cell, or in the failed one; returns the cell left
    open for a retry, if this attempt failed and has tries left."""
    emit = turn.emit

    if retry is not None:
        cell = retry.cell
        number = retry.attempts + 1
        await turn.notebook.rewrite_cell(cell, code, number)
    else:
        cell = await turn.notebook.create_cell(code)
        number = 1

    proposed = {"step": step, "cell_id": str(cell.id), "attempt": number, "code": code}
    await emit("code.proposed", proposed)

    if number == 1:
        await emit("cell.created", {"cell": await turn.notebook.describe(cell)})

    await emit("attempt.started", {"cell_id": str(cell.id), "attempt": number})

    outputs: list[Output] = []

    async def collect(output: Output) -> None:
        outputs.append(output)
        await emit("cell.output", output_event(cell, number, output))

    started = time.monotonic()
    result = await run(code, collect, turn.kernels, emit)
    duration_ms = elapsed_ms(started)
    status = attempt_status(result)

    finished = {
        "cell_id": str(cell.id),
        "attempt": number,
        "status": status,
        "execution_count": execution_count(result),
        "duration_ms": duration_ms,
    }
    await emit("attempt.finished", finished)

    read_back = as_text(outputs, result)
    turn.produced.append(read_back)
    if result is None:
        read_back = DIED

    is_error = status != "ok"
    result_item = ToolResult(call_id=reply.turn.call_id, content=read_back, is_error=is_error)
    turn.history.append(result_item)

    # A dead kernel is not retried in place: what the cell needed is gone with it.
    open_again = is_error and number < MAX_ATTEMPTS and result is not None
    cell_status = cell_status_of(status)

    await turn.notebook.finish_attempt(
        cell, outputs, cell_status, execution_count(result), duration_ms
    )

    if open_again:
        return Retry(cell=cell, attempts=number)

    cell_finished = {
        "cell_id": str(cell.id),
        "status": cell_status,
        "attempts": number,
        "execution_count": execution_count(result),
        "duration_ms": duration_ms,
    }
    await emit("cell.finished", cell_finished)

    return None


def output_event(cell: CellRef, attempt: int, output: Output) -> dict[str, object]:
    """cell.output: the cell and attempt, then the output's own fields flattened
    after its kind, as events.md lays them out."""
    event: dict[str, object] = {
        "cell_id": str(cell.id),
        "attempt": attempt,
        "kind": kind_of(output),
    }

    for name, value in fields_of(output).items():
        event[name] = value

    return event


async def run(
    code: str,
    collect: OnOutput,
    kernels: Kernels,
    emit: Emit,
) -> ExecutionResult | None:
    """The execution's result — or None when the kernel died under it, after
    starting another for the next attempt."""
    kernel = await kernels.current()

    try:
        return await kernel.execute(code, collect)
    except KernelDied:
        await emit("kernel.restarted", {"reason": "died"})
        await kernels.replace()
        return None


def attempt_status(result: ExecutionResult | None) -> str:
    if result is None:
        return "error"

    return result.status


def cell_status_of(status: str) -> CellStatus:
    """What the cells table says after an attempt. A timeout is an error to the
    cell; a cell still open for a retry stays error until the retry rewrites it."""
    if status == "ok":
        return "ok"

    if status == "cancelled":
        return "cancelled"

    return "error"


def execution_count(result: ExecutionResult | None) -> int | None:
    if result is None:
        return None

    return result.execution_count


def elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
