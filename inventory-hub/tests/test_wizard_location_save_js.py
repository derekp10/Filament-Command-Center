"""Group 40.7 — the wizard's save handling of a Location move, as hermetic JS checks
under node's `vm` (the stub DOM of test_core1_return_ejectall_js.py; the real
inv_core.js + inv_wizard.js, no browser, no container).

Derek, 2026-10-19 (answer 7): a Location change in the wizard behaves like Force
Location. The server saves the other edits and moves the spool through the engine;
this page:
  - sends the move doors' contract on every save (`confirmed_toolheads: []`,
    `confirmed_fed_heads: []`) plus the picker's choice (`wizardState.
    pendingPlacement`: an edit's `slot` / `picked_slot` / `expected_feed` /
    `auto_deploy`, a create's `placements`, one per new spool; a picked box slot
    places only the first, Claude's call 29);
  - shows a question the engine asked through window.askMoveConfirm (the one move
    dispatcher) and replays it on /api/smart_move (window.buildMoveReplay); an
    Unassigned asked about uses Force Location's force_unassign replay;
  - says a refusal in a 7 s error and keeps the other edits saved; names where a
    move landed; takes a same-slot swap's old spool into the buffer;
  - starts a clone of a toolhead's (or Printer row's) spool Unassigned (Claude's
    call 28).

Base proof (0b0eeb7): all 13 fail. The saves carried no door contract and no
placements; a partial answer showed only "Error: …" (no dialog, so no replay, no
store, no Cancel line: those scenarios stop on the missing dialog), a refused
move raised no error toast, a swapped-out spool never reached the buffer, a
create's per-spool results were never read, and a clone pre-filled XL-3. One is
signature-only there: the classifier test (wizardCloneStartsBlank doesn't exist);
the pre-fill test is its behavioural twin.
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import FED, PRELUDE

MODULES = ["inv_core.js", "inv_wizard.js"]

# The wizard's form, for wizardSubmit: the stub DOM answers every id, so only the
# fields a test cares about are set. resolveEmptySpoolWeight lives in
# weight_utils.js, which isn't loaded here.
WIZARD = r"""
window.resolveEmptySpoolWeight = () => null;
const field = (id, v) => { document.getElementById(id).value = v; };
['wiz-spool-used', 'wiz-spool-empty_weight', 'wiz-spool-initial_weight', 'wiz-spool-comment', 'wiz-spool-price',
 'wiz-fil-color_name', 'wiz-fil-material', 'wiz-fil-weight', 'wiz-fil-empty_weight', 'wiz-fil-diameter',
 'wiz-fil-density', 'wiz-fil-settings_extruder_temp', 'wiz-fil-settings_bed_temp', 'wiz-fil-nozzle_temp_max',
 'wiz-fil-bed_temp_max', 'wiz-fil-vendor-sel', 'wiz-spool-location'].forEach(id => field(id, ''));
field('wiz-spool-qty', '1');
const editing = (sid, loc) => {
  wizardState.mode = 'edit_spool'; wizardState.editSpoolId = sid; wizardState.selectedFilamentId = 7;
  field('wiz-spool-location', loc);
};
const creating = (qty, loc) => {
  wizardState.mode = 'existing'; wizardState.selectedFilamentId = 7; wizardState.spoolRows = [];
  field('wiz-spool-qty', String(qty)); field('wiz-spool-location', loc);
};
const status = () => document.getElementById('wiz-status-msg').innerHTML;
const submitDisabled = () => document.getElementById('btn-wiz-submit').disabled;
const answerFor = (map) => { window.__extra = (url) => (url in map ? { body: map[url].shift() } : null); };
// Each toast with its duration: inv_core's showToast appends the toast, then
// arms its dismiss with setTimeout(dismiss, duration).
const toastLog = [];
{
  const box = document.getElementById('toast-container');
  const append = box.appendChild.bind(box);
  let last = null;
  box.appendChild = (el) => {
    last = { msg: el.innerText, type: String(el.className).replace('toast-msg toast-', '') };
    toastLog.push(last);
    return append(el);
  };
  const timer = globalThis.setTimeout;
  globalThis.setTimeout = (fn, ms, ...rest) => {
    if (last && last.duration === undefined) { last.duration = ms; last = null; }
    return timer(fn, ms, ...rest);
  };
}
"""

PARTIAL = {"success": False, "spool_saved": True, "location_moved": False}


def _run(tmp_path, body):
    res = run_js(tmp_path, MODULES, PRELUDE + WIZARD + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _js(value):
    return json.dumps(value)


# ---- what a save sends ---------------------------------------------------------------------

def test_an_edit_save_sends_the_door_contract_and_the_pickers_slot(tmp_path):
    res = _run(tmp_path, f"""
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = {{ location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'xl-2', auto_deploy: true }};
answerFor({{ '/api/edit_spool_wizard': [{_js({"success": True, "spool_id": 57, "spool_saved": True,
                                               "location_moved": True, "location_where": "LR-MDB-1 slot 2 → XL-2",
                                               "location_result": {"status": "success", "failures": {},
                                                                   "auto_deployed_to": "XL-2"}})}] }});
