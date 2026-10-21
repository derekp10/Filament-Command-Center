"""An archived spool is never left archived on a head (Group 51 review, engine-1;
Derek's rule, 2026-10-20).

51.1 made a move's write keep a spool archived (an archived spool stays
archived). But every reader of a head (Smart Load's residents, the print deduct,
Printer Status) lists only spools in stock, so a spool archived by hand and then
loaded onto a toolhead sat there invisible: the next print charged nothing and
the next spool was loaded on top of it. The review's fix refused every archived
spool at a head. Derek, 2026-10-20: spools are archived because they hit 0 g,
rarely by hand, so one whose record still has filament on it and is being loaded
physically has filament: the head write un-archives it (`unarchived` in the
answer, a WARNING line, the pre-archive note used up). One at 0 g, or with no
known weight, is still refused with nothing written (`blocked_reason:
archived`), and so is any archived spool when the caller keeps it archived (a
wizard Save that ticks Archived, `keep_archived`). Into a bound slot the box
write stores it, and the chained deploy loads it or says why not.

The REAL routes, engine and update_spool, with only Spoolman's HTTP faked, and
location readers that omit archived spools as Spoolman's default list does
(adopted from the review's probe, test_probe_engine_archived_onto_head.py).
Base proof (dev f978ef9): every test fails there but the control: the
un-archive ones because it refused every archived spool, the refusals on their
new wording, _filament_left_g because it didn't exist.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, WireSpoolman, _unwire, run_move  # noqa: E402

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3)],
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3"}}},
    {"LocationID": "CR-SHELF", "Type": "Shelf", "Max Spools": "12", "parent_id": "LR"},
]
DOOR = {"confirmed_toolheads": [], "confirmed_fed_heads": []}
EMPTY_WHY = ("#58 is archived with no filament left on its record (0 g), so it was not loaded onto XL-1: "
             "weigh it back into stock first")
UNKNOWN_WHY = ("#59 is archived and its record doesn't say how much filament is left, so it was not loaded "
               "onto XL-1: weigh it back into stock first")


class ArchivedHidingSpoolman(WireSpoolman):
    """The REAL update_spool with HTTP faked, keeping weights and `archived`
    like Spoolman, whose LOCATION readers omit archived spools as Spoolman's
    default spool list does."""

    def _http_patch(self, url, json=None, **k):
        sid = int(str(url).rstrip("/").rsplit("/", 1)[-1])
        body = copy.deepcopy(json)
        self.patch_bodies.append((sid, body))
        rec = self.spools.setdefault(sid, {"location": "", "extra": {}})
        for key in ("location", "used_weight", "initial_weight", "archived"):
            if key in body:
                rec[key] = body[key]
        if "extra" in body:
            rec["extra"] = {key: _unwire(val) for key, val in body["extra"].items()}
        return MagicMock(ok=True, status_code=200, json=MagicMock(return_value={"id": sid, **copy.deepcopy(rec)}))

    def _match(self, rec, loc):
        return None if rec.get("archived") else super()._match(rec, loc)


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


def _sm():
    return ArchivedHidingSpoolman({
        # Archived by hand with 300 g left (it was set aside on the shelf).
        57: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 700, "archived": True,
             "extra": {"fcc_pre_archive_location": "CR-SHELF"}},
        # Auto-archived when a print used it up.
        58: {"location": "", "initial_weight": 1000, "used_weight": 1000, "archived": True, "extra": {}},
        # Archived, and neither it nor its filament has a weight.
        59: {"location": "CR-SHELF", "used_weight": 40, "archived": True, "extra": {}},
        60: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 100, "archived": False, "extra": {}},
    })


def _post(client, sm, url, body):
    return run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                    call=lambda: client.post(url, json=body)).get_json()


def _doors(sid):
    return [
        ("/api/smart_move", dict(DOOR, location="XL-1", spools=[sid], origin="buffer")),                # LOC:XL-1
        ("/api/smart_move", dict(DOOR, location="XL-1", spools=[sid], origin="buffer", expected_residents=[])),
        ("/api/manage_contents", dict(DOOR, action="add", location="XL-1", spool_id=f"ID:{sid}",
                                      origin="manual_override")),                                       # Force Location
    ]


DOOR_IDS = ["head-label", "printer-picker-head-pick", "force-location"]


@pytest.mark.parametrize("door", range(3), ids=DOOR_IDS)
def test_an_archived_spool_with_filament_on_record_is_unarchived_and_loaded(client, door):
    """RED on 2ec9f46: refused there, whatever its weight."""
    sm = _sm()
    url, body = _doors(57)[door]
    res = _post(client, sm, url, body)
    assert res["status"] == "success" and not res.get("failures"), res
    assert res["unarchived"] == [{"id": 57, "left_g": 300.0, "head": "XL-1"}], res
    rec = sm.spools[57]
    assert rec["location"] == "XL-1" and rec["archived"] is False, rec
    # One PATCH moves and un-archives it, and uses up the pre-archive note.
    [(sid, patch)] = [(s, b) for s, b in sm.patch_bodies if s == 57]
    assert patch["archived"] is False and patch["location"] == "XL-1", patch
    assert str(rec["extra"].get("fcc_pre_archive_location") or "").strip('"') == "", rec["extra"]
    warn = [e for e in state.RECENT_LOGS if e["type"] == "WARNING"
            and "#57 was archived with 300 g left on its record: FCC un-archived it to load it onto XL-1" in e["msg"]]
    assert warn, state.RECENT_LOGS


@pytest.mark.parametrize("sid, why", [(58, EMPTY_WHY), (59, UNKNOWN_WHY)], ids=["used-up", "no-known-weight"])
@pytest.mark.parametrize("door", range(3), ids=DOOR_IDS)
def test_an_archived_spool_with_no_filament_on_record_is_refused_with_nothing_written(client, door, sid, why):
    sm = _sm()
    url, body = _doors(sid)[door]
    before = copy.deepcopy(sm.spools[sid])
    res = _post(client, sm, url, body)
    assert res.get("blocked_reason") == "archived", res
    assert res["msg"] == f"Not loaded: {why}.", res
    assert sm.writes == [] and sm.spools[sid] == before, sm.writes


def test_a_caller_that_keeps_it_archived_is_refused():
    """A wizard Save that ticks Archived and sets a head (`keep_archived`)."""
    sm = _sm()
    res = run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                   target="XL-1", raw_spools=[57], origin="wizard_edit", confirm_active_print=[],
                   keep_archived=True)
    assert res.get("blocked_reason") == "archived", res
    assert res["msg"] == "Not loaded: #57 is archived, so it was not loaded onto XL-1: untick Archived to load it.", res
    assert sm.writes == [] and sm.spools[57]["archived"] is True


def test_a_bound_slot_stores_and_loads_one_with_filament_on_record(client):
    """Scan #57's label, then LR-MDB-1 slot 1's (bound to XL-1): the box write
    stores it, and the chained deploy un-archives and loads it."""
    sm = _sm()
    state.GLOBAL_BUFFER = [{"id": 57, "display": "#57"}]
    res = _post(client, sm, "/api/identify_scan", dict(DOOR, text="LOC:LR-MDB-1:SLOT:1", source="barcode"))
    assert res["action"] == "assignment_done" and res["auto_deployed_to"] == "XL-1", res
    assert res["smart_move"]["unarchived"] == [{"id": 57, "left_g": 300.0, "head": "XL-1"}], res
    rec = sm.spools[57]
    assert rec["location"] == "XL-1" and rec["archived"] is False, rec
    assert rec["extra"].get("physical_source") == "LR-MDB-1", rec["extra"]


def test_a_bound_slot_stores_a_used_up_one_and_says_why_it_was_not_loaded(client):
    sm = _sm()
    state.GLOBAL_BUFFER = [{"id": 58, "display": "#58"}]
    res = _post(client, sm, "/api/identify_scan", dict(DOOR, text="LOC:LR-MDB-1:SLOT:1", source="barcode"))
    rec = sm.spools[58]
    assert rec["location"] == "LR-MDB-1" and str(rec["extra"].get("container_slot")).strip('"') == "1", rec
    assert rec["archived"] is True and sm.direct_at("XL-1") == [], rec
    assert res.get("not_deployed_target") == "XL-1" and EMPTY_WHY in (res.get("not_deployed") or ""), res


def test_control_a_spool_in_stock_still_loads_and_names_nothing(client):
    sm = _sm()
    res = _post(client, sm, "/api/smart_move", dict(DOOR, location="XL-1", spools=[60], origin="buffer"))
    assert res["status"] == "success" and not res["failures"], res
    assert "unarchived" not in res, res
    assert sm.direct_at("XL-1") == [60]
    assert all("archived" not in b for _s, b in sm.patch_bodies), sm.patch_bodies


@pytest.mark.parametrize("rec, left", [
    ({"remaining_weight": 250.5}, 250.5),
    ({"initial_weight": 1000, "used_weight": 700}, 300.0),
    ({"used_weight": 100, "filament": {"weight": 750}}, 650.0),
    ({"used_weight": 10}, None),
    ({"remaining_weight": "x", "initial_weight": 1000, "used_weight": 1000}, 0.0),
    (None, None),
], ids=["spoolman-remaining", "own-capacity", "filament-capacity", "unknown", "bad-remaining", "no-record"])
def test_filament_left_on_a_record(rec, left):
    assert logic._filament_left_g(rec) == left


def test_a_tool_head_no_printer_lists_unarchives_it_too(client):
    """2026-10-20 review (engine-3): XL-9 is a Tool Head row that XL's
    toolheads[] doesn't list (an ambiguous tool number on create, or one removed
    in Settings), so its write takes the GENERIC branch, which left #57 archived
    ON XL-9 with a plain success. RED on b779b84."""
    sm = _sm()
    store = LocationsStore(ROWS + [{"LocationID": "XL-9", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"}])
    res = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP,
                   call=lambda: client.post("/api/smart_move", json=dict(DOOR, location="XL-9", spools=[57],
                                                                          origin="buffer"))).get_json()
    assert res["status"] == "success" and not res.get("failures"), res
    assert res["unarchived"] == [{"id": 57, "left_g": 300.0, "head": "XL-9"}], res
    assert sm.spools[57]["location"] == "XL-9" and sm.spools[57]["archived"] is False, sm.spools[57]
