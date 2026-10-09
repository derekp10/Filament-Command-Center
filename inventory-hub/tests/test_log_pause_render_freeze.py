"""Activity-Log pause must freeze the RENDER, not the FETCH.

Derek's stated intent:
    "Pausing the log just pauses it so what is currently displayed doesn't move,
     for copying text and whatnot. Technically the badge for the log file should
     pop up and notify the user more logs are available. Unpausing should just
     allow it to update to current state. The log should always be tracking in
     the background — it's just that the updates to the panel in the dashboard
     should be paused."

What it used to do instead: `updateLogState` early-returned while paused and
`_dashboardPulseTick` dropped the 'logs' section, so the tab stopped POLLING.
Consequences:
  - `_updateLogPill` has exactly one call site — inside the render path — so the
    "N new" badge could never appear while paused, which is precisely the
    notification Derek expected;
  - every flag riding that payload (audit_active, bulk_move_active/stage,
    undo_available) stopped arriving, so deck tiles went stale against sessions
    the server-side idle watchdog had already cancelled.

The fix freezes only the `#live-logs` rewrite. These tests pin both halves —
that the list really does stop moving (the point of the feature) and that
everything else really does keep running (the bug).
"""
from __future__ import annotations

import pytest

DASH = "http://localhost:8000/"

# A log entry timestamped far enough ahead that it always sorts as "unseen"
# against the stored last-seen marker, so the pill logic is exercised.
PROBE = {
    "time": "23:59:58",
    "type": "info",
    "msg": "PROBE-PAUSED-ENTRY",
}


def _boot(page):
    page.goto(DASH, wait_until="domcontentloaded")
    page.wait_for_function("typeof state !== 'undefined'", timeout=15000)
    page.wait_for_function("typeof window._renderLogsPayload === 'function'", timeout=15000)
    # Make the probe entry count as unseen for the pill.
    page.evaluate("localStorage.setItem('fcc.logPill.lastSeenTime', '00:00:00')")
    # Start from a known un-paused state.
    page.evaluate("if (state.logsPaused) window.toggleLogsStickyPause();")


@pytest.mark.usefixtures("require_server")
def test_pause_freezes_the_list_but_not_the_pill_or_flags(page):
    _boot(page)
    # Force the pill HIDDEN before pausing. Without this the assertion at the
    # end is vacuous: `_boot` sets lastSeenTime to '00:00:00', so every real dev
    # log entry already counts as unseen and the heartbeat has shown the pill
    # long before the pause — and pausing never hides it, so "pill is visible"
    # would pass whether or not the paused tick ran _updateLogPill at all.
    # '23:00:00' is later than any real dev log entry (so the pill hides now)
    # but EARLIER than the probe's 23:59:58 (so the probe still counts as
    # unseen and must make the pill reappear).
    page.evaluate("""
        localStorage.setItem('fcc.logPill.lastSeenTime', '23:00:00');
        window._renderLogsPayload({logs: [], status: {spoolman: true}}, true);
    """)
    page.wait_for_function(
        "getComputedStyle(document.getElementById('fcc-log-pill')).display === 'none'",
        timeout=5000,
    )

    page.evaluate("window.toggleLogsStickyPause()")
    assert page.evaluate("state.logsPaused") is True

    frozen = page.evaluate("document.getElementById('live-logs').innerHTML")

    # Hand the renderer a payload exactly as the heartbeat would.
    page.evaluate(
        """(probe) => window._renderLogsPayload({
               logs: [probe],
               status: {spoolman: true},
               audit_active: false,
           })""",
        PROBE,
    )

    after = page.evaluate("document.getElementById('live-logs').innerHTML")
    assert after == frozen, (
        "the log list moved while paused — pause exists so text stays still "
        "long enough to select and copy an error out of it"
    )
    assert "PROBE-PAUSED-ENTRY" not in after

    # ...but the badge MUST have noticed, which is the whole point.
    assert page.evaluate(
        "getComputedStyle(document.getElementById('fcc-log-pill')).display"
    ) != "none", (
        "the 'N new' pill stayed hidden while paused — this is the notification "
        "Derek explicitly expects, and its only call site is the render path"
    )


@pytest.mark.usefixtures("require_server")
def test_paused_tab_keeps_polling(page):
    """The regression that starved everything else: no fetch at all while paused."""
    _boot(page)
    page.evaluate("""
        window.__logFetches = 0;
        const orig = window.fetch;
        window.fetch = (...args) => {
            const u = String(args[0] || '');
            if (u.includes('/api/logs')) window.__logFetches++;
            return orig.apply(window, args);
        };
    """)
    page.evaluate("window.toggleLogsStickyPause()")
    assert page.evaluate("state.logsPaused") is True

    page.evaluate("window.__logFetches = 0; updateLogState();")
    page.wait_for_function("window.__logFetches > 0", timeout=5000)

    assert page.evaluate("window.__logFetches") > 0, (
        "updateLogState did not fetch while paused — the log must keep tracking "
        "in the background; only the panel freezes"
    )


@pytest.mark.usefixtures("require_server")
def test_resume_snaps_to_current_state(page):
    """Resuming must catch up.

    Subtle failure this guards: the render short-circuits on an unchanged
    content hash. Paused ticks still stored that hash, so without clearing it on
    resume the catch-up render would be skipped and the frozen list would stay
    on screen looking live.
    """
    _boot(page)
    page.evaluate("window.toggleLogsStickyPause()")

    # Freeze, then poison the DOM so a real re-render is unmistakable.
    page.evaluate(
        "document.getElementById('live-logs').innerHTML = '<div>STALE-FROZEN</div>'"
    )
    # Drive a paused tick so lastLogHash is populated, which is what used to
    # make the resume render short-circuit.
    page.evaluate(
        """(probe) => window._renderLogsPayload({logs: [probe], status: {spoolman: true}})""",
        PROBE,
    )
    assert "STALE-FROZEN" in page.evaluate(
        "document.getElementById('live-logs').innerHTML"
    )

    page.evaluate("window.toggleLogsStickyPause()")   # resume
    assert page.evaluate("state.logsPaused") is False

    page.wait_for_function(
        "!document.getElementById('live-logs').innerHTML.includes('STALE-FROZEN')",
        timeout=8000,
    )


@pytest.mark.usefixtures("require_server")
def test_review_button_still_works_after_a_pause_cycle(page):
    """Explicitly called out as the risk when this fix was filed.

    `_renderLogsPayload` is the shared render path for the whole dashboard
    heartbeat, and it injects the 🛑 Review button for pending cancel-deducts.
    "Skip only the rewrite" must not damage that markup or its handler.
    """
    _boot(page)
    page.evaluate("window.toggleLogsStickyPause()")
    page.evaluate("window.toggleLogsStickyPause()")   # pause + resume
    assert page.evaluate("state.logsPaused") is False

    review_log = {
        "time": "23:59:59",
        "type": "warning",
        "msg": "cancelled print pending review",
        "meta": {"type": "cancel_deduct_pending"},
    }
    page.evaluate(
        """(entry) => window._renderLogsPayload(
               {logs: [entry], status: {spoolman: true}}, true)""",
        review_log,
    )

    btn = page.locator("#live-logs .cancel-review-log button")
    assert btn.count() == 1, "the 🛑 Review affordance was lost from the log row"
    assert "openCancelReview" in (btn.get_attribute("onclick") or ""), (
        "the Review button rendered but lost its handler"
    )
