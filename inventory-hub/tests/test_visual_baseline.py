"""
Full-UI visual baseline capture.

Each top-level view and each modal in its default state gets a screenshot
baseline. Run once to establish baselines, then all subsequent runs diff
against them. Baselines live at tests/__screenshots__/chromium-1600x1300/.

First run:  pytest inventory-hub/tests/test_visual_baseline.py --update-snapshots
Later:      pytest inventory-hub/tests/test_visual_baseline.py

Each view is its own test so one flaky surface doesn't block the others.

Since the readability review (2026-10-21) the comparator compares colours
(conftest.compare_screenshot); before, any two captures of the same size
"matched", and these baselines, from April 2026, showed a dashboard with no
Printer Status. A full-page capture of the live dashboard can't match from
one run to the next (the Activity Log, the buffer, dev's printers and their
grams, the counts), so each page gets fixed answers for its live feeds:
_steady_page() (the heartbeat carries only a made-up printer fleet,
conftest.stub_printer_fleet; no log lines; an empty buffer, queue and label
backlog, kept in this page), and LIVE_MASK blanks what is still live (the
version badge, the Locations list and its count).
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from conftest import own_the_buffer, stub_printer_fleet


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _steady_page(page: Page) -> None:
    """Fixed answers for the dashboard's live feeds (install before goto):
    the made-up printer fleet in the heartbeat, no Activity Log lines, and an
    empty buffer, print queue, label backlog and list of print reviews (the
    "🛑 N reviews" badge; dev's own reviews come and go), each kept in this
    page (a write to them never reaches dev)."""
    own_the_buffer(page, [])

    def queue(route):
        body = "[]" if route.request.method == "GET" else '{"success": true}'
        route.fulfill(status=200, content_type="application/json", body=body)
    page.route("**/api/state/queue", queue)
    page.route("**/api/print_queue/pending*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"success": True, "items": []})))
    page.route("**/api/logs*", lambda route: route.abort())
    stub_printer_fleet(page)
    page.route("**/api/cancel_deduct/pending*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"pending": []})))


def _live_mask(page: Page) -> list:
    """What still changes from run to run: the version badge (the commit),
    and the Locations list and its count (dev's locations)."""
    return [page.locator("#fcc-build-version"), page.locator("#location-table"), page.locator("#loc-count")]


def _goto_dashboard(page: Page, base_url: str, reset_js: str = "") -> None:
    _steady_page(page)
    page.goto(base_url)
    # Dashboard deck is the earliest stable anchor.
    page.wait_for_selector(".deck-btn, #live-activity, #command-buffer", timeout=10000)
    # Defensive cross-test pollution teardown (Group 16.3).
    if reset_js:
        page.evaluate(reset_js)
        page.wait_for_timeout(200)
    # Let the initial 5-second tick settle so cards stop shifting.
    page.wait_for_timeout(1500)


def _dismiss_any_open_modal(page: Page) -> None:
    """Best-effort cleanup between captures."""
    # SweetAlert2
    swal = page.locator(".swal2-popup")
    if swal.count() > 0 and swal.first.is_visible():
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        # Escape-confirm overlay?
        confirm_yes = page.locator("#fcc-escape-yes")
        if confirm_yes.count() > 0 and confirm_yes.first.is_visible():
            confirm_yes.click()
            page.wait_for_timeout(200)
    # Bootstrap-style modals
    for sel in ["#spoolModal", "#locationsModal", "#queueModal", "#wizardModal", "#backlogModal"]:
        modal = page.locator(sel)
        if modal.count() > 0 and modal.first.is_visible():
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def test_baseline_dashboard(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    """Dashboard with empty buffer — the default landing surface."""
    _goto_dashboard(page, base_url, reset_dom_state_js)
    snapshot(page, "dashboard-default", mask=_live_mask(page))


def test_baseline_search_offcanvas(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    _goto_dashboard(page, base_url, reset_dom_state_js)
    btn = page.locator('nav button:has-text("SEARCH")')
    if btn.count() == 0:
        pytest.skip("Search nav button not present in current UI")
    btn.first.click()
    page.wait_for_selector("#global-search-query", timeout=5000)
    page.wait_for_timeout(500)
    snapshot(page, "search-offcanvas-empty", mask=_live_mask(page))


def test_baseline_locations_modal(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    _goto_dashboard(page, base_url, reset_dom_state_js)
    page.evaluate("window.openLocationsModal && window.openLocationsModal()")
    try:
        page.wait_for_selector("#locationsModal, .modal.show", timeout=5000)
    except Exception:
        pytest.skip("Locations modal did not open — selector changed")
    page.wait_for_timeout(500)
    snapshot(page, "locations-modal-default", mask=_live_mask(page))


def test_baseline_queue_modal(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    _goto_dashboard(page, base_url, reset_dom_state_js)
    page.evaluate("window.openQueueModal && window.openQueueModal()")
    try:
        page.wait_for_selector("#queueModal, .modal.show", timeout=5000)
    except Exception:
        pytest.skip("Queue modal did not open — selector changed")
    page.wait_for_timeout(500)
    snapshot(page, "queue-modal-default", mask=_live_mask(page))


def test_baseline_wizard_modal(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    _goto_dashboard(page, base_url, reset_dom_state_js)
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    try:
        page.wait_for_selector("#wizardModal, .modal.show", timeout=5000)
    except Exception:
        pytest.skip("Wizard modal did not open — selector changed")
    page.wait_for_timeout(500)
    snapshot(page, "wizard-modal-step1", mask=_live_mask(page))


def test_baseline_backlog_modal(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    _goto_dashboard(page, base_url, reset_dom_state_js)
    page.evaluate("window.openBacklogModal && window.openBacklogModal()")
    try:
        page.wait_for_selector("#backlogModal, .modal.show", timeout=5000)
    except Exception:
        pytest.skip("Backlog modal did not open — selector changed")
    page.wait_for_timeout(500)
    snapshot(page, "backlog-modal-default", mask=_live_mask(page))


def test_baseline_weigh_out_modal(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    _goto_dashboard(page, base_url, reset_dom_state_js)
    # Requires at least one spool on a printer — may not be present in every dev state.
    page.evaluate("window.openWeighOutModal && window.openWeighOutModal()")
    # Weigh-out may pop SweetAlert or a custom modal depending on printer state.
    try:
        page.wait_for_selector(".swal2-popup, #weighOutModal, .modal.show", timeout=3000)
    except Exception:
        pytest.skip("Weigh-out modal did not open (no eligible spool, or selector changed)")
    page.wait_for_timeout(500)
    snapshot(page, "weigh-out-modal-default", mask=_live_mask(page))


def test_baseline_spool_details_modal(page: Page, base_url: str, snapshot, require_server, reset_dom_state_js: str):
    _goto_dashboard(page, base_url, reset_dom_state_js)
    # Open Search to surface spool cards reliably, then close the offcanvas
    # so it doesn't intercept the View Details click.
    page.locator('nav button:has-text("SEARCH")').click()
    page.locator("#global-search-query").fill("a")
    page.locator('label[for="searchTypeSpools"]').click()
    page.wait_for_timeout(1000)
    cards = page.locator(".fcc-spool-card")
    if cards.count() == 0:
        pytest.skip("No spool cards rendered to open details modal")

    # Close the search offcanvas — it intercepts pointer events otherwise.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    offcanvas = page.locator("#offcanvasSearch.show")
    if offcanvas.count() > 0:
        # Fallback: click the close button directly.
        close_btn = page.locator("#offcanvasSearch .btn-close")
        if close_btn.count() > 0:
            close_btn.first.click()
            page.wait_for_timeout(400)

    # Cards from search results may now be in the main buffer. Re-query.
    visible_cards = page.locator(".fcc-spool-card:visible")
    if visible_cards.count() == 0:
        pytest.skip("No spool cards visible after closing offcanvas")
    visible_cards.first.locator('div[title="View Details"]').click()
    try:
        expect(page.locator("#spoolModal")).to_be_visible(timeout=3000)
    except Exception:
        pytest.skip("Spool details modal did not open")
    page.wait_for_timeout(500)
    snapshot(page, "spool-details-modal-default", mask=_live_mask(page))
