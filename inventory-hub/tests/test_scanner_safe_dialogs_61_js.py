"""Group 61: Scanner-Safe Dialogs (2026-10-29), hermetic.

Five older dialogs answered a scan's Enter as a person's (found by the Group 57
review, round 5, on dev, read-only). Runs the REAL scan accumulator
(scripts.html's keydown block) with the REAL overlay_mount.js, inv_core.js,
ui_builder.js, inv_details.js, inv_cmd.js (processScan and its open
questions), inv_loc_mgr.js, duplicate_picker.js, draggable_pill.js and
inv_wizard.js, in `isolated_page` (no route to any network), so it RUNS under
--offline. Keys go on a fake clock (test_slow_scan_slash_js.TYPE_JS), so a
scanner's speed is exact; the location editor's boxes, which need real text,
are typed with the real keyboard; and a Space a scan carries is a real key
where a button's own press is what is tested (a synthetic key presses nothing).

Pinned:
- the legacy-ID duplicate picker (Derek, 2026-10-29: hold until answered, and
  a listed spool's own label picks it): a scan presses no button; a listed
  spool's ID:<n> (or SPL:<n>, or the bare number) picks that spool, an ID:
  label with the scan's own source and the others as no label scan (only a
  scanned ID: label verifies a printed label); the legacy label read again is
  named as itself; any other scan is refused with a note, nothing joins the
  buffer and nothing is left in the scan buffer; CMD:CANCEL cancels; a
  person's Enter, clicks and a jump in the list ("#135") work as before, and
  "Use selected" is no label scan (it sent 'barcode', so the server marked the
  spool's label printed and the spool left the label backlog);
- the location editor: on a dropdown, keys that match the start of none of its
  options are a scan at any speed (a person's jump, "dr" or a "3D ..." custom
  type, still saves), and a scan's letters that moved it are put back; on a
  button, a scan's Enter and a Space inside a scan press nothing; in a box, a
  whole FCC label at the end of the keys typed (from the first of them or
  after a pause), any burst, or digits faster than a person types go to the
  scan path, and the box gets back its text and caret from before the scan's
  first key, wherever the caret was; a name typed at a person's pace, or
  stored, stays a name;
- the parent tree picker: a scan picks no node (its Enter picked the
  highlighted parent and threw the scan away); a pickable location's own label
  picks it as the parent, another place's is refused with a note, any other
  scan too; a person's Enter still picks;
- a focused wizard section header, the floating search pill and the filament
  editor's "Close without saving?": a scan's Enter, and a Space inside a scan,
  press nothing, and the scan reaches the scan path; a person's keys work;
- a refused scan's text is escaped in the Activity Log, which draws it as HTML.
RED before Group 61, on ca1a701, or before its review's fixes, on a95163c
(each test says how).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_slow_scan_slash_js import TYPE_JS, _accumulator

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
SPEEDS = [1, 26, 60, 150]

STUBS = r"""
window.registerShortcut = function () {};
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.__ids = [];          // /api/identify_scan's requests: {text, source}
window.__logs = [];         // /api/log_event's lines (the Activity Log draws them as HTML)
window.__answers = {};      // a scan's text -> its answer
window.__toggles = 0;       // the wizard section's Bootstrap Collapse toggles
// (show / hide: the wizard's Shift+E / Shift+C, which the C of "LOC:" from a
// slow scanner still reaches, leaving the scan whole: CLAUDE.md's keyboard order)
window.bootstrap = { Collapse: { getOrCreateInstance: function () {
    return { toggle: function () { window.__toggles += 1; }, show: function () {}, hide: function () {} }; } } };
window.fetch = function (url, opts) {
    url = String(url);
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    let ans = { status: 'success', success: true };
    if (url.indexOf('/api/log_event') !== -1) window.__logs.push(body.msg);
    if (url.indexOf('/api/identify_scan') !== -1) {
        window.__ids.push({ text: body.text, source: body.source });
        const s = /^(?:ID:)?(\d+)$/.exec(String(body.text).toUpperCase());
        ans = window.__answers[body.text] || (s
            ? { type: 'spool', id: Number(s[1]), display: 'Spool #' + s[1], color: '888888', remaining_weight: 500 }
            : { type: 'error', msg: 'Unknown Code' });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ans),
                             text: () => Promise.resolve(JSON.stringify(ans)) });
};
window.__si = window.setInterval; window.setInterval = () => 0;   // inv_cmd.js's 2 s buffer poll: off
"""

# The location editor (#locModal: its boxes, Max Spools a number box as on the
# page, the Type and Parent selects with a custom type and a parent that start
# with a digit, a Cancel), the filament editor the close question mounts in, a
# wizard section and its header, and the floating search pill; all there
# before the modules load, as on the page (inv_loc_mgr.js and inv_wizard.js
# wire theirs at load).
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>.modal{display:none}.modal.show{display:block}</style>
</head><body>
<div id="locModal" class="modal show"><div class="modal-content">
  <input id="edit-name" type="text"><input id="edit-id" type="text"><input id="edit-max" type="number" value="1">
  <select id="edit-type"><option>Room</option><option>Dryer Box</option><option>Shelf</option><option>Printer</option>
    <option>3D Printer Shelf</option></select>
  <select id="edit-parent"><option value="__auto__">Auto</option><option value="__none__">Top level</option>
    <option value="FL2">2nd Floor (FL2)</option><option value="CR">Computer Room (CR)</option>
    <option value="GARAGE">Garage (GARAGE)</option><option value="LR">Living Room (LR)</option></select>
  <button id="loc-cancel" type="button">Cancel</button>
</div></div>
<div id="editFilamentModal" class="modal show"><div class="modal-dialog"><div class="modal-content">filament editor</div></div></div>
<div id="wizardModal" class="modal show">
  <button type="button" class="fcc-wiz-section-toggle" data-bs-target="#wiz-spool-extras-panel">Extras</button>
  <div id="wiz-spool-extras-panel" class="collapse"></div>
</div>
<button id="fcc-test-pill" type="button">🔍</button>
</body></html>"""

