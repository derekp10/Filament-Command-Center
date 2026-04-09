import pytest
from playwright.sync_api import Page, expect

def test_loc_grid_layout_data_presence(page: Page):
    """
    E2E structural test verifying that the refactored Slotted Grid layout
    renders the rich data cleanly (Weight, Buttons, Spool Name)
    inside SpoolCardBuilder.
    """
    page.goto("http://localhost:8000")
    
    # Wait for the buffer grid/deck to load (simulate or find a grid item)
    # The application defaults to loc_grid when a slot is provided.
    # We can inject a mock spool into a grid to verify its physical rendering via SpoolCardBuilder natively.
    
    page.evaluate('''() => {
        const mockItem = {
            id: 9999,
            display: "PLA Neon Green",
            details: {
                brand: "Polymaker",
                material: "PLA",
                color_name: "Neon Green",
                weight: 450
            }
        };
        const html = window.SpoolCardBuilder.buildCard(mockItem, 'loc_grid', { slotNum: 1, locId: "Box 1" });
        const div = document.createElement('div');
        div.id = 'test-grid-container';
        div.innerHTML = html;
        document.body.appendChild(div);
    }''')
    
    # Verify the rich data components were built into the grid card!
    card = page.locator('#test-grid-container .slot-btn')
    expect(card).to_be_visible()
    
    # Text checks
    expect(card.locator('.slot-num-gold')).to_contain_text('SLOT 1')
    expect(card).to_contain_text('⚖️ [450g]')
    
    # Metric Check
    expect(card.locator('.text-line-2')).to_contain_text('Polymaker PLA')
    expect(card.locator('.text-line-3')).to_contain_text('Neon Green')
    
    # Action Button Arrays
    btn_container = card.locator('.fcc-card-action-btn')
    expect(btn_container).to_have_count(4) # Pick, Details, Edit, Eject
    
    # Clean up
    page.evaluate('''() => { document.getElementById('test-grid-container').remove(); }''')
