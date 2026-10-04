"""Naive grounding: is every number in the answer somewhere in what the code
printed?

It catches the invented number — the model stating a figure no output contains.
It does not catch code that silently drops rows, or a right number for the wrong
question. Necessary, not sufficient (the POC's finding).

Numbers are compared as values, not as text, so "1.840.000,00" in the answer
matches 1840000.0 printed by pandas, and "41%" matches 0.41 or 41.0. Small
integers and years are skipped: "the 3 regions", "in 2025" would match anything.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

# 1.234,56 · 1,234.56 · 1234.56 · -12 · 41% — and "R$ 1,84 mi"-style suffixes
# are left to the rounding tolerance below.
NUMBER = re.compile(r"-?\d[\d.,]*%?")

YEARS = range(1900, 2101)
SMALL = 10


@dataclass(frozen=True)
class Grounding:
    numbers: int
    found: int
    unfound: list[str]


def check(answer: str, outputs: Sequence[str]) -> Grounding:
    produced: list[float] = []
    for output in outputs:
        for token in NUMBER.findall(output):
            produced.extend(values_of(token))

    claimed = 0
    unfound = []

    for token in NUMBER.findall(answer):
        values = values_of(token)
        if not values or trivial(values):
            continue

        claimed += 1
        if not any(close_to_one(value, produced) for value in values):
            unfound.append(token.rstrip(".,"))

    return Grounding(numbers=claimed, found=claimed - len(unfound), unfound=unfound)


def values_of(token: str) -> list[float]:
    """Every value a written number could be — "1.234" is 1234 or 1.234 — and a
    percentage both as written and as a fraction."""
    text = token.rstrip(".,")
    percent = text.endswith("%")
    text = text.rstrip("%")

    readings = set()
    for decimal_mark, grouping in ((".", ","), (",", ".")):
        plain = text.replace(grouping, "").replace(decimal_mark, ".")
        try:
            readings.add(float(plain))
        except ValueError:
            continue

    values = list(readings)
    if percent:
        values.extend(value / 100 for value in readings)

    return values


def trivial(values: list[float]) -> bool:
    for value in values:
        if value.is_integer() and (abs(value) <= SMALL or int(value) in YEARS):
            return True

    return False


def close_to_one(value: float, produced: list[float]) -> bool:
    """Equal, or equal once rounded the way the answer rounded it — "1.84M" for
    1_840_231 is checked as 1.84 against 1.84 millions too."""
    for candidate in produced:
        if math.isclose(value, candidate, rel_tol=0.005):
            return True

        for scale in (1_000, 1_000_000, 1_000_000_000):
            if math.isclose(value * scale, candidate, rel_tol=0.005):
                return True

    return False
