"""Printer Status: each printer's name (its ▲▼ arrows before it), the info
line under the name (its state, its 🛑 review count), its tiles under that
in even rows, the printers a step in under the title (Derek, 2026-10-22,
2026-10-23 and 2026-10-24).

2026-10-22: when a printer's heads don't fit on one line, split them into the
fewest rows with EQUAL counts (8 -> 4 + 4, 7 -> 4 + 3, 10 -> 5 + 5; never a
lone tile). The tiles then sat beside a 12.5rem name column (style "S1").
2026-10-23, after seeing S1, a narrower column (S2) and the name above the
tiles (S3): "name on top of tool heads, probably reads better, especially if
we indent in the toolheads more so that they read as a sub thing of the
printer name. We also avoid the word wrap effect on the red notification dot
about pending reviews ... Also, this way, if printer names go ungodly long for
some reason, they don't clash or break the toolhead display."
2026-10-24, approving S3 with two tweaks: "adjust the printers and the order
node to read as under printer status, so indenting the rows in just a bit so
it reads more like a sub set, and less like an ordered list" and "move the
individual printer state and review buttons before the name of the printer,
that way it's more of an easy glance at what's going on with each printer,
and all that data lines up so your eyes don't have to dart all over the place
to find out which printer is idle, printing, or has an error of some sort".
Later that day, seeing the state and the count before the name: "I do see
some value in being able to have the printer names first too. We could do
something like the printer name, then under it, the status and review,
basically we could treat that section as an information area about state and
issues, then the toolheads. While having the status information first is
nice, you now have to go hunting for the printer name to know what those
statuses apply to." So each printer is three parts:
    [▲▼] [name]                     <- the name's line
         [STATE] [🛑 N]             <- the info line (.fcc-ps-info)
         [tile] [tile] [tile] ...   <- the tiles, in even rows
the name, the info line and the tiles starting at the same place, a step in
from the arrows, and every printer starts 1.5rem in, under the title's first
letter. The state and the count have slots of the same width on every printer
(the count's is kept with no reviews), so the names, the states, the counts
and the tiles line up down the page.

Hermetic, and it RUNS under --offline: `isolated_page` (a chromium with no
route to any network) with the real static/css/global.css, text_size.js,
ui_builder.js, inv_core.js, inv_printer_status.js and cancel_review.js, a few
lines standing in for the Bootstrap classes the widget uses (Bootstrap comes
from a CDN), and the dashboard's own scan accumulator, lifted from
templates/components/scripts.html (since Group 50.6 a person's Enter on a
focused button presses it; a scan's Enter ends the scan). The widget is fed made-up fleets
through refreshPrinterStatusWidgetFromAggregate, as the heartbeat feeds it,
and the review count comes from cancel_review.js's own poll, answered in the
page. Pinned:
  - the rule (window.fccPrinterStatusTileRows(n, fit)): the fewest rows for
    what fits on a line, counts as equal as they can be, the longer first, a
    row of one tile only where at most two fit on a line;
  - each printer is its name's line, then the info line, then the tiles
    (2026-10-24): the arrows before the name, centred on its line; the name
    on one line, its full text in its title; under it the info line, the
    state badge (filling its slot) then the 🛑 N count (in its slot), on one
    centre line, the count's 🛑 and its number never parted (and the count is
    put back in its slot after a repaint and a reorder); under that the
    tiles; the name, the info line and the tiles start at the same place;
  - the names, the states, the counts and the tiles line up down the page:
    every printer's name, info line, state slot, count slot and first tile
    start at the same place and every badge is the same width, with IDLE,
    PRINTING, ATTENTION, ERROR, OFFLINE and no state yet, with and without
    reviews, at every size and on a phone; a state wider than ATTENTION
    (OPERATIONAL) or a count of 100 or more widens only its own slot, whole,
    never cut, and moves no name and no tile;
  - the printers step in under the title (2026-10-24): each row, its arrows
    first, starts 1.5rem in, under the title's first letter, where the body
    is 23rem wide or more; on a phone narrower than that at the body's edge,
    as before (there the step would cost the second tile on each line);
  - every tile sits under the info line, every line of tiles starts under
    the name's first letter, and nothing sticks out of the row;
  - even rows at every Text size at 390, 412, 1024, 1366 and 1600 px (the
    INDX's 8 heads one row on Derek's 1600 px window at Small and Standard
    again, 4 + 4 at Large and Extra Large); the rows are the fewest that fit
    and are drawn as the layout recorded them (data-rows);
  - a phone: where fewer than two tiles fit under the name and more fit
    across the row, the tiles start at the row's edge, at most two to a line
    (at Standard every window from 376 to 425 px; below that one a line,
    under the name);
  - a printer between two others (both arrows) has the same name line as
    the others (review, 2026-10-23, F6), its arrows centred on the name's
    line, clear of the divider above, of the info line and of the tiles;
  - a 60-character printer name keeps to one line (it ends in "…" where the
    line is short, its full text in its title), and the info line and the
    tiles sit exactly where they sit under a short name;
  - a printer whose name has an apostrophe ("Derek's XL"), or quotes, an
    ampersand, angle brackets and a backslash, gets its 🛑 N count on its
    info line and in the collapsed strip, and its arrows move it, by mouse
    and by Enter: data-printer holds the plain name, the arrows' handlers a
    JS string (SpoolCardBuilder.jsArg);
  - 7, 10 and 13 heads where three fit on a line are 3 + 2 + 2, 3 + 3 + 2 + 2
    and 3 + 3 + 3 + 2 + 2, each line starting under the name (a plain grid
    fill is 3 + 3 + 1);
  - what the browser drew is checked: with a margin the sums don't count, a
    line of tiles wider than its area is laid out again with one tile fewer
    (the measure's own count, data-fit, says the check did it), under the
    name, or at the row's edge where none fits under the name;
  - at a 110 % display scale (a real device scale factor: the tile area is
    519.84 or 1399.84 px, which clientWidth calls 520 or 1400, exactly what 3
    or 8 tiles need), the MEASURE counts the tiles that fit (data-fit);
  - Enter on a focused ▲ / ▼ moves the printer with the accumulator cancelling
    every Enter, as the dashboard does (review, 2026-10-23, F3), and the focus
    stays on the moved printer's arrow; a scan typed onto a focused arrow
    stays a scan;
  - a short laptop window (review, 2026-10-23, F2): on a 1280 x 800 laptop at
    Small and Standard dev's two printers (8 and 5 heads) show whole in the
    open widget; where the info lines make them taller than the widget may
    be (1366 x 768, and 1280 x 800 at Large) the widget scrolls inside
    itself, never past its limit, and every tile can be scrolled to;
  - the collapsed strip keeps every chip inside the window at 1024 px at every
    size, at 1280 px at Extra Large and on a phone, its 🛑 count last and in
    one piece (review, 2026-10-23, F5);
  - it lays out again after a Text size change and a resize, after a repaint
    and the ▲▼ reorder (by mouse and by keyboard), after the widget is
    collapsed and opened again, and after a review count changes (the
    review poll's own re-balance, which no count needs any more: it moves no
    tile);
  - the material line's line height is 1.2 at every size.
The same on the real page (Bootstrap, the heartbeat, dev's container) is
test_printer_status_even_rows_e2e.py.

RED before the info line under the name (2026-10-24, second round). On
c0d4962 (this file in a throwaway worktree of it): 61 of 123, for the name's
line then the info line, the names, info lines, states, counts and tiles
lining up, the rows the name's new place changed (1600 px at Small and
Standard, 1024 px, 1366 px at Extra Large, the phones at Large and Extra
Large and from 426 px at Standard), the middle printer's gaps, the long name
leaving the info line and the tiles where they are, a count of 100 moving no
tile, the apostrophe name, the 110 % scale windows and the drawn check at
1307 and 440 px. The 62 that hold there are guards for what this must not
change: the rule (20), the step in under the title (12), the collapsed strip
(7), the material line (4), the accumulator canary, Enter and a scan on an
arrow (3), the short laptop windows (5), the rows that come out the same
either way (9: 390 and 412 px at Small and Standard, 1366 px at Small,
Standard and Large, 1600 px at Large and Extra Large) and the drawn check at
412 and 380 px. Mutations of the finished code, one at a time: the review
poll not laying the rows out again fails
test_a_count_reaching_100_moves_no_tile_and_the_poll_still_lays_the_rows_out;
data-printer back to the arrows' JS escape fails the apostrophe test; the
tile area measured from the row's edge instead of from the name fails 31
(the phones, the 110 % scale, the drawn checks). A tile allowed to shrink
again before the rows are laid out (no `flex: none` on .fcc-ps-th) fails
nothing now: under the name there is room for a whole tile on any window
from 226 px. (On 8f9213c, before the first round, that round's version of
this file was 76 of 121 red.)
"""
from __future__ import annotations

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
        <div class="fcc-ps-header-chips"></div>
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

