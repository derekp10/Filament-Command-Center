"""Group 58's review on the real dashboard, with Bootstrap, the page's own polls and a real
keyboard: what sits on what during an audit, and where the keyboard goes. Every test
answers FCC's routes in this browser, on their real shapes (test_audit_page_58_js.SESSION
and the rest are pinned to them), so nothing reaches a real session or dev's spools.

The rules are proved on the real routes in test_audit_stacking_58_js.py and
test_audit_no_label_58_js.py; this is the same flows where the real stacking, the real
Bootstrap sizes and a real Location Manager can get in the way.

RED before the review's fixes, unless a test says it pins what was already right.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from test_audit_done_question_58_e2e import BACK, QUESTION, Asked, _long_audit, _on_top, _scan_keys
from test_audit_no_label_58_e2e import BUTTON, FOUND, MARK, NOT_SCANNED, UNDO, _running, tile
from test_audit_no_label_58_js import PAST_N, walked
from test_audit_page_58_e2e import CANCEL, DONE, PANEL, _dashboard, _start
from test_scanner_safe_dialogs_61_js import LEGACY

pytestmark = pytest.mark.usefixtures("require_server")

SHORTCUTS = "#fcc-shortcuts-overlay"
LOOSE = "#fcc-loose-list"
ROW = LOOSE + " .fcc-loose-row.kb-active"
PICKER = "#fcc-legacy-picker-overlay"
USE = "#fcc-legacy-picker-use"
FLASH = "#fcc-legacy-picker-flash"
LOOSE_ANSWER = {"read_ok": True, "read_error": None, "count": 1, "places": [
    {"id": "A-ROOM", "name": "A Room", "type": "Room", "spools": [
        {"id": 8001, "display": "#8001 Some Brand PLA (Gold)", "color": "F9E352",
         "color_direction": "longitudinal", "remaining_weight": 912}]}]}
CR_LF = 120                     # past a scanner's second Enter: a person's Enter again


def _help(page: Page):
    page.keyboard.press("?")
    expect(page.locator(SHORTCUTS)).to_be_visible()


def _loose_up(page: Page):
    page.route("**/api/loose_spools", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(LOOSE_ANSWER)))
    page.click("#fcc-audit-panel-loose")
    expect(page.locator(ROW)).to_have_count(1)


def _picker_up(page: Page, server):
    server.answers["LEG:120"] = LEGACY
    _scan_keys(page, "LEG:120")
    expect(page.locator(PICKER)).to_be_visible()
    expect(page.locator(USE)).to_be_focused()
    page.wait_for_timeout(CR_LF)


@pytest.mark.parametrize("width, height", [(1600, 1300), (1366, 768)])
def test_the_list_hit_tests_on_top_of_the_real_panel_and_escape_leaves_the_panel(page: Page, base_url: str, width, height):
    """Findings 24 and 42, with the real sizes: at 1366 x 768 only a sliver of it showed,
    and the keys were dead with no sign why. After Escape they all work: N, the arrows
    and Enter. RED before the fix at the hit test: the list's centre was the panel."""
    page.set_viewport_size({"width": width, "height": height})
    server = _running(page, base_url)
    page.click(tile(NOT_SCANNED))
    page.wait_for_selector(BUTTON)
    page.focus(BUTTON)
    _help(page)
    assert _on_top(page, SHORTCUTS)
    expect(page.locator("#fcc-shortcuts-list")).to_contain_text("Audit Panel")

    page.keyboard.press("Enter")
    page.keyboard.press("n")
    page.wait_for_timeout(PAST_N)
    assert server.scans == ["CMD:AUDIT"] and server.pressed == [{"audit_id": "boot-1", "id": NOT_SCANNED, "found": True}]

    page.keyboard.press("Escape")
    expect(page.locator(SHORTCUTS)).to_be_hidden()
    expect(page.locator(PANEL)).to_be_visible()
    assert page.evaluate("state.auditActive") is True

    page.wait_for_timeout(520)                  # the n in the scan buffer, under an Enter
    page.keyboard.press("ArrowRight")
    expect(page.locator(tile(FOUND))).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(page.locator(tile(NOT_SCANNED))).to_be_focused()
    page.keyboard.press("n")
    expect(page.locator(UNDO)).to_be_visible()
    assert server.scans == ["CMD:AUDIT", MARK]


def test_space_under_the_list_cant_cancel_the_audit(page: Page, base_url: str):
    """The list hides the focused button, and a Space isn't an Enter: nothing stopped it."""
    server = _running(page, base_url)
    page.locator(CANCEL).scroll_into_view_if_needed()
    page.focus(CANCEL)
    _help(page)
    page.keyboard.press(" ")
    page.wait_for_timeout(200)
    assert server.scans == ["CMD:AUDIT"] and page.evaluate("state.auditActive") is True