LEGACY = {"type": "ambiguous", "legacy_id": "120", "candidates": [
    {"id": 134, "remaining_weight": 800, "location": "LR-MDB-1", "archived": False, "filament_id": 7,
     "filament_name": "Galaxy Black", "material": "PLA", "vendor_name": "Prusament", "display": "#134"},
    {"id": 135, "remaining_weight": 0, "location": "", "archived": False, "filament_id": 7,
     "filament_name": "Galaxy Black", "material": "PLA", "vendor_name": "Prusament", "display": "#135"}]}

LOC_ROWS = [{"LocationID": "LR", "Name": "Living Room", "Type": "Room"},
            {"LocationID": "GARAGE", "Name": "Garage", "Type": "Room"},
            {"LocationID": "LR-MDB-1", "Name": "Dryer", "Type": "Dryer Box"}]


@pytest.fixture
def page61(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "inv_details.js", "inv_cmd.js",
                 "inv_loc_mgr.js", "duplicate_picker.js", "draggable_pill.js", "inv_wizard.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content="window.setInterval = window.__si;")
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate("""() => {
        window.__saves = 0; window.saveLocation = () => { window.__saves += 1; };
        window.__taps = 0;
        window.__clicks = { header: 0, pill: 0, cancel: 0 };
        document.querySelector('.fcc-wiz-section-toggle').addEventListener('click', () => { window.__clicks.header += 1; });
        document.getElementById('fcc-test-pill').addEventListener('click', () => { window.__clicks.pill += 1; });
        document.getElementById('loc-cancel').addEventListener('click', () => { window.__clicks.cancel += 1; });
        window.makeDraggablePill(document.getElementById('fcc-test-pill'),
            { key: 'fcc.test.pill', defaultPos: () => ({ left: 10, bottom: 10 }), onTap: () => { window.__taps += 1; } });
    }""")
    return page


def _clock(page):
    """The fake clock, before anything is typed with it."""
    page.evaluate(TYPE_JS, ["", 0, False, {}])


def _type(page, text, ms, enter=True):
    page.evaluate(TYPE_JS, [text, ms, enter, {}])


# Typing INTO a text box on the fake clock, as a browser does it: each key's
# keydown (Shift down first for a capital or a shifted symbol, as a scanner
# sends them), then, unless a handler prevented it, the character put in at
# the caret, over the selection, and its input event. Backspace takes out the
# selection or the character before the caret; ArrowLeft / ArrowRight move the
# caret; "Ctrl+A" selects everything, another "Ctrl+<key>" changes nothing (a
# copy); Enter last (its keydown). `pauses`: {index: extra ms before that key}.
TYPE_BOX_JS = r"""([text, ms, enter, pauses]) => {
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
    keys.forEach((key, i) => {
        window.__T += ms + ((pauses && pauses[String(i)]) || 0);
        const t = document.activeElement || document.body;
        const ctrl = /^Ctrl\+.$/.test(key);
        const k = ctrl ? key.slice(5).toLowerCase() : key;
        const shift = !ctrl && k.length === 1 && (k !== k.toLowerCase() || SHIFTED.includes(k));
        if (shift) t.dispatchEvent(new KeyboardEvent('keydown', { key: 'Shift', shiftKey: true, bubbles: true, cancelable: true }));
        const go = t.dispatchEvent(new KeyboardEvent('keydown', { key: k, ctrlKey: ctrl, shiftKey: shift, bubbles: true, cancelable: true }));
        if (go && t.tagName === 'INPUT' && t.type === 'text' && !t.readOnly) {
            const s0 = t.selectionStart, s1 = t.selectionEnd;
            if (ctrl) {
                if (k === 'a') t.select();
            } else if (k === 'ArrowLeft') {
                t.setSelectionRange(Math.max(0, s0 - 1), Math.max(0, s0 - 1));
            } else if (k === 'ArrowRight') {
                t.setSelectionRange(Math.min(t.value.length, s1 + 1), Math.min(t.value.length, s1 + 1));
            } else if (k === 'Backspace') {
                if (s0 !== s1) t.setRangeText('', s0, s1, 'end');
                else if (s0 > 0) t.setRangeText('', s0 - 1, s0, 'end');
                t.dispatchEvent(new Event('input', { bubbles: true }));
            } else if (k.length === 1) {
                t.setRangeText(k, s0, s1, 'end');
                t.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
        t.dispatchEvent(new KeyboardEvent('keyup', { key: k, bubbles: true }));
        if (shift) t.dispatchEvent(new KeyboardEvent('keyup', { key: 'Shift', bubbles: true }));
    });
}"""


def _type_box(page, text, ms, enter=True, pauses=None):
    page.evaluate(TYPE_BOX_JS, [text, ms, enter, {str(k): v for k, v in (pauses or {}).items()}])


def _later(page, ms):
    """The fake clock moves on (no key)."""
    page.evaluate("(ms) => { window.__T += ms; }", ms)


def _ids(page):
    return page.evaluate("() => window.__ids.map((r) => [r.text, r.source])")


def _buffer(page):
    return page.evaluate("() => state.scanBuffer")


def _toasts(page):
    """The toasts on screen, [type, text] (inv_core.js's showToast)."""
    return page.evaluate("""() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))
        .map((e) => [e.className.replace('toast-msg toast-', ''), e.innerText])""")


# --- 61.1 the legacy-ID duplicate picker ------------------------------------------

def _open_picker(page, choose=None):
    """A legacy label two spools share, scanned: the real scan path opens it.
    `choose`: a spool picked in its list first (it starts with none, and "Use
    selected" with none closes it), the focus back on "Use selected"."""
    page.evaluate("(a) => { window.__answers['LEG:120'] = a; window.processScan('LEG:120', 'barcode'); }", LEGACY)
    page.wait_for_selector("#fcc-legacy-picker-overlay", timeout=5000)
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'fcc-legacy-picker-use'")
    if choose is not None:
        page.select_option("#fcc-legacy-picker-sel", str(choose))
        page.focus("#fcc-legacy-picker-use")


def _picker(page):
    return page.evaluate("""() => ({ open: !!document.getElementById('fcc-legacy-picker-overlay'),
        flash: (document.getElementById('fcc-legacy-picker-flash') || {}).textContent || '',
        held: state.heldSpools.map((s) => s.id) })""")


@pytest.mark.parametrize("ms", SPEEDS)
def test_a_scan_while_the_picker_is_open_presses_nothing(page61, ms):
    """With #134 picked in its list. RED on ca1a701: the scan's Enter pressed
    "Use selected": #134 joined the buffer (as a 'barcode' ID: scan), the
    picker closed, and the scan's own text stayed in the scan buffer (glued to
    the next scan)."""
    _clock(page61)
    _open_picker(page61, choose=134)
    _type(page61, "LOC:LR-MDB-1", ms)
    p = _picker(page61)
    assert p["open"] and p["held"] == [], p
    assert "Answer the question on screen first" in p["flash"], p
    assert _ids(page61) == [["LEG:120", "barcode"]], _ids(page61)
    assert _buffer(page61) == ""
    assert any(t == "warning" and "Answer the question on screen first" in m for t, m in _toasts(page61)), (
        "the refusal is said in a toast too", _toasts(page61))


@pytest.mark.parametrize("label", ["ID:135", "SPL:135", "135"])
@pytest.mark.parametrize("ms", [1, 60])
def test_a_listed_spools_own_label_picks_it(page61, label, ms):
    """An ID: label keeps the scan's own source: scanned at scanner speed it
    verifies the spool's printed label (the server's rule), slower it doesn't.
    An SPL: label or a bare number never does, as outside the picker (Group 61
    review: in the picker they went out as a 'barcode' ID: scan and verified
    it). RED on ca1a701: the Enter picked the selected #134."""
    _clock(page61)
    _open_picker(page61)
    _type(page61, label, ms)
    page61.wait_for_function("() => window.__ids.length === 2")
    want = "barcode" if (ms == 1 and label == "ID:135") else "keyboard"
    assert _ids(page61) == [["LEG:120", "barcode"], ["ID:135", want]], _ids(page61)
    page61.wait_for_function("() => state.heldSpools.length === 1")
    assert _picker(page61)["held"] == [135] and not _picker(page61)["open"]


def test_a_key_left_in_front_of_a_listed_spools_label_still_picks_it(page61):
    """A person's stray key glued in front ("xID:135"): still that spool's label,
    picked, though never as a scanned ID: label. RED on a95163c: it went out as
    a 'barcode' ID: scan, which verifies the spool's printed label."""
    _clock(page61)
    _open_picker(page61)
    _type(page61, "xID:135", 1)
    page61.wait_for_function("() => window.__ids.length === 2")
    assert _ids(page61)[1] == ["ID:135", "keyboard"], _ids(page61)


def test_a_spool_not_on_the_list_is_refused(page61):
    _clock(page61)
    _open_picker(page61)
    _type(page61, "ID:999", 26)
    p = _picker(page61)
    assert p["open"] and p["held"] == [] and "#999 isn't one of the spools listed" in p["flash"], p
    assert _ids(page61) == [["LEG:120", "barcode"]]


def test_scan_to_cancel_cancels_it(page61):
    """Nothing of the scan is left in the scan buffer (on ca1a701 the old Enter
    closed the picker too, but "CMD:CANCEL" stayed there, glued to the next
    scan)."""
    _clock(page61)
    _open_picker(page61)
    _type(page61, "CMD:CANCEL", 26)
    p = _picker(page61)
    assert not p["open"] and p["held"] == [], p
    assert _ids(page61) == [["LEG:120", "barcode"]] and _buffer(page61) == ""


@pytest.mark.parametrize("typed", ["#135", "#13"])
def test_a_persons_jump_in_the_list_then_enter_picks_that_spool(page61, typed):
    """Every option starts with its spool's number, so a person types it to
    jump there (real keys: the browser's own typeahead moves the list; "#13"
    is the start of both, and the spool the list shows is the one picked).
    RED on a95163c (Group 61 review): the Enter was taken as a scan of "#135"
    and refused, with a 7 s warning, though they had just picked one."""
    _open_picker(page61)
    page61.focus("#fcc-legacy-picker-sel")
    page61.keyboard.type(typed, delay=120)
    shown = int(page61.input_value("#fcc-legacy-picker-sel"))
    assert shown == 135 if typed == "#135" else shown in (134, 135), shown
    page61.keyboard.press("Enter")
    page61.wait_for_function("() => window.__ids.length === 2", timeout=5000)
    assert _ids(page61)[1] == [f"ID:{shown}", "keyboard"], _ids(page61)
    page61.wait_for_function("() => state.heldSpools.length === 1")
    assert _picker(page61)["held"] == [shown] and not _picker(page61)["open"]


def test_a_spools_number_typed_on_a_button_picks_it(page61):
    """"#135" typed with a button focused reaches the question as a scan, and
    is that spool's number. RED on a95163c: refused (no pattern took a '#')."""
    _clock(page61)
    _open_picker(page61)
    _type(page61, "#135", 120)
    page61.wait_for_function("() => window.__ids.length === 2")
    assert _ids(page61)[1] == ["ID:135", "keyboard"], _ids(page61)


@pytest.mark.parametrize("label", ["120", "LEG:120"])
def test_the_legacy_label_read_again_is_named_as_itself(page61, label):
    """A scanner's second read of the legacy label that opened the picker. RED
    on a95163c (Group 61 review): the bare number was called a spool ("#120
    isn't one of the spools listed"), though 120 is the legacy id on screen."""
    _clock(page61)
    _open_picker(page61)
    _type(page61, label, 1)
    p = _picker(page61)
    assert p["open"] and p["held"] == [], p
    assert "That is legacy label 120, which this question is about" in p["flash"], p
    assert _ids(page61) == [["LEG:120", "barcode"]] and _buffer(page61) == ""


def test_use_selected_is_no_label_scan(page61):
    """RED on ca1a701: the pick went to the scan path as a 'barcode' ID: scan,
    and the server marked #134's label printed and verified (it left the label
    backlog), though the picker is there because #134 has no label of its own."""
    _open_picker(page61, choose=134)
    page61.click("#fcc-legacy-picker-use")
    page61.wait_for_function("() => window.__ids.length === 2")
    assert _ids(page61)[1] == ["ID:134", "keyboard"], _ids(page61)


def test_a_persons_enter_still_answers_the_focused_button(page61):
    _clock(page61)
    _open_picker(page61, choose=134)
    _type(page61, "", 0)                                   # Enter on "Use selected"
    page61.wait_for_function("() => window.__ids.length === 2")
    assert _ids(page61)[1] == ["ID:134", "keyboard"] and not _picker(page61)["open"]
    _open_picker(page61)
    page61.focus("#fcc-legacy-picker-cancel")
    _type(page61, "", 0)                                   # Enter on Cancel
    assert not _picker(page61)["open"] and len(_ids(page61)) == 3


def test_the_question_goes_when_the_picker_closes(page61):
    """Cancelled, it holds no scan off: the next one acts."""
    _clock(page61)
    _open_picker(page61)
    page61.click("#fcc-legacy-picker-cancel")
    _type(page61, "ID:57", 26)
    page61.wait_for_function("() => window.__ids.length === 2")
    assert _ids(page61)[1][0] == "ID:57"


# --- 61.2 the location editor -----------------------------------------------------

@pytest.mark.parametrize("label", ["57", "1024"])
@pytest.mark.parametrize("ms", SPEEDS)
def test_digits_on_the_type_select_are_a_scan(page61, label, ms):
    """No Type starts with these digits. RED on ca1a701 (all but a 4-digit
    label at scanner speed, a burst): the Enter saved the location, and the
    digits went nowhere."""
    _clock(page61)
    page61.focus("#edit-type")
    _type(page61, label, ms)
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61)[0][0] == label


