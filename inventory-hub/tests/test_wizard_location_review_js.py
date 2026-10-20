"""Group 40.7 review — the browser half of the wizard Location fixes, as hermetic JS
checks under node's `vm` (the real inv_core.js, inv_cmd.js and inv_wizard.js over
the stub DOM of test_core1_return_ejectall_js.py; the slot / Printer picker is
test_wizard_picker_js's stub that answers what a user picked). No browser, no
container. The server half is in test_wizard_location_review.py.

Findings pinned here (each test names its own):
  - wizard-resave-unloads-head: after a move lands (the edit's answer, or a
    question answered on /api/smart_move) the Location field shows where the
    spool is now, so a second Save sends the head and moves nothing.
  - wizard-tab-resets-head-to-unassigned: Tab and Enter through a Location the
    list doesn't show (a head) leave it alone unless the user typed.
  - wizard-slotless-create-loads-empty-head: Save opens the picker for a box or
    printer that has no held choice, posts only after a pick, and saves nothing
    on Escape; after a create the field drops the used "— slot N".
  - wizard-stale-pick-via-reopens-picker: a blank Location opens no picker, and a
    held choice is dropped once the field's value stops matching it.
  - wizard-not-moved-drops-to-buffer: an edit whose move didn't land still takes
    a Swap's old spool into this page's buffer.
  - wizard-refused-pick-resent: a refusal of the held choice drops it and says
    "Pick a slot again" (or "a toolhead"); Save then opens the picker; another
    refusal keeps it.
  - wizard-loop-undo-buffer-top: the per-spool loop's moves go as origin
    'wizard_create' (asserted on what wizardPlaceRemaining passes: inv_cmd.js's
    performContextAssign gains `opts.origin` in a sibling change).
  - wizard-create-cancel-silent: a create placement's question that ends in no
    move says, once, for 7 s, that the new spool exists and is Unassigned.
  - wizard-create-question-drops-nostore: the first new spool's question keeps
    the held choice's noStore (no "Just store it" the engine would refuse).

Base proof (7976b72): 22 of these 24 fail there, each on what the page did (a
Tab that wrote "-- Unassigned --", a second Save that sent the box, a picker
opened for an abandoned pick, a slotless placement, a buffer without #60, …).
The two that pass there are the controls marked in their docstrings.
Adopted from the reviewers' probes: test_probe_wizard_tab_resets_head (and its
mini DOM), test_probe_wizard_second_create_slotless (its "the field still names
slot 2" precondition is now the bug's fix: the label is reset, and the next
create opens the picker), test_probe_wizard_stale_pick_loop,
test_probe_wizard_swap_failed_buffer (page half), test_probe_wizard_refused_pick_
resent and test_probe_wizard_create_cancel_silent.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import FED, PRELUDE
from test_wizard_location_save_js import WIZARD
from test_wizard_picker_js import MODULES as PICKER, SETUP

SAVE = ["inv_core.js", "inv_wizard.js"]


def _run(tmp_path, modules, body, setup=""):
    res = run_js(tmp_path, modules, PRELUDE + WIZARD + setup + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


# ---- wizard-resave-unloads-head ----------------------------------------------------------

MOVED_TO_XL1 = {"success": True, "spool_id": 57, "spool_saved": True, "location_moved": True,
                "location_where": "LR-MDB-1 slot 1 → XL-1", "location_now": "XL-1",
                "location_result": {"status": "success", "failures": {}, "auto_deployed_to": "XL-1"}}


def test_after_a_landed_edit_a_second_save_sends_the_head_not_the_box(tmp_path):
    """Save 1 moved #57 into LR-MDB-1 slot 1, whose chain loaded XL-1. Save 2 (the
    user fixes a comment) used to send LR-MDB-1 again, and the server stored #57
    back in its slot, unloading XL-1 unasked. It sends XL-1 now: no move."""
    res = _run(tmp_path, SAVE, """
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '1', expected_feed: 'XL-1', via: 'LR-MDB-1' };
answerFor({ '/api/edit_spool_wizard': [__MOVED__, { success: true, spool_id: 57 }] });
await window.wizardSubmit();
await __settle(80);
const between = { value: document.getElementById('wiz-spool-location').value,
                  label: document.getElementById('wiz-spool-location-search').value };
