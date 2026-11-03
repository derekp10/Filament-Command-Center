"""Audit's Done, build spec section 5 of Group 58 (it replaced 18.2's one-step park).

Done writes nothing while it has spools to park: it asks, through the real
/api/identify_scan, and a Yes to the real /api/audit/park parks them in one Undo.
Every expected spool that wasn't scanned is parked unless it isn't there to park:
deleted, archived, moved on since the location scan, in the scan buffer, or on a
head (Bulk Move's skip rule, one helper shared with it). A spool the question named
is checked once more right before its write.

REWRITTEN ON PURPOSE (2026-11-02). The old file mocked update_spool, which is how
Done's behaviour stayed hidden for months: it took a loaded spool off its head and
left it listed in its box, pinned here as "container_slot stays". Everything that
writes below runs the real update_spool over tests/spoolman_extra_fake.SpoolmanHTTPFake.

Undo of a park is tests/test_audit_undo_58.py. Which audit lost a spool, and the
day in the note's reading, are tests/test_audit_lost_spools_58.py.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402
from spoolman_extra_fake import _Resp  # noqa: E402
from test_audit_session_58 import (  # noqa: E402,F401
    AUDIT_SCAN, add_spool, env, log_text, park, report, scan, session, start,
)


@pytest.fixture(autouse=True)
def _isolated_audit_session(monkeypatch):
    """Reset AUDIT_SESSION before / after each test so cross-test bleed can't mask
    a regression, and give each test its own Undo stack."""
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-11-02")
    state.reset_audit()
    yield
    state.reset_audit()


def spools(env):
    return env["fake"].records["spool"]


def extra_of(env, sid):
    """A spool's stored extras, parsed, as a person reading Spoolman sees them."""
    return {k: json.loads(v) for k, v in env["fake"].extra("spool", sid).items()}


def patched_ids(env):
    return [p[1] for p in env["fake"].patches]


def no_writes(env):
    return env["fake"].patches == []


def _two_missing(env):
    """A box audit with #1 found and #2, #3 missing."""
    for sid in (1, 2, 3):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(sid))
    start(env, "LR-MDB-1")
    scan(env, "ID:1")


# ---------------------------------------------------------------------------
# Done asks
# ---------------------------------------------------------------------------

def test_done_writes_nothing_and_asks(env):
    _two_missing(env)
    audit_id = session()["audit_id"]
    env["logs"].clear()
    question = scan(env, "CMD:DONE")
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, C3): the question carries the
    # Extras Done files here (`file`, none here) and the words for a multi-slot box.
    # And again (Derek, 2026-11-03, H S1): each row carries its tile's look, from the
    # row the session stored at the scan.
    tile = {"color": "72071C", "color_direction": "longitudinal", "remaining_weight": 500.0}
    assert question == {
        "type": "audit_done_question", "audit_id": audit_id, "location": "LR-MDB-1",
        "found": 1, "expected": 3, "stays": [], "file": [], "file_note": "",
        "park": [{"id": 2, "display": "#2 Some Brand PLA (Red)", "where": "LR-MDB-1 slot 2", "slot": "2", **tile},
                 {"id": 3, "display": "#3 Some Brand PLA (Red)", "where": "LR-MDB-1 slot 3", "slot": "3", **tile}],
    }
    assert no_writes(env)
    assert session()["active"] is True and session()["scanned_items"] == [1]    # its scans are kept
    assert state.AUDIT_LAST_END is None and state.UNDO_STACK == []
    assert not any("Audit Report" in m for m in log_text(env))


def test_done_reads_the_list_once_with_the_archived_spools(env, monkeypatch):
    """One read answers for every spool, and a missing id can mean only "deleted"."""
    _two_missing(env)
    asked = []
    real = spoolman_api.get_all_spools_strict

    def spy(*a, **k):
        asked.append(k)
        return real(*a, **k)

    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", spy)
    env["fake"].gets.clear()
    scan(env, "CMD:DONE")
    assert asked == [{"allow_archived": True}] and env["fake"].gets == ["/api/v1/spool"]


def test_a_page_from_before_the_question_is_told_to_reload_and_nothing_moves(env):
    """A bare CMD:DONE from a page left open across a deploy would otherwise end in
    a question it can't show."""
    _two_missing(env)
    env["logs"].clear()
    ans = scan(env, "CMD:DONE", ask=False)
    assert ans == {"type": "error", "stale_page": True,
                   "msg": "This page is out of date, so Done did nothing. Reload the page (Ctrl+F5) "
                          "and press Done again."}
    assert no_writes(env) and session()["active"] is True
    assert [(m, c) for m, c, _ in env["logs"]] == [(f"⚠️ {ans['msg']}", "WARNING")]


@pytest.mark.parametrize("marker", [1, "true", "yes", False, None])
def test_only_a_real_true_says_the_page_can_ask(env, marker):
    _two_missing(env)
    body = {"text": "CMD:DONE", "source": "keyboard", "audit_ask": marker}
    assert env["client"].post("/api/identify_scan", json=body).get_json().get("stale_page") is True


