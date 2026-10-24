"""Printer Status on the real page: each printer's name on a header line, its
tiles under the name in even rows (Derek, 2026-10-22 and 2026-10-23).

2026-10-22: split a printer's heads into the fewest rows with EQUAL counts
(8 -> 4 + 4, 7 -> 4 + 3, 10 -> 5 + 5; never a lone tile), re-balanced on a
resize and on a Text size change. 2026-10-23, Derek's pick of the three
name-column styles: "name on top of tool heads ... indent in the toolheads
more so that they read as a sub thing of the printer name. We also avoid the
word wrap effect on the red notification dot about pending reviews ... if
printer names go ungodly long for some reason, they don't clash or break the
toolhead display."

The dev container's real page (Bootstrap, the heartbeat, cancel_review.js's
own poll, the scan accumulator, the Settings path for the size) with a
made-up fleet in every source the widget reads (conftest.stub_printer_fleet):
an INDX-like printer with 8 heads and an XL-like one with 5, as dev has, and
made-up pending reviews for them (the 🛑 N count). Pinned:
  - on Derek's 1600 x 1300 window, at each Text size: the 8 heads are one row
    at Small and Standard and 4 + 4 at Large and Extra Large, the 5 one row,
    every tile under the header line and every line under the name's first
    letter, nothing out of the row; the header (the ▲▼ arrow, the name, the
    state badge, the 🛑 N count) on one line, the count after the badge, its
    dot and number together;
  - 390, 412, 1024 and 1366 px at Standard and Extra Large, the same checks;
    on a 390 px phone at Standard (an iPhone 12 to 16) the tiles start at the
    row's edge, two to a line (review, 2026-10-23, F1: one a line before);
  - a Text size picked in Settings lays the rows out again at once, and a
    resize does too;
  - collapsing and opening the widget, the ▲▼ reorder and a heartbeat that
    repaints keep the rows even and the count on the header line; the
    collapsed strip still leads each printer with its state and ends with its
    count, 6 px from its last chip;
  - the collapsed strip keeps every chip inside the window at 1024 px, at
    1280 px at Extra Large and on a phone (F5: the INDX's last heads and its
    🛑 count ran off the right edge): a group wraps its own chips;
  - Enter on a focused ▲ / ▼ moves the printer, past the dashboard's own scan
    accumulator, which cancels every Enter outside a text field (F3: Enter did
    nothing there), the focus staying on the moved printer's arrow; a scan
    typed onto a focused arrow still reaches processScan; a mouse click lets
    the focus go, as before;
  - on a 1280 x 800 laptop (a Framework 12 at 150 %) at Small, Standard and
    Large, and 1366 x 768 at Small and Standard, both printers' 13 tiles show
    whole in the open widget, with the deck and a 7rem strip of the log and
    the buffer still on screen (F2: 8 of 13 showed);
  - a printer between two others has the same header line as they do, its
    arrows clear of the divider and of the tiles (F6: 6.6 px taller);
  - 7 and 10 heads where three fit on a line are 3 + 2 + 2 and 3 + 3 + 2 + 2,
    each line starting under the name;
  - a 60-character printer name keeps the header on one line (ending in "…"
    on a phone, its full text in its title) and leaves every tile where it is
    under a short name, at 412 and 1600 px;
  - the material line is 1.2 high at Large, inside its tile.
Every layout check holds the lines drawn to the ones the layout recorded
(data-rows). The rule itself and the 110 % display scale are
test_printer_status_even_rows.py (hermetic, under --offline).

READ-ONLY: every request that isn't a read is answered in the browser, and
the widget's sources answer the made-up fleet in this page only.

RED before the fixes: with b49b263's global.css, inv_printer_status.js and
cancel_review.js served to this file's pages by a local pass-through proxy
(INVENTORY_HUB_URL; nothing on disk changed), 15 of 34: the 390 px phone at
one tile a line (F1), the 1280 x 800 and 1366 x 768 windows hiding the XL's
tiles (F2, 5), Enter on a focused arrow cancelled by the accumulator (F3),
the collapsed strip off the screen (F5, 6), the middle printer's header line
taller at 1600 and 390 px (F6, 2). The scan typed onto a focused arrow and
the mouse click letting the focus go hold there: guards for what the fix
must not change. On 234f41a (its three files on disk for one run, restored
after), the 2026-10-23 version of this file was 15 of 16 red: the tiles
beside a 12.5rem name column, the 🛑 N count inside the name with the badge
under it, the 60-character name pushing the tiles down.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page

from conftest import stub_printer_fleet
from test_printer_status_even_rows import (ARROWS_JS, FOCUS_JS, HEADER_JS, LAYOUT_JS, LONG_NAME, ROOT_PX, STRIP_JS,
                                           _drawn_as_recorded, _one_header_line, _placed)
from test_text_size_guard import _read_only

pytestmark = pytest.mark.usefixtures("require_server")

KEY = "fcc.textSize"
INDX = "ZZ Even INDX"
XL = "ZZ Even XL"
REVIEWS = {INDX: 3, XL: 1}


def _item(sid, material, grams=640):
    return {"id": sid, "color": "2A6F97", "color_direction": "longitudinal", "remaining_weight": grams,
            "initial_weight": 1000, "display": f"#{sid} Even Test {material}", "details": {"material": material}}


def _indx(state="IDLE", prefix="ZE", bound=(1, 4)):
    return {"state": {"state": state, "is_active": state == "PRINTING"},
            "heads": [(f"{prefix}-{i}", i in bound,
                       _item(9300 + i, "Polycarbonate" if i == 1 else "PETG") if i in (1, 4) else None)
                      for i in range(1, 9)]}


def _xl(prefix="ZX"):
    return {"state": {"state": "PRINTING", "is_active": True},
            "heads": [(f"{prefix}-{i}", True, _item(9310 + i, "PETG") if i == 2 else None) for i in range(1, 6)]}


FLEET = {INDX: _indx(), XL: _xl()}
# Dev's own head ids (RCOI-1 .. RCOI-8, XL-1 .. XL-5), every head bound to a
# box slot (an empty one reads "empty" in the collapsed strip, the widest
# chip), so the strip's chips are as wide as they get on dev.
DEV_IDS = {INDX: _indx(prefix="RCOI", bound=range(1, 9)), XL: _xl(prefix="XL")}


def _store(page: Page, name: str):
    page.add_init_script("(() => { try { localStorage.setItem(%r, %r); } catch (e) {} })();" % (KEY, name))


def _pending(page: Page, counts: dict):
    """cancel_review.js's poll answers `counts` reviews per printer (this page
    only; registered last, so it answers before the read-only route)."""
    body = json.dumps({"pending": [{"printer_name": name, "job_id": f"{name}#{i}", "kind": "cancel"}
                                   for name, n in counts.items() for i in range(n)]})
    page.route("**/api/cancel_deduct/pending*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=body))


def _open(page: Page, base_url: str, size: str = "Standard", width: int = 1600, height: int = 1300, fleet=None,
          reviews=None, order=None, collapsed=False):
    fleet = fleet or FLEET
    reviews = REVIEWS if reviews is None else reviews
    _read_only(page)
    stub_printer_fleet(page, fleet)
    _pending(page, reviews)
    _store(page, size)
    if order is not None:
        page.add_init_script("(() => { try { localStorage.setItem('fcc.printerStatus.order', %r); } catch (e) {} })();"
                             % json.dumps(order))
    if collapsed:
        page.add_init_script("(() => { try { localStorage.setItem('fcc.printerStatus.collapsed', '1'); } catch (e) {} })();")
    page.set_viewport_size({"width": width, "height": height})
    page.goto(base_url, wait_until="domcontentloaded")
    where = '.fcc-ps-header-chips' if collapsed else '.fcc-ps-body'
    page.wait_for_function("([n, c, where]) => typeof state !== 'undefined' && state.locationsLoaded"
                           " && document.querySelectorAll('#printer-status-widget .fcc-ps-row').length === n"
                           " && document.querySelectorAll('#printer-status-widget ' + where + ' .fcc-cr-chip').length === c",
                           arg=[len(fleet), sum(1 for n in reviews.values() if n), where], timeout=45_000)
    page.wait_for_timeout(800)


def _layout(page: Page):
    return _drawn_as_recorded(page.evaluate(LAYOUT_JS))


def _settled(page: Page, want: dict):
    """Wait for {printer: rows}: a resize lays the rows out on the next frame."""
    page.wait_for_function("""([js, want]) => { const got = (eval(js))();
        return Object.entries(want).every(([k, v]) => got[k] && got[k].rows === v); }""",
                           arg=[LAYOUT_JS, want], timeout=5000)


def _all_placed(got: dict, size: str, where):
    """Every printer's tiles under the header line, under the name's first
    letter (or, on a phone, from the row's edge), the name a step in."""
    for name, g in got.items():
        _placed(g, (where, name))
        assert g["indent"] == pytest.approx(1.625 * ROOT_PX[size], abs=0.05), (where, name, g)


def _headers(page: Page, size: str, counts: dict = REVIEWS):
    head = page.evaluate(HEADER_JS)
    for name, h in head.items():
        _one_header_line(h, name, size)
        assert h["chipText"] == (f"🛑 {counts[name]}" if counts.get(name) else None), (name, h)
    return head


def _order(page: Page):
    return [r.get_attribute("data-printer") for r in page.locator("#printer-status-widget .fcc-ps-row").all()]


@pytest.mark.parametrize("size", ["Small", "Standard", "Large", "Extra Large"])
def test_on_derek_s_window_each_printer_s_tiles_sit_under_its_name(page: Page, base_url: str, size):
    _open(page, base_url, size)
    got = _layout(page)
    one_row = size in ("Small", "Standard")
    assert (got[INDX]["rows"], got[XL]["rows"]) == ("8" if one_row else "4+4", "5"), (size, got)
    assert not got[INDX]["edge"] and not got[XL]["edge"], got
    _all_placed(got, size, size)
    _headers(page, size)


@pytest.mark.parametrize("width, size, indx, xl, edge", [
    (390, "Standard", "2+2+2+2", "2+2+1", True),
    (390, "Extra Large", "1+1+1+1+1+1+1+1", "1+1+1+1+1", False),
    (412, "Standard", "2+2+2+2", "2+2+1", False),
    (412, "Extra Large", "1+1+1+1+1+1+1+1", "1+1+1+1+1", False),
    (1024, "Standard", "4+4", "5", False),
    (1024, "Extra Large", "4+4", "3+2", False),
    (1366, "Standard", "4+4", "5", False),
    (1366, "Extra Large", "4+4", "5", False),
])
def test_narrower_windows_keep_the_header_and_even_rows(page: Page, base_url: str, width, size, indx, xl, edge):
    _open(page, base_url, size, width, 900)
    got = _layout(page)
    assert (got[INDX]["rows"], got[XL]["rows"], got[INDX]["edge"], got[XL]["edge"]) == (indx, xl, edge, edge), (
        width, size, got)
    _all_placed(got, size, (width, size))
    _headers(page, size)


def test_a_size_picked_in_settings_and_a_resize_lay_the_rows_out_again(page: Page, base_url: str):
    _open(page, base_url, "Standard", 1024, 900)
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "5")
    page.evaluate("() => window.openConfigModal()")
    sel = page.locator('.cfgset-input[data-key="fcc.textSize"]')
    sel.wait_for(state="visible", timeout=15_000)
    sel.select_option("Extra Large")
    page.wait_for_function("() => document.documentElement.getAttribute('data-fcc-text-size') === 'xlarge'",
                           timeout=3000)
    _settled(page, {INDX: "4+4", XL: "3+2"})
    page.keyboard.press("Escape")
    page.set_viewport_size({"width": 1600, "height": 1300})
    _settled(page, {INDX: "4+4", XL: "5"})
    page.set_viewport_size({"width": 800, "height": 1100})
    _settled(page, {INDX: "3+3+2", XL: "3+2"})
    _all_placed(_layout(page), "Extra Large", 800)