await window.wizardSubmit();
await __settle(80);
return { between, bodies: posts('/api/edit_spool_wizard') };
""".replace("__MOVED__", _js(MOVED_TO_XL1)))
    assert res["between"] == {"value": "XL-1", "label": "XL-1"}, res["between"]
    second = res["bodies"][1]
    assert second["spool_data"]["location"] == "XL-1", second
    for key in ("slot", "picked_slot", "expected_feed", "record_source", "swap"):
        assert key not in second, (key, second)


def test_after_an_answered_question_lands_a_second_save_sends_the_head(tmp_path):
    """The partial path: the server asked (XL-1 runs #99 from elsewhere), "Load
    it instead" replayed on /api/smart_move and loaded XL-1. Save 2 sends XL-1."""
    asked = {"success": False, "spool_saved": True, "location_moved": False, "msg": "FCC has to ask first",
             "location_result": dict(FED, target="LR-MDB-1", slot_picked=False, feed="XL-1", can_load=True,
                                     leaving=[])}
    res = _run(tmp_path, SAVE, """
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = { location: 'LR-MDB-1', slot: '1', expected_feed: 'XL-1', via: 'LR-MDB-1' };
answerFor({ '/api/edit_spool_wizard': [__ASKED__, { success: true, spool_id: 57 }],
            '/api/smart_move': [{ status: 'success', failures: {}, auto_deployed_to: 'XL-1' }] });
await window.wizardSubmit();
await __settle(80);
await click('.fcc-apc-yes');
await __settle(80);
await window.wizardSubmit();
await __settle(80);
return { bodies: posts('/api/edit_spool_wizard'), replays: posts('/api/smart_move').length };
""".replace("__ASKED__", _js(asked)))
    assert res["replays"] == 1, res
    second = res["bodies"][1]
    assert second["spool_data"]["location"] == "XL-1" and "slot" not in second, second


# ---- wizard-tab-resets-head-to-unassigned (the reviewers' mini DOM) ------------------------

MINI_DOM = r"""
const mkEl = (id) => {
  const listeners = {};
  const classes = new Set();
  const el = {
    id, value: '', placeholder: '', style: { display: 'none' }, dataset: {}, children: [], _html: '',
    classList: {
      add: (...c) => c.forEach(x => classes.add(x)), remove: (...c) => c.forEach(x => classes.delete(x)),
      contains: (c) => classes.has(c),
    },
    addEventListener(t, fn) { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener() {},
    dispatchEvent(ev) { (listeners[ev.type] || []).forEach(fn => fn(ev)); return true; },
    fire(type, props) {
      const ev = Object.assign({ type, preventDefault() {}, stopPropagation() {} }, props || {});
      (listeners[type] || []).forEach(fn => fn(ev));
    },
    getBoundingClientRect() { return { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 }; },
    scrollTop: 0,
    cloneNode() { const c = mkEl(id); c.value = el.value; c.placeholder = el.placeholder; return c; },
    querySelectorAll(sel) { return sel === '.autocomplete-option' ? el.children.slice() : []; },
    querySelector(sel) {
      if (sel === '.autocomplete-option.active') return el.children.find(c => c.classList.contains('active')) || null;
      return null;
    },
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html; },
    set(html) {
      el._html = html;
      el.children = [];
      const re = /<div class="([^"]*)"\s+data-value="([^"]*)"\s+data-label="([^"]*)">/g;
      let m;
      while ((m = re.exec(html))) {
        const opt = mkEl('');
        m[1].split(/\s+/).filter(Boolean).forEach(c => opt.classList.add(c));
        const unesc = (s) => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>').replace(/&amp;/g, '&');
        opt.dataset.value = unesc(m[2]);
        opt.dataset.label = unesc(m[3]);
        el.children.push(opt);
      }
    },
  });
  return el;
};
const combo = { 'wiz-spool-location-search': mkEl('wiz-spool-location-search'),
                'wiz-spool-location': mkEl('wiz-spool-location'), 'dropdown-location': mkEl('dropdown-location') };
const parent = { replaceChild(fresh, old) { combo[old.id] = fresh; return old; } };
combo['wiz-spool-location-search'].parentNode = parent;
const baseGet = document.getElementById.bind(document);
document.getElementById = (id) => combo[id] || baseGet(id);
const ROWS = [
  { LocationID: 'XL', Name: 'XL', Type: 'Printer', 'Max Spools': '0',
    toolheads: [1, 2, 3].map(n => ({ location_id: 'XL-' + n, position: n - 1 })) },
  ...[1, 2, 3].map(n => ({ LocationID: 'XL-' + n, Name: 'XL-' + n, Type: 'Tool Head', 'Max Spools': '1' })),
  { LocationID: 'LR-MDB-1', Name: 'LR box', Type: 'Dryer Box', 'Max Spools': '4' },
  { LocationID: 'CR-CT-2-R1', Name: 'Cart row', Type: 'Cart Row', 'Max Spools': '0' },
];
state.allLocations = ROWS;
// The wizard's own binding (the list hides toolheads), answered from ROWS.
window.__extra = (url) => (url === '/api/locations' ? { body: ROWS } : null);
await wizardFetchLocations();
const search = () => document.getElementById('wiz-spool-location-search');
const hidden = document.getElementById('wiz-spool-location');
const shownNow = () => ({ value: hidden.value, label: search().value });
const put = (value, label) => { hidden.value = value; search().value = label; };
"""


@pytest.mark.parametrize("key", ["Tab", "Enter"])
def test_tab_or_enter_through_a_printer_pickers_head_keeps_it(tmp_path, key):
    """The Printer picker left 'XL-3 (via XL)'. Derek clicks back into the field
    and Tabs (or presses Enter) on: it became "-- Unassigned --", and Save took
    #57 off its new head before it ever got there."""
    res = _run(tmp_path, SAVE, MINI_DOM + """
editing(57, 'CR-CT-2-R1');
put('XL-3', 'XL-3 (via XL)');
wizardState.pendingPlacement = { location: 'XL-3', record_source: '', via: 'XL', label: 'XL-3' };
const before = shownNow();
search().fire('focus');
search().fire('keydown', { key: '__KEY__' });
const after = shownNow();
answerFor({ '/api/edit_spool_wizard': [{ success: true, spool_id: 57 }] });
await window.wizardSubmit();
await __settle(60);
return { before, after, sent: posts('/api/edit_spool_wizard')[0] };
""".replace("__KEY__", key))
    assert res["after"] == res["before"] == {"value": "XL-3", "label": "XL-3 (via XL)"}, res
    assert res["sent"]["spool_data"]["location"] == "XL-3" and res["sent"]["record_source"] == "", res["sent"]


def test_tab_through_an_edited_spools_head_keeps_it(tmp_path):
    """Editing #57, loaded on XL-1 (pre-filled "XL-1"): Tab from the filament
    fields through Location to the weights used to write '' and Save then
    force-unassigned #57 off XL-1 with no question while the XL was idle."""
    res = _run(tmp_path, SAVE, MINI_DOM + """
editing(57, 'XL-1');
put('XL-1', 'XL-1');
search().fire('focus');
search().fire('keydown', { key: 'Tab' });
const after = shownNow();
answerFor({ '/api/edit_spool_wizard': [{ success: true, spool_id: 57 }] });
await window.wizardSubmit();
await __settle(60);
return { after, sent: posts('/api/edit_spool_wizard')[0] };
""")
    assert res["after"] == {"value": "XL-1", "label": "XL-1"}, res
    assert res["sent"]["spool_data"]["location"] == "XL-1", res["sent"]


def test_a_typed_query_and_an_untouched_listed_value_behave_as_before(tmp_path):
    """Control (passes on the base too): 25.I's rules for the Location and vendor
    comboboxes. A typed query confirms the first match on Tab; Tab through a
    listed value changes nothing (and fires no change)."""
    res = _run(tmp_path, SAVE, MINI_DOM + """
put('', '');
search().fire('focus');
search().value = 'cart';
search().fire('input');
search().fire('keydown', { key: 'Tab' });
const typed = shownNow();
let changes = 0;
hidden.addEventListener('change', () => changes++);
search().fire('focus');
search().fire('keydown', { key: 'Tab' });
return { typed, untouched: shownNow(), changes };
""")
    assert res["typed"] == {"value": "CR-CT-2-R1", "label": "Cart row (CR-CT-2-R1)"}, res
    assert res["untouched"] == res["typed"] and res["changes"] == 0, res


# ---- wizard-stale-pick-via-reopens-picker ------------------------------------------------

def test_a_blank_location_create_opens_no_picker_for_an_abandoned_pick(tmp_path):
    """The reviewers' probe: the user picked LR-MDB-1 slot 2, then emptied the
    field, and created 2 spools. They are Unassigned, as asked, and no picker
    opens for LR-MDB-1 (Enter there took the star, which could load a head)."""
    created = {"success": True, "filament_id": 7, "created_spools": [501, 502], "placed": {},
               "unplaced": [501, 502], "location_results": {}, "placement_requests": {}, "placements_ok": True}
    res = _run(tmp_path, PICKER, """
creating(2, '');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'XL-2',
                                  via: 'LR-MDB-1', label: 'LR-MDB-1 slot 2' };
answerFor({ '/api/create_inventory_wizard': [__CREATED__] });
await window.wizardSubmit();
await __settle(150);
return { sent: posts('/api/create_inventory_wizard')[0].placements,
         pickers: window.__pickerCalls.map(c => [c.location, c.spool, c.step]), toasts: toasts().map(t => t.msg) };
""".replace("__CREATED__", _js(created)), setup=SETUP)
    assert res["sent"] == [None, None], res
    assert res["pickers"] == [], ("a picker opened for the abandoned LR-MDB-1 pick", res["pickers"])


def test_typing_over_a_held_pick_drops_it(tmp_path):
    """Typing (or backspacing) in the Location changes its value without a pick;
    the held choice for LR-MDB-1 slot 2 is dropped once the value isn't LR-MDB-1."""
    res = _run(tmp_path, SAVE, MINI_DOM + """
put('LR-MDB-1', 'LR box (LR-MDB-1) — LR-MDB-1 slot 2');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'XL-2', via: 'LR-MDB-1' };
search().fire('focus');
search().value = 'LR box (LR-MDB-1)';      // backspaced the slot: still LR-MDB-1, the pick stays
search().fire('input');
const same = wizardState.pendingPlacement && wizardState.pendingPlacement.picked_slot;
search().value = '';
search().fire('input');
return { same, value: hidden.value, pending: wizardState.pendingPlacement };
""")
    assert res["same"] == "2", res
    assert res["value"] == "" and res["pending"] is None, res


# ---- wizard-slotless-create-loads-empty-head ---------------------------------------------

def _created(sid, where):
    return {"success": True, "filament_id": 7, "created_spools": [sid], "placed": {str(sid): where}, "unplaced": [],
            "location_results": {str(sid): {"status": "success", "failures": {}}},
            "placement_requests": {str(sid): {"location": "LR-MDB-1"}}, "placements_ok": True}


def test_a_create_into_a_box_with_no_pick_opens_the_picker_first(tmp_path):
    """A box confirmed with Tab, typed, or pre-filled by a Clone: Save opens its
    picker and sends the slot chosen there. It used to send the box with no
    slot, and the engine's star slot loaded an empty head with the new spool."""
    res = _run(tmp_path, PICKER, """
creating(1, 'LR-MDB-1');
setShown('LR-MDB-1', 'LR box (LR-MDB-1)');
window.__picks = [slotPick('4', '')];
answerFor({ '/api/create_inventory_wizard': [__CREATED__] });
await window.wizardSubmit();
await __settle(100);
return { calls: window.__pickerCalls.map(c => [c.location, c.spool]),
         sent: posts('/api/create_inventory_wizard').map(b => b.placements) };
""".replace("__CREATED__", _js(_created(501, "LR-MDB-1 slot 4"))), setup=SETUP)
    assert res["calls"] == [["LR-MDB-1", None]], res
    assert res["sent"] == [[{"location": "LR-MDB-1", "picked_slot": "4", "expected_feed": ""}]], res


def test_escape_in_the_save_picker_saves_nothing_and_says_so(tmp_path):
    res = _run(tmp_path, PICKER, """
creating(1, 'LR-MDB-1');
setShown('LR-MDB-1', 'LR box (LR-MDB-1)');
await window.wizardSubmit();
await __settle(80);
return { posts: posts('/api/create_inventory_wizard').length, status: status(), disabled: submitDisabled(),
         shown: shown(), toasts: toasts().map(t => t.msg) };
""", setup=SETUP)
    assert res["posts"] == 0, res
    assert "Nothing was saved: pick a slot in LR-MDB-1" in res["status"] and res["disabled"] is False, res
    assert res["shown"] == {"value": "LR-MDB-1", "label": "LR box (LR-MDB-1)"}, res
    assert "Location not changed — the picker was closed" not in res["toasts"], res


def test_the_next_create_after_a_pick_opens_the_picker_again(tmp_path):
    """The reviewers' probe: the wizard stays open after a create for rapid adds.
    The pick (slot 2) is used up, so the field no longer names it, and the next
    create asks for a slot again instead of sending the box without one."""
    first = dict(_created(501, "LR-MDB-1 slot 2"),
                 placement_requests={"501": {"location": "LR-MDB-1", "picked_slot": "2"}})
    res = _run(tmp_path, PICKER, """
creating(1, 'CR-SHELF');
setShown('LR-MDB-1', 'LR box (LR-MDB-1)');
window.__picks = [slotPick('2', 'XL-2')];
await window.wizardLocationPicked('LR-MDB-1', { value: 'CR-SHELF', label: 'Shelf (CR-SHELF)' });
answerFor({ '/api/create_inventory_wizard': [__FIRST__, __SECOND__] });
await window.wizardSubmit();
await __settle(80);
const between = { pending: wizardState.pendingPlacement, shown: shown() };
window.__picks = [slotPick('3', 'XL-3')];
await window.wizardSubmit();
await __settle(80);
return { between, calls: window.__pickerCalls.length,
         bodies: posts('/api/create_inventory_wizard').map(b => b.placements) };
""".replace("__FIRST__", _js(first)).replace("__SECOND__", _js(_created(502, "LR-MDB-1 slot 3"))), setup=SETUP)
    assert res["bodies"][0] == [{"location": "LR-MDB-1", "picked_slot": "2", "expected_feed": "XL-2"}], res
    assert res["between"]["pending"] is None and "slot 2" not in res["between"]["shown"]["label"], res
    assert res["between"]["shown"]["value"] == "LR-MDB-1", res
    assert res["calls"] == 2, res
    assert res["bodies"][1] == [{"location": "LR-MDB-1", "picked_slot": "3", "expected_feed": "XL-3"}], res


def test_a_create_onto_a_printer_row_opens_the_printer_picker_first(tmp_path):
    """XL is a printer, not a toolhead: Save opens its picker and sends the head
    chosen there (the server used to refuse XL outright, creating nothing)."""
    res = _run(tmp_path, PICKER, """
creating(1, 'XL');
setShown('XL', 'XL (XL)');
window.__picks = [headPick('XL-2', { feeds: [] })];
answerFor({ '/api/create_inventory_wizard': [{ success: true, created_spools: [501], placed: { '501': 'XL-2' },
            unplaced: [], location_results: { '501': { status: 'success', failures: {} } },
            placement_requests: { '501': { location: 'XL-2' } }, placements_ok: true }] });
await window.wizardSubmit();
await __settle(120);
return { calls: window.__pickerCalls.map(c => c.location), sent: posts('/api/create_inventory_wizard'),
         shown: shown() };
""", setup=SETUP)
    assert res["calls"] == ["XL"], res
    [sent] = res["sent"]
    assert sent["spool_data"]["location"] == "XL-2", sent
    # Group 51.6: the head was shown empty, so a spool loaded there before Save is refused.
    assert sent["placements"] == [{"location": "XL-2", "record_source": "", "expected_residents": []}], sent
    assert res["shown"]["value"] == "XL", "the used head pick leaves the printer in the field for the next create"


def test_an_edit_into_another_box_opens_the_picker_but_an_unchanged_box_does_not(tmp_path):
    """Edit: the Location changed to a box (typed / Tab) opens the picker; a
    spool already in that box saves without one (that half is a control: the
    base never opened a picker at Save)."""
    res = _run(tmp_path, PICKER, """
editing(57, 'LR-MDB-1');
wizardState.editSpoolLocation = 'CR-SHELF';
window.__picks = [slotPick('2', 'XL-2')];
answerFor({ '/api/edit_spool_wizard': [{ success: true, spool_id: 57 }, { success: true, spool_id: 57 }] });
await window.wizardSubmit();
await __settle(80);
const moved = { calls: window.__pickerCalls.length, body: posts('/api/edit_spool_wizard')[0] };
editing(57, 'LR-MDB-1');
wizardState.editSpoolLocation = 'LR-MDB-1';
wizardState.pendingPlacement = null;
await window.wizardSubmit();
await __settle(80);
return { moved, calls: window.__pickerCalls.length, body: posts('/api/edit_spool_wizard')[1] };
""", setup=SETUP)
    assert res["moved"]["calls"] == 1 and res["moved"]["body"]["picked_slot"] == "2", res["moved"]
    assert res["calls"] == 1 and "picked_slot" not in res["body"], res


# ---- wizard-not-moved-drops-to-buffer ----------------------------------------------------

SWAPPED = [{"id": 60, "display": "#60", "filed_to": "CR-CT-2-R2"}]


def test_a_swapped_out_spool_reaches_the_buffer_when_the_move_did_not_land(tmp_path):
    """The reviewers' probe (page half): the Swap took #60 out of CR-MDB-1 slot 2
    into the scan buffer, then Spoolman rejected #57's own write."""
    answer = {"success": False, "spool_saved": True, "location_moved": False,
              "msg": "Saved your other changes, but #57 was not moved to CR-MDB-1: 400: rejected by test.",
              "location_result": {"status": "success", "failures": {"57": "400: rejected by test"},
                                  "to_buffer": SWAPPED}, "to_buffer": SWAPPED}
    res = _run(tmp_path, SAVE, """
editing(57, 'CR-MDB-1');
state.heldSpools = [];
wizardState.pendingPlacement = { location: 'CR-MDB-1', slot: '2', expected_feed: '', swap: true };
answerFor({ '/api/edit_spool_wizard': [__ANSWER__] });
await window.wizardSubmit();
await __settle(80);
return { held: state.heldSpools.map(s => s.id), toasts: toasts().map(t => t.msg) };
""".replace("__ANSWER__", _js(answer)))
    assert res["held"] == [60], ("the swapped-out spool never reached this page's buffer", res)
    assert "✋ #60 → your buffer (filed back in CR-CT-2-R2)" in res["toasts"], res["toasts"]


def test_a_swapped_out_spool_reaches_the_buffer_while_the_move_asks(tmp_path):
    asked = {"success": False, "spool_saved": True, "location_moved": False, "msg": "FCC has to ask first",
             "to_buffer": SWAPPED,
             "location_result": dict(FED, target="LR-MDB-1", slot_picked=False, feed="XL-1", can_load=True,
                                     leaving=[], to_buffer=SWAPPED)}
    res = _run(tmp_path, SAVE, """
editing(57, 'LR-MDB-1');
state.heldSpools = [];
answerFor({ '/api/edit_spool_wizard': [__ASKED__] });
await window.wizardSubmit();
await __settle(80);
return { held: state.heldSpools.map(s => s.id), asking: html().length };
""".replace("__ASKED__", _js(asked)))
    assert res["asking"] == 1 and res["held"] == [60], res


# ---- wizard-refused-pick-resent ----------------------------------------------------------

TAKEN_MSG = ("Saved your other changes, but #57 was not moved to LR-MDB-1: LR-MDB-1 slot 2 was taken by #77 while "
             "you were deciding, so nothing moved — try again.")
TAKEN = {"success": False, "spool_saved": True, "location_moved": False, "msg": TAKEN_MSG, "pick_refused": True,
         "location_result": {"status": "error", "blocked_reason": "picked_slot_taken",
                             "msg": "Not moved: LR-MDB-1 slot 2 was taken by #77 while you were deciding, "
                                    "so nothing moved — try again.",
                             "failures": {"57": "LR-MDB-1 slot 2 was taken by #77"}}}
GHOST_MSG = ("Saved your other changes, but #57 was not moved to LR-MDB-1: LR-MDB-1 slot 2 still holds #60, loaded "
             "on XL-3, while the slot feeds XL-2: take #60 off XL-3 first, so nothing moved.")
GHOST = {"success": False, "spool_saved": True, "location_moved": False, "msg": GHOST_MSG, "pick_refused": True,
         "location_result": {"status": "success", "failures": {"57": GHOST_MSG.split(": ", 1)[1]}}}


@pytest.mark.parametrize("refused", [TAKEN, dict(TAKEN, pick_refused=None), GHOST],
                         ids=["picked_slot_taken", "blocked_reason-only", "ghost-claim"])
def test_a_refused_held_pick_is_dropped_and_not_sent_again(tmp_path, refused):
    """The reviewers' probe: the pick was refused (slot 2 taken meanwhile; or the
    slot still claimed by a deployed spool, which only the server's
    `pick_refused` names), and every Save re-sent it to the same refusal."""
    refused = {k: v for k, v in refused.items() if v is not None}
    res = _run(tmp_path, SAVE, """
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'XL-2', via: 'LR-MDB-1',
                                 label: 'LR-MDB-1 slot 2' };
answerFor({ '/api/edit_spool_wizard': [__REFUSED__, __REFUSED__] });
await window.wizardSubmit();
await __settle(80);
const first = { status: status(), disabled: submitDisabled(), pending: wizardState.pendingPlacement,
                toasts: toasts().map(t => t.msg) };
await window.wizardSubmit();
await __settle(80);
return { first, bodies: posts('/api/edit_spool_wizard') };
""".replace("__REFUSED__", _js(refused)))
    first = res["first"]
    assert first["pending"] is None and first["disabled"] is False, first
    assert "Pick a slot again: Save opens the picker for LR-MDB-1." in first["status"], first
    assert any(t.endswith("Pick a slot again: Save opens the picker for LR-MDB-1.") for t in first["toasts"]), first
    second = res["bodies"][1]
    assert "picked_slot" not in second and "expected_feed" not in second, ("re-sent the refused pick", second)


def test_after_a_refused_pick_save_opens_the_picker_again(tmp_path):
    res = _run(tmp_path, PICKER, """
editing(57, 'LR-MDB-1');
wizardState.editSpoolLocation = 'CR-SHELF';
setShown('LR-MDB-1', 'LR box (LR-MDB-1) — LR-MDB-1 slot 2');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'XL-2', via: 'LR-MDB-1',
                                 label: 'LR-MDB-1 slot 2' };
answerFor({ '/api/edit_spool_wizard': [__TAKEN__, { success: true, spool_id: 57 }] });
await window.wizardSubmit();
await __settle(80);
const between = shown();
window.__picks = [slotPick('3', 'XL-3')];
await window.wizardSubmit();
await __settle(80);
return { between, calls: window.__pickerCalls.map(c => c.location), second: posts('/api/edit_spool_wizard')[1] };
""".replace("__TAKEN__", _js(TAKEN)), setup=SETUP)
    assert res["between"]["value"] == "LR-MDB-1" and "slot 2" not in res["between"]["label"], res
    assert res["calls"] == ["LR-MDB-1"], res
    assert res["second"]["picked_slot"] == "3" and res["second"]["expected_feed"] == "XL-3", res["second"]


def test_a_refused_head_source_goes_back_to_the_printers_picker(tmp_path):
    """The Printer picker's "came from" LR-MDB-1 slot 2 was refused
    (record_source): the field goes back to XL, so Save opens XL's picker."""
    refused = {"success": False, "spool_saved": True, "location_moved": False,
               "msg": "Saved your other changes, but #57 was not moved to XL-3: LR-MDB-1 slot 2 holds #77, so #57 "
                      "can't be recorded as coming from it.",
               "location_result": {"status": "error", "blocked_reason": "record_source", "msg": "Not moved",
                                   "failures": {"57": "x"}}}
    res = _run(tmp_path, PICKER, """
editing(57, 'XL-3');
wizardState.editSpoolLocation = 'CR-SHELF';
setShown('XL-3', 'XL-3 (via XL)');
wizardState.pendingPlacement = { location: 'XL-3', record_source: { box: 'LR-MDB-1', slot: '2' }, via: 'XL',
                                 label: 'XL-3' };
answerFor({ '/api/edit_spool_wizard': [__REFUSED__, { success: true, spool_id: 57 }] });
await window.wizardSubmit();
await __settle(80);
const between = shown();
const said = status();
window.__picks = [headPick('XL-3', { feeds: [] })];
await window.wizardSubmit();
await __settle(120);
return { between, said, calls: window.__pickerCalls.map(c => c.location),
         second: posts('/api/edit_spool_wizard')[1] };
""".replace("__REFUSED__", _js(refused)), setup=SETUP)
    assert res["between"]["value"] == "XL", res
    assert "Pick a toolhead again: Save opens the picker for XL." in res["said"], res["said"]
    assert res["calls"] == ["XL"], res
    assert res["second"]["spool_data"]["location"] == "XL-3" and res["second"]["record_source"] == "", res["second"]


def test_a_refusal_that_isnt_about_the_pick_keeps_it(tmp_path):
    """Control (passes on the base too): Spoolman rejected the write. Saving again
    may work, so the second Save sends the same pick."""
    refused = {"success": False, "spool_saved": True, "location_moved": False,
               "msg": "Saved your other changes, but #57 was not moved to LR-MDB-1: 400: rejected by test.",
               "location_result": {"status": "success", "failures": {"57": "400: rejected by test"}}}
    res = _run(tmp_path, SAVE, """
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'XL-2', via: 'LR-MDB-1' };
answerFor({ '/api/edit_spool_wizard': [__REFUSED__, __REFUSED__] });
await window.wizardSubmit();
await __settle(80);
await window.wizardSubmit();
await __settle(80);
return { bodies: posts('/api/edit_spool_wizard').map(b => b.picked_slot), status: status() };
""".replace("__REFUSED__", _js(refused)))
    assert res["bodies"] == ["2", "2"], res
    assert "again: Save opens the picker" not in res["status"], res


# ---- wizard-loop-undo-buffer-top ---------------------------------------------------------

def test_the_per_spool_loop_places_as_wizard_create_not_buffer(tmp_path):
    """performContextAssign's own moves are 'buffer' moves; Undo of one puts the
    spool at the TOP of the scan buffer (the next toolhead scan loads it). These
    new spools were never in the buffer. Asserted on what wizardPlaceRemaining
    passes (a stub performContextAssign): inv_cmd.js gains `opts.origin`."""
    res = _run(tmp_path, SAVE, """
const calls = [];
globalThis.performContextAssign = (tid, slot, heads, ids, picked, opts) => {
  calls.push({ tid, ids, picked, origin: opts && opts.origin });
  opts.onOutcome({ outcome: 'moved' });
};
window.placeOneWithPicker = async ({ loc, sid, send }) => {
  const out = await new Promise((resolve) => send({ location: loc, picked_slot: '3', expected_feed: '' }, resolve));
  return Object.assign({ placement: {} }, out);
};
await window.wizardPlaceRemaining({ spoolIds: [502, 503], location: 'LR-MDB-1',
                                    placement: { location: 'LR-MDB-1', via: 'LR-MDB-1' } });
return { calls };
""")
    assert [c["ids"] for c in res["calls"]] == [[502], [503]], res
    assert [c["origin"] for c in res["calls"]] == ["wizard_create", "wizard_create"], res


# ---- wizard-create-cancel-silent ---------------------------------------------------------

ASKED_PRINTING = {"status": "requires_confirm", "confirm_type": "active_print",
                  "active_prints": [{"toolhead": "XL-3", "printer_name": "XL", "state": "PRINTING",
                                     "role": "destination", "spools": [501]}],
                  "active_print": {"toolhead": "XL-3", "printer_name": "XL", "state": "PRINTING"},
                  "fed_heads": [], "can_store": False, "target": "XL-3", "target_slot": None, "slot_picked": False,
                  "feed": None, "can_load": False, "leaving": [], "spools": [501],
                  "msg": "XL is PRINTING — moving a spool here will disrupt the print. Continue?"}


def test_a_cancelled_create_placement_says_the_new_spool_is_unassigned(tmp_path):
    """The reviewers' probe: the new spool's placement asked (XL is printing) and
    Derek cancelled. #501 exists, Unassigned, and nothing said so."""
    created = {"success": True, "filament_id": 7, "created_spools": [501], "placed": {}, "unplaced": [501],
               "placements_ok": False, "location_results": {"501": ASKED_PRINTING},
               "placement_requests": {"501": {"location": "XL-3"}},
               "warning": "#501 was created but not placed in XL-3, so it is Unassigned: FCC has to ask first."}
    res = _run(tmp_path, SAVE, """
creating(1, 'XL-3');
wizardState.pendingPlacement = { location: 'XL-3', via: 'XL', label: 'XL-3' };
answerFor({ '/api/create_inventory_wizard': [__CREATED__] });
await window.wizardSubmit();
await __settle(80);
const shownQ = html().pop();
await click('.fcc-apc-no');
await __settle(80);
return { shownQ, all: toastLog, moves: posts('/api/smart_move').length };
""".replace("__CREATED__", _js(created)))
    assert "XL is PRINTING" in res["shownQ"] and res["moves"] == 0, res
    said = [t for t in res["all"] if "#501" in t["msg"] and "Unassigned" in t["msg"]]
    assert len(said) == 1, res["all"]
    assert said[0]["msg"] == "#501 was created and stays Unassigned: scan or Force Location it into place.", said
    assert said[0]["duration"] >= 7000, said


# ---- wizard-create-question-drops-nostore ------------------------------------------------

def test_the_first_new_spools_question_keeps_the_pickers_no_store(tmp_path):
    """The picker's "Put it in slot 1" over a stale record held noStore: the
    engine refuses a store there, so the question offers no "Just store it"."""
    question = dict(FED, spools=[501], target="LR-MDB-1", slot_picked=False, feed="XL-1", can_load=True, leaving=[])
    created = {"success": True, "filament_id": 7, "created_spools": [501], "placed": {}, "unplaced": [501],
               "placements_ok": False, "location_results": {"501": question},
               "placement_requests": {"501": {"location": "LR-MDB-1", "slot": "1", "expected_feed": "XL-1"}}}
    res = _run(tmp_path, SAVE, """
creating(1, 'LR-MDB-1');
wizardState.pendingPlacement = { location: 'LR-MDB-1', slot: '1', expected_feed: 'XL-1', noStore: true,
                                 via: 'LR-MDB-1', label: 'LR-MDB-1 slot 1' };
answerFor({ '/api/create_inventory_wizard': [__CREATED__] });
await window.wizardSubmit();
await __settle(80);
return { q: html().pop() };
""".replace("__CREATED__", _js(created)))
    assert "Load #57 onto XL-1?" in res["q"] and "Load it instead" in res["q"], res["q"]
    assert "Just store it" not in res["q"], res["q"]
