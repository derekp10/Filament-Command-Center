"""A label scanned while the Quick-Weigh window is open is the scan's, never a
weight (Group 57 review, rounds 5 and 6: RED, older than Group 57), hermetic.

Runs the REAL overlay_mount.js, inv_core.js, weight_utils.js and
weight_entry.js, and the REAL scan accumulator (scripts.html's keydown block,
lifted as test_slow_scan_slash_js.py lifts it), in `isolated_page` (a chromium
with no route to any network), so it RUNS under --offline. Typed with
Playwright's real keyboard, since a number field keeps only the characters a
real key can type into it (the defect), on a fake clock (Date.now and
performance.now; the page's timers run as they do), so a scanner's speed is
exact whatever the machine's load.

The defect: the Quick-Weigh window (window.WeightEntry.openModal: a buffer
card's weight, the wizard's weigh) answered every Enter with Save and asked no
scan rule, and its weight field, focused from the moment it opens, had no field
scan capture. A scanner's label went into the field: a number field (Gross,
Net, Set Used) kept the digits of "ID:57" and Save stored 57 g; in Gross that is
under the empty spool, so the spool read empty and Auto Archive (on by default)
archived it. A reading typed first got the digits appended ("645" then "ID:57":
64557 g, the spool read full). With the focus on Save the scan's Enter saved the
reading typed so far, and with it on a mode tab the scan's 'D' set the stored
default mode. Round 5's fix judged the speed between keys (each under 150 ms),
and round 6 found what that left: a scanner at 150 ms a key or slower, a burst
scanner (its label in a burst, its Enter a moment later), or one pause inside a
label still saved it; the missing-tare prompt's box had no capture at all (a
label became the tare); a scan with the focus on the Auto Archive switch was
lost, and its Enter saved and its 'D' set the default; Enter on Cancel, × or Set
as default saved; the prompt's Enter ran this window's Save a second time (a
second prompt stayed up and saved again), its Escape cancelled this window and
its arrows switched this window's mode; after a pause the 'D' of a label's own
"ID:" cut the scan; a person's quick "645g" or "+25 " was taken for a scan; and
the preview kept the scanner's digits after the field got its reading back.

Pinned (RED on 5b5a18e, each test says how): every weight box judges what was
typed (inv_core.js, installWeightScanCapture): a ':' or '/' proves a label at
any speed, and its keys never reach the box; anything else a weight can't hold
is a scan only at scanner speed, unless it reads as a weight with its unit; a
Space or a comma is a weight's. The window's keys belong to it only while it is
on top (window.isTopOverlay), Enter answers the control it is on, and the D
leaves a scan's own D alone. A label of digits alone ("57") typed after a
reading is not pinned: it can't be told from a scale that types its reading,
which is Derek's call.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_slow_scan_slash_js import _accumulator

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
INPUT = "#fcc-we-input"
PROMPT = "#fcc-missing-empty-weight-overlay"
PROMPT_INPUT = "#fcc-missing-empty-weight-overlay-input"
MODES = ["gross", "net", "set_used", "additive"]
SPEEDS = [2, 40, 150, 250]          # ms a key: a fast scanner to one slower than the repo's slowest

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
window.__cancelled = 0;
"""

# The page's clock: Date.now and performance.now move only when a test says.
FAKE_CLOCK = r"""() => {
    if (window.__fakeClock) return;
    const base = Date.now(), pbase = performance.now();
    window.__T = 0;
    Date.now = () => base + window.__T;
    performance.now = () => pbase + window.__T;
    window.__fakeClock = true;
}"""

# Spool #6 as dev has it: 1000 g, 31 g used, a 167 g empty spool (`tare: null`
# for a spool with none on record anywhere, as every Prusament spool on dev).
OPEN_JS = """(o) => { window.__saved = []; window.__cancelled = 0;
    window.WeightEntry.openModal({ title: 'Weigh', spool: { id: 6, initial_weight: 1000, used_weight: 31 },
        empty_spool_weight: o.tare, defaultMode: o.mode, showAutoArchive: true,
        onSubmit: (p) => window.__saved.push(p), onCancel: () => { window.__cancelled += 1; } }); }"""


@pytest.fixture
def weigh(isolated_page):
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "weight_utils.js", "weight_entry.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate(FAKE_CLOCK)

    def open_(mode, tare=167):
        page.evaluate(OPEN_JS, {"mode": mode, "tare": tare})
        page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=INPUT)

    return page, open_


