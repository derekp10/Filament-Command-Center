"""Group 51.5-51.7, the browser half — every door sends what it showed, under
node's `vm` (no browser, no container): the REAL inv_cmd.js, inv_quickswap.js,
inv_loc_mgr.js and inv_wizard.js, a stub picker and canned server answers.

  - the Printer picker's head pick sends `expected_residents` (what "XL-2 holds
    #99" showed; [] for an empty head), and a `residents_changed` answer opens
    the picker again with a 7 s warning instead of ending the loop;
  - a Swap / Overwrite pick of an occupied slot sends `expected_occupant`, as
    does the Location Manager grid's prompt, whose `occupant_changed` answer is
    a warning that redraws the grid;
  - the Quick-Swap tap sends the card's spool as `expected_spool` and shows the
    server's `quickswap_spool_mismatch`;
  - the wizard keeps both fields on a held choice, and drops a choice the
    server refused for any of the new reasons.

Base proof (52741e6): every test fails there.
"""
from __future__ import annotations

import json
from pathlib import Path

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE, QS, SCAN
from test_printer_picker_js import SETUP
from test_review_fixes_40_final_js import _grid
from test_spoolman_read_load_52_js import run as run_lm

MODULES = Path(__file__).resolve().parent.parent / "static" / "js" / "modules"
DONE = {"status": "success", "failures": {}}


def _js(value):
    return json.dumps(value)


def _picker(tmp_path, body):
    res = run_js(tmp_path, SCAN, PRELUDE + SETUP + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


# ---- 51.6: the Printer picker's head pick ----------------------------------------------------------

def test_a_head_pick_sends_the_head_it_showed_empty(tmp_path):
    res = _picker(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1' }})];
await scanLoc('XL');
return {{ posts: posts('/api/smart_move') }};
""")
    [post] = res["posts"]
    assert post["location"] == "XL-2" and post["expected_residents"] == [], post


def test_a_head_pick_over_a_resident_sends_the_resident_the_question_named(tmp_path):
    resident = {"id": 99, "display": "#99", "from": "LR-MDB-1 slot 2", "goes": "back to LR-MDB-1"}
    res = _picker(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1', resident: {_js(resident)}, residents: [{_js(resident)}] }})];
await scanLoc('XL');
await click('.fcc-apc-yes');
await __settle(200);
return {{ posts: posts('/api/smart_move') }};
""")
    [post] = res["posts"]
    assert post["expected_residents"] == [99], post


def test_a_head_that_changed_since_the_pick_opens_the_picker_again(tmp_path):
    changed = {"status": "error", "blocked_reason": "residents_changed", "failures": {"57": "x"},
               "msg": "Not loaded: XL-2 now holds #77, which wasn't on it when you picked XL-2 (it was empty), "
                      "so #57 was not loaded: pick again."}
    res = _picker(tmp_path, f"""
answerWith('/api/smart_move', [{_js(changed)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1' }})];
await scanLoc('XL');
await __settle(200);
return {{ calls: window.__pickerCalls.length, toasts: toasts(), held: state.heldSpools.map(s => s.id) }};
""")
    assert res["calls"] == 2, res        # the picker opened again (the stub then closed it)
    warn = [t for t in res["toasts"] if "XL-2 now holds #77" in t["msg"]]
    assert warn and warn[0]["type"] == "warning", res["toasts"]
    assert res["held"] == [57], res      # nothing moved: still in the buffer


def test_a_slot_that_changed_since_the_pick_opens_the_picker_again(tmp_path):
    """Review engine-2: step 6's occupant_changed answers status 'success' with
    the spool in `failures` (the engine's real shape), and the picker loop used
    to read that as a failed move (7 s error, loop stopped)."""
    why = "LR-MDB-1 slot 2 holds #78 now, not #77 as when you chose, so nothing moved: look at the slot again"
    changed = {"status": "success", "failures": {"57": why}, "blocked_reason": "occupant_changed"}
    pick = {"kind": "slot", "box": "LR-MDB-1", "slot": "2", "free": False, "via": "key",
            "occupant": {"id": 77, "display": "#77"}, "send": {"slot": "2"}, "expected_feed": "XL-2",
            "choice": "overwrite", "swap": False, "displaced": None, "store_ok": True}
    res = _picker(tmp_path, f"""
answerWith('/api/smart_move', [{_js(changed)}]);
window.__picks = [{_js(pick)}];
await scanLoc('LR-MDB-1');
await __settle(200);
return {{ calls: window.__pickerCalls.length, toasts: toasts(), held: state.heldSpools.map(s => s.id) }};
""")
    assert res["calls"] == 2, res                    # the picker opened again
    assert {"msg": f"⚠️ {why}", "type": "warning"} in res["toasts"], res["toasts"]
    assert not any(t["type"] == "error" for t in res["toasts"]), res["toasts"]
    assert res["held"] == [57], res


# ---- 51.7: Swap / Overwrite in the slot picker and the grid ----------------------------------------

def _slot_pick(choice, free=False):
    occupant = None if free else {"id": 77, "display": "#77"}
    return {"kind": "slot", "box": "LR-MDB-1", "slot": "2", "free": free, "via": "key", "occupant": occupant,
            "send": {"picked_slot": "2"} if free else {"slot": "2"}, "expected_feed": "XL-2",
            "choice": choice, "swap": choice == "swap", "displaced": occupant if choice == "swap" else None,
            "store_ok": True}


def test_a_swap_or_overwrite_pick_sends_the_occupant_it_named(tmp_path):
    res = _picker(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}, {{ id: 59, display: '#59' }}];
