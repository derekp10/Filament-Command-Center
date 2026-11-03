"""Group 58, Derek's decisions of 2026-11-03 for the audit's look, the server half
(section H of docs/agent_docs/tasks/58-audit-label-truth.md):

S1 Done's question draws its spools as the panel's tiles do: every row of `park`,
   `file` and `stays` carries its colour and grams, from the rows the session stored
   at each scan (what the tiles draw), never a read of its own.
S2 A find with no label read says so, in its Activity Log line and in `heard`: a
   🔎 Find a spool pick "Found #1 with Find a spool, no label read (2 left)", any
   other "Found #1, no label read (2 left)"; a real label read keeps "Found #1 (2 left)".
S3 The report as data, for the report window: each spool once, under what the end
   did with it, from the stored rows and the end's own results; kept for the last 10
   audits (GET /api/audit/report?id=), and opened from a 📝 Read the report button on
   the report's Activity Log line, which keeps every word it had.
S4 A found tile's own 🏷️ (POST /api/audit/needs_label {audit_id, id}) marks the
   spool it names as needing a label, by the strip's rules and through its helper,
   and leaves the last found alone; the strip's "undo that" takes it back.
S5 The reasons Done gives for leaving a spool where it is name the audited place,
   never "here": they are read in the question, the report and a toast, away from
   the panel ("FCC has it in LR-MDB-1 already", "PM-DB-1 holds one spool, and 2 were
   found in it").

All of it through the Flask test client and the real session, on the real read and
write functions over tests/spoolman_extra_fake.SpoolmanHTTPFake, never a mocked
update_spool. RED on 69b0d95 unless a test says it pins what was already right.
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
import stock_report  # noqa: E402
from spoolman_extra_fake import _Resp  # noqa: E402
from test_audit_session_58 import (  # noqa: E402,F401
    AUDIT_SCAN, add_spool, env, log_text, report, scan, scan_answer, session, start,
)

PLACE = "CR-CT-1-R1"            # a cart row: a plain place with no slots


@pytest.fixture(autouse=True)
def _own_undo_stack(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-11-03")


def spools(env):
    return env["fake"].records["spool"]


def look(env, sid, hex_=None, multi=None, direction=None, remaining=None):
    """Give spool `sid` its own colour (its filament's) and grams, in Spoolman."""
    rec = spools(env)[sid]
    if hex_ is not None:
        rec["filament"]["color_hex"] = hex_
    if multi is not None:
        rec["filament"]["multi_color_hexes"] = multi
    if direction is not None:
        rec["filament"]["multi_color_direction"] = direction
    if remaining is not None:
        rec["remaining_weight"] = remaining


def live():
    res = app_module.app.test_client().get("/api/audit_session")
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def question(env):
    asked = scan(env, "CMD:DONE")
    assert asked["type"] == "audit_done_question", asked
    return asked


def _shelf(env):
    """An audit of a cart row: #1 found, #2 not scanned (Done parks it), #3 not
    scanned and moved to CR-CT-1 since (Done leaves it), and Extra #20 from LR-MDB-2
    slot 3 (Done files it here). Each with its own look."""
    for sid, hex_, grams in ((1, "111111", 900.0), (2, "222222", 250.0), (3, "333333", 75.5)):
        add_spool(env, sid, PLACE)
        look(env, sid, hex_, remaining=grams)
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    look(env, 20, "444444", multi="FF0000,00FF00", direction="coaxial", remaining=12.5)
    start(env, PLACE)
    scan(env, "ID:1")
    scan(env, "ID:20")
    spools(env)[3]["location"] = "CR-CT-1"


# ---------------------------------------------------------------------------
# S1: Done's question draws its spools as the panel's tiles do
# ---------------------------------------------------------------------------

def test_every_row_of_the_question_carries_its_tiles_look(env):
    _shelf(env)
    asked = question(env)
    assert asked["park"] == [{"id": 2, "display": "#2 Some Brand PLA (Red)", "where": PLACE, "slot": "",
                              "color": "222222", "color_direction": "longitudinal", "remaining_weight": 250.0}]
    assert asked["stays"] == [{"id": 3, "display": "#3 Some Brand PLA (Red)", "where": "CR-CT-1",
                               "why": "moved to CR-CT-1",
                               "color": "333333", "color_direction": "longitudinal", "remaining_weight": 75.5}]
    assert asked["file"] == [{"id": 20, "display": "#20 Some Brand PLA (Red)", "where": "LR-MDB-2 slot 3",
                              "color": "FF0000,00FF00", "color_direction": "coaxial", "remaining_weight": 12.5}]


def test_the_question_draws_each_spool_as_the_panel_did(env):
    """One look on both: the panel's poll and the question read the same stored row."""
    _shelf(env)
    panel = {row["id"]: row for key in ("expected", "rogue") for row in live()[key]}
    asked = question(env)
    for group in ("park", "stays", "file"):
        for row in asked[group]:
            tile = panel[row["id"]]
            assert (row["color"], row["color_direction"], row["remaining_weight"]) == \
                (tile["color"], tile["color_direction"], tile["remaining_weight"]), (group, row, tile)


def test_the_look_is_the_stored_rows_and_costs_no_read(env):
    """A filament recoloured, or a spool weighed, in Spoolman since its scan: the
    question still draws what the panel drew, and Done reads only its one list."""
    _shelf(env)
    for sid in (2, 3, 20):
        look(env, sid, "ABCDEF", multi="", direction="longitudinal", remaining=1.0)
    env["fake"].gets.clear()
    asked = question(env)
    assert [(r["id"], r["color"], r["remaining_weight"]) for r in asked["park"] + asked["stays"] + asked["file"]] \
        == [(2, "222222", 250.0), (3, "333333", 75.5), (20, "FF0000,00FF00", 12.5)]
    assert env["fake"].gets == ["/api/v1/spool"]          # plan_audit_done's one read


def test_a_spool_deleted_since_its_scan_keeps_its_look_in_the_question(env):
    """Its tile on the panel still drew it; the question says why it stays."""
    _shelf(env)
    del spools(env)[3]
    asked = question(env)
    assert asked["stays"] == [{"id": 3, "display": "#3 Some Brand PLA (Red)", "where": "",
                               "why": logic.AUDIT_GONE_WHY,
                               "color": "333333", "color_direction": "longitudinal", "remaining_weight": 75.5}]


def test_a_row_with_no_stored_data_draws_a_plain_swatch(env):
    """A session built by hand: no stored rows, so nothing to draw it with, and the
    question reads nothing for it."""
    add_spool(env, 5, PLACE)
    state.AUDIT_SESSION.update({"active": True, "audit_id": "x-1", "location_id": PLACE,
                                "expected_items": [5], "scanned_items": []})
    asked = question(env)
    assert asked["park"][0]["id"] == 5
    assert {k: asked["park"][0][k] for k in ("color", "color_direction", "remaining_weight")} == \
        {"color": "", "color_direction": "longitudinal", "remaining_weight": None}


# ---------------------------------------------------------------------------
# S2: a find with no label read says so
# ---------------------------------------------------------------------------

def _box(env):
    """An audit of LR-MDB-1 with #1, #2 and #3 filed there."""
    for sid in (1, 2, 3):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(sid))
    start(env, "LR-MDB-1")


