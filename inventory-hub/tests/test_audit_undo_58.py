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
    lines = errors(env)
    assert any("not putting Spool #1 back in LR-MDB-1 slot 1" in m and "holds #9" in m for m in lines), lines
    assert any("Undo partly failed" in m for m in lines), lines
    assert done["retry"] == [] and state.UNDO_STACK == []     # final: it would bury every older record


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
    assert len(state.UNDO_STACK) == 1


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


def test_a_big_batch_that_cant_be_read_is_counted_in_the_refusal(env):
    """A toast names thirty spools no better than it says thirty."""
    _park_box(env, 6)
    env["fake"].down = True
    assert ask_undo(env)["msg"] == ("Couldn't read 6 spools from Spoolman, so FCC can't tell where they are now. "
                                    "Nothing was undone; try again in a moment.")


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
    assert done["msg"] == ("Undo could not put back #1 (could not be read from Spoolman). "
                           "Press Undo Last Move again to try it again.")
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
# A failure that says nothing about the spool leaves Undo available (finding 1)
# ---------------------------------------------------------------------------

def _refuse_writes(env, monkeypatch, *sids, status=500, message="nope (test)"):
    """Spoolman refuses these spools' PATCHes. Returns the real patch, to end it."""
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        if int(url.rstrip("/").rsplit("/", 1)[1]) in sids:
            return _Resp(status, {"message": message})
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    return real


def _during_the_undo(monkeypatch, begin):
    """`begin` runs once the Yes has passed the route's own re-read: the blip lands
    inside perform_undo, where a real one would. Returns the real perform_undo."""
    real = logic.perform_undo

    def inside(expected_id=None):
        begin()
        return real(expected_id=expected_id)

    monkeypatch.setattr(logic, "perform_undo", inside)
    return real


def _blip_reads_of(env, monkeypatch, *sids):
    """These spools' own reads time out during the Undo. Returns the end of the blip."""
    real_get = env["fake"].get
    blip = {"on": False}
    ends = tuple(f"/spool/{sid}" for sid in sids)

    def get(url, timeout=None, **kw):
        if blip["on"] and url.rstrip("/").endswith(ends):
            raise TimeoutError("read timed out (test)")
        return real_get(url, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "get", get)
    real_undo = _during_the_undo(monkeypatch, lambda: blip.update(on=True))

    def end():
        blip["on"] = False
        monkeypatch.setattr(logic, "perform_undo", real_undo)

    return end


def errors(env):
    return [m for m, c, _ in env["logs"] if c == "ERROR"]


def test_a_box_read_that_fails_keeps_the_whole_batch_on_undo(env):
    """The review's red: the record was used up before its checks, so one failed list
    read lost every spool's way back while the answer said to try again."""
    _park_box(env, 3)
    asked = ask_undo(env)
    env["fake"].list_reads_fail = True
    done = yes_undo(env, asked)
    assert done["success"] is False and done["restored"] == [] and done["retry"] == [1, 2, 3]
    assert env["fake"].patches == []
    assert "Press Undo Last Move again to try them again." in done["msg"]

    env["fake"].list_reads_fail = False
    again = ask_undo(env)
    assert again["requires_confirm"] is True and again["undo_id"] == asked["undo_id"]
    assert again["msg"] == asked["msg"]
    done = yes_undo(env, again)
    assert done["success"] is True and done["restored"] == [1, 2, 3] and done["retry"] == []
    assert {spools(env)[sid]["location"] for sid in (1, 2, 3)} == {"LR-MDB-1"}
    assert extra_of(env, 2)["container_slot"] == "2"
    assert state.UNDO_STACK == []                     # nothing left to retry


def test_a_box_that_cant_be_read_is_said_once_however_big_the_batch(env):
    env["rows"].append({"LocationID": "BIG-BOX", "Type": "Dryer Box", "Max Spools": "30"})
    _park_box(env, 30, place="BIG-BOX")
    asked = ask_undo(env)
    env["fake"].list_reads_fail = True
    done = yes_undo(env, asked)
    assert done["msg"].count("could not be read from Spoolman") == 1
    assert done["msg"].count("BIG-BOX") == 1
    assert done["msg"].startswith("Undo could not put back 30 spools (BIG-BOX could not be read from Spoolman (")
    assert done["msg"].endswith("Press Undo Last Move again to try them again.")
    assert len(errors(env)) == 1 and errors(env)[0].count("could not be read from Spoolman") == 1
    assert len(env["logs"]) == 1                      # the 50-line log keeps its other lines
    assert len(state.UNDO_STACK[-1]["moves"]) == 30


