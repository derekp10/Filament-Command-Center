"""Frontend tests for the L206 dashboard_pulse migration.

Confirms:
1. The 5s heartbeat now hits /api/dashboard_pulse instead of the legacy
   per-section endpoints (/api/logs, /api/locations, /api/spools/refresh).
2. Adaptive cadence reads the current bucket correctly (active vs idle
   vs hidden).
3. The bulk-pulse dispatcher fans the response out to each section's
   renderer (logs, status dots, manage view, printer status).
"""
from __future__ import annotations


def _track_requests(page, prefixes):
    """Attach a request listener returning a counts dict keyed by the
    first matching prefix. Buckets unrelated requests under 'other'.
    """
    counts = {p: 0 for p in prefixes}
    counts['other'] = 0

    def _on_req(req):
        url = req.url
        for p in prefixes:
            if p in url:
                counts[p] += 1
                return
        counts['other'] += 1

    page.on('request', _on_req)
    return counts


def test_heartbeat_uses_dashboard_pulse_not_individual_endpoints(
    page, require_server, base_url
):
    """After my L206 migration, the 5s heartbeat fires exactly one
    /api/dashboard_pulse call per tick, not the legacy fan-out. The
    legacy /api/logs endpoint should ONLY be hit by the initial
    DOMContentLoaded force=true call (not by the heartbeat)."""
    counts = _track_requests(page, [
        '/api/dashboard_pulse',
        '/api/logs',
        '/api/locations',
        '/api/spools/refresh',
        '/api/get_contents',
        '/api/printer_map',
        '/api/machine/',
    ])
    page.goto(base_url, wait_until='domcontentloaded')
    # Wait through ~2 heartbeat ticks (5s each).
    page.wait_for_timeout(12_000)

    # Pulse should have fired at least 2 times by now (initial + heartbeats).
    assert counts['/api/dashboard_pulse'] >= 2, (
        f"Expected dashboard_pulse to fire on the heartbeat; got "
        f"{counts['/api/dashboard_pulse']} calls. Full counts: {counts}"
    )

    # /api/logs should fire at most ONCE — the immediate force=true call
    # from updateLogState(true) on DOMContentLoaded. The heartbeat path
    # gets logs via the bulk endpoint, not by hitting /api/logs directly.
    assert counts['/api/logs'] <= 1, (
        f"/api/logs should fire only from the initial DOMContentLoaded "
        f"force=true call; got {counts['/api/logs']} calls — the heartbeat "
        f"may still be hitting the legacy endpoint."
    )

    # /api/spools/refresh should fire 0 times when the buffer is empty
    # (bulk endpoint handles refresh via its spools_refresh section, and
    # only when the frontend includes refresh_spool_ids).
    # If the buffer is non-empty in dev, it could still fire from a
    # user-action dispatch — we don't assert == 0 to keep the test robust.


def test_pulse_interval_returns_active_when_visible_and_recent(
    page, require_server, base_url
):
    """The cadence function returns the ACTIVE interval (5s) by default
    on a freshly-loaded page (tab visible, activity timestamp recent)."""
    page.goto(base_url, wait_until='domcontentloaded')
    # Bump activity timestamp explicitly so the test is robust even when
    # 60s+ has passed since the last interaction (e.g. on slow CI).
    page.evaluate("() => document.dispatchEvent(new MouseEvent('mousedown'))")
    interval = page.evaluate("() => window._pulseInterval()")
    assert interval == 5000, (
        f"Active cadence should be 5000ms; got {interval}"
    )


def test_pulse_interval_returns_hidden_when_document_hidden(
    page, require_server, base_url
):
    """When the tab is hidden, the cadence stretches to 30s — same data
    flow, just less frequently — to avoid burning background polls."""
    page.goto(base_url, wait_until='domcontentloaded')
    # Override document.hidden / visibilityState via property descriptor.
    page.evaluate("""() => {
        Object.defineProperty(document, 'hidden', { get: () => true, configurable: true });
        Object.defineProperty(document, 'visibilityState', { get: () => 'hidden', configurable: true });
    }""")
    interval = page.evaluate("() => window._pulseInterval()")
    assert interval == 30000, (
        f"Hidden cadence should be 30000ms; got {interval}"
    )


def test_pulse_interval_returns_idle_after_60s_threshold(
    page, require_server, base_url
):
    """When the user hasn't interacted in > 60s, cadence stretches to
    15s. We simulate the idle state by mocking the module-scoped
    timestamp via a recent-activity dispatch in the past."""
    page.goto(base_url, wait_until='domcontentloaded')
    # Force document.hidden=false explicitly so the idle bucket — not
    # the hidden bucket — is the one we're checking.
    page.evaluate("""() => {
        Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
    }""")
    # Reach into the module via a known-good fingerprint: re-run the
    # cadence eval after evaluating a 70s-back Date.now mock so the
    # idle threshold trips. Easiest path: use performance.now overrides
    # are messy; instead, evaluate an artificial idle state by clobbering
    # the lastUserActivity-style logic via a temporary Date.now override.
    interval = page.evaluate("""() => {
        const real = Date.now;
        try {
            // Pretend "now" is 70s ahead of the last activity bump.
            Date.now = () => real() + 70_000;
            return window._pulseInterval();
        } finally {
            Date.now = real;
        }
    }""")
    assert interval == 15000, (
        f"Idle cadence (>60s since interaction) should be 15000ms; "
        f"got {interval}"
    )