window.__picks = [{_js(_slot_pick("swap"))}, {_js(_slot_pick("overwrite"))}, {_js(_slot_pick(None, free=True))}];
await scanLoc('LR-MDB-1');
await __settle(300);
return {{ posts: posts('/api/smart_move') }};
""")
    swap, overwrite, free = res["posts"]
    assert swap["expected_occupant"] == 77 and swap["swap"] is True and swap["slot"] == "2", swap
    assert overwrite["expected_occupant"] == 77 and "swap" not in overwrite, overwrite
    assert "expected_occupant" not in free and free["picked_slot"] == "2", free


def test_the_grids_swap_and_overwrite_send_the_spool_the_prompt_named(tmp_path):
    res = _grid(tmp_path, r"""
state.heldSpools = [{ id: 57, display: '#57' }];
state.currentGrid = { 2: { id: 77, display: '#77', location: 'LR-MDB-1' } };
window.handleSlotInteraction(2);
state.modalCallbacks[0]();
await __settle(200);
state.heldSpools = [{ id: 57, display: '#57' }];
window.handleSlotInteraction(2);
state.modalCallbacks[1]();
await __settle(200);
return { posts: posts('/api/manage_contents') };
""")
    swap, overwrite = res["posts"]
    assert swap["expected_occupant"] == 77 and swap["swap"] is True, swap
    assert overwrite["expected_occupant"] == 77 and "swap" not in overwrite, overwrite


def test_the_grid_shows_a_changed_slot_as_a_warning_and_keeps_the_spool(tmp_path):
    why = "LR-MDB-1 slot 2 holds #78 now, not #77 as when you chose, so nothing moved: look at the slot again"
    res = _grid(tmp_path, f"""
answerWith('/api/manage_contents', [{_js({"status": "success", "failures": {"57": why},
                                          "blocked_reason": "occupant_changed"})}]);
