"""Group 51.4 — 40.0d's free-feed-slot check compares slots in one form.

logic._free_feed_slots compared effective_slot(...) == slot raw, so a slot
stored as "02" (or quoted) read as free. A spare scanned onto a head records a
feed slot as its home only when exactly ONE free slot feeds the head (Group
40.0d), so the held slot became the new spool's recorded home too: two spools
claimed LR-MDB-1 slot 2. Runs the REAL engine (tests/move_engine_harness.py).

Base proof (52741e6): the zero-padded form fails there (slot 2 reads free, and
#42 records LR-MDB-1:2). The quoted form and the control pass on both: the
location reader already strips quotes; they stay as guards.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, run_move  # noqa: E402

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2)],
    # Slot 2 is XL-2's only feed.
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2"}}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


def _spools(held_slot):
    # #42 is Unassigned: a spool from a plain place keeps that place as its trail,
    # and only a spool with none gets a feed slot recorded (Group 40.0d).
    return {42: {"location": "", "extra": {}},
            77: {"location": "LR-MDB-1", "extra": {"container_slot": held_slot}}}


@pytest.mark.parametrize("held_slot", ["02", '"2"'], ids=["zero-padded", "quoted"])
def test_a_held_slot_in_another_form_is_not_free(held_slot):
    sm = FakeSpoolman(_spools(held_slot))
    with patch.object(logic.spoolman_api, "get_spools_at_location_detailed_strict",
                      side_effect=sm.at_location_detailed_strict):
        free, why = logic._free_feed_slots("XL-2", copy.deepcopy(ROWS), 42)
    assert (free, why) == ([], ""), free


@pytest.mark.parametrize("held_slot", ["02", '"2"'], ids=["zero-padded", "quoted"])
def test_a_spare_onto_the_head_records_no_home_in_a_held_slot(held_slot):
    sm = FakeSpoolman(_spools(held_slot))
    res = run_move(sm, probe=IDLE, printer_map=PRINTER_MAP, locations=copy.deepcopy(ROWS),
                   target="XL-2", raw_spools=[42], origin="test")
    assert res["status"] == "success" and not res["failures"], res
    assert "recorded_source" not in res, res
    extra = sm.spools[42]["extra"]
    assert not extra.get("physical_source") and not extra.get("physical_source_slot"), extra


def test_control_a_free_feed_slot_is_still_recorded():
    """Control (green on the base too): slot 2 is empty, so it is #42's home."""
    sm = FakeSpoolman({42: {"location": "", "extra": {}}})
    res = run_move(sm, probe=IDLE, printer_map=PRINTER_MAP, locations=copy.deepcopy(ROWS),
                   target="XL-2", raw_spools=[42], origin="test")
    assert res.get("recorded_source") == "LR-MDB-1:2", res
