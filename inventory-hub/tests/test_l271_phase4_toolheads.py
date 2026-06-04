"""L271 Phase 4 (step 1) — fold printer_map into Printer-row toolheads[].

`migrate_printer_map_to_toolheads_if_needed` writes a `toolheads:[{location_id,
position}]` array onto each first-class Type:"Printer" row, derived from
config.json's printer_map (grouped by printer PREFIX = the Printer row's unique
LocationID). printer_name is NOT stored per toolhead — the Printer row's Name is
the single source of truth.

`build_printer_map_from_rows` is the inverse accessor: it reconstructs the exact
`{LOCID_UPPER: {printer_name, position}}` dict that config_loader.load_config()
exposes today, so step-2 consumers swap their data source with no logic change.
The byte-identical round-trip (printer_map → toolheads[] → printer_map) is the
load-bearing invariant pinned here.

DUAL-READ: this is purely additive — printer_map stays authoritative this phase.
"""
import copy
import json
import os

import pytest

import locations_db


def _read_app():
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with open(os.path.join(here, "app.py"), "r", encoding="utf-8") as f:
        return f.read()


# A deliberately NON-CONTIGUOUS example (XL-5 at position 5) — proves the migration
# preserves `position` VERBATIM and never renumbers to 0..N-1. NOTE: this is synthetic,
# NOT XL's real data. Real XL is contiguous 0..4 (`position` = FilaBridge toolhead_id,
# 0-based); the prod "5" was a typo Derek fixed to 4 on 2026-06-04. We keep a synthetic
# gap here purely to lock in the no-auto-resequence guarantee (matters for the Step-4 PUT).
PRINTER_MAP = {
    "XL-1": {"printer_name": "🦝 XL", "position": 0},
    "XL-2": {"printer_name": "🦝 XL", "position": 1},
    "XL-3": {"printer_name": "🦝 XL", "position": 2},
    "XL-4": {"printer_name": "🦝 XL", "position": 3},
    "XL-5": {"printer_name": "🦝 XL", "position": 5},
    "CORE1": {"printer_name": "🦝 Core One Upgraded", "position": 0},
}


def _printer_rows():
    """Printer rows as Phase 3 leaves them (no toolheads[] yet) + a non-printer
    row that must be ignored by the fold."""
    return [
        {"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL", "parent_id": "LR", "Max Spools": "0"},
        {"LocationID": "CORE1", "Type": "Printer", "Name": "🦝 Core One Upgraded",
         "parent_id": "CR", "Max Spools": "1"},
        {"LocationID": "XL-1", "Type": "Tool Head", "Name": "XL T1", "parent_id": "XL", "Max Spools": "1"},
    ]


# --------------------------------------------------------------------------- #
# Migration                                                                    #
# --------------------------------------------------------------------------- #

def test_fold_writes_sorted_toolheads_with_position_gap():
    out, changed = locations_db.migrate_printer_map_to_toolheads_if_needed(_printer_rows(), PRINTER_MAP)
    assert changed is True
    xl = [r for r in out if r["LocationID"] == "XL"][0]
    assert xl["toolheads"] == [
        {"location_id": "XL-1", "position": 0},
        {"location_id": "XL-2", "position": 1},
        {"location_id": "XL-3", "position": 2},
        {"location_id": "XL-4", "position": 3},
        {"location_id": "XL-5", "position": 5},   # synthetic non-contiguous position preserved verbatim (no auto-renumber)
    ]
    core1 = [r for r in out if r["LocationID"] == "CORE1"][0]
    assert core1["toolheads"] == [{"location_id": "CORE1", "position": 0}]
    # the non-printer Tool Head row is never given a toolheads[] of its own
    th = [r for r in out if r["LocationID"] == "XL-1"][0]
    assert "toolheads" not in th


def test_accessor_round_trips_byte_identical():
    """printer_map → toolheads[] → printer_map reproduces the EXACT dict that
    config_loader.load_config()['printer_map'] exposes (uppercased keys). This
    is what lets every step-2 consumer swap data source with no logic change."""
    out, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(_printer_rows(), PRINTER_MAP)
    assert locations_db.build_printer_map_from_rows(out) == PRINTER_MAP


def test_idempotent_across_json_round_trip():
    out1, changed1 = locations_db.migrate_printer_map_to_toolheads_if_needed(_printer_rows(), PRINTER_MAP)
    assert changed1 is True
    # simulate the save→reload boundary (dicts come back from disk fresh)
    reloaded = json.loads(json.dumps(out1))
    snapshot = copy.deepcopy(reloaded)
    out2, changed2 = locations_db.migrate_printer_map_to_toolheads_if_needed(reloaded, PRINTER_MAP)
    assert changed2 is False, "second boot must be a no-op"
    assert out2 == snapshot