state.heldSpools = [{{ id: 57, display: '#57' }}];
state.currentGrid = {{ 2: {{ id: 77, display: '#77', location: 'LR-MDB-1' }} }};
window.handleSlotInteraction(2);
state.modalCallbacks[0]();
await __settle(200);
return {{ toasts: toasts(), held: state.heldSpools.map(s => s.id) }};
""")
    assert {"msg": f"⚠️ {why}", "type": "warning"} in res["toasts"], res["toasts"]
    assert res["held"] == [57], res


def test_a_doubled_slot_names_both_spools_and_sends_no_occupant(tmp_path):
    """Review browser-2: two stored spools claim slot 2 (the second is drawn
    under Unslotted). The prompt named only the first, and its Overwrite sent
    expected_occupant for it, which the engine refused on every try (the other
    claimant is in the slot too), so the doubled slot could never be sorted out."""
    res = _grid(tmp_path, r"""
window._renderManagePayload('LR-MDB-1', [
  { id: 77, display: '#77', location: 'LR-MDB-1', slot: '2', is_ghost: false },
  { id: 78, display: '#78', location: 'LR-MDB-1', slot: '2', is_ghost: false }]);
state.heldSpools = [{ id: 57, display: '#57' }];
window.handleSlotInteraction(2);
const shown = prompt();
state.modalCallbacks[1]();
await __settle(200);
return { shown, posts: posts('/api/manage_contents') };
""")
    assert "#77 and #78 both claim slot 2" in res["shown"]["msg"], res["shown"]
    assert "Overwrite: #77 and #78 stay in LR-MDB-1 without a slot" in res["shown"]["msg"], res["shown"]
    [overwrite] = res["posts"]
    assert "expected_occupant" not in overwrite and str(overwrite["slot"]) == "2", overwrite


GRID_DOWN = """
window.SpoolCardBuilder = { buildCard: (it) => `CARD#${it.id}` };
state.allLocations = [{ LocationID: 'LR-MDB-1', Type: 'Dryer Box', 'Max Spools': '4', Occupancy: '0/4' }];
state.locationsLoaded = true;
window.renderFeedsSection = () => {};
window.renderQuickSwapSection = () => {};
const prompts = [];
globalThis.promptAction = (title, msg) => { prompts.push(String(msg)); };
window.__respond = (url) => url.startsWith('/api/get_contents?id=LR-MDB-1')
  ? { status: 502, body: { error: "Couldn't read LR-MDB-1 from Spoolman (Read timed out.)." } } : { body: {} };
// The box open before this one left its grid behind.
state.currentGrid = { 2: { id: 77, display: '#77', location: 'LR-MDB-2' } };
window.openManage('LR-MDB-1');
await __settle(60);
document.getElementById('manageModal').classList.add('show');
const grid = Object.keys(state.currentGrid);
state.heldSpools = [{ id: 57, display: '#57' }];
window.handleSlotInteraction(2);
await __settle(60);
return { grid, prompts, toasts: __rec.toasts, logs: __rec.logs,
         adds: __rec.fetches.filter(f => f.url === '/api/manage_contents') };
"""


def test_a_slot_scan_while_the_box_could_not_be_read_moves_nothing(tmp_path):
    """Review browser-5: LR-MDB-1's open couldn't read Spoolman (52.1b's notice
    is up, no cards). The grid still held the LAST box's slots, so CMD:SLOT:2
    offered to swap out #77, a spool of another box."""
    res = run_lm(tmp_path, ["inv_loc_mgr.js"], GRID_DOWN)
    assert res["grid"] == [], res                    # the last box's slots are gone
    assert res["prompts"] == [] and res["adds"] == [], res
    warn = [t for t in res["toasts"] if "Spoolman didn't answer for LR-MDB-1" in t["msg"]]
    assert warn and warn[0]["type"] == "warning" and warn[0]["duration"] >= 7000, res["toasts"]
    assert any(lg["level"] == "WARNING" and "Slot 2 of LR-MDB-1 ignored" in lg["msg"] for lg in res["logs"]), res


# ---- 51.5: the Quick-Swap tap ----------------------------------------------------------------------