COLLAPSED_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-header-chips .fcc-ps-printer-group'))
    .map((g) => { const kids = Array.from(g.children); const chip = g.querySelector('.fcc-cr-chip');
        const tops = chip ? new Set(Array.from((() => { const r = document.createRange(); r.selectNodeContents(chip);
            return r.getClientRects(); })()).filter((x) => x.width > 0).map((x) => Math.round(x.top))) : new Set();
        return { printer: g.dataset.printer, first: kids[0] && kids[0].classList.contains('fcc-ps-state-chip'),
                 last: chip ? kids[kids.length - 1] === chip : null, text: chip ? chip.textContent : null,
                 margin: chip ? getComputedStyle(chip).marginLeft : null, lines: tops.size }; })"""


def test_collapse_reorder_and_a_repaint_keep_the_rows_even(page: Page, base_url: str):
    _open(page, base_url)
    page.evaluate("() => window.togglePrinterStatusWidget()")
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    # The collapsed strip as it was: each printer's state first, its 🛑 N last,
    # 6 px from its last chip, on one line.
    strip = page.evaluate(COLLAPSED_JS)
    assert [(s["printer"], s["first"], s["last"], s["text"], s["margin"], s["lines"]) for s in strip] == [
        (INDX, True, True, "🛑 3", "6px", 1), (XL, True, True, "🛑 1", "6px", 1)], strip
    page.set_viewport_size({"width": 1024, "height": 900})
    page.evaluate("() => window.togglePrinterStatusWidget()")
    _settled(page, {INDX: "4+4", XL: "5"})
    first = page.locator("#printer-status-widget .fcc-ps-row").first.get_attribute("data-printer")
    page.evaluate("(n) => window.movePrinterStatusRow(n, 1)", first)
    assert page.locator("#printer-status-widget .fcc-ps-row").first.get_attribute("data-printer") != first
    assert (_layout(page)[INDX]["rows"], _layout(page)[XL]["rows"]) == ("4+4", "5")
    _headers(page, "Standard")
    # A heartbeat with a change (another spool on the INDX) repaints the rows.
    # The repaint and the reads in one turn of the page's JS: the next real
    # tick answers the stub fleet again and would repaint it back.
    got = page.evaluate("""([indx, xl, js, hjs]) => {
        const heads = (prefix, n, loaded) => Array.from({ length: n }, (_, i) => ({ id: prefix + '-' + (i + 1),
            position: i, unbound: false, loaded_count: loaded.includes(i) ? 1 : 0,
            item: loaded.includes(i) ? { id: 9400 + i, color: '7B2CBF', remaining_weight: 300, initial_weight: 1000,
                                          display: '#' + (9400 + i), details: { material: 'PLA' } } : null }));
        const rows = {}; rows[indx] = { state: { state: 'IDLE', is_active: false }, toolheads: heads('ZE', 8, [0, 1, 2]) };
        rows[xl] = { state: { state: 'IDLE', is_active: false }, toolheads: heads('ZX', 5, [4]) };
        window.refreshPrinterStatusWidgetFromAggregate(rows);
        return { repainted: !!document.querySelector("#printer-status-widget .fcc-ps-th[data-spool-id='9402']"),
                 layout: (eval(js))(), header: (eval(hjs))() }; }""", [INDX, XL, LAYOUT_JS, HEADER_JS])
    assert got["repainted"], got
    _drawn_as_recorded(got["layout"])
    assert (got["layout"][INDX]["rows"], got["layout"][XL]["rows"]) == ("4+4", "5"), got
    for name, h in got["header"].items():
        _one_header_line(h, name, "Standard")
        assert h["chipText"] == f"🛑 {REVIEWS[name]}", (name, h)


@pytest.mark.parametrize("width, size", [(1024, "Small"), (1024, "Standard"), (1024, "Large"), (1024, "Extra Large"),
                                         (1280, "Extra Large"), (390, "Standard")])
def test_the_collapsed_strip_keeps_every_chip_on_screen(page: Page, base_url: str, width, size):
    """Collapsed, a printer's group wider than the window ran off its right
    edge (the INDX's at 1024 px at every size and at 1280 px at Extra Large:
    its last heads and its 🛑 count, all a minimized widget shows of a
    review). It wraps its own chips now: every chip inside the window, the
    state first and the count last, the 🛑 with its number."""
    _open(page, base_url, size, width, 900, fleet=DEV_IDS, reviews={INDX: 3, XL: 12}, collapsed=True)
    got = page.evaluate(STRIP_JS)
    assert got["sw"] <= got["iw"], f"the page scrolls sideways: {got}"
    assert [(g["printer"], g["chips"], g["count"], g["last"], g["state"], g["countLines"]) for g in got["groups"]] == [
        (INDX, 10, "🛑 3", True, True, 1), (XL, 7, "🛑 12", True, True, 1)], got
    for g in got["groups"]:
        assert g["left"] >= -0.5 and g["right"] <= got["iw"] + 0.5, f"a chip is off the screen: {width} {size} {g}"


# --- Enter on the arrows, past the dashboard's scan accumulator (F3) -------------

def test_enter_on_a_focused_arrow_moves_the_printer_and_keeps_the_focus(page: Page, base_url: str):
    """The dashboard's scan accumulator (scripts.html) cancels every Enter
    outside a text field, so Enter on a focused ▲ / ▼ did nothing (Space
    worked). The arrows answer it now, and the focus stays on the moved
    printer's arrow (its ▲ once it is last), so Enter again moves it back."""
    _open(page, base_url, order=[INDX, XL])
    assert _order(page) == [INDX, XL]
    page.locator("#printer-status-widget .fcc-ps-row").first.locator("button.fcc-ps-reorder").focus()
    page.keyboard.press("Enter")
    assert _order(page) == [XL, INDX]
    assert page.evaluate(FOCUS_JS) == {"tag": "BUTTON", "dir": "-1", "printer": INDX}
    page.keyboard.press("Enter")
    assert _order(page) == [INDX, XL]
    assert page.evaluate(FOCUS_JS) == {"tag": "BUTTON", "dir": "1", "printer": INDX}
    # The order is kept, as a click keeps it.
    assert json.loads(page.evaluate("() => localStorage.getItem('fcc.printerStatus.order')")) == [INDX, XL]


