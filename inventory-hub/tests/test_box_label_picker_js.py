"""Group 40.2 — a multi-slot box's own label scanned with spools in the buffer
opens the slot picker (Derek's D2.1), once per spool that was buffered when the
label was scanned (Q1, answered 2026-10-13: loop). Hermetic, under node's `vm`:
inv_cmd.js runs for real, the picker (window.openSlotPicker) is a stub that
answers what a user picked, and the server's answers are canned.

Pinned here:
  - the box label opens the picker for the TOP spool (no move until a pick), a
    PolyDryer (Max Spools 1) and a shelf keep today's path;
  - what a pick sends: a free slot as `picked_slot` (never an Overwrite `slot`),
    an occupied one as `slot` after the user chose, the feed the tile showed as
    `expected_feed` on the FIRST request, the one spool, `confirmed_fed_heads`;
  - Swap puts the slot's old spool in the buffer once the move lands;
  - the loop: the next spool's picker after a move, "1 of 2" / "2 of 2",
    Escape stops and the rest stay buffered, Cancel on a load question steps
    back to the same spool's picker, a failure ends the loop, a spool a Swap
    hands back is never offered again, and a summary ends a loop of several;
  - a second box label scanned while a loop runs is refused.

HEAD proof (d8f6128): there the box label posts the whole buffer to
/api/smart_move with no slot and never opens a picker, and performContextAssign
reports no outcome, so 11 of these 12 fail; the one that passes is the control
(a PolyDryer and a shelf keep today's path). Re-run on the extract after the
onOutcome pin was added (f5f3ba2's message says "10 of 12").
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import FED, PRELUDE, SCAN

SETUP = r"""
state.allLocations = state.allLocations.concat([
  { LocationID: 'PM-DB-2', Name: 'PolyDryer', Type: 'Dryer Box', 'Max Spools': '1' },
  { LocationID: 'CR-SHELF', Name: 'Shelf', Type: 'Shelf', 'Max Spools': '12' },
]);
// The picker: each call takes the next canned pick (undefined = Escape).
window.__picks = [];
window.__pickerCalls = [];
window.openSlotPicker = (opts) => {
  window.__pickerCalls.push(opts);
  const p = window.__picks.shift();
  return Promise.resolve(p === undefined ? null : p);
};
// A location scan answers as a location (the server's shape).
window.__extra = (url) => (url === '/api/identify_scan')
  ? { body: { type: 'location', id: window.__scanLoc, contents: [] } } : null;
const scanLoc = async (id) => { window.__scanLoc = id; window.processScan('LOC:' + id, 'barcode'); await __settle(250); };
const freePick = (slot, feed) => ({ kind: 'slot', box: 'LR-MDB-1', slot, free: true, via: 'scan',
  send: { picked_slot: slot }, expected_feed: feed, choice: null, swap: false, displaced: null });
"""

DONE = {"status": "success", "failures": {}}


def _run(tmp_path, body):
    res = run_js(tmp_path, SCAN, PRELUDE + SETUP + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


def test_a_box_label_opens_the_picker_and_a_free_pick_is_sent_as_picked_slot(tmp_path):
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(dict(DONE, auto_deployed_to="XL-2"))}]);
window.__picks = [freePick('2', 'XL-2')];
await scanLoc('LR-MDB-1');
return {{ calls: window.__pickerCalls, posts: posts('/api/smart_move'),
         held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert len(res["calls"]) == 1, res["calls"]
    call = res["calls"][0]
    assert call["location"] == "LR-MDB-1" and call["spool"] == 57 and call["step"] == "", call
    assert res["posts"] == [{"location": "LR-MDB-1", "spools": [57], "slot": None, "origin": "buffer",
                             "confirmed_toolheads": [], "confirmed_fed_heads": [],
                             "picked_slot": "2", "expected_feed": "XL-2"}], res["posts"]
    assert res["held"] == []
    assert any(t["msg"] == "✅ #57 → LR-MDB-1 slot 2 → XL-2" for t in res["toasts"]), res["toasts"]


def test_escape_moves_nothing_and_says_the_spool_stays_buffered(tmp_path):
    res = _run(tmp_path, """
await scanLoc('LR-MDB-1');
return { calls: window.__pickerCalls.length, posts: posts('/api/smart_move'),
         held: state.heldSpools.map(s => s.id), toasts: toasts() };
