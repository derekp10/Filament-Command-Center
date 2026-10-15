"""Group 40.0c — a move into a bound box slot asks first when the head that slot
feeds already runs a spool from somewhere else (Derek's D2.2 / D2.3).

The auto-deploy chain loaded the slot's head and Smart Load unloaded whatever it
held, with no question when the printer was idle (Derek: "XL-1 running off a
PolyDryer while slot 1 is prepped for later"). The engine now answers
`requires_confirm` / `confirm_type: "head_fed"` before anything is written, in
the one 39.1 shape (`fed_heads` beside `active_prints`), unless:
  - the head is empty (an idle printer loads with no prompt);
  - its spool is the slot's OWN spool, whose trail is this very box and slot
    (Derek's everyday swap, "replace the spool in LR-MDB-1 slot 3");
  - the caller confirmed it: a page sends each answer's `confirm_key`
    ("XL-1#99"), which covers that head only while it runs exactly the spools
    the question named; a bare head id (internal callers) covers it whatever
    it runs. A slot rebound meanwhile is asked again.
"Just store it" is the same move with auto_deploy false (40.0b). A spool loaded
onto the head while the printer was being checked was never shown to the user,
so the chained deploy refuses to unload it, whatever its trail says, and the
incoming spool stays stored in its slot.

Doors: a question goes only to a request carrying `confirmed_fed_heads`; a page
from before 40.0c can't answer it (its replay rebuilt the confirm from
`active_print` and looped), so it is told to reload instead, naming the head.

The REAL engine runs over tests/move_engine_harness.py with a live locations
store, so the PolyDryer release on eject runs for real.
HEAD proof (97d05aa): every question test moves the spool unasked there (no
head_fed answer), the unreadable-head tests load it anyway, the chain-guard
tests unload #7 / #200, and the doors answer assignment_done / success instead
of asking. The controls (an empty idle head, the same-slot swap, "Just store
it", can_store false, the load replay, a stale page that needs no question)
pass on HEAD by design: they pin what must not change.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    # PM-DB-2 is a PolyDryer; its spool #99 runs on XL-1, so it is attached there.
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "PM-DB-3", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {}}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
]

FROM_POLYDRYER = {"physical_source": "PM-DB-2", "physical_source_slot": "1", "container_slot": ""}


@pytest.fixture(autouse=True)
def _isolate_state():
    prior = (state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER)
    state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = [], [], []
    try:
        yield
    finally:
        state.RECENT_LOGS, state.UNDO_STACK, state.GLOBAL_BUFFER = prior


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _sm(resident_extra=None, more=None):
    """#42 waits in the cart row; XL-1 runs #99 with `resident_extra` as its
    extras (no #99 at all when None); `more` adds spools."""
    spools = {42: {"location": "CR-CT-2-R1", "extra": {}}}
    if resident_extra is not None:
        spools[99] = {"location": "XL-1", "extra": dict(resident_extra)}
    spools.update(more or {})
    return FakeSpoolman(spools)


def _move(sm, store=None, probe=IDLE, slot="1", **kw):
    store = store or LocationsStore(ROWS)
    res = run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP,
                   target="LR-MDB-1", raw_spools=[42], target_slot=slot, origin="test", **kw)
    return res, store


def _logs(needle, types=None):
    return [e for e in state.RECENT_LOGS
            if needle in str(e.get("msg", "")) and (types is None or e.get("type") in types)]


# ---- when it asks nothing ----------------------------------------------------------

def test_an_empty_idle_head_loads_with_no_question():
    """Derek: "An empty head on an idle printer loads without an extra prompt.\""""
    sm = _sm()
    res, _ = _move(sm)
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42]


@pytest.mark.parametrize("trail_slot, slot", [("1", "1"), ('"1"', "1"), ("1", 1), ("01", "1")],
                         ids=["plain", "quoted-trail", "int-slot", "zero-padded"])
