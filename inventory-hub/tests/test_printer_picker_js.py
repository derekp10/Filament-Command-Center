"""Group 40.5 — the Printer picker's doors (Derek's D3, item F), under node's
`vm` (no browser, no container): inv_cmd.js runs for real, the picker
(window.openSlotPicker) is a stub that answers what a user picked, and the
server's answers are canned.

Pinned here:
  - LOC:XL (a Printer row that isn't its own toolhead) with a buffer opens the
    Printer picker once per buffered spool (Q1: loop); a head pick posts
    /api/smart_move onto the head, a Printer Pool pick posts the box slot;
  - a head that holds a spool asks first ("Load #57 onto XL-2? …", Load it
    instead / Cancel; no store), and Cancel steps back to the picker;
  - "Record it as coming from…" for a spool from no box: the one free feed slot
    is pre-selected (its QR / Enter), a feed slot's label scanned picks it, No
    box sends '', Cancel steps back, no free slot sends '' unasked, a spool from
    a cart is never asked;
  - item F (Derek's answer 8): an empty-buffer LOC:XL opens the view and grabs
    nothing; a toolhead grabs only its direct spool; a single-spool dryer box
    grabs its spool even while it is loaded on a head; a room grabs nothing;
  - the browser's printer-row classifier agrees with the server's.

HEAD proof: see the commit message.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE, SCAN, _text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROWS = [
    {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Name": "XL", "Type": "Printer", "Max Spools": "0",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Name": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1"} for n in (1, 2, 3)],
    {"LocationID": "CORE1", "Name": "Core One", "Type": "Printer", "Max Spools": "1",
     "toolheads": [{"location_id": "CORE1", "position": 0}]},
    {"LocationID": "MK4", "Name": "MK4", "Type": "Printer", "Max Spools": "0", "toolheads": []},
    {"LocationID": "LR-MDB-1", "Name": "LR box", "Type": "Dryer Box", "Max Spools": "4",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    {"LocationID": "PM-DB-2", "Name": "PolyDryer", "Type": "Dryer Box", "Max Spools": "1"},
    {"LocationID": "CR-CT-2-R1", "Name": "Cart row", "Type": "Cart Row", "Max Spools": "0"},
    {"LocationID": "CR-SHELF", "Name": "Shelf", "Type": "Shelf", "Max Spools": "1"},
]

SETUP = f"""
state.allLocations = {json.dumps(ROWS)};
window.__picks = [];
window.__pickerCalls = [];
window.openSlotPicker = (opts) => {{
  window.__pickerCalls.push(opts);
  const p = window.__picks.shift();
  return Promise.resolve(p === undefined ? null : p);
}};
window.__opened = [];
window.openManage = (id) => window.__opened.push(id);
window.__contents = [];
window.__extra = (url) => (url === '/api/identify_scan')
  ? {{ body: {{ type: 'location', id: window.__scanLoc, contents: window.__contents }} }} : null;
const scanLoc = async (id) => {{ window.__scanLoc = id; window.processScan('LOC:' + id, 'barcode'); await __settle(250); }};
const head = (id, extra) => Object.assign({{ kind: 'head', head: id, printer: 'XL', resident: null, residents: [],
  feeds: [], spool_location: '', via: 'key' }}, extra || {{}});
"""

DONE = {"status": "success", "failures": {}}
FREE_FEED = [{"box": "LR-MDB-1", "slot": "2", "spool": None, "claimed_by": None, "free": True}]


def _run(tmp_path, body):
    res = run_js(tmp_path, SCAN, PRELUDE + SETUP + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


def test_loc_xl_with_a_buffer_opens_the_printer_picker_and_a_head_pick_loads_it(tmp_path):
    """#57 sits on a cart, so no "came from" question: it keeps the cart as its
    trail. XL-2 is empty: no load question either."""
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1', feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
return {{ calls: window.__pickerCalls, posts: posts('/api/smart_move'), held: state.heldSpools.map(s => s.id) }};
""")
    assert [(c["location"], c["spool"]) for c in res["calls"]] == [("XL", 57)], res["calls"]
    [post] = res["posts"]
    assert post["location"] == "XL-2" and post["spools"] == [57] and post["slot"] is None, post
    assert post["confirmed_fed_heads"] == [] and "record_source" not in post, post
    assert res["held"] == []