def press(page, keys, ms, enter=True, pauses=None):
    """Real keys on the page's fake clock: each `ms` after the one before
    (`pauses` adds a key's own wait, {index: ms}), the Enter last. `keys` is a
    string, or a list of keys (named ones such as "Backspace" among them)."""
    seq = list(keys)
    if enter:
        seq.append("Enter")
    for i, k in enumerate(seq):
        page.evaluate("(ms) => { window.__T += ms; }", ms + (pauses or {}).get(i, 0))
        if len(k) == 1:
            page.keyboard.type(k)
        else:
            page.keyboard.press(k)


def later(page, ms):
    page.evaluate("(ms) => { window.__T += ms; }", ms)


def _seen(page):
    return page.evaluate("""([s, p]) => ({ saved: window.__saved.map((x) => x.raw_value),
        tares: window.__saved.map((x) => x.empty_spool_weight), scans: window.__scans.slice(),
        value: (document.querySelector(s) || {}).value, open: !!document.querySelector(s),
        cancelled: window.__cancelled, prompts: document.querySelectorAll(p).length,
        mode: window.__store['fcc.weighEntry.defaultMode'] || null, buffer: state.scanBuffer,
        tab: (document.querySelector('.fcc-we-tab.btn-info') || {}).dataset ? document.querySelector('.fcc-we-tab.btn-info').dataset.mode : null,
        preview: (document.getElementById('fcc-we-preview') || {}).textContent || '' })""", [INPUT, PROMPT])


def _on_tab(page, mode="net"):
    """The mode set to `mode` and the focus on its tab (Shift+Tab from the
    field, say)."""
    tab = page.locator(f".fcc-we-tab[data-mode='{mode}']")
    tab.click()
    tab.focus()
    later(page, 700)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("ms", SPEEDS)
def test_a_label_scanned_into_the_weight_is_the_scans(weigh, mode, ms):
    """The window open in each mode, the field focused, and FCC's own spool
    label scanned at each speed: it reaches the scan path, the field is empty
    again, nothing is saved and the window stays. RED on 5b5a18e at 150 and
    250 ms a key: a number field saved 57 g (in Gross the spool read empty, and
    was archived), and Additive kept the text with the scan gone nowhere."""
    page, open_ = weigh
    open_(mode)
    press(page, "ID:57", ms)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["value"] == "" and s["open"], (mode, ms, s)


@pytest.mark.parametrize("mode", ["gross", "net", "set_used"])
@pytest.mark.parametrize("gap", [450, 700])
def test_a_burst_scanners_label_is_the_scans(weigh, mode, gap):
    """A scanner that sends its label in a burst and its Enter a moment later
    (the repo's model: keys 2 ms apart, the Enter 450 or 700 ms after): the
    Enter is the label's. RED on 5b5a18e: the Enter came over 150 ms after the
    last key, so Gross saved 134 g."""
    page, open_ = weigh
    open_(mode)
    press(page, "ID:134", 2, pauses={6: gap})
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:134"] and s["value"] == "", (mode, gap, s)


@pytest.mark.parametrize("at", [3, 4, 5])               # after the ':', before the last digit, before the Enter
@pytest.mark.parametrize("pause", [300, 600, 1900])
def test_a_pause_inside_a_label_is_the_scans(weigh, at, pause):
    """A scanner that stalls inside the label, up to the accumulator's 2 s:
    the label is still the scan's. RED on 5b5a18e: a stall of 150 ms or more
    left digits the field could hold, and Save stored them."""
    page, open_ = weigh
    open_("gross")
    press(page, "ID:57", 5, pauses={at: pause})
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["value"] == "", (at, pause, s)


@pytest.mark.parametrize("mode, reading", [("gross", "645"), ("set_used", "575"), ("additive", "+25")])
@pytest.mark.parametrize("scanner", ["fast", "slow", "burst"])
def test_a_reading_typed_before_a_scan_is_kept(weigh, mode, reading, scanner):
    """A person types the reading, then scans the next spool's label before
    pressing Enter: the field keeps the reading, the label goes to the scan
    path, and the person's own Enter then saves the reading. RED on 5b5a18e
    for a slower or a burst scanner: the digits joined the reading ("64557",
    "645134") and the scan's Enter saved it."""
    page, open_ = weigh
    open_(mode)
    press(page, reading, 200, enter=False)
    later(page, 300)
    label = "ID:134" if scanner == "burst" else "ID:57"
    if scanner == "fast":
        press(page, label, 5)
    elif scanner == "slow":
        press(page, label, 250)
    else:
        press(page, label, 2, pauses={6: 450})
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == [label] and s["value"] == reading, (mode, scanner, s)
    later(page, 300)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__saved.length === 1")
    assert _seen(page)["saved"] == [reading]


