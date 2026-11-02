"""Lost spools say so, the server half of build spec section 8 of Group 58.

Derek's note (2026-11-01): he wants lost spools apart from Unassigned's many spools
and easy to find, assign or clear later: "if one is found, it's apparent that this
was filed away because we didn't know where it went". UNKNOWN already is that list,
so each spool in it says which audit lost it and when, from fcc_pre_audit_location:
<PLACE>[:<slot>]@<YYYY-MM-DD>, no new field. A hand move into UNKNOWN blanks the
note, so a note is only ever an audit's.

The cards, the spool window's badge and the toast are the page half.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402
from test_audit_session_58 import (  # noqa: E402,F401
    add_spool, env, log_text, park, report, scan, session, start,
)

LOST = {"place": "LR-MDB-1", "slot": "2", "on": "2026-11-01"}
NOTE = "LR-MDB-1:2@2026-11-01"


@pytest.fixture(autouse=True)
def _own_undo_stack(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-11-02")


def spools(env):
    return env["fake"].records["spool"]


def note_of(env, sid):
    return json.loads(env["fake"].extra("spool", sid).get("fcc_pre_audit_location", '""'))


# ---------------------------------------------------------------------------
# Reading the note
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("note, want", [
    ("LR-MDB-1:2@2026-11-01", {"place": "LR-MDB-1", "slot": "2", "on": "2026-11-01"}),
    ("LR-MDB-1@2026-11-01", {"place": "LR-MDB-1", "slot": "", "on": "2026-11-01"}),
    ("LR-MDB-1", {"place": "LR-MDB-1", "slot": "", "on": ""}),          # an older FCC's note
    ('"LR-MDB-1:2@2026-11-01"', {"place": "LR-MDB-1", "slot": "2", "on": "2026-11-01"}),    # still wrapped
    ("LR", {"place": "LR", "slot": "", "on": ""}),
    ("BIN@2", {"place": "BIN@2", "slot": "", "on": ""}),                # an @ that is no day
    ("Bin 2:3@2026-11-01", {"place": "Bin 2", "slot": "3", "on": "2026-11-01"}),
])
def test_audit_lost_from_reads_a_note(note, want):
    assert spoolman_api.audit_lost_from("UNKNOWN", {"fcc_pre_audit_location": note}) == want


def test_a_written_note_reads_back():
    assert spoolman_api.audit_lost_from(
        "unknown", {"fcc_pre_audit_location": logic._audit_park_note("LR-MDB-1", "2", "2026-11-01")}) == LOST


@pytest.mark.parametrize("location", ["", None, "LR-MDB-1", "XL-1", "UNASSIGNED"])
def test_a_spool_anywhere_else_is_lost_by_nobody(location):
    """The move engine carries the note along: it goes stale at the next move."""
    assert spoolman_api.audit_lost_from(location, {"fcc_pre_audit_location": NOTE}) is None


@pytest.mark.parametrize("extra", [{}, None, "junk", {"fcc_pre_audit_location": ""},
                                   {"fcc_pre_audit_location": None}, {"fcc_pre_audit_location": '""'}])
def test_no_note_is_no_answer(extra):
    assert spoolman_api.audit_lost_from("UNKNOWN", extra) is None


@pytest.mark.parametrize("lost, words", [
    (LOST, "the audit of LR-MDB-1 slot 2 on 2026-11-01"),
    ({"place": "LR", "slot": "", "on": "2026-11-01"}, "the audit of LR on 2026-11-01"),
    ({"place": "LR-MDB-1", "slot": "", "on": ""}, "the audit of LR-MDB-1"),
])
def test_the_words(lost, words):
    assert spoolman_api.audit_lost_words(lost) == words


def _record(location, extra):
    return {"id": 5, "location": location, "extra": extra, "remaining_weight": 100,
            "filament": {"name": "Red", "material": "PLA", "vendor": {"name": "Some Brand"}}}


def test_a_cards_details_carry_it():
    info = spoolman_api.format_spool_display(_record("UNKNOWN", {"fcc_pre_audit_location": NOTE}))
    assert info["details"]["lost_from"] == LOST


@pytest.mark.parametrize("location, extra", [("LR-MDB-1", {"fcc_pre_audit_location": NOTE}), ("UNKNOWN", {})])
def test_other_cards_details_say_none(location, extra):
    assert spoolman_api.format_spool_display(_record(location, extra))["details"]["lost_from"] is None


def test_a_location_rows_details_carry_it_too(env):
    """The Unknown list's cards are this row."""
    add_spool(env, 1, "UNKNOWN", fcc_pre_audit_location=NOTE)
    (row,) = env["client"].get("/api/get_contents?id=UNKNOWN").get_json()
    assert row["details"]["lost_from"] == LOST


