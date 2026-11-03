"""Done files the Extras here (Group 58; Derek, 2026-11-03, C: "Select it for that
location"). Built on Claude's safe defaults for his look, in commits of their own,
so it comes out cleanly if he says no; this whole file goes with it.

A spool found here that FCC has somewhere else (an Extra, scanned or picked in Find)
is moved here by Done's Yes, in the same question as the park and the same Undo:
C1 who is filed, C2 the write, C3 Done asks, C4 the answer and the report, C5 one
Undo (the filed group first), C6 the hint an Extra's row carries for the strip.

Everything runs through the real /api/identify_scan, /api/audit/park and /api/undo,
on the real update_spool over tests/spoolman_extra_fake.SpoolmanHTTPFake, never a
mocked update_spool or perform_smart_move. RED on 296e2a7 unless a test says it
pins what was already right.
"""
from __future__ import annotations

import json
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
from spoolman_extra_fake import _Resp  # noqa: E402
from test_audit_session_58 import (  # noqa: E402,F401
    AUDIT_SCAN, add_spool, env, log_text, report, scan, scan_answer, session, start,
)

RED = "Some Brand PLA (Red)"
HEAD_WHY = "loaded on XL-1: an audit never takes a spool off a printer"
PRINTER_WHY = "an audit never loads a printer"
# PIN UPDATED DELIBERATELY (review of 7e3720f, S-7): the note names the gesture that sets
# a slot (the spool's label, then the slot's); "scan its slot label afterwards" picked up
# the slot's own spool, or moved a buffered one in.
ONE_SLOT = "It goes in with no slot: scan it, then its slot's label, to set one."
MORE_SLOTS = "They go in with no slot: scan each one, then its slot's label, to set it."
_ALL = object()


@pytest.fixture(autouse=True)
def _own_undo_stack(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-11-03")


@pytest.fixture
def places(env):
    """One-spool places: a single-slot dryer box (Max Spools 1, and one at "0", which
    counts as single-slot too), and a row whose Max Spools is 1."""
    env["rows"].extend([
        {"LocationID": "PM-DB-1", "Name": "Dryer 1", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "CR"},
        {"LocationID": "PM-DB-2", "Name": "Dryer 2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "CR"},
        {"LocationID": "PM-DB-0", "Name": "Dryer 0", "Type": "Dryer Box", "Max Spools": "0", "parent_id": "CR"},
        {"LocationID": "SPOT-1", "Name": "Holder 1", "Type": "Spool Holder", "Max Spools": "1", "parent_id": "CR"},
        {"LocationID": "SPOT-2", "Name": "Holder 2", "Type": "Spool Holder", "Max Spools": "1", "parent_id": "CR"},
    ])
    return env


def spools(env):
    return env["fake"].records["spool"]


def extra_of(env, sid):
    return {k: json.loads(v) for k, v in env["fake"].extra("spool", sid).items()}


def patched(env):
    return [p[1] for p in env["fake"].patches]


def plan():
    return logic.plan_audit_done(session())


def question(env):
    asked = scan(env, "CMD:DONE")
    assert asked["type"] == "audit_done_question", asked
    return asked


def yes(env, asked=None, ids=None, file_ids=_ALL, today="2026-11-03", audit_id=None, file_where=_ALL):
    """The Yes to Done's question: every spool it showed, or what the test says.
    `file_ids` left out of the body when the test passes None (a page from before C).
    `file_where`, as the page sends it: where the question showed each Extra ({id:
    where}), sent with `file_ids`; None leaves it out, a dict is sent as it is.
    PIN UPDATED DELIBERATELY (review of 7e3720f, R-1): the page sends it, and the
    server checks each Extra against it."""
    asked = asked or question(env)
    body = {"audit_id": audit_id or asked["audit_id"], "today": today,
            "ids": [r["id"] for r in asked["park"]] if ids is None else ids}
    if file_ids is _ALL:
        body["file_ids"] = [r["id"] for r in asked["file"]]
    elif file_ids is not None:
        body["file_ids"] = file_ids
    if file_where is _ALL:
        if file_ids is not None:
            body["file_where"] = {str(r["id"]): r["where"] for r in asked["file"]}
    elif file_where is not None:
        body["file_where"] = file_where
    res = app_module.app.test_client().post("/api/audit/park", json=body)
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def ask_undo(env):
    return env["client"].post("/api/undo", json={}).get_json()


def yes_undo(env, asked=None):
    asked = asked or ask_undo(env)
    assert asked.get("requires_confirm") is True, asked
    return env["client"].post("/api/undo", json={"confirm": True, "undo_id": asked["undo_id"],
                                                 "confirmed_toolheads": []}).get_json()


def _refuse(env, monkeypatch, *sids, message="nope (test)"):
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        if int(url.rstrip("/").rsplit("/", 1)[1]) in sids:
            return _Resp(400, {"message": message})
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)
    return real


def _lands_but_times_out(env, monkeypatch, *sids):
    real = env["fake"].patch

    def patch(url, json=None, timeout=None, **kw):           # noqa: A002
        answer = real(url, json=json, timeout=timeout, **kw)
        if int(url.rstrip("/").rsplit("/", 1)[1]) in sids:
            raise TimeoutError("read timed out (test)")
        return answer

    monkeypatch.setattr(spoolman_api.requests, "patch", patch)


def _changes_at_last_look(monkeypatch, sid, change):
    """`change` lands in the moment after the plan: the Yes's own read of the spool,
    right before its write, is the first to see it."""
    real = spoolman_api.get_spool_answer

    def spy(asked):
        if asked == sid:
            change()
        return real(asked)

    monkeypatch.setattr(spoolman_api, "get_spool_answer", spy)


def _extra_here(env, place="LR-MDB-1", sid=20, at="LR-MDB-2", found=(1,), **extra):
    """An audit of `place` with #1 filed there, and Extra #`sid` that FCC has at `at`."""
    for n in found:
        add_spool(env, n, place, container_slot=str(n))
    add_spool(env, sid, at, **extra)
    start(env, place)
    for n in found:
        scan(env, f"ID:{n}")
    scan(env, f"ID:{sid}")
    assert sid in session()["rogue_items"], session()


def _file_row(sid, where, location, slot=""):
    return {"id": sid, "display": f"#{sid} {RED}", "where": where, "location": location, "slot": slot}


def _stay(sid, why, where):
    return {"id": sid, "display": f"#{sid} {RED}", "where": where, "why": why}


# ---------------------------------------------------------------------------
# C1: who is filed
# ---------------------------------------------------------------------------

def test_an_extra_from_another_place_is_filed_here_and_its_slot_kept_for_the_undo(env):
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    got = plan()
    assert got["park"] == [] and got["stays"] == []
    assert got["file"] == [_file_row(20, "LR-MDB-2 slot 3", "LR-MDB-2", "3")]
    assert got["file_note"] == ONE_SLOT                      # LR-MDB-1 is a multi-slot box
    assert patched(env) == []


@pytest.mark.parametrize("at, extra, where", [
    ("", {}, "Unassigned"),
    ("UNKNOWN", {"fcc_pre_audit_location": "CR-CT-1:2@2026-11-01"}, "Unknown"),
    ("CR-CT-1", {}, "CR-CT-1"),
    ("XL", {}, "XL"),               # filed on a multi-head printer's own row: loaded nowhere
])
def test_anything_else_is_filed_here(env, at, extra, where):
    _extra_here(env, at=at, **extra)
    assert plan()["file"] == [_file_row(20, where, at)]


def test_a_place_with_no_slots_needs_no_slot_note(env):
    _extra_here(env, place="CR-CT-1", at="LR-MDB-2", container_slot="3")
    got = plan()
    assert [r["id"] for r in got["file"]] == [20] and got["file_note"] == ""


def test_two_extras_into_a_multi_slot_box_are_told_so(env):
    _extra_here(env, at="CR-CT-1")
    add_spool(env, 21, "CR")
    scan(env, "ID:21")
    got = plan()
    assert [r["id"] for r in got["file"]] == [20, 21]
    assert got["file_note"] == MORE_SLOTS          # PIN UPDATED DELIBERATELY (S-7): the gesture's words


def _box_of_four(env, found, missing=(), extras=((20, "CR-CT-1"),)):
    """LR-MDB-1 (4 slots): `found` in their own slots and scanned, `missing` slotted and
    not scanned (Done parks them), and Extras from elsewhere."""
    for sid in list(found) + list(missing):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(sid))
    for sid, at in extras:
        add_spool(env, sid, at)
    start(env, "LR-MDB-1")
    for sid in list(found) + [sid for sid, _at in extras]:
        scan(env, f"ID:{sid}")


