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
