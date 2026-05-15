"""L286 — replace hover-only auto-refresh pause with a click-to-toggle
sticky pause. Mouse-hover transient pause still works (handy when
glancing at the log without committing); click on the status indicator
locks the pause until clicked again so cursor movement can't unstick it.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_log_status_click_toggles_sticky_pause(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)

    status = page.locator("#log-status")
    expect(status).to_be_visible()
    # Initial label invites the user to pause.
    text_before = status.inner_text()
    assert "click to pause" in text_before.lower(), f"unexpected initial label: {text_before!r}"

    # Click once → sticky pause.
    status.click()
    page.wait_for_function(
        "() => window.logsStickyPaused === true && state.logsPaused === true",
        timeout=2000,
    )
    text_paused = status.inner_text()
    assert "paused" in text_paused.lower()
    assert "click to resume" in text_paused.lower(), f"paused label should advertise resume: {text_paused!r}"

    # Hovering away from the log box must NOT unstick the pause.
    page.evaluate("() => pauseLogs(false)")  # simulate mouseleave
    paused_after_unhover = page.evaluate("() => state.logsPaused")
    assert paused_after_unhover is True, "Sticky pause should survive a mouseleave"

    # Click again → resume.
    status.click()
    page.wait_for_function(
        "() => window.logsStickyPaused === false && state.logsPaused === false",
        timeout=2000,
    )
    text_resumed = status.inner_text()
    assert "auto-refresh" in text_resumed.lower(), f"resumed label should say Auto-Refresh: {text_resumed!r}"