def test_the_slots_own_spool_coming_back_out_asks_nothing(trail_slot, slot):
    """XL-1 runs #99, deployed from LR-MDB-1 slot 1. Putting #42 in slot 1 is the
    normal swap: #42 loads, and no new question is asked. Deliberately changed
    (Group 40.2, Derek's 2026-10-15 answer): #99 used to go "home" into the slot
    #42 now holds (it landed there with no slot); it goes to the scan buffer,
    Unassigned (test_same_slot_swap_to_buffer.py pins the rest)."""
    sm = _sm({"physical_source": "LR-MDB-1", "physical_source_slot": trail_slot, "container_slot": ""})
    res, _ = _move(sm, slot=slot)
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42]
    assert sm.spools[99]["location"] == "", sm.writes
    assert [i["id"] for i in res.get("to_buffer") or []] == [99], res


# ---- the question ------------------------------------------------------------------

def test_a_head_running_a_polydryer_spool_asks_first_and_writes_nothing():
    sm = _sm(FROM_POLYDRYER)
    res, store = _move(sm)
    assert res.get("status") == "requires_confirm" and res.get("confirm_type") == "head_fed", res
    assert sm.writes == [], f"wrote {sm.writes} before the question"
    assert res["title"] == "Load #42 onto XL-1?"
    assert res["msg"] == res["body"] == ("LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #99 (from "
                                         "PM-DB-2). Loading #42 sends #99 back to PM-DB-2.")
    assert res["can_store"] is True and res["target_slot"] == "1" and res["spools"] == [42], res
    assert res["active_prints"] == [] and res["active_print"] is None, res
    fed = res["fed_heads"]
    assert [(f["toolhead"], f["box"], f["slot"], f["printer_name"], f["confirm_key"]) for f in fed] == [
        ("XL-1", "LR-MDB-1", "1", "XL", "XL-1#99")], fed
    resident = fed[0]["resident"]
    assert resident["id"] == 99 and resident["trail"] == {"box": "PM-DB-2", "slot": "1"}, resident
    assert resident["goes_to"] == "PM-DB-2", resident
    assert store.bound("PM-DB-2") == "XL-1", "a question must not detach the PolyDryer"


def test_load_it_instead_with_the_answers_key_loads_and_sends_the_polydryer_spool_home():
    sm = _sm(FROM_POLYDRYER)
    asked, store = _move(sm)
    res, _ = _move(sm, store=store, confirmed_fed_heads=[asked["fed_heads"][0]["confirm_key"]])
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42]
    assert sm.spools[99]["location"] == "PM-DB-2", sm.writes
    assert store.bound("PM-DB-2") == "", "PM-DB-2's own spool left XL-1, so it lets go (42.1)"


def test_a_yes_about_one_spool_never_covers_another():
    """The question named #99. While the dialog was open #99 went home and #7
    (from PM-DB-3) was loaded onto XL-1: the Yes about #99 doesn't cover #7, so
    the replay asks again, naming #7, and nothing moves."""
    sm = _sm(FROM_POLYDRYER)
    asked, store = _move(sm)
    sm.spools[99] = {"location": "PM-DB-2", "extra": {"container_slot": "1"}}
    sm.spools[7] = {"location": "XL-1", "extra": {"physical_source": "PM-DB-3", "physical_source_slot": "1"}}
    again, _ = _move(sm, store=store, confirmed_fed_heads=[asked["fed_heads"][0]["confirm_key"]])
    assert again.get("confirm_type") == "head_fed", again
    assert again["fed_heads"][0]["confirm_key"] == "XL-1#7", again
    assert "XL-1 is running #7 (from PM-DB-3)" in again["msg"], again["msg"]
    assert sm.direct_at("XL-1") == [7] and sm.spools[42]["location"] == "CR-CT-2-R1"


def test_just_store_it_keeps_the_spool_in_the_slot_and_the_head_as_it_was():
    sm = _sm(FROM_POLYDRYER)
    res, store = _move(sm, auto_deploy=False)
    assert res.get("status") == "success" and not res.get("failures"), res
    assert sm.spools[42]["location"] == "LR-MDB-1"
    assert sm.spools[42]["extra"]["container_slot"] == "1"
    assert sm.direct_at("XL-1") == [99], sm.writes
    assert store.bound("PM-DB-2") == "XL-1"


