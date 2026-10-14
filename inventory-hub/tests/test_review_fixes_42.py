"""Group 42 adversarial review (2026-10-14): one pin per confirmed backend finding,
each proven red on the branch before its fix.

  lifecycle-1     a PolyDryer followed a spool from a head it was never attached
                  to, and Undo re-attached a box the move had not released;
  engine-guards-1 the single-slot auto-slot put a second spool in slot 1 beside the
                  box's own deployed spool, and Quick-Swap then moved a different
                  spool than its card showed;
  lifecycle-3     Return's "a free slot instead" was false for a single-slot box,
                  and the engine unseated the spool holding slot 1 anyway;
  lifecycle-4     a print deduct that emptied a spool and timed out after it landed
                  left the spool's PolyDryer attached to the empty head;
  engine-guards-4 Undo refused to put a spool back on a multi-head Printer row;
  data-safety-3   Return's fallback took a PolyDryer's lifecycle binding as a feed;
  data-safety-4   auto-unarchive called a Spoolman-native place that still holds
                  spools "gone";
  data-safety-7   a wizard or /api/spool/update location edit off a head released
                  no box;
  frontend-3      a location scan answered a Spoolman blip as "empty";
  frontend-6      Unbind detached a box from whatever head it named by then.

The real engine, update_spool and binding helpers run against move_engine_harness's
fakes, WeightWireSpoolman's wire and a live locations.json store.
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
from test_one_spool_per_toolhead_42_3 import _archived, _refill, _wire  # noqa: E402

XL, INDX = "🦝 XL", "🦝 Core One INDX"
PRINTER_MAP = {
    "XL-2": {"printer_name": XL, "position": 1},
    "XL-4": {"printer_name": XL, "position": 3},
    "RCOI-1": {"printer_name": INDX, "position": 0},
    "RCOI-2": {"printer_name": INDX, "position": 1},
    "RCOI-3": {"printer_name": INDX, "position": 2},
}
BASE = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-2", "position": 1}, {"location_id": "XL-4", "position": 3}]},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-4", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "RCOI", "Type": "Printer", "Max Spools": "0", "parent_id": "CR",
     "toolheads": [{"location_id": f"RCOI-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"RCOI-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "RCOI"}
      for n in (1, 2, 3)],
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {}}},
]


def _box(box, head=None):
    return {"LocationID": box, "Type": "Dryer Box", "Max Spools": "1", "parent_id": "PM",
            "extra": {"slot_targets": {"1": head} if head else {}}}


def _trail(box, slot="1"):
    return {"physical_source": box, "physical_source_slot": slot}


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


def _go(sm, store, call=None, **kw):
    return run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP, call=call, **kw)


def _undo(sm, store):
    record = state.UNDO_STACK[-1]
    return _go(sm, store, call=lambda: logic.perform_undo(expected_id=record["id"]))


# --- lifecycle-1: a box follows (and comes back) only from its own spool's head ---

def _stale_trail(bound_to="RCOI-3"):
    """PM-DB-4 runs its own #60 on RCOI-3. #61 on RCOI-1 still names PM-DB-4 as its
    home: the 13.6 reverse-binding wrote such trails before 42.1 step 5."""
    store = LocationsStore(BASE + [_box("PM-DB-4", bound_to)])
    sm = FakeSpoolman({
        60: {"location": "RCOI-3", "extra": _trail("PM-DB-4")},
        61: {"location": "RCOI-1", "extra": _trail("PM-DB-4", "")},
    })
    return store, sm


def test_a_box_follows_only_from_the_head_it_is_attached_to(logs):
    store, sm = _stale_trail()
    res = _go(sm, store, target="RCOI-2", raw_spools=[61])
    assert logic.smart_move_failure(res, 61) == "", res
    assert store.bound("PM-DB-4") == "RCOI-3", "PM-DB-4 was taken off its own spool's head"
    assert (sm.spools[61]["extra"].get("physical_source") or "") == "", "the stale trail survived"
    assert not any("follows" in m for m, _ in logs), logs


def test_undo_never_attaches_a_box_over_another_heads_binding(logs):
    store, sm = _stale_trail()
    assert logic.smart_move_failure(_go(sm, store, target="CR-CT-2-R1", raw_spools=[61]), 61) == ""
    assert store.bound("PM-DB-4") == "RCOI-3"
    assert _undo(sm, store)["success"] is True
    assert sm.spools[61]["location"] == "RCOI-1"
    assert store.bound("PM-DB-4") == "RCOI-3", "Undo took PM-DB-4 off its own spool's head"


def test_undo_never_creates_a_binding_the_move_did_not_release(logs):
    store, sm = _stale_trail(bound_to=None)
    del sm.spools[60]
    _go(sm, store, target="CR-CT-2-R1", raw_spools=[61])
    assert _undo(sm, store)["success"] is True
    assert sm.spools[61]["location"] == "RCOI-1" and store.bound("PM-DB-4") == ""


def test_undoing_a_follow_takes_the_box_back_to_the_first_head(logs):
    """Control (passes before the fix too): #50 went XL-2 -> XL-4 and PM-DB-2
    followed; Undo brings both back."""
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": _trail("PM-DB-2")}})
    assert logic.smart_move_failure(_go(sm, store, target="XL-4", raw_spools=[50]), 50) == ""
    assert store.bound("PM-DB-2") == "XL-4"
    assert _undo(sm, store)["success"] is True
    assert sm.spools[50]["location"] == "XL-2" and store.bound("PM-DB-2") == "XL-2"


def test_undoing_a_smart_load_brings_the_unloaded_spools_box_back(logs):
    """Control: loading #77 onto XL-2 sent PM-DB-2's own #50 home and released
    PM-DB-2; Undo puts #50 back on XL-2 and re-attaches PM-DB-2."""
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": _trail("PM-DB-2")},
                       77: {"location": "CR-CT-2-R1", "extra": {}}})
    assert logic.smart_move_failure(_go(sm, store, target="XL-2", raw_spools=[77]), 77) == ""
    assert sm.spools[50]["location"] == "PM-DB-2" and store.bound("PM-DB-2") == ""
    assert _undo(sm, store)["success"] is True
    assert sm.direct_at("XL-2") == [50] and store.bound("PM-DB-2") == "XL-2"


