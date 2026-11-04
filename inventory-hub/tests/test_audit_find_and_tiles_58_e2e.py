"""Derek's answers of 2026-11-03 on Group 58, on the real dashboard: a tile's real QR code
scanned as a scanner's keys (A1), 🔎 Find a spool by keyboard and by mouse (A2), and the
phone width, with Bootstrap, the real accumulator and the page's own polls.

FCC's routes are answered in this browser on their real shapes (the audit's session,
test_audit_page_58_js.SESSION; the search's rows, test_audit_find_and_tiles_58_js.SEARCH_ROWS;
both pinned to the real routes), and every request that isn't a GET is answered here and
recorded, so nothing reaches dev but reads and dev's own audit stays idle.

The rules are proved hermetically in test_audit_find_and_tiles_58_js.py; the double
click on a Find row and on an Extra tile, at five window sizes, in
test_audit_double_click_58_e2e.py; the contrast and text-size guards in
test_contrast_guard.py and test_text_size_guard.py.
"""
from __future__ import annotations

import json
import time

import pytest
from playwright.sync_api import Page, expect

import conftest
from test_audit_find_and_tiles_58_js import SEARCH_ROWS, search_row
from test_audit_no_label_58_e2e import SCANNER, Marks, tile
from test_audit_page_58_e2e import PANEL, _dashboard, _start
from test_audit_page_58_js import SESSION
from test_audit_question_dialog_58_js import _question
from test_scanner_safe_dialogs_61_js import LEGACY

pytestmark = pytest.mark.usefixtures("require_server")

FIND = "#fcc-audit-find"
FIND_BTN = "#fcc-audit-panel-find"
FIND_BOX = FIND + " [data-find-box]"
FIND_BODY = FIND + " [data-find-body]"
NOT_SCANNED = 99


class Finds(Marks):
    """Marks, with every write answered here, the search answered from SEARCH_ROWS, and a
    find by a tile's QR or a Find pick turning the session as the routes turn it."""

    def __init__(self, page):
        self.writes, self.searches = [], []
        page.route("**/*", self._any)                   # first: every route after it wins
        super().__init__(page)
        page.route("**/api/search*", self._search)
        conftest.own_the_buffer(page, [])

    def _any(self, route):
        if route.request.method == "GET":
            route.continue_()
            return
        self.writes.append("/" + route.request.url.split("/", 3)[3].split("?")[0])
        self._json(route, {"success": True, "status": "success"})

    def _search(self, route):
        q = route.request.url.split("q=", 1)[1].split("&", 1)[0].replace("+", " ").lower()
        self.searches.append(route.request.url.split("/", 3)[3])
        rows = [r for r in SEARCH_ROWS if all(w in r["display"].lower() for w in q.split())]
        self._json(route, {"success": True, "results": rows})

    def _find(self, sid):
        rows = self.session["expected"]
        if any(r["id"] == sid for r in rows):
            self._set(dict(next(r for r in rows if r["id"] == sid), found=True, label_read=False))

    def _scan(self, route):
        body = route.request.post_data_json or {}
        text = str(body.get("text") or "")
        self.sources = getattr(self, "sources", []) + [(text, body.get("source"))]
        if text.upper().startswith("CMD:FOUND:"):
            self._find(int(text.rsplit(":", 1)[1]))
        elif text.startswith("ID:"):
            self._find(int(text[3:]))
        super()._scan(route)


def _running(page: Page, base_url: str):
    server = Finds(page)
    _dashboard(page, base_url)
    _start(page)
    page.wait_for_selector(tile(NOT_SCANNED))
    return server


def test_a_real_tile_qr_scanned_as_a_scanners_keys_finds_the_spool(page: Page, base_url: str):
    server = _running(page, base_url)
    qr = f"{tile(NOT_SCANNED)} .fcc-audit-tile-qr"
    expect(page.locator(f"{qr} canvas, {qr} img").first).to_be_attached()
    assert page.get_attribute(qr, "data-audit-qr") == "CMD:FOUND:boot-1:99"
    assert page.get_attribute(qr, "aria-hidden") == "true"
    box = page.locator(qr).bounding_box()
    assert round(box["width"]) == 78 and round(box["height"]) == 78          # 72 px and its quiet zone
    assert page.locator(f"{tile(57)} .fcc-audit-tile-qr").count() == 0        # found: none
    page.evaluate(SCANNER, "CMD:FOUND:boot-1:99")
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("found, no label read")
    expect(page.locator(qr)).to_have_count(0)
    assert ("CMD:FOUND:boot-1:99", "barcode") in server.sources
    assert server.writes == []