def test_a_scan_typed_onto_a_focused_arrow_reaches_the_scan_path(page: Page, base_url: str):
    """A scanner types into whatever has the focus. On an arrow its Enter ends
    the scan (window.enterIsAScan): processScan gets the label, nothing moves.
    (The label is a made-up place, and every write is answered in this page.)"""
    _open(page, base_url, order=[INDX, XL])
    page.locator("#printer-status-widget .fcc-ps-row").first.locator("button.fcc-ps-reorder").focus()
    page.evaluate("() => { window._fccLastLocScan = null; }")
    page.keyboard.type("LOC:ZZ-NOPE-1")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window._fccLastLocScan && window._fccLastLocScan.text === 'LOC:ZZ-NOPE-1'",
                           timeout=5000)
    assert _order(page) == [INDX, XL]
    assert page.evaluate("() => state.scanBuffer") == ""


def test_a_mouse_click_on_an_arrow_lets_the_focus_go_as_before(page: Page, base_url: str):
    _open(page, base_url, order=[INDX, XL])
    page.locator("#printer-status-widget .fcc-ps-row").first.locator("button.fcc-ps-reorder").click()
    assert _order(page) == [XL, INDX]
    assert page.evaluate(FOCUS_JS)["tag"] == "BODY"


# --- a short laptop window (F2) -------------------------------------------------

