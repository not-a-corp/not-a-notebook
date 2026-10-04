"""What a careful analyst would catch in a table, before anyone asks a question.

Each detector looks at one kind of trouble and returns findings. A finding says
what, where — the row as numbered in the file, so a person can find it — and
shows suspicious values both ways when they can be read two ways. Nothing is
fixed: the table is described as it is, and the model decides with the user.

    {"kind": "subtotal_rows", "column": "região", "rows": [5], "count": 1,
     "message": "..."}

The detectors are heuristics, tuned to be quiet on clean files: a finding that
cries wolf teaches the model to ignore findings.
"""

from __future__ import annotations

import itertools
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

# How many example rows a finding lists. The count says how many there are.
MAX_ROWS = 10
MAX_EXAMPLES = 5

# A text column is read as numbers, or as dates, when at least this share of its
# values parse as one.
PARSE_SHARE = 0.8

MIN_VALUES_FOR_OUTLIERS = 10

# ── reading a value ──────────────────────────────────────────────────────────

CURRENCY = re.compile(r"^(R\$|US\$|\$|€|£)\s*")

NUMBER_SHAPES = {
    # 1234 · 1234.56 · -0.5
    "plain": re.compile(r"^-?\d+(\.\d+)?$"),
    # 1.234 · 1.234,56 · 1234,56 — the decimal mark is the comma
    "brazilian": re.compile(r"^-?(\d{1,3}(\.\d{3})+(,\d+)?|\d+,\d+)$"),
    # 1,234 · 1,234.56 — the comma groups thousands
    "us": re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$"),
}

DATE_SHAPES = {
    "iso": re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})"),
    "slashed": re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$"),
    "dashed": re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"),
    "dotted": re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"),
}

SUBTOTAL_LABEL = re.compile(
    r"\b(sub\s*-?\s*totais|sub\s*-?\s*total|total|totais|soma|grand total)\b"
)

# What people type when there is no value.
PLACEHOLDERS = {
    "",
    "-",
    "--",
    "—",
    "–",
    "?",
    "n/a",
    "na",
    "n/d",
    "nd",
    "null",
    "none",
    "nan",
    "sem dado",
    "sem dados",
    "#n/d",
    "#n/a",
}


def readings(value: str) -> dict[str, float]:
    """Every way a text could be a number: {"brazilian": 1234.0, "plain": 1.234}.

    Several entries means the text is ambiguous — "1.234" is a thousand two
    hundred and thirty-four in Brazil and one point two three four elsewhere.
    """
    text = CURRENCY.sub("", value.strip())
    found = {}

    for shape, pattern in NUMBER_SHAPES.items():
        if pattern.match(text):
            found[shape] = as_number(text, shape)

    return found


def as_number(text: str, shape: str) -> float:
    if shape == "brazilian":
        return float(text.replace(".", "").replace(",", "."))

    if shape == "us":
        return float(text.replace(",", ""))

    return float(text)


def has_currency(value: str) -> bool:
    return CURRENCY.match(value.strip()) is not None


def date_reading(value: str) -> str | None:
    """How a text is written as a date: iso, dd/mm, mm/dd, ambiguous — or None."""
    text = value.strip()

    if DATE_SHAPES["iso"].match(text):
        return "iso"

    for shape in ("slashed", "dashed", "dotted"):
        match = DATE_SHAPES[shape].match(text)
        if match is None:
            continue

        first = int(match.group(1))
        second = int(match.group(2))

        if first > 12 and second <= 12:
            return "dd/mm"

        if second > 12 and first <= 12:
            return "mm/dd"

        if first <= 12 and second <= 12:
            return "ambiguous"

    return None


def normalised(label: str) -> str:
    """A label with case, accents and spacing taken away — what is left is what
    two spellings of the same category share."""
    decomposed = unicodedata.normalize("NFKD", label)
    letters = "".join(c for c in decomposed if not unicodedata.combining(c))

    return " ".join(letters.casefold().split())


def is_placeholder(value: str) -> bool:
    return normalised(value) in PLACEHOLDERS


# ── a table, as the detectors see it ─────────────────────────────────────────


@dataclass
class Table:
    """A table with the arithmetic every detector needs done once.

    Detectors walk the frame by position; findings speak in rows as a person
    sees them in the file. The frame's index still holds each record's place in
    the file — blank lines were dropped without renumbering — and `first_row` is
    the file row of index 0.
    """

    frame: Any
    first_row: int
    numbers: dict[str, Any]
    subtotals: list[int]

    def row(self, position: int) -> int:
        label = self.frame.index[position]
        return self.first_row + int(label)


