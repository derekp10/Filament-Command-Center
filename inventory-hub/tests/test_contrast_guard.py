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
import requests
from playwright.sync_api import Page, expect


TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_slot(api_base_url):
    """Ensure at least one binding exists so the Quick-Swap grid and
    Bind picker render populated rows."""
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
    page.wait_for_function("() => typeof window.openManage === 'function'", timeout=5000)
    page.wait_for_timeout(400)
    page.evaluate(f"window.openManage({loc_id!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=8000)
    page.wait_for_timeout(700)


# ---------------------------------------------------------------------------
# Bind picker — the immediate offender that prompted this fix
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    """The exact surface the user reported. Opens the picker, asserts
    every slot-row label meets AA contrast."""
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator("#quickswap-bind-slot-btn").click()
    overlay = page.locator("#fcc-bind-picker-overlay")
    expect(overlay).to_be_visible(timeout=3000)
    # Let the slots list populate.
    expect(page.locator(".fcc-bind-picker-item").first).to_be_visible(timeout=3000)
    assert_contrast(overlay)


# ---------------------------------------------------------------------------
# Quick-Swap grid — populated toolhead view
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_section_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=3000)
    assert_contrast(page.locator("#manage-quickswap-section"))


# ---------------------------------------------------------------------------
# Feeds editor — open state on a Dryer Box
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_feeds_section_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    _open_manage(page, base_url, TEST_BOX)
    # Feeds starts collapsed; open it so the rows render and get asserted.
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(400)
    assert_contrast(page.locator("#manage-feeds-section"))


# ---------------------------------------------------------------------------
# Confirm overlay — swap prompt
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "bound_slot")
def test_quickswap_confirm_overlay_has_no_gray_on_gray_text(page: Page, base_url: str, assert_contrast):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible(timeout=3000)
    # Return-to-Slot opens the confirm overlay without needing a loaded spool
    # (it'll land on "nothing to return" if the toolhead is empty, which
    # still renders the same overlay shell we want to check).
    page.locator("#quickswap-return-btn").click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    expect(overlay).to_be_visible(timeout=3000)
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