@pytest.mark.parametrize("typed", ["dr", "rr"])
def test_a_persons_typeahead_and_enter_still_save(page61, typed):
    """46.2's design: "dr" then Enter on the Type select saves (the start of
    "Dryer Box"); so does one letter again and again ("rr"), which steps
    through the options starting with it."""
    _clock(page61)
    page61.focus("#edit-type")
    _type(page61, typed, 220)
    assert page61.evaluate("() => window.__saves") == 1
    assert _ids(page61) == [] and _buffer(page61) == ""


@pytest.mark.parametrize("select, key, want", [
    ("#edit-type", "3", "3D Printer Shelf"),                    # a custom type
    ("#edit-parent", "2", "FL2"),                               # a parent, "2nd Floor (FL2)"
])
def test_a_persons_digit_jump_on_a_dropdown_still_saves(page61, select, key, want):
    """A custom type, or a parent's name, can start with a digit; the person
    types it to jump there (real keys: the browser's own typeahead), then
    Enter. RED on a95163c (Group 61 review): digits alone were a scan on every
    dropdown, so the form wasn't saved and that spool joined the buffer."""
    page61.focus(select)
    page61.keyboard.press(key)
    page61.wait_for_timeout(300)
    page61.keyboard.press("Enter")
    assert page61.evaluate("() => window.__saves") == 1
    assert page61.input_value(select) == want
    assert _ids(page61) == [] and _buffer(page61) == ""