@pytest.mark.parametrize("extra, came_from, goes, goes_to", [
    ({}, None, "to Room LR", "LR"),
    ({"physical_source": "CR-CT-2-R1", "physical_source_slot": ""}, "CR-CT-2-R1",
     "back to CR-CT-2-R1", "CR-CT-2-R1"),
    ({"physical_source": "LR-MDB-1", "physical_source_slot": "2"}, "LR-MDB-1 slot 2",
     "back to LR-MDB-1", "LR-MDB-1"),
    ({"physical_source": "LR-MDB-1", "physical_source_slot": ""}, "LR-MDB-1",
     "back to LR-MDB-1", "LR-MDB-1"),
    # A stale head-to-head trail: the eject won't go back to a toolhead.
    ({"physical_source": "XL-2", "physical_source_slot": ""}, None, "to Room LR", "LR"),
], ids=["no-trail", "from-a-cart-row", "from-another-slot", "box-with-a-blank-slot", "stale-toolhead-trail"])
def test_any_other_trail_or_none_asks_first(extra, came_from, goes, goes_to):
    """Only this very box AND slot is the slot's own spool. Anything else, or no
    trail at all (FCC can't tell where it is fed from), asks: a wrong silent
    unload costs more than one tap. "From" and "sends … to" say exactly what
    Smart Load's eject does: a spool with no usable home goes to the Room the
    printer sits in."""
    sm = _sm(extra)
    res, _ = _move(sm)
    assert res.get("confirm_type") == "head_fed", res
    assert sm.writes == []
    resident = res["fed_heads"][0]["resident"]
    assert resident["goes_to"] == goes_to, resident
    running = f"#99 (from {came_from})" if came_from else "#99 (FCC doesn't know where it came from)"
    assert res["msg"] == (f"LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running {running}. "
                          f"Loading #42 sends #99 {goes}."), res["msg"]


def test_printing_and_fed_is_one_question_and_the_load_needs_both_answers():
    sm = _sm(FROM_POLYDRYER)
    printing = _probe_for({"XL"})
    res, store = _move(sm, probe=printing)
    assert res.get("confirm_type") == "head_fed", res
    assert [(a["toolhead"], a["role"]) for a in res["active_prints"]] == [("XL-1", "feeds")], res
    assert res["active_print"]["printer_name"] == "XL", res
    assert res["msg"] == ("XL is PRINTING. LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #99 "
                          "(from PM-DB-2). Loading #42 sends #99 back to PM-DB-2, so FCC stops "
                          "charging this print to #99."), res["msg"]
    key = res["fed_heads"][0]["confirm_key"]

    only_fed, _ = _move(sm, store=store, probe=printing, confirmed_fed_heads=[key])
    assert only_fed.get("confirm_type") == "active_print" and only_fed["can_store"] is True, only_fed
    assert only_fed["title"] == "Load #42 onto XL-1?", only_fed
    assert not only_fed["body"].endswith("Continue?") and only_fed["msg"].endswith("Continue?"), only_fed
    only_print, _ = _move(sm, store=store, probe=printing, confirm_active_print=["XL-1"])
    assert only_print.get("confirm_type") == "head_fed" and only_print["active_prints"] == [], only_print
    assert sm.writes == []

    both, _ = _move(sm, store=store, probe=printing, confirm_active_print=["XL-1"],
                    confirmed_fed_heads=[key])
    assert both.get("auto_deployed_to") == "XL-1", both
    assert sm.direct_at("XL-1") == [42]