@pytest.mark.parametrize("text, source, words, found_by", [
    ("ID:1", "search", "Found #1 with Find a spool, no label read (2 left)", "no_label"),   # 🔎 Find a spool
    ("ID:1", "keyboard", "Found #1, no label read (2 left)", "no_label"),   # a typed id; the legacy picker
    ("SPL:1", "barcode", "Found #1, no label read (2 left)", "no_label"),   # a scanner, but no ID: label
    ("ID:1", "barcode", "Found #1 (2 left)", "label"),                      # a real read of its label
], ids=["find-a-spool", "typed", "spl-label", "label-read"])
def test_a_finds_line_says_whether_a_label_was_read(env, text, source, words, found_by):
    """It read "Found #1 (2 left)" whatever found the spool, the words of a label read.
    The line and `heard` say the same, and so does the tile (`found_by`)."""
    _box(env)
    assert scan_answer(text, source=source) == {**AUDIT_SCAN, "heard": words}
    assert log_text(env)[0] == f"✅ {words}"
    assert session()["found_by"] == {"1": found_by}


@pytest.mark.parametrize("source, words", [
    ("search", "Found #7 with Find a spool, no label read: loaded on XL-1 from here"),
    ("keyboard", "Found #7, no label read: loaded on XL-1 from here"),
    ("barcode", "Found #7: loaded on XL-1 from here"),
], ids=["find-a-spool", "typed", "label-read"])
def test_a_spool_loaded_from_here_says_whether_a_label_was_read(env, source, words):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 7, "XL-1", physical_source="LR-MDB-1", physical_source_slot="2")
    start(env, "LR-MDB-1")
    assert scan_answer("ID:7", source=source) == {**AUDIT_SCAN, "heard": words}
    assert log_text(env)[0] == f"🔗 {words}."


