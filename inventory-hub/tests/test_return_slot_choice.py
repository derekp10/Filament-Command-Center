"""Group 40.6 — Return's slot choice (Derek's D5, and his 2026-10-13 answer 6),
its display (item D) and the DEPLOYED card's ↩️ (item E, the server half),
through the Flask client and the REAL move engine over move_engine_harness's
fakes. Nothing here mocks perform_smart_move ([[mocked engine hides chain
bugs]]); the printer probe is patched below the per-move memo.

POST /api/quickswap/return gained three optional fields:
  - dry_run: true -> return_plan (200) and nothing written: the box and the
    exact slot the Return would use (slot null = no slot), or needs_choice with
    the slot picker's model in return mode (`options`) and its ⭐;
  - slot (+ box): the user's choice, a slot number or "none", checked at write
    time against a strict read. A gone or claimed slot is return_slot_taken
    (409) with fresh options, nothing written; a chosen slot goes to the engine
    as picked_slot, so a spool that takes it while FCC checks the printer is
    never unseated; "none" lands unslotted on purpose (the engine's new
    `unslotted` keyword: step 3 would otherwise pick a slot);
  - expected_spool: return_spool_mismatch (409) when the head runs another.
Without slot: the recorded slot while free is one tap; else exactly one free
slot feeding the head, with no single-slot box attached to it, is one tap; else
return_choose_slot (200), nothing written.

HEAD proof (0b0eeb7, the tests copied into a `git archive` extract): every test
here fails there except the engine control noted in its docstring; the reasons
are in the commit message.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import state  # noqa: E402

from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, _probe_for, run_move  # noqa: E402

PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
DEV_FEEDS = {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}   # dev's LR-MDB-1


def _rows(feeds=None, extra=()):
    return [
        {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
        {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
         "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
        *[{"LocationID": f"XL-{n}", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"} for n in (1, 2, 3)],
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
         "extra": {"slot_targets": dict(feeds or DEV_FEEDS)}},
        {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
        *extra,
    ]


def _polydryer(head=None):
    return {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
            "extra": {"slot_targets": {"1": head} if head else {}}}


def _deployed(box, slot):
    return {"physical_source": box, "physical_source_slot": slot, "container_slot": ""}


def _stored(slot):
    return {"location": "LR-MDB-1", "extra": {"container_slot": str(slot)}}


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


def _post(client, sm, body, rows=None, probe=IDLE):
    store = LocationsStore(_rows() if rows is None else rows)
    r = run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP,
                 call=lambda: client.post("/api/quickswap/return", json=body))
    return r.status_code, r.get_json()


def _logs(needle, types=None):
    return [str(e.get("msg")) for e in state.RECENT_LOGS
            if needle in str(e.get("msg", "")) and (types is None or e.get("type") in types)]


def _slot(model, n):
    return next(s for s in model["slots"] if s["slot"] == str(n))


def _at(sm, sid):
    rec = sm.spools[sid]
    return rec["location"], str((rec.get("extra") or {}).get("container_slot") or "")


# ---- the dry run names the exact slot ---------------------------------------------------------

def test_a_dry_run_names_the_free_recorded_slot_and_writes_nothing(client):
    """Item D: the confirm can name the slot the Return will use."""
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}})
    status, body = _post(client, sm, {"toolhead": "XL-3", "dry_run": True})
    assert status == 200 and body["action"] == "return_plan", body
    assert (body["box"], body["slot"], body["source"], body["needs_choice"]) == (
        "LR-MDB-1", "3", "physical_source", False), body
    assert body["spool"] == 77 and body["display"] == "#77" and body["options"] is None, body
    assert body["occupancy"] == {"after": 1, "max": 4}, body
    assert (body["toolhead"], body["active_toolhead"], body["requested"]) == ("XL-3", "XL-3", "XL-3")
    assert sm.writes == [] and _at(sm, 77) == ("XL-3", ""), sm.writes


def test_the_free_recorded_slot_is_still_one_tap_and_the_log_names_it(client):
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}})
    status, body = _post(client, sm, {"toolhead": "XL-3"})
    assert status == 200 and body["action"] == "return_done", body
    assert (body["box"], body["slot"], body["source"]) == ("LR-MDB-1", "3", "physical_source"), body
    assert _at(sm, 77) == ("LR-MDB-1", "3") and sm.direct_at("XL-3") == []
    assert _logs("↩️ Return: Spool #77 from <b>XL-3</b> → <b>LR-MDB-1 slot 3</b> (original source)",
                 types={"SUCCESS"}), state.RECENT_LOGS


# ---- no usable recorded slot: one tap when obvious, the chooser otherwise ----------------------

def test_a_taken_recorded_slot_asks_on_its_box_and_stars_the_heads_free_slot(client):
    """D5: slot 1 (where #77 came from) holds #57, and two free slots feed XL-3,
    so nothing is obvious: no write, the chooser on LR-MDB-1, ⭐ slot 2."""
    rows = _rows({"1": "XL-3", "2": "XL-3", "3": "XL-3", "4": "PRINTER:XL"})
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "1")}, 57: _stored(1)})
    for dry in (True, False):
        status, body = _post(client, sm, {"toolhead": "XL-3", "dry_run": dry}, rows=rows)
        assert status == 200 and body["action"] == ("return_plan" if dry else "return_choose_slot"), body
        assert body["needs_choice"] is True and body["box"] == "LR-MDB-1" and body["slot"] is None, body
        assert body["recommended"] == {"kind": "slot", "box": "LR-MDB-1", "slot": "2"}, body
        assert body["options"]["mode"] == "return" and body["options"]["location"] == "LR-MDB-1", body
        assert _slot(body["options"], 1)["blocked"] == "Holds #57: Return takes a free slot, or No slot"
        assert "LR-MDB-1 slot 1, where it came from, holds #57" in body["note"], body
        assert "2 free slots feed XL-3" in body["note"], body
    assert sm.writes == [] and _at(sm, 57) == ("LR-MDB-1", "1") and _at(sm, 77) == ("XL-3", "")


def test_a_taken_recorded_slot_with_no_free_head_slot_stars_the_printer_pool(client):
    """D5's second choice: no free slot feeds XL-3, so the ⭐ is the free Printer
    Pool slot of XL's printer (dev's LR-MDB-1 slot 4)."""
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}, 57: _stored(3)})
    status, body = _post(client, sm, {"toolhead": "XL-3"})
    assert status == 200 and body["action"] == "return_choose_slot", body
    assert body["recommended"] == {"kind": "slot", "box": "LR-MDB-1", "slot": "4"}, body
    assert "no free slot feeds XL-3" in body["note"], body
    assert sm.writes == []


def test_one_free_slot_feeding_the_head_is_one_tap_for_a_spool_with_no_trail(client):
    """Derek's answer 6 (2026-10-13): one tap when the answer is obvious, and the
    confirm still names it."""
    sm = FakeSpoolman({42: {"location": "XL-2", "extra": {}}})
    status, plan = _post(client, sm, {"toolhead": "XL-2", "dry_run": True})
    assert status == 200 and plan["action"] == "return_plan" and plan["needs_choice"] is False, plan
    assert (plan["box"], plan["slot"], plan["source"]) == ("LR-MDB-1", "2", "feed_slot"), plan
    assert plan["note"] == "#42 has no recorded slot; LR-MDB-1 slot 2 is the only free slot that feeds XL-2"
    status, body = _post(client, sm, {"toolhead": "XL-2", "box": "LR-MDB-1", "slot": "2", "expected_spool": 42})
    assert status == 200 and body["action"] == "return_done", body
    assert (body["slot"], body["source"]) == ("2", "feed_slot"), body
    assert _at(sm, 42) == ("LR-MDB-1", "2") and sm.direct_at("XL-2") == []
    assert _logs("(the only free slot that feeds XL-2)", types={"SUCCESS"}), state.RECENT_LOGS


def test_an_attached_polydryer_makes_the_one_free_slot_a_choice(client):
    """Derek's builder note: a single-slot box attached to the head is a second
    feed, so a spool with no trail there gets the chooser, never a silent guess."""
    rows = _rows(extra=[_polydryer(head="XL-2")])
    sm = FakeSpoolman({42: {"location": "XL-2", "extra": {}}})
    status, body = _post(client, sm, {"toolhead": "XL-2"}, rows=rows)
    assert status == 200 and body["action"] == "return_choose_slot", body
    assert body["recommended"] == {"kind": "slot", "box": "LR-MDB-1", "slot": "2"}, body
    assert "PM-DB-2 is attached to XL-2 too" in body["note"], body
    assert sm.writes == []


def test_a_polydryer_spool_goes_back_to_its_polydryer(client):
    """The builder note's other half: its trail names the box, so that is where
    it goes, slot 1, one tap."""
    rows = _rows(extra=[_polydryer(head="XL-2")])
    sm = FakeSpoolman({50: {"location": "XL-2", "extra": _deployed("PM-DB-2", "1")}})
    status, plan = _post(client, sm, {"toolhead": "XL-2", "dry_run": True}, rows=rows)
    assert plan["action"] == "return_plan" and (plan["box"], plan["slot"], plan["needs_choice"]) == (
        "PM-DB-2", "1", False), plan
    status, body = _post(client, sm, {"toolhead": "XL-2", "box": "PM-DB-2", "slot": "1",
                                      "expected_spool": 50}, rows=rows)
    assert status == 200 and body["action"] == "return_done" and body["slot"] == "1", body
    assert _at(sm, 50) == ("PM-DB-2", "1")


def test_a_taken_polydryer_is_named_as_no_slot_before_and_after(client):
    rows = _rows(extra=[_polydryer(head="XL-2")])
    sm = FakeSpoolman({18: {"location": "PM-DB-2", "extra": {"container_slot": "1"}},
                       50: {"location": "XL-2", "extra": _deployed("PM-DB-2", "1")}})
    status, plan = _post(client, sm, {"toolhead": "XL-2", "dry_run": True}, rows=rows)
    assert plan["action"] == "return_plan" and plan["box"] == "PM-DB-2" and plan["slot"] is None, plan
    assert plan["note"] == "PM-DB-2 slot 1 holds #18, so #50 goes in without a slot", plan
    assert plan["occupancy"] == {"after": 2, "max": 1}, plan
    status, body = _post(client, sm, {"toolhead": "XL-2", "box": "PM-DB-2", "slot": "none",
                                      "expected_spool": 50}, rows=rows)
    assert status == 200 and body["action"] == "return_done" and body["slot"] is None, body
    assert _at(sm, 18) == ("PM-DB-2", "1") and _at(sm, 50) == ("PM-DB-2", "")
    assert _logs("⚠️ Return: PM-DB-2 slot 1 already holds #18 — #50 goes back into PM-DB-2 unslotted"), \
        state.RECENT_LOGS
    assert _logs("↩️ Return: Spool #50 from <b>XL-2</b> → <b>PM-DB-2</b> (no slot)"), state.RECENT_LOGS


def test_a_full_box_recommends_no_slot(client):
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")},
                       51: _stored(1), 52: _stored(2), 57: _stored(3), 54: _stored(4)})
    status, body = _post(client, sm, {"toolhead": "XL-3", "dry_run": True})
    assert status == 200 and body["needs_choice"] is True, body
    assert body["recommended"] == {"kind": "none", "box": "LR-MDB-1"}, body
    assert all(s["blocked"] for s in body["options"]["slots"]), body["options"]["slots"]
    assert body["occupancy"] == {"after": 5, "max": 4}, body
    assert sm.writes == []


# ---- the user's choice, checked at write time ---------------------------------------------------

def test_no_slot_lands_unslotted_and_never_prints_null(client):
    """The No slot tile. Slots 1, 2 and 4 are free: without the engine's new
    `unslotted` keyword, step 3 would put #77 in slot 1. No `box`: the chosen
    slot is in the box the chooser showed."""
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}, 57: _stored(3)})
    status, body = _post(client, sm, {"toolhead": "XL-3", "slot": "none", "expected_spool": 77})
    assert status == 200 and body["action"] == "return_done", body
    assert body["box"] == "LR-MDB-1" and body["slot"] is None and body["source"] == "chosen", body
    assert _at(sm, 77) == ("LR-MDB-1", "") and _at(sm, 57) == ("LR-MDB-1", "3")
    assert _logs("↩️ Return: Spool #77 from <b>XL-3</b> → <b>LR-MDB-1</b> (no slot)",
                 types={"SUCCESS"}), state.RECENT_LOGS
    said = str(body) + " ".join(str(e.get("msg")) for e in state.RECENT_LOGS)
    assert "SLOT:null" not in said and "SLOT:None" not in said and "slot None" not in said, said


def test_a_pick_among_several_head_slots_is_logged_as_chosen(client):
    """The success line says why the slot: "(the only free slot that feeds
    XL-3)" is for the one-tap answer only; a pick among two free XL-3 slots is
    "(chosen)"."""
    rows = _rows({"1": "XL-3", "2": "XL-3", "3": "XL-3", "4": "PRINTER:XL"})
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "1")}, 57: _stored(1)})
    status, body = _post(client, sm, {"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "3", "expected_spool": 77},
                         rows=rows)
    assert status == 200 and body["action"] == "return_done", body
    assert (body["slot"], body["source"]) == ("3", "chosen"), body
    assert _at(sm, 77) == ("LR-MDB-1", "3") and _at(sm, 57) == ("LR-MDB-1", "1")
    assert _logs("→ <b>LR-MDB-1 slot 3</b> (chosen)", types={"SUCCESS"}), state.RECENT_LOGS


def test_a_chosen_slot_another_spool_holds_is_refused_with_fresh_options(client):
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")},
                       57: _stored(3), 58: _stored(2)})
    status, body = _post(client, sm, {"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "2", "expected_spool": 77})
    assert status == 409 and body["action"] == "return_slot_taken", body
    assert body["taken_by"] == [58] and body["slot"] == "2" and body["box"] == "LR-MDB-1", body
    assert "LR-MDB-1 slot 2 holds #58" in body["error"], body
    assert body["options"]["mode"] == "return" and _slot(body["options"], 2)["blocked"], body
    assert body["recommended"] == {"kind": "slot", "box": "LR-MDB-1", "slot": "4"}, body
    assert sm.writes == [] and _at(sm, 58) == ("LR-MDB-1", "2")


def test_a_slot_taken_while_fcc_checks_the_printer_is_never_unseated(client):
    """The chosen slot is free when the request arrives and taken by #58 during
    the printer check. The engine gets it as picked_slot, so #58 is never
    unseated (an Overwrite slot would have cleared #58's slot and left it
    floating in the box): nothing moves, and the user picks again."""
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}})

    def racing_probe(url, printer_name):
        sm.spools[58] = _stored(3)
        return IDLE(url, printer_name)

    status, body = _post(client, sm, {"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "3",
                                      "expected_spool": 77}, probe=racing_probe)
    assert status == 409 and body["action"] == "return_slot_taken", body
    assert body["taken_by"] == [58] and "filled by #58" in body["error"], body
    assert body["options"]["mode"] == "return", body
    assert _at(sm, 58) == ("LR-MDB-1", "3") and _at(sm, 77) == ("XL-3", ""), sm.writes
    assert [w for w in sm.writes if w[0] == 58] == [], sm.writes


def test_a_chosen_slot_off_a_printing_head_asks_first_and_the_replay_keeps_it(client):
    """Group 39.2's source check still asks before a printing head is emptied,
    and the answer names the slot; the confirmed replay puts it there."""
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}, 57: _stored(3)})
    ask = {"toolhead": "XL-3", "box": "LR-MDB-1", "slot": "4", "expected_spool": 77}
    status, body = _post(client, sm, ask, probe=_probe_for({"XL"}))
    assert status == 200 and body["action"] == "return_requires_confirm", body
    assert (body["box"], body["slot"]) == ("LR-MDB-1", "4"), body
    assert [(a["toolhead"], a["role"]) for a in body["active_prints"]] == [("XL-3", "source")], body
    assert sm.writes == []
    status, body = _post(client, sm, dict(ask, confirmed_toolheads=["XL-3"]), probe=_probe_for({"XL"}))
    assert status == 200 and body["action"] == "return_done" and body["slot"] == "4", body
    assert _at(sm, 77) == ("LR-MDB-1", "4")


def test_another_spool_on_the_head_is_refused(client):
    """expected_spool: the page showed #77; the head runs #43 now."""
    sm = FakeSpoolman({43: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}})
    for dry in (True, False):
        status, body = _post(client, sm, {"toolhead": "XL-3", "dry_run": dry, "expected_spool": 77})
        assert status == 409 and body["action"] == "return_spool_mismatch", body
        assert body["spool"] == 43 and body["expected_spool"] == 77, body
        assert body["error"].startswith("XL-3 holds #43 now, not #77, so nothing was moved"), body
    assert sm.writes == []


