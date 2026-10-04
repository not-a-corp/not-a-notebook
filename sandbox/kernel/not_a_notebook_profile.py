"""What the model knows about a file: its profile, computed here, inside the sandbox.

The model never sees the raw rows. It sees this — format, tables, columns, types,
missing values, a few sample values — and writes code against it.

Called by the API as one expression that leaves no name behind in the kernel's
namespace:

    __import__("not_a_notebook_profile").emit("/data/sales.csv")

which prints the profile as one JSON document on stdout. A file that cannot be
read is still a profile — `"readable": false` and why — because "this is not a
CSV" is exactly what the user needs to hear before asking anything.

Each table carries its findings — subtotal rows, mixed formats, a header off row
1, and the rest of what the README promises — from not_a_notebook_findings.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from not_a_notebook_findings import (
    first_sheet_not_the_data,
    header_row,
    misplaced_header,
    table_findings,
)

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

# Enough lines to see past a report's title block to its header and some data.
SNIFF_LINES = 50

SEPARATORS = [",", ";", "\t", "|"]


@dataclass(frozen=True)
class Read:
    """One table, read from its header down."""

    sheet: str | None
    frame: Any
    # The row, as numbered in the file, of the frame's index 0.
    first_row: int
    # The header's own finding, if it was not on the first row.
    findings: list[dict[str, Any]]


@dataclass(frozen=True)
class Reading:
    """Every table in a file, with what was learned reading it."""

    tables: list[Read]
    # The encoding that decoded a CSV or TSV; None for binary formats.
    encoding: str | None = None
    # A workbook's sheets, in its own order; None for single-table formats.
    sheets: list[str] | None = None
    # About the file as a whole — a workbook whose data is not on its first sheet.
    findings: list[dict[str, Any]] | None = None


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
    for read in reading.tables:
        table_profiles.append(table_profile(read))

    file_findings = reading.findings or []

    return {
        "format": file_format,
        "readable": True,
        "encoding": reading.encoding,
        "sheets": reading.sheets,
        "findings": file_findings,
        "tables": table_profiles,
    }


def read_tables(path: str, file_format: str) -> Reading:
    if file_format in ("csv", "tsv"):
        return read_delimited(path, file_format)

    if file_format == "excel":
        return read_workbook(path)

    if file_format == "parquet":
        import pandas as pd

        frame = pd.read_parquet(path)
        # No header line in a Parquet file: row 1 is the first record.
        read = Read(sheet=None, frame=frame, first_row=1, findings=[])
        return Reading(tables=[read])

    raise ValueError(f"not a format this sandbox reads: {Path(path).suffix}")


def read_delimited(path: str, file_format: str) -> Reading:
    import pandas as pd

    raw_bytes = Path(path).read_bytes()
    text, encoding = decode(raw_bytes)
    lines = text.splitlines()

    separator = "\t"
    if file_format == "csv":
        separator = sniff_separator(lines[:SNIFF_LINES])

    raw = raw_rows(lines[:SNIFF_LINES], separator)
    header = header_row(raw)

    # Blank lines kept, then dropped by hand, so a row's index still says which
    # line of the file it came from.
    frame = pd.read_csv(
        io.StringIO(text),
        sep=separator,
        skiprows=header,
        skip_blank_lines=False,
    )
    frame = frame.dropna(how="all")

    read = Read(
        sheet=None,
        frame=frame,
        first_row=header + 2,
        findings=misplaced_header(header, raw),
    )

    return Reading(tables=[read], encoding=encoding)


def read_workbook(path: str) -> Reading:
    import pandas as pd

    raw_sheets = pd.read_excel(path, sheet_name=None, header=None, nrows=SNIFF_LINES)

    tables = []
    sheets = []
    for name, raw in raw_sheets.items():
        header = header_row(raw)
        frame = pd.read_excel(path, sheet_name=name, header=header)
        frame = frame.dropna(how="all")

        read = Read(
            sheet=str(name),
            frame=frame,
            first_row=header + 2,
            findings=misplaced_header(header, raw),
        )
        tables.append(read)
        sheets.append(str(name))

    sized = []
    for read in tables:
        sized.append((read.sheet or "", read.frame))

    # In the workbook's order: the sheet that matters is not always the first.
    return Reading(tables=tables, sheets=sheets, findings=first_sheet_not_the_data(sized))


def decode(raw: bytes) -> tuple[str, str]:
    last_error: Exception | None = None

    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc

    assert last_error is not None
    raise last_error


def sniff_separator(lines: list[str]) -> str:
    """The separator most lines agree on.

    Not pandas' own sniffing, which reads the first line only — and the first line
    of a report is often its title. For each candidate, count it on every line;
    the winner is the one whose most common count, above zero, the most lines
    share. A Brazilian CSV is ";": "," is its decimal mark.
    """
    best = ","
    best_agreement = 0

    for candidate in SEPARATORS:
        counts = Counter(line.count(candidate) for line in lines if line.strip())
        counts.pop(0, None)
        if not counts:
            continue

        agreement = counts.most_common(1)[0][1]
        if agreement > best_agreement:
            best = candidate
            best_agreement = agreement

    return best


def raw_rows(lines: list[str], separator: str) -> Any:
    """The first lines as cells, ragged rows padded, no header assumed."""
    import pandas as pd

    rows = []
    for record in csv.reader(lines, delimiter=separator):
        cells = []
        for cell in record:
            value = cell.strip() or None
            cells.append(value)
        rows.append(cells)

    return pd.DataFrame(rows)


def table_profile(read: Read) -> dict[str, Any]:
    frame = read.frame

    columns = []
    for name in list(frame.columns)[:MAX_COLUMNS]:
        column = column_profile(name, frame[name])
        columns.append(column)

    findings = list(read.findings)
    findings.extend(table_findings(frame, read.first_row))

    return {
        "sheet": read.sheet,
        "rows": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": columns,
        "findings": findings,
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
