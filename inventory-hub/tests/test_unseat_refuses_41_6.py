"""Group 41.6 — a spool is never seated in a slot the engine couldn't clear.

The slot block in _perform_smart_move_impl read the slot with the fail-open
reader (a Spoolman timeout looked like an empty slot) and, when the unseat of
the current occupant was rejected, only logged it and seated the incoming spool
anyway, so two spools claimed one slot. Now the slot read is strict, and a
failed read or unseat records a failure for the incoming spool and writes
nothing for it. The real engine runs against tests/move_engine_harness.py.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, run_move  # noqa: E402

LOCATIONS = [
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0"},
]


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _sm(**kw):
    return FakeSpoolman({
        7: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}},
        42: {"location": "CR-CT-2-R1", "extra": {}},
    }, **kw)


def _in_slot(sm, box, slot):
    return sorted(sid for sid, r in sm.spools.items()
                  if r.get("location") == box and (r.get("extra") or {}).get("container_slot") == slot)


def _move_42_into_slot_2(sm):
    return run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map={},
                    target="LR-MDB-1", raw_spools=[42], target_slot="2")


def test_a_rejected_unseat_leaves_the_incoming_spool_where_it_was(logs):
    """FAILS on the old engine: #7's unseat was rejected and only logged, then
    #42 was seated in slot 2 anyway, so slot 2 held both."""
    sm = _sm(reject_ids=[7])
    res = _move_42_into_slot_2(sm)
    why = logic.smart_move_failure(res, 42)
    assert "couldn't unseat #7 from slot 2" in why, res
    assert sm.spools[42]["location"] == "CR-CT-2-R1", "the incoming spool was moved"
    assert _in_slot(sm, "LR-MDB-1", "2") == [7]
    assert any("Not moving Spool #42 into LR-MDB-1 slot 2" in m and a[0] == "ERROR" for m, a in logs), logs


def test_an_unreadable_slot_seats_nothing(logs):
    """FAILS on the old engine: the fail-open read answered [] on a Spoolman
    timeout, so #42 was seated over #7 without unseating it."""
    sm = _sm()
    sm.list_reads_fail = True
    res = _move_42_into_slot_2(sm)
    assert "couldn't read LR-MDB-1 from Spoolman" in logic.smart_move_failure(res, 42), res
    assert sm.spools[42]["location"] == "CR-CT-2-R1"
    assert _in_slot(sm, "LR-MDB-1", "2") == [7]


def test_an_accepted_unseat_still_seats_the_incoming_spool(logs):
    """Control (passes on the old engine too): #7 leaves slot 2, #42 takes it."""
    sm = _sm()
    res = _move_42_into_slot_2(sm)
    assert logic.smart_move_failure(res, 42) == "", res
    assert _in_slot(sm, "LR-MDB-1", "2") == [42]
    assert sm.spools[7]["location"] == "LR-MDB-1" and sm.spools[7]["extra"]["container_slot"] == ""