def test_a_spool_with_no_slot_still_goes_back_when_a_box_cant_be_read(env):
    """Its write needs no read of the box, so the failed read says nothing about it."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    park(env)
    asked = ask_undo(env)
    env["fake"].list_reads_fail = True
    done = yes_undo(env, asked)
    assert done["restored"] == [2] and done["retry"] == [1]
    assert list(state.UNDO_STACK[-1]["moves"]) == [1]


def test_a_spool_read_blip_mid_batch_keeps_only_that_spool(env, monkeypatch):
    _park_box(env, 3)
    asked = ask_undo(env)
    end = _blip_reads_of(env, monkeypatch, 2)
    done = yes_undo(env, asked)
    assert done["success"] is False and done["restored"] == [1, 3] and done["retry"] == [2]
    assert done["msg"] == ("Undo could not put back #2 (could not be read from Spoolman). "
                           "Press Undo Last Move again to try it again.")
    assert spools(env)[2]["location"] == "UNKNOWN"
    (record,) = state.UNDO_STACK
    assert list(record["moves"]) == [2]

    end()
    env["fake"].patches.clear()
    again = ask_undo(env)
    assert again["undo_id"] == asked["undo_id"]
    assert again["msg"] == "Undo: put #2 back in LR-MDB-1 slot 2?"     # exactly those
    done = yes_undo(env, again)
    assert done["success"] is True and done["restored"] == [2]
    assert spools(env)[2]["location"] == "LR-MDB-1" and extra_of(env, 2)["container_slot"] == "2"
    assert [p[1] for p in env["fake"].patches] == [2]
    assert state.UNDO_STACK == []


def test_an_outage_mid_batch_is_said_once_too(env, monkeypatch):
    _park_box(env, 6)
    asked = ask_undo(env)
    _during_the_undo(monkeypatch, lambda: setattr(env["fake"], "down", True))
    done = yes_undo(env, asked)
    assert done["msg"] == ("Undo could not put back 6 spools (could not be read from Spoolman). "
                           "Press Undo Last Move again to try them again.")
    assert len(errors(env)) == 1 and len(env["logs"]) == 1
    assert list(state.UNDO_STACK[-1]["moves"]) == [1, 2, 3, 4, 5, 6]


def test_a_write_that_fails_mid_batch_keeps_only_that_spool(env, monkeypatch):
    _park_box(env, 3)
    asked = ask_undo(env)
    real_patch = _refuse_writes(env, monkeypatch, 2)
    done = yes_undo(env, asked)
    assert done["success"] is False and done["restored"] == [1, 3] and done["retry"] == [2]
    assert spools(env)[2]["location"] == "UNKNOWN"
    assert "Press Undo Last Move again to try it again." in done["msg"] and "nope (test)" in done["msg"]
    assert any("Undo partly failed" in m and "nope (test)" in m for m in errors(env)), errors(env)

    monkeypatch.setattr(spoolman_api.requests, "patch", real_patch)
    again = ask_undo(env)
    assert again["msg"] == "Undo: put #2 back in LR-MDB-1 slot 2?"
    assert yes_undo(env, again)["restored"] == [2]
    assert spools(env)[2]["location"] == "LR-MDB-1" and state.UNDO_STACK == []


def test_every_write_refused_is_one_sentence_and_the_batch_stays(env, monkeypatch):
    _park_box(env, 5)
    asked = ask_undo(env)
    _refuse_writes(env, monkeypatch, 1, 2, 3, 4, 5)
    done = yes_undo(env, asked)
    assert done["msg"].count("nope (test)") == 1 and "5 spools" in done["msg"]
    assert len(errors(env)) == 1
    assert list(state.UNDO_STACK[-1]["moves"]) == [1, 2, 3, 4, 5]


def test_a_write_that_times_out_and_didnt_land_stays_on_undo(env, monkeypatch):
    _park_box(env, 2)
    asked = ask_undo(env)

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        raise TimeoutError("connect timed out (test)")

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    done = yes_undo(env, asked)
    assert done["retry"] == [1, 2] and "connect timed out" in done["msg"]
    assert list(state.UNDO_STACK[-1]["moves"]) == [1, 2]


def test_a_write_that_raises_takes_no_other_spools_undo_with_it(env, monkeypatch):
    _park_box(env, 3)
    asked = ask_undo(env)
    real = logic._move_write

    def blow_up(sid, target, new_extra, unarchive=False):
        if sid == 2:
            raise RuntimeError("<boom>")
        return real(sid, target, new_extra, unarchive=unarchive)

    monkeypatch.setattr(logic, "_move_write", blow_up)
    done = yes_undo(env, asked)
    assert done["restored"] == [1, 3] and done["retry"] == [2]
    assert any("&lt;boom&gt;" in m for m in errors(env)) and not any("<boom>" in m for m in errors(env))
    assert list(state.UNDO_STACK[-1]["moves"]) == [2]


def test_a_one_spool_place_that_cant_be_read_is_asked_once_and_kept(env):
    """The occupants read (_blocked) fails like a box read: one read, one line, and
    the spools stay on Undo. A place re-typed since the park holds one spool now."""
    env["rows"].append({"LocationID": "TRAY-1", "Type": "Cart"})
    add_spool(env, 1, "TRAY-1")
    add_spool(env, 2, "TRAY-1")
    start(env, "TRAY-1")
    park(env)
    env["rows"][-1]["Type"] = "Tool Head"
    asked = ask_undo(env)
    env["fake"].list_reads_fail = True
    env["fake"].gets.clear()
    env["fake"].patches.clear()
    env["logs"].clear()
    done = yes_undo(env, asked)
    assert done["success"] is False and done["retry"] == [1, 2] and env["fake"].patches == []
    assert env["fake"].gets.count("/api/v1/spool") == 1
    assert done["msg"].count("TRAY-1 could not be read from Spoolman") == 1 and len(errors(env)) == 1
    assert list(state.UNDO_STACK[-1]["moves"]) == [1, 2]

    # Once it answers, its holder is a real claim: final, so the record goes.
    env["fake"].list_reads_fail = False
    done = yes_undo(env)
    assert done["restored"] == [1] and done["retry"] == []
    assert "#2 (it holds #1)" in done["msg"] and "Press Undo" not in done["msg"]
    assert state.UNDO_STACK == []


def test_a_one_spool_places_id_is_escaped_in_its_line(env):
    """A LocationID is outside text, and an audit's lines all go through the escape."""
    env["rows"].append({"LocationID": "<B>TRAY", "Type": "Cart"})
    add_spool(env, 1, "<B>TRAY")
    add_spool(env, 2, "<B>TRAY")
    start(env, "<B>TRAY")
    park(env)
    env["rows"][-1]["Type"] = "Tool Head"
    env["logs"].clear()
    done = yes_undo(env)
    assert "#2 (it holds #1)" in done["msg"]
    assert any("&lt;B&gt;TRAY — it holds #1" in m for m in errors(env)), errors(env)
    assert not any("<B>" in m for m, _c, _x in env["logs"]), env["logs"]


