"""Group 17.1 — the Filament Details modal shows swatch + label-confirmed
status badges so the user can see at a glance whether a swatch has been
printed and whether the printed label has been physically confirmed.

Reads from existing extras:
  - `sample_printed` (true / false / missing)
  - `needs_label_print` (false=confirmed, true=needs print, missing=unknown)
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
def test_filament_details_renders_sample_and_label_status_rows(page: Page, base_url: str, api_base_url: str, reset_dom_state_js: str):
    fil = _find_any_filament(api_base_url)
    if not fil:
        pytest.skip("No filaments in dev environment.")
    fid = fil.get('id')

    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof openFilamentDetails === 'function' && modals && modals.filamentModal", timeout=10000)
    page.evaluate(f"openFilamentDetails({fid})")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)

    sample_el = page.locator("#fil-detail-sample-status")
    label_el = page.locator("#fil-detail-label-status")
    expect(sample_el).to_be_visible(timeout=3000)
    expect(label_el).to_be_visible(timeout=3000)

    sample_txt = sample_el.inner_text().strip()
    label_txt = label_el.inner_text().strip()
    # Either confirmed-status, needs-print, or unknown — all are valid for an
    # arbitrary dev filament. Just assert the badge populated with a known
    # state and isn't empty / placeholder.
    assert sample_txt in {"✅ Yes", "No", "unknown"}, f"unexpected sample status: {sample_txt!r}"
    assert label_txt in {"✅ Confirmed", "🖨️ Needs print", "unknown"}, f"unexpected label status: {label_txt!r}"
