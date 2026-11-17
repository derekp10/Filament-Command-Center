"""mountOverlay's `trapTab` (Group 58 review, finding 27), hermetic: the REAL
overlay_mount.js in `isolated_page`, and real Tab keys, because what a browser's own Tab
does is the point. test_audit_stacking_58_js.py has the three overlays that pass it.

Opt-in: every other overlay keeps the Tab it had. While the overlay is on top, Tab and
Shift+Tab wrap inside its focusable, visible, enabled controls, a focus outside it comes
to its first one, and nothing but Tab is touched.

RED on 1f8e03a unless a test says it pins what was already right.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MODULES = Path(__file__).resolve().parent.parent / "static" / "js" / "modules"

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<button id="behind">behind</button><input id="box" type="text">
</body></html>"""

SHEET = """<div id="sheet" tabindex="-1">
    <button id="one">one</button>
    <button id="off" disabled>off</button>
    <button id="gone" style="display:none">gone</button>
    <button id="unseen" style="visibility:hidden">unseen</button>
    <div id="inert-part" inert><button id="asleep">asleep</button></div>
    <div id="row" tabindex="-1">a row</div>
    <a id="link" href="#here">link</a>
    <input id="secret" type="hidden">
    <select id="list" size="2"><option>a</option><option>b</option></select>
    <button id="last">last</button>
</div>"""
WALK = ["one", "link", "list", "last"]


@pytest.fixture
def overlay(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=(MODULES / "overlay_mount.js").read_text(encoding="utf-8"))

    def mount(**opts):
        page.evaluate("""([id, content, opts]) => { window.__h = window.__h || {};
            window.__h[id] = window.mountOverlay(Object.assign({ id, content }, opts)); }""",
                      [opts.pop("id", "fcc-test"), opts.pop("content", SHEET), opts])
    return page, mount


def at(page):
    return page.evaluate("() => document.activeElement.id || document.activeElement.tagName")


def tabs(page, key, times):
    out = []
    for _ in range(times):
        page.keyboard.press(key)
        out.append(at(page))
    return out


def test_it_is_off_unless_asked_for(overlay):
    """A pin: every other overlay's Tab is what it was."""
    page, mount = overlay
    mount()
    page.focus("#last")
    page.keyboard.press("Tab")
    assert at(page) not in WALK


def test_tab_wraps_round_the_controls_it_can_land_on(overlay):
    page, mount = overlay
    mount(trapTab=True)
    page.focus("#one")
    assert tabs(page, "Tab", 4) == WALK[1:] + WALK[:1]


def test_shift_tab_wraps_the_other_way(overlay):
    page, mount = overlay
    mount(trapTab=True)
    page.focus("#one")
    assert tabs(page, "Shift+Tab", 4) == ["last", "list", "link", "one"]


@pytest.mark.parametrize("key, want", [("Tab", "link"), ("Shift+Tab", "one")])
def test_from_a_focus_out_of_the_tab_order_it_goes_to_the_nearest_stop(overlay, key, want):
    """A list row with tabindex -1, between #one and #link: a browser's own order, kept. A
    pin: proved on a copy that goes to the first stop."""
    page, mount = overlay
    mount(trapTab=True)
    page.focus("#row")
    page.keyboard.press(key)
    assert at(page) == want


@pytest.mark.parametrize("key, want", [("Tab", "one"), ("Shift+Tab", "last")])
def test_from_the_panel_itself_it_goes_in_at_the_near_end(overlay, key, want):
    page, mount = overlay
    mount(trapTab=True)
    page.focus("#sheet")
    page.keyboard.press(key)
    assert at(page) == want


@pytest.mark.parametrize("key", ["Tab", "Shift+Tab"])
@pytest.mark.parametrize("left_on", ["#behind", "#box", None], ids=["a-button", "a-box", "nothing"])
def test_a_focus_outside_it_comes_to_the_first(overlay, key, left_on):
    page, mount = overlay
    mount(trapTab=True)
    if left_on:
        page.focus(left_on)
    page.keyboard.press(key)
    assert at(page) == "one"