# --- engine-guards-1: one spool per slot of a single-slot box -----------------------

def test_a_spool_put_in_a_polydryer_whose_own_spool_is_deployed_stays_unslotted(logs):
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": _trail("PM-DB-2")},
                       77: {"location": "CR-CT-2-R1", "extra": {}}})
    assert logic.smart_move_failure(_go(sm, store, target="PM-DB-2", raw_spools=[77]), 77) == ""
    assert sm.spools[77]["location"] == "PM-DB-2"
    assert sm.spools[77]["extra"]["container_slot"] == "", "#77 took slot 1 from the deployed #50"
    assert _go(sm, store, call=lambda: logic.find_spool_in_slot("PM-DB-2", "1")) == 50


def test_an_empty_polydryer_still_puts_its_spool_in_slot_1(logs):
    """Control: 42.2's rule stands when nothing else claims slot 1."""
    store = LocationsStore(BASE + [_box("PM-DB-2")])
    sm = FakeSpoolman({77: {"location": "CR-CT-2-R1", "extra": {}}})
    assert logic.smart_move_failure(_go(sm, store, target="PM-DB-2", raw_spools=[77]), 77) == ""
    assert sm.spools[77]["extra"]["container_slot"] == "1"


def test_quickswap_refuses_a_slot_two_spools_claim(client, logs):
    """Data written before the fix: #50 deployed from PM-DB-2 slot 1, and #77 in
    PM-DB-2 slot 1. The grid showed one card and the server moved the other."""
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": _trail("PM-DB-2")},
                       77: {"location": "PM-DB-2", "extra": {"container_slot": "1"}}})
    assert _go(sm, store, call=lambda: logic.find_spool_in_slot("PM-DB-2", "1")) is None
    resp = _go(sm, store, call=lambda: client.post(
        "/api/quickswap", json={"toolhead": "XL-2", "box": "PM-DB-2", "slot": "1"}))
    body = resp.get_json()
    assert resp.status_code == 409 and body["action"] == "quickswap_ambiguous_slot", body
    assert body["error"] == ("PM-DB-2 slot 1 is claimed by #50 and #77 — open PM-DB-2 and "
                             "move one of them first"), body
    assert sm.writes == []


# --- lifecycle-3: Return never unseats the spool holding a PolyDryer's slot ---------

@pytest.mark.parametrize("trail_slot", ["1", ""], ids=["trail-slot-1", "legacy-blank-trail"])
def test_return_into_a_taken_polydryer_leaves_its_spool_seated(client, logs, trail_slot):
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    sm = FakeSpoolman({18: {"location": "PM-DB-2", "extra": {"container_slot": "1"}},
                       50: {"location": "XL-2", "extra": _trail("PM-DB-2", trail_slot)}})
    body = _go(sm, store, call=lambda: client.post("/api/quickswap/return",
                                                   json={"toolhead": "XL-2"})).get_json()
    assert body.get("action") == "return_done", body
    assert sm.spools[50]["location"] == "PM-DB-2" and sm.spools[50]["extra"]["container_slot"] == ""
    assert sm.spools[18]["extra"]["container_slot"] == "1", "Return unseated #18"
    assert body["slot"] is None, body
    if trail_slot:
        assert ("⚠️ Return: PM-DB-2 slot 1 already holds #18 — #50 goes back into PM-DB-2 unslotted",
                ("WARNING", "ffaa00")) in logs, logs