def test_a_stale_page_with_nothing_to_park_still_ends_the_audit(env):
    """Nothing can go wrong for it: there is no question to lose."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    audit_id = session()["audit_id"]
    assert scan(env, "CMD:DONE", ask=False) == {**AUDIT_SCAN, "audit_ended": {"id": audit_id, "why": "done"}}


def test_nothing_missing_reports_and_ends_with_no_read(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    env["logs"].clear()
    env["fake"].gets.clear()
    audit_id = session()["audit_id"]
    assert scan(env, "CMD:DONE") == {**AUDIT_SCAN, "audit_ended": {"id": audit_id, "why": "done"}}
    assert "Perfect Match" in report(env)
    assert env["fake"].gets == [] and no_writes(env)
    assert session()["active"] is False


def test_done_with_no_place_parks_nothing(env):
    """Defensive: a session with no location has no note to write."""
    state.AUDIT_SESSION.update({"active": True, "audit_id": "x-1", "location_id": "",
                                "expected_items": [101, 102], "scanned_items": [], "rogue_items": []})
    assert "audit_ended" in scan(env, "CMD:DONE")
    assert no_writes(env) and env["fake"].gets == []


@pytest.mark.parametrize("how", ["list_reads_fail", "down"])
def test_a_failed_read_at_done_keeps_the_audit_open(env, how):
    _two_missing(env)
    env["logs"].clear()
    setattr(env["fake"], how, True)
    ans = scan(env, "CMD:DONE")
    assert ans == {"type": "error", "msg": "Couldn't read LR-MDB-1 from Spoolman, so nothing was moved. "
                                           "Try Done again in a moment."}
    assert no_writes(env) and session()["active"] is True and session()["scanned_items"] == [1]
    assert any("Couldn't read LR-MDB-1" in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]
    assert not any("Audit Report" in m for m in log_text(env))

    setattr(env["fake"], how, False)
    assert scan(env, "CMD:DONE")["type"] == "audit_done_question"


def test_an_answer_that_isnt_a_list_is_a_failed_read(env, monkeypatch):
    _two_missing(env)
    monkeypatch.setattr(spoolman_api.requests, "get", lambda *a, **k: _Resp(200, {"oops": True}))
    assert "Couldn't read LR-MDB-1" in scan(env, "CMD:DONE")["msg"]
    assert session()["active"] is True


def test_locations_it_cant_read_is_a_failed_read_too(env, monkeypatch):
    """Without them FCC can't tell a head, and a head is never parked."""
    _two_missing(env)

    def corrupt():
        raise ValueError("corrupt (test)")

    monkeypatch.setattr(logic.locations_db, "load_locations_list", corrupt)
    assert "Couldn't read LR-MDB-1" in scan(env, "CMD:DONE")["msg"]
    assert no_writes(env) and session()["active"] is True


# ---------------------------------------------------------------------------
# One case per kind in plan_audit_done
# ---------------------------------------------------------------------------

def _plain_and(env, place="LR-MDB-1"):
    """#1 stays parkable, so the question is asked; #2 is the case under test."""
    add_spool(env, 1, place)
    add_spool(env, 2, place, container_slot="2")
    start(env, place)


def _one_stay(env):
    question = scan(env, "CMD:DONE")
    assert [row["id"] for row in question["park"]] == [1], question
    (stay,) = question["stays"]
    return stay


def test_the_plans_own_shape(env):
    add_spool(env, 1, "LR-MDB-1", container_slot="2")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    del spools(env)[2]
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, C1): the plan files the Extras too.
    assert logic.plan_audit_done(session()) == {
        "read_ok": True, "read_error": None, "occupants": 1, "file": [], "file_note": "",
        "park": [{"id": 1, "display": "#1 Some Brand PLA (Red)", "where": "LR-MDB-1 slot 2", "slot": "2"}],
        "stays": [{"id": 2, "display": "#2 Some Brand PLA (Red)", "where": "", "why": "no longer in Spoolman"}],
    }
    assert no_writes(env)


def test_a_plan_that_cant_read_says_so(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    env["fake"].down = True
    plan = logic.plan_audit_done(session())
    assert plan["read_ok"] is False and "isn't answering" in plan["read_error"]
    assert plan["park"] == [] and plan["stays"] == []


def test_a_plain_spool_is_parked(env):
    _plain_and(env)
    question = scan(env, "CMD:DONE")
    assert [row["id"] for row in question["park"]] == [1, 2] and question["stays"] == []


def test_a_deleted_spool_stays_and_says_so(env):
    _plain_and(env)
    del spools(env)[2]
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S1): the row carries its tile's look,
    # from the row the session stored at the location scan, so a deleted spool keeps it.
    assert _one_stay(env) == {"id": 2, "display": "#2 Some Brand PLA (Red)", "where": "",
                              "why": "no longer in Spoolman",
                              "color": "72071C", "color_direction": "longitudinal", "remaining_weight": 500.0}


def test_an_archived_spool_stays(env):
    """The Unknown list shows no archived spool: parked, it would vanish."""
    _plain_and(env)
    spools(env)[2]["archived"] = True
    stay = _one_stay(env)
    assert (stay["id"], stay["why"], stay["where"]) == (2, "archived", "LR-MDB-1 slot 2")


@pytest.mark.parametrize("now, where", [
    ("LR-MDB-2", "LR-MDB-2 slot 2"),
    ("XL-1", "XL-1 slot 2"),            # taken to a head meanwhile: never off it
    ("", "Unassigned"),
    ("UNKNOWN", "Unknown"),
])
def test_a_spool_that_moved_stays_and_says_where_it_is_now(env, now, where):
    _plain_and(env)
    spools(env)[2]["location"] = now
    stay = _one_stay(env)
    assert (stay["id"], stay["where"], stay["why"]) == (2, where, f"moved to {where}")


def test_a_spool_in_the_scan_buffer_stays(env):
    _plain_and(env)
    state.GLOBAL_BUFFER = [{"id": 2, "display": "#2"}]
    stay = _one_stay(env)
    assert (stay["id"], stay["why"]) == (2, "in the scan buffer")


def test_a_trail_doesnt_make_a_filed_spool_a_stay(env):
    """His forgotten spool: filed here on record, a stale trail or none."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1", physical_source="LR-MDB-2", physical_source_slot="3")
    start(env, "LR-MDB-1")
    assert [row["id"] for row in scan(env, "CMD:DONE")["park"]] == [1]


@pytest.mark.parametrize("place", ["XL-1", "CORE1"])
def test_a_head_audit_parks_nothing(env, place):
    """A spool FCC has on a head that isn't scanned stays on the head: the rule is
    Bulk Move's, a head or a printer that is its own head."""
    add_spool(env, 1, place, physical_source="LR-MDB-1")
    start(env, place)
    env["logs"].clear()
    assert "audit_ended" in scan(env, "CMD:DONE")
    assert no_writes(env)
    assert spools(env)[1]["location"] == place
    assert "<b>Left alone:</b> #1 Some Brand PLA (Red) → loaded in a toolhead slot" in report(env)


def test_a_spool_filed_on_a_multi_head_printers_row_is_parked(env):
    """It isn't loaded anywhere, as for Bulk Move (Group 40 item H)."""
    add_spool(env, 1, "XL")
    start(env, "XL")
    assert [row["id"] for row in scan(env, "CMD:DONE")["park"]] == [1]


