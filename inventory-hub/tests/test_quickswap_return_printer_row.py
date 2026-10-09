"""Quick-Swap Return resolves a Printer row's toolheads from the row (L271), not
from a "<printer id>-" prefix (2026-09-13).

POST /api/quickswap/return {toolhead} accepts a registered toolhead id or a
printer. For a printer it used to fan out over printer_map keys starting with
"<id>-". That is the same prefix-only assumption that stopped the frontend's
Return on the Core One (Printer row CORE1, single head CORE1). The backend
survived CORE1 only because the exact-toolhead branch caught it; any printer
whose heads do not spell "<id>-..." was a 404, and a lookalike head from another
printer (XL-B1 under XLB) was pulled into the XL fan-out.

Order now: exact toolhead id, then the Printer row's toolheads[], then the
legacy prefix fan-out (kept until L271 Phase 5).

Hermetic: printer_map, locations and every Spoolman / move call are patched.
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _printer_row(loc_id, name, heads):
    return {"LocationID": loc_id, "Name": name, "Type": "Printer",
            "toolheads": [{"location_id": h, "position": i} for i, h in enumerate(heads)]}


def _printer_map(*rows):
    return {th["location_id"].upper(): {"printer_name": row["Name"], "position": th["position"]}
            for row in rows for th in row["toolheads"]}


class _Harness:
    """Patches the collaborators api_quickswap_return reads, records the probe
    order and the move, and serves `loaded` ({toolhead: spool_id})."""

    def __init__(self, rows, loaded, extra_rows=()):
        self.printer_map = _printer_map(*[r for r in rows if r.get("Type") == "Printer"])
        self.locs = list(rows) + list(extra_rows)
        self.loaded = {k.upper(): v for k, v in loaded.items()}
        self.probed = []
        self.moves = []

    def _at(self, loc):
        loc = str(loc).upper()
        self.probed.append(loc)
        return [self.loaded[loc]] if loc in self.loaded else []

    def _spool(self, sid):
        for th, loaded_sid in self.loaded.items():
            if int(loaded_sid) == int(sid):
                return {"id": int(sid), "location": th, "extra": {}}
        return None

    def _move(self, target, spools, target_slot=None, origin=None, **kwargs):
        self.moves.append((target, list(spools), target_slot, origin))
        return {"status": "success"}

    def post(self, client, toolhead):
        with ExitStack() as stack:
            stack.enter_context(patch.object(locations_db, "get_active_printer_map",
                                             return_value=self.printer_map))
            stack.enter_context(patch.object(locations_db, "load_locations_list", return_value=self.locs))
            stack.enter_context(patch.object(spoolman_api, "get_spools_at_location", side_effect=self._at))
            stack.enter_context(patch.object(spoolman_api, "get_spool", side_effect=self._spool))
            stack.enter_context(patch.object(spoolman_api, "get_spools_at_location_detailed", return_value=[]))
            stack.enter_context(patch.object(logic, "perform_smart_move", side_effect=self._move))
            stack.enter_context(patch.object(state, "add_log_entry"))
            return client.post("/api/quickswap/return", json={"toolhead": toolhead})


def _box(loc_id, targets):
    return {"LocationID": loc_id, "Type": "Dryer Box", "Max Spools": "4",
            "extra": {"slot_targets": dict(targets)}}


def test_return_on_a_printer_row_uses_its_toolheads_without_the_id_prefix(client):
    """A Core One+ row (C1P) owning CORE1-T1 / CORE1-T2, the second one loaded.
    FAILS on the old route: 404 return_bad_toolhead, because no printer_map key
    starts with "C1P-"."""
    c1p = _printer_row("C1P", "Core One+", ["CORE1-T1", "CORE1-T2"])
    h = _Harness([c1p], loaded={"CORE1-T2": 55}, extra_rows=[_box("CR-DB-1", {"1": "CORE1-T2"})])

    r = h.post(client, "c1p")

    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["action"] == "return_done"
    assert (body["toolhead"], body["box"], body["slot"], body["source"]) == (
        "CORE1-T2", "CR-DB-1", "1", "first_binding")
    assert h.probed == ["CORE1-T1", "CORE1-T2"]
    assert h.moves == [("CR-DB-1", [55], "1", "quickswap_return")]


def test_return_on_the_core1_printer_row_acts_on_its_same_named_head(client):
    """The real Core One shape: Printer row CORE1, single head CORE1. PASSES on
    the old route too (the exact-toolhead branch caught it; the bug was only in
    the frontend). Pinned so the backend half of the CORE1 Return keeps working."""
    core1 = _printer_row("CORE1", "Core One Upgraded", ["CORE1"])
    h = _Harness([core1], loaded={"CORE1": 42}, extra_rows=[_box("CR-DB-1", {"2": "CORE1"})])

    r = h.post(client, "CORE1")

    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert (body["action"], body["toolhead"], body["box"], body["slot"]) == (
        "return_done", "CORE1", "CR-DB-1", "2")
    assert h.probed == ["CORE1"]
    assert h.moves == [("CR-DB-1", [42], "2", "quickswap_return")]


def test_printer_fan_out_never_reaches_another_printers_lookalike_head(client):
    """XL owns XL-1 / XL-2; a second printer XLB owns XL-B1, which also starts
    with "XL-". Only XL-B1 is loaded, so a Return on XL has nothing to return.
    FAILS on the old route: the prefix fan-out probed XL-B1 and returned the
    OTHER printer's spool (return_done on XL-B1)."""
    xl = _printer_row("XL", "XL", ["XL-1", "XL-2"])
    xlb = _printer_row("XLB", "XL B", ["XL-B1"])
    h = _Harness([xl, xlb], loaded={"XL-B1": 66}, extra_rows=[_box("LR-MDB-1", {"1": "XL-B1"})])

    r = h.post(client, "XL")

    assert r.status_code == 404, r.get_json()
    body = r.get_json()
    assert body["action"] == "return_no_spool"
    assert body["candidates"] == ["XL-1", "XL-2"]
    assert "XL-B1" not in h.probed
    assert h.moves == []


