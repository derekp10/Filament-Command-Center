"""Group 51 review (engine-1, orange): an archived spool is never loaded onto a head.

51.1 made a move's write keep a spool archived (Derek: an archived spool stays
archived). But every reader of a head (Smart Load's residents, the print deduct,
Printer Status) lists only spools in stock, so a spool archived by hand and then
loaded onto a toolhead sat there invisible: the next print charged nothing and
the next spool was loaded on top of it. Now the engine refuses it at step 4,
before anything is written (`blocked_reason: archived`), on every door that
loads a head; into a bound slot the box write stores it and the chained deploy
says why it wasn't loaded.

Adopted from the reviewer's probe (test_probe_engine_archived_onto_head.py):
the REAL routes, engine and update_spool, with only Spoolman's HTTP faked, and
location readers that omit archived spools as Spoolman's default list does.
Base proof: on the bundle tip a5d8cb8 every test fails except the control.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

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
WHY = "#57 is archived, so it was not loaded onto XL-1: weigh it back into stock (or untick Archived in Edit) first"


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
        57: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 700, "archived": True, "extra": {}},
        60: {"location": "CR-SHELF", "initial_weight": 1000, "used_weight": 100, "archived": False, "extra": {}},
    })


def _post(client, sm, url, body):
    return run_move(sm, probe=IDLE, store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                    call=lambda: client.post(url, json=body)).get_json()


@pytest.mark.parametrize("url, body", [
    ("/api/smart_move", dict(DOOR, location="XL-1", spools=[57], origin="buffer")),                  # LOC:XL-1
    ("/api/smart_move", dict(DOOR, location="XL-1", spools=[57], origin="buffer", expected_residents=[])),
    ("/api/manage_contents", dict(DOOR, action="add", location="XL-1", spool_id="ID:57",
                                  origin="manual_override")),                                         # Force Location
], ids=["head-label", "printer-picker-head-pick", "force-location"])
def test_an_archived_spool_is_refused_at_a_head_with_nothing_written(client, url, body):
    sm = _sm()
    res = _post(client, sm, url, body)
    assert res.get("blocked_reason") == "archived", res
    assert res["msg"] == f"Not loaded: {WHY}.", res
    assert sm.writes == [], sm.writes
    assert sm.spools[57]["location"] == "CR-SHELF" and sm.spools[57]["archived"] is True


def test_a_bound_slot_stores_it_and_says_why_it_was_not_loaded(client):
    """Scan #57's label, then LR-MDB-1 slot 1's (bound to XL-1)."""
    sm = _sm()
    state.GLOBAL_BUFFER = [{"id": 57, "display": "#57"}]
    res = _post(client, sm, "/api/identify_scan", dict(DOOR, text="LOC:LR-MDB-1:SLOT:1", source="barcode"))
    rec = sm.spools[57]
    assert rec["location"] == "LR-MDB-1" and rec["extra"].get("container_slot") == "1", rec
    assert rec["archived"] is True and sm.direct_at("XL-1") == [], rec
    assert res.get("not_deployed_target") == "XL-1" and WHY in (res.get("not_deployed") or ""), res


def test_control_a_spool_in_stock_still_loads(client):
    sm = _sm()
    res = _post(client, sm, "/api/smart_move", dict(DOOR, location="XL-1", spools=[60], origin="buffer"))
    assert res["status"] == "success" and not res["failures"], res
    assert sm.direct_at("XL-1") == [60]
