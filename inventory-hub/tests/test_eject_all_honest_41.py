"""Group 41.1 / 41.2 / 41.8 / 41.9 — Eject All refuses the views it must not
sweep, says what it really did, and no door turns a blank or a virtual list
into "every spool".

Derek's answers that shape these pins:
  - D4 (2026-09-13): block Eject All on Room and Printer views ("an eject all
    on a room would be catastrophic"); boxes, carts, shelves and heads keep it,
    with honest per-spool results.
  - 2026-10-13: the refusal's pointer follows the Bulk Moves switch; a printer
    points at its cards and heads; head-less printers and synthesized rows are
    blocked too; every blank / UNASSIGNED / UNKNOWN door is refused.
  - Q1 (2026-09-18): a spool with no saved home goes to Unassigned after ONE
    prompt (Eject All asks once for the batch), never up to its Room; Smart
    Load's resident keeps the printer's Room. A Room-valued trail is a home.

The real clear_location route, perform_smart_eject and perform_smart_move run
against tests/move_engine_harness.py's FakeSpoolman.
"""
from __future__ import annotations

import copy
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import routes_scan  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, run_move  # noqa: E402

PRINTER_MAP = {
    "XL-1": {"printer_name": "🦝 XL", "position": 0},
    "XL-2": {"printer_name": "🦝 XL", "position": 1},
    "XL-3": {"printer_name": "🦝 XL", "position": 2},
    "TB-1": {"printer_name": "Test Bench", "position": 0},
    # get_active_printer_map lists a dual-role row that names itself a head.
    "SOLO": {"printer_name": "Solo", "position": 0},
}