VISIBLE_JS = r"""() => { const q = (s) => document.querySelector(s);
    const body = q('#printer-status-widget .fcc-ps-body'); const b = body.getBoundingClientRect();
    const tiles = Array.from(body.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
    const deck = q('.cmd-deck').getBoundingClientRect();
    const labels = Array.from(document.querySelectorAll('.cmd-deck .deck-label, .cmd-deck .deck-qr'))
        .map((l) => l.getBoundingClientRect().bottom);
    return { shown: tiles.filter((r) => r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5).length, tiles: tiles.length,
             sh: body.scrollHeight, ch: body.clientHeight, vh: innerHeight, deckBottom: deck.bottom,
             lowest: Math.max(...labels), strip: q('.content-row').getBoundingClientRect().height,
             root: parseFloat(getComputedStyle(document.documentElement).fontSize) }; }"""


@pytest.mark.parametrize("width, height, size", [(1280, 800, "Small"), (1280, 800, "Standard"), (1280, 800, "Large"),
                                                 (1366, 768, "Small"), (1366, 768, "Standard")])
def test_on_a_short_laptop_window_both_printers_show_whole(page: Page, base_url: str, width, height, size):
    """The name's own line made the open widget taller, and at 1280 x 800 (a
    Framework 12 at 150 %) or 1366 x 768 its limit, then 40 % of the window,
    hid the second printer's tiles (8 of 13 showed). Now the gap between
    printers is gone and the limit is 45 %: all 13 show without scrolling,
    and the deck and a 7rem strip of the log and the buffer stay on screen."""
    _open(page, base_url, size, width, height, fleet=DEV_IDS)
    got = page.evaluate(VISIBLE_JS)
    assert (got["shown"], got["tiles"]) == (13, 13) and got["sh"] <= got["ch"] + 1, (width, height, size, got)
    assert got["deckBottom"] <= got["vh"] + 0.5 and got["lowest"] <= got["vh"] + 0.5, got
    assert got["strip"] >= 7 * got["root"] - 2, got


