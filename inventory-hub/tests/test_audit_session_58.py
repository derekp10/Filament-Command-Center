"""Group 58, build spec sections 1 to 4: what an audit expects, what each scan
does to it, how it ends, and what the page is told.

Everything here runs through the Flask test client and the real session, on the
real read and write functions over tests/spoolman_extra_fake.SpoolmanHTTPFake (a
mocked update_spool is how Done's behaviour stayed hidden for months), with
locations.json's rows in Derek's shape.

Derek's rule (2026-11-01): a spool has one location. An audit expects the spools
whose OWN location is exactly the place scanned. A spool loaded from the place,
or filed in a place inside it, isn't on the list.

Done's plan, its question, the park and its Undo are in
tests/test_audit_auto_park_unknown.py and tests/test_audit_undo_58.py.
"""
from __future__ import annotations

import copy
import html
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import config_loader  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from spoolman_extra_fake import SpoolmanHTTPFake, _Resp  # noqa: E402

AUDIT_SCAN = {"type": "command", "cmd": "audit_scan"}
SPOOL_LIST = "/api/v1/spool"

ROWS = [
    {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "parent_id": None},
    {"LocationID": "LR-MDB-1", "Name": "Box 1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR"},
    {"LocationID": "LR-MDB-2", "Name": "Box 2", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR"},
    {"LocationID": "CR", "Name": "Craft Room", "Type": "Room", "parent_id": None},
    {"LocationID": "CR-CT-1", "Name": "Cart", "Type": "Cart", "parent_id": "CR"},
    {"LocationID": "CR-CT-1-R1", "Name": "Row 1", "Type": "Cart", "parent_id": "CR-CT-1"},
    {"LocationID": "CR-CT-1-R2", "Name": "Row 2", "Type": "Cart", "parent_id": "CR-CT-1"},
    {"LocationID": "XL", "Name": "Big Printer", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1}]},
    {"LocationID": "XL-1", "Name": "Head 1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Name": "Head 2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    # A printer that is its own head.
    {"LocationID": "CORE1", "Name": "Small Printer", "Type": "Printer", "Max Spools": "1", "parent_id": "CR",
     "toolheads": [{"location_id": "CORE1", "position": 0}]},
    {"LocationID": "SHELF-1", "Name": "Empty Shelf", "Type": "Wall Shelf", "parent_id": None},
]

SPOOL_FIELDS = [{"key": key, "field_type": "text", "name": key} for key in (
    "container_slot", "physical_source", "physical_source_slot", "fcc_pre_archive_location",
    "fcc_pre_audit_location", "fcc_pre_box_location")]
SPOOL_FIELDS.append({"key": "needs_label_print", "field_type": "boolean", "name": "Needs Label Print"})


def _wire(extra):
    return {key: json.dumps(value) for key, value in (extra or {}).items()}


def add_spool(env, sid, location, name="Red", **extra):
    """A spool on the fake, in Spoolman's wire shape."""
    return env["fake"].add(
        "spool", sid, _wire(extra), location=location, remaining_weight=500.0, used_weight=100.0,
        initial_weight=1000.0, archived=False,
        filament={"id": sid + 1000, "name": name, "material": "PLA", "color_hex": "72071C",
                  "vendor": {"id": 1, "name": "Some Brand"}, "extra": {}})


@pytest.fixture
def env(monkeypatch):
    fake = SpoolmanHTTPFake(fields={"spool": copy.deepcopy(SPOOL_FIELDS)})
    monkeypatch.setattr(spoolman_api.requests, "get", fake.get)
    monkeypatch.setattr(spoolman_api.requests, "patch", fake.patch)
    monkeypatch.setattr(spoolman_api, "_RAW_EXTRAS_RETRY_DELAY_S", 0)
    monkeypatch.setattr(spoolman_api, "_FIELD_SCHEMA_CACHE", {})
    monkeypatch.setattr(spoolman_api, "_SPOOLMAN_VERSION_CACHE", {})
    monkeypatch.setattr(config_loader, "load_config",
                        lambda: {"server_ip": "spoolman.test", "spoolman_port": 7000})
    rows = copy.deepcopy(ROWS)
    monkeypatch.setattr(locations_db, "load_locations_list", lambda: copy.deepcopy(rows))
    # And the save (Group 45.9): a single-slot box attach or release would write
    # these rows over the run's locations.json. Loads keep answering `rows`, as
    # they did when a save went to disk.
    monkeypatch.setattr(locations_db, "save_locations_list", lambda *a, **k: True)
    logs = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, cat="INFO", color=None, meta=None:
                        logs.append((msg, cat, color)))
    monkeypatch.setattr(state, "AUDIT_LAST_END", None)
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [])
    state.reset_audit()
    app_module.app.config["TESTING"] = True
    yield {"fake": fake, "logs": logs, "client": app_module.app.test_client(), "rows": rows}
    if logic._AUDIT_END_LOCK.locked():
        logic._AUDIT_END_LOCK.release()
    state.reset_audit()


def scan_answer(text, source="keyboard", ask=True, **more):
    """The route's whole answer. `more`: other keys of the request (`audit_seen`)."""
    # A client of its own, so a scan can land in the middle of another's request.
    # `ask`: this page can show Done's question (`audit_ask`, on every scan).
    # `source`: keyboard reads no label, so these tests see the audit and nothing
    # else; a real label read is "barcode" (tests/test_audit_no_label_58.py).
    body = {"text": text, "source": source, "confirmed_fed_heads": [], **more}
    if ask:
        body["audit_ask"] = True
    res = app_module.app.test_client().post("/api/identify_scan", json=body)
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def scan(env, text, source="keyboard", ask=True, **more):
    """A scan, with `heard` taken out of an answer the audit took. PIN UPDATED
    DELIBERATELY (Group 58 review): `heard` is the sentence for a hidden panel,
    pinned on its own below through scan_answer, so the exact pins in these files
    stay exact on every other key. Any other answer keeps it: a refusal that grew
    one fails them. And again (Derek, 2026-11-03, H S3): `report`, the report as
    data a Done that ended the audit carries, is taken out the same way, and pinned
    on its own in tests/test_audit_tiles_and_report_58.py."""
    answer = scan_answer(text, source=source, ask=ask, **more)
    if answer.get("cmd") == "audit_scan":
        answer.pop("heard", None)
        answer.pop("report", None)
    return answer


def park(env, ids=None, audit_id=None, today=None):
    """The Yes to Done's question: asks, then says yes to every spool it named,
    or to `ids` for the audit `audit_id` when the test has its own answer."""
    if ids is None:
        question = scan(env, "CMD:DONE")
        assert question["type"] == "audit_done_question", question
        ids, audit_id = [row["id"] for row in question["park"]], question["audit_id"]
    res = app_module.app.test_client().post("/api/audit/park", json={"audit_id": audit_id, "ids": ids,
                                                                     "today": today})
    assert res.status_code == 200, res.get_data(as_text=True)
    return res.get_json()


def start(env, place):
    assert scan(env, "CMD:AUDIT") == AUDIT_SCAN
    assert scan(env, f"LOC:{place}") == AUDIT_SCAN
    env["logs"].clear()
    env["fake"].gets.clear()


def session():
    return state.AUDIT_SESSION


def log_text(env):
    return [msg for msg, _cat, _color in env["logs"]]


def report(env):
    lines = [msg for msg in log_text(env) if "Audit Report" in msg]
    assert len(lines) == 1, log_text(env)
    return lines[0]


# ---------------------------------------------------------------------------
# 1. The session
# ---------------------------------------------------------------------------

def test_reset_audit_clears_everything_the_session_gained():
    state.AUDIT_SESSION.update({
        "audit_id": "x-1", "trail_items": [1], "rows": {"1": {"id": 1}}, "start_note": "a note",
        "last_found": 1, "found_by": {"1": "label"}, "label_flagged": {"1": True}})
    state.reset_audit()
    got = state.AUDIT_SESSION
    assert (got["audit_id"], got["trail_items"], got["rows"], got["start_note"]) == (None, [], {}, "")
    assert (got["last_found"], got["found_by"], got["label_flagged"]) == (None, {}, {})


def test_each_audit_has_its_own_id_and_a_restart_cant_reuse_it(env):
    scan(env, "CMD:AUDIT")
    first = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    scan(env, "CMD:AUDIT")
    second = session()["audit_id"]
    assert first and second and first != second
    assert first.startswith(logic._UNDO_EPOCH + "-")      # as _push_undo: the process's own token


def test_a_session_of_only_some_keys_still_takes_scans():
    """Tests and old sessions build partial dicts: every key is read with .get."""
    state.AUDIT_SESSION.clear()
    state.AUDIT_SESSION.update({"active": True, "location_id": "LR-MDB-1", "expected_items": [5]})
    try:
        assert logic.process_audit_scan({"type": "spool", "id": 5}) == {"status": "success",
                                                                        "heard": "Found #5 (All found!)"}
        assert state.AUDIT_SESSION["scanned_items"] == [5]
    finally:
        state.AUDIT_SESSION.clear()
        state.reset_audit()


# ---------------------------------------------------------------------------
# 2. The location scan: the one rule
# ---------------------------------------------------------------------------

def test_a_room_expects_only_the_spools_filed_at_the_room_itself(env):
    """The old list also held every spool under the room's first segment and every
    trail naming it: on dev auditing CR listed 86, with 7 filed there, and Done
    parked the other 79."""
    add_spool(env, 1, "LR")
    add_spool(env, 2, "lr")                                  # the case doesn't matter
    add_spool(env, 3, "LR-MDB-1", container_slot="1")        # a place inside it
    add_spool(env, 4, "XL-1", physical_source="LR")          # only a trail here
    add_spool(env, 5, "XL-2", physical_source="LR-MDB-1")    # a prefix hit by its trail
    add_spool(env, 6, "CR")                                  # another room
    start(env, "LR")
    assert session()["expected_items"] == [1, 2]


