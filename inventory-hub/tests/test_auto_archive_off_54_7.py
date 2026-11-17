"""Group 54.7 (server half) — "Auto-Archive 0g" off means off (Derek, 2026-11-07, (a)).

The weigh-out window's "Auto-Archive 0g" switch and the Quick-Weigh's "Auto Archive
& Eject if Empty (0g)" only decided whether the page itself sent `archived: true`
and unassigned the spool afterwards. The server's archive edge
(`spoolman_api._auto_archive_on_empty`, run by `update_spool`) archived every weight
write that left nothing whatever the switch said: with the switch off, a spool
weighed to 0 g was still archived, Unassigned, its trail blanked and a pre-archive
note planted, and its single-slot box let go.

Now `update_spool(sid, data, archive_on_empty=True)` takes the edge as a keyword
(today's default), and `/api/spool/update` reads an optional top-level
`auto_archive` beside `id` and `updates`: only JSON `false` passes
`archive_on_empty=False`, and only then is the keyword passed at all, so a
two-argument stand-in for update_spool still serves every other request. With the
edge off, nothing is archived or moved; the refill edge still runs, so a refill
still un-archives, and an archived spool weighed to 0 g stays archived where it is.

Everything runs the REAL update_spool (and the REAL route, its box release and the
single-slot box helpers) over tests/spoolman_extra_fake.SpoolmanHTTPFake and an
in-memory locations.json, or over tests/move_engine_harness
([[mocked engine hides chain bugs]]).

Base proof (502f06d, Group 54.6 in, 54.7 not): every test marked RED fails there;
the controls pass.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402  (before any patch: its import runs the startup migrations)
import locations_db  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, LocationsStore, WeighedWireSpoolman, run_move  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake  # noqa: E402

TRAIL = ("container_slot", "physical_source", "physical_source_slot")
SPOOL_FIELDS = [
    *[{"key": k, "field_type": "text", "name": k} for k in (
        "container_slot", "physical_source", "physical_source_slot",
        "fcc_pre_archive_location", "fcc_pre_box_location", "fcc_pre_audit_location")],
    {"key": "needs_label_print", "field_type": "boolean", "name": "Needs Label Print"},
]
PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2)],
    {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR", "extra": {}},
    {"LocationID": "CR-SHELF", "Type": "Shelf", "Max Spools": "12", "parent_id": "LR"},
]


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


def _logs(fragment):
    return [e for e in state.RECENT_LOGS if fragment in str(e.get("message", e))]


@pytest.fixture
def sm(monkeypatch):
    """A Spoolman 0.27 over HTTP and an in-memory locations.json (`sm.store`):
    spoolman_api's HTTP seam on the fake, locations_db's file reads and writes on
    the store, and the active printer map fixed, so the archive edge's box release,
    the route's release after a direct write and the single-slot helpers run for
    real and nothing reads or writes the real files."""
    fake = SpoolmanHTTPFake(version="0.27.0", fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    fake.store = LocationsStore(ROWS)
    monkeypatch.setattr(spoolman_api.config_loader, "get_api_urls", lambda: ("http://sm.test", "http://fb"))
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
    monkeypatch.setattr(locations_db, "load_locations_list", fake.store.load)
    monkeypatch.setattr(locations_db, "save_locations_list", fake.store.save)
    monkeypatch.setattr(locations_db, "get_active_printer_map", lambda *a, **k: copy.deepcopy(PRINTER_MAP))
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(spoolman_api, name, {}).clear()
    yield fake
    for name in ("_FIELD_SCHEMA_CACHE", "_SPOOLMAN_VERSION_CACHE"):
        getattr(spoolman_api, name, {}).clear()


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _loaded_from_its_box(sm):
    """#57 on XL-1, loaded from the single-slot box PM-DB-1 (bound to XL-1), 700 of
    1000 g used."""
    sm.add("spool", 57, {"physical_source": '"PM-DB-1"', "physical_source_slot": '"1"',
                         "needs_label_print": "false"},
           location="XL-1", initial_weight=1000.0, used_weight=700.0, archived=False)


def _archived_by_hand_empty(sm):
    """#57 archived by hand on CR-SHELF, all 1000 g used."""
    sm.add("spool", 57, {}, location="CR-SHELF", initial_weight=1000.0, used_weight=1000.0, archived=True)


def _archived_empty_with_a_note(sm):
    """#57 archived empty off CR-SHELF by the edge: Unassigned, its note saying where."""
    sm.add("spool", 57, {"fcc_pre_archive_location": '"CR-SHELF"'},
           location="", initial_weight=1000.0, used_weight=1000.0, archived=True)


