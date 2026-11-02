"""Undo Last Move on an audit's park, build spec section 6 of Group 58.

A park can be 30 spools nobody has looked at for a while, and the natural next step
after an audit is to find one and move it, or delete one that is truly gone. So a
record with `only_if_at` puts a spool back only while it is still at Unknown, right
before each write. Ordinary Undo keeps its behaviour, pinned at the bottom.

Everything here is the real /api/identify_scan, /api/audit/park and /api/undo on
the real update_spool over tests/spoolman_extra_fake.SpoolmanHTTPFake.
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
from spoolman_extra_fake import _Resp  # noqa: E402
from test_audit_session_58 import (  # noqa: E402,F401
    add_spool, env, log_text, park, scan, session, start,
)


@pytest.fixture(autouse=True)
def _own_undo_stack(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-11-02")


def spools(env):
    return env["fake"].records["spool"]


def extra_of(env, sid):
    return {k: json.loads(v) for k, v in env["fake"].extra("spool", sid).items()}


def ask_undo(env):
    return env["client"].post("/api/undo", json={}).get_json()


def yes_undo(env, asked=None):
    asked = asked or ask_undo(env)
    assert asked.get("requires_confirm") is True, asked
    return env["client"].post("/api/undo", json={"confirm": True, "undo_id": asked["undo_id"],
                                                 "confirmed_toolheads": []}).get_json()


def _park_box(env, count=2, place="LR-MDB-1", first=1):
    """A box audit that parks `count` spools in slots 1.. and leaves the audit over."""
    for n in range(count):
        add_spool(env, first + n, place, container_slot=str(n + 1))
    start(env, place)
    assert park(env, today="2026-11-02")["parked"] == list(range(first, first + count))
    env["fake"].patches.clear()
    env["logs"].clear()


# ---------------------------------------------------------------------------
# The batch comes back
# ---------------------------------------------------------------------------

def test_thirty_spools_come_back_on_one_yes_with_their_slots_and_trails(env):
    env["rows"].append({"LocationID": "BIG-BOX", "Name": "Big Box", "Type": "Dryer Box", "Max Spools": "30"})
    env["rows"].append({"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"})
    before = {}
    for sid in range(1, 31):
        add_spool(env, sid, "BIG-BOX", container_slot=str(sid),
                  physical_source="BIG-BOX" if sid % 2 else "CR-CT-1",
                  physical_source_slot=str(sid) if sid % 2 else "",
                  fcc_pre_box_location="CR-CT-1-R1" if sid == 7 else "")
        before[sid] = extra_of(env, sid)
    start(env, "BIG-BOX")
    assert park(env, today="2026-11-02")["parked"] == list(range(1, 31))
    assert {spools(env)[sid]["location"] for sid in range(1, 31)} == {"UNKNOWN"}
    assert extra_of(env, 12)["physical_source"] == ""

    asked = ask_undo(env)
    assert asked["msg"] == "Undo: put 30 spools back in BIG-BOX (parked at Unknown by its audit)?"
    env["fake"].patches.clear()
    env["logs"].clear()
    done = yes_undo(env, asked)
    assert done["success"] is True and sorted(done["restored"]) == list(range(1, 31))
    assert done["msg"] == "↩️ Undo: 30 spools are back in BIG-BOX (parked at Unknown by its audit)."
    assert done["left_alone"] == [] and done["dropped"] == []
    assert len(env["fake"].patches) == 30
    assert len(log_text(env)) == 1                    # one line, however many spools
    for sid in range(1, 31):
        assert spools(env)[sid]["location"] == "BIG-BOX"
        got = extra_of(env, sid)
        for key in ("container_slot", "physical_source", "physical_source_slot", "fcc_pre_box_location"):
            assert got.get(key, "") == before[sid].get(key, ""), (sid, key)
        assert got.get("fcc_pre_audit_location", "") == ""      # an Undo clears the note
    assert state.UNDO_STACK == []


def test_a_box_read_is_one_read_per_box(env):
    _park_box(env, 4)
    env["fake"].gets.clear()
    done = yes_undo(env)
    assert done["success"] is True
    assert env["fake"].gets.count("/api/v1/spool") == 1, env["fake"].gets


def test_three_or_fewer_use_the_sentence_every_move_uses(env):
    _park_box(env, 3)
    assert ask_undo(env)["msg"] == ("Undo: put #1 back in LR-MDB-1 slot 1, #2 back in LR-MDB-1 slot 2 "
                                    "and #3 back in LR-MDB-1 slot 3?")
    done = yes_undo(env)
    assert done["msg"].startswith("↩️ Undo: #1 Some Brand PLA (Red) is back in LR-MDB-1 slot 1")
    assert "they had been moved to UNKNOWN" in done["msg"]


def test_a_spool_back_in_its_slot_is_on_the_next_audits_list(env):
    _park_box(env, 2)
    yes_undo(env)
    start(env, "LR-MDB-1")
    assert session()["expected_items"] == [1, 2]


def test_a_later_move_on_top_is_what_undo_asks_about(env):
    _park_box(env, 2)
    logic._push_undo({"target": "SHELF-1", "moves": {9: "CR"}, "extras": {}, "labels": {}, "summary": "x",
                      "origin": ""})
    add_spool(env, 9, "SHELF-1")
    assert "#9 back in CR" in ask_undo(env)["msg"]


def test_a_batch_undo_never_joins_the_scan_buffer(env):
    """Its origin is 'audit': 'buffer' would push restored spools into it."""
    _park_box(env, 2)
    yes_undo(env)
    assert state.GLOBAL_BUFFER == []


def test_undo_stays_refused_while_a_new_audit_runs(env):
    _park_box(env, 2)
    scan(env, "CMD:AUDIT")
    assert "off while an audit is running" in ask_undo(env)["msg"]
    assert len(state.UNDO_STACK) == 1


# ---------------------------------------------------------------------------
# A spool that moved on
# ---------------------------------------------------------------------------

def test_a_spool_moved_on_is_left_alone_and_named(env):
    """Found and put on a shelf: Undo used to drag it back to the box."""
    _park_box(env, 2)
    spools(env)[1].update(location="CR-CT-1-R1")
    asked = ask_undo(env)
    assert asked["msg"] == "Undo: put #2 back in LR-MDB-1 slot 2? Left where it is now: #1 at CR-CT-1-R1."
    done = yes_undo(env, asked)
    assert done["success"] is True
    assert done["restored"] == [2]
    assert done["left_alone"] == [{"id": 1, "where": "CR-CT-1-R1"}]
    assert "Left where it is now: #1 at CR-CT-1-R1." in done["msg"]
    assert spools(env)[1]["location"] == "CR-CT-1-R1" and [p[1] for p in env["fake"].patches] == [2]
    assert spools(env)[2]["location"] == "LR-MDB-1"
    assert any("Left where it is now: #1" in m for m in log_text(env))
    assert not any(c == "ERROR" for _m, c, _ in env["logs"]), env["logs"]


def test_a_spool_moved_on_says_its_slot_too(env):
    _park_box(env, 2)
    spools(env)[1].update(location="LR-MDB-2", extra={"container_slot": '"3"'})
    assert yes_undo(env)["left_alone"] == [{"id": 1, "where": "LR-MDB-2 slot 3"}]


def test_a_spool_moved_on_during_the_undo_is_left_alone_too(env, monkeypatch):
    """The question said it would go back; the check right before the write wins."""
    _park_box(env, 2)
    asked = ask_undo(env)
    assert "#1 back" in asked["msg"]
    real = logic.perform_undo

    def moved_after_the_question(expected_id=None):
        spools(env)[1].update(location="SHELF-1")
        return real(expected_id=expected_id)

    monkeypatch.setattr(logic, "perform_undo", moved_after_the_question)
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [2]
    assert done["left_alone"] == [{"id": 1, "where": "SHELF-1"}]
    assert spools(env)[1]["location"] == "SHELF-1"


def test_more_spools_count_and_name_those_left_alone(env):
    _park_box(env, 6)
    spools(env)[1].update(location="SHELF-1")
    assert ask_undo(env)["msg"] == ("Undo: put 5 spools back in LR-MDB-1 (parked at Unknown by its audit)? "
                                    "Left where it is now: #1 at SHELF-1.")


def test_a_long_left_alone_list_stops_at_three_names(env):
    _park_box(env, 6)
    for sid in (1, 2, 3, 4, 5):
        spools(env)[sid].update(location="SHELF-1")
    assert ask_undo(env)["msg"] == ("Undo: put #6 back in LR-MDB-1 slot 6? Left where they are now: #1 at SHELF-1, "
                                    "#2 at SHELF-1, #3 at SHELF-1 and 2 more.")


def test_the_question_doesnt_ask_about_a_head_the_guard_leaves_alone(env, monkeypatch):
    """Its question and its guard agree: a parked spool that reached a printing head
    since isn't moved, so nothing mid-print is asked about."""
    _park_box(env, 2)
    spools(env)[1].update(location="XL-1")
    asked_heads = []

    def printing(head, printer_map=None):
        asked_heads.append(head)
        return {"toolhead": head, "printer_name": "Big Printer", "state": "PRINTING"}

    monkeypatch.setattr(logic, "_active_print_info_for_location", printing)
    asked = ask_undo(env)
    assert asked["confirm_type"] == "undo" and asked["active_prints"] == [] and asked_heads == []
    done = yes_undo(env, asked)
    assert done["left_alone"] == [{"id": 1, "where": "XL-1"}] and spools(env)[1]["location"] == "XL-1"
    assert done["success"] is True