def test_the_quickswap_tap_sends_the_cards_spool_and_shows_a_mismatch(tmp_path):
    error = ("LR-MDB-1 slot 3 holds #77 now, not #57, so nothing was loaded onto XL-2. The slots have been "
             "refreshed: tap again if you still want it.")
    res = run_js(tmp_path, QS, PRELUDE + f"""
window.attachConfirmQRs = null;
answerWith('/api/quickswap', [{_js({"action": "quickswap_spool_mismatch", "spool": 77, "expected_spool": 57,
                                    "error": error})}]);
const card = {{ dataset: {{ box: 'LR-MDB-1', slot: '3', toolhead: 'XL-2', spoolId: '57', spoolLabel: '#57' }},
               hasAttribute: () => false, querySelector: () => null }};
window.quickSwapTap(card);
await __settle(150);
const yes = (__overlayEls[__overlayEls.length - 1] || {{ querySelector: () => null }}).querySelector('#fcc-quickswap-yes');
if (yes && yes.onclick) yes.onclick();
await __settle(200);
return {{ posts: posts('/api/quickswap'), toasts: toasts() }};
""")
    assert res["unhandled"] == [], res["unhandled"]
    [post] = res["posts"]
    assert post["expected_spool"] == "57" and post["slot"] == "3", post
    assert {"msg": f"⚠️ {error}", "type": "warning"} in res["toasts"], res["toasts"]


# ---- review engine-3: the Quick-Swap deposit ------------------------------------------------------

def test_a_deposit_says_it_showed_the_slot_empty_and_warns_when_it_was_filled(tmp_path):
    why = "LR-MDB-1 slot 1 was taken by #77 while you were deciding, so nothing moved — try again"
    taken = {"type": "assignment", "action": "assignment_failed", "location": "LR-MDB-1", "slot": "1",
             "spool": 57, "msg": why, "smart_move": {"status": "error", "blocked_reason": "picked_slot_taken",
                                                    "failures": {"57": why}}}
    res = run_js(tmp_path, QS, PRELUDE + f"""
answerWith('/api/identify_scan', [{_js(taken)}]);
window.quickSwapDeposit({{ dataset: {{ box: 'LR-MDB-1', slot: '1', toolhead: 'XL-1' }} }});
await __settle(200);
await click('#fcc-quickswap-yes');
await __settle(200);
return {{ posts: posts('/api/identify_scan'), toasts: toasts(), held: state.heldSpools.map(s => s.id) }};
""")
    assert res["unhandled"] == [], res["unhandled"]
    [post] = res["posts"]
    assert post["shown_empty"] is True and post["text"] == "LOC:LR-MDB-1:SLOT:1", post
    assert {"msg": f"⚠️ {why}", "type": "warning"} in res["toasts"], res["toasts"]
    assert not any(t["type"] == "error" for t in res["toasts"]), res["toasts"]
    assert res["held"] == [57], res


# ---- the wizard's held choice ----------------------------------------------------------------------