def test_a_spool_leaving_a_head_on_the_same_printing_xl_is_one_question():
    """#42 leaves the printing XL-3 for slot 1, whose XL-1 runs a PolyDryer spool.
    One question names both heads; #42 keeps feeding the same XL print through
    XL-1, so its sentence doesn't claim FCC stops charging it (39's engine-1),
    and "XL is PRINTING." is said once."""
    sm = _sm(FROM_POLYDRYER)
    sm.spools[42] = {"location": "XL-3", "extra": {}}
    res, _ = _move(sm, probe=_probe_for({"XL"}))
    assert res.get("confirm_type") == "head_fed", res
    assert sorted((a["toolhead"], a["role"]) for a in res["active_prints"]) == [
        ("XL-1", "feeds"), ("XL-3", "source")], res
    assert res["msg"] == ("XL is PRINTING. LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #99 "
                          "(from PM-DB-2). Loading #42 sends #99 back to PM-DB-2, so FCC stops "
                          "charging this print to #99. #42 is loaded on XL-3."), res["msg"]
    assert sm.writes == []


def test_a_doubled_head_names_every_spool_the_load_unloads():
    sm = _sm(FROM_POLYDRYER, more={7: {"location": "XL-1", "extra": {}}})
    res, _ = _move(sm)
    fed = res["fed_heads"][0]
    assert [r["id"] for r in fed["residents"]] == [7, 99] and fed["confirm_key"] == "XL-1#7,99", fed
    assert res["msg"] == ("LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #7 (FCC doesn't know where "
                          "it came from) and #99 (from PM-DB-2). Loading #42 sends #7 to Room LR and "
                          "#99 back to PM-DB-2."), res["msg"]


def test_a_slot_rebound_between_question_and_answer_is_asked_again():
    """The Yes covered XL-1. Slot 1 now feeds XL-2, which runs #77 from PM-DB-3:
    the replay is asked about XL-2, and nothing moves."""
    sm = _sm(FROM_POLYDRYER, more={77: {"location": "XL-2", "extra": {
        "physical_source": "PM-DB-3", "physical_source_slot": "1"}}})
    first, store = _move(sm)
    assert first["fed_heads"][0]["toolhead"] == "XL-1", first
    store.row("LR-MDB-1")["extra"]["slot_targets"]["1"] = "XL-2"
    again, _ = _move(sm, store=store, confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]])
    assert again.get("confirm_type") == "head_fed", again
    assert [f["toolhead"] for f in again["fed_heads"]] == ["XL-2"], again
    assert again["title"] == "Load #42 onto XL-2?"
    assert sm.writes == []


# ---- failing closed ------------------------------------------------------------------

def test_a_head_spoolman_cant_list_refuses_before_writing():
    sm = _sm(FROM_POLYDRYER)
    sm.list_reads_fail = True
    res, _ = _move(sm)
    assert res.get("status") == "error", res
    assert "couldn't read XL-1 from Spoolman" in res["msg"], res
    assert "42" in res["failures"] and sm.writes == []
    assert _logs("couldn't read XL-1", types={"ERROR"}), state.RECENT_LOGS


@pytest.mark.parametrize("why", ["timeout", "error-body"])
def test_a_resident_whose_record_cant_be_read_refuses_before_writing(why):
    """A timeout reads as None; Spoolman's error body is a truthy dict with no id
    (get_spool returns it as is), which is no record either."""
    sm = _sm(FROM_POLYDRYER)
    if why == "timeout":
        sm.unreadable = {99}
    else:
        real = sm.get_spool
        sm.get_spool = lambda sid: {"message": "Item not found"} if int(sid) == 99 else real(sid)
    res, _ = _move(sm)
    assert res.get("status") == "error" and "couldn't read #99 on XL-1" in res["msg"], res
    assert sm.writes == []


# ---- the chained deploy's guard --------------------------------------------------------

def _loads_during_the_probe(sm, sid, extra):
    """A probe stub that puts `sid` on XL-1 while FCC asks the XL for its state."""
    def probe(url, name):
        sm.spools[sid] = {"location": "XL-1", "extra": dict(extra)}
        return IDLE(url, name)
    return probe