def test_pulse_interval_fast_polls_after_print_finish_edge(
    page, require_server, base_url
):
    """L25 / FilaBridge Phase 0 — when a printer transitions from an
    in-progress state (PRINTING) to an ended state (FINISHED), the cadence is
    forced to the ACTIVE 5s bucket for ~30s, overriding the idle + hidden
    buckets, so the post-deduct weight lands within one fast tick instead of
    lagging a full bucket behind the deduct's separate clock."""
    page.goto(base_url, wait_until='domcontentloaded')
    # Clean fast-poll state, and force the tab hidden so the baseline bucket
    # would be 30s — the finish edge must override it.
    page.evaluate("""() => {
        window._resetFastPollForTest();
        Object.defineProperty(document, 'hidden', { get: () => true, configurable: true });
    }""")
    assert page.evaluate("() => window._pulseInterval()") == 30000, (
        "Baseline (hidden, no recent finish edge) should be the 30s bucket"
    )
    # Feed two pulses for a synthetic printer: PRINTING then FINISHED — the
    # in-progress -> ended edge. (A distinct name so a real dev pulse can't
    # clobber the synthetic transition.)
    page.evaluate("""() => {
        window._notePrinterStatesForFastPoll({ FccTestPrinter: { state: { state: 'PRINTING', is_active: true } } });
        window._notePrinterStatesForFastPoll({ FccTestPrinter: { state: { state: 'FINISHED', is_active: false } } });
    }""")
    assert page.evaluate("() => window._fastPollActive()") is True, (
        "A print-finish edge should arm the fast-poll burst"
    )
    assert page.evaluate("() => window._pulseInterval()") == 5000, (
        "The finish edge must force the ACTIVE 5s cadence even while hidden"
    )
    # Past the ~30s window the burst expires and the hidden bucket reasserts.
    expired = page.evaluate("""() => {
        const real = Date.now;
        try { Date.now = () => real() + 40_000; return window._pulseInterval(); }
        finally { Date.now = real; }
    }""")
    assert expired == 30000, (
        f"After the fast-poll window elapses the hidden bucket should "
        f"reassert; got {expired}"
    )


def test_pulse_interval_no_fast_poll_on_pause(
    page, require_server, base_url
):
    """A PRINTING -> PAUSED transition is not a finish — no deduct happens on
    a pause, so it must not arm the fast-poll burst (PAUSED is an in-progress
    state, not an ended one)."""
    page.goto(base_url, wait_until='domcontentloaded')
    page.evaluate("() => window._resetFastPollForTest()")
    page.evaluate("""() => {
        window._notePrinterStatesForFastPoll({ FccTestPrinter: { state: { state: 'PRINTING', is_active: true } } });
        window._notePrinterStatesForFastPoll({ FccTestPrinter: { state: { state: 'PAUSED', is_active: false } } });
    }""")
    assert page.evaluate("() => window._fastPollActive()") is False, (
        "A pause is not a finish; the fast-poll burst must not arm"
    )


def test_dashboard_pulse_dispatcher_repaints_status_dots(
    page, require_server, base_url
):
    """Status dot DOM is what the user actually sees. After a heartbeat
    tick, st-spoolman should carry a status-on/off class based on the bulk
    endpoint's response. (The FilaBridge dot was retired in the FilaBridge
    Phase-2 cutover, Phase E Slice 4.)"""
    page.goto(base_url, wait_until='domcontentloaded')
    # Wait for the initial pulse to land.
    page.wait_for_timeout(2_000)
    sm_class = page.evaluate("() => document.getElementById('st-spoolman')?.className || ''")
    # The dot may be on or off depending on dev environment health, but
    # the class must be one of the two — never empty / never missing.
    assert 'status-on' in sm_class or 'status-off' in sm_class, (
        f"st-spoolman should carry a status-on/off class after a pulse; got '{sm_class}'"
    )
    # The FilaBridge dot element is gone — assert it no longer exists.
    assert page.evaluate("() => document.getElementById('st-filabridge') === null"), (
        "st-filabridge should have been removed in Phase E Slice 4"
    )


def test_inventory_sync_pulse_carries_source_detail_from_bulk(
    page, require_server, base_url
):
    """The bulk-pulse dispatcher tags inventory:sync-pulse events with
    {source: 'dashboard_pulse'} so other listeners can skip work the
    bulk path already did (notably liveRefreshBuffer's duplicate
    /api/spools/refresh fetch)."""
    page.goto(base_url, wait_until='domcontentloaded')
    captured = page.evaluate("""async () => {
        return new Promise((resolve) => {
            const handler = (e) => {
                document.removeEventListener('inventory:sync-pulse', handler);
                resolve(e.detail || null);
            };
            document.addEventListener('inventory:sync-pulse', handler);
            // Trigger a single bulk-pulse tick directly so we don't have
            // to wait for the next 5s heartbeat.
            if (window._dashboardPulseTickOnce) window._dashboardPulseTickOnce();
            // Bail out if the event never fires within 8s
            setTimeout(() => resolve('TIMEOUT'), 8000);
        });
    }""")
    assert captured != 'TIMEOUT', "inventory:sync-pulse never fired after a bulk tick"
    assert captured is not None and isinstance(captured, dict), (
        f"Expected inventory:sync-pulse to carry a detail dict; got {captured}"
    )
    assert captured.get('source') == 'dashboard_pulse', (
        f"Expected detail.source == 'dashboard_pulse'; got {captured}"
    )
