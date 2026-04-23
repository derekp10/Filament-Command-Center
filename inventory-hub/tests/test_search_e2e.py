import re
from playwright.sync_api import Page, expect

def test_global_search_offcanvas_visibility(page: Page):
    """Verifies the Search Offcanvas wrapper opens successfully via the Navigation bar."""
    page.goto("http://localhost:8000")
    
    # Check for the SEARCH button in the nav and click it
    search_btn = page.locator('nav button:has-text("SEARCH")')
    expect(search_btn).to_be_visible()
    search_btn.click()
    
    # Wait for the Offcanvas to slide in
    offcanvas = page.locator('#offcanvasSearch')
    expect(offcanvas).to_be_visible()
    
    # Check title
    expect(offcanvas.locator('.offcanvas-title')).to_contain_text("FIND SPOOL")
    
    # Close it
    page.locator('#offcanvasSearch .btn-close').click()
    page.wait_for_timeout(500)  # Wait for animation
    expect(offcanvas).not_to_be_visible()

def test_global_search_realtime_typing(page: Page):
    """Verifies that typing inside the search box triggers the SearchEngine loader and renders results."""
    page.goto("http://localhost:8000")
    page.locator('nav button:has-text("SEARCH")').click()
    
    # Type a query
    search_input = page.locator('#global-search-query')
    search_input.fill("Prusament")
    
    # It should briefly show "Searching Network..."
    results_box = page.locator('#global-search-results')
    # Use relaxed locator parsing because it renders fast if running locally
    page.wait_for_timeout(1000) # Wait for debounce + API
    
    # Assuming the API returned data or an error (we just want to make sure it processed)
    # The default state is a 💬, if it went away, the search engaged
    # (Checking for specific text might flap on empty DBs, but 💬 disappearing is a solid reactive signal)
    expect(results_box).not_to_contain_text("💬")

def test_global_search_js_callback_mode(page: Page):
    """Verifies that the generic fallback mode triggers appropriate contextual UI hints."""
    page.goto("http://localhost:8000")
    
    # Force open the search engine via JS with a mock callback
    page.evaluate("SearchEngine.open({ callback: (id) => window._testSelectedId = id })")
    
    # The context hint should now be warning and visible
    ctx = page.locator('#global-search-context')
    expect(ctx).to_be_visible()
    expect(ctx).to_contain_text("Select a spool")
    
    # Close it out safely
    page.locator('#offcanvasSearch .btn-close').click()

def test_global_search_clear_color(page: Page):
    """Verifies the clear color button resets the color hex input field."""
    page.goto("http://localhost:8000")
    page.locator('nav button:has-text("SEARCH")').click()
    
    # Wait for the panel to be visible to ensure elements are intractable
    expect(page.locator('#offcanvasSearch')).to_be_visible()
    
    hex_input = page.locator('#global-search-color-hex')
    hex_input.fill("#FF0000")
    expect(hex_input).to_have_value("#FF0000")
    
    page.locator('#global-search-clear-color').click()
    expect(hex_input).to_have_value("")

def test_global_search_type_toggle(page: Page):
    """Verifies that the target type toggle successfully switches between Spool and Filament states."""
    page.goto("http://localhost:8000")
    page.locator('nav button:has-text("SEARCH")').click()
    
    # Wait for the panel to be visible
    expect(page.locator('#offcanvasSearch')).to_be_visible()
    page.wait_for_timeout(500)
    
    spool_radio = page.locator('#searchTypeSpools')
    fil_radio = page.locator('#searchTypeFilaments')
    
    expect(spool_radio).to_be_checked()
    
    # Switch to Filaments (Clicking the label associated with the radio)
    page.locator('label[for="searchTypeFilaments"]').click()
    page.wait_for_timeout(200) # Debounce
    
    expect(fil_radio).to_be_checked()

