"""Group 46.5 (was 37.1): a blank LocationID is refused on save, and an existing
blank row can be deleted explicitly.

Root cause (2026-10-08): on save, `if old_id:` is falsy for a blank id, so the
old row was never filtered out, and the duplicate guard was skipped because the
new id was falsy too. A blank row was therefore accepted, and giving it a real
id later appended a SECOND row and left the blank one behind forever (renaming
again collided with the row just made: the "already exists" message). Repair was
blocked both ways, because DELETE /api/locations answers 400 on a blank id.

The fix, per the task file (NOT a startup migration, which would touch prod's
hand-made blank "Unknown Location" row):
  - POST /api/locations answers 400 on a blank or whitespace LocationID;
  - DELETE /api/locations?blank_id=1 removes the row(s) whose LocationID is
    blank — explicitly requested, never by accident (a bare ?id= still 400s,
    pinned by test_l316_charact_record_deletes.py), and with NO Spoolman cascade:
    a blank location is how Spoolman spells "unassigned", so the generic
    cascade's get_spools_at_location('') could reach every unassigned spool.

Dev's own blank "TestCart" row (Derek's repro) is untouched by these tests: the
locations store is stubbed throughout.

HEAD proof: on the pre-fix routes_locations.py the save tests answer 200 and
persist the blank row, and the delete tests answer 400.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import app as app_module  # noqa: E402


def _patch_locations(monkeypatch, rows):
    """Stub the locations store; returns the list of save_locations_list payloads."""
    saves = []
    monkeypatch.setattr(app_module.locations_db, "load_locations_list", lambda: rows)
    monkeypatch.setattr(
        app_module.locations_db, "save_locations_list",
        lambda lst: saves.append(lst) or True,
    )
    return saves


def _capture_logs(monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.state, "add_log_entry",
                        lambda msg, *a, **k: calls.append((msg, a, k)))
    return calls


def _no_spoolman(monkeypatch):
    """Any Spoolman call from a blank-id delete is a bug: fail loudly."""
    def _boom(*a, **k):
        raise AssertionError(f"a blank-id location delete reached Spoolman: {a} {k}")
    for name in ("get_spools_at_location", "get_spools_at_location_detailed", "update_spool"):
        monkeypatch.setattr(app_module.spoolman_api, name, _boom)


ROWS = [
    {"LocationID": "", "Name": "TestCart", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "CR", "Name": "Computer Room", "Type": "Room", "Max Spools": "0", "parent_id": None},
    {"LocationID": "CR-CT-1", "Name": "Cart 1", "Type": "Cart", "Max Spools": "", "parent_id": "CR"},
]


# ---------------------------------------------------------------------------
# POST /api/locations — a blank id is refused
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blank", ["", "   ", "\t", None])
def test_create_with_a_blank_id_is_refused(monkeypatch, blank):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS[1:]])
    logs = _capture_logs(monkeypatch)
    new = {"Name": "Nameless", "Type": "Cart", "Max Spools": "0"}
    if blank is not None:
        new["LocationID"] = blank

    r = client.post("/api/locations", json={"old_id": "", "new_data": new})

    assert r.status_code == 400, r.get_json()
    body = r.get_json()
    assert body["success"] is False and "LocationID" in body["error"], body
    assert saves == [], "a blank LocationID was persisted"
    assert not any("Created" in m for m, _, _ in logs), logs


def test_editing_a_row_to_a_blank_id_is_refused(monkeypatch):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS[1:]])
    _capture_logs(monkeypatch)
    r = client.post("/api/locations", json={
        "old_id": "CR-CT-1",
        "new_data": {"LocationID": "  ", "Name": "Cart 1", "Type": "Cart", "Max Spools": ""}})
    assert r.status_code == 400 and saves == []


def test_a_missing_new_data_is_refused_not_a_500(monkeypatch):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS[1:]])
    _capture_logs(monkeypatch)
    r = client.post("/api/locations", json={"old_id": ""})
    assert r.status_code == 400 and saves == []


def test_a_normal_create_still_saves(monkeypatch):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS[1:]])
    _capture_logs(monkeypatch)
    r = client.post("/api/locations", json={
        "old_id": "", "new_data": {"LocationID": "CR-CT-2", "Name": "Cart 2", "Type": "Cart", "Max Spools": ""}})
    assert r.status_code == 200 and r.get_json()["success"] is True
    assert [row["LocationID"] for row in saves[-1]] == ["CR", "CR-CT-1", "CR-CT-2"]


# ---------------------------------------------------------------------------
# DELETE /api/locations?blank_id=1 — the explicit repair path
# ---------------------------------------------------------------------------

def test_blank_id_delete_removes_only_the_blank_row(monkeypatch):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS])
    logs = _capture_logs(monkeypatch)
    _no_spoolman(monkeypatch)

    r = client.delete("/api/locations?blank_id=1")

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["success"] is True
    assert len(saves) == 1
    assert [row["LocationID"] for row in saves[0]] == ["CR", "CR-CT-1"]
    assert any("blank LocationID" in m and "TestCart" in m for m, _, _ in logs), logs


def test_blank_id_delete_removes_every_blank_row(monkeypatch):
    """Two blank rows collapse to one on screen, so one delete clears both."""
    client = app_module.app.test_client()
    rows = [dict(r) for r in ROWS] + [{"LocationID": "  ", "Name": "Ghost", "Type": "Cart"}]
    saves = _patch_locations(monkeypatch, rows)
    _capture_logs(monkeypatch)
    _no_spoolman(monkeypatch)

    r = client.delete("/api/locations?blank_id=1")

    assert r.status_code == 200
    assert [row["LocationID"] for row in saves[0]] == ["CR", "CR-CT-1"]
    assert r.get_json()["deleted"] == 2


def test_blank_id_delete_with_nothing_blank_is_a_404_and_no_save(monkeypatch):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS[1:]])
    _capture_logs(monkeypatch)
    _no_spoolman(monkeypatch)
    r = client.delete("/api/locations?blank_id=1")
    assert r.status_code == 404 and saves == []
    assert r.get_json()["success"] is False


def test_blank_id_and_a_real_id_together_are_refused(monkeypatch):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS])
    _capture_logs(monkeypatch)
    _no_spoolman(monkeypatch)
    r = client.delete("/api/locations?blank_id=1&id=CR-CT-1")
    assert r.status_code == 400 and saves == []


def test_blank_id_delete_reports_a_failed_save(monkeypatch):
    client = app_module.app.test_client()
    monkeypatch.setattr(app_module.locations_db, "load_locations_list", lambda: [dict(r) for r in ROWS])
    monkeypatch.setattr(app_module.locations_db, "save_locations_list", lambda lst: False)
    logs = _capture_logs(monkeypatch)
    _no_spoolman(monkeypatch)
    r = client.delete("/api/locations?blank_id=1")
    assert r.status_code == 500 and r.get_json()["success"] is False
    assert any(a and a[0] == "ERROR" for _, a, _ in logs), logs


@pytest.mark.parametrize("flag", ["0", "false", "", "no"])
def test_a_false_blank_flag_keeps_the_28b1_answer(monkeypatch, flag):
    client = app_module.app.test_client()
    saves = _patch_locations(monkeypatch, [dict(r) for r in ROWS])
    _capture_logs(monkeypatch)
    r = client.delete(f"/api/locations?blank_id={flag}")
    assert r.status_code == 400
    assert r.get_json() == {"success": False, "msg": "No location id provided."}
    assert saves == []
