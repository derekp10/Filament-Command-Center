"""L286 — click-to-toggle pause indicator is the only pause path. The
hover-mouseenter/leave pause that lived on the #live-logs container
was removed in the follow-up commit because it caused accidental
pauses Derek didn't realize were active. Tests below cover:
  - Initial label invites the user to pause.
  - Click toggles into paused state (state.logsPaused = true).
  - Click again toggles back to running.
  - No mouseenter / mouseleave handlers remain on the log container.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_log_status_click_toggles_pause(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)

    status = page.locator("#log-status")
    expect(status).to_be_visible()
    # Initial label invites the user to pause.
    text_before = status.inner_text()
    assert "click to pause" in text_before.lower(), f"unexpected initial label: {text_before!r}"

    # Click once → paused.
    status.click()
    page.wait_for_function(
        "() => state.logsPaused === true && window.logsStickyPaused === true",
        timeout=2000,
    )
    text_paused = status.inner_text()
    assert "paused" in text_paused.lower()
    assert "click to resume" in text_paused.lower(), f"paused label should advertise resume: {text_paused!r}"

    # Click again → resume.
    status.click()
    page.wait_for_function(
        "() => state.logsPaused === false && window.logsStickyPaused === false",
        timeout=2000,
    )
    text_resumed = status.inner_text()
    assert "auto-refresh" in text_resumed.lower(), f"resumed label should say Auto-Refresh: {text_resumed!r}"


@pytest.mark.usefixtures("require_server")
def test_live_logs_no_longer_pauses_on_hover(page: Page, base_url: str):
    """L286 follow-up: hover-mouseenter/leave is gone. The container
    shouldn't carry the old onmouseenter / onmouseleave attributes,
    and triggering them shouldn't flip the pause state."""
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)

    live_logs = page.locator("#live-logs")
    expect(live_logs).to_be_visible()

    # The inline attributes the old behavior depended on are gone.
    assert live_logs.get_attribute("onmouseenter") in (None, ""), (
        "onmouseenter handler should be removed"
    )
    assert live_logs.get_attribute("onmouseleave") in (None, ""), (
        "onmouseleave handler should be removed"
    )

    # And dispatching the events explicitly does NOT pause the log.
    paused_before = page.evaluate("() => state.logsPaused")
    page.evaluate(
        """() => {
            const el = document.getElementById('live-logs');
            el.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
            el.dispatchEvent(new MouseEvent('mouseleave', {bubbles: true}));
        }"""
    )
    paused_after = page.evaluate("() => state.logsPaused")
    assert paused_after == paused_before, (
        "Hover events should be no-ops; paused state must not change."
    )