def test_every_spool_moved_on_still_clears_the_record(env):
    """Or it would sit on the stack burying every older move."""
    add_spool(env, 7, "SHELF-1")
    logic._push_undo({"target": "SHELF-1", "moves": {7: "CR"}, "extras": {}, "labels": {}, "summary": "older",
                      "origin": ""})
    _park_box(env, 2)
    spools(env)[1].update(location="SHELF-1")
    spools(env)[2].update(location="SHELF-1")
    asked = ask_undo(env)
    assert asked["msg"].startswith("Undo: nothing from this audit is at Unknown any more")
    assert "Left where they are now: #1 at SHELF-1 and #2 at SHELF-1." in asked["msg"]
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [] and env["fake"].patches == []
    assert done["msg"] == ("↩️ Undo: nothing went back. Left where they are now: #1 at SHELF-1 "
                           "and #2 at SHELF-1.")
    assert "#7 back in CR" in ask_undo(env)["msg"]


# ---------------------------------------------------------------------------
# A deleted spool
# ---------------------------------------------------------------------------

def test_a_deleted_spool_doesnt_block_undo(env):
    """Spoolman's 404 body read as "unreadable", so the record answered "Couldn't
    read #1" for good and buried every older one. Deleting a truly lost spool is the
    natural next step after an audit."""
    _park_box(env, 2)
    del spools(env)[1]
    asked = ask_undo(env)
    assert asked["requires_confirm"] is True and asked["msg"] == "Undo: put #2 back in LR-MDB-1 slot 2?"
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [2] and done["dropped"] == [1]
    assert "#1 is no longer in Spoolman." in done["msg"]
    assert [p[1] for p in env["fake"].patches] == [2]
    assert 1 not in spools(env)