def test_the_spool_window_gets_it(env):
    """A record it reads raw: the page has no parser of its own."""
    add_spool(env, 1, "UNKNOWN", fcc_pre_audit_location=NOTE)
    add_spool(env, 2, "LR-MDB-1", fcc_pre_audit_location=NOTE)
    assert env["client"].get("/api/spool_details?id=1").get_json()["lost_from"] == LOST
    assert "lost_from" not in env["client"].get("/api/spool_details?id=2").get_json()


# ---------------------------------------------------------------------------
# A scan outside an audit
# ---------------------------------------------------------------------------

def test_a_lost_spool_scanned_outside_an_audit_says_it_turned_up(env):
    add_spool(env, 99, "UNKNOWN", fcc_pre_audit_location=NOTE)
    env["logs"].clear()
    ans = scan(env, "ID:99", source="keyboard")
    assert ans["type"] == "spool" and ans["id"] == 99 and ans["location"] == "UNKNOWN"
    assert ans["lost_from"] == LOST
    words = "#99 turned up. It was marked lost by the audit of LR-MDB-1 slot 2 on 2026-11-01. Scan where it goes."
    assert ans["lost_msg"] == words
    assert env["logs"] == [(f"❓ {words}", "WARNING", "ffaa00")]


def test_an_older_notes_scan_says_what_it_can(env):
    add_spool(env, 99, "UNKNOWN", fcc_pre_audit_location="LR-MDB-1")
    ans = scan(env, "ID:99", source="keyboard")
    assert ans["lost_msg"] == "#99 turned up. It was marked lost by the audit of LR-MDB-1. Scan where it goes."


def test_a_turned_up_line_escapes_the_place(env):
    add_spool(env, 99, "UNKNOWN", fcc_pre_audit_location="<B>BOX@2026-11-01")
    env["logs"].clear()
    ans = scan(env, "ID:99", source="keyboard")
    assert "<B>BOX" in ans["lost_msg"]                # the toast draws plain text
    assert log_text(env)[0].startswith("❓ #99 turned up.") and "&lt;B&gt;BOX" in log_text(env)[0]


def test_a_spool_at_unknown_with_no_note_scans_as_ever(env):
    add_spool(env, 99, "UNKNOWN")
    env["logs"].clear()
    ans = scan(env, "ID:99", source="keyboard")
    assert "lost_from" not in ans and "lost_msg" not in ans and env["logs"] == []


def test_a_spool_with_an_old_note_somewhere_else_scans_as_ever(env):
    add_spool(env, 99, "SHELF-1", fcc_pre_audit_location=NOTE)
    env["logs"].clear()
    ans = scan(env, "ID:99", source="keyboard")
    assert "lost_from" not in ans and env["logs"] == []


def test_the_whole_walk_a_park_then_a_scan_that_finds_it(env):
    add_spool(env, 99, "LR-MDB-1", container_slot="2")
    start(env, "LR-MDB-1")
    park(env, today="2026-11-01")
    ans = scan(env, "ID:99", source="keyboard")
    assert ans["lost_from"] == LOST


# ---------------------------------------------------------------------------
# A scan inside an audit
# ---------------------------------------------------------------------------

