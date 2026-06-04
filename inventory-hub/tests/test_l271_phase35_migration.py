"""L271 Phase 3.5 — immediate-parent + printer-room migration tests.

`migrate_immediate_parent_ids_if_needed` re-derives every row's parent_id from
the flat first-segment to its IMMEDIATE parent and nests printers under their
room. These pin the exact re-parenting, idempotency, override-respect, the
printer-room derivation order, and the PM/PJ/TST fallback.

Pure-function — operates on in-memory fixture lists, no disk / no server.
"""
import copy

import pytest

import locations_db as L


def _pid(rows):
    return {r["LocationID"]: r.get("parent_id") for r in rows}


# A flat (Phase 1A/2.5) tree mirroring the dev shape: rooms + carts + cart-rows,
# a printer with toolheads (room auto-derivable), a dual-role printer (override),
# and PM (pseudo, no on-disk room row).
def _flat_tree():
    return [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "parent_id": None},
        {"LocationID": "CR-CT-1", "Type": "Cart", "parent_id": "CR"},
        {"LocationID": "CR-CT-1-R1", "Type": "Cart", "parent_id": "CR"},
        {"LocationID": "CR-CT-1-R2", "Type": "Cart", "parent_id": "CR"},
        {"LocationID": "CR-WLN-R1-SC1", "Type": "Shelf", "parent_id": "CR"},  # no CR-WLN row -> stays CR
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "parent_id": "LR"},
        {"LocationID": "XL", "Name": "XL", "Type": "Printer", "parent_id": None},
        {"LocationID": "XL-1", "Type": "Tool Head", "Location": "Living Room", "parent_id": "XL"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Location": "Living Room", "parent_id": "XL"},
        {"LocationID": "CORE1", "Name": "Core One", "Type": "Printer", "parent_id": None},  # no toolheads
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "parent_id": "PM"},  # PM has no room row
    ]


def test_reparents_cart_rows_to_carts_and_printers_to_rooms():
    rows = _flat_tree()
    out, changed = L.migrate_immediate_parent_ids_if_needed(rows)
    assert changed is True
    pid = _pid(out)
    # cart-rows -> their cart
    assert pid["CR-CT-1-R1"] == "CR-CT-1"
    assert pid["CR-CT-1-R2"] == "CR-CT-1"
    # cart stays under the room (CR-CT not a row)
    assert pid["CR-CT-1"] == "CR"
    # shelf with no intermediate row stays under the room
    assert pid["CR-WLN-R1-SC1"] == "CR"
    # toolheads stay under their printer
    assert pid["XL-1"] == "XL"
    # printer with toolheads -> room auto-derived from toolhead Location
    assert pid["XL"] == "LR"
    # dual-role printer (no toolheads) -> override map room
    assert pid["CORE1"] == "CR"
    # PM box keeps its pseudo-prefix (no on-disk PM room row)
    assert pid["PM-DB-1"] == "PM"
    # untouched rows
    assert pid["LR-MDB-1"] == "LR"


def test_idempotent_second_run_is_noop():
    rows = _flat_tree()
    out1, changed1 = L.migrate_immediate_parent_ids_if_needed(rows)
    assert changed1 is True
    out2, changed2 = L.migrate_immediate_parent_ids_if_needed(copy.deepcopy(out1))
    assert changed2 is False
    assert _pid(out1) == _pid(out2)


def test_respects_operator_override():
    rows = _flat_tree()
    # Operator deliberately re-parented CR-CT-1-R1 somewhere that differs from
    # BOTH the flat default (CR) and the immediate parent (CR-CT-1).
    for r in rows:
        if r["LocationID"] == "CR-CT-1-R1":
            r["parent_id"] = "LR"
    out, _ = L.migrate_immediate_parent_ids_if_needed(rows)
    assert _pid(out)["CR-CT-1-R1"] == "LR"  # left untouched


def test_printer_room_override_used_when_autoderive_fails():
    # XL with NO toolhead Location -> falls back to override map (LR).
    rows = [
        {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "parent_id": None},
        {"LocationID": "XL", "Type": "Printer", "parent_id": None},
        {"LocationID": "XL-1", "Type": "Tool Head", "parent_id": "XL"},  # no Location field
    ]
    out, _ = L.migrate_immediate_parent_ids_if_needed(rows)
    assert _pid(out)["XL"] == "LR"


def test_printer_room_autoderive_beats_override_when_present():
    # A toolhead Location pointing at a DIFFERENT room than the override wins
    # (auto-derive is primary; override is only a fallback).
    rows = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "parent_id": None},
        {"LocationID": "XL", "Type": "Printer", "parent_id": None},
        {"LocationID": "XL-1", "Type": "Tool Head", "Location": "Computer Room", "parent_id": "XL"},
    ]
    out, _ = L.migrate_immediate_parent_ids_if_needed(rows)
    assert _pid(out)["XL"] == "CR"  # auto-derived from the toolhead, not the LR override


def test_printer_unresolvable_room_left_unchanged():
    # Unknown printer with no toolheads, no Location, not in the override map.
    rows = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "parent_id": None},
        {"LocationID": "ZZZ", "Type": "Printer", "parent_id": None},
    ]
    out, changed = L.migrate_immediate_parent_ids_if_needed(rows)
    assert _pid(out)["ZZZ"] is None  # untouched
    assert changed is False


def test_printer_room_with_no_room_row_rejected():
    # Override resolves CORE1 -> CR, but there's NO on-disk CR room row.
    rows = [
        {"LocationID": "CORE1", "Type": "Printer", "parent_id": None},
    ]
    out, changed = L.migrate_immediate_parent_ids_if_needed(rows)
    assert _pid(out)["CORE1"] is None  # rejected: dangling FK not written
    assert changed is False


def test_pre_1a_row_without_parent_id_gets_immediate():
    rows = [
        {"LocationID": "CR", "Name": "Computer Room", "Type": "Room"},  # no parent_id key
        {"LocationID": "CR-CT-1", "Type": "Cart"},                      # no parent_id key
        {"LocationID": "CR-CT-1-R1", "Type": "Cart"},                   # no parent_id key
    ]
    out, changed = L.migrate_immediate_parent_ids_if_needed(rows)
    assert changed is True
    pid = _pid(out)
    assert pid["CR"] is None
    assert pid["CR-CT-1"] == "CR"
    assert pid["CR-CT-1-R1"] == "CR-CT-1"


def test_non_list_input_safe():
    out, changed = L.migrate_immediate_parent_ids_if_needed("not a list")
    assert out == "not a list"
    assert changed is False