@pytest.mark.parametrize("case", ["return_plan", "return_choose_slot", "return_slot_taken", "return_spool_mismatch"])
def test_every_new_action_carries_the_29_b3_keys(client, case):
    """Asked on the printer (XL), acted on its loaded head (XL-3)."""
    spools = {77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}}
    body = {"toolhead": "XL"}
    if case == "return_plan":
        body["dry_run"] = True
    elif case == "return_choose_slot":
        spools[57] = _stored(3)
    elif case == "return_slot_taken":
        spools[58] = _stored(2)
        body.update(box="LR-MDB-1", slot="2")
    else:
        body["expected_spool"] = 99
    sm = FakeSpoolman(spools)
    _status, answer = _post(client, sm, body)
    assert answer["action"] == case, answer
    assert (answer["toolhead"], answer["requested"], answer["active_toolhead"]) == ("XL", "XL", "XL-3"), answer
    assert sm.writes == []


def test_an_unreadable_box_is_refused_before_anything_moves(client):
    """Strict reads: a Spoolman blip on the box is not an empty box."""
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}})
    sm.fail_list_reads = {1}   # 0: the head's residents; 1: the box
    status, body = _post(client, sm, {"toolhead": "XL-3"})
    assert status == 409 and body["action"] == "return_failed", body
    assert "couldn't read LR-MDB-1 from Spoolman" in body["error"], body
    assert sm.writes == [] and _at(sm, 77) == ("XL-3", "")