def test_a_spool_loaded_during_the_printer_check_is_not_unloaded_unasked():
    """XL-1 is empty when the move looks. While FCC asks the XL for its state,
    #7 is loaded onto XL-1 from PM-DB-3. The chain must not unload #7 without the
    question: #42 stays stored in slot 1 and the move says why, and how to load it."""
    sm = _sm(more={7: {"location": "PM-DB-3", "extra": {"container_slot": "1"}}})
    probe = _loads_during_the_probe(sm, 7, {"physical_source": "PM-DB-3", "physical_source_slot": "1",
                                            "container_slot": ""})
    res, _ = _move(sm, probe=probe)
    assert res.get("status") == "success" and "auto_deployed_to" not in res, res
    assert sm.spools[42]["location"] == "LR-MDB-1" and sm.spools[42]["extra"]["container_slot"] == "1"
    assert sm.direct_at("XL-1") == [7], sm.writes
    why = (res.get("auto_deploy_skipped") or {}).get("42", "")
    assert why == ("XL-1 started running #7 (from PM-DB-3) while FCC was checking the printer, so #42 "
                   "stayed in LR-MDB-1 slot 1 and was not loaded. To load it, use XL-1's Quick-Swap "
                   "(LR-MDB-1 slot 1)"), res
    assert res.get("auto_deploy_target") == "XL-1", res
    assert not _logs("Auto-deployed"), state.RECENT_LOGS
    assert _logs("NOT deployed", types={"WARNING"}), state.RECENT_LOGS


def test_a_spare_whose_trail_is_this_slot_is_still_a_newcomer():
    """The design review's orange: during the probe a spare #200 is scanned onto
    XL-1, and 40.0d records LR-MDB-1 slot 1 (then XL-1's only free feed) as where
    it came from. Its trail is this very slot, yet nobody was asked about it:
    the guard keys on what the user was shown, not on trails."""
    sm = _sm(more={200: {"location": "", "extra": {}}})
    probe = _loads_during_the_probe(sm, 200, {"physical_source": "LR-MDB-1", "physical_source_slot": "1",
                                              "container_slot": ""})
    res, _ = _move(sm, probe=probe)
    assert "auto_deployed_to" not in res, res
    assert sm.direct_at("XL-1") == [200] and sm.spools[42]["location"] == "LR-MDB-1", sm.writes
    assert "XL-1 started running #200" in (res.get("auto_deploy_skipped") or {}).get("42", ""), res


def test_the_guard_lets_a_head_covered_whatever_it_runs_through():
    """An internal caller's bare head id covers XL-1 whatever it runs."""
    sm = _sm(more={7: {"location": "PM-DB-3", "extra": {"container_slot": "1"}}})
    probe = _loads_during_the_probe(sm, 7, {"physical_source": "PM-DB-3", "physical_source_slot": "1",
                                            "container_slot": ""})
    res, _ = _move(sm, probe=probe, confirmed_fed_heads=["XL-1"])
    assert res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42] and sm.spools[7]["location"] == "PM-DB-3", sm.writes


def test_a_confirmed_key_does_not_let_a_newcomer_through():
    """The user confirmed loading over #99 (its key). During the replay's probe
    #7 joins it on XL-1: the Yes never named #7, so #42 stays stored."""
    sm = _sm(FROM_POLYDRYER, more={7: {"location": "PM-DB-3", "extra": {"container_slot": "1"}}})
    probe = _loads_during_the_probe(sm, 7, {"physical_source": "PM-DB-3", "physical_source_slot": "1",
                                            "container_slot": ""})
    res, _ = _move(sm, probe=probe, confirmed_fed_heads=["XL-1#99"])
    assert "auto_deployed_to" not in res, res
    assert sorted(sm.direct_at("XL-1")) == [7, 99] and sm.spools[42]["location"] == "LR-MDB-1", sm.writes


# ---- "Just store it" is offered only where it differs from a load ----------------------

def test_can_store_marks_a_bound_slots_printing_question():
    sm = _sm()
    res, _ = _move(sm, probe=_probe_for({"XL"}))
    assert res.get("confirm_type") == "active_print" and res["can_store"] is True, res
    assert res["title"] == "Load #42 onto XL-1?" and res["spools"] == [42], res
    # XL-1 is empty, so nothing is "unloaded" (Group 40 review).
    assert res["body"] == "XL is PRINTING. LR-MDB-1 slot 1 feeds XL-1, so this also loads #42 onto XL-1.", res