await window.wizardSubmit();
await __settle(100);
return {{ body: posts('/api/edit_spool_wizard')[0], toasts: toasts(), pending: wizardState.pendingPlacement }};
""")
    body = res["body"]
    assert body["confirmed_toolheads"] == [] and body["confirmed_fed_heads"] == [], body
    assert body["picked_slot"] == "2" and body["expected_feed"] == "XL-2" and "slot" not in body, body
    assert "auto_deploy" not in body and body["spool_data"]["location"] == "LR-MDB-1", body
    assert any(t["msg"] == "✅ #57 → LR-MDB-1 slot 2 → XL-2" and t["type"] == "success" for t in res["toasts"]), res
    assert res["pending"] is None, "a placement that landed is used up"


def test_a_pick_for_another_place_is_not_sent_with_a_typed_location(tmp_path):
    """The user picked LR-MDB-1 slot 2, then typed CR-CT-2-R1: a plain move, no slot."""
    res = _run(tmp_path, f"""
editing(57, 'CR-CT-2-R1');
wizardState.pendingPlacement = {{ location: 'LR-MDB-1', picked_slot: '2', expected_feed: 'XL-2' }};
answerFor({{ '/api/edit_spool_wizard': [{_js({"success": True, "spool_id": 57})}] }});
await window.wizardSubmit();
await __settle(60);
return {{ body: posts('/api/edit_spool_wizard')[0] }};
""")
    body = res["body"]
    assert body["confirmed_fed_heads"] == [] and body["spool_data"]["location"] == "CR-CT-2-R1", body
    for key in ("slot", "picked_slot", "expected_feed", "auto_deploy"):
        assert key not in body, (key, body)


def test_a_create_places_a_picked_box_slot_for_the_first_spool_only(tmp_path):
    """Claude's call 29: the chosen slot for the first new spool, the rest left for
    the per-spool picker loop; a typed place goes to every spool; blank, none. A
    head the Printer picker chose takes the first spool only too (integration,
    2026-10-19: the rest get their own picker; it used to send every spool to the
    head, which the server refuses outright)."""
    res = _run(tmp_path, """
creating(3, 'LR-MDB-1');
wizardState.pendingPlacement = { location: 'LR-MDB-1', picked_slot: '1', expected_feed: '', auto_deploy: false };
answerFor({ '/api/create_inventory_wizard': [{ success: true, created_spools: [501, 502, 503],
            placed: {}, unplaced: [501, 502, 503], location_results: {}, placement_requests: {} }] });
await window.wizardSubmit();
await __settle(60);
const make = window.wizardCreatePlacements || (() => 'missing');
return {
  body: posts('/api/create_inventory_wizard')[0],
  typed: make(2, 'cr-ct-2-r1', null),
  head: make(2, 'XL-3', { location: 'XL-3' }),
  blank: make(2, '', null),
};
""")
    body = res["body"]
    assert body.get("placements") == [{"location": "LR-MDB-1", "picked_slot": "1", "expected_feed": "",
                                       "auto_deploy": False}, None, None], body
    assert body["confirmed_toolheads"] == [] and body["confirmed_fed_heads"] == [], body
    assert res["typed"] == [{"location": "CR-CT-2-R1"}, {"location": "CR-CT-2-R1"}], res
    assert res["head"] == [{"location": "XL-3"}, None], res   # the rest: the per-spool picker loop
    assert res["blank"] == [None, None], res


# ---- an edit's answer ------------------------------------------------------------------------

def test_an_edit_question_is_asked_and_its_load_is_replayed_on_smart_move(tmp_path):
    """XL-1 runs a PolyDryer's spool: the server saved the other edits and asked.
    "Load it instead" replays the move on /api/smart_move with the confirm key."""
    asked = dict(PARTIAL, msg="Saved your other changes, but #57 was not moved to LR-MDB-1: FCC has to ask first",
                 location_result=dict(FED, target="LR-MDB-1", slot_picked=False, feed="XL-1", can_load=True,
                                      leaving=[]))
    done = {"status": "success", "failures": {}, "auto_deployed_to": "XL-1"}
    res = _run(tmp_path, f"""
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = {{ location: 'LR-MDB-1', slot: '1', expected_feed: 'XL-1' }};
answerFor({{ '/api/edit_spool_wizard': [{_js(asked)}], '/api/smart_move': [{_js(done)}] }});
await window.wizardSubmit();
await __settle(80);
const before = {{ html: html().pop(), status: status(), dirty: wizardState.isDirty }};
await click('.fcc-apc-yes');
await __settle(80);
return {{ before, replay: posts('/api/smart_move'), toasts: toasts(), status: status(),
          dirty: wizardState.isDirty, pending: wizardState.pendingPlacement }};