@pytest.mark.parametrize("found, missing, extras, note", [
    # 1 stays, 3 come in: 4 in 4 slots.
    ((1,), (), ((20, "CR-CT-1"), (21, "SHELF-1"), (22, "")), MORE_SLOTS),
    # 3 stay, #4 is parked, 3 come in: 6 in a box of 4, one slot free (the dev run's).
    ((1, 2, 3), (4,), ((20, "CR-CT-1"), (21, "SHELF-1"), (22, "")),
     "LR-MDB-1 has 4 slots, and filing these makes 6 spools there, so only 1 of them can have a slot. "
     "They go in with no slot: scan one, then a free slot's label, to set it."),
    # Full, and one comes in.
    ((1, 2, 3, 4), (), ((20, "CR-CT-1"),),
     "LR-MDB-1 has 4 slots, and filing it makes 5 spools there: it goes in with no slot, and no slot is free."),
    ((1, 2, 3, 4), (), ((20, "CR-CT-1"), (21, "SHELF-1")),
     "LR-MDB-1 has 4 slots, and filing these makes 6 spools there: they go in with no slot, and no slot is "
     "free."),
])
def test_the_note_counts_the_free_slots_after_the_park(env, found, missing, extras, note):
    """Review of 7e3720f, R-3: Done filled a 4-slot box to 6 with no word, and the note
    promised each Extra a slot. It counts the slots left free once the park is done."""
    _box_of_four(env, found, missing, extras)
    asked = question(env)
    assert [r["id"] for r in asked["park"]] == list(missing)
    assert [r["id"] for r in asked["file"]] == [sid for sid, _at in extras]
    assert asked["file_note"] == note


@pytest.mark.parametrize("held, note", [
    # #5 has no slot, as C's own filing leaves a spool (a second audit of the box meets
    # one), so slot 4 is free for one of the two.
    ({1: "1", 2: "2", 3: "3", 5: ""},
     "LR-MDB-1 has 4 slots, and filing these makes 6 spools there, so only 1 of them can have a slot. "
     "They go in with no slot: scan one, then a free slot's label, to set it."),
    # #1 and #2 both claim slot 1, so slots 2 and 4 are free: one for each.
    ({1: "1", 2: "1", 3: "3"}, MORE_SLOTS),
])
def test_the_note_counts_the_slots_the_spools_there_claim(env, held, note):
    """The re-check of 492f466 (R-3's fix): the note took the box's slots less the spools
    left after the park, so a spool with no slot read as a slot taken ("...: they go in
    with no slot, and no slot is free." while slot 4 was), and so did a doubled slot
    ("only 1 of them can have a slot" while slots 2 and 4 were). It counts the slots those
    spools claim, by the one slot rule (box_slot_claims). RED on 5afeb8b."""
    for sid, slot in held.items():
        add_spool(env, sid, "LR-MDB-1", container_slot=slot)
    add_spool(env, 20, "CR-CT-1")
    add_spool(env, 21, "SHELF-1")
    start(env, "LR-MDB-1")
    for sid in [*held, 20, 21]:
        scan(env, f"ID:{sid}")
    asked = question(env)
    assert asked["park"] == [] and [r["id"] for r in asked["file"]] == [20, 21]
    assert asked["file_note"] == note


def test_a_spool_loaded_from_the_box_still_holds_its_slot_in_the_note(env):
    """Pins what was already right: a spool on a head from slot 4 still sits in it,
    feeding the head, so slot 4 isn't free (box_slot_claims counts the slot a deployed
    spool came from), and it counts among the spools there."""
    for sid in (1, 2, 3):
        add_spool(env, sid, "LR-MDB-1", container_slot=str(sid))
    add_spool(env, 6, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    add_spool(env, 20, "CR-CT-1")
    start(env, "LR-MDB-1")
    for sid in (1, 2, 3, 20):
        scan(env, f"ID:{sid}")
    assert question(env)["file_note"] == ("LR-MDB-1 has 4 slots, and filing it makes 5 spools there: it goes in "
                                          "with no slot, and no slot is free.")


def test_done_still_files_every_extra_into_a_full_box(env):
    """Pins what was already right: the note says the box goes over its slots, and Done
    files them all the same (Derek, 2026-11-03, R-3's answer (a): it files them all and
    says so in the question)."""
    _box_of_four(env, (1, 2, 3), (4,), ((20, "CR-CT-1"), (21, "SHELF-1"), (22, "")))
    assert yes(env)["filed"] == [20, 21, 22]
    assert sorted(s["id"] for s in spools(env).values() if s["location"] == "LR-MDB-1") == [1, 2, 3, 20, 21, 22]


def test_the_gesture_the_note_names_sets_the_filed_spools_slot(env):
    """S-7: "scan it, then its slot's label" is the gesture: a spool's scan puts it at the
    front of the scan buffer (the page's), and a slot label sets the buffer's first spool.
    Pins that the gesture works on the real route, with another spool buffered behind."""
    add_spool(env, 30, "SHELF-1")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    assert yes(env)["filed"] == [20] and extra_of(env, 20)["container_slot"] == ""
    state.GLOBAL_BUFFER = [{"id": 20}, {"id": 30}]     # #20 scanned: the front of the buffer
    res = app_module.app.test_client().post("/api/identify_scan", json={
        "text": "LOC:LR-MDB-1:SLOT:4", "source": "barcode", "confirmed_fed_heads": [], "confirmed_toolheads": []})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert spools(env)[20]["location"] == "LR-MDB-1" and extra_of(env, 20)["container_slot"] == "4"
    assert spools(env)[30]["location"] == "SHELF-1"


def test_one_deleted_since_stays(env):
    _extra_here(env)
    del spools(env)[20]
    got = plan()
    assert got["file"] == [] and got["stays"] == [_stay(20, logic.AUDIT_GONE_WHY, "")]


def test_one_archived_since_stays(env):
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    spools(env)[20]["archived"] = True
    assert plan()["stays"] == [_stay(20, "archived", "LR-MDB-2 slot 3")]


def test_one_filed_here_since_is_left_out(env):
    _extra_here(env)
    spools(env)[20]["location"] = "LR-MDB-1"
    got = plan()
    assert got["file"] == [] and got["stays"] == [] and got["park"] == []


@pytest.mark.parametrize("at, why", [("XL-1", HEAD_WHY),
                                     ("CORE1", "loaded on CORE1: an audit never takes a spool off a printer")])
def test_one_on_a_head_stays(env, at, why):
    _extra_here(env, at=at, physical_source="CR-CT-1")
    assert plan()["stays"] == [_stay(20, why, at)]


def test_one_in_the_scan_buffer_stays(env):
    _extra_here(env, at="CR-CT-1")
    state.GLOBAL_BUFFER = [{"id": 20}]
    assert plan()["stays"] == [_stay(20, "in the scan buffer", "CR-CT-1")]


def test_one_buffered_on_a_head_says_the_head(env):
    _extra_here(env, at="XL-1", physical_source="CR-CT-1")
    state.GLOBAL_BUFFER = [{"id": 20}]
    assert plan()["stays"] == [_stay(20, HEAD_WHY, "XL-1")]


def test_a_room_audit_never_pulls_a_spool_out_of_a_box_inside_it(env):
    """An audit of a room must not pull a spool out of its box."""
    add_spool(env, 1, "LR")
    add_spool(env, 20, "LR-MDB-1", container_slot="2")
    add_spool(env, 21, "CR-CT-1")
    start(env, "LR")
    for sid in (1, 20, 21):
        scan(env, f"ID:{sid}")
    got = plan()
    assert got["stays"] == [_stay(20, "FCC has it in LR-MDB-1 slot 2, inside LR", "LR-MDB-1 slot 2")]
    assert [r["id"] for r in got["file"]] == [21]


@pytest.mark.parametrize("place", ["XL-1", "XL", "CORE1"])
def test_every_extra_stays_when_the_place_is_a_head_or_a_printer(env, place):
    add_spool(env, 1, place)
    add_spool(env, 20, "CR-CT-1")
    start(env, place)
    scan(env, "ID:1")
    scan(env, "ID:20")
    got = plan()
    assert got["file"] == [] and got["stays"] == [_stay(20, PRINTER_WHY, "CR-CT-1")]


@pytest.mark.parametrize("place", ["PM-DB-1", "PM-DB-0", "SPOT-1"])
def test_a_one_spool_place_takes_an_extra_the_park_makes_room_for(places, place):
    env = places
    add_spool(env, 10, place, container_slot="1" if place.startswith("PM") else "")
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, place)
    scan(env, "ID:20")
    got = plan()
    assert [r["id"] for r in got["park"]] == [10] and got["stays"] == []
    assert [r["id"] for r in got["file"]] == [20] and got["file_note"] == ""


