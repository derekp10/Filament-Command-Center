"""
Full-UI visual baseline capture.

Each top-level view and each modal in its default state gets a screenshot
baseline. Run once to establish baselines, then all subsequent runs diff
against them. Baselines live at tests/__screenshots__/chromium-1600x1300/.

First run:  UPDATE_VISUAL_BASELINES=1 pytest inventory-hub/tests/test_visual_baseline.py
            (a missing baseline is written too; look at each capture before keeping it)
Later:      pytest inventory-hub/tests/test_visual_baseline.py

Each view is its own test so one flaky surface doesn't block the others.

Since the readability review (2026-10-21) the comparator compares colours
(conftest.compare_screenshot); before, any two captures of the same size
"matched", and these baselines, from April 2026, showed a dashboard with no
Printer Status. A full-page capture of the live dashboard can't match from
one run to the next (the Activity Log, the buffer, dev's printers and their
grams, the counts), so each page gets fixed answers for its live feeds:
_steady_page() (the heartbeat carries only a made-up printer fleet and a
fixed ⚠️ Low stock count, conftest.stub_printer_fleet; no log lines; an empty
buffer, queue and label backlog, kept in this page), and LIVE_MASK blanks what
is still live (the version badge, the Locations list and its count). The spool
window's baseline buffers one made-up spool of its own (VISUAL_SPOOL_CARD) and
answers every read the window makes with a made-up record (stub_visual_spool;
Group 45.11: it used to look for a spool card after a search and skip, every
run since the buffer became the page's own, so its April baseline was never
compared).
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from conftest import own_the_buffer, stub_printer_fleet, wait_modal_settled


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _steady_page(page: Page, buffer=()) -> None:
    """Fixed answers for the dashboard's live feeds (install before goto):
    the made-up printer fleet in the heartbeat, no Activity Log lines, and a
    buffer holding `buffer` (empty unless a test gives it a made-up spool),
    an empty print queue, label backlog and list of print reviews (the
    "🛑 N reviews" badge; dev's own reviews come and go), each kept in this
    page (a write to them never reaches dev)."""
    own_the_buffer(page, list(buffer))

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


# The spool window's own spool (Group 45.11), made up like conftest.VISUAL_FLEET:
# the buffer card the page holds (every field the buffer's refresh compares,
# inv_cmd.js _renderSpoolsRefreshPayload) and the record /api/spool_details
# answers for it (extras already decoded, as the route sends them). Its own
# product and purchase links show both link buttons whatever dev's config.json
# says about a Buy More template.
VISUAL_SPOOL_CARD = {
    "id": 9201, "display": "#9201 ZZ Visual PETG (Visual Teal)", "color": "1E9C8F",
    "color_direction": "longitudinal", "remaining_weight": 810.5, "location": "ZZ-VIS-SHELF",
    "slot": "", "is_ghost": False, "archived": False, "deployed_to": None,
    "details": {"brand": "ZZ Visual", "material": "PETG", "color_name": "Visual Teal"},
}
VISUAL_SPOOL_DETAILS = {
    "id": 9201, "archived": False, "location": "ZZ-VIS-SHELF",
    "comment": "Made-up spool for the visual baseline.",
    "initial_weight": 1000.0, "spool_weight": 200.0, "used_weight": 189.5, "remaining_weight": 810.5,
    "extra": {"product_url": "https://example.invalid/visual-teal",
              "purchase_url": "https://example.invalid/visual-teal/buy"},
    "filament": {
        "id": 9301, "name": "Visual Teal", "material": "PETG", "color_hex": "1E9C8F", "weight": 1000.0,
        "settings_extruder_temp": 240, "settings_bed_temp": 80,
        "vendor": {"id": 9401, "name": "ZZ Visual", "extra": {}},
        "extra": {"nozzle_temp_max": "250", "bed_temp_max": "90", "slicer_profile": "Generic PETG",
                  "filament_attributes": ["Matte"]},
    },
}
# The fields _renderSpoolsRefreshPayload compares: a refresh answering the card's
# own values repaints nothing (and so saves nothing).
_REFRESH_FIELDS = ("display", "color", "color_direction", "remaining_weight", "details", "archived",
                   "location", "is_ghost", "slot", "deployed_to")


def stub_visual_spool(page: Page, card=None, details=None) -> None:
    """Answer every read the spool window and the buffer card make about the
    made-up spool: GET /api/spool_details for it (on open, and again silently
    on each heartbeat while the window is open) and POST /api/spools/refresh
    (500 ms after the page takes its buffer in; dev would answer a junk card
    for an id it lacks). Everything else falls through. Install before goto."""
    from urllib.parse import parse_qs, urlsplit
    card = card or VISUAL_SPOOL_CARD
    details = details or VISUAL_SPOOL_DETAILS
    sid = str(card["id"])

    def handle(route):
        req = route.request
        url = urlsplit(req.url)
        if url.path == "/api/spool_details" and (parse_qs(url.query).get("id") or [""])[0] == sid:
            body = details
        elif url.path == "/api/spools/refresh" and req.method.upper() == "POST":
            try:
                asked = [str(i) for i in ((req.post_data_json or {}).get("spools") or [])]
            except ValueError:
                asked = []
            body = {sid: {k: card[k] for k in _REFRESH_FIELDS}} if sid in asked else {}
        else:
            route.fallback()
            return
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.route("**/api/**", handle)


def _goto_dashboard(page: Page, base_url: str, reset_js: str = "", buffer=()) -> None:
    _steady_page(page, buffer)
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
    """The spool window, opened from the 🔍 View Details of the buffer's one
    card, a made-up spool whose every read is answered here (Group 45.11), so
    the window shows the same spool on every run and the test never skips."""
    stub_visual_spool(page)
    _goto_dashboard(page, base_url, reset_dom_state_js, buffer=[VISUAL_SPOOL_CARD])
    card = page.locator(f'#buffer-zone .fcc-spool-card[data-spool-id="{VISUAL_SPOOL_CARD["id"]}"]')
    expect(card).to_be_visible()
    card.locator('[title="View Details"]').click()
    expect(page.locator("#spoolModal")).to_be_visible()
    # After visible: before show() starts, the modal already reads as settled.
    wait_modal_settled(page, "spoolModal")
    expect(page.locator("#detail-id")).to_have_text(str(VISUAL_SPOOL_DETAILS["id"]))
    expect(page.locator("#detail-color-name")).to_have_text(VISUAL_SPOOL_DETAILS["filament"]["name"])
    # The pointer rested on the card's 🔍, under the backdrop: off to a corner.
    page.mouse.move(1, 1)
    snapshot(page, "spool-details-modal-default", mask=_live_mask(page))
