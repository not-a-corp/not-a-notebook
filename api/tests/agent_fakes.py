"""A scripted model, a scripted kernel, an in-memory notebook and a list of
events — the whole agent loop with nothing real behind it (decision 15)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.domain.agent import CellRef, CellStatus
from app.domain.llm import AssistantTurn, Item, OnDelta, Reply, Usage
from app.domain.runtime import (
    ErrorOutput,
    ExecutionResult,
    KernelDied,
    OnOutput,
    Output,
    StreamOutput,
)

SOURCE = "fake:model"


def wants(code: str, text: str = "", call_id: str | None = None) -> Reply:
    turn = AssistantTurn(
        text=text,
        code=code,
        call_id=call_id or f"call_{uuid4().hex[:8]}",
        source=SOURCE,
        raw=None,
    )
    return Reply(turn=turn, usage=Usage(100, 20, 5), stop="code")


def answers(text: str) -> Reply:
    turn = AssistantTurn(text=text, code=None, call_id=None, source=SOURCE, raw=None)
    return Reply(turn=turn, usage=Usage(100, 30, 0), stop="answer")


def asks(question: str) -> Reply:
    turn = AssistantTurn(text="", code=None, call_id="call_ask", source=SOURCE, raw=None)
    return Reply(turn=turn, usage=Usage(100, 10, 0), stop="question", question=question)


class ScriptedModel:
    """Answers with the next reply in its script, streaming its text."""

    def __init__(self, replies: Sequence[Reply]) -> None:
        self.replies = list(replies)
        self.seen: list[list[Item]] = []

    async def complete(self, system: str, history: Sequence[Item], on_delta: OnDelta) -> Reply:
        self.seen.append(list(history))
        reply = self.replies.pop(0)

        if reply.turn.text:
            await on_delta(reply.turn.text)

        return reply


@dataclass
class Run:
    """One scripted execution: what it prints, and how it ends."""

    outputs: list[Output] = field(default_factory=list)
    status: str = "ok"
    dies: bool = False


def prints(text: str) -> Run:
    return Run(outputs=[StreamOutput(name="stdout", text=text)])


def fails(name: str = "KeyError", value: str = "'região'") -> Run:
    error = ErrorOutput(name=name, value=value, traceback=[f"{name}: {value}"])
    return Run(outputs=[error], status="error")


class ScriptedKernel:
    def __init__(self, runs: Sequence[Run]) -> None:
        self.runs = list(runs)
        self.executed: list[str] = []
        self.count = 0

    async def execute(
        self, code: str, on_output: OnOutput, store_history: bool = True
    ) -> ExecutionResult:
        self.executed.append(code)
        run = self.runs.pop(0)

        if run.dies:
            raise KernelDied("out of memory")

        for output in run.outputs:
            await on_output(output)

        self.count += 1
        return ExecutionResult(status=run.status, execution_count=self.count, duration_ms=3)  # type: ignore[arg-type]

    async def interrupt(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class ScriptedKernels:
    def __init__(self, kernel: ScriptedKernel) -> None:
        self.kernel = kernel
        self.replaced = 0

    async def current(self) -> ScriptedKernel:
        return self.kernel

    async def replace(self) -> ScriptedKernel:
        self.replaced += 1
        return self.kernel


@dataclass
class Cell:
    id: Any
    source: str
    attempts: int = 1
    status: str = "running"
    outputs: list[Output] = field(default_factory=list)


class MemoryNotebook:
    def __init__(self) -> None:
        self.cells: list[Cell] = []

    async def create_cell(self, source: str) -> CellRef:
        cell = Cell(id=uuid4(), source=source)
        self.cells.append(cell)
        return CellRef(id=cell.id, position=len(self.cells))

    async def rewrite_cell(self, cell: CellRef, source: str, attempt: int) -> None:
        found = self.find(cell)
        found.source = source
        found.attempts = attempt
        found.status = "running"
        found.outputs = []

    async def finish_attempt(
        self,
        cell: CellRef,
        outputs: Sequence[Output],
        status: CellStatus,
        execution_count: int | None,
        duration_ms: int,
    ) -> None:
        found = self.find(cell)
        found.status = status
        found.outputs = list(outputs)

    async def describe(self, cell: CellRef) -> dict[str, Any]:
        found = self.find(cell)
        return {"id": str(found.id), "source": found.source}

    def find(self, cell: CellRef) -> Cell:
        for candidate in self.cells:
            if candidate.id == cell.id:
                return candidate

        raise AssertionError("no such cell")


class Events:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))

    def types(self) -> list[str]:
        return [event_type for event_type, _ in self.events]

    def of(self, event_type: str) -> list[dict[str, Any]]:
        return [payload for kind, payload in self.events if kind == event_type]
