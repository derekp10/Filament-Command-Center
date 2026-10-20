"""Group 51.1 — only a weight write is a refill.

update_spool's refill edge (_auto_unarchive_on_refill) read the record's own
weight when a write carried none, so any write to a spool archived by hand with
weight left un-archived it: a move (Force Location, a slot-label scan, the
wizard), the `ID:` label-verify scan's flag, the Undo of a move. An extra-only
write also sent it back to its pre-archive place. Derek's example: archive #57 by
hand with 300 g left and Force Location it onto CR-CT-2-R1: it came back into
stock. Now it moves and stays archived (his 43.2 rule: an archived spool stays
archived). A weight change that leaves weight on it still un-archives it, and an
explicit `archived: False` still gets its place back.

Everything here runs the REAL update_spool (archive and refill edges, the extras
merge) under the REAL routes and move engine, with only Spoolman's HTTP faked
(tests/move_engine_harness.py; [[mocked engine hides chain bugs]]).

Base proof (52741e6): every test fails there except the ones marked "control".
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api as sm_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, WeighedWireSpoolman, run_move  # noqa: E402

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3)],
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3"}}},
    {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2", "parent_id": "LR", "extra": {}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
    {"LocationID": "CR-SHELF", "Type": "Shelf", "Max Spools": "12", "parent_id": "LR"},
]
DOOR = {"confirmed_toolheads": [], "confirmed_fed_heads": []}


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _hand_archived(location="CR-SHELF", **extra):
    """#57, archived by hand with 300 g left (1000 g spool, 700 g used)."""
    return {57: {"location": location, "initial_weight": 1000, "used_weight": 700, "archived": True,
                 "extra": dict(extra)}}


def _call(sm, fn, store=None):
    return run_move(sm, probe=IDLE, store=store or LocationsStore(ROWS), printer_map=PRINTER_MAP, call=fn)


def _unarchived_by(sm, sid=57):
    """Every PATCH that took #57 out of the archive."""
    return [body for s, body in sm.patch_bodies if s == sid and body.get("archived") is False]


def _logs(fragment):
    return [e for e in state.RECENT_LOGS if fragment in str(e.get("message", e))]


# ---- the doors ------------------------------------------------------------------------------------------

def test_force_location_moves_a_hand_archived_spool_and_it_stays_archived(client):
    """Derek's example: Force Location (manage_contents add) onto CR-CT-2-R1."""
    sm = WeighedWireSpoolman(_hand_archived())
    res = _call(sm, lambda: client.post("/api/manage_contents", json=dict(
        DOOR, action="add", location="CR-CT-2-R1", spool_id="ID:57", origin="manual_override"))).get_json()
    assert res["status"] == "success" and not res.get("failures"), res
    spool = sm.spools[57]
    assert spool["location"] == "CR-CT-2-R1" and spool["archived"] is True, spool
    assert not _unarchived_by(sm), sm.patch_bodies
    assert not _logs("Auto-unarchived") and not _logs("Un-archived"), state.RECENT_LOGS


def test_a_slot_label_scan_stores_it_and_it_stays_archived(client):
    """The buffered spool scanned into LR-MDB-2 slot 1 (an unbound slot)."""
    state.GLOBAL_BUFFER = [{"id": 57, "display": "#57"}]
    sm = WeighedWireSpoolman(_hand_archived())
    res = _call(sm, lambda: client.post("/api/identify_scan", json=dict(
        DOOR, text="LOC:LR-MDB-2:SLOT:1", source="barcode"))).get_json()
    assert res["action"] == "assignment_done", res
    spool = sm.spools[57]
    assert spool["location"] == "LR-MDB-2" and spool["extra"]["container_slot"] == "1", spool
    assert spool["archived"] is True, spool
    assert not _unarchived_by(sm), sm.patch_bodies


@pytest.mark.parametrize("note", ["", "XL-1"], ids=["no-note", "pre-archive-note"])
def test_an_id_label_scan_verifies_the_label_and_it_stays_archived_where_it_is(client, note):
    """The label-verify scan writes only the flag. With a pre-archive note it also
    sent the spool back onto XL-1 (an extra-only write named no location, so the
    refill edge restored the note's place)."""
    extra = {"needs_label_print": True}
    if note:
        extra["fcc_pre_archive_location"] = note
    sm = WeighedWireSpoolman(_hand_archived(**extra))
    res = _call(sm, lambda: client.post("/api/identify_scan", json={"text": "ID:57", "source": "barcode"}))
    assert res.get_json()["type"] == "spool", res.get_json()
    spool = sm.spools[57]
    assert spool["extra"]["needs_label_print"] is False, spool
    assert spool["archived"] is True and spool["location"] == "CR-SHELF", spool
    assert spool["extra"].get("fcc_pre_archive_location", "") == note, spool
    assert not _unarchived_by(sm), sm.patch_bodies