def test_the_wizard_keeps_what_the_picker_showed_and_drops_a_choice_refused_for_it(tmp_path):
    res = run_js(tmp_path, ["inv_core.js", "inv_wizard.js"], PRELUDE + r"""
const head = window.wizardPlacementFor('XL-2', { location: 'XL-2', expected_residents: [99] });
const slot = window.wizardPlacementFor('LR-MDB-1', { location: 'LR-MDB-1', slot: '2', swap: true, expected_occupant: 77 });
const refused = ['slot_claimed', 'residents_changed', 'occupant_changed', 'picked_slot_taken', 'head_fed']
  .map(r => [r, window.wizardPickRefused({ location_result: { blocked_reason: r } })]);
return { head, slot, refused };
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["head"] == {"expected_residents": [99]}, res["head"]
    assert res["slot"] == {"slot": "2", "swap": True, "expected_occupant": 77}, res["slot"]
    assert res["refused"] == [["slot_claimed", True], ["residents_changed", True], ["occupant_changed", True],
                              ["picked_slot_taken", True], ["head_fed", False]], res["refused"]


def test_a_wizard_question_whose_replay_finds_the_slot_changed_drops_the_held_pick(tmp_path):
    """Review browser-6: the answered question's replay was refused for
    occupant_changed (a head or slot that changed since the pick), and the held
    pick was kept, so the next Save sent it again and was refused again ("Save
    again to retry"). Now it is dropped, as a first answer's refusal is."""
    resident = {"id": 99, "from": "PM-DB-1", "goes": "back to PM-DB-1"}
    asked = {"status": "requires_confirm", "confirm_type": "head_fed", "target": "LR-MDB-1", "target_slot": "2",
             "slot_picked": False, "feed": "XL-2", "can_load": True, "can_store": True, "leaving": [],
             "spools": [42], "active_prints": [], "active_print": None,
             "fed_heads": [{"toolhead": "XL-2", "printer_name": "XL", "box": "LR-MDB-1", "slot": "2",
                            "resident": resident, "residents": [resident], "confirm_key": "XL-2#99"}],
             "title": "Load #42 onto XL-2?", "body": "LR-MDB-1 slot 2 feeds XL-2, and XL-2 is running #99.",
             "msg": "LR-MDB-1 slot 2 feeds XL-2, and XL-2 is running #99."}
    why = "LR-MDB-1 slot 2 holds #78 now, not #77 as when you chose, so nothing moved: look at the slot again"
    changed = {"status": "success", "failures": {"42": why}, "blocked_reason": "occupant_changed"}
    data = {"success": False, "spool_saved": True, "location_moved": False, "location_result": asked,
            "msg": "Saved your other changes, but #42 was not moved to LR-MDB-1: FCC has to ask first"}
    res = run_js(tmp_path, ["inv_core.js", "inv_wizard.js"], PRELUDE + f"""
answerWith('/api/smart_move', [{_js(changed)}]);
const held = {{ location: 'LR-MDB-1', slot: '2', swap: true, expected_occupant: 77 }};
wizardState.pendingPlacement = held;
const outcomes = [];
window.wizardEditLocationNotMoved({_js(data)}, {{
  spoolId: 42, location: 'LR-MDB-1', fields: {{ slot: '2', swap: true, expected_occupant: 77 }},
  placement: held, onDone: (o, r, info) => outcomes.push([o, r, info || null]) }});
await __settle(150);
await click('.fcc-apc-yes');
await __settle(200);
return {{ outcomes, held: wizardState.pendingPlacement, posts: posts('/api/smart_move') }};
""")
    assert res["unhandled"] == [], res["unhandled"]
    [post] = res["posts"]
    assert post["expected_occupant"] == 77 and post["confirmed_fed_heads"] == ["XL-2#99"], post
    [(outcome, answer, info)] = res["outcomes"]
    assert outcome == "refused" and info["repick"] is True, res["outcomes"]
    assert info["tail"] == " Pick a slot again: Save opens the picker for LR-MDB-1.", info
    assert answer["msg"] == f"Saved your other changes, but #42 was not moved: {why}.", answer
    assert res["held"] is None, res


def test_force_location_forwards_what_the_picker_showed():
    """Force Location's picker door (inv_details.js) builds its own request from
    the placement: it must forward both fields, and send the two "changed"
    refusals back to the picker as 'cancelled' (it opens again)."""
    src = (MODULES / "inv_details.js").read_text(encoding="utf-8")
    start = src.index("window.promptEditLocation = ")
    body = src[start:src.index("\n};", start)]
    assert "original.expected_residents = pl.expected_residents" in body
    assert "original.expected_occupant = pl.expected_occupant" in body
    assert "'residents_changed'" in body and "'occupant_changed'" in body and "outcome: 'cancelled'" in body