def test_a_slot_really_claimed_stays_out_of_the_retry_and_buries_nothing(env, monkeypatch):
    add_spool(env, 7, "SHELF-1")
    logic._push_undo({"target": "SHELF-1", "moves": {7: "CR"}, "extras": {}, "labels": {}, "summary": "older",
                      "origin": ""})
    _park_box(env, 2)
    add_spool(env, 9, "LR-MDB-1", container_slot="1")
    asked = ask_undo(env)
    real_patch = _refuse_writes(env, monkeypatch, 2)
    done = yes_undo(env, asked)
    assert done["retry"] == [2]
    assert done["msg"].startswith("Undo could not put back #1 (LR-MDB-1 slot 1 holds #9), #2 (")
    assert done["msg"].endswith("Press Undo Last Move again to try #2 again.")
    assert list(state.UNDO_STACK[-1]["moves"]) == [2] and len(state.UNDO_STACK) == 2

    monkeypatch.setattr(spoolman_api.requests, "patch", real_patch)
    assert yes_undo(env)["restored"] == [2]
    assert "#7 back in CR" in ask_undo(env)["msg"]     # the older move isn't buried


def test_nothing_left_to_retry_clears_the_record(env):
    add_spool(env, 7, "SHELF-1")
    logic._push_undo({"target": "SHELF-1", "moves": {7: "CR"}, "extras": {}, "labels": {}, "summary": "older",
                      "origin": ""})
    _park_box(env, 2)
    add_spool(env, 9, "LR-MDB-1", container_slot="1")
    done = yes_undo(env)
    assert done["success"] is False and done["retry"] == [] and "Press Undo" not in done["msg"]
    assert len(state.UNDO_STACK) == 1 and "#7 back in CR" in ask_undo(env)["msg"]