@pytest.mark.parametrize("mode, typed, ms, saved", [
    ("gross", "645g", 100, "645"),           # a quick typist's unit
    ("gross", "645 g", 100, "645"),
    ("additive", "+25 ", 60, "+25 "),         # a stray Space
    ("gross", "645.5 g", 5, "645.5"),         # a scale that types its reading with the unit
    ("net", "645.5g", 5, "645.5"),
    ("gross", " 645.5", 5, "645.5"),          # and with a padding Space
])
def test_a_reading_with_its_unit_or_a_space_is_a_weight(weigh, mode, typed, ms, saved):
    """A reading typed quickly with its unit or a Space, or one a scale types,
    and Enter right after: it is saved, as before round 5. RED on 5b5a18e:
    round 5's speed rule took each for a scan and emptied the field."""
    page, open_ = weigh
    open_(mode)
    press(page, typed, ms)
    page.wait_for_function("() => window.__saved.length === 1")
    s = _seen(page)
    assert s["saved"] == [saved] and s["scans"] == [], (typed, s)


def test_a_fast_label_without_a_colon_is_a_scan(weigh):
    """Another label at scanner speed whose characters a weight can't hold (a
    bare location label, "XL-3": in Net a number field kept -3 g, and the spool
    read full) is a scan, as the weigh-out list's boxes always had it."""
    page, open_ = weigh
    open_("net")
    press(page, "XL-3", 5)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["XL-3"] and s["value"] == "", s


def test_a_scan_with_the_focus_on_save_saves_nothing(weigh):
    """A reading typed, the focus moved to Save, and a label scanned: its keys
    go to the scan accumulator, and its Enter is the scan's. Nothing is saved
    and the label reaches the scan path. RED on aecf901: the scan's Enter
    saved the reading typed so far (and its 'D' set the default mode)."""
    page, open_ = weigh
    open_("gross")
    press(page, "645", 50, enter=False)
    page.evaluate("() => document.getElementById('fcc-we-save').focus()")
    later(page, 700)
    press(page, "ID:57", 5)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["value"] == "645" and s["mode"] is None, s


@pytest.mark.parametrize("how", ["tab", "click"])
def test_a_scan_with_the_focus_on_the_auto_archive_switch_is_the_scans(weigh, how):
    """A reading typed, the focus on the Auto Archive switch (a Tab from the
    field, or a click on it), and a label scanned: the scan reaches the scan
    path, nothing is saved, the default mode stays as it was. RED on 5b5a18e:
    a checkbox is an INPUT, so the scan accumulator ignored its keys, the scan
    was lost, its 'D' set the default and its Enter saved 645."""
    page, open_ = weigh
    open_("gross")
    press(page, "645", 200, enter=False)
    if how == "tab":
        page.keyboard.press("Tab")
    else:
        page.locator("#fcc-we-auto-archive").click()
    assert page.evaluate("() => document.activeElement.id") == "fcc-we-auto-archive"
    later(page, 700)
    press(page, "ID:57", 5)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["mode"] is None and s["open"], (how, s)


@pytest.mark.parametrize("target, outcome", [
    ("#fcc-we-cancel", "cancelled"), ("#fcc-we-close", "cancelled"), ("#fcc-we-set-default", "default"),
    (".fcc-we-tab[data-mode='net']", "net"), ("#fcc-we-auto-archive", "saved"), ("#fcc-we-save", "saved")])
def test_enter_answers_the_control_it_is_on(weigh, target, outcome):
    """A person's Enter presses the button it is on: Cancel and × cancel, Set
    as default sets it, a mode tab picks its mode; on Save or the switch it
    saves. RED on 5b5a18e: on Cancel, × or Set as default it saved the reading
    (a low reading archived the spool), and on a mode tab it did nothing."""
    page, open_ = weigh
    open_("gross")
    press(page, "645", 200, enter=False)
    page.locator(target).focus()
    later(page, 700)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    s = _seen(page)
    if outcome == "cancelled":
        assert s["cancelled"] == 1 and s["saved"] == [] and not s["open"], s
    elif outcome == "default":
        assert s["mode"] == "gross" and s["saved"] == [] and s["open"], s
    elif outcome == "net":
        assert s["tab"] == "net" and s["saved"] == [] and s["open"], s
    else:
        assert s["saved"] == ["645"] and not s["open"], s


