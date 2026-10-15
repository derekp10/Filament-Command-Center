"""
Unit tests for the auto-slot-pick behavior in logic.perform_smart_move.

When a caller asks to move a spool into a slotted container (Max Spools > 1)
without specifying `target_slot`, logic.perform_smart_move should pick the
lowest-numbered free slot automatically. This replaces the prior behavior
where the spool would land with an empty container_slot (effectively staging).

Tests mock the Spoolman / filabridge / state helpers so they run on the host
without needing a live container. The spec:

  - If Max Spools > 1 AND target_slot is omitted AND at least one slot is free,
    pick a slot by the slot picker's rule (Group 40.0e, logic.recommend_box_slot):
    the spool's own slot when it already sits in the box, else the lowest free
    slot that loads no busy toolhead, else the lowest free slot.
  - If every slot is occupied, leave target_slot as None (caller's explicit
    slot-less move stays unchanged — no surprise unseat).
  - If the target is single-occupancy (toolhead, MMU slot, etc.) or flat
    (room), auto-slot-pick must not fire.
  - If the caller explicitly passes target_slot, that value wins regardless
    of whether the slot is free.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402


FAKE_LOCATIONS = [
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "LR MDB"},
    {"LocationID": "CORE1-M0", "Type": "Tool Head", "Max Spools": "1", "Name": "M0"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
]


def _held(sid, slot):
    """A box item in the shape spoolman_api._build_location_match gives it (Group
    40.0e reads `location` / `is_ghost`, so a bare {id, slot} could pass for
    the wrong reason)."""
    return {"id": sid, "slot": slot, "location": "LR-MDB-1", "is_ghost": False}


def _capture_update_spool_calls():
    """Return (patches, recorded_calls) so tests can assert on what extras landed."""
    calls = []

    def _fake_update(sid, payload):
        calls.append((sid, payload))
        return {"id": sid}

    return _fake_update, calls


def _run_move(target, spools=None, target_slot=None, existing_at_target=None):
    """Run perform_smart_move with all side-effect deps patched. Returns
    (return_value, list_of_update_spool_calls)."""
    if spools is None:
        spools = [42]
    if existing_at_target is None:
        existing_at_target = []

    fake_update, recorded = _capture_update_spool_calls()
    import contextlib

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(logic.locations_db, "load_locations_list", return_value=FAKE_LOCATIONS))
        stack.enter_context(patch.object(logic.config_loader, "load_config", return_value={"printer_map": {}}))
        stack.enter_context(patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")))
        stack.enter_context(patch.object(
            logic.spoolman_api, "get_spools_at_location_detailed", return_value=existing_at_target
        ))
        # Smart Load's resident read on a single-occupancy target (strict since
        # Group 39.7).
        stack.enter_context(patch.object(
            logic.spoolman_api, "get_spools_at_location_detailed_strict", return_value=existing_at_target
        ))
        stack.enter_context(patch.object(
            logic.spoolman_api, "get_spool", return_value={
                "id": 42, "location": "CR", "extra": {}, "name": "Test",
            }
        ))
        stack.enter_context(patch.object(
            logic.spoolman_api, "format_spool_display",
            return_value={"text": "#42 Test", "color": "ffffff"},
        ))
        stack.enter_context(patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update))
        stack.enter_context(patch.object(logic.state, "add_log_entry"))

        result = logic.perform_smart_move(
            target, spools, target_slot=target_slot, origin="test", auto_deploy=False
        )

    return result, recorded


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_auto_slot_pick_chooses_first_free_slot_when_box_empty():
    """Empty dryer box → first spool lands in slot 1."""
    _, calls = _run_move("LR-MDB-1", existing_at_target=[])
    # One update_spool call.
    assert len(calls) == 1
    _, payload = calls[0]
    # container_slot picked automatically.
    assert payload["extra"].get("container_slot") == "1"


def test_auto_slot_pick_skips_occupied_slots():
    """Slots 1 and 2 are taken → auto-pick slot 3."""
    _, calls = _run_move(
        "LR-MDB-1",
        existing_at_target=[_held(101, "1"), _held(102, "2")],
    )
    _, payload = calls[0]
    assert payload["extra"].get("container_slot") == "3"


def test_auto_slot_pick_handles_noncontiguous_occupied_slots():
    """Only slot 2 is taken → slot 1 is still the lowest free."""
    _, calls = _run_move(
        "LR-MDB-1",
        existing_at_target=[_held(101, "2")],
    )
    _, payload = calls[0]
    assert payload["extra"].get("container_slot") == "1"


def test_auto_slot_pick_keeps_a_spools_own_slot_in_the_same_box():
    """The moving spool already sits in slot 3 of the target: it keeps slot 3.
    Group 40.0e (the slot picker's rule 1, Derek's D2.1): it used to hop to the
    lowest free slot, which can feed a different toolhead. Slots 1 and 2 are
    free here. (This test was test_auto_slot_pick_ignores_own_slot_for_reassigns,
    whose fake item had no `location`, as a real box listing always does.)"""
    _, calls = _run_move(
        "LR-MDB-1",
        existing_at_target=[{"id": 42, "slot": "3", "location": "LR-MDB-1", "is_ghost": False}],
    )
    _, payload = calls[0]
    assert payload["extra"].get("container_slot") == "3"


def test_auto_slot_pick_puts_a_deployed_spool_back_in_its_own_slot():
    """A spool deployed FROM slot 3 is listed in the box as a ghost of slot 3, and
    physically still sits in slot 3, so a slotless move into the box puts it back
    there (Group 40 review; it used to take the lowest free slot, which loaded
    another head)."""
    _, calls = _run_move(
        "LR-MDB-1",
        existing_at_target=[{"id": 42, "slot": "3", "location": "LR-MDB-1", "is_ghost": True}],
    )
    _, payload = calls[0]
    assert payload["extra"].get("container_slot") == "3"


def test_auto_slot_pick_leaves_slot_empty_when_box_is_full():
    """All 4 slots occupied → leave target_slot as None (caller meant staging)."""
    _, calls = _run_move(
        "LR-MDB-1",
        existing_at_target=[_held(101, "1"), _held(102, "2"), _held(103, "3"), _held(104, "4")],
    )
    _, payload = calls[0]
    # When no free slot is found, target_slot stays None, which the downstream
    # else-branch normalizes to container_slot = "".
    assert payload["extra"].get("container_slot") == ""


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------

def test_auto_slot_pick_does_not_trigger_on_single_occupancy_target():
    """Toolheads (Max Spools = 1) shouldn't auto-slot-pick — they're flat."""
    _, calls = _run_move("CORE1-M0", existing_at_target=[])
    _, payload = calls[0]
    # container_slot cleared normally via the else-branch; never "1".
    assert payload["extra"].get("container_slot") == ""


def test_auto_slot_pick_does_not_trigger_on_room_target():
    """Rooms (Max Spools = 0) shouldn't auto-slot-pick either."""
    _, calls = _run_move("CR", existing_at_target=[])
    _, payload = calls[0]
    assert payload["extra"].get("container_slot") == ""


def test_explicit_slot_always_wins_even_when_slot_occupied():
    """When target_slot is given, auto-pick must not override it — the normal
    unseat logic runs instead."""
    _, calls = _run_move(
        "LR-MDB-1",
        target_slot="2",
        existing_at_target=[{"id": 101, "slot": "2"}, {"id": 102, "slot": "3"}],
    )
    # The moved spool lands in the explicit slot (unseating logic runs, asserted
    # via the final update_spool call for sid=42).
    update_42 = [p for (sid, p) in calls if sid == 42]
    assert update_42, "expected an update_spool call for the moved spool"
    assert update_42[0]["extra"].get("container_slot") == "2"


def test_auto_slot_pick_does_not_trigger_on_bulk_move():
    """A bulk move of 2+ spools into a slotted container without an explicit
    slot must NOT auto-pick — otherwise all spools share one slot and each
    unseats the previous. Slotless bulk moves stay slotless (staging behavior).
    """
    _, calls = _run_move(
        "LR-MDB-1",
        spools=[42, 43, 44],
        existing_at_target=[],
    )
    # One update_spool call per spool, all with empty container_slot.
    assert len(calls) == 3
    for _sid, payload in calls:
        assert payload["extra"].get("container_slot") == ""
