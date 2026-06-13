"""Group 20.3 — toolhead-delete cascade (logic.perform_toolhead_delete_cascade).

Deleting a toolhead row must propagate to the three drifting binding stores:
  - DIRECT spools (Spoolman location == toolhead)  -> UNASSIGNED + ghost-trail cleared
  - GHOST spools (deployed via physical_source)     -> un-deployed, box location KEPT
  - FilaBridge toolhead map                         -> unmapped
  - dryer-box slot_targets feeding the toolhead     -> dropped (PRINTER: sentinels kept)
  - Printer-row toolheads[] (L271 Phase-4 store)    -> the entry pruned
An ACTIVE print on the toolhead blocks with requires_confirm and touches nothing.

Pure unit tests — every external store is stubbed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402


def _patch(monkeypatch, *, spools_at, spool_extras, active=None):
    """Stub the external stores the cascade touches. Returns the update-capture
    list. printer_map maps XL-3 -> ('🦝 XL', 2) so _toolhead_of resolves."""
    monkeypatch.setattr(logic.config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
    monkeypatch.setattr(logic.locations_db, "get_active_printer_map",
                        lambda loc_list=None: {"XL-3": {"printer_name": "🦝 XL", "position": 2}})
    monkeypatch.setattr(logic, "_active_print_info_for_location", lambda loc, pm=None: active)
    monkeypatch.setattr(logic.spoolman_api, "get_spools_at_location_detailed", lambda loc: list(spools_at))
    monkeypatch.setattr(logic.spoolman_api, "get_spool",
                        lambda sid: {"id": sid, "extra": dict(spool_extras.get(sid, {}))})
    updates = []

    def _upd(sid, data):
        updates.append((sid, data))
        return True
    monkeypatch.setattr(logic.spoolman_api, "update_spool", _upd)
    monkeypatch.setattr(logic.spoolman_api, "LAST_SPOOLMAN_ERROR", None, raising=False)
    return updates


def test_direct_spool_unassigned_and_ghost_trail_cleared(monkeypatch):
    updates = _patch(
        monkeypatch,
        spools_at=[{"id": 5, "is_ghost": False}],
        spool_extras={5: {"physical_source": "PM-DB-1", "physical_source_slot": "2",
                          "container_slot": "", "nozzle_temp_max": "260"}})
    loc = [{"LocationID": "XL", "Type": "Printer", "Name": "🦝 XL",
            "toolheads": [{"location_id": "XL-3", "position": 2}]}]
    res = logic.perform_toolhead_delete_cascade("XL-3", loc)

    assert res["status"] == "ok"
    assert res["unassigned"] == [5] and res["undeployed"] == []
    sid, data = updates[0]
    assert sid == 5 and data["location"] == ""              # → UNASSIGNED
    assert data["extra"]["physical_source"] == ""
    assert data["extra"]["physical_source_slot"] == ""
    assert data["extra"]["container_slot"] == ""
    assert data["extra"]["nozzle_temp_max"] == "260"        # sibling extra preserved (read-merge-write)
    assert res["toolhead_pruned_from"] == ["XL"] and loc[0]["toolheads"] == []


def test_ghost_spool_undeployed_not_yanked_from_box(monkeypatch):
    updates = _patch(
        monkeypatch,
        spools_at=[{"id": 7, "is_ghost": True}],
        spool_extras={7: {"physical_source": "XL-3", "physical_source_slot": "1", "container_slot": "1"}})
    res = logic.perform_toolhead_delete_cascade("XL-3", [])

    assert res["undeployed"] == [7] and res["unassigned"] == []
    sid, data = updates[0]
    assert sid == 7
    assert "location" not in data                            # box location NOT touched
    assert data["extra"]["physical_source"] == "" and data["extra"]["physical_source_slot"] == ""
    assert data["extra"]["container_slot"] == "1"            # still lives in its box slot


def test_slot_targets_feeding_toolhead_dropped_sentinels_and_others_kept(monkeypatch):
    _patch(monkeypatch, spools_at=[], spool_extras={})
    loc = [{"LocationID": "PM-DB-1", "Type": "Dryer Box",
            "extra": {"slot_targets": {"1": "XL-3", "2": "XL-4", "3": "PRINTER:XL"}}}]
    res = logic.perform_toolhead_delete_cascade("XL-3", loc)

    assert res["slot_bindings_cleared"] == ["PM-DB-1:1"]
    assert loc[0]["extra"]["slot_targets"] == {"2": "XL-4", "3": "PRINTER:XL"}


def test_toolhead_pruned_from_printer_row_only(monkeypatch):
    _patch(monkeypatch, spools_at=[], spool_extras={})
    loc = [{"LocationID": "XL", "Type": "Printer",
            "toolheads": [{"location_id": "XL-1", "position": 0},
                          {"location_id": "XL-3", "position": 2}]}]
    res = logic.perform_toolhead_delete_cascade("XL-3", loc)

    assert res["toolhead_pruned_from"] == ["XL"]
    assert loc[0]["toolheads"] == [{"location_id": "XL-1", "position": 0}]   # only XL-3 removed


def test_no_references_is_clean_noop_summary(monkeypatch):
    updates = _patch(monkeypatch, spools_at=[], spool_extras={})
    res = logic.perform_toolhead_delete_cascade("XL-3", [])

    assert res["status"] == "ok"
    assert res["unassigned"] == [] and res["undeployed"] == []
    assert res["slot_bindings_cleared"] == [] and res["toolhead_pruned_from"] == []
    assert updates == []


def test_active_print_blocks_without_confirm_touches_nothing(monkeypatch):
    updates = _patch(
        monkeypatch,
        spools_at=[{"id": 1, "is_ghost": False}], spool_extras={1: {}},
        active={"printer_name": "🦝 XL", "state": "PRINTING", "toolhead": "XL-3"})
    loc = [{"LocationID": "XL", "Type": "Printer",
            "toolheads": [{"location_id": "XL-3", "position": 2}]}]
    res = logic.perform_toolhead_delete_cascade("XL-3", loc)

    assert res["status"] == "requires_confirm" and res["confirm_type"] == "active_print"
    assert updates == []                                     # nothing mutated
    assert loc[0]["toolheads"] == [{"location_id": "XL-3", "position": 2}]   # not pruned


def test_confirm_active_print_proceeds(monkeypatch):
    updates = _patch(
        monkeypatch,
        spools_at=[{"id": 1, "is_ghost": False}], spool_extras={1: {}},
        active={"printer_name": "🦝 XL", "state": "PRINTING"})
    res = logic.perform_toolhead_delete_cascade(
        "XL-3", [{"LocationID": "XL", "Type": "Printer",
                  "toolheads": [{"location_id": "XL-3", "position": 2}]}],
        confirm_active_print=True)

    assert res["status"] == "ok" and res["unassigned"] == [1]
