"""Config / Admin modal smoke test.

Verifies the ⚙️ button in the nav bar opens the modal and the modal carries its
expected sections. (The original FilaBridge ↔ Spoolman Reconcile section was
retired in the FilaBridge Phase-2 cutover, Phase E — FCC is now the single
source of truth, so there is nothing to reconcile.)
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_config_button_opens_modal(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof window.openConfigModal === 'function'", timeout=10000)

    btn = page.locator("#btn-config")
    expect(btn).to_be_visible()
    btn.click()

    modal = page.locator("#configModal")
    expect(modal).to_be_visible(timeout=5000)
    # Surviving sections are present (Filament Attributes manager + Build Info).
    expect(page.locator("#btn-config-attrs-scan")).to_be_visible()
    expect(page.locator("#config-build-info")).to_be_visible()