def test_a_box_doesnt_expect_the_spool_loaded_from_it(env):
    """Derek's #242: on record in LR-MDB-2 slot 1, running on XL-4. The old list
    held it, so Done took it off the head."""
    add_spool(env, 1, "LR-MDB-2", container_slot="2")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    assert session()["expected_items"] == [1]


def test_a_forgotten_spool_stays_on_the_list(env):
    """His forgotten-spool case: filed here on record, and physically elsewhere.
    That is the audit's real job, so it stays expected, and missing."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1", physical_source="LR-MDB-1")
    start(env, "LR-MDB-1")
    assert session()["expected_items"] == [1]


def test_a_head_expects_the_spool_on_it(env):
    add_spool(env, 1, "XL-1", physical_source="LR-MDB-1")
    start(env, "XL-1")
    assert session()["expected_items"] == [1]


def test_a_second_location_scan_refuses_with_its_words(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    ans = scan(env, "LOC:LR-MDB-2")
    assert ans == {"type": "error", "msg": "Already auditing LR-MDB-1. Finish first!"}
    assert session()["location_id"] == "LR-MDB-1"
    assert any("Already auditing LR-MDB-1" in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]
    assert env["fake"].gets == []


@pytest.mark.parametrize("text, word", [("LOC:UNKNOWN", "Unknown"), ("LOC:UNASSIGNED", "Unassigned"),
                                        ("UNKNOWN", "Unknown"), ("unassigned", "Unassigned")])
def test_the_two_lists_refuse_with_no_read(env, text, word):
    """Done on either would overwrite the only record of where a lost spool was
    expected, or send every workbench spool to Unknown."""
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    ans = scan(env, text)
    assert ans == {"type": "error", "msg": f"{word} is a list, not a place you can audit."}
    assert session()["location_id"] is None
    assert env["fake"].gets == []
    assert [c for _m, c, _ in env["logs"]] == ["WARNING"], env["logs"]


@pytest.mark.parametrize("how", ["list_reads_fail", "down"])
def test_a_failed_read_stores_nothing_and_the_same_label_works_next(env, how):
    """Group 52's rule: it used to store the place, read 0 expected, refuse the
    rescan as "Already auditing", and end on a green Perfect Match."""
    add_spool(env, 1, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    setattr(env["fake"], how, True)
    ans = scan(env, "LOC:LR-MDB-1")
    assert ans == {"type": "error", "msg": "Couldn't read LR-MDB-1 from Spoolman, so the audit hasn't "
                                           "started. Scan it again in a moment."}
    assert session()["location_id"] is None and session()["expected_items"] == []
    assert any("Couldn't read LR-MDB-1" in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]

    setattr(env["fake"], how, False)
    assert scan(env, "LOC:LR-MDB-1") == AUDIT_SCAN
    assert session()["location_id"] == "LR-MDB-1" and session()["expected_items"] == [1]


def test_an_answer_that_isnt_a_list_is_a_failed_read(env, monkeypatch):
    scan(env, "CMD:AUDIT")
    monkeypatch.setattr(spoolman_api.requests, "get", lambda *a, **k: _Resp(200, {"oops": True}))
    ans = scan(env, "LOC:LR-MDB-1")
    assert ans["type"] == "error" and "Couldn't read LR-MDB-1" in ans["msg"], ans
    assert session()["location_id"] is None


def test_a_place_fcc_doesnt_know_is_refused_and_the_right_one_still_works(env):
    """A mistyped label used to lock the audit at 0 expected."""
    add_spool(env, 1, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    ans = scan(env, "LOC:LR-TYPO")
    assert ans == {"type": "error", "msg": "LR-TYPO isn't a place FCC knows."}
    assert session()["location_id"] is None and session()["rows"] == {}
    assert scan(env, "LOC:LR-MDB-1") == AUDIT_SCAN
    assert session()["expected_items"] == [1]


def test_a_real_place_with_nothing_filed_still_starts(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "SHELF-1")
    assert session()["location_id"] == "SHELF-1" and session()["expected_items"] == []
    assert session()["start_note"] == ""


def test_a_place_with_spools_but_no_row_still_audits(env):
    add_spool(env, 1, "GARAGE-BIN")
    start(env, "GARAGE-BIN")
    assert session()["expected_items"] == [1]


def test_a_virtual_room_with_spools_inside_it_is_a_place_fcc_knows(env):
    """A room /api/locations draws from its spools alone has no row, and may have
    nothing filed at it: it isn't a mistyped label. It starts, and says why the
    list is empty."""
    add_spool(env, 1, "GR-CT-1")
    add_spool(env, 2, "GR-CT-2")
    start(env, "GR")
    assert session()["expected_items"] == []
    assert session()["start_note"].startswith("Nothing is filed here itself. 2 more are in the places")


def test_a_pseudo_prefix_is_no_place_even_with_boxes_under_it(env):
    """PM is the first segment of the portable boxes' ids, never a room."""
    env["rows"].append({"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1"})
    add_spool(env, 1, "PM-DB-1")
    scan(env, "CMD:AUDIT")
    assert scan(env, "LOC:PM")["msg"] == "PM isn't a place FCC knows."


@pytest.mark.parametrize("place, spools, note", [
    ("CR", [("CR", ""), ("CR", ""), ("CR-CT-1", ""), ("CR-CT-1-R1", ""), ("CR-CT-1-R2", "")],
     "2 are filed here. 3 more are in the places inside it, and this audit doesn't check those: "
     "audit each of them."),
    ("CR", [("CR", ""), ("CR-CT-1-R1", "")],
     "1 is filed here. 1 more is in a place inside it, and this audit doesn't check it: audit that place too."),
    ("CR-CT-1", [("CR-CT-1-R1", ""), ("CR-CT-1-R2", "")],
     "Nothing is filed here itself. 2 more are in the places inside it, and this audit doesn't check "
     "those: audit each of them."),
    ("XL", [("XL-2", ""), ("XL-1", "")],
     "Nothing is filed here itself. 2 more are in the places inside it (XL-1, XL-2), and this audit "
     "doesn't check those: audit each of them."),
    ("LR-MDB-1", [("LR-MDB-1", "")], ""),
])
def test_the_start_note_says_what_this_audit_doesnt_check(env, place, spools, note):
    for sid, (loc, _unused) in enumerate(spools, 1):
        add_spool(env, sid, loc)
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    assert scan(env, f"LOC:{place}") == AUDIT_SCAN
    assert session()["start_note"] == note
    line = log_text(env)[-1]
    assert f"Auditing <b>{place}</b>" in line and (note in line), line


def test_a_nested_printers_heads_are_inside_its_room_but_not_on_its_list(env):
    add_spool(env, 1, "LR")
    add_spool(env, 2, "XL-1")
    start(env, "LR")
    assert session()["expected_items"] == [1]
    assert session()["start_note"].startswith("1 is filed here. 1 more is in a place inside it")


@pytest.mark.parametrize("head_row", [
    {"LocationID": "HEAD-A", "Name": "Head", "Type": "Tool Head", "Max Spools": "1", "parent_id": None},
    {"LocationID": "HEAD-A", "Name": "Head", "Type": "Tool Head", "Max Spools": "1"},
    None,                                            # no row of its own at all
])
def test_a_printers_head_is_inside_it_whatever_its_own_row_says(env, head_row):
    """The Printer row's toolheads[] says which heads it owns. XL-1 and XL-2 above
    have parent_id XL, so the tree answers for them and that list never decides:
    this head's id doesn't spell its printer, and nothing but the list names it."""
    env["rows"].append({"LocationID": "MK4", "Name": "Another Printer", "Type": "Printer", "Max Spools": "0",
                        "toolheads": [{"location_id": "HEAD-A", "position": 0}]})
    if head_row:
        env["rows"].append(head_row)
    add_spool(env, 1, "HEAD-A")
    scan(env, "CMD:AUDIT")
    assert scan(env, "LOC:MK4") == AUDIT_SCAN
    assert session()["start_note"] == ("Nothing is filed here itself. 1 more is in a place inside it (HEAD-A), "
                                       "and this audit doesn't check it: audit that place too.")


def test_a_trail_alone_is_not_a_place_inside(env):
    add_spool(env, 1, "SHELF-1", physical_source="LR-MDB-1")
    start(env, "LR")
    assert session()["expected_items"] == [] and session()["start_note"] == ""


