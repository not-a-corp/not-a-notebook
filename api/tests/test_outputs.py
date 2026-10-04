"""Jupyter messages become the domain's outputs, richest MIME type first."""

from __future__ import annotations

from app.domain.runtime import (
    ErrorOutput,
    ImageOutput,
    PlotlyOutput,
    StreamOutput,
    TableOutput,
    TextOutput,
)
from app.runtime.jupyter_outputs import PLOTLY_MIME, TABLE_MIME, from_message


def test_a_stream_keeps_its_name_and_text() -> None:
    output = from_message("stream", {"name": "stderr", "text": "careful\n"})

    assert output == StreamOutput(name="stderr", text="careful\n")


def test_an_error_loses_its_terminal_colours() -> None:
    content = {
        "ename": "KeyError",
        "evalue": "'region'",
        "traceback": ["\x1b[31mKeyError\x1b[39m: 'region'", "\x1b[1;32mline 3\x1b[0m"],
    }

    output = from_message("error", content)

    assert output == ErrorOutput(
        name="KeyError",
        value="'region'",
        traceback=["KeyError: 'region'", "line 3"],
    )


def test_a_plotly_spec_wins_over_everything_else() -> None:
    bundle = {PLOTLY_MIME: {"data": [], "layout": {}}, "text/html": "<div>", "text/plain": "Fig"}

    output = from_message("display_data", {"data": bundle})

    assert output == PlotlyOutput(spec={"data": [], "layout": {}})


def test_a_table_wins_over_its_html_and_text() -> None:
    table = {"columns": ["a"], "rows": [[1]], "total_rows": 1}
    bundle = {TABLE_MIME: table, "text/html": "<table>", "text/plain": "   a\n0  1"}

    output = from_message("execute_result", {"data": bundle, "execution_count": 3})

    assert output == TableOutput(columns=["a"], rows=[[1]], total_rows=1)


def test_a_png_wins_over_its_text() -> None:
    bundle = {"image/png": "iVBORw0KGgo=", "text/plain": "<Figure size 640x480>"}

    output = from_message("display_data", {"data": bundle})

    assert output == ImageOutput(png="iVBORw0KGgo=")


def test_plain_text_is_the_last_resort() -> None:
    output = from_message("execute_result", {"data": {"text/plain": "2"}})

    assert output == TextOutput(text="2")


def test_html_alone_is_dropped() -> None:
    assert from_message("display_data", {"data": {"text/html": "<b>hi</b>"}}) is None


def test_messages_without_output_carry_none() -> None:
    assert from_message("status", {"execution_state": "busy"}) is None
    assert from_message("execute_input", {"code": "1 + 1"}) is None
