"""Regression guard for the search FAB — buglist L36 / Group 21.1.

The floating 🔍 search button (#fcc-fab-search) is the primary search affordance
and must stay ALWAYS available, including over modals. It must NOT, at its
default position, cover live data — the WEIGH QR on the cmd-deck (the original
L36 victim) or the buffer-card weight readouts (the 21.1 victim).

21.1 made the FAB drag-to-park (fab_drag.js) with its position persisted to
localStorage and a data-free default (bottom-left, inside the cmd-deck band).
These tests assert: it's VISIBLE (never hidden — an earlier attempt hid it,
which was rejected); its default box clears the WEIGH QR and buffer weights; a
tap opens search; a drag moves + persists it (and does NOT open search); a
saved position is restored + clamped on-screen; it stays clickable over an open
modal; and the new '/' + Ctrl/Cmd+K shortcuts open search.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _rects_overlap(a: dict, b: dict) -> bool:
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


def _goto_dashboard(page: Page, viewport=None):
    if viewport:
        page.set_viewport_size(viewport)
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function("typeof window.SearchEngine === 'object'")
    page.wait_for_selector("#fcc-fab-search", state="attached", timeout=10000)


def _fab_center(page: Page):
    box = page.locator("#fcc-fab-search").bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


# --- default placement clears all live data --------------------------------

def _check_default_clears_data(page: Page, viewport: dict):
    # Fresh default position (no saved override).
    page.add_init_script("try { localStorage.removeItem('fcc.fab.pos'); } catch(e){}")
    _goto_dashboard(page, viewport)
    # Seed a full buffer + scroll to the bottom so the WORST-case bottom card
    # weight is rendered (the 21.1 collision was with the bottom card).
    page.evaluate(
        """() => {
            state.heldSpools = [298,297,255,254,253,252,251].map(id => ({id, display:'#'+id, color:'888888'}));
            renderBuffer();
            const bc = document.querySelector('.buffer-content'); if (bc) bc.scrollTop = bc.scrollHeight;
        }"""
    )
    page.wait_for_timeout(400)
    fab = page.locator("#fcc-fab-search")
    expect(fab).to_be_visible()
    fab_box = fab.bounding_box()

    weigh_box = page.locator("#qr-weigh").bounding_box()
    assert weigh_box and not _rects_overlap(fab_box, weigh_box), (
        f"default FAB {fab_box} overlaps the WEIGH QR {weigh_box} (L36) at {viewport}"
    )
    weights = page.locator("#buffer-zone .fcc-card-metric")
    for i in range(weights.count()):
        wb = weights.nth(i).bounding_box()
        if wb:
            assert not _rects_overlap(fab_box, wb), (
                f"default FAB {fab_box} overlaps a buffer weight {wb} (21.1) at {viewport}"
            )
    # navbar search button still present.
    expect(page.get_by_role("button", name="🔍 SEARCH")).to_be_visible()


def test_fab_default_clears_data_at_default_viewport(page: Page):
    _check_default_clears_data(page, {"width": 1600, "height": 1300})


def test_fab_default_clears_data_at_short_viewport(page: Page):
    _check_default_clears_data(page, {"width": 1280, "height": 700})


# --- tap vs drag ------------------------------------------------------------

def test_fab_tap_opens_search(page: Page):
    _goto_dashboard(page)
    cx, cy = _fab_center(page)
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.up()  # no movement → a clean tap
    page.wait_for_selector("#offcanvasSearch.show", timeout=4000)


def test_fab_drag_moves_and_persists_without_opening(page: Page):
    page.add_init_script("try { localStorage.removeItem('fcc.fab.pos'); } catch(e){}")
    _goto_dashboard(page)
    before = page.locator("#fcc-fab-search").bounding_box()
    cx, cy = _fab_center(page)
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 100, cy - 100, steps=8)  # >6px → drag
    page.mouse.up()
    page.wait_for_timeout(300)
    after = page.locator("#fcc-fab-search").bounding_box()
    assert (abs(after["x"] - before["x"]) > 20 or abs(after["y"] - before["y"]) > 20), (
        f"FAB should have moved on drag: before={before} after={after}"
    )
    saved = page.evaluate("() => localStorage.getItem('fcc.fab.pos')")
    assert saved, "drag should persist the position to localStorage 'fcc.fab.pos'"
    # A drag must NOT have opened search.
    assert page.locator("#offcanvasSearch.show").count() == 0, "drag must not open search"


def test_fab_position_restored_and_clamped(page: Page):
    # Saved position well inside a 1600x1300 viewport.
    page.add_init_script("localStorage.setItem('fcc.fab.pos', JSON.stringify({left:500, bottom:400}));")
    _goto_dashboard(page, {"width": 1600, "height": 1300})
    box = page.locator("#fcc-fab-search").bounding_box()
    # left:500 → x≈500; bottom:400 → y = 1300-400-65 = 835.
    assert abs(box["x"] - 500) < 4, f"restored left should be ~500: {box}"
    assert abs(box["y"] - 835) < 6, f"restored bottom:400 → y~835: {box}"
    # Shrinking the viewport must clamp it back on-screen.
    page.set_viewport_size({"width": 700, "height": 500})
    page.wait_for_timeout(200)
    box2 = page.locator("#fcc-fab-search").bounding_box()
    assert box2["x"] + box2["width"] <= 700 and box2["y"] + box2["height"] <= 500, (
        f"FAB must stay within the shrunk viewport: {box2}"
    )
    assert box2["x"] >= 0 and box2["y"] >= 0, f"FAB must not go off the top/left: {box2}"


# --- always available -------------------------------------------------------

def test_fab_clickable_over_open_modal(page: Page):
    _goto_dashboard(page)
    page.evaluate(
        """() => {
            document.getElementById('detail-id').innerText = '255';
            document.getElementById('detail-color-name').innerText = 'Test';
            if (modals && modals.spoolModal) modals.spoolModal.show();
        }"""
    )
    page.wait_for_selector("#spoolModal.show", timeout=4000)
    fab = page.locator("#fcc-fab-search")
    expect(fab).to_be_visible()
    cx, cy = _fab_center(page)
    top = page.evaluate(
        "([x,y]) => { const el = document.elementFromPoint(x,y); return el ? (el.id || el.className) : null; }",
        [cx, cy],
    )
    assert top and "fcc-fab-search" in str(top), (
        f"FAB must be the top (clickable) element over an open modal, got {top!r}"
    )


def test_search_keyboard_shortcuts_open_search(page: Page):
    _goto_dashboard(page)
    # '/' on the bare dashboard opens search.
    page.keyboard.press("/")
    page.wait_for_selector("#offcanvasSearch.show", timeout=4000)
    # Close, then Ctrl+K reopens.
    page.evaluate("() => { if (window.SearchEngine && SearchEngine.offcanvas) SearchEngine.offcanvas.hide(); }")
    page.wait_for_function("() => !document.getElementById('offcanvasSearch').classList.contains('show')", timeout=4000)
    page.keyboard.press("Control+k")
    page.wait_for_selector("#offcanvasSearch.show", timeout=4000)


def test_slash_does_not_open_search_while_typing(page: Page):
    _goto_dashboard(page)
    # Focus a real input, type '/', it must NOT open search.
    page.evaluate(
        """() => {
            const inp = document.createElement('input');
            inp.id = '__test_input'; document.body.appendChild(inp); inp.focus();
        }"""
    )
    page.focus("#__test_input")
    page.keyboard.press("/")
    page.wait_for_timeout(300)
    assert page.locator("#offcanvasSearch.show").count() == 0, "'/' inside an input must not open search"