@pytest.mark.parametrize("place", ["PM-DB-1", "SPOT-1"])
def test_an_empty_one_spool_place_takes_one_extra(places, place):
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, place)
    scan(env, "ID:20")
    assert [r["id"] for r in plan()["file"]] == [20]


@pytest.mark.parametrize("place", ["PM-DB-1", "SPOT-1"])
def test_a_one_spool_place_whose_spool_was_found_keeps_the_extra_out(places, place):
    env = places
    add_spool(env, 10, place)
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, place)
    scan(env, "ID:10")
    scan(env, "ID:20")
    got = plan()
    assert got["file"] == []
    assert got["stays"] == [_stay(20, f"{place} holds one spool, and #10 is there", "LR-MDB-2 slot 3")]


def test_a_one_spool_place_whose_spool_is_loaded_from_it_keeps_the_extra_out(places):
    """A box's spool on its head physically sits in the box, feeding the head."""
    env = places
    add_spool(env, 11, "XL-2", physical_source="PM-DB-1", physical_source_slot="1")
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    assert plan()["stays"] == [_stay(20, "PM-DB-1 holds one spool, and #11 is there", "LR-MDB-2 slot 3")]


def test_a_one_spool_place_with_two_extras_files_neither(places):
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    add_spool(env, 21, "CR-CT-1")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    scan(env, "ID:21")
    got = plan()
    why = "PM-DB-1 holds one spool, and 2 were found here"
    assert got["file"] == [] and got["stays"] == [_stay(20, why, "LR-MDB-2 slot 3"), _stay(21, why, "CR-CT-1")]


def test_only_the_extras_that_qualify_count_toward_one(places):
    """An Extra that stays for its own reason doesn't crowd out the one that can go in."""
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    add_spool(env, 21, "XL-1", physical_source="CR-CT-1")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    scan(env, "ID:21")
    got = plan()
    assert [r["id"] for r in got["file"]] == [20] and got["stays"] == [_stay(21, HEAD_WHY, "XL-1")]


def test_nothing_missing_and_no_extra_still_reads_nothing(env):
    """Pins what was already right: Done with nothing to plan reads no Spoolman."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    env["fake"].gets.clear()
    assert scan(env, "CMD:DONE")["audit_ended"]["why"] == "done"
    assert env["fake"].gets == []


def test_an_extra_taken_back_isnt_filed(env):
    """A3 and C together: a spool taken back off the Extras is no longer Done's."""
    _extra_here(env)
    res = app_module.app.test_client().post("/api/audit/found", json={
        "audit_id": session()["audit_id"], "id": 20, "found": False}).get_json()
    assert res["success"] is True
    assert plan()["file"] == []


# ---------------------------------------------------------------------------
# C3: Done asks when there is anything to park or to file
# ---------------------------------------------------------------------------

def test_done_asks_with_only_extras_and_writes_nothing(env):
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    audit_id = session()["audit_id"]
    asked = scan(env, "CMD:DONE")
    assert asked == {"type": "audit_done_question", "audit_id": audit_id, "location": "LR-MDB-1",
                     "found": 1, "expected": 1, "park": [], "stays": [],
                     "file": [{"id": 20, "display": f"#20 {RED}", "where": "LR-MDB-2 slot 3"}],
                     "file_note": ONE_SLOT}
    assert patched(env) == [] and session()["active"] is True and state.UNDO_STACK == []


def test_done_asks_once_for_both(env):
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="CR-CT-1")
    asked = question(env)
    assert [r["id"] for r in asked["park"]] == [2] and [r["id"] for r in asked["file"]] == [20]


def test_extras_that_all_stay_end_the_audit_with_no_question(env):
    _extra_here(env, at="XL-1", physical_source="CR-CT-1")
    audit_id = session()["audit_id"]
    env["logs"].clear()
    assert scan(env, "CMD:DONE") == {**AUDIT_SCAN, "audit_ended": {"id": audit_id, "why": "done"}}
    assert f"#20 {RED} → {HEAD_WHY}" in report(env)
    assert patched(env) == []


def test_a_page_from_before_the_question_is_told_to_reload(env):
    _extra_here(env)
    ans = scan(env, "CMD:DONE", ask=False)
    assert ans["type"] == "error" and ans["stale_page"] is True
    assert session()["active"] is True and patched(env) == []


# ---------------------------------------------------------------------------
# C2: the write, and C4: the answer and the report
# ---------------------------------------------------------------------------

def test_the_yes_files_it_here_with_no_slot_and_clears_its_trail_and_notes(env):
    _extra_here(env, at="LR-MDB-2", container_slot="3", physical_source="CR-CT-1", physical_source_slot="4",
                fcc_pre_box_location="CR-CT-1-R1", fcc_pre_archive_location="SHELF-1", needs_label_print=True)
    audit_id = session()["audit_id"]
    result = yes(env)
    assert result == {"success": True, "parked": [], "filed": [20], "stayed": [], "failed": [],
                      "msg": "Filed #20 here. Undo Last Move puts it back.",
                      "audit_ended": {"id": audit_id, "why": "done"}}
    assert spools(env)[20]["location"] == "LR-MDB-1"
    got = extra_of(env, 20)
    for key in ("container_slot", "physical_source", "physical_source_slot", "fcc_pre_box_location",
                "fcc_pre_audit_location"):
        assert got[key] == "", key           # "": a popped key is kept by the merge
    assert got["fcc_pre_archive_location"] == "SHELF-1" and got["needs_label_print"] is True
    assert session()["active"] is False