# --- lifecycle-4: the archive edge releases the box even when the PATCH timed out ----

def _weighed(**kw):
    return WeightWireSpoolman({50: {
        "location": "XL-2", "initial_weight": 1000, "used_weight": 900, "archived": False,
        "filament": {"weight": 1000}, "extra": _trail("PM-DB-2")}}, **kw)


def _wire_ctx(sm, store):
    return [
        patch.object(spoolman_api.requests, "get", side_effect=sm._get),
        patch.object(spoolman_api.requests, "patch", side_effect=sm._patch),
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(logic.locations_db, "get_active_printer_map", return_value=PRINTER_MAP),
        patch.object(logic.locations_db, "load_locations_list", side_effect=store.load),
        patch.object(logic.locations_db, "save_locations_list", side_effect=store.save),
    ]


def test_a_deduct_that_lands_but_times_out_still_releases_the_box(logs):
    """update_spool's timeout is a READ timeout: the deduct's re-read counts the
    charge as landed, so its PolyDryer must let go too."""
    sm, store = _weighed(patch_fails={50}), LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    with ExitStack() as st:
        for p in _wire_ctx(sm, store):
            st.enter_context(p)
        assert spoolman_api.update_spool(50, {"used_weight": 1000}) is None
    assert sm.spools[50]["archived"] is True and sm.spools[50]["location"] == ""
    assert store.bound("PM-DB-2") == ""
    assert ("🔓 PM-DB-2 detached from XL-2 — its spool #50 was archived empty", ("INFO",)) in logs, logs


def test_a_deduct_that_never_landed_releases_nothing(logs):
    sm, store = _weighed(patch_lost={50}), LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    with ExitStack() as st:
        for p in _wire_ctx(sm, store):
            st.enter_context(p)
        assert spoolman_api.update_spool(50, {"used_weight": 1000}) is None
    assert sm.spools[50]["location"] == "XL-2"
    assert store.bound("PM-DB-2") == "XL-2" and store.saves == []


# --- engine-guards-4: Undo and a multi-head Printer row ------------------------------

def test_undo_puts_a_spool_back_on_a_multi_head_printer_row(logs):
    """XL owns XL-2 and XL-4, so the engine lets several spools sit on XL itself
    (a LOC:XL scan). Undo refused, calling XL a one-spool head."""
    store = LocationsStore(BASE)
    sm = FakeSpoolman({1: {"location": "XL", "extra": {}}, 2: {"location": "XL", "extra": {}}})
    assert logic.smart_move_failure(_go(sm, store, target="CR-CT-2-R1", raw_spools=[1]), 1) == ""
    res = _undo(sm, store)
    assert res["success"] is True, res
    assert sm.direct_at("XL") == [1, 2]


def test_undo_still_refuses_a_one_slot_printer_that_holds_another_spool(logs):
    """Control: a Printer row that is its own (only) head holds one spool."""
    core1 = {"LocationID": "CORE1", "Type": "Printer", "Max Spools": "1",
             "toolheads": [{"location_id": "CORE1", "position": 0}]}
    store = LocationsStore(BASE + [core1])
    sm = FakeSpoolman({77: {"location": "CORE1", "extra": {}}, 42: {"location": "CR", "extra": {}}})
    _go(sm, store, target="CR-CT-2-R1", raw_spools=[77])
    sm.spools[42]["location"] = "CORE1"
    res = _undo(sm, store)
    assert res["success"] is False and "#77 (it holds #42)" in res["msg"], res


# --- data-safety-3: Return's fallback skips a PolyDryer's lifecycle binding -----------

def test_return_never_falls_back_to_a_polydryer_binding(client, logs):
    """A stale attachment is not a feed: #61's trail names the cart it came from,
    so Return has no box slot to send it to (step 5 keeps 13.6 out the same way)."""
    store = LocationsStore(BASE + [_box("PM-DB-4", "RCOI-1")])
    sm = FakeSpoolman({61: {"location": "RCOI-1", "extra": {"physical_source": "CR-CT-2-R1"}}})
    resp = _go(sm, store, call=lambda: client.post("/api/quickswap/return", json={"toolhead": "RCOI-1"}))
    body = resp.get_json()
    assert resp.status_code == 404 and body["action"] == "return_no_binding", body
    assert sm.spools[61]["location"] == "RCOI-1" and sm.writes == []


