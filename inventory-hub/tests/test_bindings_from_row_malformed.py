"""A malformed row in locations.json must not take down the slot-binding readers.

Background (2026-08-03):
  `locations_db._bindings_from_row` did `extra = row.get('extra') or {}` and then
  `extra.get('slot_targets')`. If `extra` is a STRING — or any non-dict — that
  second `.get` raises AttributeError rather than degrading to "no bindings".
  `logic._slot_targets_for` was a near-duplicate of the same helper that DID
  carry the isinstance guard, so the two had silently drifted: one crashed and
  one didn't, and only one normalized its values.

Why a malformed row is reachable even though Derek doesn't hand-edit the file:
  it is plain JSON on disk, an agent may edit it at his request (it cannot be
  edited by the app for every field), and a writer bug can emit the wrong shape.
  The blast radius is the point — `get_bindings_for_machine` feeds the Quick-Swap
  grid and `/api/locations` renders the whole Location Manager, so one bad row
  would black out the UI rather than just losing that row's bindings.

The fix put the guard in the SHARED helper (`locations_db.bindings_from_row`)
and made `logic._slot_targets_for` delegate to it, so they cannot drift again.
These tests pin the guard at the shared helper AND at each of the four call
sites, because a guard is only worth what its callers actually inherit.
"""
from __future__ import annotations

import pytest

import locations_db
import logic


# Every shape a hand-edit or a writer bug could plausibly produce where a dict
# was expected. `{}`/absent are the benign ones; the rest used to raise.
MALFORMED_EXTRAS = [
    "slot_targets: 1 -> XL-1",   # someone typed YAML-ish text into the field
    [],                          # JSON array instead of object
    ["1", "XL-1"],
    42,
    True,
    "",
]


class TestSharedHelper:
    def test_normal_row_still_normalizes(self):
        row = {"extra": {"slot_targets": {1: "XL-1", "2": "", "3": None}}}
        assert locations_db.bindings_from_row(row) == {
            "1": "XL-1", "2": None, "3": None,
        }

    @pytest.mark.parametrize("extra", MALFORMED_EXTRAS)
    def test_non_dict_extra_degrades_to_empty(self, extra):
        assert locations_db.bindings_from_row({"extra": extra}) == {}

    @pytest.mark.parametrize("targets", ["XL-1", ["XL-1"], 7])
    def test_non_dict_slot_targets_degrades_to_empty(self, targets):
        assert locations_db.bindings_from_row({"extra": {"slot_targets": targets}}) == {}

    @pytest.mark.parametrize("row", [None, "a string row", 5, []])
    def test_non_dict_row_degrades_to_empty(self, row):
        assert locations_db.bindings_from_row(row) == {}

    def test_absent_extra_and_absent_slot_targets(self):
        assert locations_db.bindings_from_row({}) == {}
        assert locations_db.bindings_from_row({"extra": {}}) == {}

    def test_private_alias_still_resolves(self):
        """The helper was private until 2026-08-03; the alias keeps any
        straggling reference working."""
        assert locations_db._bindings_from_row is locations_db.bindings_from_row


class TestLogicDelegates:
    """logic._slot_targets_for must inherit the guard, not re-implement it."""

    @pytest.mark.parametrize("extra", MALFORMED_EXTRAS)
    def test_malformed_extra_degrades_to_empty(self, extra):
        loc_map = {"PM-DB-A": {"extra": extra}}
        assert logic._slot_targets_for("PM-DB-A", loc_map) == {}

    def test_missing_location_degrades_to_empty(self):
        assert logic._slot_targets_for("NOPE", {}) == {}
        assert logic._slot_targets_for(None, {}) == {}

    def test_lookup_is_case_and_space_insensitive(self):
        loc_map = {"PM-DB-A": {"extra": {"slot_targets": {"1": "XL-1"}}}}
        assert logic._slot_targets_for("  pm-db-a  ", loc_map) == {"1": "XL-1"}

    def test_delegates_rather_than_reimplements(self, monkeypatch):
        """Pin the delegation itself — a future edit that re-inlines the
        extraction would silently reopen the drift this fix closed."""
        called = {}

        def _spy(row):
            called["row"] = row
            return {"9": "SPY"}

        monkeypatch.setattr(locations_db, "bindings_from_row", _spy)
        out = logic._slot_targets_for("PM-DB-A", {"PM-DB-A": {"extra": {}}})
        assert out == {"9": "SPY"}, "logic._slot_targets_for no longer delegates"
        assert called["row"] == {"extra": {}}


class TestCallSitesSurviveAMalformedRow:
    """The three locations_db call sites, each given a poisoned row alongside a
    good one: the bad row must be ignored, the good one must still be read."""

    def test_get_dryer_box_bindings(self, monkeypatch):
        rows = [
            {"LocationID": "PM-DB-BAD", "Type": locations_db.DRYER_BOX_TYPE,
             "extra": "not-a-dict"},
            {"LocationID": "PM-DB-OK", "Type": locations_db.DRYER_BOX_TYPE,
             "extra": {"slot_targets": {"1": "XL-1"}}},
        ]
        monkeypatch.setattr(locations_db, "load_locations_list", lambda: rows)

        assert locations_db.get_dryer_box_bindings("PM-DB-BAD") == {}
        assert locations_db.get_dryer_box_bindings("PM-DB-OK") == {"1": "XL-1"}

    def test_get_bindings_for_machine(self, monkeypatch):
        rows = [
            {"LocationID": "PM-DB-BAD", "Type": locations_db.DRYER_BOX_TYPE,
             "extra": "not-a-dict"},
            {"LocationID": "PM-DB-OK", "Type": locations_db.DRYER_BOX_TYPE,
             "extra": {"slot_targets": {"1": "XL-1"}}},
        ]
        monkeypatch.setattr(locations_db, "load_locations_list", lambda: rows)

        # Must not raise, and must still find the good box's binding.
        # printer_map is keyed by TOOLHEAD id; each cfg names its printer.
        printer_map = {"XL-1": {"printer_name": "XL"}}
        result = locations_db.get_bindings_for_machine("XL", printer_map)
        assert isinstance(result, dict)
        flat = repr(result)
        assert "PM-DB-OK" in flat, f"good row's binding was lost: {result}"

    def test_migrate_feeder_map_if_needed(self):
        rows = [
            {"LocationID": "PM-DB-BAD", "Type": locations_db.DRYER_BOX_TYPE,
             "extra": "not-a-dict"},
        ]
        # The poisoned row is a migration CANDIDATE (it's in feeder_map), so the
        # helper is reached on the "already migrated?" check — the exact call
        # that used to raise.
        out, changed = locations_db.migrate_feeder_map_if_needed(
            rows, {"PM-DB-BAD": "XL-1"}
        )
        assert changed is True
        assert out[0]["extra"] == {"slot_targets": {"1": "XL-1"}}, (
            "a malformed extra should be replaced by the migration, not crash it"
        )
