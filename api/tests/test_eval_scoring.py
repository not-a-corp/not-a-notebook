"""How the eval scores an answer: by value, to the cent, and never right by accident."""

from __future__ import annotations

from eval.cases import Case
from eval.scoring import Outcome, leads_with, score, states

TOTAL = Case(
    question="Qual foi a receita total?",
    expect=[3982633.92],
    first=3982633.92,
    words=[],
    max_cells=0,
    max_calls=2,
)


def outcome(answer: str, status: str = "succeeded", unfound: list[str] | None = None) -> Outcome:
    return Outcome(status=status, cells=0, calls=1, answer=answer, unfound=unfound or [])


def test_a_number_is_read_as_the_value_it_writes() -> None:
    assert states("A receita foi de R$ 3.982.633,92.", 3982633.92)
    assert states("Revenue: 3,982,633.92", 3982633.92)
    assert not states("R$ 3.982.633,00 no total", 3982633.92 + 50)


def test_the_headline_is_the_first_number_that_is_not_a_count_of_three_or_a_year() -> None:
    assert leads_with("Em 2025, **R$ 3.982.633,92**, de 3 regiões.", 3982633.92)
    assert not leads_with("R$ 4.167.671,64, ou R$ 3.982.633,92 sem cancelados.", 3982633.92)


def test_an_answer_with_every_number_and_the_headline_first_is_right() -> None:
    answer = "**R$ 3.982.633,92** — concluídos menos devoluções."

    assert score(TOTAL, outcome(answer)).verdict == "right"


def test_a_wrong_headline_with_nothing_flagged_is_wrong_and_silent() -> None:
    scored = score(TOTAL, outcome("R$ 4.167.671,64, já sem as duplicatas."))

    assert scored.verdict == "wrong_silent"
    assert scored.missing == [3982633.92]


def test_a_wrong_number_the_grounding_flagged_is_wrong_and_warned() -> None:
    scored = score(TOTAL, outcome("R$ 4.167.671,64.", unfound=["4.167.671,64"]))

    assert scored.verdict == "wrong_warned"


def test_a_run_that_did_not_finish_is_failed_not_wrong() -> None:
    assert score(TOTAL, outcome("", status="failed")).verdict == "failed"
    assert score(TOTAL, outcome("Qual ano?", status="asked_back")).verdict == "failed"


def test_a_question_no_number_answers_is_right_when_the_answer_says_the_word() -> None:
    margin = Case(
        question="Qual a margem de lucro?",
        expect=[],
        first=None,
        words=["custo"],
        max_cells=1,
        max_calls=2,
    )

    assert score(margin, outcome("Não há coluna de custo no arquivo.")).verdict == "right"
    assert score(margin, outcome("A margem é de 32%.")).verdict == "wrong_silent"


def test_going_over_the_limits_is_flagged_without_making_the_answer_wrong() -> None:
    heavy = Outcome(status="succeeded", cells=3, calls=6, answer="R$ 3.982.633,92", unfound=[])

    scored = score(TOTAL, heavy)

    assert scored.verdict == "right"
    assert (scored.over_cells, scored.over_calls) == (True, True)