def test_find_by_keyboard(page: Page, base_url: str):
    server = _running(page, base_url)
    page.keyboard.press("/")
    expect(page.locator(FIND_BOX)).to_be_focused()
    page.keyboard.type("glow blue", delay=20)
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(1)
    expect(page.locator(f"{FIND} .fcc-find-row")).to_contain_text("📍 LR-MDB-1 slot 2")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_contain_text("on the list")
    assert server.searches == ["api/search?q=glow+blue&type=spool&strict=1"]
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(page.locator(FIND)).to_have_count(0)
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("found, no label read")
    assert ("ID:99", "audit_find") in server.sources      # PIN UPDATED DELIBERATELY (Q5: Find's own source)
    expect(page.locator(FIND_BTN)).to_be_focused()


def test_find_by_mouse(page: Page, base_url: str):
    server = _running(page, base_url)
    page.click(FIND_BTN)
    page.fill(FIND_BOX, "glow")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(len(SEARCH_ROWS))
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='242']")).to_contain_text("🔗 loaded from LR-MDB-2 slot 4")
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='260']")).to_contain_text("❓ Lost: CR-CT-1 slot 2")
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='270']")).to_contain_text("Unassigned")
    page.click(f"{FIND} .fcc-find-row[data-find-id='99']")
    expect(page.locator(FIND)).to_have_count(0)
    expect(page.locator(tile(NOT_SCANNED))).to_contain_text("found, no label read")
    assert ("ID:99", "audit_find") in server.sources      # PIN UPDATED DELIBERATELY (Q5: Find's own source)


@pytest.mark.parametrize("width, height", [(390, 844), (1600, 1300)])
def test_nothing_scrolls_sideways(page: Page, base_url: str, width, height):
    """At phone width too: the tiles with their QR, the strip with its 🖨️, and Find."""
    page.set_viewport_size({"width": width, "height": height})
    server = _running(page, base_url)
    page.click(tile(NOT_SCANNED))                    # the strip, with the spool not flagged
    page.evaluate(SCANNER, "CMD:NEEDLABEL")          # flagged: the strip's 🖨️ shows
    expect(page.locator("#fcc-audit-label-queue")).to_be_visible()

    def sideways():
        return page.evaluate("""() => { const p = document.querySelector('#fcc-audit-panel-overlay > div');
            const b = document.getElementById('fcc-audit-panel-body'); const r = p.getBoundingClientRect();
            return { page: document.documentElement.scrollWidth > innerWidth, body: b.scrollWidth > b.clientWidth + 1,
                     out: r.left < -0.5 || r.right > innerWidth + 0.5 }; }""")
    assert sideways() == {"page": False, "body": False, "out": False}
    page.click(FIND_BTN)
    page.fill(FIND_BOX, "glow")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(len(SEARCH_ROWS))
    got = page.evaluate("""() => { const p = document.querySelector('#fcc-audit-find .fcc-find-panel');
        const body = p.querySelector('[data-find-body]'); const r = p.getBoundingClientRect();
        return { out: r.left < -0.5 || r.right > innerWidth + 0.5, body: body.scrollWidth > body.clientWidth + 1 }; }""")
    assert got == {"out": False, "body": False}
    assert page.evaluate("() => document.documentElement.scrollWidth > innerWidth") is False
    assert server.writes == []


# --- The dock leaves the tiles room (Derek, 2026-11-03, sample 1b) --------------------------
# The Last found box, Needs a label, Done... and Cancel Audit sit in a dock under the list that
# never scrolls. On a window too short for the dock and a tile row (a phone at Extra Large
# text, a phone held sideways) it goes in the flow after the tiles, and the two scroll as
# one. It replaced the Last found strip stuck over the tiles (review of 7e3720f, P-5: on a
# phone at Extra Large the strip was taller than the body, and no tile could be pressed).
# PIN UPDATED DELIBERATELY: these two tests pinned the strip's 45% rule.