def describe(frame: Any, first_row: int) -> Table:
    table = Table(frame=frame, first_row=first_row, numbers={}, subtotals=[])

    for name in frame.columns:
        values = numeric_view(frame[name])
        if values is not None:
            table.numbers[str(name)] = values

    table.subtotals = subtotal_positions(table)
    return table


def text_values(series: Any) -> Any:
    """The non-empty values of a column holding text, or None if it holds none."""
    if series.dtype.kind in "biufcmM":
        return None

    present = series.dropna()
    present = present[present.map(lambda v: isinstance(v, str))]

    if len(present) == 0:
        return None

    return present


def numeric_view(series: Any) -> Any:
    """The column as floats — directly when numeric, or when it is text whose
    values read as numbers in one dominant format. None otherwise."""
    import pandas as pd

    if series.dtype.kind in "biuf":
        return series.astype(float)

    values = text_values(series)
    if values is None:
        return None

    meaningful = values[~values.map(is_placeholder)]
    if len(meaningful) == 0:
        return None

    parsed = meaningful.map(readings)
    shapes: Counter[str] = Counter()
    for found in parsed:
        if len(found) == 1:
            # The shapes' names, not the parsed numbers, are what is counted.
            shapes.update(found.keys())

    if not shapes:
        return None

    parses = parsed.map(len) > 0
    if parses.mean() < PARSE_SHARE:
        return None

    dominant = shapes.most_common(1)[0][0]
    numbers = pd.Series(float("nan"), index=series.index)

    for position, found in parsed.items():
        if dominant in found:
            numbers[position] = found[dominant]

    return numbers


def finding(kind: str, message: str, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"kind": kind, "message": message}

    for key, value in details.items():
        result[key] = value

    return result


def positions_to_rows(table: Table, positions: list[int]) -> list[int]:
    rows = []
    for position in positions[:MAX_ROWS]:
        rows.append(table.row(position))

    return rows


# ── the detectors ────────────────────────────────────────────────────────────


def subtotal_positions(table: Table) -> list[int]:
    frame = table.frame
    positions = []

    for index, (_, record) in enumerate(frame.iterrows()):
        for value in record:
            if isinstance(value, str) and SUBTOTAL_LABEL.search(normalised(value)):
                positions.append(index)
                break

    return positions


def subtotal_rows(table: Table) -> list[dict[str, Any]]:
    if not table.subtotals:
        return []

    # A row labelled "total" that also equals the sum of the records since the
    # previous total is almost certainly a total; saying so is what makes the
    # finding believable.
    confirmed = []
    start = 0

    for position in table.subtotals:
        for name, values in table.numbers.items():
            if sums_the_rows_above(values, start, position):
                confirmed.append({"row": table.row(position), "column": name})
                break

        start = position + 1

    count = len(table.subtotals)
    rows = positions_to_rows(table, table.subtotals)
    message = (
        f"{count} row(s) look like totals mixed in with the records (rows {rows}). "
        "Summing the column with them in counts those values twice."
    )

    return [finding("subtotal_rows", message, rows=rows, count=count, sums_checked=confirmed)]


def sums_the_rows_above(values: Any, start: int, position: int) -> bool:
    total = values.iloc[position]
    if math.isnan(total) or position == start:
        return False

    above = values.iloc[start:position].sum()

    return math.isclose(above, total, rel_tol=1e-6, abs_tol=0.01)


def exact_duplicates(table: Table) -> list[dict[str, Any]]:
    duplicated = table.frame.duplicated(keep="first")
    count = int(duplicated.sum())

    if count == 0:
        return []

    positions = [i for i, flag in enumerate(duplicated) if flag]
    rows = positions_to_rows(table, positions)
    message = f"{count} row(s) are exact copies of an earlier row (rows {rows})."

    return [finding("exact_duplicates", message, rows=rows, count=count)]


