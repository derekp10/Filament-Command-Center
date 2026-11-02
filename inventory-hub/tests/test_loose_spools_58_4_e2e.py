"""Group 58.4 over the real dashboard: the Locations window's 🧺 Loose spools button,
real Bootstrap, the real Location Manager, the real audit panel.

READ-ONLY. Every request that isn't a read is answered inside the browser
(test_text_size_guard._read_only), so nothing here reaches dev's data, and the
list itself writes nothing. The rows come from /api/loose_spools, stubbed where a
test's point is the page, and dev's own answer where it's the route.

Hermetic twin: test_loose_spools_58_4_js.py.
"""
from __future__ import annotations

import json

import pytest
import requests
from playwright.sync_api import Page, expect

from conftest import quiet_heartbeat
from test_text_size_guard import SAMPLE_AUDIT, SAMPLE_LOOSE, _hide, _read_only, _ready, _shown

pytestmark = pytest.mark.usefixtures("require_server")

OVERLAY = "#fcc-loose-list"
PANEL = OVERLAY + " .fcc-loose-panel"
ROW = OVERLAY + " .fcc-loose-row"
BUTTON = "#loc-loose-list-btn"
DOWN = {"read_ok": False, "read_error": "couldn't read Spoolman (test)", "count": 0, "places": []}


def _serve(page: Page, *answers):
    """/api/loose_spools answers these in turn; the last repeats."""
    queue = list(answers)
    page.route("**/api/loose_spools", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps(queue.pop(0) if len(queue) > 1 else queue[0])))


def _on_top(page: Page, selector: str) -> bool:
    """What a click at the middle of `selector` would hit is inside it."""
    return page.evaluate("""(sel) => { const el = document.querySelector(sel);
        const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); }""", selector)


def _open_locations(page: Page, base_url: str):
    _ready(page, base_url)
    _shown(page, "locMgrModal", "() => window.openLocationsModal()")


def test_the_list_opens_over_the_locations_window_and_escape_closes_only_it(page: Page, base_url: str):
    _read_only(page)
    _serve(page, SAMPLE_LOOSE)
    _open_locations(page, base_url)
    page.click(BUTTON)
    expect(page.locator(ROW + ".kb-active")).to_have_count(1)
    assert _on_top(page, PANEL)
    page.keyboard.press("ArrowDown")
    assert page.locator(ROW + ".kb-active").get_attribute("data-spool") == "2"
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_have_count(0)
    page.wait_for_timeout(500)
    expect(page.locator("#locMgrModal")).to_be_visible()                       # the window under it stays
    assert page.evaluate("document.activeElement.id") == "loc-loose-list-btn"
    page.keyboard.press("Escape")                                              # and answers its own Escape next
    page.wait_for_function("() => !document.getElementById('locMgrModal').classList.contains('show')")


def test_the_list_closes_with_the_locations_window(page: Page, base_url: str):
    _read_only(page)
    _serve(page, SAMPLE_LOOSE)
    _open_locations(page, base_url)
    page.click(BUTTON)
    expect(page.locator(ROW + ".kb-active")).to_have_count(1)
    _hide(page, "locMgrModal")
    expect(page.locator(OVERLAY)).to_have_count(0)


def test_enter_opens_the_place_in_the_real_location_manager(page: Page, base_url: str, api_base_url: str):
    """Dev's own answer, so the place is a real row: the window opens on it, on top."""
    body = requests.get(api_base_url + "/api/loose_spools", timeout=20).json()
    assert body["read_ok"] is True, body
    if not body["places"]:
        pytest.skip("dev has no loose spool to open")
    first = body["places"][0]
    _read_only(page)
    _open_locations(page, base_url)
    page.click(BUTTON)
    expect(page.locator(ROW + ".kb-active")).to_have_count(1)
    assert page.locator(ROW + ".kb-active").get_attribute("data-place") == first["id"]
    assert page.locator(ROW).count() == body["count"]
    page.keyboard.press("Enter")
    expect(page.locator(OVERLAY)).to_have_count(0)
    page.wait_for_function("(id) => document.getElementById('manageModal').classList.contains('show')"
                           " && document.getElementById('manage-loc-id').value === id", arg=first["id"], timeout=15_000)
    assert _on_top(page, "#manageModal .modal-content")


def test_a_failed_read_shows_the_notice_and_try_again_reads_again(page: Page, base_url: str):
    _read_only(page)
    _serve(page, DOWN, SAMPLE_LOOSE)
    _open_locations(page, base_url)
    page.click(BUTTON)
    notice = page.locator(OVERLAY + " [data-loose-notice]")
    expect(notice).to_be_visible()
    assert "no loose" not in page.locator(PANEL).inner_text().lower()
    page.keyboard.press("Enter")                                               # on Try again, by the real accumulator
    expect(page.locator(ROW)).to_have_count(3)
    expect(notice).to_have_count(0)


def test_a_scan_passes_the_list_by(page: Page, base_url: str):
    """A scanner's keys and Enter over the list reach the scan path, whose window
    then opens where it can be seen; the list gives way."""
    _read_only(page)
    _serve(page, SAMPLE_LOOSE)
    _open_locations(page, base_url)
    page.click(BUTTON)
    expect(page.locator(ROW + ".kb-active")).to_have_count(1)
    page.keyboard.type("CMD:WEIGH", delay=0)
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.getElementById('weighOutModal').classList.contains('show')", timeout=10_000)
    expect(page.locator(OVERLAY)).to_have_count(0)


def test_over_the_real_audit_panel(page: Page, base_url: str):
    """The way in slice s5 wires: tier confirm, above the audit panel. Enter opens
    nothing there, and Escape leaves the panel up."""
    quiet_heartbeat(page)
    _read_only(page, extra_get={"/api/audit_session": SAMPLE_AUDIT})
    _serve(page, SAMPLE_LOOSE)
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.openAuditPanel === 'function' && typeof window.openLooseList === 'function'",
                           timeout=45_000)
    page.evaluate("() => { state.auditActive = true; window.openAuditPanel(); }")
    page.wait_for_function("() => { const b = document.getElementById('fcc-audit-panel-body');"
                           " return !!b && /Auditing/.test(b.innerText); }", timeout=10_000)
    page.evaluate("() => { window.openLooseList({ tier: 'confirm' }); }")
    expect(page.locator(ROW + ".kb-active")).to_have_count(1)
    assert _on_top(page, PANEL)
    assert "Enter" not in page.locator(OVERLAY + " [data-loose-foot]").inner_text()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.evaluate("() => document.getElementById('manageModal').classList.contains('show')") is False
    expect(page.locator(OVERLAY)).to_have_count(1)
    page.keyboard.press("Escape")
    expect(page.locator(OVERLAY)).to_have_count(0)
    expect(page.locator("#fcc-audit-panel-body")).to_be_visible()