DOCK_FIT = """() => { const w = document.getElementById('fcc-audit-panel-scroll');
    const b = document.getElementById('fcc-audit-panel-body'); const d = document.getElementById('fcc-audit-panel-dock');
    return { flow: w.classList.contains('fcc-audit-scroll-flow'), body: b.clientHeight, content: b.scrollHeight,
             dock: d.getBoundingClientRect().height, rem: parseFloat(getComputedStyle(document.documentElement).fontSize) }; }"""
# Each tile, scrolled into view as far as it goes: can its middle be pressed?
TILES_PRESSABLE = """() => { const b = document.getElementById('fcc-audit-panel-body');
    return Array.from(b.querySelectorAll('.fcc-audit-tile')).map((t) => {
        t.scrollIntoView({ block: 'center' });
        const r = t.getBoundingClientRect();
        const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !!e && t.contains(e); }); }"""
# The dock's three buttons and their QRs: wholly seen (corners and middle) as they are, or,
# `scroll`, once scrolled into view.
DOCK_SEEN = """(scroll) => ['#fcc-audit-panel-needlabel', '#fcc-audit-panel-done', '#fcc-audit-panel-cancel',
    '#fcc-audit-panel-qr-needlabel', '#fcc-audit-panel-qr-done', '#fcc-audit-panel-qr-cancel'].filter((s) => {
    const e = document.querySelector(s); if (scroll) e.scrollIntoView({ block: 'nearest' });
    const r = e.getBoundingClientRect();
    return ![[r.left + 3, r.top + 3], [r.right - 3, r.top + 3], [r.left + 3, r.bottom - 3], [r.right - 3, r.bottom - 3],
             [r.left + r.width / 2, r.top + r.height / 2]].every(([x, y]) => { const h = document.elementFromPoint(x, y);
        return !!h && e.contains(h); }); })"""


def _flagged_last_found(page: Page, server):
    """#99 found and marked "Needs a label" here: the Last found box with "undo that" and the 🖨️."""
    flagged = dict(SESSION["expected"][1], found=True, label_status=True, flagged_here=True, label_read=False)
    server.session = dict(SESSION, expected=[SESSION["expected"][0], flagged], last_found=flagged)
    page.evaluate("() => window.refreshAuditSession()")
    page.wait_for_selector("#fcc-audit-label-queue")
    page.wait_for_timeout(300)                       # its QR draws two frames later


def _leaves_room(page: Page, what: str):
    """Docked: the dock's controls in view with no scroll, and the list keeps a tile row
    (or all of itself, when shorter). In the flow: they can be scrolled to. Either way
    every tile can be brought into view and pressed."""
    got = page.evaluate(DOCK_FIT)
    if not got["flow"]:
        assert got["body"] >= min(7 * got["rem"], got["content"]) - 1, (what, got)
        assert page.evaluate(DOCK_SEEN, False) == [], (what, got)
    assert all(page.evaluate(TILES_PRESSABLE)), (what, got)
    assert page.evaluate(DOCK_SEEN, True) == [], (what, got)
    return got


@pytest.mark.parametrize("width, height, size, docked", [
    (390, 844, "Standard", True), (390, 844, "Large", True), (390, 844, "Extra Large", False),
    (844, 390, "Standard", False),
    (1366, 768, "Standard", True), (1366, 768, "Large", True), (1600, 1300, "Standard", True)])
def test_the_dock_leaves_the_tiles_room(page: Page, base_url: str, width, height, size, docked):
    """Under the list while it leaves the list a tile row, else in the flow after the
    tiles; every tile can be brought into view and pressed, and so can the dock's three
    buttons and their QRs. RED on 517abe1 (no dock)."""
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    server = _running(page, base_url)
    _flagged_last_found(page, server)
    got = _leaves_room(page, f"{width}x{height} {size}")
    assert got["flow"] is (not docked), got
    assert server.writes == []


