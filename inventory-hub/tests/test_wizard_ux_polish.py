"""
Tests for the Wizard UX Polish bundle (feature/wizard-ux-polish):
  - FID/SID badges in the modal title + Step 2 / Step 3 headers
  - Vendor and Location searchable combobox (keyboard filter + arrow/Enter)
  - Nested Swal replaced by toast in wizardPromptNewChoice

UI assertions use the seeded container; a few use the search API to find
a real spool to drive the edit wizard.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


# --- Helpers ----------------------------------------------------------------

def _open_wizard_fresh(page: Page):
    """Open the add-inventory wizard without any edit/clone context."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible()


def _open_wizard_for_edit(page: Page, spool_id: int):
    """Open the edit wizard for a specific spool id."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.evaluate(f"window.openEditWizard && window.openEditWizard({spool_id})")
    expect(page.locator("#wizardModal")).to_be_visible()
    # Wait until the fetch resolves and step 2 is revealed
    expect(page.locator("#step-2-filament")).to_be_visible(timeout=10_000)


# --- Context badges ---------------------------------------------------------

def test_context_label_hidden_in_add_mode(page: Page):
    """In fresh add-new mode, context badges should all be empty/hidden."""
    _open_wizard_fresh(page)

    title_label = page.locator("#wiz-context-label")
    expect(title_label).to_have_text("")

    step2_ctx = page.locator("#wiz-step2-fil-context")
    step3_ctx = page.locator("#wiz-step3-spl-context")
    # Hidden via style="display:none"; Playwright reports them as not visible.
    expect(step2_ctx).not_to_be_visible()
    expect(step3_ctx).not_to_be_visible()


def test_context_label_shows_ids_on_edit(page: Page, api_base_url: str):
    """Edit wizard should show Spool and Filament badges in title + section headers."""
    # Find a real spool id via the search API. The UI offcanvas-search hits
    # /api/search which returns {results: [...], success: true}; each result
    # carries an id plus a nested filament block.
    r = requests.get(f"{api_base_url}/api/search?q=", timeout=5)
    if not r.ok:
        pytest.skip("search API unavailable")
    results = (r.json() or {}).get("results") or []
    if not results:
        pytest.skip("no spools to edit in this environment")
    spool_id = results[0].get("id")
    if not spool_id:
        pytest.skip("search result missing id")

    # Pull filament id from spool_details so we assert on the correct value
    detail = requests.get(f"{api_base_url}/api/spool_details", params={"id": spool_id}, timeout=5).json()
    filament_id = (detail or {}).get("filament", {}).get("id")

    _open_wizard_for_edit(page, spool_id)

    # Title badge always shows Spool immediately; Filament fills in after fetch.
    title_label = page.locator("#wiz-context-label")
    expect(title_label).to_contain_text(f"Spool #{spool_id}")
    if filament_id is not None:
        expect(title_label).to_contain_text(f"Filament #{filament_id}")

    # Step 3 (spool) badge should be visible and match.
    step3_badge = page.locator("#wiz-step3-spl-badge")
    expect(step3_badge).to_be_visible()
    expect(step3_badge).to_contain_text(f"Spool #{spool_id}")

    if filament_id is not None:
        step2_badge = page.locator("#wiz-step2-fil-badge")
        expect(step2_badge).to_be_visible()
        expect(step2_badge).to_contain_text(f"Filament #{filament_id}")


# --- Searchable comboboxes --------------------------------------------------

def test_vendor_combobox_filters_on_type(page: Page):
    """Typing into the vendor search input filters the dropdown options."""
    _open_wizard_fresh(page)

    search = page.locator("#wiz-fil-vendor-search")
    expect(search).to_be_visible()
    search.click()

    dropdown = page.locator("#dropdown-vendor")
    expect(dropdown).to_be_visible()

    # Count all options before filtering
    all_opts = dropdown.locator(".autocomplete-option")
    total = all_opts.count()
    if total < 2:
        pytest.skip("need at least 2 vendor options to test filtering")

    # Type a likely-unique substring of the first option to narrow the list
    first_label = all_opts.first.inner_text().strip()
    # Use first 3 chars (avoids matching "Generic" which is always present)
    typed = first_label[:3]
    search.fill(typed)

    filtered = dropdown.locator(".autocomplete-option")
    assert filtered.count() <= total, "filtered list should be <= full list"
    # Every visible option should contain the typed substring (case-insensitive)
    for i in range(filtered.count()):
        text = filtered.nth(i).inner_text().lower()
        assert typed.lower() in text


def test_location_combobox_enter_selects(page: Page):
    """Arrow-Enter on the location combobox populates the hidden LocationID."""
    _open_wizard_fresh(page)

    search = page.locator("#wiz-spool-location-search")
    hidden = page.locator("#wiz-spool-location")
    expect(search).to_be_visible()

    search.click()
    dropdown = page.locator("#dropdown-location")
    expect(dropdown).to_be_visible()

    opts = dropdown.locator(".autocomplete-option")
    if opts.count() < 2:
        pytest.skip("need at least 2 location options to test keyboard navigation")

    # Skip the "-- Unassigned --" row (index 0) by pressing ArrowDown twice
    search.press("ArrowDown")
    search.press("ArrowDown")
    search.press("Enter")

    # Hidden input should now hold the LocationID of option #1 (0-indexed)
    picked = opts.nth(1).get_attribute("data-value")
    expect(hidden).to_have_value(picked or "")
    # Visible input should show the matching Name
    expected_label = opts.nth(1).get_attribute("data-label") or ""
    expect(search).to_have_value(expected_label)