def test_every_spool_deleted_clears_the_record(env):
    _park_box(env, 2)
    spools(env).clear()
    done = yes_undo(env)
    assert done["success"] is True and done["dropped"] == [1, 2] and done["restored"] == []
    assert done["msg"] == "↩️ Undo: nothing went back. #1 and #2 are no longer in Spoolman."
    assert state.UNDO_STACK == []


# ---------------------------------------------------------------------------
# A slot taken
# ---------------------------------------------------------------------------

def test_a_slot_taken_isnt_doubled(env):
    _park_box(env, 2)
    add_spool(env, 9, "LR-MDB-1", container_slot="1")
    done = yes_undo(env)
    assert done["success"] is False
    assert done["restored"] == [2]
    assert done["msg"] == "Undo could not put back #1 (LR-MDB-1 slot 1 holds #9)."
    assert spools(env)[1]["location"] == "UNKNOWN" and spools(env)[2]["location"] == "LR-MDB-1"
    assert extra_of(env, 1)["fcc_pre_audit_location"] == "LR-MDB-1:1@2026-11-02"       # its note stays
    assert [p[1] for p in env["fake"].patches] == [2]
    errors = [m for m, c, _ in env["logs"] if c == "ERROR"]
    assert any("not putting Spool #1 back in LR-MDB-1 slot 1" in m and "holds #9" in m for m in errors), errors
    assert any("Undo partly failed" in m for m in errors), errors


def test_a_slot_held_by_a_spool_deployed_from_it_is_taken_too(env):
    """The one slot rule: a loaded spool still physically holds its slot."""
    _park_box(env, 1)
    add_spool(env, 9, "XL-1", physical_source="LR-MDB-1", physical_source_slot="1")
    done = yes_undo(env)
    assert done["success"] is False and "LR-MDB-1 slot 1 holds #9" in done["msg"]
    assert spools(env)[1]["location"] == "UNKNOWN"


def test_a_single_slot_boxs_blank_slot_is_its_slot(env):
    env["rows"].append({"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1"})
    add_spool(env, 1, "PM-DB-1")
    start(env, "PM-DB-1")
    park(env)
    add_spool(env, 9, "PM-DB-1", container_slot="1")
    done = yes_undo(env)
    assert done["success"] is False and "PM-DB-1 slot 1 holds #9" in done["msg"]
    assert spools(env)[1]["location"] == "UNKNOWN"