def test_it_reads_the_controls_at_the_press_not_at_the_mount(overlay):
    """A button enabled or drawn since counts: the panel redraws its body. A pin: proved on
    a copy that reads them once."""
    page, mount = overlay
    mount(trapTab=True)
    page.evaluate("() => { document.getElementById('off').disabled = false; }")
    page.focus("#one")
    page.keyboard.press("Tab")
    assert at(page) == "off"


def test_with_no_control_to_land_on_the_focus_stays_put(overlay):
    page, mount = overlay
    mount(trapTab=True, content='<div id="bare">words only</div>')
    page.focus("#box")
    page.keyboard.press("Tab")
    assert at(page) == "box"


def test_only_the_overlay_on_top_traps(overlay):
    """What is on top owns the keys: the one under it leaves them alone, and an overlay over
    it that traps nothing keeps the Tab it had. A pin: proved on a copy with no such test."""
    page, mount = overlay
    mount(trapTab=True)
    mount(id="fcc-over", tier="confirm", content='<div><button id="a">a</button><button id="b">b</button></div>')
    page.focus("#a")
    page.keyboard.press("Tab")
    assert at(page) == "b"
    page.keyboard.press("Tab")
    assert at(page) not in WALK


def test_it_goes_when_the_overlay_on_top_goes(overlay):
    page, mount = overlay
    mount(trapTab=True)
    mount(id="fcc-over", tier="confirm", trapTab=True,
          content='<div><button id="a">a</button><button id="b">b</button></div>')
    page.focus("#a")
    assert tabs(page, "Tab", 2) == ["b", "a"]
    page.evaluate("() => window.__h['fcc-over'].cleanup()")
    page.focus("#last")
    assert tabs(page, "Tab", 1) == ["one"]


def test_it_goes_with_the_overlay(overlay):
    """A pin: proved on a copy with neither the disposer nor the on-top test."""
    page, mount = overlay
    mount(trapTab=True)
    page.evaluate("""() => { window.__h['fcc-test'].cleanup(); window.__kept = null;
        document.addEventListener('keydown', (e) => { window.__kept = e.defaultPrevented; }); }""")
    page.focus("#behind")
    page.keyboard.press("Tab")
    assert page.evaluate("window.__kept") is False and at(page) == "box"


def test_the_documents_other_capture_listeners_still_hear_tab(overlay):
    """The legacy picker reads a Tab as a person's key in one of those: stopImmediate-
    Propagation would take that away. Tab stops there: a bubble listener hears nothing."""
    page, mount = overlay
    page.evaluate("""() => { window.__heard = { capture: 0, bubble: 0 };
        document.addEventListener('keydown', (e) => { if (e.key === 'Tab') window.__heard.bubble += 1; }); }""")
    mount(trapTab=True)
    page.evaluate("""() => document.addEventListener('keydown', (e) => {
        if (e.key === 'Tab') window.__heard.capture += 1; }, true)""")
    page.focus("#one")
    page.keyboard.press("Tab")
    assert page.evaluate("window.__heard") == {"capture": 1, "bubble": 0}


@pytest.mark.parametrize("key", ["ArrowDown", "Enter", "x", " ", "Escape"])
def test_nothing_but_tab_is_touched(overlay, key):
    """A pin: scans and every other key go on as they went. Proved on a copy with no key
    test."""
    page, mount = overlay
    page.evaluate("""() => { window.__heard = [];
        document.addEventListener('keydown', (e) => { window.__heard.push([e.key, e.defaultPrevented]); }); }""")
    mount(trapTab=True, onEscape=None)
    page.focus("#row")
    page.keyboard.press(key)
    # Escape is mountOverlay's own, and it stops there.
    assert page.evaluate("window.__heard") == ([] if key == "Escape" else [[key, False]])


@pytest.mark.parametrize("mod", ["Control", "Alt"])
def test_a_browsers_own_chord_is_left_alone(overlay, mod):
    """A pin of the modifier test: proved on a copy without it."""
    page, mount = overlay
    page.evaluate("""() => { window.__prevented = null;
        document.addEventListener('keydown', (e) => { if (e.key === 'Tab') window.__prevented = e.defaultPrevented; }); }""")
    mount(trapTab=True)
    page.focus("#one")
    page.keyboard.down(mod)
    page.keyboard.press("Tab")
    page.keyboard.up(mod)
    assert page.evaluate("window.__prevented") is False
