"""Group 42.3 — one loaded spool per toolhead: the engine guards.

Derek's principle (2026-09-13): "a toolhead should never have two spools
attached to it directly… If looking at the toolhead, I should only ever see one
in there." Smart Load enforced it for a single move; three other writers could
still stack a second spool on a head:

  42.3a  /api/smart_move (or any caller) with several spools, or a location that
         expands to several, wrote every one of them onto the head;
  42.3b  Undo put a moved spool back on its head with no occupancy check, so an
         undo after a writer that records no undo doubled the head (I5-10). It
         also never touched a single-slot box's binding;
  42.3c  a used-up spool weighed back above 0 g was auto-unarchived back onto
         the toolhead it was printed empty on, whoever is loaded there now (I5-9).
         Derek, 2026-10-13: then it goes to Unassigned with a 7 s warning.

The real engine, real update_spool and the real binding helpers run against
move_engine_harness's fakes, WeightWireSpoolman's wire and a live
locations.json store.
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, run_move  # noqa: E402

XL = "🦝 XL"
PRINTER_MAP = {
    "XL-1": {"printer_name": XL, "position": 0},
    "XL-2": {"printer_name": XL, "position": 1},
    "RCOI-1": {"printer_name": "🦝 Core One INDX", "position": 0},
}
LOCATIONS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1}]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "RCOI-1", "Type": "Tool Head", "Max Spools": "1"},
    {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2", "parent_id": "LR"},
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "PM",
     "extra": {"slot_targets": {}}},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [])
    monkeypatch.setattr(state, "BULK_MOVE_SESSION", {"active": False})
    monkeypatch.setattr(state, "AUDIT_SESSION", {"active": False})


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _go(sm, store=None, call=None, **kw):
    if store is None:
        return run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map=PRINTER_MAP, call=call, **kw)
    return run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP, call=call, **kw)


# --- 42.3a: several spools onto one head -------------------------------------

def test_smart_move_refuses_two_spools_onto_one_head(client, logs):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}, 43: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _go(sm, call=lambda: client.post("/api/smart_move", json={"location": "XL-1", "spools": [42, 43]})).get_json()
    assert body["status"] == "error" and body["blocked_reason"] == "single_occupancy", body
    assert body["msg"] == "XL-1 holds one spool — move them one at a time (got 2)", body
    assert set(body["failures"]) == {"42", "43"}
    assert sm.writes == []
    assert ("⚠️ Not moved: XL-1 holds one spool — move them one at a time (got 2).", ("WARNING", "ffaa00")) in logs


def test_a_location_that_expands_to_two_spools_is_refused_too(logs):
    sm = FakeSpoolman({7: {"location": "LR-MDB-2", "extra": {"container_slot": "1"}},
                       8: {"location": "LR-MDB-2", "extra": {"container_slot": "2"}}})
    res = _go(sm, target="RCOI-1", raw_spools=["LR-MDB-2"])
    assert res["blocked_reason"] == "single_occupancy" and "got 2" in res["msg"], res
    assert sm.writes == []


def test_one_spool_and_the_same_spool_twice_still_load(logs):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res = _go(sm, target="XL-1", raw_spools=[42, 42])
    assert logic.smart_move_failure(res, 42) == "", res
    assert sm.direct_at("XL-1") == [42]


# --- 42.3b: Undo never doubles a head, and carries the box lifecycle --------------

def test_undo_wont_put_a_spool_back_on_a_head_something_else_was_loaded_on(logs):
    """I5-10: move #77 off XL-1, let a writer that records no undo (the wizard,
    an auto-unarchive) put #42 there, then undo: XL-1 held [42, 77]."""
    store = LocationsStore(LOCATIONS)
    sm = FakeSpoolman({77: {"location": "XL-1", "extra": {}}, 42: {"location": "CR", "extra": {}}})
    assert logic.smart_move_failure(_go(sm, store, target="CR-CT-2-R1", raw_spools=[77]), 77) == ""
    record = state.UNDO_STACK[-1]
    sm.spools[42]["location"] = "XL-1"   # a writer that pushed no undo record
    res = _go(sm, store, call=lambda: logic.perform_undo(expected_id=record["id"]))
    assert res["success"] is False and "#77 (it holds #42)" in res["msg"], res
    assert sm.direct_at("XL-1") == [42] and sm.spools[77]["location"] == "CR-CT-2-R1"
    assert any("Undo: not putting Spool #77 back on XL-1 — it holds #42" in m and a[0] == "ERROR"
               for m, a in logs), logs


