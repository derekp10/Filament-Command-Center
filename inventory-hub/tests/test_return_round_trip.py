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
    and the head stays empty.

HEAD proof (0b0eeb7): see the commit message.
"""
from __future__ import annotations

import json

import pytest

from roundtrip_harness import ALL_LOCATIONS_JS, FROM_POLYDRYER, QS, run, world
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


def _setup(picks=()):
    return SETUP_JS.replace("__PICKS__", json.dumps(list(picks)))


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
