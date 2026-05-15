"""L26 follow-up — opening the wizard while a Spool/Filament Details
modal is open should forcibly close the details modal first. Mirrors
the details↔details sibling-close pattern shipped in Group 8.3
(2026-05-12).

Symptom Derek reproed 2026-04-29: opening the Add/Edit Wizard on top
of a details modal triggered a race where the silent-refresh path's
promise landed mid-open, leaving state.processing stuck true and
freezing barcode scans / FilaBridge updates until a hard refresh.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


def _find_any_filament(api_base_url: str):
    r = requests.get(f"{api_base_url}/api/filaments", timeout=10)
    if not r.ok:
        return None
    payload = r.json()
    fils = payload.get('filaments') if isinstance(payload, dict) else payload
    return (fils or [None])[0]


@pytest.mark.usefixtures("require_server")
def test_opening_wizard_closes_filament_details(page: Page, base_url: str, api_base_url: str, reset_dom_state_js: str):
    fil = _find_any_filament(api_base_url)
    if not fil:
        pytest.skip("No filaments in dev environment.")
    fid = fil.get('id')

    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof openFilamentDetails === 'function' && typeof window.openWizardModal === 'function' && modals && modals.filamentModal",
        timeout=10000,
    )

    # Step 1: open filament details
    page.evaluate(f"openFilamentDetails({fid})")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)

    # Step 2: launch the wizard — sibling-close should hide filamentModal.
    page.evaluate("window.openWizardModal()")
    # Wait for the wizard to appear and the details modal to disappear.
    expect(page.locator("#wizardModal")).to_be_visible(timeout=5000)
    # The sibling-close uses a 400ms retry so give it room.
    expect(page.locator("#filamentModal")).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server")
def test_hide_all_details_modals_helper_exposed(page: Page, base_url: str):
    """Smoke: window.hideAllDetailsModals is exposed for callers other
    than the wizard (e.g. future scan paths that need the same
    sibling-close discipline)."""
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    typeof = page.evaluate("() => typeof window.hideAllDetailsModals")
    assert typeof == "function", f"helper should be exposed; got typeof={typeof!r}"
