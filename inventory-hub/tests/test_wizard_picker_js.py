"""Group 40.7 — the wizard's Location opens the pickers (Derek's answer 7: "a
Location change in the Add/Edit Spool wizard behaves like Force Location"),
under node's `vm` with the real inv_core.js, inv_cmd.js and inv_wizard.js; the
picker (window.openSlotPicker) is a stub that answers what a user picked.

Pinned here:
  - picking a multi-slot box or a Printer row that isn't its own toolhead opens
    its picker (window.placeOneWithPicker) and HOLDS the choice for Save
    (wizardState.pendingPlacement; nothing is posted): a box slot, or a head
    (whose Location becomes the head, "XL-2 (via XL)") with its "came from"
    answer;
  - Escape in the picker puts the Location back as it stood;
  - a plain place opens nothing and drops a held choice;
  - Save sends the held choice (`record_source`, `swap`) with the edit;
  - a create places the first new spool where the picker said, and the rest get
    their own picker, one at a time (Claude's call 29; window.wizardPlaceRemaining).

HEAD proof: see the commit message.
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE
from test_wizard_location_save_js import WIZARD

MODULES = ["inv_core.js", "ui_builder.js", "inv_cmd.js", "inv_wizard.js"]

ROWS = [
    {"LocationID": "XL", "Name": "XL", "Type": "Printer", "Max Spools": "0",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Name": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1"} for n in (1, 2, 3)],
    {"LocationID": "LR-MDB-1", "Name": "LR box", "Type": "Dryer Box", "Max Spools": "4",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    {"LocationID": "CR-SHELF", "Name": "Shelf", "Type": "Shelf", "Max Spools": "12"},
]

SETUP = f"""
wizardState.allLocationRows = {json.dumps(ROWS)};
state.allLocations = {json.dumps(ROWS)};
window.__picks = [];
window.__pickerCalls = [];
window.openSlotPicker = (opts) => {{
  window.__pickerCalls.push(opts);
  const p = window.__picks.shift();
  return Promise.resolve(p === undefined ? null : p);
}};
const shown = () => ({{ value: document.getElementById('wiz-spool-location').value,
                        label: document.getElementById('wiz-spool-location-search').value }});
const setShown = (value, label) => {{
  document.getElementById('wiz-spool-location').value = value;
  document.getElementById('wiz-spool-location-search').value = label;
}};
const slotPick = (slot, feed) => ({{ kind: 'slot', box: 'LR-MDB-1', slot, free: true, via: 'key',
  send: {{ picked_slot: slot }}, expected_feed: feed, choice: null, swap: false, displaced: null, store_ok: true }});
const headPick = (head, extra) => Object.assign({{ kind: 'head', head, printer: 'XL', resident: null, residents: [],
  feeds: [{{ box: 'LR-MDB-1', slot: '2', spool: null, claimed_by: null, free: true }}], spool_location: '', via: 'key' }},
  extra || {{}});
"""


def _run(tmp_path, body):
    res = run_js(tmp_path, MODULES, PRELUDE + WIZARD + SETUP + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


def test_picking_a_box_holds_its_slot_for_save(tmp_path):
    res = _run(tmp_path, """
editing(57, 'CR-SHELF');
setShown('LR-MDB-1', 'LR box (LR-MDB-1)');
window.__picks = [slotPick('2', 'XL-2')];
await window.wizardLocationPicked('LR-MDB-1', { value: 'CR-SHELF', label: 'Shelf (CR-SHELF)' });
return { calls: window.__pickerCalls, pending: wizardState.pendingPlacement, shown: shown(),
         posts: __rec.fetches.filter(f => f.method === 'POST').map(f => f.url) };
""")
    [call] = res["calls"]
    assert call["location"] == "LR-MDB-1" and call["spool"] == 57, call
    pending = res["pending"]
    assert (pending["location"], pending["picked_slot"], pending["expected_feed"], pending["via"]) == \
        ("LR-MDB-1", "2", "XL-2", "LR-MDB-1"), pending
    assert res["shown"] == {"value": "LR-MDB-1", "label": "LR box (LR-MDB-1) — LR-MDB-1 slot 2"}, res["shown"]
    assert [p for p in res["posts"] if p not in ("/api/log_event",)] == [], res["posts"]


def test_picking_a_printer_holds_the_head_and_where_it_came_from(tmp_path):
    res = _run(tmp_path, """
creating(1, 'XL');
setShown('XL', 'XL (XL)');
window.__picks = [headPick('XL-2')];
const out = window.wizardLocationPicked('XL', { value: '', label: '' });
await __settle(150);
const dialog = html().pop();
await click('.fcc-rs-opt[data-rs-i="0"]');
await out;
return { dialog, pending: wizardState.pendingPlacement, shown: shown(), spool: window.__pickerCalls[0].spool };
""")
    assert "Record the new spool as coming from" in res["dialog"], res["dialog"]
    assert res["spool"] is None, res
    pending = res["pending"]
    assert pending["location"] == "XL-2" and pending["via"] == "XL", pending
    assert pending["record_source"] == {"box": "LR-MDB-1", "slot": "2"}, pending
    assert res["shown"] == {"value": "XL-2", "label": "XL-2 (via XL)"}, res["shown"]


def test_escape_in_the_picker_puts_the_location_back(tmp_path):
    res = _run(tmp_path, """
