"""The agent's turn with a scripted model and kernel: every rule of the loop,
and the events in the order events.md promises."""

from __future__ import annotations

import asyncio

import pytest
from app.agent.loop import (
    MAX_ATTEMPTS,
    MAX_STEPS,
    STEPS_LEFT_WARNING,
    Meter,
    ModelRefused,
    StepLimit,
    budget_note,
    run_turn,
)
from app.domain.llm import AssistantTurn, Reply, ToolResult, Usage, UserText
from tests.support.agent import (
    Events,
    MemoryNotebook,
    Run,
    ScriptedKernel,
    ScriptedKernels,
    ScriptedModel,
    answers,
    asks,
    fails,
    prints,
    wants,
)


async def turn(
    replies: list[Reply], runs: list[Run]
) -> tuple[object, ScriptedModel, ScriptedKernel, MemoryNotebook, Events, Meter]:
    model = ScriptedModel(replies)
    kernel = ScriptedKernel(runs)
    notebook = MemoryNotebook()
    events = Events()
    meter = Meter()

    outcome = await run_turn(
        model,
        ScriptedKernels(kernel),
        "system",
        [UserText("Which region sold the most?")],
        notebook,
        events,
        meter,
        asyncio.Event(),
    )

    return outcome, model, kernel, notebook, events, meter


async def test_an_answer_without_code_ends_the_turn() -> None:
    outcome, _, kernel, notebook, events, _ = await turn([answers("Hello.")], [])

    assert outcome.kind == "answer"  # type: ignore[attr-defined]
    assert outcome.text == "Hello."  # type: ignore[attr-defined]
    assert kernel.executed == []
    assert notebook.cells == []
    assert events.types() == ["llm.started", "llm.delta", "llm.finished"]


async def test_code_runs_in_a_cell_and_its_output_goes_back_to_the_model() -> None:
    replies = [wants("print(1 + 1)", call_id="call_1"), answers("It is 2.")]

    outcome, model, kernel, notebook, events, _ = await turn(replies, [prints("2\n")])

    assert kernel.executed == ["print(1 + 1)"]
    assert notebook.cells[0].status == "ok"
    assert outcome.produced == ["2"]  # type: ignore[attr-defined]

    second_look = model.seen[1]
    assert isinstance(second_look[1], AssistantTurn)
    assert second_look[2] == ToolResult(call_id="call_1", content="2", is_error=False)


async def test_the_events_come_in_the_order_events_md_promises() -> None:
    replies = [wants("print(2)", text="Let me check."), answers("2.")]

    _, _, _, _, events, _ = await turn(replies, [prints("2\n")])

    assert events.types() == [
        "llm.started",
        "llm.delta",
        "llm.finished",
        "code.proposed",
        "cell.created",
        "attempt.started",
        "cell.output",
        "attempt.finished",
        "cell.finished",
        "llm.started",
        "llm.delta",
        "llm.finished",
    ]
    output = events.of("cell.output")[0]
    assert output["kind"] == "stream"
    assert output["name"] == "stdout"
    assert output["text"] == "2\n"
    assert output["attempt"] == 1


async def test_a_retry_rewrites_the_same_cell() -> None:
    replies = [wants("df['região']"), wants("df['regiao']"), answers("Done.")]

    _, _, kernel, notebook, events, _ = await turn(replies, [fails(), prints("ok\n")])

    assert len(notebook.cells) == 1
    assert notebook.cells[0].source == "df['regiao']"
    assert notebook.cells[0].attempts == 2
    assert notebook.cells[0].status == "ok"
    assert [e["attempt"] for e in events.of("code.proposed")] == [1, 2]
    assert len(events.of("cell.created")) == 1
    assert events.of("cell.finished") == [
        {
            "cell_id": str(notebook.cells[0].id),
            "status": "ok",
            "attempts": 2,
            "execution_count": 2,
            "duration_ms": events.of("cell.finished")[0]["duration_ms"],
        }
    ]


async def test_the_model_sees_the_error_as_an_error() -> None:
    replies = [wants("boom", call_id="call_1"), answers("Sorry.")]

    _, model, _, _, _, _ = await turn(replies, [fails("ZeroDivisionError", "division by zero")])

    result = model.seen[1][2]
    assert isinstance(result, ToolResult)
    assert result.is_error is True
    assert "ZeroDivisionError: division by zero" in result.content


