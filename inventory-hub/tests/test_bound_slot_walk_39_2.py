"""Group 39.2 (engine part, I1-06): the pre-flight walks a named slot's binding
only when the move will auto-deploy.

The pre-flight asked about a Dryer Box slot's bound head even with
auto_deploy=False. Return parks a spool that way, so a Return into a slot bound
to a printing head asked about a head the move never touches. The 39.2 route
work (Quick-Swap and Return reading `confirmed_toolheads`) is still to come.

The REAL engine runs through tests/move_engine_harness.py.
HEAD proof: on the pre-I1-06 engine the first test answers requires_confirm.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import state  # noqa: E402
from move_engine_harness import WireSpoolman, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {"XL-3": {"printer_name": "XL", "position": 2}}
LOCATIONS = [
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB",
     "extra": {"slot_targets": {"3": "XL-3"}}},
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


def _move(sm, auto_deploy):
    calls = []
    inner = _probe_for({"XL"})

    def probe(url, name):
        calls.append(name)
        return inner(url, name)
    res = run_move(sm, probe=probe, locations=LOCATIONS, printer_map=PRINTER_MAP,
                   target="LR-MDB-1", raw_spools=[42], target_slot="3", auto_deploy=auto_deploy)
    return res, calls


def test_a_park_into_a_bound_slot_does_not_ask_about_its_head():
    sm = WireSpoolman({42: {"location": "CR", "extra": {}}})
    res, calls = _move(sm, auto_deploy=False)
    assert res.get("status") == "success", res
    assert calls == [], f"probed {calls} for a head the park never loads"
    assert sm.spools[42]["location"] == "LR-MDB-1"


def test_just_store_it_keeps_the_slot_and_leaves_the_printing_head_alone():
    """Group 40.0b: 40.3's "Just store it" is this call. The spool lands in the
    named slot and the printing head keeps its own spool. (Group 39 landed the
    behaviour; this pins the path 40.3 will lean on.)"""
    sm = WireSpoolman({240: {"location": "CR", "extra": {}}, 99: {"location": "XL-3", "extra": {}}})
    res = run_move(sm, probe=_probe_for({"XL"}), locations=LOCATIONS, printer_map=PRINTER_MAP,
                   target="LR-MDB-1", raw_spools=[240], target_slot="3", auto_deploy=False)
    assert res.get("status") == "success" and not res.get("failures"), res
    assert sm.spools[240]["location"] == "LR-MDB-1" and sm.spools[240]["extra"]["container_slot"] == "3"
    assert sm.direct_at("XL-3") == [99], "the store touched the printing head"


def test_a_deploying_move_still_asks_about_the_bound_head():
    sm = WireSpoolman({42: {"location": "CR", "extra": {}}})
    res, _ = _move(sm, auto_deploy=True)
    assert res.get("status") == "requires_confirm", res
    assert [(a["toolhead"], a["role"]) for a in res["active_prints"]] == [("XL-3", "feeds")]
    assert sm.patch_bodies == []
