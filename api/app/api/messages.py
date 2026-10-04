"""Talking to the analyst: a message is a question, and the run that answers it."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.core.start_message_run import start_message_run
from app.dependencies import (
    Caller,
    Crypto,
    Db,
    EnvironmentKeys,
    Http,
    Jobs,
    Kernels,
    Live,
    Pool,
)
from app.domain.files import conversation_folder
from app.domain.messages import MessageAccepted, MessageRequest
from app.runs.message import Question, Services, answer_in_background

router = APIRouter(prefix="/conversations", tags=["messages"])


@router.post("/{conversation_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def send(
    conversation_id: UUID,
    payload: MessageRequest,
    caller: Caller,
    conn: Db,
    pool: Pool,
    kernels: Kernels,
    live: Live,
    http: Http,
    cipher: Crypto,
    keys: EnvironmentKeys,
    jobs: Jobs,
) -> MessageAccepted:
    run = await start_message_run(conn, caller, conversation_id, payload.text)

    services = Services(
        pool=pool,
        broadcast=live,
        kernels=kernels,
        http=http,
        cipher=cipher,
        environment_keys=keys,
    )
    question = Question(
        user_id=caller,
        conversation_id=conversation_id,
        folder=conversation_folder(caller, conversation_id),
        text=payload.text,
    )

    # The answer goes out now; the run streams at GET /runs/{id}/events.
    jobs.spawn(answer_in_background(services, question, run))

    return MessageAccepted(message=run.message, run_id=run.run_id)