def _assert_kept_on_its_head(sm):
    rec = sm.records["spool"][57]
    assert rec["archived"] is False and rec["location"] == "XL-1", rec
    assert rec["extra"]["physical_source"] == '"PM-DB-1"' and rec["extra"]["physical_source_slot"] == '"1"', rec
    assert "fcc_pre_archive_location" not in rec["extra"], rec
    assert sm.store.bound("PM-DB-1") == "XL-1", sm.store.row("PM-DB-1")
    assert not _logs("Auto-archived") and not _logs("detached"), state.RECENT_LOGS


# ---- update_spool's keyword ---------------------------------------------------------------------------

@pytest.mark.parametrize("weight", [{"used_weight": 1000}, {"remaining_weight": 0}], ids=["used", "left"])
def test_update_spool_with_the_edge_off_sends_the_weight_alone(sm, weight):
    """A spool in LR-MDB-1 slot 2 weighed to 0 g with archive_on_empty=False: the
    PATCH is the weight and nothing else, so it stays in stock in its slot, with no
    note and no "Auto-archived" line. RED on 502f06d (no such keyword)."""
    sm.add("spool", 57, {"container_slot": '"2"'},
           location="LR-MDB-1", initial_weight=1000.0, used_weight=700.0, archived=False)
    out = spoolman_api.update_spool(57, dict(weight), archive_on_empty=False)
    assert out is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    (_entity, _sid, body), = sm.patches
    assert body == weight, body
    rec = sm.records["spool"][57]
    assert rec["archived"] is False and rec["location"] == "LR-MDB-1", rec
    assert rec["extra"] == {"container_slot": '"2"'}, rec
    assert not _logs("Auto-archived"), state.RECENT_LOGS


def test_update_spool_with_the_edge_off_leaves_an_archived_spool_where_it_is(sm):
    """An archived spool weighed to 0 g again: no idempotent `archived: True,
    location: ''` write (which would take it off its shelf and plant a note), only
    the weight. RED on 502f06d (no such keyword)."""
    _archived_by_hand_empty(sm)
    assert spoolman_api.update_spool(57, {"used_weight": 1000}, archive_on_empty=False) is not None
    (_entity, _sid, body), = sm.patches
    assert body == {"used_weight": 1000}, body
    rec = sm.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "CR-SHELF" and rec["extra"] == {}, rec


def test_update_spool_with_the_edge_off_still_unarchives_a_refill(sm):
    """The refill edge isn't the switch's: 400 g left on a spool archived empty
    brings it back into stock where its note says, and uses the note up. RED on
    502f06d (no such keyword)."""
    _archived_empty_with_a_note(sm)
    assert spoolman_api.update_spool(57, {"used_weight": 600}, archive_on_empty=False) is not None
    (_entity, _sid, body), = sm.patches
    assert body["archived"] is False and body["location"] == "CR-SHELF", body
    rec = sm.records["spool"][57]
    assert rec["archived"] is False and rec["location"] == "CR-SHELF", rec
    assert rec["extra"]["fcc_pre_archive_location"] == '""', rec
    assert _logs("📤 Auto-unarchived Spool #57"), state.RECENT_LOGS


# ---- /api/spool/update's `auto_archive` ---------------------------------------------------------------

def _post(client, updates, **top):
    return client.post("/api/spool/update", json={"id": 57, "updates": updates, **top}).get_json()


@pytest.mark.parametrize("weight", [{"used_weight": 1000}, {"remaining_weight": 0}], ids=["used", "left"])
def test_auto_archive_false_keeps_a_loaded_spool_weighed_to_nothing_on_its_head(sm, client, weight):
    """Derek's answer: with the switch off, #57 weighed to 0 g stays in stock where
    it is: on XL-1, its trail to PM-DB-1 kept, no note, PM-DB-1 still bound, and the
    answer says nothing was archived. RED on 502f06d: the route ignored the switch,
    so #57 was archived and Unassigned and PM-DB-1 let go. ("left" is where 54.6
    meets 54.7: the fallback row's `remaining_weight` keeps it in stock too.)"""
    _loaded_from_its_box(sm)
    res = _post(client, dict(weight), auto_archive=False)
    assert res["status"] == "success", res
    assert res["auto_archived"] is False and res["needs_empty_weight_prompt"] is False, res
    _assert_kept_on_its_head(sm)