LOCATIONS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1},
                   {"location_id": "XL-3", "position": 2}]},
    {"LocationID": "NEWP", "Type": "Printer", "Max Spools": "0", "toolheads": []},
    {"LocationID": "SOLO", "Type": "Printer", "Max Spools": "1",
     "toolheads": [{"location_id": "SOLO", "position": 0}]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR"},
    {"LocationID": "CR-CT-2", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR-CT-2"},
    # A contrived prefix collision: a cart "TB" whose matcher reaches the head TB-1.
    {"LocationID": "TB", "Type": "Cart", "Max Spools": "0"},
    {"LocationID": "TB-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "TB"},
]


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _clear(sm, client, location, **extra):
    body = {"action": "clear_location", "location": location, **extra}
    resp = run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map=PRINTER_MAP,
                    call=lambda: client.post("/api/manage_contents", json=body))
    return resp.get_json()


# --- 41.1 / 41.9: which views refuse --------------------------------------

@pytest.mark.parametrize("loc,expected", [
    ("LR", "room_view"),
    ("XL", "printer_view"),        # a printer whose heads are XL-1..XL-3
    ("NEWP", "printer_view"),      # a printer with no heads yet
    ("SOLO", None),                # a dual-role printer that is its own head keeps it
    ("XL-2", None),                # a head keeps Eject All (behind the print probe)
    ("LR-MDB-1", None),            # a box
    ("CR-CT-2-R1", None),          # a cart row
    ("ZZ-9", "synthesized"),       # no locations.json row: a "(Room)" or Spoolman-native name
    ("UNASSIGNED", "unassigned"),
    ("unknown", "unknown"),
    ("  ", "blank"),
])
def test_which_views_refuse_eject_all(loc, expected):
    rows = {r["LocationID"]: r for r in LOCATIONS}
    key = loc.strip().upper()
    assert logic.eject_all_block_reason(loc, rows.get(key), PRINTER_MAP) == expected


@pytest.mark.parametrize("loc,reason,what", [
    ("LR", "room_view", "a room"),
    ("XL", "printer_view", "a printer"),
    ("NEWP", "printer_view", "a printer"),
    ("ZZ-9", "synthesized", "not a saved location"),
    ("UNASSIGNED", "unassigned", "the Unassigned list"),
    ("UNKNOWN", "unknown", "the Unknown list"),
])
def test_a_refused_view_reads_and_writes_nothing(client, logs, loc, reason, what):
    """FAILS on the old route: LR's and XL's matches were ejected (XL's heads
    mid-print, with no prompt), and UNASSIGNED "returned" trail-carrying spools
    into their old boxes."""
    sm = FakeSpoolman({
        11: {"location": "LR-MDB-1", "extra": {}},
        12: {"location": "XL-2", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
        13: {"location": "", "extra": {"physical_source": "LR-MDB-1"}},
    })
    body = _clear(sm, client, loc)
    assert body["success"] is False and body["blocked_reason"] == reason, body
    # Counted on the fake: run_move patches the reader itself, so an outer mock
    # here never saw a call (Group 41 review).
    assert sm.list_reads == 0, "a refused view read Spoolman"
    assert sm.writes == [], "a refused view wrote"
    assert (f"⚠️ Eject All refused on {loc.upper()} ({what}): nothing was moved", ("WARNING", "ffaa00")) in logs


def test_a_rooms_pointer_follows_the_bulk_moves_switch(client, logs):
    """Derek, 2026-10-13: with Bulk Moves on, point at Move all → and warn about
    its preview; with it off (prod today), say where to eject from instead."""
    sm = FakeSpoolman({})
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=True):
        on = _clear(sm, client, "LR")["msg"]
    with patch.object(routes_scan, "_bulk_moves_enabled", return_value=False):
        off = _clear(sm, client, "LR")["msg"]
    assert "🔀 Move all →" in on and "preview" in on, on
    assert "Move all" not in off and "boxes, drawers and shelves" in off, off


def test_a_printers_refusal_names_its_heads(client, logs):
    sm = FakeSpoolman({})
    msg = _clear(sm, client, "XL")["msg"]
    assert "XL-1 … XL-3" in msg and "FCC asks first if XL is printing" in msg, msg
    assert "Settings → Toolheads" in _clear(sm, client, "NEWP")["msg"]


def test_check_only_answers_without_reading_spoolman(client, logs):
    """The browser asks before it shows "Nuke all unslotted in …?"."""
    sm = FakeSpoolman({11: {"location": "LR-MDB-1", "extra": {}}})
    ok = _clear(sm, client, "LR-MDB-1", check_only=True)
    refused = _clear(sm, client, "LR", check_only=True)
    assert ok == {"success": True, "check_only": True}, ok
    assert refused["blocked_reason"] == "room_view", refused
    assert sm.list_reads == 0 and sm.writes == []


# --- 41.1 belt and braces: a head's spool is never swept from another view ---

def test_a_heads_resident_reached_by_prefix_is_left_loaded(client, logs):
    """The cart TB's matcher reaches TB-1's resident by first segment. #21 has a
    saved home, so a guard that only listed it (no `continue`) would send it
    back to LR-MDB-1 off the head mid-print. (The old route answered
    REQUIRE_CONFIRM for a homeless resident and wrote nothing, so a resident
    with no home could never show a sweep: Group 41 review.) FAILS on the old
    route, which returned #21 home."""
    sm = FakeSpoolman({
        21: {"location": "TB-1", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2"}},
        22: {"location": "TB", "extra": {}},            # loose on the cart, no home
    })
    body = _clear(sm, client, "TB", confirmed_unassign_ids=[22])
    assert body["skipped_loaded"] == [21] and body["needs_unassign"] == [], body
    assert sm.direct_at("TB-1") == [21], "the head's spool was swept"
    assert [w for w in sm.writes if w[0] == 21] == [], "the head's spool was written"
    assert body["ejected"] == [22], body


# --- 41.2: honest per-spool results -----------------------------------------

def _cart_row_spools():
    return {
        31: {"location": "CR-CT-2-R1", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "3"}},
        32: {"location": "CR-CT-2-R1", "extra": {}},                      # no saved home
        33: {"location": "CR-CT-2-R1", "extra": {"physical_source": "LR-MDB-1"}},
        34: {"location": "CR-CT-2-R1", "extra": {"container_slot": "1"}},  # in a slot
    }


def test_eject_all_lists_what_it_did_and_asks_once_for_the_homeless(client, logs):
    """FAILS on the old route: every eject was counted as done whatever it
    answered (the homeless #32 and the rejected #33 included), with a bare
    success. Now: #31 went home, #32 needs the unassign decision, #33's write
    was rejected, #34 sits in a slot."""
    sm = FakeSpoolman(_cart_row_spools(), reject_ids=[33])
    body = _clear(sm, client, "CR-CT-2-R1")
    assert body["success"] is False, body
    assert body["ejected"] == [31]
    assert body["needs_unassign"] == [32]
    assert [f["id"] for f in body["failed"]] == [33], body
    assert body["skipped_slotted"] == [34] and body["skipped_loaded"] == []
    assert "#32" in body["unassign_msg"] and "Unassign it?" in body["unassign_msg"], body
    assert sm.direct_at("LR-MDB-1") == [31]
    assert any("Eject All on CR-CT-2-R1: ejected 1, 1 need a decision, 1 failed" in m
               and a[0] == "WARNING" for m, a in logs), logs


def test_the_unassign_yes_unassigns_only_the_ids_it_names(client, logs):
    sm = FakeSpoolman({32: {"location": "CR-CT-2-R1", "extra": {}},
                       35: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _clear(sm, client, "CR-CT-2-R1", confirmed_unassign_ids=[32])
    assert body["ejected"] == [32] and body["needs_unassign"] == [35], body
    assert sm.spools[32]["location"] == "" and sm.spools[35]["location"] == "CR-CT-2-R1"
    assert "2 spools" not in body["unassign_msg"] and "#35" in body["unassign_msg"]


def test_several_homeless_spools_get_one_batch_prompt(client, logs):
    sm = FakeSpoolman({32: {"location": "CR-CT-2-R1", "extra": {}},
                       35: {"location": "CR-CT-2-R1", "extra": {}}})
    body = _clear(sm, client, "CR-CT-2-R1")
    assert body["needs_unassign"] == [32, 35] and sm.writes == []
    assert body["unassign_msg"] == ("2 spools on CR-CT-2-R1 have no saved home (#32, #35). "
                                    "Unassign them?"), body


def test_an_unreadable_location_ejects_nothing(client, logs):
    """FAILS on the old route: the fail-open reader answered [] on a Spoolman
    timeout and Eject All reported success for a location it never read."""
    sm = FakeSpoolman(_cart_row_spools())
    sm.list_reads_fail = True
    body = _clear(sm, client, "CR-CT-2-R1")
    assert body["success"] is False and "Couldn't read CR-CT-2-R1" in body["msg"], body
    assert sm.writes == []
    assert any(m.startswith("❌ Eject All on CR-CT-2-R1: couldn't read it") and a[0] == "ERROR"
               for m, a in logs), logs


def test_a_clean_eject_all_logs_one_success_line(client, logs):
    sm = FakeSpoolman({31: _cart_row_spools()[31]})
    body = _clear(sm, client, "CR-CT-2-R1")
    assert body["success"] is True and body["ejected"] == [31], body
    assert ("⏏️ Eject All on CR-CT-2-R1: ejected 1", ("SUCCESS", "00ff00")) in logs, logs


# --- 41.8: no Room fallback; a Room-valued trail is still a home -----------

def _eject(sm, sid, **kw):
    return run_move(sm, probe=IDLE, locations=LOCATIONS, printer_map=PRINTER_MAP,
                    call=lambda: logic.perform_smart_eject(sid, **kw))


@pytest.mark.parametrize("where", ["CR-CT-2-R1", "LR-MDB-1"])
def test_a_homeless_spool_asks_to_unassign_instead_of_going_to_its_room(logs, where):
    """FAILS on the old engine: it went up to its Room (CR / LR) unasked."""
    sm = FakeSpoolman({41: {"location": where, "extra": {}}})
    assert _eject(sm, 41) == "REQUIRE_CONFIRM"
    assert sm.writes == []
    assert _eject(sm, 41, confirmed_unassign=True) is True
    assert sm.spools[41]["location"] == ""


def test_a_room_valued_trail_is_a_saved_home(logs):
    """Prod #243 sits on RCOI-8 with physical_source CR: ejecting it returns it
    to CR with no prompt (Claude's call 17, pinned 2026-10-14)."""
    sm = FakeSpoolman({243: {"location": "XL-3", "extra": {"physical_source": "CR"}}})
    assert _eject(sm, 243, confirm_active_print=True) is True
    assert sm.spools[243]["location"] == "CR"


def test_smart_loads_resident_still_goes_to_the_printers_room(logs):
    """Derek kept his 2026-09-12 rule for the resident Smart Load pushes off."""
    sm = FakeSpoolman({51: {"location": "XL-1", "extra": {}}})
    assert _eject(sm, 51, confirm_active_print=True, homeless_destination="LR") is True
    assert sm.spools[51]["location"] == "LR"


# --- 41.9: no door sweeps "every spool" -------------------------------------

# The harness's fake matcher skips blank names, so it can't show the old sweep;
# these drive the REAL matcher (spoolman_api.get_all_spools patched underneath).
UNASSIGNED_SPOOLS = [{"id": 61, "location": "", "extra": {}},
                     {"id": 62, "location": "", "extra": {"physical_source": '"LR-MDB-1"'}}]


def _real_matcher(call):
    with patch.object(logic.spoolman_api, "get_all_spools",
                      side_effect=lambda *a, **k: copy.deepcopy(UNASSIGNED_SPOOLS)) as listing,          patch.object(logic.spoolman_api, "update_spool") as upd,          patch.object(logic.spoolman_api, "get_spool", return_value=None),          patch.object(logic.locations_db, "load_locations_list",
                      side_effect=lambda *a, **k: copy.deepcopy(LOCATIONS)),          patch.object(logic.locations_db, "get_active_printer_map", return_value=PRINTER_MAP),          patch.object(logic.config_loader, "load_config", return_value={}):
        return call(), listing, upd


def test_the_real_matcher_still_reads_a_blank_as_every_unassigned_spool():
    """Precondition, pinned so the tests below keep proving something."""
    found, _, _ = _real_matcher(lambda: logic.spoolman_api.get_spools_at_location(""))
    assert sorted(found) == [61, 62]


@pytest.mark.parametrize("item", ["", "  ", "UNASSIGNED", "unknown", '""'])
def test_a_move_refuses_a_blank_or_virtual_item(logs, item):
    """FAILS on the old engine: a blank item expanded to every spool with no
    location (plus every spool with no trail as a ghost) and moved them all."""
    res, listing, upd = _real_matcher(lambda: logic.perform_smart_move("CR-CT-2-R1", [item]))
    assert res["status"] == "error", res
    assert listing.call_count == 0, "the move expanded the item through the matcher"
    assert upd.call_count == 0


def test_the_smart_move_route_refuses_a_blank_item(client, logs):
    resp, listing, upd = _real_matcher(lambda: client.post(
        "/api/smart_move", json={"location": "CR-CT-2-R1", "spools": [""]}))
    assert resp.get_json()["status"] == "error"
    assert listing.call_count == 0 and upd.call_count == 0


@pytest.mark.parametrize("arg", ["", "%20%20"])
def test_get_contents_with_a_blank_id_is_an_empty_list(client, arg):
    """FAILS on the old route: '' answered every spool with no location."""
    with patch.object(app_module.spoolman_api, "get_spools_at_location_detailed",
                      return_value=[{"id": 1}]) as reader:
        r = client.get(f"/api/get_contents?id={arg}")
    assert r.status_code == 200 and r.get_json() == []
    assert reader.call_count == 0
