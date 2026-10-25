"""Group 40.7 — the Add / Edit Spool wizard's Location goes through the move engine.

Derek, 2026-10-19 (answer 7): a Location change in the wizard behaves like Force
Location. The edit door used to diff `location` as a plain key and PATCH it straight
to Spoolman: no Smart Load, no active-print or "already fed" question, no Printer-row
refusal, and the old slot and trail stayed behind. Now:
  - edit: every other edit is saved first; the Location then goes through
    perform_smart_move (anything) or perform_force_unassign (Unassigned). A refused
    or asked move leaves the other edits saved, answers `success: false`,
    `spool_saved`, `location_moved`, `location_result` (the engine's answer) and a
    `msg` an older page can show; the stale-page rules apply as at the doors;
  - create: refused before anything is created for a Printer row that isn't a head,
    or several spools onto a one-spool place; otherwise every spool is created
    Unassigned and placed through the engine, one call each (`placements`, or, for
    a request without the key, `spool_data.location`), reported per spool;
  - /api/spool/update: a location change blanks the slot and trail the spool left,
    and a toolhead or Printer-row target is refused with nothing written.

The REAL engine runs over tests/move_engine_harness.py (a live locations store, the
probe patched below the per-move memo); nothing here mocks perform_smart_move,
perform_smart_eject or _perform_smart_move_impl.

Base proof (0b0eeb7, the tip before 40.7): 21 of 22 fail, each on what happened to
the spools: the edit PATCHed the new location straight through (CORE1 held #42 and
#99; #42 filed on XL; #42 written into LR-MDB-1 over XL-1's PolyDryer spool with no
question; an unassigned #42 kept its trail; a re-typed same place was PATCHed), the
same-slot swap never ran, the floating spool got no slot, the archive-and-move write
named the new place, every create was made at the location itself (two on CORE1,
one on XL, unslotted in boxes) with no placement report, and /api/spool/update kept
the old slot and wrote onto heads and Printer rows. Controls: the last test passes
there by design (an unchanged location, a caller's own slot), and
test_the_wizards_question_is_answered_on_the_smart_move_door fails there only
because the base edit asks nothing (KeyError: location_result); the /api/smart_move
replay it then makes is the existing door's.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, WireSpoolman, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {
    "XL-1": {"printer_name": "XL", "position": 0},
    "XL-2": {"printer_name": "XL", "position": 1},
    "XL-3": {"printer_name": "XL", "position": 2},
    # A dual-role printer (the old CORE1): its own one toolhead, offered in the
    # wizard's Location list because its Type is Printer.
    "CORE1": {"printer_name": "Core One", "position": 0},
}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR", "Name": "XL",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3)],
    {"LocationID": "CORE1", "Type": "Printer", "Max Spools": "1", "parent_id": "CR", "Name": "Core One",
     "toolheads": [{"location_id": "CORE1", "position": 0}]},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    {"LocationID": "CR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "CR",
     "extra": {"slot_targets": {}}},
    # A PolyDryer whose own spool runs on XL-1, so it is attached there (Group 20.2).
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "CR-CT-2-R2", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
]

FROM_POLYDRYER = {"physical_source": "PM-DB-2", "physical_source_slot": "1", "container_slot": ""}
# What a 40.7 page sends on every save that can move a spool (the door contract).
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


def _post(client, sm, url, body, probe=IDLE, store=None):
    store = store or LocationsStore(ROWS)
    return run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP,
                    call=lambda: client.post(url, json=body)).get_json()


def _edit(client, sm, spool_data, probe=IDLE, sid=42, **extra):
    return _post(client, sm, "/api/edit_spool_wizard",
                 dict({"spool_id": sid, "spool_data": spool_data}, **extra), probe=probe)


def _logs(needle, types=None):
    return [e for e in state.RECENT_LOGS
            if needle in str(e.get("msg", "")) and (types is None or e.get("type") in types)]


def _other_edit_landed(sm, sid=42, comment="edited"):
    return any(s == sid and d.get("comment") == comment for s, d in sm.writes)


class _Maker:
    """create_spool / create_filament for the create door: each new spool is born
    in the fake Spoolman (so the engine can read and move it), and every payload
    is kept."""

    def __init__(self, sm, first=501):
        self.sm, self.next, self.spools, self.filaments = sm, first, [], []

    def create_spool(self, data):
        self.spools.append(copy.deepcopy(data))
        sid, self.next = self.next, self.next + 1
        self.sm.spools[sid] = {"location": data.get("location", ""),
                               "extra": copy.deepcopy(data.get("extra") or {})}
        return {"id": sid}

    def create_filament(self, data):
        self.filaments.append(copy.deepcopy(data))
        return {"id": 7}


def _create(client, sm, body, probe=IDLE, store=None):
    maker = _Maker(sm)
    with patch.object(spoolman_api, "create_spool", side_effect=maker.create_spool), \
         patch.object(spoolman_api, "create_filament", side_effect=maker.create_filament):
        return _post(client, sm, "/api/create_inventory_wizard", body, probe=probe, store=store), maker


NEW_FILAMENT = {"name": "Galaxy Black", "material": "PLA", "extra": {}}


# ---- edit: the Location is a move ------------------------------------------------------

def test_an_edit_onto_a_loaded_one_spool_printer_unloads_its_spool_home(client):
    """Manual check W2: CORE1 holds #99 (from CR-CT-2-R2). Editing #42's Location to
    CORE1 sends #99 home and loads #42: CORE1 never holds two. The comment edit
    landed first, in a write that names where #42 still was."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       99: {"location": "CORE1", "extra": {"physical_source": "CR-CT-2-R2",
                                                           "physical_source_slot": "", "container_slot": ""}}})
    body = _edit(client, sm, {"location": "CORE1", "comment": "edited"}, **DOOR)
    assert sm.direct_at("CORE1") == [42], sm.spools
    assert sm.spools[99]["location"] == "CR-CT-2-R2", sm.writes
    assert sm.writes[0] == (42, {"comment": "edited", "location": "CR-CT-2-R1"}), sm.writes
    assert body["success"] is True and body["location_moved"] is True, body
    assert body["location_where"] == "CORE1" and body["location_result"]["status"] == "success", body


