"""
Visual snapshots for Phase 1 scan toasts. Captures each toast variant so
regressions in color, border, or wording get caught automatically.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _goto(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(800)


def _snap_toast(page: Page, name: str, snapshot, toast_selector: str) -> None:
    toast = page.locator(toast_selector).first
    expect(toast).to_be_visible(timeout=3000)
    # Snapshot just the toast element so viewport scroll doesn't affect the diff.
    snapshot(toast, name)


@pytest.mark.usefixtures("clean_buffer", "require_server")
def test_visual_toast_bad_target(page: Page, base_url: str, snapshot):
    _goto(page, base_url)
    page.evaluate("window.processScan('LOC:NOT-A-REAL-PLACE:SLOT:1', 'test')")
    _snap_toast(page, "scan-toast-bad-target", snapshot, ".toast-msg.toast-error")


@pytest.mark.usefixtures("clean_buffer", "require_server")
def test_visual_toast_bad_slot(page: Page, base_url: str, snapshot):
    _goto(page, base_url)
    page.evaluate("state.heldSpools = [{id: 999, display: 'Test', color: 'ff0000'}]; renderBuffer();")
    page.wait_for_timeout(400)
    page.evaluate("window.processScan('LOC:LR-MDB-1:SLOT:99', 'test')")
    _snap_toast(page, "scan-toast-bad-slot", snapshot, ".toast-msg.toast-error")