""")
    assert "Load #57 onto XL-1?" in res["before"]["html"] and "Just store it in LR-MDB-1 slot 1" in res["before"]["html"]
    assert "Saved your other changes" in res["before"]["status"] and res["before"]["dirty"] is True, res["before"]
    assert len(res["replay"]) == 1, res["replay"]
    replay = res["replay"][0]
    assert replay["location"] == "LR-MDB-1" and replay["spools"] == [57] and replay["slot"] == "1", replay
    assert replay["confirmed_fed_heads"] == ["XL-1#99"] and replay["expected_feed"] == "XL-1", replay
    assert replay["origin"] == "wizard_edit" and "auto_deploy" not in replay, replay
    assert any(t["msg"] == "✅ #57 → LR-MDB-1 slot 1 → XL-1" for t in res["toasts"]), res["toasts"]
    assert "Spool Updated" in res["status"] and res["dirty"] is False and res["pending"] is None, res


def test_just_store_it_replays_a_store(tmp_path):
    asked = dict(PARTIAL, location_result=dict(FED, target="LR-MDB-1", slot_picked=False, feed="XL-1",
                                               can_load=True, leaving=[]))
    res = _run(tmp_path, f"""
editing(57, 'LR-MDB-1');
wizardState.pendingPlacement = {{ location: 'LR-MDB-1', slot: '1', expected_feed: 'XL-1' }};
answerFor({{ '/api/edit_spool_wizard': [{_js(asked)}],
            '/api/smart_move': [{{ status: 'success', failures: {{}} }}] }});
await window.wizardSubmit();
await __settle(80);
await click('.fcc-apc-store');
await __settle(80);
return {{ replay: posts('/api/smart_move'), toasts: toasts().map(t => t.msg) }};
""")
    replay = res["replay"][0]
    assert replay["auto_deploy"] is False and replay["confirmed_fed_heads"] == [], replay
    assert "📦 #57 stored in LR-MDB-1 slot 1 — XL-1 left as it was" in res["toasts"], res["toasts"]


def test_cancel_moves_nothing_and_says_save_again(tmp_path):
    asked = dict(PARTIAL, location_result=dict(FED, target="LR-MDB-1", slot_picked=False, feed="XL-1",
                                               can_load=True, leaving=[]))
    res = _run(tmp_path, f"""
editing(57, 'LR-MDB-1');
answerFor({{ '/api/edit_spool_wizard': [{_js(asked)}] }});
await window.wizardSubmit();
await __settle(80);
await click('.fcc-apc-no');
return {{ moves: posts('/api/smart_move').length, status: status(), disabled: submitDisabled(),
          toasts: toasts().map(t => t.msg) }};
""")
    assert res["moves"] == 0 and res["disabled"] is False, res
    assert "Saved your other changes. #57 was not moved: Save again to move it." in res["status"], res
    assert "Cancelled — nothing moved" in res["toasts"], res


def test_a_refused_move_says_why_for_7s_and_keeps_save_usable(tmp_path):
    refused = dict(PARTIAL, msg=("Saved your other changes, but #57 was not moved to XL: XL is a printer, not a "
                                 "toolhead — pick one of its toolheads (XL-1 to XL-5)."),
                   location_result={"status": "error", "blocked_reason": "printer_row",
                                    "msg": "XL is a printer, not a toolhead", "failures": {"57": "x"}})
    res = _run(tmp_path, f"""
editing(57, 'XL');
answerFor({{ '/api/edit_spool_wizard': [{_js(refused)}] }});
await window.wizardSubmit();
await __settle(80);
return {{ all: toastLog, status: status(), disabled: submitDisabled(), overlays: html().length,
          moves: posts('/api/smart_move').length }};
