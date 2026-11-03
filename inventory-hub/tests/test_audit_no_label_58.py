"""Group 58.2, built on Derek's stated defaults (a) and (b): an audit's label side.

(a) A spool with no label has nothing to scan, so a tile can be pressed instead, and
the last spool found can be marked as needing one (key N, the strip's button, its
QR). (b) A real label read in an audit confirms only a MISSING status: a walk along a
shelf must not clear its reprint reminders, and dev has 48 of them.

All of it through the Flask test client and the real session, on the real read and
write functions over tests/spoolman_extra_fake.SpoolmanHTTPFake: the audit tests that
mocked update_spool are how Done's behaviour stayed hidden for months.

The page's half is tests/test_audit_no_label_58_js.py and _e2e.py.

RED on 39b0d1a unless a test says it pins what was already right.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import _Resp  # noqa: E402
from test_audit_session_58 import (  # noqa: E402,F401
    add_spool, env, log_text, park, report, scan, scan_answer, session, start,
)

AUDIT_SCAN = {"type": "command", "cmd": "audit_scan"}
LABEL = "needs_label_print"
MARK = "CMD:NEEDLABEL"


def read_label(env, sid):
    """A scanner reading the spool's printed ID: label."""
    return scan(env, f"ID:{sid}", source="barcode")


def wire(env, sid):
    """The status as Spoolman holds it: 'true', 'false', or None for no status."""
    return env["fake"].extra("spool", sid).get(LABEL)


def writes(env):
    return [p[1] for p in env["fake"].patches]


def live(env):
    res = app_module.app.test_client().get("/api/audit_session")
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def row(env, sid):
    body = live(env)
    return next(r for key in ("expected", "rogue", "trail") for r in body[key] if r["id"] == sid)


def post(path, body):
    res = app_module.app.test_client().post(path, json=body)
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def press(env, sid, found=True, audit_id=None):
    return post("/api/audit/found", {"audit_id": audit_id or session()["audit_id"], "id": sid, "found": found})


def undo(env, sid, audit_id=None):
    return post("/api/audit/needs_label_undo", {"audit_id": audit_id or session()["audit_id"], "id": sid})


def refuse_writes(env, monkeypatch, status=500, body="Spoolman says no (test)"):
    def refused(url, json=None, timeout=None, **kw):  # noqa: A002
        return _Resp(status, {"message": body})
    monkeypatch.setattr(spoolman_api.requests, "patch", refused)


def write_lands_then_times_out(env, monkeypatch):
    """A slow Spoolman: the write lands and `requests` raises its read timeout."""
    def late(url, json=None, timeout=None, **kw):  # noqa: A002
        env["fake"].patch(url, json=json, timeout=timeout)
        raise TimeoutError("read timed out (test)")
    monkeypatch.setattr(spoolman_api.requests, "patch", late)


# ---------------------------------------------------------------------------
# A label read in an audit: rule (b), one test per status
# ---------------------------------------------------------------------------

def test_a_label_read_confirms_a_missing_status(env):
    """The audit gate answered before the label check, so an ID: pass inside an audit
    (the natural way to walk a shelf) did nothing."""
    add_spool(env, 5, "LR-MDB-1", container_slot="1")
    start(env, "LR-MDB-1")
    assert read_label(env, 5) == AUDIT_SCAN
    assert wire(env, 5) == "false"
    assert writes(env) == [5]
    assert session()["scanned_items"] == [5]
    assert "✔️ Spool #5 Label Verified" in log_text(env)
    assert env["fake"].extra("spool", 5)["container_slot"] == '"1"'      # its siblings kept
    got = row(env, 5)
    assert got["label_status"] is False and got["label_read"] is True and got["found"] is True


def test_a_label_read_leaves_a_flag_up_and_the_panel_says_so(env):
    """Rule (b): True can mean "the printed label is out of date", and a walk mustn't
    clear a whole shelf's reprint reminders."""
    add_spool(env, 5, "LR-MDB-1", needs_label_print=True)
    start(env, "LR-MDB-1")
    assert read_label(env, 5) == AUDIT_SCAN
    assert wire(env, 5) == "true" and writes(env) == []
    assert session()["scanned_items"] == [5]
    got = row(env, 5)
    assert got["label_status"] is True and got["label_read"] is True and got["flagged_here"] is False


def test_a_label_read_of_a_confirmed_label_writes_and_logs_nothing(env):
    """Quiet: an audit logs only a flip. Outside one it says "already verified" per
    scan, and the Activity Log keeps 50 lines."""
    add_spool(env, 5, "LR-MDB-1", needs_label_print=False)
    start(env, "LR-MDB-1")
    assert read_label(env, 5) == AUDIT_SCAN
    assert wire(env, 5) == "false" and writes(env) == []
    assert not any("verified" in line.lower() for line in log_text(env)), log_text(env)
    assert row(env, 5)["label_status"] is False


def test_a_status_that_changed_during_the_audit_is_read_fresh(env):
    """The stored row says none, and a flag raised elsewhere since stays up."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    env["fake"].records["spool"][5]["extra"][LABEL] = "true"
    read_label(env, 5)
    assert wire(env, 5) == "true" and writes(env) == []
    assert row(env, 5)["label_status"] is True


def test_a_second_read_of_a_label_just_confirmed_writes_nothing_more(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    read_label(env, 5)
    read_label(env, 5)
    assert writes(env) == [5]


def test_a_read_of_an_extras_label_confirms_it_too(env):
    """It is physically here, and its label was read."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR", container_slot="")
    start(env, "LR-MDB-1")
    read_label(env, 7)
    assert session()["rogue_items"] == [7] and wire(env, 7) == "false"
    assert row(env, 7)["label_read"] is True


def test_a_read_of_a_spool_loaded_from_here_confirms_it_too(env):
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    add_spool(env, 5, "LR-MDB-2")
    start(env, "LR-MDB-2")
    read_label(env, 242)
    assert session()["trail_items"] == [242] and wire(env, 242) == "false"