def test_a_row_read_again_is_said_as_the_scan_that_read_it_found_it(env):
    """A spool scanned while Spoolman wasn't answering is read again by its next scan,
    and that scan's words are the find's."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 7, "XL-1", physical_source="LR-MDB-1", physical_source_slot="2")
    start(env, "LR-MDB-1")
    env["fake"].down = True
    scan(env, "ID:7")
    env["fake"].down = False
    env["logs"].clear()
    heard = "Found #7 with Find a spool, no label read: loaded on XL-1 from here"
    assert scan_answer("ID:7", source="search")["heard"] == heard
    assert log_text(env) == [f"🔗 {heard}."]


def test_a_direct_call_that_doesnt_say_how_keeps_a_label_reads_words(env):
    """Pins what was already right: process_audit_scan's own callers (a test, an old
    caller) that pass no `how` get the words they always had."""
    _box(env)
    assert logic.process_audit_scan({"type": "spool", "id": 1}) == {"status": "success",
                                                                     "heard": "Found #1 (2 left)"}


# ---------------------------------------------------------------------------
# S5: the reasons name the audited place, never "here"
# ---------------------------------------------------------------------------

HERE_ALREADY = "FCC has it in LR-MDB-1 already"


def yes(env, asked):
    """The Yes to Done's question, for everything it showed (where it showed each Extra)."""
    body = {"audit_id": asked["audit_id"], "today": "2026-11-03", "ids": [r["id"] for r in asked["park"]],
            "file_ids": [r["id"] for r in asked["file"]],
            "file_where": {str(r["id"]): r["where"] for r in asked["file"]}}
    res = app_module.app.test_client().post("/api/audit/park", json=body)
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def _extra_from_box_2(env):
    """An audit of LR-MDB-1 with #1 filed there, and Extra #20 from LR-MDB-2 slot 3."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    scan(env, "ID:20")


def test_an_extra_filed_here_at_the_last_look_says_where_fcc_has_it(env, monkeypatch):
    """The question showed #20 to be filed; another tab filed it in LR-MDB-1 in the
    moment between the Yes's plan and its last look (_audit_file_one)."""
    _extra_from_box_2(env)
    asked = question(env)
    real = spoolman_api.get_spool_answer

    def filed_meanwhile(sid):
        if sid == 20:
            spools(env)[20].update(location="LR-MDB-1")
        return real(sid)

    monkeypatch.setattr(spoolman_api, "get_spool_answer", filed_meanwhile)
    result = yes(env, asked)
    assert [(s["id"], s["why"]) for s in result["stayed"]] == [(20, HERE_ALREADY)]
    assert f"#20 Some Brand PLA (Red) → {HERE_ALREADY}" in report(env)


def test_an_extra_the_yes_names_and_the_plan_left_out_says_where_fcc_has_it(env):
    """Filed in LR-MDB-1 while the question sat open, so the Yes's own plan leaves it
    out (_audit_file_dropped)."""
    _extra_from_box_2(env)
    asked = question(env)
    spools(env)[20].update(location="LR-MDB-1", extra=dict(spools(env)[20]["extra"], container_slot='"2"'))
    result = yes(env, asked)
    assert result["stayed"] == [{"id": 20, "display": "#20 Some Brand PLA (Red)", "where": "LR-MDB-1",
                                 "why": HERE_ALREADY}]


def test_the_strips_hint_for_an_extra_fcc_has_here_already_names_the_place(env):
    """Filed in LR-MDB-1 after the location scan, so it isn't on the list: an Extra
    whose hint says why Done leaves it (the strip reads it, C6)."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "LR-MDB-1")
    spools(env)[20].update(location="LR-MDB-1")
    scan(env, "ID:20")
    (row,) = live()["rogue"]
    assert row["at_done"] == {"files": False, "why": HERE_ALREADY}


def test_a_one_spool_place_with_two_extras_says_they_were_found_in_it(env):
    env["rows"].append({"LocationID": "PM-DB-1", "Name": "Dryer 1", "Type": "Dryer Box", "Max Spools": "1",
                        "parent_id": "CR"})
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    add_spool(env, 21, "CR-CT-1")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    scan(env, "ID:21")
    why = "PM-DB-1 holds one spool, and 2 were found in it"
    assert [(s["id"], s["why"]) for s in logic.plan_audit_done(session())["stays"]] == [(20, why), (21, why)]
    env["logs"].clear()
    assert "audit_ended" in scan(env, "CMD:DONE")          # nothing to park or file: Done ends
    assert f"#20 Some Brand PLA (Red) → {why}" in report(env)


# ---------------------------------------------------------------------------
# S4: a found tile's own 🏷️
# ---------------------------------------------------------------------------

LABEL = "needs_label_print"


def post(path, body):
    res = app_module.app.test_client().post(path, json=body)
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def tile_mark(sid, audit_id=None):
    """A found tile's 🏷️ pressed."""
    return post("/api/audit/needs_label", {"audit_id": audit_id or session()["audit_id"], "id": sid})


def undo_mark(sid, audit_id=None):
    return post("/api/audit/needs_label_undo", {"audit_id": audit_id or session()["audit_id"], "id": sid})


