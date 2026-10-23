"""Printer Status: each printer's name on a header line, its tiles under the
name in even rows (Derek, 2026-10-22 and 2026-10-23).

2026-10-22: when a printer's heads don't fit on one line, split them into the
fewest rows with EQUAL counts (8 -> 4 + 4, 7 -> 4 + 3, 10 -> 5 + 5; never a
lone tile). The tiles then sat beside a 12.5rem name column (style "S1").
2026-10-23, after seeing S1, a narrower column (S2) and the name above the
tiles (S3): "name on top of tool heads, probably reads better, especially if
we indent in the toolheads more so that they read as a sub thing of the
printer name. We also avoid the word wrap effect on the red notification dot
about pending reviews ... Also, this way, if printer names go ungodly long for
some reason, they don't clash or break the toolhead display." So each printer
is now a header line (the ▲▼ arrows, the name, its state badge, the 🛑 N
review count) with the tiles under it, starting under the name's first letter,
in even rows across the row's width minus that step.

Hermetic, and it RUNS under --offline: `isolated_page` (a chromium with no
route to any network) with the real static/css/global.css, text_size.js,
ui_builder.js, inv_core.js, inv_printer_status.js and cancel_review.js, and a
few lines standing in for the Bootstrap classes the widget uses (Bootstrap
comes from a CDN). The widget is fed made-up fleets through
refreshPrinterStatusWidgetFromAggregate, as the heartbeat feeds it, and the
review count comes from cancel_review.js's own poll, answered in the page.
Pinned:
  - the rule (window.fccPrinterStatusTileRows(n, fit)): the fewest rows for
    what fits on a line, counts as equal as they can be, the longer first, a
    row of one tile only where at most two fit on a line;
  - the header is ONE line: the arrows, the name, the badge and the review
    count share a centre line, the count's 🛑 and its number never part, the
    badge follows the name and the count follows the badge, all inside the
    row, at 412 and 1600 px at Standard and Extra Large (and the count is put
    back after a repaint and a reorder);
  - every tile sits under the header, every line of tiles starts under the
    name's first letter, a step in from the arrows (the arrows' width and the
    grid's gap: 1.625rem), and nothing sticks out of the row;
  - even rows at every Text size at 412, 1024, 1366 and 1600 px: the INDX's 8
    heads are one row on Derek's 1600 px window at Small and Standard and
    4 + 4 at Large and Extra Large; the rows are the fewest that fit and are
    drawn as the layout recorded them (data-rows);
  - a 60-character printer name keeps the header on one line (it ends in "…"
    where the line is short, its full text in its title), and the tiles sit
    exactly where they sit under a short name;
  - 7, 10 and 13 heads where three fit on a line are 3 + 2 + 2, 3 + 3 + 2 + 2
    and 3 + 3 + 3 + 2 + 2, each line starting under the name (a plain grid
    fill is 3 + 3 + 1);
  - what the browser drew is checked: with a margin the sums don't count, a
    line of tiles wider than its area is laid out again with one tile fewer;
  - at a 110 % display scale (a real device scale factor: the tile area is
    695.65 or 1223.84 px, which clientWidth calls 696 or 1224, exactly what 4
    or 7 tiles need), the tiles counted are the ones that fit;
  - it lays out again after a Text size change and a resize, after a repaint
    and the ▲▼ reorder (by mouse and by keyboard), and after the widget is
    collapsed and opened again;
  - the material line's line height is 1.2 at every size.
The same on the real page (Bootstrap, the heartbeat, dev's container) is
test_printer_status_even_rows_e2e.py.

RED on 234f41a (this file alone in a throwaway worktree at 234f41a): 54 of
59. There the 🛑 N count sat inside the name (and the badge under it), the
tiles beside a 12.5rem name column (or, on a phone, under it from the row's
left edge, not under the name), a 60-character name wrapped down the column
and pushed the tiles 57.6 px lower at 412 px, the name had no title, the rule
answered `below` (the beside / under mode), and the 110 % windows found here
land elsewhere in the old layout. The 5 that hold there: the rule's sizes for
every count and room (unchanged since 2026-10-22) and the 1.2 material line
at the four sizes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"

# The Bootstrap rules the widget's markup leans on, so the layout here is the
# page's (box-sizing, and the utility classes on the arrows and the chip).
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

# fetch answers cancel_review.js's poll from window.__pending (the reviews the
# 🛑 count shows) and leaves every other request pending forever.
PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.__pending = [];
window.fetch = (url) => (String(url).indexOf('/api/cancel_deduct/pending') !== -1
    ? Promise.resolve({ ok: true, json: () => Promise.resolve({ pending: window.__pending }) })
    : new Promise(() => {}));
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
SIZES = ("Small", "Standard", "Large", "Extra Large")
ROOT_PX = {"Small": 16, "Standard": 16, "Large": 18, "Extra Large": 20}
# 60 characters: longer than any header line on a phone, shorter than one on 1600 px.
LONG_NAME = "ZZ A Printer Whose Name Goes On And On Past Any Sensible End"
assert len(LONG_NAME) == 60


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

# Per printer: the count on each line of tiles, what the layout recorded
# (data-rows), whether every tile is under the header line, whether every line
# of tiles starts under the name's first letter, the name's step in from the
# row's left edge, how many tiles stick out (past the row's right edge, or left
# of the name), and how many tiles fit on a line by measure, with no slack:
# the fewest rows are ceil(n / fits).
LAYOUT_JS = r"""() => {
    const out = {};
    document.querySelectorAll('#printer-status-widget .fcc-ps-row').forEach((row) => {
        const rs = getComputedStyle(row);
        const rowR = row.getBoundingClientRect();
        const left = rowR.left + parseFloat(rs.paddingLeft) + parseFloat(rs.borderLeftWidth);
        const right = rowR.right - parseFloat(rs.paddingRight) - parseFloat(rs.borderRightWidth);
        const name = row.querySelector('.fcc-ps-name').getBoundingClientRect();
        const header = Array.from(row.querySelectorAll('.fcc-ps-reorder, .fcc-ps-name, .fcc-ps-state, .fcc-cr-chip'))
            .map((el) => el.getBoundingClientRect()).filter((r) => r.height > 0);
        const headerBottom = Math.max(...header.map((r) => r.bottom));
        const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
        const lines = [];
        tiles.forEach((r) => {
            const line = lines.find((l) => Math.abs(l.top - r.top) < 2);
            if (line) { line.n++; line.left = Math.min(line.left, r.left); } else lines.push({ top: r.top, n: 1, left: r.left });
        });
        lines.sort((a, b) => a.top - b.top);
        const heads = row.querySelector('.fcc-ps-toolheads');
        const gap = parseFloat(getComputedStyle(heads).columnGap);
        const tileW = tiles.length ? tiles[0].width : 0;
        out[row.dataset.printer] = {
            rows: lines.map((l) => l.n).join('+'), data: heads.dataset.rows || null,
            below: tiles.every((r) => r.top >= headerBottom - 0.5),
            under: lines.every((l) => Math.abs(l.left - name.left) < 0.5),
            indent: Math.round((name.left - left) * 100) / 100,
            out: tiles.filter((r) => r.right > right + 0.5 || r.left < name.left - 0.5).length,
            fits: tileW ? Math.floor((right - name.left + gap) / (tileW + gap)) : 0,
        };
    });
    return out;
}"""

# Per printer, the header line: the centre line of each of its parts (the
# arrows' pair, the name, the badge, the review count), their left and right
# edges, how many lines the name's and the count's text take (a Range's
# boxes), the count's text, the row's content edges, and the name's title and
# whether it is cut short with "…".
HEADER_JS = r"""() => {
    const out = {};
    const lineTops = (el) => {
        const range = document.createRange(); range.selectNodeContents(el);
        const tops = [];
        Array.from(range.getClientRects()).filter((r) => r.width > 0).forEach((r) => {
            if (!tops.some((t) => Math.abs(t - r.top) < 3)) tops.push(r.top); });
        return tops.length;
    };
    const box = (el) => { if (!el) return null; const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, mid: (r.top + r.bottom) / 2 }; };
    document.querySelectorAll('#printer-status-widget .fcc-ps-row').forEach((row) => {
        const rs = getComputedStyle(row);
        const rowR = row.getBoundingClientRect();
        const name = row.querySelector('.fcc-ps-name');
        const chip = row.querySelector('.fcc-cr-chip');
        const arrows = Array.from(row.querySelectorAll('.fcc-ps-reorder')).map(box);
        out[row.dataset.printer] = {
            arrows: arrows.length ? { left: Math.min(...arrows.map((a) => a.left)), right: Math.max(...arrows.map((a) => a.right)),
                                      mid: (Math.min(...arrows.map((a) => a.top)) + Math.max(...arrows.map((a) => a.bottom))) / 2 } : null,
            name: box(name), badge: box(row.querySelector('.fcc-ps-state')), chip: box(chip),
            chipInHead: !!chip && !!chip.closest('.fcc-ps-head') && !name.contains(chip),
            chipText: chip ? chip.textContent : null,
            nameLines: lineTops(name), chipLines: chip ? lineTops(chip) : 0,
            rowLeft: rowR.left + parseFloat(rs.paddingLeft), rowRight: rowR.right - parseFloat(rs.paddingRight),
            title: name.getAttribute('title'), text: name.textContent,
            cut: name.scrollWidth > name.clientWidth + 0.5 && getComputedStyle(name).textOverflow === 'ellipsis',
        };
    });
    return out;
}"""


def _drawn_as_recorded(got):
    """Every printer's tiles as the layout recorded them (review, 2026-10-22):
    the lines drawn are data-rows. A layout whose CSS drew something else
    (rows not started in column 1, so 3 + 3 + 1 for a planned 3 + 2 + 2)
    passed every check that only compared fixed strings."""
    wrong = {k: v for k, v in got.items() if v["rows"] != v["data"]}
    assert not wrong, f"drawn differently from what the layout recorded: {wrong}"
    return got


def _build(page):
    """The widget's page: the real CSS and modules, a Bootstrap stand-in."""
    page.set_content(PAGE.format(standin=BOOTSTRAP_STANDIN, css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("inv_core.js", "ui_builder.js", "inv_printer_status.js", "text_size.js", "cancel_review.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))


@pytest.fixture
def widget(isolated_page):
    page = isolated_page
    _build(page)
    yield page
    assert page.evaluate("window.__errors") == []


def _feed(page, fleet=None):
    page.evaluate("(rows) => window.refreshPrinterStatusWidgetFromAggregate(rows)", fleet or FLEET)


def _size(page, name):
    """The Text size as Settings applies it (text_size.js: the attribute on
    <html> and the fcc:text-size event)."""
    page.evaluate("(n) => window.fccTextSize.apply(n)", name)


def _reviews(page, counts):
    """`counts` pending reviews per printer ({name: n}), as cancel_review.js's
    poll reads them; waits for the 🛑 N counts on the open widget."""
    pending = [{"printer_name": name, "job_id": f"{name}#{i}"} for name, n in counts.items() for i in range(n)]
    page.evaluate("(p) => { window.__pending = p; return window.refreshCancelReviewBadge(); }", pending)
    page.wait_for_function("(n) => document.querySelectorAll('#printer-status-widget .fcc-ps-body .fcc-cr-chip').length === n",
                           arg=sum(1 for n in counts.values() if n), timeout=3000)


def _layout(page):
    return _drawn_as_recorded(page.evaluate(LAYOUT_JS))


def _settled(page, want):
    """Wait until the layout reads `want` ({printer: rows}) — a resize lays the
    rows out on the next animation frame."""
    page.wait_for_function("""([js, want]) => { const got = (eval(js))();
        return Object.entries(want).every(([k, v]) => got[k] && got[k].rows === v); }""",
                           arg=[LAYOUT_JS, want], timeout=5000)


def _one_header_line(h, name, size):
    """The header line of one printer, as Derek chose it (2026-10-23)."""
    where = (name, size, h)
    # The name on one line; the badge after it, the 🛑 N count after the badge,
    # in the header (never inside the name, which ends in "…"), every part on
    # one centre line, inside the row.
    assert h["nameLines"] == 1, where
    assert h["badge"] and h["name"]["right"] <= h["badge"]["left"] + 0.5, where
    assert abs(h["badge"]["mid"] - h["name"]["mid"]) <= 1.5, where
    if h["arrows"]:
        assert h["arrows"]["right"] <= h["name"]["left"] - 0.5, where
        assert abs(h["arrows"]["mid"] - h["name"]["mid"]) <= 1.5, where
    if h["chip"]:
        assert h["chipInHead"], where
        assert h["chipLines"] == 1, f"the 🛑 and its count split across lines: {where}"
        assert h["badge"]["right"] <= h["chip"]["left"] + 0.5, where
        assert abs(h["chip"]["mid"] - h["name"]["mid"]) <= 1.5, where
        assert h["chip"]["right"] <= h["rowRight"] + 0.5, where
    assert h["badge"]["right"] <= h["rowRight"] + 0.5, where
    # Its full name is its title, whether or not it is cut short.
    assert h["title"] == name, where


# --- the rule ------------------------------------------------------------------

@pytest.mark.parametrize("n, fit, sizes", [
    (8, 8, [8]),                 # the INDX on Derek's 1600 px window at Standard: one row
    (8, 7, [4, 4]),              # ... at Large: 7 fit
    (8, 6, [4, 4]),              # ... at Extra Large: 6 fit
    (8, 5, [4, 4]),
    (8, 3, [3, 3, 2]),
    (8, 2, [2, 2, 2, 2]),        # a phone at Standard
    (8, 1, [1] * 8),             # a phone at Large / Extra Large
    (7, 5, [4, 3]),
    (7, 3, [3, 2, 2]),           # never 3 + 3 + 1
    (10, 8, [5, 5]),
    (10, 3, [3, 3, 2, 2]),
    (13, 4, [4, 3, 3, 3]),
    (5, 8, [5]),                 # the XL: one row
    (5, 4, [3, 2]),
    (5, 2, [2, 2, 1]),           # a phone: the one lone tile left
    (4, 3, [2, 2]),
    (1, 1, [1]),
    (3, 0, [1, 1, 1]),           # none fit by measure: one a line
    (0, 5, []),
])
def test_the_rule(widget, n, fit, sizes):
    got = widget.evaluate("([n, f]) => window.fccPrinterStatusTileRows(n, f)", [n, fit])
    assert got["sizes"] == sizes, got
    assert got["rows"] == len(sizes) and got["cols"] == (sizes[0] if sizes else 0), got
    assert "below" not in got, f"the beside / under-the-name mode is gone: {got}"


def test_the_rule_is_the_fewest_even_rows_for_every_count_and_room(widget):
    """Every count up to 16 heads, room for 1 to 14 on a line: the rows add up,
    are as few as fit, differ by at most one with the longer first, and hold a
    lone tile only where at most two fit on a line."""
    bad = widget.evaluate("""() => {
        const bad = [];
        for (let n = 1; n <= 16; n++) for (let fit = 1; fit <= 14; fit++) {
            const r = window.fccPrinterStatusTileRows(n, fit);
            const ok = r.sizes.reduce((a, b) => a + b, 0) === n && r.rows === Math.ceil(n / fit)
                && r.sizes[0] <= fit && r.cols === r.sizes[0]
                && r.sizes.every((s, i) => i === 0 || (s <= r.sizes[i - 1] && r.sizes[0] - s <= 1))
                && !(fit >= 3 && r.rows > 1 && r.sizes.includes(1));
            if (!ok) bad.push([n, fit, r]);
        }
        return bad.slice(0, 10); }""")
    assert bad == [], bad


# --- the layout ------------------------------------------------------------------

# (width, size) -> (the INDX's 8 heads, the XL's 5): one row where all fit
# (the INDX on Derek's 1600 px window at Small and Standard), else the fewest
# even rows; two to a line on a 412 px phone at Small and Standard, one at
# Large and Extra Large.
WIDTHS = {
    (412, "Small"): ("2+2+2+2", "2+2+1"), (412, "Standard"): ("2+2+2+2", "2+2+1"),
    (412, "Large"): ("1+1+1+1+1+1+1+1", "1+1+1+1+1"), (412, "Extra Large"): ("1+1+1+1+1+1+1+1", "1+1+1+1+1"),
    (1024, "Small"): ("4+4", "5"), (1024, "Standard"): ("4+4", "5"),
    (1024, "Large"): ("4+4", "3+2"), (1024, "Extra Large"): ("4+4", "3+2"),
    (1366, "Small"): ("4+4", "5"), (1366, "Standard"): ("4+4", "5"),
    (1366, "Large"): ("4+4", "5"), (1366, "Extra Large"): ("4+4", "5"),
    (1600, "Small"): ("8", "5"), (1600, "Standard"): ("8", "5"),
    (1600, "Large"): ("4+4", "5"), (1600, "Extra Large"): ("4+4", "5"),
}


@pytest.mark.parametrize("width, size", list(WIDTHS))
def test_even_rows_under_the_name_at_each_size_and_width(widget, width, size):
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    _feed(page)
    got = _layout(page)
    indx, xl = WIDTHS[(width, size)]
    assert (got[INDX]["rows"], got[XL]["rows"]) == (indx, xl), (width, size, got)
    for name, n in ((INDX, 8), (XL, 5)):
        g = got[name]
        # Under the header line, each line starting under the name's first
        # letter, a step in from the arrows (their 1.125rem and the 0.5rem gap).
        assert g["below"] and g["under"], (width, size, name, g)
        assert g["indent"] == pytest.approx(1.625 * ROOT_PX[size], abs=0.05), (width, size, name, g)
        # Nothing sticks out, and the rows are the fewest that fit.
        assert g["out"] == 0, (width, size, name, g)
        assert len(g["rows"].split("+")) == -(-n // max(1, g["fits"])), (width, size, name, g)


@pytest.mark.parametrize("width, size", [(412, "Standard"), (412, "Extra Large"), (1600, "Standard"),
                                         (1600, "Extra Large"), (1024, "Large")])
def test_the_header_is_one_line_with_the_dot_and_its_count_together(widget, width, size):
    """The ▲▼ arrows, the name, the state badge and the 🛑 N count on one
    line, the count after the badge, its dot and number never parted (Derek:
    "avoid the word wrap effect on the red notification dot"). 12 reviews for
    the INDX at its widest (PRINTING) on a phone at Extra Large is the
    tightest line: the name gives way, never the count."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    fleet = {INDX: _printer("ZE", 8, "PRINTING", loaded=(0, 3)), XL: _printer("ZX", 5, loaded=(1, 2))}
    _feed(page, fleet)
    _reviews(page, {INDX: 12, XL: 1})
    head = page.evaluate(HEADER_JS)
    for name in (INDX, XL):
        _one_header_line(head[name], name, size)
    assert (head[INDX]["chipText"], head[XL]["chipText"]) == ("🛑 12", "🛑 1"), head
    # The first printer has only ▼ and the last only ▲: each on the name's line.
    assert head[INDX]["arrows"] and head[XL]["arrows"], head
    got = _layout(page)
    assert all(v["below"] and v["under"] and v["out"] == 0 for v in got.values()), got


def test_the_count_comes_back_on_the_header_after_a_repaint_and_a_reorder(widget):
    page = widget
    _feed(page)
    _reviews(page, {INDX: 3})
    # A heartbeat that changes a tile repaints the rows; the widget puts the
    # count back (window.cancelReviewDecorate) on the header line.
    _feed(page, {INDX: _printer("ZE", 8, loaded=(0, 3, 5)), XL: FLEET[XL]})
    head = page.evaluate(HEADER_JS)
    _one_header_line(head[INDX], INDX, "Standard")
    assert head[INDX]["chipText"] == "🛑 3" and head[XL]["chip"] is None, head
    page.evaluate("(n) => window.movePrinterStatusRow(n, 1)", INDX)
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == XL
    head = page.evaluate(HEADER_JS)
    _one_header_line(head[INDX], INDX, "Standard")
    assert head[INDX]["chipText"] == "🛑 3", head


@pytest.mark.parametrize("width, size", [(412, "Standard"), (412, "Extra Large"), (1024, "Standard"),
                                         (1600, "Standard"), (1600, "Extra Large")])
def test_a_60_character_name_neither_overlaps_nor_shifts_the_tiles(widget, width, size):
    """Derek: "if printer names go ungodly long for some reason, they don't
    clash or break the toolhead display". The header stays one line (the name
    ends in "…" where the line is too short for it, its full text in its
    title; the badge and the count stay on the line), and every tile sits
    exactly where it sits under a short name."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    tiles_js = """() => { const row = document.querySelector('#printer-status-widget .fcc-ps-row');
        const r0 = row.getBoundingClientRect();
        return Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => { const r = t.getBoundingClientRect();
            return [Math.round((r.left - r0.left) * 100) / 100, Math.round((r.top - r0.top) * 100) / 100,
                    Math.round(r.width * 100) / 100]; }); }"""
    short = {INDX: _printer("ZE", 8, "PRINTING", loaded=(0, 3)), XL: FLEET[XL]}
    _feed(page, short)
    _reviews(page, {INDX: 12})
    before = page.evaluate(tiles_js)
    # The same 8 heads under the long name (it sorts first, as the INDX did).
    long_fleet = {LONG_NAME: short[INDX], XL: FLEET[XL]}
    _feed(page, long_fleet)
    _reviews(page, {LONG_NAME: 12})
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == LONG_NAME
    after = page.evaluate(tiles_js)
    assert after == before, f"the long name moved the tiles: {before} -> {after}"
    head = page.evaluate(HEADER_JS)[LONG_NAME]
    _one_header_line(head, LONG_NAME, size)
    assert head["text"] == LONG_NAME and head["chipText"] == "🛑 12", head
    assert head["name"]["right"] <= head["badge"]["left"] + 0.5, head
    # Where the line is short the name is cut, never the badge or the count.
    if width == 412:
        assert head["cut"], f"the name should end in … on a phone: {head}"
    got = _layout(page)
    assert got[LONG_NAME]["below"] and got[LONG_NAME]["under"] and got[LONG_NAME]["out"] == 0, got


# Counts where a plain grid fill is uneven: where three tiles fit on a line it
# draws 3 + 3 + 1 and 3 + 3 + 3 + 1. Only each row's first tile starting in
# column 1 draws what the rule says (review, 2026-10-22: the 8, 5, 3 and 2
# heads every other check uses come out the same either way).
UNEVEN = {"ZZ Seven": _printer("ZS", 7, loaded=(0,)), "ZZ Ten": _printer("ZT", 10, loaded=(1,)),
          "ZZ Thirteen": _printer("ZH", 13)}


@pytest.mark.parametrize("width, size", [(700, "Standard"), (800, "Extra Large")])
def test_each_row_of_tiles_starts_under_the_name(widget, width, size):
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _size(page, size)
    _feed(page, UNEVEN)
    got = _layout(page)
    assert {k: (v["rows"], v["under"], v["out"]) for k, v in got.items()} == {
        "ZZ Seven": ("3+2+2", True, 0), "ZZ Ten": ("3+3+2+2", True, 0),
        "ZZ Thirteen": ("3+3+3+2+2", True, 0)}, (width, size, got)


SEVEN = {"ZZ Seven": _printer("ZS", 7)}
FOUR = {"ZZ Four": _printer("ZF", 4)}


@pytest.mark.parametrize("style, width, fleet, plain, want", [
    # 1282 px: seven tiles fill the area under the name to the px (1224 px);
    # with a margin the sums don't count, the seventh doesn't fit.
    (".fcc-ps-th { margin-right: 2px; }", 1282, SEVEN, "7", "4+3"),
    # 412 px: two tiles fit on a line under the name (354 px), but not with a
    # 40 px margin each.
    (".fcc-ps-th { margin-right: 40px; }", 412, FOUR, "2+2", "1+1+1+1"),
])
def test_what_the_browser_drew_is_checked(widget, style, width, fleet, plain, want):
    """The sums can't know every style (or every rounding: the 110 % display
    scale below), so the layout checks what the browser drew: a line of tiles
    wider than its area is laid out again with one tile fewer per line."""
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _feed(page, fleet)
    (name,) = fleet
    assert _layout(page)[name]["rows"] == plain        # without the margin
    page.add_style_tag(content=style)
    page.evaluate("() => window.balancePrinterStatusRows()")
    got = _layout(page)[name]
    assert (got["rows"], got["out"]) == (want, 0), got


# --- a display scale of 110 % (Windows' display scaling, or a browser zoom) -----
# A CSS px is 1.1 device px, so the page's widths are fractions of a px: at a
# 753 px window the tile area is 695.65 px wide and clientWidth says 696,
# exactly what four tiles need (at 1281 px: 1223.84, and seven need 1224).
# Whole px count one tile more than fits (review, 2026-10-22).
TRAP_FLEET = {f"ZZ {n:02d} heads": _printer(f"Z{n}", n) for n in (4, 5, 7, 8, 10)}

# What whole px and the fraction count on a line, for the row of `n`.
TRAP_JS = r"""(n) => {
    const row = Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row'))
        .find((r) => r.querySelectorAll('.fcc-ps-th').length === n);
    const heads = row.querySelector('.fcc-ps-toolheads');
    const gap = parseFloat(getComputedStyle(heads).columnGap);
    const tileW = row.querySelector('.fcc-ps-th').getBoundingClientRect().width;
    const count = (w, slack) => Math.floor((w + gap + slack) / (tileW + gap));
    const rect = heads.getBoundingClientRect().width;
    return { clientWidth: heads.clientWidth, width: rect, whole: count(heads.clientWidth, 0.5), fraction: count(rect, 0) };
}"""


@pytest.fixture(scope="module")
def scaled_chromium(playwright):
    """A second private chromium at a 110 % display scale (a real device scale
    factor, not an emulated one: the window is in device px and the page's
    widths come out as fractions of a px). As cut off from every network as
    `isolated_page`'s (conftest: the dead proxy and the resolver rule), and
    every request is aborted, so it runs under --offline."""
    from conftest import ISOLATED_BROWSER_ARGS, ISOLATED_PROXY
    try:
        browser = playwright.chromium.launch(
            headless=True, proxy=ISOLATED_PROXY,
            args=[*ISOLATED_BROWSER_ARGS, "--force-device-scale-factor=1.1", "--window-size=1200,1300"])
    except Exception as exc:  # noqa: BLE001 - playwright raises its own Error type
        pytest.skip(f"chromium could not launch at a 110 % scale ({exc})")
    yield browser
    browser.close()


@pytest.mark.parametrize("window, trap, want", [
    (753, 4, {4: "2+2", 5: "3+2", 7: "3+2+2", 8: "3+3+2", 10: "3+3+2+2"}),
    (1281, 7, {4: "4", 5: "5", 7: "4+3", 8: "4+4", 10: "5+5"}),
])
def test_at_a_110_percent_display_scale_it_counts_what_really_fits(scaled_chromium, window, trap, want):
    context = scaled_chromium.new_context(no_viewport=True)
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    try:
        _build(page)
        cdp = context.new_cdp_session(page)
        wid = cdp.send("Browser.getWindowForTarget")["windowId"]
        cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"width": window, "height": 1300}})
        page.wait_for_function("(w) => Math.abs(innerWidth - w) <= 2", arg=window, timeout=5000)
        _feed(page, TRAP_FLEET)
        page.evaluate("() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)))")
        # The trap is set: whole px count one tile more on a line than fits.
        got_trap = page.evaluate(TRAP_JS, trap)
        assert got_trap["whole"] == got_trap["fraction"] + 1 and got_trap["width"] < got_trap["clientWidth"], (
            f"a {window} px window no longer lands where whole px count a tile too many; pick another: {got_trap}")
        got = _layout(page)
        assert {k: (v["rows"], v["under"], v["out"]) for k, v in got.items()} == \
            {f"ZZ {n:02d} heads": (rows, True, 0) for n, rows in want.items()}, (window, got)
        assert page.evaluate("window.__errors") == []
    finally:
        context.close()


def test_it_lays_out_again_after_a_text_size_change_and_a_resize(widget):
    page = widget
    page.set_viewport_size({"width": 1024, "height": 900})
    _feed(page)
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "5")
    _size(page, "Extra Large")              # the tiles grow: 4 fit on a line
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "3+2")
    page.set_viewport_size({"width": 1600, "height": 1300})
    _settled(page, {INDX: "4+4", XL: "5"})
    page.set_viewport_size({"width": 800, "height": 900})
    _settled(page, {INDX: "3+3+2", XL: "3+2"})
    _size(page, "Standard")
    got = _layout(page)
    assert (got[INDX]["rows"], got[XL]["rows"]) == ("4+4", "3+2"), got
    page.set_viewport_size({"width": 1600, "height": 1300})
    _settled(page, {INDX: "8", XL: "5"})
    assert all(v["below"] and v["under"] for v in _layout(page).values())


def test_a_repaint_a_reorder_and_collapsing_keep_the_rows_even(widget):
    page = widget
    _feed(page)
    # A heartbeat with a change (a spool loaded on the INDX): a new paint.
    changed = {INDX: _printer("ZE", 8, loaded=(0, 3, 5)), XL: FLEET[XL]}
    _feed(page, changed)
    assert _layout(page)[INDX]["rows"] == "8"
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == INDX
    page.evaluate("(n) => window.movePrinterStatusRow(n, 1)", INDX)
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == XL
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("8", "5")
    # By keyboard too: the first printer's ▼ (its only arrow), Enter.
    page.locator(".fcc-ps-row").first.locator("button.fcc-ps-reorder").focus()
    page.keyboard.press("Enter")
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == INDX
    # Collapsed, the window and the size change; opened again, it measures again.
    page.evaluate("() => window.togglePrinterStatusWidget()")
    assert page.evaluate("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    page.set_viewport_size({"width": 1024, "height": 900})
    _size(page, "Extra Large")
    page.evaluate("() => window.togglePrinterStatusWidget()")
    _settled(page, {INDX: "4+4", XL: "3+2"})
    assert all(v["below"] and v["under"] and v["out"] == 0 for v in _layout(page).values())


@pytest.mark.parametrize("size", SIZES)
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
