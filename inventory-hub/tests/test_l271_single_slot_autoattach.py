"""Group 20.2 — single-slot dryer-box auto-attach / auto-detach helpers.

A spool deployed FROM a single-slot box (Max Spools <= 1) attaches that box to
the toolhead (slot_targets["1"] -> toolhead); ejecting off the toolhead detaches
it. Multi-slot boxes (user-configured bindings) are never touched. Pure unit
tests over the locations_db helpers (load/save stubbed).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import locations_db  # noqa: E402


def _patch_locs(monkeypatch, rows):
    """Stub load/save; returns a dict that captures the saved list (if any)."""
    captured = {}
    monkeypatch.setattr(locations_db, "load_locations_list",
                        lambda: [dict(r) for r in rows])

    def _save(lst, *a, **k):
        captured["list"] = lst
        return True
    monkeypatch.setattr(locations_db, "save_locations_list", _save)
    return captured


# --- _is_single_slot_dryer_box ---

def test_is_single_slot_only_for_box_max1():
    assert locations_db._is_single_slot_dryer_box({"Type": "Dryer Box", "Max Spools": "1"})
    assert locations_db._is_single_slot_dryer_box({"Type": "Dryer Box", "Max Spools": "0"})
    assert not locations_db._is_single_slot_dryer_box({"Type": "Dryer Box", "Max Spools": "4"})
    assert not locations_db._is_single_slot_dryer_box({"Type": "Tool Head", "Max Spools": "1"})
    # Fail-safe: missing / unparseable Max Spools is NOT auto-managed.
    assert not locations_db._is_single_slot_dryer_box({"Type": "Dryer Box"})
    assert not locations_db._is_single_slot_dryer_box({"Type": "Dryer Box", "Max Spools": "abc"})


# --- attach ---

def test_attach_binds_single_slot_box(monkeypatch):
    saved = _patch_locs(monkeypatch, [
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "extra": {}}])
    ok, detail = locations_db.attach_single_slot_box_to_toolhead("PM-DB-1", "XL-1")
    assert ok
    box = next(r for r in saved["list"] if r["LocationID"] == "PM-DB-1")
    assert box["extra"]["slot_targets"] == {"1": "XL-1"}


def test_attach_is_idempotent_no_write(monkeypatch):
    saved = _patch_locs(monkeypatch, [
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1",
         "extra": {"slot_targets": {"1": "XL-1"}}}])
    ok, detail = locations_db.attach_single_slot_box_to_toolhead("PM-DB-1", "xl-1")
    assert ok and detail == "already attached"
    assert "list" not in saved  # no redundant save


def test_attach_noop_for_multislot_box(monkeypatch):
    saved = _patch_locs(monkeypatch, [
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "extra": {}}])
    ok, detail = locations_db.attach_single_slot_box_to_toolhead("LR-MDB-1", "XL-1")
    assert not ok and "single-slot" in detail
    assert "list" not in saved


def test_attach_noop_for_non_box(monkeypatch):
    saved = _patch_locs(monkeypatch, [
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"}])
    ok, _ = locations_db.attach_single_slot_box_to_toolhead("XL-1", "XL-2")
    assert not ok
    assert "list" not in saved


def test_attach_overwrites_to_follow_the_spool(monkeypatch):
    # The box's one spool moved from XL-1 to XL-2 -> binding follows.
    saved = _patch_locs(monkeypatch, [
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1",
         "extra": {"slot_targets": {"1": "XL-1"}}}])
    ok, _ = locations_db.attach_single_slot_box_to_toolhead("PM-DB-1", "XL-2")
    assert ok
    box = next(r for r in saved["list"] if r["LocationID"] == "PM-DB-1")
    assert box["extra"]["slot_targets"] == {"1": "XL-2"}


# --- detach ---

def test_detach_clears_single_slot_leaves_multislot(monkeypatch):
    saved = _patch_locs(monkeypatch, [
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1",
         "extra": {"slot_targets": {"1": "XL-1"}}},
        # multi-slot box ALSO bound to XL-1 — must be left untouched (user config)
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2"}}}])
    detached = locations_db.detach_single_slot_boxes_from_toolhead("XL-1")
    assert detached == ["PM-DB-1"]
    box = next(r for r in saved["list"] if r["LocationID"] == "PM-DB-1")
    assert box["extra"]["slot_targets"] == {}
    multi = next(r for r in saved["list"] if r["LocationID"] == "LR-MDB-1")
    assert multi["extra"]["slot_targets"] == {"1": "XL-1", "2": "XL-2"}


def test_detach_noop_when_bound_elsewhere(monkeypatch):
    saved = _patch_locs(monkeypatch, [
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1",
         "extra": {"slot_targets": {"1": "XL-2"}}}])
    detached = locations_db.detach_single_slot_boxes_from_toolhead("XL-1")
    assert detached == []
    assert "list" not in saved  # nothing to do, no save


def test_attach_detach_round_trip(monkeypatch):
    rows = [{"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "extra": {}}]
    # attach
    saved = _patch_locs(monkeypatch, rows)
    locations_db.attach_single_slot_box_to_toolhead("PM-DB-1", "XL-3")
    attached_rows = saved["list"]
    assert attached_rows[0]["extra"]["slot_targets"] == {"1": "XL-3"}
    # detach (feed the attached state back in)
    saved2 = _patch_locs(monkeypatch, attached_rows)
    detached = locations_db.detach_single_slot_boxes_from_toolhead("XL-3")
    assert detached == ["PM-DB-1"]
    assert saved2["list"][0]["extra"]["slot_targets"] == {}
