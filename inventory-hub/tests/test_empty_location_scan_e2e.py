"""Empty-location scan warning (Feature-Buglist.md: "if a legacy barcode has no
spools attached, the UI should warn about this").

Scanning a location/legacy label that resolves to ZERO spools used to open the
Location Manager SILENTLY. Now it raises an info toast + a WARNING activity-log
entry before opening the manager (which carries the Add-Spool affordance),
mirroring the existing empty-SLOT path.

We stub the /api/identify_scan response so the test is deterministic (doesn't
depend on dev data containing a guaranteed-empty location). The backend already
returns {type:'location', contents:[]} for an empty location.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _goto(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.processScan === 'function'", timeout=5_000)


def _stub_location_response(page: Page, loc_id: str, contents: list) -> None:
    page.evaluate(
        """([locId, contents]) => {
            const orig = window.fetch;
            window.fetch = function(url, opts) {
                if (typeof url === 'string' && url.includes('/api/identify_scan')) {
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve({
                            type: 'location', id: locId,
                            display: 'LOC: ' + locId, contents: contents,
                        }),
                    });
                }
                return orig.apply(this, arguments);
            };
        }""",
        [loc_id, contents],
    )


def test_empty_location_scan_warns(page: Page):
    _goto(page)
    page.evaluate("state.heldSpools = []")  # empty buffer → not an assign flow
    _stub_location_response(page, "ZZ-EMPTY-TEST", [])

    page.evaluate("window.processScan('LOC:ZZ-EMPTY-TEST', 'test')")

    toast = page.locator(".toast-msg.toast-info")
    expect(toast).to_be_visible(timeout=3_000)
    expect(toast).to_contain_text("is empty")
    expect(toast).to_contain_text("ZZ-EMPTY-TEST")


def test_non_empty_location_scan_does_not_warn(page: Page):
    """A location WITH spools must NOT raise the empty warning — it opens the
    manager (or quick-picks) as before."""
    _goto(page)
    page.evaluate("state.heldSpools = []")
    _stub_location_response(
        page, "ZZ-FULL-TEST",
        [{"id": 9999, "display": "Test Spool", "color": "#abcabc",
          "remaining_weight": 500, "slot": 2}],
    )

    page.evaluate("window.processScan('LOC:ZZ-FULL-TEST', 'test')")
    # Give the handler a beat to run.
    page.wait_for_timeout(500)
    # No "is empty" info toast.
    assert page.evaluate(
        "Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
        ".every(t => !t.innerText.includes('is empty'))"
    ) is True
