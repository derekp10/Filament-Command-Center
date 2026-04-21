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


def _open_manage(page: Page, base_url: str, loc_id: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(500)
    page.evaluate(f"window.openManage({loc_id!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_grid_visible_on_bound_toolhead(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    section = page.locator("#manage-quickswap-section")
    expect(section).to_be_visible()
    # With the fixture binding in place, at least one slot button renders.
    slots = page.locator(".fcc-qs-slot")
    expect(slots.first).to_be_visible(timeout=3000)


@pytest.mark.usefixtures("require_server")
def test_quickswap_grid_hidden_on_dryer_box(page: Page, base_url: str):
    _open_manage(page, base_url, NON_TOOLHEAD_LOC)
    expect(page.locator("#manage-quickswap-section")).to_be_hidden()


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_keyboard_q_focuses_first_slot(page: Page, base_url: str):
    import re
    _open_manage(page, base_url, TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    page.keyboard.press("q")
    page.wait_for_timeout(200)
    first = page.locator(".fcc-qs-slot").first
    # Match any class list that contains both fcc-qs-slot and kb-active.
    expect(first).to_have_class(re.compile(r'fcc-qs-slot(?=.*\bkb-active\b)'))


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_tap_opens_confirm_overlay(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    # Specifically target the slot button that came from our fixture's binding,
    # not whatever happens to be first in the grid.
    test_btn = page.locator(f".fcc-qs-slot[data-box='{TEST_BOX}'][data-toolhead='{TEST_TOOLHEAD}']").first
    expect(test_btn).to_be_visible(timeout=3000)
    test_btn.click()
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=2000)
    expect(page.locator("#fcc-quickswap-confirm-title")).to_contain_text(TEST_BOX)
    expect(page.locator("#fcc-quickswap-confirm-title")).to_contain_text(TEST_TOOLHEAD)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_confirm_overlay_cancel_dismisses(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator(".fcc-qs-slot").first.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    expect(overlay).to_be_visible(timeout=2000)
    page.locator("#fcc-quickswap-no").click()
    expect(overlay).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_confirm_yes_actually_performs_swap(page: Page, base_url: str):
    """Regression guard: a duplicate window.quickSwapTap definition was
    overriding the real handler, so clicking Yes did nothing. This test
    catches that class of bug by watching the /api/quickswap request
    fire in response to the Yes click."""
    _open_manage(page, base_url, TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    test_btn = page.locator(f".fcc-qs-slot[data-box='{TEST_BOX}'][data-toolhead='{TEST_TOOLHEAD}']").first
    expect(test_btn).to_be_visible(timeout=3000)
    test_btn.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    expect(overlay).to_be_visible(timeout=2000)
    # Listen for the quickswap POST fired by the Yes button.
    with page.expect_request(
        lambda req: req.url.endswith("/api/quickswap") and req.method == "POST",
        timeout=3000,
    ) as req_info:
        page.locator("#fcc-quickswap-yes").click()
    body = req_info.value.post_data_json
    assert body["toolhead"] == TEST_TOOLHEAD
    assert body["box"] == TEST_BOX
    assert body["slot"] == "1"


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_escape_in_overlay_closes_overlay_only(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator(".fcc-qs-slot").first.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    expect(overlay).to_be_visible(timeout=2000)
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
