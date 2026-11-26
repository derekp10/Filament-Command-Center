"""Group 65's picture walk (Derek, 2026-11-24): the 🔁 spool-changed Activity Log line names
each changed head as the card's rows do.

The card's banner said "toolhead position(s) 0" over rows that said "HEAD-1", and its line
in the Activity Log "at toolhead position(s) [0]". Both now name the head ("on RCOI-1"),
from the card's rows, else its heads, and "T2" (the slicer's tool, as the card's lines say
it) only for a head FCC has no name for. The real route runs over tests/deduct_wire_harness.py
(the 43.4 rig); the banner's twin is test_spool_changed_heads_named_65_js.py.

Red on fadc6409.
"""
from __future__ import annotations

import pytest

import print_deduct
from test_cancel_review_keeps_every_head_43_4 import (  # noqa: F401  (_isolated_stores: autouse)
    INDX, JOB, _ctx3, _isolated_stores, _rec, _sm3, logs)
from deduct_wire_harness import _start, _stop


def _route(changed):
    sm = _sm3()
    ctx = _ctx3(sm)
    _start(ctx)
    try:
        return print_deduct._route_completion_to_review(
            INDX, "f.bgcode", JOB, {0: 7.0, 1: 10.0}, "http://fb", changed)
    finally:
        _stop(ctx)


@pytest.mark.parametrize("changed, said", [
    ([0], "spool changed mid-print ('f.bgcode') on RCOI-1 — "),
    ([1, 0], "spool changed mid-print ('f.bgcode') on RCOI-1 and RCOI-2 — "),
])
def test_the_line_names_each_changed_head_as_the_cards_rows_do(logs, changed, said):
    out = _route(changed)
    assert out["status"] == "pending_spool_changed", out
    assert [r["toolhead"] for r in _rec()["spools"]] == ["RCOI-1", "RCOI-2"]
    line = next(m for m, _ in logs if "spool changed mid-print" in m)
    assert said in line and "position" not in line, line


def test_a_head_with_no_row_is_named_from_the_cards_heads_else_as_the_slicers_tool():
    rows = [{"toolhead": "XL-2", "position": 1}]
    heads = [{"toolhead": "XL-3", "position": 2, "sid": 5}]
    assert print_deduct._changed_heads_words([1, 2, 4], rows, heads) == "XL-2, XL-3 and T4"
    assert print_deduct._changed_heads_words([2], rows, heads) == "XL-3"
    assert print_deduct._changed_heads_words([], rows, heads) == ""
    assert print_deduct._changed_heads_words([0], [{"toolhead": "<b>H</b>", "position": 0}]) == "&lt;b&gt;H&lt;/b&gt;"
