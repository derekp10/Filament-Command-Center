"""Group 39.1 (engine half): every confirm names its toolhead.

R2-08: the deposit's active-print confirm was an unscoped boolean, so a stale
Quick-Swap grid whose slot had since been rebound to another head carried an
"XL-3 is printing, continue?" Yes onto a DIFFERENT printing head. Now
perform_smart_move's `confirm_active_print` is True (covers every head: internal
callers, the legacy browser flag), falsy (none), or the LocationIDs whose
warning the user actually saw. The pre-flight lists the heads the move touches
(the destination, and a named slot's bound head that the auto-deploy chain
loads), skips the covered ones without probing them, and answers ONE confirm
in the shared shape before anything is written.

The routes and the frontend still send booleans; switching them to
`confirmed_toolheads` is the next 39.1 step (see the 2026-10-13 handoff).

The REAL engine runs through tests/move_engine_harness.py; the probe is stubbed
below the per-move memo, as production caches it.
HEAD proof: on the pre-39.1 engine a head list is just "truthy", so the first,
fourth and fifth tests deposit onto the uncovered printing head, and the shape
test finds no `active_prints`.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import FakeSpoolman, WireSpoolman, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {
    "XL-1": {"printer_name": "XL", "position": 0},
    "XL-2": {"printer_name": "XL", "position": 1},
    "XL-3": {"printer_name": "XL", "position": 2},
}


def _locs(slot3_feeds="XL-3"):
    return [
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-2"},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3"},
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB",
         "extra": {"slot_targets": {"3": slot3_feeds}}},
        {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
    ]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


def _counting(printing):
    calls = []
    inner = _probe_for(printing)

    def probe(url, printer_name):
        calls.append(printer_name)
        return inner(url, printer_name)
    return probe, calls


def _sm(extra_spools=None):
    spools = {42: {"location": "CR", "extra": {}}}
    spools.update(extra_spools or {})
    return WireSpoolman(spools)


def test_a_confirm_for_another_head_is_asked_again():
    """The R2-08 case: the grid confirmed XL-3, but LR-MDB-1 slot 3 now feeds
    XL-2 and the XL is printing. The deposit must ask about XL-2 and write
    nothing."""
    sm = _sm()
    res = run_move(sm, probe=_probe_for({"XL"}), locations=_locs(slot3_feeds="XL-2"),
                   printer_map=PRINTER_MAP, target="LR-MDB-1", raw_spools=[42],
                   target_slot="3", confirm_active_print=["XL-3"])
    assert res.get("status") == "requires_confirm", res
    assert [(a["toolhead"], a["role"]) for a in res["active_prints"]] == [("XL-2", "feeds")], res
    assert sm.patch_bodies == [], f"wrote {sm.patch_bodies} before the confirm"


def test_a_covered_head_is_not_probed():
    """["XL-3"] covers XL-3: loading onto it while the XL prints neither asks nor
    probes the printer."""
    sm = _sm()
    probe, calls = _counting({"XL"})
    res = run_move(sm, probe=probe, locations=_locs(), printer_map=PRINTER_MAP,
                   target="XL-3", raw_spools=[42], confirm_active_print=["xl-3"])
    assert res.get("status") == "success", res
    assert calls == [], f"probed {calls} for a head the confirm covered"
    assert sm.spools[42]["location"] == "XL-3"


def test_the_legacy_boolean_still_covers_every_head():
    sm = _sm()
    res = run_move(sm, probe=_probe_for({"XL"}), locations=_locs(slot3_feeds="XL-2"),
                   printer_map=PRINTER_MAP, target="LR-MDB-1", raw_spools=[42],
                   target_slot="3", confirm_active_print=True)
    assert res.get("status") == "success", res
    assert res.get("auto_deployed_to") == "XL-2", res


def test_the_answer_has_the_shared_shape():
    sm = FakeSpoolman({42: {"location": "CR", "extra": {}}})
    res = run_move(sm, probe=_probe_for({"XL"}), locations=_locs(), printer_map=PRINTER_MAP,
                   target="XL-3", raw_spools=[42], confirm_active_print=False)
    assert res["status"] == "requires_confirm" and res["confirm_type"] == "active_print"
    assert res["active_prints"] == [{"toolhead": "XL-3", "printer_name": "XL", "state": "PRINTING",
                                     "role": "destination", "spools": [42]}]
    assert res["active_print"] == {"toolhead": "XL-3", "printer_name": "XL", "state": "PRINTING"}
    assert res["fed_heads"] == [] and res["can_store"] is False and res["target_slot"] is None
    assert res["msg"] == "XL is PRINTING — moving a spool here will disrupt the print."
    assert sm.writes == []


def test_a_scoped_confirm_carries_through_the_auto_deploy_chain():
    """Confirming XL-3 for its own bound slot deploys onto XL-3 with no second
    ask. A confirm for a DIFFERENT head is asked about XL-3 and writes nothing:
    `confirm and explicit_slot` used to turn any head list into a blanket True."""
    sm = _sm()
    ok = run_move(sm, probe=_probe_for({"XL"}), locations=_locs(), printer_map=PRINTER_MAP,
                  target="LR-MDB-1", raw_spools=[42], target_slot="3",
                  confirm_active_print=["XL-3"])
    assert ok.get("status") == "success" and ok.get("auto_deployed_to") == "XL-3", ok

    sm2 = _sm()
    asked = run_move(sm2, probe=_probe_for({"XL"}), locations=_locs(), printer_map=PRINTER_MAP,
                     target="LR-MDB-1", raw_spools=[42], target_slot="3",
                     confirm_active_print=["XL-1"])
    assert asked.get("status") == "requires_confirm", asked
    assert [a["toolhead"] for a in asked["active_prints"]] == ["XL-3"]
    assert sm2.patch_bodies == []


def test_a_scoped_confirm_covers_the_smart_load_eject_off_that_head():
    """Loading onto a printing XL-3 that holds #99: the confirm for XL-3 also
    covers unloading #99 from it (perform_smart_eject takes a boolean)."""
    sm = _sm({99: {"location": "XL-3", "extra": {}}})
    res = run_move(sm, probe=_probe_for({"XL"}), locations=_locs(), printer_map=PRINTER_MAP,
                   target="XL-3", raw_spools=[42], confirm_active_print=["XL-3"])
    assert res.get("status") == "success", res
    assert sm.spools[42]["location"] == "XL-3"
    assert sm.spools[99]["location"] != "XL-3", "the resident stayed on the head"


@pytest.mark.parametrize("value,every,heads", [
    (True, True, frozenset()),
    (False, False, frozenset()),
    (None, False, frozenset()),
    ([], False, frozenset()),
    (["xl-3", " XL-1 "], False, frozenset({"XL-3", "XL-1"})),
    ("XL-2", False, frozenset({"XL-2"})),
    (1, True, frozenset()),
])
def test_confirm_scope(value, every, heads):
    assert logic._confirm_scope(value) == (every, heads)
