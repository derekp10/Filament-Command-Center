"""A label scanned while the Quick-Weigh window is open is the scan's, never a
weight (Group 57 review, round 5: RED, older than Group 57), hermetic.

Runs the REAL overlay_mount.js, inv_core.js, weight_utils.js and
weight_entry.js, and the REAL scan accumulator (scripts.html's keydown block,
lifted as test_slow_scan_slash_js.py lifts it), in `isolated_page` (a chromium
with no route to any network), so it RUNS under --offline. Typed with
Playwright's real keyboard: a number field keeps only the characters a real key
can type into it, which is the defect.

The defect: the Quick-Weigh window (window.WeightEntry.openModal: a buffer
card's weight, the weigh-out list, the wizard's weigh) answered every Enter with
Save and asked no scan rule, and its weight field, focused from the moment it
opens, had no field scan capture. A scanner's label went into the field: a
number field (Gross, Net, Set Used) kept the digits of "ID:57" and Save stored
57 g; in Gross that is under the empty spool, so the spool read empty and Auto
Archive (on by default) archived it. A reading typed first got the digits
appended ("645" then "ID:57": 64557 g, the spool read full). With the focus on
Save the scan's Enter saved the reading typed so far, and with it on a mode tab
the scan's 'D' set the stored default mode.

Pinned, at 5 and 40 ms a key (a slower scanner's label takes more than the
150 ms the field capture used to allow in all): the label reaches the scan path,
the field gets back what was typed before it, nothing is saved and the window
stays; a person's reading and Enter still save in every mode, and a person's D
still sets the default; and the weigh-out list's weight boxes, which had the
capture already, take a slower scanner's label too. A label of digits alone
("57") typed after a reading is not pinned: it can't be told from a scale that
types its reading (inv_weigh_out.js keeps it a weight), which is Derek's call.
RED on aecf901, each test says how.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_slow_scan_slash_js import _accumulator

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
INPUT = "#fcc-we-input"
MODES = ["gross", "net", "set_used", "additive"]

STUBS = r"""
window.__store = {};
Object.defineProperty(window, 'localStorage', { configurable: true, get: () => ({
    getItem: (k) => (k in window.__store ? window.__store[k] : null),
    setItem: (k, v) => { window.__store[k] = String(v); },
    removeItem: (k) => { delete window.__store[k]; } }) });
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__scans = [];
window.processScan = function (t) { window.__scans.push(t); };
window.showToast = function () {};
window.__saved = [];
"""

# Spool #6 as dev has it: 1000 g, 31 g used, a 167 g empty spool.
OPEN_JS = """(mode) => { window.__saved = [];
    window.WeightEntry.openModal({ title: 'Weigh', spool: { id: 6, initial_weight: 1000, used_weight: 31 },
        empty_spool_weight: 167, defaultMode: mode, showAutoArchive: true,
        onSubmit: (p) => window.__saved.push(p) }); }"""


@pytest.fixture
def weigh(isolated_page):
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "weight_utils.js", "weight_entry.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=_accumulator())          # last, as on the page

    def open_(mode):
        page.evaluate(OPEN_JS, mode)
        page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=INPUT)

    return page, open_


def _seen(page):
    return page.evaluate("""(s) => ({ saved: window.__saved.map((p) => p.raw_value), scans: window.__scans.slice(),
        value: (document.querySelector(s) || {}).value, open: !!document.querySelector(s),
        mode: window.__store['fcc.weighEntry.defaultMode'] || null, buffer: state.scanBuffer })""", INPUT)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("ms", [5, 40])
def test_a_label_scanned_into_the_weight_is_the_scans(weigh, mode, ms):
    """The window open in each mode, the field focused, and FCC's own spool
    label scanned: it reaches the scan path, the field is empty again, nothing
    is saved and the window stays. RED on aecf901: Gross saved 57 g (the
    spool read empty, and was archived), Net 57 g left, Set Used 57 g used;
    Additive kept the text and the scan went nowhere."""
    page, open_ = weigh
    open_(mode)
    page.keyboard.type("ID:57", delay=ms)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["value"] == "" and s["open"], (mode, ms, s)


@pytest.mark.parametrize("mode, reading", [("gross", "645"), ("additive", "+25")])
def test_a_reading_typed_before_a_scan_is_kept(weigh, mode, reading):
    """A person types the reading, then scans the next spool's label before
    pressing Enter: the field keeps the reading, the label goes to the scan
    path, and the person's own Enter then saves the reading. RED before round
    5: the digits joined the reading ("64557") and the scan's Enter saved it."""
    page, open_ = weigh
    open_(mode)
    page.keyboard.type(reading, delay=200)
    page.wait_for_timeout(300)
    page.keyboard.type("ID:57", delay=5)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["value"] == reading, (mode, s)
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__saved.length === 1")
    assert _seen(page)["saved"] == [reading]


