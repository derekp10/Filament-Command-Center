"""Group 39.7 (R1-03): Smart Load's resident list fails closed.

Loading a spool onto a toolhead first unloads the spool already on it. The list
of what the head holds was read fail-OPEN (get_spools_at_location swallows a
Spoolman error and answers []), so a Spoolman blip made an occupied head look
empty and the incoming spool landed on top of the resident: two spools on one
head. The list is now read with get_spools_at_location_detailed_strict; when it
raises, the move answers status error with a failure per incoming spool, logs
ERROR, and writes nothing.

R1-02 rides along: the matcher's rows already say which hits are ghosts or a
Printer row's prefix hits, so those are skipped without a get_spool of their own.

The REAL engine runs through tests/move_engine_harness.py; `list_reads_fail`
makes the fail-open readers answer [] and the strict reader raise, as Spoolman
being down does in production.
HEAD proof: on the pre-39.7 engine the first two tests load on top of #99
(status success, XL-1 holds both), and the ghost test reads #77.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import state  # noqa: E402
from move_engine_harness import IDLE, WireSpoolman, run_move  # noqa: E402

PRINTER_MAP = {"XL-1": {"printer_name": "XL", "position": 0}}
LOCATIONS = [
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB"},
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


def _move(sm, spool_id=42):
    return run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map=PRINTER_MAP,
                    target="XL-1", raw_spools=[spool_id])


def test_an_unreadable_resident_list_refuses_the_load():
    """The task file's pin: the list read raises, so XL-1 still holds only #99,
    the answer is status error, and nothing was written."""
    sm = WireSpoolman({99: {"location": "XL-1", "extra": {}},
                       42: {"location": "CR", "extra": {}}})
    sm.list_reads_fail = True
    res = _move(sm)
    assert res.get("status") == "error", res
    assert res.get("failures") == {"42": "could not read XL-1 from Spoolman"}, res
    assert sm.direct_at("XL-1") == [99], f"XL-1 holds {sm.direct_at('XL-1')}"
    assert sm.writes == [] and sm.patch_bodies == [], f"wrote {sm.writes}"
    errors = [e for e in state.RECENT_LOGS if e.get("type") == "ERROR"]
    assert any("#42" in e.get("msg", "") and "could not read XL-1" in e.get("msg", "")
               for e in errors), state.RECENT_LOGS
    assert state.UNDO_STACK == [], "a refused move left an undo record"


def test_every_incoming_spool_gets_the_failure():
    sm = WireSpoolman({99: {"location": "XL-1", "extra": {}},
                       42: {"location": "CR", "extra": {}},
                       43: {"location": "CR", "extra": {}}})
    sm.list_reads_fail = True
    res = run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map=PRINTER_MAP,
                   target="XL-1", raw_spools=[42, 43])
    assert res.get("status") == "error", res
    assert set(res.get("failures", {})) == {"42", "43"}, res
    assert sm.writes == []


def test_a_ghost_costs_no_read_and_does_not_block():
    """#77 passed through XL-1 and now sits in the dryer box: its stale
    physical_source still names XL-1, so the matcher returns it. It is not a
    resident, so it is neither read nor ejected, and #42 loads."""
    sm = WireSpoolman({77: {"location": "LR-MDB-1",
                            "extra": {"physical_source": "XL-1", "container_slot": "2"}},
                       42: {"location": "CR", "extra": {}}})
    reads = []
    real_get = sm.get_spool

    def counting_get(sid):
        reads.append(int(sid))
        return real_get(sid)
    sm.get_spool = counting_get
    res = _move(sm)
    assert res.get("status") == "success", res
    assert sm.direct_at("XL-1") == [42]
    assert sm.spools[77]["location"] == "LR-MDB-1"
    assert 77 not in reads, f"read the ghost #77: {reads}"


def test_a_readable_resident_is_still_unloaded():
    sm = WireSpoolman({99: {"location": "XL-1", "extra": {}},
                       42: {"location": "CR", "extra": {}}})
    res = _move(sm)
    assert res.get("status") == "success", res
    assert sm.direct_at("XL-1") == [42]
    assert sm.spools[99]["location"] != "XL-1"


def test_a_resident_whose_own_read_fails_still_refuses():
    """The list names #99 as a direct resident but its own read fails: refuse,
    as before 39.7 (the eject could not snapshot or move it)."""
    sm = WireSpoolman({99: {"location": "XL-1", "extra": {}},
                       42: {"location": "CR", "extra": {}}}, unreadable=[99])
    res = _move(sm)
    assert res.get("status") == "error", res
    assert "could not be read" in res["failures"]["42"], res
    assert sm.direct_at("XL-1") == [99]
    assert sm.patch_bodies == []


def test_a_spool_loaded_during_the_printer_probe_is_unloaded_too():
    """Review engine-2. The resident list is read in step 4, before the printer
    probe, which waits seconds on an unreachable printer. Another request that
    loads #57 onto XL-1 meanwhile (#196 out, #57 in) must not leave XL-1 holding
    #42 and #57: step 6 re-lists the head strictly after the probe."""
    sm = WireSpoolman({42: {"location": "CR", "extra": {}},
                       57: {"location": "CR", "extra": {}},
                       196: {"location": "XL-1", "extra": {}}})

    def offline_probe_with_a_concurrent_load(_url, _name):
        sm.spools[196]["location"] = "CR"
        sm.spools[57]["location"] = "XL-1"
        return None   # unreachable: fail open

    res = run_move(sm, probe=offline_probe_with_a_concurrent_load, locations=LOCATIONS,
                   printer_map=PRINTER_MAP, target="XL-1", raw_spools=[42], confirm_active_print=[])
    assert res.get("status") == "success", res
    assert sm.direct_at("XL-1") == [42], f"XL-1 holds {sm.direct_at('XL-1')}"