""")
    errors = [t for t in res["all"] if t["type"] == "error"]
    assert len(errors) == 1 and errors[0]["duration"] >= 7000, res["all"]
    assert errors[0]["msg"].startswith("❌ Saved your other changes, but #57 was not moved to XL: XL is a printer"), errors
    assert "text-danger" in res["status"] and "was not moved to XL" in res["status"], res["status"]
    assert res["disabled"] is False and res["overlays"] == 0 and res["moves"] == 0, res


def test_an_unassign_asked_about_replays_force_locations_force_unassign(tmp_path):
    asked = dict(PARTIAL, location_result={
        "status": "requires_confirm", "confirm_type": "active_print",
        "active_print": {"toolhead": "CORE1", "printer_name": "Core One", "state": "PRINTING"},
        "msg": "Core One is PRINTING — force-unassigning from this toolhead will disrupt the print."})
    res = _run(tmp_path, f"""
editing(57, '');
answerFor({{ '/api/edit_spool_wizard': [{_js(asked)}], '/api/manage_contents': [{{ success: true }}] }});
await window.wizardSubmit();
await __settle(80);
const shown = html().pop();
await click('.fcc-apc-yes');
await __settle(80);
return {{ shown, sent: posts('/api/manage_contents'), moves: posts('/api/smart_move').length,
          toasts: toasts().map(t => t.msg), status: status() }};
""")
    assert "Core One is PRINTING" in res["shown"] and "Continue Anyway" in res["shown"], res["shown"]
    assert res["moves"] == 0, "an unassign is never replayed as a move to ''"
    assert res["sent"] == [{"action": "force_unassign", "location": "", "spool_id": 57,
                            "origin": "wizard_edit", "confirm_active_print": True}], res["sent"]
    assert "✅ #57 → Unassigned" in res["toasts"] and "Spool Updated" in res["status"], res


def test_the_same_slot_swaps_old_spool_reaches_this_pages_buffer(tmp_path):
    swapped = {"id": 99, "display": "#99 Old Red", "off_head": "XL-1"}
    moved = {"success": True, "spool_id": 57, "spool_saved": True, "location_moved": True,
             "location_where": "LR-MDB-1 slot 1 → XL-1", "to_buffer": [swapped],
             "location_result": {"status": "success", "failures": {}, "to_buffer": [swapped]}}
    res = _run(tmp_path, f"""
editing(57, 'LR-MDB-1');
answerFor({{ '/api/edit_spool_wizard': [{_js(moved)}] }});
state.heldSpools = [];
await window.wizardSubmit();
await __settle(80);
return {{ held: state.heldSpools.map(s => s.id), toasts: toasts().map(t => t.msg) }};
""")
    assert res["held"] == [99], res
    assert "✋ #99 → your buffer (taken off XL-1)" in res["toasts"], res["toasts"]


# ---- a create's answer -------------------------------------------------------------------------

def test_a_creates_questions_are_asked_one_at_a_time(tmp_path):
    """Two new spools, each asked about: the second dialog opens only once the first
    is answered (a second dialog on the same overlay would replace the first)."""
    q = dict(FED, target="LR-MDB-1", slot_picked=False, feed="XL-1", can_load=True, leaving=[])
    created = {"success": True, "created_spools": [501, 502], "placed": {}, "unplaced": [501, 502],
               "placements_ok": False,
               "location_results": {"501": dict(q, spools=[501]), "502": dict(q, spools=[502])},
               "placement_requests": {"501": {"location": "LR-MDB-1", "slot": "1"},
                                      "502": {"location": "LR-MDB-1", "slot": "1"}},
               "warning": "#501 was created but not placed …"}
    res = _run(tmp_path, f"""
creating(2, 'LR-MDB-1');
answerFor({{ '/api/create_inventory_wizard': [{_js(created)}],
            '/api/smart_move': [{{ status: 'success', failures: {{}}, auto_deployed_to: 'XL-1' }},
                                {{ status: 'success', failures: {{}} }}] }});
await window.wizardSubmit();
await __settle(80);
const first = html().length;
await click('.fcc-apc-yes');
await __settle(80);
const second = html().length;
await click('.fcc-apc-store');
await __settle(80);
return {{ first, second, replays: posts('/api/smart_move'), toasts: toasts().map(t => t.msg) }};
""")
    assert res["first"] == 1 and res["second"] == 2, res
    assert [r["spools"] for r in res["replays"]] == [[501], [502]], res["replays"]
    assert res["replays"][0]["origin"] == "wizard_create" and res["replays"][1]["auto_deploy"] is False, res
    assert "#501 was created but not placed …" not in res["toasts"], "the summary is for older pages"


def test_a_refused_placement_is_a_7s_error_naming_the_unassigned_spool(tmp_path):
    created = {"success": True, "created_spools": [501], "placed": {}, "unplaced": [501], "placements_ok": False,
               "location_results": {"501": {"status": "error", "msg": "Not moved: couldn't read CR-MDB-1",
                                            "failures": {"501": "couldn't read CR-MDB-1 from Spoolman"}}},
               "placement_requests": {"501": {"location": "CR-MDB-1"}}}
    res = _run(tmp_path, f"""
