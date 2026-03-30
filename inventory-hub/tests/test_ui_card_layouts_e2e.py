import pytest
from playwright.sync_api import Page, expect

def test_fancy_button_layout_applied(page: Page):
    """
    E2E structural test verifying that all filament cards (black, solid, and multi-color)
    utilize the "fancy button" visual layout framework.
    Specifically checks:
    1. Inner .cham-body has an opaque dark core termination mapping to the dark base matrix.
    2. Inner .cham-body does NOT have the glaring glossy inset ring or top border artifacts.
    """
    page.goto("http://localhost:8000")
    
    # Wait for the buffer grid/deck to load the dynamically styled spool elements
    page.wait_for_selector(".buffer-item", timeout=10000)
    
    # Evaluate styles directly in the browser context to inspect exactly what the styling engine outputs
    result = page.evaluate('''() => {
        const cards = document.querySelectorAll(".buffer-item");
        if (cards.length === 0) return { error: "No cards found to test" };
        
        for (let i = 0; i < cards.length; i++) {
            const card = cards[i];
            const body = card.querySelector(".fcc-spool-card-inner");
            if (!body) {
                // Buffer padding objects and empty slots don't contain filament layout components
                if (card.innerText.includes("Empty") || card.className.includes("empty")) continue;
                return { error: `Missing inner core inside populated card ${card.dataset.spoolId}` };
            }
            
            // Check that glossy inner border is structurally removed
            const bodyStyle = window.getComputedStyle(body);
            if (bodyStyle.borderTopWidth !== "0px" && bodyStyle.borderTopStyle !== "none") {
                return { error: `Card ${card.dataset.spoolId} has an unwanted top border: ` + bodyStyle.borderTop };
            }
            
            if (bodyStyle.boxShadow && bodyStyle.boxShadow !== "none" && bodyStyle.boxShadow.includes("inset")) {
                return { error: `Card ${card.dataset.spoolId} has an unwanted glossy inset box-shadow: ` + bodyStyle.boxShadow };
            }
            
            // Check that the inner background utilizes the 10% dark alpha layer to correctly flood the inner card with the beautiful frame background
            if (!body.style.background.includes('rgba(5, 5, 5, 0.1)')) {
                return { error: `Card ${card.dataset.spoolId} inner background does not utilize the dynamic transparency bleed. Found: ${body.style.background}` };
            }
        }
        
        return { success: true, count: cards.length };
    }''')
    
    assert "error" not in result, f"Layout regression detected: {result.get('error')}"
    assert result.get("success") is True, "Failed to comprehensively validate the unified fancy button layout."
    assert result.get("count", 0) > 0, "No operational cards were evaluated on screen."
