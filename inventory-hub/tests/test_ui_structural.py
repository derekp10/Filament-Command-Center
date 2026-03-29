import pytest
from playwright.sync_api import Page, expect
import json

# =====================================================================
# GLOBAL DOM LAYOUT SCANNER
# 
# Used as a secondary "catch-all" to find hidden structural issues 
# across all UI elements that explicit Python tests might miss.
# =====================================================================
JS_LAYOUT_SCANNER = """
() => {
    let violations = [];
    const elements = document.querySelectorAll('*');
    
    // Elements we expect to explicitly ignore because they inherently overflow 
    // or are structurally safe to bypass heuristics.
    const ignoreTags = ['HTML', 'BODY', 'SCRIPT', 'STYLE', 'LINK', 'META', 'HEAD', 'TITLE', 'CANVAS', 'SVG', 'PATH', 'OPTION', 'OPTGROUP'];
    const ignoreClasses = ['d-none', 'visually-hidden', 'offcanvas', 'modal'];

    for (let el of elements) {
        if (ignoreTags.includes(el.tagName)) continue;
        
        let shouldIgnore = false;
        for (let cls of ignoreClasses) {
            if (el.classList.contains(cls)) shouldIgnore = true;
        }
        if (shouldIgnore) continue;

        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

        // Check ancestors for display:none
        let isHiddenParent = false;
        let curr = el.parentElement;
        while(curr && curr !== document.body) {
            if (window.getComputedStyle(curr).display === 'none') {
                isHiddenParent = true;
                break;
            }
            curr = curr.parentElement;
        }
        if (isHiddenParent) continue;

        const rect = el.getBoundingClientRect();
        
        // --- 1. SQUISHED OR COLLAPSED CONTENT ---
        // If an element has direct text content but 0 height/width, it's typically a CSS structural failure
        if (el.childNodes.length > 0 && Array.from(el.childNodes).some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0)) {
            if (rect.height < 5 || rect.width < 5) {
                // Ignore small inline elements unless block/flex
                if (style.display !== 'inline') {
                    violations.push({
                        type: 'COLLAPSED_CONTENT',
                        node: `${el.tagName}#${el.id}.${el.className}`,
                        desc: `Element has text but is severely squished (width: ${rect.width}, height: ${rect.height})`
                    });
                }
            }
        }

        // --- 2. OVERFLOW / CUTTING OFF ---
        // If an element's text/children physically exceed its client boundaries and it isn't set to scroll
        const isOverflowingX = el.scrollWidth > el.clientWidth + 2; // small tolerance
        const isOverflowingY = el.scrollHeight > el.clientHeight + 2;
        
        if ((isOverflowingX || isOverflowingY)) {
            if (style.overflowX !== 'scroll' && style.overflowX !== 'auto' && style.overflowY !== 'auto' && style.overflowY !== 'scroll') {
                if (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA') {
                    violations.push({
                        type: 'OVERFLOW_CUTOFF',
                        node: `${el.tagName}#${el.id}.${el.className}`,
                        desc: `Content exceeds boundaries (scroll W/H: ${el.scrollWidth}/${el.scrollHeight} vs client W/H: ${el.clientWidth}/${el.clientHeight}) Overflow style: ${style.overflow}`
                    });
                }
            }
        }
    }
    return violations;
}
"""

def execute_global_scanner(page: Page, context_name: str):
    """Executes the JS layout scanner and asserts no structural violations."""
    violations = page.evaluate(JS_LAYOUT_SCANNER)
    
    if violations:
        filtered_violations = []
        for v in violations:
            if "select2" in v['node'].lower(): continue
            if "navbar" in v['node'].lower() and "COLLAPSED_CONTENT" in v['type']: continue
            if "justify-content-between" in v['node'].lower() and "OVERFLOW" in v['type']: continue
            if "wizard-step" in v['node'].lower() and "OVERFLOW" in v['type']: continue
            filtered_violations.append(v)
            
        if filtered_violations:
            report = json.dumps(filtered_violations, indent=2)
            pytest.fail(f"Global UI Structural Violations Detected in {context_name}:\n{report}")


# =====================================================================
# GLOBAL SWEEP TESTS (Catch-all)
# =====================================================================
def test_structural_global_dashboard(page: Page):
    """Verifies ALL elements on the main dashboard default view using JS Scanner."""
    page.goto("http://localhost:8000")
    page.wait_for_selector('.fcc-spool-card, nav', state='visible')
    page.wait_for_timeout(1000)
    execute_global_scanner(page, "Main Dashboard")


def test_structural_global_modals(page: Page):
    """Verifies ALL elements inside Modals/Overlays using JS Scanner."""
    page.goto("http://localhost:8000")
    
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_timeout(1000)
    page.locator('#global-search-query').fill("a")
    page.wait_for_timeout(1500)
    execute_global_scanner(page, "Global Search Offcanvas")
    
    page.locator('#offcanvasSearch .btn-close').click()
    page.wait_for_timeout(500)
    
    page.get_by_role("button", name="ADD INVENTORY").click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.wait_for_timeout(1000)
    execute_global_scanner(page, "Inventory Wizard Modal")


