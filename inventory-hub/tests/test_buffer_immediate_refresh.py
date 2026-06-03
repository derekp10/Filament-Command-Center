"""Buffer-card latency fix (buglist 2026-06-02): a local "something moved"
signal (scan-assign, context-assign, quick-swap, eject) should refresh the
active buffer cards' underlying data immediately rather than waiting up to a
full adaptive-cadence window (5s / 15s / 30s) for the next dashboard pulse.

The fix wires `inventory:locations-changed` → `liveRefreshBuffer()` and makes
`performContextAssign` + `doEject` dispatch that canonical event. These tests
exercise the wiring deterministically by stubbing the buffer/refresh endpoints.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect


def _stub_buffer_endpoints(page: Page, fresh: dict):
    # Keep the 2s loadBuffer poll from clobbering the seeded buffer or
    # persisting it back to the real dev server.
    def _buffer(route):
        if route.request.method == "POST":
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.fulfill(status=200, content_type="application/json", body="[]")
    page.route("**/api/state/buffer", _buffer)
    # The immediate refresh path posts here; echo fresh data so we can also
    # confirm the card repaints.
    page.route(
        "**/api/spools/refresh",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(fresh)
        ),
    )


def _seed_held_spool(page: Page, sid: int, remaining: int):
    page.evaluate(
        """([sid, remaining]) => {
            state.heldSpools = [{
                id: sid, display: 'Seeded Spool', color: '#888888',
                color_direction: 'longitudinal', remaining_weight: remaining,
                details: 'seed', archived: false, location: 'Room LR'
            }];
            // Protect the seed from the 2s loadBuffer server-overwrite (grace
            // window keys off this timestamp).
            window.lastLocalBufferChange = Date.now();
            if (window.renderBuffer) window.renderBuffer();
        }""",
        [sid, remaining],
    )


@pytest.mark.usefixtures("require_server")
def test_locations_changed_triggers_immediate_buffer_refresh(page: Page, base_url: str, reset_dom_state_js: str):
    sid = 987654
    _stub_buffer_endpoints(page, fresh={str(sid): {
        "display": "Seeded Spool", "color": "#888888",
        "color_direction": "longitudinal", "remaining_weight": 321,
        "details": "fresh", "archived": False, "location": "Room CR",
    }})
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof window.liveRefreshBuffer === 'function' && typeof state !== 'undefined'", timeout=10000)

    _seed_held_spool(page, sid, remaining=500)

    # The immediate refresh must fire as a direct result of the event — well
    # under the 5s active cadence. /api/spools/refresh is ONLY hit by the
    # liveRefreshBuffer path (the pulse uses /api/dashboard_pulse), so observing
    # it within 2s ties it to our dispatch.
    with page.expect_request("**/api/spools/refresh", timeout=2000) as req_info:
        page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:locations-changed'))")
    assert req_info.value.method == "POST"
    posted = req_info.value.post_data_json
    assert sid in (posted.get("spools") or []), f"refresh should request the held id, got {posted!r}"

    # And the card should repaint with the fresh weight from the stubbed payload.
    page.wait_for_function(
        "(sid) => { const s = (state.heldSpools||[]).find(x => x.id === sid); return s && s.remaining_weight === 321; }",
        arg=sid,
        timeout=3000,
    )


@pytest.mark.usefixtures("require_server")
def test_immediate_refresh_listener_is_registered(page: Page, base_url: str, reset_dom_state_js: str):
    # Lighter guard: with an EMPTY buffer the dispatch must NOT throw and
    # liveRefreshBuffer no-ops (no /api/spools/refresh request). This pins the
    # "no-op on empty buffer" contract the fix relies on for cheapness.
    fired = {"n": 0}
    page.route(
        "**/api/spools/refresh",
        lambda route: (fired.__setitem__("n", fired["n"] + 1), route.fulfill(
            status=200, content_type="application/json", body="{}"))[1],
    )
    page.route("**/api/state/buffer", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=("{}" if route.request.method == "POST" else "[]")))
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof window.liveRefreshBuffer === 'function' && typeof state !== 'undefined'", timeout=10000)
    page.evaluate("() => { state.heldSpools = []; }")
    page.evaluate("() => document.dispatchEvent(new CustomEvent('inventory:locations-changed'))")
    # Give any erroneous fetch a beat to fire.
    page.wait_for_timeout(400)
    assert fired["n"] == 0, "liveRefreshBuffer should no-op on an empty buffer"