def test_a_room_audit_parks_only_the_spools_filed_at_the_room(env):
    add_spool(env, 1, "LR")
    add_spool(env, 2, "LR-MDB-1", container_slot="1")
    add_spool(env, 3, "XL-1", physical_source="LR")
    start(env, "LR")
    result = park(env)
    assert result["parked"] == [1] and patched_ids(env) == [1]
    assert spools(env)[2]["location"] == "LR-MDB-1" and spools(env)[3]["location"] == "XL-1"


def test_only_stays_end_the_audit_with_a_report(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    state.GLOBAL_BUFFER = [{"id": 1}]
    del spools(env)[2]
    env["logs"].clear()
    audit_id = session()["audit_id"]
    assert scan(env, "CMD:DONE") == {**AUDIT_SCAN, "audit_ended": {"id": audit_id, "why": "done"}}
    line = report(env)
    assert "#1 Some Brand PLA (Red) → in the scan buffer" in line
    assert "#2 Some Brand PLA (Red) → no longer in Spoolman" in line
    assert "Parked" not in line and no_writes(env)


@pytest.mark.parametrize("rec, buffered, want", [
    ({"id": 5, "is_ghost": True, "location": "LR"}, [], "deployed to a live toolhead"),
    ({"id": 5, "archived": True, "location": "LR"}, [], "archived"),
    ({"id": 5, "location": "LR"}, [5], "in the scan buffer"),
    ({"id": 5, "location": "XL-1"}, [], "loaded in a toolhead slot"),
    ({"id": 5, "location": "LR"}, [], ""),
    ({"id": None, "location": "LR"}, [0], "in the scan buffer"),     # as Bulk Move's int(sid or 0)
])
def test_the_shared_skip_rule_keeps_bulk_moves_words(rec, buffered, want):
    assert logic._left_in_place_reason(rec, set(buffered), {"XL-1": {}}, {}) == want


# ---------------------------------------------------------------------------
# The park: what it writes
# ---------------------------------------------------------------------------

def test_the_yes_parks_with_the_note_and_clears_slot_and_trail(env):
    add_spool(env, 1, "LR-MDB-1", container_slot="2", physical_source="CR-CT-1", physical_source_slot="5",
              fcc_pre_box_location="CR-CT-1-R1")
    start(env, "LR-MDB-1")
    audit_id = session()["audit_id"]
    result = park(env, today="2026-11-01")
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, C4): the answer says what was filed.
    assert result == {
        "success": True, "parked": [1], "filed": [], "stayed": [], "failed": [],
        "msg": "Parked 1 spool at Unknown. Undo Last Move puts it back.",
        "audit_ended": {"id": audit_id, "why": "done"},
    }
    assert spools(env)[1]["location"] == "UNKNOWN"
    extra = extra_of(env, 1)
    assert extra["fcc_pre_audit_location"] == "LR-MDB-1:2@2026-11-01"
    for key in ("container_slot", "physical_source", "physical_source_slot", "fcc_pre_box_location"):
        assert extra[key] == "", key       # "": a popped key is kept by the merge
    assert session()["active"] is False
    assert state.AUDIT_LAST_END == {"id": audit_id, "why": "done", "location": "LR-MDB-1"}


def test_a_key_left_out_would_have_been_kept(env):
    """Why "" and never a pop, on the fake's own merge: the trail is really gone."""
    add_spool(env, 1, "LR-MDB-1", container_slot="2")
    start(env, "LR-MDB-1")
    park(env)
    (_e, _i, body), = env["fake"].patches
    assert body["extra"]["container_slot"] == '""'


def test_its_other_extras_are_kept(env):
    env["fake"].fields["spool"].append({"key": "spool_temp", "field_type": "text", "name": "spool_temp"})
    add_spool(env, 1, "LR-MDB-1", spool_temp="220")
    start(env, "LR-MDB-1")
    park(env)
    assert extra_of(env, 1)["spool_temp"] == "220"


@pytest.mark.parametrize("slot, note", [("", "LR-MDB-1:@2026-11-02"), ("3", "LR-MDB-1:3@2026-11-02")])
def test_the_notes_slot_is_empty_when_it_had_none(env, slot, note):
    """The ':' is always there: a LocationID can hold one (finding 8)."""
    add_spool(env, 1, "LR-MDB-1", container_slot=slot)
    start(env, "LR-MDB-1")
    park(env)
    assert extra_of(env, 1)["fcc_pre_audit_location"] == note


@pytest.mark.parametrize("today, day", [
    ("2026-11-01", "2026-11-01"),   # dev's clock is UTC: an evening here is tomorrow there
    ("2026-11-04", "2026-11-04"),
    ("2026-11-05", "2026-11-02"),   # further off than two days: the server's
    ("not a day", "2026-11-02"),
    (None, "2026-11-02"),
])
def test_the_notes_day_is_the_pages_by_the_excluded_marks_rule(env, today, day):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    park(env, today=today)
    assert extra_of(env, 1)["fcc_pre_audit_location"] == f"LR-MDB-1:@{day}"


def test_a_room_audits_note_names_the_room_a_spool_was_filed_at(env):
    add_spool(env, 1, "lr")
    start(env, "LR")
    park(env)
    assert extra_of(env, 1)["fcc_pre_audit_location"] == "LR:@2026-11-02"


def test_a_parked_spool_stops_being_listed_in_its_box(env):
    """Done used to leave a parked spool's slot claimed and its tile in the box,
    and the next audit of the box expected it again."""
    add_spool(env, 1, "LR-MDB-1", container_slot="2", physical_source="LR-MDB-1", physical_source_slot="2")
    add_spool(env, 2, "LR-MDB-1", container_slot="3")
    start(env, "LR-MDB-1")
    scan(env, "ID:2")
    park(env)
    held = env["client"].get("/api/get_contents?id=LR-MDB-1").get_json()
    assert [row["id"] for row in held] == [2]
    start(env, "LR-MDB-1")
    assert session()["expected_items"] == [2]


def test_each_parked_spool_has_a_line_and_the_report_says_it_all(env):
    _two_missing(env)
    env["logs"].clear()
    park(env)
    lines = log_text(env)
    assert lines[0] == ("❓ Audit: moved Spool #2 Some Brand PLA (Red) → UNKNOWN (was expected at "
                        "LR-MDB-1 slot 2, not scanned)")
    assert "<b>Parked at Unknown:</b> #2, #3 (Undo Last Move puts them back)" in report(env)
    assert "Audit Report" in lines[-2] and lines[-1] == "Audit Mode Ended."