# --- a printer between two others (F6) ------------------------------------------

MIDDLE = "ZZ Even Middle"
THREE = {INDX: _indx(), MIDDLE: {"state": {"state": "PRINTING", "is_active": True},
                                 "heads": [(f"ZM-{i}", True, _item(9330 + i, "PETG") if i == 2 else None)
                                           for i in range(1, 4)]},
         XL: _xl()}


@pytest.mark.parametrize("width", [1600, 390])
def test_a_printer_between_two_others_has_the_same_header_line(page: Page, base_url: str, width):
    _open(page, base_url, "Standard", width, 1100, fleet=THREE, reviews={MIDDLE: 2}, order=[INDX, MIDDLE, XL])
    rows = page.evaluate(ARROWS_JS)
    assert [(r["printer"], r["n"]) for r in rows] == [(INDX, 1), (MIDDLE, 2), (XL, 1)], rows
    gaps = [round(r["nameToTile"], 1) for r in rows]
    assert max(gaps) - min(gaps) <= 0.5, f"the tiles sit at different depths under their names: {gaps}"
    for r in rows:
        where = (width, r["printer"], r)
        assert r["headH"] == pytest.approx(r["nameH"], abs=0.5), where
        if r["printer"] != INDX:
            assert min(a["top"] for a in r["arrows"]) >= r["divider"] + 2, where
        for a in r["arrows"]:
            for t in r["tiles"]:
                assert (a["right"] <= t["left"] or t["right"] <= a["left"]
                        or a["bottom"] + 2 <= t["top"] or t["bottom"] + 2 <= a["top"]), where
    _headers(page, "Standard", {MIDDLE: 2})


