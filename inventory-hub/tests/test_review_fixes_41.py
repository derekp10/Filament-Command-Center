"""Group 41's adversarial review (2026-10-14): one pin per confirmed finding.
Each fails on the branch before the review's fixes (a1b2db7).

Undo Last Move
  - a box-slot move whose auto-deploy loaded a head kept the BOX as the
    record's target, so undoing it mid-print emptied that head unasked;
  - record numbers restarted at 1 with the process, so a dialog left open
    across a restart could undo a move it never named;
  - a Yes with no number skipped both the stale check and the print re-check;
  - a page loaded before 41.4 got a question it can't show: nothing happened,
    and nothing was logged;
  - it was refused during a bulk move but not during an audit, whose panel
    hides the dialog the same way.
The move engine
  - a write that landed but answered an error (update_spool's timeout is a
    READ timeout) was tallied as failed and left out of the undo record;
  - a one-spool head named with a slot was re-read AFTER Smart Load unloaded
    it, so a blip there left the head empty;
  - a ghost (a spool deployed FROM the slot) was "unseated", a write that never
    frees the slot, and its failure refused the incoming spool;
  - the auto-slot pick read the box fail-open, so a blip picked an occupied
    slot whose spool the strict slot block then unseated.
Location delete
  - the toolhead cascade read fail-open: a blip deleted the head with its spool
    still filed on it;
  - the prompt's contents read was fail-open ("It holds no spools.");
  - a refused delete hid the spools it had already unassigned.
Room-like rows
  - a "Virtual Room / Zone" row, or a blank-Type parent the UI shows as
    "(Room)", was swept by Eject All and by a delete's prefix match;
  - /api/locations now marks the rows FCC synthesizes, so the frontend hides
    ✏️ / 🗑️ on those and not on real rows that share a Type.

The real engine and routes run against tests/move_engine_harness.py's FakeSpoolman.
"""
from __future__ import annotations

import itertools
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, _probe_for, run_move  # noqa: E402

