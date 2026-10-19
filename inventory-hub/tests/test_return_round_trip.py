"""Group 40.6 — Return through BOTH halves (the 40.3 review's C6 lesson: halves
pinned separately hid a composition bug). The REAL inv_quickswap.js runs under
node's vm (tests/roundtrip_harness.py), and every fetch it makes is answered by
the REAL Flask app and move engine over move_engine_harness's fakes, with a
live in-memory locations.json. Only the slot picker's UI is a stub that answers
what a user picked; its model, the dry run, the confirm's printer check and the
Return are the real ones.

Pinned:
  - a free recorded slot: the confirm names it, the Yes puts the spool there,
    and the toast says "↩️ #77 → LR-MDB-1 slot 3";
  - a taken recorded slot: the chooser opens on the box (nothing written until
    the pick), a slot that feeds ANOTHER head only stores the spool there
    (Return never loads a head), and No slot lands it unslotted, "(no slot)";
  - item E: the DEPLOYED card's ↩️ returns its spool off its head into its slot,
    and the head stays empty;
  - the Group 40.6 review: a box with no slot count takes the slot its confirm
    named (R2), and a Room view's stale-trail card writes no other spool (R1).

HEAD proof (0b0eeb7): see the commit message.
"""
from __future__ import annotations

import copy
import json

import pytest

from roundtrip_harness import ALL_LOCATIONS_JS, FROM_POLYDRYER, QS, ROWS, run, world
from test_core1_return_ejectall_js import pytestmark  # noqa: F401  (skip without node)

FROM_SLOT_3 = {"physical_source": "LR-MDB-1", "physical_source_slot": "3", "container_slot": ""}

SETUP_JS = ALL_LOCATIONS_JS + r"""
window.__picks = __PICKS__;
window.__pickerCalls = [];
window.openSlotPicker = (opts) => {
  window.__pickerCalls.push({ location: opts.location, spool: opts.spool, mode: opts.mode, toolhead: opts.toolhead });
  const p = window.__picks.shift();
  return Promise.resolve(p === undefined ? null : p);
};
const returnOn = async (head) => {
  window.renderQuickSwapSection(state.allLocations.find(l => l.LocationID === head));
  await __settle(400);
  window.returnToolheadToSlot();
  await __settle(1800);
};
"""


def _setup(picks=(), rows=None):
    """The scenario's setup; `rows`: the browser's own view of locations.json
    when the world's rows differ from the shared ones (the later assignment
    wins)."""
    js = SETUP_JS.replace("__PICKS__", json.dumps(list(picks)))
    if rows is not None:
        js += "state.allLocations = " + json.dumps(rows) + ";\n"
    return js


def _pick(slot):
    return {"kind": "slot", "box": "LR-MDB-1", "slot": slot, "free": True, "send": {"picked_slot": slot},
            "expected_feed": "", "choice": None, "swap": False, "displaced": None}


def _toast_msgs(res):
    return [t["msg"] for t in res["toasts"]]