def wire(env, sid):
    """The label status as Spoolman holds it: 'true', 'false', or None for none."""
    return env["fake"].extra("spool", sid).get(LABEL)


def writes(env):
    return [p[1] for p in env["fake"].patches]


def tile(sid):
    return next(r for key in ("expected", "rogue", "trail") for r in live()[key] if r["id"] == sid)


def _found_two(env):
    """LR-MDB-1 with #5 and #6, both found (#6 last), and #7 not scanned."""
    for sid in (5, 6, 7):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(sid - 4))
    start(env, "LR-MDB-1")
    scan(env, "ID:5")
    scan(env, "ID:6")
    env["logs"].clear()
    env["fake"].patches.clear()
    env["fake"].gets.clear()


def test_a_tiles_mark_marks_that_spool_and_leaves_the_last_found_alone(env):
    _found_two(env)
    before = env["fake"].extra("spool", 5)
    assert tile_mark(5) == {"success": True, "msg": "#5 is marked: it needs a label."}
    assert wire(env, 5) == "true" and writes(env) == [5]
    assert {k: v for k, v in env["fake"].extra("spool", 5).items() if k != LABEL} == before   # siblings kept
    assert session()["last_found"] == 6 and live()["last_found"]["id"] == 6
    assert session()["label_flagged"] == {"5": None}
    got = tile(5)
    assert got["label_status"] is True and got["flagged_here"] is True
    assert log_text(env) == ["🏷️ #5 Some Brand PLA (Red): marked as needing a label."]


def test_an_extras_tile_marks_it_too(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 20, "CR-CT-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:20")
    scan(env, "ID:1")
    assert tile_mark(20)["success"] is True
    assert wire(env, 20) == "true" and session()["last_found"] == 1
    assert tile(20)["flagged_here"] is True


def test_a_spool_loaded_from_here_can_be_marked_as_the_strip_marks_it(env):
    """The strip's rule: any spool this audit found."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 7, "XL-1", physical_source="LR-MDB-1", physical_source_slot="2")
    start(env, "LR-MDB-1")
    scan(env, "ID:7")
    scan(env, "ID:1")
    assert tile_mark(7)["success"] is True and wire(env, 7) == "true"


def test_a_second_tap_takes_the_mark_back_on_a_spool_that_isnt_the_last_found(env):
    _found_two(env)
    tile_mark(5)
    assert undo_mark(5) == {"success": True, "msg": "Undone: #5 has no label status again."}
    assert wire(env, 5) is None and session()["label_flagged"] == {}
    assert session()["last_found"] == 6
    assert tile(5)["flagged_here"] is False and tile(5)["label_status"] is None


def test_a_mark_on_a_confirmed_label_is_undone_to_confirmed(env):
    add_spool(env, 5, "LR-MDB-1", needs_label_print=False)
    add_spool(env, 6, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:5")
    scan(env, "ID:6")
    tile_mark(5)
    assert session()["label_flagged"] == {"5": False} and wire(env, 5) == "true"
    assert undo_mark(5)["msg"] == "Undone: #5's label is confirmed again."
    assert wire(env, 5) == "false"


def test_a_flag_already_up_says_so_and_writes_nothing(env):
    add_spool(env, 5, "LR-MDB-1", needs_label_print=True)
    start(env, "LR-MDB-1")
    scan(env, "ID:5")
    env["fake"].patches.clear()
    assert tile_mark(5) == {"success": True, "already": True, "msg": "#5 is already flagged for a new label."}
    assert writes(env) == [] and session()["label_flagged"] == {}


def test_a_double_tap_is_one_write(env):
    _found_two(env)
    tile_mark(5)
    assert tile_mark(5)["already"] is True
    assert writes(env) == [5] and session()["label_flagged"] == {"5": None}


@pytest.mark.parametrize("sid, words", [
    (7, "#7 hasn't been found in this audit, so nothing was marked."),     # on the list, not scanned
    (99, "#99 hasn't been found in this audit, so nothing was marked."),   # not this audit's at all
    ("x", "That press didn't name a spool, so nothing was marked."),
], ids=["not-scanned", "not-this-audits", "no-id"])
def test_a_spool_this_audit_hasnt_found_is_refused(env, sid, words):
    _found_two(env)
    add_spool(env, 99, "CR-CT-1")
    assert tile_mark(sid) == {"success": False, "msg": words}
    assert writes(env) == [] and env["fake"].gets == [] and session()["label_flagged"] == {}
    assert any(c == "WARNING" and words in m for m, c, _ in env["logs"]), env["logs"]


@pytest.mark.parametrize("sid", [5, 20], ids=["an-expected-tile-pressed-again", "an-extra-taken-back"])
def test_a_find_taken_back_is_refused(env, sid):
    _found_two(env)
    add_spool(env, 20, "CR-CT-1")
    scan(env, "ID:20")
    assert post("/api/audit/found", {"audit_id": session()["audit_id"], "id": sid, "found": False})["success"]
    env["fake"].patches.clear()
    assert tile_mark(sid)["success"] is False and writes(env) == []


def test_another_audits_tile_marks_nothing(env):
    _found_two(env)
    assert tile_mark(5, audit_id="x-99") == {"success": False, "stale": True, "msg": "That audit has already ended."}
    assert writes(env) == [] and session()["label_flagged"] == {}


def test_with_no_audit_it_marks_nothing(env):
    _found_two(env)
    audit_id = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    env["fake"].patches.clear()
    assert tile_mark(5, audit_id=audit_id) == {"success": False, "stale": True,
                                                "msg": "That audit has already ended."}
    assert writes(env) == []


def test_while_the_audit_is_finishing_it_marks_nothing(env):
    _found_two(env)
    assert logic._AUDIT_END_LOCK.acquire(False)
    try:
        ans = tile_mark(5)
    finally:
        logic._AUDIT_END_LOCK.release()
    assert ans == {"success": False, "busy": True, "msg": logic.AUDIT_FINISHING_MSG}
    assert writes(env) == []


def test_an_archived_spool_is_refused(env):
    """The Backlog can't show it, so the mark would be seen nowhere."""
    _found_two(env)
    spools(env)[5]["archived"] = True
    ans = tile_mark(5)
    assert ans["success"] is False and "archived" in ans["msg"] and "Backlog" in ans["msg"]
    assert writes(env) == [] and session()["label_flagged"] == {}


