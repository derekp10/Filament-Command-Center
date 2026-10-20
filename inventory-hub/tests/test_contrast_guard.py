"""
Contrast guard — catches gray-on-gray text anywhere inside the Phase 2/3
overlays and sections.

Background: we've chased the same class of bug repeatedly this round —
someone drops a Bootstrap `text-muted` onto a `bg-dark` surface and the
text becomes unreadable. Visual snapshots only catch the specific
placements they happen to capture; this test walks EVERY text-bearing
element in each new surface and asserts computed contrast meets
WCAG AA. If any future change re-introduces low-contrast text, this
fires with a list of exactly which elements.

Uses the `assert_contrast` fixture from conftest.py.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_slot(borrow_box_bindings):
    """Bind PM-DB-1 slot 1 -> XL-1 so the Quick-Swap grid and Bind picker
    render populated rows. PM-DB-1 must be at its fixed baseline first and is
    put back to that baseline afterwards (conftest `borrow_box_bindings`)."""
    borrow_box_bindings(TEST_BOX, {"1": TEST_TOOLHEAD})


# ---------------------------------------------------------------------------
# Bind picker — the immediate offender that prompted this fix
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    """The exact surface the user reported. Opens the picker, asserts
    every slot-row label meets AA contrast."""
    open_manage_modal(TEST_TOOLHEAD)
    page.locator("#quickswap-bind-slot-btn").click()
    overlay = page.locator("#fcc-bind-picker-overlay")
    # Bind picker fetches /api/dryer_boxes/slots before opening; 8s gives
    # headroom under sweep load, same pattern as other Group 9 timeouts.
    expect(overlay).to_be_visible(timeout=8000)
    # Let the slots list populate.
    expect(page.locator(".fcc-bind-picker-item").first).to_be_visible(timeout=3000)
    assert_contrast(overlay)


# ---------------------------------------------------------------------------
# Quick-Swap grid — populated toolhead view
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_section_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=8000)
    assert_contrast(page.locator("#manage-quickswap-section"))


# ---------------------------------------------------------------------------
# Feeds editor — open state on a Dryer Box
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_feeds_section_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    open_manage_modal(TEST_BOX)
    # Feeds starts collapsed; open it so the rows render and get asserted.
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(400)
    assert_contrast(page.locator("#manage-feeds-section"))


# ---------------------------------------------------------------------------
# Confirm overlay — swap prompt
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_confirm_overlay_has_no_gray_on_gray_text(page: Page, open_manage_modal, assert_contrast):
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=8000)
    # Return-to-Slot opens the confirm overlay without needing a loaded spool
    # (it'll land on "nothing to return" if the toolhead is empty, which
    # still renders the same overlay shell we want to check).
    page.locator("#quickswap-return-btn").click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # Group 40.6: a spool with no obvious slot opens the slot picker before the
    # confirm; Enter takes its highlight (nothing is written: no Yes here).
    page.wait_for_function(
        "!!document.getElementById('fcc-quickswap-confirm-overlay')"
        " || !!document.querySelector('#fcc-slot-picker [data-sp-state=\"ready\"]')", timeout=8000)
    if page.evaluate("!!document.querySelector('#fcc-slot-picker [data-sp-state=\"ready\"]')"):
        page.keyboard.press("Enter")
    # Overlay mount awaits a 3s active-print probe; 8s gives headroom
    # under sweep load (same fix as Group 14.2).
    expect(overlay).to_be_visible(timeout=8000)
    assert_contrast(overlay)


# ---------------------------------------------------------------------------
# Shortcuts overlay (? help)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_shortcuts_overlay_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    overlay = page.locator("#fcc-shortcuts-overlay")
    expect(overlay).to_be_visible(timeout=3000)
    assert_contrast(overlay)


# ---------------------------------------------------------------------------
# Printer Status widget (Group 9.3) — both expanded and collapsed views
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_printer_status_widget_expanded_has_no_gray_on_gray_text(
    page: Page, base_url: str, assert_contrast
):
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('#printer-status-widget .fcc-ps-th')",
        timeout=8000,
    )
    assert_contrast(page.locator("#printer-status-widget"))


@pytest.mark.usefixtures("require_server")
def test_low_stock_panel_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    """Group 49.2a — the ⚠️ Low-stock list over the real dashboard: its rows (one
    highlighted), tags and Buy More links, its error state, and the search
    panel's button that opens it. /api/stock_report is stubbed, so no dev data
    is read. (Hermetic twin: test_low_stock_panel.py.)"""
    import json as _json
    answers = [
        (200, {
            "success": True, "threshold_g": 250.0, "filaments": 2, "spools": 3,
            "low": [{"filament_id": 88, "display": "Overture - PETG - Red Blue", "color": "BA0C2F,0047BB",
                     "color_direction": "coaxial", "grams": 220.4, "spools": 2, "spools_total": 2,
                     "attributes": ["Silk", "One-off"], "one_off": True,
                     "buy_url": "https://shop.example/s?q=Overture"}],
            "out": [{"filament_id": 20, "display": "Generic - PLA - Lipstick Red", "color": "ff0000",
                     "color_direction": "longitudinal", "grams": 0, "spools": 0, "spools_total": 1,
                     "attributes": [], "one_off": False, "buy_url": None}]}),
        (502, {"success": False, "error": "spoolman_unreachable", "msg": "x"}),
    ]

    def _answer(route):
        status, body = answers.pop(0) if len(answers) > 1 else answers[0]
        route.fulfill(status=status, content_type="application/json", body=_json.dumps(body))
    page.route("**/api/stock_report", _answer)
    page.goto(base_url)
    page.wait_for_function("() => window.SearchEngine && typeof window.openLowStockPanel === 'function'")
    page.evaluate("SearchEngine.open()")
    expect(page.locator("#global-search-low-stock")).to_be_visible()
    assert_contrast(page.locator("#global-search-low-stock"))
    page.locator("#global-search-low-stock").click()
    panel = page.locator("#fcc-low-stock-overlay .fcc-stock-panel")
    expect(panel.locator(".fcc-stock-row.kb-active")).to_have_count(1)
    assert_contrast(panel)
    page.evaluate("window.openLowStockPanel()")      # the error state
    expect(panel.locator("[role=alert]")).to_be_visible()
    assert_contrast(panel)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_printer_status_widget_collapsed_has_no_gray_on_gray_text(
    page: Page, base_url: str, assert_contrast
):
    """Collapsed strip recurringly hits the text-muted footgun — pinned
    here so it can't slip back in. Empty toolheads' "empty" label is a
    common offender (Bootstrap text-muted is too dark for our bg)."""
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function(
        "() => document.querySelector('#printer-status-widget .fcc-ps-th')",
        timeout=8000,
    )
    page.locator("#printer-status-widget .fcc-ps-header-bar").click()
    expect(page.locator("#printer-status-widget .fcc-ps-header-chips")).to_be_visible(
        timeout=2000
    )
    assert_contrast(page.locator("#printer-status-widget"))


# ---------------------------------------------------------------------------
# Spool window — the slicer profile row (Group 48.2)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_spool_window_slicer_profile_row_is_readable(page: Page, base_url: str, assert_contrast):
    """Stubbed spool, so dev data can't change what is drawn."""
    import json as _json
    payload = {"id": 999001, "archived": False, "location": "Room LR", "comment": "", "used_weight": 100.0,
               "remaining_weight": 900.0, "extra": {},
               "filament": {"id": 555001, "name": "Test Color", "material": "PLA", "color_hex": "ff8800",
                            "weight": 1000, "vendor": {"name": "TestVendor"},
                            "extra": {"slicer_profile": '"Prusament PLA"'}}}
    page.route("**/api/spool_details*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=_json.dumps(payload)))
    page.goto(base_url)
    page.wait_for_function("typeof openSpoolDetails === 'function' && modals && modals.spoolModal", timeout=10000)
    page.evaluate("openSpoolDetails(999001)")
    row = page.locator("#spool-detail-slicer-profile-row")
    expect(row).to_contain_text("Prusament PLA", timeout=5000)
    assert_contrast(row)
