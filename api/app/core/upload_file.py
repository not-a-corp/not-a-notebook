"""Receiving a file into a conversation — which starts the run that profiles it.

Everything touching the kernel is a run (decision 17), and profiling happens in
the kernel, so an upload is a run. Starting it is an INSERT that the "one run in
progress per conversation" index can refuse: CONVERSATION_BUSY, with no SELECT
first.

The bytes, the file row, the run row and the conversation's activity land
together or not at all: staged first, then one transaction, and the staged bytes
are only moved into the conversation's folder inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO
from uuid import UUID

from psycopg import AsyncConnection, errors

from app.domain.errors import ConversationBusy, ConversationNotFound, FileAlreadyExists
from app.domain.files import (
    FileInfo,
    FileStore,
    Staged,
    UploadAccepted,
    check_file_name,
    conversation_folder,
    file_key,
)


@dataclass(frozen=True)
class ProfileJob:
    """What the background profiling needs, in internal ids — it never leaves
    the process."""

    run_id: int
    file_id: int
    conversation_id: UUID
    folder: str
    name: str


@dataclass(frozen=True)
class Upload:
    accepted: UploadAccepted
    job: ProfileJob


async def upload_file(
    conn: AsyncConnection[Any],
    store: FileStore,
    user_id: UUID,
    conversation_id: UUID,
    name: str | None,
    source: BinaryIO,
    max_bytes: int,
) -> Upload:
    checked_name = check_file_name(name)
    staged = await store.stage(source, max_bytes)

    try:
        upload = await record(conn, store, staged, user_id, conversation_id, checked_name)
    except BaseException:
        await store.discard(staged)
        raise

    return upload


async def record(
    conn: AsyncConnection[Any],
    store: FileStore,
    staged: Staged,
    user_id: UUID,
    conversation_id: UUID,
    name: str,
) -> Upload:
    run_sql = """
        INSERT INTO runs AS r (conversation_id, kind)
        SELECT c.id,
               'profile'
          FROM conversations c
          JOIN users u
            ON u.id = c.user_id
         WHERE u.external_id = %(user_id)s
           AND c.external_id = %(conversation_id)s
        RETURNING r.id,
                  r.external_id,
                  r.conversation_id
    """

    run_params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
    }

    file_sql = """
        INSERT INTO files AS f (conversation_id, name, bytes, sha256, storage_key)
        VALUES (%(conversation_id)s, %(name)s, %(bytes)s, %(sha256)s, %(storage_key)s)
        RETURNING f.id,
                  f.external_id,
                  f.name,
                  f.bytes,
                  f.profile,
                  f.created_at
    """

    touch_sql = """
        UPDATE conversations c
           SET updated_at = now()
         WHERE c.id = %(conversation_id)s
    """

    key = file_key(user_id, conversation_id, name)

    async with conn.transaction(), conn.cursor() as cur:
        try:
            await cur.execute(run_sql, run_params)
        except errors.UniqueViolation as exc:
            raise ConversationBusy from exc

        run = await cur.fetchone()
        if run is None:
            raise ConversationNotFound

        file_params: dict[str, Any] = {
            "conversation_id": run["conversation_id"],
            "name": name,
            "bytes": staged.size,
            "sha256": staged.sha256,
            "storage_key": key,
        }

        try:
            await cur.execute(file_sql, file_params)
        except errors.UniqueViolation as exc:
            raise FileAlreadyExists from exc

        stored = await cur.fetchone()
        assert stored is not None  # RETURNING on a successful INSERT

        touch_params = {"conversation_id": run["conversation_id"]}
        await cur.execute(touch_sql, touch_params)

        # Last, so a refused row never leaves bytes behind at the file's name.
        await store.commit(staged, key)

    file = FileInfo(
        id=stored["external_id"],
        name=stored["name"],
        bytes=stored["bytes"],
        profile=stored["profile"],
        created_at=stored["created_at"],
    )

    job = ProfileJob(
        run_id=run["id"],
        file_id=stored["id"],
        conversation_id=conversation_id,
        folder=conversation_folder(user_id, conversation_id),
        name=name,
    )

    accepted = UploadAccepted(file=file, run_id=run["external_id"])

    return Upload(accepted=accepted, job=job)
