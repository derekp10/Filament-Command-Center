"""L124 regression — scanning a toolhead with multiple spools in the
buffer must only assign the topmost spool. The rest stay in the buffer.

Pre-fix behavior sent the entire buffer to `/api/smart_move`, and the
backend's per-spool loop wrote every spool's Spoolman `location` to the
toolhead — breaking filabridge's one-spool-one-toolhead invariant and
making all the buffered spools appear loaded on the same printer.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page


@pytest.mark.usefixtures("require_server")
def test_toolhead_scan_with_multi_spool_buffer_sends_only_topmost(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_function("typeof window.processScan === 'function'", timeout=10000)
    # Wait until allLocations is populated so the LOC type lookup hits.
    page.wait_for_function(
        "Array.isArray(state.allLocations) && state.allLocations.some(l => (l.Type || '').toLowerCase().includes('tool'))",
        timeout=10000,
    )

    # Pick a real toolhead from the live location list so the response from
    # /api/identify_scan returns res.type === 'location' (not 'error').
    toolhead_id = page.evaluate(
        """() => {
            const th = state.allLocations.find(l => (l.Type || '').toLowerCase().includes('tool'));
            return th ? th.LocationID : null;
        }"""
    )
    assert toolhead_id, "no toolhead in dev environment"

    # Stub /api/buffer so background polling can't overwrite the test's
    # synthetic spools with real Spoolman state. Then seed two fakes and
    # mark a recent local change so the race-protection guard skips the
    # next loadBuffer overwrite (covers any in-flight poll).
    page.route("**/api/buffer", lambda route: route.fulfill(
        status=200, content_type='application/json',
        body=json.dumps([
            { "id": 9991, "display": "TOP", "color": "#ff0000", "remaining_weight": 500 },
            { "id": 9992, "display": "BOTTOM", "color": "#00ff00", "remaining_weight": 500 },
        ]),
    ))
    page.evaluate(
        """() => {
            window.lastLocalBufferChange = Date.now();
            state.heldSpools = [
                { id: 9991, display: 'TOP', color: '#ff0000', remaining_weight: 500 },
                { id: 9992, display: 'BOTTOM', color: '#00ff00', remaining_weight: 500 },
            ];
        }"""
    )

    # Intercept the /api/smart_move POST and return a synthetic success.
    captured = {}
    def handle(route):
        req = route.request
        if req.method == 'POST' and req.url.endswith('/api/smart_move'):
            try:
                captured['payload'] = json.loads(req.post_data or '{}')
            except json.JSONDecodeError:
                captured['payload'] = None
            route.fulfill(
                status=200,
                content_type='application/json',
                body=json.dumps({"status": "success", "filabridge_ok": True}),
            )
        else:
            route.continue_()
    page.route("**/api/smart_move", handle)

    # Drive the scan through the same router the real input flow uses.
    page.evaluate(f"window.processScan('LOC:{toolhead_id}', 'test')")

    # Poll for the captured payload (fetch is async).
    page.wait_for_function(
        "() => state.heldSpools.length === 1 && state.heldSpools[0].id === 9992",
        timeout=5000,
    )

    assert captured.get('payload'), "smart_move was not called"
    sent = captured['payload'].get('spools', [])
    assert sent == [9991], (
        f"toolhead scan should send only the topmost spool, got {sent}"
    )
    # The non-topmost spool stays in the buffer for the next destination.
    remaining = page.evaluate("() => state.heldSpools.map(s => s.id)")
    assert remaining == [9992], f"buffer remainder unexpected: {remaining}"


@pytest.mark.usefixtures("require_server")
def test_multispool_dryer_box_scan_still_sends_full_buffer(page: Page, base_url: str):
    """Negative regression: multi-spool destinations (dryer box, shelf, etc.)
    should still get the entire buffer in one call — the L124 fix is scoped
    to single-occupancy targets only."""
    page.goto(base_url)
    page.wait_for_function("typeof window.processScan === 'function'", timeout=10000)
    page.wait_for_function(
        "Array.isArray(state.allLocations) && state.allLocations.some(l => parseInt(l['Max Spools']||'0') > 1)",
        timeout=10000,
    )
    multi_id = page.evaluate(
        """() => {
            const m = state.allLocations.find(l => parseInt(l['Max Spools']||'0') > 1 && !(l.Type||'').toLowerCase().includes('tool'));
            return m ? m.LocationID : null;
        }"""
    )
    assert multi_id, "no multi-spool non-toolhead in dev environment"

    page.evaluate(
        """() => {
            state.heldSpools = [
                { id: 9991, display: 'TOP', color: '#ff0000', remaining_weight: 500 },
                { id: 9992, display: 'BOTTOM', color: '#00ff00', remaining_weight: 500 },
            ];
        }"""
    )

    captured = {}
    def handle(route):
        req = route.request
        if req.method == 'POST' and req.url.endswith('/api/smart_move'):
            try:
                captured['payload'] = json.loads(req.post_data or '{}')
            except json.JSONDecodeError:
                captured['payload'] = None
            route.fulfill(
                status=200,
                content_type='application/json',
                body=json.dumps({"status": "success", "filabridge_ok": True}),
            )
        else:
            route.continue_()
    page.route("**/api/smart_move", handle)

    page.evaluate(f"window.processScan('LOC:{multi_id}', 'test')")
    page.wait_for_function("() => state.heldSpools.length === 0", timeout=5000)

    assert captured.get('payload'), "smart_move was not called"
    sent = captured['payload'].get('spools', [])
    assert sorted(sent) == [9991, 9992], (
        f"multi-spool target should receive both spools, got {sent}"
    )