""")
    assert res["calls"] == 1 and res["posts"] == [] and res["held"] == [57], res
    assert any(t["msg"] == "Nothing placed in LR-MDB-1: #57 stays in your buffer" for t in res["toasts"]), res


def test_an_occupied_slot_is_sent_as_slot_and_swap_buffers_its_old_spool(tmp_path):
    swap = {"kind": "slot", "box": "LR-MDB-1", "slot": "3", "free": False, "via": "key",
            "send": {"slot": "3"}, "expected_feed": "XL-3", "choice": "swap", "swap": True,
            "displaced": {"id": 77, "display": "#77 Old"}}
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [{_js(swap)}];
await scanLoc('LR-MDB-1');
return {{ posts: posts('/api/smart_move'), held: state.heldSpools.map(s => s.id),
         saves: posts('/api/state/buffer').map(b => (b.buffer || []).map(s => s.id)) }};
""")
    post = res["posts"][0]
    assert post["slot"] == "3" and "picked_slot" not in post and post["expected_feed"] == "XL-3", post
    assert res["held"] == [77] and res["saves"][-1] == [77], res


def test_two_spools_get_one_picker_each_and_a_summary(tmp_path):
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/smart_move', [{_js(DONE)}, {_js(DONE)}]);
window.__picks = [freePick('1', 'XL-1'), freePick('4', '')];
await scanLoc('LR-MDB-1');
return {{ calls: window.__pickerCalls.map(c => [c.spool, c.step]),
         posts: posts('/api/smart_move').map(p => [p.spools, p.picked_slot, p.expected_feed]),
         held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert res["calls"] == [[57, "1 of 2"], [58, "2 of 2"]], res["calls"]
    assert res["posts"] == [[[57], "1", "XL-1"], [[58], "4", ""]], res["posts"]
    assert res["held"] == []
    assert any(t["msg"] == "📦 LR-MDB-1: #57 → slot 1, #58 → slot 4" and t["type"] == "success"
               for t in res["toasts"]), res["toasts"]


def test_escape_on_the_second_spool_keeps_it_buffered(tmp_path):
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [freePick('1', 'XL-1')];
await scanLoc('LR-MDB-1');
return {{ calls: window.__pickerCalls.length, posts: posts('/api/smart_move').length,
         held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert res["calls"] == 2 and res["posts"] == 1 and res["held"] == [58], res
    assert any(t["msg"] == "📦 LR-MDB-1: #57 → slot 1; #58 stays in your buffer" for t in res["toasts"]), res


def test_cancel_on_the_load_question_steps_back_to_the_same_spools_picker(tmp_path):
    """Claude's call 24: Cancel steps back one dialog. Slot 1's head runs a
    PolyDryer spool, so the server asks; Cancel reopens #57's picker, and the
    second pick (slot 4, a pool slot) moves it."""
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(FED)}, {_js(DONE)}]);
window.__picks = [freePick('1', 'XL-1'), freePick('4', '')];
await scanLoc('LR-MDB-1');
await click('.fcc-apc-no');
await __settle(200);
return {{ calls: window.__pickerCalls.map(c => c.spool), posts: posts('/api/smart_move'),
         held: state.heldSpools.map(s => s.id) }};
""")
    assert res["calls"] == [57, 57], res["calls"]
    first, second = res["posts"]
    assert first["picked_slot"] == "1" and first["expected_feed"] == "XL-1", first
    assert second["picked_slot"] == "4" and second["expected_feed"] == "" and second["confirmed_fed_heads"] == [], second
    assert res["held"] == []


def test_load_it_instead_replays_with_the_key_and_the_picked_slot(tmp_path):
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(FED)}, {_js(DONE)}]);
window.__picks = [freePick('1', 'XL-1')];
await scanLoc('LR-MDB-1');
await click('.fcc-apc-yes');
await __settle(200);
return {{ calls: window.__pickerCalls.length, posts: posts('/api/smart_move'), held: state.heldSpools.map(s => s.id) }};
""")
    load = res["posts"][1]
    assert load["confirmed_fed_heads"] == ["XL-1#99"] and load["picked_slot"] == "1", load
    assert load["expected_feed"] == "XL-1" and load["spools"] == [57], load
    assert res["calls"] == 1 and res["held"] == []


