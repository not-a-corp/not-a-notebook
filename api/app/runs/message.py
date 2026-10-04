"""A message run, from the user's question to `run.finished` (events.md).

    run.started → kernel → the agent's turn → answer or question → run.finished

Whatever breaks, `run.finished` is the last event and the run row is closed.
What broke decides the `run.error` before it: the provider, the sandbox, a model
that refused or would not stop — or our own bug, logged under an id the event
carries and nothing more.

The one exception is shutdown: a run cancelled because the process is stopping
emits nothing more, and is closed as failed on the next startup.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx2
from psycopg_pool import AsyncConnectionPool

from app.agent import grounding
from app.agent.context import history_for
from app.agent.loop import Meter, ModelRefused, StepLimit, run_turn
from app.agent.prompt import system_prompt
from app.core.resolve_model import resolve_endpoint
from app.core.run_records import RunStatus, finish_run, store_reply
from app.core.start_message_run import MessageRun
from app.core.turn_context import turn_context
from app.domain.agent import Emit
from app.domain.errors import ModelNotFound, SandboxUnavailable
from app.domain.llm import ProviderError
from app.providers.factory import model_for
from app.runs.events import RunEvents
from app.runs.kernels import ConversationKernels
from app.runs.notebook import StoredNotebook
from app.runtime.registry import KernelRegistry
from app.security.secrets import Cipher

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Services:
    """What a run takes from the process, as the lifespan built it."""

    pool: AsyncConnectionPool
    kernels: KernelRegistry
    http: httpx2.AsyncClient
    cipher: Cipher
    environment_keys: Mapping[str, str | None]


@dataclass(frozen=True)
class Question:
    user_id: UUID
    conversation_id: UUID
    folder: str
    text: str


async def answer_in_background(services: Services, question: Question, run: MessageRun) -> None:
    emit = RunEvents(services.pool, run.run_row_id)
    meter = Meter()

    status = await answer(services, question, run, emit, meter)

    async with services.pool.connection() as conn:
        finished = await finish_run(conn, run.run_row_id, status, meter.usage)

    summary = {
        "status": status,
        "tokens_in": meter.usage.input_tokens,
        "tokens_out": meter.usage.output_tokens,
        "tokens_reasoning": meter.usage.reasoning_tokens,
        "wall_ms": finished.wall_ms,
    }
    await emit("run.finished", summary)


async def answer(
    services: Services,
    question: Question,
    run: MessageRun,
    emit: Emit,
    meter: Meter,
) -> RunStatus:
    """The run's status, once everything it emits before run.finished is out."""
    details = {"run_id": run.run_id}

    # First, before anything that can fail: run.started opens every stream.
    started = {
        "run_id": str(run.run_id),
        "conversation_id": str(question.conversation_id),
        "kind": "message",
        "model": run.model_name,
    }
    await emit("run.started", started)

    try:
        return await converse(services, question, run, emit, meter)
    except ProviderError as exc:
        log.warning("run %(run_id)s: the provider failed", details)
        await run_error(emit, "MODEL_UNAVAILABLE", f"The provider answered: {exc}")
    except ModelNotFound:
        await run_error(emit, "MODEL_UNAVAILABLE", "The conversation's model was removed.")
    except ModelRefused:
        await run_error(emit, "MODEL_REFUSED", "The model's safety system declined.")
    except StepLimit:
        await run_error(emit, "STEP_LIMIT", "The model kept running code without answering.")
    except SandboxUnavailable:
        await run_error(emit, "SANDBOX_UNAVAILABLE", "A kernel could not be started.")
    except Exception:
        error_id = str(uuid.uuid4())
        log.exception(
            "run %(run_id)s failed: %(error_id)s", {"run_id": run.run_id, "error_id": error_id}
        )
        await run_error(emit, "INTERNAL_ERROR", "Something went wrong.", error_id)

    return "failed"


async def converse(
    services: Services,
    question: Question,
    run: MessageRun,
    emit: Emit,
    meter: Meter,
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
    )

    async with services.pool.connection() as conn:
        message = await store_reply(
            conn, run.conversation_row_id, run.run_row_id, run.run_id, outcome.text
        )

    shown = message.model_dump(mode="json")

    if outcome.kind == "question":
        await emit("question", {"message": shown})
        return "awaiting_user"

    await emit("answer", {"message": shown})

    checked = grounding.check(outcome.text, outcome.produced)
    grounded = {"numbers": checked.numbers, "found": checked.found, "unfound": checked.unfound}
    await emit("grounding.checked", grounded)

    return "succeeded"


async def run_error(emit: Emit, code: str, message: str, error_id: str | None = None) -> None:
    payload: dict[str, Any] = {"code": code, "message": message, "error_id": error_id}
    await emit("run.error", payload)