def test_a_lost_spool_found_here_loses_its_note(env):
    _extra_here(env, at="UNKNOWN", fcc_pre_audit_location="CR-CT-1:2@2026-11-01")
    assert yes(env)["filed"] == [20]
    assert spools(env)[20]["location"] == "LR-MDB-1" and extra_of(env, 20)["fcc_pre_audit_location"] == ""


@pytest.mark.parametrize("place", ["PM-DB-1", "PM-DB-0"])
def test_a_spool_filed_in_a_single_slot_box_takes_its_one_slot(places, place):
    """Review of 7e3720f, S-9: a single-slot dryer box's spool is in slot "1", as the
    engine writes it (Group 42.2). Written blank, a second spool put in later went in
    unslotted, and then neither read as slot 1 (the 42.2 symptom: Quick-Swap reads the
    box as empty)."""
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, place)
    scan(env, "ID:20")
    assert yes(env)["filed"] == [20]
    assert spools(env)[20]["location"] == place and extra_of(env, 20)["container_slot"] == "1"
    add_spool(env, 40, "SHELF-1")
    assert logic.perform_smart_move(place, [40], origin="test")["status"] == "success"
    assert [str(s) for s in logic.spools_in_slot(place, "1")] == ["20"]


def test_a_spool_filed_on_a_one_spool_holder_has_no_slot(places):
    """Pins what was already right: a Max Spools 1 row that isn't a dryer box has no
    slots, so nothing is written there."""
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "SPOT-1")
    scan(env, "ID:20")
    assert yes(env)["filed"] == [20]
    assert spools(env)[20]["location"] == "SPOT-1" and extra_of(env, 20)["container_slot"] == ""


def test_the_parks_come_first_and_one_toast_says_both(places):
    env = places
    add_spool(env, 10, "PM-DB-1", container_slot="1")
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    result = yes(env)
    assert result["parked"] == [10] and result["filed"] == [20] and result["success"] is True
    assert result["msg"] == "Parked 1 spool at Unknown. Filed #20 here. Undo Last Move puts them back."
    assert patched(env) == [10, 20]
    assert spools(env)[10]["location"] == "UNKNOWN" and spools(env)[20]["location"] == "PM-DB-1"


def test_a_park_that_failed_keeps_the_one_spool_place_full(places, monkeypatch):
    """The write reads the place first: the parked spool is still there, so the
    Extra stays, and with nothing landed the audit runs on."""
    env = places
    add_spool(env, 10, "PM-DB-1", container_slot="1")
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    _refuse(env, monkeypatch, 10)
    result = yes(env)
    assert result["success"] is False and result["parked"] == [] and result["filed"] == []
    assert [f["id"] for f in result["failed"]] == [10] and "audit_ended" not in result
    assert result["stayed"] == [_stay(20, "PM-DB-1 holds one spool, and #10 is there", "LR-MDB-2 slot 3")]
    assert spools(env)[20]["location"] == "LR-MDB-2" and session()["active"] is True
    assert "The audit is still open" in result["msg"]


def test_a_spool_put_in_the_one_spool_place_meanwhile_keeps_the_extra_out(places, monkeypatch):
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "SPOT-1")
    scan(env, "ID:20")
    asked = question(env)
    _changes_at_last_look(monkeypatch, 20, lambda: add_spool(env, 30, "SPOT-1"))
    result = yes(env, asked)
    assert result["filed"] == [] and result["stayed"] == [
        _stay(20, "SPOT-1 holds one spool, and #30 is there", "LR-MDB-2 slot 3")]
    assert spools(env)[20]["location"] == "LR-MDB-2"


def test_a_one_spool_place_it_cant_read_before_the_write_is_a_failure(places, monkeypatch):
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    asked = question(env)
    _changes_at_last_look(monkeypatch, 20, lambda: setattr(env["fake"], "list_reads_fail", True))
    result = yes(env, asked)
    assert result["filed"] == [] and [f["id"] for f in result["failed"]] == [20]
    assert "couldn't read PM-DB-1 from Spoolman" in result["failed"][0]["why"]
    assert spools(env)[20]["location"] == "LR-MDB-2" and session()["active"] is True


@pytest.mark.parametrize("change, why", [
    (lambda env: spools(env)[20].update(location="CR-CT-1"), "moved to CR-CT-1 slot 3"),   # its slot is kept
    (lambda env: spools(env)[20].update(archived=True), "archived"),
    (lambda env: spools(env)[20].update(location="XL-1"), HEAD_WHY),
    (lambda env: setattr(state, "GLOBAL_BUFFER", [{"id": 20}]), "in the scan buffer"),
    (lambda env: spools(env).pop(20), logic.AUDIT_GONE_WHY),
    (lambda env: spools(env)[20].update(location="LR-MDB-1"), "FCC has it here already"),
])
def test_a_change_at_the_last_look_is_a_stay_never_a_write(env, monkeypatch, change, why):
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    asked = question(env)
    _changes_at_last_look(monkeypatch, 20, lambda: change(env))
    result = yes(env, asked)
    assert result["parked"] == [2] and result["filed"] == []
    assert [(s["id"], s["why"]) for s in result["stayed"]] == [(20, why)]
    assert 20 not in patched(env)


def _move(env, sid, location, slot=""):
    """Someone files the spool elsewhere while Done's question is open: Spoolman's own
    page, or the wizard, Quick-Swap or Force Location in another tab, none of which
    asks the audit."""
    rec = spools(env)[sid]
    rec["location"] = location
    rec["extra"]["container_slot"] = json.dumps(slot)


@pytest.mark.parametrize("to, slot, why", [
    ("CR-CT-1", "", "moved to CR-CT-1"),
    ("PM-DB-2", "", "moved to PM-DB-2"),             # into a PolyDryer
    ("LR-MDB-2", "4", "moved to LR-MDB-2 slot 4"),   # another slot of the same box
])
def test_an_extra_moved_while_the_question_was_open_stays_where_it_went(places, to, slot, why):
    """Review of 7e3720f, R-1 (and S-1): the last look compared the record with the Yes's
    own plan, which already saw the move, so the Extra was pulled out of its new place.
    It is checked against where the question showed it (`file_where`)."""
    env = places
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    asked = question(env)
    assert asked["file"][0]["where"] == "LR-MDB-2 slot 3"
    _move(env, 20, to, slot)
    env["logs"].clear()
    result = yes(env, asked)
    assert result["parked"] == [2] and result["filed"] == []
    assert [(s["id"], s["why"]) for s in result["stayed"]] == [(20, why)]
    assert 20 not in patched(env)
    assert spools(env)[20]["location"] == to and extra_of(env, 20)["container_slot"] == slot
    (record,) = state.UNDO_STACK
    assert "filed" not in record and record["moves"] == {2: "LR-MDB-1"}
    assert f"#20 {RED} → {why}" in report(env) and "Filed here" not in report(env)


@pytest.mark.parametrize("file_where", [None, {}, {"21": "LR-MDB-2 slot 3"}, "LR-MDB-2 slot 3"])
def test_a_yes_naming_an_extra_without_where_it_was_shown_files_nothing(env, file_where):
    """R-1: an Extra the Yes names with no `file_where` entry (none sent, another
    spool's, or not a dict at all) can't be checked against its question, so it stays."""
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    asked = question(env)
    result = yes(env, asked, file_where=file_where)
    assert result["filed"] == []
    assert result["stayed"] == [_stay(20, "wasn't in the question you answered", "LR-MDB-2 slot 3")]
    assert patched(env) == [] and spools(env)[20]["location"] == "LR-MDB-2"


