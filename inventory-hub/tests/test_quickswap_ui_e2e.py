"""
UI-path E2E tests for Phase 3 Quick-Swap + shortcuts overlay.

Exercises the actual UI: opening a toolhead in Location Manager shows
the Quick-Swap grid when bindings exist, keyboard navigation highlights
buttons, Enter fires the confirm overlay, `?` toggles the shortcuts
reference, and the grid is hidden for non-toolhead locations.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"
DRYER_BOX_LOC = TEST_BOX
NON_TOOLHEAD_LOC = DRYER_BOX_LOC  # Dryer Box isn't a toolhead


@pytest.fixture
def bound_slot(api_base_url):
    """Ensure PM-DB-1 slot 1 is bound to XL-1 for the duration of the test."""
    snap = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": TEST_TOOLHEAD}},
        timeout=5,
    )
    yield
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": original},
        timeout=5,
    )


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_grid_visible_on_bound_toolhead(page: Page, open_manage_modal):
    open_manage_modal(TEST_TOOLHEAD)
    section = page.locator("#manage-quickswap-section")
    expect(section).to_be_visible()
    # With the fixture binding in place, at least one slot button renders.
    slots = page.locator(".fcc-qs-slot")
    expect(slots.first).to_be_visible(timeout=8000)


@pytest.mark.usefixtures("require_server")
def test_quickswap_grid_hidden_on_dryer_box(page: Page, open_manage_modal):
    open_manage_modal(NON_TOOLHEAD_LOC)
    expect(page.locator("#manage-quickswap-section")).to_be_hidden()


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_keyboard_q_focuses_first_slot(page: Page, open_manage_modal):
    import re
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=8000)
    page.keyboard.press("q")
    page.wait_for_timeout(200)
    first = page.locator(".fcc-qs-slot").first
    # Match any class list that contains both fcc-qs-slot and kb-active.
    expect(first).to_have_class(re.compile(r'fcc-qs-slot(?=.*\bkb-active\b)'))


@pytest.mark.usefixtures("require_server")
def test_quickswap_tap_opens_confirm_overlay(page: Page, open_manage_modal, bound_loaded_slot):
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    open_manage_modal(toolhead)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=8000)
    test_btn = page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first
    expect(test_btn).to_be_visible(timeout=3000)
    test_btn.click()
    # showConfirmOverlay awaits a ~3s active-print probe before it mounts the
    # overlay (offline dev printers hit the full timeout) — allow probe + network.
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=8000)
    expect(page.locator("#fcc-quickswap-confirm-title")).to_contain_text(box)
    expect(page.locator("#fcc-quickswap-confirm-title")).to_contain_text(toolhead)


@pytest.mark.usefixtures("require_server")
def test_quickswap_confirm_overlay_cancel_dismisses(page: Page, open_manage_modal, bound_loaded_slot):
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    open_manage_modal(toolhead)
    page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # showConfirmOverlay awaits a ~3s active-print probe before mounting; 8s
    # gives headroom for probe + network under sweep load. Same pattern as
    # test_quickswap_deposit_and_header (Group 14.2).
    expect(overlay).to_be_visible(timeout=8000)
    page.locator("#fcc-quickswap-no").click()
    expect(overlay).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server")
def test_quickswap_confirm_yes_actually_performs_swap(page: Page, open_manage_modal, bound_loaded_slot):
    """Regression guard: a duplicate window.quickSwapTap definition was
    overriding the real handler, so clicking Yes did nothing. This test
    catches that class of bug by watching the /api/quickswap request
    fire in response to the Yes click.

    The swap POST is stubbed (fulfilled client-side) so the assertion stays
    non-destructive — the request still fires and is asserted, but the backend
    never mutates real inventory (which would consume the bound_loaded_slot)."""
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    page.route(
        "**/api/quickswap",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"status": "success"}'
        ),
    )
    open_manage_modal(toolhead)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=8000)
    test_btn = page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first
    expect(test_btn).to_be_visible(timeout=3000)
    test_btn.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # ~3s active-print probe before the overlay mounts (offline dev printers).
    expect(overlay).to_be_visible(timeout=8000)
    with page.expect_request(
        lambda req: req.url.endswith("/api/quickswap") and req.method == "POST",
        timeout=3000,
    ) as req_info:
        page.locator("#fcc-quickswap-yes").click()
    body = req_info.value.post_data_json
    assert body["toolhead"] == toolhead
    assert body["box"] == box
    assert body["slot"] == slot


@pytest.mark.usefixtures("require_server")
def test_quickswap_escape_in_overlay_closes_overlay_only(page: Page, open_manage_modal, bound_loaded_slot):
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    open_manage_modal(toolhead)
    page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # ~3s active-print probe before the overlay mounts (offline dev printers).
    expect(overlay).to_be_visible(timeout=8000)
    page.keyboard.press("Escape")
    expect(overlay).to_be_hidden(timeout=2000)
    # The manage modal should still be open.
    expect(page.locator("#manageModal")).to_be_visible()


@pytest.mark.usefixtures("require_server")
def test_shortcuts_overlay_toggles_via_button(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    overlay = page.locator("#fcc-shortcuts-overlay")
    expect(overlay).to_be_visible()
    # List contains at least one of the seeded shortcuts.
    expect(page.locator("#fcc-shortcuts-list")).to_contain_text("Quick-Swap")


@pytest.mark.usefixtures("require_server")
def test_shortcuts_overlay_toggles_via_question_mark_key(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    # Blur any input first so the ? listener isn't blocked.
    page.locator("body").click()
    # Playwright's Shift+/ mapping varies; dispatch a synthetic key event
    # so we exercise the same JS keydown handler the user triggers.
    page.evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key: '?', bubbles: true}))")
    overlay = page.locator("#fcc-shortcuts-overlay")
    expect(overlay).to_be_visible(timeout=2000)
    page.keyboard.press("Escape")
    expect(overlay).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server")
def test_shortcuts_overlay_question_mark_mid_scan_does_not_trigger(page: Page, base_url: str):
    """L40 — a legacy QR scan with `?` mid-stream should NOT pop the help overlay."""
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("body").click()
    # Simulate a scanner streaming characters into the document at high speed:
    # several chars first (populates state.scanBuffer + sets scanStartTime),
    # then `?` arrives mid-stream. The overlay must stay hidden.
    page.evaluate(
        """() => {
            // Seed the scan buffer the way scripts.html's keydown listener does:
            // first character sets scanStartTime, subsequent chars append.
            // `state` is a script-scope `let` in inv_core.js — accessible globally
            // in non-module scripts but NOT bound to window.
            state.scanBuffer = 'https://legacy.example/spool';
            state.scanStartTime = Date.now();
            document.dispatchEvent(new KeyboardEvent('keydown', {key: '?', bubbles: true}));
        }"""
    )
    overlay = page.locator("#fcc-shortcuts-overlay")
    expect(overlay).to_be_hidden(timeout=1000)


@pytest.mark.usefixtures("require_server")
def test_shortcuts_overlay_question_mark_at_start_of_scan_does_not_trigger(page: Page, base_url: str):
    """L40 round 2 — a legacy QR whose payload STARTS with `?` (so the
    scan buffer is still empty at capture-phase, defeating the round-1
    mid-stream detection). The defer-then-cancel mechanism waits 120ms
    after a `?` press; if any other character arrives in that window
    we treat it as a scan stream and skip the help-overlay open."""
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("body").click()

    # Simulate a barcode burst: `?`, `i`, `d`, `=`, `4`, `2` — scan stream
    # starting with `?`. Each dispatched immediately (synchronous burst,
    # well under the 120ms defer window).
    page.evaluate(
        """() => {
            const fire = (k) => document.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true}));
            fire('?');
            fire('i'); fire('d'); fire('='); fire('4'); fire('2');
        }"""
    )

    overlay = page.locator("#fcc-shortcuts-overlay")
    # Give the defer timer extra slack to confirm it stayed hidden.
    page.wait_for_timeout(400)
    expect(overlay).to_be_hidden(timeout=500)


@pytest.mark.usefixtures("require_server")
def test_shortcuts_overlay_backdrop_dismisses_overlay(page: Page, base_url: str):
    """L218 — clicking outside the help overlay should dismiss it, not fall through."""
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    overlay = page.locator("#fcc-shortcuts-overlay")
    backdrop = page.locator("#fcc-shortcuts-overlay-backdrop")
    expect(overlay).to_be_visible()
    expect(backdrop).to_be_visible()
    # Click the backdrop (top-left corner is safe — well outside the centered panel).
    backdrop.click(position={"x": 10, "y": 10})
    expect(overlay).to_be_hidden(timeout=2000)
    expect(backdrop).to_be_hidden(timeout=2000)