def test_resync_when_printer_map_changes():
    out, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(_printer_rows(), PRINTER_MAP)
    bigger = dict(PRINTER_MAP, **{"XL-6": {"printer_name": "🦝 XL", "position": 6}})
    out2, changed = locations_db.migrate_printer_map_to_toolheads_if_needed(out, bigger)
    assert changed is True
    xl = [r for r in out2 if r["LocationID"] == "XL"][0]
    assert {"location_id": "XL-6", "position": 6} in xl["toolheads"]
    assert locations_db.build_printer_map_from_rows(out2) == bigger


def test_no_empty_array_churn_for_unmapped_printer():
    """A Printer row with no printer_map entries AND no toolheads key is left
    untouched — no empty-array write, no spurious changed=True."""
    rows = [{"LocationID": "ZZ", "Type": "Printer", "Name": "Ghost", "parent_id": None}]
    out, changed = locations_db.migrate_printer_map_to_toolheads_if_needed(rows, PRINTER_MAP)
    assert changed is False
    assert "toolheads" not in out[0]


def test_clears_stale_toolheads_when_map_drops_printer():
    """A Printer row that HAD toolheads but no longer has map entries is cleared
    to [] so the dual-read accessor doesn't surface a ghost toolhead."""
    rows = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL",
             "toolheads": [{"location_id": "XL-1", "position": 0}]}]
    out, changed = locations_db.migrate_printer_map_to_toolheads_if_needed(rows, {"CORE1": {"printer_name": "C", "position": 0}})
    assert changed is True
    assert out[0]["toolheads"] == []


def test_mixed_case_location_id_is_uppercased():
    rows = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL"}]
    out, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(
        rows, {"xl-1": {"printer_name": "🦝 XL", "position": 0}})
    assert out[0]["toolheads"] == [{"location_id": "XL-1", "position": 0}]
    assert "XL-1" in locations_db.build_printer_map_from_rows(out)


def test_mmu_alias_same_position_both_fold_under_prefix():
    """MMU M0/M1 aliases share a position; both must land under the CORE1 prefix,
    sorted (position, location_id) so M0 precedes M1, and round-trip intact —
    the schema preserves `position`, which the MMU dedup heuristic keys on."""
    rows = [{"LocationID": "CORE1", "Type": "Printer", "Name": "🦝 Core One Upgraded", "Max Spools": "1"}]
    pm = {
        "CORE1-M0": {"printer_name": "🦝 Core One Upgraded", "position": 0},
        "CORE1-M1": {"printer_name": "🦝 Core One Upgraded", "position": 0},
    }
    out, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(rows, pm)
    assert out[0]["toolheads"] == [
        {"location_id": "CORE1-M0", "position": 0},
        {"location_id": "CORE1-M1", "position": 0},
    ]
    assert locations_db.build_printer_map_from_rows(out) == pm


def test_non_int_position_coerced():
    rows = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL"}]
    out, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(
        rows, {"XL-1": {"printer_name": "🦝 XL", "position": "2"}, "XL-2": {"printer_name": "🦝 XL"}})
    pm = locations_db.build_printer_map_from_rows(out)
    assert pm["XL-1"]["position"] == 2 and pm["XL-2"]["position"] == 0


def test_accessor_uses_printer_row_name_as_source_of_truth():
    """Intended drift-resolution: rename the Printer row and the reconstructed
    printer_name follows the row (Name is authoritative), NOT the stale config."""
    out, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(_printer_rows(), PRINTER_MAP)
    xl = [r for r in out if r["LocationID"] == "XL"][0]
    xl["Name"] = "🦝 XL (renamed)"
    pm = locations_db.build_printer_map_from_rows(out)
    assert pm["XL-1"]["printer_name"] == "🦝 XL (renamed)"


def test_non_list_and_empty_map_are_noops():
    assert locations_db.migrate_printer_map_to_toolheads_if_needed("nope", PRINTER_MAP) == ("nope", False)
    rows = _printer_rows()
    out, changed = locations_db.migrate_printer_map_to_toolheads_if_needed(rows, {})
    assert changed is False


# --------------------------------------------------------------------------- #
# get_active_printer_map — the dual-read consumer entrypoint (step 2)          #
# --------------------------------------------------------------------------- #

