"""Group 40's final review (2026-10-19): the browser doors' fixes, under node's
`vm` (no browser, no container). inv_cmd.js / inv_loc_mgr.js run for real; the
picker (window.openSlotPicker) is a stub that answers what a user picked, and
the server's answers are canned.

Pinned here:
  - BD-1: "Record it as coming from…" settles when its host modal closes, so the
    picker loop's lock is released (the next box label opens its picker), and a
    question that steps back never re-opens the picker over a closed modal;
  - BD-2: a slower scanner's Enter in that dialog is left to the scan (a slot
    label still in the scan buffer), which then picks the scanned slot; a
    person's Enter (empty buffer) still answers the focused button;
  - BD-3: a spool whose own PolyDryer follows it head to head is not asked where
    it came from (the model's `spool_keeps_trail`), and an answer the engine
    kept a trail over is named in the toast;
  - BD-4: the Location Manager grid words its choice from the slot's spool: a
    DEPLOYED card on the slot's own head offers one "Swap it out", one on
    another head offers nothing, a stale record "Put it in slot N", a stored
    spool says Swap may leave it Unassigned;
  - BD-6: a held-off scan's hint names the buttons on screen (no "Just store it"
    on a question without one), and "No box" has its own scan code when a slot
    is pre-selected;
  - the two contracts the other review fixes use: `performContextAssign`'s
    `opts.origin` and `doAssign`'s `options.pickedSlot`.

HEAD proof: every test here fails on 7976b72 (see the commit message).
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import LM, PRELUDE, SCAN
from test_printer_picker_js import DONE, FREE_FEED, SETUP

TWO_FREE = FREE_FEED + [{"box": "LR-MDB-2", "slot": "1", "spool": None, "claimed_by": None, "free": True}]
RESIDENT = {"id": 99, "display": "#99", "from": "LR-MDB-1 slot 2", "goes": ""}

# The real overlay_mount.js host cascade: Bootstrap drops `.show` from the modal,
# then fires hidden.bs.modal, which removes every overlay mounted on it (DOM
# only: its onEscape is never called).
HOST_CASCADE = r"""
const mm = document.getElementById('manageModal');
mm.classList.add('show');
const hostLs = [];
mm.addEventListener = (t, fn) => hostLs.push([t, fn]);
mm.removeEventListener = (t, fn) => { const i = hostLs.findIndex(([a, b]) => a === t && b === fn); if (i >= 0) hostLs.splice(i, 1); };
const __m2 = window.mountOverlay;
window.mountOverlay = (opts) => {
  const h = __m2(opts);
  h.element.isConnected = true;
  const orig = h.cleanup;
  let done = false;
  h.cleanup = () => { if (done) return; done = true; h.element.isConnected = false; orig(); };
  if (opts.host && typeof opts.host.addEventListener === 'function') {
    opts.host.addEventListener('hidden.bs.modal', () => h.cleanup());
  }
  return h;
};
const hideHost = async () => {
  mm.classList.remove('show');
  hostLs.filter(([t]) => t === 'hidden.bs.modal').forEach(([, fn]) => fn());
  await __settle(150);
};
"""


def _js(value):
    return json.dumps(value)


def _scan(tmp_path, body, host=False):
    res = run_js(tmp_path, SCAN, PRELUDE + SETUP + (HOST_CASCADE if host else "") + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


# --- BD-1 ------------------------------------------------------------------------------

def test_record_source_closed_with_its_host_ends_the_loop_and_frees_the_box_label(tmp_path):
    res = _scan(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
const asked = html().filter(h => h.includes('Record #57 as coming from')).length;
await hideHost();
const openQuestions = (window._fccOpenMoveQuestions || []).length;
window._fccLastLocScan = null;
window.__picks = [];
await scanLoc('LR-MDB-1');
return {{ asked, openQuestions, calls: window.__pickerCalls.map(c => c.location),
         posts: posts('/api/smart_move'), toasts: toasts().map(t => t.msg), held: state.heldSpools.map(s => s.id) }};
""", host=True)
    assert res["asked"] == 1, res
    assert res["openQuestions"] == 0, res
    assert res["posts"] == [] and res["held"] == [57], res
    assert not any("Still placing your buffer" in t for t in res["toasts"]), res["toasts"]
    # The box label opened its own picker: the first loop had ended.
    assert res["calls"] == ["XL", "LR-MDB-1"], res["calls"]


