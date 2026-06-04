"""L271 Phase 3 — first-class Printer rows migration (locations_db).

`migrate_printers_to_rows_if_needed` persists each printer in config.json's
printer_map as a Type:"Printer" row in locations.json so /api/locations no
longer synthesizes them. parent_id stays None this phase (printers render as
top-level roots; room-nesting is a later phase — Derek 2026-06-03).

Covers the two real-world shapes: XL (no on-disk row → append) and CORE1
(dash-free dual-role: a Tool Head row + a duplicate blank-Type stub → promote
in place + drop the stub), plus idempotency and name resolution.
"""
import copy

import locations_db


PRINTER_MAP = {
    "XL-1": {"printer_name": "🦝 XL", "position": 0},
    "XL-2": {"printer_name": "🦝 XL", "position": 1},
    "CORE1": {"printer_name": "🦝 Core One Upgraded", "position": 0},
}


def _toolheads():
    return [
        {"LocationID": "XL-1", "Type": "Tool Head", "Name": "XL T1", "parent_id": "XL", "Max Spools": "1"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Name": "XL T2", "parent_id": "XL", "Max Spools": "1"},
    ]


def test_xl_appends_first_class_printer_row():
    rows = _toolheads()
    out, changed = locations_db.migrate_printers_to_rows_if_needed(rows, PRINTER_MAP)
    assert changed is True
    xl = [r for r in out if r["LocationID"] == "XL"]
    assert len(xl) == 1
    assert xl[0]["Type"] == "Printer"
    assert xl[0]["Name"] == "🦝 XL"
    assert xl[0]["parent_id"] is None         # top-level root for now (nest later)
    assert xl[0]["Max Spools"] == "0"         # aggregates its toolhead children
    # the toolhead children are untouched
    assert [r for r in out if r["LocationID"] == "XL-1"][0]["parent_id"] == "XL"


def test_core1_dualrole_promote_and_dedupe():
    rows = _toolheads() + [
        {"LocationID": "CORE1", "Type": "Tool Head", "Name": "🦝 Core One Upgraded Tool Head",
         "parent_id": None, "Max Spools": "1"},
        {"LocationID": "CORE1", "Type": "", "Name": "CORE1", "parent_id": None, "Max Spools": "0"},
    ]
    out, changed = locations_db.migrate_printers_to_rows_if_needed(rows, PRINTER_MAP)
    assert changed is True
    core1 = [r for r in out if r["LocationID"] == "CORE1"]
    assert len(core1) == 1, "the blank-Type duplicate must be removed"
    assert core1[0]["Type"] == "Printer"
    assert core1[0]["Name"] == "🦝 Core One Upgraded"
    assert core1[0]["Max Spools"] == "1", "dual-role deploy-slot capacity preserved"
    assert core1[0]["parent_id"] is None


def test_idempotent_second_run_is_noop():
    rows = _toolheads() + [
        {"LocationID": "CORE1", "Type": "Tool Head", "Name": "x", "parent_id": None, "Max Spools": "1"},
        {"LocationID": "CORE1", "Type": "", "Name": "CORE1", "parent_id": None, "Max Spools": "0"},
    ]
    out1, changed1 = locations_db.migrate_printers_to_rows_if_needed(rows, PRINTER_MAP)
    assert changed1 is True
    snapshot = copy.deepcopy(out1)
    out2, changed2 = locations_db.migrate_printers_to_rows_if_needed(out1, PRINTER_MAP)
    assert changed2 is False, "second boot must be a no-op"
    assert out2 == snapshot


def test_non_list_and_empty_map_are_noops():
    assert locations_db.migrate_printers_to_rows_if_needed("nope", PRINTER_MAP) == ("nope", False)
    out, changed = locations_db.migrate_printers_to_rows_if_needed(_toolheads(), {})
    assert changed is False


def test_printer_name_fallback():
    out, changed = locations_db.migrate_printers_to_rows_if_needed([], {"ZZ-1": {"position": 0}})
    zz = [r for r in out if r["LocationID"] == "ZZ"]
    assert zz and zz[0]["Name"] == "ZZ System"
