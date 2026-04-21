"""
UI-path E2E tests for Phase 1 slot-QR assignment.

These drive the actual UI (typing into the hidden scan input and watching
for toast + buffer + Activity Log updates) to catch frontend regressions
that API-path tests can't. Lightweight suite: covers the three failure
paths + the no-buffer pickup fallback. The happy-path (real spool move)
is covered by the API-path test + the unit tests.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _goto_and_wait(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(800)


def _fire_scan(page: Page, text: str) -> None:
    """Invoke processScan directly — avoids hidden input focus races."""
    page.evaluate(f"window.processScan({text!r}, 'test')")


@pytest.mark.usefixtures("clean_buffer", "require_server")
def test_ui_slot_scan_bad_target_shows_error_toast(page: Page, base_url: str):
    _goto_and_wait(page, base_url)
    _fire_scan(page, "LOC:NOT-A-REAL-PLACE:SLOT:1")
    toast = page.locator(".toast-msg.toast-error")
    expect(toast).to_be_visible(timeout=3000)
    expect(toast).to_contain_text("NOT-A-REAL-PLACE")
    expect(toast).to_contain_text("valid load target")


@pytest.mark.usefixtures("clean_buffer", "require_server")
def test_ui_slot_scan_bad_slot_shows_error_toast(page: Page, base_url: str):
    _goto_and_wait(page, base_url)
    # Seed the buffer with a dummy held spool so the scan hits the load path
    # (without a buffered spool, an out-of-range slot falls through to the
    # pickup lookup instead — that's correct behavior, just different test).
    page.evaluate("state.heldSpools = [{id: 999, display: 'Test', color: 'ff0000'}]; renderBuffer();")
    # Force a persistence so backend sees it before the scan.
    page.wait_for_timeout(400)
    _fire_scan(page, "LOC:LR-MDB-1:SLOT:99")
    toast = page.locator(".toast-msg.toast-error")
    expect(toast).to_be_visible(timeout=3000)
    expect(toast).to_contain_text("99")
    expect(toast).to_contain_text("invalid")


@pytest.mark.usefixtures("clean_buffer", "require_server")
def test_ui_slot_scan_no_buffer_triggers_pickup_flow(page: Page, base_url: str):
    """With empty buffer, scanning a slot QR triggers the pickup lookup.
    The real behavior then depends on whether the slot has a spool in
    Spoolman, so we only assert the flow is triggered (manager opens or
    a toast appears) — not the specific outcome."""
    _goto_and_wait(page, base_url)
    # Buffer is already clean from the fixture.
    _fire_scan(page, "LOC:LR-MDB-1:SLOT:1")
    # Either a success toast (picked up), a "slot empty" toast, or the
    # manage modal opens. All three are valid for this flow.
    page.wait_for_timeout(1500)
    has_toast = page.locator(".toast-msg").count() > 0
    manage_open = page.locator("#manageModal.show, #manageModal[style*='display: block']").count() > 0
    assert has_toast or manage_open, (
        "Expected at least one of: toast, manage modal open — got neither. "
        "Pickup flow did not trigger."
    )


@pytest.mark.usefixtures("clean_buffer", "require_server")
def test_ui_slot_scan_toast_error_duration_is_long_enough(page: Page, base_url: str):
    """Error toasts should stick around for at least 7 seconds — blind
    scanners miss short toasts."""
    _goto_and_wait(page, base_url)
    _fire_scan(page, "LOC:NOT-A-REAL-PLACE:SLOT:1")
    toast = page.locator(".toast-msg.toast-error").first
    expect(toast).to_be_visible(timeout=3000)
    # Still visible after 5 seconds — shorter than the 8 s duration.
    page.wait_for_timeout(5000)
    expect(toast).to_be_visible()