def number_formats(table: Table) -> list[dict[str, Any]]:
    findings = []

    for name in table.frame.columns:
        values = text_values(table.frame[name])
        if values is None or str(name) not in table.numbers:
            continue

        shapes: Counter[str] = Counter()
        ambiguous = []
        currency = 0

        for value in values:
            if is_placeholder(value):
                continue

            found = readings(value)
            if has_currency(value):
                currency += 1

            if len(found) == 1:
                shapes.update(found.keys())

            if len(found) > 1 and len(ambiguous) < MAX_EXAMPLES:
                ambiguous.append({"value": value, "readings": found})

        formats = dict(shapes)
        if currency:
            formats["with_currency"] = currency

        mixed = len(shapes) > 1 or 0 < currency < len(values)

        message = f"'{name}' holds numbers written as text ({', '.join(formats)})."
        if mixed:
            message += " The formats are mixed."
        if ambiguous:
            message += " Some values read two ways."

        findings.append(
            finding(
                "number_formats",
                message,
                column=str(name),
                formats=formats,
                mixed=mixed,
                ambiguous=ambiguous,
            )
        )

    return findings


def date_formats(table: Table) -> list[dict[str, Any]]:
    findings = []

    for name in table.frame.columns:
        values = text_values(table.frame[name])
        if values is None:
            continue

        kinds = values.map(date_reading)
        dated = kinds.dropna()
        if len(dated) == 0 or len(dated) / len(values) < PARSE_SHARE:
            continue

        counted = dict(Counter(dated))
        written = set(counted) - {"ambiguous"}

        examples = []
        if "ambiguous" in counted and "dd/mm" not in written and "mm/dd" not in written:
            for value in values[kinds == "ambiguous"].head(MAX_EXAMPLES):
                first, second = re.split(r"[/.\-]", value.strip())[:2]
                examples.append(
                    {
                        "value": value,
                        "as_dd_mm": f"day {first}, month {second}",
                        "as_mm_dd": f"month {first}, day {second}",
                    }
                )

        mixed = len(written) > 1
        if not mixed and not examples and written <= {"iso"}:
            continue

        message = f"'{name}' holds dates written as text ({', '.join(counted)})."
        if mixed:
            message += " The formats are mixed."
        if examples:
            message += " No value settles day-first or month-first; both readings are possible."

        findings.append(
            finding("date_formats", message, column=str(name), formats=counted, ambiguous=examples)
        )

    return findings


def inconsistent_labels(table: Table) -> list[dict[str, Any]]:
    findings = []

    for name in table.frame.columns:
        values = text_values(table.frame[name])
        if values is None or str(name) in table.numbers:
            continue

        distinct = values.unique()
        if len(distinct) > 200:
            continue

        groups: dict[str, Counter[str]] = {}
        for value in values:
            if is_placeholder(value):
                continue
            groups.setdefault(normalised(value), Counter())[value] += 1

        variants = []
        for spellings in groups.values():
            if len(spellings) > 1:
                variants.append(dict(spellings))

        if not variants:
            continue

        message = (
            f"'{name}' spells the same label more than one way "
            f"({len(variants)} label(s)); grouping by it splits them."
        )
        findings.append(
            finding("inconsistent_labels", message, column=str(name), variants=variants)
        )

    return findings


def contradicting_columns(table: Table) -> list[dict[str, Any]]:
    """A column that is the product of two others on most rows — and is not on
    some. revenue ≠ quantity × price, without knowing which is which by name."""
    findings = []
    names = list(table.numbers)[:12]
    excluded = set(table.subtotals)

    for left, right in itertools.combinations(names, 2):
        for result in names:
            if result in (left, right):
                continue

            a = table.numbers[left]
            b = table.numbers[right]
            c = table.numbers[result]

            usable = []
            for position in range(len(c)):
                values = (a.iloc[position], b.iloc[position], c.iloc[position])
                if position not in excluded and not any(math.isnan(v) for v in values):
                    usable.append(position)

            if len(usable) < 3:
                continue

            holds = []
            breaks = []
            for position in usable:
                expected = a.iloc[position] * b.iloc[position]
                actual = c.iloc[position]
                if math.isclose(expected, actual, rel_tol=0.01, abs_tol=0.01):
                    holds.append(position)
                else:
                    breaks.append(position)

            if not breaks or len(holds) / len(usable) < PARSE_SHARE:
                continue

            rows = positions_to_rows(table, breaks)
            message = (
                f"'{result}' equals '{left}' × '{right}' on {len(holds)} of {len(usable)} "
                f"rows, but not on rows {rows}."
            )
            findings.append(
                finding(
                    "contradicting_columns",
                    message,
                    columns=[result, left, right],
                    rows=rows,
                    count=len(breaks),
                )
            )

    return findings