def test_auto_archive_false_leaves_an_archived_spool_weighed_to_nothing_where_it_is(sm, client):
    """An archived spool weighed to 0 g with the switch off stays archived on
    CR-SHELF. RED on 502f06d: the idempotent write took it off the shelf and
    planted a note."""
    _archived_by_hand_empty(sm)
    res = _post(client, {"used_weight": 1000}, auto_archive=False)
    assert res["status"] == "success" and res["auto_archived"] is False, res
    rec = sm.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "CR-SHELF" and rec["extra"] == {}, rec


def test_control_auto_archive_false_still_unarchives_a_refill(sm, client):
    """Control (green on 502f06d too): a refill with the switch off un-archives."""
    _archived_empty_with_a_note(sm)
    res = _post(client, {"used_weight": 600}, auto_archive=False)
    assert res["status"] == "success" and res["auto_archived"] is False, res
    rec = sm.records["spool"][57]
    assert rec["archived"] is False and rec["location"] == "CR-SHELF", rec


@pytest.mark.parametrize("top", [{}, {"auto_archive": True}, {"auto_archive": "false"},
                                 {"auto_archive": 0}, {"auto_archive": None}, {"auto_archive": "no"}],
                         ids=["absent", "true", "text-false", "zero", "null", "text-no"])
def test_control_anything_but_json_false_archives_as_before(sm, client, top):
    """Control (green on 502f06d too): only exactly JSON false turns the edge off.
    Anything else is today's rule: archived, Unassigned with a note saying XL-1,
    its trail cleared and PM-DB-1 let go."""
    _loaded_from_its_box(sm)
    res = _post(client, {"used_weight": 1000}, **top)
    assert res["status"] == "success" and res["auto_archived"] is True, res
    rec = sm.records["spool"][57]
    assert rec["archived"] is True and rec["location"] == "", rec
    assert rec["extra"]["fcc_pre_archive_location"] == '"XL-1"', rec
    assert all(rec["extra"][k] == '""' for k in TRAIL), rec
    assert sm.store.bound("PM-DB-1") == "", sm.store.row("PM-DB-1")


# ---- the keyword goes only with false (stand-ins for update_spool) ------------------------------------

@pytest.mark.parametrize("top", [{}, {"auto_archive": True}, {"auto_archive": "false"}, {"auto_archive": None}],
                         ids=["absent", "true", "text-false", "null"])
def test_control_a_two_argument_stand_in_serves_every_request_but_false(monkeypatch, client, top):
    """Control (green on 502f06d too): many tests patch update_spool with a
    two-argument stand-in, and the route passes no keyword unless the request says
    false, so they keep working."""
    calls = []
    monkeypatch.setattr(spoolman_api, "get_spool", lambda sid: {"id": int(sid), "archived": False})
    monkeypatch.setattr(spoolman_api, "update_spool",
                        lambda sid, data: calls.append((sid, data)) or {"id": int(sid), "archived": False})
    res = _post(client, {"used_weight": 1000}, **top)
    assert res["status"] == "success", res
    assert calls == [(57, {"used_weight": 1000})], calls


def test_auto_archive_false_reaches_update_spool_as_its_keyword(monkeypatch, client):
    """RED on 502f06d: the route never passed it."""
    seen = []
    monkeypatch.setattr(spoolman_api, "get_spool", lambda sid: {"id": int(sid), "archived": False})
    monkeypatch.setattr(spoolman_api, "update_spool",
                        lambda sid, data, **kw: seen.append(kw) or {"id": int(sid), "archived": False})
    assert _post(client, {"used_weight": 1000}, auto_archive=False)["status"] == "success"
    assert seen == [{"archive_on_empty": False}], seen


def test_the_move_engine_harness_passes_the_keyword_on(client):
    """tests/move_engine_harness's stand-ins take the keyword and its
    WireSpoolman hands it to the REAL update_spool, so a route test through
    run_move sees the switch. RED on 502f06d: the route never passed it, so #57
    was archived off XL-1 and PM-DB-1 let go."""
    sm = WeighedWireSpoolman({57: {"location": "XL-1", "initial_weight": 1000, "used_weight": 700,
                                   "archived": False,
                                   "extra": {"physical_source": "PM-DB-1", "physical_source_slot": "1"}}})
    store = LocationsStore(ROWS)
    res = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP,
                   call=lambda: client.post("/api/spool/update", json={
                       "id": 57, "updates": {"used_weight": 1000}, "auto_archive": False})).get_json()
    assert res["status"] == "success" and res["auto_archived"] is False, res
    spool = sm.spools[57]
    assert spool["archived"] is False and spool["location"] == "XL-1" and spool["used_weight"] == 1000, spool
    assert spool["extra"].get("physical_source") == "PM-DB-1", spool
    assert store.bound("PM-DB-1") == "XL-1", store.row("PM-DB-1")
