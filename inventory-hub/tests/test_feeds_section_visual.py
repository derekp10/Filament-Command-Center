"""
Visual baselines for the Phase 2 Feeds section inside the Location Manager.

Captures the collapsed header, the expanded body with rows, and the saved-
state indicator. These tests share the same tolerance + baseline directory
as the rest of the suite (chromium-1600x1300).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

TEST_BOX = "PM-DB-1"


@pytest.fixture
def box_at_baseline(borrow_box_bindings):
    """PM-DB-1 at its fixed binding baseline for the capture, so the Feeds rows
    can't bake in a binding some earlier run left behind; put back to that
    baseline afterwards (conftest `borrow_box_bindings`)."""
    borrow_box_bindings(TEST_BOX)


@pytest.mark.usefixtures("require_server", "box_at_baseline")
def test_visual_feeds_section_collapsed(page: Page, open_manage_modal, snapshot):
    open_manage_modal(TEST_BOX)
    snapshot(page.locator("#manage-feeds-section"), "feeds-section-collapsed")


@pytest.mark.usefixtures("require_server", "box_at_baseline")
def test_visual_feeds_section_expanded(page: Page, open_manage_modal, snapshot):
    open_manage_modal(TEST_BOX)
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(400)
    snapshot(page.locator("#manage-feeds-section"), "feeds-section-expanded")
