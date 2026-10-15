"""Group 40.3 — the three-way head-load dialog (window.confirmHeadLoad) in a real
browser: the keys the node-vm stub can't drive, and a stubbed visual baseline.

Pinned here (Derek's answers, 2026-10-14):
  - Enter stores ("Just store it" is focused), on the fed dialog AND on a
    printing one; with no store option Enter cancels;
  - Tab cycles Load / Store / Cancel; Escape cancels (mountOverlay owns it, and
    the Location Manager underneath stays open);
  - an Enter that ends a scanner burst is the scan's, never a click.
The dialog is opened directly with a fixed answer; no server door is called.
HERMETIC: every non-GET is answered synthetically; the buffer is served empty.

HEAD proof: window.confirmHeadLoad doesn't exist on HEAD; every test fails there.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.usefixtures("require_server")

FED_IDLE = {
    "status": "requires_confirm", "confirm_type": "head_fed",
    "fed_heads": [{"toolhead": "XL-1", "printer_name": "XL", "box": "LR-MDB-1", "slot": "1",
                   "resident": {"id": 1, "from": "PM-DB-3"}, "residents": [{"id": 1, "from": "PM-DB-3"}],
                   "confirm_key": "XL-1#1"}],
    "active_prints": [], "active_print": None, "can_store": True, "target_slot": None, "spools": [57],
    "title": "Load #57 onto XL-1?",
    "body": ("LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #1 (from PM-DB-3). "
             "Loading #57 sends #1 back to PM-DB-3."),
}
PRINTING_STORE = {
    "status": "requires_confirm", "confirm_type": "active_print",
    "active_prints": [{"toolhead": "XL-2", "printer_name": "XL", "state": "PRINTING", "role": "feeds", "spools": [57]}],
    "active_print": {"toolhead": "XL-2", "printer_name": "XL", "state": "PRINTING"},
    "fed_heads": [], "can_store": True, "target_slot": "2", "spools": [57],
    "title": "Load #57 onto XL-2?",
    "body": "XL is PRINTING. LR-MDB-1 slot 2 feeds XL-2, so this also loads #57 onto XL-2.",
}

OPEN_JS = """([answer, box, hostId]) => {
  window.__choice = null;
  window.confirmHeadLoad({ answer, box, host: hostId ? document.getElementById(hostId) : null,
    onLoad: () => { window.__choice = 'load'; },
    onStore: () => { window.__choice = 'store'; },
    onCancel: () => { window.__choice = 'cancel'; } });
}"""
OVERLAY = "#fcc-active-print-confirm-overlay"


@pytest.fixture
def dialog_page(page: Page, base_url):
    from conftest import quiet_heartbeat

    def _handle(route):
        try:
            req = route.request
            if req.method == "GET" and "/api/state/buffer" in req.url:
                route.fulfill(status=200, content_type="application/json", body="[]")
            elif req.method not in ("GET", "HEAD", "OPTIONS"):
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"success": True}))
            else:
                route.continue_()
        except PlaywrightError as e:
            if "closed" not in str(e).lower():
                raise

    page.context.route("**/*", _handle)
    quiet_heartbeat(page)
    page.goto(base_url)
    page.wait_for_function("() => typeof window.confirmHeadLoad === 'function'", timeout=15_000)
    yield page
    try:
        page.close()
    except PlaywrightError:
        pass
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _open(page, answer, box="LR-MDB-1", host=None):
    page.evaluate(OPEN_JS, [answer, box, host])
    expect(page.locator(f"{OVERLAY} .fcc-apc-store, {OVERLAY} .fcc-apc-no").first).to_be_visible()
    page.wait_for_function("(sel) => document.activeElement && document.activeElement.closest(sel)",
                           arg=OVERLAY, timeout=3_000)


def _choice(page):
    page.wait_for_function("() => window.__choice !== null", timeout=3_000)
    return page.evaluate("() => window.__choice")


@pytest.mark.parametrize("answer", [FED_IDLE, PRINTING_STORE], ids=["fed-idle", "printing"])
def test_enter_stores(dialog_page, answer):
    page = dialog_page
    _open(page, answer)
    expect(page.locator(f"{OVERLAY} .fcc-apc-store")).to_be_focused()
    page.keyboard.press("Enter")
    assert _choice(page) == "store"
    expect(page.locator(OVERLAY)).to_have_count(0)


def test_without_a_store_option_enter_cancels(dialog_page):
    page = dialog_page
    _open(page, dict(FED_IDLE, can_store=False))
    assert page.locator(f"{OVERLAY} .fcc-apc-store").count() == 0
    expect(page.locator(f"{OVERLAY} .fcc-apc-no")).to_be_focused()
    page.keyboard.press("Enter")
    assert _choice(page) == "cancel"


def test_tab_cycles_and_enter_on_load_loads(dialog_page):
    page = dialog_page
    _open(page, FED_IDLE)
    page.keyboard.press("Tab")      # store -> cancel
    expect(page.locator(f"{OVERLAY} .fcc-apc-no")).to_be_focused()
    page.keyboard.press("Tab")      # cancel -> load (wraps)
    expect(page.locator(f"{OVERLAY} .fcc-apc-yes")).to_be_focused()
    page.keyboard.press("Enter")
    assert _choice(page) == "load"


def test_escape_cancels(dialog_page):
    page = dialog_page
    _open(page, FED_IDLE)
    page.keyboard.press("Escape")
    assert _choice(page) == "cancel"
    expect(page.locator(OVERLAY)).to_have_count(0)


def test_escape_cancels_and_leaves_the_location_manager_open(dialog_page):
    """The docstring's claim, tested (Group 40.3 review, D7): over the Location
    Manager, Escape cancels the dialog only; mountOverlay owns it, so the
    manager underneath stays open."""
    from conftest import wait_modal_settled
    page = dialog_page
    page.evaluate("() => bootstrap.Modal.getOrCreateInstance(document.getElementById('manageModal')).show()")
    wait_modal_settled(page, "manageModal")
    expect(page.locator("#manageModal")).to_be_visible()
    _open(page, FED_IDLE, host="manageModal")
    page.keyboard.press("Escape")
    assert _choice(page) == "cancel"
    expect(page.locator(OVERLAY)).to_have_count(0)
    page.wait_for_timeout(500)   # long enough for a second Escape handler to start the fade
    wait_modal_settled(page, "manageModal")
    expect(page.locator("#manageModal")).to_be_visible()
    assert page.evaluate("() => document.getElementById('manageModal').classList.contains('show')")


def test_a_scanner_bursts_enter_is_not_a_click(dialog_page):
    """A scan typed at scanner speed ends with Enter: that Enter is the scan's.
    It must not also store (the focused button)."""
    page = dialog_page
    _open(page, FED_IDLE)
    page.keyboard.type("ID:999999", delay=0)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    assert page.evaluate("() => window.__choice") is None
    expect(page.locator(OVERLAY)).to_be_visible()


def test_head_load_dialog_visual(dialog_page, snapshot):
    page = dialog_page
    _open(page, FED_IDLE)
    page.wait_for_timeout(400)   # the QR codes draw on a double rAF
    snapshot(page.locator(f"{OVERLAY} .fcc-apc-panel"), "head-load-confirm-fed",
             mask=[page.locator(f"{OVERLAY} .fcc-confirm-qr-row img, {OVERLAY} .fcc-confirm-qr-row canvas")])
