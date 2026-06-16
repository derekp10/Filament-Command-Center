"""
Group 21.3 — manual assign to a toolhead must auto-eject the resident so a
single head never holds two spools.

perform_smart_move's "Smart Load" branch only fires when the target is a
single-occupancy head. That gate was an inline type list
(['Tool Head', 'MMU Slot', 'Printer']) that omitted 'No MMU Direct Load' — the
Core One direct-load type — even though locations_db.TOOLHEAD_TYPES has always
listed it. A 'No MMU Direct Load' head that wasn't ALSO present in printer_map
(so is_printer couldn't rescue it) therefore skipped the resident eject and
ended up with two spools attached.

These tests pin perform_smart_move's internals with an EMPTY printer_map so
is_printer is always False — the only thing that can trigger the eject is the
is_toolhead type check, isolating the fix.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402


def _run_move(target_type, *, printer_map=None, resident_id=99, new_id=42):
    """Drive perform_smart_move assigning `new_id` onto a head of the given
    Type that already holds `resident_id`. Returns the list of spool ids that
    perform_smart_eject was called with (i.e. the residents that got unseated).
    """
    printer_map = printer_map if printer_map is not None else {}
    target = "CORE1-M0"
    loc_list = [
        {"LocationID": target, "Type": target_type, "Max Spools": "1",
         "Name": "Core One Direct Load"},
    ]
    spool_data = {"id": new_id, "location": "", "extra": {}}
    ejected = []

    def fake_update(sid, data):
        return {"id": sid, **data}

    def fake_eject(rid, *a, **k):
        ejected.append(rid)
        return True

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.locations_db, "get_active_printer_map",
                     return_value=printer_map),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_data),
        # The resident occupying the head — returned for the Smart-Load probe.
        patch.object(logic.spoolman_api, "get_spools_at_location",
                     return_value=[resident_id]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed",
                     return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "Test", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        # Capture every resident eject the move triggers.
        patch.object(logic, "perform_smart_eject", side_effect=fake_eject),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    for m in ctx:
        m.start()
    try:
        logic.perform_smart_move(target, [new_id], origin="test",
                                 confirm_active_print=True)
    finally:
        for m in reversed(ctx):
            m.stop()
    return ejected


def test_no_mmu_direct_load_auto_ejects_resident():
    """The regression: a 'No MMU Direct Load' head not in printer_map must
    still unseat its resident on a manual assign."""
    ejected = _run_move("No MMU Direct Load")
    assert 99 in ejected, (
        "resident #99 was NOT auto-ejected from the No MMU Direct Load head — "
        "is_toolhead missed the type, leaving two spools on one head"
    )


def test_tool_head_auto_ejects_resident():
    """Sanity: the always-supported 'Tool Head' type still auto-ejects (guards
    against the centralization accidentally dropping a type)."""
    assert 99 in _run_move("Tool Head")


def test_mmu_slot_auto_ejects_resident():
    assert 99 in _run_move("MMU Slot")


def test_canonical_toolhead_types_are_all_covered():
    """Every locations_db.TOOLHEAD_TYPES member is treated as single-occupancy
    by perform_smart_move, so this can't silently drift again."""
    for t in logic.locations_db.TOOLHEAD_TYPES:
        assert 99 in _run_move(t), f"type {t!r} skipped the resident auto-eject"


def test_toolhead_types_is_single_canonical_frozenset():
    """locations_db.TOOLHEAD_TYPES collapsed from a duplicate set+frozenset pair
    (2026-06-15 cleanup) to ONE canonical frozenset. Re-introducing a mutable
    ``TOOLHEAD_TYPES = {...}`` duplicate would make the surviving binding a plain
    set, so the isinstance guard catches the drift before it ships."""
    tt = logic.locations_db.TOOLHEAD_TYPES
    assert isinstance(tt, frozenset), (
        f"TOOLHEAD_TYPES must be a frozenset (got {type(tt).__name__}) — a "
        "re-added mutable duplicate likely shadowed the canonical definition"
    )
    assert tt == frozenset({'Tool Head', 'MMU Slot', 'No MMU Direct Load'})
