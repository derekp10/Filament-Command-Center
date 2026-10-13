"""Group 39.1 / 39.2: the browser's move doors confirm BY HEAD.

The five doors (manage_contents add, /api/smart_move, the identify_scan slot
branch, /api/quickswap, /api/quickswap/return) read `confirmed_toolheads`, the
heads whose active-print warning the user saw. A bare legacy
`confirm_active_print: true` covers no head, so a stale cached page is asked
again. Quick-Swap and Return no longer pass True unconditionally (39.2): the
server re-checks what the overlay's probe (fail-open on a timeout) missed.

R2-08, the case this closes: a Quick-Swap grid confirmed XL-3, the slot was
rebound to XL-2 meanwhile, and the boolean carried the XL-3 confirm onto XL-2.

The REAL engine runs through tests/move_engine_harness.py; the probe is stubbed
below the per-move memo. HEAD proof: the pre-39.1 routes ignore
`confirmed_toolheads`, answer no `active_prints`, move on a bare `true`, and
Return never asks; the first four tests fail there (the last two guard paths
that did not change).
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import state  # noqa: E402
from move_engine_harness import WireSpoolman, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {
    "XL-2": {"printer_name": "XL", "position": 1},
    "XL-3": {"printer_name": "XL", "position": 2},
}
LOCATIONS = [
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-2"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB",
     "extra": {"slot_targets": {"3": "XL-3"}}},
    {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB 2"},
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


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _locs(slot3="XL-3"):
    locs = copy.deepcopy(LOCATIONS)
    locs[2]["extra"]["slot_targets"]["3"] = slot3
    return locs


def _run(sm, probe, call, locations=None):
    return run_move(sm, probe=probe, locations=locations or LOCATIONS, printer_map=PRINTER_MAP, call=call)


def _counting(printing, state_name="PRINTING", active=True):
    calls = []

    def probe(_url, name):
        calls.append(name)
        on = name in printing
        return {"state": state_name if on else "IDLE", "is_active": on and active}
    return probe, calls


def test_a_stale_grid_confirm_is_asked_about_the_head_the_slot_feeds_now(client):
    """The task file's R2-08 pin: the deposit confirmed XL-3, but LR-MDB-1 slot
    3 now feeds XL-2 and the XL is printing."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = WireSpoolman({42: {"location": "CR", "extra": {}}})
    r = _run(sm, _probe_for({"XL"}), lambda: client.post("/api/identify_scan", json={
        "text": "LOC:LR-MDB-1:SLOT:3", "source": "quickswap_deposit",
        "confirmed_toolheads": ["XL-3"]}), locations=_locs(slot3="XL-2"))
    body = r.get_json()
    assert body["action"] == "assignment_requires_confirm", body
    assert [a["toolhead"] for a in body["active_prints"]] == ["XL-2"], body
    assert sm.patch_bodies == [], f"wrote {sm.patch_bodies} before the confirm"
    assert [i["id"] for i in state.GLOBAL_BUFFER] == [42]


def test_the_replay_naming_that_head_deposits_and_deploys(client):
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = WireSpoolman({42: {"location": "CR", "extra": {}}})
    r = _run(sm, _probe_for({"XL"}), lambda: client.post("/api/identify_scan", json={
        "text": "LOC:LR-MDB-1:SLOT:3", "source": "quickswap_deposit",
        "confirmed_toolheads": ["XL-3", "XL-2"]}), locations=_locs(slot3="XL-2"))
    body = r.get_json()
    assert body["action"] == "assignment_done" and body.get("auto_deployed_to") == "XL-2", body
    assert sm.spools[42]["location"] == "XL-2"


def test_a_bare_legacy_confirm_on_quickswap_is_asked_again(client):
    sm = WireSpoolman({240: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}}})
    r = _run(sm, _probe_for({"XL"}), lambda: client.post("/api/quickswap", json={
        "toolhead": "XL-3", "box": "LR-MDB-1", "slot": "3", "confirm_active_print": True}))
    body = r.get_json()
    assert r.status_code == 200 and body["action"] == "quickswap_requires_confirm", body
    assert [(a["toolhead"], a["role"]) for a in body["active_prints"]] == [("XL-3", "destination")], body
    assert sm.patch_bodies == [] and sm.spools[240]["location"] == "LR-MDB-1"


def test_quickswap_confirmed_for_its_head_swaps_and_sends_the_resident_home(client):
    sm = WireSpoolman({240: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}},
                       99: {"location": "XL-3", "extra": {"physical_source": "LR-MDB-2",
                                                          "physical_source_slot": "1"}}})
    r = _run(sm, _probe_for({"XL"}), lambda: client.post("/api/quickswap", json={
        "toolhead": "XL-3", "box": "LR-MDB-1", "slot": "3", "confirmed_toolheads": ["XL-3"]}))
    body = r.get_json()
    assert body["action"] == "quickswap_done", body
    assert sm.direct_at("XL-3") == [240]
    assert sm.spools[99]["location"] == "LR-MDB-2"


def test_a_return_bound_to_the_same_printer_probes_it_once(client):
    """The slot Return parks in feeds the head it empties: one printer, one
    probe (the source check), one answer."""
    sm = WireSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3", "container_slot": ""}}})
    probe, calls = _counting({"XL"})
    r = _run(sm, probe, lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-3"}))
    body = r.get_json()
    assert body["action"] == "return_requires_confirm", body
    assert calls == ["XL"], calls
    assert sm.patch_bodies == []


def test_a_paused_printer_lets_return_through(client):
    sm = WireSpoolman({240: {"location": "XL-3", "extra": {
        "physical_source": "LR-MDB-1", "physical_source_slot": "3", "container_slot": ""}}})
    probe, _ = _counting({"XL"}, state_name="PAUSED", active=False)
    r = _run(sm, probe, lambda: client.post("/api/quickswap/return", json={"toolhead": "XL-3"}))
    body = r.get_json()
    assert body["action"] == "return_done", body
    assert sm.spools[240]["location"] == "LR-MDB-1"