def test_a_closed_host_never_reopens_the_picker_after_a_question_steps_back(tmp_path):
    """The head-load question settles on host close (confirmActivePrint's own
    listener) and steps back; the picker is not opened again over a modal that
    has gone."""
    res = _scan(tmp_path, f"""
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1', resident: {_js(RESIDENT)}, residents: [{_js(RESIDENT)}] }})];
await scanLoc('XL');
const asked = html().filter(h => h.includes('Load #57 onto XL-2?')).length;
await hideHost();
return {{ asked, calls: window.__pickerCalls.length, posts: posts('/api/smart_move'),
         held: state.heldSpools.map(s => s.id) }};
""", host=True)
    assert res["asked"] == 1, res
    assert res["calls"] == 1, res
    assert res["posts"] == [] and res["held"] == [57], res


# --- BD-2 ------------------------------------------------------------------------------

SLOW_ENTER = r"""
const m = lastMount();
const none = m.el.querySelector('.fcc-rs-none');
const cancel = m.el.querySelector('.fcc-rs-cancel');
none.click = () => none.onclick && none.onclick();
cancel.click = () => cancel.onclick && cancel.onclick();
m.el.querySelectorAll = () => [none, cancel];
document.activeElement = none;
let stopped = false;
const enter = async () => {
  m.ls.filter(([t]) => t === 'keydown').forEach(([, fn]) => fn({ key: 'Enter', shiftKey: false,
    preventDefault() {}, stopPropagation() { stopped = true; } }));
  await __settle(200);
};
"""


def test_a_slower_scanners_enter_is_left_to_the_scan_which_picks_the_scanned_slot(tmp_path):
    res = _scan(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(TWO_FREE)} }})];
await scanLoc('XL');
const focus = lastMount().opts.initialFocus;
{SLOW_ENTER}
// A scanner that took ~0.9 s over the slot label: its Enter arrives now.
state.scanBuffer = 'LOC:LR-MDB-1:SLOT:2';
state.scanStartTime = Date.now() - 900;
await enter();
const before = posts('/api/smart_move').length;
// The accumulator submits the scan it owned.
state.scanBuffer = '';
window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode');
await __settle(250);
return {{ focus, stopped, before, posts: posts('/api/smart_move') }};
""")
    assert res["focus"] == ".fcc-rs-none", res
    assert res["stopped"] is False and res["before"] == 0, res
    [post] = res["posts"]
    assert post["location"] == "XL-2" and post["record_source"] == {"box": "LR-MDB-1", "slot": "2"}, post


def test_a_persons_enter_still_answers_the_focused_button(tmp_path):
    res = _scan(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(TWO_FREE)} }})];
await scanLoc('XL');
{SLOW_ENTER}
state.scanBuffer = '';
await enter();
return {{ stopped, posts: posts('/api/smart_move') }};
""")
    assert res["stopped"] is True, res
    [post] = res["posts"]
    assert post["record_source"] == "", post


# --- BD-3 ------------------------------------------------------------------------------

def test_a_polydryer_spool_moving_head_to_head_is_not_asked_where_it_came_from(tmp_path):
    res = _scan(tmp_path, f"""
state.heldSpools = [{{ id: 50, display: '#50', location: 'XL-2' }}];
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-3', {{ spool_location: 'XL-2', spool_keeps_trail: 'PM-DB-2',
                                 feeds: [{{ box: 'LR-MDB-1', slot: '3', spool: null, claimed_by: null, free: true }}] }})];
await scanLoc('XL');
return {{ asked: html().filter(h => h.includes('Record #50 as coming from')).length, posts: posts('/api/smart_move') }};
""")
    assert res["asked"] == 0, res
    [post] = res["posts"]
    assert post["location"] == "XL-3" and "record_source" not in post, post