def test_a_label_read_with_no_place_yet_does_nothing(env):
    """The label check runs only once the audit has taken the spool. Pins what was
    already right on 39b0d1a, where no check ran at all; proved on a copy with the
    check moved above the refusal, as is the next test."""
    add_spool(env, 5, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    assert read_label(env, 5) == {"type": "error", "msg": "Scan a Location first!"}
    assert writes(env) == [] and wire(env, 5) is None and session()["found_by"] == {}


def test_a_spool_that_doesnt_exist_is_no_label_read(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert read_label(env, 999) == {"type": "error", "msg": "Spool #999 not found"}
    assert writes(env) == [] and session()["found_by"] == {}
    assert not any(c == "ERROR" for _m, c, _ in env["logs"]), env["logs"]


@pytest.mark.parametrize("text, source", [
    ("ID:5", "keyboard"),       # typed, or a scanner slower than 150 ms over the label
    ("SPL:5", "barcode"),
    ("5", "barcode"),
    ("ID:5", "search"),         # a search card's button
    ("ID:5", ""),
])
def test_only_a_real_label_read_confirms(env, text, source):
    """Each finds the spool, and none of them has read its label. The same test as
    outside an audit, where only a scanned ID: label verifies a printed label."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert scan(env, text, source=source) == AUDIT_SCAN
    assert session()["scanned_items"] == [5]
    assert writes(env) == [] and wire(env, 5) is None
    got = row(env, 5)
    assert got["found"] is True and got["label_read"] is False and got["label_status"] is None


def test_a_typed_id_then_its_label_counts_as_read(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5", source="keyboard")
    assert row(env, 5)["label_read"] is False
    assert read_label(env, 5) == AUDIT_SCAN
    got = row(env, 5)
    assert got["label_read"] is True and got["label_status"] is False and wire(env, 5) == "false"


def test_a_label_read_then_a_typed_id_stays_a_label_read(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    read_label(env, 5)
    scan(env, "5", source="keyboard")
    assert row(env, 5)["label_read"] is True


def test_a_filament_label_is_still_a_refusal(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert read_label(env, 5) == AUDIT_SCAN
    ans = scan(env, "FIL:1005", source="barcode")
    assert ans == {"type": "error", "msg": "That's a filament label, not a spool"}
    assert writes(env) == [5]


# ---------------------------------------------------------------------------
# A found spool stays found
# ---------------------------------------------------------------------------

def test_a_failed_write_keeps_the_spool_found_and_says_so(env, monkeypatch):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    refuse_writes(env, monkeypatch, body="<b>no</b>")
    ans = read_label(env, 5)
    assert ans["type"] == "command" and ans["cmd"] == "audit_scan"
    assert "#5" in ans["warning"] and "couldn't be confirmed" in ans["warning"]
    assert session()["scanned_items"] == [5]
    errors = [(m, c) for m, c, _ in env["logs"] if c == "ERROR"]
    assert len(errors) == 1 and errors[0][0].startswith("❌ Failed to verify Spool #5 label:")
    assert "&lt;b&gt;no&lt;/b&gt;" in errors[0][0], errors          # Activity Log lines are HTML
    got = row(env, 5)
    assert got["found"] is True and got["label_read"] is True and got["label_status"] is None


@pytest.mark.parametrize("how", ["down", "deleted", "not_json"])
def test_a_failed_read_keeps_the_spool_found_and_says_so(env, monkeypatch, how):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    if how == "down":
        env["fake"].down = True
    elif how == "deleted":
        del env["fake"].records["spool"][5]          # Spoolman's 404 body is a truthy dict
    else:
        class Broken:
            def json(self):
                raise ValueError("not JSON (test)")
        monkeypatch.setattr(spoolman_api.requests, "get", lambda *a, **k: Broken())
    ans = read_label(env, 5)
    assert ans["cmd"] == "audit_scan" and "couldn't read its label status" in ans["warning"]
    assert session()["scanned_items"] == [5] and writes(env) == []
    assert any(c == "ERROR" and "#5" in m for m, c, _ in env["logs"]), env["logs"]


def test_a_label_check_that_blows_up_keeps_the_spool_found(env, monkeypatch):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")

    def boom(_sid):
        raise RuntimeError("boom (test)")
    monkeypatch.setattr(spoolman_api, "get_spool_answer", boom)
    ans = read_label(env, 5)
    assert ans["cmd"] == "audit_scan" and "label check failed" in ans["warning"]
    assert session()["scanned_items"] == [5]


def test_a_spool_whose_check_failed_can_be_read_again(env, monkeypatch):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    good = spoolman_api.requests.patch
    refuse_writes(env, monkeypatch)
    read_label(env, 5)
    assert wire(env, 5) is None
    monkeypatch.setattr(spoolman_api.requests, "patch", good)
    assert read_label(env, 5) == AUDIT_SCAN
    assert wire(env, 5) == "false" and row(env, 5)["label_status"] is False


# ---------------------------------------------------------------------------
# Outside an audit nothing changes: these pin what was already right, each proved
# on a copy with _verify_spool_label broken
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flag, wrote, line", [
    ({}, "false", "✔️ Spool #5 Label Verified"),
    ({LABEL: True}, "false", "✔️ Spool #5 Label Verified"),
])
def test_outside_an_audit_a_label_read_still_clears_a_flag(env, flag, wrote, line):
    add_spool(env, 5, "LR-MDB-1", **flag)
    ans = scan(env, "ID:5", source="barcode")
    assert ans["type"] == "spool" and ans["label_already_verified"] is False
    assert wire(env, 5) == wrote and line in log_text(env)


def test_outside_an_audit_a_confirmed_label_still_says_so(env):
    add_spool(env, 5, "LR-MDB-1", needs_label_print=False)
    ans = scan(env, "ID:5", source="barcode")
    assert ans["label_already_verified"] is True and writes(env) == []
    assert "ℹ️ Spool #5 already verified" in log_text(env)


def test_outside_an_audit_a_failed_write_still_logs_and_answers(env, monkeypatch):
    add_spool(env, 5, "LR-MDB-1")
    refuse_writes(env, monkeypatch)
    ans = scan(env, "ID:5", source="barcode")
    assert ans["type"] == "spool" and ans["label_already_verified"] is False
    assert any(c == "ERROR" and "Failed to verify Spool #5 label" in m for m, c, _ in env["logs"])


# ---------------------------------------------------------------------------
# CMD:NEEDLABEL
# ---------------------------------------------------------------------------

def test_the_command_is_a_command():
    assert logic.resolve_scan("CMD:NEEDLABEL") == {"type": "command", "cmd": "needlabel"}
    assert logic.resolve_scan("cmd:needlabel") == {"type": "command", "cmd": "needlabel"}


def test_outside_an_audit_it_is_an_error_and_writes_nothing(env):
    add_spool(env, 5, "LR-MDB-1")
    ans = scan(env, MARK, source="barcode")
    assert ans["type"] == "error" and "No audit is running" in ans["msg"]
    assert writes(env) == []
    assert any(c == "WARNING" and "No audit is running" in m for m, c, _ in env["logs"])


def test_with_a_bulk_move_armed_it_says_the_same_and_leaves_the_session_alone(env):
    state.BULK_MOVE_SESSION["active"] = True
    state.BULK_MOVE_SESSION["stage"] = "awaiting_source"
    try:
        ans = scan(env, MARK)
        assert ans["type"] == "error" and "No audit is running" in ans["msg"]
        assert state.BULK_MOVE_SESSION["stage"] == "awaiting_source"
    finally:
        state.reset_bulk_move()


def test_with_nothing_found_yet_it_refuses(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    ans = scan(env, MARK)
    assert ans == {"type": "error", "msg": "Nothing has been found yet: scan a spool or press its tile first."}
    assert writes(env) == [] and env["fake"].gets == []
    assert any(c == "WARNING" and "Nothing has been found" in m for m, c, _ in env["logs"])


def test_it_marks_the_last_spool_found_and_keeps_its_siblings(env):
    """routes_print_queue.py's partial write: the merge keeps every other extra."""
    add_spool(env, 5, "LR-MDB-1", container_slot="2", physical_source="CR-CT-1", physical_source_slot="3")
    start(env, "LR-MDB-1")
    scan(env, "5")
    before = env["fake"].extra("spool", 5)
    ans = scan(env, MARK)
    assert ans == {**AUDIT_SCAN, "said": "#5 is marked: it needs a label."}
    assert wire(env, 5) == "true" and writes(env) == [5]
    assert {k: v for k, v in env["fake"].extra("spool", 5).items() if k != LABEL} == before
    assert session()["label_flagged"] == {"5": None}
    assert any("marked as needing a label" in m for m, _c, _ in env["logs"]), env["logs"]
    got = row(env, 5)
    assert got["label_status"] is True and got["flagged_here"] is True


def test_the_flag_goes_where_the_backlog_reads_it(env):
    """The 🏷️ Backlog's own test, on the record the mark wrote."""
    import routes_print_queue
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    assert routes_print_queue._needs_label(env["fake"].records["spool"][5]) is False
    scan(env, MARK)
    assert routes_print_queue._needs_label(env["fake"].records["spool"][5]) is True


def test_a_double_read_is_one_write(env):
    add_spool(env, 5, "LR-MDB-1", container_slot="2")
    start(env, "LR-MDB-1")
    scan(env, "5")
    assert scan(env, MARK)["said"] == "#5 is marked: it needs a label."
    assert scan(env, MARK) == {**AUDIT_SCAN, "said": "#5 is already flagged for a new label.", "said_type": "info"}
    assert writes(env) == [5] and session()["label_flagged"] == {"5": None}
    assert env["fake"].extra("spool", 5)["container_slot"] == '"2"'


def test_a_mark_cleared_elsewhere_can_be_raised_again_and_undone_to_that(env):
    """A Backlog's Mark Printed since: "already flagged" would be untrue, and what the
    second mark replaces is that newer status."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    env["fake"].records["spool"][5]["extra"][LABEL] = "false"
    assert scan(env, MARK)["said"] == "#5 is marked: it needs a label."
    assert wire(env, 5) == "true" and session()["label_flagged"] == {"5": False}
    undo(env, 5)
    assert wire(env, 5) == "false"


def test_a_flag_already_up_says_so_with_no_write_and_nothing_to_undo(env):
    add_spool(env, 5, "LR-MDB-1", needs_label_print=True)
    start(env, "LR-MDB-1")
    scan(env, "5")
    ans = scan(env, MARK)
    assert ans["said"] == "#5 is already flagged for a new label."
    assert writes(env) == [] and session()["label_flagged"] == {}
    assert row(env, 5)["flagged_here"] is False


def test_a_confirmed_spool_keeps_its_status_as_the_prior_one(env):
    add_spool(env, 5, "LR-MDB-1", needs_label_print=False)
    start(env, "LR-MDB-1")
    read_label(env, 5)
    scan(env, MARK)
    assert session()["label_flagged"] == {"5": False} and wire(env, 5) == "true"


def test_a_label_just_confirmed_then_marked_keeps_confirmed_as_the_prior_one(env):
    """Scanned, and the person decides the label won't do: what the mark replaced is
    the status that scan has just written."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    read_label(env, 5)
    scan(env, MARK)
    assert session()["label_flagged"] == {"5": False}


def test_an_archived_spool_refuses(env):
    """The Backlog can't show it, so the mark would be seen nowhere."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    env["fake"].records["spool"][7]["archived"] = True
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    assert session()["rogue_items"] == [7]
    ans = scan(env, MARK)
    assert ans["type"] == "error" and "archived" in ans["msg"] and "Backlog" in ans["msg"]
    assert writes(env) == [] and session()["label_flagged"] == {}


def test_a_rejection_surfaces_spoolmans_words_and_leaves_no_mark(env, monkeypatch):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    good = spoolman_api.requests.patch
    refuse_writes(env, monkeypatch, body="<i>nope</i>")
    ans = scan(env, MARK)
    assert ans["type"] == "error" and "Couldn't mark #5" in ans["msg"] and "<i>nope</i>" in ans["msg"]
    assert session()["label_flagged"] == {} and row(env, 5)["label_status"] is None
    errors = [m for m, c, _ in env["logs"] if c == "ERROR"]
    assert len(errors) == 1 and "&lt;i&gt;nope&lt;/i&gt;" in errors[0], errors
    monkeypatch.setattr(spoolman_api.requests, "patch", good)
    assert scan(env, MARK)["said"] == "#5 is marked: it needs a label."
    assert wire(env, 5) == "true"


def test_a_write_reported_failed_that_landed_counts(env, monkeypatch):
    """update_spool's timeout is a READ timeout. Refused, the mark would stand on the
    record with no way to undo it."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    write_lands_then_times_out(env, monkeypatch)
    assert scan(env, MARK)["said"] == "#5 is marked: it needs a label."
    assert wire(env, 5) == "true" and session()["label_flagged"] == {"5": None}


def test_a_read_that_fails_marks_nothing(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    env["fake"].down = True
    ans = scan(env, MARK)
    assert ans["type"] == "error" and "Couldn't read #5" in ans["msg"]
    assert writes(env) == [] and session()["label_flagged"] == {}


def test_a_spool_deleted_since_refuses(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    del env["fake"].records["spool"][5]
    assert scan(env, MARK) == {"type": "error", "msg": "Spool #5 not found"}
    assert writes(env) == []


def test_a_rescan_selects_a_spool_again(env):
    """last_found is set before the "Already scanned" answer."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "1")
    scan(env, "2")
    assert session()["last_found"] == 2
    scan(env, "1")
    assert session()["last_found"] == 1
    scan(env, MARK)
    assert wire(env, 1) == "true" and wire(env, 2) is None


def test_an_extra_rescanned_is_selected_again(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    scan(env, "1")
    scan(env, "ID:7")
    assert session()["last_found"] == 7 and session()["rogue_items"] == [7]


def test_a_spool_loaded_from_here_is_the_last_found_too(env):
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    add_spool(env, 5, "LR-MDB-2")
    start(env, "LR-MDB-2")
    scan(env, "ID:242")
    assert session()["last_found"] == 242 and live(env)["last_found"]["id"] == 242


def test_an_extra_spoolman_wouldnt_answer_for_is_the_last_found_too(env):
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start(env, "LR-MDB-1")
    env["fake"].down = True
    scan(env, "ID:7")
    assert session()["last_found"] == 7


def test_a_refused_scan_selects_nothing(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, "ID:999")
    assert session()["last_found"] == 5


def test_a_flagged_spools_second_read_keeps_the_flag(env):
    """Marked, then its label read twice: nothing clears the mark, and with rule (a)
    a scan would have."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    env["fake"].gets.clear()
    assert read_label(env, 5) == AUDIT_SCAN
    assert read_label(env, 5) == AUDIT_SCAN
    assert wire(env, 5) == "true" and writes(env) == [5]
    assert env["fake"].gets == []                                      # skipped, not just unwritten
    assert session()["label_flagged"] == {"5": None}


def test_the_mark_is_escaped_in_the_log(env):
    add_spool(env, 5, "LR-MDB-1", name="<b>Red</b>")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    line = next(m for m in log_text(env) if "marked as needing a label" in m).lower()
    assert "<b>" not in line and "&lt;b&gt;" in line


def test_the_end_clears_the_marks_and_leaves_the_flag(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    scan(env, "CMD:CANCEL")
    assert session()["label_flagged"] == {} and session()["last_found"] is None
    assert wire(env, 5) == "true"


def test_a_mark_that_loses_a_race_with_the_end_writes_nothing(env, monkeypatch):
    """Its read was out when the audit ended: the mark would stand on the record with
    no audit left to undo it. Pins what was already right; proved on a copy with the
    check after the read taken out."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    real = spoolman_api.get_spool_answer

    def ended_meanwhile(sid):
        answer = real(sid)
        monkeypatch.setattr(spoolman_api, "get_spool_answer", real)
        assert "audit_ended" in scan(env, "CMD:CANCEL")
        return answer

    monkeypatch.setattr(spoolman_api, "get_spool_answer", ended_meanwhile)
    assert scan(env, MARK) == {"type": "error", "msg": "That audit has ended."}
    assert session()["active"] is False
    assert writes(env) == [] and wire(env, 5) is None


def test_the_report_names_the_spools_marked_as_needing_a_label(env):
    """A mark's spool is on the Backlog, and the report is what is left of an audit:
    with no read, from the rows stored at each scan."""
    add_spool(env, 1, "LR-MDB-1", name="Red")
    add_spool(env, 2, "LR-MDB-1", name="Blue")
    add_spool(env, 7, "CR", name="Stray")
    start(env, "LR-MDB-1")
    for spool in ("1", "ID:7"):
        scan(env, spool)
        scan(env, MARK)
    scan(env, "2")
    env["logs"].clear()
    env["fake"].gets.clear()
    scan(env, "CMD:CANCEL")
    line = report(env)
    assert "<b>Needs a label:</b> #1 Some Brand PLA (Red), #7 Some Brand PLA (Stray)" in line
    assert env["fake"].gets == []


def test_a_mark_undone_isnt_in_the_report(env):
    """Green with no such line at all; proved on a copy that keeps an undone mark in
    label_flagged."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "1")
    scan(env, MARK)
    undo(env, 1)
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    assert "Needs a label" not in report(env)


def test_with_no_marks_the_report_has_no_such_line(env):
    """The line is this audit's marks, never the flags already up. Green with no such
    line at all; proved on a copy whose report reads the rows' flags."""
    add_spool(env, 1, "LR-MDB-1", needs_label_print=True)
    start(env, "LR-MDB-1")
    scan(env, "1")
    scan(env, MARK)                                 # already flagged: not this audit's mark
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    assert "Needs a label" not in report(env)


def test_the_reports_marks_are_escaped(env):
    add_spool(env, 1, "LR-MDB-1", name="<b>Red</b>")
    start(env, "LR-MDB-1")
    scan(env, "1")
    scan(env, MARK)
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    line = report(env).lower()
    assert "<b>red" not in line and "&lt;b&gt;red" in line


def test_the_idle_line_names_the_marks_with_no_read(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "1")
    scan(env, MARK)
    env["logs"].clear()
    env["fake"].gets.clear()
    session()["last_activity_ts"] = time.time() - state.AUDIT_IDLE_TIMEOUT_SECONDS - 5
    app_module._check_audit_idle_timeout()
    (msg, _cat, _color), = env["logs"]
    assert "found 1 of 2; missing #2; needs a label #1." in msg
    assert env["fake"].gets == []


def test_a_mark_while_the_audit_is_finishing_is_refused(env):
    """Pins process_audit_scan's rule on the new command; proved on a copy with the
    lock check taken out."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    assert logic._AUDIT_END_LOCK.acquire(False)
    try:
        ans = scan(env, MARK)
    finally:
        logic._AUDIT_END_LOCK.release()
    assert ans == {"type": "error", "msg": logic.AUDIT_FINISHING_MSG}
    assert writes(env) == []


# ---------------------------------------------------------------------------
# "undo that"
# ---------------------------------------------------------------------------

def test_undo_puts_a_missing_status_back_through_the_delete_sentinel(env):
    """A mark raised by mistake can't be undone by Mark Printed or a scan: both write
    False, "confirmed", on a spool that may have no label. A JSON null on 0.27."""
    add_spool(env, 5, "LR-MDB-1", container_slot="2")
    start(env, "LR-MDB-1")
    scan(env, "5")
    before = env["fake"].extra("spool", 5)
    scan(env, MARK)
    env["fake"].patches.clear()
    ans = undo(env, 5)
    assert ans == {"success": True, "msg": "Undone: #5 has no label status again."}
    assert LABEL not in env["fake"].extra("spool", 5)
    assert env["fake"].extra("spool", 5) == before
    (_entity, _id, body), = env["fake"].patches
    assert body["extra"][LABEL] is None
    assert session()["label_flagged"] == {}
    got = row(env, 5)
    assert got["label_status"] is None and got["flagged_here"] is False
    assert any("Undone: #5" in m for m, _c, _ in env["logs"])


def test_undo_puts_a_confirmed_status_back(env):
    add_spool(env, 5, "LR-MDB-1", needs_label_print=False)
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    assert undo(env, 5) == {"success": True, "msg": "Undone: #5's label is confirmed again."}
    assert wire(env, 5) == "false" and row(env, 5)["label_status"] is False


def test_it_can_be_marked_again_after_an_undo(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    undo(env, 5)
    assert scan(env, MARK)["said"] == "#5 is marked: it needs a label."
    assert wire(env, 5) == "true" and session()["label_flagged"] == {"5": None}


def test_undo_of_a_spool_that_wasnt_marked_writes_nothing(env):
    add_spool(env, 5, "LR-MDB-1", needs_label_print=True)
    start(env, "LR-MDB-1")
    scan(env, "5")
    ans = undo(env, 5)
    assert ans["success"] is False and "wasn't marked" in ans["msg"]
    assert writes(env) == [] and wire(env, 5) == "true"


def test_a_mark_can_still_be_undone_after_another_spool_was_found(env):
    """"undo that" shows on the strip, so selecting the spool again brings it back."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "1")
    scan(env, MARK)
    scan(env, "2")
    assert live(env)["last_found"]["flagged_here"] is False
    scan(env, "1")
    assert live(env)["last_found"]["flagged_here"] is True
    assert undo(env, 1)["success"] is True and wire(env, 1) is None


def test_a_second_undo_writes_nothing(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    undo(env, 5)
    env["fake"].patches.clear()
    assert undo(env, 5)["success"] is False
    assert writes(env) == []


def test_undo_for_another_audit_writes_nothing(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    env["fake"].patches.clear()
    ans = undo(env, 5, audit_id="another-1")
    assert ans["success"] is False and ans["stale"] is True
    assert writes(env) == [] and wire(env, 5) == "true"


def test_undo_after_the_audit_ended_writes_nothing(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    audit_id = session()["audit_id"]
    scan(env, "5")
    scan(env, MARK)
    scan(env, "CMD:CANCEL")
    env["fake"].patches.clear()
    ans = undo(env, 5, audit_id=audit_id)
    assert ans["stale"] is True and writes(env) == [] and wire(env, 5) == "true"


def test_undo_with_no_audit_id_is_stale(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert post("/api/audit/needs_label_undo", {"id": 5})["stale"] is True


def test_undo_leaves_a_status_newer_than_the_mark(env):
    """A Backlog's Mark Printed since: that status is newer than the one this would
    put back. Said, and nothing written."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    env["fake"].records["spool"][5]["extra"][LABEL] = "false"
    env["fake"].patches.clear()
    ans = undo(env, 5)
    assert ans["success"] is True and "left as it is" in ans["msg"]
    assert ans["left_alone"] is True           # the press didn't do what it asked: the panel says so
    assert writes(env) == [] and wire(env, 5) == "false"
    assert session()["label_flagged"] == {} and row(env, 5)["label_status"] is False


def test_undo_that_cant_read_leaves_the_mark(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    env["fake"].patches.clear()
    env["fake"].down = True
    ans = undo(env, 5)
    assert ans["success"] is False and "its mark stands" in ans["msg"]
    assert writes(env) == [] and session()["label_flagged"] == {"5": None}


def test_undo_of_a_spool_deleted_since_forgets_the_mark(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    del env["fake"].records["spool"][5]
    assert undo(env, 5) == {"success": False, "msg": "Spool #5 not found"}
    assert session()["label_flagged"] == {}


def test_a_rejected_undo_keeps_the_mark_and_it_can_be_tried_again(env, monkeypatch):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    good = spoolman_api.requests.patch
    refuse_writes(env, monkeypatch, body="<i>nope</i>")
    ans = undo(env, 5)
    assert ans["success"] is False and "Couldn't undo the mark on #5" in ans["msg"]
    assert session()["label_flagged"] == {"5": None} and wire(env, 5) == "true"
    errors = [m for m, c, _ in env["logs"] if c == "ERROR"]
    assert len(errors) == 1 and "&lt;i&gt;nope&lt;/i&gt;" in errors[0], errors
    monkeypatch.setattr(spoolman_api.requests, "patch", good)
    assert undo(env, 5)["success"] is True
    assert wire(env, 5) is None


def test_an_undo_reported_failed_that_landed_counts(env, monkeypatch):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    write_lands_then_times_out(env, monkeypatch)
    assert undo(env, 5)["success"] is True
    assert wire(env, 5) is None and session()["label_flagged"] == {}


def test_a_spoolman_that_cant_clear_it_says_so_and_keeps_the_mark(env):
    """Spoolman up to 0.25 can't clear a boolean extra: the flag stays, so "undo
    that" mustn't say it went. Dev and prod run 0.27."""
    add_spool(env, 5, "LR-MDB-1")
    env["fake"].version = "0.23.1"
    start(env, "LR-MDB-1")
    scan(env, "5")
    scan(env, MARK)
    ans = undo(env, 5)
    assert ans["success"] is False and "not cleared" in ans["msg"] and "0.26 or newer" in ans["msg"]
    assert session()["label_flagged"] == {"5": None} and wire(env, 5) == "true"


# ---------------------------------------------------------------------------
# A tile's press
# ---------------------------------------------------------------------------

def test_a_press_finds_a_spool_with_no_label_read_and_touches_spoolman_not_at_all(env):
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 6, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert press(env, 5) == {"success": True, "found": True}
    assert session()["scanned_items"] == [5] and session()["last_found"] == 5
    assert session()["found_by"] == {"5": "no_label"}
    assert writes(env) == [] and env["fake"].gets == []
    assert any("Found #5" in m and "no label read" in m and "(1 left)" in m for m, _c, _ in env["logs"]), env["logs"]
    got = row(env, 5)
    assert got["found"] is True and got["label_read"] is False


def test_a_press_refreshes_the_idle_timer(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    session()["last_activity_ts"] = time.time() - 600
    press(env, 5)
    assert time.time() - session()["last_activity_ts"] < 5


def test_a_second_press_unfinds_it(env):
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 6, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 5)
    assert press(env, 5, found=False) == {"success": True, "found": False}
    assert session()["scanned_items"] == [] and session()["found_by"] == {}
    assert row(env, 5)["found"] is False
    assert live(env)["stats"]["missing"] == 2
    assert any("back on the not-scanned list" in m for m, _c, _ in env["logs"])


def test_a_scan_never_unfinds(env):
    """Found by a press, then scanned, in every way, any number of times: still found."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 5)
    for text, source in (("ID:5", "barcode"), ("ID:5", "barcode"), ("5", "keyboard"), ("SPL:5", "barcode")):
        assert scan(env, text, source=source) == AUDIT_SCAN
        assert session()["scanned_items"] == [5]
    assert row(env, 5)["found"] is True


def test_a_press_says_what_it_wants_so_a_double_press_cant_flip_it(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 5)
    assert press(env, 5) == {"success": True, "found": True}       # sent before the tile redrew
    assert session()["scanned_items"] == [5]
    press(env, 5, found=False)
    assert press(env, 5, found=False) == {"success": True, "found": False}
    assert session()["scanned_items"] == []


def test_a_press_on_a_spool_found_by_its_label_keeps_that_and_selects_it(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    read_label(env, 1)
    scan(env, "2")
    press(env, 1)
    assert session()["last_found"] == 1 and session()["found_by"]["1"] == "label"


def test_a_spool_found_by_its_label_can_be_unfound_and_its_label_stays_confirmed(env):
    """No hard stop on a correction (Derek): the wrong spool scanned here can be taken
    back. The label really was read, so its status stays."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    read_label(env, 5)
    assert press(env, 5, found=False)["success"] is True
    assert session()["scanned_items"] == [] and wire(env, 5) == "false"
    got = row(env, 5)
    assert got["found"] is False and got["label_read"] is False


def test_unfinding_the_last_found_leaves_nothing_to_mark(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 5)
    press(env, 5, found=False)
    assert session()["last_found"] is None and live(env)["last_found"] is None
    assert scan(env, MARK)["type"] == "error"


def test_unfinding_another_spool_keeps_the_last_found(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 1)
    press(env, 2)
    press(env, 1, found=False)
    assert session()["last_found"] == 2


def test_a_mark_outlives_its_spool_being_unfound_and_comes_back_with_it(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 5)
    scan(env, MARK)
    press(env, 5, found=False)
    assert wire(env, 5) == "true" and row(env, 5)["label_status"] is True
    press(env, 5)
    assert live(env)["last_found"]["flagged_here"] is True
    assert undo(env, 5)["success"] is True and wire(env, 5) is None


def test_a_spool_a_press_found_isnt_parked(env):
    """Done's plan reads the same list, so a found tile keeps its spool in place."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 1)
    res = park(env)
    assert res["parked"] == [2]
    assert env["fake"].records["spool"][1]["location"] == "LR-MDB-1"


def test_a_spool_unfound_is_parked_again(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    press(env, 1)
    press(env, 2)
    press(env, 1, found=False)
    question = scan(env, "CMD:DONE")
    assert [r["id"] for r in question["park"]] == [1]


@pytest.mark.parametrize("sid", [999, "abc", None, True, [5]])
def test_a_press_for_a_spool_not_on_the_list_is_refused(env, sid):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    ans = press(env, sid)
    assert ans["success"] is False and "isn't on this audit's list" in ans["msg"]
    assert session()["scanned_items"] == []


def test_an_extra_is_taken_back_by_a_press(env):
    """PIN UPDATED DELIBERATELY (Derek, 2026-11-03, A3): Done files the Extras here
    now, so one scanned or picked by mistake must be undoable before Done. It was
    refused ("Only the Expected tiles are buttons"). RED on 296e2a7."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    assert session()["last_found"] == 7 and session()["found_by"] == {"7": logic.AUDIT_FOUND_NO_LABEL}
    env["logs"].clear()
    assert press(env, 7, found=False) == {"success": True, "found": False}
    assert session()["rogue_items"] == [] and session()["scanned_items"] == []
    assert session()["found_by"] == {} and session()["last_found"] is None
    body = live(env)
    assert body["rogue"] == [] and body["stats"]["rogue"] == 0 and body["last_found"] is None
    assert log_text(env) == ["↩️ #7 is off the Extra list: it isn't here after all."]
    assert writes(env) == []


def test_taking_back_an_extra_keeps_another_last_found(env):
    """RED on 296e2a7."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    scan(env, "ID:5")
    assert press(env, 7, found=False)["success"] is True
    assert session()["last_found"] == 5 and session()["scanned_items"] == [5]


def test_a_double_press_on_an_extra_is_one_take_back(env):
    """The second press, sent before the tile redrew, is answered quietly: a double
    press does what one press does. RED on 296e2a7."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    env["logs"].clear()
    assert press(env, 7, found=False) == {"success": True, "found": False}
    assert press(env, 7, found=False) == {"success": True, "found": False}
    assert len(log_text(env)) == 1 and session()["rogue_items"] == []


def test_an_extra_taken_back_and_scanned_again_is_an_extra_again(env):
    """Its row stays, so nothing about it is lost; a scan reads it again. RED on 296e2a7."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    press(env, 7, found=False)
    assert scan_answer("ID:7")["heard"] == "Extra: FCC has #7 at CR"
    assert session()["rogue_items"] == [7] and session()["last_found"] == 7


def test_a_label_mark_stays_when_its_extra_is_taken_back(env):
    """As an Expected tile's un-find keeps its mark: "undo that" comes back with the
    spool. RED on 296e2a7."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    scan(env, MARK)
    press(env, 7, found=False)
    assert session()["rogue_items"] == []
    assert wire(env, 7) == "true" and session()["label_flagged"] == {"7": None}
    scan(env, "ID:7")
    assert live(env)["last_found"]["flagged_here"] is True


def test_a_press_never_makes_an_extra_or_finds_one_again(env):
    """found: true on a spool not on the list stays refused, an Extra included."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    add_spool(env, 8, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    press(env, 7, found=False)
    for sid in (7, 8):
        ans = press(env, sid)
        assert ans["success"] is False and "isn't on this audit's list" in ans["msg"]
    assert session()["rogue_items"] == [] and session()["scanned_items"] == []


def test_a_spool_loaded_from_here_cant_be_taken_back(env):
    """Its tile stays a plain tile, and the server holds to that too. Pins what was
    already right."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="1")
    start(env, "LR-MDB-1")
    scan(env, "ID:242")
    assert session()["trail_items"] == [242]
    assert press(env, 242, found=False)["success"] is False
    assert session()["trail_items"] == [242] and 242 in session()["scanned_items"]


@pytest.mark.parametrize("found", [None, "true", 1])
def test_a_press_that_doesnt_say_found_or_not_is_refused(env, found):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    ans = post("/api/audit/found", {"audit_id": session()["audit_id"], "id": 5, "found": found})
    assert ans["success"] is False and session()["scanned_items"] == []


def test_a_press_for_another_audit_is_stale(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    ans = press(env, 5, audit_id="another-1")
    assert ans["success"] is False and ans["stale"] is True and session()["scanned_items"] == []


def test_a_press_with_no_audit_running_is_stale(env):
    assert post("/api/audit/found", {"audit_id": "x", "id": 5, "found": True})["stale"] is True


def test_a_press_while_the_audit_is_finishing_is_refused(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert logic._AUDIT_END_LOCK.acquire(False)
    try:
        ans = press(env, 5)
    finally:
        logic._AUDIT_END_LOCK.release()
    assert ans == {"success": False, "busy": True, "msg": logic.AUDIT_FINISHING_MSG}
    assert session()["scanned_items"] == []


def test_a_press_after_the_idle_limit_finds_no_audit(env):
    """The scan gate's rule: the check comes before the press can refresh the timer."""
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    audit_id = session()["audit_id"]
    session()["last_activity_ts"] = time.time() - state.AUDIT_IDLE_TIMEOUT_SECONDS - 5
    ans = press(env, 5, audit_id=audit_id)
    assert ans["stale"] is True and session()["active"] is False
    assert state.AUDIT_LAST_END["why"] == "idle"


@pytest.mark.parametrize("path", ["/api/audit/found", "/api/audit/needs_label_undo"])
def test_a_body_that_isnt_json_is_refused_as_stale(env, path):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    res = app_module.app.test_client().post(path, data="not json", content_type="text/plain")
    assert res.status_code == 200 and res.get_json()["stale"] is True


# ---------------------------------------------------------------------------
# What the panel draws from
# ---------------------------------------------------------------------------

def test_the_session_says_what_the_strip_shows_and_reads_nothing(env):
    add_spool(env, 1, "LR-MDB-1", needs_label_print=True)
    add_spool(env, 2, "LR-MDB-1", needs_label_print=False)
    add_spool(env, 3, "LR-MDB-1")
    start(env, "LR-MDB-1")
    read_label(env, 2)
    press(env, 1)
    env["fake"].gets.clear()
    body = live(env)
    assert env["fake"].gets == []
    assert body["last_found"]["id"] == 1 and body["last_found"]["found"] is True
    by_id = {r["id"]: r for r in body["expected"]}
    assert by_id[1]["label_status"] is True and by_id[1]["label_read"] is False
    assert by_id[2]["label_status"] is False and by_id[2]["label_read"] is True
    assert by_id[3]["label_status"] is None and by_id[3]["found"] is False


def test_with_nothing_found_the_strip_has_nothing(env):
    add_spool(env, 5, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert live(env)["last_found"] is None


def test_a_row_with_no_stored_data_still_says_its_status(env):
    """A session built by hand: _enrich's row."""
    add_spool(env, 5, "LR-MDB-1", needs_label_print=True)
    state.AUDIT_SESSION.update({"active": True, "location_id": "LR-MDB-1", "expected_items": [5],
                                "scanned_items": [5], "last_found": 5, "last_activity_ts": time.time()})
    body = live(env)
    assert body["last_found"]["label_status"] is True


# ---------------------------------------------------------------------------
# A tile's QR (Derek, 2026-11-03, A1): CMD:FOUND:<audit id>:<spool id>
# A spool with no label can be found by the QR its Expected tile shows, for a
# scanner-only screen. It does what pressing the tile does, through one helper, and
# never takes a find back. Every test here is RED on 296e2a7, where the QR read as
# "Malformed Command", unless it says it pins what was already right.
# ---------------------------------------------------------------------------

AUDIT_ID = "a1b2c3d4-7"       # hex letters in it, so an upper-cased read differs


def tile_qr(sid, audit_id=AUDIT_ID):
    return f"CMD:FOUND:{audit_id}:{sid}"


def start_with_id(env, place):
    """start(), with an audit id that holds letters: a real one may be all digits."""
    start(env, place)
    state.AUDIT_SESSION["audit_id"] = AUDIT_ID


FOUND_57 = {"type": "command", "cmd": "found", "audit": "a1b2c3d4-3", "id": 57}


@pytest.mark.parametrize("text", [
    "CMD:FOUND:a1b2c3d4-3:57",
    "cmd:found:A1B2C3D4-3:57",                              # a scanner set to upper case reads the same
    "qCMD:FOUND:a1b2c3d4-3:57",                             # a key left in front
    "CMD:FOUND:a1b2c3d4-3:56CMD:FOUND:a1b2c3d4-3:57",       # a double read glued on: the last label
    " CMD:FOUND:a1b2c3d4-3: 57 ",
])
def test_a_tiles_qr_is_a_command_naming_its_audit_and_spool(text):
    assert logic.resolve_scan(text) == FOUND_57


def test_a_real_audit_id_reads_back_whole_and_no_other_command_takes_it():
    """The substring ladder: nothing above CMD:FOUND matches its payload."""
    aid = logic.new_audit_id()
    assert logic.resolve_scan(f"CMD:FOUND:{aid}:5") == {"type": "command", "cmd": "found", "audit": aid, "id": 5}
    assert logic.resolve_scan(f"CMD:FOUND:{aid.upper()}:5")["audit"] == aid


@pytest.mark.parametrize("text", ["CMD:FOUND", "CMD:FOUND:", "CMD:FOUND:57", "CMD:FOUND::57",
                                  "CMD:FOUND:a1b2c3d4-3:", "CMD:FOUND:a1b2c3d4-3:5x",
                                  "CMD:FOUND:a1b2c3d4-3:-5", "CMD:FOUND:a1b2c3d4-3:²",
                                  # Another label glued on after the QR (review of 7e3720f, S-3:
                                  # RED there, read as another audit's QR naming #58 or #9).
                                  "CMD:FOUND:a1b2c3d4-3:57ID:58", "CMD:FOUND:a1b2c3d4-3:57 ID:58",
                                  "CMD:FOUND:a1b2c3d4-3:57SPL:58", "CMD:FOUND:a1b2c3d4-3:57FIL:9"])
def test_a_malformed_tile_qr_says_what_to_do(text):
    assert logic.resolve_scan(text) == {"type": "error", "msg": logic.AUDIT_FOUND_QR_UNREAD}
    assert "scan it again, or press the tile" in logic.AUDIT_FOUND_QR_UNREAD


def test_a_tiles_qr_finds_its_spool_as_a_press_does_and_reads_no_label(env):
    """Found here, no label read, the last found: a picture of the tile, never the
    spool's label, so even a scanner's read confirms no label status (rule (b) would
    confirm a missing one)."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 6, "LR-MDB-1")
    start_with_id(env, "LR-MDB-1")
    ans = scan_answer(tile_qr(5), source="barcode")
    assert ans == {**AUDIT_SCAN, "heard": "Found #5 by its tile's QR, no label read (1 left)"}
    assert session()["scanned_items"] == [5] and session()["last_found"] == 5
    assert session()["found_by"] == {"5": logic.AUDIT_FOUND_NO_LABEL}
    assert log_text(env) == ["✅ Found #5 by its tile's QR, no label read (1 left)"]
    assert env["fake"].gets == [] and writes(env) == [] and wire(env, 5) is None
    assert row(env, 5)["found"] is True and row(env, 5)["label_read"] is False


def test_the_press_and_the_qr_are_one_find(env):
    """Both doors go through logic._audit_find_listed: the same session, one line each."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 6, "LR-MDB-1")
    start_with_id(env, "LR-MDB-1")
    press(env, 5)
    scan(env, tile_qr(6))
    assert log_text(env) == ["✅ Found #5 by hand, no label read (1 left)",
                             "✅ Found #6 by its tile's QR, no label read (All found!)"]
    assert session()["found_by"] == {"5": "no_label", "6": "no_label"} and session()["last_found"] == 6


def test_an_upper_case_read_finds_its_spool(env):
    """Caps Lock, or a scanner set to upper case: the audit id is compared without case."""
    add_spool(env, 5, "LR-MDB-1")
    start_with_id(env, "LR-MDB-1")
    assert scan_answer(tile_qr(5).upper())["heard"] == "Found #5 by its tile's QR, no label read (All found!)"
    assert session()["scanned_items"] == [5]


def test_another_audits_qr_marks_nothing_and_says_so(env):
    add_spool(env, 5, "LR-MDB-1")
    start_with_id(env, "LR-MDB-1")
    ans = scan(env, tile_qr(5, audit_id="0000ffff-9"))
    assert ans == {"type": "error", "msg": "That tile's QR is from another audit, so nothing was marked."}
    assert session()["scanned_items"] == [] and session()["last_found"] is None
    assert any(c == "WARNING" and "another audit" in m for m, c, _ in env["logs"])


@pytest.mark.parametrize("sid", [7, 999])
def test_a_qr_for_a_spool_not_on_the_list_marks_nothing(env, sid):
    """#7 is an Extra here: found, but not on the list. A QR never makes one, and an
    Extra's tile has none."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 7, "CR")
    start_with_id(env, "LR-MDB-1")
    scan(env, "ID:5")
    scan(env, "ID:7")
    ans = scan(env, tile_qr(sid))
    assert ans == {"type": "error", "msg": f"#{sid} isn't on this audit's list, so nothing was marked."}
    assert session()["scanned_items"] == [5, 7] and session()["rogue_items"] == [7]
    assert session()["last_found"] == 7


def test_a_malformed_qr_in_an_audit_marks_nothing_and_says_what_to_do(env):
    add_spool(env, 5, "LR-MDB-1")
    start_with_id(env, "LR-MDB-1")
    assert scan(env, "CMD:FOUND:5") == {"type": "error", "msg": logic.AUDIT_FOUND_QR_UNREAD}
    assert session()["scanned_items"] == []


@pytest.mark.parametrize("glued", ["ID:6", " ID:6", "SPL:6", "FIL:9"])
def test_a_tiles_qr_with_another_label_glued_on_says_it_didnt_read_right(env, glued):
    """Two scans can arrive glued (a scanner's read, then the next one's): the label after
    the QR is not part of its audit id. Review of 7e3720f, S-3: RED there, where the scan
    answered "That tile's QR is from another audit", which points at a stale QR that
    isn't one."""
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 6, "LR-MDB-1")
    start_with_id(env, "LR-MDB-1")
    assert scan_answer(f"{tile_qr(5)}{glued}", source="barcode") == {"type": "error",
                                                                      "msg": logic.AUDIT_FOUND_QR_UNREAD}
    assert session()["scanned_items"] == [] and session()["last_found"] is None
    assert writes(env) == []


def test_a_double_read_selects_the_spool_again_logs_nothing_and_never_takes_it_back(env):
    add_spool(env, 5, "LR-MDB-1")
    add_spool(env, 6, "LR-MDB-1")
    start_with_id(env, "LR-MDB-1")
    scan(env, tile_qr(5))
    scan(env, "ID:6")
    env["logs"].clear()
    assert scan_answer(tile_qr(5)) == {**AUDIT_SCAN, "heard": "#5 is already scanned"}
    assert scan_answer(tile_qr(5)) == {**AUDIT_SCAN, "heard": "#5 is already scanned"}
    assert session()["scanned_items"] == [5, 6] and session()["last_found"] == 5
    assert log_text(env) == [] and writes(env) == []


def test_outside_an_audit_a_tiles_qr_marks_nothing_and_says_why(env):
    add_spool(env, 5, "LR-MDB-1")
    ans = scan(env, tile_qr(5), source="barcode")
    assert ans == {"type": "error",
                   "msg": "No audit is running, so nothing was marked: a tile's QR works only during its audit."}
    assert writes(env) == [] and env["fake"].gets == [] and wire(env, 5) is None
    assert any(c == "WARNING" and "No audit is running" in m for m, c, _ in env["logs"])


def test_with_a_bulk_move_armed_a_tiles_qr_says_the_same_and_leaves_the_session_alone(env):
    """Above the bulk gates, as "Needs a label" is: they would call it a scan out of place."""
    state.BULK_MOVE_SESSION["active"] = True
    state.BULK_MOVE_SESSION["stage"] = "awaiting_source"
    try:
        ans = scan(env, tile_qr(5))
        assert ans["type"] == "error" and "No audit is running" in ans["msg"]
        assert state.BULK_MOVE_SESSION["stage"] == "awaiting_source"
    finally:
        state.reset_bulk_move()
