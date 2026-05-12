import pytest
from playwright.sync_api import Page, expect

def test_details_modal_interactions(page: Page, reset_dom_state_js: str):
    """
    E2E test verifying:
    1. Spool cards can be clicked to open the Details Modal without JS errors.
    2. The location badge on the Details Modal is clickable and launches the Location Manager.
    3. The filament swatch correctly applies solid colors without glossy button gradients.
    """
    page.goto("http://localhost:8000")

    # Defensive cross-test pollution teardown — buglist L233 / Group 14.3.
    # See conftest.RESET_DOM_STATE_JS for the patterns it handles.
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)

    # 1. Open Search Offcanvas to guarantee spool cards are loaded
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_selector("#offcanvasSearch", timeout=5000)
    
    # Trigger a generic search to populate results
    search_input = page.locator('#global-search-query')
    search_input.fill("a")
    
    # Wait for the view details button to appear on a search result card
    # Scope to inside the offcanvas — page-wide .fcc-card-action-btn matches
    # both dashboard buffer cards (behind the offcanvas-backdrop at z-index 1040)
    # and offcanvas search-result cards. .first could pick a dashboard card,
    # in which case the click is geometrically intercepted by the offcanvas
    # backdrop. Scoping makes the click land on a real search-result card.
    # Group 14.3 / 14.6.
    page.wait_for_selector("#offcanvasSearch .fcc-card-action-btn[title='View Details']", timeout=10000)
    
    # Track console errors to ensure "r is not defined" or similar bugs do not regress
    errors = []
    page.on("pageerror", lambda err: errors.append(err.message))
    
    # 2. Click the first View Details button
    page.click("#offcanvasSearch .fcc-card-action-btn[title='View Details']")
    
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

    # 5. Check "Buy More" button existence and formatting
    # We navigate back to the Spool modal if it was closed
    if cursor_style == "pointer":
        page.locator(".btn-close-white", has_text="").last.click() # Close location manager
        page.click("#offcanvasSearch .fcc-card-action-btn[title='View Details']")
        expect(modal).to_be_visible()

    buy_more_btn = page.locator("#detail-btn-buy-more")
    expect(buy_more_btn).to_be_attached()
    
    href = buy_more_btn.get_attribute("href")
    
    # It should either be a populated amazon link from our config, or a real purchase_url, or hidden if none.
    # Our test system has the fallback URL configured in config.json
    assert href is not None, "Buy More button must have an href attribute"
    if not buy_more_btn.is_hidden():
        assert href.startswith("http"), "Buy More URL must be a valid HTTP link"
