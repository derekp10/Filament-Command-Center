"""Group 41.3 — deleting a location never reaches a loaded head, refuses a
location that still contains others, and keeps the row if anything fails.

Derek's answers: Q4 C (2026-10-13) refuse to delete a Room while any location
sits inside it, and an emptied Room unassigns only the spools filed on the
Room itself; and, the same evening, the same refusal for every location type.
Group 37's invariant: a delete must never reach a live toolhead. The plan-time
finding this closes: deleting LR-MDB-1 took the spools deployed from it off
XL-1…XL-3, through the ghost match on their trail.

The real DELETE /api/locations route runs against
tests/move_engine_harness.py's FakeSpoolman; locations.json saves are captured.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, run_move  # noqa: E402

PRINTER_MAP = {
    "XL-1": {"printer_name": "🦝 XL", "position": 0},
    "XL-2": {"printer_name": "🦝 XL", "position": 1},
    "TB-1": {"printer_name": "Test Bench", "position": 0},
}
LOCATIONS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR"},
    {"LocationID": "LR-SD-1", "Type": "Drawer", "Max Spools": "0", "parent_id": "LR"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1}]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR-CT-2", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR-CT-2"},
    {"LocationID": "DR", "Type": "Room", "Max Spools": "0"},
    # A contrived prefix collision: the cart TB's matcher reaches the head TB-1.
    {"LocationID": "TB", "Type": "Cart", "Max Spools": "0"},
    {"LocationID": "TB-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "ZZ"},
]


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _delete(sm, client, loc):
    saves = []
    with patch.object(locations_db, "save_locations_list",
                      side_effect=lambda lst: saves.append([r["LocationID"] for r in lst]) or True):
        resp = run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map=PRINTER_MAP,
                        call=lambda: client.delete(f"/api/locations?id={loc}"))
    return resp.status_code, resp.get_json(), saves


@pytest.mark.parametrize("loc,inside", [
    ("LR", "LR still contains LR-MDB-1, LR-SD-1 and XL — move or delete them first."),
    ("CR-CT-2", "CR-CT-2 still contains CR-CT-2-R1 — move or delete them first."),
])
def test_a_location_with_locations_inside_is_not_deleted(client, logs, loc, inside):
    """FAILS on the old route: deleting LR unassigned every spool in its boxes and
    drawers (by prefix) while their rows stayed; a cart lost its rows' spools."""
    sm = FakeSpoolman({1: {"location": "LR-MDB-1", "extra": {"container_slot": "1"}},
                       2: {"location": "CR-CT-2-R1", "extra": {}}})
    with patch.object(logic.spoolman_api, "get_spools_at_location_detailed_strict") as strict:
        status, body, saves = _delete(sm, client, loc)
    assert status == 409 and body["msg"] == inside, body
    assert strict.call_count == 0 and sm.writes == [] and saves == []
    assert (f"⚠️ Delete refused: {inside}", ("WARNING", "ffaa00")) in logs


def test_an_emptied_room_unassigns_only_the_spools_filed_on_it(client, logs):
    """FAILS on the old route: #2 (filed on a row-less DR-X-9, a prefix hit) was
    unassigned with the Room's own #1."""
    sm = FakeSpoolman({1: {"location": "DR", "extra": {}},
                       2: {"location": "DR-X-9", "extra": {}}})
    status, body, saves = _delete(sm, client, "DR")
    assert status == 200 and body["unassigned"] == [1], body
    assert sm.spools[1]["location"] == "" and sm.spools[2]["location"] == "DR-X-9"
    assert saves and "DR" not in saves[-1]


def test_deleting_a_box_never_takes_a_spool_off_the_head_it_feeds(client, logs):
    """FAILS on the old route: #57, deployed from LR-MDB-1 slot 1 onto XL-1,
    matched the box through its trail and was unassigned off the head. Now it
    stays on XL-1 and loses only the trail to the deleted box; #58, in slot 2,
    is unassigned with its slot cleared."""
    sm = FakeSpoolman({
        57: {"location": "XL-1", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "1"}},
        58: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}},
    })
    status, body, saves = _delete(sm, client, "LR-MDB-1")
    assert status == 200, body
    assert sm.spools[57]["location"] == "XL-1"
    assert sm.spools[57]["extra"]["physical_source"] == "" and sm.spools[57]["extra"]["physical_source_slot"] == ""
    assert sm.spools[58]["location"] == "" and sm.spools[58]["extra"]["container_slot"] == ""
    assert body["unassigned"] == [58] and body["trails_cleared"] == [57], body
    assert saves and "LR-MDB-1" not in saves[-1]
    assert any(m.startswith("🗑️ Deleted: LR-MDB-1 — 1 spool(s) → Unassigned; 1 box link(s) cleared")
               for m, _ in logs), logs


def test_a_heads_resident_reached_by_prefix_is_left_loaded(client, logs):
    """FAILS on the old route: deleting the cart TB unassigned TB-1's spool."""
    sm = FakeSpoolman({21: {"location": "TB-1", "extra": {}}})
    status, body, saves = _delete(sm, client, "TB")
    assert status == 200 and body["skipped_loaded"] == [21], body
    assert sm.spools[21]["location"] == "TB-1" and sm.writes == []


def test_a_rejected_write_keeps_the_row(client, logs):
    sm = FakeSpoolman({58: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}}}, reject_ids=[58])
    status, body, saves = _delete(sm, client, "LR-MDB-1")
    assert status == 502 and body["success"] is False and "#58" in body["msg"], body
    assert saves == [], "the row was deleted with a spool still filed on it"


@pytest.mark.parametrize("loc,status_code", [("UNASSIGNED", 400), ("unknown", 400), ("ZZ-9", 409)])
def test_a_built_in_list_or_an_unsaved_name_is_not_deleted(client, logs, loc, status_code):
    """FAILS on the old route: a "(Room)" or native name went down the generic
    path, which unassigned every spool its prefix matched."""
    sm = FakeSpoolman({31: {"location": "ZZ-9-A", "extra": {}}, 32: {"location": "", "extra": {}}})
    status, body, saves = _delete(sm, client, loc)
    assert status == status_code and body["success"] is False, body
    assert sm.writes == [] and saves == []


def test_a_lowercase_id_deletes_the_row_it_names(client, logs):
    """FAILS on the old route: the guard matched case-insensitively but the
    final filter did not, so ?id=dr reported success and deleted nothing."""
    sm = FakeSpoolman({})
    status, body, saves = _delete(sm, client, "dr")
    assert status == 200 and saves and "DR" not in saves[-1], (body, saves)