def test_a_retried_record_is_the_same_record_with_fewer_spools(env, monkeypatch):
    _park_box(env, 2)
    (before,) = state.UNDO_STACK
    asked = ask_undo(env)
    _refuse_writes(env, monkeypatch, 2)
    yes_undo(env, asked)
    (after,) = state.UNDO_STACK
    assert after is not before
    assert {k: v for k, v in after.items() if k != "moves"} == {k: v for k, v in before.items() if k != "moves"}
    assert after["moves"] == {2: "LR-MDB-1"}


def test_a_retry_goes_back_under_a_move_that_landed_meanwhile(env, monkeypatch):
    """Undo is last in, first out: a move made during the Undo stays the last move."""
    _park_box(env, 2)
    add_spool(env, 7, "SHELF-1")
    asked = ask_undo(env)
    real_get = env["fake"].get

    def move_lands_then_the_box_read_fails(url, timeout=None, **kw):
        if url.rstrip("/").endswith("/api/v1/spool"):
            logic._push_undo({"target": "SHELF-1", "moves": {7: "CR"}, "extras": {}, "labels": {},
                              "summary": "newer", "origin": ""})
            return _Resp(503, {"message": "unavailable (test)"})
        return real_get(url, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "get", move_lands_then_the_box_read_fails)
    assert yes_undo(env, asked)["retry"] == [1, 2]
    monkeypatch.setattr(spoolman_api.requests, "get", real_get)
    assert [r["summary"] for r in state.UNDO_STACK] == ["Parked 2 at Unknown by the audit of LR-MDB-1", "newer"]
    assert "#7 back in CR" in ask_undo(env)["msg"]


def test_a_retried_spool_found_since_clears_the_record(env, monkeypatch):
    _park_box(env, 2)
    asked = ask_undo(env)
    end = _blip_reads_of(env, monkeypatch, 2)
    yes_undo(env, asked)
    end()
    spools(env)[2].update(location="SHELF-1")
    done = yes_undo(env)
    assert done["success"] is True and done["left_alone"] == [{"id": 2, "where": "SHELF-1"}]
    assert state.UNDO_STACK == []


def test_a_blip_on_the_retry_keeps_it_again(env, monkeypatch):
    _park_box(env, 2)
    asked = ask_undo(env)
    env["fake"].list_reads_fail = True
    assert yes_undo(env, asked)["retry"] == [1, 2]
    assert yes_undo(env)["retry"] == [1, 2]
    assert len(state.UNDO_STACK) == 1
    env["fake"].list_reads_fail = False
    assert yes_undo(env)["restored"] == [1, 2] and state.UNDO_STACK == []


# ---------------------------------------------------------------------------
# A write that landed and timed out (finding 6)
# ---------------------------------------------------------------------------

def _lands_but_times_out(env, monkeypatch, *sids):
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        answer = real(url, json=json, timeout=timeout, **kw)
        if int(url.rstrip("/").rsplit("/", 1)[1]) in sids:
            raise TimeoutError("read timed out (test)")
        return answer

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)


