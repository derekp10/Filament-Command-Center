"""Group 62.5: a key a person leaves under the ⌨️ list goes when they close it, hermetic.

The hotkeys the ⌨️ list covers stand down while it is up (the audit panel's N, the
Quick-Weigh's D, the grid's Q), so the scan accumulator keeps such a key as a scan's
first. Closing the list left it there for the accumulator's 2 s: a person's next Enter
read as a scan of "n" (enterIsAScan's in-flight rule) and was sent to the scan path,
which toasted an unknown code. Group 58 made the Space after it press nothing a mouse
couldn't reach; this is the Enter. And Shift+B, which the list lists, didn't stand down
at all: pressed while reading the list, it armed a bulk move and opened its panel under
the list, out of sight (2026-11-17, from Group 73's task file).

The real ⌨️ list (shortcuts_registry.js and its markup from dashboard.html), the real
scan accumulator (scripts.html, lifted as test_slow_scan_slash_js.py lifts it), the real
Shift+B block of inv_cmd.js and the real overlay_mount.js / inv_core.js, in
`isolated_page` (no network), with keys typed on a fake clock, so it runs under
--offline. processScan is a stub that records what reaches it.

RED on 152cb6e: the key left under the list reached the scan path, and Shift+B armed a
bulk move under the list. The scan read under the list, and the scan still arriving as
the list closes, pin what was already right.
"""
from __future__ import annotations

import pytest

from test_audit_no_label_58_js import real_shortcut_list
from test_slow_scan_confirms_js import MODULES, SHIFT_B
from test_slow_scan_slash_js import TYPE_JS, _accumulator

LIST = "#fcc-shortcuts-overlay"

STUBS = r"""
window.__scans = [];
window.__bulk = 0;
window.processScan = function (t) { window.__scans.push(t); };
window.showToast = function () {};
window.toggleBulkMove = function () { window.__bulk += 1; };
"""


@pytest.fixture
def list_page(isolated_page):
    p = isolated_page
    p.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    p.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js"):
        p.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    p.add_script_tag(content=SHIFT_B)
    real_shortcut_list(p)
    p.add_script_tag(content=_accumulator())             # last, as on the page
    p.evaluate(TYPE_JS, ["", 0, False, {}])               # the fake clock, before any key
    return p


def _type(page, keys, ms=30):
    page.evaluate(TYPE_JS, [keys, ms, False, {}])


def _later(page, ms):
    page.evaluate("(ms) => { window.__T += ms; }", ms)


def _open_list(page):
    page.evaluate("() => window.toggleShortcutsOverlay()")        # the title bar's ?
    page.wait_for_function("(s) => document.querySelector(s).style.display === 'block'", arg=LIST)


def _list_up(page):
    return page.evaluate("(s) => document.querySelector(s).style.display === 'block'", LIST)


def _seen(page):
    return page.evaluate("() => ({ scans: window.__scans.slice(), buffer: state.scanBuffer, bulk: window.__bulk })")


@pytest.mark.parametrize("close", ["escape", "close-button", "backdrop", "question-mark"])
def test_a_key_left_under_the_list_goes_when_a_person_closes_it(list_page, close):
    """N pressed under the list (the audit panel's N stands down there), the list
    closed, then a person's Enter 100 ms later: nothing reaches the scan path. RED on
    152cb6e for Escape, the ✕ and the backdrop: processScan("n"). A second ? already
    took the keys with it (its own clearScanBuffer, Group 57 review round 5): a pin."""
    page = list_page
    _open_list(page)
    _type(page, ["n"])
    _later(page, 50)
    if close == "escape":
        _type(page, ["Escape"])
    elif close == "close-button":
        page.click(f"{LIST} .btn-close")
    elif close == "backdrop":
        page.mouse.click(4, 4)
    else:
        # A person's ?: under 500 ms after another key it is a scan's (the list's own
        # rule, window.scanIsArriving), and the list stays up.
        _later(page, 600)
        _type(page, ["?"])
        page.wait_for_function("(s) => document.querySelector(s).style.display === 'none'", arg=LIST)
    assert not _list_up(page)
    _later(page, 100)
    _type(page, ["Enter"])
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["scans"] == [] and s["buffer"] == "", s


def test_two_keys_left_under_the_list_go_too(list_page):
    """Two keys (N, then the Quick-Weigh's D) and an Enter a second after the close:
    still nothing. RED on 152cb6e: processScan("nd"), the accumulator's full 2 s."""
    page = list_page
    _open_list(page)
    _type(page, ["n", "d"], 200)
    _type(page, ["Escape"])
    _later(page, 1000)
    _type(page, ["Enter"])
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["scans"] == [] and s["buffer"] == "", s


def test_a_scan_read_under_the_list_still_goes_out_whole(list_page):
    """A pin: scans work under the list, and its Enter came before any close."""
    page = list_page
    _open_list(page)
    _type(page, list("LOC:SHELF-1") + ["Enter"], 1)
    page.wait_for_timeout(50)
    assert _seen(page)["scans"] == ["LOC:SHELF-1"] and _list_up(page)


def test_a_scan_still_arriving_as_the_list_closes_stays_whole(list_page):
    """A pin for the close's own rule: the list closed by a click while a slow scanner
    is part way into a label keeps what it has typed, so the label arrives whole."""
    page = list_page
    _open_list(page)
    _type(page, list("LOC:SH"), 40)
    page.mouse.click(4, 4)                          # its backdrop
    assert not _list_up(page)
    _type(page, list("ELF-1") + ["Enter"], 40)
    page.wait_for_timeout(50)
    assert _seen(page)["scans"] == ["LOC:SHELF-1"]


def test_shift_b_stands_down_under_the_list(list_page):
    """Shift+B while reading the list (which lists it) arms nothing, and its B goes with
    the close; after the close it arms a bulk move as before. RED on 152cb6e: it armed
    the session under the list."""
    page = list_page
    _open_list(page)
    _type(page, ["B"])                              # TYPE_JS sends a capital with Shift held
    assert _seen(page)["bulk"] == 0
    _type(page, ["Escape"])
    assert _seen(page)["buffer"] == ""
    _later(page, 600)
    _type(page, ["B"])
    assert _seen(page)["bulk"] == 1
