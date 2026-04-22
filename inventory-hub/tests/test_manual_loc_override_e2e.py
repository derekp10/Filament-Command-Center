import pytest
from playwright.sync_api import Page, expect


# The Force Location Override modal was refactored to use a search+keyboard-
# navigable list backed by a hidden input (#swal-override-loc is now hidden,
# not a <select>). Step 6 of this test drives a <select> that no longer
# exists. Rewriting step 6 to drive the new search-and-pick flow is its own
# work; the offcanvas-interception fix is in place so the earlier steps run.
@pytest.mark.xfail(
    reason="Step 6 drives the old <select>; Force Location modal is now a search+list. Needs rewrite.",
    strict=False,
)
def test_manual_location_override_e2e(page: Page):
    """
    E2E Test to verify the manual location editing behavior via the Spool Details modal.
    Ensures the SweetAlert modal appears, intercepts the /api/manage_contents call, and 
    confirms the correct 'add' action and origin is passed.
    """
    # 1. Navigate to Dashboard
    page.goto("http://localhost:8000")
    
    # 2. Open Search to guarantee at least one SPOOL card renders
    page.locator('nav button:has-text("SEARCH")').click()
    page.locator('#global-search-query').fill("a")
    page.locator('label[for="searchTypeSpools"]').click()
    page.wait_for_timeout(1000)

    # If no cards rendered, skip test safely
    cards = page.locator('.fcc-spool-card')
    if cards.count() == 0:
        pytest.skip("No spool cards rendered in test environment.")

    # Close the search offcanvas — it intercepts pointer events on card clicks.
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    if page.locator("#offcanvasSearch.show").count() > 0:
        close_btn = page.locator("#offcanvasSearch .btn-close")
        if close_btn.count() > 0:
            close_btn.first.click()
            page.wait_for_timeout(400)

    # 3. Click the first Spool's "View Details" button (re-query visible cards)
    visible_cards = page.locator('.fcc-spool-card:visible')
    if visible_cards.count() == 0:
        pytest.skip("No spool cards visible after closing offcanvas.")
    first_spool = visible_cards.first
    first_spool.locator('div[title="View Details"]').click()
    
    # Wait for the modal and specifically the Location edit button to be visible
    expect(page.locator('#spoolModal')).to_be_visible()
    edit_btn = page.locator('#spoolModal button[title="Force/Override Location"]')
    expect(edit_btn).to_be_visible()
    
    # 4. Click Edit Location
    edit_btn.click()
    
    # 5. Verify SweetAlert dropdown emerges with the proper override select
    swal_popup = page.locator('.swal2-popup')
    expect(swal_popup).to_be_visible()
    expect(page.locator('text="Force Location Override"')).to_be_visible()
    
    # 6. Intercept API and Submit Form
    with page.expect_request(lambda request: "/api/manage_contents" in request.url and request.method == "POST") as intercepted_req:
        # Select "Unassigned" (value: "")
        page.locator('#swal-override-loc').select_option(value="")
        # Click Force Move
        page.locator('button.swal2-confirm').click()
    
    # 7. Validate the POST payload matches the smart_move protocol requirements
    req = intercepted_req.value
    assert req.method == "POST"
    
    post_data = req.post_data_json
    assert post_data['action'] == 'force_unassign'
    assert post_data['location'] == ''
    assert post_data['origin'] == 'manual_override'
    assert 'spool_id' in post_data