# Counts a plain grid fill draws unevenly (3 + 3 + 1, 3 + 3 + 3 + 1) where three
# tiles fit on a line: only each row's first tile starting in column 1 draws
# the rule's 3 + 2 + 2 (review, 2026-10-22: the 8 and 5 heads above come out
# the same either way).
UNEVEN = {
    "ZZ Seven": {"state": {"state": "IDLE", "is_active": False},
                 "heads": [(f"ZS-{i}", True, _item(9320 + i, "PETG") if i == 1 else None) for i in range(1, 8)]},
    "ZZ Ten": {"state": {"state": "IDLE", "is_active": False},
               "heads": [(f"ZT-{i}", True, None) for i in range(1, 11)]},
}


def test_seven_and_ten_heads_start_each_row_under_the_name(page: Page, base_url: str):
    _open(page, base_url, "Extra Large", 800, 900, fleet=UNEVEN, reviews={})
    got = _layout(page)
    assert {k: (v["rows"], v["under"], v["below"], v["out"]) for k, v in got.items()} == {
        "ZZ Seven": ("3+2+2", True, True, 0), "ZZ Ten": ("3+3+2+2", True, True, 0)}, got


TILES_JS = """(name) => { const row = Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row'))
        .find((r) => r.dataset.printer === name);
    const r0 = row.getBoundingClientRect();
    return Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => { const r = t.getBoundingClientRect();
        return [Math.round((r.left - r0.left) * 100) / 100, Math.round((r.top - r0.top) * 100) / 100,
                Math.round(r.width * 100) / 100]; }); }"""