def test_the_slot_list_flags_single_slot_boxes(client):
    """The Return preview reads this list; it needs the flag to skip the same
    bindings the server does."""
    store = LocationsStore(BASE + [_box("PM-DB-4", "RCOI-1")])
    with patch.object(logic.locations_db, "load_locations_list", side_effect=store.load):
        slots = client.get("/api/dryer_boxes/slots").get_json()["slots"]
    assert [s for s in slots if s["box"] == "PM-DB-4"] == [
        {"box": "PM-DB-4", "box_name": "PM-DB-4", "slot": "1", "target": "RCOI-1", "single_slot": True}]
    assert all("single_slot" not in s for s in slots if s["box"] == "LR-MDB-1"), slots


# --- data-safety-4: a Spoolman-native place that still holds spools is not "gone" -----

def test_a_spoolman_native_place_with_spools_is_restored(logs):
    sm = WeightWireSpoolman(_archived("SHELF3", sid=99))
    ctx, reads = _wire(sm, residents={"SHELF3": [100]})
    out = _refill(sm, ctx, sid=99)
    assert out and not out.get("fcc_warning"), out
    assert sm.spools[99]["archived"] is False and sm.spools[99]["location"] == "SHELF3"
    assert reads == ["SHELF3"]


def test_a_native_place_fcc_cant_read_counts_as_taken(logs):
    sm = WeightWireSpoolman(_archived("SHELF3", sid=99))
    ctx, _ = _wire(sm, read_fails=True)
    out = _refill(sm, ctx, sid=99)
    assert "FCC couldn't read SHELF3 from Spoolman, so it is Unassigned" in out.get("fcc_warning", ""), out
    assert sm.spools[99]["location"] == ""


# --- data-safety-7: a direct location edit off a head releases its box ---------------

@pytest.mark.parametrize("door", ["spool-update", "wizard"])
def test_editing_a_spool_off_its_head_releases_its_box(client, logs, door):
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": _trail("PM-DB-2")}})
    if door == "spool-update":
        call = lambda: client.post("/api/spool/update",  # noqa: E731
                                   json={"id": 50, "updates": {"location": "CR-CT-2-R1"}})
    else:
        call = lambda: client.post("/api/edit_spool_wizard",  # noqa: E731
                                   json={"spool_id": 50, "spool_data": {"location": "CR-CT-2-R1"}})
    body = _go(sm, store, call=call).get_json()
    assert sm.spools[50]["location"] == "CR-CT-2-R1", body
    assert store.bound("PM-DB-2") == ""
    assert ("🔓 PM-DB-2 detached from XL-2 — its spool #50 left the head", ("INFO",)) in logs, logs


def test_an_edit_that_keeps_the_spool_on_its_head_releases_nothing(client, logs):
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": _trail("PM-DB-2")}})
    _go(sm, store, call=lambda: client.post("/api/spool/update",
                                            json={"id": 50, "updates": {"comment": "hi"}}))
    assert store.bound("PM-DB-2") == "XL-2" and store.saves == []


# --- frontend-3: a location scan tells "couldn't read" from "empty" -------------------

def test_a_location_scan_says_when_it_could_not_read_the_location(client, logs):
    with patch.object(spoolman_api, "get_spools_at_location_detailed", return_value=[]), \
         patch.object(spoolman_api, "get_spools_at_location_detailed_strict",
                      side_effect=spoolman_api.requests.ConnectionError("unreachable (test)")):
        body = client.post("/api/identify_scan", json={"text": "LOC:RCOI-1", "source": "barcode"}).get_json()
    assert body["type"] == "location" and body["contents"] == [], body
    assert body.get("contents_error", "").startswith("couldn't read RCOI-1 from Spoolman"), body
    assert any(m.startswith("⚠️ 🔎 RCOI-1: couldn't read RCOI-1 from Spoolman") and a[0] == "WARNING"
               for m, a in logs), logs


# --- frontend-6: Unbind only detaches the box from the head the button showed ---------

def test_unbind_refuses_when_the_box_is_attached_to_another_head_now(client, logs):
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-4")])
    resp = _go(FakeSpoolman({}), store, call=lambda: client.put(
        "/api/dryer_box/PM-DB-2/bindings/1", json={"target": None, "expected_target": "XL-2"}))
    body = resp.get_json()
    assert resp.status_code == 409 and body["error"] == "binding_moved", body
    assert body["msg"] == ("PM-DB-2 is attached to XL-4 now, not XL-2, so nothing was changed. "
                           "Reopen XL-2 to see where it is."), body
    assert store.bound("PM-DB-2") == "XL-4" and store.saves == []


def test_unbind_still_detaches_from_the_head_it_showed(client, logs):
    store = LocationsStore(BASE + [_box("PM-DB-2", "XL-2")])
    resp = _go(FakeSpoolman({}), store, call=lambda: client.put(
        "/api/dryer_box/PM-DB-2/bindings/1", json={"target": None, "expected_target": "XL-2"}))
    assert resp.status_code == 200, resp.get_json()
    assert store.bound("PM-DB-2") == ""