def test_a_scan_with_the_focus_on_save_saves_nothing(weigh):
    """A reading typed, the focus moved to Save, and a label scanned: its keys
    go to the scan accumulator, and its Enter is the scan's. Nothing is saved
    and the label reaches the scan path. RED on aecf901: the scan's Enter
    saved the reading typed so far (and its 'D' set the default mode)."""
    page, open_ = weigh
    open_("gross")
    page.keyboard.type("645", delay=50)
    page.evaluate("() => document.getElementById('fcc-we-save').focus()")
    page.keyboard.type("ID:57", delay=5)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["value"] == "645" and s["mode"] is None, s


def test_a_scans_d_on_a_mode_tab_never_sets_the_default(weigh):
    """The focus on a mode tab and a label scanned ("ID:57" has a D): the
    stored default stays as it was, and the label reaches the scan path. A
    person's D there still sets it, and leaves no 'd' to start the next scan.
    RED on aecf901: the scan made Net the default."""
    page, open_ = weigh
    open_("gross")
    page.locator(".fcc-we-tab[data-mode='net']").click()
    page.locator(".fcc-we-tab[data-mode='net']").focus()
    page.keyboard.type("ID:57", delay=5)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["mode"] is None and s["scans"] == ["ID:57"] and s["saved"] == [], s
    page.wait_for_timeout(600)                         # past the 500 ms a scan is in flight
    page.keyboard.press("d")
    s = _seen(page)
    assert s["mode"] == "net" and s["buffer"] == "", s


def test_a_persons_typing_then_a_pause_is_never_taken_for_a_scan(weigh):
    """A person types something a weight can't hold, quickly ("+50g" in
    Additive), stops, and presses Enter half a second later: the Enter is
    theirs. Their text stays in the field (it reads "Invalid input"), nothing
    goes to the scan path, and nothing is saved. A scanner sends its Enter
    right after its last key, and the capture asks that too: going by the gap
    between keys alone, the typing was sent off as a scan and wiped from the
    field."""
    page, open_ = weigh
    open_("additive")
    page.keyboard.type("+50g", delay=30)
    page.wait_for_timeout(500)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == [] and s["value"] == "+50g" and s["open"], s
    assert "Invalid input" in page.evaluate("() => document.getElementById('fcc-we-warn').textContent")


@pytest.mark.parametrize("ms", [5, 40])
def test_the_weigh_out_lists_weight_box_takes_a_slower_scanners_label_too(isolated_page, ms):
    """The weigh-out list's weight boxes (inv_weigh_out.js) had the field
    capture already, but it allowed a whole label only 150 ms: "ID:57" at 40 ms
    a key took 200 ms and was typed in as a weight. It goes by the gap between
    keys there too: the label reaches the scan path and the reading typed
    before it stays. RED on aecf901 at 40 ms a key."""
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body>"
                     "<input class='weigh-input' id='w1'></body></html>")
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "inv_weigh_out.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.locator("#w1").focus()
    page.keyboard.type("645", delay=200)
    page.wait_for_timeout(300)
    page.keyboard.type("ID:57", delay=ms)
    page.keyboard.press("Enter")
    assert page.evaluate("() => [window.__scans.slice(), document.getElementById('w1').value]") == [["ID:57"], "645"]


def test_a_persons_reading_and_enter_still_save(weigh):
    """A reading typed by hand, by a fast typist too, and Enter saves it in
    every mode: the field capture never takes digits, '.', '+' or '-'. Keys a
    person left in the scan buffer before the window opened don't take that
    Enter (only an Enter off the field asks whether it is a scan's)."""
    page, open_ = weigh
    for mode, reading in (("gross", "645.5"), ("net", "425"), ("additive", "-10"), ("set_used", "575")):
        page.evaluate("() => { state.scanBuffer = 'ab'; state.scanStartTime = Date.now() - 1000; }")
        open_(mode)
        page.keyboard.type(reading, delay=30)
        page.keyboard.press("Enter")
        page.wait_for_function("() => window.__saved.length === 1")
        assert _seen(page)["saved"] == [reading], mode