async def test_after_the_last_attempt_new_code_gets_a_new_cell() -> None:
    replies = [wants(f"try {n}") for n in range(MAX_ATTEMPTS)]
    replies += [wants("something else"), answers("I could not.")]
    runs = [fails() for _ in range(MAX_ATTEMPTS)] + [prints("fine\n")]

    _, _, _, notebook, events, _ = await turn(replies, runs)

    assert len(notebook.cells) == 2
    assert notebook.cells[0].status == "error"
    assert notebook.cells[0].attempts == MAX_ATTEMPTS
    assert notebook.cells[1].source == "something else"
    statuses = [e["status"] for e in events.of("cell.finished")]
    assert statuses == ["error", "ok"]


async def test_a_dead_kernel_is_replaced_and_the_model_is_told() -> None:
    replies = [wants("huge = b'x' * 10**12", call_id="call_1"), wants("small"), answers("Ok.")]
    kernel = ScriptedKernel([Run(dies=True), prints("ok\n")])
    kernels = ScriptedKernels(kernel)
    model = ScriptedModel(replies)
    notebook = MemoryNotebook()
    events = Events()

    await run_turn(
        model, kernels, "s", [UserText("go")], notebook, events, Meter(), asyncio.Event()
    )

    assert kernels.replaced == 1
    assert {"reason": "died"} in events.of("kernel.restarted")
    told = model.seen[1][2]
    assert isinstance(told, ToolResult)
    assert "kernel died" in told.content
    # Not retried in place: what the cell needed died with the kernel.
    assert len(notebook.cells) == 2


async def test_a_question_ends_the_turn_waiting_for_the_user() -> None:
    outcome, _, kernel, _, _, _ = await turn([asks("2024 or 2025?")], [])

    assert outcome.kind == "question"  # type: ignore[attr-defined]
    assert outcome.text == "2024 or 2025?"  # type: ignore[attr-defined]
    assert kernel.executed == []


async def test_a_question_keeps_its_options() -> None:
    outcome, _, _, _, _, _ = await turn([asks("Which year?", ("2024", "2025"))], [])

    assert outcome.kind == "question"  # type: ignore[attr-defined]
    assert outcome.options == ("2024", "2025")  # type: ignore[attr-defined]


async def test_a_refusal_raises() -> None:
    refused = Reply(
        turn=AssistantTurn(text="", code=None, call_id=None, source="x", raw=None),
        usage=Usage(),
        stop="refusal",
    )

    with pytest.raises(ModelRefused):
        await turn([refused], [])


async def test_a_model_that_never_answers_hits_the_step_limit_and_its_tokens_still_count() -> None:
    replies = [wants(f"print({n})") for n in range(MAX_STEPS)]
    runs = [prints(f"{n}\n") for n in range(MAX_STEPS)]
    meter = Meter()

    with pytest.raises(StepLimit):
        await run_turn(
            ScriptedModel(replies),
            ScriptedKernels(ScriptedKernel(runs)),
            "s",
            [UserText("loop")],
            MemoryNotebook(),
            Events(),
            meter,
            asyncio.Event(),
        )

    assert meter.usage.input_tokens == 100 * MAX_STEPS


def test_the_model_is_told_nothing_while_it_has_steps_to_spare() -> None:
    assert budget_note(STEPS_LEFT_WARNING + 1) is None


def test_the_model_is_warned_when_steps_run_low_and_told_firmly_on_the_last() -> None:
    warning = budget_note(STEPS_LEFT_WARNING)
    last = budget_note(1)

    assert warning is not None
    assert str(STEPS_LEFT_WARNING) in warning
    assert last is not None
    assert "last" in last


async def test_the_warning_is_read_by_the_model_and_kept_out_of_the_notebook() -> None:
    replies = [wants(f"print({n})", call_id=f"call_{n}") for n in range(MAX_STEPS - 1)]
    replies.append(answers("Done."))
    runs = [prints(f"{n}\n") for n in range(MAX_STEPS - 1)]

    outcome, model, _, notebook, _, _ = await turn(replies, runs)

    assert outcome.kind == "answer"  # type: ignore[attr-defined]

    first_result = model.seen[1][-1]
    assert isinstance(first_result, ToolResult)
    assert first_result.content == "0"

    last_result = model.seen[-1][-1]
    assert isinstance(last_result, ToolResult)
    assert "last allowed" in last_result.content
    assert "last allowed" not in str(notebook.cells[-1].outputs)


async def test_tokens_add_up_across_steps() -> None:
    replies = [wants("1"), answers("1.")]

    _, _, _, _, _, meter = await turn(replies, [prints("1\n")])

    assert meter.usage == Usage(input_tokens=200, output_tokens=50, reasoning_tokens=5)