def test_a_spool_spoolman_wont_answer_for_is_refused(env):
    _found_two(env)
    env["fake"].down = True
    ans = tile_mark(5)
    assert ans["success"] is False and "Couldn't read #5" in ans["msg"]
    assert writes(env) == [] and session()["label_flagged"] == {}


def test_a_rejected_write_surfaces_spoolmans_words_and_leaves_no_mark(env, monkeypatch):
    _found_two(env)

    def refused(url, json=None, timeout=None, **kw):  # noqa: A002
        return _Resp(500, {"message": "<i>nope</i>"})

    monkeypatch.setattr(spoolman_api.requests, "patch", refused)
    ans = tile_mark(5)
    assert ans["success"] is False and "Couldn't mark #5" in ans["msg"] and "<i>nope</i>" in ans["msg"]
    assert session()["label_flagged"] == {}
    errors = [m for m, c, _ in env["logs"] if c == "ERROR"]
    assert len(errors) == 1 and "&lt;i&gt;nope&lt;/i&gt;" in errors[0], errors


def test_a_write_reported_failed_that_landed_counts(env, monkeypatch):
    """update_spool's timeout is a READ timeout: refused, the mark would stand on the
    record with no way to undo it."""
    _found_two(env)

    def late(url, json=None, timeout=None, **kw):  # noqa: A002
        env["fake"].patch(url, json=json, timeout=timeout)
        raise TimeoutError("read timed out (test)")

    monkeypatch.setattr(spoolman_api.requests, "patch", late)
    assert tile_mark(5) == {"success": True, "msg": "#5 is marked: it needs a label."}
    assert wire(env, 5) == "true" and session()["label_flagged"] == {"5": None}


def test_a_tiles_mark_refreshes_the_idle_timer(env):
    """A person pressed something: a mark made near the end of the idle window must
    not see the audit end a moment later."""
    _found_two(env)
    a_while_ago = time.time() - 60
    session()["last_activity_ts"] = a_while_ago
    assert tile_mark(5)["success"] is True
    assert session()["last_activity_ts"] > a_while_ago


def test_the_strips_mark_still_marks_the_last_found(env):
    """One helper behind both: CMD:NEEDLABEL acts on the last found, a tile on its own."""
    _found_two(env)
    assert scan(env, "CMD:NEEDLABEL") == {**AUDIT_SCAN, "said": "#6 is marked: it needs a label."}
    assert tile_mark(5)["success"] is True
    assert session()["label_flagged"] == {"6": None, "5": None} and session()["last_found"] == 6


def test_a_mark_made_on_a_tile_is_in_the_report(env):
    _found_two(env)
    tile_mark(5)
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    assert "<b>Needs a label:</b> #5 Some Brand PLA (Red)" in report(env)


# ---------------------------------------------------------------------------
# S3: the report as data, and its button on the Activity Log line
# ---------------------------------------------------------------------------

HEAD_WHY = "loaded on XL-1: an audit never takes a spool off a printer"
GONE = ("FCC no longer has that audit's report: it keeps the last 10, and a restart clears them. "
        "Its line in the Activity Log has the same report in words.")
