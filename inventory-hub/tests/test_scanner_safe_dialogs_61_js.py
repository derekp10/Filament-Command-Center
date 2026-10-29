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
  spool's ID:<n> (or SPL:<n>, or the bare number) picks that spool, sent with
  the scan's own source; any other scan is refused with a note, nothing joins
  the buffer and nothing is left in the scan buffer; CMD:CANCEL cancels; a
  person's Enter and clicks work as before, and "Use selected" is no label
  scan (it sent 'barcode', so the server marked the spool's label printed and
  the spool left the label backlog);
- the location editor: digits alone on the Type select are a scan at any
  speed, while a person's typeahead and Enter still save; a whole FCC label
  typed into a box at any speed goes to the scan path and the box keeps what
  it held (typed over the selected name, or after it), while a name with a
  ':' stays a name;
- the parent tree picker: a scan picks no node (its Enter picked the
  highlighted parent and threw the scan away); a pickable location's own label
  picks it as the parent, another place's is refused with a note, any other
  scan too; a person's Enter still picks;
- a focused wizard section header, the floating search pill and the filament
  editor's "Close without saving?": a scan's Enter, and a Space inside a scan,
  press nothing, and the scan reaches the scan path; a person's keys work.
RED before Group 61, on ca1a701 (each test says how).
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
window.__answers = {};      // a scan's text -> its answer
window.__toggles = 0;       // the wizard section's Bootstrap Collapse toggles
window.bootstrap = { Collapse: { getOrCreateInstance: function () {
    return { toggle: function () { window.__toggles += 1; } }; } } };
