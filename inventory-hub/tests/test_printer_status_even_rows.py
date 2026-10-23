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
    more fit there (or all of them); under it only when fewer fit and that
    takes fewer rows of tiles (or none fit beside it); a row of one tile only
    where at most two fit across the row and the count is odd;
  - the layout: on Derek's 1600 x 1300 window the 8 heads are 4 + 4 and the 5
    stay one row, beside the name, at every Text size; narrower windows split
    as the rule says (1024: 4 + 4 and 3 + 2, or 3 + 3 + 2 at Extra Large; 800
    at Extra Large and a 412 px phone: under the name); every row's tiles fit
    the row (nothing sticks out);
  - every layout check also holds what was drawn to what the layout recorded
    (data-rows, data-place), so CSS that draws other lines can't pass;
  - 7, 10 and 13 heads where three fit beside the name are 3 + 2 + 2,
    3 + 3 + 2 + 2 and 3 + 3 + 3 + 2 + 2: each row starts in the first column
    (a plain grid fill is 3 + 3 + 1);
  - 4 heads with room for two beside the name stay beside it as 2 + 2 (600 px
    at Small and Standard, 800 px at Large and Extra Large), while 8 and 5 take
    fewer rows under it;
  - what the browser drew is checked: with a margin the sums don't count, a
    row planned beside the name that wrapped under it, or a line of tiles
    wider than its row, is laid out again with one tile fewer per line;
  - at a 110 % display scale (a real device scale factor: the row is 911.65 or
    1439.83 px, which clientWidth calls 912 or 1440), the tiles counted beside
    the name are the ones that fit (its own private chromium, as cut off as
    `isolated_page`'s);
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

Review proof (2026-10-22, c5c9d1f, this file alone in a copy of that commit):
11 RED: the rule for 4 heads with two beside (2 + 2 under the name) and 5
with two across, the rule sweep, the 4 heads drawn under the name at all four
widths, both drawn-checks (7 wrapped under the name while the layout said
beside; two tiles sticking out of the row), and at 110 % the 4, 7, 8 and 10 heads
drawn under the name while the layout said beside (and the 7 at 1471 px). And
with the line that starts each row in column 1 deleted from today's code: 3
RED (the 7 / 10 / 13 heads drawn 3 + 3 + 1, 3 + 3 + 3 + 1, 3 + 3 + 3 + 3 + 1
against a recorded 3 + 2 + 2 ...); every other check passed there, as it
did for the review.
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
# the name), whether any tile or row sticks out of the printer's row, and what
# the layout recorded (data-rows, data-place).
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
        const heads = row.querySelector('.fcc-ps-toolheads');
        out[name] = { rows: lines.map((l) => l.n).join('+'), place: beside ? 'beside' : (below ? 'below' : 'mixed'),
                      out: tiles.filter((r) => r.right > rowR.right + 0.5 || r.left < rowR.left - 0.5).length,
                      data: (heads.dataset.rows || null), dataPlace: (heads.dataset.place || null) };
    });
    return out;
}"""


def _drawn_as_recorded(got):
    """Every printer's tiles as the layout recorded them (review, 2026-10-22):
    the lines drawn are data-rows and they sit where data-place says. A layout
    whose CSS drew something else (rows not started in column 1, so 3 + 3 + 1
    for a planned 3 + 2 + 2, or tiles that wrapped under the name while the
    plan said beside) passed every check that only compared fixed strings."""
    wrong = {k: v for k, v in got.items() if (v["rows"], v["place"]) != (v["data"], v["dataPlace"])}
    assert not wrong, f"drawn differently from what the layout recorded: {wrong}"
    return got


def _build(page):
    """The widget's page: the real CSS and modules, a Bootstrap stand-in."""
    page.set_content(PAGE.format(standin=BOOTSTRAP_STANDIN, css=GLOBAL_CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("inv_core.js", "ui_builder.js", "inv_printer_status.js", "text_size.js"):
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


def _layout(page):
    return _drawn_as_recorded(page.evaluate(LAYOUT_JS))


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
    (8, 2, 3, ("below", [3, 3, 2])),     # under three beside: under the name, when that saves rows
    (5, 2, 3, ("below", [3, 2])),
    (7, 2, 3, ("below", [3, 2, 2])),
    (3, 2, 3, ("below", [3])),
    (4, 2, 3, ("beside", [2, 2])),       # 2 + 2 either way: beside, no line for the name alone
    (4, 2, 4, ("below", [4])),           # one row under the name beats two beside it
    (5, 2, 2, ("beside", [2, 2, 1])),    # 2 + 2 + 1 either way
    (4, 1, 3, ("below", [2, 2])),
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
    at most one, the longer first, as few as fit, and none holds a lone tile.
    The tiles go under the name only when fewer than three fit beside it, and
    then only when that takes fewer rows (or none fit beside it)."""
    bad = widget.evaluate("""() => {
        const bad = [];
        for (let n = 1; n <= 16; n++) for (let side = 0; side <= 12; side++) for (let full = Math.max(side, 3); full <= 14; full++) {
            const r = window.fccPrinterStatusTileRows(n, side, full);
            const per = r.below ? full : side;
            const under = !(side >= n || side >= 3) && (side === 0 || Math.ceil(n / full) < Math.ceil(n / side));
            const ok = r.sizes.reduce((a, b) => a + b, 0) === n && r.rows === Math.ceil(n / per)
                && r.sizes.every((s, i) => i === 0 || (s <= r.sizes[i - 1] && r.sizes[0] - s <= 1))
                && !(r.rows > 1 && r.sizes.includes(1)) && r.below === under;
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
    assert got[INDX] == {"rows": "4+4", "place": "beside", "out": 0, "data": "4+4", "dataPlace": "beside"}, (size, got)
    assert got[XL] == {"rows": "5", "place": "beside", "out": 0, "data": "5", "dataPlace": "beside"}, (size, got)


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


# Counts where a plain grid fill is uneven: at a width where three tiles fit
# beside the name it draws 3 + 3 + 1 and 3 + 3 + 3 + 1. Only each row's first
# tile starting in column 1 draws what the rule says (review, 2026-10-22: the
# 8, 5, 3 and 2 heads every other check uses come out the same either way).
UNEVEN = {"ZZ Seven": _printer("ZS", 7, loaded=(0,)), "ZZ Ten": _printer("ZT", 10, loaded=(1,)),
          "ZZ Thirteen": _printer("ZH", 13)}


@pytest.mark.parametrize("width, size", [(800, "Standard"), (1024, "Extra Large")])
def test_each_row_of_tiles_starts_in_the_first_column(widget, width, size):
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _size(page, size)
    _feed(page, UNEVEN)
    got = _layout(page)
    assert {k: (v["rows"], v["place"], v["out"]) for k, v in got.items()} == {
        "ZZ Seven": ("3+2+2", "beside", 0), "ZZ Ten": ("3+3+2+2", "beside", 0),
        "ZZ Thirteen": ("3+3+3+2+2", "beside", 0)}, (width, size, got)
    # Every line starts under the first tile.
    starts = page.evaluate("""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row')).map((row) => {
        const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
        return tiles.filter((r, i) => i === 0 || Math.abs(r.top - tiles[i - 1].top) >= 2).map((r) => Math.round(r.left)); })""")
    assert all(len(set(s)) == 1 for s in starts), starts


# Derek's rule puts the tiles under the name only where that takes fewer rows
# (review, 2026-10-22): 4 heads with room for two beside the name were drawn
# 2 + 2 under it, the same 2 + 2 plus a line for the name.
FOURS = {"ZZ Four": _printer("ZF", 4, loaded=(0,)), INDX: _printer("ZE", 8, loaded=(0, 3)),
         "ZZ Five": _printer("ZV", 5)}


@pytest.mark.parametrize("width, size", [(600, "Small"), (600, "Standard"), (800, "Large"), (800, "Extra Large")])
def test_four_heads_with_room_for_two_beside_the_name_stay_beside_it(widget, width, size):
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    _size(page, size)
    _feed(page, FOURS)
    got = _layout(page)
    # Two fit beside the name and three across the row: 4 stays beside it as
    # 2 + 2; 8 and 5 take fewer rows under it (3 + 3 + 2 and 3 + 2).
    assert {k: (v["rows"], v["place"], v["out"]) for k, v in got.items()} == {
        "ZZ Four": ("2+2", "beside", 0), INDX: ("3+3+2", "below", 0), "ZZ Five": ("3+2", "below", 0)}, (width, size, got)


SEVEN = {"ZZ Seven": _printer("ZS", 7)}
FOUR = {"ZZ Four": _printer("ZF", 4)}


@pytest.mark.parametrize("style, width, fleet, want", [
    # 1472 px: seven tiles fill the row beside the name to the px; with a
    # margin the sums don't count, the seventh doesn't fit.
    (".fcc-ps-name-col { margin-right: 2px; }", 1472, SEVEN, {"ZZ Seven": ("4+3", "beside")}),
    # 412 px: two tiles fit across the row under the name, but not with a
    # 40 px margin each.
    (".fcc-ps-th { margin-right: 40px; }", 412, FOUR, {"ZZ Four": ("1+1+1+1", "below")}),
])
def test_what_the_browser_drew_is_checked(widget, style, width, fleet, want):
    """The sums can't know every style (or every rounding: the 110 % display
    scale below), so the layout checks what the browser drew: tiles planned
    beside the name that wrapped under it, or a line of tiles wider than its
    row, are laid out again with one tile fewer per line."""
    page = widget
    page.set_viewport_size({"width": width, "height": 900})
    page.add_style_tag(content=style)
    _feed(page, fleet)
    got = _layout(page)
    assert {k: (v["rows"], v["place"], v["out"]) for k, v in got.items()} == \
        {k: v + (0,) for k, v in want.items()}, got


# --- a display scale of 110 % (Windows' display scaling, or a browser zoom) -----
# A CSS px is 1.1 device px, so the page's widths are fractions of a px: at a
# 943 px window the row is 911.65 px wide and clientWidth says 912, exactly
# what four tiles need beside the name (at 1471 px: 1439.83, and seven need
# 1440). Whole px counted one tile more than fits, so the tiles wrapped under
# the name while the layout said beside (review, 2026-10-22).
TRAP_FLEET = {f"ZZ {n:02d} heads": _printer(f"Z{n}", n) for n in (4, 5, 7, 8, 10)}

# What whole px and the fraction count beside the name, for the row of `n`.
TRAP_JS = r"""(n) => {
    const row = Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row'))
        .find((r) => r.querySelectorAll('.fcc-ps-th').length === n);
    const rs = getComputedStyle(row);
    const gap = parseFloat(getComputedStyle(row.querySelector('.fcc-ps-toolheads')).columnGap);
    const tileW = row.querySelector('.fcc-ps-th').getBoundingClientRect().width;
    const nameW = row.querySelector('.fcc-ps-name-col').getBoundingClientRect().width + parseFloat(rs.columnGap);
    const count = (w, slack) => Math.floor((w - nameW + gap + slack) / (tileW + gap));
    const rect = row.getBoundingClientRect().width;
    return { clientWidth: row.clientWidth, width: rect, whole: count(row.clientWidth, 0.5), fraction: count(rect, 0) };
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


@pytest.mark.parametrize("window, want", [
    (943, {4: "2+2", 5: "3+2", 7: "3+2+2", 8: "3+3+2", 10: "3+3+2+2"}),
    (1471, {4: "4", 5: "5", 7: "4+3", 8: "4+4", 10: "5+5"}),
])
def test_at_a_110_percent_display_scale_it_counts_what_really_fits(scaled_chromium, window, want):
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
        # The trap is set: whole px count one tile more beside the name than fits.
        trap = page.evaluate(TRAP_JS, 4 if window == 943 else 7)
        assert trap["whole"] == trap["fraction"] + 1 and trap["width"] < trap["clientWidth"], (
            f"a {window} px window no longer lands where whole px count a tile too many; pick another: {trap}")
        got = _layout(page)
        assert {k: (v["rows"], v["place"], v["out"]) for k, v in got.items()} == \
            {f"ZZ {n:02d} heads": (rows, "beside", 0) for n, rows in want.items()}, (window, got)
        assert page.evaluate("window.__errors") == []
    finally:
        context.close()


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