def test_an_edit_to_a_printer_row_is_refused_and_the_other_edits_stay_saved(client):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _edit(client, sm, {"location": "XL", "comment": "edited"}, **DOOR)
    assert sm.spools[42]["location"] == "CR-CT-2-R1", sm.writes
    assert body["success"] is False and body["spool_saved"] is True and body["location_moved"] is False, body
    assert body["location_result"]["blocked_reason"] == "printer_row", body
    assert body["msg"].startswith("Saved your other changes, but #42 was not moved to XL: XL is a printer, "
                                  "not a toolhead"), body["msg"]
    assert sm.spools[42]["location"] == "CR-CT-2-R1" and _other_edit_landed(sm), sm.writes


def test_an_edit_into_a_bound_slot_whose_head_runs_a_spool_from_elsewhere_asks_first(client):
    """Derek's D2.2 on the wizard door: XL-1 runs #99 from PM-DB-2, and slot 1 feeds
    XL-1. The edit asks the engine's head_fed question; nothing moves until the user
    answers, and the other edits are saved."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    body = _edit(client, sm, {"location": "LR-MDB-1", "comment": "edited"}, slot="1", **DOOR)
    assert sm.spools[42]["location"] == "CR-CT-2-R1" and sm.direct_at("XL-1") == [99], sm.writes
    assert _other_edit_landed(sm), sm.writes
    result = body["location_result"]
    assert body["success"] is False and body["spool_saved"] is True and body["location_moved"] is False, body
    assert result["status"] == "requires_confirm" and result["confirm_type"] == "head_fed", result
    assert result["fed_heads"][0]["confirm_key"] == "XL-1#99", result
    assert "FCC has to ask first" in body["msg"] and "stale_page" not in body, body


def test_the_wizards_question_is_answered_on_the_smart_move_door(client):
    """The browser replays the wizard's question through /api/smart_move (window.
    buildMoveReplay): "Load it instead" with the confirm key loads #42 and sends #99
    back to its PolyDryer."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    store = LocationsStore(ROWS)
    asked = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP, call=lambda: client.post(
        "/api/edit_spool_wizard", json=dict({"spool_id": 42, "spool_data": {"location": "LR-MDB-1"},
                                             "slot": "1"}, **DOOR))).get_json()["location_result"]
    replay = {"location": "LR-MDB-1", "spools": [42], "slot": "1", "origin": "wizard_edit",
              "confirmed_toolheads": [], "confirmed_fed_heads": [asked["fed_heads"][0]["confirm_key"]],
              "expected_feed": asked["feed"]}
    done = run_move(sm, probe=IDLE, store=store, printer_map=PRINTER_MAP,
                    call=lambda: client.post("/api/smart_move", json=replay)).get_json()
    assert done["status"] == "success" and done.get("auto_deployed_to") == "XL-1", done
    assert sm.direct_at("XL-1") == [42] and sm.spools[99]["location"] == "PM-DB-2", sm.spools