XL = "🦝 XL"
PRINTER_MAP = {
    "XL-1": {"printer_name": XL, "position": 0},
    "XL-2": {"printer_name": XL, "position": 1},
    # A dual-role printer that is its own head (the old Core One shape).
    "SOLO": {"printer_name": "Solo", "position": 0},
}
LOCATIONS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    # Slot 2 feeds XL-2, so a spool placed there is loaded onto XL-2.
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"2": "XL-2"}}},
    {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1}]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "SOLO", "Type": "Printer", "Max Spools": "1",
     "toolheads": [{"location_id": "SOLO", "position": 0}]},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "CR-CT-2-R2", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
    # Room-like rows that aren't Type "Room": a zone, and a legacy blank-Type parent.
    {"LocationID": "GAR", "Type": "Virtual Room", "Max Spools": "0"},
    {"LocationID": "OLD", "Type": "", "Max Spools": "0"},
]


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def quiet_sessions(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(state, "BULK_MOVE_SESSION", {"active": False})
    monkeypatch.setattr(state, "AUDIT_SESSION", {"active": False})


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _move(sm, probe=IDLE, **kw):
    return run_move(sm, probe=probe, locations=LOCATIONS, printer_map=PRINTER_MAP, **kw)


def _call(sm, fn, probe=IDLE):
    return run_move(sm, probe=probe, locations=LOCATIONS, printer_map=PRINTER_MAP, call=fn)


def _undo(sm, client, body=None, probe=IDLE, raw=False):
    def post():
        if raw:   # what a page loaded before 41.4 sends: no body at all
            return client.post("/api/undo")
        return client.post("/api/undo", json={} if body is None else body)
    return _call(sm, post, probe).get_json()


def _in_slot(sm, box, slot):
    return sorted(sid for sid, r in sm.spools.items()
                  if r.get("location") == box and (r.get("extra") or {}).get("container_slot") == slot)


# --- Undo Last Move -----------------------------------------------------------

def _deploy_57_through_slot_2(sm):
    res = _move(sm, target="LR-MDB-1", raw_spools=[57], target_slot="2")
    assert logic.smart_move_failure(res, 57) == "", res
    assert sm.spools[57]["location"] == "XL-2", "precondition: the chain loaded #57 onto XL-2"
    return state.UNDO_STACK[-1]


def test_undoing_an_auto_deploy_names_the_head_it_loaded(client, logs):
    """The record's target is LR-MDB-1, but #57 is on XL-2: the question must
    probe XL-2, and the log must say where #57 was taken from."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}})
    record = _deploy_57_through_slot_2(sm)
    writes = len(sm.writes)

    ask = _undo(sm, client, probe=_probe_for({XL}))
    assert ask["requires_confirm"] is True, ask
    assert [a["toolhead"] for a in ask["active_prints"]] == ["XL-2"], ask
    assert "XL-2" in ask["msg"] and ask["msg"].endswith("Undo: put #57 back in CR-CT-2-R1?"), ask
    assert len(sm.writes) == writes, "the question wrote"

    done = _undo(sm, client, {"confirm": True, "undo_id": record["id"], "confirmed_toolheads": ["XL-2"]},
                 probe=_probe_for({XL}))
    assert done["success"] is True, done
    assert sm.spools[57]["location"] == "CR-CT-2-R1"
    assert done["msg"] == "↩️ Undo: #57 is back in CR-CT-2-R1 (it had been moved to LR-MDB-1; #57 was at XL-2)", done


def test_undoing_an_auto_deploy_from_another_head_names_both_heads(client, logs):
    """The finding's variant: #57 came off XL-1, so the undo loads XL-1 AND
    empties XL-2; the call-out named only XL-1."""
    sm = FakeSpoolman({57: {"location": "XL-1", "extra": {}}})
    _deploy_57_through_slot_2(sm)
    ask = _undo(sm, client, probe=_probe_for({XL}))
    assert sorted(a["toolhead"] for a in ask["active_prints"]) == ["XL-1", "XL-2"], ask


def test_an_unreadable_spool_asks_nothing_and_writes_nothing(client, logs):
    """Where a spool is NOW decides which heads are asked about, so a spool
    Spoolman can't read fails closed instead of asking a partial question."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}})
    _deploy_57_through_slot_2(sm)
    sm.unreadable.add(57)
    writes = len(sm.writes)
    ask = _undo(sm, client)
    assert ask["success"] is False and not ask.get("requires_confirm"), ask
    assert "Couldn't read #57 from Spoolman" in ask["msg"], ask
    assert len(sm.writes) == writes and len(state.UNDO_STACK) == 1


def test_an_undo_number_from_before_a_restart_is_refused(client, logs, monkeypatch):
    """The first move after a restart was numbered 1 again, so a dialog left
    open across the restart (holding 1) undid it."""
    monkeypatch.setattr(logic, "_UNDO_IDS", itertools.count(1))
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}})
    _move(sm, target="CR-CT-2-R2", raw_spools=[57])
    writes = len(sm.writes)
    done = _undo(sm, client, {"confirm": True, "undo_id": 1})
    assert done["success"] is False and done.get("stale") is True, done
    assert len(sm.writes) == writes and len(state.UNDO_STACK) == 1
    assert sm.spools[57]["location"] == "CR-CT-2-R2"


def test_a_yes_that_names_no_move_is_refused(client, logs):
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}})
    _move(sm, target="CR-CT-2-R2", raw_spools=[57])
    writes = len(sm.writes)
    done = _undo(sm, client, {"confirm": True})
    assert done["success"] is False, done
    assert len(sm.writes) == writes and len(state.UNDO_STACK) == 1
    assert any("didn't say which move" in m and a[0] == "WARNING" for m, a in logs), logs