def test_the_park_makes_one_undo_record(env):
    add_spool(env, 1, "lr-mdb-1", container_slot="2", physical_source="CR-CT-1", physical_source_slot="5",
              fcc_pre_box_location="CR-CT-1-R1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    park(env, today="2026-11-02")
    (record,) = state.UNDO_STACK
    assert record["id"].startswith(logic._UNDO_EPOCH + "-")
    assert record["moves"] == {1: "lr-mdb-1", 2: "LR-MDB-1"}          # the real place, as it was
    assert set(record["extras"][1]) == set(spoolman_api.SYSTEM_MANAGED_EXTRAS)
    assert record["extras"][1]["container_slot"] == "2"
    assert record["extras"][1]["physical_source"] == "CR-CT-1"
    assert record["extras"][1]["fcc_pre_box_location"] == "CR-CT-1-R1"
    assert record["extras"][1]["fcc_pre_audit_location"] == ""
    assert record["labels"] == {1: "#1 Some Brand PLA (Red)", 2: "#2 Some Brand PLA (Red)"}
    assert record["origin"] == "audit" and record["only_if_at"] == "UNKNOWN" and record["target"] == "UNKNOWN"
    assert record["slots"] == {1: "2", 2: ""} and record["place_had_row"] is True
    for key in ("released", "ejections", "ejection_extras", "ejection_released", "displaced"):
        assert record[key] == {}, key


# ---------------------------------------------------------------------------
# The park: when a write goes wrong
# ---------------------------------------------------------------------------

def _refuse(env, monkeypatch, *sids, message="nope (test)"):
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        if int(url.rstrip("/").rsplit("/", 1)[1]) in sids:
            return _Resp(400, {"message": message})
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)


def _lands_but_times_out(env, monkeypatch, *sids):
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        answer = real(url, json=json, timeout=timeout, **kw)
        if int(url.rstrip("/").rsplit("/", 1)[1]) in sids:
            raise TimeoutError("read timed out (test)")
        return answer

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)


def test_a_rejected_write_is_listed_and_the_spool_stays(env, monkeypatch):
    """Nothing landed, so nothing ended (finding 2, a pin changed on purpose): this
    test used to pin the audit's end, and with it the loss of every scan."""
    _two_missing(env)
    _refuse(env, monkeypatch, 2, 3)
    env["logs"].clear()
    result = park(env)
    assert result["success"] is False and result["parked"] == []
    assert [(f["id"], f["display"]) for f in result["failed"]] == [(2, "#2 Some Brand PLA (Red)"),
                                                                   (3, "#3 Some Brand PLA (Red)")]
    assert "HTTP 400" in result["failed"][0]["why"] and "nope (test)" in result["failed"][0]["why"]
    assert spools(env)[2]["location"] == "LR-MDB-1" and spools(env)[3]["location"] == "LR-MDB-1"
    assert extra_of(env, 2)["container_slot"] == "2"
    assert any("failed to park Spool #2" in m and "nope (test)" in m and c == "ERROR"
               for m, c, _ in env["logs"]), env["logs"]
    assert state.UNDO_STACK == []                         # nothing landed, nothing to undo
    assert "audit_ended" not in result
    assert session()["active"] is True and state.AUDIT_LAST_END is None
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, the toast): it says where to read why.
    assert result["msg"] == ("Nothing was parked. Couldn't park #2 and #3. "
                             "The audit is still open, so you can press Done again. "
                             "The Activity Log says what went wrong.")
    assert not any("Audit Report" in m for m in log_text(env)), log_text(env)
    assert any(result["msg"] in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]


def test_a_yes_where_nothing_landed_keeps_the_scans_and_done_works_again(env, monkeypatch):
    _two_missing(env)
    audit_id = session()["audit_id"]
    real = spoolman_api.requests.patch
    _refuse(env, monkeypatch, 2, 3)
    park(env)
    assert session()["scanned_items"] == [1] and session()["audit_id"] == audit_id
    assert not logic._AUDIT_END_LOCK.locked()

    monkeypatch.setattr(spoolman_api.requests, "patch", real)
    env["logs"].clear()
    env["fake"].patches.clear()
    result = park(env)
    assert result["success"] is True and result["parked"] == [2, 3]
    assert result["audit_ended"] == {"id": audit_id, "why": "done"}
    assert session()["active"] is False and len(state.UNDO_STACK) == 1
    assert "Found 1 of 3." in report(env)                # the first scan survived


def test_an_outage_right_after_the_plan_keeps_the_audit_too(env, monkeypatch):
    """Spoolman stops answering between the plan's list read and the first spool's
    last look: nothing is written, and the audit isn't lost with it."""
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    real = spoolman_api.get_spool_answer

    def down_from_here(sid):
        env["fake"].down = True
        return real(sid)

    monkeypatch.setattr(spoolman_api, "get_spool_answer", down_from_here)
    result = park(env, ids, audit_id)
    assert result["success"] is False and [f["id"] for f in result["failed"]] == [2, 3]
    assert "audit_ended" not in result and session()["active"] is True
    assert no_writes(env) and state.UNDO_STACK == []


def test_a_failure_with_stays_says_both_and_keeps_the_audit(env, monkeypatch):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    spools(env)[3]["location"] = "LR-MDB-2"
    _refuse(env, monkeypatch, 2)
    result = park(env, ids, audit_id)
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, the toast): it says where to read why.
    assert result["msg"] == ("Nothing was parked. 1 left where it is. Couldn't park #2. "
                             "The audit is still open, so you can press Done again. "
                             "The Activity Log says what went wrong.")
    assert [s["id"] for s in result["stayed"]] == [3] and session()["active"] is True


def test_one_landed_write_still_ends_the_audit(env, monkeypatch):
    """A true partial failure: its record exists, and Undo is refused while an audit
    runs, so it ends."""
    _two_missing(env)
    audit_id = session()["audit_id"]
    _refuse(env, monkeypatch, 2)
    result = park(env)
    assert result["parked"] == [3] and [f["id"] for f in result["failed"]] == [2]
    assert result["audit_ended"] == {"id": audit_id, "why": "done"}
    assert session()["active"] is False and len(state.UNDO_STACK) == 1


