"""A '/' in a scan still arriving is the scan's, however slow the scanner
(Group 57 review, round 3), hermetic.

Runs the REAL scan accumulator (the keydown block of
templates/components/scripts.html, lifted as it is), the REAL fab_drag.js (the
global search's '/') and the REAL overlay_mount.js, inv_core.js and
inv_stock.js, with the ⚠️ button's real markup, in `isolated_page` (a chromium
with no route to any network), so it RUNS under --offline. The keys are typed
on a fake clock (Date.now and performance.now), one every `ms`, so a scanner's
speed is exact whatever the machine's load.

The defect: a Prusament spool QR is a URL ending in '/'. isScanInFlight's
500 ms runs from a scan's FIRST key, and a slower scanner (about 12 ms a key or
more) is still typing the 45-character URL after it, so a late '/' read as a
person's. The Low stock reason dialog claimed it and emptied the scan buffer
(d1fcea3), and the scan's Enter then pressed the dialog's focused button: a
scan saved an exclusion, or "Include again" removed one. The list claimed it
too (its filter key) and opened a filament window, and fab_drag.js opened the
search.

Pinned, at every speed from 1 to 150 ms a key: the URL reaches processScan whole
and once; the dialog writes nothing and stays up; the search never opens; the
list opens no filament window and keeps its filter as it was. A person's lone
'/' (the buffer empty, or its last key over 500 ms ago) is still the dialog's,
the list's (its filter) and the page's (the search). RED on 2749590.

Round 4: round 3's rule measured the scanner's pause (the last key under 500 ms
ago), so a scanner that stalled half a second before the URL's last '/' still
saved an exclusion, and one before an earlier '/' cut the scan, opened a
filament window or the search. Two or more characters in the buffer are a scan
now however long it paused (enterIsAScan's rule). Pinned too: a stall of 600 ms
or 1.5 s before the last '/' or an earlier one, and a scanner sending bursts
with 450 or 700 ms between them, in every place; the boundary (two keys left
are a scan, one is a person's, two Spaces a button press left are nobody's
scan); and a '/' the dialog takes empties the buffer, so a stray key never
starts the next scan. RED on dd81587.

Round 5: two keys a person left (two stray letters, the '?' that opened and
closed the shortcut list) held the search, the list's filter and the dialog's
'/' off for 2 s, each '/' restarting it. A buffer is a scan now while it LOOKS
like one (a ':' or '/' in it, or "http" first), and every FCC label has its ':'
before any '/', so the boundary moved: keys a person left hold nothing off;
"https:" keeps its '/' however long the scanner paused, up to the accumulator's
2 s. The keys are typed as a scanner sends them (Shift down before each capital
and ':', and each key's keyup), and every test runs on the focused reason radio
too (the radio capture's, since the accumulator ignores a radio's keys): a
NumLock or dead key mid-label is skipped there, a one-key label and a 1.5 s
stall before the Enter are scans, and a reason picked with the mouse starts the
capture afresh. RED on 91e79e8.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from test_low_stock_glance_57_js import (BOOTSTRAP_HIDDEN, BODY, BTN, GLOBAL_CSS, MARK, MODULES, PAGE, PANEL,
                                         PRELUDE, REPORT, _answer, _button_markup)

HUB = Path(__file__).resolve().parent.parent
SCRIPTS = HUB / "templates" / "components" / "scripts.html"
URL = "https://prusament.com/spool/17705/5b1a183b26/"     # FCC's Prusament QR shape (logic.py)
SPEEDS = [1, 8, 13, 18, 26, 40, 60, 150]                   # ms a key: fast to a very slow Bluetooth scanner
SLASHES = [i for i, ch in enumerate(URL) if ch == "/"]     # where a stall can land before a '/'
DIALOG = "#fcc-low-stock-reason"


def _accumulator():
    """The scan accumulator, exactly as the page has it."""
    src = SCRIPTS.read_text(encoding="utf-8")
    a = src.index("state.scanStartTime = 0;")
    b = src.index("// L206", a)
    block = src[a:b]
    assert "processScan(state.scanBuffer" in block and "state.scanBuffer += e.key" in block, block[:300]
    return block


STUBS = r"""
window.__scans = [];
window.processScan = function (buf) { window.__scans.push(buf); };
window.__search = 0;
window.SearchEngine = { open: function () { window.__search += 1; } };
"""

# Typing on the page's fake clock: each key `ms` after the one before, Enter
# last; `pauses` adds a key's own extra wait before it ({index: ms}). `text` is
# a string, or a list of keys (a named key such as "NumLock" among them). Keys
# go as a scanner sends them: Shift down before a capital or a shifted symbol
# (':' among them; Shift+B and the wizard's Shift+E / Shift+C see a label's
# capitals as theirs), each key's keyup, then Shift's.
TYPE_JS = r"""([text, ms, enter, pauses]) => {
    if (!window.__fakeClock) {
        const base = Date.now(), pbase = performance.now();
        window.__T = 0;
        Date.now = () => base + window.__T;
        performance.now = () => pbase + window.__T;
        window.__fakeClock = true;
    }
    const keys = Array.isArray(text) ? text.slice() : [...text];
    if (enter) keys.push('Enter');
    const SHIFTED = '~!@#$%^&*()_+{}|:"<>?';
    const send = (t, type, key, shiftKey) =>
        t.dispatchEvent(new KeyboardEvent(type, { key, shiftKey, bubbles: true, cancelable: true }));
    keys.forEach((key, i) => {
        window.__T += ms + ((pauses && pauses[i]) || 0);
        const t = document.activeElement || document.body;
        const shift = key.length === 1 && (key !== key.toLowerCase() || SHIFTED.includes(key));
        if (shift) send(t, 'keydown', 'Shift', true);
        send(t, 'keydown', key, shift);
        const u = document.activeElement || document.body;      // where the key left the focus
        send(u, 'keyup', key, shift);
        if (shift) send(u, 'keyup', 'Shift', false);
    });
}"""


def _type(page, text, ms, enter=True, pauses=None):
    page.evaluate(TYPE_JS, [text, ms, enter, {str(k): v for k, v in (pauses or {}).items()}])


def _later(page, ms):
    """The fake clock moves on (no key)."""
    page.evaluate("(ms) => { window.__T += ms; }", ms)


@pytest.fixture
def scan_page(isolated_page):
    page = isolated_page
    page.set_content(PAGE.format(css=GLOBAL_CSS.read_text(encoding="utf-8") + BOOTSTRAP_HIDDEN,
                                 button=_button_markup()))
    page.add_script_tag(content=PRELUDE + STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "inv_stock.js", "fab_drag.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=_accumulator())        # last, as on the page (after fab_drag.js)
    page.evaluate("() => { window.__toasts = []; window.showToast = (m, t, ms) => window.__toasts.push({m, t, ms}); }")
    _type(page, "", 0, enter=False)                   # the fake clock, before anything is typed
    return page


def _open_list(page, report=None):
    page.evaluate("(a) => { window.__answers = a; }", [_answer(report or REPORT)])
    page.locator(BTN).click()
    page.wait_for_selector(PANEL)
    page.wait_for_function("(s) => document.querySelector(s).dataset.stockState === 'ready'", arg=BODY)


def _seen(page):
    return page.evaluate(f"""() => ({{ scans: window.__scans.slice(), sent: window.__sent.slice(),
        search: window.__search, opened: window.__opened.slice(),
        dialog: !!document.querySelector('{DIALOG}'), list: !!document.querySelector('{PANEL}'),
        filter: !!(document.activeElement && document.activeElement.hasAttribute('data-stock-filter')),
        filterValue: (document.querySelector('[data-stock-filter]') || {{}}).value,
        buffer: state.scanBuffer }})""")


def _reset(page):
    page.evaluate("() => { window.__scans = []; }")
    _later(page, 3000)


ROW = "#fcc-low-stock-overlay .fcc-stock-row.kb-active"
RADIO = f"{DIALOG} input[value='discontinued']"
PLACES = ["exclude", "dialog", "include", "radio", "list", "nothing"]


def _place(page, where):
    """Sets up `where` (the reason dialog with Exclude, its own text, Include
    again or a reason focused; the list with a row highlighted; nothing open)
    and returns what puts the focus back there before each scan."""
    if where == "nothing":
        return lambda: page.evaluate("() => document.activeElement && document.activeElement.blur()")
    if where == "include":
        report = copy.deepcopy(REPORT)
        row = report["low"].pop(0)
        row["excluded"] = MARK
        report["excluded"].append(row)
        _open_list(page, report)
        page.locator('[data-stock-tab="excluded"]').click()
    else:
        _open_list(page)
    if where == "list":
        return lambda: page.locator(ROW).focus()
    page.keyboard.press("Delete")
    page.wait_for_selector(DIALOG)
    if where != "include":
        page.locator(RADIO).check()
    if where == "dialog":
        return lambda: page.locator(f"{DIALOG} .fcc-stock-dlg-name").click()     # the focus on the dialog itself
    if where == "radio":
        return lambda: page.locator(RADIO).focus()
    target = f"{DIALOG} [data-stock-dlg-save]" if where == "exclude" else f"{DIALOG} [data-stock-dlg-include]"
    return lambda: page.locator(target).focus()


def _whole(page, where, why):
    """The URL reached the scan path whole and once, and nothing else happened
    where it was scanned."""
    s = _seen(page)
    assert s["scans"] == [URL] and s["search"] == 0, (where, why, s)
    if where in ("exclude", "dialog", "include", "radio"):
        assert s["sent"] == [] and s["dialog"] and s["buffer"] == "", (where, why, s)
    if where == "list":
        assert s["opened"] == [] and not s["filter"] and s["filterValue"] == "" and s["list"], (where, why, s)


@pytest.mark.parametrize("where", PLACES)
def test_a_slow_scanners_url_does_nothing_but_scan(scan_page, where):
    """A Prusament URL scanned at every speed onto the reason dialog (Exclude,
    Include again on an Excluded row, or the dialog itself), onto the list, or
    with nothing open: the scan goes to the scan path whole, nothing is written,
    the dialog stays, no filter, no filament window, no search. RED on 2749590
    from 13 ms a key: the dialog's POST /api/filament/164/stock_exclusion (or
    DELETE on Include again); in the list the late '/' focused the filter, the
    rest of the URL went into it, and its Enter opened #164's window; with
    nothing open it opened the search panel and was lost."""
    page = scan_page
    focus = _place(page, where)
    for ms in SPEEDS:
        focus()
        _type(page, URL, ms)
        _whole(page, where, ms)
        _reset(page)


@pytest.mark.parametrize("where", PLACES)
def test_a_scanner_that_stalls_keeps_its_scan_whole(scan_page, where):
    """Round 4: a scanner that stalled 500 ms or more before a '/' (a Bluetooth
    link's hiccup, or a busy page) had it claimed as a person's: before the
    URL's last '/', the claim emptied the buffer and the scan's Enter saved an
    exclusion; before an earlier one, it cut the scan, opened the filament
    window or the search. Before the last '/' and two earlier ones, after 600 ms
    and 1.5 s (the accumulator keeps a buffer for 2 s). RED on dd81587."""
    page = scan_page
    focus = _place(page, where)
    for at in (SLASHES[-1], SLASHES[-2], SLASHES[1]):
        for stall in (600, 1500):
            focus()
            _type(page, URL, 13, pauses={at: stall})
            _whole(page, where, (at, stall))
            _reset(page)


@pytest.mark.parametrize("where", PLACES)
def test_a_scanner_that_sends_bursts_keeps_its_scan_whole(scan_page, where):
    """A scanner that sends a few keys at a time: six keys 2 ms apart, then a
    gap of 450 ms (round 4's skeptic: whole on round 3's code) or 700 ms (cut
    there: the search opened twice and processScan got nothing)."""
    page = scan_page
    focus = _place(page, where)
    for gap in (450, 700):
        focus()
        _type(page, URL, 2, pauses={i: gap for i in range(6, len(URL), 6)})
        _whole(page, where, gap)
        _reset(page)


def test_keys_a_person_left_hold_nothing_off_a_scan_does(scan_page):
    """The boundary, with nothing open, 600 ms and 1.9 s after the last key
    (past the 500 ms a scan is in flight, inside the accumulator's 2 s). Keys a
    person pressed and left don't look like a scan, so a '/' is the person's: it
    opens the search and takes them out of the buffer (round 5: round 4 counted
    any two characters, so "ab" or the shortcut list's "??" held the search off
    for 2 s, each '/' restarting it). A buffer that looks like one (a ':' or '/'
    in it, or "http" first) keeps its '/' however long the scanner paused. A
    Space with nothing before it isn't kept at all."""
    page = scan_page
    for left, theirs in (("ab", True), ("a", True), ("  ", True), (" a", True), ("a b", True), ("??", True),
                         ("12", True), ("ID:", False), ("https:", False), ("http", False), ("LOC:LR", False),
                         ("https://prusament.com", False)):
        for pause in (600, 1900):
            page.evaluate("() => { window.clearScanBuffer(); window.__search = 0; }")
            _later(page, 3000)
            _type(page, left, 10, enter=False)
            _later(page, pause)
            _type(page, "/", 10, enter=False)
            s = _seen(page)
            if theirs:
                assert s["search"] == 1 and s["buffer"] == "", (left, pause, s)
            else:
                assert s["search"] == 0 and s["buffer"] == left + "/", (left, pause, s)


def test_a_space_a_button_left_never_starts_a_scan(scan_page):
    """Space pressed on a focused button, then a label 1.5 s later: the label
    arrives as it is ("LOC:LR-MDB-1", not " LOC:LR-MDB-1"), and it started when
    its own first key came, so it is still in flight 400 ms later. RED on
    91e79e8: the accumulator kept the space for 2 s and started the scan's
    500 ms from it."""
    page = scan_page
    page.evaluate("() => { const b = document.createElement('button'); b.id = 'probe-btn';"
                  " document.body.appendChild(b); b.focus(); }")
    _type(page, " ", 10, enter=False)
    assert _seen(page)["buffer"] == ""
    _later(page, 1500)
    _type(page, "LOC:LR", 13, enter=False)
    _later(page, 300)
    assert page.evaluate("() => window.isScanInFlight()") is True
    _type(page, "-MDB-1", 13)
    assert _seen(page)["scans"] == ["LOC:LR-MDB-1"]


def test_a_scan_onto_a_reason_with_a_scanners_other_keys_arrives_whole(scan_page):
    """Onto the focused reason (a radio: the radio capture's keys, not the
    accumulator's), a label carrying a key that isn't a character: a NumLock
    (a keypad-emulating scanner), a dead key (an international layout) or an
    unidentified key. They are skipped, as the accumulator skips them, and as
    Shift before each capital is: the label reaches the scan path whole and
    nothing is saved. RED on 91e79e8: any such key started the capture afresh,
    and "LOC:LR-MDB-" + NumLock + "1" arrived as "1"."""
    page = scan_page
    focus = _place(page, "radio")
    for keys, want in ((list("LOC:LR-MDB-") + ["NumLock", "1"], "LOC:LR-MDB-1"),
                       (list("ID:5") + ["Dead", "7"], "ID:57"),
                       (list("LOC:XL") + ["Unidentified"] + list("-1"), "LOC:XL-1")):
        for ms in (1, 13, 60, 150):
            focus()
            _type(page, keys, ms)
            s = _seen(page)
            assert s["scans"] == [want] and s["sent"] == [] and s["dialog"], (want, ms, s)
            _reset(page)


def test_a_one_key_label_and_a_pause_before_the_enter_are_scans_on_a_reason(scan_page):
    """The radio capture's time rules, on the scanner's side: a one-key label
    ("7", an old bare spool id) whose Enter comes 250 or 450 ms after it, a
    label whose scanner paused 1.5 s before its Enter (under the accumulator's
    2 s), and a label at 150 ms a key are scans, and nothing is saved.
    Unpinned until round 5: a 100 ms rule for the lone key, the Enter or the
    gap between keys passed every test."""
    page = scan_page
    focus = _place(page, "radio")
    for keys, ms, pauses in (("7", 250, None), ("7", 450, None), ("57", 13, {2: 1500}),
                             ("LOC:LR-MDB-1", 13, {12: 1500}), ("LOC:LR-MDB-1", 150, None)):
        focus()
        _type(page, keys, ms, pauses=pauses)
        s = _seen(page)
        assert s["scans"] == [keys] and s["sent"] == [] and s["dialog"], (keys, ms, pauses, s)
        _reset(page)


def test_a_reason_picked_with_the_mouse_starts_the_capture_afresh(scan_page):
    """Two keys a person pressed on a reason ('/' from habit, twice), then
    another reason picked with the mouse and Enter 400 ms later: the Enter is
    theirs and saves, and nothing goes to the scan path (a scanner never
    clicks). RED on 91e79e8: the two keys were scanned and nothing was saved."""
    page = scan_page
    focus = _place(page, "radio")
    focus()
    _type(page, "//", 300, enter=False)
    page.locator(f"{DIALOG} input[value='cant_find']").click()
    _type(page, "", 400)
    page.wait_for_function("() => window.__sent.length === 1")
    assert _seen(page)["scans"] == []


def test_a_slash_the_dialog_takes_empties_the_buffer(scan_page):
    """A key a person pressed and left on the dialog, then their '/' 600 ms
    later: the dialog takes the '/' and empties the buffer, so the stray key
    doesn't start the next scan ("xLOC:LR-MDB-1", an unknown code). Unpinned
    until round 4 (the buffer was empty before the '/' in every test)."""
    page = scan_page
    focus = _place(page, "exclude")
    focus()
    _type(page, "x", 10, enter=False)
    _later(page, 600)
    _type(page, "/", 10, enter=False)
    s = _seen(page)
    assert s["dialog"] and s["search"] == 0 and s["buffer"] == "", s
    _type(page, "LOC:LR-MDB-1", 13)
    s = _seen(page)
    assert s["scans"] == ["LOC:LR-MDB-1"] and s["sent"] == [] and s["dialog"], s


def test_a_persons_slash_is_still_theirs(scan_page):
    """The buffer empty, or its last key over 500 ms ago (a key pressed and
    left): the page's '/' opens the search, the list's focuses its filter, the
    dialog's keeps the search away; none goes into the scan buffer."""
    page = scan_page
    _type(page, "/", 10, enter=False)
    assert _seen(page)["search"] == 1 and _seen(page)["buffer"] == ""
    _later(page, 3000)
    _type(page, "x", 10, enter=False)                    # a key pressed and left
    _later(page, 600)
    _type(page, "/", 10, enter=False)
    assert _seen(page)["search"] == 2, _seen(page)
    page.evaluate("() => window.clearScanBuffer()")
    _later(page, 3000)

    _open_list(page)
    page.locator("#fcc-low-stock-overlay .fcc-stock-row.kb-active").focus()
    _type(page, "x", 10, enter=False)
    _later(page, 600)
    _type(page, "/", 10, enter=False)
    s = _seen(page)
    assert s["filter"] and s["search"] == 2 and s["buffer"] == "", s

    page.locator("#fcc-low-stock-overlay .fcc-stock-row.kb-active").focus()
    page.keyboard.press("Delete")
    page.wait_for_selector(DIALOG)
    page.locator(f"{DIALOG} [data-stock-dlg-save]").focus()
    _later(page, 3000)
    _type(page, "/", 10, enter=False)
    s = _seen(page)
    assert s["dialog"] and s["search"] == 2 and s["buffer"] == "" and s["sent"] == [], s
