"""
Integrity guards for inventory-hub/data/locations.json.

Background: a manual-edit gone wrong (stray comma, truncated overwrite,
typo like `"Device Type": "X"D,`) renders the entire dashboard empty
because every consumer of `locations_db.load_locations_list()` swallowed
the JSONDecodeError and returned `[]`. The bug-2 fix made load_locations_list
raise loudly, but the tests below add a second line of defense: explicit,
schema-level guards that fail in CI before the corruption can ship.

Run cheaply against the *real* committed/dev file — no fixture needed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import locations_db  # noqa: E402

LOCATIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "locations.json"


def _required_keys_for(row: dict) -> set:
    """Different Type values legitimately have different shapes — Rooms
    are sparse (no Device Type), Dryer Boxes need Max Spools, etc. Return
    the minimum-acceptable key set for the row's declared Type so we can
    catch tail-truncation and copy-paste skews without flagging legit
    schema variation as an error.
    """
    base = {"LocationID", "Type"}
    t = row.get("Type")
    if t == "Tool Head":
        return base | {"Location", "Device Identifier", "Device Type", "Order", "Max Spools", "Name"}
    if t == "Dryer Box":
        return base | {"Location", "Max Spools", "Name"}
    if t == "MMU Slot":
        return base | {"Location", "Order", "Max Spools", "Name"}
    if t == "No MMU Direct Load":
        return base | {"Location", "Max Spools", "Name"}
    if t in {"Cart", "Sliding Drawer"}:
        return base | {"Name"}
    # Rooms / Virtual / Printer (synthetic) — minimum identification only.
    return base | {"Name"}


# ---------------------------------------------------------------------------
# Static schema guards — these run on the actual file shipped in the repo
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def locations_data():
    if not LOCATIONS_PATH.exists():
        pytest.skip(f"{LOCATIONS_PATH} not present (fresh checkout)")
    raw = LOCATIONS_PATH.read_text(encoding="utf-8")
    return raw, json.loads(raw)


def test_locations_file_is_valid_json(locations_data):
    """Hard contract: locations.json must always parse cleanly. A failure
    here means the dashboard is rendering empty — fix the file before
    merging."""
    raw, data = locations_data
    assert isinstance(data, list), "locations.json root must be a list"


def test_locations_file_is_a_nonempty_list(locations_data):
    """Empty list is technically valid JSON but blanks the dashboard.
    Catch fresh-write accidents (e.g. a save that emitted []) early."""
    _, data = locations_data
    assert len(data) > 0, "locations.json is empty — dashboard would render with no locations"


def test_every_row_is_a_dict_with_LocationID_and_Type(locations_data):
    """Trim guard: tail truncation tends to leave a half-row with a
    LocationID but missing Type, or vice-versa. Both are required."""
    _, data = locations_data
    for i, row in enumerate(data):
        assert isinstance(row, dict), f"row {i} is not a dict: {row!r}"
        assert row.get("LocationID"), f"row {i} missing LocationID: {row!r}"
        assert row.get("Type"), f"row {i} missing Type: {row!r}"


def test_no_duplicate_LocationIDs(locations_data):
    """Two rows sharing the same LocationID would let the wrong one
    silently win on lookup. Catch the dup at the file level."""
    _, data = locations_data
    seen = {}
    for row in data:
        loc = str(row.get("LocationID", "")).upper()
        if loc in seen:
            pytest.fail(f"duplicate LocationID '{loc}' at indices {seen[loc]} and {data.index(row)}")
        seen[loc] = data.index(row)


def test_each_row_has_minimum_schema_for_its_type(locations_data):
    """Catches the "X-5 truncated to 4 fields while X-4 has 10" pattern
    that happens when a partial overwrite leaves a half-baked row."""
    _, data = locations_data
    for i, row in enumerate(data):
        required = _required_keys_for(row)
        present = set(row.keys())
        missing = required - present
        assert not missing, (
            f"row {i} (LocationID={row.get('LocationID')}, Type={row.get('Type')}) "
            f"is missing required keys for its type: {sorted(missing)}"
        )


def test_no_unbalanced_quotes_in_string_fields(locations_data):
    """Catches the `"Device Type": "X"D,` typo class — a string field
    whose value contains an unescaped quote that JSON parsing tolerates
    in some positions but breaks in others."""
    raw, _ = locations_data
    # Quick heuristic: every line that looks like `"Key": "Value",` should
    # have an even number of double quotes (4 or 6 — header + value).
    for lineno, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if ":" not in stripped or not stripped.startswith('"'):
            continue
        # Skip lines that don't have a string value (numbers, booleans, etc.)
        # — those don't include a closing `",`.
        if '": "' not in stripped:
            continue
        # Ignore escaped quotes \" — a real file shouldn't have them in
        # location values, but be conservative.
        scrubbed = stripped.replace('\\"', '')
        n = scrubbed.count('"')
        assert n % 2 == 0 and n in (4, 6), (
            f"line {lineno} has an unbalanced/odd quote count ({n}): {line!r}"
        )


# ---------------------------------------------------------------------------
# Round-trip guard — load via the production helper so the same code path
# the dashboard uses is exercised
# ---------------------------------------------------------------------------

def test_load_locations_list_against_real_file(monkeypatch):
    """End-to-end: prove the production loader returns a non-empty list
    for the real file and never raises LocationsCorruptError."""
    if not LOCATIONS_PATH.exists():
        pytest.skip("data/locations.json missing")
    monkeypatch.setattr(locations_db, "JSON_FILE", str(LOCATIONS_PATH))
    rows = locations_db.load_locations_list()
    assert isinstance(rows, list)
    assert len(rows) > 0, "loader returned empty list — file likely corrupt despite syntax check"


def test_save_then_load_roundtrip_preserves_list(tmp_path, monkeypatch):
    """Reciprocal guard: save_locations_list followed by load_locations_list
    must round-trip cleanly. If the saver ever stops calling json.dump or
    starts producing non-list output, this test catches it."""
    fake = tmp_path / "locations.json"
    monkeypatch.setattr(locations_db, "JSON_FILE", str(fake))
    sample = [
        {"LocationID": "TEST-1", "Type": "Tool Head", "Name": "test 1"},
        {"LocationID": "TEST-DB", "Type": "Dryer Box", "Name": "test db", "Max Spools": "4",
         "extra": {"slot_targets": {"1": "TEST-1"}}},
    ]
    locations_db.save_locations_list(sample)
    rows = locations_db.load_locations_list()
    assert rows == sample


def test_no_blank_type_on_parent_rows(locations_data):
    """A parent placeholder row (LocationID with no `-`, e.g. 'XL' or
    'CORE1') with `Type: ""` strands the row in 'Unassigned virtual
    storage' rendering — the synthesizer skips it because the row
    technically exists, but the empty Type means the UI can't classify
    it. Any parent-shaped row must declare its Type explicitly.
    """
    _, data = locations_data
    for row in data:
        lid = str(row.get("LocationID", ""))
        if lid and "-" not in lid:
            t = str(row.get("Type", "")).strip()
            assert t, (
                f"parent row LocationID={lid!r} has blank Type — would render as "
                "Unassigned virtual storage. Set Type to 'Printer', 'Room', or 'Virtual Room'."
            )


def test_every_printer_map_prefix_has_a_parent_or_is_synthesized():
    """Every printer prefix declared in config.json's printer_map MUST
    eventually appear as a Printer-typed entry in /api/locations — either
    because locations.json carries the parent row or because the
    synthesizer at app.py injects it. Test against the live API so we
    catch both paths."""
    import requests
    try:
        cfg = requests.get("http://localhost:8000/api/printer_map", timeout=3).json()
    except requests.RequestException:
        pytest.skip("dev server unreachable")
    prefixes = set()
    for printer_name, entries in (cfg.get("printers") or {}).items():
        for e in entries or []:
            loc = str(e.get("location_id", ""))
            if "-" in loc:
                prefixes.add(loc.split("-", 1)[0].upper())
    if not prefixes:
        pytest.skip("printer_map empty on this env")

    locs = requests.get("http://localhost:8000/api/locations", timeout=5).json()
    printer_lids = {str(r.get("LocationID", "")).upper() for r in locs if r.get("Type") == "Printer"}
    missing = prefixes - printer_lids
    assert not missing, (
        f"printer_map declares prefixes {sorted(prefixes)} but only {sorted(printer_lids)} "
        f"surface as Type=='Printer' in /api/locations. Missing: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Phase-1A: parent_id schema guards
#
# These run the parent_id backfill migration in-memory against the real
# committed file, then assert the result is well-formed. Pre-restart on
# any host, the on-disk file may not yet carry parent_id — the migration
# runs at app startup and writes back. These tests guard the *contract*
# (after migration, every row has a string-or-None parent_id) so a future
# refactor that breaks the migration's output shape fails CI immediately.
# ---------------------------------------------------------------------------

def test_every_row_has_parent_id_after_migration(locations_data):
    """After running migrate_parent_ids_if_needed, every dict row carries
    a `parent_id` key. Catches a future refactor that strips the field."""
    _, data = locations_data
    migrated, _ = locations_db.migrate_parent_ids_if_needed(list(data))
    for row in migrated:
        if not isinstance(row, dict):
            continue
        assert "parent_id" in row, (
            f"row LocationID={row.get('LocationID')!r} missing parent_id "
            "after migration — migration is broken or the schema regressed."
        )


def test_parent_id_is_string_or_none_after_migration(locations_data):
    """`parent_id` must be either a non-empty uppercase string (a parent
    LocationID) or None (top-level row). Catches accidental empty-string
    or non-string types creeping into the schema."""
    _, data = locations_data
    migrated, _ = locations_db.migrate_parent_ids_if_needed(list(data))
    for row in migrated:
        if not isinstance(row, dict):
            continue
        pid = row.get("parent_id")
        if pid is None:
            continue
        assert isinstance(pid, str), (
            f"row LocationID={row.get('LocationID')!r} has non-string "
            f"parent_id={pid!r} (type={type(pid).__name__})"
        )
        assert pid, (
            f"row LocationID={row.get('LocationID')!r} has empty-string "
            "parent_id — should be None for top-level rows."
        )
        assert pid == pid.upper(), (
            f"row LocationID={row.get('LocationID')!r} has non-uppercase "
            f"parent_id={pid!r} — migration uppercases all values."
        )


def test_parent_id_matches_prefix_for_pre_migration_rows(locations_data):
    """For any row whose parent_id was derived (not operator-set), the
    value must equal the LocationID prefix. Cross-check that catches a
    drift between the migration logic and the prefix-parsing fallback
    that remaining consumers still use during Phases 1B/2."""
    _, data = locations_data
    migrated, _ = locations_db.migrate_parent_ids_if_needed(list(data))
    for row in migrated:
        if not isinstance(row, dict):
            continue
        loc_id = row.get("LocationID")
        if not isinstance(loc_id, str):
            continue
        expected = locations_db.derive_parent_id_from_prefix(loc_id)
        actual = row.get("parent_id")
        assert actual == expected, (
            f"row LocationID={loc_id!r} has parent_id={actual!r} but "
            f"prefix derivation expects {expected!r}. If this row was "
            "operator-edited, that's fine — but the committed file should "
            "match prefix-derivation in Phase 1A."
        )