def test_the_dock_follows_a_text_size_change(page: Page, base_url: str):
    """A Text size picked with the panel up (Settings, no reload): the dock is measured
    again and goes in the flow when it no longer leaves room, and back when it does."""
    page.set_viewport_size({"width": 390, "height": 844})
    server = _running(page, base_url)
    _flagged_last_found(page, server)
    assert page.evaluate(DOCK_FIT)["flow"] is False
    resize = ("(s) => { document.documentElement.setAttribute('data-fcc-text-size', s);"
              " document.dispatchEvent(new CustomEvent('fcc:text-size', { detail: { name: s } })); }")
    page.evaluate(resize, "xlarge")
    page.wait_for_function("() => document.getElementById('fcc-audit-panel-scroll').classList.contains('fcc-audit-scroll-flow')")
    _leaves_room(page, "after Extra Large")
    page.set_viewport_size({"width": 1366, "height": 768})
    page.evaluate(resize, "standard")
    page.wait_for_function("() => !document.getElementById('fcc-audit-panel-scroll').classList.contains('fcc-audit-scroll-flow')")
    _leaves_room(page, "back at Standard")
    assert server.writes == []


@pytest.mark.parametrize("width, height, size", [(390, 844, "Standard"), (390, 844, "Large"), (360, 740, "Standard")])
def test_on_a_phone_the_dock_buttons_are_one_height(page: Page, base_url: str, width, height, size):
    """Derek's look of 2026-11-04 (T7), on the real dashboard with Bootstrap: on a phone Done…
    was 30 px tall against 45 and 50 for Needs a label and Cancel Audit, which wrap to two
    lines. The three start and end level, each centring its words. Its hermetic twin, red on
    8ca03e1, is test_audit_panel_look_58_js.py's."""
    from test_audit_panel_look_58_js import DOCK_BUTTONS
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    server = _running(page, base_url)
    _flagged_last_found(page, server)
    got = page.evaluate(DOCK_BUTTONS, ["#fcc-audit-panel-needlabel", "#fcc-audit-panel-done", "#fcc-audit-panel-cancel"])
    what = f"{width}x{height} {size}: {got}"
    assert max(g["height"] for g in got) - min(g["height"] for g in got) <= 1, what
    assert max(g["top"] for g in got) - min(g["top"] for g in got) <= 1, what
    assert all(abs(g["off"]) <= 1.5 for g in got), what
    assert server.writes == []


# --- A phone's rows (review of 7e3720f, P-4) ----------------------------------------------
# Names as long as dev's ("Sunlu PETG (Red (Glow In The Dark Red))"), with each tag: #99 is
# on this audit's list, #57 and #200 found already (SESSION).
LONG_ROWS = [search_row(99, "Red (Glow In The Dark Red)", "LR-MDB-1", "2"),
             search_row(57, "Transparent Orange Glow", "LR-MDB-1", "1"),
             search_row(200, "Galaxy Black Sparkle", "LR-MDB-2", "3"),
             search_row(260, "Glow Gold Silk Dual Colour", "UNKNOWN",
                        lost_from={"place": "CR-CT-1", "slot": "2", "on": "2026-11-01"}),
             search_row(270, "Glow Grey Matte", "")]

# Every row's name and place, and its tag: whole (no text cut, nothing past the row's edge).
ROWS_CUT = """() => {
    const cut = [];
    document.querySelectorAll('#fcc-audit-find .fcc-find-row').forEach((row) => {
        const r = row.getBoundingClientRect();
        row.querySelectorAll('.fcc-find-name, .fcc-find-where, .fcc-find-tag').forEach((el) => {
            const b = el.getBoundingClientRect();
            const block = getComputedStyle(el).display !== 'inline';
            if ((block && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1))
                    || b.left < r.left - 0.5 || b.right > r.right + 0.5 || b.bottom > r.bottom + 0.5) {
                cut.push(row.dataset.findId + ': ' + el.className + ' ' + el.textContent);
            }
        });
    });
    return cut;
}"""


