"""How the kernel shows a table: as data, not as HTML.

A pandas or polars object left as a cell's last expression is displayed with one
more MIME type beside the usual ones:

    application/vnd.not-a-notebook.table+json
    {"columns": [...], "rows": [[...], ...], "total_rows": 1234}

The API turns that into the `table` output — the client draws it, in its own
style, and at most 100 rows ever travel. HTML tables would be the kernel's style
and every row.

Loaded as an IPython extension (see ipython_kernel_config.py), so nothing it
defines lands in the namespace the generated code and the model see.
"""

from __future__ import annotations

import json
from typing import Any

from IPython.core.formatters import BaseFormatter
from IPython.core.interactiveshell import InteractiveShell
from traitlets import ObjectName, Unicode

TABLE_MIME = "application/vnd.not-a-notebook.table+json"
MAX_ROWS = 100


class TableFormatter(BaseFormatter):  # type: ignore[misc]
    format_type = Unicode(TABLE_MIME)
    print_method = ObjectName("_repr_not_a_notebook_table_")
    _return_type = (dict,)


def pandas_table(value: Any) -> dict[str, Any]:
    import pandas as pd

    frame = value
    if isinstance(value, pd.Series):
        frame = value.to_frame()

    # A grouped result keeps its keys in the index; they are columns to whoever
    # reads the table. The default 0..n index is noise, and is dropped.
    if not isinstance(frame.index, pd.RangeIndex):
        frame = frame.reset_index()

    head = frame.head(MAX_ROWS)

    # to_json, not .values: it already turns NaN into null, timestamps into ISO
    # strings and numpy scalars into plain numbers — everything JSON can carry.
    encoded = head.to_json(orient="split", date_format="iso", index=False)
    split = json.loads(encoded)

    columns = []
    for column in split["columns"]:
        columns.append(str(column))

    return {
        "columns": columns,
        "rows": split["data"],
        "total_rows": len(frame),
    }


def polars_table(value: Any) -> dict[str, Any]:
    import polars as pl

    frame = value
    if isinstance(value, pl.Series):
        frame = value.to_frame()

    head = frame.head(MAX_ROWS).to_pandas()
    table = pandas_table(head)
    table["total_rows"] = frame.height

    return table


def load_ipython_extension(shell: InteractiveShell) -> None:
    display = shell.display_formatter
    formatter = TableFormatter(parent=display)
    display.formatters[TABLE_MIME] = formatter

    # By name, so that loading the extension imports neither library: a kernel
    # that never touches pandas does not pay for it at startup.
    formatter.for_type_by_name("pandas", "DataFrame", pandas_table)
    formatter.for_type_by_name("pandas", "Series", pandas_table)
    formatter.for_type_by_name("polars.dataframe.frame", "DataFrame", polars_table)
    formatter.for_type_by_name("polars.series.series", "Series", polars_table)
