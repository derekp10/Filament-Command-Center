"""Regression guard for the draggable Activity-Log pill (2026-06-15).

Once the search FAB became drag-to-park (21.1), the hard-anchored "N new"
Activity-Log pill (#fcc-log-pill) looked orphaned next to it. It now shares the
same engine (draggable_pill.js → window.makeDraggablePill), persisting to
localStorage 'fcc.logPill.pos'. These tests assert: a tap opens the log overlay;
a drag moves + persists it (and does NOT open the overlay); a saved position is
restored + viewport-clamped; and — critically — dragging never breaks the pill's
JS-toggled show/hide ("unseen" gate in inv_core.js), since the engine writes only
position, never `display`.
"""
from __future__ import annotations

from playwright.sync_api import Page


def _goto_dashboard(page: Page, viewport=None):
    if viewport:
        page.set_viewport_size(viewport)
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function("typeof window.makeDraggablePill === 'function'")
    page.wait_for_selector("#fcc-log-pill", state="attached", timeout=10000)


def _show_pill(page: Page):
    # The pill is display:none until there are unseen log entries; force it
    # visible the same way _updateLogPill does (inline-flex !important) so we can
    # interact with it. The drag engine attached its listeners on init, while
    # hidden — this only flips visibility, never position.
    page.evaluate(
        """() => {
            const pill = document.getElementById('fcc-log-pill');
            pill.style.setProperty('display', 'inline-flex', 'important');
            pill.style.alignItems = 'center';
        }"""
    )
    page.wait_for_timeout(100)


def _pill_center(page: Page):
    box = page.locator("#fcc-log-pill").bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_log_pill_shows_naturally_with_unseen_entries(page: Page):
    """The drag wiring must NOT interfere with _updateLogPill's show path: an
    unseen log entry must still surface the pill, on-screen + clickable. Injects
    a log through the real render path (force=true bypasses the no-wiggle hash)
    so the test is independent of the dev container's (restart-wiped) log ring."""
    page.add_init_script(
        "try { localStorage.removeItem('fcc.logPill.lastSeenTime');"
        " localStorage.removeItem('fcc.logPill.pos'); } catch(e){}"
    )
    _goto_dashboard(page)
    page.wait_for_function("typeof window._renderLogsPayload === 'function'")
    page.evaluate(
        "() => window._renderLogsPayload({logs:[{time:'23:59:59', msg:'diag entry', type:'info'}]}, true)"
    )
    page.wait_for_function(
        "() => { const p = document.getElementById('fcc-log-pill');"
        " return p && getComputedStyle(p).display !== 'none'; }",
        timeout=4000,
    )
    box = page.locator("#fcc-log-pill").bounding_box()
    assert box is not None, "pill reports a box-less layout despite display != none"
    vw = page.evaluate("() => window.innerWidth")
    vh = page.evaluate("() => window.innerHeight")
    assert (box["x"] >= 0 and box["y"] >= 0
            and box["x"] + box["width"] <= vw and box["y"] + box["height"] <= vh), (
        f"pill surfaced off-screen: {box} in {vw}x{vh}"
    )
    # And the surfaced pill must be the clickable top element at its center.
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    top = page.evaluate(
        "([x,y]) => { const el = document.elementFromPoint(x,y);"
        " return el ? (el.closest('#fcc-log-pill') ? 'fcc-log-pill' : (el.id||el.className)) : null; }",
        [cx, cy],
    )
    assert top and "fcc-log-pill" in str(top), f"surfaced pill not clickable, got {top!r}"


def test_log_pill_tap_opens_overlay(page: Page):
    _goto_dashboard(page)
    _show_pill(page)
    cx, cy = _pill_center(page)
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.up()  # clean tap → openLogPillOverlay
    page.wait_for_selector("#fcc-log-pill-overlay", timeout=5000)


def test_log_pill_drag_moves_persists_and_does_not_open(page: Page):
    page.add_init_script("try { localStorage.removeItem('fcc.logPill.pos'); } catch(e){}")
    _goto_dashboard(page)
    _show_pill(page)
    before = page.locator("#fcc-log-pill").bounding_box()
    cx, cy = _pill_center(page)
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx - 120, cy - 80, steps=8)  # >6px → drag
    page.mouse.up()
    page.wait_for_timeout(300)
    after = page.locator("#fcc-log-pill").bounding_box()
    assert (abs(after["x"] - before["x"]) > 20 or abs(after["y"] - before["y"]) > 20), (
        f"log pill should have moved on drag: before={before} after={after}"
    )
    saved = page.evaluate("() => localStorage.getItem('fcc.logPill.pos')")
    assert saved, "drag should persist the position to localStorage 'fcc.logPill.pos'"
    assert page.locator("#fcc-log-pill-overlay").count() == 0, "drag must not open the log overlay"


def test_log_pill_position_restored_and_clamped(page: Page):
    page.add_init_script("localStorage.setItem('fcc.logPill.pos', JSON.stringify({left:500, bottom:400}));")
    _goto_dashboard(page, {"width": 1600, "height": 1300})
    _show_pill(page)
    box = page.locator("#fcc-log-pill").bounding_box()
    # left:500 → x≈500; bottom:400 → y = 1300 - 400 - height.
    assert abs(box["x"] - 500) < 6, f"restored left should be ~500: {box}"
    expected_y = 1300 - 400 - box["height"]
    assert abs(box["y"] - expected_y) < 8, f"restored bottom:400 → y~{expected_y}: {box}"
    # Shrinking the viewport must clamp it back on-screen.
    page.set_viewport_size({"width": 700, "height": 500})
    page.wait_for_timeout(200)
    box2 = page.locator("#fcc-log-pill").bounding_box()
    assert box2["x"] + box2["width"] <= 700 and box2["y"] + box2["height"] <= 500, (
        f"log pill must stay within the shrunk viewport: {box2}"
    )
    assert box2["x"] >= 0 and box2["y"] >= 0, f"log pill must not go off the top/left: {box2}"


def test_log_pill_drag_survives_show_hide_toggle(page: Page):
    """The engine must never touch `display`, so the pill's JS show/hide ('unseen'
    gate) keeps working AND the dragged position persists across a hide→show."""
    page.add_init_script("try { localStorage.removeItem('fcc.logPill.pos'); } catch(e){}")
    _goto_dashboard(page)
    _show_pill(page)
    cx, cy = _pill_center(page)
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx - 150, cy - 100, steps=8)
    page.mouse.up()
    page.wait_for_timeout(200)
    dragged = page.locator("#fcc-log-pill").bounding_box()
    # Hide (as _updateLogPill does when the unseen count hits 0) then re-show.
    page.evaluate("() => document.getElementById('fcc-log-pill').style.display = 'none'")
    page.wait_for_timeout(100)
    assert page.locator("#fcc-log-pill").is_visible() is False
    _show_pill(page)
    shown = page.locator("#fcc-log-pill").bounding_box()
    assert abs(shown["x"] - dragged["x"]) < 3 and abs(shown["y"] - dragged["y"]) < 3, (
        f"dragged position must survive a hide→show toggle: dragged={dragged} shown={shown}"
    )
    # Still the top (clickable) element at its center after the toggle.
    sx, sy = _pill_center(page)
    top = page.evaluate(
        "([x,y]) => { const el = document.elementFromPoint(x,y); "
        "return el ? (el.closest('#fcc-log-pill') ? 'fcc-log-pill' : (el.id || el.className)) : null; }",
        [sx, sy],
    )
    assert top and "fcc-log-pill" in str(top), f"pill must stay clickable after toggle, got {top!r}"