def test_a_free_recorded_slot_is_named_and_used(tmp_path):
    res = run(tmp_path, world({77: {"location": "XL-3", "extra": FROM_SLOT_3}}), QS, _setup() + r"""
await returnOn('XL-3');
const shown = html().slice();
await click('#fcc-quickswap-yes', 1500);
const st = await ctl('state');
return { shown, toasts: toasts(), s77: st.spools['77'], picker: window.__pickerCalls,
         posts: posts('/api/quickswap/return') };
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["picker"] == [] and len(res["shown"]) == 1, res
    assert "Sending back to:" in res["shown"][0] and "LR-MDB-1 slot 3" in res["shown"][0], res["shown"]
    assert res["s77"]["location"] == "LR-MDB-1" and res["s77"]["extra"]["container_slot"] == "3", res["s77"]
    assert "↩️ #77 → LR-MDB-1 slot 3" in _toast_msgs(res), res["toasts"]
    assert res["posts"][0] == {"toolhead": "XL-3", "dry_run": True}, res["posts"]


@pytest.mark.parametrize("pick, landed, toast", [
    (_pick("1"), "1", "↩️ #77 → LR-MDB-1 slot 1"),
    ({"kind": "none", "box": "LR-MDB-1"}, "", "↩️ #77 → LR-MDB-1 (no slot)"),
], ids=["a-slot-feeding-another-head", "no-slot"])
def test_a_taken_recorded_slot_asks_and_the_pick_only_stores(tmp_path, pick, landed, toast):
    """#57 holds slot 3 (where #77 came from) and no other slot feeds XL-3, so
    the chooser opens. Slot 1 feeds XL-1, which runs #99 from a PolyDryer:
    Return stores #77 there and leaves XL-1 alone."""
    spools = {77: {"location": "XL-3", "extra": FROM_SLOT_3},
              57: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}},
              99: {"location": "XL-1", "extra": FROM_POLYDRYER}}
    res = run(tmp_path, world(spools), QS, _setup([pick]) + r"""
await returnOn('XL-3');
const writesBeforeYes = (await ctl('state')).writes.length;
const shown = html().slice();
await click('#fcc-quickswap-yes', 1500);
const st = await ctl('state');
return { shown, writesBeforeYes, toasts: toasts(), picker: window.__pickerCalls,
         s77: st.spools['77'], s57: st.spools['57'], s99: st.spools['99'] };
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["picker"] == [{"location": "LR-MDB-1", "spool": 77, "mode": "return", "toolhead": "XL-3"}], res
    assert res["writesBeforeYes"] == 0, res
    assert res["s77"]["location"] == "LR-MDB-1" and res["s77"]["extra"]["container_slot"] == landed, res["s77"]
    assert res["s57"]["extra"]["container_slot"] == "3", res["s57"]
    assert res["s99"]["location"] == "XL-1", res["s99"]
    assert toast in _toast_msgs(res), res["toasts"]
    assert not any("null" in m for m in _toast_msgs(res)), res["toasts"]


def test_the_deployed_cards_return_takes_its_spool_off_the_head_into_its_slot(tmp_path):
    """Item E, manual check R3: the ↩️ on LR-MDB-1 slot 2's DEPLOYED card."""
    res = run(tmp_path, world({42: {"location": "XL-2", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "2", "container_slot": ""}}}), QS, _setup() + r"""
const ghost = { id: 42, display: '#42', color: 'ff0000', is_ghost: true, deployed_to: 'XL-2', slot: '2' };
const card = window.SpoolCardBuilder.buildCard(ghost, 'loc_grid', { slotNum: 2, locId: 'LR-MDB-1' });
eval('window.' + (card.match(/returnDeployedSpool\([^)]*\)/) || [''])[0]);
await __settle(1800);
await click('#fcc-quickswap-yes', 1500);
const st = await ctl('state');
return { toasts: toasts(), s42: st.spools['42'], onXL2: Object.keys(st.spools).filter(k => st.spools[k].location === 'XL-2'),
         posts: posts('/api/quickswap/return'), adds: posts('/api/manage_contents') };
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["s42"]["location"] == "LR-MDB-1" and res["s42"]["extra"]["container_slot"] == "2", res["s42"]
    assert res["onXL2"] == [] and res["adds"] == [], res
    assert [p.get("expected_spool") for p in res["posts"]] == [42, 42], res["posts"]
    assert "↩️ #42 → LR-MDB-1 slot 2" in _toast_msgs(res), res["toasts"]


# ---- Group 40.6 review (R1, R2) through both halves -----------------------------------------------
# Both fail on 7976b72 (the review's base).

def test_a_box_with_no_slot_count_takes_the_slot_its_confirm_named(tmp_path):
    """R2 (probe RT4): LR-BOX-9's Max Spools was cleared in the editor, and #77
    came from its slot 3. The confirm names LR-BOX-9 slot 3, the Yes puts #77
    there, and the toast says so. The Yes used to be refused ("LR-BOX-9 has one
    slot, not slot 3") with a 7 s error toast, on every retry."""
    rows = copy.deepcopy(ROWS) + [{"LocationID": "LR-BOX-9", "Type": "Dryer Box", "Max Spools": "",
                                   "parent_id": "LR", "extra": {"slot_targets": {}}}]
    w = world({77: {"location": "XL-3", "extra": {"physical_source": "LR-BOX-9", "physical_source_slot": "3",
                                                  "container_slot": ""}}})
    w["rows"] = rows
    res = run(tmp_path, w, QS, _setup(rows=rows) + r"""
await returnOn('XL-3');
const shown = html().slice();
await click('#fcc-quickswap-yes', 1500);
const st = await ctl('state');
return { shown, toasts: toasts(), s77: st.spools['77'], answers: answersOf('/api/quickswap/return') };
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert [a.get("action") for a in res["answers"]] == ["return_plan", "return_done"], res["answers"]
    assert len(res["shown"]) == 1 and "LR-BOX-9 slot 3" in res["shown"][0], res["shown"]
    assert res["s77"]["location"] == "LR-BOX-9" and res["s77"]["extra"]["container_slot"] == "3", res["s77"]
    assert _toast_msgs(res) == ["↩️ #77 → LR-BOX-9 slot 3"], res["toasts"]


# The doAssign contract inv_loc_mgr.js's _doAssignFinalize posts (Group 40.6 review,
# R1: `pickedSlot` sends slot null and picked_slot, kept by the engine only while
# that slot is free). doAssign itself is being changed elsewhere, so this stands in
# for it; everything it posts is answered by the real app and engine.
DO_ASSIGN_CONTRACT_JS = r"""
window.__assigns = [];
window.doAssign = (loc, spool, slot, fromBuffer, options) => {
  const o = options || {};
  window.__assigns.push([loc, spool, slot, fromBuffer, o]);
  const body = { action: 'add', location: loc, spool_id: 'ID:' + spool, slot, origin: '',
                 confirmed_toolheads: [], confirmed_fed_heads: [] };
  if (o.autoDeploy === false) body.auto_deploy = false;
  if (o.pickedSlot != null) { body.slot = null; body.picked_slot = o.pickedSlot; }
  return fetch('/api/manage_contents', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                         body: JSON.stringify(body) }).then(r => r.json());
};
"""


@pytest.mark.parametrize("slot_1_holder", [57, None], ids=["slot-1-taken", "slot-1-free"])
def test_a_room_views_stale_trail_return_writes_no_other_spool(tmp_path, slot_1_holder):
    """R1 (probes P6 and the card probe), end to end: #60 sits on a cart but its
    record still names LR-MDB-1 slot 1. The Room view (LR) lists it, by the flat
    prefix matcher, as a DEPLOYED card; the card is built from the server's own
    /api/get_contents?id=LR item and its ↩️ tapped. On 7976b72 the card named
    the Room, so the fallback posted {location: 'LR', slot: '1'}: the engine's
    Overwrite unseated slot 1 of every LR-* box (#57 in LR-MDB-1, #58 in
    LR-MDB-2) and filed #60 in the Room itself. Now it names LR-MDB-1 with a
    picked slot: no other spool is written, and #60 goes back in its slot only
    while that slot is free."""
    rows = copy.deepcopy(ROWS) + [{"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2",
                                   "parent_id": "LR", "extra": {"slot_targets": {}}}]
    spools = {60: {"location": "CR-CT-2-R1", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "1",
                                                       "container_slot": ""}},
              58: {"location": "LR-MDB-2", "extra": {"container_slot": "1"}}}
    if slot_1_holder:
        spools[slot_1_holder] = {"location": "LR-MDB-1", "extra": {"container_slot": "1"}}
    w = world(spools)
    w["rows"] = rows
    res = run(tmp_path, w, QS, _setup(rows=rows) + DO_ASSIGN_CONTRACT_JS + r"""
const items = await fetch('/api/get_contents?id=LR').then(r => r.json());
const ghost = items.find(i => i.id === 60);
const card = window.SpoolCardBuilder.buildCard(ghost, 'loc_list', { locId: 'LR', index: 0 });
const call = (card.match(/returnDeployedSpool\([^)]*\)/) || [''])[0];
eval('window.' + call);
await __settle(1500);
const st = await ctl('state');
return { ghost, call, assigns: window.__assigns, adds: posts('/api/manage_contents'),
         spools: st.spools, written: st.writes.map(w => w[0]) };
""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["ghost"]["is_ghost"] is True and res["ghost"]["location"] == "LR-MDB-1", res["ghost"]
    assert [s for s in res["written"] if s != 60] == [], (res["written"], res["spools"], res["adds"])
    assert res["spools"]["58"]["extra"]["container_slot"] == "1", res["spools"]["58"]
    assert res["spools"]["60"]["location"] != "LR", res["spools"]["60"]
    assert [a[0] for a in res["assigns"]] == ["LR-MDB-1"], res["assigns"]
    if slot_1_holder:
        assert res["spools"]["57"]["extra"]["container_slot"] == "1", res["spools"]["57"]
        assert res["spools"]["60"]["location"] == "CR-CT-2-R1" and res["written"] == [], res
    else:
        assert res["spools"]["60"]["location"] == "LR-MDB-1", res["spools"]["60"]
        assert res["spools"]["60"]["extra"]["container_slot"] == "1", res["spools"]["60"]
