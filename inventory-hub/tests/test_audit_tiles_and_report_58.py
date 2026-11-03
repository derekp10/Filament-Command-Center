"""Group 58, Derek's decisions of 2026-11-03 for the audit's look, the server half
(section H of docs/agent_docs/tasks/58-audit-label-truth.md):

S1 Done's question draws its spools as the panel's tiles do: every row of `park`,
   `file` and `stays` carries its colour and grams, from the rows the session stored
   at each scan (what the tiles draw), never a read of its own.
S2 A find with no label read says so, in its Activity Log line and in `heard`: a
   🔎 Find a spool pick "Found #1 with Find a spool, no label read (2 left)", any
   other "Found #1, no label read (2 left)"; a real label read keeps "Found #1 (2 left)".
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

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402
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