def test_a_write_that_landed_but_reported_failure_counts_as_parked(env, monkeypatch):
    """update_spool's timeout is a READ timeout: Spoolman can commit and answer
    slowly. Left out of the record, it could never be undone."""
    _two_missing(env)
    _lands_but_times_out(env, monkeypatch, 2)
    env["logs"].clear()
    result = park(env, today="2026-11-02")
    assert result["success"] is True and result["parked"] == [2, 3] and result["failed"] == []
    assert set(state.UNDO_STACK[0]["moves"]) == {2, 3}
    assert any("re-read shows it there: counted as moved" in m for m in log_text(env)), log_text(env)


def test_a_timeout_that_didnt_land_is_a_failure(env, monkeypatch):
    _two_missing(env)

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        raise TimeoutError("connect timed out (test)")

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    result = park(env)
    assert result["success"] is False and [f["id"] for f in result["failed"]] == [2, 3]
    assert "connect timed out" in result["failed"][0]["why"]
    assert spools(env)[2]["location"] == "LR-MDB-1"


def test_a_write_that_raises_is_a_failure_and_the_batch_goes_on(env, monkeypatch):
    _two_missing(env)
    real = logic._move_write

    def blow_up(sid, target, new_extra, unarchive=False):
        if sid == 2:
            raise RuntimeError("<boom>")
        return real(sid, target, new_extra, unarchive=unarchive)

    monkeypatch.setattr(logic, "_move_write", blow_up)
    env["logs"].clear()
    result = park(env)
    assert result["parked"] == [3] and [f["id"] for f in result["failed"]] == [2]
    assert not logic._AUDIT_END_LOCK.locked()
    assert any("&lt;boom&gt;" in m and c == "ERROR" for m, c, _ in env["logs"]), env["logs"]


def test_a_mixed_batch_names_every_spool_and_only_what_landed_goes_in_the_undo(env, monkeypatch):
    for sid in (1, 2, 3, 4, 5, 6):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(sid))
    start(env, "LR-MDB-1")
    scan(env, "ID:6")
    state.GLOBAL_BUFFER = [{"id": 4}]
    del spools(env)[5]
    _refuse(env, monkeypatch, 2)
    env["logs"].clear()
    result = park(env)
    assert result["success"] is False
    assert result["parked"] == [1, 3]
    assert [f["id"] for f in result["failed"]] == [2]
    assert {s["id"]: s["why"] for s in result["stayed"]} == {4: "in the scan buffer", 5: "no longer in Spoolman"}
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, the toast): it points to the report.
    assert result["msg"] == ("Parked 2 spools at Unknown. 2 left where they are. Couldn't park #2. "
                             "Undo Last Move puts them back. The Activity Log lists each spool.")
    assert set(state.UNDO_STACK[0]["moves"]) == {1, 3}
    line = report(env)
    assert "<b>Parked at Unknown:</b> #1, #3" in line and "<b>Failed:</b> #2" in line
    assert "in the scan buffer" in line and "no longer in Spoolman" in line
    assert session()["active"] is False


def test_outside_text_in_the_parks_lines_is_escaped(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1", name="<i>Blue")
    add_spool(env, 2, "LR-MDB-1", name="<i>Red")
    start(env, "LR-MDB-1")
    _refuse(env, monkeypatch, 1, message="<script>x</script>")
    env["logs"].clear()
    park(env)
    joined = "\n".join(log_text(env))
    assert "<script>" not in joined and "<I>" not in joined, joined
    assert "&lt;script&gt;" in joined and "&lt;I&gt;Red" in joined


# ---------------------------------------------------------------------------
# The toast (Derek, 2026-11-03): "Things like that toast will get pretty complicated
# depending on if there's a high number of moves", and the report "helps address the
# '64 placed here' ambiguity". The toast stays short however big the audit: every list
# in it names three spools at most and counts past that, and when it counted a group,
# or anything stayed or failed, it ends by pointing to the Activity Log, which names
# every spool. A shelf is 10 spools or more.
# ---------------------------------------------------------------------------

def _missing(env, n, place="CR-CT-1"):
    """An audit of `place` (a cart, no slots) with #1 found and #2 to #n+1 not scanned."""
    for sid in range(1, n + 2):
        add_spool(env, sid, place)
    start(env, place)
    scan(env, "ID:1")
    return list(range(2, n + 2))


@pytest.mark.parametrize("n, msg", [
    (1, "Parked 1 spool at Unknown. Undo Last Move puts it back."),
    (3, "Parked 3 spools at Unknown. Undo Last Move puts them back."),
    (4, "Parked 4 spools at Unknown. Undo Last Move puts them back. The Activity Log lists each spool."),
    (12, "Parked 12 spools at Unknown. Undo Last Move puts them back. The Activity Log lists each spool."),
])
def test_a_park_past_three_points_to_the_report_that_names_each_spool(env, n, msg):
    """RED on 5afeb8b past three: the toast never said where to see which spools went.
    Up to three it reads as it did (those pin what was already right)."""
    ids = _missing(env, n)
    result = park(env)
    assert result["parked"] == ids and result["msg"] == msg
    assert "<b>Parked at Unknown:</b> " + ", ".join(f"#{s}" for s in ids) in report(env)


def test_failures_past_three_are_counted_and_each_one_is_in_the_activity_log(env, monkeypatch):
    """"Couldn't park" named every id: a shelf Spoolman refused made a toast of a dozen
    numbers. Past three it counts them, and the report names each one, under the ERROR
    line that says why. RED on 5afeb8b."""
    ids = _missing(env, 5)
    _refuse(env, monkeypatch, *ids[:4])
    env["logs"].clear()
    result = park(env)
    assert result["parked"] == [6] and [f["id"] for f in result["failed"]] == [2, 3, 4, 5]
    assert result["msg"] == ("Parked 1 spool at Unknown. Couldn't park 4 spools. Undo Last Move puts it back. "
                             "The Activity Log lists each spool.")
    assert "<b>Failed:</b> #2, #3, #4, #5" in report(env)
    assert sum(1 for m, c, _ in env["logs"] if c == "ERROR" and "failed to park Spool" in m) == 4


def test_a_yes_where_every_write_failed_points_to_the_failure_lines(env, monkeypatch):
    """Nothing landed, so the audit stays open and there is no report yet: the toast
    points to the ERROR lines, one per spool, which say what went wrong. RED on 5afeb8b."""
    ids = _missing(env, 4)
    _refuse(env, monkeypatch, *ids)
    env["logs"].clear()
    result = park(env)
    assert "audit_ended" not in result and session()["active"] is True
    assert result["msg"] == ("Nothing was parked. Couldn't park 4 spools. The audit is still open, so you can "
                             "press Done again. The Activity Log says what went wrong.")
    assert sum(1 for m, c, _ in env["logs"] if c == "ERROR" and "failed to park Spool" in m) == 4
    assert not any("Audit Report" in m for m in log_text(env))


# ---------------------------------------------------------------------------
# The park: a last look right before each write
# ---------------------------------------------------------------------------

def _changes_at_last_look(env, monkeypatch, sid, change):
    """`change` lands in the moment after the plan: the question was true, and the
    spool's own read just before its write is the first to see otherwise."""
    real = spoolman_api.get_spool_answer

    def spy(asked):
        if asked == sid:
            change()
        return real(asked)

    monkeypatch.setattr(spoolman_api, "get_spool_answer", spy)


def _asked(env):
    question = scan(env, "CMD:DONE")
    return question, [row["id"] for row in question["park"]], question["audit_id"]


def test_a_spool_loaded_at_the_last_moment_stays_on_its_head(env, monkeypatch):
    """The reason this write isn't the move engine: it would take a spool off an
    idle head unasked."""
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    _changes_at_last_look(env, monkeypatch, 2, lambda: spools(env)[2].update(location="XL-1"))
    env["fake"].patches.clear()
    result = park(env, ids, audit_id)
    assert patched_ids(env) == [3]
    assert spools(env)[2]["location"] == "XL-1"
    assert result["parked"] == [3]
    assert result["stayed"] == [{"id": 2, "display": "#2 Some Brand PLA (Red)", "where": "XL-1 slot 2",
                                 "why": "moved to XL-1 slot 2"}]
    assert result["success"] is True


def test_a_spool_archived_at_the_last_moment_stays(env, monkeypatch):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    _changes_at_last_look(env, monkeypatch, 2, lambda: spools(env)[2].update(archived=True))
    assert park(env, ids, audit_id)["stayed"][0]["why"] == "archived"
    assert patched_ids(env) == [3]


def test_a_spool_buffered_at_the_last_moment_stays(env, monkeypatch):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)

    def buffer_it():
        state.GLOBAL_BUFFER = [{"id": 2}]

    _changes_at_last_look(env, monkeypatch, 2, buffer_it)
    assert park(env, ids, audit_id)["stayed"][0]["why"] == "in the scan buffer"
    assert patched_ids(env) == [3]