def test_an_answer_the_engine_kept_a_trail_over_is_named_in_the_toast(tmp_path):
    answer = dict(DONE, record_source_ignored=True, record_source_kept="PM-DB-2")
    res = _scan(tmp_path, f"""
state.heldSpools = [{{ id: 50, display: '#50', location: 'XL-2' }}];
answerWith('/api/smart_move', [{_js(answer)}]);
window.__picks = [head('XL-3', {{ spool_location: 'XL-2',
                                 feeds: [{{ box: 'LR-MDB-1', slot: '3', spool: null, claimed_by: null, free: true }}] }})];
await scanLoc('XL');
await click('.fcc-rs-opt[data-rs-i="0"]');
await __settle(200);
return {{ toasts: toasts().map(t => t.msg) }};
""")
    assert "✅ #50 → XL-3 (its home stays PM-DB-2)" in res["toasts"], res["toasts"]
    assert not any(t.startswith("Assigned") for t in res["toasts"]), res["toasts"]


# --- BD-6 ------------------------------------------------------------------------------

def test_a_held_off_scans_hint_names_only_the_buttons_on_screen(tmp_path):
    res = _scan(tmp_path, f"""
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1', resident: {_js(RESIDENT)}, residents: [{_js(RESIDENT)}] }})];
await scanLoc('XL');
const hint = window._fccOpenMoveQuestion && window._fccOpenMoveQuestion.hint;
window.processScan('ID:58', 'barcode');
await __settle(150);
return {{ hint, toasts: toasts().map(t => t.msg) }};
""")
    assert res["hint"] == "Answer the question on screen first: Load it instead or Cancel", res
    assert "Answer the question on screen first: Load it instead or Cancel" in res["toasts"], res["toasts"]
    assert not any("Just store it" in t for t in res["toasts"]), res["toasts"]


def test_the_three_ways_hint_is_unchanged(tmp_path):
    res = run_js(tmp_path, SCAN, PRELUDE + r"""
window.confirmActivePrint({ title: 'Load #57 onto XL-1?', msg: 'x', printing: false,
  onConfirm: () => {}, onStore: () => {}, onCancel: () => {} });
return { hint: window._fccOpenMoveQuestion.hint };
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["hint"] == "Answer the question on screen first: Load it instead, Just store it, or Cancel", res


def test_no_box_has_its_own_scan_code_when_a_slot_is_preselected(tmp_path):
    res = _scan(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
const focus = lastMount().opts.initialFocus;
const sid = sidOf();
window.processScan('CMD:STORE:' + sid, 'barcode');
await __settle(250);
return {{ focus, sid, posts: posts('/api/smart_move') }};
""")
    assert res["focus"] == '.fcc-rs-opt[data-rs-i="0"]' and res["sid"], res
    [post] = res["posts"]
    assert post["location"] == "XL-2" and post["record_source"] == "", post


# --- the contracts the Return and wizard fixes use -------------------------------------

def test_perform_context_assign_sends_the_callers_origin(tmp_path):
    res = _scan(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}, {_js(DONE)}]);
performContextAssign('LR-MDB-1', null, [], [57], '3', {{ origin: 'wizard_create' }});
await __settle(200);
state.heldSpools = [{{ id: 58, display: '#58' }}];
performContextAssign('LR-MDB-1', null, [], [58], '4');
await __settle(200);
return {{ posts: posts('/api/smart_move') }};
""")
    first, second = res["posts"]
    assert first["origin"] == "wizard_create" and first["picked_slot"] == "3", first
    assert second["origin"] == "buffer", second


def _grid(tmp_path, body):
    rows = [
        {"LocationID": "XL", "Name": "XL", "Type": "Printer",
         "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
        *[{"LocationID": f"XL-{n}", "Name": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1"} for n in (1, 2, 3)],
        {"LocationID": "LR-MDB-1", "Name": "LR box", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "4": "PRINTER:XL"}}},
        {"LocationID": "CR-CT-2-R1", "Name": "Cart row", "Type": "Cart Row", "Max Spools": "0"},
    ]
    res = run_js(tmp_path, LM, PRELUDE + f"""