def test_a_lost_spool_scanned_in_an_audit_is_an_extra_whose_tile_says_so(env):
    add_spool(env, 1, "SHELF-1")
    add_spool(env, 99, "UNKNOWN", name="Mystery", fcc_pre_audit_location=NOTE)
    start(env, "SHELF-1")
    scan(env, "ID:99")
    assert session()["rogue_items"] == [99]
    words = "Unknown (marked lost by the audit of LR-MDB-1 slot 2 on 2026-11-01)"
    body = env["client"].get("/api/audit_session").get_json()
    assert body["rogue"][0]["where"] == words and body["rogue"][0]["lost_from"] == LOST
    assert env["logs"][-1][:2] == (f"⚠️ Extra: #99 Some Brand PLA (Mystery): FCC has it at {words}.", "WARNING")
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    assert f"#99 Some Brand PLA (Mystery) → {words}" in report(env)


def test_a_spool_at_unknown_with_no_note_is_a_plain_extra(env):
    add_spool(env, 1, "SHELF-1")
    add_spool(env, 99, "UNKNOWN")
    start(env, "SHELF-1")
    scan(env, "ID:99")
    row = env["client"].get("/api/audit_session").get_json()["rogue"][0]
    assert row["where"] == "Unknown" and "lost_from" not in row


# ---------------------------------------------------------------------------
# A hand move into UNKNOWN
# ---------------------------------------------------------------------------

def test_a_hand_move_into_unknown_blanks_an_old_note(env):
    """"Marked lost by the audit" must be true: an old note rides along on every
    move, so a spool sent to Unknown by hand would claim an audit lost it."""
    add_spool(env, 1, "SHELF-1", fcc_pre_audit_location=NOTE)
    res = logic.perform_smart_move("UNKNOWN", [1], origin="manual")
    assert res["status"] == "success", res
    assert spools(env)[1]["location"] == "UNKNOWN" and note_of(env, 1) == ""
    assert scan(env, "ID:1", source="keyboard").get("lost_from") is None


def test_its_undo_brings_the_note_back(env):
    add_spool(env, 1, "SHELF-1", fcc_pre_audit_location=NOTE)
    logic.perform_smart_move("UNKNOWN", [1], origin="manual")
    assert logic.perform_undo()["success"] is True
    assert note_of(env, 1) == NOTE and spools(env)[1]["location"] == "SHELF-1"


def test_a_rescan_onto_unknown_keeps_the_audits_note(env):
    """No move happened: it is still the spool that audit lost."""
    add_spool(env, 1, "UNKNOWN", fcc_pre_audit_location=NOTE)
    logic.perform_smart_move("UNKNOWN", [1], origin="manual")
    assert note_of(env, 1) == NOTE


def test_a_move_anywhere_else_keeps_the_note(env):
    """It is harmless there (only UNKNOWN reads it), and Undo's snapshot needs no
    new rule. The next park overwrites it."""
    add_spool(env, 1, "UNKNOWN", fcc_pre_audit_location=NOTE)
    logic.perform_smart_move("SHELF-1", [1], origin="manual")
    assert note_of(env, 1) == NOTE and spools(env)[1]["location"] == "SHELF-1"
    assert scan(env, "ID:1", source="keyboard").get("lost_from") is None


# ---------------------------------------------------------------------------
# Finding them again
# ---------------------------------------------------------------------------

def test_bulk_moves_plan_from_unknown_lists_the_parked_spools(env):
    """The way to file a lot of them at once, behind its flag: parked spools have no
    slot and no trail, so nothing skips them."""
    for sid in (1, 2, 3):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(sid))
    start(env, "LR-MDB-1")
    assert park(env)["parked"] == [1, 2, 3]
    plan = logic.plan_bulk_move("UNKNOWN", "SHELF-1")
    assert plan["ok"] is True and plan["movable_ids"] == [1, 2, 3] and plan["skipped"] == []
    assert set(plan["rows"]) == {"1", "2", "3"}


def test_a_parked_spool_is_in_the_unknown_list_with_its_note(env):
    add_spool(env, 1, "LR-MDB-1", container_slot="2")
    start(env, "LR-MDB-1")
    park(env, today="2026-11-01")
    (row,) = env["client"].get("/api/get_contents?id=UNKNOWN").get_json()
    assert row["id"] == 1 and row["slot"] == "" and row["details"]["lost_from"] == LOST
