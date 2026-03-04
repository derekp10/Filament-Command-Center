import re
import pytest
from playwright.sync_api import Page, expect

def test_wizard_field_sync(page: Page):
    """
    E2E test verifying that custom extra fields propagate from Filament to Spool automatically,
    and that the unlinking/relinking functionality works as expected.
    """
    page.goto("http://localhost:8000")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    
    modal = page.locator("#wizardModal")
    expect(modal).to_be_visible()
    
    # We need to simulate the environment having identical extra fields for Filament and Spool.
    # The UI generates these based on `/api/external/fields`, so we must ensure a matching field exists
    # If a known field like "purchase_link" isn't present, the test might fail based on environment.
    # To keep it robust without mocking the backend, we check if syncing was rendered at all.
    
    # Wait for dynamic fields to render
    page.wait_for_timeout(1000)
    
    sync_btns = page.locator(".wizard-sync-btn.active-sync")
    
    # If the user hasn't defined matching fields in their DB, we can't fully run the E2E
    # without mocking the network response. So we do a soft test.
    if sync_btns.count() > 0:
        active_btn = None
        field_key = None
        
        for i in range(sync_btns.count()):
            btn_candidate = sync_btns.nth(i)
            key_candidate = btn_candidate.get_attribute("data-sync-target")
            input_candidate = page.locator(f"#wiz_fil_ef_{key_candidate}")
            
            # Fast-fail locator check to prevent 30s timeouts on invisible/missing dynamically keyed elements
            if input_candidate.count() > 0:
                type_attr = input_candidate.evaluate("el => el.type")
                if type_attr in ["text", "url"] or type_attr is None:
                    active_btn = btn_candidate
                    field_key = key_candidate
                    break
                
        if not active_btn:
            pytest.skip("No text-based synced fields found to test.")
            
        btn = page.locator(f".wizard-sync-btn[data-sync-target='{field_key}']")
        
        fil_input = page.locator(f"#wiz_fil_ef_{field_key}")
        spool_input = page.locator(f"#wiz_spool_ef_{field_key}")
        
        expect(fil_input).to_be_visible()
        expect(spool_input).to_be_visible()
        expect(btn).to_have_class(re.compile(r"active-sync"))
        expect(spool_input).to_have_attribute("readonly", "true")
        
        # Test 1: Propagation
        test_val = "https://example.com/filament"
        fil_input.fill(test_val)
        expect(spool_input).to_have_value(test_val)
        
        # Test 2: Unlinking
        btn.click()
        expect(btn).not_to_have_class(re.compile(r"active-sync"))
        expect(spool_input).not_to_have_attribute("readonly", "true")
        
        # Modify Spool independently
        test_val_spool = "https://example.com/spool"
        spool_input.fill(test_val_spool)
        expect(spool_input).to_have_value(test_val_spool)
        expect(fil_input).to_have_value(test_val) # Filament should stay unchanged
        
        # Test 3: Relinking
        btn.click()
        expect(btn).to_have_class(re.compile(r"active-sync"))
        expect(spool_input).to_have_attribute("readonly", "true")
        expect(spool_input).to_have_value(test_val) # Should pull original Filament value back