def test_the_list_draws_over_the_question_too(page: Page, base_url: str):
    server = Asked(page)
    _dashboard(page, base_url)
    _start(page)
    page.click(DONE)
    expect(page.locator(BACK)).to_be_focused()
    _help(page)
    assert _on_top(page, SHORTCUTS)
    page.keyboard.press("Escape")
    expect(page.locator(SHORTCUTS)).to_be_hidden()
    expect(page.locator(QUESTION)).to_be_visible()
    assert server.parks == []


def test_a_legacy_label_under_the_loose_list_opens_on_top_and_takes_a_persons_enter(page: Page, base_url: str):
    """Finding 25. RED before the fix: the picker was wholly covered by the list, and a
    person's Enter was the list's."""
    server = _running(page, base_url)
    _loose_up(page)
    _picker_up(page, server)
    assert _on_top(page, USE) and _on_top(page, "#fcc-legacy-picker-cancel") and _on_top(page, "#fcc-legacy-picker-sel")
    page.select_option("#fcc-legacy-picker-sel", "135")
    page.focus(USE)
    page.keyboard.press("Enter")
    page.wait_for_function("() => !state.processing")
    expect(page.locator(PICKER)).to_have_count(0)
    assert server.scans[-1] == "ID:135"
    expect(page.locator(LOOSE)).to_have_count(1)


def test_a_listed_spools_own_label_reaches_the_picker_under_the_loose_list(page: Page, base_url: str):
    """A pin: a scan goes by the open question, not by what is drawn on top. Its hermetic twin
    is proved on a broken copy."""
    server = _running(page, base_url)
    _loose_up(page)
    _picker_up(page, server)
    _scan_keys(page, "ID:134")
    expect(page.locator(PICKER)).to_have_count(0)
    assert server.scans[-1] == "ID:134"


def test_escape_closes_only_the_picker_over_the_loose_list(page: Page, base_url: str):
    server = _running(page, base_url)
    _loose_up(page)
    _picker_up(page, server)
    page.keyboard.press("Escape")
    expect(page.locator(PICKER)).to_have_count(0)
    expect(page.locator(LOOSE)).to_have_count(1)
    expect(page.locator(PANEL)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(LOOSE)).to_have_count(0)
    expect(page.locator(PANEL)).to_be_visible()
    assert page.evaluate("state.auditActive") is True


def test_use_selected_with_nothing_picked_says_so_on_the_real_page(page: Page, base_url: str):
    """Finding 39. RED before the fix: the picker closed, and the audit knew nothing."""
    server = _running(page, base_url)
    _picker_up(page, server)
    before = list(server.scans)
    page.keyboard.press("Enter")
    expect(page.locator(FLASH)).to_have_text("Pick a spool first")
    expect(page.locator(PICKER)).to_be_visible()
    expect(page.locator("#fcc-legacy-picker-sel")).to_be_focused()
    assert _on_top(page, FLASH) and server.scans == before


def test_the_walk_from_the_review_stays_in_the_loose_list(page: Page, base_url: str):
    """Finding 27: Shift+Tab from the first row reached Cancel Audit in two, behind the
    list. RED before the fix."""
    server = _running(page, base_url)
    _loose_up(page)
    for _ in range(6):
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("(s) => !!document.activeElement.closest(s)", LOOSE)
    page.keyboard.press(" ")
    page.wait_for_timeout(200)
    assert server.scans == ["CMD:AUDIT"] and page.evaluate("state.auditActive") is True


