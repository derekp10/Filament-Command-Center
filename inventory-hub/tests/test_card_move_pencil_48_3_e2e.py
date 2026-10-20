"""Group 48.3 — a ✏️ beside a search or buffer card's 📍 badge moves the spool.

Derek, 2026-10-19 (option B): the badge keeps opening the location; a separate
✏️ beside it moves the spool through Force Location, as the spool window's pair
does. Force Location was tied to the spool window (its dialog mounted on
#spoolModal), so from a card it now mounts on the page, the search panel closes
first, a buffer card's spool leaves the buffer once the move lands, and a box
opens the slot picker exactly as from the spool window. No new write path.

HERMETIC AGAINST DEV DATA: the buffer is the page's own (own_the_buffer), the
location list, the search answer, the placement model and every POST are
routed; nothing reaches dev's Spoolman or its shared buffer.
Base proof (52741e6): the cards have no ✏️, so every test fails.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

import conftest
from test_slot_picker_e2e import ROWS as PICKER_ROWS, build_model

pytestmark = pytest.mark.usefixtures("require_server")

SID = 999501
SPOOL = {"id": SID, "display": f"#{SID} FCC Test PLA (Test Red)", "color": "cc2222", "location": "FCC-TEST-SHELF",
         "remaining_weight": 640, "is_ghost": False, "archived": False,
         "details": {"brand": "FCC Test", "material": "PLA", "color_name": "Test Red", "weight": 640}}
LOCS = PICKER_ROWS + [{"LocationID": "FCC-TEST-CART", "Name": "Cart (test)", "Type": "Cart", "Max Spools": "0"}]
CARD_BTN = "#buffer-zone .fcc-card-move-btn"
POPUP = ".swal2-popup"


def _json(route, payload, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))


def _setup(page: Page, base_url: str, buffer=(SPOOL,)):
    posts = []
    conftest.own_the_buffer(page, list(buffer))
    conftest.quiet_heartbeat(page)

    def locations(route):
        if route.request.method == "GET":
            _json(route, LOCS)
        else:
            route.continue_()

    def manage(route):
        posts.append(route.request.post_data_json)
        _json(route, {"status": "success", "failures": {}})

    page.route("**/api/locations", locations)
    page.route("**/api/manage_contents", manage)
    page.route("**/api/spools/refresh", lambda route: _json(route, {str(SID): {
        k: SPOOL[k] for k in ("display", "color", "location", "remaining_weight", "details", "is_ghost", "archived")}}))
    page.route("**/api/placement_options*", lambda route: _json(
        route, build_model("FCC-TEST-BOX", spool=SID)))
    page.route("**/api/printer_state/**", lambda route: _json(
        route, {"known": True, "is_active": False, "state": "IDLE", "printer_name": "FCC Test XL"}))
    page.route("**/api/search*", lambda route: _json(route, {"success": True, "results": [SPOOL]}))
    page.goto(base_url)
    page.wait_for_function("typeof window.moveSpoolFromCard === 'function'", timeout=10000)
    expect(page.locator(CARD_BTN)).to_have_count(1 if buffer else 0, timeout=10000)
    return posts


def _buffer(page):
    return page.evaluate("() => state.heldSpools.map(s => s.id)")


def _choose(page, loc):
    page.locator(f"{POPUP} .swal-loc-item[data-id='{loc}']").click()
    page.locator(f"{POPUP} .swal2-confirm").click()


def test_a_buffer_cards_pencil_moves_it_with_the_spool_window_closed(page: Page, base_url: str):
    posts = _setup(page, base_url)
    page.locator(CARD_BTN).click()
    expect(page.locator(POPUP)).to_be_visible(timeout=5000)
    expect(page.locator("#spoolModal")).not_to_be_visible()
    expect(page.locator(f"{POPUP} #swal-override-search")).to_be_focused()
    _choose(page, "FCC-TEST-CART")
    page.wait_for_function(f"() => !state.heldSpools.some(s => s.id === {SID})", timeout=5000)
    [post] = posts
    assert (post["action"], post["location"], post["spool_id"], post["origin"]) == (
        "add", "FCC-TEST-CART", str(SID), "manual_override"), post
    assert _buffer(page) == []


def test_escape_moves_nothing(page: Page, base_url: str):
    posts = _setup(page, base_url)
    page.locator(CARD_BTN).click()
    expect(page.locator(POPUP)).to_be_visible(timeout=5000)
    page.keyboard.press("Escape")
    page.locator("#fcc-escape-yes").click()
    expect(page.locator(POPUP)).not_to_be_visible(timeout=5000)
    assert posts == [] and _buffer(page) == [SID]


def test_a_box_opens_the_slot_picker_as_from_the_spool_window(page: Page, base_url: str):
    posts = _setup(page, base_url)
    page.locator(CARD_BTN).click()
    expect(page.locator(POPUP)).to_be_visible(timeout=5000)
    _choose(page, "FCC-TEST-BOX")
    expect(page.locator("#fcc-slot-picker [data-sp-state='ready']")).to_be_visible(timeout=8000)
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-slot-picker")).to_have_count(0, timeout=5000)
    assert posts == [] and _buffer(page) == [SID]


def test_the_pencil_is_a_keyboard_button(page: Page, base_url: str, assert_contrast):
    _setup(page, base_url)
    btn = page.locator(CARD_BTN)
    assert btn.evaluate("el => el.tagName") == "BUTTON"
    assert_contrast(btn)
    btn.focus()
    page.keyboard.press("Space")
    expect(page.locator(POPUP)).to_be_visible(timeout=5000)


def test_the_badge_itself_still_opens_the_location(page: Page, base_url: str):
    _setup(page, base_url)
    page.locator("#buffer-zone .loc-badge-hover").first.click()
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    expect(page.locator(POPUP)).to_have_count(0)


def test_a_search_cards_pencil_closes_the_search_panel_first(page: Page, base_url: str):
    _setup(page, base_url, buffer=())
    page.locator('nav button:has-text("SEARCH")').click()
    page.locator("#global-search-query").fill("test")
    pencil = page.locator("#offcanvasSearch .fcc-card-move-btn")
    expect(pencil).to_have_count(1, timeout=8000)
    pencil.click()
    expect(page.locator(POPUP)).to_be_visible(timeout=5000)
    expect(page.locator("#offcanvasSearch")).not_to_have_class("offcanvas show", timeout=5000)
    expect(page.locator(f"{POPUP} #swal-override-search")).to_be_focused()
