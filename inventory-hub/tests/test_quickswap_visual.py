"""
Visual baselines for Phase 3 — Quick-Swap grid and shortcuts overlay.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_slot(api_base_url):
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


@pytest.mark.usefixtures("require_server", "bound_slot", "clean_buffer")
def test_visual_quickswap_grid(page: Page, open_manage_modal, snapshot):
    # A populated buffer turns the empty-slot row into a green "Deposit from
    # buffer" affordance — visible content that changes the grid's height
    # (~22px taller per slot row). The baseline is captured with an empty
    # buffer, so the test pins clean_buffer to keep render reproducible in
    # the sweep regardless of prior tests' buffer state. Group 14.4.
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-default")


@pytest.mark.usefixtures("require_server", "bound_slot", "clean_buffer")
def test_visual_quickswap_kb_active(page: Page, open_manage_modal, snapshot):
    open_manage_modal(TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    page.keyboard.press("q")
    page.wait_for_timeout(200)
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-kb-active")


@pytest.mark.usefixtures("require_server")
def test_visual_quickswap_confirm_overlay(page: Page, open_manage_modal, snapshot, bound_loaded_slot):
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    open_manage_modal(toolhead)
    page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first.click()
    # ~3s active-print probe before the overlay mounts (offline dev printers).
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=8000)
    # Snapshot the bounded confirm CARD, not the full-viewport backdrop: the
    # backdrop is semi-transparent, so capturing it bakes the live dashboard
    # (activity-log timestamps, backlog count) into the baseline and guarantees
    # a >1% drift on every run. The card (`.border-info`, min-width 420px) is
    # the only bordered panel inside the overlay and pins the layout/styling.
    card = page.locator("#fcc-quickswap-confirm-overlay .border-info").first
    expect(card).to_be_visible()
    snapshot(card, "quickswap-confirm-overlay")


@pytest.mark.usefixtures("require_server")
def test_visual_shortcuts_overlay(page: Page, base_url: str, snapshot):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    expect(page.locator("#fcc-shortcuts-overlay")).to_be_visible()
    page.wait_for_timeout(300)
    snapshot(page.locator("#fcc-shortcuts-overlay"), "shortcuts-overlay-default")
