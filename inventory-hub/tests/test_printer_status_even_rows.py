"""Printer Status: a printer's tiles in even rows beside its name (Derek,
2026-10-22).

The INDX's 8 heads used to drop under the printer's name whenever they didn't
fit beside it, and at Large and Extra Large wrap 7 + 1. Derek's call: when the
heads don't fit on one row beside the name, split them into the fewest rows
with EQUAL counts (8 -> 4 + 4, 7 -> 4 + 3, 10 -> 5 + 5; never a lone tile),
the tiles staying beside the name column like the XL row. Also: the tile's
material line goes from line-height 1.1 to 1.2, so a descender never clips.

Hermetic, and it RUNS under --offline: `isolated_page` (a chromium with no
route to any network) with the real static/css/global.css, text_size.js,
ui_builder.js, inv_core.js and inv_printer_status.js, and a few lines standing
in for the Bootstrap classes the widget uses (Bootstrap comes from a CDN).
The widget is fed made-up fleets through refreshPrinterStatusWidgetFromAggregate,
as the heartbeat feeds it. Pinned:
  - the rule itself (window.fccPrinterStatusTileRows): fewest rows, counts as
    equal as they can be, the longer rows first, beside the name when three or
    more fit there (or all of them), else under it; a row of one tile only
    where at most two fit across the row and the count is odd;
  - the layout: on Derek's 1600 x 1300 window the 8 heads are 4 + 4 and the 5
    stay one row, beside the name, at every Text size; narrower windows split
    as the rule says (1024: 4 + 4 and 3 + 2, or 3 + 3 + 2 at Extra Large; 800
    at Extra Large and a 412 px phone: under the name); every row's tiles fit
    the row (nothing sticks out);
  - it lays out again after a Text size change and a resize, after a repaint
    and the ▲▼ reorder, and after the widget is collapsed and opened again;
  - the material line's line height is 1.2 at every size.
The same on the real page (Bootstrap, the heartbeat, dev's container) is
test_printer_status_even_rows_e2e.py.

HEAD proof (0c965c7, this file alone in a throwaway worktree at HEAD): all 32
RED. HEAD has no rule (fccPrinterStatusTileRows) and no layout beyond
flex-wrap: on 1600 x 1300 the 8 heads under the name in one line of 8 at Small
and Standard, 7 + 1 at Large and Extra Large; 6 + 2 at 1366 px Extra Large,
5 + 3 at 1024 px, the 5 heads 4 + 1 at 1024 px Extra Large and 800 px (where
plain wrapping happens to draw what the rule draws, the layout's own record of
its split, data-rows, is missing); and a 1.1 material line.
"""
from __future__ import annotations

from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"

# The Bootstrap rules the widget's markup leans on, so the layout here is the
# page's (box-sizing, and the utility classes on the name column and the chip).
BOOTSTRAP_STANDIN = """
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; font-family: "Segoe UI", system-ui, sans-serif; line-height: 1.5; }
.d-flex { display: flex !important; }
.flex-column { flex-direction: column !important; }
.flex-wrap { flex-wrap: wrap !important; }
.align-items-center { align-items: center !important; }
.ms-2 { margin-left: .5rem !important; }
.ms-3 { margin-left: 1rem !important; }
.ms-auto { margin-left: auto !important; }
.gap-1 { gap: .25rem !important; }
.gap-2 { gap: .5rem !important; }
.fw-bold { font-weight: 700 !important; }
.text-info { color: #0dcaf0 !important; }
.text-light { color: #f8f9fa !important; }
.text-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
"""