def test_tab_stays_on_the_real_panel(page: Page, base_url: str):
    """The page behind has hundreds of stops, and the mouse can't reach one of them. RED
    before the fix: past Cancel Audit the keyboard went out to the page."""
    _running(page, base_url)
    page.locator(CANCEL).scroll_into_view_if_needed()
    page.focus(CANCEL)
    page.keyboard.press("Tab")
    expect(page.locator("#fcc-audit-panel-loose")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(page.locator(CANCEL)).to_be_focused()


@pytest.mark.parametrize("width, height, size", [(1366, 768, "Standard"), (1366, 768, "Extra Large"), (1600, 1000, "Standard")])
def test_every_tile_the_keyboard_reaches_is_in_view_on_the_real_panel(page: Page, base_url: str, width, height, size):
    """Finding 37, at the sizes the review measured, with the real Bootstrap and the strip
    up: the arrows both ways, then Tab both ways. RED before the fix: the strip covered
    12 of 30 tiles at 1366 x 768."""
    page.add_init_script("(() => { try { localStorage.setItem('fcc.textSize', %r); } catch (e) {} })();" % size)
    _long_audit(page, base_url, width, height, rows=30)
    expect(page.locator(BUTTON)).to_be_visible()
    ids = list(range(100, 130))

    def hidden(key, steps):
        return [sid for sid, shown in walked(page, key, steps) if not shown]

    assert hidden("ArrowRight", len(ids) + 1) == []
    assert hidden("ArrowLeft", len(ids) + 1) == []
    page.focus(tile(ids[0]))
    assert hidden("Tab", len(ids) - 1) == []
    assert hidden("Shift+Tab", len(ids) - 1) == []


def test_a_strip_that_appears_leaves_the_keyboards_tile_in_view(page: Page, base_url: str):
    """The first find draws the strip, and its QR comes two frames later: with an empty QR
    box the tile was scrolled clear of a strip 80 px short of its real size, and went
    under it when the QR drew. RED with no size on the box."""
    server = _long_audit(page, base_url, 1366, 768, rows=30)
    found = server.session
    server.session = dict(found, last_found=None)
    page.evaluate("window.refreshAuditSession()")
    expect(page.locator(BUTTON)).to_have_count(0)
    in_view = page.evaluate("""() => { const b = document.querySelector('#fcc-audit-panel-body').getBoundingClientRect();
        return Array.from(document.querySelectorAll('.fcc-audit-tile'))
            .filter((t) => t.getBoundingClientRect().bottom < b.bottom).length; }""")
    walked(page, "ArrowRight", in_view)         # a real keyboard, to the lowest tile in view
    at = page.evaluate("document.activeElement.dataset.auditTile")
    server.session = found
    page.evaluate("window.refreshAuditSession()")
    expect(page.locator(BUTTON)).to_be_visible()
    page.wait_for_timeout(200)                  # the QR draws two frames later
    assert page.locator("#fcc-audit-panel-qr-needlabel").bounding_box()["height"] >= 80
    assert page.evaluate("document.activeElement.dataset.auditTile") == at
    assert _on_top(page, tile(at))


def test_a_click_on_a_tile_half_under_the_strip_still_presses_it_on_the_real_panel(page: Page, base_url: str):
    """A pin: a tile pressed this close to the edge and scrolled clear of it between mousedown
    and mouseup leaves the pointer in the gap between tiles, which is a click on no tile."""
    server = _long_audit(page, base_url, 1366, 768, rows=30)
    expect(page.locator(BUTTON)).to_be_visible()
    aim = page.evaluate("""([body, strip]) => {
        const b = document.querySelector(body);
        const line = document.querySelector(strip).getBoundingClientRect().top;
        const t = Array.from(document.querySelectorAll('.fcc-audit-tile'))
            .find((el) => el.getBoundingClientRect().top > line + 200);
        b.scrollTop += t.getBoundingClientRect().top + 12 - line;
        const now = t.getBoundingClientRect();
        return { id: Number(t.dataset.auditTile), x: now.left + now.width / 2, y: now.top + 9, hit: now.top - line }; }""",
                        ["#fcc-audit-panel-body", "#fcc-audit-last-found"])
    assert aim["hit"] == pytest.approx(-12, abs=1)      # it really is under the strip's edge
    page.mouse.click(aim["x"], aim["y"])
    page.wait_for_timeout(200)
    assert [p["id"] for p in server.found] == [aim["id"]]


def test_back_on_a_hidden_panel_over_the_location_manager_hands_the_keyboard_to_done(page: Page, base_url: str):
    """Finding 41, as the review met it: the panel hidden, the Location Manager open, its QR
    or a label reading CMD:DONE, and Back. RED before the fix: the focus fell to the
    page, and Enter did nothing."""
    Asked(page)
    _dashboard(page, base_url)
    page.wait_for_function("() => state.locationsLoaded", timeout=45_000)
    _start(page)
    page.click("#fcc-audit-panel-close")
    expect(page.locator(PANEL)).to_have_count(0)
    place = page.evaluate("() => state.allLocations.find((l) => l.Type === 'Dryer Box').LocationID")
    page.evaluate("(p) => { window.openManage(p); }", place)
    expect(page.locator("#manageModal")).to_be_visible()
    page.evaluate("() => { window.processScan('CMD:DONE', 'barcode'); }")
    expect(page.locator(BACK)).to_be_focused()
    page.wait_for_timeout(CR_LF)
    page.keyboard.press("Escape")
    expect(page.locator(QUESTION)).to_have_count(0)
    expect(page.locator(DONE)).to_be_focused()