def test_a_spool_deleted_at_the_last_moment_stays(env, monkeypatch):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    _changes_at_last_look(env, monkeypatch, 2, lambda: spools(env).pop(2))
    result = park(env, ids, audit_id)
    assert result["stayed"] == [{"id": 2, "display": "#2 Some Brand PLA (Red)", "where": "",
                                 "why": "no longer in Spoolman"}]
    assert patched_ids(env) == [3] and result["success"] is True


def test_a_spool_it_cant_read_at_the_last_moment_isnt_written_and_counts_as_failed(env, monkeypatch):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    real = spoolman_api.get_spool_answer
    monkeypatch.setattr(spoolman_api, "get_spool_answer",
                        lambda sid: (None, False) if sid == 2 else real(sid))
    result = park(env, ids, audit_id)
    assert [f["id"] for f in result["failed"]] == [2] and result["success"] is False
    assert result["failed"][0]["why"] == "couldn't read where FCC has it"
    assert patched_ids(env) == [3]


def test_a_spool_scanned_after_the_question_is_found_and_not_parked(env):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    scan(env, "ID:2")               # another device's scan
    result = park(env, ids, audit_id)
    assert result["parked"] == [3] and patched_ids(env) == [3]


def test_only_the_spools_in_the_yes_are_parked(env):
    """A spool out of the buffer since the question is parkable now, but nobody was
    asked about it."""
    _two_missing(env)
    state.GLOBAL_BUFFER = [{"id": 3}]
    _q, ids, audit_id = _asked(env)
    assert ids == [2]
    state.GLOBAL_BUFFER = []
    result = park(env, ids, audit_id)
    assert result["parked"] == [2] and patched_ids(env) == [2]
    assert result["stayed"] == [{"id": 3, "display": "#3 Some Brand PLA (Red)", "where": "LR-MDB-1 slot 3",
                                 "why": "wasn't in the question you answered"}]


def test_a_yes_for_a_spool_the_audit_never_listed_writes_nothing(env):
    _two_missing(env)
    add_spool(env, 9, "CR")
    _q, _ids, audit_id = _asked(env)
    park(env, [9], audit_id)
    assert 9 not in patched_ids(env)
    assert spools(env)[9]["location"] == "CR"


def test_string_ids_count_as_the_same_spools(env):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    assert park(env, [str(s) for s in ids], audit_id)["parked"] == ids


@pytest.mark.parametrize("body", [{"ids": []}, {}, {"ids": "2"}, {"ids": 2}, {"ids": {"2": True}}])
def test_a_yes_that_names_no_spools_is_refused_and_the_audit_runs_on(env, body):
    _two_missing(env)
    _q, _ids, audit_id = _asked(env)
    result = env["client"].post("/api/audit/park", json={"audit_id": audit_id, **body}).get_json()
    assert result["success"] is False
    assert result["msg"] == "That Yes didn't say which spools it answers, so nothing was moved. Press Done again."
    assert no_writes(env) and session()["active"] is True


def test_a_body_that_isnt_json_is_a_stale_yes(env):
    _two_missing(env)
    res = env["client"].post("/api/audit/park", data="nonsense")
    assert res.status_code == 200
    assert res.get_json()["stale"] is True and no_writes(env) and session()["active"] is True


# ---------------------------------------------------------------------------
# A Yes that comes too late, or twice
# ---------------------------------------------------------------------------

