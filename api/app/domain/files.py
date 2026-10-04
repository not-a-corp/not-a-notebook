"""Uploaded files: the rules for their names, the store that keeps them, and
their shape in the API.

A file's name is what the generated code sees at /data/<name>. That is why it is
checked here rather than sanitised: rewriting "sales/2025.csv" into something
else would leave the user asking for a file the code cannot find by that name.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, BinaryIO, Protocol
from uuid import UUID

from pydantic import BaseModel

from app.domain.errors import InvalidInput, UnsupportedFileType

ACCEPTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".parquet"}

# The files.name column.
MAX_NAME_LENGTH = 255


def check_file_name(name: str | None) -> str:
    """The name as given, if it can be a file in /data; raises otherwise."""
    if name is None:
        raise InvalidInput("The file has no name.")

    if name != name.strip() or name in ("", ".", ".."):
        raise InvalidInput("That is not a usable file name.")

    if len(name) > MAX_NAME_LENGTH:
        raise InvalidInput(f"File names are at most {MAX_NAME_LENGTH} characters.")

    # One path component, nothing that could climb out of the folder or that a
    # filesystem would refuse.
    forbidden = ("/", "\\", "\x00")
    if any(character in name for character in forbidden):
        raise InvalidInput("A file name cannot contain a path.")

    if name.startswith("."):
        raise InvalidInput("A file name cannot start with a dot.")

    extension = PurePosixPath(name).suffix.lower()
    if extension not in ACCEPTED_EXTENSIONS:
        raise UnsupportedFileType

    return name


def conversation_folder(user_id: UUID, conversation_id: UUID) -> str:
    """Where a conversation's files live in the store, and what its kernel mounts.

    Built from the two external ids so the key says whose files these are
    without a lookup — and holds nothing a user typed.
    """
    return f"{user_id}/{conversation_id}"


def file_key(user_id: UUID, conversation_id: UUID, name: str) -> str:
    folder = conversation_folder(user_id, conversation_id)

    return f"{folder}/{name}"


@dataclass(frozen=True)
class Staged:
    """Bytes received and counted, not yet anywhere a kernel can see them."""

    token: str
    size: int
    sha256: bytes


class FileStore(Protocol):
    """Where uploads are kept. A local volume today; an S3 adapter is a second
    file the day the hosted version needs more than one machine (decision 9).

    Saving is two steps so that the database row and the bytes land together:
    stage, insert the row, commit — and discard the staged bytes if the row is
    refused.
    """

    async def stage(self, source: BinaryIO, max_bytes: int) -> Staged: ...

    async def commit(self, staged: Staged, key: str) -> None: ...

    async def discard(self, staged: Staged) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def prepare_folder(self, folder: str) -> None: ...

    async def delete_folder(self, folder: str) -> None: ...


class FileInfo(BaseModel):
    id: UUID
    name: str
    bytes: int
    # None until the profiling run writes it.
    profile: dict[str, Any] | None
    created_at: datetime


class UploadAccepted(BaseModel):
    file: FileInfo
    run_id: UUID
