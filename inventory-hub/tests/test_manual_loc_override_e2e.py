import pytest
from playwright.sync_api import Page, expect


# Rewritten for the post-refactor Force Location Override modal:
#   - Old: a <select> (#swal-override-loc) chose the location.
#   - New: #swal-override-loc is now a hidden input holding the selected id,
#          and the visible UI is a search box (#swal-override-search) plus
#          a scrollable list of .swal-loc-item divs (data-id="<locId>").
# Matches the setup/pattern used by test_force_location_keyboard_e2e so the
# search-offcanvas interception issue that sank the legacy version is avoided
# — we never close the offcanvas; we just click the card directly.
@pytest.fixture
def force_location_modal(page: Page):
    """Open the Force Location Override SweetAlert modal on a spool."""
    page.goto("http://localhost:8000")

    page.locator('nav button:has-text("SEARCH")').click()
    page.locator('#global-search-query').fill("a")
    page.locator('label[for="searchTypeSpools"]').click()
    page.wait_for_timeout(1000)

    cards = page.locator('.fcc-spool-card')
    if cards.count() == 0:
        pytest.skip("No spool cards rendered in test environment.")

    cards.first.locator('div[title="View Details"]').click()

    expect(page.locator('#spoolModal')).to_be_visible()
    edit_btn = page.locator('#spoolModal button[title="Force/Override Location"]')
    expect(edit_btn).to_be_visible()
    edit_btn.click()

    expect(page.locator('.swal2-popup')).to_be_visible()
    expect(page.locator('text="Force Location Override"')).to_be_visible()

    return page


def test_manual_location_override_click_unassigned_posts_force_unassign(force_location_modal):
    """Clicking the "-- Unassigned --" list item and pressing Force Move should
    POST /api/manage_contents with action='force_unassign' and origin='manual_override'."""
    page = force_location_modal

    # The hidden input and search should exist.
    expect(page.locator('#swal-override-search')).to_be_visible()
    expect(page.locator('#swal-override-loc')).to_have_count(1)

    # "-- Unassigned --" is always seeded at the top of the list with data-id="".
    unassigned_item = page.locator('.swal-loc-item[data-id=""]')
    expect(unassigned_item).to_have_count(1)

    with page.expect_request(
        lambda request: "/api/manage_contents" in request.url and request.method == "POST"
    ) as intercepted_req:
        unassigned_item.click()
        # Sanity check: click handler wrote "" into the hidden input.
        assert page.locator('#swal-override-loc').input_value() == ""
        page.locator('button.swal2-confirm').click()

    req = intercepted_req.value
    post_data = req.post_data_json
    assert post_data['action'] == 'force_unassign'
    assert post_data['location'] == ''
    assert post_data['origin'] == 'manual_override'
    assert 'spool_id' in post_data


def test_manual_location_override_keyboard_select_submits(force_location_modal):
    """Keyboard path: filter to 'Unassigned', ArrowDown to highlight it, Enter
    to commit the selection, then click Force Move. Verifies the new
    search+list modal's keyboard contract matches the submit path."""
    page = force_location_modal

    page.locator('#swal-override-search').fill('Unassigned')
    page.wait_for_timeout(150)

    page.locator('#swal-override-search').press('ArrowDown')
    page.locator('#swal-override-search').press('Enter')

    assert page.locator('#swal-override-loc').input_value() == ""

    with page.expect_request(
        lambda request: "/api/manage_contents" in request.url and request.method == "POST"
    ) as intercepted_req:
        page.locator('button.swal2-confirm').click()

    post_data = intercepted_req.value.post_data_json
    assert post_data['action'] == 'force_unassign'
    assert post_data['location'] == ''
    assert post_data['origin'] == 'manual_override'