def test_a_press_from_a_page_older_than_41_4_is_refused_and_logged(client, logs):
    """The old triggerUndo POSTs no body and ignores the answer, so the
    question it got made pressing Undo do nothing, silently."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}})
    _move(sm, target="CR-CT-2-R2", raw_spools=[57])
    writes = len(sm.writes)
    done = _undo(sm, client, raw=True)
    assert done["success"] is False and done.get("stale_page") is True, done
    assert "Reload the page" in done["msg"], done
    assert any("out of date" in m and a[0] == "WARNING" for m, a in logs), logs
    assert len(sm.writes) == writes and len(state.UNDO_STACK) == 1


def test_undo_is_off_while_an_audit_runs(client, logs, monkeypatch):
    """Like a bulk move: the audit panel hides the dialog, and the scans it then
    swallowed were auto-parked to UNKNOWN by the audit's Done."""
    monkeypatch.setattr(state, "AUDIT_SESSION", {"active": True, "location_id": "CR-CT-2-R1"})
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}})
    _move(sm, target="CR-CT-2-R2", raw_spools=[57])
    ask = _undo(sm, client)
    assert ask["success"] is False and not ask.get("requires_confirm"), ask
    assert "audit" in ask["msg"], ask
    assert any("audit" in m and a[0] == "WARNING" for m, a in logs), logs


# --- The move engine ------------------------------------------------------------

def test_a_write_that_landed_despite_an_error_counts_as_moved(logs):
    """It used to be a failure: left out of the undo record (Undo couldn't put
    it back) and tallied as failed."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}}, landed_but_failed=[57])
    res = _move(sm, target="LR-MDB-2", raw_spools=[57], target_slot="1")
    assert logic.smart_move_failure(res, 57) == "", res
    assert state.UNDO_STACK and state.UNDO_STACK[-1]["moves"] == {57: "CR-CT-2-R1"}
    assert any("but a re-read shows it there" in m and a[0] == "WARNING" for m, a in logs), logs


def test_a_rejected_write_is_still_a_failure(logs):
    """Control: a write that really didn't land stays a failure (passes before too)."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}}, reject_ids=[57])
    res = _move(sm, target="LR-MDB-2", raw_spools=[57], target_slot="1")
    assert "rejected by test" in logic.smart_move_failure(res, 57), res
    assert state.UNDO_STACK == []


def test_the_bulk_tally_counts_a_write_that_landed_as_moved(logs):
    sm = FakeSpoolman({1: {"location": "CR-CT-2-R1", "extra": {}},
                       2: {"location": "CR-CT-2-R1", "extra": {}},
                       3: {"location": "CR-CT-2-R1", "extra": {}}}, landed_but_failed=[2])
    body = _call(sm, lambda: logic.execute_bulk_move(logic.plan_bulk_move("CR-CT-2-R1", "CR-CT-2-R2")))
    assert body["success"] is True and body["moved"] == 3 and body["failed"] == [], body
    assert sm.direct_at("CR-CT-2-R2") == [1, 2, 3]


class _BlipAfterUnload(FakeSpoolman):
    """Spoolman's spool list stops answering once SOLO's resident has left."""

    def at_location_detailed_strict(self, loc):
        if str(loc).upper() == "SOLO" and self.spools[50]["location"] != "SOLO":
            self.list_reads += 1
            raise spoolman_api.requests.ConnectionError("Spoolman blip after the unload (test)")
        return super().at_location_detailed_strict(loc)