def test_a_spool_from_no_box_is_asked_where_it_came_from_and_the_one_free_slot_is_preselected(tmp_path):
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(dict(DONE, recorded_source="LR-MDB-1:2"))}]);
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
const dialog = html().pop();
const focus = lastMount().opts.initialFocus;
await click('.fcc-rs-opt[data-rs-i="0"]');
await __settle(200);
return {{ dialog, focus, posts: posts('/api/smart_move'), toasts: toasts() }};
""")
    assert "Record #57 as coming from" in res["dialog"] and "LR-MDB-1 slot 2" in _text(res["dialog"]), res["dialog"]
    assert res["focus"] == '.fcc-rs-opt[data-rs-i="0"]', res["focus"]
    [post] = res["posts"]
    assert post["location"] == "XL-2" and post["record_source"] == {"box": "LR-MDB-1", "slot": "2"}, post
    assert any(t["msg"] == "#57 → XL-2 (recorded as from LR-MDB-1 slot 2)" for t in res["toasts"]), res["toasts"]


def test_several_free_slots_preselect_nothing_and_no_box_records_nothing(tmp_path):
    feeds = FREE_FEED + [{"box": "TST-MDB-1", "slot": "1", "spool": None, "claimed_by": None, "free": True},
                         {"box": "LR-MDB-9", "slot": "3", "spool": None, "claimed_by": 61, "free": False}]
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(feeds)} }})];
await scanLoc('XL');
const dialog = html().pop();
const focus = lastMount().opts.initialFocus;
await click('.fcc-rs-none');
await __settle(200);
return {{ dialog, focus, posts: posts('/api/smart_move'), toasts: toasts() }};
""")
    assert res["focus"] == ".fcc-rs-none", res["focus"]
    assert "holds #61" in res["dialog"] and "disabled" in res["dialog"], res["dialog"]
    [post] = res["posts"]
    assert post["record_source"] == "", post
    assert any(t["msg"] == "✅ #57 → XL-2 (no box slot recorded)" for t in res["toasts"]), res["toasts"]


def test_a_feed_slots_label_scanned_picks_it(tmp_path):
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode');
await __settle(250);
return {{ posts: posts('/api/smart_move') }};
""")
    [post] = res["posts"]
    assert post["record_source"] == {"box": "LR-MDB-1", "slot": "2"}, post


def test_a_feed_slots_label_with_a_key_left_in_front_still_picks_it(tmp_path):
    """A key a person left glued in front of the feed slot's label: the
    question reads its last label, and picks the slot. RED on 5b5a18e: it read
    the scan from its start, refused it and held it off as another scan."""
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
window.processScan('qLOC:LR-MDB-1:SLOT:2', 'barcode');
await __settle(250);
return {{ posts: posts('/api/smart_move') }};
""")
    [post] = res["posts"]
    assert post["record_source"] == {"box": "LR-MDB-1", "slot": "2"}, post


def test_a_feed_slot_of_a_box_whose_id_ends_in_loc_is_read_whole(tmp_path):
    """A feed slot in a box whose id ends in LOC ("XLOC"): its label picks it.
    RED on 4ac78d0: the question read from the last "LOC:" in the scan, which
    was inside the box id ("LOC:SLOT:2"), and refused it."""
    feeds = [{"box": "XLOC", "slot": "2", "spool": None, "claimed_by": None, "free": True}]
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(feeds)} }})];
await scanLoc('XL');
window.processScan('LOC:XLOC:SLOT:2', 'barcode');
await __settle(250);
return {{ posts: posts('/api/smart_move') }};
""")
    [post] = res["posts"]
    assert post["record_source"] == {"box": "XLOC", "slot": "2"}, post


def test_a_scanners_double_read_of_a_label_with_a_key_in_front_acts_once(tmp_path):
    """The feed slot's label with a key left in front ('qLOC:…'), and the
    scanner's second read of it 20 ms later: the question picks the slot once,
    and the second read is dropped as a double read ("Ignored a second read").
    RED on 4ac78d0: the first read wasn't remembered as a location label read,
    so the second went on to the server as a fresh slot scan (one that loads
    the buffer's spool into that slot)."""
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
window.processScan('qLOC:LR-MDB-1:SLOT:2', 'barcode');
await __settle(20);
window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode', Date.now());
await __settle(250);
return {{ moves: posts('/api/smart_move').length, scans: posts('/api/identify_scan').map(p => p.text), toasts: toasts() }};
""")
    assert res["moves"] == 1 and res["scans"] == ["LOC:XL"], res
    assert any("Ignored a second read" in t["msg"] for t in res["toasts"]), res["toasts"]


def test_another_scan_is_held_off_while_it_asks(tmp_path):
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
window.processScan('ID:99', 'barcode');
await __settle(150);
return {{ posts: posts('/api/smart_move'), scans: posts('/api/identify_scan').length, toasts: toasts() }};
""")
    assert res["posts"] == [] and res["scans"] == 1, res     # only the LOC:XL scan reached the server
    assert any("pick a slot (or scan its label), No box, or Cancel" in t["msg"] for t in res["toasts"]), res["toasts"]