def test_a_location_scan_is_one_read_of_the_list(env):
    add_spool(env, 1, "LR")
    add_spool(env, 2, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    env["fake"].gets.clear()
    scan(env, "LOC:LR")
    assert env["fake"].gets == [SPOOL_LIST]


def test_the_list_read_leaves_archived_spools_out(env):
    add_spool(env, 1, "LR")
    env["fake"].records["spool"][1]["archived"] = True
    start(env, "LR")
    assert session()["expected_items"] == []


def test_a_row_is_stored_from_the_match(env):
    add_spool(env, 1, "LR-MDB-1", name="Galaxy Black", container_slot="2")
    start(env, "LR-MDB-1")
    row = session()["rows"]["1"]
    assert row == {
        "id": 1, "display": "#1 Some Brand PLA (Galaxy Black)", "color": "72071C",
        "color_direction": "longitudinal", "remaining_weight": 500.0, "slot": "2",
        "location": "LR-MDB-1", "where": "LR-MDB-1 slot 2", "label_status": None,
    }


def test_a_read_that_loses_a_race_stores_nothing(env, monkeypatch):
    """Scans aren't serial: the audit can end while the list is being read, and
    a late location scan must not write into a session nobody owns."""
    add_spool(env, 1, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    real = spoolman_api.get_all_spools_strict

    def ended_meanwhile(*a, **k):
        spools = real(*a, **k)
        monkeypatch.setattr(spoolman_api, "get_all_spools_strict", real)
        assert scan(env, "CMD:CANCEL")["audit_ended"]["why"] == "cancel"
        return spools

    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", ended_meanwhile)
    assert scan(env, "LOC:LR-MDB-1") == {"type": "error", "msg": "That audit has ended."}
    assert session()["active"] is False
    assert session()["location_id"] is None and session()["expected_items"] == []


def test_a_read_that_loses_to_another_location_scan_says_so(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-2")
    scan(env, "CMD:AUDIT")
    real = spoolman_api.get_all_spools_strict

    def other_scan_won(*a, **k):
        spools = real(*a, **k)
        monkeypatch.setattr(spoolman_api, "get_all_spools_strict", real)
        assert scan(env, "LOC:LR-MDB-2") == AUDIT_SCAN
        return spools

    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", other_scan_won)
    ans = scan(env, "LOC:LR-MDB-1")
    assert ans == {"type": "error", "msg": "Already auditing LR-MDB-2. Finish first!"}
    assert session()["expected_items"] == [2]


# ---------------------------------------------------------------------------
# 3. A spool scan
# ---------------------------------------------------------------------------

def test_a_spool_before_a_place_is_refused_in_words(env):
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    ans = scan(env, "ID:1")
    assert ans == {"type": "error", "msg": "Scan a Location first!"}
    assert session()["scanned_items"] == []
    assert any("Scan a Location first!" in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]


def test_left_counts_the_list_and_never_subtracts_an_extra(env):
    """Expected 3, one Extra and two found used to log "All found!" with one
    spool still unscanned."""
    for sid in (1, 2, 3):
        add_spool(env, sid, "LR-MDB-1")
    add_spool(env, 9, "LR-MDB-2")
    start(env, "LR-MDB-1")
    scan(env, "ID:9")
    scan(env, "ID:1")
    scan(env, "ID:2")
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S2): these are typed ids, which
    # read no label, and the line says so.
    assert log_text(env)[-1] == "✅ Found #2, no label read (1 left)"
    scan(env, "ID:3")
    assert log_text(env)[-1] == "✅ Found #3, no label read (All found!)"


def test_a_spool_already_scanned_answers_quietly(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "LR-MDB-2")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    scan(env, "ID:9")
    env["logs"].clear()
    env["fake"].gets.clear()
    assert scan(env, "ID:1") == AUDIT_SCAN
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert env["logs"] == [] and env["fake"].gets == []
    assert session()["scanned_items"] == [1, 9] and session()["rogue_items"] == [9]


def test_a_spool_on_the_list_needs_no_read(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    assert env["fake"].gets == []


def test_an_extra_spoolman_wont_answer_for_is_recorded_and_never_a_500(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    env["fake"].down = True
    assert scan(env, "ID:999") == AUDIT_SCAN
    assert session()["rogue_items"] == [999] and session()["scanned_items"] == [999]
    assert session()["rows"]["999"]["where"] == "couldn't read where FCC has it"
    assert session()["rows"]["999"]["display"] == "#999"
    assert any("couldn't read where FCC has it" in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]


def test_a_5xx_with_a_json_body_is_an_extra_not_a_spool_that_doesnt_exist(env, monkeypatch):
    """Its error body read as a truthy dict with no id: "Spool #N not found", and a
    spool in the person's hand left no mark."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "SHELF-1")
    start(env, "LR-MDB-1")
    real_get = env["fake"].get

    def get(url, timeout=None, **kw):
        if url.rstrip("/").endswith("/spool/2"):
            return _Resp(500, {"message": "database is locked (test)"})
        return real_get(url, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "get", get)
    assert scan(env, "ID:2") == AUDIT_SCAN
    assert session()["rogue_items"] == [2]
    assert session()["rows"]["2"]["where"] == "couldn't read where FCC has it"


def test_a_body_that_isnt_json_is_an_extra_too(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")

    class _NotJson:
        status_code = 200
        ok = True

        def json(self):
            raise ValueError("not JSON")

    monkeypatch.setattr(spoolman_api.requests, "get", lambda *a, **k: _NotJson())
    assert scan(env, "ID:999") == AUDIT_SCAN
    assert session()["rogue_items"] == [999]


def test_a_spool_that_doesnt_exist_is_refused_and_recorded_nowhere(env):
    """Spoolman's 404 body is a truthy dict: it used to log "Found #999999! (DB says:
    Unknown)" and draw a tile reading "#? [No Filament Data]"."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    ans = scan(env, "ID:999999")
    assert ans == {"type": "error", "msg": "Spool #999999 not found"}
    assert session()["scanned_items"] == [] and session()["rogue_items"] == []
    assert "999999" not in session()["rows"]


def test_a_spool_loaded_from_here_is_a_quiet_find(env):
    """A spool loaded from a bound box physically sits in that box, feeding the
    head: found, and no Extra."""
    add_spool(env, 1, "LR-MDB-2", container_slot="2")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    assert scan(env, "ID:242") == AUDIT_SCAN
    assert session()["trail_items"] == [242] and session()["rogue_items"] == []
    assert session()["scanned_items"] == [242]
    assert session()["rows"]["242"]["where"] == "XL-1" and session()["rows"]["242"]["slot"] == "1"
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S2): a typed id reads no label,
    # and the line says so (a real label read keeps "Found #242: loaded on …").
    assert [(m, c) for m, c, _ in env["logs"]] == [("🔗 Found #242, no label read: loaded on XL-1 from here.",
                                                    "INFO")]


def test_a_printer_that_is_its_own_head_counts_as_a_head(env):
    add_spool(env, 1, "CORE1", physical_source="LR-MDB-2")
    add_spool(env, 2, "LR-MDB-2")
    start(env, "LR-MDB-2")
    assert scan(env, "ID:1") == AUDIT_SCAN
    assert session()["trail_items"] == [1] and session()["rogue_items"] == []


@pytest.mark.parametrize("location, source, where", [
    ("XL", "LR-MDB-2", "XL"),                 # a multi-head printer's row is no head
    ("CR-CT-1", "LR-MDB-2", "CR-CT-1"),       # a stale trail, on no head
    ("XL-1", "LR-MDB-1", "XL-1"),             # loaded from another box
])
def test_a_trail_only_counts_on_a_head_and_from_this_place(env, location, source, where):
    add_spool(env, 1, location, physical_source=source)
    add_spool(env, 2, "LR-MDB-2")
    start(env, "LR-MDB-2")
    assert scan(env, "ID:1") == AUDIT_SCAN
    assert session()["rogue_items"] == [1] and session()["trail_items"] == []
    assert session()["rows"]["1"]["where"] == where


def test_an_extra_says_where_fcc_has_it_and_the_word_is_extra(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR-CT-1-R2", name="Mystery", container_slot="3")
    start(env, "LR-MDB-1")
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert session()["rogue_items"] == [9]
    assert session()["rows"]["9"]["where"] == "CR-CT-1-R2 slot 3"
    (msg, cat, _color), = env["logs"]
    assert msg == "⚠️ Extra: #9 Some Brand PLA (Mystery): FCC has it at CR-CT-1-R2 slot 3."
    assert cat == "WARNING"
    assert "rogue" not in msg.lower()


@pytest.mark.parametrize("location, where", [("", "Unassigned"), (None, "Unassigned"), ("UNKNOWN", "Unknown")])
def test_a_blank_location_reads_unassigned(env, location, where):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, location)
    start(env, "LR-MDB-1")
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert session()["rows"]["9"]["where"] == where


def test_an_archived_extra_is_read_like_any_other(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    env["fake"].records["spool"][9]["archived"] = True
    start(env, "LR-MDB-1")
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert session()["rogue_items"] == [9] and session()["rows"]["9"]["where"] == "CR"


def test_a_scan_that_loses_a_race_with_the_end_records_nothing(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    real = spoolman_api.get_spool_answer

    def ended_meanwhile(sid):
        answer = real(sid)
        monkeypatch.setattr(spoolman_api, "get_spool_answer", real)
        scan(env, "CMD:CANCEL")
        return answer

    monkeypatch.setattr(spoolman_api, "get_spool_answer", ended_meanwhile)
    scan(env, "ID:9")
    assert session()["active"] is False
    assert session()["rogue_items"] == [] and session()["rows"] == {}


def test_a_double_read_of_an_extra_records_it_once(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    real = spoolman_api.get_spool_answer

    def read_twice(sid):
        answer = real(sid)
        monkeypatch.setattr(spoolman_api, "get_spool_answer", real)
        scan(env, "ID:9")           # the second read lands first
        return answer

    monkeypatch.setattr(spoolman_api, "get_spool_answer", read_twice)
    scan(env, "ID:9")
    assert session()["rogue_items"] == [9] and session()["scanned_items"] == [9]


# --- a row recorded while Spoolman wasn't answering ---------------------------

UNREAD = "couldn't read where FCC has it"


def scanned_in_a_blip(env, sid, source="keyboard"):
    env["fake"].down = True
    scan(env, f"ID:{sid}", source=source)
    env["fake"].down = False
    assert session()["rows"][str(sid)]["where"] == UNREAD
    env["logs"].clear()
    env["fake"].gets.clear()


def test_a_spool_scanned_in_a_blip_reads_as_loaded_from_here_when_scanned_again(env):
    """Derek's #242 again. It was an Extra for good: the re-scan answered "Already
    scanned" with no read, and the report lost its Perfect Match to a blip."""
    add_spool(env, 1, "LR-MDB-2", container_slot="2")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    scan(env, "ID:1")
    scanned_in_a_blip(env, 242)
    assert scan(env, "ID:242") == AUDIT_SCAN
    assert session()["rogue_items"] == [] and session()["trail_items"] == [242]
    assert session()["scanned_items"] == [1, 242]
    row = session()["rows"]["242"]
    assert (row["where"], row["slot"], row["display"]) == ("XL-1", "1", "#242 Some Brand PLA (Red)")
    assert [c for _m, c, _ in env["logs"]] == ["INFO"], env["logs"]
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    line = report(env)
    assert "Perfect Match" in line and "Loaded from here" in line and "Extra" not in line, line


def test_a_spool_scanned_in_a_blip_reads_as_an_extra_with_its_real_place(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR-CT-1-R2", name="Stray", container_slot="3")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9)
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert session()["rogue_items"] == [9] and session()["scanned_items"] == [9]
    assert session()["rows"]["9"]["where"] == "CR-CT-1-R2 slot 3"
    assert session()["rows"]["9"]["display"] == "#9 Some Brand PLA (Stray)"
    assert log_text(env) == ["⚠️ Extra: #9 Some Brand PLA (Stray): FCC has it at CR-CT-1-R2 slot 3."]


@pytest.mark.parametrize("how", ["down", "5xx"])
def test_a_spool_scanned_in_a_blip_stays_as_it_is_while_spoolman_wont_answer(env, monkeypatch, how):
    """Quiet: nothing changed, so nothing more is logged, and the scan still selects
    it. And it can be read again after that."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9)
    scan(env, "ID:1")
    env["logs"].clear()
    real_get = env["fake"].get
    if how == "down":
        env["fake"].down = True
    else:
        monkeypatch.setattr(spoolman_api.requests, "get", lambda url, timeout=None, **kw:
                            _Resp(500, {"message": "database is locked (test)"}))
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert session()["rogue_items"] == [9] and session()["scanned_items"] == [9, 1]
    assert session()["rows"]["9"]["where"] == UNREAD
    assert session()["last_found"] == 9
    assert env["logs"] == []

    env["fake"].down = False
    monkeypatch.setattr(spoolman_api.requests, "get", real_get)
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert session()["rows"]["9"]["where"] == "CR"


def test_a_mistyped_id_scanned_in_a_blip_leaves_no_mark_once_spoolman_answers(env):
    """It stayed on the report as an Extra, and only Cancel or Done cleared it."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    scanned_in_a_blip(env, 9999)
    assert session()["last_found"] == 9999 and "9999" in session()["found_by"]
    assert scan(env, "ID:9999") == {"type": "error", "msg": "Spool #9999 not found"}
    assert session()["rogue_items"] == [] and session()["scanned_items"] == [1]
    assert "9999" not in session()["rows"] and "9999" not in session()["found_by"]
    assert session()["last_found"] is None
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    assert "Perfect Match" in report(env)


def test_a_mistyped_id_gone_leaves_the_last_spool_found_alone(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9999)
    scan(env, "ID:1")
    scan(env, "ID:9999")
    assert session()["last_found"] == 1


def test_a_spool_deleted_after_it_was_marked_leaves_no_mark_either(env):
    """Marked once Spoolman answered, then gone: the report mustn't name it."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9)
    assert scan(env, "CMD:NEEDLABEL")["said"] == "#9 is marked: it needs a label."
    assert session()["label_flagged"] == {"9": None}
    del env["fake"].records["spool"][9]
    scan(env, "ID:9")
    assert session()["label_flagged"] == {}


def test_a_read_again_keeps_the_label_read_it_had(env):
    """Its label was read in the blip, and a typed id doesn't take that back, as for
    any other spool."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9, source="barcode")
    assert session()["found_by"]["9"] == logic.AUDIT_FOUND_BY_LABEL
    scan(env, "ID:9")
    assert session()["found_by"]["9"] == logic.AUDIT_FOUND_BY_LABEL
    assert session()["rows"]["9"]["where"] == "CR"


def test_only_the_unread_row_reads_again(env):
    """A row that has its place stays a double read: the rest of this section's
    rule is about that one row, and a shelf's worth of double reads reads nothing."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9)
    scan(env, "ID:9")
    env["fake"].gets.clear()
    env["logs"].clear()
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert env["fake"].gets == [] and env["logs"] == []


def test_a_double_read_of_a_row_being_read_again_records_it_once(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9)
    real = spoolman_api.get_spool_answer

    def read_twice(sid):
        answer = real(sid)
        monkeypatch.setattr(spoolman_api, "get_spool_answer", real)
        scan(env, "ID:9")           # the second read lands first
        return answer

    monkeypatch.setattr(spoolman_api, "get_spool_answer", read_twice)
    assert scan(env, "ID:9") == AUDIT_SCAN
    assert session()["rogue_items"] == [9] and session()["scanned_items"] == [9]
    assert len(env["logs"]) == 1, env["logs"]


def test_a_row_being_read_again_stays_on_the_panel_until_the_read_answers(env, monkeypatch):
    """The read takes a moment, and a poll or a Done can land in it."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scanned_in_a_blip(env, 9)
    real = spoolman_api.get_spool_answer
    during = []

    def look_during_the_read(sid):
        during.append((list(session()["rogue_items"]), list(session()["scanned_items"])))
        return real(sid)

    monkeypatch.setattr(spoolman_api, "get_spool_answer", look_during_the_read)
    scan(env, "ID:9")
    assert during == [([9], [9])]


# --- the locations file ---------------------------------------------------------

LOCATIONS_WORDS = "Couldn't read the locations file, so nothing was recorded. Scan it again in a moment."


def locations_file_breaks(monkeypatch):
    """A hand edit gone wrong: what load_locations_list raises for it."""
    good = locations_db.load_locations_list

    def corrupt():
        raise locations_db.LocationsCorruptError("data/locations.json",
                                                 json.JSONDecodeError("Expecting value (test)", "{", 1))

    monkeypatch.setattr(locations_db, "load_locations_list", corrupt)
    return lambda: monkeypatch.setattr(locations_db, "load_locations_list", good)


def test_a_broken_locations_file_refuses_a_location_scan_in_words(env, monkeypatch):
    """An HTML 500, and the panel said FCC didn't answer. The same scan outside an
    audit answers 200, so this was the audit's own."""
    add_spool(env, 1, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    mended = locations_file_breaks(monkeypatch)
    assert scan(env, "LOC:LR-MDB-1") == {"type": "error", "msg": LOCATIONS_WORDS}
    assert session()["active"] is True and session()["location_id"] is None
    assert session()["expected_items"] == [] and session()["rows"] == {}
    assert [(m, c) for m, c, _ in env["logs"]] == [(f"⚠️ {LOCATIONS_WORDS}", "WARNING")]
    mended()
    assert scan(env, "LOC:LR-MDB-1") == AUDIT_SCAN
    assert session()["expected_items"] == [1]


def test_a_broken_locations_file_records_nothing_for_a_spool_loaded_from_here(env, monkeypatch):
    """Only the file can say the spool is on a head. An Extra here would be a guess,
    so the person scans it again."""
    add_spool(env, 1, "LR-MDB-2")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    mended = locations_file_breaks(monkeypatch)
    assert scan(env, "ID:242") == {"type": "error", "msg": LOCATIONS_WORDS}
    assert session()["scanned_items"] == [] and session()["rogue_items"] == [] and session()["trail_items"] == []
    assert "242" not in session()["rows"] and session()["found_by"] == {} and session()["last_found"] is None
    assert [c for _m, c, _ in env["logs"]] == ["WARNING"], env["logs"]
    mended()
    assert scan(env, "ID:242") == AUDIT_SCAN
    assert session()["trail_items"] == [242]


def test_a_broken_locations_file_leaves_a_row_being_read_again_as_it_was(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-2")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    scanned_in_a_blip(env, 242)
    mended = locations_file_breaks(monkeypatch)
    assert scan(env, "ID:242") == {"type": "error", "msg": LOCATIONS_WORDS}
    assert session()["rogue_items"] == [242] and session()["scanned_items"] == [242]
    assert session()["rows"]["242"]["where"] == UNREAD
    mended()
    scan(env, "ID:242")
    assert session()["rogue_items"] == [] and session()["trail_items"] == [242]


# ---------------------------------------------------------------------------
# 4. Other scans and commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, words", [
    ("LOC:LR-MDB-1:SLOT:2", "That's a slot label: scan the box's own label to audit it, or a spool's label"),
    ("FIL:5", "That's a filament label, not a spool"),
    ("https://prusament.com/spool/1234/abcdef0123/", "Scan a spool's FCC label"),
    ("ID:abc", "Invalid Spool ID Format"),                      # an error keeps its own words
    ("LOC:", "Empty Location Code"),
    ("not a label", "Unknown Code (Use LOC: prefix)"),
    ("CMD:GIBBERISH", "Malformed Command"),
    ("CMD:EJECT", "Command not allowed in Audit"),
])
def test_every_other_scan_has_its_own_words_and_a_log_line(env, text, words):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    ans = scan(env, text)
    assert ans == {"type": "error", "msg": words}
    assert session()["scanned_items"] == [] and session()["rogue_items"] == []
    assert any(words in m and c == "WARNING" for m, c, _ in env["logs"]), env["logs"]


def test_a_shared_legacy_label_skips_the_gate_and_its_pick_counts(env, monkeypatch):
    """Two spools share the label: the audit used to answer "Unknown scan type".
    The picker opens over the panel now, and its pick comes back as ID:<n>."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    start(env, "LR-MDB-1")
    stale = time.time() - 60
    session()["last_activity_ts"] = stale
    records = [env["fake"].records["spool"][sid] for sid in (1, 2)]
    monkeypatch.setattr(spoolman_api, "find_spools_by_legacy_id", lambda legacy: copy.deepcopy(records))
    ans = scan(env, "LEG:77")
    assert ans["type"] == "ambiguous" and [c["id"] for c in ans["candidates"]] == [1, 2]
    assert session()["scanned_items"] == [] and session()["rogue_items"] == []
    assert session()["last_activity_ts"] > stale      # a person is at it

    assert scan(env, "ID:2", source="keyboard") == AUDIT_SCAN
    assert session()["scanned_items"] == [2]


@pytest.mark.parametrize("audit_running", [True, False])
def test_a_shared_legacy_labels_log_line_escapes_the_label(env, monkeypatch, audit_running):
    """Activity Log messages are HTML, and this text is what was scanned."""
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 2, "LR-MDB-1")
    if audit_running:
        start(env, "LR-MDB-1")
    records = [env["fake"].records["spool"][sid] for sid in (1, 2)]
    monkeypatch.setattr(spoolman_api, "find_spools_by_legacy_id", lambda legacy: copy.deepcopy(records))
    ans = scan(env, "LEG:<B>77")
    assert ans["type"] == "ambiguous" and ans["legacy_id"] == "<B>77"
    assert log_text(env)[-1] == "⚠️ Legacy ID &lt;B&gt;77 matches 2 spools — pick one to continue"


def test_cmd_audit_during_an_audit_keeps_the_27_5_answer(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    audit_id = session()["audit_id"]
    assert scan(env, "CMD:AUDIT") == AUDIT_SCAN
    assert (session()["audit_id"], session()["location_id"], session()["scanned_items"]) == (
        audit_id, "LR-MDB-1", [1])


def test_no_audit_answer_is_the_buffer_clear_any_more(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    answers = [scan(env, "CMD:AUDIT"), scan(env, "CMD:AUDIT"), scan(env, "LOC:LR-MDB-1"),
               scan(env, "ID:1"), scan(env, "ID:9"), scan(env, "ID:1")]
    assert answers == [AUDIT_SCAN] * len(answers)


@pytest.mark.parametrize("command, why", [("CMD:DONE", "done"), ("CMD:CANCEL", "cancel")])
def test_an_answer_that_ended_the_audit_says_so(env, command, why):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    audit_id = session()["audit_id"]
    assert scan(env, command) == {**AUDIT_SCAN, "audit_ended": {"id": audit_id, "why": why}}
    assert state.AUDIT_LAST_END == {"id": audit_id, "why": why, "location": "LR-MDB-1"}


def test_the_last_end_outlives_the_next_audits_start(env):
    """The heartbeat's audit_end has to say how the audit a page believed in went,
    whatever has started since."""
    scan(env, "CMD:AUDIT")
    first = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    scan(env, "CMD:AUDIT")
    assert state.AUDIT_LAST_END == {"id": first, "why": "cancel", "location": ""}


# --- the idle watchdog -------------------------------------------------------

def _go_stale():
    session()["last_activity_ts"] = time.time() - (state.AUDIT_IDLE_TIMEOUT_SECONDS + 60)


def test_a_scan_after_the_idle_window_finds_no_session(env):
    """It used to refresh the timestamp first, reviving a stale session."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    audit_id = session()["audit_id"]
    _go_stale()
    ans = scan(env, "ID:1", source="keyboard")
    assert ans["type"] == "spool" and ans["id"] == 1      # the normal path
    assert session()["active"] is False
    assert state.AUDIT_LAST_END == {"id": audit_id, "why": "idle", "location": "LR-MDB-1"}


def test_cmd_audit_after_the_idle_window_starts_a_new_audit(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    old = session()["audit_id"]
    _go_stale()
    assert scan(env, "CMD:AUDIT") == AUDIT_SCAN
    assert session()["active"] is True and session()["audit_id"] != old
    assert session()["location_id"] is None


def test_the_idle_end_is_one_line_from_ids_alone(env):
    """It used to throw the results away. The heartbeat reads nothing from
    Spoolman for it."""
    for sid in (101, 102, 103):
        add_spool(env, sid, "LR-MDB-1")
    add_spool(env, 999, "CR")
    add_spool(env, 7, "XL-1", physical_source="LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:101")
    scan(env, "ID:999")
    scan(env, "ID:7")
    env["logs"].clear()
    env["fake"].gets.clear()
    _go_stale()
    app_module._check_audit_idle_timeout()
    assert session()["active"] is False
    (msg, cat, color), = env["logs"]
    assert (cat, color) == ("WARNING", "ffaa00")
    assert "found 1 of 3; missing #102, #103; extra #999; loaded from here #7" in msg
    assert "(was on LR-MDB-1)" in msg and "no spools moved" in msg
    assert env["fake"].gets == []


def test_the_idle_end_of_an_audit_with_no_place_has_nothing_to_report(env):
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    _go_stale()
    app_module._check_audit_idle_timeout()
    (msg, _cat, _color), = env["logs"]
    assert "found" not in msg.lower() and session()["active"] is False


def test_the_watchdog_stays_away_while_an_end_is_running(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    _go_stale()
    with logic._AUDIT_END_LOCK:
        app_module._check_audit_idle_timeout()
        assert session()["active"] is True and env["logs"] == []
    app_module._check_audit_idle_timeout()
    assert session()["active"] is False


def test_the_watchdog_never_takes_the_lock_for_an_audit_that_isnt_stale(env, monkeypatch):
    """A scan arriving in that instant would be told the audit is finishing."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")

    class _Lock:
        def locked(self):
            return False

        def acquire(self, *a):
            raise AssertionError("the watchdog took the end lock with nothing to end")

    monkeypatch.setattr(logic, "_AUDIT_END_LOCK", _Lock())
    app_module._check_audit_idle_timeout()
    assert session()["active"] is True


def test_a_scan_landing_as_the_watchdog_takes_the_lock_keeps_the_audit(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    _go_stale()

    class _Lock:
        def locked(self):
            return False

        def acquire(self, *a):
            session()["last_activity_ts"] = time.time()    # the scan got there first
            return True

        def release(self):
            pass

    monkeypatch.setattr(logic, "_AUDIT_END_LOCK", _Lock())
    app_module._check_audit_idle_timeout()
    assert session()["active"] is True


def test_a_second_watchdog_finds_nothing_to_end(env):
    start(env, "SHELF-1")
    _go_stale()
    app_module._check_audit_idle_timeout()
    first = state.AUDIT_LAST_END
    env["logs"].clear()
    app_module._check_audit_idle_timeout()
    assert env["logs"] == [] and state.AUDIT_LAST_END is first


# --- the end lock ------------------------------------------------------------

@pytest.mark.parametrize("text", ["CMD:DONE", "CMD:CANCEL", "ID:1", "ID:9", "FIL:5", "LOC:LR-MDB-2"])
def test_every_scan_is_refused_while_the_audit_is_finishing(env, text):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    with logic._AUDIT_END_LOCK:
        ans = scan(env, text)
    assert ans == {"type": "error", "msg": "The audit is already finishing."}
    assert session()["active"] is True and session()["scanned_items"] == []
    assert env["fake"].patches == []
    assert any("already finishing" in m for m in log_text(env))


def test_a_second_done_during_the_park_parks_nothing_more(env, monkeypatch):
    """A second press or a scanned Done while the first was writing used to run
    the whole list again, and report twice."""
    for sid in (1, 2, 3):
        add_spool(env, sid, "LR-MDB-1")
    start(env, "LR-MDB-1")
    answers = []
    real = env["fake"].patch

    def patch_then_press_done(url, json=None, timeout=None, **kw):   # noqa: A002
        answers.append(scan(env, "CMD:DONE"))
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch_then_press_done)
    assert "audit_ended" in park(env)
    assert sorted(p[1] for p in env["fake"].patches) == [1, 2, 3]
    assert answers == [{"type": "error", "msg": "The audit is already finishing."}] * 3
    assert len([m for m in log_text(env) if "Audit Report" in m]) == 1


def test_a_second_done_during_the_first_ones_read_is_refused(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    real = spoolman_api.get_all_spools_strict
    answers = []

    def read_then_press_done(*a, **k):
        answers.append(scan(env, "CMD:DONE"))
        return real(*a, **k)

    monkeypatch.setattr(spoolman_api, "get_all_spools_strict", read_then_press_done)
    assert scan(env, "CMD:DONE")["type"] == "audit_done_question"
    assert answers == [{"type": "error", "msg": "The audit is already finishing."}]


def test_cancel_during_a_park_doesnt_end_it_twice(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    audit_id = session()["audit_id"]
    answers = []
    real = env["fake"].patch

    def patch_then_cancel(url, json=None, timeout=None, **kw):       # noqa: A002
        answers.append(scan(env, "CMD:CANCEL"))
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", patch_then_cancel)
    park(env)
    assert answers == [{"type": "error", "msg": "The audit is already finishing."}]
    assert state.AUDIT_LAST_END == {"id": audit_id, "why": "done", "location": "LR-MDB-1"}


def test_two_ends_at_once_only_one_wins(env):
    """The lock is a real one: a loser in another thread is refused, never queued."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    results = []
    logic._AUDIT_END_LOCK.acquire()

    def press():
        results.append(logic._audit_finish("cancel"))

    worker = threading.Thread(target=press)
    worker.start()
    worker.join(5)
    logic._AUDIT_END_LOCK.release()
    assert not worker.is_alive(), "the loser waited for the lock"
    assert results == [{"status": "error", "msg": "The audit is already finishing."}]


# --- a scan past the gate as the audit ends -----------------------------------

ENDED = {"type": "error", "msg": "That audit has ended."}


def ended_just_past_the_gate(env, monkeypatch, name="process_audit_scan"):
    """A whole other request ends the audit in the instant between the route's gate
    and logic.`name`, as two presses a moment apart can. Two real threads hit it 8
    times in 1500 at a 1 microsecond switch interval; this hits it every time."""
    real = getattr(logic, name)

    # **kwargs: the route passes process_audit_scan the find's `how` (Group 58 H S2).
    def ended_first(*args, **kwargs):
        monkeypatch.setattr(logic, name, real)
        assert "audit_ended" in scan(env, "CMD:CANCEL")
        return real(*args, **kwargs)

    monkeypatch.setattr(logic, name, ended_first)


@pytest.mark.parametrize("name", ["process_audit_scan", "_audit_finish"])
@pytest.mark.parametrize("second", ["CMD:CANCEL", "CMD:DONE"])
def test_an_end_past_the_gate_ends_nothing_more(env, monkeypatch, second, name):
    """It ran on the reset session: a second report ("nothing was checked"), a second
    "Audit Mode Ended.", and AUDIT_LAST_END lost the real id, so another tab said
    "FCC restarted" instead of "elsewhere"."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    audit_id = session()["audit_id"]
    env["logs"].clear()
    ended_just_past_the_gate(env, monkeypatch, name)
    assert scan(env, second) == ENDED
    assert state.AUDIT_LAST_END == {"id": audit_id, "why": "cancel", "location": "LR-MDB-1"}
    assert sum("Audit Report" in m for m in log_text(env)) == 1, log_text(env)
    assert log_text(env).count("Audit Mode Ended.") == 1, log_text(env)
    assert not logic._AUDIT_END_LOCK.locked()


@pytest.mark.parametrize("text", ["LOC:LR-MDB-1", "ID:1", "CMD:NEEDLABEL", "FIL:5"])
def test_a_scan_past_the_gate_stores_nothing_on_an_ended_session(env, monkeypatch, text):
    """A location stored location_id and expected_items on an inactive session: the
    heartbeat then read audit_active false with an audit_location. The check after
    each read can't see it, because a reset session's id is None on both sides."""
    add_spool(env, 1, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    ended_just_past_the_gate(env, monkeypatch)
    assert scan(env, text) == ENDED
    got = session()
    assert (got["location_id"], got["expected_items"], got["rows"], got["scanned_items"]) == (None, [], {}, [])
    assert env["client"].get("/api/logs").get_json()["audit_location"] == ""
    assert env["fake"].patches == []


# --- Done, for now, and Cancel ----------------------------------------------

def test_done_moves_only_the_new_rules_list_on_the_real_write(env):
    """The heart of the rule, on the real update_spool: a room audit used to park
    every spool under the room, a loaded one included, off its head."""
    add_spool(env, 1, "LR", container_slot="")
    add_spool(env, 2, "LR")
    add_spool(env, 3, "LR-MDB-1", container_slot="1")               # inside the room
    add_spool(env, 242, "XL-1", physical_source="LR")               # loaded from it
    add_spool(env, 4, "XL-2", physical_source="LR-MDB-1")           # a prefix hit
    start(env, "LR")
    scan(env, "ID:1")
    assert "audit_ended" in park(env)
    assert [p[1] for p in env["fake"].patches] == [2]
    spools = env["fake"].records["spool"]
    assert spools[2]["location"] == "UNKNOWN"
    assert spools[1]["location"] == "LR" and spools[3]["location"] == "LR-MDB-1"
    assert spools[242]["location"] == "XL-1" and spools[4]["location"] == "XL-2"


def test_cancel_writes_nothing(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:9")
    assert "audit_ended" in scan(env, "CMD:CANCEL")
    assert env["fake"].patches == []
    assert session()["active"] is False


# --- the report --------------------------------------------------------------

def test_the_report_is_one_entry_naming_the_place_and_everything_in_it(env):
    for sid in (1, 2):
        add_spool(env, sid, "LR-MDB-2", name=f"Filed {sid}")
    add_spool(env, 9, "CR-CT-1-R2", name="Stray", container_slot="3")
    add_spool(env, 7, "XL-1", name="Running", physical_source="LR-MDB-2")
    start(env, "LR-MDB-2")
    scan(env, "ID:1")
    scan(env, "ID:9")
    scan(env, "ID:7")
    env["logs"].clear()
    env["fake"].gets.clear()
    scan(env, "CMD:CANCEL")
    line = report(env)
    assert "Audit Report: LR-MDB-2" in line
    assert "Found 1 of 2." in line
    assert "<b>Missing:</b> #2 Some Brand PLA (Filed 2)" in line
    assert "<b>Extra:</b> #9 Some Brand PLA (Stray) → CR-CT-1-R2 slot 3" in line
    assert "<b>Loaded from here:</b> #7 Some Brand PLA (Running) → XL-1" in line
    assert "Perfect Match" not in line and "Parked" not in line
    # The panel's stored rows name them: no read for a report.
    assert env["fake"].gets == []


def test_the_report_is_written_after_everything_but_the_end(env):
    """The log keeps 50 lines, and 49 parked spools used to push the report out."""
    for sid in (1, 2):
        add_spool(env, sid, "LR-MDB-1")
    start(env, "LR-MDB-1")
    park(env)
    lines = log_text(env)
    assert "Audit Report" in lines[-2] and lines[-1] == "Audit Mode Ended."
    assert sum("moved Spool" in m for m in lines) == 2


def test_the_report_says_what_was_parked_and_what_failed(env, monkeypatch):
    for sid in (1, 2):
        add_spool(env, sid, "LR-MDB-1")
    start(env, "LR-MDB-1")
    real = env["fake"].patch

    def refuse_spool_2(url, json=None, timeout=None, **kw):          # noqa: A002
        if url.rstrip("/").endswith("/2"):
            return _Resp(400, {"message": "nope (test)"})
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", refuse_spool_2)
    park(env)
    line = report(env)
    assert "<b>Parked at Unknown:</b> #1" in line
    assert "<b>Failed:</b> #2" in line


@pytest.mark.parametrize("filed, found, extra, perfect", [
    ([1, 2], [1, 2], [], True),
    ([1, 2], [1], [], False),               # one missing
    ([1, 2], [1, 2], [9], False),           # an extra
    ([], [], [], False),                    # nothing expected
    ([], [], [9], False),                   # nothing expected, an extra
])
def test_perfect_match_takes_something_expected_all_found_and_no_extra(env, filed, found, extra, perfect):
    for sid in filed:
        add_spool(env, sid, "SHELF-1")
    for sid in extra:
        add_spool(env, sid, "CR")
    start(env, "SHELF-1")
    for sid in found + extra:
        scan(env, f"ID:{sid}")
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    line = report(env)
    assert ("Perfect Match" in line) is perfect, line
    color = next(c for m, _cat, c in env["logs"] if "Audit Report" in m)
    assert color == ("00ff00" if perfect else "ffaa00")


def test_a_spool_loaded_from_here_doesnt_spoil_a_perfect_match(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 7, "XL-1", physical_source="LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    scan(env, "ID:7")
    env["logs"].clear()
    scan(env, "CMD:CANCEL")
    line = report(env)
    assert "Perfect Match" in line and "Loaded from here" in line


@pytest.mark.parametrize("command", ["CMD:DONE", "CMD:CANCEL"])
def test_no_place_no_perfect_match(env, command):
    """It used to end on a green "Perfect Match" with nothing checked."""
    scan(env, "CMD:AUDIT")
    scan(env, command)
    line = report(env)
    assert "Audit ended before a location was scanned: nothing was checked." in line
    assert "Perfect Match" not in line


def test_nothing_expected_and_nothing_scanned_says_that(env):
    start(env, "SHELF-1")
    scan(env, "CMD:CANCEL")
    line = report(env)
    assert "Audit Report: SHELF-1" in line and "Nothing was filed here and nothing was scanned." in line


def test_a_failed_read_can_no_longer_end_on_a_perfect_match(env):
    scan(env, "CMD:AUDIT")
    env["fake"].list_reads_fail = True
    scan(env, "LOC:LR-MDB-1")
    scan(env, "CMD:DONE")
    assert "nothing was checked" in report(env)


# --- every audit line escapes outside text ------------------------------------

def test_outside_text_in_every_audit_line_is_escaped(env, monkeypatch):
    add_spool(env, 1, "<B>BOX", name="<i>Red")
    add_spool(env, 2, "<B>BOX", name="<i>Blue")
    add_spool(env, 3, "<B>BOX", name="<i>Green")
    add_spool(env, 9, "<B>BIN", name="<i>Stray")
    env["fake"].patches.clear()
    assert scan(env, "CMD:AUDIT") == AUDIT_SCAN
    assert scan(env, "LOC:<B>BOX") == AUDIT_SCAN
    scan(env, "ID:9")
    real = env["fake"].patch

    def refuse_spool_2(url, json=None, timeout=None, **kw):          # noqa: A002
        if url.rstrip("/").endswith("/2"):
            return _Resp(400, {"message": "<script>nope</script>"})
        return real(url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(spoolman_api.requests, "patch", refuse_spool_2)
    park(env)
    joined = "\n".join(log_text(env))
    for piece in ("&lt;B&gt;BOX", "&lt;B&gt;BIN", "&lt;I&gt;Red", "&lt;I&gt;Stray", "&lt;script&gt;nope"):
        assert piece in joined, joined
    assert "<B>BOX" not in joined and "<I>" not in joined and "<script>" not in joined, joined


def test_a_refusal_escapes_the_scanned_text_in_its_log_line(env):
    scan(env, "CMD:AUDIT")
    env["logs"].clear()
    ans = scan(env, "LOC:<B>TYPO")
    assert ans["msg"] == "<B>TYPO isn't a place FCC knows."      # the toast draws plain text
    assert log_text(env) == ["⚠️ &lt;B&gt;TYPO isn't a place FCC knows."]


def test_the_idle_line_escapes_the_place(env):
    add_spool(env, 1, "<B>BOX")
    scan(env, "CMD:AUDIT")
    scan(env, "LOC:<B>BOX")
    env["logs"].clear()
    _go_stale()
    app_module._check_audit_idle_timeout()
    assert "(was on &lt;B&gt;BOX)" in log_text(env)[0]


# ---------------------------------------------------------------------------
# /api/audit_session: from the stored rows
# ---------------------------------------------------------------------------

def _panel_session(env):
    add_spool(env, 1, "LR-MDB-2", name="Filed", container_slot="2")
    add_spool(env, 2, "LR-MDB-2", name="Other")
    add_spool(env, 9, "CR-CT-1-R2", name="Stray", container_slot="3")
    add_spool(env, 7, "XL-1", name="Running", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    scan(env, "ID:1")
    scan(env, "ID:9")
    scan(env, "ID:7")
    env["fake"].gets.clear()


def test_the_panels_poll_reads_no_spoolman(env):
    """Each poll used to read one spool at a time, every 2 s, from every browser."""
    _panel_session(env)
    body = env["client"].get("/api/audit_session").get_json()
    assert env["fake"].gets == []
    assert body["audit_id"] == session()["audit_id"]
    assert body["location_id"] == "LR-MDB-2"
    assert body["stats"] == {"total_expected": 2, "found": 1, "missing": 1, "rogue": 1, "trail": 1}

    expected = {row["id"]: row for row in body["expected"]}
    assert expected[1]["found"] is True and expected[2]["found"] is False
    assert expected[1]["where"] == "LR-MDB-2 slot 2" and expected[2]["where"] == "LR-MDB-2"
    assert expected[1]["display"] == "#1 Some Brand PLA (Filed)" and expected[1]["color"] == "72071C"

    assert [r["id"] for r in body["rogue"]] == [9]
    assert body["rogue"][0]["rogue"] is True and body["rogue"][0]["where"] == "CR-CT-1-R2 slot 3"
    assert [r["id"] for r in body["trail"]] == [7]
    assert body["trail"][0]["trail"] is True and body["trail"][0]["found"] is True
    assert body["trail"][0]["where"] == "XL-1" and body["trail"][0]["slot"] == "1"


def test_a_blip_cant_blank_a_tile(env):
    _panel_session(env)
    env["fake"].down = True
    body = env["client"].get("/api/audit_session").get_json()
    assert {r["display"] for r in body["expected"]} == {"#1 Some Brand PLA (Filed)", "#2 Some Brand PLA (Other)"}


def test_the_panel_gets_the_start_note(env):
    add_spool(env, 1, "CR")
    add_spool(env, 2, "CR-CT-1")
    start(env, "CR")
    body = env["client"].get("/api/audit_session").get_json()
    assert body["note"] == session()["start_note"]
    assert body["note"].startswith("1 is filed here.")


def test_a_row_with_no_stored_data_is_still_read(env):
    """Hand-built sessions and the endpoint's own tests; a failed read keeps the
    row, with no made-up place."""
    add_spool(env, 5, "LR-MDB-1", container_slot="2")
    state.AUDIT_SESSION.update({"active": True, "location_id": "LR-MDB-1",
                                "expected_items": [5, 6], "scanned_items": []})
    body = env["client"].get("/api/audit_session").get_json()
    rows = {r["id"]: r for r in body["expected"]}
    assert rows[5]["where"] == "LR-MDB-1 slot 2" and rows[5]["display"].startswith("#5")
    assert rows[6]["display"] == "#6" and rows[6]["where"] == ""


# ---------------------------------------------------------------------------
# The heartbeat
# ---------------------------------------------------------------------------

def _heartbeats(env):
    logs = env["client"].get("/api/logs").get_json()
    status = env["client"].get("/api/dashboard_pulse?include=status").get_json()["status"]
    return logs, status


def test_the_heartbeat_names_the_place_and_says_nothing_has_ended(env):
    add_spool(env, 1, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    for payload in _heartbeats(env):
        assert payload["audit_active"] is True and payload["audit_location"] == ""
        assert payload["audit_end"] is None
    scan(env, "LOC:LR-MDB-1")
    for payload in _heartbeats(env):
        assert payload["audit_location"] == "LR-MDB-1"


@pytest.mark.parametrize("end", ["CMD:DONE", "CMD:CANCEL", "idle"])
def test_the_heartbeat_says_why_the_audit_ended(env, end):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    audit_id = session()["audit_id"]
    if end == "idle":
        _go_stale()
    else:
        scan(env, end)
    want = {"id": audit_id, "why": {"CMD:DONE": "done", "CMD:CANCEL": "cancel", "idle": "idle"}[end],
            "location": "LR-MDB-1"}
    for payload in _heartbeats(env):      # the watchdog rides the heartbeat
        assert payload["audit_active"] is False and payload["audit_location"] == ""
        assert payload["audit_end"] == want


def test_the_heartbeat_says_which_audit_runs(env):
    """A hidden panel has no poll, so this keeps the id a page stamps its scans with
    current, in both shapes."""
    for payload in _heartbeats(env):
        assert payload["audit_id"] is None
    scan(env, "CMD:AUDIT")
    audit_id = session()["audit_id"]
    assert audit_id
    for payload in _heartbeats(env):
        assert payload["audit_id"] == audit_id
    scan(env, "CMD:CANCEL")
    for payload in _heartbeats(env):
        assert payload["audit_id"] is None


# ---------------------------------------------------------------------------
# A scan says which audit it was read for (`audit_seen`)
# ---------------------------------------------------------------------------

def gone(text):
    return {"type": "audit_gone", "msg": f"The audit has ended, so {text} did nothing. Scan it again if you meant it."}


@pytest.fixture
def one_in_the_buffer(env, monkeypatch):
    """A spool on the list, and another buffered, which a slot label would load."""
    add_spool(env, 1, "LR-MDB-1", container_slot="1")
    add_spool(env, 5, "CR-CT-1", name="Buffered")
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [{"id": 5, "display": "#5"}])
    return env


# What a page sends once its audit has gone. Each would act, and three would write.
SCANS_MEANT_FOR_AN_AUDIT = [("LOC:LR-MDB-2:SLOT:2", "barcode"), ("LOC:LR-MDB-2", "barcode"),
                            ("ID:1", "barcode"), ("CMD:DONE", "barcode")]


def assert_did_nothing(env, before, text):
    """No write, no move, the buffer as it was, and one line saying so."""
    assert env["fake"].patches == []
    assert env["fake"].records["spool"] == before
    assert state.GLOBAL_BUFFER == [{"id": 5, "display": "#5"}]
    lines = [(m, c) for m, c, _ in env["logs"] if "The audit has ended" in m]
    assert lines == [(f"⚠️ {html.escape(gone(text)['msg'], quote=False)}", "WARNING")]


@pytest.mark.parametrize("text, source", SCANS_MEANT_FOR_AN_AUDIT)
@pytest.mark.parametrize("ended_by", ["CMD:CANCEL", "idle"])
def test_a_scan_for_an_audit_that_has_gone_does_nothing(one_in_the_buffer, text, source, ended_by):
    """It fell through to the normal paths: a slot label scanned at a hidden panel
    after an idle end loaded the buffered spool into that slot."""
    env = one_in_the_buffer
    start(env, "LR-MDB-1")
    seen = session()["audit_id"]
    if ended_by == "idle":
        _go_stale()             # the scan itself finds this out, before it refreshes anything
    else:
        scan(env, ended_by)
    env["logs"].clear()
    before = copy.deepcopy(env["fake"].records["spool"])
    assert scan(env, text, source=source, audit_seen=seen) == gone(text)
    assert_did_nothing(env, before, text)
    assert session()["active"] is False


@pytest.mark.parametrize("text, source", SCANS_MEANT_FOR_AN_AUDIT)
def test_a_scan_for_an_audit_that_gave_way_to_another_leaves_that_one_alone(one_in_the_buffer, text, source):
    """It would have landed on the next audit: a Done there, or a spool found there
    that nobody read for it."""
    env = one_in_the_buffer
    start(env, "LR-MDB-1")
    seen = session()["audit_id"]
    scan(env, "CMD:CANCEL")
    start(env, "LR-MDB-1")
    running = session()["audit_id"]
    assert running != seen
    before = copy.deepcopy(env["fake"].records["spool"])
    assert scan(env, text, source=source, audit_seen=seen) == gone(text)
    assert_did_nothing(env, before, text)
    got = session()
    assert (got["active"], got["audit_id"], got["location_id"], got["scanned_items"]) == (
        True, running, "LR-MDB-1", [])


def test_with_no_stamp_those_scans_act_as_they_always_did(one_in_the_buffer):
    """A page from before the release sends none, so there is no check. And this is
    what the stamp stops, on the real engine: a label read that writes, and a slot
    label that loads the buffered spool."""
    env = one_in_the_buffer
    assert scan(env, "ID:1", source="barcode")["type"] == "spool"
    assert [p[1] for p in env["fake"].patches] == [1]
    ans = scan(env, "LOC:LR-MDB-2:SLOT:2")
    assert ans["type"] == "assignment" and ans["moved"] == 5, ans
    assert env["fake"].records["spool"][5]["location"] == "LR-MDB-2"


def test_the_right_id_is_an_ordinary_audit_scan(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert scan(env, "ID:1", audit_seen=session()["audit_id"]) == AUDIT_SCAN
    assert session()["scanned_items"] == [1]


def test_a_page_with_no_id_yet_is_fine_while_an_audit_runs(env):
    """The moment after it started one, before the heartbeat told it the id."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert scan(env, "ID:1", audit_seen=True) == AUDIT_SCAN
    assert session()["scanned_items"] == [1]


def test_a_page_with_no_id_yet_is_told_when_none_runs(env):
    add_spool(env, 1, "LR-MDB-1")
    assert scan(env, "ID:1", audit_seen=True) == gone("ID:1")


@pytest.mark.parametrize("seen", [None, False, ""])
def test_no_belief_is_no_check(env, seen):
    add_spool(env, 1, "LR-MDB-1")
    assert scan(env, "ID:1", audit_seen=seen)["type"] == "spool"


def test_the_stamp_is_read_after_the_idle_check(env):
    """A scan after 30 idle minutes counts as gone, so it can't refresh the audit it
    was meant for, and the page hears why."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    seen = session()["audit_id"]
    _go_stale()
    assert scan(env, "ID:1", audit_seen=seen) == gone("ID:1")
    assert state.AUDIT_LAST_END == {"id": seen, "why": "idle", "location": "LR-MDB-1"}


def test_the_gone_line_escapes_what_was_scanned(env):
    """Activity Log messages are HTML, and the toast draws plain text."""
    text = "LOC:<B>BOX"
    assert scan(env, text, audit_seen=True)["msg"] == gone(text)["msg"]
    assert log_text(env) == ["⚠️ The audit has ended, so LOC:&lt;B&gt;BOX did nothing. Scan it again if you meant it."]


@pytest.mark.parametrize("active, running, seen, want", [
    (False, None, "boot-1", True),      # no audit runs
    (False, None, True, True),
    (True, "boot-2", "boot-1", True),   # a different one runs
    (True, "boot-1", "boot-1", False),
    (True, "boot-1", True, False),
    (True, "boot-1", None, False),      # no belief: no check
    (False, None, None, False),
])
def test_audit_seen_gone(active, running, seen, want):
    state.reset_audit()
    state.AUDIT_SESSION.update(active=active, audit_id=running)
    try:
        assert logic.audit_seen_gone(seen) is want
    finally:
        state.reset_audit()


# ---------------------------------------------------------------------------
# A closed dialog's cancel QR, at the gates
# ---------------------------------------------------------------------------

STALE_CANCEL = "That cancel QR belongs to a dialog that has closed — ignored"
CLOSED_DIALOG_QRS = ["CMD:CANCEL:ab12cd", "cmd:cancel:ab12cd", "qCMD:CANCEL:ab12cd"]
BARE_CANCELS = ["CMD:CANCEL", "cmd:cancel", "qCMD:CANCEL", '"CMD:CANCEL"', "  CMD:CANCEL  "]


@pytest.fixture
def bulk_move():
    state.BULK_MOVE_SESSION.update(active=True, stage="awaiting_dest", source_id="LR-MDB-1",
                                   last_activity_ts=time.time())
    yield state.BULK_MOVE_SESSION
    state.reset_bulk_move()


@pytest.mark.parametrize("text", CLOSED_DIALOG_QRS)
def test_a_closed_dialogs_cancel_qr_ends_no_audit(env, text):
    """resolve_scan finds CMD:CANCEL anywhere in the text, so "Scan to go back" read
    after its question closed, on a page that hadn't heard an audit runs, threw away
    every scan in it."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    env["logs"].clear()
    assert scan(env, text) == {"type": "error", "msg": STALE_CANCEL}
    assert session()["active"] is True and session()["scanned_items"] == [1]
    assert state.AUDIT_LAST_END is None
    assert [(m, c) for m, c, _ in env["logs"]] == [(f"⚠️ {STALE_CANCEL}", "WARNING")]


@pytest.mark.parametrize("text", CLOSED_DIALOG_QRS)
def test_a_closed_dialogs_cancel_qr_cancels_no_bulk_move(env, bulk_move, text):
    assert scan(env, text) == {"type": "error", "msg": STALE_CANCEL}
    assert bulk_move["active"] is True and bulk_move["stage"] == "awaiting_dest"
    assert [(m, c) for m, c, _ in env["logs"]] == [(f"⚠️ {STALE_CANCEL}", "WARNING")]


@pytest.mark.parametrize("text", BARE_CANCELS)
def test_the_bare_command_cancels_an_audit_with_or_without_a_stray_key(env, text):
    """A QR is read at the end of a scan, so a key left in front never stops "Scan to
    Cancel". Pins what was already right; proved on a copy with the gate on every
    scan that isn't exactly CMD:CANCEL."""
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    assert "audit_ended" in scan(env, text)
    assert session()["active"] is False


@pytest.mark.parametrize("text", BARE_CANCELS)
def test_the_bare_command_cancels_a_bulk_move_with_or_without_a_stray_key(env, bulk_move, text):
    scan(env, text)
    assert bulk_move["active"] is False


@pytest.mark.parametrize("text", CLOSED_DIALOG_QRS + BARE_CANCELS)
def test_outside_a_session_a_cancel_answers_as_it_always_did(env, text):
    assert scan(env, text) == {"type": "command", "cmd": "cancel"}
    assert env["logs"] == []


# ---------------------------------------------------------------------------
# `heard`: what a scan did, for a hidden panel
# ---------------------------------------------------------------------------

def test_a_location_scan_is_heard(env):
    for sid in (1, 2):
        add_spool(env, sid, "LR-MDB-1")
    scan(env, "CMD:AUDIT")
    assert scan_answer("LOC:LR-MDB-1") == {**AUDIT_SCAN, "heard": "Auditing LR-MDB-1: 2 expected"}


def test_a_spool_on_the_list_is_heard_with_what_is_left(env):
    for sid in (1, 2):
        add_spool(env, sid, "LR-MDB-1")
    start(env, "LR-MDB-1")
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S2): a typed id reads no label,
    # and `heard` says so; a real read of the label keeps the old words.
    assert scan_answer("ID:1") == {**AUDIT_SCAN, "heard": "Found #1, no label read (1 left)"}
    assert scan_answer("ID:2", source="barcode") == {**AUDIT_SCAN, "heard": "Found #2 (All found!)"}


def test_a_double_read_is_heard(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    scan(env, "ID:1")
    scan(env, "ID:9")
    assert scan_answer("ID:1") == {**AUDIT_SCAN, "heard": "#1 is already scanned"}
    assert scan_answer("ID:9") == {**AUDIT_SCAN, "heard": "#9 is already scanned"}


def test_a_double_read_that_lost_the_race_is_heard_too(env, monkeypatch):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR")
    start(env, "LR-MDB-1")
    real = spoolman_api.get_spool_answer

    def read_twice(sid):
        answer = real(sid)
        monkeypatch.setattr(spoolman_api, "get_spool_answer", real)
        scan(env, "ID:9")
        return answer

    monkeypatch.setattr(spoolman_api, "get_spool_answer", read_twice)
    assert scan_answer("ID:9")["heard"] == "#9 is already scanned"


def test_an_extra_is_heard_with_where_fcc_has_it(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "CR-CT-1-R2", container_slot="3")
    start(env, "LR-MDB-1")
    assert scan_answer("ID:9") == {**AUDIT_SCAN, "heard": "Extra: FCC has #9 at CR-CT-1-R2 slot 3"}


def test_an_extra_spoolman_wont_answer_for_is_heard_in_its_own_words(env):
    add_spool(env, 1, "LR-MDB-1")
    start(env, "LR-MDB-1")
    env["fake"].down = True
    assert scan_answer("ID:9") == {**AUDIT_SCAN, "heard": "Extra: #9: couldn't read where FCC has it"}
    assert scan_answer("ID:9") == {**AUDIT_SCAN, "heard": "Extra: #9: couldn't read where FCC has it"}


def test_a_lost_spool_is_heard_saying_which_audit_lost_it(env):
    add_spool(env, 1, "LR-MDB-1")
    add_spool(env, 9, "UNKNOWN", fcc_pre_audit_location="LR-MDB-2:2@2026-11-01")
    start(env, "LR-MDB-1")
    assert scan_answer("ID:9")["heard"] == (
        "Extra: FCC has #9 at Unknown (marked lost by the audit of LR-MDB-2 slot 2 on 2026-11-01)")


def test_a_spool_loaded_from_here_is_heard(env):
    add_spool(env, 1, "LR-MDB-2")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S2): a real read of the label keeps
    # these words; a typed id's say no label was read (test_audit_tiles_and_report_58).
    assert scan_answer("ID:242", source="barcode") == {**AUDIT_SCAN, "heard": "Found #242: loaded on XL-1 from here"}


def test_a_row_read_again_is_heard_as_what_it_turned_out_to_be(env):
    add_spool(env, 1, "LR-MDB-2")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-2", physical_source_slot="1")
    start(env, "LR-MDB-2")
    scanned_in_a_blip(env, 242)
    # PIN UPDATED DELIBERATELY (Derek, 2026-11-03, H S2): a typed id reads no label.
    assert scan_answer("ID:242")["heard"] == "Found #242, no label read: loaded on XL-1 from here"


@pytest.mark.parametrize("text, msg", [("LOC:LR-TYPO", "LR-TYPO isn't a place FCC knows."),
                                       ("ID:999999", "Spool #999999 not found")])
def test_a_refusal_has_no_heard(env, text, msg):
    """A refusal has its own toast. On the whole answer: scan() leaves these alone."""
    add_spool(env, 1, "LR-MDB-1")
    if text.startswith("LOC:"):
        scan(env, "CMD:AUDIT")
    else:
        start(env, "LR-MDB-1")
    assert scan_answer(text) == {"type": "error", "msg": msg}


def test_a_command_has_no_heard(env):
    add_spool(env, 1, "LR-MDB-1")
    assert scan_answer("CMD:AUDIT") == AUDIT_SCAN
    assert scan_answer("CMD:AUDIT") == AUDIT_SCAN
    assert set(scan_answer("CMD:CANCEL")) == {"type", "cmd", "audit_ended"}
