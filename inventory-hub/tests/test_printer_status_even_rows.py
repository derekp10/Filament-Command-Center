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
ui_builder.js, inv_core.js, inv_printer_status.js and cancel_review.js, a few
lines standing in for the Bootstrap classes the widget uses (Bootstrap comes
from a CDN), and a few standing in for the dashboard's scan accumulator
(templates/components/scripts.html, which cancels every Enter outside a text
field; a canary below holds it to that). The widget is fed made-up fleets
through refreshPrinterStatusWidgetFromAggregate, as the heartbeat feeds it,
and the review count comes from cancel_review.js's own poll, answered in the
page. Pinned:
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
  - even rows at every Text size at 390, 412, 1024, 1366 and 1600 px: the
    INDX's 8 heads are one row on Derek's 1600 px window at Small and
    Standard and 4 + 4 at Large and Extra Large; the rows are the fewest that
    fit and are drawn as the layout recorded them (data-rows);
  - a phone (review, 2026-10-23, F1): where the step in leaves room for one
    tile on a line and the row's whole width for two (376 to 401 px at
    Standard: an iPhone 12 to 16 is 390 or 393 px), the tiles start at the
    row's edge, two to a line (they were one: 8 lines for the INDX);
  - a printer between two others (both arrows) has the same header line as
    the others (review, 2026-10-23, F6: the pair made it 34 px tall, so its
    tiles sat 12.2 px under its name instead of 5.6): the arrows are centred
    on the name's line, clear of the divider above and of the tiles below;
  - a 60-character printer name keeps the header on one line (it ends in "…"
    where the line is short, its full text in its title), and the tiles sit
    exactly where they sit under a short name;
  - 7, 10 and 13 heads where three fit on a line are 3 + 2 + 2, 3 + 3 + 2 + 2
    and 3 + 3 + 3 + 2 + 2, each line starting under the name (a plain grid
    fill is 3 + 3 + 1);
  - what the browser drew is checked: with a margin the sums don't count, a
    line of tiles wider than its area is laid out again with one tile fewer
    (the measure's own count, data-fit, says the check did it);
  - at a 110 % display scale (a real device scale factor: the tile area is
    695.65 or 1223.84 px, which clientWidth calls 696 or 1224, exactly what 4
    or 7 tiles need), the MEASURE counts the tiles that fit (data-fit): the
    drawn check would put a whole-px count right afterwards, so the rows alone
    could not tell (review, 2026-10-23, F4);
  - Enter on a focused ▲ / ▼ moves the printer with the accumulator cancelling
    every Enter, as the dashboard does (review, 2026-10-23, F3: Enter did
    nothing there, only Space did), and the focus stays on the moved printer's
    arrow, so Enter again moves it on; a scan typed onto a focused arrow stays
    a scan;
  - on a 1280 x 800 laptop at Small, Standard and Large, and 1366 x 768 at
    Standard, dev's two printers (8 and 5 heads) show whole in the open widget
    (review, 2026-10-23, F2: 8 of 13 tiles showed);
  - the collapsed strip keeps every chip inside the window at 1024 px at every
    size, at 1280 px at Extra Large and on a phone, its 🛑 count last and in
    one piece (review, 2026-10-23, F5: the INDX's group ran off the right edge);
  - it lays out again after a Text size change and a resize, after a repaint
    and the ▲▼ reorder (by mouse and by keyboard), and after the widget is
    collapsed and opened again;
  - the material line's line height is 1.2 at every size.
The same on the real page (Bootstrap, the heartbeat, dev's container) is
test_printer_status_even_rows_e2e.py.

RED before the fixes. On b49b263 (the build the 2026-10-23 review looked at;
this file in a scratch copy of it, `git archive b49b263`): 34 of 95, for the
review's findings: F1, the phones from 376 to 401 px (390 at Small and
Standard, the 60-character name and the header at 390, the resize down to 390,
Large at 430) at one tile a line, 11; F2, the laptop windows, 4; F3, Enter
cancelled by the accumulator, 3; F4, no data-fit, 4; F5, the strip off the
screen, 7; F6, the middle printer's header line 34 px tall, 5. The other 61
hold there. F4's own proof is a mutation: this file against a copy of the
fixed inv_printer_status.js measuring the tile area in whole px
(heads.clientWidth) fails both 110 % cases, which b49b263's version of this
file passed (the drawn check put the rows right after it); with the drawn
check removed instead, the two cases of test_what_the_browser_drew_is_checked
fail and the 110 % ones hold. On 234f41a (the name in a 12.5rem column) the
2026-10-23 version of this file was 54 of 59 red; its two 110 % cases failed
there only at their own guard (the trap lands elsewhere in that layout), so
they proved nothing about the measuring.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"
SCRIPTS_HTML = HUB / "templates" / "components" / "scripts.html"

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

# The dashboard's scan accumulator (scripts.html), as far as a focused button
# sees it: a key outside a text field with no Ctrl / Alt / Meta goes into
# state.scanBuffer, and EVERY Enter is cancelled, a button's own press
# included; the characters before it are a scan (window.__scans here, where
# the page hands them to processScan). Added after the modules, as the
# dashboard's own listener is (its DOMContentLoaded handler).
ACCUMULATOR = r"""
window.__scans = [];
document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key === 'Enter') {
        e.preventDefault();
        if (state.scanBuffer.length > 0) window.__scans.push(state.scanBuffer);
        state.scanBuffer = '';
        state.scanStartTime = 0;
    } else if (e.key.length === 1) {
        if (state.scanBuffer.length === 0) state.scanStartTime = Date.now();
        state.scanBuffer += e.key;
    }
});
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
# (data-rows) and how many tiles its measure counted on a line (data-fit),
# whether the tiles start at the row's edge (a phone: .fcc-ps-edge), whether
# every tile is under the header line, whether every line of tiles starts
# under the name's first letter (`under`) or at the row's left edge
# (`atEdge`), the name's step in from the row's left edge, how many tiles
# stick out (past the row's right edge, or left of where the lines start),
# and how many tiles fit on a line by measure, with no slack, under the name
# (`fits`) and across the row (`fitsWhole`): the fewest rows are ceil(n / fits).
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
        const edge = row.classList.contains('fcc-ps-edge');
        const start = edge ? left : name.left;
        out[row.dataset.printer] = {
            rows: lines.map((l) => l.n).join('+'), data: heads.dataset.rows || null,
            fit: heads.dataset.fit ? Number(heads.dataset.fit) : null, edge,
            below: tiles.every((r) => r.top >= headerBottom - 0.5),
            under: lines.every((l) => Math.abs(l.left - name.left) < 0.5),
            atEdge: lines.every((l) => Math.abs(l.left - left) < 0.5),
            indent: Math.round((name.left - left) * 100) / 100,
            out: tiles.filter((r) => r.right > right + 0.5 || r.left < start - 0.5).length,
            fits: tileW ? Math.floor((right - name.left + gap) / (tileW + gap)) : 0,
            fitsWhole: tileW ? Math.floor((right - left + gap) / (tileW + gap)) : 0,
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
    """The widget's page: the real CSS and modules, a Bootstrap stand-in and
    the scan accumulator's stand-in."""
    page.set_content(PAGE.format(standin=BOOTSTRAP_STANDIN, css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("inv_core.js", "ui_builder.js", "inv_printer_status.js", "text_size.js", "cancel_review.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=ACCUMULATOR)


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


def _order(page):
    return [r.get_attribute("data-printer") for r in page.locator("#printer-status-widget .fcc-ps-row").all()]


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


def _placed(g, where):
    """Where a printer's tiles start: under the name's first letter, or, on a
    phone with room for two from the row's edge and one under the name, at
    the row's edge (review, 2026-10-23). Either way under the header line,
    nothing out of the row, and the fewest rows for what fits there."""
    want_edge = g["fits"] < 2 <= g["fitsWhole"]
    assert g["edge"] == want_edge, f"the tiles should start {'at the edge' if want_edge else 'under the name'}: {where} {g}"
    assert g["below"] and (g["atEdge"] if g["edge"] else g["under"]) and g["out"] == 0, (where, g)
    fits = g["fitsWhole"] if g["edge"] else g["fits"]
    n = sum(int(c) for c in g["rows"].split("+"))
    assert len(g["rows"].split("+")) == -(-n // max(1, fits)), (where, g)


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
# even rows; two to a line on a phone at Small and Standard (at 390 px from
# the row's edge, at 412 px under the name), one at Large and Extra Large.
WIDTHS = {
    (390, "Small"): ("2+2+2+2", "2+2+1"), (390, "Standard"): ("2+2+2+2", "2+2+1"),
    (390, "Large"): ("1+1+1+1+1+1+1+1", "1+1+1+1+1"), (390, "Extra Large"): ("1+1+1+1+1+1+1+1", "1+1+1+1+1"),
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
    for name in (INDX, XL):
        g = got[name]
        # Under the header line; each line starting under the name's first
        # letter, a step in from the arrows (their 1.125rem and the 0.5rem
        # gap), or, at 390 px at Small and Standard, at the row's edge; the
        # name keeps its step either way. Nothing sticks out, and the rows are
        # the fewest that fit.
        _placed(g, (width, size, name))
        assert g["edge"] == (width == 390 and size in ("Small", "Standard")), (width, size, name, g)
        assert g["indent"] == pytest.approx(1.625 * ROOT_PX[size], abs=0.05), (width, size, name, g)


# Phones (review, 2026-10-23): two tiles need 344 px at Standard (168 + 8 +
# 168). Under the name a row has the window minus 32 px (the widget's padding)
# minus 26 (the step in), so two fit there from 402 px; from the row's edge
# they fit from 376 px. 234f41a used the whole row on a phone (two to a line
# from 376 px); b49b263 only the part under the name, so a 390 or 393 px
# iPhone (12 to 16) dropped to one tile a line: 8 lines for the INDX.
PHONES = {
    360: ("1+1+1+1+1+1+1+1", "1+1+1+1+1", False),   # two don't fit even from the edge
    375: ("1+1+1+1+1+1+1+1", "1+1+1+1+1", False),   # an iPhone SE / 13 mini: 343 px, one short
    376: ("2+2+2+2", "2+2+1", True),
    384: ("2+2+2+2", "2+2+1", True),
    390: ("2+2+2+2", "2+2+1", True),                # an iPhone 12 to 14
    393: ("2+2+2+2", "2+2+1", True),                # an iPhone 14 Pro to 16
    401: ("2+2+2+2", "2+2+1", True),
    402: ("2+2+2+2", "2+2+1", False),               # two fit under the name
    412: ("2+2+2+2", "2+2+1", False),
    430: ("2+2+2+2", "2+2+1", False),
}


@pytest.mark.parametrize("width", list(PHONES))
def test_a_phone_too_narrow_for_two_under_the_name_starts_them_at_the_row_s_edge(widget, width):
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _feed(page)
    got = _layout(page)
    indx, xl, edge = PHONES[width]
    assert (got[INDX]["rows"], got[XL]["rows"], got[INDX]["edge"], got[XL]["edge"]) == (indx, xl, edge, edge), (
        width, got)
    for name in (INDX, XL):
        _placed(got[name], (width, name))
    # The header line keeps its step in either way: the name, after the arrow.
    head = page.evaluate(HEADER_JS)
    for name in (INDX, XL):
        _one_header_line(head[name], name, "Standard")


def test_at_the_edge_at_large_too(widget):
    """At Large a tile is 189 px: two need 387 px, which a 430 px phone has
    from the row's edge (394) but not under the name (365)."""
    page = widget
    page.set_viewport_size({"width": 430, "height": 900})
    _size(page, "Large")
    _feed(page)
    got = _layout(page)
    assert (got[INDX]["rows"], got[XL]["rows"], got[INDX]["edge"]) == ("2+2+2+2", "2+2+1", True), got
    for name in (INDX, XL):
        _placed(got[name], (430, "Large", name))
    # Back under the name, one a line, when the window is too narrow for two
    # either way; and at the edge again, two a line, when it grows back.
    page.set_viewport_size({"width": 412, "height": 900})
    _settled(page, {INDX: "1+1+1+1+1+1+1+1"})
    assert not _layout(page)[INDX]["edge"]
    page.set_viewport_size({"width": 430, "height": 900})
    _settled(page, {INDX: "2+2+2+2"})
    assert _layout(page)[INDX]["edge"]


@pytest.mark.parametrize("width, size", [(412, "Standard"), (412, "Extra Large"), (1600, "Standard"),
                                         (1600, "Extra Large"), (1024, "Large"), (390, "Standard")])
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
    for name, g in got.items():
        _placed(g, (width, size, name))


# A printer between two others shows both arrows (review, 2026-10-23, F6).
FIRST, MIDDLE, LAST = "ZZ A First", "ZZ B Middle", "ZZ C Last"
THREE = {FIRST: _printer("ZA", 8, loaded=(0,)), MIDDLE: _printer("ZB", 3, "PRINTING", loaded=(1,)),
         LAST: _printer("ZC", 5, loaded=(1,))}

# Per printer: the header line's height (.fcc-ps-head) and the name's, the gap
# from the name's line to its first tile, the arrows' boxes, the divider
# above the row (the bottom of its top border) and every tile's box.
ARROWS_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row')).map((row) => {
    const rr = row.getBoundingClientRect();
    const name = row.querySelector('.fcc-ps-name').getBoundingClientRect();
    const head = row.querySelector('.fcc-ps-head').getBoundingClientRect();
    const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
    const arrows = Array.from(row.querySelectorAll('.fcc-ps-reorder')).map((a) => a.getBoundingClientRect());
    const box = (r) => ({ left: r.left, right: r.right, top: r.top, bottom: r.bottom });
    return { printer: row.dataset.printer, n: arrows.length, headH: head.height, nameH: name.height,
             nameMid: (name.top + name.bottom) / 2, nameToTile: Math.min(...tiles.map((t) => t.top)) - name.bottom,
             divider: rr.top + parseFloat(getComputedStyle(row).borderTopWidth), arrows: arrows.map(box),
             tiles: tiles.map(box), edge: row.classList.contains('fcc-ps-edge') }; })"""


@pytest.mark.parametrize("width, size", [(1600, "Standard"), (1600, "Extra Large"), (1024, "Large"),
                                         (390, "Standard"), (430, "Large")])
def test_a_printer_between_two_others_has_the_same_header_line(widget, width, size):
    """Every printer's header line is the name's line, the middle one's too
    (it shows both arrows; their pair made its header 34 px tall at Standard,
    so its tiles sat 12.2 px under its name instead of 5.6). The arrows stay
    centred on the name's line, at least 2 px clear of the divider above and
    of every tile, on a phone whose tiles start at the row's edge too (390 px
    at Standard, 430 px at Large)."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    _feed(page, THREE)
    rows = page.evaluate(ARROWS_JS)
    assert [(r["printer"], r["n"]) for r in rows] == [(FIRST, 1), (MIDDLE, 2), (LAST, 1)], rows
    assert len({r["edge"] for r in rows}) == 1 and rows[0]["edge"] == (width in (390, 430)), rows
    gaps = [round(r["nameToTile"], 1) for r in rows]
    assert max(gaps) - min(gaps) <= 0.5, f"the tiles sit at different depths under their names: {gaps}"
    for r in rows:
        where = (width, size, r["printer"], r)
        assert r["headH"] == pytest.approx(r["nameH"], abs=0.5), f"the header line is taller than the name's: {where}"
        mid = (min(a["top"] for a in r["arrows"]) + max(a["bottom"] for a in r["arrows"])) / 2
        assert abs(mid - r["nameMid"]) <= 1.5, where
        if r["printer"] != FIRST:
            assert min(a["top"] for a in r["arrows"]) >= r["divider"] + 2, f"an arrow touches the divider: {where}"
        for a in r["arrows"]:
            for t in r["tiles"]:
                apart = (a["right"] <= t["left"] or t["right"] <= a["left"]
                         or a["bottom"] + 2 <= t["top"] or t["bottom"] + 2 <= a["top"])
                assert apart, f"an arrow touches a tile: {where}"
    # The middle printer moves both ways, by mouse.
    page.locator(".fcc-ps-row").nth(1).locator("button.fcc-ps-reorder[data-dir='-1']").click()
    assert _order(page) == [MIDDLE, FIRST, LAST]
    page.locator(".fcc-ps-row").nth(0).locator("button.fcc-ps-reorder[data-dir='1']").click()
    page.locator(".fcc-ps-row").nth(1).locator("button.fcc-ps-reorder[data-dir='1']").click()
    assert _order(page) == [FIRST, LAST, MIDDLE]


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
                                         (1600, "Standard"), (1600, "Extra Large"), (390, "Standard")])
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
    if width in (390, 412):
        assert head["cut"], f"the name should end in … on a phone: {head}"
    _placed(_layout(page)[LONG_NAME], (width, size, LONG_NAME))


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


@pytest.mark.parametrize("style, width, fleet, plain, counted, want", [
    # 1282 px: seven tiles fill the area under the name to the px (1224 px);
    # with a margin the sums don't count, the seventh doesn't fit.
    (".fcc-ps-th { margin-right: 2px; }", 1282, SEVEN, "7", 7, "4+3"),
    # 412 px: two tiles fit on a line under the name (354 px), but not with a
    # 40 px margin each.
    (".fcc-ps-th { margin-right: 40px; }", 412, FOUR, "2+2", 2, "1+1+1+1"),
])
def test_what_the_browser_drew_is_checked(widget, style, width, fleet, plain, counted, want):
    """The sums can't know every style (or every rounding: the 110 % display
    scale below), so the layout checks what the browser drew: a line of tiles
    wider than its area is laid out again with one tile fewer per line. The
    measure's own count stays what it counted (data-fit), so it is the check
    that put the rows right here."""
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _feed(page, fleet)
    (name,) = fleet
    assert _layout(page)[name]["rows"] == plain        # without the margin
    page.add_style_tag(content=style)
    page.evaluate("() => window.balancePrinterStatusRows()")
    got = _layout(page)[name]
    assert (got["rows"], got["out"], got["fit"], got["under"], got["below"]) == (want, 0, counted, True, True), got


# --- a display scale of 110 % (Windows' display scaling, or a browser zoom) -----
# A CSS px is 1.1 device px, so the page's widths are fractions of a px: at a
# 753 px window the tile area is 695.65 px wide and clientWidth says 696,
# exactly what four tiles need (at 1281 px: 1223.84, and seven need 1224).
# Whole px count one tile more than fits (review, 2026-10-22). The drawn check
# would put such a count right afterwards (one relayout), so the rows alone
# can't tell a measure that counted right from one that didn't: data-fit, the
# measure's own count, can (review, 2026-10-23, F4).
TRAP_FLEET = {f"ZZ {n:02d} heads": _printer(f"Z{n}", n) for n in (4, 5, 7, 8, 10)}

# What whole px and the fraction count on a line, for the row of `n`, and
# what the layout's measure counted (data-fit).
TRAP_JS = r"""(n) => {
    const row = Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row'))
        .find((r) => r.querySelectorAll('.fcc-ps-th').length === n);
    const heads = row.querySelector('.fcc-ps-toolheads');
    const gap = parseFloat(getComputedStyle(heads).columnGap);
    const tileW = row.querySelector('.fcc-ps-th').getBoundingClientRect().width;
    const count = (w, slack) => Math.floor((w + gap + slack) / (tileW + gap));
    const rect = heads.getBoundingClientRect().width;
    return { clientWidth: heads.clientWidth, width: rect, whole: count(heads.clientWidth, 0.5), fraction: count(rect, 0),
             measured: Number(heads.dataset.fit) };
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
        # The measure counted the tiles that fit, not the whole px' one more.
        assert got_trap["measured"] == got_trap["fraction"], (
            f"the measure counted {got_trap['measured']} on a line, {got_trap['fraction']} fit: {got_trap}")
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
    # Down to a 390 px phone: two a line from the row's edge; Large there is
    # one a line, under the name again.
    page.set_viewport_size({"width": 390, "height": 900})
    _settled(page, {INDX: "2+2+2+2", XL: "2+2+1"})
    assert all(v["edge"] and v["atEdge"] for v in _layout(page).values())
    _size(page, "Large")
    got = _layout(page)
    assert (got[INDX]["rows"], got[INDX]["edge"], got[INDX]["under"]) == ("1+1+1+1+1+1+1+1", False, True), got


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
    # By keyboard too: the first printer's ▼ (its only arrow), Enter, with the
    # accumulator in the page cancelling every Enter, as the dashboard's does.
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


# --- the arrows by keyboard (review, 2026-10-23, F3) -----------------------------

FOCUS_JS = r"""() => { const a = document.activeElement; const row = a && a.closest ? a.closest('.fcc-ps-row') : null;
    return { tag: a ? a.tagName : null, dir: a && a.getAttribute ? a.getAttribute('data-dir') : null,
             printer: row ? row.dataset.printer : null }; }"""


def test_the_dashboard_s_accumulator_cancels_every_enter_outside_a_text_field():
    """The stand-in above is the dashboard's: its key handler skips text
    fields and modifier combos, then cancels every Enter (a scan ends in
    Enter), which is why the arrows answer Enter themselves. If the
    accumulator ever leaves a button's Enter alone, this fails: change the
    stand-in with it."""
    src = SCRIPTS_HTML.read_text(encoding="utf-8")
    handler = src[src.index("document.addEventListener('keydown', (e) => {"):]
    assert re.search(r"if \(e\.target\.tagName === 'INPUT' \|\| e\.target\.tagName === 'TEXTAREA'\) return;", handler)
    assert re.search(r"if \(e\.ctrlKey \|\| e\.altKey \|\| e\.metaKey\) return;", handler)
    assert re.search(r"if \(e\.key === 'Enter'\) \{\s*e\.preventDefault\(\);", handler)


def test_enter_on_a_focused_arrow_moves_its_printer_and_keeps_the_focus(widget):
    """Enter on a focused ▲ / ▼ moves the printer, as a click does, with the
    accumulator cancelling every Enter (it did nothing on the dashboard: only
    Space moved a printer). The rows are drawn again, and the focus stays on
    the moved printer's arrow: its other one when it no longer has the same
    (the INDX moved to the bottom has only ▲), so Enter again moves it back."""
    page = widget
    _feed(page, THREE)
    first = page.locator(".fcc-ps-row").first.locator("button.fcc-ps-reorder")
    first.focus()
    page.keyboard.press("Enter")
    assert _order(page) == [MIDDLE, FIRST, LAST]
    assert page.evaluate(FOCUS_JS) == {"tag": "BUTTON", "dir": "1", "printer": FIRST}
    page.keyboard.press("Enter")
    assert _order(page) == [MIDDLE, LAST, FIRST]
    assert page.evaluate(FOCUS_JS) == {"tag": "BUTTON", "dir": "-1", "printer": FIRST}
    page.keyboard.press("Enter")
    assert _order(page) == [MIDDLE, FIRST, LAST]
    assert page.evaluate(FOCUS_JS) == {"tag": "BUTTON", "dir": "-1", "printer": FIRST}
    # A heartbeat that repaints keeps the focus where it is.
    _feed(page, {**THREE, LAST: _printer("ZC", 5, loaded=(1, 3))})
    assert page.evaluate(FOCUS_JS) == {"tag": "BUTTON", "dir": "-1", "printer": FIRST}
    assert page.evaluate("window.__scans") == []


def test_a_scan_typed_onto_a_focused_arrow_stays_a_scan(widget):
    """A scanner types its label and Enter into whatever has the focus: on an
    arrow, the Enter ends the scan (window.enterIsAScan), never moves the
    printer, and the accumulator gets the label."""
    page = widget
    _feed(page, THREE)
    page.locator(".fcc-ps-row").first.locator("button.fcc-ps-reorder").focus()
    page.keyboard.type("LOC:ZZ-SCAN-1")
    page.keyboard.press("Enter")
    assert _order(page) == [FIRST, MIDDLE, LAST]
    assert page.evaluate("window.__scans") == ["LOC:ZZ-SCAN-1"]
    # A person's Enter afterwards is a press again.
    page.keyboard.press("Enter")
    assert _order(page) == [MIDDLE, FIRST, LAST]
    assert page.evaluate("window.__scans") == ["LOC:ZZ-SCAN-1"]


# --- the open widget on a short laptop window (review, 2026-10-23, F2) -----------

@pytest.mark.parametrize("width, height, size", [(1280, 800, "Small"), (1280, 800, "Standard"),
                                                 (1280, 800, "Large"), (1366, 768, "Standard")])
def test_on_a_short_laptop_window_every_tile_shows_without_scrolling(widget, width, height, size):
    """Each printer's name on its own line made the open widget taller, and
    at 1280 x 800 (a Framework 12 at 150 %) or 1366 x 768 the body's limit,
    then 40 % of the window, hid the second printer's tiles under its fold (8
    of 13 showed). Now there is no gap between printers (the rows' padding
    puts the divider half way) and the limit is 45 %: dev's two printers (8
    and 5 heads) show whole, and the body doesn't scroll."""
    page = widget
    page.set_viewport_size({"width": width, "height": height})
    _size(page, size)
    _feed(page)
    got = page.evaluate("""() => { const body = document.querySelector('#printer-status-widget .fcc-ps-body');
        const b = body.getBoundingClientRect();
        const tiles = Array.from(body.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
        return { shown: tiles.filter((r) => r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5).length, tiles: tiles.length,
                 sh: body.scrollHeight, ch: body.clientHeight, maxH: getComputedStyle(body).maxHeight }; }""")
    assert (got["shown"], got["tiles"]) == (13, 13) and got["sh"] <= got["ch"] + 1, (width, height, size, got)