def test_xl_printer_row_fan_out_keeps_the_natural_order(client):
    """XL behaviour is unchanged: the row's heads, stored out of order, are still
    probed in natural order (29.B1: XL-2 before XL-10). PASSES on the old route
    too (prefix fan-out, same set, same sort)."""
    xl = {"LocationID": "XL", "Name": "XL", "Type": "Printer", "toolheads": [
        {"location_id": "XL-10", "position": 9},
        {"location_id": "XL-2", "position": 1},
        {"location_id": "XL-1", "position": 0},
    ]}
    h = _Harness([xl], loaded={})

    r = h.post(client, "XL")

    assert r.status_code == 404
    assert r.get_json()["candidates"] == ["XL-1", "XL-2", "XL-10"]
    assert h.probed == ["XL-1", "XL-2", "XL-10"]


def test_return_reads_locations_json_once(client):
    """The route loads the locations list once and passes it to
    get_active_printer_map. get_active_printer_map is NOT patched here, so its
    real build runs. Called with no list, it reloads locations.json itself.
    FAILS on the first cut of the fix: load_locations_list ran twice, once for
    the printer_map build and once for the route's own read."""
    core1 = _printer_row("CORE1", "Core One Upgraded", ["CORE1"])
    locs = [core1, _box("CR-DB-1", {"2": "CORE1"})]
    loads = []

    def _load():
        loads.append(1)
        return locs

    def _spool(sid):
        return {"id": int(sid), "location": "CORE1", "extra": {}} if int(sid) == 42 else None

    with patch.object(locations_db, "load_locations_list", side_effect=_load), \
         patch.object(spoolman_api, "get_spools_at_location",
                      side_effect=lambda loc: [42] if str(loc).upper() == "CORE1" else []), \
         patch.object(spoolman_api, "get_spool", side_effect=_spool), \
         patch.object(spoolman_api, "get_spools_at_location_detailed", return_value=[]), \
         patch.object(logic, "perform_smart_move", return_value={"status": "success"}) as move, \
         patch.object(state, "add_log_entry"):
        r = client.post("/api/quickswap/return", json={"toolhead": "CORE1"})

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["action"] == "return_done"
    assert move.call_count == 1
    assert len(loads) == 1, f"locations.json was read {len(loads)} times"


def test_prefix_fan_out_still_works_when_no_printer_row_exists(client):
    """Legacy fallback, PASSES on the old route too: no Printer row for XL (a
    printer_map with no row behind it), so the "XL-" prefix still fans out."""
    xl = _printer_row("XL", "XL", ["XL-1", "XL-2"])
    h = _Harness([xl], loaded={"XL-2": 88}, extra_rows=[_box("LR-MDB-2", {"1": "XL-2"})])
    h.locs = [r for r in h.locs if r.get("Type") != "Printer"]

    r = h.post(client, "XL")

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["toolhead"] == "XL-2"
    assert h.probed == ["XL-1", "XL-2"]