def test_a_slot_on_another_box_in_the_room_is_no_claim(env):
    """A Room's read lists its rows' spools, each with its own slot."""
    add_spool(env, 1, "LR", container_slot="2")
    start(env, "LR")
    park(env)
    add_spool(env, 9, "LR-MDB-1", container_slot="2")
    assert yes_undo(env)["success"] is True
    assert spools(env)[1]["location"] == "LR"


def test_a_place_with_no_row_is_checked_like_any_other(env):
    """"A place with spools but no row still audits", and its slot can be taken."""
    add_spool(env, 1, "GARAGE-BIN", container_slot="2")
    add_spool(env, 2, "GARAGE-BIN", container_slot="3")
    start(env, "GARAGE-BIN")
    park(env)
    add_spool(env, 9, "GARAGE-BIN", container_slot="2")
    done = yes_undo(env)
    assert done["restored"] == [2] and "GARAGE-BIN slot 2 holds #9" in done["msg"]
    assert spools(env)[2]["location"] == "GARAGE-BIN"


def test_a_spool_with_no_slot_needs_no_box_read(env):
    add_spool(env, 1, "SHELF-1")
    start(env, "SHELF-1")
    park(env)
    env["fake"].gets.clear()
    assert yes_undo(env)["success"] is True
    assert "/api/v1/spool" not in env["fake"].gets


def test_a_box_that_cant_be_read_writes_nothing_and_costs_one_read(env):
    _park_box(env, 3)
    asked = ask_undo(env)
    env["fake"].list_reads_fail = True
    env["fake"].gets.clear()
    done = yes_undo(env, asked)
    assert done["success"] is False and done["restored"] == []
    assert env["fake"].patches == []
    assert env["fake"].gets.count("/api/v1/spool") == 1
    assert "LR-MDB-1 could not be read from Spoolman" in done["msg"]


# ---------------------------------------------------------------------------
# A timeout
# ---------------------------------------------------------------------------

def test_a_timeout_writes_nothing_and_the_undo_is_still_there(env):
    _park_box(env, 2)
    env["fake"].down = True
    asked = ask_undo(env)
    assert asked["success"] is False and "requires_confirm" not in asked
    assert asked["msg"] == ("Couldn't read #1 and #2 from Spoolman, so FCC can't tell where they are now. "
                            "Nothing was undone; try again in a moment.")
    assert env["fake"].patches == [] and len(state.UNDO_STACK) == 1

    env["fake"].down = False
    assert yes_undo(env)["success"] is True


def test_a_timeout_on_the_yes_writes_nothing_and_the_undo_is_still_there(env):
    _park_box(env, 2)
    asked = ask_undo(env)
    env["fake"].down = True
    res = env["client"].post("/api/undo", json={"confirm": True, "undo_id": asked["undo_id"],
                                                "confirmed_toolheads": []}).get_json()
    assert res["success"] is False and "Nothing was undone" in res["msg"]
    assert env["fake"].patches == [] and len(state.UNDO_STACK) == 1


def test_a_spool_unreadable_right_before_its_write_isnt_written_and_counts_as_failed(env, monkeypatch):
    """Readable for the question, then Spoolman stops answering for it."""
    _park_box(env, 2)
    asked = ask_undo(env)
    real_undo = logic.perform_undo
    real_read = spoolman_api.get_spool_answer

    def blip_in_the_undo(expected_id=None):
        monkeypatch.setattr(spoolman_api, "get_spool_answer",
                            lambda sid: (None, False) if sid == 1 else real_read(sid))
        return real_undo(expected_id=expected_id)

    monkeypatch.setattr(logic, "perform_undo", blip_in_the_undo)
    done = yes_undo(env, asked)
    assert done["success"] is False and done["restored"] == [2]
    assert done["msg"] == "Undo could not put back #1 (it could not be read from Spoolman)."
    assert [p[1] for p in env["fake"].patches] == [2]
    assert spools(env)[1]["location"] == "UNKNOWN"


def test_a_body_that_isnt_json_counts_as_unreadable(env, monkeypatch):
    _park_box(env, 1)

    class _NotJson:
        status_code = 200
        ok = True

        def json(self):
            raise ValueError("not JSON")

    real_get = env["fake"].get

    def get(url, timeout=None, **kw):
        return _NotJson() if url.rstrip("/").endswith("/spool/1") else real_get(url, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "get", get)
    assert ask_undo(env)["success"] is False
    assert env["fake"].patches == []


