import re
from playwright.sync_api import Page, expect

def test_clone_spool_button(page: Page):
    """
    E2E test verifying that clicking a Spool from the Backlog opens its details,
    and clicking 'Clone Spool' immediately transports the user to an auto-filled New Inventory Wizard.
    """
    # 1. Hard Navigate / Refresh
    page.goto("http://localhost:8000")

    # 2. Click the 'Backlog' button (by title or text)
    page.get_by_role("button", name=re.compile("Backlog")).click()
    
    # 3. Wait for backlog rows to render
    backlog_list = page.locator("#backlog-list")
    expect(backlog_list).to_be_visible()
    
    # 4. Find the first SPOOL row and click it to open details.
    # The SPOOL text is next to the icon.
    first_spool = page.locator(".backlog-row").filter(has_text="SPOOL").first
    first_spool.click()
    
    # 5. Wait for the Spool Details modal
    spool_modal = page.locator("#spoolModal")
    expect(spool_modal).to_be_visible()
    
    # 6. Click 'Clone Spool'
    spool_modal.get_by_role("button", name=re.compile("Clone Spool")).click()
    
    # 7. Verify Spool modal closes and Wizard opens
    wizard = page.locator("#wizardModal")
    expect(wizard).to_be_visible()
    
    # Verify we auto-transitioned to 'Existing Filament' mode and the success message appears
    status_msg = page.locator("#wiz-status-msg")
    expect(status_msg).to_contain_text("Wizard successfully pre-filled", timeout=5000)
    
    # 8. Close the wizard modal cleanly
    wizard.get_by_text("Cancel", exact=True).click()
    expect(wizard).not_to_be_visible()
