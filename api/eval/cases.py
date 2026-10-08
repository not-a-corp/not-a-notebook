"""A file and the questions asked of it, with what a right answer holds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Case:
    question: str
    # Numbers a right answer states, worked out without the model.
    expect: list[float]
    # The number a right answer leads with, when the question has one headline.
    first: float | None
    # Words a right answer holds, for the question no number answers.
    words: list[str]
    # Cells the question may cost. 0 is a question the notebook already answers.
    max_cells: int
    max_calls: int


@dataclass(frozen=True)
class Suite:
    file: Path
    cases: list[Case]


def load_suite(path: Path) -> Suite:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    file = path.parent.parent / "files" / document["file"]

    cases = []
    for entry in document["cases"]:
        case = Case(
            question=entry["question"],
            expect=entry.get("expect", []),
            first=entry.get("first"),
            words=entry.get("words", []),
            max_cells=entry["max_cells"],
            max_calls=entry["max_calls"],
        )
        cases.append(case)

    return Suite(file=file, cases=cases)