@pytest.mark.parametrize("size", ["Standard", "Large", "Extra Large"])
def test_a_phones_rows_cut_no_name_and_keep_their_tags(page: Page, base_url: str, size):
    """At 390 x 844: the name wraps (its colour tells two spools apart, and a touch screen
    can't show the row's title), and the tag goes under it. RED on e7886e9: every tagged
    row's name was cut at Standard, and every row's at Extra Large."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    server = _running(page, base_url)
    page.route("**/api/search*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"success": True, "results": LONG_ROWS})))
    page.click(FIND_BTN)
    page.fill(FIND_BOX, "glow")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(len(LONG_ROWS))
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='99'] [data-find-tag]")).to_have_text("on the list")
    expect(page.locator(f"{FIND} .fcc-find-row[data-find-id='57'] [data-find-tag]")).to_have_text("✅ found")
    assert page.evaluate(ROWS_CUT) == []
    got = page.evaluate("""() => { const p = document.querySelector('#fcc-audit-find .fcc-find-panel');
        const body = p.querySelector('[data-find-body]'); const r = p.getBoundingClientRect();
        return { out: r.left < -0.5 || r.right > innerWidth + 0.5, body: body.scrollWidth > body.clientWidth + 1 }; }""")
    assert got == {"out": False, "body": False}
    assert server.writes == []


def test_a_wide_windows_rows_keep_their_tag_beside_the_name(page: Page, base_url: str):
    """Where the window is wide the tag stays at the row's end, on the name's line, as
    before, and nothing is cut. Pins what was already right beside P-4's change."""
    page.set_viewport_size({"width": 1366, "height": 768})
    server = _running(page, base_url)
    page.route("**/api/search*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"success": True, "results": LONG_ROWS})))
    page.click(FIND_BTN)
    page.fill(FIND_BOX, "glow")
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(len(LONG_ROWS))
    assert page.evaluate(ROWS_CUT) == []
    beside = page.evaluate("""() => { const row = document.querySelector("#fcc-audit-find .fcc-find-row[data-find-id='99']");
        const n = row.querySelector('.fcc-find-name').getBoundingClientRect();
        const t = row.querySelector('.fcc-find-tag').getBoundingClientRect();
        return t.left >= n.right - 0.5 && t.top < n.bottom; }""")
    assert beside is True
    assert server.writes == []


# --- The keyboard stays in Find (review of 7e3720f, P-7) ----------------------------------

def test_a_legacy_label_scanned_into_finds_box_and_its_picker_cancelled_leaves_the_keyboard_in_find(
        page: Page, base_url: str):
    """The legacy picker the scan opens, over Find, and its Escape: the keyboard goes
    back to Find's box, and letters typed next land there, not in the scan buffer (which
    the next Enter would send as a scan). RED on 80ef514: BODY, and "glow" went to the
    scan buffer."""
    server = _running(page, base_url)
    server.answers["LEG:120"] = LEGACY
    page.click(FIND_BTN)
    expect(page.locator(FIND_BOX)).to_be_focused()
    page.keyboard.type("LEG:120", delay=5)
    page.keyboard.press("Enter")
    expect(page.locator(PICKER)).to_be_visible()
    expect(page.locator("#fcc-legacy-picker-use")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator(PICKER)).to_have_count(0)
    expect(page.locator(FIND_BOX)).to_be_focused()
    page.keyboard.type("glow", delay=30)
    expect(page.locator(FIND_BOX)).to_have_value("glow")
    assert page.evaluate("state.scanBuffer") == ""
    expect(page.locator(f"{FIND} .fcc-find-row")).to_have_count(len(SEARCH_ROWS))
    assert server.writes == []


# --- '/' and Ctrl+K under what sits over the panel (review of 7e3720f, P-2) ---------------
# The audit's '/' opens Find while the panel is on top. With something over the panel, the
# global search's own '/' (fab_drag.js) opened #offcanvasSearch behind everything (z 1045
# under 20000), and its box took the keyboard 400 ms later: the next scan went into that
# hidden box and never reached the audit. RED on e7886e9 (each case's first assertion).

LOOSE = "#fcc-loose-list"
LOOSE_ROW = LOOSE + " .fcc-loose-row.kb-active"
LOOSE_ANSWER = {"read_ok": True, "read_error": None, "count": 1, "places": [
    {"id": "A-ROOM", "name": "A Room", "type": "Room", "spools": [
        {"id": 8001, "display": "#8001 Some Brand PLA (Gold)", "color": "F9E352",
         "color_direction": "longitudinal", "remaining_weight": 912}]}]}
PICKER = "#fcc-legacy-picker-overlay"
SHORTCUTS = "#fcc-shortcuts-overlay"
SEARCH_SHUT = "() => !document.getElementById('offcanvasSearch').classList.contains('show')"
OVERLAYS = "() => Array.from(document.querySelectorAll('[data-overlay-mount=\"1\"]')).map((e) => e.id)"


def _search_stays_shut(page: Page, keys: str = "/"):
    page.keyboard.press(keys)
    page.wait_for_timeout(900)                       # the offcanvas's show, and its box's 400 ms focus
    assert page.evaluate(SEARCH_SHUT), "the global search opened behind the audit"
    assert page.evaluate("() => document.getElementById('global-search-query') !== document.activeElement")


def _reaches_fcc(page: Page, server, text: str = "ID:99"):
    """A scan typed as a scanner types it reaches /api/identify_scan."""
    before = len(getattr(server, "sources", []))
    page.keyboard.type(text, delay=5)
    page.keyboard.press("Enter")
    deadline = time.monotonic() + 5
    while len(getattr(server, "sources", [])) == before and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    assert [t for t, _s in getattr(server, "sources", [])[before:]] == [text]


def test_a_slash_under_the_loose_list_opens_no_search_and_the_next_scan_reaches_the_audit(page: Page, base_url: str):
    server = _running(page, base_url)
    page.route("**/api/loose_spools", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(LOOSE_ANSWER)))
    page.click("#fcc-audit-panel-loose")
    expect(page.locator(LOOSE_ROW)).to_be_focused()
    page.wait_for_timeout(800)                       # past the 🔎/🧺 press's second-press window
    _search_stays_shut(page)
    expect(page.locator(LOOSE_ROW)).to_be_focused()  # the list kept it, and the keyboard
    assert page.evaluate("state.scanBuffer") == ""   # the '/' joins no scan
    _reaches_fcc(page, server)
    assert server.writes == []


