"""Is an answer right, and what did it cost.

The three verdicts are the plan's (the POC's finding): **right**; **wrong and
warned**, where the grounding check flagged a number; **wrong and silent**, a
confident answer, a wrong number and nothing flagged. The last one is the metric
that matters. A run that did not finish is its own thing, `failed`.

Numbers are compared as values, the way grounding reads them, so "3.982.633,92"
in the answer is 3982633.92.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.agent.grounding import NUMBER, trivial, values_of

from eval.cases import Case

# To the cent, and a model that rounds to the real is still right.
TOLERANCE = 1.0


@dataclass(frozen=True)
class Outcome:
    status: str
    cells: int
    calls: int
    answer: str
    # Numbers the grounding check could not find in any output.
    unfound: list[str]


@dataclass(frozen=True)
class Score:
    verdict: str
    missing: list[float]
    led_with_it: bool
    over_cells: bool
    over_calls: bool


def is_close(values: list[float], expected: float) -> bool:
    close = [math.isclose(value, expected, abs_tol=TOLERANCE) for value in values]

    return any(close)


def states(answer: str, expected: float) -> bool:
    tokens = NUMBER.findall(answer)
    found = [is_close(values_of(token), expected) for token in tokens]

    return any(found)


def leads_with(answer: str, expected: float) -> bool:
    """The first number the answer says that is not a count of three or a year."""
    for token in NUMBER.findall(answer):
        values = values_of(token)
        if not values or trivial(values):
            continue

        return is_close(values, expected)

    return False


def mentions(answer: str, word: str) -> bool:
    return re.search(re.escape(word), answer, re.IGNORECASE) is not None


def score(case: Case, outcome: Outcome) -> Score:
    over_cells = outcome.cells > case.max_cells
    over_calls = outcome.calls > case.max_calls

    if outcome.status != "succeeded":
        return Score("failed", [], False, over_cells, over_calls)

    missing = []
    for expected in case.expect:
        if not states(outcome.answer, expected):
            missing.append(expected)

    led_with_it = True
    if case.first is not None:
        led_with_it = leads_with(outcome.answer, case.first)

    said_words = True
    for word in case.words:
        if not mentions(outcome.answer, word):
            said_words = False

    right = not missing and led_with_it and said_words
    if right:
        return Score("right", missing, led_with_it, over_cells, over_calls)

    if outcome.unfound:
        return Score("wrong_warned", missing, led_with_it, over_cells, over_calls)

    return Score("wrong_silent", missing, led_with_it, over_cells, over_calls)