def test_the_yes_still_files_an_extra_that_is_where_its_question_showed_it(env):
    """Pins what was already right, with `file_where` now sent: an Extra that didn't move
    is filed, and the report and the log say where the question showed it."""
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    env["logs"].clear()
    assert yes(env)["filed"] == [20]
    assert spools(env)[20]["location"] == "LR-MDB-1"
    assert "(FCC had it at LR-MDB-2 slot 3)" in report(env)
    assert any("filed Spool #20" in m and "(FCC had it at LR-MDB-2 slot 3)" in m for m, _c, _ in env["logs"])


def test_one_it_cant_read_at_the_last_look_isnt_written_and_counts_as_failed(env, monkeypatch):
    _extra_here(env)
    asked = question(env)
    real = spoolman_api.get_spool_answer
    monkeypatch.setattr(spoolman_api, "get_spool_answer", lambda sid: (None, False) if sid == 20 else real(sid))
    result = yes(env, asked)
    assert result["filed"] == [] and result["failed"] == [{"id": 20, "display": f"#20 {RED}",
                                                           "why": logic.AUDIT_WHERE_UNREAD}]
    assert patched(env) == [] and session()["active"] is True


def test_a_rejected_write_is_an_error_line_with_spoolmans_words(env, monkeypatch):
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env)
    _refuse(env, monkeypatch, 20)
    env["logs"].clear()
    result = yes(env)
    assert result["success"] is False and result["parked"] == [2] and result["filed"] == []
    (fail,) = result["failed"]
    assert fail["id"] == 20 and "nope (test)" in fail["why"]
    assert any(c == "ERROR" and "failed to file Spool #20" in m and "nope (test)" in m for m, c, _ in env["logs"])
    # One park landed, so the audit ends (Undo is refused while one runs).
    assert result["audit_ended"]["why"] == "done"
    assert result["msg"] == ("Parked 1 spool at Unknown. Couldn't file #20 here. "
                             "Undo Last Move puts it back.")


def test_a_yes_where_only_a_file_was_tried_and_it_failed_keeps_the_audit(env, monkeypatch):
    _extra_here(env)
    _refuse(env, monkeypatch, 20)
    result = yes(env)
    assert result["success"] is False and "audit_ended" not in result and session()["active"] is True
    assert result["msg"] == ("Nothing was moved. Couldn't file #20 here. "
                             "The audit is still open, so you can press Done again.")
    assert state.UNDO_STACK == []


def test_a_write_that_landed_but_timed_out_counts_as_filed(env, monkeypatch):
    _extra_here(env)
    _lands_but_times_out(env, monkeypatch, 20)
    result = yes(env)
    assert result["filed"] == [20] and result["success"] is True


def test_a_yes_from_a_page_before_c_files_nothing(env):
    """No `file_ids`: the Extra the question showed stays, and says why."""
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="CR-CT-1")
    result = yes(env, file_ids=None)
    assert result["parked"] == [2] and result["filed"] == []
    assert result["stayed"] == [_stay(20, "wasn't in the question you answered", "CR-CT-1")]
    assert spools(env)[20]["location"] == "CR-CT-1"


def test_a_yes_with_only_extras_names_them_in_file_ids(env):
    _extra_here(env)
    assert yes(env, ids=[])["filed"] == [20]


def test_a_yes_naming_nothing_is_refused(env):
    _extra_here(env)
    result = yes(env, ids=[], file_ids=[])
    assert result["success"] is False and "didn't say which spools" in result["msg"]
    assert session()["active"] is True and patched(env) == []


def test_a_yes_for_a_spool_the_plan_doesnt_file_files_nothing(env):
    _extra_here(env)
    result = yes(env, ids=[], file_ids=[20, 999])
    assert result["filed"] == [20] and patched(env) == [20]


def _taken_back(env, sid=20):
    res = app_module.app.test_client().post("/api/audit/found", json={
        "audit_id": session()["audit_id"], "id": sid, "found": False}).get_json()
    assert res["success"] is True, res


@pytest.mark.parametrize("change, why, where", [
    (lambda env: _move(env, 20, "LR-MDB-1"), "FCC has it here already", "LR-MDB-1"),
    (_taken_back, "isn't an Extra any more", "LR-MDB-2 slot 3"),
    (lambda env: _move(env, 20, "XL-1"), HEAD_WHY, "XL-1"),
])
def test_a_file_only_yes_that_files_nothing_says_nothing_was_moved_and_why(env, change, why, where):
    """Review of 7e3720f, S-5: the question asked only to file #20. Filed here by another
    tab, taken back, or put on a head before the Yes, it isn't filed, and the answer said
    "Nothing was parked.", naming no spool in the first two cases. It says nothing was
    moved, counts #20 as left where it is, and the report says why."""
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    asked = question(env)
    change(env)
    env["logs"].clear()
    result = yes(env, asked)
    assert result["filed"] == [] and result["parked"] == []
    assert result["msg"] == "Nothing was moved. 1 left where it is."
    assert result["stayed"] == [_stay(20, why, where)]
    assert f"#20 {RED} → {why}" in report(env)
    assert 20 not in patched(env) and result["audit_ended"]["why"] == "done"


def test_a_file_only_yes_whose_one_spool_place_filled_meanwhile_says_nothing_was_moved(places):
    """S-5 and R-2: a spool put in the one-spool place before the Yes keeps the Extra out,
    and the answer doesn't talk of a park nobody asked for."""
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    asked = question(env)
    assert asked["park"] == [] and [r["id"] for r in asked["file"]] == [20]
    add_spool(env, 21, "PM-DB-1")
    result = yes(env, asked)
    assert result["filed"] == [] and result["msg"] == "Nothing was moved. 1 left where it is."
    assert result["stayed"] == [_stay(20, "PM-DB-1 holds one spool, and #21 is there", "LR-MDB-2 slot 3")]


def test_a_yes_that_does_both_and_moves_nothing_says_nothing_was_moved(env):
    """S-5: a park and a filing that both stayed."""
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    asked = question(env)
    _move(env, 2, "SHELF-1")
    _move(env, 20, "LR-MDB-1")
    result = yes(env, asked)
    assert result["parked"] == [] and result["filed"] == []
    assert result["msg"] == "Nothing was moved. 2 left where they are."
    assert [(s["id"], s["why"]) for s in result["stayed"]] == [(2, "moved to SHELF-1"), (20, "FCC has it here already")]


def test_an_id_the_audit_never_had_adds_no_stay(env):
    """Pins what was already right: a Yes naming a spool this audit never saw says
    nothing of it."""
    _extra_here(env)
    result = yes(env, ids=[], file_ids=[20, 999])
    assert result["filed"] == [20] and result["stayed"] == []


def test_string_ids_count_as_the_same_spools(env):
    _extra_here(env)
    assert yes(env, ids=[], file_ids=["20"])["filed"] == [20]


def test_the_report_names_each_filed_spool_and_where_fcc_had_it(env):
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    env["logs"].clear()
    yes(env)
    line = report(env)
    assert f"📥 <b>Filed here:</b> #20 {RED} (FCC had it at LR-MDB-2 slot 3) (Undo Last Move puts it back)" in line
    assert any("filed Spool #20" in m and c == "INFO" for m, c, _ in env["logs"])


