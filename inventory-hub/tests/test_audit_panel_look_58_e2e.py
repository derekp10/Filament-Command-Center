"""Group 58, Derek's second look (2026-11-03, section H), on the real dashboard with Bootstrap
and the page's own polls: the dock (sample 1b) at the five window sizes the double-click
sweep uses, on a short list and a big shelf.

FCC's routes are answered in this browser on their real shapes
(test_audit_double_click_58_e2e.Sweep, every request that isn't a GET answered there), so
nothing reaches dev but reads, and dev's own audit stays idle.

The rules are proved hermetically in test_audit_panel_look_58_js.py; a real double click on
every control of the panel, the dock's included, in test_audit_double_click_58_e2e.py.
"""
from __future__ import annotations

import pytest

from test_audit_double_click_58_e2e import BODY, SIZES, board  # noqa: F401  (board: the fixture)

pytestmark = pytest.mark.usefixtures("require_server")

DOCK = "#fcc-audit-panel-dock"
TALLY = "#fcc-audit-panel-tally"
CONTROLS = ["#fcc-audit-panel-needlabel", "#fcc-audit-panel-done", "#fcc-audit-panel-cancel",
            "#fcc-audit-panel-qr-needlabel", "#fcc-audit-panel-qr-done", "#fcc-audit-panel-qr-cancel"]
QRS = CONTROLS[3:]

# What is wholly seen of each of `sels`: its four corners (2 px in) and its middle hit-test to it.
UNSEEN = r"""(sels) => sels.filter((s) => { const e = document.querySelector(s); if (!e) return true;
    const r = e.getBoundingClientRect(); if (r.width < 4 || r.height < 4) return true;
    return ![[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2],
             [r.left + r.width / 2, r.top + r.height / 2]].every(([x, y]) => {
        const h = document.elementFromPoint(x, y); return !!h && e.contains(h); }); })"""
# The tiles wholly in the body's view now, and the QR boxes' top edges.
GEOMETRY = r"""([body, qrs, dock]) => { const b = document.querySelector(body).getBoundingClientRect();
    const whole = Array.from(document.querySelectorAll(body + ' .fcc-audit-tile')).filter((t) => {
        const r = t.getBoundingClientRect(); return r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5; }).length;
    return { whole, tops: qrs.map((q) => document.querySelector(q).getBoundingClientRect().top),
             dock: document.querySelector(dock).getBoundingClientRect().top,
             flow: document.getElementById('fcc-audit-panel-scroll').classList.contains('fcc-audit-scroll-flow') }; }"""


@pytest.mark.parametrize("rows", [6, 24], ids=["6-spools", "24-spools"])
def test_the_dock_keeps_the_exits_and_the_tally_in_view_at_every_size(board, rows):
    """At the top of a big shelf, its middle and its end: Needs a label, Done and Cancel
    Audit and their three QRs, in one row, and the tally above the list, wholly seen with
    no scroll of their own, and the list keeps at least a tile row. RED on 517abe1: Done,
    Cancel and their QRs were seen only at the list's end."""
    page = board.page
    board.begin(rows, rows // 2, last=0)
    what = f"{board.size[0]}x{board.size[1]}, {rows} spools"
    docks = []
    for at in ("0", "b.scrollHeight / 2", "b.scrollHeight"):
        page.evaluate(f"(s) => {{ const b = document.querySelector(s); b.scrollTop = {at}; }}", BODY)
        page.wait_for_timeout(50)
        assert page.evaluate(UNSEEN, CONTROLS + [TALLY, "#fcc-audit-last-found"]) == [], (what, at)
        got = page.evaluate(GEOMETRY, [BODY, QRS, DOCK])
        assert got["flow"] is False, (what, got)
        assert max(got["tops"]) - min(got["tops"]) <= 1, (what, got)
        assert got["whole"] >= min(2, rows), (what, at, got)
        docks.append(got["dock"])
    assert docks[0] == docks[1] == docks[2], (what, docks)      # the dock never scrolled
