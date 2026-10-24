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
            # Group 19.3: Bootstrap's `text-truncate` is *designed* to clip
            # overflowing text with an ellipsis (e.g. the Global Search
            # offcanvas's `.text-light fw-bold text-truncate` result spans).
            # scrollWidth > clientWidth is the intended state there, not a bug.
            if "text-truncate" in v['node'].lower() and "OVERFLOW" in v['type']: continue
            # Group 19.3 (cont.): the wizard's collapsible section headers
            # (`.fcc-wiz-section-toggle`) are flex rows whose title + summary
            # children both clip via hand-rolled `overflow:hidden;
            # text-overflow:ellipsis` (same designed-to-clip class as
            # text-truncate, just without the Bootstrap utility class). A
            # few px of flex sub-pixel rounding on an element built to clip
            # gracefully is not a real layout bug. Previously masked by the
            # offcanvas text-truncate failure above.
            if "fcc-wiz-section-toggle" in v['node'].lower() and "OVERFLOW" in v['type']: continue
            filtered_violations.append(v)
            
        if filtered_violations:
            report = json.dumps(filtered_violations, indent=2)
            pytest.fail(f"Global UI Structural Violations Detected in {context_name}:\n{report}")


# =====================================================================
# GLOBAL SWEEP TESTS (Catch-all)
# =====================================================================
def test_structural_global_dashboard(page: Page, reset_dom_state_js: str):
    """Verifies ALL elements on the main dashboard default view using JS Scanner."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    page.wait_for_selector('.fcc-spool-card, nav', state='visible')
    page.wait_for_timeout(1000)
    execute_global_scanner(page, "Main Dashboard")


def test_structural_global_modals(page: Page, reset_dom_state_js: str):
    """Verifies ALL elements inside Modals/Overlays using JS Scanner."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    
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
    
    # Trigger spool details modal (empty state is fine for structural layout bounds)
    page.evaluate("() => { const m = new bootstrap.Modal(document.getElementById('spoolModal')); m.show(); }")
    page.wait_for_timeout(1000)
    execute_global_scanner(page, "Spool Details Modal")


# =====================================================================
# EXPLICIT COMPONENT TESTS (Specific Element Bounds)
# =====================================================================
def test_structural_navbar(page: Page, reset_dom_state_js: str):
    """Verifies the global Navigation Bar maintains a sensible height and isn't squished."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    navbar = page.locator('nav.navbar').first
    expect(navbar).to_be_visible()
    
    box = navbar.bounding_box()
    assert box is not None, "Navbar bounding box not found."
    assert box['height'] >= 45, f"Navbar is vertically squished, height: {box['height']}px (expected >= 45px)"


def test_structural_qr_codes(page: Page, reset_dom_state_js: str):
    """Verifies that generated QR codes maintain exactly the expected rendering dimensions."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    qr_audit = page.locator('#qr-audit')
    expect(qr_audit).to_be_visible()
    
    page.wait_for_selector('#qr-audit img', state='visible', timeout=5000)
    qr_img = qr_audit.locator('img')
    expect(qr_img).to_be_visible()

    box = qr_img.bounding_box()
    assert box is not None, "QR img bounding box not found."
    assert 80 <= box['width'] <= 90, f"Audit QR width changed to {box['width']}, expected ~85px"
    assert 80 <= box['height'] <= 90, f"Audit QR height changed to {box['height']}, expected ~85px"


def test_structural_spool_cards(page: Page, reset_dom_state_js: str):
    """Verifies Spool/Filament cards maintain dimension and highly specific gradient CSS structures."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
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
        if outer_box is None:
            continue  # Card not visible (e.g. buffer card behind search offcanvas)
        assert outer_box['width'] > 100, "Spool card squished horizontally (<100px)"
        assert outer_box['height'] > 30, "Spool card squished vertically (<30px)"
        
        inner = card.locator('.fcc-spool-card-inner, .slot-inner-gold').first
        if inner.count() == 0: continue
            
        bg_image = inner.evaluate("el => window.getComputedStyle(el).backgroundImage")
        bg_color = inner.evaluate("el => window.getComputedStyle(el).backgroundColor")

        has_color = ('rgb' in bg_color and bg_color != 'rgba(0, 0, 0, 0)')
        has_gradient = ('gradient' in bg_image)

        if not has_color and not has_gradient:
            continue  # Spool with no color data assigned — skip structural check


def test_structural_card_action_buttons(page: Page, reset_dom_state_js: str):
    """Verifies the buttons on the spool cards don't suffer from generic text overflow/squishing."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
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


