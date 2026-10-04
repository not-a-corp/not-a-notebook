"""A conversation's files."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, UploadFile, status

from app.core.delete_file import delete_file
from app.core.upload_file import upload_file
from app.dependencies import Caller, Config, Db, Jobs, Kernels, Pool, Store
from app.domain.files import UploadAccepted
from app.runs.profile import profile_in_background

router = APIRouter(prefix="/conversations", tags=["files"])


@router.post("/{conversation_id}/files", status_code=status.HTTP_202_ACCEPTED)
async def upload(
    conversation_id: UUID,
    file: UploadFile,
    caller: Caller,
    conn: Db,
    store: Store,
    settings: Config,
    pool: Pool,
    kernels: Kernels,
    jobs: Jobs,
) -> UploadAccepted:
    upload = await upload_file(
        conn,
        store,
        caller,
        conversation_id,
        name=file.filename,
        source=file.file,
        max_bytes=settings.max_upload_mb * 1024 * 1024,
    )

    # The answer goes out now; the profile is written when the run finishes.
    jobs.spawn(profile_in_background(pool, kernels, upload.job))

    return upload.accepted


@router.delete(
    "/{conversation_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete(
    conversation_id: UUID,
    file_id: UUID,
    caller: Caller,
    conn: Db,
    store: Store,
) -> Response:
    await delete_file(conn, store, caller, conversation_id, file_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