def test_cancel_on_where_it_came_from_steps_back_to_the_picker(tmp_path):
    res = _run(tmp_path, f"""
window.__picks = [head('XL-2', {{ feeds: {_js(FREE_FEED)} }})];
await scanLoc('XL');
await click('.fcc-rs-cancel');
await __settle(200);
return {{ calls: window.__pickerCalls.length, posts: posts('/api/smart_move'), held: state.heldSpools.map(s => s.id) }};
""")
    assert res["calls"] == 2 and res["posts"] == [] and res["held"] == [57], res


def test_no_free_feed_slot_records_nothing_unasked(tmp_path):
    taken = [{"box": "LR-MDB-1", "slot": "2", "spool": None, "claimed_by": 61, "free": False}]
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ feeds: {_js(taken)} }})];
await scanLoc('XL');
return {{ posts: posts('/api/smart_move'), dialogs: html().filter(h => h.includes('Record #57')).length }};
""")
    assert res["dialogs"] == 0 and res["posts"][0]["record_source"] == "", res


def test_a_head_that_holds_a_spool_asks_first_and_cancel_steps_back(tmp_path):
    resident = {"id": 99, "display": "#99", "from": "LR-MDB-1 slot 2", "goes": "back to LR-MDB-1"}
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1', resident: {_js(resident)}, residents: [{_js(resident)}] }})];
await scanLoc('XL');
const asked = html().pop();
await click('.fcc-apc-no');
await __settle(200);
return {{ asked, calls: window.__pickerCalls.length, posts: posts('/api/smart_move') }};
""")
    assert "Load #57 onto XL-2?" in res["asked"], res["asked"]
    assert "XL-2 holds #99 (from LR-MDB-1 slot 2). Loading #57 sends #99 back to LR-MDB-1 slot 2." in res["asked"]
    assert "Just store it" not in res["asked"], res["asked"]
    assert res["calls"] == 2 and res["posts"] == [], res


def test_load_it_instead_loads_the_head(tmp_path):
    resident = {"id": 99, "display": "#99", "from": "", "goes": "to Room LR"}
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1', resident: {_js(resident)}, residents: [{_js(resident)}] }})];
await scanLoc('XL');
const asked = html().pop();
await click('.fcc-apc-yes');
await __settle(200);
return {{ asked, posts: posts('/api/smart_move') }};
""")
    assert "Loading #57 sends #99 to Room LR." in res["asked"], res["asked"]
    assert res["posts"][0]["location"] == "XL-2", res["posts"]


def test_a_printer_pool_pick_stages_the_spool_in_its_box_slot(tmp_path):
    pool = {"kind": "pool", "box": "LR-MDB-1", "slot": "4", "free": True, "via": "key",
            "send": {"picked_slot": "4"}, "expected_feed": "", "choice": None, "swap": False, "displaced": None,
            "store_ok": True}
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
window.__picks = [{_js(pool)}];
await scanLoc('XL');
return {{ posts: posts('/api/smart_move') }};
""")
    [post] = res["posts"]
    assert (post["location"], post["picked_slot"], post["expected_feed"], post["spools"]) == ("LR-MDB-1", "4", "", [57]), post
    assert "record_source" not in post