def test_undo_wont_put_a_spool_back_on_a_head_it_cant_read(logs):
    store = LocationsStore(LOCATIONS)
    sm = FakeSpoolman({77: {"location": "XL-1", "extra": {}}})
    _go(sm, store, target="CR-CT-2-R1", raw_spools=[77])
    record = state.UNDO_STACK[-1]
    sm.list_reads_fail = True
    res = _go(sm, store, call=lambda: logic.perform_undo(expected_id=record["id"]))
    assert res["success"] is False and "could not be read from Spoolman" in res["msg"], res
    assert sm.spools[77]["location"] == "CR-CT-2-R1"


def test_undoing_a_polydryer_deploy_releases_the_box(logs):
    """#50 from PM-DB-2 onto XL-2 attached PM-DB-2; undoing it puts #50 back in
    PM-DB-2, and PM-DB-2 lets go of XL-2 (its own spool left the head)."""
    store = LocationsStore(LOCATIONS)
    sm = FakeSpoolman({50: {"location": "PM-DB-2", "extra": {"container_slot": "1"}}})
    assert logic.smart_move_failure(_go(sm, store, target="XL-2", raw_spools=[50]), 50) == ""
    assert store.bound("PM-DB-2") == "XL-2", "precondition: the deploy attached PM-DB-2"
    record = state.UNDO_STACK[-1]
    res = _go(sm, store, call=lambda: logic.perform_undo(expected_id=record["id"]))
    assert res["success"] is True, res
    assert sm.spools[50]["location"] == "PM-DB-2" and store.bound("PM-DB-2") == ""


def test_undoing_a_move_off_the_head_brings_its_box_back(logs):
    """#50 (from PM-DB-2) moved XL-2 → a cart row released PM-DB-2; undoing it
    puts #50 back on XL-2, and PM-DB-2 attaches to XL-2 again."""
    store = LocationsStore([r if r["LocationID"] != "PM-DB-2" else
                            {**r, "extra": {"slot_targets": {"1": "XL-2"}}} for r in LOCATIONS])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": {"physical_source": "PM-DB-2",
                                                           "physical_source_slot": "1"}}})
    assert logic.smart_move_failure(_go(sm, store, target="CR-CT-2-R1", raw_spools=[50]), 50) == ""
    assert store.bound("PM-DB-2") == "", "precondition: the move released PM-DB-2"
    record = state.UNDO_STACK[-1]
    res = _go(sm, store, call=lambda: logic.perform_undo(expected_id=record["id"]))
    assert res["success"] is True, res
    assert sm.spools[50]["location"] == "XL-2" and store.bound("PM-DB-2") == "XL-2"
    assert sm.spools[50]["extra"]["physical_source"] == "PM-DB-2"


# --- 42.3c: auto-unarchive never lands on an occupied head ---------------------------

def _archived(note, sid=77, **extra):
    return {sid: {"location": "", "archived": True, "initial_weight": 1000, "used_weight": 1000,
                  "filament": {"weight": 1000},
                  "extra": {"fcc_pre_archive_location": note, **extra}}}


def _wire(sm, residents=None, read_fails=False):
    """The real update_spool over the wire; the strict location read answers from
    `residents` ({loc: [ids loaded there]})."""
    reads = []

    def strict(loc):
        reads.append(loc)
        if read_fails:
            raise spoolman_api.requests.ConnectionError("Spoolman unreachable (test)")
        return [{"id": i, "location": loc, "is_ghost": False} for i in (residents or {}).get(str(loc).upper(), [])]
    ctx = [
        patch.object(spoolman_api.requests, "get", side_effect=sm._get),
        patch.object(spoolman_api.requests, "patch", side_effect=sm._patch),
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(spoolman_api.locations_db, "get_active_printer_map", return_value=PRINTER_MAP),
        patch.object(spoolman_api.locations_db, "load_locations_list", return_value=LOCATIONS),
        patch.object(spoolman_api, "get_spools_at_location_detailed_strict", side_effect=strict),
    ]
    return ctx, reads