@pytest.mark.parametrize("slot", ["abc", "0", "-1"])
def test_a_slot_that_is_not_a_slot_is_a_bad_request(client, slot):
    sm = FakeSpoolman({77: {"location": "XL-3", "extra": _deployed("LR-MDB-1", "3")}})
    status, body = _post(client, sm, {"toolhead": "XL-3", "slot": slot})
    assert status == 400 and body["action"] == "return_bad_request", body
    assert sm.writes == []


# ---- item E: the DEPLOYED card's ↩️ is the canonical Return ---------------------------------------

def test_the_deployed_cards_return_names_its_spool_and_leaves_the_head_empty(client):
    """Manual check R3: the card's spool comes back into its slot and stays OFF
    the head (the card used to post the slot with the auto-deploy chain on)."""
    sm = FakeSpoolman({42: {"location": "XL-1", "extra": _deployed("LR-MDB-1", "1")}})
    status, plan = _post(client, sm, {"toolhead": "XL-1", "dry_run": True, "expected_spool": 42})
    assert plan["action"] == "return_plan" and (plan["box"], plan["slot"]) == ("LR-MDB-1", "1"), plan
    status, body = _post(client, sm, {"toolhead": "XL-1", "box": "LR-MDB-1", "slot": "1", "expected_spool": 42})
    assert status == 200 and body["action"] == "return_done", body
    assert _at(sm, 42) == ("LR-MDB-1", "1") and sm.direct_at("XL-1") == [], sm.writes
    assert not _logs("Auto-deployed"), state.RECENT_LOGS


# ---- the engine keyword ------------------------------------------------------------------------

@pytest.mark.parametrize("unslotted, landed", [(True, ""), (False, "1")], ids=["unslotted", "control"])
def test_the_unslotted_keyword_skips_the_slot_pick(unslotted, landed):
    """`unslotted=True` puts a slotless spool in a multi-slot box with no slot;
    without it step 3 picks the lowest free slot. HEAD: the keyword doesn't
    exist (a TypeError, signature only); the control passes there."""
    sm = FakeSpoolman({77: {"location": "CR-CT-2-R1", "extra": {}}})
    kwargs = {"unslotted": True} if unslotted else {}
    result = run_move(sm, probe=IDLE, store=LocationsStore(_rows()), printer_map=PRINTER_MAP,
                      target="LR-MDB-1", raw_spools=[77], auto_deploy=False, origin="test", **kwargs)
    assert logic.smart_move_failure(result, 77) == "", result
    assert _at(sm, 77) == ("LR-MDB-1", landed), sm.spools[77]
