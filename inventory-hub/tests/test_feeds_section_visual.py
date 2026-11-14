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


def _own_buffer(page: Page):
    """This page's own empty buffer. The Location Manager draws its nav deck
    above the section when dev's shared buffer holds a spool, and with one an
    earlier test left there the section's text came out a fraction of a pixel
    off and failed one run in three (readability review, 2026-10-21, once the
    comparator compared colours).

    The box's own contents are answered as empty, and the heartbeat (whose
    manage section redraws them from dev) is stopped, for the same reason
    (Group 45, 2026-11-13): the spool card dev's PM-DB-1 holds sits above the
    section. The baselines were taken with dev's PM-DB-1 empty; the refresh from
    prod put #66 in it, and the collapsed capture failed at 6.7% with no code
    change."""
    from urllib.parse import parse_qs, urlsplit
    from conftest import own_the_buffer, quiet_heartbeat
    own_the_buffer(page, [])

    def _is_box_contents(url: str) -> bool:
        parts = urlsplit(url)
        return parts.path == "/api/get_contents" and parse_qs(parts.query).get("id") == [TEST_BOX]

    page.route(_is_box_contents, lambda route: route.fulfill(
        status=200, content_type="application/json", body="[]"))
    quiet_heartbeat(page)


@pytest.mark.usefixtures("require_server", "box_at_baseline")
def test_visual_feeds_section_collapsed(page: Page, open_manage_modal, snapshot):
    _own_buffer(page)
    open_manage_modal(TEST_BOX)
    snapshot(page.locator("#manage-feeds-section"), "feeds-section-collapsed")


@pytest.mark.usefixtures("require_server", "box_at_baseline")
def test_visual_feeds_section_expanded(page: Page, open_manage_modal, snapshot):
    _own_buffer(page)
    open_manage_modal(TEST_BOX)
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(400)
    snapshot(page.locator("#manage-feeds-section"), "feeds-section-expanded")