def test_get_active_printer_map_prefers_rows():
    out, _ = locations_db.migrate_printer_map_to_toolheads_if_needed(_printer_rows(), PRINTER_MAP)
    assert locations_db.get_active_printer_map(out) == PRINTER_MAP


def test_get_active_printer_map_has_no_config_fallback(monkeypatch):
    """L271 Phase 4 (step 4 — the cutover): the dual-read config fallback is GONE.
    The Printer rows' toolheads[] are the sole source — a row with no toolheads[]
    yields an empty map even when config.json STILL carries a printer_map (it
    survives only as the boot-time priming seed, never read here)."""
    import config_loader
    # Config still has a full printer_map; get_active_printer_map must IGNORE it.
    monkeypatch.setattr(config_loader, "load_config", lambda: {"printer_map": PRINTER_MAP})
    rows_without_toolheads = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL"}]
    assert locations_db.get_active_printer_map(rows_without_toolheads) == {}


def test_prime_only_primes_unfolded_but_never_reverts_a_folded_row():
    """L271 Phase 4 (step 4): the STARTUP fold runs prime_only=True. It PRIMES a
    never-folded row (fresh deploy) but must NEVER overwrite an already-folded
    toolheads[], or a UI edit (rows authoritative) would be reverted from the now-
    stale config seed on the next reboot. The PUT path (prime_only=False) re-syncs."""
    # (a) PRIME a never-folded row: no toolheads key yet → folds from the seed.
    fresh = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL"}]
    out, changed = locations_db.migrate_printer_map_to_toolheads_if_needed(
        fresh, {"XL-1": {"printer_name": "🦝 XL", "position": 0}}, prime_only=True)
    assert changed is True
    assert out[0]["toolheads"] == [{"location_id": "XL-1", "position": 0}]

    # (b) DO NOT revert an already-folded row that DIFFERS from the (stale) seed.
    edited = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL",
               "toolheads": [{"location_id": "XL-1", "position": 9}]}]  # a UI edit: pos 9
    out2, changed2 = locations_db.migrate_printer_map_to_toolheads_if_needed(
        edited, {"XL-1": {"printer_name": "🦝 XL", "position": 0}}, prime_only=True)
    assert changed2 is False  # NOT reverted
    assert out2[0]["toolheads"] == [{"location_id": "XL-1", "position": 9}]

    # (c) The EDIT path (default re-sync) DOES overwrite the folded row.
    edited2 = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL",
                "toolheads": [{"location_id": "XL-1", "position": 9}]}]
    out3, changed3 = locations_db.migrate_printer_map_to_toolheads_if_needed(
        edited2, {"XL-1": {"printer_name": "🦝 XL", "position": 0}})
    assert changed3 is True
    assert out3[0]["toolheads"] == [{"location_id": "XL-1", "position": 0}]


# --------------------------------------------------------------------------- #
# Source canaries (the migration must run at startup AND on the printer_map PUT) #
# --------------------------------------------------------------------------- #

def test_migration_wired_at_startup_and_on_put():
    """Like the Phase 3 canary: the fold must be referenced in BOTH the startup
    block and the /api/printer_map PUT handler so an edited map keeps toolheads[]
    current without a reboot."""
    assert _read_app().count("migrate_printer_map_to_toolheads_if_needed") >= 2


# --------------------------------------------------------------------------- #
# Live integration                                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.integration
def test_live_printer_rows_carry_toolheads_matching_printer_map(api_base_url, require_server):
    """Live: every Printer row on /api/locations carries a toolheads[] whose
    reconstruction equals the live /api/printer_map flat entries (the dual-read
    invariant on real data)."""
    import requests
    rows = requests.get(f"{api_base_url}/api/locations", timeout=10).json()
    rows = rows.get("locations", rows) if isinstance(rows, dict) else rows
    printers = [r for r in rows if str(r.get("Type", "")).strip().lower() == "printer"]
    assert printers, "expected first-class Printer rows on disk"
    for p in printers:
        assert isinstance(p.get("toolheads"), list), f"{p.get('LocationID')} missing toolheads[]"

    # Reconstruct printer_map from the rows and compare to the live editor view.
    reconstructed = locations_db.build_printer_map_from_rows(rows)
    pm_body = requests.get(f"{api_base_url}/api/printer_map", timeout=10).json()
    live = {
        str(e["location_id"]).upper(): {"printer_name": e["printer_name"], "position": int(e["position"])}
        for e in pm_body.get("entries", [])
    }
    assert reconstructed == live, "toolheads[] reconstruction must match the live printer_map"
