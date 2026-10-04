"""Where generated code runs: the protocol, and what comes back from it.

The agent and the routes depend on these and nothing else. The Docker adapter in
`app/runtime/` is the only implementation; another one (a hosted sandbox, say)
would be a second file, and nothing above this line would change.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class StreamOutput:
    """Printed text. It arrives in chunks as the code runs, not in lines."""

    name: Literal["stdout", "stderr"]
    text: str


@dataclass(frozen=True)
class ErrorOutput:
    """An exception, structured: the self-correction loop reads these fields."""

    name: str
    value: str
    traceback: list[str]


@dataclass(frozen=True)
class PlotlyOutput:
    """A Plotly figure as its spec. The client renders it, in the client's theme."""

    spec: dict[str, Any]


@dataclass(frozen=True)
class TableOutput:
    """A DataFrame or Series: at most 100 rows travel, total_rows says how many exist."""

    columns: list[str]
    rows: list[list[Any]]
    total_rows: int


@dataclass(frozen=True)
class TextOutput:
    """The plain value of an expression that is none of the above."""

    text: str


@dataclass(frozen=True)
class ImageOutput:
    """A PNG, base64 — for code that insists on matplotlib."""

    png: str


type Output = StreamOutput | ErrorOutput | PlotlyOutput | TableOutput | TextOutput | ImageOutput

type OnOutput = Callable[[Output], Awaitable[None]]

# cancelled: interrupted on request. timed_out: interrupted for running past the
# wall-time limit. Either way the kernel and its state survive.
type ExecutionStatus = Literal["ok", "error", "cancelled", "timed_out"]


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    execution_count: int | None
    duration_ms: int


class KernelDied(Exception):
    """The kernel is gone — out of memory, most often — and its state with it.

    Not a DomainError: no route answers with it. Whoever ran the code tells the
    conversation that the kernel restarted (decision 3).
    """


class Kernel(Protocol):
    async def execute(self, code: str, on_output: OnOutput) -> ExecutionResult: ...

    async def interrupt(self) -> None: ...

    async def shutdown(self) -> None: ...


class Runtime(Protocol):
    async def start(self, session: UUID) -> Kernel: ...