def test_a_scans_letters_on_a_dropdown_are_put_back(page61):
    """Real keys, so the browser's typeahead moves the dropdown as it does on
    the page. RED on a95163c (and before Group 61): a location label at
    scanner speed moved the Parent to the first place starting with L, and an
    old label with no prefix ("PM-DB-1"), slower, set the Type to Printer and
    saved the location."""
    page61.select_option("#edit-parent", "GARAGE")
    page61.evaluate("""() => { window.__parentChanges = []; const p = document.getElementById('edit-parent');
        p.addEventListener('change', () => window.__parentChanges.push(p.value)); }""")
    page61.focus("#edit-parent")
    page61.keyboard.type("LOC:CR", delay=5)
    page61.keyboard.press("Enter")
    page61.wait_for_function("() => window.__ids.length === 1", timeout=5000)
    assert _ids(page61)[0][0] == "LOC:CR"
    assert page61.input_value("#edit-parent") == "GARAGE"
    # Put back with a change event, as the breadcrumb (and a suggested id) follow it.
    assert page61.evaluate("() => window.__parentChanges[window.__parentChanges.length - 1]") == "GARAGE"
    assert any(t == "info" and 'Parent is back to "Garage (GARAGE)"' in m for t, m in _toasts(page61)), _toasts(page61)
    page61.select_option("#edit-type", "Room")
    page61.focus("#edit-type")
    page61.keyboard.type("PM-DB-1", delay=60)
    page61.keyboard.press("Enter")
    page61.wait_for_function("() => window.__ids.length === 2", timeout=5000)
    assert _ids(page61)[1][0] == "PM-DB-1"
    assert page61.input_value("#edit-type") == "Room"
    assert page61.evaluate("() => window.__saves") == 0


def test_a_slower_scan_on_an_editor_button_is_a_scan(page61):
    """RED on a95163c: an old label with no prefix, typed slower than a burst
    with a button focused, pressed it (Cancel closed the editor, Save saved
    it): only digits or a ':' or '/' counted as a scan there."""
    _clock(page61)
    page61.focus("#loc-cancel")
    _type(page61, "PM-DB-1", 60)
    assert page61.evaluate("() => window.__clicks.cancel") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [["PM-DB-1", "keyboard"]]


def test_a_persons_enter_on_an_editor_button_presses_it(page61):
    """46.2's design: Enter on a button presses it, and a key a person left a
    second before goes with it, never to the scan path."""
    _clock(page61)
    page61.focus("#loc-cancel")
    _type(page61, "t", 0, enter=False)
    _later(page61, 1000)
    _type(page61, "", 0)
    assert page61.evaluate("() => window.__clicks.cancel") == 1
    assert _ids(page61) == [] and _buffer(page61) == ""


@pytest.mark.parametrize("ms", [1, 150])
def test_a_space_inside_a_scan_presses_no_editor_button(page61, ms):
    """A LocationID may hold a Space ("LOC:GARAGE SHELF"): the real Space key
    presses nothing, and the scan arrives whole. RED on a95163c (and before
    Group 61): it clicked the focused Cancel mid-scan (the editor closed, its
    edits lost)."""
    _clock(page61)
    page61.focus("#loc-cancel")
    _type(page61, "LOC:GARAGE", ms, enter=False)
    page61.keyboard.press(" ")
    page61.wait_for_timeout(50)
    assert page61.evaluate("() => window.__clicks.cancel") == 0, "the Space clicked Cancel"
    _type(page61, "SHELF", ms)
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61)[0][0] == "LOC:GARAGE SHELF"
    assert page61.evaluate("() => window.__clicks.cancel") == 0


