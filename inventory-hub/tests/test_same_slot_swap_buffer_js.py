"""Group 40 — the browser half of the same-slot swap (Derek, 2026-10-15): the
slot's old spool, which the server took off its head into the scan buffer,
reaches THIS page's buffer too, under node's `vm` (no browser, no container).

The server puts it at the end of its buffer replica, but every page saves its
own buffer whole (last writer wins), so a door that only dropped the spool it
placed would save the replica WITHOUT the swapped-out spool. Each door that can
complete such a move therefore adds the answer's `to_buffer` entries itself,
behind the spools already waiting, with ONE save (two saves in a row can reach
the server out of order, and the one without the spool would win), and toasts
"✋ #99 → your buffer (taken off XL-1)". Undo answers `unbuffered`: the spool
is back on its head, so it leaves the buffer on screen without a save (the
server already dropped it, and loadBuffer adopts the server's list).

HEAD proof (d8f6128): window.takeIntoBuffer doesn't exist there and no door
reads `to_buffer`, so 5 of these 7 fail. The 2 that pass there are controls by
design: an answer with nothing swapped out adds nothing, and a spool already in
the buffer stays there once (HEAD never adds it at all).
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import LM, PRELUDE, SCAN

SWAPPED = {"id": 99, "display": "#99 Old Red", "color": "cc2222", "remaining_weight": 0, "location": "",
           "is_ghost": False, "slot": "", "deployed_to": None, "off_head": "XL-1"}
SLOT_SWAP_DONE = {"type": "assignment", "action": "assignment_done", "location": "LR-MDB-1", "slot": "1",
                  "moved": 57, "remaining_buffer": 0, "auto_deployed_to": "XL-1", "to_buffer": [SWAPPED]}
MOVE_SWAP_DONE = {"status": "success", "failures": {}, "auto_deployed_to": "XL-1", "to_buffer": [SWAPPED]}


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


SAVES = "posts('/api/state/buffer').map(b => (b.buffer || []).map(s => s.id))"


def test_a_slot_scan_puts_the_swapped_out_spool_in_the_buffer_with_one_save(tmp_path):
    """Derek's S2: one buffered spool (#57) into LR-MDB-1 slot 1, whose own #99
    ran on XL-1. #57 leaves the buffer, #99 joins it, saved once."""
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(SLOT_SWAP_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(200);
return {{ held: state.heldSpools, saves: {SAVES}, toasts: toasts() }};
""")
    assert [s["id"] for s in res["held"]] == [99], res["held"]
    assert "off_head" not in res["held"][0] and res["held"][0]["display"] == "#99 Old Red"
    assert res["saves"] == [[99]], res["saves"]
    msgs = [t["msg"] for t in res["toasts"]]
    assert msgs.index("✅ Loaded #57 into LR-MDB-1:1") < msgs.index("✋ #99 → your buffer (taken off XL-1)"), msgs
    assert any(t["msg"] == "✋ #99 → your buffer (taken off XL-1)" and t["type"] == "info" for t in res["toasts"])


def test_the_swapped_out_spool_waits_behind_the_spools_still_buffered(tmp_path):
    res = _run(tmp_path, SCAN, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/identify_scan', [{_js(dict(SLOT_SWAP_DONE, action="assignment_partial", remaining_buffer=1))}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id), saves: {SAVES} }};
""")
    assert res["held"] == [58, 99] and res["saves"] == [[58, 99]], res


def test_a_spool_already_buffered_is_not_added_twice(tmp_path):
    res = _run(tmp_path, SCAN, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 99, display: '#99' }}];
answerWith('/api/identify_scan', [{_js(SLOT_SWAP_DONE)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id) }};
""")
    assert res["held"] == [99], res


def test_an_assign_from_the_buffer_takes_it_too(tmp_path):
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/smart_move', [{_js(MOVE_SWAP_DONE)}]);
performContextAssign('LR-MDB-1', '1', [], [57]);
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id), saves: {SAVES}, toasts: toasts() }};
""")
    assert res["held"] == [99] and res["saves"] == [[99]], res
    assert any(t["msg"] == "✋ #99 → your buffer (taken off XL-1)" for t in res["toasts"]), res["toasts"]


def test_the_location_manager_takes_it_too(tmp_path):
    res = _run(tmp_path, LM, f"""
answerWith('/api/manage_contents', [{_js(MOVE_SWAP_DONE)}]);
window.doAssign('LR-MDB-1', 57, 1, true);
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert res["held"] == [99], res
    assert any(t["msg"] == "✋ #99 → your buffer (taken off XL-1)" for t in res["toasts"]), res["toasts"]


def test_an_answer_with_nothing_swapped_out_adds_nothing(tmp_path):
    """Control (passes on HEAD too): an empty idle head."""
    done = {k: v for k, v in SLOT_SWAP_DONE.items() if k != "to_buffer"}
    res = _run(tmp_path, SCAN, f"""
answerWith('/api/identify_scan', [{_js(done)}]);
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id), toasts: toasts().map(t => t.msg) }};
""")
    assert res["held"] == [] and not any("your buffer" in m for m in res["toasts"]), res


def test_undo_takes_the_spool_back_out_of_the_buffer_without_saving(tmp_path):
    """The undo put #99 back on XL-1; the server dropped it from its replica (and
    re-buffered #57), so this page drops it on screen and saves nothing: the
    loadBuffer that follows adopts the server's list."""
    res = _run(tmp_path, SCAN, """
state.heldSpools = [{ id: 99, display: '#99' }, { id: 43, display: '#43' }];
answerWith('/api/undo', [{ success: true, msg: '↩️ Undo: #57 is back in CR-CT-2-R1', restored: [57, 99],
                           unbuffered: [99] }]);
// Hold the server sync off (a tick in flight), so what is left is this page's own edit.
window.isBufferSyncing = true;
triggerUndo({ confirm: true, undoId: 'x-1', heads: [] });
await __settle(200);
return { held: state.heldSpools.map(s => s.id), saves: posts('/api/state/buffer').length,
         undos: posts('/api/undo').length };
""")
    assert res["undos"] == 1, res
    assert res["held"] == [43] and res["saves"] == 0, res
