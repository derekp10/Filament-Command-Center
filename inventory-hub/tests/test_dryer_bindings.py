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
