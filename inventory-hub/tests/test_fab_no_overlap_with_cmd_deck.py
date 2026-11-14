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

Group 45.10: nothing here writes to dev. Every test owns the page's buffer
(conftest.own_the_buffer, an empty start, before page.goto), so neither the
seven spools the two default-placement tests put in the buffer nor a stale
buffer dev's server holds is saved to dev's shared one (renderBuffer's save, the
grace path's, and the save after a refresh repaints a card all POST the page's
buffer). A write tripwire (`dev_writes`, autouse) answers every request the page
sends to /api/** that isn't a GET in the page and records it, except the
heartbeat and the spool refresh, which only read (test_text_size_guard.READ_POSTS).
It closes the page before the routes come off (a live page's 2 s buffer poll,
un-routed, could still save to dev), then fails the test that wrote. The seven
ids are made up and the two placement tests quiet the heartbeat and answer the
spool refresh with nothing new, so no record of dev's repaints their cards.

Proving the tripwire: a copy of this module with the tripwire and without
own_the_buffer must fail the two default-placement tests, naming
POST /api/state/buffer, and leave dev's buffer reading the same before and
after (the tripwire answers those saves in the page).
"""
from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

from conftest import own_the_buffer, quiet_heartbeat
from test_text_size_guard import READ_POSTS

# Made-up spool ids for the seven buffer cards (dev's own ids name copies of
# Derek's real spools since its 2026-11-13 refresh from prod).
SEVEN = [999298, 999297, 999255, 999254, 999253, 999252, 999251]


@pytest.fixture(autouse=True)
def dev_writes(page: Page):
    """Every write this page sends to /api/**, answered in the page (it never
    reaches dev) and recorded as 'METHOD /path'. Registered before the test's
    own routes, which Playwright asks first, so a write a test answers itself
    (own_the_buffer's buffer saves) never gets here."""
    written = []

    def handle(route):
        req = route.request
        method = req.method.upper()
        path = urlsplit(req.url).path
        if method in ("GET", "HEAD") or (method == "POST" and path in READ_POSTS):
            route.fallback()
            return
        if path == "/api/log_event":
            # A line for dev's Activity Log, not data: kept out of it, never a red
            # (a leaked dev audit ending mid-test logs one, _sayAuditEndedUnderPage).
            route.fulfill(status=200, content_type="application/json", body='{"success": true}')
            return
        written.append(f"{method} {path}")
        route.fulfill(status=200, content_type="application/json", body='{"success": true}')

    page.route("**/api/**", handle)
    yield written
    try:
        page.close()   # first: an un-routed live page can still save its buffer to dev
    except PlaywrightError:
        pass
    assert written == [], f"this test sent writes meant for dev (answered in the page instead): {written}"


@pytest.fixture(autouse=True)
def held(page: Page, dev_writes):
    """The page's own buffer endpoint, starting empty (after the tripwire, so it
    answers first). The stored dict: `held['buffer']` is what the page saved."""
    return own_the_buffer(page, [])


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

def _check_default_clears_data(page: Page, viewport: dict, held: dict, dev_writes: list):
    # Fresh default position (no saved override).
    page.add_init_script("try { localStorage.removeItem('fcc.fab.pos'); } catch(e){}")
    # The seven cards stay as injected: no heartbeat repaints them, and the
    # spool refresh (the only other source) brings nothing new.
    quiet_heartbeat(page)
    page.route("**/api/spools/refresh", lambda route: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    _goto_dashboard(page, viewport)
    # Seed a full buffer + scroll to the bottom so the WORST-case bottom card
    # weight is rendered (the 21.1 collision was with the bottom card).
    page.evaluate(
        """(ids) => {
            state.heldSpools = ids.map(id => ({id, display:'#'+id, color:'888888'}));
            renderBuffer();
            const bc = document.querySelector('.buffer-content'); if (bc) bc.scrollTop = bc.scrollHeight;
        }""",
        SEVEN,
    )
    page.wait_for_timeout(400)
    # renderBuffer still saves the seven, into this page's own store (45.10).
    for _ in range(50):
        if [s.get("id") for s in held["buffer"]] == SEVEN:
            break
        page.wait_for_timeout(100)
    assert [s.get("id") for s in held["buffer"]] == SEVEN, held["buffer"]
    fab = page.locator("#fcc-fab-search")
    expect(fab).to_be_visible()
    fab_box = fab.bounding_box()

    weigh_box = page.locator("#qr-weigh").bounding_box()
    assert weigh_box and not _rects_overlap(fab_box, weigh_box), (
        f"default FAB {fab_box} overlaps the WEIGH QR {weigh_box} (L36) at {viewport}"
    )
    weights = page.locator("#buffer-zone .fcc-card-metric")
    assert weights.count() == len(SEVEN), weights.count()
    for i in range(weights.count()):
        wb = weights.nth(i).bounding_box()
        if wb:
            assert not _rects_overlap(fab_box, wb), (
                f"default FAB {fab_box} overlaps a buffer weight {wb} (21.1) at {viewport}"
            )
    # navbar search button still present.
    expect(page.get_by_role("button", name="🔍 SEARCH")).to_be_visible()
    assert dev_writes == [], f"writes meant for dev (answered in the page instead): {dev_writes}"


def test_fab_default_clears_data_at_default_viewport(page: Page, held, dev_writes):
    _check_default_clears_data(page, {"width": 1600, "height": 1300}, held, dev_writes)


def test_fab_default_clears_data_at_short_viewport(page: Page, held, dev_writes):
    _check_default_clears_data(page, {"width": 1280, "height": 700}, held, dev_writes)


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