def _name(page, value, select=True, caret=None):
    """The Name box holding `value`, focused: all of it selected (as the editor
    opens it), or the caret at `caret`, or at its end."""
    page.evaluate("""([v, sel, at]) => { const n = document.getElementById('edit-name'); n.value = v; n.focus();
        if (at != null) n.setSelectionRange(at, at); else if (sel) n.select(); else n.setSelectionRange(v.length, v.length); }""",
                  [value, select, caret])


def _box(page, sel="#edit-name"):
    """A box's [text, selectionStart, selectionEnd]."""
    return page.evaluate("(s) => { const b = document.querySelector(s); return [b.value, b.selectionStart, b.selectionEnd]; }", sel)


@pytest.mark.parametrize("text, want", [
    ("LOC:LR-MDB-1", True),
    ("loc:lr-mdb-1", True),                                     # Caps Lock, or a lower-case scanner
    ("LOC:GARAGE SHELF", True),                                 # an id may hold a Space
    ("ID:57", True),
    ("LEGACY:7", True),
    ("https://prusament.com/spool/1/ab/", True),
    ("Shelf 3LOC:LR-MDB-1", False),                             # where a label starts is the capture's question
    ("Shelf: top", False),
    ("Grid:2", False),                                          # "ID" inside a word
    ("LOC: here", False),                                       # a blank after the ':'
    ("Bin 3/4", False),
    ("My shelf", False),
])
def test_what_reads_as_one_whole_label(page61, text, want):
    assert page61.evaluate("(t) => window.fccIsLabel(t)", text) is want, text


@pytest.mark.parametrize("ms", [60, 150, 400])
def test_a_label_typed_over_the_name_is_a_scan(page61, ms):
    """The editor selects the name as it opens, so a scan replaces it. RED on
    ca1a701: typed slower than the field capture's burst (3 keys inside 150 ms),
    the label was saved as the location's name."""
    _name(page61, "Shelf 3")
    page61.keyboard.type("LOC:LR-MDB-1", delay=ms)
    page61.keyboard.press("Enter")
    assert page61.evaluate("() => window.__saves") == 0
    assert page61.input_value("#edit-name") == "Shelf 3"
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [["LOC:LR-MDB-1", "keyboard"]]


def test_a_label_typed_after_the_name_keeps_the_name(page61):
    _name(page61, "Shelf 3", select=False)
    page61.keyboard.type("ID:57", delay=80)
    page61.keyboard.press("Enter")
    assert page61.evaluate("() => window.__saves") == 0 and page61.input_value("#edit-name") == "Shelf 3"
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61)[0][0] == "ID:57"


@pytest.mark.parametrize("name", ["Shelf: top", "Grid:2", "Bin 3/4"])
def test_a_name_with_a_colon_stays_a_name(page61, name):
    _name(page61, "")
    page61.keyboard.type(name, delay=60)
    page61.keyboard.press("Enter")
    assert page61.evaluate("() => window.__saves") == 1 and page61.input_value("#edit-name") == name
    assert _ids(page61) == []


# Judged on the keys typed, not the box's text (Group 61 review). The boxes
# below are typed on the fake clock, the characters put in at the caret as a
# browser does (TYPE_BOX_JS), so each speed is exact.

@pytest.mark.parametrize("label, ms, caret", [
    ("ID:5", 60, 19), ("ID:5", 150, 19),                        # just before the name's last "1"
    ("LOC:LR-MDB-1", 20, 19), ("LOC:LR-MDB-1", 60, 0),          # ... and at its start
])
def test_a_label_typed_inside_the_name_takes_none_of_it(page61, label, ms, caret):
    """The person clicked inside the name to fix it, and a slower scanner read
    a label there. RED on a95163c: the box's text from the label to its end
    was read as the label ("ID:51", so spool #51 joined the buffer though #5
    was scanned; "LOC:LR-MDB-1Computer Room Cart 1"), and the name lost it."""
    _clock(page61)
    _name(page61, "Computer Room Cart 1", caret=caret)
    _type_box(page61, label, ms)
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [[label, "keyboard"]], _ids(page61)
    assert _box(page61) == ["Computer Room Cart 1", caret, caret]


@pytest.mark.parametrize("ms", [26, 60])
def test_a_label_typed_after_a_name_ending_in_a_letter_is_a_scan(page61, ms):
    """The caret at the end of a name that ends in a letter (17 of dev's 83).
    RED on a95163c (and before Group 61): saved as the name, "Living
    RoomLOC:LR-MDB-1"."""
    _clock(page61)
    _name(page61, "Living Room", select=False)
    _type_box(page61, "LOC:LR-MDB-1", ms)
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [["LOC:LR-MDB-1", "keyboard"]]
    assert _box(page61) == ["Living Room", 11, 11]


def test_a_label_after_a_pause_is_a_scan_and_the_keys_before_it_stay(page61):
    """A key the person typed, then (after a pause) the scanner: the key is
    theirs and stays, the label is the scan's. RED on a95163c: "Shelf
    3qLOC:LR-MDB-1" was saved as the name."""
    _clock(page61)
    _name(page61, "Shelf 3", select=False)
    _type_box(page61, "q", 0, enter=False)
    _type_box(page61, "LOC:LR-MDB-1", 60, pauses={0: 700})
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [["LOC:LR-MDB-1", "keyboard"]]
    assert _box(page61) == ["Shelf 3q", 8, 8]