PAGE = """<!doctype html><html data-fcc-text-size="standard"><head><meta charset="utf-8">
<style>{standin}</style><style>{css}</style></head><body>
<div id="printer-status-widget" class="fcc-ps-widget fcc-ps-loading">
    <div class="fcc-ps-header">
        <div class="fcc-ps-header-bar" onclick="window.togglePrinterStatusWidget()">
            <span class="fcc-ps-toggle">▾</span>
            <span class="fcc-ps-title">🖨️ Printer Status</span>
            <span class="fcc-ps-hint">click to collapse</span>
        </div>
        <div class="fcc-ps-header-chips d-flex flex-wrap align-items-center gap-1 ms-3"></div>
    </div>
    <div class="fcc-ps-body">
        <div class="fcc-ps-skeleton">Loading printer status…</div>
    </div>
</div>
</body></html>"""

PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.fetch = () => new Promise(() => {});
// This page has no origin, so the browser refuses it localStorage; the
// widget keeps its collapsed state there, so it gets one of its own.
(() => {
    const data = new Map();
    const store = { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)),
                    removeItem: (k) => data.delete(k), clear: () => data.clear() };
    Object.defineProperty(window, 'localStorage', { value: store, configurable: true });
})();
"""

INDX = "ZZ Even INDX"
XL = "ZZ Even XL"


def _item(sid, colour, material, grams=640):
    return {"id": sid, "display": f"#{sid} Even Test {material}", "color": colour, "color_direction": "longitudinal",
            "remaining_weight": grams, "initial_weight": 1000, "details": {"material": material}}


def _printer(prefix, n, state="IDLE", loaded=()):
    """`n` heads; the positions in `loaded` hold a spool with a material line
    (PETG and Polycarbonate: a "g" and a "y" to clip)."""
    mats = ["PETG", "Polycarbonate", "PLA Silk", "ASA"]
    return {"state": {"state": state, "is_active": state == "PRINTING"},
            "toolheads": [{"id": f"{prefix}-{i + 1}", "position": i, "unbound": False,
                           "item": _item(9200 + i, "2a6f97", mats[i % len(mats)]) if i in loaded else None,
                           "loaded_count": 1 if i in loaded else 0}
                          for i in range(n)]}


FLEET = {INDX: _printer("ZE", 8, loaded=(0, 3)), XL: _printer("ZX", 5, "PRINTING", loaded=(1, 2))}

# Per printer: the counts of each row of tiles, where they sit (beside / below
# the name), and whether any tile or row sticks out of the printer's row.
LAYOUT_JS = r"""() => {
    const out = {};
    document.querySelectorAll('#printer-status-widget .fcc-ps-row').forEach((row) => {
        const name = row.dataset.printer;
        const nameR = row.querySelector('.fcc-ps-name-col').getBoundingClientRect();
        const rowR = row.getBoundingClientRect();
        const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
        const lines = [];
        tiles.forEach((r) => {
            const line = lines.find((l) => Math.abs(l.top - r.top) < 2);
            if (line) line.n++; else lines.push({ top: r.top, n: 1 });
        });
        lines.sort((a, b) => a.top - b.top);
        // Beside: every tile right of the name column; below: every tile under it.
        const beside = tiles.every((r) => r.left >= nameR.right - 0.5);
        const below = tiles.every((r) => r.top >= nameR.bottom - 0.5);
        out[name] = { rows: lines.map((l) => l.n).join('+'), place: beside ? 'beside' : (below ? 'below' : 'mixed'),
                      out: tiles.filter((r) => r.right > rowR.right + 0.5 || r.left < rowR.left - 0.5).length,
                      data: (row.querySelector('.fcc-ps-toolheads').dataset.rows || null) };
    });
    return out;
}"""


@pytest.fixture
def widget(isolated_page):
    page = isolated_page
    page.set_content(PAGE.format(standin=BOOTSTRAP_STANDIN, css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("inv_core.js", "ui_builder.js", "inv_printer_status.js", "text_size.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    yield page
    assert page.evaluate("window.__errors") == []


def _feed(page, fleet=None):
    page.evaluate("(rows) => window.refreshPrinterStatusWidgetFromAggregate(rows)", fleet or FLEET)


def _size(page, name):
    """The Text size as Settings applies it (text_size.js: the attribute on
    <html> and the fcc:text-size event)."""
    page.evaluate("(n) => window.fccTextSize.apply(n)", name)


def _layout(page):
    return page.evaluate(LAYOUT_JS)


def _settled(page, want):
    """Wait until the layout reads `want` ({printer: rows}) — a resize lays the
    rows out on the next animation frame."""
    page.wait_for_function("""([js, want]) => { const got = (eval(js))();
        return Object.entries(want).every(([k, v]) => got[k] && got[k].rows === v); }""",
                           arg=[LAYOUT_JS, want], timeout=5000)


# --- the rule ------------------------------------------------------------------

@pytest.mark.parametrize("n, side, full, want", [
    (8, 7, 8, ("beside", [4, 4])),       # the INDX on 1600 px: 7 fit beside the name
    (8, 5, 7, ("beside", [4, 4])),       # ... at Extra Large: 5 fit
    (7, 5, 6, ("beside", [4, 3])),
    (10, 7, 8, ("beside", [5, 5])),
    (5, 7, 8, ("beside", [5])),          # the XL: one row
    (5, 4, 5, ("beside", [3, 2])),
    (8, 3, 4, ("beside", [3, 3, 2])),
    (7, 3, 4, ("beside", [3, 2, 2])),    # never 3 + 3 + 1
    (13, 4, 5, ("beside", [4, 3, 3, 3])),
    (2, 2, 3, ("beside", [2])),          # all of them fit, however few
    (8, 2, 3, ("below", [3, 3, 2])),     # under three beside: under the name
    (5, 0, 2, ("below", [2, 2, 1])),     # a phone: the one lone tile left
    (8, 0, 1, ("below", [1] * 8)),
    (1, 0, 1, ("below", [1])),
])
def test_the_rule(widget, n, side, full, want):
    got = widget.evaluate("([n, s, f]) => window.fccPrinterStatusTileRows(n, s, f)", [n, side, full])
    place, sizes = want
    assert ("below" if got["below"] else "beside", got["sizes"]) == (place, sizes), got
    assert got["rows"] == len(sizes) and got["cols"] == sizes[0], got


def test_the_rule_never_leaves_a_lone_tile_where_three_fit(widget):
    """Every count up to 16 heads, every room from 3 tiles: the rows differ by
    at most one, the longer first, as few as fit, and none holds a lone tile."""
    bad = widget.evaluate("""() => {
        const bad = [];
        for (let n = 1; n <= 16; n++) for (let side = 0; side <= 12; side++) for (let full = Math.max(side, 3); full <= 14; full++) {
            const r = window.fccPrinterStatusTileRows(n, side, full);
            const per = r.below ? full : side;
            const ok = r.sizes.reduce((a, b) => a + b, 0) === n && r.rows === Math.ceil(n / per)
                && r.sizes.every((s, i) => i === 0 || (s <= r.sizes[i - 1] && r.sizes[0] - s <= 1))
                && !(r.rows > 1 && r.sizes.includes(1)) && r.below === !(side >= n || side >= 3);
            if (!ok) bad.push([n, side, full, r]);
        }
        return bad.slice(0, 10); }""")
    assert bad == [], bad


# --- the layout ------------------------------------------------------------------

@pytest.mark.parametrize("size", ["Small", "Standard", "Large", "Extra Large"])
def test_on_derek_s_window_the_8_heads_are_4_and_4_beside_the_name(widget, size):
    page = widget
    _size(page, size)
    _feed(page)
    got = _layout(page)
    assert got[INDX] == {"rows": "4+4", "place": "beside", "out": 0, "data": "4+4"}, (size, got)
    assert got[XL] == {"rows": "5", "place": "beside", "out": 0, "data": "5"}, (size, got)


@pytest.mark.parametrize("width, size, indx, xl", [
    (1366, "Extra Large", ("4+4", "beside"), ("3+2", "beside")),
    (1024, "Standard", ("4+4", "beside"), ("3+2", "beside")),
    (1024, "Extra Large", ("3+3+2", "beside"), ("3+2", "beside")),
    (800, "Standard", ("3+3+2", "beside"), ("3+2", "beside")),
    (800, "Extra Large", ("3+3+2", "below"), ("3+2", "below")),
    (412, "Standard", ("2+2+2+2", "below"), ("2+2+1", "below")),
    (412, "Extra Large", ("1+1+1+1+1+1+1+1", "below"), ("1+1+1+1+1", "below")),
])
def test_narrower_windows_split_by_the_rule(widget, width, size, indx, xl):
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _size(page, size)
    _feed(page)
    got = _layout(page)
    # As drawn, and as the layout recorded it (data-rows: where the tiles go
    # under the name anyway, plain wrapping can draw the same lines).
    assert (got[INDX]["rows"], got[INDX]["place"], got[INDX]["data"]) == indx + (indx[0],), (width, size, got)
    assert (got[XL]["rows"], got[XL]["place"], got[XL]["data"]) == xl + (xl[0],), (width, size, got)
    assert got[INDX]["out"] == 0 and got[XL]["out"] == 0, f"tiles sticking out of their row: {got}"


def test_it_lays_out_again_after_a_text_size_change_and_a_resize(widget):
    page = widget
    page.set_viewport_size({"width": 1024, "height": 900})
    _feed(page)
    assert _layout(page)[INDX]["rows"] == "4+4"
    _size(page, "Extra Large")              # the tiles grow: 3 fit beside the name
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("3+3+2", "3+2")
    page.set_viewport_size({"width": 1600, "height": 1300})
    _settled(page, {INDX: "4+4", XL: "5"})
    page.set_viewport_size({"width": 800, "height": 900})
    _settled(page, {INDX: "3+3+2", XL: "3+2"})
    assert _layout(page)[INDX]["place"] == "below"
    _size(page, "Standard")
    got = _layout(page)
    assert (got[INDX]["rows"], got[INDX]["place"]) == ("3+3+2", "beside"), got


def test_a_repaint_a_reorder_and_collapsing_keep_the_rows_even(widget):
    page = widget
    _feed(page)
    # A heartbeat with a change (a spool loaded on the INDX): a new paint.
    changed = {INDX: _printer("ZE", 8, loaded=(0, 3, 5)), XL: FLEET[XL]}
    _feed(page, changed)
    assert _layout(page)[INDX]["rows"] == "4+4"
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == INDX
    page.evaluate("(n) => window.movePrinterStatusRow(n, 1)", INDX)
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == XL
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "5")
    # Collapsed, the window and the size change; opened again, it measures again.
    page.evaluate("() => window.togglePrinterStatusWidget()")
    assert page.evaluate("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    page.set_viewport_size({"width": 1024, "height": 900})
    _size(page, "Extra Large")
    page.evaluate("() => window.togglePrinterStatusWidget()")
    _settled(page, {INDX: "3+3+2", XL: "3+2"})


@pytest.mark.parametrize("size", ["Small", "Standard", "Large", "Extra Large"])
def test_the_material_line_is_1_2_high(widget, size):
    page = widget
    _size(page, size)
    _feed(page)
    lines = page.evaluate("""() => Array.from(document.querySelectorAll('.fcc-ps-chip-mat')).map((el) => {
        const cs = getComputedStyle(el);
        return { text: el.textContent.trim(), ratio: parseFloat(cs.lineHeight) / parseFloat(cs.fontSize),
                 h: el.clientHeight, lh: parseFloat(cs.lineHeight) }; })""")
    assert {ln["text"] for ln in lines} >= {"PETG", "Polycarbonate"}, lines
    for ln in lines:
        assert ln["ratio"] == pytest.approx(1.2, abs=0.01), (size, ln)
        assert ln["h"] >= ln["lh"] - 1, (size, ln)
