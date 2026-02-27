import re
from playwright.sync_api import Page, expect

def test_wizard_manual_creation(page: Page):
    """
    E2E test verifying that the "Add Inventory" wizard opens, accepts inputs
    for a new manual filament and spool, and successfully submits the payload.
    """
    # 1. Navigate to the app
    page.goto("http://localhost:8000")

    # 2. Click the 'ADD INVENTORY' button via its text
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()

    # 3. Wait for the wizard modal to be clearly visible
    modal = page.locator("#wizardModal")
    expect(modal).to_be_visible()

    # 4. We expect the 'Manual' tab to be active by default, but let's click it to be safe.
    page.locator("#btn-type-manual").click()

    # 5. Fill out Filament details (Step 2)
    page.fill("#wiz-fil-material", "Pytest-PLA")
    page.fill("#wiz-fil-color_name", "E2E Ruby Red")
    
    # Locate the first wizard color hex input
    page.locator("#wiz-fil-color_hex_0").fill("#FF0044")
    
    page.fill("#wiz-fil-density", "1.24")
    page.fill("#wiz-fil-diameter", "1.75")
    
    # We use nth(0) because the DOM currently has duplicate #wiz-fil-weight IDs
    weight_inputs = page.locator("#wiz-fil-weight")
    weight_inputs.nth(0).fill("1000")
    
    # Fill empty spool weight
    page.fill("#wiz-fil-empty_weight", "250")

    # 6. Fill out Spool details (Step 3)
    # 7. Submit the form
    submit_btn = page.locator("#btn-wiz-submit")
    expect(submit_btn).not_to_be_disabled()
    submit_btn.click()

    # 8. Assert Success
    # The wizard-status-msg updates dynamically
    status_msg = page.locator("#wiz-status-msg")
    expect(status_msg).to_contain_text("Success!", timeout=5000)

    # 9. Ensure the modal can close
    modal.get_by_text("Cancel", exact=True).click()
    expect(modal).not_to_be_visible()