def test_undo_of_the_move_puts_it_back_and_it_stays_archived(client):
    """Force Location onto CR-CT-2-R1, then Undo Last Move (ask, then Yes)."""
    sm = WeighedWireSpoolman(_hand_archived())
    store = LocationsStore(ROWS)
    moved = _call(sm, lambda: client.post("/api/manage_contents", json=dict(
        DOOR, action="add", location="CR-CT-2-R1", spool_id="ID:57", origin="manual_override")),
        store=store).get_json()
    assert moved["status"] == "success", moved
    ask = _call(sm, lambda: client.post("/api/undo", json={}), store=store).get_json()
    assert ask.get("requires_confirm") and ask.get("undo_id") is not None, ask
    done = _call(sm, lambda: client.post("/api/undo", json={"confirm": True, "undo_id": ask["undo_id"],
                                                            "confirmed_toolheads": []}),
                 store=store).get_json()
    assert done.get("success") is True, done
    spool = sm.spools[57]
    assert spool["location"] == "CR-SHELF" and spool["archived"] is True, spool
    assert not _unarchived_by(sm), sm.patch_bodies


def test_control_a_weigh_out_that_leaves_weight_still_unarchives(client):
    """Control (green on the base too): a weight change IS a refill. The weigh
    screens send `used_weight` through /api/spool/update."""
    sm = WeighedWireSpoolman(_hand_archived())
    res = _call(sm, lambda: client.post("/api/spool/update", json={"id": 57, "updates": {"used_weight": 500}}))
    assert res.get_json().get("status") == "success", res.get_json()
    assert sm.spools[57]["archived"] is False and sm.spools[57]["used_weight"] == 500, sm.spools[57]


# ---- the edge itself ------------------------------------------------------------------------------------

_ARCHIVED_WITH_WEIGHT = {"archived": True, "initial_weight": 1000, "used_weight": 700,
                         "extra": {"fcc_pre_archive_location": "XL-1"}}


@pytest.fixture(autouse=True)
def _no_destination_reads(monkeypatch):
    """Every test in this file (autouse fixtures are module-wide): where an
    un-archived spool goes (Group 42.3c) is its note's place, as for an empty
    head, with no read of locations.json or Spoolman. 42.3c has its own tests."""
    monkeypatch.setattr(sm_api, "_unarchive_destination", lambda existing, prev, remaining: (str(prev), None))


@pytest.mark.parametrize("write", [
    {"location": "CR-CT-2-R1"},
    {"location": "LR-MDB-2", "extra": {"container_slot": "1"}},
    {"extra": {"needs_label_print": False}},
    {"spool_weight": 180},
], ids=["location", "move-with-trail", "extra-only", "tare-only"])
def test_a_write_without_a_weight_is_no_refill(write):
    data = dict(write)
    warning = sm_api._auto_unarchive_on_refill(data, dict(_ARCHIVED_WITH_WEIGHT))
    assert warning is None
    assert "archived" not in data and data.get("location") == write.get("location"), data
    assert (data.get("extra") or {}).get("fcc_pre_archive_location") is None, data


def test_control_an_explicit_unarchive_still_gets_its_place_back():
    """Control (green on the base too): `archived: False` is the caller's own
    un-archive; with weight left it still goes back to its pre-archive place."""
    data = {"archived": False}
    sm_api._auto_unarchive_on_refill(data, dict(_ARCHIVED_WITH_WEIGHT, location=""))
    assert data["archived"] is False and data["location"] == "XL-1", data


@pytest.mark.parametrize("write", [{"used_weight": 600}, {"initial_weight": 1200}], ids=["used", "initial"])
def test_control_a_weight_write_with_weight_left_is_a_refill(write):
    """Control (green on the base too)."""
    data = dict(write)
    sm_api._auto_unarchive_on_refill(data, dict(_ARCHIVED_WITH_WEIGHT, location=""))
    assert data["archived"] is False, data


def test_a_weigh_back_sent_as_remaining_weight_is_a_refill():
    """Review engine-5: the weigh-out row's fallback (no spool details) sends
    `remaining_weight`; 51.1 counted only used / initial weight as a weight
    write, so weighing a spool archived by hand back to 250 g left it archived.
    RED on a5d8cb8."""
    data = {"remaining_weight": 250.0}
    sm_api._auto_unarchive_on_refill(data, dict(_ARCHIVED_WITH_WEIGHT, location=""))
    assert data["archived"] is False and data["location"] == "XL-1", data


@pytest.mark.parametrize("left", [0, -5, "x"], ids=["empty", "below-empty", "not-a-number"])
def test_control_a_remaining_weight_with_nothing_left_stays_archived(left):
    data = {"remaining_weight": left}
    sm_api._auto_unarchive_on_refill(data, dict(_ARCHIVED_WITH_WEIGHT, location=""))
    assert "archived" not in data and "location" not in data, data
