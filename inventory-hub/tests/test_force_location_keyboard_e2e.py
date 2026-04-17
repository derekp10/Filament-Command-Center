import re
import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def force_location_modal(page: Page):
    """Open the Force Location Override SweetAlert modal on a spool and return the page."""
    # Navigate to Dashboard
    page.goto("http://localhost:8000")

    # Open Search to guarantee at least one spool card renders
    page.locator('nav button:has-text("SEARCH")').click()
    page.locator('#global-search-query').fill("a")
    page.locator('label[for="searchTypeSpools"]').click()
    page.wait_for_timeout(1000)

    cards = page.locator('.fcc-spool-card')
    if cards.count() == 0:
        pytest.skip("No spool cards rendered in test environment.")

    # Click the first spool's View Details button
    first_spool = cards.first
    first_spool.locator('div[title="View Details"]').click()

    # Wait for details modal and click location edit
    expect(page.locator('#spoolModal')).to_be_visible()
    edit_btn = page.locator('#spoolModal button[title="Force/Override Location"]')
    expect(edit_btn).to_be_visible()
    edit_btn.click()

    # Wait for the SweetAlert popup
    swal_popup = page.locator('.swal2-popup')
    expect(swal_popup).to_be_visible()
    expect(page.locator('text="Force Location Override"')).to_be_visible()

    return page


def test_force_location_autofocus(force_location_modal):
    """Search input should be focused automatically when the modal opens."""
    page = force_location_modal
    search_input = page.locator('#swal-override-search')
    expect(search_input).to_be_focused()


def test_force_location_arrow_navigation(force_location_modal):
    """Arrow keys should navigate through visible location items."""
    page = force_location_modal
    search_input = page.locator('#swal-override-search')
    items = page.locator('.swal-loc-item')

    # Need at least 2 items to test navigation
    if items.count() < 2:
        pytest.skip("Need at least 2 location items to test arrow navigation.")

    # Press ArrowDown once — first item should be kb-active
    search_input.press('ArrowDown')
    expect(items.nth(0)).to_have_class(re.compile(r'kb-active'))

    # Press ArrowDown again — second item should be kb-active, first should not
    search_input.press('ArrowDown')
    expect(items.nth(1)).to_have_class(re.compile(r'kb-active'))
    expect(items.nth(0)).not_to_have_class(re.compile(r'kb-active'))

    # Press ArrowUp — back to first item
    search_input.press('ArrowUp')
    expect(items.nth(0)).to_have_class(re.compile(r'kb-active'))

    # Test wrap-around: press ArrowUp from first item should go to last
    search_input.press('ArrowUp')
    last_index = items.count() - 1
    expect(items.nth(last_index)).to_have_class(re.compile(r'kb-active'))


def test_force_location_enter_selects(force_location_modal):
    """Enter should select the keyboard-highlighted item without closing the modal."""
    page = force_location_modal
    search_input = page.locator('#swal-override-search')
    items = page.locator('.swal-loc-item')
    hidden_input = page.locator('#swal-override-loc')

    if items.count() < 2:
        pytest.skip("Need at least 2 location items to test Enter selection.")

    # Navigate to second item and press Enter
    search_input.press('ArrowDown')
    search_input.press('ArrowDown')
    target_id = items.nth(1).get_attribute('data-id')
    search_input.press('Enter')

    # Hidden input should have the selected item's data-id
    expect(hidden_input).to_have_value(target_id)

    # The item should show selected background (#444 = rgb(68, 68, 68))
    expect(items.nth(1)).to_have_css('background', re.compile(r'rgb\(68,\s*68,\s*68\)'))

    # kb-active class should be cleared after Enter
    expect(items.nth(1)).not_to_have_class(re.compile(r'kb-active'))

    # Modal should still be open
    expect(page.locator('.swal2-popup')).to_be_visible()


def test_force_location_filter_resets_keyboard(force_location_modal):
    """Typing in the search input should reset the keyboard highlight."""
    page = force_location_modal
    search_input = page.locator('#swal-override-search')
    items = page.locator('.swal-loc-item')

    if items.count() < 1:
        pytest.skip("Need at least 1 location item.")

    # Navigate down to highlight an item
    search_input.press('ArrowDown')
    expect(items.nth(0)).to_have_class(re.compile(r'kb-active'))

    # Type something to filter — kb-active should be cleared
    search_input.fill("test")
    kb_active_items = page.locator('.swal-loc-item.kb-active')
    expect(kb_active_items).to_have_count(0)


def test_force_location_mouse_clears_keyboard(force_location_modal):
    """Hovering with the mouse should clear the keyboard highlight."""
    page = force_location_modal
    search_input = page.locator('#swal-override-search')
    items = page.locator('.swal-loc-item')

    if items.count() < 2:
        pytest.skip("Need at least 2 location items.")

    # Navigate to first item via keyboard
    search_input.press('ArrowDown')
    expect(items.nth(0)).to_have_class(re.compile(r'kb-active'))

    # Hover over a different item with mouse
    items.nth(1).hover()

    # kb-active should be cleared from all items
    kb_active_items = page.locator('.swal-loc-item.kb-active')
    expect(kb_active_items).to_have_count(0)


def test_force_location_escape_confirmation(force_location_modal):
    """Escape should show an inline confirmation overlay; 'No' keeps the modal open."""
    page = force_location_modal
    search_input = page.locator('#swal-override-search')
    overlay = page.locator('#fcc-escape-confirm-overlay')

    # Overlay should be hidden initially
    expect(overlay).not_to_be_visible()

    # Press Escape — should show the inline confirmation overlay
    search_input.press('Escape')
    page.wait_for_timeout(200)
    expect(overlay).to_be_visible()

    # Click "No, go back" — overlay should hide, modal stays open
    page.locator('#fcc-escape-no').click()
    page.wait_for_timeout(200)
    expect(overlay).not_to_be_visible()
    expect(page.locator('text="Force Location Override"')).to_be_visible()

    # Press Escape again and confirm with "Yes, close"
    search_input.press('Escape')
    page.wait_for_timeout(200)
    expect(overlay).to_be_visible()
    page.locator('#fcc-escape-yes').click()
    page.wait_for_timeout(200)

    # The entire modal should now be closed
    expect(page.locator('.swal2-popup')).not_to_be_visible()


def test_force_location_escape_toggles_overlay(force_location_modal):
    """Pressing Escape while confirmation is showing should dismiss it (go back)."""
    page = force_location_modal
    search_input = page.locator('#swal-override-search')
    overlay = page.locator('#fcc-escape-confirm-overlay')

    # Open confirmation overlay
    search_input.press('Escape')
    page.wait_for_timeout(200)
    expect(overlay).to_be_visible()

    # Press Escape again — should dismiss the overlay, not close the modal
    page.press('#fcc-escape-no', 'Escape')
    page.wait_for_timeout(200)
    expect(overlay).not_to_be_visible()
    expect(page.locator('text="Force Location Override"')).to_be_visible()
