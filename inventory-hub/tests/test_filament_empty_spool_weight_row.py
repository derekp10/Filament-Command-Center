"""Group 17.5 — the Filament Details modal surfaces the resolved
Empty Spool Weight + inheritance badge so the user doesn't have to
open the Edit modal to see what value the backfill cascade will use.
Uses weight_utils.js's `resolveEmptySpoolWeightSource` cascade.
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
def test_filament_details_modal_shows_empty_spool_weight_row(page: Page, base_url: str, api_base_url: str, reset_dom_state_js: str):
    fil = _find_any_filament(api_base_url)
    if not fil:
        pytest.skip("No filaments in dev environment.")
    fid = fil.get('id')

    page.goto(base_url)
    # Wait for DOMContentLoaded init to finish wiring up `modals` (filamentModal
    # is registered in scripts.html's DOMContentLoaded handler). Without this
    # the `openFilamentDetails` call resolves but modals.filamentModal.show()
    # silently no-ops.
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof openFilamentDetails === 'function' && modals && modals.filamentModal", timeout=10000)
    page.evaluate(f"openFilamentDetails({fid})")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)

    # The new row exists with a value populated by the resolver.
    value_el = page.locator("#fil-detail-empty-spool-weight")
    badge_el = page.locator("#fil-detail-empty-spool-source")
    expect(value_el).to_be_visible(timeout=3000)
    expect(badge_el).to_be_visible(timeout=3000)

    txt = value_el.inner_text().strip()
    # Either "<N> g" or "—" if neither filament nor vendor has a value.
    assert txt == "—" or txt.endswith(" g"), f"unexpected value text: {txt!r}"
    badge_txt = badge_el.inner_text().strip()
    assert badge_txt in {"not set", "↩ filament", "↩ vendor"}, f"unexpected badge: {badge_txt!r}"
