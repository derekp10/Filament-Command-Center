"""Group 19.1 — hermetic unit coverage for reset_dev.py's restore-decision logic.

These tests exercise the PURE comparison helpers (`_values_equal`,
`_drifted_payload`) that decide which fields get PATCHed back to the seed.
They touch no network and no Spoolman — the network round-trips (capture,
PATCH, DELETE, docker restart) are validated by running the script against
the live dev backend, but the drift logic that gates every write is locked
down here so a regression can't silently start over- or under-writing.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

# reset_dev.py lives in setup-and-rebuild/ (a sibling of inventory-hub/),
# which isn't a package. Load it by path.
_RESET_DEV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "setup-and-rebuild", "reset_dev.py")
)


@pytest.fixture(scope="module")
def reset_dev():
    if not os.path.exists(_RESET_DEV_PATH):
        pytest.skip(f"reset_dev.py not found at {_RESET_DEV_PATH}")
    spec = importlib.util.spec_from_file_location("reset_dev", _RESET_DEV_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- _values_equal --------------------------------------------------------

def test_values_equal_float_tolerance(reset_dev):
    # Spoolman serializes 1.24 with float noise; a sub-epsilon delta is NOT drift.
    assert reset_dev._values_equal(1.24, 1.2400000001)
    assert reset_dev._values_equal(1000.0, 1000)
    # A real change IS drift.
    assert not reset_dev._values_equal(1.24, 1.25)


def test_values_equal_strings_and_none(reset_dev):
    assert reset_dev._values_equal("PM-DB-3", "PM-DB-3")
    assert not reset_dev._values_equal("PM-DB-3", "")
    assert reset_dev._values_equal(None, None)
    assert not reset_dev._values_equal(None, "x")


def test_values_equal_dicts(reset_dev):
    assert reset_dev._values_equal({"a": "1"}, {"a": "1"})
    # None and {} treated as the empty dict (Spoolman returns {} for no extras).
    assert reset_dev._values_equal(None, {})
    assert not reset_dev._values_equal({"a": "1"}, {"a": "2"})


# --- _drifted_payload -----------------------------------------------------

def test_no_drift_returns_empty_payload(reset_dev):
    """A live spool identical to the seed yields no PATCH (idempotency)."""
    seed = {
        "id": 1, "location": "PM-DB-3", "archived": False,
        "initial_weight": 1000.0, "spool_weight": 0.0, "used_weight": 150.0,
        "lot_nr": None, "comment": "[Fan: On]",
        "extra": {"container_slot": '"\\"\\"\\""', "needs_label_print": "true"},
    }
    live = dict(seed)
    assert reset_dev._drifted_payload("spool", seed, live) == {}


def test_location_drift_is_restored(reset_dev):
    """The headline contamination: a sweep moved the spool's location."""
    seed = {"id": 1, "location": "PM-DB-3", "archived": False, "extra": {}}
    live = {"id": 1, "location": "SOME-TEST-LOC", "archived": False, "extra": {}}
    payload = reset_dev._drifted_payload("spool", seed, live)
    assert payload == {"location": "PM-DB-3"}


def test_archived_and_extra_drift_restored_together(reset_dev):
    seed = {
        "id": 1, "location": "PM-DB-3", "archived": False,
        "extra": {"container_slot": '""', "needs_label_print": "false"},
    }
    live = {
        "id": 1, "location": "PM-DB-3", "archived": True,
        "extra": {"container_slot": '"XL-1"', "needs_label_print": "true"},
    }
    payload = reset_dev._drifted_payload("spool", seed, live)
    assert payload["archived"] is False
    # Whole-extra overwrite (Spoolman replaces the entire extra dict on PATCH).
    assert payload["extra"] == seed["extra"]
    assert "location" not in payload  # unchanged → not sent


def test_extra_overwrite_drops_sweep_added_keys(reset_dev):
    """If a sweep ADDED an extra key, the seed's (smaller) extra must fully
    replace it — not merge — so the stray key is gone after restore."""
    seed = {"id": 9, "extra": {"website": '""'}}
    live = {"id": 9, "extra": {"website": '""', "junk_key": '"oops"'}}
    payload = reset_dev._drifted_payload("vendor", seed, live)
    assert payload == {"extra": {"website": '""'}}


def test_filament_attributes_extra_restored(reset_dev):
    """L319/L58 contamination: filament_attributes got rewritten on the
    filament's extra. Restore overwrites the whole extra back to seed."""
    seed = {"id": 3, "material": "PLA",
            "extra": {"filament_attributes": '["Silk"]', "sample_printed": "true"}}
    live = {"id": 3, "material": "PLA",
            "extra": {"filament_attributes": '["Silk","Wood"]', "sample_printed": "true"}}
    payload = reset_dev._drifted_payload("filament", seed, live)
    assert payload == {"extra": {"filament_attributes": '["Silk"]', "sample_printed": "true"}}


def test_weight_triple_drift_restored(reset_dev):
    """Weigh-out / auto-deduct tests move used_weight; restore puts it back."""
    seed = {"id": 1, "location": "X", "archived": False,
            "initial_weight": 1000.0, "spool_weight": 0.0, "used_weight": 150.0,
            "extra": {}}
    live = dict(seed, used_weight=812.5)
    payload = reset_dev._drifted_payload("spool", seed, live)
    assert payload == {"used_weight": 150.0}


def test_only_restorable_fields_considered(reset_dev):
    """A drift in a field NOT on the restore list (e.g. remaining_weight, a
    derived read-only field) must not produce a PATCH."""
    seed = {"id": 1, "location": "X", "archived": False, "extra": {},
            "remaining_weight": 850.0}
    live = {"id": 1, "location": "X", "archived": False, "extra": {},
            "remaining_weight": 123.0}
    assert reset_dev._drifted_payload("spool", seed, live) == {}


def test_restore_field_sets_are_sane(reset_dev):
    """Guard the field config: extra must be restorable on every entity (it's
    the primary contamination vector), and spool must restore location+archived."""
    rf = reset_dev.RESTORE_FIELDS
    for entity in ("vendor", "filament", "spool"):
        assert "extra" in rf[entity], f"{entity} must restore extra"
    assert "location" in rf["spool"]
    assert "archived" in rf["spool"]