def test_can_store_is_false_for_a_head_target():
    sm = _sm()
    res = run_move(sm, probe=_probe_for({"XL"}), store=LocationsStore(ROWS), printer_map=PRINTER_MAP,
                   target="XL-1", raw_spools=[42], origin="test")
    assert res.get("confirm_type") == "active_print" and res["can_store"] is False, res
    assert "title" not in res and "body" not in res, res


def test_can_store_is_false_for_a_pool_slot_the_spool_leaves_a_printing_head_for():
    sm = _sm()
    sm.spools[42] = {"location": "XL-3", "extra": {}}
    res, _ = _move(sm, probe=_probe_for({"XL"}), slot="4")
    assert res.get("confirm_type") == "active_print", res
    assert [(a["toolhead"], a["role"]) for a in res["active_prints"]] == [("XL-3", "source")], res
    assert res["can_store"] is False, res


# ---- the doors ------------------------------------------------------------------------

def _door(sm, client, path, body, store=None, probe=IDLE):
    store = store or LocationsStore(ROWS)
    return run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP,
                    call=lambda: client.post(path, json=body)), store


def test_the_slot_scan_relays_the_question(client):
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(FROM_POLYDRYER)
    r, _ = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []})
    body = r.get_json()
    assert body["action"] == "assignment_requires_confirm" and body["confirm_type"] == "head_fed", body
    assert [(f["toolhead"], f["confirm_key"]) for f in body["fed_heads"]] == [("XL-1", "XL-1#99")], body
    assert body["can_store"] is True and body["title"] == "Load #42 onto XL-1?", body
    assert body["target_slot"] == "1" and body["moved"] == 42 and body["spools"] == [42], body
    assert body["body"] == body["msg"] and "sends #99 back to PM-DB-2" in body["msg"], body
    assert sm.writes == [] and [i["id"] for i in state.GLOBAL_BUFFER] == [42]


def test_the_slot_scans_store_replay_stores_without_deploying(client):
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(FROM_POLYDRYER)
    r, _ = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": [],
        "spool_id": 42, "auto_deploy": False})
    body = r.get_json()
    assert body["action"] == "assignment_done" and not body.get("auto_deployed_to"), body
    assert not body.get("not_deployed"), body
    assert sm.spools[42]["location"] == "LR-MDB-1" and sm.direct_at("XL-1") == [99]
    assert state.GLOBAL_BUFFER == []


def test_the_slot_scans_load_replay_loads(client):
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(FROM_POLYDRYER)
    r, _ = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": ["XL-1#99"],
        "confirmed_toolheads": [], "spool_id": 42})
    body = r.get_json()
    assert body["action"] == "assignment_done" and body.get("auto_deployed_to") == "XL-1", body
    assert sm.direct_at("XL-1") == [42] and sm.spools[99]["location"] == "PM-DB-2"


@pytest.mark.parametrize("path, body", [
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "slot": "1",
                              "spool_id": "ID:42", "origin": "buffer"}),
    ("/api/smart_move", {"location": "LR-MDB-1", "slot": "1", "spools": [42], "origin": "buffer"}),
], ids=["manage_contents", "smart_move"])
def test_the_other_doors_relay_the_question_and_take_both_answers(client, path, body):
    sm = _sm(FROM_POLYDRYER)
    asked, store = _door(sm, client, path, dict(body, confirmed_toolheads=[], confirmed_fed_heads=[]))
    a = asked.get_json()
    assert a.get("confirm_type") == "head_fed" and a["fed_heads"][0]["confirm_key"] == "XL-1#99", a
    assert sm.writes == []

    stored, _ = _door(copy.deepcopy(sm), client, path, dict(body, confirmed_toolheads=[],
                                                             confirmed_fed_heads=[], auto_deploy=False))
    assert stored.get_json().get("status") == "success", stored.get_json()

    loaded, _ = _door(sm, client, path, dict(body, confirmed_toolheads=[], confirmed_fed_heads=["XL-1#99"]),
                      store=store)
    assert loaded.get_json().get("auto_deployed_to") == "XL-1", loaded.get_json()
    assert sm.direct_at("XL-1") == [42]