def test_the_report_of_a_place_with_nothing_filed_says_when_before_what_done_filed(env):
    """Review of 7e3720f, R-4's note: an audit of a place FCC had nothing filed at opened
    its report with "Nothing was filed here." above its own "Filed here" line."""
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "LR-MDB-1")
    scan(env, "ID:20")
    env["logs"].clear()
    assert yes(env)["filed"] == [20]
    line = report(env)
    assert "<br>Nothing was filed here when the audit began.<br>" in line
    assert "📥 <b>Filed here:</b>" in line


def test_the_report_of_a_place_with_nothing_filed_and_nothing_filed_by_done_is_as_it_was(env):
    """Pins what was already right: with nothing filed by Done, the line is the park's own."""
    add_spool(env, 20, "XL-1", physical_source="CR-CT-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:20")
    env["logs"].clear()
    assert scan(env, "CMD:DONE")["audit_ended"]["why"] == "done"      # the Extra stays: no question
    assert "<br>Nothing was filed here.<br>" in report(env)


def test_outside_text_in_the_filing_lines_is_escaped(env, monkeypatch):
    _extra_here(env, at="CR-CT-1")
    spools(env)[20]["filament"]["name"] = "<b>Bold</b>"
    _refuse(env, monkeypatch, 20, message="<script>x</script>")
    env["logs"].clear()
    yes(env)
    for msg, _cat, _color in env["logs"]:
        assert "<script>" not in msg and "<b>Bold</b>" not in msg, msg


def test_the_undo_record_carries_the_filed_group(places):
    env = places
    add_spool(env, 10, "PM-DB-1", container_slot="1")
    add_spool(env, 20, "LR-MDB-2", container_slot="3", physical_source="CR-CT-1", physical_source_slot="4")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    yes(env)
    (record,) = state.UNDO_STACK
    assert record["moves"] == {10: "PM-DB-1"} and record["only_if_at"] == "UNKNOWN"
    assert record["filed_at"] == "PM-DB-1"
    snap = record["filed"][20]
    assert snap["location"] == "LR-MDB-2" and snap["slot"] == "3" and snap["place_had_row"] is True
    assert set(snap["extras"]) == set(spoolman_api.SYSTEM_MANAGED_EXTRAS)
    assert snap["extras"]["physical_source"] == "CR-CT-1" and snap["extras"]["container_slot"] == "3"
    assert record["labels"][20] == f"#20 {RED}"


def test_a_park_with_nothing_filed_is_the_parks_own_record(env):
    """Pins the parked group's record, key for key, when nothing is filed: what was
    already right (red on 296e2a7 only because its question had no `file`)."""
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    start(env, "LR-MDB-1")
    yes(env)
    (record,) = state.UNDO_STACK
    assert "filed" not in record and "filed_at" not in record


# ---------------------------------------------------------------------------
# C5: one Undo, the filed group first
# ---------------------------------------------------------------------------

def _filed_and_parked(env):
    """PM-DB-1: #10 not scanned (parked), #20 found there from LR-MDB-2 slot 3 (filed)."""
    add_spool(env, 10, "PM-DB-1", container_slot="1")
    add_spool(env, 20, "LR-MDB-2", container_slot="3", physical_source="CR-CT-1", physical_source_slot="4")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    assert yes(env)["filed"] == [20]
    env["fake"].patches.clear()
    env["logs"].clear()


def test_one_undo_puts_both_back_the_filed_group_first(places):
    """#10 can go back into PM-DB-1 only once #20 has left it."""
    env = places
    _filed_and_parked(env)
    asked = ask_undo(env)
    assert asked["msg"] == ("Undo: put #10 back in PM-DB-1 (parked at Unknown by its audit) and #20 back in "
                            "LR-MDB-2 slot 3 (filed in PM-DB-1 by the same audit)?")
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [20, 10]
    assert patched(env) == [20, 10]
    assert spools(env)[20]["location"] == "LR-MDB-2" and spools(env)[10]["location"] == "PM-DB-1"
    got = extra_of(env, 20)
    assert (got["container_slot"], got["physical_source"], got["physical_source_slot"]) == ("3", "CR-CT-1", "4")
    assert extra_of(env, 10)["fcc_pre_audit_location"] == ""
    assert done["msg"].startswith(f"↩️ Undo: #20 {RED} is back in LR-MDB-2 slot 3 (filed in PM-DB-1 by its audit); "
                                  f"#10 {RED} is back in PM-DB-1 slot 1")
    assert state.UNDO_STACK == []


def test_the_undo_asks_about_no_head(places):
    env = places
    _filed_and_parked(env)
    (record,) = state.UNDO_STACK
    guard = logic._undo_guard(record)
    assert logic._undo_current_heads(record, {"XL-1": {}}, guard) == ([], [])
    assert ask_undo(env)["confirm_type"] == "undo"


def test_a_filed_only_record_comes_back_on_its_own(env):
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    yes(env)
    asked = ask_undo(env)
    assert asked["msg"] == "Undo: put #20 back in LR-MDB-2 slot 3 (filed in LR-MDB-1 by its audit)?"
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [20]
    assert done["msg"] == f"↩️ Undo: #20 {RED} is back in LR-MDB-2 slot 3 (filed in LR-MDB-1 by its audit)."
    assert spools(env)[20]["location"] == "LR-MDB-2" and extra_of(env, 20)["container_slot"] == "3"
    assert state.UNDO_STACK == []


@pytest.mark.parametrize("at, extra, back", [("", {}, "in Unassigned"),
                                             ("UNKNOWN", {"fcc_pre_audit_location": "CR-CT-1:2@2026-11-01"},
                                              "at Unknown")])
def test_a_filed_spool_goes_back_to_unassigned_or_unknown_with_its_note(env, at, extra, back):
    _extra_here(env, at=at, **extra)
    yes(env)
    asked = ask_undo(env)
    assert asked["msg"] == f"Undo: put #20 back {back} (filed in LR-MDB-1 by its audit)?"
    assert yes_undo(env, asked)["success"] is True
    assert spools(env)[20]["location"] == at
    assert extra_of(env, 20).get("fcc_pre_audit_location", "") == extra.get("fcc_pre_audit_location", "")


def test_a_slot_taken_since_is_final_and_the_parked_spool_is_held_back(places):
    """#20's old slot is taken, so #20 stays in PM-DB-1 for good, and #10 can't go back
    in beside it (_undo_hold_parked). Review of 7e3720f, S-6: renamed from
    ..._and_the_parked_group_still_goes_back, which said the opposite of what it checks,
    and its no-op `spools(env)[20]["location"] = "PM-DB-1"` is the precondition it is."""
    env = places
    _filed_and_parked(env)
    assert spools(env)[20]["location"] == "PM-DB-1"   # still filed here
    add_spool(env, 30, "LR-MDB-2", container_slot="3")
    done = yes_undo(env)
    assert done["success"] is False
    assert "#20 (LR-MDB-2 slot 3 holds #30)" in done["msg"]
    assert any(c == "ERROR" and "not putting Spool #20 back in LR-MDB-2 slot 3" in m for m, c, _ in env["logs"])
    assert spools(env)[20]["location"] == "PM-DB-1"
    # PM-DB-1 holds one spool and #20 stays in it, so #10 can't go back either.
    assert spools(env)[10]["location"] == "UNKNOWN"
    assert "#10 (PM-DB-1 holds one spool, and #20 is there)" in done["msg"]
    assert state.UNDO_STACK == []                     # final: no retry copy


def test_a_slot_taken_since_in_a_box_with_room_the_parked_group_still_goes_back(env):
    """A filed spool has no slot, so in a multi-slot box it claims none: #2 goes back while
    #20 stays. Review of 7e3720f, S-6: renamed from ..._leaves_the_parked_group_alone,
    which read as if #2 stayed."""
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    yes(env)
    add_spool(env, 30, "LR-MDB-2", container_slot="3")
    done = yes_undo(env)
    assert done["restored"] == [2] and "#20 (LR-MDB-2 slot 3 holds #30)" in done["msg"]
    assert spools(env)[2]["location"] == "LR-MDB-1"