def test_a_slash_under_dones_question_opens_no_search_and_its_qr_still_answers_it(page: Page, base_url: str):
    server = _running(page, base_url)
    page.evaluate("(q) => window.askAuditDone(q)", _question(park=1))
    back = "#fcc-audit-done-question .fcc-apc-no"
    expect(page.locator(back)).to_be_focused()
    _search_stays_shut(page)
    expect(page.locator(back)).to_be_focused()
    sid = page.evaluate("Object.keys(window._fccActiveConfirms).pop()")
    page.keyboard.type(f"CMD:CANCEL:{sid}", delay=0)
    page.keyboard.press("Enter")
    expect(page.locator("#fcc-audit-done-question")).to_have_count(0)
    assert page.evaluate(OVERLAYS) == [PANEL[1:]]
    assert server.writes == []


def test_a_slash_on_the_legacy_picker_opens_no_search(page: Page, base_url: str):
    server = _running(page, base_url)
    server.answers["LEG:120"] = LEGACY
    page.evaluate("() => window.processScan('LEG:120', 'barcode')")
    use = "#fcc-legacy-picker-use"
    expect(page.locator(use)).to_be_focused()
    _search_stays_shut(page)
    expect(page.locator(use)).to_be_focused()
    page.keyboard.press("Escape")                    # the picker's own Cancel: only it goes
    expect(page.locator(PICKER)).to_have_count(0)
    assert page.evaluate(OVERLAYS) == [PANEL[1:]]


def test_a_slash_with_the_shortcut_list_over_find_opens_no_search_and_escape_closes_only_the_list(
        page: Page, base_url: str):
    """The list says '/' is Find's "Back to the box": read, not pressed through. RED on
    e7886e9, where the search opened behind, the next Escape hid the audit's panel (the
    list's Escape skips a box's keys) and the scan went into the search's box."""
    server = _running(page, base_url)
    page.click(FIND_BTN)
    expect(page.locator(FIND_BOX)).to_be_focused()
    page.focus(FIND + " [data-find-close]")          # off the box, where '/' would be the box's own
    page.keyboard.press("?")
    expect(page.locator(SHORTCUTS)).to_be_visible()
    _search_stays_shut(page)
    page.keyboard.press("Escape")
    expect(page.locator(SHORTCUTS)).to_be_hidden()
    assert page.evaluate(OVERLAYS) == [PANEL[1:], FIND[1:]]
    _reaches_fcc(page, server)


def test_ctrl_k_during_an_audit_opens_no_search(page: Page, base_url: str):
    """With the panel itself on top: Ctrl+K opened the search behind it (RED on e7886e9)."""
    server = _running(page, base_url)
    page.wait_for_timeout(600)
    _search_stays_shut(page, "Control+k")
    _reaches_fcc(page, server)
    assert server.writes == []