creating(1, 'CR-MDB-1');
answerFor({{ '/api/create_inventory_wizard': [{_js(created)}] }});
await window.wizardSubmit();
await __settle(80);
return {{ all: toastLog }};
""")
    errors = [t for t in res["all"] if t["type"] == "error"]
    assert errors and errors[0]["duration"] >= 7000, res["all"]
    assert errors[0]["msg"] == ("❌ New spool #501 was not placed in CR-MDB-1, so it is Unassigned: "
                                "couldn't read CR-MDB-1 from Spoolman"), errors


# ---- Clone (Claude's call 28) ---------------------------------------------------------------

def test_a_clone_of_a_toolhead_or_printer_rows_spool_starts_unassigned(tmp_path):
    """The classifier behind Claude's call 28 (on the base it doesn't exist, a
    signature-only failure; the pre-fill test below is the behavioural one)."""
    res = _run(tmp_path, """
const rows = [
  { LocationID: 'XL', Type: 'Printer', toolheads: [{ location_id: 'XL-1' }, { location_id: 'XL-3' }] },
  { LocationID: 'XL-1', Type: 'Tool Head' },
  { LocationID: 'CORE1', Type: 'Printer', toolheads: [{ location_id: 'CORE1' }] },
  { LocationID: 'RCOI-2', Type: 'No MMU Direct Load' },
  { LocationID: 'LR-MDB-1', Type: 'Dryer Box' },
  { LocationID: 'CR-CT-2-R1', Type: 'Cart Row' },
];
const blank = (loc, extra) => window.wizardCloneStartsBlank({ location: loc, extra: extra || {} }, rows);
return {
  head: blank('XL-1'), headWithoutRow: blank('XL-3'), printer: blank('XL'), dualRole: blank('core1'),
  direct: blank('RCOI-2'), box: blank('LR-MDB-1'), cart: blank('CR-CT-2-R1'), none: blank(''),
  staleTrailOnCart: blank('CR-CT-2-R1', { physical_source: 'LR-MDB-1' }),
  noRowsDeployed: window.wizardCloneStartsBlank({ location: 'XL-1', extra: { physical_source: 'LR-MDB-1' } }, []),
  noRowsShelf: window.wizardCloneStartsBlank({ location: 'CR-CT-2-R1', extra: {} }, []),
};
""")
    assert all(res[k] is True for k in ("head", "headWithoutRow", "printer", "dualRole", "direct", "noRowsDeployed")), res
    assert all(res[k] is False for k in ("box", "cart", "none", "staleTrailOnCart", "noRowsShelf")), res


def test_the_clone_prefill_leaves_a_toolheads_location_blank(tmp_path):
    spool = {"id": 134, "location": "XL-3", "comment": "", "extra": {"physical_source": "LR-MDB-1"},
             "filament": {"id": 7, "material": "PLA", "name": "Galaxy Black", "vendor": {"name": "Prusament"}}}
    res = _run(tmp_path, f"""
window.openWizardModal = async () => {{}};
window.wizardSelectType = () => {{}};
window.wizardExistingSelected = () => {{}};
window.resolveEmptySpoolWeightSource = () => ({{ value: null, source: null }});
window.wizardPrefillSpoolPrice = () => {{}};
window.wizardApplyCollapseDefaults = () => {{}};
wizardState.allLocationRows = [{{ LocationID: 'XL', Type: 'Printer', toolheads: [{{ location_id: 'XL-3' }}] }},
                               {{ LocationID: 'XL-3', Type: 'Tool Head' }}];
field('wiz-spool-location', 'stale');
window.__extra = (url) => (url.startsWith('/api/spool_details') ? {{ body: {_js(spool)} }} : null);
await window.openCloneWizard(134);
await __settle(80);
return {{ loc: document.getElementById('wiz-spool-location').value, status: status() }};
""")
    assert res["loc"] == "", res
    assert "Location left blank: #134 is on XL-3, so pick where the copy goes." in res["status"], res["status"]