def test_the_box_gets_back_what_it_held_just_before_the_scan(page61):
    """RED on a95163c: the box got back what it held at the first key of the
    last 2 s of keys, whatever happened since: the last location's name after
    a save and another location opened at once, a name the person had just
    deleted, a name they had replaced."""
    _clock(page61)
    # A renamed and saved with Enter, then B opened (its name set and
    # selected, as openEdit does), and a scan into it at once.
    _name(page61, "Location A")
    _type_box(page61, "Shelf A", 100)
    assert page61.evaluate("() => window.__saves") == 1
    _later(page61, 200)
    _name(page61, "Location B")
    _type_box(page61, "ID:57", 60)
    assert _box(page61) == ["Location B", 0, 10]
    # The selected name deleted with Backspace, then a scan: still empty.
    _later(page61, 100)
    _name(page61, "Old name")
    _type_box(page61, ["Backspace"], 100, enter=False)
    _type_box(page61, "ID:58", 60)
    assert _box(page61) == ["", 0, 0]
    # A new name typed, Ctrl+A, then a scan: the new name, still selected.
    _name(page61, "Old name")
    _type_box(page61, "New name", 100, enter=False)
    _type_box(page61, ["Ctrl+A"], 100, enter=False)
    _type_box(page61, "ID:59", 60)
    assert _box(page61) == ["New name", 0, 8]
    assert [t for t, _ in _ids(page61)] == ["ID:57", "ID:58", "ID:59"]
    assert page61.evaluate("() => window.__saves") == 1


def test_a_burst_with_a_stall_inside_a_label_goes_whole(page61):
    """A burst scanner that stalls 300 ms inside a label. RED on a95163c (and
    before Group 61): the burst rule read only what came after the stall,
    "C:LR-MDB-1" (Unknown Code), and left "LO" in the box."""
    _clock(page61)
    _name(page61, "Shelf 3")
    _type_box(page61, "LOC:LR-MDB-1", 5, pauses={2: 300})
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [["LOC:LR-MDB-1", "keyboard"]]
    assert _box(page61) == ["Shelf 3", 0, 7]


@pytest.mark.parametrize("label", ["57", "1024", "PM-DB-1"])
def test_a_scan_with_no_prefix_typed_at_scanner_speed_is_a_scan(page61, label):
    """An old digits-only label, or an old location label with no prefix, at
    scanner speed: a scan, the name kept (Derek: "not input data"). RED on
    a95163c (and before Group 61): typed over the name and saved."""
    _clock(page61)
    _name(page61, "Shelf 3")
    _type_box(page61, label, 5)
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [[label, "barcode"]]
    assert _box(page61) == ["Shelf 3", 0, 7]


@pytest.mark.parametrize("digits", ["57", "1024"])
@pytest.mark.parametrize("ms", [60, 150])
def test_digits_typed_at_a_persons_pace_are_a_name(page61, digits, ms):
    _clock(page61)
    _name(page61, "")
    _type_box(page61, digits, ms)
    assert page61.evaluate("() => window.__saves") == 1 and _box(page61)[0] == digits
    assert _ids(page61) == []


@pytest.mark.parametrize("name", ["Old:Blue", "Box ID:3"])
def test_a_stored_name_that_looks_like_a_label_saves_on_enter(page61, name):
    """No key typed, so nothing to judge. RED on a95163c (Group 61 review):
    the editor opened on such a name, and a plain Enter sent it to the scan
    path and emptied or cut the box ("Box " and spool #3 in the buffer)."""
    _clock(page61)
    _name(page61, name)
    _type_box(page61, "", 0)
    assert page61.evaluate("() => window.__saves") == 1
    assert _box(page61)[0] == name and _ids(page61) == []


@pytest.mark.parametrize("name", ["Box ID:3", "Rack-ID:4", "Shelf ID:12 top"])
def test_a_name_typed_on_at_a_persons_pace_stays_a_name(page61, name):
    """A label inside a name typed with no pause is the name's. RED on a95163c
    (Group 61 review): "Box ID:3" put spool #3 in the buffer and left "Box "."""
    _clock(page61)
    _name(page61, "")
    _type_box(page61, name, 120)
    assert page61.evaluate("() => window.__saves") == 1
    assert _box(page61)[0] == name and _ids(page61) == []


def test_a_label_typed_into_max_spools_is_a_scan(page61):
    """A number box takes only a label's digits and dashes, and has no caret to
    follow: its keys are judged as they were typed (real keys). RED on a95163c:
    its Enter saved the form, Max Spools read as empty."""
    page61.evaluate("() => { const m = document.getElementById('edit-max'); m.value = '1'; m.focus(); }")
    page61.keyboard.type("LOC:LR-MDB-1", delay=60)
    page61.keyboard.press("Enter")
    page61.wait_for_function("() => window.__ids.length === 1", timeout=5000)
    assert _ids(page61) == [["LOC:LR-MDB-1", "keyboard"]]
    assert page61.input_value("#edit-max") == "1"
    assert page61.evaluate("() => window.__saves") == 0


def test_a_label_typed_into_a_locked_id_box_is_a_scan(page61):
    """A printer's ID box is read-only (its toolheads are keyed by it), so a
    label's keys never reach it: they are judged as they were typed. RED on
    a95163c: its Enter saved the form, and the scan was lost."""
    _clock(page61)
    page61.evaluate("() => { const b = document.getElementById('edit-id'); b.value = 'XL'; b.readOnly = true; b.focus(); }")
    _type_box(page61, "LOC:LR-MDB-1", 60)
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61) == [["LOC:LR-MDB-1", "keyboard"]]
    assert page61.input_value("#edit-id") == "XL"


def test_keys_a_click_or_the_page_split_are_two_inputs(page61):
    """A person typed "LOC", clicked to move the caret, then typed ":5": no
    label, the box's text is theirs (keys are judged as one run only while the
    box is as the last of them left it). Text the page set in between (the
    caret where it was) splits them too. RED on a95163c: the box's text "Box
    LOC:5" was read as a label and sent to the scan path."""
    _clock(page61)
    _name(page61, "Bin ", select=False)
    _type_box(page61, "LOC", 120, enter=False)
    page61.evaluate("() => document.getElementById('edit-name').setSelectionRange(0, 0)")
    _type_box(page61, ":5", 120)
    assert page61.evaluate("() => window.__saves") == 1 and _ids(page61) == []
    assert _box(page61)[0] == ":5Bin LOC"
    _name(page61, "Bin ", select=False)
    _type_box(page61, "LOC", 120, enter=False)
    page61.evaluate("() => { const n = document.getElementById('edit-name'); n.value = 'Box LOC'; n.setSelectionRange(7, 7); }")
    _type_box(page61, ":5", 120)
    assert page61.evaluate("() => window.__saves") == 2 and _ids(page61) == []
    assert _box(page61)[0] == "Box LOC:5"


