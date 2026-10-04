"""Naive grounding: numbers in the answer against numbers the code produced."""

from __future__ import annotations

from app.agent.grounding import check


def test_a_number_the_code_printed_is_found() -> None:
    checked = check("Sudeste sold 1840231.50.", ["total=1840231.5"])

    assert checked.numbers == 1
    assert checked.unfound == []


def test_a_brazilian_number_matches_what_pandas_printed() -> None:
    checked = check("Sudeste vendeu R$ 1.840.231,50.", ["1840231.5"])

    assert checked.unfound == []


def test_a_rounded_millions_figure_matches() -> None:
    checked = check("Sudeste sold 1.84M.", ["1840231.5"])

    assert checked.unfound == []


def test_a_percentage_matches_its_fraction() -> None:
    checked = check("That is 41% of the total.", ["share: 0.4103"])

    assert checked.unfound == []


def test_an_invented_number_is_unfound() -> None:
    checked = check("Sudeste sold 1.84M, 41% of the total.", ["1840231.5"])

    assert checked.numbers == 2
    assert checked.found == 1
    assert checked.unfound == ["41%"]


def test_small_counts_and_years_are_not_checked() -> None:
    checked = check("Across the 3 regions in 2025, nothing changed.", [])

    assert checked.numbers == 0