state.allLocations = {_js(rows)};
document.getElementById('manage-loc-id').value = 'LR-MDB-1';
document.getElementById('manageModal').classList.add('show');
answerWith('/api/manage_contents', [{{ status: 'success', failures: {{}} }}]);
const prompt = () => ({{ title: document.getElementById('action-title').innerText,
  msg: document.getElementById('action-msg').innerHTML,
  buttons: (document.getElementById('action-buttons').innerHTML.match(/modal-action-btn">([^<]*)</g) || [])
    .map(b => b.replace(/^.*">/, '').replace(/<$/, '')) }});
""" + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def test_doassign_picked_slot_is_sent_as_picked_slot_never_an_overwrite(tmp_path):
    res = _grid(tmp_path, r"""
window.doAssign('LR-MDB-1', 42, null, null, { autoDeploy: false, pickedSlot: 3 });
await __settle(200);
return { posts: posts('/api/manage_contents'), toasts: toasts().map(t => t.msg) };
""")
    [post] = res["posts"]
    assert post["slot"] is None and post["picked_slot"] == "3" and post["auto_deploy"] is False, post
    assert "↩️ #42 → LR-MDB-1 slot 3" in res["toasts"], res["toasts"]


# --- BD-4 ------------------------------------------------------------------------------

def test_grid_deployed_card_on_its_own_head_offers_one_swap_it_out(tmp_path):
    res = _grid(tmp_path, r"""
state.heldSpools = [{ id: 57, display: '#57' }];
state.currentGrid = { 1: { id: 99, display: '#99', is_ghost: true, deployed_to: 'XL-1', location: 'LR-MDB-1' } };
window.handleSlotInteraction(1);
const p = prompt();
state.modalCallbacks[0]();
await __settle(200);
return { p, posts: posts('/api/manage_contents') };
""")
    assert res["p"]["title"] == "Slot Occupied", res["p"]
    assert "#99 is loaded on XL-1: it comes off into your scan buffer" in res["p"]["msg"], res["p"]
    assert "without a slot" not in res["p"]["msg"], res["p"]
    assert res["p"]["buttons"] == ["Swap it out", "Cancel"], res["p"]
    [post] = res["posts"]
    assert post["location"] == "LR-MDB-1" and post["slot"] == 1 and "swap" not in post, post


def test_grid_deployed_card_on_another_head_offers_nothing(tmp_path):
    res = _grid(tmp_path, r"""
state.heldSpools = [{ id: 57, display: '#57' }];
state.currentGrid = { 1: { id: 99, display: '#99', is_ghost: true, deployed_to: 'XL-3', location: 'LR-MDB-1' } };
window.handleSlotInteraction(1);
const p = prompt();
state.modalCallbacks[0]();
await __settle(150);
return { p, posts: posts('/api/manage_contents') };
""")
    assert "#99 is loaded on XL-3, while the slot feeds XL-1" in res["p"]["msg"], res["p"]
    assert res["p"]["buttons"] == ["OK"], res["p"]
    assert res["posts"] == [], res


def test_grid_stale_record_is_put_in_without_moving_it(tmp_path):
    res = _grid(tmp_path, r"""
state.heldSpools = [{ id: 57, display: '#57' }];
state.currentGrid = { 1: { id: 60, display: '#60', is_ghost: true, deployed_to: 'CR-CT-2-R1', location: 'LR-MDB-1' } };
window.handleSlotInteraction(1);
const p = prompt();
state.modalCallbacks[0]();
await __settle(200);
return { p, posts: posts('/api/manage_contents') };
""")
    assert "record still names slot 1, though it is on CR-CT-2-R1" in res["p"]["msg"], res["p"]
    assert res["p"]["buttons"] == ["Put it in slot 1", "Cancel"], res["p"]
    [post] = res["posts"]
    assert post["slot"] == 1 and "swap" not in post, post


def test_grid_stored_spool_says_swap_may_leave_it_unassigned(tmp_path):
    res = _grid(tmp_path, r"""
state.heldSpools = [{ id: 57, display: '#57' }];
state.currentGrid = { 2: { id: 77, display: '#77', location: 'LR-MDB-1' } };
window.handleSlotInteraction(2);
const p = prompt();
state.modalCallbacks[0]();
await __settle(200);
return { p, posts: posts('/api/manage_contents') };
""")
    assert res["p"]["buttons"] == ["Swap", "Overwrite", "Cancel"], res["p"]
    assert "Unassigned if FCC has no record of that" in res["p"]["msg"], res["p"]
    assert "#77 stays in LR-MDB-1 without a slot" in res["p"]["msg"], res["p"]
    [post] = res["posts"]
    assert post["slot"] == 2 and post["swap"] is True, post


# --- BD-5 ------------------------------------------------------------------------------

def test_the_deposit_card_on_a_printer_view_opens_the_picker_once_for_the_top_spool(tmp_path):
    """The Location Manager's DEPOSIT card on XL (a Printer row that isn't its own
    head) places only the buffer's top spool, through the Printer picker, as
    scanning XL's label does for each spool."""
    res = run_js(tmp_path, ["inv_core.js", "ui_builder.js", "inv_cmd.js", "inv_loc_mgr.js"],
                 PRELUDE + SETUP + f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1' }})];
const card = _buildDepositCard('XL');
card.onclick();
await __settle(300);
return {{ calls: window.__pickerCalls.map(c => [c.location, c.spool]), posts: posts('/api/smart_move'),
         assigns: posts('/api/manage_contents'), held: state.heldSpools.map(s => s.id) }};
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["calls"] == [["XL", 57]], res["calls"]
    [post] = res["posts"]
    assert post["location"] == "XL-2" and post["spools"] == [57], post
    assert res["assigns"] == [] and res["held"] == [58], res


# --- the Return fixer's integration notes 2 and 3 --------------------------------------

def test_a_stale_trails_return_into_a_taken_slot_says_what_happened(tmp_path):
    """The DEPLOYED card's stale-trail ↩️ (R1's fallback) sends its slot as
    `pickedSlot`; when another spool holds it, the engine's "taken while you were
    deciding … try again" is wrong (nobody was deciding, and a retry fails the
    same way), so the toast says what happened and how to fix the record."""
    taken = {"status": "error", "blocked_reason": "picked_slot_taken",
             "msg": "Not moved: LR-MDB-1 slot 1 was taken by #57 while you were deciding, so nothing moved — try again.",
             "failures": {"60": "LR-MDB-1 slot 1 was taken by #57"}}
    res = _grid(tmp_path, f"""
answerWith('/api/manage_contents', [{_js(taken)}]);
window.doAssign('LR-MDB-1', 60, null, null, {{ autoDeploy: false, pickedSlot: '1' }});
await __settle(200);
return {{ toasts: toasts() }};
""")
    msgs = [t["msg"] for t in res["toasts"]]
    assert any(m.startswith("❌ #60 wasn't put back in LR-MDB-1 slot 1, the slot its record names") for m in msgs), msgs
    assert not any("while you were deciding" in m for m in msgs), msgs


def test_after_a_move_the_view_on_screen_repaints(tmp_path):
    """A DEPLOYED card's ↩️ in a Room view puts the spool back into a box of that
    Room; the Room is the view to repaint (a refresh of the box was ignored)."""
    res = _grid(tmp_path, r"""
const refreshed = [];
window.refreshManageView = (id) => { refreshed.push(id); return true; };
document.getElementById('manage-loc-id').value = 'LR';
window.doAssign('LR-MDB-1', 60, null, null, { autoDeploy: false, pickedSlot: '1' });
await __settle(250);
return { refreshed };
""")
    assert res["refreshed"] == ["LR"], res


# --- the move-pipeline follow-ups' last E2E debt (item 6): Return's printer-view target ---

def test_return_from_a_printer_view_skips_a_head_that_only_lists_a_ghost(tmp_path):
    """↩️ Return on a Printer row's view (XL) acts on the first head that holds a
    spool ON it (`_resolveReturnTarget`); a head whose contents list only a ghost
    (a spool deployed elsewhere) is skipped. Unpinned since the 2026-09-12 diff
    review (the move-pipeline follow-ups, item 6)."""
    from test_return_slot_choice_js import PRELUDE as RETURN_PRELUDE, QS, _plan
    plan = _plan(toolhead="XL-2", active_toolhead="XL-2", requested="XL-2", box="LR-MDB-1", slot="2")
    res = run_js(tmp_path, QS, RETURN_PRELUDE + f"""
window.__contents = {{
  'XL-1': [{{ id: 99, is_ghost: true, deployed_to: 'XL-3', location: 'LR-MDB-1' }}],
  'XL-2': [{{ id: 77, location: 'XL-2' }}],
}};
window.__plan = {{ body: {_js(plan)} }};
await openHead('XL');
return out();
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["posts"] and res["posts"][0]["toolhead"] == "XL-2" and res["posts"][0]["dry_run"] is True, res["posts"]
