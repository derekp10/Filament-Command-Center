"""18.2 Part B — visual audit panel smoke test.

Verifies that calling window.openAuditPanel() directly mounts the
mountOverlay-based panel with the expected scaffold and that
closeAuditPanel() tears it down. Bypasses the full
scan-CMD:AUDIT-then-scan-a-location flow by directly seeding the
audit session via API + state, then driving the panel from the JS.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect


# An ACTIVE session payload, shaped like /api/audit_session's enriched response.
# The panel's 2s poll closes itself the moment it sees `active: false`, so this
# has to be in place before openAuditPanel() runs.
_ACTIVE_SESSION = {
    "active": True,
    "location_id": "PM-DB-1",
    "stats": {"total_expected": 1, "found": 1, "missing": 0, "rogue": 0},
    "expected": [{
        "id": 1,
        "display": "Test Spool",
        "color": "#ff0000",
        "color_direction": "longitudinal",
        "multi_color_hexes": "",
        "remaining_weight": 500,
        "slot": "1",
        "found": True,
    }],
    "rogue": [],
    "idle_timeout_min": 20,
}


@pytest.mark.usefixtures("require_server")
def test_audit_panel_opens_and_closes(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof window.openAuditPanel === 'function' && typeof window.closeAuditPanel === 'function'"
        " && typeof window.mountOverlay === 'function'",
        timeout=10000,
    )

    # Group 38 — this test used to race the panel's OWN correct behaviour and
    # was a load-sensitive flake (caught 2026-08-07: the overlay mounted and
    # rendered its title, then `#fcc-audit-panel-close` was "element(s) not
    # found").
    #
    # `openAuditPanel()` mounts synchronously and immediately starts `_poll()`;
    # on `{active: false}` that poll calls `closeAuditPanel()` and tears the
    # whole overlay down (inv_cmd.js). The test never started an audit — its
    # docstring claims it seeds one, but the body never did — so dev answers
    # `{"active": false}` and the panel is ENTITLED to close. It passed only
    # when all three assertions beat the fetch; under sweep load the fetch won.
    #
    # This is a visual-panel smoke test, so stub the data source and let it test
    # the panel. The endpoint itself is covered by test_audit_session_endpoint.py,
    # and stubbing keeps the test from having to start (and then clean up) a real
    # audit session on shared dev.
    page.route(
        "**/api/audit_session",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_ACTIVE_SESSION),
        ),
    )

    page.evaluate("window.openAuditPanel()")
    overlay = page.locator("#fcc-audit-panel-overlay")
    expect(overlay).to_be_visible(timeout=5000)
    # Title carries the audit emoji and "Audit in Progress" text.
    expect(overlay).to_contain_text("Audit in Progress")
    # The Hide button exists; click it should tear down.
    hide = page.locator("#fcc-audit-panel-close")
    expect(hide).to_be_visible()
    hide.click()
    expect(page.locator("#fcc-audit-panel-overlay")).to_be_hidden(timeout=3000)


@pytest.mark.usefixtures("require_server")
def test_audit_panel_closes_itself_when_no_audit_is_active(
    page: Page, base_url: str, reset_dom_state_js: str
):
    """The panel's own poll must tear it down once the session goes inactive.

    Group 38 — this is pinned for two reasons. It is CORRECT behaviour worth
    keeping (a panel for an audit that is no longer running should not linger),
    and it is precisely the mechanism that made the sibling test above a
    load-sensitive flake: with no audit active, `openAuditPanel()` mounts and
    then immediately closes itself, so the sibling only passed when its three
    assertions beat the `/api/audit_session` fetch. Making that behaviour
    explicit here means the next person to see the panel "vanish" finds the
    reason in a test name rather than in a truncated traceback.
    """
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof window.openAuditPanel === 'function' && typeof window.mountOverlay === 'function'",
        timeout=10000,
    )

    page.route(
        "**/api/audit_session",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"active": False}),
        ),
    )

    page.evaluate("window.openAuditPanel()")
    # Mounted synchronously, then removed by the first poll tick.
    expect(page.locator("#fcc-audit-panel-overlay")).to_be_hidden(timeout=5000)
