"""
Visual baselines for the Phase 2 Feeds section inside the Location Manager.

Captures the collapsed header, the expanded body with rows, and the saved-
state indicator. These tests share the same tolerance + baseline directory
as the rest of the suite (chromium-1600x1300).
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

TEST_BOX = "PM-DB-1"


@pytest.fixture
def restore_bindings(api_base_url):
    snap = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
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


@pytest.mark.usefixtures("require_server", "restore_bindings")
def test_visual_feeds_section_collapsed(page: Page, base_url: str, snapshot):
    _open_manage(page, base_url, TEST_BOX)
    snapshot(page.locator("#manage-feeds-section"), "feeds-section-collapsed")


@pytest.mark.usefixtures("require_server", "restore_bindings")
def test_visual_feeds_section_expanded(page: Page, base_url: str, snapshot):
    _open_manage(page, base_url, TEST_BOX)
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(400)
    snapshot(page.locator("#manage-feeds-section"), "feeds-section-expanded")