def _real_accumulator():
    """The dashboard's scan accumulator (scripts.html's keydown block), lifted
    as it is (test_slow_scan_slash_js.py's way): since Group 50.6 a person's
    Enter on a focused button presses it, and a scan's Enter still ends the
    scan. The scans it hands to processScan land in window.__scans here."""
    src = SCRIPTS_HTML.read_text(encoding="utf-8")
    a = src.index("state.scanStartTime = 0;")
    b = src.index("// L206", a)
    block = src[a:b]
    assert "processScan(state.scanBuffer" in block and "function personMayPress" in block, block[:300]
    return block


# Added after the modules, as the dashboard's own listener is (its
# DOMContentLoaded handler).
ACCUMULATOR = (
    "window.__scans = [];\n"
    "window.processScan = function (buf) { window.__scans.push(buf); };\n"
    + _real_accumulator()
)

INDX = "ZZ Even INDX"
XL = "ZZ Even XL"
SIZES = ("Small", "Standard", "Large", "Extra Large")
ROOT_PX = {"Small": 16, "Standard": 16, "Large": 18, "Extra Large": 20}
# 60 characters: longer than a name's line on a phone, shorter than one on 1600 px.
LONG_NAME = "ZZ A Printer Whose Name Goes On And On Past Any Sensible End"
assert len(LONG_NAME) == 60
# The printers step in under the title from a body this many rem wide (two
# tiles beside each other, 21.5rem, plus the 1.5rem step).
STEP_FROM_REM = 23
STEP_REM = 1.5


def _item(sid, colour, material, grams=640):
    return {"id": sid, "display": f"#{sid} Even Test {material}", "color": colour, "color_direction": "longitudinal",
            "remaining_weight": grams, "initial_weight": 1000, "details": {"material": material}}


def _printer(prefix, n, state="IDLE", loaded=()):
    """`n` heads; the positions in `loaded` hold a spool with a material line
    (PETG and Polycarbonate: a "g" and a "y" to clip). `state` None is a
    printer that didn't answer (OFFLINE); "" one not probed yet (no badge)."""
    mats = ["PETG", "Polycarbonate", "PLA Silk", "ASA"]
    out = {"toolheads": [{"id": f"{prefix}-{i + 1}", "position": i, "unbound": False,
                          "item": _item(9200 + i, "2a6f97", mats[i % len(mats)]) if i in loaded else None,
                          "loaded_count": 1 if i in loaded else 0}
                         for i in range(n)]}
    if state is None:
        out["state"] = None
    elif state:
        out["state"] = {"state": state, "is_active": state == "PRINTING"}
    return out


FLEET = {INDX: _printer("ZE", 8, loaded=(0, 3)), XL: _printer("ZX", 5, "PRINTING", loaded=(1, 2))}

# Per printer: the count on each line of tiles, what the layout recorded
# (data-rows) and how many tiles its measure counted on a line (data-fit),
# whether the tiles start at the row's edge (a phone: .fcc-ps-edge), whether
# every tile is under the name and the info line, whether every line of tiles
# starts under the name's first letter (`under`) or at the row's left edge
# (`atEdge`), where the name and the first tile start (`nameLeft`,
# `tileLeft`) and the name's step in from the row's left edge (the arrows and
# their gap), how many tiles stick out (past the row's right edge, or left of
# where the lines start), and how many tiles fit on a line by measure, with
# no slack, under the name (`fits`) and across the row (`fitsWhole`).
LAYOUT_JS = r"""() => {
    const out = {};
    document.querySelectorAll('#printer-status-widget .fcc-ps-row').forEach((row) => {
        const rs = getComputedStyle(row);
        const rowR = row.getBoundingClientRect();
        const left = rowR.left + parseFloat(rs.paddingLeft) + parseFloat(rs.borderLeftWidth);
        const right = rowR.right - parseFloat(rs.paddingRight) - parseFloat(rs.borderRightWidth);
        const name = row.querySelector('.fcc-ps-name').getBoundingClientRect();
        const header = Array.from(row.querySelectorAll('.fcc-ps-reorder, .fcc-ps-name, .fcc-ps-info, .fcc-ps-state, .fcc-cr-chip'))
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
            nameLeft: Math.round(name.left * 100) / 100,
            tileLeft: tiles.length ? Math.round(Math.min(...tiles.map((r) => r.left)) * 100) / 100 : null,
            indent: Math.round((name.left - left) * 100) / 100,
            out: tiles.filter((r) => r.right > right + 0.5 || r.left < start - 0.5).length,
            fits: tileW ? Math.max(0, Math.floor((right - name.left + gap) / (tileW + gap))) : 0,
            fitsWhole: tileW ? Math.floor((right - left + gap) / (tileW + gap)) : 0,
        };
    });
    return out;
}"""

