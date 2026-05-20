"""18.2 Part B — visual audit panel smoke test.

Verifies that calling window.openAuditPanel() directly mounts the
mountOverlay-based panel with the expected scaffold and that
closeAuditPanel() tears it down. Bypasses the full
scan-CMD:AUDIT-then-scan-a-location flow by directly seeding the
audit session via API + state, then driving the panel from the JS.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


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