# ---------------------------------------------------------------------------
# What it writes, and how it says so
# ---------------------------------------------------------------------------

def test_a_rejected_restore_is_a_failure_and_the_rest_go_back(env, monkeypatch):
    _park_box(env, 2)
    real = env["fake"].patch

    def refuse_1(url, json=None, timeout=None, **kw):        # noqa: A002
        if url.rstrip("/").endswith("/1"):
            return _Resp(400, {"message": "<b>nope</b>"})
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", refuse_1)
    done = yes_undo(env)
    assert done["success"] is False and done["restored"] == [2]
    assert spools(env)[1]["location"] == "UNKNOWN"
    assert "<b>nope</b>" not in "\n".join(log_text(env)) and "&lt;b&gt;nope" in "\n".join(log_text(env))


def test_a_spool_name_in_undos_line_is_escaped(env):
    add_spool(env, 1, "LR-MDB-1", name="<i>Blue")
    start(env, "LR-MDB-1")
    park(env)
    env["logs"].clear()
    done = yes_undo(env)
    line = log_text(env)[0]
    assert "<I>" not in line and "&lt;I&gt;Blue" in line
    assert "<I>Blue" in done["msg"]              # the toast draws plain text


def test_what_stayed_and_what_failed_are_both_said(env):
    _park_box(env, 3)
    add_spool(env, 9, "LR-MDB-1", container_slot="1")
    spools(env)[2].update(location="SHELF-1")
    del spools(env)[3]
    done = yes_undo(env)
    assert done["success"] is False
    assert done["msg"] == ("Undo could not put back #1 (LR-MDB-1 slot 1 holds #9). Left where it is now: "
                           "#2 at SHELF-1. #3 is no longer in Spoolman.")
    assert done["left_alone"] == [{"id": 2, "where": "SHELF-1"}] and done["dropped"] == [3]


# ---------------------------------------------------------------------------
# Ordinary Undo doesn't change
# ---------------------------------------------------------------------------

def _ordinary_move(env, *sids):
    """A real engine move, whose record has no `only_if_at`."""
    for sid in sids:
        add_spool(env, sid, "CR-CT-1-R1")
    assert logic.perform_smart_move("SHELF-1", list(sids), origin="manual")["status"] == "success"
    env["fake"].patches.clear()
    assert "only_if_at" not in state.UNDO_STACK[-1]


def test_an_ordinary_undo_still_restores_blindly(env):
    """The guards are the audit's alone: every other move's Undo shares this code."""
    _ordinary_move(env, 1)
    spools(env)[1].update(location="CR")
    done = yes_undo(env)
    assert done["success"] is True and spools(env)[1]["location"] == "CR-CT-1-R1"
    assert "left_alone" not in done and "dropped" not in done


def test_an_ordinary_undo_still_says_every_spool(env):
    _ordinary_move(env, 1, 2, 3, 4, 5)
    assert ask_undo(env)["msg"] == ("Undo: put #1 back in CR-CT-1-R1, #2 back in CR-CT-1-R1, #3 back in "
                                    "CR-CT-1-R1, #4 back in CR-CT-1-R1 and #5 back in CR-CT-1-R1?")
    done = yes_undo(env)
    assert done["msg"].count("is back in CR-CT-1-R1") == 5


def test_an_ordinary_undo_with_a_deleted_spool_still_refuses(env):
    _ordinary_move(env, 1)
    del spools(env)[1]
    asked = ask_undo(env)
    assert asked["success"] is False
    assert asked["msg"] == ("Couldn't read #1 from Spoolman, so FCC can't tell whether this undo changes a "
                            "printing head. Nothing was undone; try again in a moment.")


def test_an_ordinary_undo_still_asks_about_a_head_a_spool_reached(env, monkeypatch):
    _ordinary_move(env, 1)
    spools(env)[1].update(location="XL-1")
    monkeypatch.setattr(logic, "_active_print_info_for_location",
                        lambda head, printer_map=None: {"toolhead": head, "printer_name": "Big Printer",
                                                        "state": "PRINTING"})
    asked = ask_undo(env)
    assert asked["confirm_type"] == "active_print" and asked["active_prints"][0]["toolhead"] == "XL-1"


def test_an_ordinary_records_slot_isnt_checked(env):
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    assert logic.perform_smart_move("SHELF-1", [1], origin="manual")["status"] == "success"
    add_spool(env, 9, "LR-MDB-1", container_slot="1")
    done = yes_undo(env)
    assert done["success"] is True and spools(env)[1]["location"] == "LR-MDB-1"
