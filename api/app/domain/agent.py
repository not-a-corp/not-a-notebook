"""What the agent loop needs from the world, as protocols.

The loop in app/agent/ runs a conversation's turn: it asks the model, runs the
code, keeps the notebook and tells the stream. It owns none of those things — it
gets them through these, which is what lets the tests run the whole loop with a
scripted model, a scripted kernel, an in-memory notebook and a list of events.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID

from app.domain.runtime import Kernel, Output

# A cell's status once an attempt at it ends, as the cells table stores it.
type CellStatus = Literal["ok", "error", "cancelled"]


@dataclass(frozen=True)
class CellRef:
    id: UUID
    position: int


class Notebook(Protocol):
    """The conversation's cells, as the loop changes them."""

    async def create_cell(self, source: str) -> CellRef:
        """A new agent cell at the end, running its first attempt."""
        ...

    async def rewrite_cell(self, cell: CellRef, source: str, attempt: int) -> None:
        """The same cell, new source, its outputs cleared: the next attempt."""
        ...

    async def finish_attempt(
        self,
        cell: CellRef,
        outputs: Sequence[Output],
        status: CellStatus,
        execution_count: int | None,
        duration_ms: int,
    ) -> None: ...

    async def describe(self, cell: CellRef) -> dict[str, Any]:
        """The cell as GET /conversations/{id} shows it — for cell.created."""
        ...


class Emit(Protocol):
    """Sends one event of events.md. The envelope — seq, t — is not the loop's
    concern."""

    async def __call__(self, event_type: str, payload: dict[str, Any]) -> None: ...


class Kernels(Protocol):
    """The conversation's kernel, and a fresh one when it dies."""

    async def current(self) -> Kernel: ...

    async def replace(self) -> Kernel:
        """After the kernel died: forget it, and start another."""
        ...
