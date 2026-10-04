"""What the model knows about a file: its profile, computed here, inside the sandbox.

The model never sees the raw rows. It sees this — format, tables, columns, types,
missing values, a few sample values — and writes code against it.

Called by the API as one expression that leaves no name behind in the kernel's
namespace:

    __import__("not_a_notebook_profile").emit("/data/sales.csv")

which prints the profile as one JSON document on stdout. A file that cannot be
read is still a profile — `"readable": false` and why — because "this is not a
CSV" is exactly what the user needs to hear before asking anything.

This is the profile's skeleton. The data-quality findings the README promises —
subtotal rows, mixed formats, a header off row 1 — are detectors added to it,
one at a time, each with its own test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAMPLES = 5
MAX_SAMPLE_CHARACTERS = 80
MAX_COLUMNS = 500

FORMATS = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".xlsx": "excel",
    ".xlsm": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
}

# Tried in order. UTF-8 first; Latin-1 decodes any byte sequence at all, so it is
# the last resort that always succeeds — and the one Brazilian spreadsheets
# exported from older Excel installs tend to need.
ENCODINGS = ["utf-8-sig", "latin-1"]


@dataclass(frozen=True)
class Reading:
    """Every table in a file, with what was learned reading it."""

    tables: list[tuple[str | None, Any]]
    # The encoding that decoded a CSV or TSV; None for binary formats.
    encoding: str | None = None
    # A workbook's sheets, in its own order; None for single-table formats.
    sheets: list[str] | None = None


def emit(path: str) -> None:
    profile = profile_of(path)
    print(json.dumps(profile, ensure_ascii=False, default=str))


def profile_of(path: str) -> dict[str, Any]:
    extension = Path(path).suffix.lower()
    file_format = FORMATS.get(extension, "unknown")

    try:
        reading = read_tables(path, file_format)
    except Exception as exc:  # noqa: BLE001 — any failure to read is the finding
        return {
            "format": file_format,
            "readable": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    table_profiles = []
    for sheet, frame in reading.tables:
        table_profiles.append(table_profile(sheet, frame))

    return {
        "format": file_format,
        "readable": True,
        "encoding": reading.encoding,
        "sheets": reading.sheets,
        "tables": table_profiles,
    }


def read_tables(path: str, file_format: str) -> Reading:
    import pandas as pd

    if file_format in ("csv", "tsv"):
        return read_delimited(path, file_format)

    if file_format == "excel":
        workbook = pd.read_excel(path, sheet_name=None)

        tables: list[tuple[str | None, Any]] = []
        sheets = []
        for name, frame in workbook.items():
            tables.append((str(name), frame))
            sheets.append(str(name))

        # In the workbook's order: the sheet that matters is not always the first.
        return Reading(tables=tables, sheets=sheets)

    if file_format == "parquet":
        frame = pd.read_parquet(path)
        return Reading(tables=[(None, frame)])

    raise ValueError(f"not a format this sandbox reads: {Path(path).suffix}")


def read_delimited(path: str, file_format: str) -> Reading:
    import pandas as pd

    # A CSV from a Brazilian Excel is separated by ";", because "," is the
    # decimal mark. The python engine sniffs the separator; a TSV needs none.
    separator = None
    if file_format == "tsv":
        separator = "\t"

    last_error: Exception | None = None

    for encoding in ENCODINGS:
        try:
            frame = pd.read_csv(path, sep=separator, engine="python", encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        return Reading(tables=[(None, frame)], encoding=encoding)

    assert last_error is not None
    raise last_error


def table_profile(sheet: str | None, frame: Any) -> dict[str, Any]:
    columns = []
    for name in list(frame.columns)[:MAX_COLUMNS]:
        column = column_profile(name, frame[name])
        columns.append(column)

    return {
        "sheet": sheet,
        "rows": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": columns,
    }


def column_profile(name: Any, series: Any) -> dict[str, Any]:
    present = series.dropna()

    samples = []
    for value in present.unique()[:SAMPLES]:
        text = str(value)[:MAX_SAMPLE_CHARACTERS]
        samples.append(text)

    return {
        "name": str(name),
        "dtype": str(series.dtype),
        "missing": int(series.isna().sum()),
        "distinct": int(present.nunique()),
        "samples": samples,
    }