# --- the collapsed strip (review, 2026-10-23, F5) ----------------------------------

# Per printer group of the collapsed strip: its chips' right edges against the
# window, its 🛑 count's text, whether the count is its last chip, how many
# lines the count's own text takes, and the page's sideways scroll.
STRIP_JS = r"""() => ({ iw: innerWidth, sw: document.documentElement.scrollWidth,
    groups: Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-header-chips .fcc-ps-printer-group')).map((g) => {
        const kids = Array.from(g.children); const chip = g.querySelector('.fcc-cr-chip');
        const lines = (el) => { const r = document.createRange(); r.selectNodeContents(el);
            const tops = []; Array.from(r.getClientRects()).filter((x) => x.width > 0).forEach((x) => {
                if (!tops.some((t) => Math.abs(t - x.top) < 3)) tops.push(x.top); }); return tops.length; };
        return { printer: g.dataset.printer, chips: kids.length,
                 right: Math.max(...kids.map((k) => k.getBoundingClientRect().right)),
                 left: Math.min(...kids.map((k) => k.getBoundingClientRect().left)),
                 count: chip ? chip.textContent : null, last: chip ? kids[kids.length - 1] === chip : null,
                 countLines: chip ? lines(chip) : 0, state: kids[0] && kids[0].classList.contains('fcc-ps-state-chip') }; }) })"""