@pytest.mark.parametrize("between", [["ArrowLeft", "ArrowRight"], ["Ctrl+C"]])
def test_a_persons_own_key_splits_the_keys_around_it(page61, between):
    """A person's key between them, even one that leaves the box as it was (an
    arrow there and back, a copy): the keys are a person's, so "ID" then ":5"
    stays the name's text, as the weight capture reads such a key. RED on
    a95163c: the box's text "Bin ID:5" was read as a label, and spool #5
    joined the buffer."""
    _clock(page61)
    _name(page61, "Bin ", select=False)
    _type_box(page61, "ID", 120, enter=False)
    _type_box(page61, between, 120, enter=False)
    _type_box(page61, ":5", 120)
    assert page61.evaluate("() => window.__saves") == 1 and _ids(page61) == []
    assert _box(page61)[0] == "Bin ID:5"


def test_a_box_put_back_tells_its_listeners(page61):
    """The Location ID box's own input listener re-syncs the parent breadcrumb
    from it (inv_loc_mgr.js): the box put back after a scan says it changed.
    RED on a95163c: its text came back, its selection didn't."""
    _clock(page61)
    page61.evaluate("""() => { window.__idInputs = []; const b = document.getElementById('edit-id');
        b.addEventListener('input', () => window.__idInputs.push(b.value)); b.value = 'LR-SHELF-2'; b.focus(); b.select(); }""")
    _type_box(page61, "LOC:LR-MDB-1", 60)
    page61.wait_for_function("() => window.__ids.length === 1")
    assert page61.evaluate("() => window.__idInputs[window.__idInputs.length - 1]") == "LR-SHELF-2"
    assert _box(page61, "#edit-id") == ["LR-SHELF-2", 0, 10]


# --- 61.3 the parent tree picker --------------------------------------------------

def _open_tree(page):
    page.evaluate("""(rows) => _renderParentTreePicker(rows, 'LR-MDB-1', document.getElementById('edit-parent'),
        document.getElementById('locModal'))""", LOC_ROWS)
    page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('fcc-tp-node')")


def _tree(page):
    return page.evaluate("""() => ({ open: !!document.getElementById('fcc-parent-tree-picker'),
        parent: document.getElementById('edit-parent').value,
        flash: (document.querySelector('#fcc-parent-tree-picker .fcc-tp-flash') || {}).textContent || '' })""")


@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_locations_label_picks_it_as_the_parent(page61, ms):
    """RED on ca1a701: the scan's Enter picked the highlighted parent (Auto) and
    the scan was thrown away."""
    _clock(page61)
    _open_tree(page61)
    _type(page61, "LOC:GARAGE", ms)
    t = _tree(page61)
    assert not t["open"] and t["parent"] == "GARAGE", t
    assert _ids(page61) == []


# (`label`, not `scan`: --offline skips a test asking for a parameter named as
# a container fixture, conftest.CONTAINER_FIXTURES.)
@pytest.mark.parametrize("label, says", [
    ("LOC:LR-MDB-1", "LR-MDB-1 isn't one of the parents offered here"),     # the location itself
    ("ID:57", "Answer the question on screen first"),
])
def test_another_scan_in_the_tree_picker_is_refused(page61, label, says):
    _clock(page61)
    _open_tree(page61)
    _type(page61, label, 26)
    t = _tree(page61)
    assert t["open"] and t["parent"] == "__auto__" and says in t["flash"], t
    assert _ids(page61) == [] and _buffer(page61) == ""


def test_a_persons_enter_in_the_tree_picker_still_picks(page61):
    _clock(page61)
    _open_tree(page61)
    _type(page61, "", 0)                                   # Enter on the highlighted Auto
    t = _tree(page61)
    assert not t["open"] and t["parent"] == "__auto__", t


# --- 61.3 the wizard header, the pill, "Close without saving?" --------------------

@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_scan_on_a_wizard_header_toggles_nothing(page61, ms):
    """RED on ca1a701: the scan's Enter toggled the section, and the scan stayed
    in the scan buffer."""
    _clock(page61)
    page61.focus(".fcc-wiz-section-toggle")
    _type(page61, "ID:57", ms)
    assert page61.evaluate("() => window.__toggles") == 0 and _buffer(page61) == ""
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61)[0][0] == "ID:57"


@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_scan_on_the_search_pill_opens_nothing(page61, ms):
    """RED on ca1a701: the scan's Enter opened the search (and the scan went
    on too)."""
    _clock(page61)
    page61.focus("#fcc-test-pill")
    _type(page61, "ID:57", ms)
    assert page61.evaluate("() => window.__taps") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61)[0][0] == "ID:57"


def test_a_persons_keys_on_the_header_and_the_pill_still_work(page61):
    _clock(page61)
    page61.focus(".fcc-wiz-section-toggle")
    _type(page61, "", 0)                                   # Enter
    page61.evaluate("() => { window.__T += 1000; }")       # past the header's own 400 ms debounce
    _type(page61, [" "], 0, enter=False)                   # Space
    assert page61.evaluate("() => window.__toggles") == 2
    page61.focus("#fcc-test-pill")
    _type(page61, "", 0)
    assert page61.evaluate("() => window.__taps") == 1
    # A key a person left a second before goes with their Enter, never to the
    # scan path as a scan of "x".
    _type(page61, "x", 0, enter=False)
    page61.evaluate("() => { window.__T += 1000; }")
    _type(page61, "", 0)
    assert page61.evaluate("() => window.__taps") == 2
    assert _ids(page61) == [] and _buffer(page61) == ""


def _open_close_question(page, focus):
    page.evaluate("() => { window.__hides = 0; _editfilShowEscapeConfirm({ hide: () => { window.__hides += 1; } }); }")
    page.focus(focus)


def _close_question(page):
    return page.evaluate("() => ({ open: !!document.getElementById('editfil-esc-confirm'), hides: window.__hides })")