def test_a_restore_that_landed_and_timed_out_counts_and_isnt_offered_again(env, monkeypatch):
    """update_spool's timeout is a READ timeout, and the park already counts this case.
    Offered again, the retry would call the spool moved on from where Undo put it."""
    _park_box(env, 2)
    asked = ask_undo(env)
    _lands_but_times_out(env, monkeypatch, 2)
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [1, 2] and done["retry"] == []
    assert spools(env)[2]["location"] == "LR-MDB-1" and extra_of(env, 2)["container_slot"] == "2"
    assert errors(env) == []
    assert any("re-read shows it there: counted as moved" in m and c == "WARNING"
               for m, c, _ in env["logs"]), env["logs"]
    assert state.UNDO_STACK == []


def test_a_landed_write_it_cant_confirm_is_named_where_it_is_on_the_retry(env, monkeypatch):
    """The re-read fails too, so nothing proves it landed: it stays on Undo, and the
    next press finds it back in its place and leaves it there, writing nothing."""
    _park_box(env, 1)
    asked = ask_undo(env)
    real_get = env["fake"].get
    real_patch = env["fake"].patch
    blind = {"on": False}

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        real_patch(url, json=json, timeout=timeout, **kw)
        blind["on"] = True
        raise TimeoutError("read timed out (test)")

    def get(url, timeout=None, **kw):
        if blind["on"]:
            raise TimeoutError("still not answering (test)")
        return real_get(url, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    monkeypatch.setattr(spoolman_api.requests, "get", get)
    done = yes_undo(env, asked)
    assert done["success"] is False and done["retry"] == [1]

    blind["on"] = False
    monkeypatch.setattr(spoolman_api.requests, "patch", real_patch)
    env["fake"].patches.clear()
    done = yes_undo(env)
    assert done["success"] is True and done["left_alone"] == [{"id": 1, "where": "LR-MDB-1 slot 1"}]
    assert env["fake"].patches == [] and state.UNDO_STACK == []


# ---------------------------------------------------------------------------
# A 5xx is not a deleted spool (item 9)
# ---------------------------------------------------------------------------

def _5xx_for(env, monkeypatch, sid, status=500):
    """Spoolman answers this spool with a JSON error body, its usual shape."""
    real_get = env["fake"].get

    def get(url, timeout=None, **kw):
        if url.rstrip("/").endswith(f"/spool/{sid}"):
            return _Resp(status, {"message": "database is locked (test)"})
        return real_get(url, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "get", get)
    return real_get


@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_5xx_is_answered_and_not_a_spool(env, monkeypatch, status):
    add_spool(env, 1, "LR-MDB-1")
    _5xx_for(env, monkeypatch, 1, status)
    assert spoolman_api.get_spool_answer(1) == (None, True)


def test_a_404_is_still_its_body(env):
    """A truthy dict with no id is how a deleted spool reads, and that doesn't change."""
    rec, answered = spoolman_api.get_spool_answer(404)
    assert answered is True and rec.get("id") is None and "message" in rec


def test_a_5xx_at_the_question_refuses_and_keeps_the_record(env, monkeypatch):
    _park_box(env, 2)
    real_get = _5xx_for(env, monkeypatch, 1)
    asked = ask_undo(env)
    assert asked["success"] is False and "requires_confirm" not in asked
    assert "Couldn't read #1" in asked["msg"] and len(state.UNDO_STACK) == 1

    monkeypatch.setattr(spoolman_api.requests, "get", real_get)
    assert yes_undo(env)["restored"] == [1, 2]


def test_a_5xx_during_the_undo_is_unreadable_never_dropped(env, monkeypatch):
    """It used to read as a deleted spool: dropped, and its way back gone for good."""
    _park_box(env, 2)
    asked = ask_undo(env)
    _during_the_undo(monkeypatch, lambda: _5xx_for(env, monkeypatch, 1))
    done = yes_undo(env, asked)
    assert done["success"] is False and done["dropped"] == []
    assert done["restored"] == [2] and done["retry"] == [1]
    assert list(state.UNDO_STACK[-1]["moves"]) == [1]


# ---------------------------------------------------------------------------
# An archived spool (finding 5)
# ---------------------------------------------------------------------------

def test_an_archived_spool_at_unknown_stays_and_says_so(env):
    """Archiving is the natural way to clear a lost spool. Undo wrote it back to its
    slot, blanked the note, and a later un-archive could double that slot: the list
    read that checks a slot can't see an archived spool."""
    _park_box(env, 2)
    spools(env)[1]["archived"] = True
    asked = ask_undo(env)
    assert asked["msg"] == "Undo: put #2 back in LR-MDB-1 slot 2? Left where it is now: #1 at Unknown (archived)."
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [2]
    assert done["left_alone"] == [{"id": 1, "where": "Unknown (archived)"}]
    assert "Left where it is now: #1 at Unknown (archived)." in done["msg"]
    assert spools(env)[1]["location"] == "UNKNOWN" and [p[1] for p in env["fake"].patches] == [2]
    assert extra_of(env, 1)["fcc_pre_audit_location"] == "LR-MDB-1:1@2026-11-02"


def test_a_spool_archived_somewhere_else_says_that_too(env):
    _park_box(env, 1)
    spools(env)[1].update(location="SHELF-1", archived=True)
    assert yes_undo(env)["left_alone"] == [{"id": 1, "where": "SHELF-1 (archived)"}]
    assert spools(env)[1]["location"] == "SHELF-1"


# ---------------------------------------------------------------------------
# A place that has gone (finding 4)
# ---------------------------------------------------------------------------

def _delete_row(env, place):
    env["rows"][:] = [r for r in env["rows"] if r["LocationID"] != place]


def test_a_place_gone_from_locations_keeps_its_spools_at_unknown(env):
    """Written to a deleted id they sit in a place nothing can show, clear or delete,
    and the note saying where they came from is gone."""
    _park_box(env, 2)
    _delete_row(env, "LR-MDB-1")
    asked = ask_undo(env)
    assert asked["requires_confirm"] is True
    words = "LR-MDB-1 is gone from Locations, so #1 and #2 stay at Unknown."
    assert asked["msg"] == f"Undo: nothing from this audit can go back. Clear it from Undo? {words}"
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [] and done["retry"] == []
    assert done["msg"] == f"↩️ Undo: nothing went back. {words}"
    assert done["place_gone"] == [1, 2]
    assert done["left_alone"] == [{"id": 1, "where": "Unknown"}, {"id": 2, "where": "Unknown"}]
    assert env["fake"].patches == [] and spools(env)[1]["location"] == "UNKNOWN"
    assert extra_of(env, 2)["fcc_pre_audit_location"] == "LR-MDB-1:2@2026-11-02"
    assert errors(env) == [] and state.UNDO_STACK == []


def test_a_place_gone_is_said_once_however_many_spools_it_holds_back(env):
    _park_box(env, 6)
    _delete_row(env, "LR-MDB-1")
    asked = ask_undo(env)
    assert asked["msg"].count("gone from Locations") == 1 and "so 6 spools stay at Unknown." in asked["msg"]
    done = yes_undo(env, asked)
    assert done["msg"].count("gone from Locations") == 1 and "so 6 spools stay at Unknown." in done["msg"]
    assert len(env["logs"]) == 1


def test_a_place_gone_says_where_a_spool_that_moved_on_is(env):
    _park_box(env, 3)
    spools(env)[1].update(location="SHELF-1")
    del spools(env)[3]
    _delete_row(env, "LR-MDB-1")
    asked = ask_undo(env)
    assert asked["msg"].endswith("Left where it is now: #1 at SHELF-1. LR-MDB-1 is gone from Locations, "
                                 "so #2 stays at Unknown.")
    done = yes_undo(env, asked)
    assert done["msg"] == ("↩️ Undo: nothing went back. Left where it is now: #1 at SHELF-1. LR-MDB-1 is gone from "
                           "Locations, so #2 stays at Unknown. #3 is no longer in Spoolman.")


def test_the_question_and_the_write_agree_when_a_row_goes_between_them(env, monkeypatch):
    _park_box(env, 2)
    asked = ask_undo(env)
    assert "#1 back in LR-MDB-1 slot 1" in asked["msg"]
    _during_the_undo(monkeypatch, lambda: _delete_row(env, "LR-MDB-1"))
    done = yes_undo(env, asked)
    assert done["success"] is True and done["place_gone"] == [1, 2] and env["fake"].patches == []


def test_a_place_with_no_row_at_the_park_isnt_a_place_gone(env):
    """"A place with spools but no row still audits", so no row now says nothing."""
    add_spool(env, 1, "GARAGE-BIN", container_slot="2")
    start(env, "GARAGE-BIN")
    park(env)
    assert state.UNDO_STACK[-1]["place_had_row"] is False
    done = yes_undo(env)
    assert done["success"] is True and done["restored"] == [1] and done["place_gone"] == []
    assert spools(env)[1]["location"] == "GARAGE-BIN"


def test_a_list_that_reads_empty_isnt_a_place_gone(env):
    """load_locations_list answers [] for a read it couldn't make: no rows at all is
    no evidence, and Undo must not throw the batch's way back away on it."""
    _park_box(env, 2)
    env["rows"].clear()
    done = yes_undo(env)
    assert done["success"] is True and done["restored"] == [1, 2] and done["place_gone"] == []


def test_a_row_put_back_since_is_a_place_again(env):
    _park_box(env, 1)
    row = next(r for r in env["rows"] if r["LocationID"] == "LR-MDB-1")
    _delete_row(env, "LR-MDB-1")
    env["rows"].append(row)
    assert yes_undo(env)["restored"] == [1]


# ---------------------------------------------------------------------------
# The slot a spool held at the park (finding 7)
# ---------------------------------------------------------------------------

def _single_slot_box(env, place="PM-DB-1"):
    env["rows"].append({"LocationID": place, "Type": "Dryer Box", "Max Spools": "1"})


def test_a_spool_unslotted_beside_a_loaded_spool_goes_back_unslotted(env):
    """#1, the box's own spool, is loaded on a head; #2 went in with no slot. Undo read
    #2's blank as slot 1, which #1 claims, and refused what the question had offered."""
    _single_slot_box(env)
    add_spool(env, 1, "XL-1", physical_source="PM-DB-1", physical_source_slot="1")
    add_spool(env, 2, "PM-DB-1")
    start(env, "PM-DB-1")
    assert park(env)["parked"] == [2]
    assert state.UNDO_STACK[-1]["slots"] == {2: ""}
    done = yes_undo(env)
    assert done["success"] is True and done["restored"] == [2]
    assert spools(env)[2]["location"] == "PM-DB-1" and extra_of(env, 2)["container_slot"] == ""


def test_a_sole_occupants_blank_slot_is_recorded_as_slot_1(env):
    _single_slot_box(env)
    add_spool(env, 1, "PM-DB-1")
    start(env, "PM-DB-1")
    park(env)
    assert state.UNDO_STACK[-1]["slots"] == {1: "1"}


def test_an_archived_spool_filed_there_is_no_occupant(env):
    """The engine's read of a box leaves it out, so the count does."""
    _single_slot_box(env)
    add_spool(env, 1, "PM-DB-1")
    add_spool(env, 2, "PM-DB-1")
    spools(env)[2]["archived"] = True
    start(env, "PM-DB-1")
    park(env)
    assert state.UNDO_STACK[-1]["slots"] == {1: "1"}


def test_two_spools_in_a_single_slot_box_have_no_slot_each(env):
    """Counted before any write: the first parked mustn't make the second a sole
    occupant, whose blank would then read as slot 1."""
    _single_slot_box(env)
    add_spool(env, 1, "PM-DB-1")
    add_spool(env, 2, "PM-DB-1")
    start(env, "PM-DB-1")
    assert park(env)["parked"] == [1, 2]
    assert state.UNDO_STACK[-1]["slots"] == {1: "", 2: ""}


def test_a_slot_recorded_for_a_multi_slot_box_is_its_own(env):
    add_spool(env, 1, "LR-MDB-1", container_slot='"03"')
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    park(env)
    assert state.UNDO_STACK[-1]["slots"] == {1: "3", 2: ""}


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
