"""Group 17.2 — clicking "Queue all active spools" on the Filament Details
modal must NOT auto-open the Print Queue modal. The friction case Derek
flagged: while queuing labels from multiple filaments, the auto-open kept
interrupting the workflow.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


def _find_filament_with_spool(api_base_url: str):
    """Locate the first filament that has at least one spool in inventory."""
    r = requests.get(f"{api_base_url}/api/filaments", timeout=10)
    if not r.ok:
        return None
    payload = r.json()
    fils = payload.get('filaments') if isinstance(payload, dict) else payload
    for fil in fils or []:
        fid = fil.get('id')
        if not fid:
            continue
        sr = requests.get(f"{api_base_url}/api/spools_by_filament?id={fid}&allow_archived=false", timeout=5)
        if sr.ok and isinstance(sr.json(), list) and len(sr.json()) > 0:
            return fid
    return None


@pytest.mark.usefixtures("require_server")
def test_queue_all_active_spools_does_not_auto_open_queue_modal(page: Page, base_url: str, api_base_url: str):
    fid = _find_filament_with_spool(api_base_url)
    if not fid:
        pytest.skip("No filaments with at least one spool in dev environment.")

    page.goto(base_url)
    # openFilamentDetails is declared `const` at script scope in inv_details.js,
    # not on window — same shape as `state`. Reach it by bare name.
    page.wait_for_function("typeof openFilamentDetails === 'function'", timeout=10000)

    # Spy on openQueueModal so we can prove it was NOT invoked.
    page.evaluate(
        """() => {
            window.__queueModalOpens = 0;
            const orig = window.openQueueModal;
            window.openQueueModal = function () {
                window.__queueModalOpens += 1;
                if (typeof orig === 'function') orig.apply(this, arguments);
            };
        }"""
    )

    page.evaluate(f"openFilamentDetails({fid})")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)
    # Wait for the queue-all button to be revealed (the handler shows it
    # after /api/spools_by_filament returns non-empty).
    btn = page.locator("#btn-queue-all-spools")
    btn.wait_for(state="visible", timeout=5000)

    btn.click()
    # Give the click handler a beat to run.
    page.wait_for_timeout(500)

    opens = page.evaluate("() => window.__queueModalOpens")
    assert opens == 0, f"openQueueModal should NOT auto-fire on Queue All (got {opens})"

    # The print queue modal itself should also remain hidden.
    queue_modal = page.locator("#queueModal")
    expect(queue_modal).to_be_hidden(timeout=2000)
