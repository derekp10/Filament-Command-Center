"""Escape-to-dismiss for toasts (Feature-Buglist.md 2026-05-30 wizard/attribute
bullet: "hitting escape on a toast should cancel the toast").

The Escape priority ladder implemented in inv_core.js is:
  1. an open mountOverlay owns Escape (closes itself),
  2. else a visible toast intercepts Escape and dismisses the newest one,
  3. else Escape falls through to the underlying modal / handler.

These tests pin all three rungs plus the progressive (newest-first) dismissal.
Toasts are raised directly via window.showToast so we don't depend on a scan.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _goto(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    # window.showToast is published by inv_core.js (the bare const is also a
    # global lexical binding). Waiting on the window alias doubles as a smoke
    # check that the export landed.
    page.wait_for_function("typeof window.showToast === 'function'", timeout=5_000)


def _toast_count(page: Page) -> int:
    """Count toasts that are still 'live' (not mid fade-out)."""
    return page.evaluate(
        """() => {
            const c = document.getElementById('toast-container');
            if (!c) return 0;
            return Array.from(c.querySelectorAll('.toast-msg'))
                .filter(t => t.style.opacity !== '0').length;
        }"""
    )


def test_escape_dismisses_newest_toast_progressively(page: Page):
    _goto(page)
    # Two long-lived toasts so the auto-timeout never races the test.
    page.evaluate("window.showToast('FIRST_TOAST', 'info', 30000)")
    page.evaluate("window.showToast('SECOND_TOAST', 'error', 30000)")
    assert _toast_count(page) == 2

    # Newest (SECOND) dismissed first.
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.body.innerText.includes('SECOND_TOAST')", timeout=2_000)
    assert _toast_count(page) == 1
    assert "FIRST_TOAST" in page.locator("#toast-container").inner_text()

    # Next Escape clears the remaining one.
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.body.innerText.includes('FIRST_TOAST')", timeout=2_000)
    assert _toast_count(page) == 0


def test_escape_with_no_toast_is_a_noop_for_the_ladder(page: Page):
    """Escape with no toasts up must NOT throw and must leave the page intact."""
    _goto(page)
    assert _toast_count(page) == 0
    page.keyboard.press("Escape")  # should be harmless
    # Page still responsive: a fresh toast can still be raised + dismissed.
    page.evaluate("window.showToast('AFTER_NOOP', 'info', 30000)")
    assert _toast_count(page) == 1
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.body.innerText.includes('AFTER_NOOP')", timeout=2_000)


def test_toast_beats_modal_close(page: Page):
    """A toast raised while the wizard modal is open intercepts Escape:
    the FIRST Escape dismisses the toast (wizard stays open); the SECOND
    Escape (no toast left) closes the wizard."""
    _goto(page)
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible()

    page.evaluate("window.showToast('OVER_WIZARD', 'warning', 30000)")
    assert _toast_count(page) == 1

    # Escape #1 → toast gone, wizard still open.
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.body.innerText.includes('OVER_WIZARD')", timeout=2_000)
    expect(page.locator("#wizardModal")).to_be_visible()

    # Escape #2 → wizard closes (nothing intercepts now).
    page.evaluate("try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}")
    page.keyboard.press("Escape")
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5_000)


def test_overlay_beats_toast(page: Page):
    """An open mountOverlay owns Escape — pressing Escape closes the overlay
    and leaves the toast untouched."""
    _goto(page)
    page.wait_for_function("typeof window.mountOverlay === 'function'", timeout=5_000)
    page.evaluate("window.showToast('BEHIND_OVERLAY', 'info', 30000)")
    page.evaluate(
        """window.mountOverlay({
            id: 'fcc-test-esc-overlay',
            content: '<div id=\\'fcc-test-esc-panel\\' style=\\'padding:20px;background:#222;color:#fff\\'>overlay</div>',
        })"""
    )
    expect(page.locator("#fcc-test-esc-overlay")).to_be_visible()
    assert _toast_count(page) == 1

    page.keyboard.press("Escape")
    # Overlay closes...
    expect(page.locator("#fcc-test-esc-overlay")).not_to_be_attached(timeout=2_000)
    # ...and the toast is still up (Escape was consumed by the overlay).
    assert _toast_count(page) == 1
    assert "BEHIND_OVERLAY" in page.locator("#toast-container").inner_text()