def dominating_values(table: Table) -> list[dict[str, Any]]:
    findings = []
    excluded = set(table.subtotals)

    for name, values in table.numbers.items():
        kept = [
            (position, values.iloc[position])
            for position in range(len(values))
            if position not in excluded and not math.isnan(values.iloc[position])
        ]

        # Below ten values, one value being half the total is just a small table.
        if len(kept) < MIN_VALUES_FOR_OUTLIERS or any(value < 0 for _, value in kept):
            continue

        total = sum(value for _, value in kept)
        if total <= 0:
            continue

        ordered = sorted(value for _, value in kept)
        quarter = len(ordered) // 4
        q1 = ordered[quarter]
        q3 = ordered[-quarter - 1]
        fence = q3 + 3 * (q3 - q1)

        for position, value in kept:
            share = value / total
            if share >= 0.5 and value > fence:
                row = table.row(position)
                message = (
                    f"One value in '{name}' (row {row}) is {share:.0%} of the column's "
                    "total. Check it is real before it drives every sum."
                )
                findings.append(
                    finding(
                        "dominating_value",
                        message,
                        column=name,
                        rows=[row],
                        share=round(share, 4),
                    )
                )

    return findings


def missing_values(table: Table) -> list[dict[str, Any]]:
    findings = []
    frame = table.frame

    for name in frame.columns:
        series = frame[name]
        empty = int(series.isna().sum())

        placeholders: Counter[str] = Counter()
        values = text_values(series)
        if values is not None:
            for value in values:
                if is_placeholder(value):
                    placeholders[value] += 1

        missing = empty + sum(placeholders.values())
        if missing == 0:
            continue

        share = missing / max(len(frame), 1)
        if not placeholders and share < 0.2:
            continue

        message = f"'{name}' is missing {missing} of {len(frame)} value(s)"
        if placeholders:
            written = sum(placeholders.values())
            spellings = ", ".join(placeholders)
            message += f", {written} of them written as text ({spellings})"
        message += "."

        findings.append(
            finding(
                "missing_values",
                message,
                column=str(name),
                count=missing,
                placeholders=dict(placeholders),
            )
        )

    return findings


DETECTORS = [
    subtotal_rows,
    exact_duplicates,
    number_formats,
    date_formats,
    inconsistent_labels,
    contradicting_columns,
    dominating_values,
    missing_values,
]


def table_findings(frame: Any, first_row: int) -> list[dict[str, Any]]:
    table = describe(frame, first_row)
    findings = []

    for detector in DETECTORS:
        findings.extend(detector(table))

    return findings


# ── before the table: where it starts, and which one it is ───────────────────


def header_row(raw: Any) -> int:
    """The position of the header in a table read with no header at all.

    The first row that is about as wide as the table and made only of labels —
    text that is neither a number nor a date. Title lines above it are narrower;
    data rows below it hold numbers.
    """
    widths = raw.notna().sum(axis=1)
    if len(widths) == 0:
        return 0

    widest = int(widths.max())
    needed = max(2, math.ceil(0.8 * widest))

    for position, (_, record) in enumerate(raw.iterrows()):
        present = [v for v in record if isinstance(v, str) and v.strip()]
        if len(present) < needed:
            continue

        labels = all(not readings(v) and date_reading(v) is None for v in present)
        if labels and len(set(present)) == len(present):
            return position

    return 0


def misplaced_header(position: int, raw: Any) -> list[dict[str, Any]]:
    if position == 0:
        return []

    above = []
    for _, record in raw.iloc[:position].iterrows():
        text = " ".join(str(v) for v in record if isinstance(v, str) and v.strip())
        if text:
            above.append(text[:80])

    message = (
        f"The header is on row {position + 1}, not row 1. The rows above it are not "
        "data; the table is described from the header down."
    )

    return [finding("header_not_on_first_row", message, header_row=position + 1, above=above)]


def first_sheet_not_the_data(sheets: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    if len(sheets) < 2:
        return []

    sizes = [(name, int(frame.notna().sum().sum())) for name, frame in sheets]
    largest_name, largest = max(sizes, key=lambda pair: pair[1])
    first_name, first = sizes[0]

    if largest_name == first_name or first >= 0.1 * largest:
        return []

    message = (
        f"The first sheet, '{first_name}', holds almost nothing ({first} cell(s)); "
        f"the data looks to be on '{largest_name}'. Reading the file without naming a "
        "sheet reads the first one."
    )

    return [finding("data_not_on_first_sheet", message, first=first_name, largest=largest_name)]