def _reload(text):
    return "Reload the page" in (text or "")


def test_a_stale_page_slot_scan_is_told_to_reload_instead_of_asked(client):
    """A page from before 40.0c sends no confirmed_fed_heads. It could never
    answer the question (each Yes would get it back), so it is told to reload,
    and told what it would have unloaded."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(FROM_POLYDRYER)
    r, _ = _door(sm, client, "/api/identify_scan", {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode"})
    body = r.get_json()
    assert body["action"] == "assignment_failed" and body.get("stale_page") is True, body
    assert body["msg"] == ("Not moved: XL-1 is running #99, and this request can't ask before loading "
                           "over it. Reload the page (Ctrl+F5) and try again."), body
    assert sm.writes == [] and [i["id"] for i in state.GLOBAL_BUFFER] == [42]
    assert _logs("It would have asked", types={"WARNING"}), state.RECENT_LOGS


@pytest.mark.parametrize("path, body", [
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "slot": "1",
                              "spool_id": "ID:42", "origin": "buffer", "confirmed_toolheads": []}),
    ("/api/smart_move", {"location": "LR-MDB-1", "slot": "1", "spools": [42], "origin": "buffer",
                         "confirmed_toolheads": []}),
], ids=["manage_contents", "smart_move"])
def test_a_stale_page_assign_is_told_to_reload(client, path, body):
    sm = _sm(FROM_POLYDRYER)
    r, _ = _door(sm, client, path, body)
    out = r.get_json()
    assert out.get("status") == "error" and out.get("stale_page") is True and _reload(out["msg"]), out
    assert sm.writes == []


def test_a_stale_page_move_that_needs_no_question_still_goes_ahead(client):
    """The stale-page rule answers only a request that would be asked: an empty
    idle head loads for an old page as it always did."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm()
    r, _ = _door(sm, client, "/api/identify_scan", {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode"})
    body = r.get_json()
    assert body["action"] == "assignment_done" and body.get("auto_deployed_to") == "XL-1", body


def test_door_helpers_read_the_request():
    assert logic.confirmed_fed_heads_from(
        {"confirmed_fed_heads": [" xl-1#99 ", "", None, '"XL-2"', {"toolhead": "XL-3"}]}) == ["XL-1#99"]
    # Only confirm keys count at the door: a bare head id ("XL-2") would cover the
    # head whatever it runs (Group 40 review); it stays an engine keyword.
    assert logic.confirmed_fed_heads_from({"confirmed_fed_heads": "XL-1"}) == []
    assert logic.confirmed_fed_heads_from(None) == []
    for off in (False, "false", "False", 0, "0", "no", "off"):
        assert logic.auto_deploy_requested({"auto_deploy": off}) is False, off
    for on in (None, True, "true", 1, "1", ""):
        assert logic.auto_deploy_requested({"auto_deploy": on}) is True, on
    assert logic.auto_deploy_requested({}) is True and logic.auto_deploy_requested(None) is True
    assert logic._fed_covered(["XL-1#7,99"], "XL-1", [99, 7]) is True
    assert logic._fed_covered(["XL-1#99"], "XL-1", [99, 7]) is False
    assert logic._fed_covered(["XL-1"], "XL-1", [5]) is True and logic._fed_covered(True, "XL-9", [5]) is True


# ---- the Group 40 review's deferred notes, pinned with 40.3 ------------------------------

class _ListedButGone(FakeSpoolman):
    """Spoolman's spool list is a moment behind: its first read of XL-1 still
    shows `listed` there, though their own records already say they left.
    Later reads show where they really are."""

    def __init__(self, spools, listed=()):
        super().__init__(spools)
        self.stale = {int(s) for s in listed}

    def _detailed(self, loc):
        items = super()._detailed(loc)
        if str(loc).upper() == "XL-1" and self.stale:
            have = {i["id"] for i in items}
            items += [{"id": sid, "is_ghost": False, "location": "XL-1", "slot": ""}
                      for sid in sorted(self.stale) if sid not in have]
            self.stale = set()
        return items


def test_a_spool_that_left_and_came_back_during_the_check_is_not_unloaded_unasked():
    """The review's engine:fed-seen-includes-left. XL-1's list still shows #7,
    but #7's own record says it already went back to PM-DB-3, so nothing is
    asked. While FCC checks the printer, #7 is put back on XL-1. It was never
    shown to the user, so the chain must not unload it: "seen" used to count
    every LISTED spool, so #7 counted as seen and went to PM-DB-3 unasked."""
    sm = _ListedButGone({42: {"location": "CR-CT-2-R1", "extra": {}},
                         7: {"location": "PM-DB-3", "extra": {"container_slot": "1"}}}, listed=[7])
    probe = _loads_during_the_probe(sm, 7, {"physical_source": "PM-DB-3", "physical_source_slot": "1",
                                            "container_slot": ""})
    res, _ = _move(sm, probe=probe)
    assert res.get("status") == "success" and "auto_deployed_to" not in res, res
    assert sm.direct_at("XL-1") == [7], sm.writes
    assert sm.spools[42]["location"] == "LR-MDB-1" and sm.spools[42]["extra"]["container_slot"] == "1"
    assert (res.get("auto_deploy_skipped") or {}).get("42", "").startswith(
        "XL-1 started running #7 (from PM-DB-3) while FCC was checking the printer"), res


def test_a_spool_that_left_between_the_two_reads_is_not_named():
    """The review's narrow branch (a): the list shows #7 on XL-1, but its record
    says PM-DB-3, so it left between the two reads. The question would name a
    spool that isn't there; nothing is asked and #42 loads. A control: it pins
    the `continue` that skips such a spool."""
    sm = _ListedButGone({42: {"location": "CR-CT-2-R1", "extra": {}},
                         7: {"location": "PM-DB-3", "extra": {"container_slot": "1"}}}, listed=[7])
    res, _ = _move(sm)
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42] and sm.spools[7]["location"] == "PM-DB-3", sm.writes


def test_a_fed_question_keeps_the_print_consequence_when_the_head_was_already_confirmed():
    """The review's protocol:fed-text-drops-print-consequence. The Quick-Swap
    deposit's first request already confirms XL-1 (its banner said the XL is
    printing), so XL-1 isn't in active_prints. Unloading #99 still stops the
    print being charged to it, and the question must say so."""
    res, _ = _move(_sm(FROM_POLYDRYER), probe=_probe_for({"XL"}), confirm_active_print=["XL-1"])
    assert res.get("confirm_type") == "head_fed" and res["active_prints"] == [], res
    assert res["body"] == ("XL is PRINTING. LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #99 (from "
                           "PM-DB-2). Loading #42 sends #99 back to PM-DB-2, so FCC stops charging this "
                           "print to #99."), res["body"]


@pytest.mark.parametrize("printing", [False, True], ids=["idle", "printing"])
@pytest.mark.parametrize("path, body", [
    ("/api/identify_scan", {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "spool_id": 42}),
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "slot": "1", "spool_id": "ID:42"}),
    ("/api/smart_move", {"location": "LR-MDB-1", "slot": "1", "spools": [42]}),
], ids=["slot_scan", "manage_contents", "smart_move"])
def test_a_pre_39_page_asked_a_fed_question_hears_the_fed_reload(client, path, body, printing):
    """The review's protocol:stale-rule-order-unpinned. A page from before
    Group 39 sends only the bare confirm_active_print flag. Asked a fed
    question, it must hear what the load would unload, idle or printing: the
    doors run stale_fed_refusal BEFORE stale_confirm_refusal, which answers any
    question. A control: it pins that order."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm(FROM_POLYDRYER)
    r, _ = _door(sm, client, path, dict(body, confirm_active_print=True),
                 probe=_probe_for({"XL"}) if printing else IDLE)
    out = r.get_json()
    assert out.get("stale_page") is True, out
    assert out["msg"] == ("Not moved: XL-1 is running #99, and this request can't ask before loading "
                          "over it. Reload the page (Ctrl+F5) and try again."), out
    assert sm.writes == []
