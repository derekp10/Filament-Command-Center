import re
from playwright.sync_api import Page, expect

def test_weigh_out_modal_e2e(page: Page, clean_buffer):
    """
    E2E test verifying that the "Weigh Out" modal opens rapidly handles scanned
    spools, and submits weight successfully.
    """
    # 1. Navigate to the app and wait for scripts to load. The clean_buffer
    # fixture wipes stale spools left by earlier tests so the "1 Spools"
    # is deterministic.
    page.goto("http://localhost:8000")
    
    # 2. Wait for the DOM and initialization
    page.wait_for_selector("#buffer-zone")

    # 3. Simulate adding a spool to the buffer directly (Spool 1 is guaranteed to exist by seed data, or we just mock the fetch)
    # We use the global processScan function exposed by our scripts
    page.evaluate("window.processScan('ID:1', 'keyboard')")
    
    # Wait for the buffer to render
    buffer_card = page.locator(".buffer-item[data-spool-id='1']")
    expect(buffer_card).to_be_visible(timeout=5000)

    # 4. Open the Weigh Out Modal
    # The qr deck button WEIGH OUT
    page.locator("#btn-deck-weigh").click()

    # 5. Wait for the modal to be visible
    modal = page.locator("#weighOutModal")
    expect(modal).to_be_visible()

    # 6. Verify the count badge shows 1
    count_badge = page.locator("#weigh-out-count")
    expect(count_badge).to_contain_text("1 Spools")

    # 7. Locate the input field for Spool 1
    weight_input = page.locator(".weigh-input[data-id='1']")
    expect(weight_input).to_be_visible()
    
    # It should be focused after 500ms
    page.wait_for_timeout(600)
    expect(weight_input).to_be_focused()

    # 8. Enter a new weight and press Enter
    weight_input.fill("850")
    weight_input.press("Enter")

    # 9. Verify the button reaches the saved state (floppy-disk emoji).
    # The UI progression is ⏳ (saving) → 💾 (saved).
    save_btn = page.locator(".weigh-save-btn[data-id='1']")
    expect(save_btn).to_contain_text("💾", timeout=5000)

    # 10. Close the modal cleanly.
    modal.locator(".btn-close").click()
    expect(modal).not_to_be_visible()
    # NOTE: earlier versions of this test also asserted the spool was
    # auto-removed from the buffer after weigh-out save. Current UX keeps
    # the spool in the buffer so the user can continue scanning. If the
    # auto-removal behavior comes back, add a dedicated test for it.