def test_global_search_material_dropdown(page: Page):
    """Verifies that the material dropdown dynamically populates from /api/materials on open."""
    page.goto("http://localhost:8000")
    page.locator('nav button:has-text("SEARCH")').click()
    
    expect(page.locator('#offcanvasSearch')).to_be_visible()
    
    # Wait for the async fetch to finish. 'Any Mat' is default so we expect >1 option.
    mat_select = page.locator('#global-search-material')
    
    # Wait until there are more than 1 options (meaning the API return has been injected)
    page.wait_for_function('document.querySelectorAll("#global-search-material option").length > 1')
    
    # Check that there are material options now
    count = mat_select.locator('option').count()
    assert count > 1

def test_wizard_advanced_search_integration(page: Page):
    """Verifies that the 'Advanced Search' button in the Wizard opens the Offcanvas globally."""
    page.goto("http://localhost:8000")
    
    # Open Wizard
    page.locator('button:has-text("ADD INVENTORY")').click()
    expect(page.locator('#wizardModal')).to_be_visible()
    
    # Click Existing Filament (default view, but make sure)
    page.locator('#btn-type-existing').click()
    
    # Click the Advanced Search button
    adv_search = page.locator('button:has-text("Advanced Search")')
    expect(adv_search).to_be_visible()
    adv_search.click()
    
    # Verify the Offcanvas slides over
    expect(page.locator('#offcanvasSearch')).to_be_visible()
    
    # Verify it automatically switched to "Filaments" mode
    fil_radio = page.locator('#searchTypeFilaments')
    expect(fil_radio).to_be_checked()


def test_search_offcanvas_does_not_intercept_clicks_after_close(page: Page):
    """Regression: after opening and closing #offcanvasSearch, the hidden offcanvas subtree
    (including #global-search-material) must not grab pointer events on content behind it.
    Bootstrap uses `visibility: hidden` to hide the offcanvas, which does not block pointer
    events by itself. Fix: `.fcc-offcanvas-search:not(.show) { pointer-events: none; }`."""
    page.goto("http://localhost:8000")

    # Open and immediately close the Search offcanvas
    page.locator('nav button:has-text("SEARCH")').click()
    offcanvas = page.locator('#offcanvasSearch')
    expect(offcanvas).to_be_visible()
    page.locator('#offcanvasSearch .btn-close').click()
    page.wait_for_timeout(500)  # wait for slide-out animation
    expect(offcanvas).not_to_be_visible()

    # The closed offcanvas must have pointer-events: none
    pe_off = offcanvas.evaluate("el => window.getComputedStyle(el).pointerEvents")
    assert pe_off == "none", (
        f"#offcanvasSearch should have pointer-events: none when closed, got {pe_off!r}. "
        "Clicks on content behind the offcanvas will be intercepted."
    )

    # The material select inside the hidden offcanvas must not intercept clicks at its own
    # geometric position (the ancestor's pointer-events:none should propagate to descendants).
    mat_select = page.locator('#global-search-material')
    box = mat_select.evaluate("el => { const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }")
    if box["w"] > 0 and box["h"] > 0:
        hit_id = page.evaluate(
            "([x, y]) => { const el = document.elementFromPoint(x, y); return el ? (el.id || el.closest('[id]')?.id || '') : ''; }",
            [box["x"] + box["w"] / 2, box["y"] + box["h"] / 2],
        )
        assert hit_id != "global-search-material", (
            f"Hidden offcanvas's #global-search-material still captures clicks (hit id={hit_id!r})"
        )

    # Reopen — pointer-events must NOT be "none" or the offcanvas is uninteractive
    page.locator('nav button:has-text("SEARCH")').click()
    expect(offcanvas).to_be_visible()
    page.wait_for_timeout(500)  # let Bootstrap's .show class transition settle
    pe_on = offcanvas.evaluate("el => window.getComputedStyle(el).pointerEvents")
    assert pe_on != "none", (
        f"#offcanvasSearch must not have pointer-events: none when open, got {pe_on!r}"
    )