def _refill(sm, ctx, sid=77, used=960):
    with ExitStack() as st:
        for p in ctx:
            st.enter_context(p)
        return spoolman_api.update_spool(sid, {"used_weight": used})


def test_an_empty_head_gets_its_spool_back_as_today(logs):
    sm = WeightWireSpoolman(_archived("XL-1"))
    ctx, reads = _wire(sm)
    out = _refill(sm, ctx)
    assert out and not out.get("fcc_warning"), out
    assert sm.spools[77]["archived"] is False and sm.spools[77]["location"] == "XL-1"
    assert sm.spools[77]["extra"]["fcc_pre_archive_location"] == "", "the note is used up (call 22)"
    assert reads == ["XL-1"]


def test_a_head_that_holds_another_spool_now_sends_it_to_unassigned(logs):
    """Derek, 2026-10-13 (A): Unassigned, with a warning naming the spool there."""
    sm = WeightWireSpoolman(_archived("RCOI-1", sid=99))
    ctx, _ = _wire(sm, residents={"RCOI-1": [299]})
    out = _refill(sm, ctx, sid=99)
    warning = "#99 is back in stock (40 g), but RCOI-1 now holds #299, so it is Unassigned — scan it to where you put it."
    assert out.get("fcc_warning") == warning, out
    assert sm.spools[99]["archived"] is False and sm.spools[99]["location"] == ""
    assert (f"⚠️ {warning}", ("WARNING", "ffaa00")) in logs, logs


def test_a_head_fcc_cant_read_counts_as_taken(logs):
    sm = WeightWireSpoolman(_archived("XL-1"))
    ctx, _ = _wire(sm, read_fails=True)
    out = _refill(sm, ctx)
    assert "FCC couldn't read XL-1 from Spoolman, so it is Unassigned" in out.get("fcc_warning", ""), out
    assert sm.spools[77]["location"] == ""


def test_a_place_that_no_longer_exists_counts_as_taken(logs):
    """Dev's #131 remembers CORE1, which no longer exists."""
    sm = WeightWireSpoolman(_archived("CORE1"))
    ctx, reads = _wire(sm)
    out = _refill(sm, ctx)
    assert "CORE1 no longer exists, so it is Unassigned" in out.get("fcc_warning", ""), out
    assert sm.spools[77]["location"] == "" and reads == []


def test_a_shelf_is_restored_with_no_read(logs):
    sm = WeightWireSpoolman(_archived("CR-CT-2-R1"))
    ctx, reads = _wire(sm)
    out = _refill(sm, ctx)
    assert not out.get("fcc_warning") and sm.spools[77]["location"] == "CR-CT-2-R1"
    assert reads == []


def test_a_deduct_to_an_archived_spool_still_unarchives_nothing(logs):
    """Group 43's constraint: a charge sends archived: True, which is not a
    refill (the early return stays)."""
    sm = WeightWireSpoolman(_archived("XL-1"))
    ctx, reads = _wire(sm, residents={"XL-1": [42]})
    with ExitStack() as st:
        for p in ctx:
            st.enter_context(p)
        out = spoolman_api.update_spool(77, {"used_weight": 990, "archived": True})
    assert out and not out.get("fcc_warning")
    assert sm.spools[77]["archived"] is True and sm.spools[77]["location"] == "" and reads == []


def test_spool_update_hands_the_warning_to_the_weigh_screen(client, logs):
    sm = WeightWireSpoolman(_archived("XL-1"))
    ctx, _ = _wire(sm, residents={"XL-1": [42]})
    with ExitStack() as st:
        for p in ctx:
            st.enter_context(p)
        body = client.post("/api/spool/update", json={"id": 77, "updates": {"used_weight": 960}}).get_json()
    assert body["status"] == "success", body
    assert body["warning"].startswith("#77 is back in stock (40 g), but XL-1 now holds #42"), body