@pytest.mark.parametrize("focus", ["#editfil-esc-yes", "#editfil-esc-no"])
@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_scan_never_answers_close_without_saving(page61, focus, ms):
    """RED on ca1a701: with Close Anyway focused the scan closed the filament
    editor unsaved; with Keep Editing it closed the question; either way the
    scan stayed in the scan buffer."""
    _clock(page61)
    _open_close_question(page61, focus)
    _type(page61, "ID:57", ms)
    assert _close_question(page61) == {"open": True, "hides": 0}
    assert _buffer(page61) == ""
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61)[0][0] == "ID:57"


def test_a_persons_enter_on_close_without_saving_still_answers(page61):
    _clock(page61)
    _open_close_question(page61, "#editfil-esc-yes")
    _type(page61, "", 0)
    assert _close_question(page61) == {"open": False, "hides": 1}
    _open_close_question(page61, "#editfil-esc-no")
    _type(page61, "", 0)
    assert _close_question(page61) == {"open": False, "hides": 0}


# --- a Space inside a scan presses no button ---------------------------------------

def _open_for_space(page, which):
    if which == "picker":
        _open_picker(page, choose=134)
        return "#fcc-legacy-picker-use"
    if which == "tree":
        _open_tree(page)
        return None                                        # a node has the focus
    if which == "close":
        _open_close_question(page, "#editfil-esc-yes")
        return None
    return {"header": ".fcc-wiz-section-toggle", "pill": "#fcc-test-pill"}[which]


def _pressed(page, which):
    return page.evaluate("""(w) => ({
        picker: () => !document.getElementById('fcc-legacy-picker-overlay') || state.heldSpools.length > 0,
        tree: () => !document.getElementById('fcc-parent-tree-picker'),
        close: () => window.__hides > 0 || !document.getElementById('editfil-esc-confirm'),
        header: () => window.__toggles > 0 || window.__clicks.header > 0,
        pill: () => window.__taps > 0 || window.__clicks.pill > 0 })[w]()""", which)


@pytest.mark.parametrize("ms", [1, 150, 400])
@pytest.mark.parametrize("which", ["picker", "tree", "close", "header", "pill"])
def test_a_space_inside_a_scan_presses_no_button(page61, which, ms):
    """A location id may hold a Space ("LOC:GARAGE SHELF"): the real Space key,
    with the label's first part in the scan buffer, presses nothing, and the
    scan arrives whole, from a burst scanner or a slower one (its Space comes
    long after the 500 ms a scan counts as in flight from its first key, so
    the rule is scanIsArriving's, not isScanInFlight's). RED on ca1a701: it
    pressed the focused button (the header and the pill took it themselves;
    the others by the button's own press)."""
    _clock(page61)
    focus = _open_for_space(page61, which)
    if focus:
        page61.focus(focus)
    before = len(_ids(page61))
    _type(page61, "LOC:GARAGE", ms, enter=False)
    page61.keyboard.press(" ")
    page61.wait_for_timeout(50)
    assert not _pressed(page61, which), f"{which}: the Space pressed the button"
    _type(page61, "SHELF", ms)
    page61.wait_for_timeout(100)
    # Whole: on the scan path (the header, the pill, the close question), or
    # refused by the open question, which quotes it (the two pickers).
    if which == "picker":
        assert "Ignored: LOC:GARAGE SHELF" in _picker(page61)["flash"], _picker(page61)
    elif which == "tree":
        assert "GARAGE SHELF isn't one of the parents offered here" in _tree(page61)["flash"], _tree(page61)
    else:
        assert [t for t, _ in _ids(page61)[before:]] == ["LOC:GARAGE SHELF"], _ids(page61)
    assert not _pressed(page61, which)
    assert page61.evaluate("() => window.__errors") == []


@pytest.mark.parametrize("which", ["picker", "tree", "close", "header"])
def test_a_persons_enter_takes_a_key_they_left_with_it(page61, which):
    """A stray key, then a second later a person's Enter: the dialog answers
    it, and the key goes with it, never glued to the next scan (the pill's
    twin is in test_a_persons_keys_on_the_header_and_the_pill_still_work)."""
    _clock(page61)
    focus = _open_for_space(page61, which)
    if focus:
        page61.focus(focus)
    before = len(_ids(page61))
    _type(page61, "x", 0, enter=False)
    _later(page61, 1000)
    _type(page61, "", 0)
    assert _pressed(page61, which), f"{which}: the person's Enter answered nothing"
    assert _buffer(page61) == "", f"{which}: the key they left stayed in the scan buffer"
    assert all(t != "x" for t, _ in _ids(page61)[before:]), _ids(page61)


def test_a_refused_scans_text_is_escaped_in_the_activity_log(page61):
    """The Activity Log draws its lines as HTML, so a scan's text put in one is
    escaped: the picker's own refusal, processScan's ("still open"), its
    double-read note, and the tree picker's. RED on a95163c (Group 61 review):
    the text went in raw, so a code holding HTML ran in the log."""
    _clock(page61)
    _open_picker(page61)
    _type(page61, "<b>x</b>ID:999", 1)                     # the picker's rule: not a listed spool
    _type(page61, "<u>z</u>", 1)                           # processScan's: no label the picker reads
    page61.click("#fcc-legacy-picker-cancel")
    _open_tree(page61)
    _type(page61, "LOC:<i>Q</i>", 1)                       # the tree picker's: no parent by that id
    page61.click("#fcc-parent-tree-picker [data-tp='cancel']")
    page61.evaluate("() => { processScan('LOC:<s>W</s>', 'barcode'); processScan('LOC:<s>W</s>', 'barcode'); }")
    page61.wait_for_function("() => window.__logs.length >= 4")
    logs = page61.evaluate("() => window.__logs")
    for raw in ("<b>", "<u>", "<i>", "<I>", "<s>"):
        assert not any(raw in m for m in logs), (raw, logs)
    for shown in ("&lt;b&gt;x&lt;/b&gt;ID:999", "&lt;u&gt;z&lt;/u&gt;", "&lt;i&gt;Q&lt;/i&gt;", "&lt;s&gt;W&lt;/s&gt;"):
        assert any(shown in m for m in logs), (shown, logs)