@pytest.mark.parametrize("label, ms, pauses", [
    ("ID:57", 5, {}),                 # round 5's case
    ("ID:57", 5, {1: 600}),           # a pause before its D
    ("CMD:WEIGH", 250, {}),           # a slower scanner: "CM" is 500 ms old at the D
    ("OLD:120", 250, {}),
])
def test_a_scans_d_on_a_mode_tab_never_sets_the_default(weigh, label, ms, pauses):
    """The focus on a mode tab and a label with a D scanned: the stored
    default stays as it was, and the label reaches the scan path whole. RED on
    aecf901 (the scan made Net the default), and on 5b5a18e after a pause
    before the D or at 250 ms a key: the D took the keys before it and the scan
    arrived cut (":57", ":WEIGH", ":120")."""
    page, open_ = weigh
    open_("gross")
    _on_tab(page)
    press(page, label, ms, pauses=pauses)
    s = _seen(page)
    assert s["mode"] is None and s["scans"] == [label] and s["saved"] == [], (label, ms, pauses, s)


def test_a_persons_d_sets_the_default_and_leaves_the_next_label_whole(weigh):
    """A person's D on a mode tab sets the default, and takes the key it finds
    left before it out of the scan buffer (a stray 'x'), so the next label
    arrives whole. Unpinned until round 6: without the clear, every test stayed
    green and the next label arrived with the stray key glued in front."""
    page, open_ = weigh
    open_("gross")
    _on_tab(page)
    press(page, "x", 0, enter=False)
    later(page, 600)
    press(page, "d", 0, enter=False)
    s = _seen(page)
    assert s["mode"] == "net" and s["buffer"] == "", s
    later(page, 600)
    press(page, "ID:57", 5)
    assert _seen(page)["scans"] == ["ID:57"]


def test_the_preview_follows_the_field_after_a_scan(weigh):
    """The preview reads what the field holds after a scan: the reading typed
    before it, or nothing. RED on 5b5a18e: the field got its reading back with
    no input event, so the preview kept the scanner's digits ("Used 1000g ·
    Remaining 0g", an empty spool, on an empty field)."""
    page, open_ = weigh
    open_("additive")
    press(page, "+25", 200, enter=False)
    before = _seen(page)["preview"]
    assert "Used" in before, before
    later(page, 300)
    press(page, "ID:57", 5)
    assert _seen(page)["preview"] == before
    page.evaluate("() => document.getElementById('fcc-we-cancel').click()")
    open_("gross")
    press(page, "ID:57", 5)
    assert _seen(page)["preview"].startswith("Enter a value"), _seen(page)["preview"]


@pytest.mark.parametrize("ms", [5, 40, 250])
def test_a_label_scanned_into_the_missing_tare_prompt_is_the_scans(weigh, ms):
    """Gross with no tare on record: Save asks for the empty spool's weight.
    A label scanned instead goes to the scan path; the prompt stays up, empty,
    and the default mode as it was. The person's own tare then saves once. RED
    on 5b5a18e: the prompt's box had no capture, so the label's digits were
    saved as the tare (57 g), its 'D' set the default, and a second prompt
    stayed up."""
    page, open_ = weigh
    open_("gross", tare=None)
    press(page, "645", 200)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PROMPT_INPUT)
    later(page, 300)
    press(page, "ID:57", ms)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == ["ID:57"] and s["mode"] is None and s["prompts"] == 1, (ms, s)
    assert page.evaluate("(s) => document.querySelector(s).value", PROMPT_INPUT) == ""
    later(page, 600)
    press(page, "167", 200)
    page.wait_for_function("() => window.__saved.length === 1")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["tares"] == [167] and s["prompts"] == 0 and not s["open"], s


def test_a_persons_enter_in_the_tare_prompt_saves_once(weigh):
    """The person types the tare and presses Enter: the weigh is saved once,
    and no prompt is left. RED on 5b5a18e: the window's own Enter ran Save
    again first, so a second, empty prompt stayed up, and answering it saved
    the weigh a second time."""
    page, open_ = weigh
    open_("gross", tare=None)
    press(page, "645", 200)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PROMPT_INPUT)
    later(page, 600)
    press(page, "167", 200)
    page.wait_for_function("() => window.__saved.length === 1")
    page.wait_for_timeout(100)
    s = _seen(page)
    assert len(s["saved"]) == 1 and s["prompts"] == 0 and not s["open"], s