BUTTON = ('<button type="button" class="btn btn-sm btn-outline-info ms-2 py-0 px-1 fcc-audit-report-open" '
          'data-audit-report="{}">📝 Read the report</button>')


@pytest.fixture(autouse=True)
def _own_reports(monkeypatch):
    monkeypatch.setattr(logic, "_AUDIT_REPORTS", {}, raising=False)


def get_report(audit_id):
    res = app_module.app.test_client().get("/api/audit/report", query_string={"id": audit_id})
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def kinds(report_data):
    return [(g["kind"], [r["id"] for r in g["rows"]]) for g in report_data["groups"]]


def _cart_row(env, monkeypatch=None):
    """An audit of the cart row CR-CT-1-R1, every spool its own colour:
      #1 found by its label; #2 found, then marked as needing a label (the strip);
      #3 not scanned (Done parks it); #4 not scanned and moved to CR-CT-1 since (Done
      leaves it); #5 not scanned, whose park Spoolman refuses when `monkeypatch` is
      given; Extra #20 from LR-MDB-2 slot 3 (Done files it), marked from its tile;
      Extra #21 on XL-1 (Done leaves it); #7 on XL-2, loaded from this row."""
    for sid, hex_ in ((1, "010101"), (2, "020202"), (3, "030303"), (4, "040404"), (5, "050505")):
        add_spool(env, sid, PLACE)
        look(env, sid, hex_, remaining=100.0 + sid)
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    look(env, 20, "202020", remaining=120.0)
    add_spool(env, 21, "XL-1")
    look(env, 21, "212121", remaining=121.0)
    add_spool(env, 7, "XL-2", physical_source=PLACE, physical_source_slot="")
    look(env, 7, "070707", remaining=107.0)
    start(env, PLACE)
    scan(env, "ID:1", source="barcode")
    scan(env, "ID:2")
    scan(env, "CMD:NEEDLABEL")
    for sid in (20, 21, 7):
        scan(env, f"ID:{sid}")
    assert tile_mark(20)["success"] is True
    spools(env)[4]["location"] = "CR-CT-1"
    if monkeypatch is not None:
        real = env["fake"].patch

        def refuse_5(url, json=None, timeout=None, **kw):  # noqa: A002
            if url.rstrip("/").endswith("/spool/5"):
                return _Resp(400, {"message": "nope (test)"})
            return real(url, json=json, timeout=timeout, **kw)

        monkeypatch.setattr(spoolman_api.requests, "patch", refuse_5)
    env["logs"].clear()


def _row(sid, hex_, grams, where, why="", needs_label=False, display=None):
    return {"id": sid, "display": display or f"#{sid} Some Brand PLA (Red)", "color": hex_,
            "color_direction": "longitudinal", "remaining_weight": grams, "where": where, "why": why,
            "needs_label": needs_label}


def test_a_yes_answers_the_report_each_spool_once_under_what_done_did(env, monkeypatch):
    _cart_row(env, monkeypatch)
    audit_id = session()["audit_id"]
    result = yes(env, question(env))
    got = result["report"]
    assert {k: got[k] for k in ("audit_id", "place", "why", "summary", "found", "expected", "extras", "loaded",
                                "perfect")} == {
        "audit_id": audit_id, "place": PLACE, "why": "done", "summary": "Found 2 of 5.", "found": 2,
        "expected": 5, "extras": 2, "loaded": 1, "perfect": False}
    assert got["groups"] == [
        {"kind": "parked", "title": "Parked at Unknown", "rows": [_row(3, "030303", 103.0, PLACE)]},
        {"kind": "filed", "title": f"Filed in {PLACE}",
         "rows": [_row(20, "202020", 120.0, "LR-MDB-2 slot 3", needs_label=True)]},
        {"kind": "stayed", "title": "Left where they are",
         "rows": [_row(4, "040404", 104.0, "CR-CT-1", "moved to CR-CT-1"),
                  _row(21, "212121", 121.0, "XL-1", HEAD_WHY)]},
        {"kind": "failed", "title": "Couldn't be moved",
         "rows": [_row(5, "050505", 105.0, PLACE, 'HTTP 400: {"message": "nope (test)"}')]},   # Spoolman's words
        {"kind": "trail", "title": f"Loaded from {PLACE}", "rows": [_row(7, "070707", 107.0, "XL-2")]},
        {"kind": "needs_label", "title": "Needs a label", "rows": [_row(2, "020202", 102.0, PLACE, needs_label=True)]},
    ]
    ids = [r["id"] for g in got["groups"] for r in g["rows"]]
    assert sorted(ids) == [2, 3, 4, 5, 7, 20, 21] and len(ids) == len(set(ids))      # each once; #1 isn't listed
    assert get_report(audit_id) == {"success": True, "report": got}