@pytest.mark.parametrize("old, why", [("PM-DB-2", "PM-DB-2 slot 1 holds #31"),
                                      ("SPOT-2", "SPOT-2 holds one spool, and #31 is there")])
def test_its_old_one_spool_place_taken_since_is_final(places, old, why):
    env = places
    _extra_here(env, at=old)
    yes(env)
    add_spool(env, 31, old)
    done = yes_undo(env)
    assert done["success"] is False and f"#20 ({why})" in done["msg"]
    assert spools(env)[20]["location"] == "LR-MDB-1" and state.UNDO_STACK == []


def test_its_old_place_gone_keeps_it_here_and_says_so_once(env):
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="CR-CT-1-R2")
    yes(env)
    env["rows"][:] = [r for r in env["rows"] if r["LocationID"] != "CR-CT-1-R2"]
    asked = ask_undo(env)
    assert asked["msg"] == ("Undo: put #2 back in LR-MDB-1 (parked at Unknown by its audit)? "
                            "CR-CT-1-R2 is gone from Locations, so #20 stays in LR-MDB-1.")
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [2] and done["place_gone"] == [20]
    assert {"id": 20, "where": "LR-MDB-1"} in done["left_alone"]
    assert done["msg"].count("is gone from Locations") == 1
    assert spools(env)[20]["location"] == "LR-MDB-1"


def test_a_place_gone_in_a_one_spool_place_holds_the_parked_spool_back(places):
    """#20 stays in PM-DB-1 for good, so #10 can't go back in: the question offers it
    no more, and the Undo fails it for good."""
    env = places
    add_spool(env, 10, "PM-DB-1", container_slot="1")
    add_spool(env, 20, "CR-CT-1-R2")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    yes(env)
    env["rows"][:] = [r for r in env["rows"] if r["LocationID"] != "CR-CT-1-R2"]
    asked = ask_undo(env)
    assert asked["msg"] == ("Undo: nothing from this audit can go back. Clear it from Undo? "
                            "CR-CT-1-R2 is gone from Locations, so #20 stays in PM-DB-1. "
                            "PM-DB-1 holds one spool, and #20 is there, so #10 stays at Unknown.")
    done = yes_undo(env, asked)
    assert done["success"] is False and done["restored"] == []
    assert spools(env)[10]["location"] == "UNKNOWN" and spools(env)[20]["location"] == "PM-DB-1"
    assert state.UNDO_STACK == []


def _filed_for_good(env, place="PM-DB-1"):
    """`place` (one spool): #10 parked, #20 filed there from CR-CT-1-R2, whose row is
    then deleted, so #20 stays in `place` for good."""
    add_spool(env, 10, place, container_slot="1" if place.startswith("PM") else "")
    add_spool(env, 20, "CR-CT-1-R2")
    start(env, place)
    scan(env, "ID:20")
    assert yes(env)["filed"] == [20]
    env["rows"][:] = [r for r in env["rows"] if r["LocationID"] != "CR-CT-1-R2"]


def test_a_parked_spool_that_moved_on_is_left_alone_not_failed_while_the_filed_one_stays(places):
    """Review of 7e3720f, S-2: #10 was found since and filed on SHELF-1. The question says
    it is left where it is; the Undo called it a failure ("#10 (PM-DB-1 holds one spool,
    and #20 is there)"), with an ERROR line, against its own question."""
    env = places
    _filed_for_good(env)
    spools(env)[10]["location"] = "SHELF-1"
    asked = ask_undo(env)
    assert "Left where it is now: #10 at SHELF-1." in asked["msg"]
    env["logs"].clear()
    done = yes_undo(env, asked)
    assert done["success"] is True and "#10 (" not in done["msg"]
    assert {"id": 10, "where": "SHELF-1"} in done["left_alone"]
    assert not any(c == "ERROR" and "#10" in m for m, c, _ in env["logs"])
    assert spools(env)[10]["location"] == "SHELF-1" and state.UNDO_STACK == []


def test_a_parked_spool_deleted_since_is_dropped_not_failed_while_the_filed_one_stays(places):
    """S-2: deleted since, #10 is dropped, as for any guarded record."""
    env = places
    _filed_for_good(env)
    del spools(env)[10]
    done = yes_undo(env)
    assert done["success"] is True and done["dropped"] == [10] and "#10 (" not in done["msg"]
    assert "#10 is no longer in Spoolman." in done["msg"]


def test_a_parked_spool_that_moved_on_doesnt_wait_with_an_unreadable_filed_one(places, monkeypatch):
    """S-2, the waiting variant: #20 couldn't be read at the Undo, so it waits in the
    retry copy, and #10, filed on SHELF-1 since, is left alone instead of waiting
    with it for a reason that isn't its own."""
    env = places
    _filed_and_parked(env)
    spools(env)[10]["location"] = "SHELF-1"
    asked = ask_undo(env)
    real_undo = logic.perform_undo
    real_read = spoolman_api.get_spool_answer

    def blip_in_the_undo(expected_id=None):
        monkeypatch.setattr(spoolman_api, "get_spool_answer",
                            lambda sid: (None, False) if sid == 20 else real_read(sid))
        return real_undo(expected_id=expected_id)

    monkeypatch.setattr(logic, "perform_undo", blip_in_the_undo)
    done = yes_undo(env, asked)
    assert done["retry"] == [20] and {"id": 10, "where": "SHELF-1"} in done["left_alone"]
    assert "#10 (" not in done["msg"]
    (copy,) = state.UNDO_STACK
    assert set(copy["filed"]) == {20} and copy["moves"] == {}


@pytest.mark.parametrize("place", ["PM-DB-1", "SPOT-1"])
def test_a_parked_spool_unreadable_while_the_filed_one_stays_for_good_is_held_back(places, monkeypatch, place):
    """Pins what was already right, kept by S-2's fix: whatever #10 is now, Undo can never
    put it back in a place #20 stays in for good, so it isn't retried (the retry copy,
    which no longer carries #20, could put it in on top of #20: on SPOT-1, which has no
    slot to check, nothing else would stop it)."""
    env = places
    _filed_for_good(env, place)
    asked = ask_undo(env)
    real_undo = logic.perform_undo
    real_read = spoolman_api.get_spool_answer

    def blip_in_the_undo(expected_id=None):
        monkeypatch.setattr(spoolman_api, "get_spool_answer",
                            lambda sid: (None, False) if sid == 10 else real_read(sid))
        return real_undo(expected_id=expected_id)

    monkeypatch.setattr(logic, "perform_undo", blip_in_the_undo)
    done = yes_undo(env, asked)
    assert done["success"] is False and done["retry"] == []
    assert f"#10 ({place} holds one spool, and #20 is there)" in done["msg"]
    assert spools(env)[10]["location"] == "UNKNOWN" and state.UNDO_STACK == []