window.fetch = function (url, opts) {
    url = String(url);
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    let ans = { status: 'success', success: true };
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

# The location editor (#locModal: its boxes, the Type select, a Cancel), the
# filament editor the close question mounts in, a wizard section and its
# header, and the floating search pill; all there before the modules load, as
# on the page (inv_loc_mgr.js and inv_wizard.js wire theirs at load).
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>.modal{display:none}.modal.show{display:block}</style>
</head><body>
<div id="locModal" class="modal show"><div class="modal-content">
  <input id="edit-name" type="text"><input id="edit-id" type="text">
  <select id="edit-type"><option>Room</option><option>Dryer Box</option><option>Shelf</option></select>
  <select id="edit-parent"><option value="__auto__">Auto</option><option value="__none__">Top level</option></select>
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
        window.__clicks = { header: 0, pill: 0 };
        document.querySelector('.fcc-wiz-section-toggle').addEventListener('click', () => { window.__clicks.header += 1; });
        document.getElementById('fcc-test-pill').addEventListener('click', () => { window.__clicks.pill += 1; });
        window.makeDraggablePill(document.getElementById('fcc-test-pill'),
            { key: 'fcc.test.pill', defaultPos: () => ({ left: 10, bottom: 10 }), onTap: () => { window.__taps += 1; } });
    }""")
    return page


def _clock(page):
    """The fake clock, before anything is typed with it."""
    page.evaluate(TYPE_JS, ["", 0, False, {}])


def _type(page, text, ms, enter=True):
    page.evaluate(TYPE_JS, [text, ms, enter, {}])


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
    """The scan's own source goes with it: a scanner-speed scan of the label
    verifies it (the server's rule), a slower one doesn't. RED on ca1a701: the
    Enter picked the selected #134."""
    _clock(page61)
    _open_picker(page61)
    _type(page61, label, ms)
    page61.wait_for_function("() => window.__ids.length === 2")
    want = "barcode" if ms == 1 else "keyboard"
    assert _ids(page61) == [["LEG:120", "barcode"], ["ID:135", want]], _ids(page61)
    page61.wait_for_function("() => state.heldSpools.length === 1")
    assert _picker(page61)["held"] == [135] and not _picker(page61)["open"]


def test_a_spool_not_on_the_list_is_refused(page61):
    _clock(page61)
    _open_picker(page61)
    _type(page61, "ID:999", 26)
    p = _picker(page61)
    assert p["open"] and p["held"] == [] and "#999 isn't one of the spools listed" in p["flash"], p
    assert _ids(page61) == [["LEG:120", "barcode"]]


def test_scan_to_cancel_cancels_it(page61):
    _clock(page61)
    _open_picker(page61)
    _type(page61, "CMD:CANCEL", 26)
    p = _picker(page61)
    assert not p["open"] and p["held"] == [], p
    assert _ids(page61) == [["LEG:120", "barcode"]]


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
    """RED on ca1a701 (all but a 4-digit label at scanner speed, a burst): the
    Enter saved the location, and the digits went nowhere."""
    _clock(page61)
    page61.focus("#edit-type")
    _type(page61, label, ms)
    assert page61.evaluate("() => window.__saves") == 0
    page61.wait_for_function("() => window.__ids.length === 1")
    assert _ids(page61)[0][0] == label


@pytest.mark.parametrize("target", ["#edit-type", "#loc-cancel"])
def test_a_persons_typeahead_and_enter_still_save(page61, target):
    """46.2's design: "dr" then Enter on the Type select saves; Enter on a
    button presses it (here Cancel, whose own click this page doesn't wire)."""
    _clock(page61)
    page61.focus(target)
    _type(page61, "dr", 220)
    saves = page61.evaluate("() => window.__saves")
    assert saves == (1 if target == "#edit-type" else 0), saves
    assert _ids(page61) == [] and _buffer(page61) == ""


def _name(page, value, select=True):
    page.evaluate("""([v, sel]) => { const n = document.getElementById('edit-name'); n.value = v; n.focus();
        if (sel) n.select(); else n.setSelectionRange(v.length, v.length); }""", [value, select])


@pytest.mark.parametrize("text, want", [
    ("LOC:LR-MDB-1", ["LOC:LR-MDB-1", ""]),
    ("Shelf 3LOC:LR-MDB-1", ["LOC:LR-MDB-1", "Shelf 3"]),
    ("loc:lr-mdb-1", ["loc:lr-mdb-1", ""]),                      # Caps Lock, or a lower-case scanner
    ("LOC:GARAGE SHELF", ["LOC:GARAGE SHELF", ""]),              # an id may hold a Space
    ("Rack 2ID:57", ["ID:57", "Rack 2"]),
    ("LEGACY:7", ["LEGACY:7", ""]),
    ("https://prusament.com/spool/1/ab/", ["https://prusament.com/spool/1/ab/", ""]),
    ("Shelf: top", None),
    ("Grid:2", None),                                           # "ID" inside a word is no prefix
    ("LOC: here", None),                                        # a blank after the ':'
    ("Bin 3/4", None),
    ("My shelf", None),
])
def test_what_counts_as_a_label_at_the_end_of_a_box(page61, text, want):
    got = page61.evaluate("(t) => { const h = window.fccLabelAtEnd(t); return h ? [h.label, h.before] : null; }", text)
    assert got == want, (text, got)


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


@pytest.mark.parametrize("which", ["picker", "tree", "close", "header", "pill"])
def test_a_space_inside_a_scan_presses_no_button(page61, which):
    """A location id may hold a Space ("LOC:GARAGE SHELF"): the real Space key,
    with the label's first part in the scan buffer, presses nothing, and the
    scan arrives whole. RED on ca1a701: it pressed the focused button (the
    header and the pill took it themselves; the others by the button's own
    press)."""
    _clock(page61)
    focus = _open_for_space(page61, which)
    if focus:
        page61.focus(focus)
    before = len(_ids(page61))
    _type(page61, "LOC:GARAGE", 1, enter=False)
    page61.keyboard.press(" ")
    page61.wait_for_timeout(50)
    assert not _pressed(page61, which), f"{which}: the Space pressed the button"
    _type(page61, "SHELF", 1)
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