def test_a_head_named_with_a_slot_is_not_read_again_after_smart_load(logs):
    """LOC:SOLO:SLOT:1 with #50 loaded: Smart Load unloads #50 after a strict
    read, then the slot block read SOLO again; a blip there refused #99 and
    left SOLO empty (mid-print, if the user had confirmed)."""
    sm = _BlipAfterUnload({
        50: {"location": "SOLO", "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "3"}},
        99: {"location": "CR-CT-2-R1", "extra": {}},
    })
    res = _move(sm, target="SOLO", raw_spools=[99], target_slot="1")
    assert logic.smart_move_failure(res, 99) == "", res
    assert sm.direct_at("SOLO") == [99]
    assert sm.spools[50]["location"] == "LR-MDB-2"


def test_a_ghost_in_the_slot_is_never_unseated(logs):
    """#57 is deployed from LR-MDB-2 slot 2 onto XL-2, so the box lists it as a
    ghost in slot 2. Clearing #57's own container_slot never frees a trail's
    slot, and since 41.6 that pointless write's failure refused #99."""
    sm = FakeSpoolman({
        57: {"location": "XL-2", "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "2"}},
        99: {"location": "CR-CT-2-R1", "extra": {}},
    }, reject_ids=[57])
    res = _move(sm, target="LR-MDB-2", raw_spools=[99], target_slot="2")
    assert logic.smart_move_failure(res, 99) == "", res
    assert _in_slot(sm, "LR-MDB-2", "2") == [99]
    assert [w for w in sm.writes if w[0] == 57] == [], "the ghost was written"


def test_auto_slot_reads_the_box_strictly(logs):
    """A blip on the fail-open pick read the box as empty, chose slot 1, and the
    strict slot block then unseated #7 from it although three slots were free."""
    sm = FakeSpoolman({7: {"location": "LR-MDB-2", "extra": {"container_slot": "1"}},
                       99: {"location": "CR-CT-2-R1", "extra": {}}})
    sm.fail_list_reads = {0}   # the auto-slot pick is this move's first list read
    res = _move(sm, target="LR-MDB-2", raw_spools=[99])
    assert "couldn't read LR-MDB-2 from Spoolman" in logic.smart_move_failure(res, 99), res
    assert sm.writes == [], "a move with an unread box wrote"
    assert _in_slot(sm, "LR-MDB-2", "1") == [7]


# --- Location delete --------------------------------------------------------------

def _delete(sm, client, loc, save_ok=True):
    saves = []

    def save(lst):
        saves.append([r["LocationID"] for r in lst])
        return save_ok
    with patch.object(locations_db, "save_locations_list", side_effect=save):
        resp = _call(sm, lambda: client.delete(f"/api/locations?id={loc}"))
    return resp.status_code, resp.get_json(), saves


def test_a_toolhead_delete_keeps_the_row_when_spoolman_cant_be_read(client, logs):
    sm = FakeSpoolman({57: {"location": "XL-2", "extra": {}}})
    sm.list_reads_fail = True
    status, body, saves = _delete(sm, client, "XL-2")
    assert status == 502 and body["success"] is False, body
    assert body["msg"].startswith("XL-2 was NOT deleted: could not list spools at XL-2"), body
    assert saves == [] and sm.writes == []


def test_a_failed_delete_names_the_spools_it_already_unassigned(client, logs):
    sm = FakeSpoolman({58: {"location": "LR-MDB-2", "extra": {"container_slot": "2"}},
                       59: {"location": "LR-MDB-2", "extra": {"container_slot": "3"}}}, reject_ids=[59])
    status, body, saves = _delete(sm, client, "LR-MDB-2")
    assert status == 502 and saves == [], body
    assert "#59" in body["msg"] and "Already unassigned: #58." in body["msg"], body
    assert any("Already unassigned: #58." in m for m, a in logs), logs


def test_a_delete_whose_save_fails_says_what_already_moved(client, logs):
    sm = FakeSpoolman({58: {"location": "LR-MDB-2", "extra": {"container_slot": "2"}}})
    status, body, saves = _delete(sm, client, "LR-MDB-2", save_ok=False)
    assert status == 500 and "locations.json could not be saved" in body["msg"], body
    assert "Already unassigned: #58." in body["msg"], body


def test_a_toolhead_delete_that_fails_names_what_it_already_did(client, logs):
    sm = FakeSpoolman({
        57: {"location": "XL-2", "extra": {}},
        60: {"location": "LR-MDB-2", "extra": {"physical_source": "XL-2"}},   # a stale trail to XL-2
    }, reject_ids=[60])
    status, body, saves = _delete(sm, client, "XL-2")
    assert status == 502 and saves == [], body
    assert "Already unassigned: #57." in body["msg"], body


def test_get_contents_can_be_read_strictly(client):
    """The delete prompt's read: a Spoolman blip is an error, not "no spools"."""
    sm = FakeSpoolman({58: {"location": "LR-MDB-2", "extra": {}}})
    sm.list_reads_fail = True
    resp = _call(sm, lambda: client.get("/api/get_contents?id=LR-MDB-2&strict=1"))
    assert resp.status_code == 502 and resp.get_json()["error"], resp.get_json()
    sm.list_reads_fail = False
    resp = _call(sm, lambda: client.get("/api/get_contents?id=LR-MDB-2&strict=1"))
    assert [r["id"] for r in resp.get_json()] == [58]


# --- Room-like rows -----------------------------------------------------------------

@pytest.mark.parametrize("loc,expected", [
    ("GAR", "room_view"),     # a "Virtual Room / Zone"
    ("OLD", "room_view"),     # a dash-less blank-Type row: the UI shows it as "OLD (Room)"
    ("LR-MDB-2", None),
])
def test_room_like_rows_refuse_eject_all(loc, expected):
    rows = {r["LocationID"]: r for r in LOCATIONS}
    assert logic.eject_all_block_reason(loc, rows[loc], PRINTER_MAP) == expected


def test_eject_all_on_a_zone_reads_and_writes_nothing(client, logs):
    sm = FakeSpoolman({1: {"location": "GAR-SHELF-1", "extra": {"physical_source": "LR-MDB-2"}}})
    body = _call(sm, lambda: client.post("/api/manage_contents",
                                         json={"action": "clear_location", "location": "GAR"})).get_json()
    assert body["success"] is False and body["blocked_reason"] == "room_view", body
    assert sm.list_reads == 0 and sm.writes == []


@pytest.mark.parametrize("loc", ["GAR", "OLD"])
def test_deleting_a_room_like_row_unassigns_only_its_own_spools(client, logs, loc):
    """#2 sits on a row-less location under the prefix; it isn't this row's."""
    sm = FakeSpoolman({1: {"location": loc, "extra": {}},
                       2: {"location": f"{loc}-X-9", "extra": {}}})
    status, body, saves = _delete(sm, client, loc)
    assert status == 200 and body["unassigned"] == [1], body
    assert sm.spools[2]["location"] == f"{loc}-X-9"


def _locations_payload(rows, native=(), spools=()):
    resp = MagicMock(ok=True)
    resp.json.return_value = list(spools)
    with patch.object(locations_db, "load_locations_list", return_value=rows), \
         patch.object(spoolman_api, "get_all_locations", return_value=list(native)), \
         patch.object(logic.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch("routes_locations.requests.get", return_value=resp):
        app_module.app.config["TESTING"] = True
        return app_module.app.test_client().get("/api/locations").get_json()


def test_api_locations_marks_the_rows_fcc_synthesizes():
    """The frontend hid ✏️ / 🗑️ by Type, which real rows share (a "Virtual Room
    / Zone", prod's blank-id "Unknown Location", a promoted blank-Type parent).
    Only rows with no locations.json row are marked."""
    rows = [{"LocationID": "GAR", "Name": "Garage", "Type": "Virtual Room"},
            {"LocationID": "OLD", "Name": "Old", "Type": ""},
            {"LocationID": "OLD-1", "Name": "Old shelf", "Type": "Shelf", "parent_id": "OLD"},
            {"LocationID": "", "Name": "Unknown Location", "Type": "Virtual Room"}]
    spools = [{"id": 1, "location": "ZZ-9", "extra": {}}, {"id": 2, "location": "Shelf 9", "extra": {}},
              {"id": 3, "location": "OLD-1", "extra": {}}]
    by_id = {r["LocationID"]: r for r in _locations_payload(rows, native=["Shelf 9"], spools=spools)}
    synthesized = sorted(lid for lid, r in by_id.items() if r.get("Synthesized"))
    assert synthesized == ["Shelf 9", "UNKNOWN", "Unassigned", "ZZ"], by_id
    assert by_id["OLD"]["Type"] == "Virtual Room", "precondition: the blank-Type parent is shown as a room"
    assert "_synth_native" not in by_id["Shelf 9"]
