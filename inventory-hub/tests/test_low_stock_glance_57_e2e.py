"""Group 57.2: the ⚠️ Low stock button inside the real dashboard (needs the dev
container; skipped under --offline). Read-only: every write the page makes is
answered in the browser (test_text_size_guard._read_only), and the reads are
dev's own heartbeat and Low-stock list, or stubs.

Pinned: the button sits in the title bar between 🛒 Queue and ?; its count is
the list's Low + Out (the real heartbeat against the real /api/stock_report);
it opens the list on its own, and the list it reads sets the count; a heartbeat
that couldn't read draws "?" before any count. The panel and the button
themselves are pinned hermetically by test_low_stock_glance_57_js.py and
test_low_stock_panel.py; the bar at every Text size by
test_text_size_setting_e2e.py; its contrast by test_contrast_guard.py.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

from conftest import quiet_heartbeat
from test_text_size_guard import _read_only

BTN = "#btn-low-stock-count"
NUM = BTN + " [data-low-stock-count]"
PANEL = "#fcc-low-stock-overlay .fcc-stock-panel"
BODY = "#fcc-low-stock-overlay [data-stock-body]"

REPORT = {
    "success": True, "threshold_g": 250.0, "filaments": 3, "spools": 6, "excluded": [],
    "low": [{"filament_id": 164, "display": "Prusament - PLA - Galaxy Black", "color": "222222",
             "color_direction": "longitudinal", "grams": 151.0, "spools": 1, "spools_total": 3,
             "attributes": [], "excluded": None, "buy_url": None},
            {"filament_id": 88, "display": "Overture - PETG - Red Blue", "color": "BA0C2F,0047BB",
             "color_direction": "coaxial", "grams": 220.4, "spools": 2, "spools_total": 2,
             "attributes": [], "excluded": None, "buy_url": None}],
    "out": [{"filament_id": 20, "display": "Generic - PLA - Lipstick Red", "color": "ff0000",
             "color_direction": "longitudinal", "grams": 0, "spools": 0, "spools_total": 2,
             "attributes": [], "excluded": None, "buy_url": None}],
}


def _painted(page):
    page.wait_for_function("(s) => { const n = document.querySelector(s); return !!n && n.textContent.trim() !== '…'; }",
                           arg=NUM, timeout=20_000)
    return page.locator(NUM).text_content().strip()


@pytest.mark.usefixtures("require_server")
def test_the_button_sits_between_queue_and_help(page: Page, base_url: str):
    _read_only(page)
    page.goto(base_url)
    _painted(page)
    boxes = page.evaluate("""() => ['btn-queue-count', 'btn-low-stock-count', 'btn-shortcuts-help'].map((id) => {
        const r = document.getElementById(id).getBoundingClientRect(); return [r.left, r.right, r.top, r.height]; })""")
    (q_l, q_r, q_t, _), (l_l, l_r, l_t, l_h), (h_l, _h_r, h_t, _) = boxes
    assert q_r <= l_l and l_r <= h_l, boxes
    assert abs(q_t - l_t) < 2 and abs(h_t - l_t) < 2 and l_h >= 30, boxes


@pytest.mark.usefixtures("require_server")
def test_the_count_is_the_lists_low_and_out(page: Page, base_url: str):
    """The real heartbeat's count against the real list (both read from dev
    Spoolman; nothing is written)."""
    _read_only(page)
    page.goto(base_url)
    shown = _painted(page)
    report = page.evaluate("() => fetch('/api/stock_report', {cache: 'no-store'}).then((r) => r.json())")
    assert report.get("success") is True, report
    expected = len(report["low"]) + len(report["out"])
    btn = page.locator(BTN)
    assert shown == str(expected), (shown, len(report["low"]), len(report["out"]))
    assert (btn.get_attribute("data-low"), btn.get_attribute("data-out")) == (
        str(len(report["low"])), str(len(report["out"])))
    assert f"{len(report['out'])} out" in (btn.get_attribute("aria-label") or "")


@pytest.mark.usefixtures("require_server")
def test_it_opens_the_list_and_the_list_sets_the_count(page: Page, base_url: str):
    """No heartbeat (quiet_heartbeat), so the only count is the list's own read:
    2 low + 1 out. The search panel stays shut."""
    _read_only(page)
    quiet_heartbeat(page)
    page.route("**/api/stock_report", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(REPORT)))
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openLowStockPanel === 'function'")
    expect(page.locator(NUM)).to_have_text("…")
    page.locator(BTN).click()
    expect(page.locator(PANEL)).to_be_visible()
    page.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)
    expect(page.locator(NUM)).to_have_text("3")
    expect(page.locator("#offcanvasSearch")).not_to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-low-stock-overlay")).to_have_count(0)


@pytest.mark.usefixtures("require_server")
def test_a_heartbeat_that_could_not_read_draws_a_question_mark(page: Page, base_url: str):
    """Before any count, a failed read is "?", never 0 (Group 52's rule)."""
    _read_only(page)

    def pulse(route):
        resp = route.fetch()
        body = resp.json()
        if "low_stock" in body:
            body["low_stock"] = {"read_ok": False, "read_error": "couldn't read Spoolman's spools (test)"}
        route.fulfill(response=resp, body=json.dumps(body))
    page.route("**/api/dashboard_pulse*", pulse)
    page.goto(base_url)
    assert _painted(page) == "?"
    assert page.locator(BTN).get_attribute("data-read") == "failed"
