"""Group 46.4: the legacy config.json:feeder_map boot import is retired once the
bindings model is live.

`migrate_feeder_map_if_needed` (run on every boot from startup_migrations.py)
skipped only boxes whose bindings were truthy. Clearing every slot of a box in
the Feeds editor saves `slot_targets: {}`, which is falsy, so the next restart
silently re-bound that box from the stale feeder_map seed. Latent today (dev's
and prod's feeder_map are empty), but it is exactly the shape of the
printer_map seed the 2026-09-29 hotfix retired: once the rows are the source of
truth, a stale seed must never write to them again.

The rule: as soon as ANY Dryer Box carries a `slot_targets` key (even `{}`),
the import is a no-op for every box.

HEAD proof: on the pre-fix locations_db.py the first two tests re-bind the box
(`changed is True`), and the authority helper doesn't exist.
"""
from __future__ import annotations

import copy
import json

import pytest

import config_loader
import locations_db
import startup_migrations

BOX = locations_db.DRYER_BOX_TYPE


def _locs():
    return [
        {"LocationID": "PM-DB-XL-L", "Type": BOX, "Max Spools": "4", "Name": "XL Left"},
        {"LocationID": "PM-DB-XL-R", "Type": BOX, "Max Spools": "2", "Name": "XL Right"},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    ]


def test_an_emptied_box_is_not_rebound_from_the_seed():
    locs = _locs()
    locs[0]["extra"] = {"slot_targets": {}, "slot_order": "rtl"}   # every slot cleared in Feeds
    before = copy.deepcopy(locs)
    out, changed = locations_db.migrate_feeder_map_if_needed(locs, {"PM-DB-XL-L": "XL-1"})
    assert changed is False, "a box whose slots were all cleared was re-bound from feeder_map"
    assert out == before


def test_the_import_retires_once_any_box_carries_bindings():
    locs = _locs()
    locs[0]["extra"] = {"slot_targets": {"1": "XL-2"}}
    out, changed = locations_db.migrate_feeder_map_if_needed(locs, {"PM-DB-XL-R": "XL-1"})
    assert changed is False, (
        "the bindings model is live (PM-DB-XL-L carries slot_targets), so the stale "
        "seed must not bind PM-DB-XL-R")
    assert "extra" not in out[1]


def test_a_fresh_install_is_still_imported_once():
    """The upgrade path the import exists for: no box has ever carried bindings."""
    out, changed = locations_db.migrate_feeder_map_if_needed(_locs(), {"PM-DB-XL-R": "XL-1"})
    assert changed is True
    assert out[1]["extra"] == {"slot_targets": {"1": "XL-1"}}
    _, again = locations_db.migrate_feeder_map_if_needed(out, {"PM-DB-XL-L": "XL-2"})
    assert again is False, "after the first import the seed is retired for every box"


class TestAuthorityHelper:
    def test_no_box_has_bindings(self):
        assert locations_db.dryer_bindings_are_authoritative(_locs()) is False

    def test_an_empty_slot_targets_counts(self):
        locs = _locs()
        locs[1]["extra"] = {"slot_targets": {}}
        assert locations_db.dryer_bindings_are_authoritative(locs) is True

    def test_only_dryer_boxes_count(self):
        locs = _locs()
        locs[2]["extra"] = {"slot_targets": {"1": "XL-1"}}   # a Tool Head row
        assert locations_db.dryer_bindings_are_authoritative(locs) is False

    @pytest.mark.parametrize("extra", ["slot_targets: {}", [], 42, None])
    def test_a_malformed_extra_does_not_count_or_raise(self, extra):
        locs = _locs()
        locs[0]["extra"] = extra
        assert locations_db.dryer_bindings_are_authoritative(locs) is False

    @pytest.mark.parametrize("rows", [None, [], ["a string row", 5, None]])
    def test_degenerate_lists(self, rows):
        assert locations_db.dryer_bindings_are_authoritative(rows) is False


def test_boot_leaves_an_emptied_box_empty(tmp_path, monkeypatch):
    """Through the real boot path: config still lists the box in feeder_map,
    the box was cleared in the Feeds editor, and a restart must keep it clear."""
    loc_file = tmp_path / "locations.json"
    locs = _locs()
    locs[0]["extra"] = {"slot_targets": {}}
    loc_file.write_text(json.dumps(locs), encoding="utf-8")
    monkeypatch.setattr(locations_db, "JSON_FILE", str(loc_file))
    monkeypatch.setattr(config_loader, "load_config",
                        lambda *a, **k: {"feeder_map": {"PM-DB-XL-L": "XL-1"}, "printer_map": {}})

    startup_migrations.run_startup_migrations()

    after = json.loads(loc_file.read_text(encoding="utf-8"))
    box = next(r for r in after if r.get("LocationID") == "PM-DB-XL-L")
    assert box["extra"]["slot_targets"] == {}, (
        f"a restart re-bound the cleared box from feeder_map: {box['extra']}")
    assert not list(tmp_path.glob("locations.json.pre-feedermap-migration-*.bak")), \
        "the retired import still wrote a pre-migration backup"
