"""Group 39.6: one confirm to eject off a printing head (backend half).

Ejecting a spool with no saved home off a printing head took THREE round trips:
the active-print answer, then (after Yes) "REQUIRE_CONFIRM" for the unassign,
then the confirmed eject, each prompt raised from the previous one's callback.
The second prompt read "Spool is already in a room. Confirm true unassign to
nowhere?" about a spool on a toolhead.

The engine's answers are unchanged (every refusal truthy; Smart Load and the
Group 41/42 plans depend on that). The "where does it go" decision moved into a
pure helper, `logic._eject_destination`, which perform_smart_eject itself runs,
and the eject route asks both questions at once when both apply:
`confirm_types: ["active_print", "unassign"]`. One Yes then sends
`confirmed: true` and `confirm_active_print: true` (doEject's half is the
frontend step, still to come).

The REAL engine runs through tests/move_engine_harness.py.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, WireSpoolman, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {"XL-3": {"printer_name": "XL", "position": 2}}
LOCATIONS = [
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "Name": "XL", "parent_id": "LR"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-3", "parent_id": "XL"},
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0", "Name": "Living Room"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB", "parent_id": "LR"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
    {"LocationID": "CR-CT-2", "Type": "Cart", "Max Spools": "0", "Name": "Cart 2", "parent_id": "CR"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart", "Max Spools": "0", "Name": "Cart 2 row 1",
     "parent_id": "CR-CT-2"},
    {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "Name": "PolyDryer 1"},
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


def _run(sm, call, probe=IDLE):
    return run_move(sm, probe=probe, locations=LOCATIONS, printer_map=PRINTER_MAP, call=call)


def _remove(client, sid, **extra):
    return lambda: client.post("/api/manage_contents",
                               json={"action": "remove", "spool_id": str(sid), **extra}).get_json()


def test_a_homeless_spool_on_a_printing_head_is_asked_once(client):
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}}})
    first = _run(sm, _remove(client, 42), probe=_probe_for({"XL"}))
    assert first["require_confirm"] is True, first
    assert first["confirm_types"] == ["active_print", "unassign"], first
    assert first["msg"] == ("#42 is loaded on XL-3 and has no saved home. Ejecting it leaves it "
                            "Unassigned, and FCC stops charging this print to it. Continue?")
    assert sm.patch_bodies == []
    # ONE Yes: both confirms in one request.
    second = _run(sm, _remove(client, 42, confirmed=True, confirm_active_print=True),
                  probe=_probe_for({"XL"}))
    # Group 42.5a: the answer says where it went (no box let go: no trail).
    assert second == {"success": True, "spool_id": 42, "from": "XL-3", "to": "", "slot": "",
                      "home": False, "released_boxes": []}, second
    assert sm.spools[42]["location"] == ""


def test_a_spool_with_a_saved_home_gets_only_the_print_prompt(client):
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {"physical_source": "LR-MDB-1",
                                                          "physical_source_slot": "3"}}})
    res = _run(sm, _remove(client, 42), probe=_probe_for({"XL"}))
    assert res["require_confirm"] is True and res["confirm_types"] == ["active_print"], res
    assert "ejecting from this toolhead will disrupt the print" in res["msg"], res


def test_the_unassign_prompt_names_a_spool_on_an_idle_head(client):
    """No print, no home: the old text said 'already in a room' about a head."""
    sm = WireSpoolman({42: {"location": "XL-3", "extra": {}}})
    res = _run(sm, _remove(client, 42))
    assert res["confirm_types"] == ["unassign"], res
    assert res["msg"] == "#42 is loaded on XL-3 and has no saved home. Unassign it?"


# The helper is the code perform_smart_eject runs; this pins that the route's
# answer and the eject's real behaviour can't drift, case by case.
@pytest.mark.parametrize("where,extra", [
    ("XL-3", {}),                                            # a toolhead: a printer is not a Room
    ("CR", {}),                                              # loose in a Room
    ("CR-CT-2-R1", {}),                                      # a cart row: its Room (until Group 41 Q1's B)
    ("PM-DB-1", {}),                                         # a PolyDryer: no Room to fall back to
    ("LR-MDB-1", {"physical_source": "XL-3"}),               # a stale toolhead trail is no home
])
def test_the_helper_agrees_with_the_eject(where, extra):
    sm = WireSpoolman({42: {"location": where, "extra": dict(extra)}})
    dest = _run(sm, lambda: logic._eject_destination(
        {"id": 42, "location": where, "extra": dict(extra)}, PRINTER_MAP))
    res = _run(sm, lambda: logic.perform_smart_eject(42, confirm_active_print=True))
    if dest["needs_unassign_confirm"]:
        assert res == "REQUIRE_CONFIRM" and sm.patch_bodies == [], (where, dest, res)
    else:
        assert res is True, (where, dest, res)
        assert sm.spools[42]["location"] == dest["target"], (where, dest, sm.spools[42])