# =====================================================================
# EXPLICIT COMPONENT TESTS (Specific Element Bounds)
# =====================================================================
def test_structural_navbar(page: Page):
    """Verifies the global Navigation Bar maintains a sensible height and isn't squished."""
    page.goto("http://localhost:8000")
    navbar = page.locator('nav.navbar').first
    expect(navbar).to_be_visible()
    
    box = navbar.bounding_box()
    assert box is not None, "Navbar bounding box not found."
    assert box['height'] >= 45, f"Navbar is vertically squished, height: {box['height']}px (expected >= 45px)"


def test_structural_qr_codes(page: Page):
    """Verifies that generated QR codes maintain exactly the expected rendering dimensions."""
    page.goto("http://localhost:8000")
    qr_audit = page.locator('#qr-audit')
    expect(qr_audit).to_be_visible()
    
    qr_img = qr_audit.locator('img')
    expect(qr_img).to_be_visible()
    
    box = qr_img.bounding_box()
    assert box is not None, "QR img bounding box not found."
    assert 80 <= box['width'] <= 90, f"Audit QR width changed to {box['width']}, expected ~85px"
    assert 80 <= box['height'] <= 90, f"Audit QR height changed to {box['height']}, expected ~85px"


def test_structural_spool_cards(page: Page):
    """Verifies Spool/Filament cards maintain dimension and highly specific gradient CSS structures."""
    page.goto("http://localhost:8000")
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_timeout(500)
    page.locator('#global-search-query').fill("a")
    page.wait_for_timeout(1500)
    
    cards = page.locator('.fcc-spool-card')
    count = cards.count()
    if count == 0:
        pytest.skip("No spool cards rendered.")
    
    for i in range(count):
        card = cards.nth(i)
        
        outer_box = card.bounding_box()
        assert outer_box['width'] > 100, "Spool card squished horizontally (<100px)"
        assert outer_box['height'] > 30, "Spool card squished vertically (<30px)"
        
        inner = card.locator('.fcc-spool-card-inner, .slot-inner-gold').first
        if inner.count() == 0: continue
            
        bg_image = inner.evaluate("el => window.getComputedStyle(el).backgroundImage")
        bg_color = inner.evaluate("el => window.getComputedStyle(el).backgroundColor")
        box_shadow = inner.evaluate("el => window.getComputedStyle(el).boxShadow")

        has_color = ('rgb' in bg_color and bg_color != 'rgba(0, 0, 0, 0)')
        has_gradient = ('gradient' in bg_image)
        
        assert has_color or has_gradient, "Card inner element missing visual background!"
        
        if has_gradient:
            if box_shadow == 'none':
                html = inner.evaluate("el => el.outerHTML")
                pytest.fail(f"Card gradient variant lost its structural inset box-shadow!\nHTML: {html}")


def test_structural_card_action_buttons(page: Page):
    """Verifies the buttons on the spool cards don't suffer from generic text overflow/squishing."""
    page.goto("http://localhost:8000")
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_timeout(500)
    page.locator('#global-search-query').fill("a")
    page.wait_for_timeout(1500)
    
    action_btns = page.locator('.fcc-card-action-btn')
    count = action_btns.count()
    
    for i in range(count):
        btn = action_btns.nth(i)
        is_overflowing = btn.evaluate("el => el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2")
        assert not is_overflowing, "Action button content is overflowing its container!"


def test_structural_search_offcanvas(page: Page):
    """Verifies the Global Search offcanvas structure maintains appropriate overlay width."""
    page.goto("http://localhost:8000")
    
    page.locator('nav button:has-text("SEARCH")').click()
    offcanvas = page.locator('#offcanvasSearch')
    expect(offcanvas).to_be_visible()
    
    box = offcanvas.bounding_box()
    assert box['width'] >= 300, f"Search offcanvas width squished to {box['width']}px"


def test_structural_wizard_modal(page: Page):
    """Verifies the 'Add Inventory' wizard respects minimum standard modal sizing constraints."""
    page.goto("http://localhost:8000")
    
    page.get_by_role("button", name="ADD INVENTORY").click()
    modal_dialog = page.locator('#wizardModal .modal-dialog')
    expect(modal_dialog).to_be_visible()
    
    box = modal_dialog.bounding_box()
    assert box['width'] >= 400, f"Wizard Modal squished horizontally to {box['width']}px"

def test_structural_archived_badges(page: Page):
    """Verifies that all variations of 'Archived' badges across the UI consistently use the hazard red (text-bg-danger) class and reject warning/yellow versions."""
    page.goto("http://localhost:8000")
    
    # Open global search to ensure some spool cards might render (if database populated)
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_timeout(500)
    page.locator('#global-search-query').fill("a")
    page.wait_for_timeout(1500)
    
    # Check all elements with the fcc-archived-badge designation
    badges = page.locator('.fcc-archived-badge')
    count = badges.count()
    if count == 0:
        pytest.skip("No archived badges rendered to verify.")
        
    for i in range(count):
        badge = badges.nth(i)
        classes = badge.evaluate("el => el.className")
        assert "text-bg-danger" in classes, "Archived badge missing text-bg-danger class!"
        assert "bg-warning" not in classes, "Archived badge incorrectly using bg-warning class!"