def test_a_cancel_reports_what_wasnt_scanned_and_the_extras_and_opens_nothing(env):
    _cart_row(env)
    audit_id = session()["audit_id"]
    env["fake"].gets.clear()
    answer = scan_answer("CMD:CANCEL")
    assert answer == {**AUDIT_SCAN, "audit_ended": {"id": audit_id, "why": "cancel"}}      # no report on it
    got = get_report(audit_id)["report"]
    assert got["why"] == "cancel" and got["summary"] == "Found 2 of 5."
    assert got["groups"] == [
        {"kind": "missing", "title": "Not scanned", "rows": [_row(3, "030303", 103.0, PLACE),
                                                             _row(4, "040404", 104.0, PLACE),
                                                             _row(5, "050505", 105.0, PLACE)]},
        {"kind": "extra", "title": "Extra (filed elsewhere)",
         "rows": [_row(20, "202020", 120.0, "LR-MDB-2 slot 3", needs_label=True), _row(21, "212121", 121.0, "XL-1")]},
        {"kind": "trail", "title": f"Loaded from {PLACE}", "rows": [_row(7, "070707", 107.0, "XL-2")]},
        {"kind": "needs_label", "title": "Needs a label", "rows": [_row(2, "020202", 102.0, PLACE, needs_label=True)]},
    ]
    assert env["fake"].gets == []                           # the stored rows: no read


def test_an_idle_end_keeps_its_report_and_its_line_carries_the_button(env):
    _cart_row(env)
    audit_id = session()["audit_id"]
    env["fake"].gets.clear()
    session()["last_activity_ts"] = time.time() - state.AUDIT_IDLE_TIMEOUT_SECONDS - 5
    app_module._check_audit_idle_timeout()
    (line,) = log_text(env)
    assert line.endswith("needs a label #2, #20. " + BUTTON.format(audit_id)), line
    got = get_report(audit_id)["report"]
    assert got["why"] == "idle" and [k for k, _ in kinds(got)] == ["missing", "extra", "trail", "needs_label"]
    assert env["fake"].gets == []


def test_a_done_with_nothing_to_park_answers_its_report_with_why_each_stays(env):
    """Nothing to park or file, so no question: the report says why each stays."""
    add_spool(env, 1, PLACE)
    add_spool(env, 2, PLACE)
    add_spool(env, 21, "XL-1")
    add_spool(env, 22, "CR-CT-1")
    start(env, PLACE)
    for sid in (1, 21, 22):
        scan(env, f"ID:{sid}")
    spools(env)[2]["location"] = "CR-CT-1"           # moved on since the location scan
    spools(env)[22]["location"] = PLACE              # filed here since its scan
    audit_id = session()["audit_id"]
    answer = scan_answer("CMD:DONE")
    assert answer["audit_ended"] == {"id": audit_id, "why": "done"}
    got = answer["report"]
    assert kinds(got) == [("missing", [2]), ("extra", [21, 22])]
    rows = {r["id"]: r for g in got["groups"] for r in g["rows"]}
    assert (rows[2]["where"], rows[2]["why"]) == ("CR-CT-1", "moved to CR-CT-1")
    assert rows[21]["why"] == HEAD_WHY
    assert (rows[22]["where"], rows[22]["why"]) == (PLACE, f"FCC has it in {PLACE} already")
    assert get_report(audit_id)["report"] == got


def test_an_extra_a_yes_didnt_name_because_fcc_has_it_here_is_left_where_it_is(env):
    """Filed in this place before Done, so the question didn't show it: the report
    still lists it once."""
    add_spool(env, 1, PLACE)
    add_spool(env, 2, PLACE)
    add_spool(env, 22, "CR-CT-1")
    start(env, PLACE)
    scan(env, "ID:1")
    scan(env, "ID:22")
    spools(env)[22]["location"] = PLACE
    got = yes(env, question(env))["report"]
    assert kinds(got) == [("parked", [2]), ("stayed", [22])]
    assert got["groups"][1]["title"] == "Left where it is"
    assert got["groups"][1]["rows"][0]["why"] == f"FCC has it in {PLACE} already"


def test_a_yes_that_leaves_the_audit_open_answers_no_report(env, monkeypatch):
    """Nothing landed, so the audit runs on and there is no report yet."""
    add_spool(env, 1, PLACE)
    add_spool(env, 5, PLACE)
    start(env, PLACE)
    scan(env, "ID:1")
    real = env["fake"].patch
    monkeypatch.setattr(spoolman_api.requests, "patch", lambda url, json=None, timeout=None, **kw:
                        _Resp(400, {"message": "nope (test)"}) if url.rstrip("/").endswith("/spool/5")
                        else real(url, json=json, timeout=timeout, **kw))
    audit_id = session()["audit_id"]
    result = yes(env, question(env))
    assert "report" not in result and "audit_ended" not in result and session()["active"] is True
    assert get_report(audit_id)["success"] is False