def test_an_unreadable_filed_spool_waits_in_the_retry_copy_and_so_does_the_parked(places, monkeypatch):
    """#20 couldn't be read, so it is still in PM-DB-1 and #10 can't go back yet:
    both wait, and the next Undo Last Move puts both back."""
    env = places
    _filed_and_parked(env)
    asked = ask_undo(env)
    real_undo = logic.perform_undo
    real_read = spoolman_api.get_spool_answer

    def blip_in_the_undo(expected_id=None):
        monkeypatch.setattr(spoolman_api, "get_spool_answer",
                            lambda sid: (None, False) if sid == 20 else real_read(sid))
        return real_undo(expected_id=expected_id)

    monkeypatch.setattr(logic, "perform_undo", blip_in_the_undo)
    done = yes_undo(env, asked)
    assert done["success"] is False and done["restored"] == [] and sorted(done["retry"]) == [10, 20]
    assert "Press Undo Last Move again" in done["msg"]
    assert patched(env) == []
    (copy,) = state.UNDO_STACK
    assert copy["id"] == asked["undo_id"] and set(copy["filed"]) == {20} and set(copy["moves"]) == {10}
    monkeypatch.setattr(spoolman_api, "get_spool_answer", real_read)
    monkeypatch.setattr(logic, "perform_undo", real_undo)
    again = yes_undo(env)
    assert again["success"] is True and again["restored"] == [20, 10]
    assert spools(env)[20]["location"] == "LR-MDB-2" and spools(env)[10]["location"] == "PM-DB-1"
    assert state.UNDO_STACK == []


def test_a_filed_write_that_failed_waits_in_the_retry_copy(env, monkeypatch):
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    yes(env)
    real = _refuse(env, monkeypatch, 20, message="busy (test)")
    done = yes_undo(env)
    assert done["success"] is False and done["restored"] == [2] and done["retry"] == [20]
    (copy,) = state.UNDO_STACK
    assert copy["moves"] == {} and set(copy["filed"]) == {20}
    assert ask_undo(env)["msg"] == "Undo: put #20 back in LR-MDB-2 slot 3 (filed in LR-MDB-1 by its audit)?"
    monkeypatch.setattr(spoolman_api.requests, "patch", real)
    assert yes_undo(env)["restored"] == [20] and state.UNDO_STACK == []


def test_a_filed_write_that_landed_but_timed_out_counts_as_restored(env, monkeypatch):
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    yes(env)
    _lands_but_times_out(env, monkeypatch, 20)
    done = yes_undo(env)
    assert done["success"] is True and done["restored"] == [20] and state.UNDO_STACK == []


def test_an_extra_that_moved_on_since_is_left_alone_and_named(env):
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    yes(env)
    spools(env)[20]["location"] = "CR-CT-1"
    asked = ask_undo(env)
    assert asked["msg"] == ("Undo: put #2 back in LR-MDB-1 (parked at Unknown by its audit)? "
                            "Left where it is now: #20 at CR-CT-1.")
    done = yes_undo(env, asked)
    assert done["success"] is True and done["restored"] == [2]
    assert done["left_alone"] == [{"id": 20, "where": "CR-CT-1"}]
    assert spools(env)[20]["location"] == "CR-CT-1"


def test_an_extra_archived_or_deleted_since_stays_out_of_the_undo(env):
    add_spool(env, 2, "LR-MDB-1", container_slot="2")
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    add_spool(env, 21, "CR-CT-1")
    scan(env, "ID:21")
    yes(env)
    spools(env)[20]["archived"] = True
    del spools(env)[21]
    done = yes_undo(env)
    assert done["success"] is True and done["restored"] == [2] and done["dropped"] == [21]
    assert done["left_alone"] == [{"id": 20, "where": "LR-MDB-1 (archived)"}]
    assert "#21 is no longer in Spoolman." in done["msg"]


def test_an_unreadable_filed_spool_keeps_the_question_from_being_asked(env, monkeypatch):
    """As for the parked group: where it is now decides, so nothing is asked."""
    _extra_here(env)
    yes(env)
    real = spoolman_api.get_spool_answer
    monkeypatch.setattr(spoolman_api, "get_spool_answer", lambda sid: (None, False) if sid == 20 else real(sid))
    asked = ask_undo(env)
    assert asked["success"] is False and "Couldn't read #20 from Spoolman" in asked["msg"]


def test_more_than_three_filed_spools_are_counted(env):
    add_spool(env, 1, "CR-CT-1")
    for sid in range(20, 24):
        add_spool(env, sid, "LR-MDB-2", container_slot=str(sid - 19))
    start(env, "CR-CT-1")
    scan(env, "ID:1")
    for sid in range(20, 24):
        scan(env, f"ID:{sid}")
    assert yes(env)["filed"] == [20, 21, 22, 23]
    asked = ask_undo(env)
    assert asked["msg"] == "Undo: put 4 spools back where they were (filed in CR-CT-1 by its audit)?"
    done = yes_undo(env, asked)
    assert done["msg"] == "↩️ Undo: 4 spools are back where they were (filed in CR-CT-1 by its audit)."


# ---------------------------------------------------------------------------
# C6: an Extra's row says what Done will do with it, from its scan's read
# ---------------------------------------------------------------------------

def _row(sid):
    body = app_module.app.test_client().get("/api/audit_session").get_json()
    return next(r for r in body["rogue"] if r["id"] == sid)


def test_an_extras_row_says_done_files_it_and_a_poll_reads_nothing(env):
    _extra_here(env, at="LR-MDB-2", container_slot="3")
    env["fake"].gets.clear()
    assert _row(20)["at_done"] == {"files": True}
    assert env["fake"].gets == []


@pytest.mark.parametrize("at, extra, why", [
    ("XL-1", {"physical_source": "CR-CT-1"}, HEAD_WHY),
])
def test_an_extras_row_says_why_it_stays(env, at, extra, why):
    _extra_here(env, at=at, **extra)
    assert _row(20)["at_done"] == {"files": False, "why": why}


def test_a_buffered_extras_row_says_so(env):
    add_spool(env, 20, "CR-CT-1")
    state.GLOBAL_BUFFER = [{"id": 20}]
    _extra_here(env, at="CR-CT-1", sid=21)
    scan(env, "ID:20")
    assert _row(20)["at_done"] == {"files": False, "why": "in the scan buffer"}


def test_an_extras_row_in_a_room_audit_says_its_box_is_inside(env):
    add_spool(env, 20, "LR-MDB-2", container_slot="1")
    start(env, "LR")
    scan(env, "ID:20")
    assert _row(20)["at_done"] == {"files": False, "why": "FCC has it in LR-MDB-2 slot 1, inside LR"}


def test_an_extras_row_at_a_printer_audit_says_it_stays(env):
    add_spool(env, 20, "CR-CT-1")
    start(env, "XL-1")
    scan(env, "ID:20")
    assert _row(20)["at_done"] == {"files": False, "why": PRINTER_WHY}


def test_an_extras_row_at_a_one_spool_place_leaves_it_to_done(places):
    env = places
    add_spool(env, 20, "LR-MDB-2", container_slot="3")
    start(env, "PM-DB-1")
    scan(env, "ID:20")
    assert _row(20)["at_done"] == {
        "files": None, "why": "PM-DB-1 holds one spool, so Done files it here only if nothing else is there"}


def test_an_extra_spoolman_didnt_answer_for_has_no_hint(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    monkeypatch.setattr(spoolman_api, "get_spool_answer", lambda sid: (None, False))
    scan(env, "ID:20")
    assert _row(20)["at_done"] is None


def test_an_extras_row_with_no_locations_file_has_no_hint_and_the_scan_still_counts(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 20, "CR-CT-1")
    start(env, "LR-MDB-1")
    import locations_db

    def unreadable():
        raise OSError("locations file locked (test)")

    monkeypatch.setattr(locations_db, "load_locations_list", unreadable)
    assert scan_answer("ID:20")["heard"] == "Extra: FCC has #20 at CR-CT-1"
    assert session()["rogue_items"] == [20] and _row(20)["at_done"] is None
