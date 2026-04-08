import re
from playwright.sync_api import Page, expect

def test_filament_new_spool_wizard(page: Page):
    """
    E2E test verifying that clicking 'New Spool' from the Filament details modal
    correctly launches the wizard, pre-filled in 'Existing' mode.
    """
    page.goto("http://localhost:8000")

    # 1. Open Search Offcanvas
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_selector("#offcanvasSearch", timeout=5000)

    # 2. Trigger search
    search_input = page.locator('#global-search-query')
    search_input.fill("a")
    
    # 3. Open Spool Details first (most reliable way to get to its parent Filament)
    page.wait_for_selector("#global-search-results .fcc-card-action-btn[title='View Details']", timeout=10000)
    page.locator("#global-search-results .fcc-card-action-btn[title='View Details']").first.click()

    spool_modal = page.locator("#spoolModal")
    expect(spool_modal).to_be_visible()

    # 4. From Spool details, click "Swatch" to open Filament details
    btn_swatch = page.locator("#btn-spool-to-filament")
    expect(btn_swatch).to_be_visible()
    btn_swatch.click()

    filament_modal = page.locator("#filamentModal")
    expect(filament_modal).to_be_visible()

    # 5. Filament ID must be present
    fil_id_text = page.locator("#fil-detail-id").text_content()
    assert fil_id_text is not None and len(fil_id_text.strip()) > 0

    # 6. Click 'New Spool'
    page.locator("#btn-fil-new-spool").click()

    # 7. Wait for wizard modal
    wizard_modal = page.locator("#wizardModal")
    expect(wizard_modal).to_be_visible()

    # 8. Check if Wizard switched to Existing Mode
    status_msg = page.locator("#wiz-status-msg")
    expect(status_msg).to_contain_text("successfully pre-filled", timeout=5000)
    
    expect(page.locator("#btn-type-existing")).to_have_class(re.compile(r"wiz-active-card"))
    
    # Ensure Spool used weight defaults to 0
    expect(page.locator("#wiz-spool-used")).to_have_value("0")