def test_escape_and_the_arrows_in_the_tare_prompt_are_the_prompts(weigh):
    """Escape in the prompt closes the prompt only: the window stays with its
    reading and the field has the focus again, and Save asks again. The arrows
    in the prompt's box leave the window's mode alone. RED on 5b5a18e: Escape
    cancelled the window and left the prompt up (answering it then saved the
    weigh that was cancelled), and an arrow switched the window's mode."""
    page, open_ = weigh
    open_("gross", tare=None)
    press(page, "645", 200)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PROMPT_INPUT)
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowLeft")
    assert _seen(page)["tab"] == "gross"
    page.keyboard.press("Escape")
    s = _seen(page)
    assert s["prompts"] == 0 and s["open"] and s["cancelled"] == 0 and s["value"] == "645", s
    assert page.evaluate("(s) => document.activeElement === document.querySelector(s)", INPUT)
    page.keyboard.press("Enter")
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PROMPT_INPUT)
    assert _seen(page)["prompts"] == 1


def test_a_label_split_by_the_focus_is_put_back_together(weigh):
    """A label whose first keys were still in the scan buffer when the field
    took the focus (its prefix and ':', or only its prefix) is finished in the
    field, and one whose field lost the focus mid-label is finished in the scan
    buffer. Each reaches the scan path whole, and nothing is saved. RED on
    5b5a18e: the field's half of the label was a weight ("57" saved), or a cut
    scan (":57", "7")."""
    page, open_ = weigh
    open_("gross")
    page.evaluate("() => { state.scanBuffer = 'ID:'; state.scanStartTime = Date.now(); }")
    press(page, "57", 5)
    page.wait_for_timeout(20)
    s = _seen(page)
    assert s["scans"] == ["ID:57"] and s["saved"] == [] and s["value"] == "" and s["buffer"] == "", s
    later(page, 3000)
    page.evaluate("() => { window.__scans = []; state.scanBuffer = 'ID'; state.scanStartTime = Date.now(); }")
    press(page, ":57", 5)
    page.wait_for_timeout(20)
    assert _seen(page)["scans"] == ["ID:57"]
    later(page, 3000)
    page.evaluate("() => { window.__scans = []; }")
    press(page, "ID:5", 5, enter=False)
    page.evaluate("() => document.getElementById('fcc-we-save').focus()")
    press(page, "7", 5)
    s = _seen(page)
    assert s["scans"] == ["ID:57"] and s["saved"] == [] and s["open"], s


def test_a_label_whose_enter_never_comes_leaves_the_reading_as_it_was(weigh):
    """A label scanned after the reading whose Enter never comes (a scanner
    that stalls 2 s or more before it, the accumulator's reset): the field
    never got the label's keys, so a person's Enter later saves the reading
    they typed. RED on 5b5a18e: the field held "64557", and that was saved."""
    page, open_ = weigh
    open_("gross")
    press(page, "645", 200, enter=False)
    later(page, 300)
    press(page, "ID:57", 5, enter=False)
    assert _seen(page)["value"] == "645"
    later(page, 2500)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__saved.length === 1")
    assert _seen(page)["saved"] == ["645"]


@pytest.mark.parametrize("then", ["Backspace", "pause"])
def test_a_persons_key_or_a_pause_drops_a_label_that_never_ended(weigh, then):
    """A label whose Enter never came (a scanner that lost it), then the
    person rubs out (Backspace) or simply waits past the accumulator's 2 s, and
    types their reading and Enter: the reading reaches the field and is saved,
    never swallowed as the rest of the label. Unpinned until it was written:
    without either rule, the reading went to the scan path glued to the label."""
    page, open_ = weigh
    open_("gross")
    press(page, "ID:5", 5, enter=False)
    if then == "Backspace":
        later(page, 300)
        page.keyboard.press("Backspace")
    else:
        later(page, 2500)
    press(page, "645", 200)
    page.wait_for_function("() => window.__saved.length === 1")
    s = _seen(page)
    assert s["saved"] == ["645"] and s["scans"] == [], (then, s)