def test_a_double_yes_writes_once_and_pushes_one_record(env):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    assert park(env, ids, audit_id)["success"] is True
    env["fake"].patches.clear()
    second = park(env, ids, audit_id)
    assert second == {"success": False, "stale": True, "msg": "That audit has already ended, so nothing was moved."}
    assert no_writes(env) and len(state.UNDO_STACK) == 1


def test_a_yes_during_the_first_is_refused_and_never_queued(env, monkeypatch):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    answers = []
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        answers.append(park(env, ids, audit_id))
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    assert park(env, ids, audit_id)["parked"] == ids
    assert answers == [{"success": False, "busy": True, "msg": "The audit is already finishing."}] * 2
    assert len(state.UNDO_STACK) == 1 and sorted(patched_ids(env)) == [2, 3]


def test_two_yeses_at_once_only_one_wins(env):
    """The lock is a real one: a loser in another thread is refused, never queued."""
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    results = []
    logic._AUDIT_END_LOCK.acquire()
    worker = threading.Thread(target=lambda: results.append(logic.park_audit_missing(audit_id, ids)))
    worker.start()
    worker.join(5)
    logic._AUDIT_END_LOCK.release()
    assert not worker.is_alive(), "the loser waited for the lock"
    assert results[0]["busy"] is True and no_writes(env)


@pytest.mark.parametrize("end", ["CMD:CANCEL", "idle"])
def test_a_yes_after_the_audit_ended_writes_nothing(env, end):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    if end == "idle":
        session()["last_activity_ts"] = time.time() - (state.AUDIT_IDLE_TIMEOUT_SECONDS + 60)
        app_module._check_audit_idle_timeout()
    else:
        scan(env, end)
    env["logs"].clear()
    result = park(env, ids, audit_id)
    assert result["success"] is False and result["stale"] is True
    assert no_writes(env) and state.UNDO_STACK == []
    assert any("already ended" in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]


def test_a_yes_for_an_earlier_audit_leaves_the_running_one_alone(env):
    _two_missing(env)
    _q, ids, old_id = _asked(env)
    scan(env, "CMD:CANCEL")
    start(env, "LR-MDB-1")
    new_id = session()["audit_id"]
    result = park(env, ids, old_id)
    assert result["stale"] is True and no_writes(env)
    assert session()["active"] is True and session()["audit_id"] == new_id


def test_a_yes_with_no_audit_id_is_stale(env):
    _two_missing(env)
    _q, ids, _audit_id = _asked(env)
    assert park(env, ids, None)["stale"] is True
    assert no_writes(env) and session()["active"] is True


@pytest.mark.parametrize("how", ["list_reads_fail", "down"])
def test_a_failed_read_at_the_yes_keeps_the_audit_open(env, how):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    setattr(env["fake"], how, True)
    result = park(env, ids, audit_id)
    assert result == {"success": False,
                      "msg": "Couldn't read LR-MDB-1 from Spoolman, so nothing was moved. Try Done again in a moment."}
    assert no_writes(env) and session()["active"] is True and state.UNDO_STACK == []
    assert not logic._AUDIT_END_LOCK.locked()

    setattr(env["fake"], how, False)
    assert park(env, ids, audit_id)["parked"] == ids


def test_a_yes_that_finds_nothing_left_to_park_ends_the_audit(env):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    spools(env)[2]["location"] = "LR-MDB-2"
    spools(env)[3]["location"] = "LR-MDB-2"
    result = park(env, ids, audit_id)
    assert result["success"] is True and result["parked"] == []
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, the toast): it points to the report.
    assert result["msg"] == "Nothing was parked. 2 left where they are. The Activity Log lists each spool."
    assert session()["active"] is False and state.UNDO_STACK == []


def test_the_lock_is_free_after_a_question(env):
    _two_missing(env)
    scan(env, "CMD:DONE")
    assert not logic._AUDIT_END_LOCK.locked()
    assert scan(env, "ID:2") == AUDIT_SCAN        # a scan still counts, the audit is open


def test_the_watchdog_stays_away_while_the_park_runs(env, monkeypatch):
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    seen = []
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        session()["last_activity_ts"] = time.time() - (state.AUDIT_IDLE_TIMEOUT_SECONDS + 60)
        app_module._check_audit_idle_timeout()
        seen.append(session()["active"])
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    assert park(env, ids, audit_id)["parked"] == ids
    assert seen == [True, True]
    assert state.AUDIT_LAST_END["why"] == "done"


def test_a_refused_yes_counts_as_a_person_at_the_audit(env):
    """A question left open for half an hour, then a Yes that a blip refuses: the
    audit runs on, and mustn't time out a moment later with its scans."""
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    session()["last_activity_ts"] = time.time() - (state.AUDIT_IDLE_TIMEOUT_SECONDS - 1)
    env["fake"].list_reads_fail = True
    assert park(env, ids, audit_id)["success"] is False
    session_ts = session()["last_activity_ts"]
    assert time.time() - session_ts < 60
    app_module._check_audit_idle_timeout()
    assert session()["active"] is True


def test_undo_stays_refused_until_the_park_is_over(env, monkeypatch):
    """The park ends the audit in its own request for this reason."""
    _two_missing(env)
    _q, ids, audit_id = _asked(env)
    answers = []
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        answers.append(env["client"].post("/api/undo", json={}).get_json())
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    park(env, ids, audit_id)
    assert all("off while an audit is running" in a["msg"] for a in answers), answers
    assert env["client"].post("/api/undo", json={}).get_json()["requires_confirm"] is True


# ---------------------------------------------------------------------------
# Cancel, and what didn't change
# ---------------------------------------------------------------------------

def test_audit_cancel_does_not_park_missing_spools(env):
    """Cancel = user bailing out. It never parks, however many are missing."""
    _two_missing(env)
    assert "audit_ended" in scan(env, "CMD:CANCEL")
    assert no_writes(env) and state.UNDO_STACK == []
    assert spools(env)[2]["location"] == "LR-MDB-1"


def test_fcc_pre_audit_location_is_system_managed():
    """The note must be in SYSTEM_MANAGED_EXTRAS so user-driven edit surfaces
    (wizard, vendor edit, manufacturer edit) can't clobber it during a save."""
    from spoolman_api import SYSTEM_MANAGED_EXTRAS
    assert 'fcc_pre_audit_location' in SYSTEM_MANAGED_EXTRAS


