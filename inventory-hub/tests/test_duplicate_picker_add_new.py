"""Group 17.4 — the legacy-id duplicate picker (`showLegacySpoolPicker`)
must expose an "➕ Add new spool" affordance that routes through
`openNewSpoolFromFilamentWizard` with the parent filament pre-selected.
Covers the case where none of the existing candidates is the right spool.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.usefixtures("require_server")
def test_duplicate_picker_renders_add_new_button(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_function("typeof window.showLegacySpoolPicker === 'function'", timeout=10000)

    # Spy on openNewSpoolFromFilamentWizard so we can prove the chip routes
    # there without actually opening the wizard.
    page.evaluate(
        """() => {
            window.__addNewCalls = [];
            window.openNewSpoolFromFilamentWizard = (fid) => {
                window.__addNewCalls.push(fid);
            };
        }"""
    )

    # Synthetic ambiguous payload — three candidates all on the same filament.
    page.evaluate(
        """() => {
            window.showLegacySpoolPicker({
                legacy_id: '58',
                candidates: [
                    { id: 101, filament_id: 42, display: 'A', remaining_weight: 800, location: 'PM-DB-1' },
                    { id: 102, filament_id: 42, display: 'B', remaining_weight: 500, location: 'LR-MDB-2' },
                    { id: 103, filament_id: 42, display: 'C', remaining_weight: 250, location: 'CR-MDB-1' },
                ],
            }, { onSelect: () => {}, onAbort: () => {} });
        }"""
    )

    add_btn = page.locator("#fcc-legacy-picker-addnew")
    expect(add_btn).to_be_visible(timeout=3000)

    add_btn.click()
    calls = page.evaluate("() => window.__addNewCalls")
    assert calls == [42], f"Add-new should hand off filament id 42; got {calls}"

    # Overlay should be gone after the click.
    expect(page.locator("#fcc-legacy-picker-overlay")).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server")
def test_duplicate_picker_hides_add_new_when_no_filament_id(page: Page, base_url: str):
    """Null-guard: if the candidate list lacks filament metadata, the
    Add-new affordance should be hidden so the user can't trigger a no-op."""
    page.goto(base_url)
    page.wait_for_function("typeof window.showLegacySpoolPicker === 'function'", timeout=10000)
    page.evaluate(
        """() => {
            window.showLegacySpoolPicker({
                legacy_id: '99',
                candidates: [
                    { id: 201, display: 'A', remaining_weight: 800, location: 'PM-DB-1' },
                    { id: 202, display: 'B', remaining_weight: 500, location: 'LR-MDB-2' },
                ],
            }, { onSelect: () => {}, onAbort: () => {} });
        }"""
    )
    expect(page.locator("#fcc-legacy-picker-overlay")).to_be_visible(timeout=3000)
    expect(page.locator("#fcc-legacy-picker-addnew")).to_have_count(0)
