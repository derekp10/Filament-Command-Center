"""Group 49.2a: the ⚠️ Low-stock list inside the real dashboard (needs the dev
container; skipped under --offline).

/api/stock_report is stubbed with page.route, so the rows are fixed and the list
never reads dev Spoolman; opening a filament reads only its (stubbed) details.
Nothing here writes anything. The panel's own behaviour in depth is pinned
hermetically by test_low_stock_panel.py; this file checks it is wired into the
real page: the search panel's button, the real filament window, the real
heartbeat (which must never ask for the list), Escape leaving the search panel
open, and the exclusion dialog over the real page (its writes are
stubbed too: nothing reaches dev Spoolman).
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
         "grams": 151.0, "spools": 1, "spools_total": 3, "attributes": [], "excluded": None,
         "buy_url": "https://www.prusa3d.com/product/prusament-pla-galaxy-black/"},
        {"filament_id": 88, "brand": "Overture", "material": "PETG", "color_name": "Red Blue",
         "display": "Overture - PETG - Red Blue", "color": "BA0C2F,0047BB", "color_direction": "coaxial",
         "grams": 220.4, "spools": 2, "spools_total": 2, "attributes": ["Silk"], "excluded": None,
         "buy_url": None},
    ],
    "out": [
        {"filament_id": 20, "brand": "Generic", "material": "PLA", "color_name": "Lipstick Red",
         "display": "Generic - PLA - Lipstick Red", "color": "ff0000", "color_direction": "longitudinal",
         "grams": 0, "spools": 0, "spools_total": 2, "attributes": ["For Infill"], "excluded": None,
         "buy_url": "https://shop.example/s?q=Generic+PLA+Lipstick%20Red"},
    ],
    "excluded": [
        {"filament_id": 41, "brand": "Sunlu", "material": "PLA", "color_name": "Glow Green",
         "display": "Sunlu - PLA - Glow Green", "color": "55ff55", "color_direction": "longitudinal",
         "grams": 120.0, "spools": 2, "spools_total": 3, "attributes": [], "buy_url": None,
         "excluded": {"reason": "Discontinued", "code": "discontinued", "note": "Prusa stopped making it",
                          "at": "2026-10-20"}},
    ],
}
FILAMENT_88 = {"id": 88, "name": "Red Blue", "material": "PETG", "color_hex": "BA0C2F",
               "multi_color_hexes": "BA0C2F,0047BB", "vendor": {"id": 1, "name": "Overture"},
               "extra": {"filament_attributes": ["Silk"]}}


def _stub_report(page, body, status=200, seen=None, then=None):
    """Answers /api/stock_report with `body` (then with `then`, from the second
    request on)."""
    def handle(route):
        if seen is not None:
            seen.append(route.request.url)
        answer = then if (then is not None and seen is not None and len(seen) > 1) else body
        route.fulfill(status=status, content_type="application/json", body=json.dumps(answer))
    page.route("**/api/stock_report", handle)


def _stub_exclusion(page, sent, answer):
    """Stubs the exclusion writes: recorded in `sent`, never sent on."""
    def handle(route):
        req = route.request
        sent.append((req.method, req.url.split("/api/", 1)[1], req.post_data_json if req.post_data else None))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer))
    page.route("**/api/filament/*/stock_exclusion", handle)


def _open_search(page, base_url, reset_dom_state_js):
    page.goto(base_url)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("() => window.SearchEngine && typeof window.openLowStockPanel === 'function'")
    page.evaluate("SearchEngine.open()")
    expect(page.locator("#offcanvasSearch")).to_be_visible()
    # Visible already while it slides in (Bootstrap's `showing`): measuring two
    # buttons mid-slide read them ~1 px apart in the wrong order (bundle run).
    page.wait_for_function("() => { const o = document.getElementById('offcanvasSearch');"
                           " return !!o && o.classList.contains('show') && !o.classList.contains('showing'); }")
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
def test_the_button_opens_the_list_on_low_with_its_tabs(page: Page, base_url: str, reset_dom_state_js: str):
    _stub_report(page, REPORT)
    _open_search(page, base_url, reset_dom_state_js)
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "ready")
    counts = page.locator(PANEL + " [data-stock-count]")
    expect(counts).to_have_text(["2", "1", "1"])
    expect(page.locator(PANEL + " [data-stock-tab='low']")).to_have_attribute("aria-selected", "true")
    rows = page.locator(PANEL + " .fcc-stock-row")
    expect(rows).to_have_count(2)
    assert [rows.nth(i).get_attribute("data-kind") for i in range(2)] == ["low", "low"]
    assert "kb-active" in (rows.nth(0).get_attribute("class") or "")
    expect(rows.nth(0).locator("a.fcc-stock-buy")).to_have_attribute(
        "href", "https://www.prusa3d.com/product/prusament-pla-galaxy-black/")
    expect(rows.nth(1).locator("a.fcc-stock-buy")).to_have_count(0)
    # One line each, with the real page's styles.
    assert all(rows.nth(i).bounding_box()["height"] <= 36 for i in range(2))
    page.keyboard.press("ArrowRight")
    expect(rows).to_have_count(1)
    expect(rows.first).to_have_attribute("data-kind", "out")


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
def test_excluding_over_the_real_page(page: Page, base_url: str, reset_dom_state_js: str):
    """The reason dialog sits above the list and the search panel (the confirm
    tier), Escape closes only it, and a save posts the reason and reads the list
    again. Both requests are stubbed: nothing reaches dev Spoolman."""
    after = json.loads(json.dumps(REPORT))
    moved = after["low"].pop(0)
    moved["excluded"] = {"reason": "One-off", "code": "one_off", "note": "", "at": "2026-10-20"}
    after["excluded"].insert(0, moved)
    seen, sent = [], []
    _stub_report(page, REPORT, seen=seen, then=after)
    _stub_exclusion(page, sent, {"success": True, "filament_id": 164, "display": "Prusament - PLA - Galaxy Black",
                                "excluded": moved["excluded"], "was": None, "msg": "ok"})
    _open_search(page, base_url, reset_dom_state_js)
    page.locator("#global-search-low-stock").click()
    _wait_state(page, "ready")
    page.keyboard.press("Delete")
    dialog = page.locator("#fcc-low-stock-reason [data-stock-dialog]")
    expect(dialog).to_be_visible()
    # On top: the point at its centre is the dialog's own.
    box = dialog.bounding_box()
    top = page.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('[data-stock-dialog]')",
                        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
    assert top is True
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(page.locator(PANEL)).to_be_visible()
    expect(page.locator("#offcanvasSearch")).to_be_visible()
    page.keyboard.press("Delete")
    page.keyboard.press("ArrowDown")                          # Discontinued -> Can't find it
    page.keyboard.press("Enter")
    expect(page.locator(PANEL + " .fcc-stock-row")).to_have_count(1)
    assert [(m, u, {k: v for k, v in b.items() if k != "today"}) for m, u, b in sent] == \
        [("POST", "filament/164/stock_exclusion", {"reason": "cant_find", "note": ""})]
    assert len(seen) == 2
    expect(page.locator(PANEL + " [data-stock-count]")).to_have_text(["1", "1", "2"])


@pytest.mark.usefixtures("require_server")
def test_the_threshold_setting_renders_in_settings(page: Page, base_url: str, reset_dom_state_js: str):
    """`low_stock_g` is a plain schema Field: Settings draws it as a number input
    with no UI code of its own. Read-only: nothing is saved."""
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof window.openConfigModal === 'function'", timeout=10000)
    page.evaluate("window.openConfigModal()")
    expect(page.locator("#configModal")).to_be_visible(timeout=5000)
    field = page.locator('.cfgset-input[data-key="low_stock_g"]')
    expect(field).to_be_visible()
    assert field.evaluate("el => el.type") == "number"
    assert float(field.input_value()) >= 0


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