editing(57, 'CR-SHELF');
setShown('LR-MDB-1', 'LR box (LR-MDB-1)');
await window.wizardLocationPicked('LR-MDB-1', { value: 'CR-SHELF', label: 'Shelf (CR-SHELF)' });
return { pending: wizardState.pendingPlacement, shown: shown(), toasts: toasts() };
""")
    assert res["pending"] is None and res["shown"] == {"value": "CR-SHELF", "label": "Shelf (CR-SHELF)"}, res
    assert any(t["msg"] == "Location not changed — the picker was closed" for t in res["toasts"]), res["toasts"]


def test_a_plain_place_opens_nothing_and_drops_a_held_choice(tmp_path):
    res = _run(tmp_path, """
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'XL-2' };
const out = window.wizardLocationPicked('CR-SHELF', { value: 'LR-MDB-1', label: 'LR box (LR-MDB-1)' });
return { out, calls: window.__pickerCalls.length, pending: wizardState.pendingPlacement };
""")
    assert res["out"] is None and res["calls"] == 0 and res["pending"] is None, res


def test_save_sends_the_held_head_and_its_source(tmp_path):
    res = _run(tmp_path, f"""
editing(57, 'XL-2');
wizardState.pendingPlacement = {{ location: 'XL-2', record_source: {{ box: 'LR-MDB-1', slot: '2' }}, via: 'XL',
                                  label: 'XL-2' }};
answerFor({{ '/api/edit_spool_wizard': [{_js({"success": True, "spool_id": 57, "spool_saved": True,
                                               "location_moved": True, "location_where": "XL-2",
                                               "location_result": {"status": "success", "failures": {},
                                                                   "recorded_source": "LR-MDB-1:2"}})}] }});
await window.wizardSubmit();
await __settle(100);
return {{ body: posts('/api/edit_spool_wizard')[0], toasts: toasts() }};
""")
    body = res["body"]
    assert body["spool_data"]["location"] == "XL-2" and body["record_source"] == {"box": "LR-MDB-1", "slot": "2"}, body
    assert any(t["msg"] == "✅ #57 → XL-2 (recorded as from LR-MDB-1 slot 2)" for t in res["toasts"]), res["toasts"]


def test_a_held_swap_is_sent_too(tmp_path):
    res = _run(tmp_path, """
const fields = window.wizardPlacementFor('LR-MDB-1', { location: 'LR-MDB-1', slot: '3', expected_feed: 'XL-3',
                                                       swap: true, record_source: undefined });
return { fields };
""")
    assert res["fields"] == {"slot": "3", "expected_feed": "XL-3", "swap": True}, res


def test_the_rest_of_a_create_gets_one_picker_each(tmp_path):
    """Claude's call 29: the first new spool went where the picker said; the
    other two get their own picker for the same place, and their moves go
    through /api/smart_move. Escape on the third leaves it Unassigned, said."""
    done = {"status": "success", "failures": {}}
    res = _run(tmp_path, f"""
answerWith('/api/smart_move', [{_js(done)}]);
window.__picks = [slotPick('3', 'XL-3')];
await window.wizardPlaceRemaining({{ spoolIds: [502, 503], location: 'LR-MDB-1',
                                     placement: {{ location: 'LR-MDB-1', picked_slot: '2', via: 'LR-MDB-1' }} }});
return {{ calls: window.__pickerCalls.map(c => [c.location, c.spool, c.step]), posts: posts('/api/smart_move'),
         toasts: toasts() }};
""")
    assert res["calls"] == [["LR-MDB-1", 502, "1 of 2 left"], ["LR-MDB-1", 503, "2 of 2 left"]], res["calls"]
    [post] = res["posts"]
    assert post["spools"] == [502] and post["picked_slot"] == "3" and post["expected_feed"] == "XL-3", post
    # Group 40 review (wizard-loop-undo-buffer-top): the real request names the
    # wizard, so Undo doesn't put a never-buffered spool at the top of the buffer.
    assert post["origin"] == "wizard_create", post
    assert any(t["msg"].startswith("1 new spool stays Unassigned (#503)") for t in res["toasts"]), res["toasts"]


def test_a_head_picks_rest_go_through_the_printer_picker(tmp_path):
    """The first new spool went on XL-2 (via XL): the next one's picker is the
    printer's, not the head's."""
    res = _run(tmp_path, """
await window.wizardPlaceRemaining({ spoolIds: [602], location: 'XL-2',
                                    placement: { location: 'XL-2', via: 'XL' } });
return { calls: window.__pickerCalls.map(c => c.location) };
""")
    assert res["calls"] == ["XL"], res
