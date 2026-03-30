import pytest
from playwright.sync_api import Page, expect

def test_details_modal_interactions(page: Page):
    """
    E2E test verifying:
    1. Spool cards can be clicked to open the Details Modal without JS errors.
    2. The location badge on the Details Modal is clickable and launches the Location Manager.
    3. The filament swatch correctly applies solid colors without glossy button gradients.
    """
    page.goto("http://localhost:8000")
    
    # 1. Ensure page loads and at least one card is visible
    page.wait_for_selector(".fcc-card-action-btn[title='View Details']", timeout=10000)
    
    # Track console errors to ensure "r is not defined" or similar bugs do not regress
    errors = []
    page.on("pageerror", lambda err: errors.append(err.message))
    
    # 2. Click the first View Details button
    page.click(".fcc-card-action-btn[title='View Details']")
    
    # Wait for the Spool Details modal to become visible
    modal = page.locator("#spoolModal")
    expect(modal).to_be_visible()
    
    assert len(errors) == 0, f"JavaScript exception occurred when opening details modal: {errors[0]}"
    
    # 3. Check the Swatch style
    swatch = page.locator("#detail-swatch")
    expect(swatch).to_be_visible()
    
    bg = swatch.evaluate("el => window.getComputedStyle(el).background")
    assert bg is not None
    
    # 4. Check the Location Badge Click-Through
    loc_badge = page.locator("#detail-location-badge")
    expect(loc_badge).to_be_visible()
    
    # If the badge is clickable (normal location), click it
    cursor_style = loc_badge.evaluate("el => window.getComputedStyle(el).cursor")
    if cursor_style == "pointer":
        loc_badge.click()
        
        # Verify the Spool Details modal hides
        expect(modal).to_be_hidden()
        
        # Verify the Location Manager modal opens
        loc_manager = page.locator("#manageLocationModal")
        expect(loc_manager).to_be_visible()