def test_a_failed_move_ends_the_loop(tmp_path):
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/smart_move', [{_js({"status": "error", "msg": "Not moved: LR-MDB-1 slot 1 was filled by #60 meanwhile"})}]);
window.__picks = [freePick('1', 'XL-1'), freePick('2', 'XL-2')];
await scanLoc('LR-MDB-1');
return {{ calls: window.__pickerCalls.length, held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert res["calls"] == 1 and res["held"] == [57, 58], res
    assert any("filled by #60 meanwhile" in t["msg"] and t["type"] == "error" for t in res["toasts"]), res
    assert any(t["msg"] == "📦 LR-MDB-1: #57 and #58 stay in your buffer (stopped after an error)"
               for t in res["toasts"]), res["toasts"]


def test_a_spool_a_swap_hands_back_is_never_offered_again(tmp_path):
    swap = {"kind": "slot", "box": "LR-MDB-1", "slot": "3", "free": False, "via": "key",
            "send": {"slot": "3"}, "expected_feed": "XL-3", "choice": "swap", "swap": True,
            "displaced": {"id": 77, "display": "#77 Old"}}
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [{_js(swap)}];
await scanLoc('LR-MDB-1');
return {{ calls: window.__pickerCalls.map(c => c.spool), held: state.heldSpools.map(s => s.id) }};
""")
    assert res["calls"] == [57] and res["held"] == [77], res


def test_a_box_label_scanned_mid_loop_is_refused(tmp_path):
    res = _run(tmp_path, """
// The picker stays open (a Promise nobody resolves) while another label comes in.
window.openSlotPicker = (opts) => { window.__pickerCalls.push(opts); return new Promise(() => {}); };
await scanLoc('LR-MDB-1');
// Later than the repeat window (a second read within it is dropped first, below).
window._fccLastLocScan = null;
await scanLoc('LR-MDB-1');
return { calls: window.__pickerCalls.length, toasts: toasts() };
""")
    assert res["calls"] == 1, res
    assert any(t["msg"] == "Still placing your buffer into LR-MDB-1: finish or cancel that first"
               and t["type"] == "warning" for t in res["toasts"]), res["toasts"]


def test_a_label_read_twice_is_read_once(tmp_path):
    """Group 40.2 review (s2-rescan-reverses-swap, queued-double-read): the same
    LOC: label read again before the first read was answered (a scanner's
    double-read the accumulator queued) or within 1.5 s after is dropped, said
    so, and reaches no server door. Another label, and CMD:NEXT, are not."""
    res = _run(tmp_path, """
answerWith('/api/smart_move', [{ status: 'success', failures: {} }]);
window.__picks = [];
const t0 = Date.now();
await scanLoc('LR-MDB-1');                       // read 1: the picker (Escape)
window.processScan('LOC:LR-MDB-1', 'barcode', t0 + 80);   // read 2, captured during read 1
await __settle(200);
await scanLoc('CR-SHELF');                       // another label: handled

return { calls: window.__pickerCalls.length,
         scans: posts('/api/identify_scan').map(b => b.text), toasts: toasts().map(t => t.msg),
         logs: posts('/api/log_event').map(b => b.msg) };
""")
    assert res["calls"] == 1, res
    assert res["scans"] == ["LOC:LR-MDB-1", "LOC:CR-SHELF"], res["scans"]
    assert "ℹ️ Ignored a second read of LOC:LR-MDB-1" in res["toasts"], res["toasts"]
    assert any("read twice within 1.5 s" in (m or "") for m in res["logs"]), res["logs"]


def test_a_slot_scan_held_back_says_so_and_keeps_the_buffer(tmp_path):
    """The server held back the spool the same-slot swap just took out of this
    slot (assignment_held): a 7 s warning, nothing leaves the buffer."""
    held = {"type": "assignment", "action": "assignment_held", "location": "LR-MDB-1", "slot": "1",
            "spool": 99, "msg": "Not loaded: #99 just came out of LR-MDB-1 slot 1 …",
            "toast": "↩️ #99 just came out of LR-MDB-1 slot 1 — not put back (it's in your buffer)"}
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 99, display: '#99' }}];
answerWith('/api/identify_scan', [{_js(held)}]);
window.__extra = null;
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(200);
return {{ held: state.heldSpools.map(s => s.id), toasts: toasts() }};
""")
    assert res["held"] == [99], res
    assert any(t["msg"] == held["toast"] and t["type"] == "warning" for t in res["toasts"]), res["toasts"]


def test_the_double_scan_rule_never_drops_a_spool_it_did_not_put_in_the_buffer(tmp_path):
    """Group 40.2 review: the box label scanned with an empty buffer opens the
    manager; a spool buffered without a scan (the manager's pickup) and the same
    label again used to empty the buffer silently. Now the picker opens."""
    res = _run(tmp_path, f"""
window.__managed = [];
window.openManage = (id) => window.__managed.push(id);   // inv_loc_mgr.js isn't loaded here
state.heldSpools = [];
await scanLoc('LR-MDB-1');                       // empty buffer: opens the manager
const remembered = state.lastScannedLoc;
window._fccLastLocScan = null;                   // later than the repeat window
state.heldSpools = [{{ id: 57, display: '#57' }}];   // the manager's ✋ pickup
await scanLoc('LR-MDB-1');
return {{ remembered, calls: window.__pickerCalls.length, held: state.heldSpools.map(s => s.id),
         managed: window.__managed }};
""")
    assert res["remembered"] == "LR-MDB-1" and res["managed"] == ["LR-MDB-1"], res
    assert res["calls"] == 1 and res["held"] == [57], res


def test_a_store_only_pick_and_a_stale_slot_reach_the_door(tmp_path):
    """Group 40.2 review: a pick the tile promised to store sends auto_deploy
    false on every request; a stale record's slot takes no "Just store it"."""
    stored = {"kind": "slot", "box": "LR-MDB-1", "slot": "3", "free": False, "via": "key",
              "send": {"slot": "3", "auto_deploy": False}, "expected_feed": "XL-3", "store_ok": True,
              "choice": "overwrite", "swap": False, "displaced": None}
    stale = {"kind": "slot", "box": "LR-MDB-1", "slot": "1", "free": False, "via": "key",
             "send": {"slot": "1"}, "expected_feed": "XL-1", "store_ok": False,
             "choice": "put", "swap": False, "displaced": None}
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/smart_move', [{_js(DONE)}, {_js(FED)}]);
window.__picks = [{_js(stored)}, {_js(stale)}];
await scanLoc('LR-MDB-1');
const shown = html().pop() || '';
return {{ posts: posts('/api/smart_move'), shown, toasts: toasts().map(t => t.msg) }};
""")
    first, second = res["posts"]
    assert first["auto_deploy"] is False and first["slot"] == "3", first
    assert "📦 #57 stored in LR-MDB-1 slot 3" in res["toasts"], res["toasts"]
    assert "auto_deploy" not in second, second
    assert "Just store it" not in res["shown"] and "Load it instead" in res["shown"], res["shown"]


def test_perform_context_assign_returns_nothing_and_reports_through_on_outcome(tmp_path):
    """A returned Promise hung a browser test for 30 minutes (2026-10-15): its
    page.evaluate awaited the move, which waited on a question the test could
    only answer after evaluate returned. The outcome goes to `onOutcome` only."""
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(FED)}, {_js(DONE)}]);
const outcomes = [];
const r = performContextAssign('LR-MDB-1', null, [], [57], null, {{ onOutcome: (o) => outcomes.push(o.outcome) }});
await __settle(150);
const before = outcomes.slice();
await click('.fcc-apc-yes');
await __settle(150);
return {{ returned: typeof r, before, after: outcomes }};
""")
    assert res["returned"] == "undefined", res
    assert res["before"] == [] and res["after"] == ["moved"], res


def test_a_polydryer_and_a_shelf_keep_todays_path(tmp_path):
    """Controls: a single-slot box and a shelf take the buffer straight away."""
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/smart_move', [{_js(DONE)}, {_js(DONE)}]);
await scanLoc('PM-DB-2');
await scanLoc('CR-SHELF');
return {{ calls: window.__pickerCalls.length,
         posts: posts('/api/smart_move').map(p => [p.location, p.spools, p.slot]) }};
""")
    assert res["calls"] == 0, res
    assert res["posts"] == [["PM-DB-2", [57], None], ["CR-SHELF", [58], None]], res["posts"]