def test_the_report_line_carries_the_button_after_its_heading(env, monkeypatch):
    """Derek likes the line as it is: it keeps every word, with the button after its
    heading, and says what it is in its `meta`, as the 🛑 Review's line does."""
    seen = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, cat="INFO", color=None, meta=None:
                        seen.append((msg, cat, color, meta)))
    for sid in (1, 2):
        add_spool(env, sid, "LR-MDB-2", name=f"Filed {sid}")
    add_spool(env, 9, "CR-CT-1-R2", name="Stray", container_slot="3")
    add_spool(env, 7, "XL-1", name="Running", physical_source="LR-MDB-2")
    start(env, "LR-MDB-2")
    for sid in (1, 9, 7):
        scan(env, f"ID:{sid}")
    audit_id = session()["audit_id"]
    seen.clear()
    scan(env, "CMD:CANCEL")
    (msg, cat, color, meta), = [entry for entry in seen if "Audit Report" in entry[0]]
    assert msg == ("📝 <b>Audit Report: LR-MDB-2</b> " + BUTTON.format(audit_id) + "<br>Found 1 of 2.<br>"
                   "❌ <b>Missing:</b> #2 Some Brand PLA (Filed 2)<br>"
                   "⚠️ <b>Extra:</b> #9 Some Brand PLA (Stray) → CR-CT-1-R2 slot 3<br>"
                   "🔗 <b>Loaded from here:</b> #7 Some Brand PLA (Running) → XL-1")
    assert (cat, color, meta) == ("INFO", "ffaa00", {"type": "audit_report", "audit_id": audit_id})


def test_the_buttons_audit_id_is_escaped(env):
    """An id is FCC's own (new_audit_id), but it goes into an HTML attribute."""
    add_spool(env, 1, PLACE)
    state.AUDIT_SESSION.update({"active": True, "audit_id": 'x"><b>-1', "location_id": PLACE,
                                "expected_items": [1], "scanned_items": []})
    scan(env, "CMD:CANCEL")
    line = report(env)
    assert 'data-audit-report="x&quot;&gt;&lt;b&gt;-1"' in line and '"><b>' not in line
    assert get_report('X"><B>-1')["success"] is True                  # an id is read without case


def test_an_end_with_no_place_has_no_button_and_an_empty_report(env):
    scan(env, "CMD:AUDIT")
    audit_id = session()["audit_id"]
    answer = scan_answer("CMD:DONE")
    assert answer["report"] == {"audit_id": audit_id, "place": "", "why": "done",
                                "summary": "Audit ended before a location was scanned: nothing was checked.",
                                "found": 0, "expected": 0, "extras": 0, "loaded": 0, "perfect": False,
                                "groups": []}
    assert report(env) == ("📝 <b>Audit Report:</b> Audit ended before a location was scanned: "
                           "nothing was checked.")


def test_a_perfect_match_says_so_in_the_report(env):
    add_spool(env, 1, PLACE)
    start(env, PLACE)
    scan(env, "ID:1")
    got = scan_answer("CMD:DONE")["report"]
    assert got["perfect"] is True and got["summary"] == "Found 1 of 1. ✅ Perfect Match! All items accounted for."
    assert got["groups"] == []


def test_fcc_keeps_the_last_ten_reports(env):
    ids = []
    for _ in range(11):
        start(env, "SHELF-1")
        ids.append(session()["audit_id"])
        scan(env, "CMD:CANCEL")
    assert get_report(ids[0]) == {"success": False, "msg": GONE}
    assert all(get_report(i)["success"] for i in ids[1:])


@pytest.mark.parametrize("query, msg", [
    ({"id": "boot-1"}, "gone"),           # never one of FCC's, or from before a restart
    ({}, "unnamed"),
    ({"id": "  "}, "unnamed"),
])
def test_a_report_fcc_doesnt_have_says_so_in_words(env, query, msg):
    words = {"gone": GONE, "unnamed": "No audit was named, so there is no report to show."}[msg]
    res = app_module.app.test_client().get("/api/audit/report", query_string=query)
    assert res.status_code == 200 and res.get_json() == {"success": False, "msg": words}


def test_the_report_reads_nothing_even_with_spoolman_down(env):
    """Its rows are the session's stored rows and the end's own results."""
    _cart_row(env)
    env["fake"].down = True
    env["fake"].gets.clear()
    got = logic._audit_report_data(session(), "cancel")
    assert env["fake"].gets == []
    assert {r["id"]: r["color"] for g in got["groups"] for r in g["rows"]} == {
        3: "030303", 4: "040404", 5: "050505", 20: "202020", 21: "212121", 7: "070707", 2: "020202"}
