"""Group 49.2a: the ⚠️ Low-stock list inside the real dashboard (needs the dev
container; skipped under --offline).

/api/stock_report is stubbed with page.route, so the rows are fixed and the list
never reads dev Spoolman; opening a filament reads only its (stubbed) details.
Nothing here writes anything. The panel's own behaviour in depth is pinned
hermetically by test_low_stock_panel.py; this file checks it is wired into the
real page: the search panel's button, the real filament window, the real
heartbeat (which must never ask for the list), and Escape leaving the search
panel open.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

PANEL = "#fcc-low-stock-overlay .fcc-stock-panel"
BODY = "#fcc-low-stock-overlay [data-stock-body]"

REPORT = {
    "success": True, "threshold_g": 250.0, "filaments": 3, "spools": 6,
    "low": [
        {"filament_id": 164, "brand": "Prusament", "material": "PLA", "color_name": "Galaxy Black",
         "display": "Prusament - PLA - Galaxy Black", "color": "222222", "color_direction": "longitudinal",
         "grams": 151.0, "spools": 1, "spools_total": 3, "attributes": [], "one_off": False,
         "buy_url": "https://www.prusa3d.com/product/prusament-pla-galaxy-black/"},
        {"filament_id": 88, "brand": "Overture", "material": "PETG", "color_name": "Red Blue",
         "display": "Overture - PETG - Red Blue", "color": "BA0C2F,0047BB", "color_direction": "coaxial",
         "grams": 220.4, "spools": 2, "spools_total": 2, "attributes": ["Silk", "One-off"], "one_off": True,
         "buy_url": None},
    ],
    "out": [
        {"filament_id": 20, "brand": "Generic", "material": "PLA", "color_name": "Lipstick Red",
         "display": "Generic - PLA - Lipstick Red", "color": "ff0000", "color_direction": "longitudinal",
         "grams": 0, "spools": 0, "spools_total": 2, "attributes": ["For Infill"], "one_off": False,
         "buy_url": "https://shop.example/s?q=Generic+PLA+Lipstick%20Red"},
    ],
}
FILAMENT_88 = {"id": 88, "name": "Red Blue", "material": "PETG", "color_hex": "BA0C2F",
               "multi_color_hexes": "BA0C2F,0047BB", "vendor": {"id": 1, "name": "Overture"},
               "extra": {"filament_attributes": ["Silk", "One-off"]}}


def _stub_report(page, body, status=200, seen=None):
    def handle(route):
        if seen is not None:
            seen.append(route.request.url)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
    page.route("**/api/stock_report", handle)


def _open_search(page, base_url, reset_dom_state_js):
    page.goto(base_url)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("() => window.SearchEngine && typeof window.openLowStockPanel === 'function'")
    page.evaluate("SearchEngine.open()")
    expect(page.locator("#offcanvasSearch")).to_be_visible()
    expect(page.locator("#global-search-low-stock")).to_be_visible()


def _wait_state(page, name):
    page.wait_for_function(
        "(n) => { const b = document.querySelector(" + json.dumps(BODY) + "); return b && b.dataset.stockState === n; }",
        arg=name, timeout=10000)


@pytest.mark.usefixtures("require_server")
def test_the_button_sits_in_the_search_panels_header_row(page: Page, base_url: str, reset_dom_state_js: str):
    """It shares the row with Refresh and Reset (no wrap: the empty-search visual
    baseline only gains the button itself)."""
    _open_search(page, base_url, reset_dom_state_js)
    low = page.locator("#global-search-low-stock").bounding_box()
    refresh = page.locator("#global-search-refresh").bounding_box()
    toggle = page.locator("label[for='searchTypeSpools']").bounding_box()
    assert abs(low["y"] - refresh["y"]) < 2 and abs(low["y"] - toggle["y"]) < 6
    assert low["x"] + low["width"] <= refresh["x"]


@pytest.mark.usefixtures("require_server")
def test_the_button_opens_the_list_low_then_out(page: Page, base_url: str, reset_dom_state_js: str):
    _stub_report(page, REPORT)
    _open_search(page, base_url, reset_dom_state_js)
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "ready")
    rows = page.locator(PANEL + " .fcc-stock-row")
    expect(rows).to_have_count(3)
    assert [rows.nth(i).get_attribute("data-kind") for i in range(3)] == ["low", "low", "out"]
    assert "kb-active" in (rows.nth(0).get_attribute("class") or "")
    expect(page.locator(PANEL + " .fcc-stock-h").first).to_have_text("Low: under 250 g (2)")
    expect(rows.nth(0).locator("a.fcc-stock-buy")).to_have_attribute(
        "href", "https://www.prusa3d.com/product/prusament-pla-galaxy-black/")
    expect(rows.nth(1).locator("a.fcc-stock-buy")).to_have_count(0)


@pytest.mark.usefixtures("require_server")
def test_enter_opens_the_real_filament_window(page: Page, base_url: str, reset_dom_state_js: str):
    _stub_report(page, REPORT)
    page.route("**/api/filament_details*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(FILAMENT_88)))
    _open_search(page, base_url, reset_dom_state_js)
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "ready")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(page.locator("#filamentModal")).to_be_visible()
    expect(page.locator("#fil-detail-id")).to_have_text("88")
    expect(page.locator("#fcc-low-stock-overlay")).to_have_count(0)
    # Showing a modal collapses the search panel (inv_core.js), as a result card does.
    expect(page.locator("#offcanvasSearch")).not_to_be_visible()


@pytest.mark.usefixtures("require_server")
def test_spoolman_down_shows_an_error_not_an_empty_list(page: Page, base_url: str, reset_dom_state_js: str):
    _stub_report(page, {"success": False, "error": "spoolman_unreachable",
                        "msg": "Spoolman didn't answer, so FCC can't tell what is low right now."}, status=502)
    _open_search(page, base_url, reset_dom_state_js)
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "error")
    expect(page.locator(BODY)).to_contain_text("Spoolman didn't answer")
    expect(page.locator(BODY)).not_to_contain_text("Nothing is low")
    expect(page.locator(PANEL + " .fcc-stock-row")).to_have_count(0)


@pytest.mark.usefixtures("require_server")
def test_nothing_low(page: Page, base_url: str, reset_dom_state_js: str):
    _stub_report(page, {"success": True, "threshold_g": 250.0, "low": [], "out": [], "filaments": 9, "spools": 20})
    _open_search(page, base_url, reset_dom_state_js)
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "empty")
    expect(page.locator(BODY)).to_contain_text("Nothing is low.")


@pytest.mark.usefixtures("require_server")
def test_escape_closes_the_list_and_leaves_the_search_panel_open(page: Page, base_url: str,
                                                                reset_dom_state_js: str):
    _stub_report(page, REPORT)
    _open_search(page, base_url, reset_dom_state_js)
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "ready")
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-low-stock-overlay")).to_have_count(0)
    expect(page.locator("#offcanvasSearch")).to_be_visible()


@pytest.mark.usefixtures("require_server")
def test_the_dashboard_never_asks_for_the_list_on_its_own(page: Page, base_url: str, reset_dom_state_js: str):
    """Not at load, not on the 5 s heartbeat: only when the panel opens (Group
    45.8's lesson: nothing heavy on the heartbeat)."""
    seen = []
    _stub_report(page, REPORT, seen=seen)
    _open_search(page, base_url, reset_dom_state_js)
    page.wait_for_timeout(6500)
    assert seen == []
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "ready")
    page.wait_for_timeout(6500)
    assert len(seen) == 1