# Per printer, its name and its info line: the box (and centre line) of each
# part (the arrows' pair, the name, the info line, the state's slot and its
# badge, the count's slot and its 🛑 N), how many lines the name's and the
# count's text take (a Range's boxes), the count's text and whether it is in
# its slot on the info line, the top of the first line of tiles, the row's
# content edges, and the name's title and whether it is cut short with "…".
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
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, mid: (r.top + r.bottom) / 2, width: r.width }; };
    document.querySelectorAll('#printer-status-widget .fcc-ps-row').forEach((row) => {
        const rs = getComputedStyle(row);
        const rowR = row.getBoundingClientRect();
        const name = row.querySelector('.fcc-ps-name');
        const info = row.querySelector('.fcc-ps-info');
        const chip = row.querySelector('.fcc-cr-chip');
        const arrows = Array.from(row.querySelectorAll('.fcc-ps-reorder')).map(box);
        const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
        out[row.dataset.printer] = {
            arrows: arrows.length ? { left: Math.min(...arrows.map((a) => a.left)), right: Math.max(...arrows.map((a) => a.right)),
                                      mid: (Math.min(...arrows.map((a) => a.top)) + Math.max(...arrows.map((a) => a.bottom))) / 2 } : null,
            name: box(name), info: box(info), badge: box(row.querySelector('.fcc-ps-state')), chip: box(chip),
            slot: box(row.querySelector('.fcc-ps-state-slot')), count: box(row.querySelector('.fcc-ps-count')),
            badgeText: row.querySelector('.fcc-ps-state') ? row.querySelector('.fcc-ps-state').textContent : null,
            chipInInfo: !!chip && !!info && info.contains(chip) && !name.contains(chip),
            chipInSlot: !!chip && !!chip.closest('.fcc-ps-count'),
            chipText: chip ? chip.textContent : null,
            nameLines: lineTops(name), chipLines: chip ? lineTops(chip) : 0,
            tilesTop: tiles.length ? Math.min(...tiles.map((t) => t.top)) : null,
            rowLeft: rowR.left + parseFloat(rs.paddingLeft), rowRight: rowR.right - parseFloat(rs.paddingRight),
            title: name.getAttribute('title'), text: name.textContent,
            cut: name.scrollWidth > name.clientWidth + 0.5 && getComputedStyle(name).textOverflow === 'ellipsis',
        };
    });
    return out;
}"""

# Where the printers start: the body's content edge and width, the root font
# size, the title's left edge, and each row's left edge and its arrows'.
STEP_JS = r"""() => {
    const w = document.getElementById('printer-status-widget');
    const body = w.querySelector('.fcc-ps-body'); const bs = getComputedStyle(body);
    const br = body.getBoundingClientRect();
    return { bodyLeft: br.left + parseFloat(bs.borderLeftWidth) + parseFloat(bs.paddingLeft),
             bodyW: body.clientWidth - parseFloat(bs.paddingLeft) - parseFloat(bs.paddingRight),
             root: parseFloat(getComputedStyle(document.documentElement).fontSize),
             title: w.querySelector('.fcc-ps-title').getBoundingClientRect().left,
             rows: Array.from(body.querySelectorAll('.fcc-ps-row')).map((row) => ({ printer: row.dataset.printer,
                 left: row.getBoundingClientRect().left,
                 arrows: row.querySelector('.fcc-ps-reorder-stack').getBoundingClientRect().left })) };
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


def _name_then_info(h, name, size):
    """One printer as Derek chose it (2026-10-24: "the printer name, then
    under it, the status and review ... then the toolheads"): the arrows
    before the name, centred on its line; the name on one line, its full text
    its title; under it the info line, starting where the name starts, the
    state badge filling its slot first and the 🛑 N count in its slot after
    it, on one centre line; the tiles under the info line. Everything inside
    the row."""
    where = (name, size, h)
    assert h["nameLines"] == 1, where
    assert h["info"] and h["slot"] and h["count"], f"the info line or its slots are missing: {where}"
    if h["arrows"]:
        assert h["arrows"]["right"] <= h["name"]["left"] - 0.5, f"the arrows should come before the name: {where}"
        assert abs(h["arrows"]["mid"] - h["name"]["mid"]) <= 1.5, f"the arrows should centre on the name's line: {where}"
    # The info line under the name, from the name's first letter.
    assert h["info"]["top"] >= h["name"]["bottom"] - 0.5, f"the info line should be under the name: {where}"
    assert abs(h["info"]["left"] - h["name"]["left"]) <= 0.5, f"the info line should start under the name: {where}"
    # On it the state first, then the count, on one line.
    assert abs(h["slot"]["left"] - h["info"]["left"]) <= 0.5, f"the state should come first on the info line: {where}"
    assert h["slot"]["right"] <= h["count"]["left"] - 0.5, f"the state should come before the count: {where}"
    assert abs(h["slot"]["mid"] - h["count"]["mid"]) <= 1.5, f"the state and the count should share a line: {where}"
    assert min(h["slot"]["top"], h["count"]["top"]) >= h["name"]["bottom"] - 0.5, f"the state is on the name's line: {where}"
    if h["badge"]:
        assert abs(h["badge"]["left"] - h["slot"]["left"]) <= 0.5 and abs(h["badge"]["right"] - h["slot"]["right"]) <= 0.5, (
            f"the badge should fill its slot: {where}")
        assert abs(h["badge"]["mid"] - h["slot"]["mid"]) <= 1.5, where
    if h["chip"]:
        assert h["chipInInfo"] and h["chipInSlot"], f"the 🛑 N count should be in its slot on the info line: {where}"
        assert h["chipLines"] == 1, f"the 🛑 and its count split across lines: {where}"
        assert h["chip"]["left"] >= h["count"]["left"] - 0.5 and h["chip"]["right"] <= h["count"]["right"] + 0.5, where
        assert abs(h["chip"]["mid"] - h["slot"]["mid"]) <= 1.5, where
    # Then the tiles, under the info line.
    if h["tilesTop"] is not None:
        assert h["tilesTop"] >= max(h["info"]["bottom"], h["slot"]["bottom"], h["count"]["bottom"]) - 0.5, (
            f"the tiles should be under the info line: {where}")
    assert h["name"]["right"] <= h["rowRight"] + 0.5 and h["count"]["right"] <= h["rowRight"] + 0.5, where
    # Its full name is its title, whether or not it is cut short.
    assert h["title"] == name, where


def _lined_up(head, names, where):
    """Derek, 2026-10-24: "all that data lines up so your eyes don't have to
    dart all over the place". Every printer's name, info line, state slot and
    count slot start at the same place, and every slot and badge is the same
    width, whatever the state and with or without reviews."""
    for part in ("name", "info", "slot", "count"):
        lefts = [round(head[n][part]["left"], 2) for n in names]
        assert max(lefts) - min(lefts) <= 0.5, f"the {part}s don't line up: {where} {dict(zip(names, lefts))}"
    for part in ("slot", "count"):
        widths = [round(head[n][part]["width"], 2) for n in names]
        assert max(widths) - min(widths) <= 0.5, f"the {part}s differ in width: {where} {dict(zip(names, widths))}"
    badges = {n: round(head[n]["badge"]["width"], 2) for n in names if head[n]["badge"]}
    if badges:
        assert max(badges.values()) - min(badges.values()) <= 0.5, f"the badges differ in width: {where} {badges}"


def _tiles_lined_up(got, where):
    """Every printer's tiles start at the same place: under the names, or, on
    a phone, at the rows' edge (every printer is the same there)."""
    lefts = {n: g["tileLeft"] for n, g in got.items() if g["tileLeft"] is not None}
    assert max(lefts.values()) - min(lefts.values()) <= 0.5, f"the tiles don't line up: {where} {lefts}"
    for n, g in got.items():
        if not g["edge"]:
            assert abs(g["tileLeft"] - g["nameLeft"]) <= 0.5, f"the tiles should start under the name: {where} {n} {g}"


def _placed(g, where):
    """Where a printer's tiles start: under the name's first letter, or, where
    fewer than two fit there and more fit across the row (a phone), at the
    row's edge, at most two to a line. Either way under the info line,
    nothing out of the row, and the fewest rows for what fits there."""
    want_edge = g["fits"] < 2 and g["fitsWhole"] > g["fits"]
    assert g["edge"] == want_edge, f"the tiles should start {'at the edge' if want_edge else 'under the name'}: {where} {g}"
    assert g["below"] and (g["atEdge"] if g["edge"] else g["under"]) and g["out"] == 0, (where, g)
    fits = min(g["fitsWhole"], 2) if g["edge"] else g["fits"]
    n = sum(int(c) for c in g["rows"].split("+"))
    assert len(g["rows"].split("+")) == -(-n // max(1, fits)), (where, g)


def _stepped(page, where):
    """The printers start under the title's first letter, 1.5rem in, where the
    body is 23rem wide or more, else at the body's edge; the arrows first."""
    got = page.evaluate(STEP_JS)
    stepped = got["bodyW"] >= STEP_FROM_REM * got["root"] - 0.01
    want = got["bodyLeft"] + (STEP_REM * got["root"] if stepped else 0)
    for r in got["rows"]:
        assert abs(r["left"] - want) <= 0.5, f"{'stepped' if stepped else 'at the edge'}? {where} {got}"
        assert abs(r["arrows"] - r["left"]) <= 0.5, (where, got)
        if stepped:
            assert abs(r["arrows"] - got["title"]) <= 0.5, f"the arrows should sit under the title: {where} {got}"
    return stepped


# --- the rule ------------------------------------------------------------------

@pytest.mark.parametrize("n, fit, sizes", [
    (8, 8, [8]),
    (8, 7, [4, 4]),              # the INDX on Derek's 1600 px window at Standard
    (8, 6, [4, 4]),              # ... at Large and Extra Large
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

# (width, size) -> (the INDX's 8 heads, the XL's 5, whether they start at the
# row's edge): one row where all fit under the name, else the fewest even
# rows. The name, and so the tiles, start a step in from the arrows (26 px
# from the row's edge at Standard, 1.5rem more from the body's), so on Derek's
# 1600 px window the INDX's 8 are one row at Small and Standard again (they
# were 4 + 4 while the state and the count sat before the name), 4 + 4 at
# Large and Extra Large. On a 390 or 412 px phone at Small and Standard the
# tiles start at the row's edge, two to a line; at Large and Extra Large one
# a line, under the name (two don't fit even from the edge).
ONES = "+".join(["1"] * 8), "+".join(["1"] * 5)
WIDTHS = {
    (390, "Small"): ("2+2+2+2", "2+2+1", True), (390, "Standard"): ("2+2+2+2", "2+2+1", True),
    (390, "Large"): (*ONES, False), (390, "Extra Large"): (*ONES, False),
    (412, "Small"): ("2+2+2+2", "2+2+1", True), (412, "Standard"): ("2+2+2+2", "2+2+1", True),
    (412, "Large"): (*ONES, False), (412, "Extra Large"): (*ONES, False),
    (1024, "Small"): ("4+4", "5", False), (1024, "Standard"): ("4+4", "5", False),
    (1024, "Large"): ("4+4", "3+2", False), (1024, "Extra Large"): ("4+4", "3+2", False),
    (1366, "Small"): ("4+4", "5", False), (1366, "Standard"): ("4+4", "5", False),
    (1366, "Large"): ("4+4", "5", False), (1366, "Extra Large"): ("4+4", "5", False),
    (1600, "Small"): ("8", "5", False), (1600, "Standard"): ("8", "5", False),
    (1600, "Large"): ("4+4", "5", False), (1600, "Extra Large"): ("4+4", "5", False),
}


@pytest.mark.parametrize("width, size", list(WIDTHS))
def test_even_rows_under_the_name_at_each_size_and_width(widget, width, size):
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    _feed(page)
    got = _layout(page)
    indx, xl, edge = WIDTHS[(width, size)]
    assert (got[INDX]["rows"], got[XL]["rows"]) == (indx, xl), (width, size, got)
    for name in (INDX, XL):
        g = got[name]
        # Under the info line; each line starting under the name's first
        # letter, or, on a phone, at the row's edge. Nothing sticks out, and
        # the rows are the fewest that fit.
        _placed(g, (width, size, name))
        assert g["edge"] == edge, (width, size, name, g)
    # Both printers' names, and their tiles, start at the same place.
    assert abs(got[INDX]["nameLeft"] - got[XL]["nameLeft"]) <= 0.5, got
    _tiles_lined_up(got, (width, size))
    _stepped(page, (width, size))


# Phones at Standard (review, 2026-10-23; the info line under the name since
# 2026-10-24): the name starts a step in from the arrows (26 px), so under it
# a row has room for one tile below 426 px, and the tiles start at the row's
# edge where two fit across it: from 376 px (two tiles are 344 px; from 400 px
# the printers step in under the title and the row is 24 px narrower, which
# still leaves 344). Below 376 px one a line, under the name (one fits there
# from 226 px).
PHONES = {
    360: (*ONES, False),                            # one a line, under the name
    375: (*ONES, False),                            # an iPhone SE / 13 mini
    376: ("2+2+2+2", "2+2+1", True),
    384: ("2+2+2+2", "2+2+1", True),
    390: ("2+2+2+2", "2+2+1", True),                # an iPhone 12 to 14
    393: ("2+2+2+2", "2+2+1", True),                # an iPhone 14 Pro to 16
    399: ("2+2+2+2", "2+2+1", True),                # the last width without the step
    400: ("2+2+2+2", "2+2+1", True),                # stepped in: the row is 344 px, two exactly
    412: ("2+2+2+2", "2+2+1", True),                # a Pixel, a Galaxy
    425: ("2+2+2+2", "2+2+1", True),                # the last width at the edge
    426: ("2+2+2+2", "2+2+1", False),               # two fit under the name
    430: ("2+2+2+2", "2+2+1", False),               # an iPhone Pro Max
    580: ("2+2+2+2", "2+2+1", False),
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
    _tiles_lined_up(got, width)
    # The name and the info line keep their places either way.
    head = page.evaluate(HEADER_JS)
    for name in (INDX, XL):
        _name_then_info(head[name], name, "Standard")
    _lined_up(head, [INDX, XL], width)
    # The step under the title never costs the second tile.
    assert _stepped(page, width) == (width >= 400), width


def test_at_the_edge_at_large_too(widget):
    """At Large a tile is 189 px: two need 387 px, which a 430 px phone has
    across the row (394) but not under the name (365). At 412 px one fits
    either way: one a line, under the name."""
    page = widget
    page.set_viewport_size({"width": 430, "height": 900})
    _size(page, "Large")
    _feed(page)
    got = _layout(page)
    assert (got[INDX]["rows"], got[XL]["rows"], got[INDX]["edge"]) == ("2+2+2+2", "2+2+1", True), got
    for name in (INDX, XL):
        _placed(got[name], (430, "Large", name))
    # One a line, under the name, when the window is too narrow for two; and
    # two a line from the edge again when it grows back.
    page.set_viewport_size({"width": 412, "height": 900})
    _settled(page, {INDX: "1+1+1+1+1+1+1+1"})
    g = _layout(page)[INDX]
    assert not g["edge"] and g["under"], g
    page.set_viewport_size({"width": 430, "height": 900})
    _settled(page, {INDX: "2+2+2+2"})
    assert _layout(page)[INDX]["edge"]


@pytest.mark.parametrize("width, size", [(412, "Standard"), (412, "Extra Large"), (1600, "Standard"),
                                         (1600, "Extra Large"), (1024, "Large"), (390, "Standard")])
def test_the_name_then_the_info_line_with_the_dot_and_its_count_together(widget, width, size):
    """The ▲▼ arrows and the name on the first line, the state badge and the
    🛑 N count on the info line under it, then the tiles (Derek, 2026-10-24),
    the count's dot and number never parted (Derek: "avoid the word wrap
    effect on the red notification dot"). 12 reviews for the INDX at its
    widest (PRINTING) on a phone at Extra Large is the fullest info line."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    fleet = {INDX: _printer("ZE", 8, "PRINTING", loaded=(0, 3)), XL: _printer("ZX", 5, loaded=(1, 2))}
    _feed(page, fleet)
    _reviews(page, {INDX: 12, XL: 1})
    head = page.evaluate(HEADER_JS)
    for name in (INDX, XL):
        _name_then_info(head[name], name, size)
    _lined_up(head, [INDX, XL], (width, size))
    assert (head[INDX]["chipText"], head[XL]["chipText"]) == ("🛑 12", "🛑 1"), head
    # The first printer has only ▼ and the last only ▲: each on the name's line.
    assert head[INDX]["arrows"] and head[XL]["arrows"], head
    got = _layout(page)
    for name, g in got.items():
        _placed(g, (width, size, name))
    _tiles_lined_up(got, (width, size))


# Derek, 2026-10-24: "which printer is idle, printing, or has an error of some
# sort". Every state FCC draws differently (idle, printing, paused,
# attention, offline) and a printer whose state isn't known yet, with and
# without reviews.
ALIGN = {"ZZ Align 1 Idle": _printer("ZA", 4, "IDLE", loaded=(0,)),
         "ZZ Align 2 Printing": _printer("ZB", 5, "PRINTING", loaded=(1,)),
         "ZZ Align 3 Attention": _printer("ZC", 3, "ATTENTION"),
         "ZZ Align 4 Error": _printer("ZD", 2, "ERROR", loaded=(0,)),
         "ZZ Align 5 Paused": _printer("ZP", 2, "PAUSED"),
         "ZZ Align 6 Offline": _printer("ZF", 2, None),
         "ZZ Align 7 Not Probed": _printer("ZN", 2, "")}
ALIGN_REVIEWS = {"ZZ Align 2 Printing": 12, "ZZ Align 3 Attention": 1, "ZZ Align 6 Offline": 3}


@pytest.mark.parametrize("width, size", [(1600, "Small"), (1600, "Standard"), (1600, "Large"), (1600, "Extra Large"),
                                         (1024, "Standard"), (412, "Standard"), (390, "Extra Large")])
def test_the_names_the_states_the_counts_and_the_tiles_line_up_down_the_page(widget, width, size):
    """Every printer's name starts at the same place, its info line under it
    from the same place, its state as wide as every other's (as wide as
    ATTENTION, the widest PrusaLink's status reports), its review count's
    slot there with no reviews too, and its tiles from the name's first
    letter, so a glance down the page reads the names, and under each its
    state and its reviews, in one column. A printer whose state isn't known
    yet keeps the empty slot."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    _feed(page, ALIGN)
    _reviews(page, ALIGN_REVIEWS)
    head = page.evaluate(HEADER_JS)
    names = list(ALIGN)
    assert [head[n]["badgeText"] for n in names] == ["IDLE", "PRINTING", "ATTENTION", "ERROR", "PAUSED", "OFFLINE",
                                                     None], head
    assert [head[n]["chipText"] for n in names] == [None, "🛑 12", "🛑 1", None, None, "🛑 3", None], head
    for n in names:
        _name_then_info(head[n], n, size)
    _lined_up(head, names, (width, size))
    # The slot fits ATTENTION exactly: its badge's text isn't cut.
    att = page.evaluate("""() => { const b = Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-state'))
        .find((el) => el.textContent === 'ATTENTION'); return [b.scrollWidth, b.clientWidth]; }""")
    assert att[0] <= att[1], att
    got = _layout(page)
    for n, g in got.items():
        _placed(g, (width, size, n))
    _tiles_lined_up(got, (width, size))
    _stepped(page, (width, size))


def test_a_wider_state_or_a_count_over_99_widens_only_its_own_slot(widget):
    """The slots are sized for what is usual: ATTENTION, the widest state
    PrusaLink's status reports, and 🛑 99. OPERATIONAL (from the older
    /api/printer some firmware answers instead) and a count of 100 or more
    widen their own slot and stay whole on the info line; after OPERATIONAL
    that printer's count steps right by the difference, the other printers'
    counts stay lined up, and every name and every tile stays where it is."""
    page = widget
    fleet = {"ZZ Wide 1": _printer("ZA", 4), "ZZ Wide 2 Old Firmware": _printer("ZB", 3, "OPERATIONAL"),
             "ZZ Wide 3": _printer("ZC", 5, "PRINTING", loaded=(1,)), "ZZ Wide 4 Busy Reviews": _printer("ZD", 2)}
    _feed(page, fleet)
    _reviews(page, {"ZZ Wide 1": 7, "ZZ Wide 4 Busy Reviews": 123})
    head = page.evaluate(HEADER_JS)
    for n in fleet:
        _name_then_info(head[n], n, "Standard")
    assert head["ZZ Wide 2 Old Firmware"]["badgeText"] == "OPERATIONAL" and head["ZZ Wide 4 Busy Reviews"]["chipText"] == "🛑 123"
    _lined_up(head, ["ZZ Wide 1", "ZZ Wide 3"], "the usual ones")
    usual = head["ZZ Wide 1"]
    old = head["ZZ Wide 2 Old Firmware"]
    assert 0.5 < old["count"]["left"] - usual["count"]["left"] < 20, (old, usual)
    assert head["ZZ Wide 4 Busy Reviews"]["count"]["width"] - usual["count"]["width"] > 0.5, head
    # The names (and the info lines' first slot) line up whatever is on them.
    for part in ("name", "info", "slot"):
        lefts = {n: round(head[n][part]["left"], 2) for n in fleet}
        assert max(lefts.values()) - min(lefts.values()) <= 0.5, (part, lefts)
    whole = page.evaluate("""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-state, #printer-status-widget .fcc-ps-body .fcc-cr-chip'))
        .map((el) => [el.textContent, el.scrollWidth <= el.clientWidth])""")
    assert all(ok for _t, ok in whole), whole
    got = _layout(page)
    for n, g in got.items():
        _placed(g, n)
    _tiles_lined_up(got, "a wider state and a count over 99")


def test_a_count_reaching_100_moves_no_tile_and_the_poll_still_lays_the_rows_out(widget):
    """While the count sat before the name, a count of 100 or more widened
    its slot and moved the name and the tiles under it 7 px right (at 922 px
    a line of four then stuck out, and the review poll laid the rows out
    again). On the info line under the name it moves nothing: every tile
    stays where it was, the rows too. The poll still lays them out again
    when a count changes (cheap, and right whatever the info line comes to
    hold): the spy below counts it."""
    page = widget
    page.set_viewport_size({"width": 922, "height": 1300})
    _feed(page)
    _reviews(page, {INDX: 7})
    tiles_js = """() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-th')).map((t) => {
        const r = t.getBoundingClientRect(); return [Math.round(r.left * 100) / 100, Math.round(r.top * 100) / 100]; })"""
    before = page.evaluate(tiles_js)
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "3+2")
    page.evaluate("""() => { const f = window.balancePrinterStatusRows; window.__balanced = 0;
        window.balancePrinterStatusRows = () => { window.__balanced++; f(); }; }""")
    _reviews(page, {INDX: 123})
    got = _layout(page)
    assert (got[INDX]["rows"], got[XL]["rows"]) == ("4+4", "3+2"), got
    assert page.evaluate(tiles_js) == before, "a count of 100 or more moved a tile"
    assert page.evaluate("window.__balanced") >= 1, "the review poll no longer lays the rows out when a count changes"
    for n, g in got.items():
        _placed(g, n)
    _tiles_lined_up(got, "with 🛑 123")
    # And as it was when the reviews are dealt with.
    _reviews(page, {INDX: 0})
    got = _layout(page)
    assert (got[INDX]["rows"], got[XL]["rows"]) == ("4+4", "3+2"), got
    assert page.evaluate(tiles_js) == before


# The printers step in under the title (Derek, 2026-10-24).
@pytest.mark.parametrize("width, size, stepped", [
    (1600, "Small", True), (1600, "Standard", True), (1600, "Large", True), (1600, "Extra Large", True),
    (1024, "Standard", True), (412, "Standard", True), (400, "Standard", True), (399, "Standard", False),
    (390, "Standard", False), (412, "Extra Large", False), (450, "Large", True), (449, "Large", False),
])
def test_the_printers_step_in_under_the_title(widget, width, size, stepped):
    """Each printer, its ▲▼ included, starts under the title's first letter,
    1.5rem in, so the printers read as the title's own and not as a numbered
    list (the arrows at the edge read like its numbers). The divider between
    printers steps in with them. A phone whose body is under 23rem keeps them
    at the edge, as before: there the step would cost the second tile on each
    line. In rem, so the same point at every size: the body is the window
    less the widget's 1rem each side, so the step comes at 400 px at
    Standard and 450 px at Large (23rem is 414 px there)."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    _feed(page)
    assert _stepped(page, (width, size)) == stepped
    divider = page.evaluate("""() => { const row = document.querySelectorAll('#printer-status-widget .fcc-ps-row')[1];
        return [row.getBoundingClientRect().left, parseFloat(getComputedStyle(row).borderTopWidth)]; }""")
    assert divider[1] >= 1, divider
    for name, g in _layout(page).items():
        _placed(g, (width, size, name))


# A printer between two others shows both arrows (review, 2026-10-23, F6).
FIRST, MIDDLE, LAST = "ZZ A First", "ZZ B Middle", "ZZ C Last"
THREE = {FIRST: _printer("ZA", 8, loaded=(0,)), MIDDLE: _printer("ZB", 3, "PRINTING", loaded=(1,)),
         LAST: _printer("ZC", 5, loaded=(1,))}

# Per printer: the name's box, the gap from the name's line to the info line
# and from the info line to the first tile, the arrows' boxes, the info
# line's box, the divider above the row (the bottom of its top border) and
# every tile's box.
ARROWS_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row')).map((row) => {
    const rr = row.getBoundingClientRect();
    const name = row.querySelector('.fcc-ps-name').getBoundingClientRect();
    const info = row.querySelector('.fcc-ps-info').getBoundingClientRect();
    const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
    const arrows = Array.from(row.querySelectorAll('.fcc-ps-reorder')).map((a) => a.getBoundingClientRect());
    const box = (r) => ({ left: r.left, right: r.right, top: r.top, bottom: r.bottom });
    return { printer: row.dataset.printer, n: arrows.length, nameH: name.height,
             nameMid: (name.top + name.bottom) / 2, nameToInfo: info.top - name.bottom,
             infoToTile: Math.min(...tiles.map((t) => t.top)) - info.bottom,
             divider: rr.top + parseFloat(getComputedStyle(row).borderTopWidth), arrows: arrows.map(box),
             info: box(info), tiles: tiles.map(box), edge: row.classList.contains('fcc-ps-edge') }; })"""


def _apart(a, b, by=2):
    return a["right"] <= b["left"] or b["right"] <= a["left"] or a["bottom"] + by <= b["top"] or b["bottom"] + by <= a["top"]


@pytest.mark.parametrize("width, size", [(1600, "Standard"), (1600, "Extra Large"), (1024, "Large"),
                                         (390, "Standard"), (430, "Large")])
def test_a_printer_between_two_others_has_the_same_name_line(widget, width, size):
    """Every printer's first line is the name's, the middle one's too (it
    shows both arrows; their pair made its line 34 px tall at Standard, so
    its tiles sat 12.2 px under its name instead of 5.6): its info line and
    its tiles sit as far under its name as every other printer's. The arrows
    stay centred on the name's line, at least 2 px clear of the divider
    above, of the info line beside them and of every tile, on a phone whose
    tiles start at the row's edge too (390 px at Standard, 430 px at Large)."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    _feed(page, THREE)
    rows = page.evaluate(ARROWS_JS)
    assert [(r["printer"], r["n"]) for r in rows] == [(FIRST, 1), (MIDDLE, 2), (LAST, 1)], rows
    assert len({r["edge"] for r in rows}) == 1 and rows[0]["edge"] == (width in (390, 430)), rows
    for gap in ("nameToInfo", "infoToTile"):
        gaps = [round(r[gap], 1) for r in rows]
        assert max(gaps) - min(gaps) <= 0.5, f"{gap} differs between the printers: {gaps}"
    for r in rows:
        where = (width, size, r["printer"], r)
        assert r["nameToInfo"] >= -0.5, f"the info line overlaps the name: {where}"
        mid = (min(a["top"] for a in r["arrows"]) + max(a["bottom"] for a in r["arrows"])) / 2
        assert abs(mid - r["nameMid"]) <= 1.5, where
        if r["printer"] != FIRST:
            assert min(a["top"] for a in r["arrows"]) >= r["divider"] + 2, f"an arrow touches the divider: {where}"
        for a in r["arrows"]:
            assert _apart(a, r["info"]), f"an arrow touches the info line: {where}"
            for t in r["tiles"]:
                assert _apart(a, t), f"an arrow touches a tile: {where}"
    _lined_up(page.evaluate(HEADER_JS), [FIRST, MIDDLE, LAST], (width, size))
    # The middle printer moves both ways, by mouse.
    page.locator(".fcc-ps-row").nth(1).locator("button.fcc-ps-reorder[data-dir='-1']").click()
    assert _order(page) == [MIDDLE, FIRST, LAST]
    page.locator(".fcc-ps-row").nth(0).locator("button.fcc-ps-reorder[data-dir='1']").click()
    page.locator(".fcc-ps-row").nth(1).locator("button.fcc-ps-reorder[data-dir='1']").click()
    assert _order(page) == [FIRST, LAST, MIDDLE]


def test_the_count_comes_back_on_the_info_line_after_a_repaint_and_a_reorder(widget):
    page = widget
    _feed(page)
    _reviews(page, {INDX: 3})
    # A heartbeat that changes a tile repaints the rows; the widget puts the
    # count back (window.cancelReviewDecorate) in its slot on the info line.
    _feed(page, {INDX: _printer("ZE", 8, loaded=(0, 3, 5)), XL: FLEET[XL]})
    head = page.evaluate(HEADER_JS)
    _name_then_info(head[INDX], INDX, "Standard")
    assert head[INDX]["chipText"] == "🛑 3" and head[XL]["chip"] is None, head
    _lined_up(head, [INDX, XL], "after a repaint")
    page.evaluate("(n) => window.movePrinterStatusRow(n, 1)", INDX)
    assert page.locator(".fcc-ps-row").first.get_attribute("data-printer") == XL
    head = page.evaluate(HEADER_JS)
    _name_then_info(head[INDX], INDX, "Standard")
    assert head[INDX]["chipText"] == "🛑 3", head
    _lined_up(head, [INDX, XL], "after a reorder")


# Names with characters an inline handler or an attribute could trip on:
# Derek's own kind ("Derek's XL"), and quotes, an ampersand, angle brackets
# and a backslash together.
APOS = "Derek's XL"
NASTY = 'ZZ O\'Brien & "Sons" <Co> \\ 2'


def test_a_printer_named_with_an_apostrophe_gets_its_count_and_moves(widget):
    """data-printer held the arrows' JS escape (Derek\\'s XL), so
    cancel_review.js, which matches it to a review's printer_name, never put
    a 🛑 N on such a printer's line (the collapsed strip, whose groups kept
    the plain name, did show it). It holds the plain name now, and the
    arrows' handlers take it as a JS string (SpoolCardBuilder.jsArg), so the
    arrows move the printer, by mouse and by Enter, whatever its name."""
    page = widget
    fleet = {APOS: _printer("ZQ", 5, "PRINTING", loaded=(1,)), INDX: FLEET[INDX], NASTY: _printer("ZN", 3, loaded=(0,))}
    _feed(page, fleet)
    _reviews(page, {APOS: 2, NASTY: 3})
    assert _order(page) == [APOS, INDX, NASTY]
    head = page.evaluate(HEADER_JS)
    assert (head[APOS]["chipText"], head[NASTY]["chipText"], head[INDX]["chipText"]) == ("🛑 2", "🛑 3", None), head
    for n in fleet:
        _name_then_info(head[n], n, "Standard")
        assert head[n]["text"] == n, head[n]
    # The collapsed strip: each group's count, its group keyed by the plain name too.
    page.evaluate("() => window.togglePrinterStatusWidget()")
    strip = page.evaluate("""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-header-chips .fcc-ps-printer-group'))
        .map((g) => [g.dataset.printer, (g.querySelector('.fcc-cr-chip') || {}).textContent || null])""")
    assert strip == [[APOS, "🛑 2"], [INDX, None], [NASTY, "🛑 3"]], strip
    page.evaluate("() => window.togglePrinterStatusWidget()")
    # The arrows, by mouse: Derek's XL down, then the other one up.
    page.locator(".fcc-ps-row").nth(0).locator("button.fcc-ps-reorder[data-dir='1']").click()
    assert _order(page) == [INDX, APOS, NASTY]
    page.locator(".fcc-ps-row").nth(2).locator("button.fcc-ps-reorder[data-dir='-1']").click()
    assert _order(page) == [INDX, NASTY, APOS]
    # By keyboard: Enter on the other one's focused ▲.
    page.locator(".fcc-ps-row").nth(1).locator("button.fcc-ps-reorder[data-dir='-1']").focus()
    page.keyboard.press("Enter")
    assert _order(page) == [NASTY, INDX, APOS]
    head = page.evaluate(HEADER_JS)
    assert (head[APOS]["chipText"], head[NASTY]["chipText"]) == ("🛑 2", "🛑 3"), head
    _lined_up(head, list(fleet), "after the moves")
    assert page.evaluate("window.__scans") == []


@pytest.mark.parametrize("width, size", [(412, "Standard"), (412, "Extra Large"), (1024, "Standard"),
                                         (1600, "Standard"), (1600, "Extra Large"), (390, "Standard")])
def test_a_60_character_name_neither_overlaps_nor_shifts_the_tiles(widget, width, size):
    """Derek: "if printer names go ungodly long for some reason, they don't
    clash or break the toolhead display". The name stays on one line (it ends
    in "…" where the line is too short for it, its full text in its title),
    and the info line, its badge and its count, and every tile sit exactly
    where they sit under a short name."""
    page = widget
    page.set_viewport_size({"width": width, "height": 1300})
    _size(page, size)
    tiles_js = """() => { const row = document.querySelector('#printer-status-widget .fcc-ps-row');
        const r0 = row.getBoundingClientRect();
        return Array.from(row.querySelectorAll('.fcc-ps-info, .fcc-ps-state, .fcc-cr-chip, .fcc-ps-th')).map((t) => {
            const r = t.getBoundingClientRect();
            return [t.className, Math.round((r.left - r0.left) * 100) / 100, Math.round((r.top - r0.top) * 100) / 100,
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
    assert after == before, f"the long name moved the info line or the tiles: {before} -> {after}"
    head = page.evaluate(HEADER_JS)
    _name_then_info(head[LONG_NAME], LONG_NAME, size)
    _lined_up(head, [LONG_NAME, XL], (width, size))
    h = head[LONG_NAME]
    assert h["text"] == LONG_NAME and h["chipText"] == "🛑 12", h
    # Where the line is short the name is cut; the info line never is.
    if width in (390, 412):
        assert h["cut"], f"the name should end in … on a phone: {h}"
    got = _layout(page)
    _placed(got[LONG_NAME], (width, size, LONG_NAME))
    _tiles_lined_up(got, (width, size))


# Counts where a plain grid fill is uneven: where three tiles fit on a line it
# draws 3 + 3 + 1 and 3 + 3 + 3 + 1. Only each row's first tile starting in
# column 1 draws what the rule says (review, 2026-10-22: the 8, 5, 3 and 2
# heads every other check uses come out the same either way).
UNEVEN = {"ZZ Seven": _printer("ZS", 7, loaded=(0,)), "ZZ Ten": _printer("ZT", 10, loaded=(1,)),
          "ZZ Thirteen": _printer("ZH", 13)}


@pytest.mark.parametrize("width, size", [(700, "Standard"), (900, "Extra Large")])
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


@pytest.mark.parametrize("style, width, fleet, plain, counted, want, where", [
    # 1307 px: seven tiles fit under the name with a px to spare (1225 px for
    # 1224); with a margin the sums don't count, the seventh doesn't.
    (".fcc-ps-th { margin-right: 2px; }", 1307, SEVEN, "7", 7, "4+3", "under"),
    # 440 px: two tiles fit on a line under the name (358 px), but not with a
    # 40 px margin each: one a line, under the name.
    (".fcc-ps-th { margin-right: 40px; }", 440, FOUR, "2+2", 2, "1+1+1+1", "under"),
    # 412 px: two fit across the row from its edge (356 px), one under the
    # name (330 px); with the margin one a line, back under the name.
    (".fcc-ps-th { margin-right: 40px; }", 412, FOUR, "2+2", 2, "1+1+1+1", "under"),
    # 380 px with the arrows' column 12rem wide: two fit across the row (348
    # px), none under the name; with the margin one a line, still from the
    # edge.
    (".fcc-ps-reorder-stack { width: 12rem; } .fcc-ps-th { margin-right: 40px; }", 380, FOUR, "2+2", 2, "1+1+1+1",
     "atEdge"),
])
def test_what_the_browser_drew_is_checked(widget, style, width, fleet, plain, counted, want, where):
    """The sums can't know every style (or every rounding: the 110 % display
    scale below), so the layout checks what the browser drew: a line of tiles
    wider than its area is laid out again with one tile fewer per line. The
    measure's own count stays what it counted (data-fit), so it is the check
    that put the rows right here. One a line goes back under the name where
    one fits there, and stays at the edge where none does."""
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _feed(page, fleet)
    (name,) = fleet
    assert _layout(page)[name]["rows"] == plain        # without the margin
    page.add_style_tag(content=style)
    page.evaluate("() => window.balancePrinterStatusRows()")
    got = _layout(page)[name]
    assert (got["rows"], got["out"], got["fit"], got[where], got["below"]) == (want, 0, counted, True, True), got


# --- a display scale of 110 % (Windows' display scaling, or a browser zoom) -----
# A CSS px is 1.1 device px, so the page's widths are fractions of a px: at a
# 601 px window the tile area under the name is 519.84 px wide and
# clientWidth says 520, exactly what three tiles need (at 1481 px: 1399.84,
# and eight need 1400). Whole px count one tile more than fits (review,
# 2026-10-22). The drawn check would put such a count right afterwards (one
# relayout), so the rows alone can't tell a measure that counted right from
# one that didn't: data-fit, the measure's own count, can (review,
# 2026-10-23, F4).
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
    (601, 4, {4: "2+2", 5: "2+2+1", 7: "2+2+2+1", 8: "2+2+2+2", 10: "2+2+2+2+2"}),
    (1481, 7, {4: "4", 5: "5", 7: "7", 8: "4+4", 10: "5+5"}),
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
    assert _stepped(page, "back at 1600")
    # Down to a 390 px phone: two a line from the row's edge, no step; Large
    # there is one a line, under the name (two don't fit from the edge either).
    page.set_viewport_size({"width": 390, "height": 900})
    _settled(page, {INDX: "2+2+2+2", XL: "2+2+1"})
    assert all(v["edge"] and v["atEdge"] for v in _layout(page).values())
    assert not _stepped(page, 390)
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
    # By keyboard too: the first printer's ▼ (its only arrow), Enter, through
    # the dashboard's own accumulator.
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
    head = page.evaluate(HEADER_JS)
    for n in (INDX, XL):
        _name_then_info(head[n], n, "Extra Large")


# --- the arrows by keyboard (review, 2026-10-23, F3) -----------------------------

FOCUS_JS = r"""() => { const a = document.activeElement; const row = a && a.closest ? a.closest('.fcc-ps-row') : null;
    return { tag: a ? a.tagName : null, dir: a && a.getAttribute ? a.getAttribute('data-dir') : null,
             printer: row ? row.dataset.printer : null }; }"""


def test_the_arrows_have_no_enter_handler_of_their_own():
    """Group 50.6: the accumulator presses a focused button on a person's
    Enter, so the arrows' own Enter handler (2026-10-23 review) went. The
    Enter tests below pass only through the real accumulator."""
    src = (MODULES / "inv_printer_status.js").read_text(encoding="utf-8")
    assert "closest('button.fcc-ps-reorder')" not in src


def test_enter_on_a_focused_arrow_moves_its_printer_and_keeps_the_focus(widget):
    """Enter on a focused ▲ / ▼ moves the printer, as a click does, through the
    dashboard's own accumulator (it did nothing there before the 2026-10-23
    review: only Space moved a printer). The rows are drawn again, and the focus stays on
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

# The open body, its scroll height against its limit, and how many tiles show
# whole in it before and after it is scrolled to its end.
BODY_JS = r"""() => { const body = document.querySelector('#printer-status-widget .fcc-ps-body');
    const shown = () => { const b = body.getBoundingClientRect();
        return Array.from(body.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect())
            .filter((r) => r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5).length; };
    const top = shown(); body.scrollTop = body.scrollHeight; const end = shown(); body.scrollTop = 0;
    return { shown: top, atEnd: end, tiles: body.querySelectorAll('.fcc-ps-th').length,
             sh: body.scrollHeight, ch: body.clientHeight, maxH: parseFloat(getComputedStyle(body).maxHeight),
             vh: innerHeight, root: parseFloat(getComputedStyle(document.documentElement).fontSize) }; }"""


# Dev's two printers as their tiles stand (2026-10-24): the INDX's 8 heads
# without a spool (a tile with no material line, 72 px tall at Standard) and
# the XL's 5 with two loaded (87 px: the material line), so the open widget
# is as tall here as on dev (353, 358 and 383 px at Small, Standard and
# Large). FLEET's INDX has spools in its first row, 14 px taller.
DEV_LIKE = {INDX: _printer("RCOI", 8), XL: _printer("XL", 5, loaded=(3, 4))}


@pytest.mark.parametrize("width, height, size, whole", [(1280, 800, "Small", True), (1280, 800, "Standard", True),
                                                        (1280, 800, "Large", False), (1366, 768, "Small", False),
                                                        (1366, 768, "Standard", False)])
def test_on_a_short_laptop_window_every_tile_shows_or_scrolls_into_view(widget, width, height, size, whole):
    """Each printer's name on its own line made the open widget taller, and
    at 1280 x 800 (a Framework 12 at 150 %) or 1366 x 768 the body's limit,
    then 40 % of the window, hid the second printer's tiles under its fold (8
    of 13 showed). The limit is 45 % now, with no gap between printers (the
    rows' padding puts the divider half way). The info line under each name
    (2026-10-24) adds a line per printer: at 1280 x 800 at Small and
    Standard dev's two printers (8 and 5 heads) still show whole and the body
    doesn't scroll; at 1280 x 800 at Large and 1366 x 768 at Small and
    Standard they are taller than the body may be, so it stops at its limit
    (the deck and a 7rem strip of the log and the buffer keep their room) and
    scrolls inside itself, every tile showing once scrolled to. The rows are
    the same either way: 4 + 4 and 5."""
    page = widget
    page.set_viewport_size({"width": width, "height": height})
    _size(page, size)
    _feed(page, DEV_LIKE)
    got = page.evaluate(BODY_JS)
    assert got["tiles"] == 13 and got["ch"] <= got["maxH"] + 0.5, got
    # The limit: 45 % of the window, or what the deck (260 px with the title
    # bar) and the 10.5rem the widget's header and the 7rem strip need leave.
    assert got["maxH"] == pytest.approx(min(0.45 * got["vh"], max(5 * got["root"], got["vh"] - 260 - 10.5 * got["root"])),
                                        abs=0.5), got
    if whole:
        assert got["shown"] == 13 and got["sh"] <= got["ch"] + 1, (width, height, size, got)
    else:
        # It may scroll: the first printer's tiles show whole without
        # scrolling, and scrolled to its end the second printer's do.
        whole_rows = page.evaluate("""() => { const body = document.querySelector('#printer-status-widget .fcc-ps-body');
            const b = body.getBoundingClientRect();
            return Array.from(body.querySelectorAll('.fcc-ps-row')).map((row) => Array.from(row.querySelectorAll('.fcc-ps-th'))
                .every((t) => { const r = t.getBoundingClientRect(); return r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5; })); }""")
        assert whole_rows[0] and got["shown"] >= 8 and got["atEnd"] >= 5, (width, height, size, got, whole_rows)
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "5")


# --- the collapsed strip (review, 2026-10-23, F5) ----------------------------------

# Per printer group of the folded strip (Group 50.1): its parts in order, their
# edges against the window, its 🛑 count's text and how many lines it takes, its
# heads (a box that scrolls sideways when they don't fit), and the page's
# sideways scroll.
STRIP_JS = r"""() => ({ iw: innerWidth, sw: document.documentElement.scrollWidth,
    groups: Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-header-chips .fcc-ps-printer-group')).map((g) => {
        const kids = Array.from(g.children); const chip = g.querySelector('.fcc-cr-chip');
        const box = g.querySelector('.fcc-ps-strip-heads');
        const lines = (el) => { const r = document.createRange(); r.selectNodeContents(el);
            const tops = []; Array.from(r.getClientRects()).filter((x) => x.width > 0).forEach((x) => {
                if (!tops.some((t) => Math.abs(t - x.top) < 3)) tops.push(x.top); }); return tops.length; };
        return { printer: g.dataset.printer, parts: kids.map((k) => k.className),
                 right: Math.max(...kids.map((k) => k.getBoundingClientRect().right)),
                 left: Math.min(...kids.map((k) => k.getBoundingClientRect().left)),
                 count: chip ? chip.textContent : null, countLines: chip ? lines(chip) : 0,
                 heads: box ? box.querySelectorAll('.fcc-ps-strip-head').length : 0,
                 scrolls: !!box && box.scrollWidth > box.clientWidth + 1 }; }) })"""


# Dev's own head ids (RCOI-1 .. RCOI-8, XL-1 .. XL-5): the strip's heads are as
# wide as dev's.
STRIP_FLEET = {INDX: _printer("RCOI", 8, loaded=(0, 3)), XL: _printer("XL", 5, "PRINTING", loaded=(1, 2))}
STRIP_PARTS = ["fcc-ps-strip-name", "fcc-ps-strip-state", "fcc-ps-strip-count", "fcc-ps-strip-heads"]


@pytest.mark.parametrize("width, size", [(1024, "Small"), (1024, "Standard"), (1024, "Large"), (1024, "Extra Large"),
                                         (1280, "Extra Large"), (412, "Standard"), (390, "Standard")])
def test_the_collapsed_strip_keeps_every_chip_on_screen(widget, width, size):
    """The strip is all a minimized widget shows (Derek, 2026-06-12: the 🛑
    count rides on it "in case the activity log isn't always visible"). A
    printer's group wider than the window ran off its right edge, taking its
    last heads and its 🛑 count with it (the INDX's 8 heads at 1024 px at every
    size, at 1280 px at Extra Large, and on a phone).

    PIN UPDATED DELIBERATELY (Group 50.1, 2026-10-29): each printer is now its
    name, its state, its 🛑 count and then its heads (it was the state, the
    heads, then the count), and a printer whose heads don't fit even on a line
    of their own scrolls them sideways inside their own box (Derek's fallback,
    2026-10-19) instead of wrapping them. Still: every part inside the window,
    the page never scrolls sideways, the 🛑 never parted from its number."""
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
    assert [(g["printer"], g["parts"], g["heads"], g["count"], g["countLines"]) for g in got["groups"]] == [
        (INDX, STRIP_PARTS, 8, "🛑 3", 1), (XL, STRIP_PARTS, 5, "🛑 12", 1)], got
    for g in got["groups"]:
        assert g["left"] >= -0.5 and g["right"] <= got["iw"] + 0.5, f"a part is off the screen: {width} {size} {g}"
    # On a phone the INDX's eight heads don't fit beside its name: they scroll.
    if width <= 412:
        assert got["groups"][0]["scrolls"], got


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