def test_a_page_from_before_40_7_asked_a_fed_question_is_told_to_reload(client):
    """The stale-page rule of the move doors: a request without `confirmed_fed_heads`
    can't show a head_fed question, so it hears which head runs what and to reload,
    while its other edits stay saved."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    body = _edit(client, sm, {"location": "LR-MDB-1", "comment": "edited"}, slot="1")
    assert body["success"] is False and body.get("stale_page") is True, body
    assert ("Saved your other changes, but #42 was not moved to LR-MDB-1: XL-1 is running #99, and this "
            "request can't ask before loading over it. Reload the page (Ctrl+F5)") in body["msg"], body["msg"]
    assert sm.spools[42]["location"] == "CR-CT-2-R1" and sm.direct_at("XL-1") == [99]
    assert _other_edit_landed(sm), sm.writes


def test_a_page_from_before_40_7_asked_a_printing_question_is_told_to_reload(client):
    """No head_fed here (CORE1 is empty), only the printing question, which an older
    wizard can't show either: its msg says so instead of asking again on every Save."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _edit(client, sm, {"location": "CORE1"}, probe=_probe_for({"Core One"}))
    assert body["success"] is False and body["location_result"]["status"] == "requires_confirm", body
    assert "Core One is PRINTING" in body["msg"], body["msg"]
    assert body["msg"].endswith("Reload the page (Ctrl+F5) and save again to answer it."), body["msg"]
    assert sm.spools[42]["location"] == "CR-CT-2-R1", sm.writes


def test_an_edit_to_unassigned_takes_force_locations_unassign_path(client):
    """Unassigned is Force Location's unassign (perform_force_unassign), not a move
    to "": the slot and trail it left are blanked, and the log says so."""
    sm = FakeSpoolman({42: {"location": "CORE1", "extra": {"physical_source": "CR-CT-2-R2",
                                                           "physical_source_slot": "", "container_slot": ""}}})
    body = _edit(client, sm, {"location": "", "comment": "edited"}, **DOOR)
    assert sm.spools[42]["location"] == "" and sm.spools[42]["extra"]["physical_source"] == "", sm.spools
    assert _logs("Force Unassigned #42", {"WARNING"}), state.RECENT_LOGS
    assert body["success"] is True and body["location_moved"] is True, body
    assert body["location_result"] is True and body["location_where"] == "Unassigned", body


def test_unassigning_off_a_printing_head_asks_and_a_confirm_of_that_head_unassigns(client):
    sm = FakeSpoolman({42: {"location": "CORE1", "extra": {"physical_source": "CR-CT-2-R2"}}})
    probe = _probe_for({"Core One"})
    asked = _edit(client, sm, {"location": ""}, probe=probe, **DOOR)
    assert asked["success"] is False and asked["location_result"]["status"] == "requires_confirm", asked
    assert asked["location_result"]["active_print"]["toolhead"] == "CORE1", asked
    assert sm.spools[42]["location"] == "CORE1" and sm.writes == [], sm.writes
    done = _edit(client, sm, {"location": ""}, probe=probe,
                 confirmed_toolheads=["CORE1"], confirmed_fed_heads=[])
    assert done["success"] is True and sm.spools[42]["location"] == "", done


def test_a_floating_spool_given_a_slot_of_its_own_box_is_moved_into_it(client):
    """#57 sits in LR-MDB-1 with no slot (the "5/4" state). Its Location doesn't
    change, but the picker's slot 4 (Printer Pool) is a move: it lands in slot 4."""
    sm = FakeSpoolman({57: {"location": "LR-MDB-1", "extra": {"container_slot": ""}}})
    body = _edit(client, sm, {"location": "LR-MDB-1"}, sid=57, picked_slot="4", expected_feed="", **DOOR)
    assert sm.spools[57]["extra"]["container_slot"] == "4", sm.spools
    assert body["success"] is True and body["location_moved"] is True, body
    assert body["location_where"] == "LR-MDB-1 slot 4", body