def test_required_spool_extras_includes_fcc_pre_audit_location():
    """The park PATCHes extra.fcc_pre_audit_location. If that field isn't in
    REQUIRED_SPOOL_EXTRAS, Spoolman 400s the write with `Unknown extra field` and
    the park fails per spool (Derek 2026-05-16 prod break)."""
    from spoolman_api import REQUIRED_SPOOL_EXTRAS
    keys = {entry[0] for entry in REQUIRED_SPOOL_EXTRAS}
    assert 'fcc_pre_audit_location' in keys


def test_an_old_bare_note_that_looks_like_a_number_stays_text():
    """An older FCC wrote the bare place. Read back parsed and re-sent by any
    full-extras write, "123" went out as a number, and Spoolman refuses the PATCH."""
    clean = spoolman_api.sanitize_outbound_data({"extra": {"fcc_pre_audit_location": "123"}})
    assert clean["extra"]["fcc_pre_audit_location"] == '"123"'


def test_audit_summary_includes_display_labels_not_bare_ids():
    """18.2 follow-up — the Activity Log Missing/Extra summary lines must include
    the spool's display label (brand + material + color), not just bare IDs. A row
    with no stored data (a session built by hand) is read for it."""
    state.AUDIT_SESSION.update({'active': True, 'location_id': "LR-MDB-1", 'expected_items': [101, 102],
                                'scanned_items': [101], 'rogue_items': [999]})
    log_calls = []

    def _fake_get_spool(sid):
        if sid == 102:
            return {"id": 102, "filament": {"name": "Galaxy Black", "material": "PLA"}}
        if sid == 999:
            return {"id": 999, "filament": {"name": "Mystery", "material": "PETG"}}
        return None

    def _fake_format(spool):
        fil = (spool or {}).get('filament') or {}
        return {"text": f"{fil.get('material','?')} ({fil.get('name','?')})", "color": "#fff"}

    with patch.object(logic.spoolman_api, "get_spool", side_effect=_fake_get_spool), \
         patch.object(logic.spoolman_api, "format_spool_display", side_effect=_fake_format), \
         patch.object(state, "add_log_entry", side_effect=lambda *a, **k: log_calls.append(a)):
        logic.process_audit_scan({'type': 'command', 'cmd': 'cancel'})

    summary = next((c[0] for c in log_calls if 'Audit Report' in c[0]), None)
    assert summary, f"No 'Audit Report' line emitted; got {[c[0] for c in log_calls]}"
    assert "#102" in summary and "PLA" in summary and "Galaxy Black" in summary, summary
    assert "#999" in summary and "PETG" in summary, summary


def test_audit_summary_falls_back_to_bare_id_on_lookup_miss():
    """If get_spool returns None / blows up, the summary still renders with `#N`
    for that entry instead of erroring out."""
    state.AUDIT_SESSION.update({'active': True, 'location_id': "LR-MDB-1", 'expected_items': [101, 102],
                                'scanned_items': [101], 'rogue_items': []})
    log_calls = []
    with patch.object(logic.spoolman_api, "get_spool", return_value=None), \
         patch.object(state, "add_log_entry", side_effect=lambda *a, **k: log_calls.append(a)):
        logic.process_audit_scan({'type': 'command', 'cmd': 'cancel'})
    summary = next((c[0] for c in log_calls if 'Audit Report' in c[0]), None)
    assert summary, "No Audit Report emitted"
    assert "#102" in summary, f"Bare-id fallback missing: {summary!r}"


def test_resolve_scan_recognizes_cmd_cancel():
    """18.2 Part B follow-up — CMD:CANCEL is the safe-bail counterpart to CMD:DONE
    for audit mode. Without parser support the deck-button toggle had no way to end
    an audit without parking (Derek 2026-05-16 prod break)."""
    with patch.object(logic.locations_db, "load_locations_list", return_value=[]):
        r = logic.resolve_scan("CMD:CANCEL")
    assert r == {'type': 'command', 'cmd': 'cancel'}


def test_audit_idle_timeout_auto_cancels_stale_session(monkeypatch):
    """A browser-tab close, crash, or abandoned session leaves
    AUDIT_SESSION.active=True with no real user behind the wheel.
    _check_audit_idle_timeout() heals this on the next /api/logs poll
    (≤ 5s after the AUDIT_IDLE_TIMEOUT_SECONDS window expires)."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [101, 102],
        "scanned_items": [],
        "rogue_items": [],
        "last_activity_ts": time.time() - (state.AUDIT_IDLE_TIMEOUT_SECONDS + 60),
    })
    log_calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda *a, **k: log_calls.append(a))

    app_module._check_audit_idle_timeout()

    assert state.AUDIT_SESSION["active"] is False, "Stale session should auto-cancel"
    # A log entry explains what happened (so the user notices on next refresh).
    assert any("auto-cancelled" in (c[0] or "") for c in log_calls), (
        f"Expected an auto-cancel log entry; got {log_calls}"
    )


def test_audit_idle_timeout_leaves_fresh_session_alone():
    """Active session with recent activity must NOT get cancelled."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [101],
        "scanned_items": [],
        "rogue_items": [],
        "last_activity_ts": time.time() - 30,   # 30s old — way under the 30-min window
    })
    app_module._check_audit_idle_timeout()
    assert state.AUDIT_SESSION["active"] is True


def test_audit_idle_timeout_seeds_missing_timestamp():
    """Legacy session from a process that pre-dates the watchdog (no
    last_activity_ts at all) should NOT get cancelled on the first check — instead
    the timer starts from now. Otherwise the watchdog would nuke any session whose
    timestamp got lost in a state migration."""
    state.AUDIT_SESSION.update({
        "active": True,
        "location_id": "LR-MDB-1",
        "expected_items": [101],
        "scanned_items": [],
        "rogue_items": [],
        "last_activity_ts": 0.0,   # no timestamp at all
    })
    app_module._check_audit_idle_timeout()
    assert state.AUDIT_SESSION["active"] is True
    assert state.AUDIT_SESSION["last_activity_ts"] > 0
