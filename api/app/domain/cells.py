"""The shapes of writing cells yourself, as api.md defines them."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

# Long enough for any cell a person writes by hand; a notebook cell is not a file.
MAX_SOURCE_LENGTH = 100_000


class CreateCellRequest(BaseModel):
    """`after_cell_id` left out puts the cell at the end; `null` puts it first."""

    source: str = Field(max_length=MAX_SOURCE_LENGTH)
    after_cell_id: UUID | None = None


class EditCellRequest(BaseModel):
    source: str = Field(max_length=MAX_SOURCE_LENGTH)


class RunAccepted(BaseModel):
    run_id: UUID
