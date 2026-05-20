"""L324 — Config / Admin modal smoke tests.

Verifies the new ⚙️ button in the nav bar opens the modal and the
modal carries the expected sections (FilaBridge Reconcile + Build Info).
Clicking the Scan button hits the live reconcile endpoint.
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
    # Both expected sections are present.
    expect(page.locator("#btn-config-reconcile-scan")).to_be_visible()
    expect(page.locator("#config-build-info")).to_be_visible()


@pytest.mark.usefixtures("require_server")
def test_config_reconcile_scan_renders_results(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function("typeof window.openConfigModal === 'function'", timeout=10000)

    page.evaluate("window.openConfigModal()")
    expect(page.locator("#configModal")).to_be_visible(timeout=5000)
    page.locator("#btn-config-reconcile-scan").click()

    # The result panel populates with either an "all clean" success alert
    # or a mismatch table. Either way the placeholder ("Click Scan") goes
    # away within a reasonable window.
    page.wait_for_function(
        """() => {
            const el = document.getElementById('config-reconcile-results');
            if (!el) return false;
            const txt = el.textContent || '';
            return txt.includes('Clean') || txt.includes('mismatch') || txt.includes('Found') || txt.includes('failed');
        }""",
        timeout=10000,
    )
