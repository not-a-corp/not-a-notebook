"""A message run's own work: the context, the agent's turn, the answer or the
question — and the grounding check (events.md). The frame around it — run.started,
errors, run.finished — is jobs/run.py's.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from app.agent import grounding
from app.agent.context import history_for
from app.agent.loop import Meter, run_turn
from app.agent.prompt import system_prompt
from app.core.models.resolve_model import resolve_endpoint
from app.core.runs.start_message_run import MessageRun
from app.core.runs.turn_context import turn_context
from app.db.messages import store_reply
from app.db.runs import RunStatus
from app.domain.agent import Emit
from app.domain.messages import GroundingResult
from app.jobs.kernels import ConversationKernels
from app.jobs.notebook import StoredNotebook
from app.jobs.run import RunJob, run_job
from app.jobs.services import Services
from app.providers.factory import model_for

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Question:
    user_id: UUID
    conversation_id: UUID
    folder: str
    text: str


async def answer_in_background(services: Services, question: Question, run: MessageRun) -> None:
    job = RunJob(
        run_row_id=run.run_row_id,
        run_id=run.run_id,
        conversation_id=question.conversation_id,
        kind="message",
        model=run.model_name,
    )

    async def work(emit: Emit, stop: asyncio.Event, meter: Meter) -> RunStatus:
        return await converse(services, question, run, emit, meter, stop)

    await run_job(services, job, work)


async def converse(
    services: Services,
    question: Question,
    run: MessageRun,
    emit: Emit,
    meter: Meter,
    stop: asyncio.Event,
) -> RunStatus:
    async with services.pool.connection() as conn:
        endpoint = await resolve_endpoint(
            conn,
            question.user_id,
            run.model_id,
            services.cipher,
            services.environment_keys,
        )
        context = await turn_context(conn, run.conversation_row_id, run.run_row_id)

    kernels = ConversationKernels(
        services.kernels,
        services.store,
        question.conversation_id,
        question.folder,
        emit,
        context.cells_have_run,
    )
    # Started before the model is asked, so the briefing can say whether the
    # notebook's variables survived.
    await kernels.current()

    history = history_for(
        context.messages,
        context.files,
        context.cells,
        kernels.lost,
        question.text,
    )
    notebook = StoredNotebook(services.pool, run.conversation_row_id, run.run_row_id)
    model = model_for(endpoint, services.http)

    outcome = await run_turn(
        model,
        kernels,
        system_prompt(endpoint.dialect),
        history,
        notebook,
        emit,
        meter,
        stop,
    )

    if outcome.kind == "question":
        async with services.pool.connection() as conn:
            question_asked = await store_reply(
                conn,
                run.conversation_row_id,
                run.run_row_id,
                run.run_id,
                outcome.text,
                "question",
                None,
            )

        await emit("question", {"message": question_asked.model_dump(mode="json")})
        return "awaiting_user"

    # Checked before the answer is stored, so the answer keeps its check: a
    # screen opened later shows the same badge the live one did.
    checked = grounding.check(outcome.text, outcome.produced)
    grounded = GroundingResult(
        numbers=checked.numbers, found=checked.found, unfound=checked.unfound
    )

    async with services.pool.connection() as conn:
        answer = await store_reply(
            conn,
            run.conversation_row_id,
            run.run_row_id,
            run.run_id,
            outcome.text,
            "answer",
            grounded,
        )

    await emit("answer", {"message": answer.model_dump(mode="json")})
    await emit("grounding.checked", grounded.model_dump())

    return "succeeded"