@pytest.mark.parametrize("width", [412, 1600])
def test_a_60_character_name_neither_overlaps_nor_shifts_the_tiles(page: Page, base_url: str, width):
    """Derek: "if printer names go ungodly long for some reason, they don't
    clash or break the toolhead display". The same 8 heads under a short name
    and under a 60-character one, PRINTING with 12 reviews (the widest header):
    every tile in the same place, the header one line."""
    context = page.context
    short = context.new_page()
    try:
        _open(short, base_url, "Standard", width, 1100, fleet={INDX: _indx("PRINTING"), XL: FLEET[XL]},
              reviews={INDX: 12})
        before = short.evaluate(TILES_JS, INDX)
    finally:
        short.close()
    _open(page, base_url, "Standard", width, 1100, fleet={LONG_NAME: _indx("PRINTING"), XL: FLEET[XL]},
          reviews={LONG_NAME: 12})
    after = page.evaluate(TILES_JS, LONG_NAME)
    assert after == before, f"the long name moved the tiles: {before} -> {after}"
    head = page.evaluate(HEADER_JS)[LONG_NAME]
    _one_header_line(head, LONG_NAME, "Standard")
    assert head["text"] == LONG_NAME and head["chipText"] == "🛑 12", head
    assert head["cut"] == (width == 412), f"the name ends in … on a phone only: {head}"
    _all_placed(_layout(page), "Standard", width)


def test_the_material_line_is_1_2_high_at_large(page: Page, base_url: str):
    """Its own box (text-truncate clips to it) is 1.2 lines high, and the
    whole box is inside its tile."""
    _open(page, base_url, "Large")
    lines = page.evaluate("""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-chip-mat'))
        .map((el) => { const cs = getComputedStyle(el); const tile = el.closest('.fcc-ps-th').getBoundingClientRect();
            const r = el.getBoundingClientRect();
            return { text: el.textContent.trim(), ratio: parseFloat(cs.lineHeight) / parseFloat(cs.fontSize),
                     high: el.clientHeight >= parseFloat(cs.lineHeight) - 0.5,
                     inTile: r.bottom <= tile.bottom + 0.5 && r.top >= tile.top - 0.5 }; })""")
    assert {ln["text"] for ln in lines} >= {"PETG", "Polycarbonate"}, lines
    for ln in lines:
        assert ln["ratio"] == pytest.approx(1.2, abs=0.01), ln
        assert ln["high"] and ln["inTile"], ln