def test_the_same_slot_swaps_old_spool_reaches_the_answer(client):
    """XL-1 runs #99 from LR-MDB-1 slot 1 (its own slot). Editing #42 into slot 1
    loads #42 and swaps #99 out into the scan buffer (Derek, 2026-10-15): the answer
    names it in `to_buffer`, for the page's buffer."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       99: {"location": "XL-1", "extra": {"physical_source": "LR-MDB-1",
                                                          "physical_source_slot": "1", "container_slot": ""}}})
    body = _edit(client, sm, {"location": "LR-MDB-1"}, slot="1", **DOOR)
    assert sm.direct_at("XL-1") == [42] and [b["id"] for b in state.GLOBAL_BUFFER] == [99], sm.spools
    assert [i["id"] for i in body.get("to_buffer") or []] == [99], body
    assert body["success"] is True and body["location_where"] == "LR-MDB-1 slot 1 → XL-1", body


def test_an_edit_that_empties_the_spool_and_moves_it_leaves_the_move_to_the_engine(client):
    """update_spool's archive edge unassigns a spool emptied by a write that names
    no location. The wizard's first write names where the spool still is, so the
    archive edge leaves it, and the engine then moves it where the user asked (into
    CR-MDB-1's first slot), as a typed location always won over the edge."""
    sm = WireSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    real_get = sm.get_spool
    sm.get_spool = lambda sid: (dict(real_get(sid) or {}, initial_weight=1000, used_weight=100)
                                if real_get(sid) else None)
    body = _edit(client, sm, {"location": "CR-MDB-1", "used_weight": 1000}, **DOOR)
    first_sid, first = sm.patch_bodies[0]
    assert first_sid == 42 and first.get("location") == "CR-CT-2-R1" and first.get("archived") is True, sm.patch_bodies
    assert body["location_moved"] is True and sm.spools[42]["location"] == "CR-MDB-1", body
    assert sm.spools[42]["extra"]["container_slot"] == "1", sm.spools


def test_an_edit_that_keeps_the_location_never_runs_the_engine(client):
    """Control: an unchanged Location (typed in another case) is no move, and the
    answer is what it was before 40.7, plus `archived_now` (the page sets its
    Archived box from it; 2026-10-20 review)."""
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _edit(client, sm, {"location": "cr-ct-2-r1", "comment": "edited"}, **DOOR)
    assert body == {"success": True, "spool_id": 42, "archived_now": False}, body
    assert sm.writes == [(42, {"comment": "edited"})], sm.writes


# ---- create: refused before anything exists, else placed through the engine ------------

def test_creating_two_spools_onto_a_one_spool_printer_is_refused_before_anything_is_created(client):
    sm = FakeSpoolman({})
    body, maker = _create(client, sm, {"filament_data": NEW_FILAMENT, "quantity": 2,
                                       "spool_data": {"location": "CORE1", "extra": {}}})
    assert body["success"] is False and body["blocked_reason"] == "single_occupancy", body
    assert body["msg"].startswith("CORE1 holds one spool") and body["msg"].endswith("Nothing was created."), body
    assert maker.spools == [] and maker.filaments == [], "created something before refusing"


def test_creating_onto_a_printer_row_is_refused_before_anything_is_created(client):
    sm = FakeSpoolman({})
    body, maker = _create(client, sm, {"filament_data": NEW_FILAMENT, "quantity": 1,
                                       "spool_data": {"location": "XL", "extra": {}}})
    assert body["success"] is False and body["blocked_reason"] == "printer_row", body
    assert body["msg"].startswith("XL is a printer, not a toolhead"), body
    assert maker.spools == [] and maker.filaments == []


def test_a_placement_for_the_first_of_three_places_one_and_leaves_two_unassigned(client):
    """Claude's call 29: the picker's slot for the first new spool; the rest stay
    Unassigned for the browser's per-spool picker loop. Every spool is created
    Unassigned and placed through the engine."""
    sm = FakeSpoolman({})
    body, maker = _create(client, sm, dict({
        "filament_id": 7, "quantity": 3, "spool_data": {"location": "LR-MDB-1", "extra": {}},
        "placements": [{"location": "LR-MDB-1", "picked_slot": "4", "expected_feed": ""}, None, None],
    }, **DOOR))
    assert [p["location"] for p in maker.spools] == ["", "", ""], "created somewhere other than Unassigned"
    assert sm.spools[501]["location"] == "LR-MDB-1" and sm.spools[501]["extra"].get("container_slot") == "4"
    assert sm.spools[502]["location"] == "" and sm.spools[503]["location"] == ""
    assert body["success"] is True and body["created_spools"] == [501, 502, 503], body
    assert body["placed"] == {"501": "LR-MDB-1 slot 4"} and body["unplaced"] == [502, 503], body
    assert body["placements_ok"] is True and list(body["location_results"]) == ["501"], body


def test_a_request_without_placements_places_every_spool_through_the_engine(client):
    """A page from before 40.7: each new spool goes where spool_data says, one engine
    call each, so a multi-slot box gives each its own slot (40.0e) instead of the
    old "all of them floating in the box"."""
    sm = FakeSpoolman({})
    body, maker = _create(client, sm, {"filament_id": 7, "quantity": 2,
                                       "spool_data": {"location": "CR-MDB-1", "extra": {}}})
    assert [p["location"] for p in maker.spools] == ["", ""]
    assert [sm.spools[s]["extra"].get("container_slot") for s in (501, 502)] == ["1", "2"], sm.spools
    assert body["success"] is True and body["placed"] == {"501": "CR-MDB-1 slot 1", "502": "CR-MDB-1 slot 2"}, body


def test_a_placement_that_asks_leaves_the_new_spool_unassigned_and_says_so(client):
    """Creation is never undone by a placement: #501 exists, Unassigned, and the
    engine's question is in location_results for the page to ask; `success` stays
    true so an older page can't Create the spools again."""
    sm = FakeSpoolman({99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    body, maker = _create(client, sm, dict({
        "filament_id": 7, "quantity": 1, "spool_data": {"location": "LR-MDB-1", "extra": {}},
        "placements": [{"location": "LR-MDB-1", "slot": "1"}],
    }, **DOOR))
    assert sm.spools[501]["location"] == "" and sm.direct_at("XL-1") == [99], sm.spools
    assert body["success"] is True and body["created_spools"] == [501] and body["unplaced"] == [501], body
    assert body["placements_ok"] is False and body["placed"] == {}, body
    assert body["location_results"]["501"]["confirm_type"] == "head_fed", body
    assert body["placement_requests"]["501"] == {"location": "LR-MDB-1", "slot": "1"}, body
    assert body["warning"].startswith("#501 was created but not placed in LR-MDB-1, so it is Unassigned: "
                                      "FCC has to ask first"), body
    assert sm.spools[501]["location"] == "" and sm.direct_at("XL-1") == [99]


# ---- /api/spool/update: a location change leaves no old slot or trail ---------------------

def _update(client, sm, sid, updates):
    return _post(client, sm, "/api/spool/update", {"id": sid, "updates": updates})


def test_a_direct_location_change_clears_the_slot_and_trail_it_left(client):
    """Derek, 2026-10-15: a spool forced to a new location shouldn't still be flagged
    as coming from its old slot. The real extras merge keeps every other extra."""
    sm = WireSpoolman({42: {"location": "LR-MDB-1", "extra": {"container_slot": "2", "spool_temp": "70"}},
                       50: {"location": "XL-2", "extra": {"physical_source": "LR-MDB-1",
                                                          "physical_source_slot": "2"}}})
    assert _update(client, sm, 42, {"location": "CR-CT-2-R1"})["status"] == "success"
    assert _update(client, sm, 50, {"location": "CR-CT-2-R1"})["status"] == "success"
    assert sm.spools[42]["location"] == "CR-CT-2-R1" and sm.spools[42]["extra"]["container_slot"] == ""
    assert sm.spools[42]["extra"]["spool_temp"] == "70", sm.spools[42]
    assert sm.spools[50]["extra"]["physical_source"] == "" and sm.spools[50]["extra"]["physical_source_slot"] == ""


@pytest.mark.parametrize("target, reason", [("XL-1", "toolhead"), ("CORE1", "toolhead"), ("XL", "printer_row")])
def test_a_direct_location_change_onto_a_toolhead_or_printer_row_writes_nothing(client, target, reason):
    sm = FakeSpoolman({42: {"location": "CR-CT-2-R1", "extra": {}},
                       99: {"location": "XL-1", "extra": {}}})
    body = _update(client, sm, 42, {"location": target, "comment": "moved"})
    assert body["status"] == "error" and body["blocked_reason"] == reason, body
    assert "Nothing was written" in body["msg"], body
    assert sm.writes == [] and sm.spools[42]["location"] == "CR-CT-2-R1"


def test_a_direct_update_that_keeps_the_location_or_names_its_slot_is_written_as_sent(client):
    """Controls: an unchanged location blanks nothing, and a slot the caller sent
    itself is written as sent."""
    sm = WireSpoolman({42: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}},
                       43: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}}})
    _update(client, sm, 42, {"location": "LR-MDB-1", "comment": "x"})
    _update(client, sm, 43, {"location": "CR-MDB-1", "extra": {"container_slot": "3"}})
    assert sm.spools[42]["extra"]["container_slot"] == "2"
    assert sm.spools[43]["location"] == "CR-MDB-1" and sm.spools[43]["extra"]["container_slot"] == "3"
