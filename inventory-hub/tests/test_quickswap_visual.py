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


def _open_manage(page: Page, base_url: str, loc_id: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(400)
    page.evaluate(f"window.openManage({loc_id!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_visual_quickswap_grid(page: Page, base_url: str, snapshot):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-default")


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_visual_quickswap_kb_active(page: Page, base_url: str, snapshot):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    expect(page.locator(".fcc-qs-slot").first).to_be_visible()
    page.keyboard.press("q")
    page.wait_for_timeout(200)
    snapshot(page.locator("#manage-quickswap-section"), "quickswap-grid-kb-active")


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_visual_quickswap_confirm_overlay(page: Page, base_url: str, snapshot):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator(".fcc-qs-slot").first.click()
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=2000)
    snapshot(page.locator("#fcc-quickswap-confirm-overlay"), "quickswap-confirm-overlay")


@pytest.mark.usefixtures("require_server")
def test_visual_shortcuts_overlay(page: Page, base_url: str, snapshot):
    page.goto(base_url)
    page.wait_for_selector("#btn-shortcuts-help", timeout=10000)
    page.locator("#btn-shortcuts-help").click()
    expect(page.locator("#fcc-shortcuts-overlay")).to_be_visible()
    page.wait_for_timeout(300)
    snapshot(page.locator("#fcc-shortcuts-overlay"), "shortcuts-overlay-default")
