"""
UI-path E2E tests for Phase 1 slot-QR assignment.

These drive the actual UI (typing into the hidden scan input and watching
for toast + buffer + Activity Log updates) to catch frontend regressions
that API-path tests can't. Lightweight suite: covers the three failure
paths + the no-buffer pickup fallback. The happy-path (real spool move)
is covered by the API-path test + the unit tests.

Group 45 (2026-11-13): every test owns the page's buffer (conftest.own_the_buffer,
an empty start), so nothing a test puts in the page's buffer (the bad-slot
test's made-up #999, a spool the pickup test picks up) is saved to dev's shared
one, and the page is closed before its routes come off. Only the pickup test
still empties dev's SERVER buffer (clean_buffer): the server reads its own
buffer to choose between loading a spool into the slot and a pickup, so a spool
left there would be loaded into LR-MDB-1 slot 1. The bad-target and bad-slot
scans are refused before the server reads its buffer.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PWTimeoutError

from conftest import own_the_buffer


# Toast-visibility tolerance. The scan POSTs to /api/identify_scan and the error
# toast only appears AFTER the (correct) error response. When the shared dev
# server is loaded by prior network-heavy tests in the same sweep (e.g.
# test_confirm_qr.py's printer-state probes), that response is slow and a tight
# 3 s wait flaked even though the toast was correct — see the
# order-dependent-pollution note in Feature-Buglist.md (Testing). 8 s tolerates
# a loaded server without weakening what's asserted (the error toast lasts 5 s,
# so it's still on screen well after it appears).
_TOAST_WAIT_MS = 8000


@pytest.fixture(autouse=True)
def held(page: Page):
    """The page's own buffer, starting empty (installed before any goto), and
    the page closed FIRST at teardown: un-routed, a live page's next buffer poll
    within 3 s of a change saves its buffer to dev's."""
    stored = own_the_buffer(page, [])
    yield stored
    try:
        page.close()
    except PlaywrightError:
        pass


def _goto_and_wait(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(800)


def _fire_scan(page: Page, text: str) -> None:
    """Invoke processScan directly — avoids hidden input focus races."""
    page.evaluate(f"window.processScan({text!r}, 'test')")


@pytest.mark.usefixtures("require_server")
def test_ui_slot_scan_bad_target_shows_error_toast(page: Page, base_url: str):
    _goto_and_wait(page, base_url)
    _fire_scan(page, "LOC:NOT-A-REAL-PLACE:SLOT:1")
    toast = page.locator(".toast-msg.toast-error")
    expect(toast).to_be_visible(timeout=_TOAST_WAIT_MS)
    expect(toast).to_contain_text("NOT-A-REAL-PLACE")
    expect(toast).to_contain_text("valid load target")


@pytest.mark.usefixtures("require_server")
def test_ui_slot_scan_bad_slot_shows_error_toast(page: Page, base_url: str, held):
    _goto_and_wait(page, base_url)
    # A held spool, as a load scan would have. The server refuses the slot as
    # out of range before it reads its buffer (routes_scan.py's assignment
    # branch), so it needn't see this made-up #999: it stays in the page's own
    # buffer (own_the_buffer) and never reaches dev's.
    page.evaluate("state.heldSpools = [{id: 999, display: 'Test', color: 'ff0000'}]; renderBuffer();")
    for _ in range(50):
        if [s.get("id") for s in held["buffer"]] == [999]:
            break
        page.wait_for_timeout(100)
    assert [s.get("id") for s in held["buffer"]] == [999], held["buffer"]
    _fire_scan(page, "LOC:LR-MDB-1:SLOT:99")
    toast = page.locator(".toast-msg.toast-error")
    expect(toast).to_be_visible(timeout=_TOAST_WAIT_MS)
    expect(toast).to_contain_text("99")
    expect(toast).to_contain_text("invalid")


@pytest.mark.usefixtures("clean_buffer", "require_server")
def test_ui_slot_scan_no_buffer_triggers_pickup_flow(page: Page, base_url: str):
    """With empty buffer, scanning a slot QR triggers the pickup lookup.
    The real behavior then depends on whether the slot has a spool in
    Spoolman, so we only assert the flow is triggered (manager opens or
    a toast appears) — not the specific outcome."""
    _goto_and_wait(page, base_url)
    # The SERVER's buffer is clean from the fixture (/api/buffer/clear): the
    # server reads its own buffer to choose a load or a pickup. The page's is its
    # own and empty (own_the_buffer), so a spool picked up stays in this page.
    # Stamp lastLocalBufferChange so a stray loadBuffer poll can't repopulate the
    # buffer between page-load and scan (which would push the scan down the LOAD
    # path instead of the empty-buffer PICKUP path we mean to exercise).
    page.evaluate("state.heldSpools = []; window.lastLocalBufferChange = Date.now();")
    _fire_scan(page, "LOC:LR-MDB-1:SLOT:1")
    # Either a success toast (picked up), a "slot empty" toast, or the manage
    # modal opens — all three are valid outcomes for this flow. Poll for any of
    # them (up to 8s) rather than a fixed 1.5s sleep: under concurrent sweep load
    # the pickup POST response (and its toast) can land later than 1.5s, which is
    # the whole flake (Group 33.2).
    _outcome = (
        "() => document.querySelectorAll('.toast-msg').length > 0"
        " || document.querySelectorAll(\"#manageModal.show, #manageModal[style*='display: block']\").length > 0"
    )
    try:
        page.wait_for_function(_outcome, timeout=8000)
    except PWTimeoutError:
        pass  # fall through to the friendly assert below
    has_toast = page.locator(".toast-msg").count() > 0
    manage_open = page.locator("#manageModal.show, #manageModal[style*='display: block']").count() > 0
    assert has_toast or manage_open, (
        "Expected at least one of: toast, manage modal open — got neither. "
        "Pickup flow did not trigger."
    )


@pytest.mark.usefixtures("require_server")
def test_ui_slot_scan_toast_error_is_long_enough_to_read(page: Page, base_url: str):
    """Error toasts should stick around long enough to read (>= 3 s) but
    not so long they get in the way — since round-8 the Activity Log is
    the authoritative record so we dropped errors from 8 s to 5 s."""
    _goto_and_wait(page, base_url)
    _fire_scan(page, "LOC:NOT-A-REAL-PLACE:SLOT:1")
    toast = page.locator(".toast-msg.toast-error").first
    expect(toast).to_be_visible(timeout=_TOAST_WAIT_MS)
    # Still visible 3 s in (comfortable read time). Error duration is 5 s.
    page.wait_for_timeout(3000)
    expect(toast).to_be_visible()


@pytest.mark.usefixtures("require_server")
def test_ui_toast_click_dismisses_immediately(page: Page, base_url: str):
    """Clicking a toast should dismiss it on the spot — zero-cost escape
    hatch when the user has already absorbed the message."""
    _goto_and_wait(page, base_url)
    _fire_scan(page, "LOC:NOT-A-REAL-PLACE:SLOT:1")
    toast = page.locator(".toast-msg.toast-error").first
    expect(toast).to_be_visible(timeout=_TOAST_WAIT_MS)
    # Use JS click to bypass pointer-event hit testing (Bootstrap layout
    # sometimes has non-toast ancestors intercept positioned-overlay
    # clicks in headless mode). The user-visible click handler is the
    # same listener wired by showToast, so this exercises the same code
    # path.
    toast.evaluate("el => el.click()")
    page.wait_for_timeout(600)
    assert page.locator(".toast-msg.toast-error").count() == 0, (
        "Clicking a toast should remove it from the DOM"
    )
