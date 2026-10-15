"""Group 40.3 — move questions through BOTH halves (Group 40.3 review, C6): the
real browser modules answer the real engine's questions and post their real
replays back (tests/roundtrip_harness.py). Each test is a path the review found
broken only in composition, or Derek's own path.

HEAD proof (run on c1c2c38): the store re-ask offered "Load it instead" and the
↩️ race's Load stored instead (the first two fail); the deposit loaded XL-1
mid-print with no dialog when the move's printer check failed (the third
fails). The load round trip is a control: it passes there too.
"""
from __future__ import annotations

from roundtrip_harness import ALL_LOCATIONS_JS, FROM_POLYDRYER, LM, QS, SCAN, run, world
from test_core1_return_ejectall_js import pytestmark  # noqa: F401  (skip without node)


def test_a_store_into_a_slot_repointed_meanwhile_is_asked_as_a_store(tmp_path):
    """XL-1 runs #99 from PM-DB-2. The slot scan asks; slot 1 is re-pointed to
    XL-2 while the dialog is open; Just store it. FCC asks again AS A STORE (no
    Load button), and the store lands: #42 in slot 1, XL-1 and XL-2 untouched."""
    res = run(tmp_path, world({42: {"location": "CR-CT-2-R1", "extra": {}},
                               99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}},
                              buffer=[{"id": 42, "display": "#42"}]), SCAN, ALL_LOCATIONS_JS + r"""
state.heldSpools = [{ id: 42, display: '#42' }];
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(1500);
const q1 = offered(html().pop());
await ctl('repoint', { box: 'LR-MDB-1', slot: 1, to: 'XL-2' });
await click('.fcc-apc-store', 1500);
const q2 = offered(html().pop());
await click('.fcc-apc-store', 1500);
const st = await ctl('state');
return { q1, q2, toasts: toasts(), where: { s42: st.spools['42'].location, slot: (st.spools['42'].extra || {}).container_slot,
         s99: st.spools['99'].location }, onXL2: Object.keys(st.spools).filter(k => st.spools[k].location === 'XL-2') };
""")
    assert res["q1"]["title"].endswith("Load #42 onto XL-1?") and res["q1"]["store"], res["q1"]
    assert res["q2"]["load"] is False and res["q2"]["store"] is True, res["q2"]
    assert res["q2"]["title"].endswith("Store #42 in LR-MDB-1 slot 1?"), res["q2"]
    assert res["where"] == {"s42": "LR-MDB-1", "slot": "1", "s99": "XL-1"} and res["onXL2"] == [], res["where"]
    assert res["unhandled"] == []
    assert any(t["msg"] == "📦 #42 stored in LR-MDB-1 slot 1 — XL-2 left as it was" for t in res["toasts"]), res["toasts"]


def test_the_deployed_cards_return_in_a_repoint_race_stays_a_return(tmp_path):
    """#50 runs on XL-1 from LR-MDB-1 slot 1, the XL prints. The DEPLOYED card's
    ↩️ asks about leaving XL-1; slot 1 is re-pointed to RC-1 meanwhile; Continue.
    FCC asks again as a store, and the spool goes back into slot 1: RC-1 stays
    empty (the ↩️ used to be turned into a load by "Load it instead")."""
    res = run(tmp_path, world({50: {"location": "XL-1", "extra": {"physical_source": "LR-MDB-1",
                                                                   "physical_source_slot": "1", "container_slot": ""}}},
                              printing=["XL"]), LM, ALL_LOCATIONS_JS + r"""
state.heldSpools = [];
window.doAssign('LR-MDB-1', 50, '1', null, { autoDeploy: false });
await __settle(1500);
await ctl('repoint', { box: 'LR-MDB-1', slot: 1, to: 'RC-1' });
await click('.fcc-apc-yes', 1500);
const q2 = offered(html().pop());
await click('.fcc-apc-store', 1500);
const st = await ctl('state');
return { q2, toasts: toasts(), where: { s50: st.spools['50'].location, slot: (st.spools['50'].extra || {}).container_slot },
         onRC1: Object.keys(st.spools).filter(k => st.spools[k].location === 'RC-1') };
""")
    assert res["q2"]["load"] is False and res["q2"]["store"] is True, res["q2"]
    assert res["where"] == {"s50": "LR-MDB-1", "slot": "1"} and res["onRC1"] == [], res
    assert res["unhandled"] == []
    assert any(t["msg"] == "↩️ #50 → LR-MDB-1 slot 1" for t in res["toasts"]), res["toasts"]


def test_a_deposit_whose_move_time_printer_check_fails_still_asks(tmp_path):
    """The XL prints and XL-1 is empty. The deposit's own check sees the print
    and leaves the question to FCC; FCC's check for the move then fails (a
    PrusaLink timeout). It asks anyway, and Enter stores: XL-1 stays empty."""
    res = run(tmp_path, world({42: {"location": "CR-CT-2-R1", "extra": {}}},
                              printing=["XL"], move_probe_fail=["XL"],
                              buffer=[{"id": 42, "display": "#42"}]), QS, ALL_LOCATIONS_JS + r"""
state.heldSpools = [{ id: 42, display: '#42' }];
window.quickSwapDeposit({ dataset: { box: 'LR-MDB-1', slot: '1', toolhead: 'XL-1' } });
await __settle(2500);
const shown = html().length;
const q = shown ? offered(html().pop()) : null;
if (shown) { document.activeElement = null; await key('Enter'); }
const st = await ctl('state');
return { shown, q, toasts: toasts(), first: posts('/api/identify_scan')[0], where: st.spools['42'].location,
         onXL1: Object.keys(st.spools).filter(k => st.spools[k].location === 'XL-1') };
""")
    assert res["first"].get("seen_printing") == ["XL-1"], res["first"]
    assert res["shown"] == 1 and res["q"]["store"] is True, res
    assert res["onXL1"] == [] and res["where"] == "LR-MDB-1", res
    assert res["unhandled"] == []
    assert any(t["msg"] == "📦 #42 stored in LR-MDB-1 slot 1 — XL-1 left as it was" for t in res["toasts"]), res["toasts"]


def test_load_it_instead_after_a_repoint_lands_on_the_new_head(tmp_path):
    """A control on the load path: the question about XL-1, a re-point to XL-2,
    Load it instead, then the re-ask "Load #42 onto XL-2?", Load: #42 is on XL-2
    and XL-1 keeps #99."""
    res = run(tmp_path, world({42: {"location": "CR-CT-2-R1", "extra": {}},
                               99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}},
                              buffer=[{"id": 42, "display": "#42"}]), SCAN, ALL_LOCATIONS_JS + r"""
state.heldSpools = [{ id: 42, display: '#42' }];
window.processScan('LOC:LR-MDB-1:SLOT:1', 'barcode');
await __settle(1500);
await ctl('repoint', { box: 'LR-MDB-1', slot: 1, to: 'XL-2' });
await click('.fcc-apc-yes', 1500);
const q2 = offered(html().pop());
await click('.fcc-apc-yes', 1500);
const st = await ctl('state');
return { q2, toasts: toasts(), s42: st.spools['42'].location, s99: st.spools['99'].location };
""")
    assert res["q2"]["load"] is True and res["q2"]["title"].endswith("Load #42 onto XL-2?"), res["q2"]
    assert (res["s42"], res["s99"]) == ("XL-2", "XL-1"), res
    assert res["unhandled"] == []
    assert any(t["msg"].startswith("✅ Loaded #42") for t in res["toasts"]), res["toasts"]
