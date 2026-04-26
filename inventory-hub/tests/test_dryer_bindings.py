"""
Unit tests for Phase 2 data layer and API: per-slot Dryer Box bindings,
feeder_map migration, validation, and reverse lookup.
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import locations_db  # noqa: E402
import app as app_module  # noqa: E402
import state  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def tmp_locations_file(tmp_path, monkeypatch):
    """Point JSON_FILE at a temp path so save/load is isolated."""
    fake = tmp_path / "locations.json"
    monkeypatch.setattr(locations_db, "JSON_FILE", str(fake))
    return fake


@pytest.fixture
def printer_map():
    return {
        "XL-1": {"printer_name": "🦝 XL", "position": 0},
        "XL-2": {"printer_name": "🦝 XL", "position": 1},
        "XL-3": {"printer_name": "🦝 XL", "position": 2},
        "XL-4": {"printer_name": "🦝 XL", "position": 3},
        "XL-5": {"printer_name": "🦝 XL", "position": 4},
        "CORE1-M0": {"printer_name": "🦝 Core One", "position": 0},
        "CORE1-M1": {"printer_name": "🦝 Core One", "position": 0},
    }


@pytest.fixture
def sample_locs():
    return [
        {"LocationID": "PM-DB-XL-L", "Type": "Dryer Box", "Max Spools": "4", "Name": "XL Left"},
        {"LocationID": "PM-DB-XL-R", "Type": "Dryer Box", "Max Spools": "2", "Name": "XL Right"},
        {"LocationID": "PM-DB-CORE1", "Type": "Dryer Box", "Max Spools": "1", "Name": "Core One Feeder"},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-4", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-5", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "CORE1-M0", "Type": "No MMU Direct Load", "Max Spools": "1"},
        {"LocationID": "CORE1-M1", "Type": "MMU Slot", "Max Spools": "1"},
        {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    ]


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def test_migrate_feeder_map_seeds_empty_bindings(sample_locs):
    feeder_map = {"PM-DB-XL-L": "XL-1", "PM-DB-CORE1": "CORE1-M0"}
    out, changed = locations_db.migrate_feeder_map_if_needed(sample_locs, feeder_map)
    assert changed is True
    xl_l = next(r for r in out if r["LocationID"] == "PM-DB-XL-L")
    core = next(r for r in out if r["LocationID"] == "PM-DB-CORE1")
    assert xl_l["extra"]["slot_targets"] == {"1": "XL-1"}
    assert core["extra"]["slot_targets"] == {"1": "CORE1-M0"}


def test_migrate_feeder_map_is_idempotent(sample_locs):
    feeder_map = {"PM-DB-XL-L": "XL-1"}
    first, first_changed = locations_db.migrate_feeder_map_if_needed(sample_locs, feeder_map)
    _, second_changed = locations_db.migrate_feeder_map_if_needed(first, feeder_map)
    assert first_changed is True
    assert second_changed is False, "second run should detect existing slot_targets and skip"


def test_migrate_feeder_map_does_not_clobber_existing(sample_locs):
    sample_locs[0]["extra"] = {"slot_targets": {"1": "XL-3", "2": "XL-4"}}
    feeder_map = {"PM-DB-XL-L": "XL-1"}
    out, changed = locations_db.migrate_feeder_map_if_needed(sample_locs, feeder_map)
    assert changed is False
    xl_l = next(r for r in out if r["LocationID"] == "PM-DB-XL-L")
    assert xl_l["extra"]["slot_targets"] == {"1": "XL-3", "2": "XL-4"}


def test_migrate_feeder_map_empty_returns_unchanged(sample_locs):
    out, changed = locations_db.migrate_feeder_map_if_needed(sample_locs, {})
    assert changed is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validate_happy_path(sample_locs, printer_map):
    errors = locations_db.validate_slot_targets(
        {"1": "XL-1", "2": "XL-2", "3": None, "4": ""},
        sample_locs, printer_map
    )
    assert errors == []


def test_validate_rejects_unknown_location(sample_locs, printer_map):
    errors = locations_db.validate_slot_targets(
        {"1": "XL-999"}, sample_locs, printer_map
    )
    assert len(errors) == 1
    slot, target, reason = errors[0]
    assert slot == "1" and target == "XL-999" and "unknown" in reason


def test_validate_rejects_non_toolhead_type(sample_locs, printer_map):
    errors = locations_db.validate_slot_targets(
        {"1": "CR"}, sample_locs, printer_map  # CR is a Room
    )
    assert len(errors) == 1
    assert "not a toolhead" in errors[0][2]


def test_validate_rejects_toolhead_not_in_printer_map(sample_locs, printer_map):
    # XL-5 is in printer_map; remove it and verify rejection.
    pm = dict(printer_map)
    pm.pop("XL-5")
    errors = locations_db.validate_slot_targets(
        {"1": "XL-5"}, sample_locs, pm
    )
    assert len(errors) == 1
    assert "printer_map" in errors[0][2]


def test_validate_allows_mix_of_null_and_real_targets(sample_locs, printer_map):
    errors = locations_db.validate_slot_targets(
        {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": None},
        sample_locs, printer_map
    )
    assert errors == []


# ---------------------------------------------------------------------------
# PRINTER:<id> sentinel — printer-affiliated staging slots
# ---------------------------------------------------------------------------

def test_validate_accepts_printer_sentinel_with_known_prefix(sample_locs, printer_map):
    errors = locations_db.validate_slot_targets(
        {"1": "PRINTER:XL"}, sample_locs, printer_map
    )
    assert errors == []


def test_validate_rejects_printer_sentinel_with_unknown_prefix(sample_locs, printer_map):
    errors = locations_db.validate_slot_targets(
        {"1": "PRINTER:GHOST"}, sample_locs, printer_map
    )
    assert len(errors) == 1
    assert "unknown printer id" in errors[0][2].lower()


def test_validate_rejects_empty_printer_sentinel(sample_locs, printer_map):
    errors = locations_db.validate_slot_targets(
        {"1": "PRINTER:"}, sample_locs, printer_map
    )
    assert len(errors) == 1
    assert "missing id" in errors[0][2].lower()


def test_is_printer_sentinel_helper():
    assert locations_db.is_printer_sentinel("PRINTER:XL")
    assert locations_db.is_printer_sentinel("printer:xl")
    assert not locations_db.is_printer_sentinel("XL-1")
    assert not locations_db.is_printer_sentinel(None)
    assert not locations_db.is_printer_sentinel("")


def test_set_bindings_allows_printer_sentinel_round_trip(sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    ok, errors, _warnings = locations_db.set_dryer_box_bindings(
        "PM-DB-XL-L", {"1": "XL-1", "4": "PRINTER:XL"}, printer_map
    )
    assert ok and errors == []
    got = locations_db.get_dryer_box_bindings("PM-DB-XL-L")
    assert got == {"1": "XL-1", "4": "PRINTER:XL"}


def test_printer_sentinel_skips_cross_box_duplicate_warning(sample_locs, printer_map, tmp_locations_file):
    # Two different boxes both binding slot 1 → PRINTER:XL should NOT warn
    # like it does for duplicate toolhead bindings — a printer pool can be
    # fed by multiple boxes without conflict.
    sample_locs[0]["extra"] = {"slot_targets": {"1": "PRINTER:XL"}}
    locations_db.save_locations_list(sample_locs)
    ok, errors, warnings = locations_db.set_dryer_box_bindings(
        "PM-DB-XL-R", {"1": "PRINTER:XL"}, printer_map
    )
    assert ok and errors == []
    assert not any("already bound" in w[2] for w in warnings), warnings


# ---------------------------------------------------------------------------
# Bug 2b — load_locations_list raises loudly on JSON corruption
# ---------------------------------------------------------------------------

def test_load_locations_list_raises_on_json_decode_error(tmp_locations_file):
    """Regression: a syntax error in locations.json (e.g. a stray comma
    from a manual edit) used to be silently swallowed — load returned [],
    which made the dashboard render with no Names / Types / grouping and
    caused the user to misattribute the symptom to whatever feature was
    being tested at the time. Now it must raise LocationsCorruptError so
    the operator sees the real cause on the first request."""
    tmp_locations_file.write_text(
        '[\n  {\n    "LocationID": "XL-3",\n    "Type": "Tool Head",\n    ,\n    "Order": "3"\n  }\n]',
        encoding="utf-8",
    )
    with pytest.raises(locations_db.LocationsCorruptError) as exc_info:
        locations_db.load_locations_list()
    err = exc_info.value
    assert err.path == str(tmp_locations_file)
    assert err.decode_error.lineno >= 1


def test_load_locations_list_returns_empty_for_missing_file(tmp_locations_file):
    """File-not-present is a legitimate fresh-install state — must NOT
    raise. (This is the carve-out from the bug-2b hardening.)"""
    if tmp_locations_file.exists():
        tmp_locations_file.unlink()
    assert locations_db.load_locations_list() == []


def test_load_locations_list_returns_empty_for_non_list_root(tmp_locations_file):
    """A valid JSON file whose root is not a list (schema mismatch) is
    also treated as empty rather than raising — preserves prior behavior
    for that specific case."""
    tmp_locations_file.write_text('{"unexpected": "shape"}', encoding="utf-8")
    assert locations_db.load_locations_list() == []


# ---------------------------------------------------------------------------
# set/get round-trip
# ---------------------------------------------------------------------------

def test_set_then_get_bindings_round_trip(sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    ok, errors, _warnings = locations_db.set_dryer_box_bindings(
        "PM-DB-XL-L", {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": None}, printer_map
    )
    assert ok and errors == []
    got = locations_db.get_dryer_box_bindings("PM-DB-XL-L")
    assert got == {"1": "XL-1", "2": "XL-2", "3": "XL-3"}  # null dropped


def test_set_bindings_rejects_bad_target_without_writing(sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    ok, errors, _warnings = locations_db.set_dryer_box_bindings(
        "PM-DB-XL-L", {"1": "BOGUS"}, printer_map
    )
    assert ok is False
    assert len(errors) == 1
    # File should NOT have been written with the bad target.
    assert locations_db.get_dryer_box_bindings("PM-DB-XL-L") == {}


def test_set_bindings_rejects_non_dryer_box(sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    ok, errors, _warnings = locations_db.set_dryer_box_bindings(
        "XL-1", {"1": "XL-2"}, printer_map
    )
    assert ok is False
    assert "not a Dryer Box" in errors[0][2]


def test_get_bindings_on_unknown_location_returns_none(tmp_locations_file):
    locations_db.save_locations_list([
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "2"}
    ])
    assert locations_db.get_dryer_box_bindings("DOES-NOT-EXIST") is None


# ---------------------------------------------------------------------------
# Reverse lookup
# ---------------------------------------------------------------------------

def test_reverse_lookup_split_xl_scenario(sample_locs, printer_map, tmp_locations_file):
    # Left box feeds XL-1..3 (plus slot 4 unassigned).
    sample_locs[0]["extra"] = {
        "slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3"}
    }
    # Right box feeds XL-4 and XL-5.
    sample_locs[1]["extra"] = {"slot_targets": {"1": "XL-4", "2": "XL-5"}}
    locations_db.save_locations_list(sample_locs)

    result = locations_db.get_bindings_for_machine("🦝 XL", printer_map)
    assert result["printer_name"] == "🦝 XL"
    th = result["toolheads"]
    assert th["XL-1"] == [{"box": "PM-DB-XL-L", "slot": "1"}]
    assert th["XL-2"] == [{"box": "PM-DB-XL-L", "slot": "2"}]
    assert th["XL-3"] == [{"box": "PM-DB-XL-L", "slot": "3"}]
    assert th["XL-4"] == [{"box": "PM-DB-XL-R", "slot": "1"}]
    assert th["XL-5"] == [{"box": "PM-DB-XL-R", "slot": "2"}]


def test_reverse_lookup_empty_toolheads_render_as_empty_lists(sample_locs, printer_map, tmp_locations_file):
    # No dryer boxes have slot_targets → every toolhead returns [].
    locations_db.save_locations_list(sample_locs)
    result = locations_db.get_bindings_for_machine("🦝 XL", printer_map)
    assert set(result["toolheads"].keys()) == {"XL-1", "XL-2", "XL-3", "XL-4", "XL-5"}
    for entries in result["toolheads"].values():
        assert entries == []


def test_reverse_lookup_unknown_printer_returns_empty_toolheads(tmp_locations_file, printer_map):
    locations_db.save_locations_list([])
    result = locations_db.get_bindings_for_machine("nonexistent", printer_map)
    assert result == {"printer_name": "nonexistent", "toolheads": {}}


def test_reverse_lookup_multiple_sources_per_toolhead(sample_locs, printer_map, tmp_locations_file):
    # Two boxes both route slot 1 → XL-1 (edge case, but model must handle it).
    sample_locs[0]["extra"] = {"slot_targets": {"1": "XL-1"}}
    sample_locs[1]["extra"] = {"slot_targets": {"1": "XL-1"}}
    locations_db.save_locations_list(sample_locs)
    result = locations_db.get_bindings_for_machine("🦝 XL", printer_map)
    boxes = {(e["box"], e["slot"]) for e in result["toolheads"]["XL-1"]}
    assert boxes == {("PM-DB-XL-L", "1"), ("PM-DB-XL-R", "1")}


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

def test_api_get_bindings_empty(client, sample_locs, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    r = client.get("/api/dryer_box/PM-DB-XL-L/bindings")
    assert r.status_code == 200
    body = r.get_json()
    # slot_order was added 2026-04-23 alongside the slot-order toggle feature.
    # Default is 'ltr' when unset.
    assert body == {"location": "PM-DB-XL-L", "slot_targets": {}, "slot_order": "ltr"}


def test_api_get_bindings_404_on_non_dryer_box(client, sample_locs, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    r = client.get("/api/dryer_box/XL-1/bindings")
    assert r.status_code == 404
    assert r.get_json()["error"] == "not_a_dryer_box"


def test_api_put_bindings_round_trip(client, sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    with patch.object(app_module.config_loader, "load_config", return_value={"printer_map": printer_map}):
        r = client.put(
            "/api/dryer_box/PM-DB-XL-L/bindings",
            json={"slot_targets": {"1": "XL-1", "2": "XL-2", "3": None}},
        )
    assert r.status_code == 200
    body = r.get_json()
    assert body["slot_targets"] == {"1": "XL-1", "2": "XL-2"}

    # Follow up with GET to confirm persistence.
    r2 = client.get("/api/dryer_box/PM-DB-XL-L/bindings")
    assert r2.get_json()["slot_targets"] == {"1": "XL-1", "2": "XL-2"}


def test_api_put_bindings_rejects_bad_target(client, sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    with patch.object(app_module.config_loader, "load_config", return_value={"printer_map": printer_map}):
        r = client.put(
            "/api/dryer_box/PM-DB-XL-L/bindings",
            json={"slot_targets": {"1": "BOGUS", "2": "XL-2"}},
        )
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "validation_failed"
    reasons = {e["slot"]: e["reason"] for e in body["errors"]}
    assert "1" in reasons
    assert "2" not in reasons, "Only the bad target should show up in errors"


def test_api_put_bindings_missing_slot_targets(client, tmp_locations_file):
    locations_db.save_locations_list([])
    r = client.put("/api/dryer_box/PM-DB-XL-L/bindings", json={})
    assert r.status_code == 400
    assert r.get_json()["error"] == "missing_slot_targets"


def test_api_machine_toolhead_slots(client, sample_locs, printer_map, tmp_locations_file):
    sample_locs[0]["extra"] = {"slot_targets": {"1": "XL-1", "2": "XL-2"}}
    sample_locs[1]["extra"] = {"slot_targets": {"1": "XL-4"}}
    locations_db.save_locations_list(sample_locs)
    with patch.object(app_module.config_loader, "load_config", return_value={"printer_map": printer_map}):
        r = client.get("/api/machine/🦝 XL/toolhead_slots")
    assert r.status_code == 200
    body = r.get_json()
    assert body["printer_name"] == "🦝 XL"
    assert body["toolheads"]["XL-1"] == [{"box": "PM-DB-XL-L", "slot": "1"}]
    assert body["toolheads"]["XL-4"] == [{"box": "PM-DB-XL-R", "slot": "1"}]
    assert body["toolheads"]["XL-5"] == []


def test_api_machine_toolhead_slots_404_on_unknown_printer(client, tmp_locations_file, printer_map):
    locations_db.save_locations_list([])
    with patch.object(app_module.config_loader, "load_config", return_value={"printer_map": printer_map}):
        r = client.get("/api/machine/nonexistent/toolhead_slots")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Phase-1A: parent_id helpers + migration
#
# Every test below covers purely additive behavior — no consumer reads
# parent_id yet. These guard the migration's correctness and idempotence
# so future phases can lean on the field as a source of truth.
# ---------------------------------------------------------------------------

def test_derive_parent_id_from_prefix_basic():
    assert locations_db.derive_parent_id_from_prefix("LR-MDB-1") == "LR"
    assert locations_db.derive_parent_id_from_prefix("CORE1-M0") == "CORE1"
    assert locations_db.derive_parent_id_from_prefix("PM-DB-XL-L") == "PM"
    assert locations_db.derive_parent_id_from_prefix("LR") is None
    assert locations_db.derive_parent_id_from_prefix("") is None
    assert locations_db.derive_parent_id_from_prefix(None) is None
    assert locations_db.derive_parent_id_from_prefix(123) is None


def test_derive_parent_id_uppercases():
    assert locations_db.derive_parent_id_from_prefix("lr-mdb-1") == "LR"
    assert locations_db.derive_parent_id_from_prefix("core1-m0") == "CORE1"


def test_resolve_parent_prefers_explicit():
    row = {"LocationID": "LR-MDB-1", "parent_id": "EXPLICIT"}
    assert locations_db.resolve_parent(row) == "EXPLICIT"


def test_resolve_parent_uppercases_explicit_value():
    row = {"LocationID": "LR-MDB-1", "parent_id": "lr"}
    assert locations_db.resolve_parent(row) == "LR"


def test_resolve_parent_explicit_null_returns_none():
    # An explicit `parent_id: None` is the schema's way of saying "this is a
    # top-level row." resolve_parent must honor that and not fall back to
    # prefix parsing — otherwise a Room incorrectly named "FOO-BAR" would
    # be treated as having parent FOO.
    row = {"LocationID": "FOO-BAR", "parent_id": None}
    assert locations_db.resolve_parent(row) is None


def test_resolve_parent_falls_back_to_prefix_when_key_missing():
    row = {"LocationID": "LR-MDB-1"}  # no parent_id key
    assert locations_db.resolve_parent(row) == "LR"


def test_resolve_parent_handles_string_arg():
    assert locations_db.resolve_parent("CORE1-M0") == "CORE1"
    assert locations_db.resolve_parent("CR") is None


def test_resolve_parent_empty_string_explicit_treated_as_none():
    row = {"LocationID": "LR-MDB-1", "parent_id": "   "}
    assert locations_db.resolve_parent(row) is None


def test_migrate_parent_ids_backfills_missing(sample_locs):
    migrated, changed = locations_db.migrate_parent_ids_if_needed(sample_locs)
    assert changed is True
    by_id = {r["LocationID"]: r for r in migrated}
    assert by_id["LR-MDB-1" if "LR-MDB-1" in by_id else "PM-DB-XL-L"]  # sample exists
    # Every row gained a parent_id key.
    for row in migrated:
        assert "parent_id" in row, f"row {row.get('LocationID')!r} missing parent_id"
    # Spot-check derived values.
    assert by_id["PM-DB-XL-L"]["parent_id"] == "PM"
    assert by_id["XL-1"]["parent_id"] == "XL"
    assert by_id["CORE1-M0"]["parent_id"] == "CORE1"
    assert by_id["CR"]["parent_id"] is None


def test_migrate_parent_ids_handles_top_level_rows():
    rows = [
        {"LocationID": "CR", "Type": "Room"},
        {"LocationID": "LR", "Type": "Room"},
        {"LocationID": "BR", "Type": "Room"},
    ]
    migrated, changed = locations_db.migrate_parent_ids_if_needed(rows)
    assert changed is True
    for row in migrated:
        assert row["parent_id"] is None


def test_migrate_parent_ids_synthesized_printer_parents():
    """A toolhead like CORE1-M0 gets parent_id='CORE1' even though no CORE1
    row exists on disk yet (printers are still synthesized at runtime in
    Phase 1A). This is intentional — Phase 3 will persist the parent rows."""
    rows = [
        {"LocationID": "CORE1-M0", "Type": "MMU Slot"},
        {"LocationID": "CORE1-M1", "Type": "MMU Slot"},
    ]
    migrated, _ = locations_db.migrate_parent_ids_if_needed(rows)
    assert all(r["parent_id"] == "CORE1" for r in migrated)


def test_migrate_parent_ids_is_idempotent(sample_locs):
    locations_db.migrate_parent_ids_if_needed(sample_locs)
    second_pass, changed = locations_db.migrate_parent_ids_if_needed(sample_locs)
    assert changed is False
    # No duplicate keys, no value drift.
    assert second_pass is sample_locs  # mutates in place
    for row in second_pass:
        assert "parent_id" in row


def test_migrate_parent_ids_respects_explicit_null():
    """If an operator pre-set parent_id=None, leave it. The 'parent_id' key
    being present is the migration's only signal that the row was already
    visited — even if the value is None."""
    rows = [
        {"LocationID": "LR-MDB-1", "parent_id": None, "Type": "Dryer Box"},
        {"LocationID": "PM-DB-XL-L", "Type": "Dryer Box"},  # missing → will backfill
    ]
    migrated, changed = locations_db.migrate_parent_ids_if_needed(rows)
    assert changed is True  # PM row triggered a change
    by_id = {r["LocationID"]: r for r in migrated}
    assert by_id["LR-MDB-1"]["parent_id"] is None  # operator value preserved
    assert by_id["PM-DB-XL-L"]["parent_id"] == "PM"  # backfilled


def test_migrate_parent_ids_handles_non_list_input():
    out, changed = locations_db.migrate_parent_ids_if_needed(None)
    assert changed is False
    assert out is None
    out2, changed2 = locations_db.migrate_parent_ids_if_needed({"not": "a list"})
    assert changed2 is False


def test_migrate_parent_ids_skips_non_dict_rows():
    rows = [
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box"},
        "not a dict",
        {"LocationID": "CR", "Type": "Room"},
    ]
    migrated, changed = locations_db.migrate_parent_ids_if_needed(rows)
    assert changed is True
    assert migrated[0]["parent_id"] == "LR"
    assert migrated[1] == "not a dict"  # untouched
    assert migrated[2]["parent_id"] is None


def test_migrate_parent_ids_save_load_round_trip(tmp_locations_file, sample_locs):
    """Round-trip through disk: migrate, save, load, every row still has parent_id."""
    migrated, _ = locations_db.migrate_parent_ids_if_needed(sample_locs)
    locations_db.save_locations_list(migrated)
    reloaded = locations_db.load_locations_list()
    for row in reloaded:
        assert "parent_id" in row, f"row {row.get('LocationID')!r} lost parent_id on round-trip"
    by_id = {r["LocationID"]: r for r in reloaded}
    assert by_id["XL-1"]["parent_id"] == "XL"
    assert by_id["CR"]["parent_id"] is None