def test_a_dialog_over_the_tare_prompt_answers_its_own_enter(weigh):
    """The prompt's keys are its own only while it is on top: with a dialog
    over it, an Enter is that dialog's, and the prompt saves nothing."""
    page, open_ = weigh
    open_("gross", tare=None)
    press(page, "645", 200)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PROMPT_INPUT)
    press(page, "167", 200, enter=False)
    page.evaluate("""() => window.mountOverlay({ id: 'fcc-probe-over', tier: 'confirm',
        content: '<div><button id="fcc-probe-btn">ok</button></div>' })""")
    page.locator("#fcc-probe-btn").focus()
    later(page, 700)
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["saved"] == [] and s["prompts"] == 1, s


def test_the_tare_prompts_buttons_answer_their_own_enter(weigh):
    """In the missing-tare prompt, a person's Enter on Cancel cancels the
    prompt (the window stays, nothing saved), and a label scanned with the
    focus on its Save button is the scan's (its keys went to the scan
    accumulator). RED on 5b5a18e: every Enter in the prompt was Save &
    Continue, and the window's own Enter ran Save a second time."""
    page, open_ = weigh
    open_("gross", tare=None)
    press(page, "645", 200)
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PROMPT_INPUT)
    page.locator(f"{PROMPT}-cancel").focus()
    later(page, 700)
    page.keyboard.press("Enter")
    s = _seen(page)
    assert s["prompts"] == 0 and s["open"] and s["saved"] == [] and s["cancelled"] == 0, s
    page.keyboard.press("Enter")
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=PROMPT_INPUT)
    page.locator(f"{PROMPT}-save").focus()
    later(page, 700)
    press(page, "ID:57", 5)
    s = _seen(page)
    assert s["scans"] == ["ID:57"] and s["prompts"] == 1 and s["saved"] == [], s


def test_a_persons_typing_then_a_pause_is_never_taken_for_a_scan(weigh):
    """A person types something a weight can't hold, quickly ("+50g" in
    Additive), stops, and presses Enter half a second later: the Enter is
    theirs. Their text stays in the field (it reads "Invalid input"), nothing
    goes to the scan path, and nothing is saved."""
    page, open_ = weigh
    open_("additive")
    press(page, "+50g", 30, pauses={4: 500})
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["saved"] == [] and s["scans"] == [] and s["value"] == "+50g" and s["open"], s
    assert "Invalid input" in page.evaluate("() => document.getElementById('fcc-we-warn').textContent")


@pytest.mark.parametrize("ms, pauses", [(5, {}), (40, {}), (250, {}), (2, {6: 450})])
def test_the_weigh_out_lists_weight_box_takes_a_label_at_any_speed(isolated_page, ms, pauses):
    """The weigh-out list's weight boxes (inv_weigh_out.js) are weight boxes
    too: the label reaches the scan path and the reading typed before it stays.
    RED on aecf901 at 40 ms a key (it allowed a whole label 150 ms), and on
    5b5a18e at 250 ms a key and for a burst scanner."""
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body>"
                     "<input class='weigh-input fcc-weight-box' id='w1'></body></html>")
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "inv_weigh_out.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate(FAKE_CLOCK)
    page.locator("#w1").focus()
    press(page, "645", 200, enter=False)
    later(page, 300)
    label = "ID:134" if pauses else "ID:57"
    press(page, label, ms, pauses=pauses)
    assert page.evaluate("() => [window.__scans.slice(), document.getElementById('w1').value]") == [[label], "645"]


def test_a_persons_reading_and_enter_still_save(weigh):
    """A reading typed by hand, by a fast typist too, and Enter saves it in
    every mode: the weight capture never takes digits, '.', '+' or '-'. Keys a
    person left in the scan buffer before the window opened don't take that
    Enter (only an Enter off the field asks whether it is a scan's), and leave
    with it (round 6: they stayed, to start the next scan)."""
    page, open_ = weigh
    for mode, reading in (("gross", "645.5"), ("net", "425"), ("additive", "-10"), ("set_used", "575")):
        page.evaluate("() => { state.scanBuffer = 'ab'; state.scanStartTime = Date.now() - 1000; }")
        open_(mode)
        press(page, reading, 30)
        page.wait_for_function("() => window.__saved.length === 1")
        assert _seen(page)["saved"] == [reading], mode
        # and the keys left in the scan buffer went with it: they'd start the next scan
        assert _seen(page)["buffer"] == "", mode
