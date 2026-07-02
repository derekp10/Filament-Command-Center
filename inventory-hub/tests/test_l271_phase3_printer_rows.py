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
import os

import pytest

import locations_db


def _read_app():
    """Concatenated source of app.py + the L316 carve modules — the blocks
    these canaries grep for now live across several flat modules extracted
    from app.py. See tests/source_family.py."""
    import source_family
    return source_family.read_app_family()


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


def test_collision_non_toolhead_row_is_not_promoted():
    """Review fix: a non-toolhead row (e.g. a Room) that shares a printer-prefix
    LocationID must NOT be corrupted into a Printer, and no duplicate appended."""
    rows = [{"LocationID": "XL", "Type": "Room", "Name": "Lounge", "parent_id": None}]
    out, changed = locations_db.migrate_printers_to_rows_if_needed(
        rows, {"XL-1": {"printer_name": "XL", "position": 0}})
    assert changed is False
    xl = [r for r in out if r["LocationID"] == "XL"]
    assert len(xl) == 1 and xl[0]["Type"] == "Room", "the colliding Room must be left untouched"


def test_collision_toolhead_plus_other_type_skips():
    """A prefix with BOTH a toolhead and a conflicting non-toolhead row is
    ambiguous — skip rather than guess."""
    rows = [
        {"LocationID": "XL", "Type": "Room", "Name": "Lounge"},
        {"LocationID": "XL", "Type": "Tool Head", "Name": "th", "Max Spools": "1"},
    ]
    out, changed = locations_db.migrate_printers_to_rows_if_needed(
        rows, {"XL-1": {"printer_name": "x", "position": 0}})
    assert changed is False
    assert not any(r["Type"] == "Printer" for r in out)


def test_exact_key_name_wins_over_prefix():
    """A dash-free exact key wins over a dashed toolhead-prefix match."""
    pm = {"CORE1-M0": {"printer_name": "WRONG toolhead name", "position": 0},
          "CORE1": {"printer_name": "🦦 Core One Upgraded", "position": 0}}
    out, _ = locations_db.migrate_printers_to_rows_if_needed(
        [{"LocationID": "CORE1", "Type": "Tool Head", "Name": "x", "Max Spools": "1"}], pm)
    core1 = [r for r in out if r["LocationID"] == "CORE1"][0]
    assert core1["Name"] == "🦦 Core One Upgraded"


def test_multiple_blank_stubs_all_removed():
    rows = [
        {"LocationID": "CORE1", "Type": "Tool Head", "Name": "x", "Max Spools": "1"},
        {"LocationID": "CORE1", "Type": "", "Name": "stub1"},
        {"LocationID": "CORE1", "Type": "  ", "Name": "stub2"},
    ]
    out, changed = locations_db.migrate_printers_to_rows_if_needed(
        rows, {"CORE1": {"printer_name": "C", "position": 0}})
    assert changed is True
    core1 = [r for r in out if r["LocationID"] == "CORE1"]
    assert len(core1) == 1 and core1[0]["Type"] == "Printer"


def test_printer_is_a_valid_slot_container_type():
    """Review fix: 'Printer' must be an accepted slot-assignment target — a
    dual-role printer (Core One) is its own deploy slot, else LOC:CORE1:SLOT:1
    scans 400."""
    import re
    m = re.search(r"container_types = \{([^}]*)\}", _read_app())
    assert m and "'Printer'" in m.group(1), "container_types must include 'Printer'"


def test_printer_map_put_resyncs_printer_rows():
    """Review fix: the /api/printer_map PUT handler must re-run the migration so
    a newly-added printer becomes first-class without a reboot (the migration is
    referenced in BOTH the startup block and the PUT handler)."""
    assert _read_app().count("migrate_printers_to_rows_if_needed") >= 2


def test_synthesizer_no_longer_injects_printers():
    """The /api/locations synthesizer must no longer conjure Type:'Printer'
    rows — printers are first-class on disk now. Guards against re-introducing
    the prefix-grouping printer synthesis (the source of the CORE1 'Virtual
    Room' quirk)."""
    app = _read_app()
    assert "printer_prefixes_to_inject" not in app, "the printer-prefix synthesis seed must stay retired"
    assert '"Type": "Printer" if is_printer' not in app, "the synthesizer must not set Type:Printer"


@pytest.mark.integration
def test_printers_are_first_class_on_disk(api_base_url, require_server):
    """Live: XL and the Core One surface as Type:'Printer' rows, and CORE1
    carries its real printer name (the fixed quirk), not 'CORE1 (Room)'."""
    import requests
    rows = requests.get(f"{api_base_url}/api/locations", timeout=10).json()
    by = {str(r.get("LocationID")): r for r in rows}
    assert by.get("XL", {}).get("Type") == "Printer"
    core1 = by.get("CORE1", {})
    assert core1.get("Type") == "Printer", f"CORE1 should be a Printer, got {core1.get('Type')!r}"
    assert "(Room)" not in str(core1.get("Name", "")), (
        f"CORE1 still shows the room-quirk name: {core1.get('Name')!r}"
    )