# Dev's own head ids (RCOI-1 .. RCOI-8, XL-1 .. XL-5): the strip's chips are as
# wide as dev's.
STRIP_FLEET = {INDX: _printer("RCOI", 8, loaded=(0, 3)), XL: _printer("XL", 5, "PRINTING", loaded=(1, 2))}


@pytest.mark.parametrize("width, size", [(1024, "Small"), (1024, "Standard"), (1024, "Large"), (1024, "Extra Large"),
                                         (1280, "Extra Large"), (412, "Standard"), (390, "Standard")])
def test_the_collapsed_strip_keeps_every_chip_on_screen(widget, width, size):
    """The strip is all a minimized widget shows (Derek, 2026-06-12: the 🛑
    count rides on it "in case the activity log isn't always visible"). A
    printer's group wider than the window ran off its right edge, taking its
    last heads and its 🛑 count with it (the INDX's 8 heads at 1024 px at every
    size, at 1280 px at Extra Large, and on a phone). Now a group wraps its own
    chips: every chip inside the window, the state first and the count last,
    the 🛑 never parted from its number."""
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _size(page, size)
    _feed(page, STRIP_FLEET)
    page.evaluate("() => window.togglePrinterStatusWidget()")
    pending = [{"printer_name": INDX, "job_id": f"{INDX}#{i}"} for i in range(3)] + \
              [{"printer_name": XL, "job_id": f"{XL}#{i}"} for i in range(12)]
    page.evaluate("(p) => { window.__pending = p; return window.refreshCancelReviewBadge(); }", pending)
    page.wait_for_function("() => document.querySelectorAll('#printer-status-widget .fcc-ps-header-chips .fcc-cr-chip').length === 2",
                           timeout=3000)
    got = page.evaluate(STRIP_JS)
    assert got["sw"] <= got["iw"], f"the page scrolls sideways: {got}"
    assert [(g["printer"], g["chips"], g["count"], g["last"], g["state"], g["countLines"]) for g in got["groups"]] == [
        (INDX, 10, "🛑 3", True, True, 1), (XL, 7, "🛑 12", True, True, 1)], got
    for g in got["groups"]:
        assert g["left"] >= -0.5 and g["right"] <= got["iw"] + 0.5, f"a chip is off the screen: {width} {size} {g}"


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
