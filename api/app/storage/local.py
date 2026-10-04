"""The FileStore on a local directory — a Docker volume, in compose.

Staged files wait in .staging inside the same root, so committing one is a
rename on the same filesystem: atomic, and never a half-written file at a name a
kernel can read.

Files are written readable by everyone and folders traversable by everyone: the
kernel reads them as an unprivileged user, through a read-only mount.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import shutil
from pathlib import Path
from typing import BinaryIO

from app.domain.errors import FileTooLarge, InvalidInput
from app.domain.files import Staged

CHUNK_BYTES = 1024 * 1024
FILE_MODE = 0o644
FOLDER_MODE = 0o755


class LocalFileStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.staging = self.root / ".staging"

    async def stage(self, source: BinaryIO, max_bytes: int) -> Staged:
        return await asyncio.to_thread(self.stage_now, source, max_bytes)

    async def commit(self, staged: Staged, key: str) -> None:
        await asyncio.to_thread(self.commit_now, staged, key)

    async def discard(self, staged: Staged) -> None:
        path = self.staging / staged.token
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def delete(self, key: str) -> None:
        path = self.inside(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

    async def prepare_folder(self, folder: str) -> None:
        path = self.inside(folder)
        await asyncio.to_thread(make_folder, path)

    async def delete_folder(self, folder: str) -> None:
        path = self.inside(folder)
        await asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)

    def stage_now(self, source: BinaryIO, max_bytes: int) -> Staged:
        make_folder(self.staging)

        token = secrets.token_hex(16)
        path = self.staging / token
        digest = hashlib.sha256()
        size = 0

        with path.open("wb") as target:
            while chunk := source.read(CHUNK_BYTES):
                size += len(chunk)

                # Counted as it arrives, so an oversized file is refused at the
                # limit, not after it has all been written.
                if size > max_bytes:
                    target.close()
                    path.unlink()
                    raise FileTooLarge

                digest.update(chunk)
                target.write(chunk)

        if size == 0:
            path.unlink()
            raise InvalidInput("The file is empty.")

        path.chmod(FILE_MODE)

        return Staged(token=token, size=size, sha256=digest.digest())

    def commit_now(self, staged: Staged, key: str) -> None:
        destination = self.inside(key)
        make_folder(destination.parent)

        source = self.staging / staged.token
        os.replace(source, destination)

    def inside(self, key: str) -> Path:
        """The path for a key, refused if it would land outside the root. Keys are
        built from ids and checked names, so this never fires — it is the last
        line, not the only one."""
        path = (self.root / key).resolve()
        root = self.root.resolve()

        if not path.is_relative_to(root) or path == root:
            raise InvalidInput("That is not a usable file name.")

        return path


def make_folder(path: Path) -> None:
    path.mkdir(mode=FOLDER_MODE, parents=True, exist_ok=True)

    # mkdir's mode is filtered by the umask; this is not.
    path.chmod(FOLDER_MODE)