def test_two_spools_get_one_printer_picker_each_and_a_summary(tmp_path):
    pool = {"kind": "pool", "box": "LR-MDB-1", "slot": "4", "free": True, "via": "key",
            "send": {"picked_slot": "4"}, "expected_feed": "", "choice": None, "swap": False, "displaced": None}
    res = _run(tmp_path, f"""
state.heldSpools = [{{ id: 57, display: '#57' }}, {{ id: 58, display: '#58' }}];
answerWith('/api/smart_move', [{_js(DONE)}, {_js(DONE)}]);
window.__picks = [head('XL-2', {{ spool_location: 'CR-CT-2-R1' }}), {_js(pool)}];
await scanLoc('XL');
return {{ calls: window.__pickerCalls.map(c => [c.spool, c.step]), toasts: toasts(), held: state.heldSpools.map(s => s.id) }};
""")
    assert res["calls"] == [[57, "1 of 2"], [58, "2 of 2"]], res["calls"]
    assert res["held"] == []
    assert any(t["msg"] == "📦 XL: #57 → XL-2, #58 → LR-MDB-1 slot 4" for t in res["toasts"]), res["toasts"]


def test_a_printer_that_is_its_own_head_keeps_the_direct_path(tmp_path):
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(DONE)}]);
await scanLoc('CORE1');
return {{ calls: window.__pickerCalls.length, posts: posts('/api/smart_move') }};
""")
    assert res["calls"] == 0 and res["posts"][0]["location"] == "CORE1", res


# ---- item F: an empty-buffer location scan ----------------------------------------------------

def _item(sid, loc, ghost=False, deployed_to=None):
    return {"id": sid, "display": f"#{sid}", "color": "888888", "location": loc, "is_ghost": ghost,
            "slot": "", "deployed_to": deployed_to}


@pytest.mark.parametrize("loc, contents, picked", [
    ("XL", [_item(99, "XL-1")], None),                                  # a printer opens its view
    ("XL-1", [_item(99, "XL-1")], 99),                                  # a head grabs its spool
    ("XL-1", [_item(60, "CR-CT-2-R1", ghost=True)], None),              # never a stale trail's spool
    ("PM-DB-2", [_item(50, "PM-DB-2", ghost=True, deployed_to="XL-2")], 50),   # Derek's answer 8
    ("PM-DB-2", [_item(51, "PM-DB-2")], 51),
    ("LR", [_item(52, "LR")], None),                                    # a room opens its view
    ("CR-SHELF", [_item(53, "CR-SHELF")], 53),                          # any one-spool row: its own spool
    ("CR-SHELF", [_item(54, "CR-SHELF-2", ghost=True)], None),
    ("CORE1", [_item(55, "CORE1")], 55),                                # a printer that is its own head
    ("UNLISTED-9", [_item(56, "UNLISTED-9")], 56),                      # no row: the old first-spool rule
], ids=["printer", "head-direct", "head-ghost", "polydryer-loaded", "polydryer-direct", "room",
        "one-spool-shelf", "one-spool-shelf-ghost", "own-head-printer", "no-row"])
def test_an_empty_buffer_scan_grabs_only_a_one_spool_places_own_spool(tmp_path, loc, contents, picked):
    res = _run(tmp_path, f"""
state.heldSpools = [];
window.__contents = {_js(contents)};
await scanLoc({_js(loc)});
return {{ held: state.heldSpools.map(s => s.id), opened: window.__opened }};
""")
    if picked is None:
        assert res["held"] == [] and res["opened"] == [loc], res
    else:
        assert res["held"] == [picked] and res["opened"] == [], res


# ---- one classifier ---------------------------------------------------------------------------

def test_the_browsers_printer_row_classifier_agrees_with_the_servers(tmp_path):
    import locations_db
    printer_map = {th["location_id"]: {} for r in ROWS if r.get("Type") == "Printer" for th in r.get("toolheads", [])}
    server = {r["LocationID"]: locations_db.is_printer_row_not_head(r["LocationID"], r, printer_map) for r in ROWS}
    res = _run(tmp_path, f"""
return {{ js: Object.fromEntries(state.allLocations.map(r => [r.LocationID, window.isPrinterRowNotHead(r)])),
         multi: state.allLocations.filter(r => window.isMultiSlotBox(r)).map(r => r.LocationID),
         single: state.allLocations.filter(r => window.isSingleSlotBox(r)).map(r => r.LocationID) }};
""")
    assert res["js"] == server, (res["js"], server)
    assert server["XL"] is True and server["MK4"] is True and server["CORE1"] is False
    assert res["multi"] == ["LR-MDB-1"] and res["single"] == ["PM-DB-2"], res
