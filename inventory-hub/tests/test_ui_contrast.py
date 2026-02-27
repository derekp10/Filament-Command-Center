import pytest
from playwright.sync_api import Page, expect

def test_global_text_contrast_no_invisible_text(page: Page):
    """
    E2E test verifying that no visible text element has the exact same text color
    as its background color (which would render it invisible).
    """
    page.goto("http://localhost:8000")
    
    # Open Modals to ensure dynamic content is evaluated
    page.get_by_role("button", name="ADD INVENTORY").click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.locator("#btn-type-manual").click()
    page.locator("#btn-type-external").click()
    page.locator("#btn-type-existing").click()
    
    # We will inject a JS script to evaluate every element on the page
    # It checks the computed color vs the effective background color.
    js_checker = """
    () => {
        let violations = [];
        const elements = document.querySelectorAll('*');
        
        // Helper to get effective background color by walking up the DOM
        function getEffectiveBgColor(el) {
            let bg = window.getComputedStyle(el).backgroundColor;
            if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg;
            if (el.parentElement) return getEffectiveBgColor(el.parentElement);
            return 'rgb(255, 255, 255)'; // Default document background
        }

        elements.forEach(el => {
            // Only care about elements with text content that are visible
            if (el.innerText && el.innerText.trim().length > 0 && el.offsetParent !== null) {
                const style = window.getComputedStyle(el);
                
                // If it's technically visible and not opacity 0
                if(style.visibility !== 'hidden' && style.opacity !== '0' && style.display !== 'none') {
                    const textColor = style.color;
                    const bgColor = getEffectiveBgColor(el);
                    
                    // Exclude elements with text-shadow containing a distinct color which forms a readable outline
                    // Or elements that are actively focused/hovered
                    
                    if (textColor === bgColor) {
                        violations.push({
                            tagName: el.tagName,
                            id: el.id,
                            className: el.className,
                            text: el.innerText.substring(0, 20),
                            color: textColor,
                            bg: bgColor
                        });
                    }
                }
            }
        });
        return violations;
    }
    """
    
    violations = page.evaluate(js_checker)
    
    # Filter out empty or irrelevant violations
    ignore_classes = ['']
    
    if violations:
        violation_details = "\\n".join([f"{v['tagName']}#{v['id']}.{v['className']} -> text:'{v['text']}' color:{v['color']}" for v in violations])
        pytest.fail(f"Found {len(violations)} elements with identical text and background colors:\\n{violation_details}")
