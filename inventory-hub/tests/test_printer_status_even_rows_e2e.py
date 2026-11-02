"""Printer Status on the real page: each printer's name (its arrows before
it), the info line under the name (its state, its 🛑 review count), its tiles
under that in even rows, the printers a step in under the title (Derek,
2026-10-22, 2026-10-23 and 2026-10-24).

2026-10-22: split a printer's heads into the fewest rows with EQUAL counts
(8 -> 4 + 4, 7 -> 4 + 3, 10 -> 5 + 5; never a lone tile), re-balanced on a
resize and on a Text size change. 2026-10-23, Derek's pick of the three
name-column styles: "name on top of tool heads ... indent in the toolheads
more so that they read as a sub thing of the printer name. We also avoid the
word wrap effect on the red notification dot about pending reviews ... if
printer names go ungodly long for some reason, they don't clash or break the
toolhead display."
2026-10-24, approving that with two tweaks: "indenting the rows in just a bit
so it reads more like a sub set, and less like an ordered list", and "move
the individual printer state and review buttons before the name of the
printer ... and all that data lines up so your eyes don't have to dart all
over the place to find out which printer is idle, printing, or has an error
of some sort". Later that day, seeing it: "the printer name, then under it,
the status and review, basically we could treat that section as an
information area about state and issues, then the toolheads. While having
the status information first is nice, you now have to go hunting for the
printer name to know what those statuses apply to."

The dev container's real page (Bootstrap, the heartbeat, cancel_review.js's
own poll, the scan accumulator, the Settings path for the size) with a
made-up fleet in every source the widget reads (conftest.stub_printer_fleet):
an INDX-like printer with 8 heads and an XL-like one with 5, as dev has, and
made-up pending reviews for them (the 🛑 N count). Pinned:
  - on Derek's 1600 x 1300 window, at each Text size: the 8 heads one row at
    Small and Standard (again: they were 4 + 4 while the state and the count
    sat before the name) and 4 + 4 at Large and Extra Large, the 5 one row,
    every tile under the info line and every line under the name's first
    letter, nothing out of the row; each printer's name on one line with its
    ▲▼ arrow before it, the info line under the name (the state badge
    filling its slot, then the 🛑 N count in its slot), its dot and number
    together; the names, the info lines, the states, the counts and the
    tiles lined up across the printers; every printer a step in under the
    title;
  - 390, 412, 1024 and 1366 px at Standard and Extra Large, the same checks;
    on a 390 and a 412 px phone at Standard the tiles start at the row's
    edge, two to a line (at Extra Large one a line, under the name), and
    from 400 px at Standard the printers step in under the title;
  - IDLE, PRINTING, ATTENTION and ERROR printers, with and without reviews:
    the names, the states, the counts and the tiles line up (2026-10-24);
  - a printer named with an apostrophe ("Derek's XL") gets its 🛑 N count on
    its info line and in the collapsed strip, and its arrows move it;
  - a Text size picked in Settings lays the rows out again at once, and a
    resize does too;
  - collapsing and opening the widget, the ▲▼ reorder and a heartbeat that
    repaints keep the rows even and the count on the info line; the
    collapsed strip still leads each printer with its state and ends with its
    count, 6 px from its last chip;
  - the collapsed strip keeps every chip inside the window at 1024 px, at
    1280 px at Extra Large and on a phone (F5: the INDX's last heads and its
    🛑 count ran off the right edge): a group wraps its own chips;
  - Enter on a focused ▲ / ▼ moves the printer, through the dashboard's own scan
    accumulator, which presses a focused button on a person's Enter since Group
    50.6 (F3: Enter did nothing there), the focus staying on the moved printer's arrow; a scan
    typed onto a focused arrow still reaches processScan; a mouse click lets
    the focus go, as before;
  - a short laptop window (F2: 8 of 13 showed): on a 1280 x 800 laptop (a
    Framework 12 at 150 %) at Small and Standard both printers' 13 tiles
    show whole in the open widget; at 1280 x 800 at Large and 1366 x 768 at
    Small and Standard the info lines make them taller than the widget may
    be, so it scrolls inside itself, the first printer whole; either way the
    deck and a 7rem strip of the log and the buffer stay on screen;
  - a printer between two others has the same name line as they do, its
    info line and tiles as far under its name, its arrows clear of the
    divider, the info line and the tiles (F6: 6.6 px taller);
  - 7 and 10 heads where three fit on a line are 3 + 2 + 2 and 3 + 3 + 2 + 2,
    each line starting under the name (Extra Large on a 900 px window);
  - a 60-character printer name keeps to one line (ending in "…" on a phone,
    its full text in its title) and leaves the info line and every tile
    where they are under a short name, at 412 and 1600 px;
  - the material line is 1.2 high at Large, inside its tile.
Every layout check holds the lines drawn to the ones the layout recorded
(data-rows). The rule itself and the 110 % display scale are
test_printer_status_even_rows.py (hermetic, under --offline).

READ-ONLY: every request that isn't a read is answered in the browser, and
the widget's sources answer the made-up fleet in this page only.

RED before the info line under the name (2026-10-24, second round): with
c0d4962's global.css, inv_printer_status.js and cancel_review.js on disk for
one run (the container serves the checkout live; this checkout's files
restored afterwards, their checksums checked), 23 of 41 here, and both of the
contrast guard's Printer Status tests (they wait for the count on the info
line): the name then the info line, the lining up, the rows on Derek's
window at every size (the INDX one row of 8 at Small and Standard) and on
narrower windows, Settings and a resize, a repaint and the reorder, the
middle printer's gaps, 7 and 10 heads at 900 px, the long name and the
apostrophe name. The 18 that hold there: the collapsed strip (6), Enter, a
scan and a click on an arrow (3), the short laptop windows (5), the step in
under the title (3) and the material line.

RED before the 2026-10-24 tweaks' first round: with 8f9213c's global.css,
inv_printer_status.js and cancel_review.js on disk for one run (the container
serves the checkout live; this checkout's files restored afterwards, their
checksums checked), 25 of 41 here, and the contrast guard's
test_printer_status_even_rows_are_readable: the header order and its slots,
the lining up, the step in under the title, the rows under a name that now
starts past the state and the count, and the apostrophe name's count (its
page waited for a count that never came). The 16 that hold there: the
collapsed strip (6), Enter, a scan and a click on an arrow (3), the short
laptop windows (5), the material line, and no step on a 390 px phone.

RED before the 2026-10-23 fixes: with b49b263's global.css, inv_printer_status.js and
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
from test_printer_status_even_rows import (APOS, ARROWS_JS, FOCUS_JS, HEADER_JS, LAYOUT_JS, LONG_NAME, STRIP_JS,
                                           TALL, _apart, _drawn_as_recorded, _lined_up, _name_then_info, _placed,
                                           _stepped, _tiles_lined_up)
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
# Dev's two printers as their tiles stand (2026-10-24): the INDX's 8 heads with
# no spool and no bound slot, the XL's 5 with spools on XL-4 and XL-5, so the
# open widget is as tall as on dev (353, 358 and 383 px at Small, Standard
# and Large); DEV_IDS's INDX has spools in its first row, 14 px taller.
DEV_LIKE = {INDX: {"state": {"state": "IDLE", "is_active": False},
                   "heads": [(f"RCOI-{i}", False, None) for i in range(1, 9)]},
            XL: {"state": {"state": "IDLE", "is_active": False},
                 "heads": [(f"XL-{i}", True, _item(9310 + i, "PLA") if i in (4, 5) else None) for i in range(1, 6)]}}


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


def _all_placed(page: Page, got: dict, where):
    """Every printer's tiles under the info line, under the name's first
    letter (or, on a phone, from the row's edge); every name and every
    printer's tiles starting at the same place; every printer a step in under
    the title where the body has room for it (2026-10-24)."""
    for name, g in got.items():
        _placed(g, (where, name))
    lefts = [g["nameLeft"] for g in got.values()]
    assert max(lefts) - min(lefts) <= 0.5, (where, got)
    _tiles_lined_up(got, where)
    _stepped(page, where)


def _headers(page: Page, size: str, counts: dict = REVIEWS):
    head = page.evaluate(HEADER_JS)
    for name, h in head.items():
        _name_then_info(h, name, size)
        assert h["chipText"] == (f"🛑 {counts[name]}" if counts.get(name) else None), (name, h)
    _lined_up(head, list(head), size)
    return head


def _order(page: Page):
    return [r.get_attribute("data-printer") for r in page.locator("#printer-status-widget .fcc-ps-row").all()]


@pytest.mark.parametrize("size", ["Small", "Standard", "Large", "Extra Large"])
def test_on_derek_s_window_each_printer_s_tiles_sit_under_its_name(page: Page, base_url: str, size):
    _open(page, base_url, size)
    got = _layout(page)
    want = ("8", "5") if size in ("Small", "Standard") else ("4+4", "5")
    assert (got[INDX]["rows"], got[XL]["rows"]) == want, (size, got)
    assert not got[INDX]["edge"] and not got[XL]["edge"], got
    _all_placed(page, got, size)
    _headers(page, size)


@pytest.mark.parametrize("width, size, indx, xl, edge", [
    (390, "Standard", "2+2+2+2", "2+2+1", True),
    (390, "Extra Large", "1+1+1+1+1+1+1+1", "1+1+1+1+1", False),
    (412, "Standard", "2+2+2+2", "2+2+1", True),
    (412, "Extra Large", "1+1+1+1+1+1+1+1", "1+1+1+1+1", False),
    (1024, "Standard", "4+4", "5", False),
    (1024, "Extra Large", "4+4", "3+2", False),
    (1366, "Standard", "4+4", "5", False),
    (1366, "Extra Large", "4+4", "5", False),
])
def test_narrower_windows_keep_the_name_the_info_line_and_even_rows(page: Page, base_url: str, width, size, indx, xl, edge):
    _open(page, base_url, size, width, TALL)
    got = _layout(page)
    assert (got[INDX]["rows"], got[XL]["rows"], got[INDX]["edge"], got[XL]["edge"]) == (indx, xl, edge, edge), (
        width, size, got)
    _all_placed(page, got, (width, size))
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
    _all_placed(page, _layout(page), 800)


# Each printer in the folded strip (Group 50.1): its parts in order, its 🛑
# count's text and how many lines it takes.
COLLAPSED_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-header-chips .fcc-ps-printer-group'))
    .map((g) => { const chip = g.querySelector('.fcc-cr-chip');
        const tops = chip ? new Set(Array.from((() => { const r = document.createRange(); r.selectNodeContents(chip);
            return r.getClientRects(); })()).filter((x) => x.width > 0).map((x) => Math.round(x.top))) : new Set();
        return { printer: g.dataset.printer, parts: Array.from(g.children).map((k) => k.className),
                 text: chip ? chip.textContent : null, lines: tops.size }; })"""
STRIP_PARTS = ["fcc-ps-strip-name", "fcc-ps-strip-state", "fcc-ps-strip-count", "fcc-ps-strip-heads"]


def test_collapse_reorder_and_a_repaint_keep_the_rows_even(page: Page, base_url: str):
    _open(page, base_url)
    page.evaluate("() => window.togglePrinterStatusWidget()")
    page.wait_for_function("() => document.getElementById('printer-status-widget').classList.contains('collapsed')")
    # The folded strip (Group 50.1, PIN UPDATED DELIBERATELY): each printer's
    # name, its state, its 🛑 N on one line, then its heads.
    strip = page.evaluate(COLLAPSED_JS)
    assert [(s["printer"], s["parts"], s["text"], s["lines"]) for s in strip] == [
        (INDX, STRIP_PARTS, "🛑 3", 1), (XL, STRIP_PARTS, "🛑 1", 1)], strip
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
        _name_then_info(h, name, "Standard")
        assert h["chipText"] == f"🛑 {REVIEWS[name]}", (name, h)
    _lined_up(got["header"], list(got["header"]), "after a repaint")


@pytest.mark.parametrize("width, size", [(1024, "Small"), (1024, "Standard"), (1024, "Large"), (1024, "Extra Large"),
                                         (1280, "Extra Large"), (390, "Standard")])
def test_the_collapsed_strip_keeps_every_chip_on_screen(page: Page, base_url: str, width, size):
    """Collapsed, a printer's group wider than the window ran off its right
    edge (the INDX's at 1024 px at every size and at 1280 px at Extra Large:
    its last heads and its 🛑 count, all a minimized widget shows of a
    review). PIN UPDATED DELIBERATELY (Group 50.1, 2026-10-29): each printer
    is its name, its state, its 🛑 count, then its heads, and heads that don't
    fit scroll sideways in their own box (Derek's fallback) instead of
    wrapping: every part inside the window, the 🛑 with its number."""
    _open(page, base_url, size, width, 900, fleet=DEV_IDS, reviews={INDX: 3, XL: 12}, collapsed=True)
    got = page.evaluate(STRIP_JS)
    assert got["sw"] <= got["iw"], f"the page scrolls sideways: {got}"
    assert [(g["printer"], g["parts"], g["heads"], g["count"], g["countLines"]) for g in got["groups"]] == [
        (INDX, STRIP_PARTS, 8, "🛑 3", 1), (XL, STRIP_PARTS, 5, "🛑 12", 1)], got
    for g in got["groups"]:
        assert g["left"] >= -0.5 and g["right"] <= got["iw"] + 0.5, f"a part is off the screen: {width} {size} {g}"
    if width <= 412:
        assert got["groups"][0]["scrolls"], f"the INDX's heads should scroll on a phone: {got}"


# --- Enter on the arrows, past the dashboard's scan accumulator (F3) -------------

def test_enter_on_a_focused_arrow_moves_the_printer_and_keeps_the_focus(page: Page, base_url: str):
    """The dashboard's scan accumulator (scripts.html) cancelled every Enter
    outside a text field, so Enter on a focused ▲ / ▼ did nothing (Space
    worked). It presses a focused button since Group 50.6, and the focus stays
    on the moved printer's arrow (its ▲ once it is last), so Enter again moves it back."""
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
    const whole = (t) => { const r = t.getBoundingClientRect(), bb = body.getBoundingClientRect();
        return r.top >= bb.top - 0.5 && r.bottom <= bb.bottom + 0.5; };
    const firstWhole = Array.from(body.querySelector('.fcc-ps-row').querySelectorAll('.fcc-ps-th')).every(whole);
    body.scrollTop = body.scrollHeight;
    const atEnd = Array.from(body.querySelectorAll('.fcc-ps-th')).filter(whole).length;
    body.scrollTop = 0;
    return { shown: tiles.filter((r) => r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5).length, tiles: tiles.length,
             firstWhole, atEnd,
             sh: body.scrollHeight, ch: body.clientHeight, vh: innerHeight, deckBottom: deck.bottom,
             lowest: Math.max(...labels), strip: q('.content-row').getBoundingClientRect().height,
             root: parseFloat(getComputedStyle(document.documentElement).fontSize) }; }"""


@pytest.mark.parametrize("width, height, size, tight", [(1280, 800, "Small", False), (1280, 800, "Standard", False),
                                                        (1280, 800, "Large", True), (1366, 768, "Small", True),
                                                        (1366, 768, "Standard", True)])
def test_on_a_short_laptop_window_both_printers_show_or_scroll_into_view(page: Page, base_url: str, width, height,
                                                                         size, tight):
    """The name's own line made the open widget taller, and at 1280 x 800 (a
    Framework 12 at 150 %) or 1366 x 768 its limit, then 40 % of the window,
    hid the second printer's tiles (8 of 13 showed). The gap between printers
    went and the limit is 45 %. The info line under each name (2026-10-24)
    adds a line per printer: at 1280 x 800 at Small and Standard all 13 still
    show without scrolling; at 1280 x 800 at Large and 1366 x 768 at Small
    and Standard the widget stops at its limit and scrolls inside itself,
    the first printer whole and the second scrolled to. Either way the deck
    and a 7rem strip of the log and the buffer stay on screen.

    PIN UPDATED DELIBERATELY (Group 50.7, Derek's pick of four, 2026-10-30):
    where it scrolled, the widget takes its short-window step instead (each
    printer's state beside its name, each material in its tile's colour band)
    and all 13 heads show without scrolling; where it fit, nothing changes."""
    _open(page, base_url, size, width, height, fleet=DEV_LIKE)
    got = page.evaluate(VISIBLE_JS)
    assert got["tiles"] == 13, got
    assert got["shown"] == 13 and got["sh"] <= got["ch"] + 1, (width, height, size, got)
    assert page.evaluate("() => document.getElementById('printer-status-widget').classList.contains('fcc-ps-tight')") \
        is tight, (width, height, size)
    assert got["deckBottom"] <= got["vh"] + 0.5 and got["lowest"] <= got["vh"] + 0.5, got
    assert got["strip"] >= 7 * got["root"] - 2, got


# --- a printer between two others (F6) ------------------------------------------

MIDDLE = "ZZ Even Middle"
THREE = {INDX: _indx(), MIDDLE: {"state": {"state": "PRINTING", "is_active": True},
                                 "heads": [(f"ZM-{i}", True, _item(9330 + i, "PETG") if i == 2 else None)
                                           for i in range(1, 4)]},
         XL: _xl()}


@pytest.mark.parametrize("width", [1600, 390])
def test_a_printer_between_two_others_has_the_same_name_line(page: Page, base_url: str, width):
    _open(page, base_url, "Standard", width, TALL, fleet=THREE, reviews={MIDDLE: 2}, order=[INDX, MIDDLE, XL])
    rows = page.evaluate(ARROWS_JS)
    assert [(r["printer"], r["n"]) for r in rows] == [(INDX, 1), (MIDDLE, 2), (XL, 1)], rows
    for gap in ("nameToInfo", "infoToTile"):
        gaps = [round(r[gap], 1) for r in rows]
        assert max(gaps) - min(gaps) <= 0.5, f"{gap} differs between the printers: {gaps}"
    for r in rows:
        where = (width, r["printer"], r)
        mid = (min(a["top"] for a in r["arrows"]) + max(a["bottom"] for a in r["arrows"])) / 2
        assert abs(mid - r["nameMid"]) <= 1.5, where
        if r["printer"] != INDX:
            assert min(a["top"] for a in r["arrows"]) >= r["divider"] + 2, where
        for a in r["arrows"]:
            assert _apart(a, r["info"]), where
            for t in r["tiles"]:
                assert _apart(a, t), where
    _headers(page, "Standard", {MIDDLE: 2})
    _stepped(page, width)


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
    _open(page, base_url, "Extra Large", 900, 900, fleet=UNEVEN, reviews={})
    got = _layout(page)
    assert {k: (v["rows"], v["under"], v["below"], v["out"]) for k, v in got.items()} == {
        "ZZ Seven": ("3+2+2", True, True, 0), "ZZ Ten": ("3+3+2+2", True, True, 0)}, got


TILES_JS = """(name) => { const row = Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row'))
        .find((r) => r.dataset.printer === name);
    const r0 = row.getBoundingClientRect();
    return Array.from(row.querySelectorAll('.fcc-ps-info, .fcc-ps-state, .fcc-cr-chip, .fcc-ps-th')).map((t) => {
        const r = t.getBoundingClientRect();
        return [t.className, Math.round((r.left - r0.left) * 100) / 100, Math.round((r.top - r0.top) * 100) / 100,
                Math.round(r.width * 100) / 100]; }); }"""


@pytest.mark.parametrize("width", [412, 1600])
def test_a_60_character_name_neither_overlaps_nor_shifts_the_tiles(page: Page, base_url: str, width):
    """Derek: "if printer names go ungodly long for some reason, they don't
    clash or break the toolhead display". The same 8 heads under a short name
    and under a 60-character one, PRINTING with 12 reviews: the info line and
    every tile in the same place, the name one line."""
    context = page.context
    short = context.new_page()
    try:
        _open(short, base_url, "Standard", width, TALL, fleet={INDX: _indx("PRINTING"), XL: FLEET[XL]},
              reviews={INDX: 12})
        before = short.evaluate(TILES_JS, INDX)
    finally:
        short.close()
    _open(page, base_url, "Standard", width, TALL, fleet={LONG_NAME: _indx("PRINTING"), XL: FLEET[XL]},
          reviews={LONG_NAME: 12})
    after = page.evaluate(TILES_JS, LONG_NAME)
    assert after == before, f"the long name moved the info line or the tiles: {before} -> {after}"
    heads = page.evaluate(HEADER_JS)
    head = heads[LONG_NAME]
    _name_then_info(head, LONG_NAME, "Standard")
    _lined_up(heads, list(heads), width)
    assert head["text"] == LONG_NAME and head["chipText"] == "🛑 12", head
    assert head["cut"] == (width == 412), f"the name ends in … on a phone only: {head}"
    _all_placed(page, _layout(page), width)


# --- 2026-10-24: the states, the counts and the names line up; the step in ------

STATES = {
    "ZZ Align Idle": {"state": {"state": "IDLE", "is_active": False},
                      "heads": [(f"ZA-{i}", True, _item(9340 + i, "PETG") if i == 1 else None) for i in range(1, 5)]},
    "ZZ Align Printing": {"state": {"state": "PRINTING", "is_active": True},
                          "heads": [(f"ZB-{i}", True, _item(9350 + i, "PLA") if i == 2 else None) for i in range(1, 6)]},
    "ZZ Align Attention": {"state": {"state": "ATTENTION", "is_active": False},
                           "heads": [(f"ZC-{i}", True, None) for i in range(1, 4)]},
    "ZZ Align Error": {"state": {"state": "ERROR", "is_active": False},
                       "heads": [(f"ZD-{i}", True, _item(9360 + i, "ASA") if i == 1 else None) for i in range(1, 3)]},
}


@pytest.mark.parametrize("width, size", [(1600, "Standard"), (1600, "Extra Large"), (412, "Standard")])
def test_the_states_the_counts_and_the_names_line_up_down_the_left(page: Page, base_url: str, width, size):
    """Derek, 2026-10-24: the name first, the state and the review count on
    the info line under it, so a glance down the page reads each printer's
    name and, under it, whether it is idle, printing or has an error. IDLE,
    PRINTING, ATTENTION and ERROR, two of them with reviews: the names lined
    up, every badge the same width in one column under them, the counts in
    the next, each printer's tiles under its name, every printer a step in
    under the title."""
    reviews = {"ZZ Align Printing": 2, "ZZ Align Attention": 12}
    _open(page, base_url, size, width, TALL, fleet=STATES, reviews=reviews, order=list(STATES))
    head = _headers(page, size, reviews)
    assert [head[n]["badgeText"] for n in STATES] == ["IDLE", "PRINTING", "ATTENTION", "ERROR"], head
    _all_placed(page, _layout(page), (width, size))


@pytest.mark.parametrize("width, stepped", [(1600, True), (412, True), (390, False)])
def test_the_printers_step_in_under_the_title(page: Page, base_url: str, width, stepped):
    """Derek, 2026-10-24: "indenting the rows in just a bit so it reads more
    like a sub set, and less like an ordered list". Each printer, its arrows
    first, starts under the title's first letter; on a phone whose widget is
    under 23rem wide (a 390 px iPhone at Standard) at the edge, as before."""
    _open(page, base_url, "Standard", width, 1100)
    assert _stepped(page, width) == stepped


def test_a_printer_named_with_an_apostrophe_gets_its_count_and_moves(page: Page, base_url: str):
    """data-printer held the arrows' JS escape (Derek\\'s XL), so the 🛑 N
    count never reached the line of a printer named like Derek's XL. The
    plain name now: the count shows on its info line and in the collapsed
    strip, and the arrows move the printer (the order kept under its plain
    name)."""
    fleet = {APOS: _xl(prefix="ZQ"), INDX: _indx()}
    _open(page, base_url, "Standard", fleet=fleet, reviews={APOS: 2, INDX: 3}, order=[APOS, INDX])
    _headers(page, "Standard", {APOS: 2, INDX: 3})
    assert _order(page) == [APOS, INDX]
    page.locator("#printer-status-widget .fcc-ps-row").first.locator("button.fcc-ps-reorder").click()
    assert _order(page) == [INDX, APOS]
    assert json.loads(page.evaluate("() => localStorage.getItem('fcc.printerStatus.order')")) == [INDX, APOS]
    _headers(page, "Standard", {APOS: 2, INDX: 3})
    page.evaluate("() => window.togglePrinterStatusWidget()")
    strip = page.evaluate(STRIP_JS)
    assert [(g["printer"], g["count"]) for g in strip["groups"]] == [(INDX, "🛑 3"), (APOS, "🛑 2")], strip


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