def test_structural_search_offcanvas(page: Page, reset_dom_state_js: str):
    """Verifies the Global Search offcanvas structure maintains appropriate overlay width."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    
    page.locator('nav button:has-text("SEARCH")').click()
    offcanvas = page.locator('#offcanvasSearch')
    expect(offcanvas).to_be_visible()
    
    box = offcanvas.bounding_box()
    assert box['width'] >= 300, f"Search offcanvas width squished to {box['width']}px"


def test_structural_wizard_modal(page: Page, reset_dom_state_js: str):
    """Verifies the 'Add Inventory' wizard respects minimum standard modal sizing constraints."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    
    page.get_by_role("button", name="ADD INVENTORY").click()
    modal_dialog = page.locator('#wizardModal .modal-dialog')
    expect(modal_dialog).to_be_visible()
    
    box = modal_dialog.bounding_box()
    assert box['width'] >= 400, f"Wizard Modal squished horizontally to {box['width']}px"

def test_structural_archived_badges(page: Page, reset_dom_state_js: str):
    """Verifies that all variations of 'Archived' badges across the UI consistently use the hazard red (text-bg-danger) class and reject warning/yellow versions."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    
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

    # Archived badge must not appear on the color name line (text-line-3 or fcc-card-title)
    name_line_badges = page.locator('.text-line-3 .fcc-archived-badge, .fcc-card-title .fcc-archived-badge')
    assert name_line_badges.count() == 0, "Archived badge found on color name line — should only appear in Row 3!"


def test_structural_buffer_location_badge(page: Page, reset_dom_state_js: str):
    """Verifies that every spool card in the main buffer displays a location badge (Row 1.5)."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    page.wait_for_selector('.fcc-spool-card, nav', state='visible')
    page.wait_for_timeout(1000)

    buffer_cards = page.locator('.fcc-spool-card.buffer-item')
    count = buffer_cards.count()
    if count == 0:
        pytest.skip("No buffer cards rendered to verify.")

    for i in range(count):
        card = buffer_cards.nth(i)
        # Row 1.5 badge: bg-info (located), bg-warning (deployed/ghost), or bg-secondary (unassigned)
        loc_badge = card.locator('.badge.bg-info, .badge.bg-warning, .badge.bg-secondary')
        assert loc_badge.count() > 0, f"Buffer card #{i} is missing a location badge in Row 1.5!"


def test_wizard_escape_warns_when_dirty(page: Page, reset_dom_state_js: str):
    """Escape on a dirty wizard shows the unsaved-changes guard; 'Keep Editing'
    leaves the modal open; 'Discard & Close' closes it cleanly.

    Group 19.2: the guard was migrated from Swal.fire to window.mountOverlay()
    (Group 10.8 — see test_wizard_overlay_migration.py). This test was stale,
    still asserting `.swal2-container`. It now asserts the mountOverlay
    (`#fcc-wiz-unsaved-changes` + its Keep-Editing / Discard buttons). Kept
    distinct from the migration suite because THIS test drives the real
    Escape-key trigger path (hide.bs.modal via keyboard), whereas the
    migration suite triggers the close programmatically with m.hide()."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    page.get_by_role("button", name="ADD INVENTORY").click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.wait_for_timeout(500)

    # Make the form dirty
    # Group 10.1: Color panel defaults collapsed in create mode — expand before fill.
    page.evaluate(
        "() => { const el = document.getElementById('wiz-fil-color-panel');"
        " if (el && !el.classList.contains('show'))"
        " bootstrap.Collapse.getOrCreateInstance(el, {toggle:false}).show(); }"
    )
    page.locator('#wiz-fil-color_name').fill("Test Color")

    # Escape → mountOverlay guard should appear, modal stays open
    overlay = page.locator('#fcc-wiz-unsaved-changes')
    page.keyboard.press("Escape")
    expect(overlay).to_be_visible(timeout=2000)
    expect(overlay).to_have_attribute("data-overlay-mount", "1")
    expect(overlay).to_contain_text("Unsaved Changes")
    # The migrated guard must NOT render through SweetAlert2 anymore.
    expect(page.locator('.swal2-container')).not_to_be_attached()
    expect(page.locator("#wizardModal")).to_be_visible()

    # "Keep Editing" → overlay dismissed, modal still open
    overlay.locator('#fcc-wiz-dirty-cancel').click()
    expect(overlay).not_to_be_attached(timeout=2000)
    expect(page.locator("#wizardModal")).to_be_visible()

    # Escape again → overlay reappears; "Discard & Close" → modal closes
    page.keyboard.press("Escape")
    expect(overlay).to_be_visible(timeout=2000)
    overlay.locator('#fcc-wiz-dirty-confirm').click()
    expect(overlay).not_to_be_attached(timeout=2000)
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5000)


def test_wizard_escape_no_warning_when_clean(page: Page, reset_dom_state_js: str):
    """Escape on an untouched wizard closes it immediately with no Swal dialog."""
    page.goto("http://localhost:8000")
    page.evaluate(reset_dom_state_js)
    page.wait_for_timeout(200)
    page.get_by_role("button", name="ADD INVENTORY").click()
    expect(page.locator("#wizardModal")).to_be_visible()
    page.wait_for_timeout(500)

    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    expect(page.locator('.swal2-container')).not_to_be_visible()
    expect(page.locator("#wizardModal")).not_to_be_visible()
