"""Group 40.3 review (wf_ca12a7f0-f09) — the engine fixes, pinned.

- A1 (orange): a slot whose own spool runs on ANOTHER head (the slot was
  re-pointed after that spool was loaded) took a new spool on a load or a blind
  scan, so two spools claimed one slot. Now refused, nothing written, naming
  the spool and where it runs.
- A3: that refusal offers "load the new spool instead" only where a load swaps
  the slot's own spool out; a binding to something that isn't a head names it.
- A2: a hand-edited "None" / "null" binding reads as unbound in `feed` as in
  `expected_feed`, so a replay converges instead of re-asking forever.
- C5: a print on the head the spool only LEAVES keeps the yes / no; the
  three-way (Enter stores) is for a load onto a head that is itself mid-print.
- C4: every question says whether it is a printing one (`printing`), the way
  its body does, so the dialog is drawn in the printing style.
- C1 / B5 (orange): toolheads the page saw printing (`seen_printing`, sent by
  the Quick-Swap deposit) count as printing whenever the move's own probe
  can't reach their printer, so a fail-open probe never loads mid-print
  unasked.
The REAL engine runs over tests/move_engine_harness.py with a live locations store.
The fix check (wf_0dddaf03-9a6) pins, at the end: a stale trail (a spool on no
head whose record still names the slot) never blocks a load (E1/S1, a
regression in f055def) and a store over one says what it is; `leaving`;
`printing` for a re-point back to a confirmed printing head; a seen_printing
that can't be read; seen_printing forgotten outside the move. Run on f055def:
the stale-trail loads fail (behavioural: refused), the store texts, the A1
wording ("while the slot feeds"), `leaving` (KeyError) and the depth leak fail;
the `printing` and forgetting pins pass there (controls for gaps the check
named).
HEAD proof of the first set (run on c1c2c38: 17 of 21 fail; corrected by the
fix check, S3, from "21 of 25"): A1's blind-scan load and the
printing question's Yes load #42 onto XL-1 there (behavioural), and its store
is refused with the old advice (text); the two A3 texts differ (text); the
"None" / "null" question names the feed "NONE", which no replay can match
(behavioural: the loop's first round); C5 offers the store on a source-only
print (behavioural); `printing` is missing (KeyError, an answer-shape red); the
three `seen_printing` engine tests fail on the keyword (signature only, the
definite-IDLE one included), the parse table on the missing helper, and the
door test loads XL-1 mid-print unasked (behavioural). The 4 that pass there are
controls by design: the same-slot swap, the store over the head's own spool
(its text is unchanged), the three-way on a head that is itself mid-print, and
a failing probe without `seen_printing` that still fails open.
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
from test_expected_feed_40_3 import PRINTER_MAP_F, ROWS_F  # noqa: E402
from test_fed_head_confirm_40_0c import FROM_POLYDRYER  # noqa: E402

# GHOST-MDB's slot 1 is bound to XL-9, which doesn't exist; CR-MDB-1 feeds nothing;
# NN-MDB-1 / NL-MDB-1 carry hand-edited "None" / "null" bindings.
ROWS_R = ROWS_F + [
    {"LocationID": "GHOST-MDB", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-9"}}},
    {"LocationID": "CR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {}}},
    {"LocationID": "NN-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "None"}}},
    {"LocationID": "NL-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "null"}}},
]


def _trail(box, slot):
    return {"physical_source": box, "physical_source_slot": str(slot), "container_slot": ""}


def _probe_fails(_url, _name):
    """PrusaLink unreachable: the probe answers None (fail open)."""
    return None


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


def _sm(spools):
    return FakeSpoolman({k: copy.deepcopy(v) for k, v in spools.items()})


def _move(sm, store=None, probe=IDLE, slot="1", target="LR-MDB-1", spools=(42,), **kw):
    store = store or LocationsStore(ROWS_R)
    res = run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP_F,
                   target=target, raw_spools=list(spools), target_slot=slot, origin="test", **kw)
    return res, store


def _slot_of(sm, sid):
    return str((sm.spools[sid].get("extra") or {}).get("container_slot") or "").strip('"')


# ---- A1: a slot whose own spool runs on another head -------------------------------------------

def _other_head():
    """LR-MDB-1 slot 1 feeds XL-1 (empty). Its own spool #60 was loaded while
    slot 1 fed XL-3 and still runs there (trail LR-MDB-1:1)."""
    return _sm({42: {"location": "CR-CT-2-R1", "extra": {}},
                60: {"location": "XL-3", "extra": _trail("LR-MDB-1", 1)}})


@pytest.mark.parametrize("auto_deploy, why", [
    (True, "LR-MDB-1 slot 1 still holds #60, loaded on XL-3, while the slot feeds XL-1: take #60 off XL-3 "
           "first, so nothing moved"),
    (False, "LR-MDB-1 slot 1 still holds #60, loaded on XL-3: take it off first, so nothing moved"),
], ids=["blind-scan-load", "store"])
def test_a_slot_whose_own_spool_runs_on_another_head_takes_no_new_spool(auto_deploy, why):
    sm = _other_head()
    res, _ = _move(sm, auto_deploy=auto_deploy)
    assert logic.smart_move_failure(res, 42) == why, res
    assert res.get("blocked_reason") == "slot_claimed", res   # Group 51.3 (step 6's refusal)
    assert sm.writes == [], sm.writes
    assert sm.spools[42]["location"] == "CR-CT-2-R1" and sm.direct_at("XL-3") == [60]
    assert "auto_deployed_to" not in res, res


def test_a_printing_xl_refuses_it_before_asking_anything():
    """XL printing. It used to ask the printing question first and then refuse
    its Yes (and its "Just store it") at the slot read. Group 40.5 (the 40.3
    "Open, narrow" note): the slot is read before any question, so the refusal
    comes first: no question whose every answer is refused, nothing written. A
    replay that confirmed XL-1 meets the same refusal."""
    sm = _other_head()
    probe = _probe_for({"XL"})
    res, store = _move(sm, probe=probe)
    assert res.get("status") == "error", res
    assert "still holds #60, loaded on XL-3, while the slot feeds XL-1" in logic.smart_move_failure(res, 42), res
    again, _ = _move(sm, store=store, probe=probe, confirm_active_print=["XL-1"], expected_feed="XL-1")
    assert "still holds #60, loaded on XL-3, while the slot feeds XL-1" in logic.smart_move_failure(again, 42), again
    assert sm.writes == []


def test_the_same_slot_swap_still_needs_no_question():
    """A control: the slot's own spool on the head the slot feeds is Derek's
    same-slot swap; the chain swaps it out."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}},
              60: {"location": "XL-1", "extra": _trail("LR-MDB-1", 1)}})
    res, _ = _move(sm)
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42]


# ---- A3: the refusal names what can be done ----------------------------------------------------

@pytest.mark.parametrize("target, extra, auto_deploy, why", [
    ("LR-MDB-1", {60: {"location": "XL-1", "extra": _trail("LR-MDB-1", 1)}}, False,
     "LR-MDB-1 slot 1 still holds #60, loaded on XL-1: take it off first, or load the new spool instead, "
     "so nothing moved"),
    ("CR-MDB-1", {60: {"location": "XL-1", "extra": _trail("CR-MDB-1", 1)}}, True,
     "CR-MDB-1 slot 1 still holds #60, loaded on XL-1: take it off first, so nothing moved"),
    ("GHOST-MDB", {60: {"location": "XL-1", "extra": _trail("GHOST-MDB", 1)}}, True,
     "GHOST-MDB slot 1 still holds #60, loaded on XL-1, and the slot is bound to XL-9, which isn't a "
     "toolhead: take #60 off XL-1 first, and fix the binding in GHOST-MDB's 🔗 Slot → Toolhead Feeds, "
     "so nothing moved"),
], ids=["store-over-the-heads-own-spool", "unbound-slot", "non-head-binding"])
def test_the_ghost_refusal_offers_a_load_only_where_one_swaps_it_out(target, extra, auto_deploy, why):
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}, **extra})
    res, _ = _move(sm, target=target, auto_deploy=auto_deploy)
    assert logic.smart_move_failure(res, 42) == why, res
    assert res.get("blocked_reason") == "slot_claimed", res   # Group 51.3
    assert sm.writes == []


# ---- A2: "None" / "null" bindings ---------------------------------------------------------------

@pytest.mark.parametrize("box", ["NN-MDB-1", "NL-MDB-1"], ids=["None", "null"])
def test_a_none_or_null_binding_is_unbound_and_its_replay_converges(box):
    """#42 leaves the printing RC-1 for slot 1, bound to the string "None" (or
    "null"). The question names no feed, and its replay stores #42: the feed
    used to read "NONE" while the replay's "" never matched, so every Yes was
    asked again."""
    sm = _sm({42: {"location": "RC-1", "extra": {}}})
    probe = _probe_for({"RC"})
    first, store = _move(sm, target=box, probe=probe)
    assert first.get("confirm_type") == "active_print" and first["feed"] == "", first
    done, _ = _move(sm, target=box, store=store, probe=probe, confirm_active_print=["RC-1"],
                    expected_feed=first["feed"])
    assert done.get("status") == "success" and "auto_deployed_to" not in done, done
    assert sm.spools[42]["location"] == box and _slot_of(sm, 42) == "1"


# ---- C5: a print on the head the spool leaves -----------------------------------------------------

def test_a_print_only_on_the_head_the_spool_leaves_keeps_the_yes_no():
    """RC prints, the XL is idle: the question is about leaving RC-1, and XL-1
    can be loaded, so there is no three-way and Enter can't quietly store."""
    sm = _sm({42: {"location": "RC-1", "extra": {}}})
    res, _ = _move(sm, probe=_probe_for({"RC"}))
    assert res.get("confirm_type") == "active_print", res
    assert [(a["toolhead"], a["role"]) for a in res["active_prints"]] == [("RC-1", "source")], res
    assert res["can_store"] is False and "title" not in res and "body" not in res, res
    assert res["printing"] is True


def test_a_print_on_the_head_the_slot_loads_keeps_the_three_way():
    """A control: the XL prints, so loading XL-1 is mid-print: the three-way."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res, _ = _move(sm, probe=_probe_for({"XL"}))
    assert res["can_store"] is True and res["title"] == "Load #42 onto XL-1?", res


# ---- C4: the question says whether it is a printing one -------------------------------------------

def test_every_question_says_whether_it_is_a_printing_one():
    idle_fed, _ = _move(_sm({42: {"location": "CR-CT-2-R1", "extra": {}},
                             99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}}))
    assert idle_fed.get("confirm_type") == "head_fed" and idle_fed["printing"] is False, idle_fed
    covered, _ = _move(_sm({42: {"location": "CR-CT-2-R1", "extra": {}},
                            99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}}),
                       probe=_probe_for({"XL"}), confirm_active_print=["XL-1"])
    assert covered.get("confirm_type") == "head_fed" and covered["active_prints"] == [], covered
    assert covered["printing"] is True, "its body says XL is PRINTING, so the dialog must say so too"
    store = LocationsStore(ROWS_R)
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}, 99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    first, store = _move(sm, store=store)
    store.row("LR-MDB-1")["extra"]["slot_targets"]["1"] = "XL-2"
    moved, _ = _move(sm, store=store, probe=_probe_for({"XL"}), confirmed_fed_heads=["XL-1#99"],
                     expected_feed="XL-1")
    assert moved.get("confirm_type") == "feed_changed" and moved["printing"] is True, moved


# ---- C1 / B5: what the page saw printing ------------------------------------------------------------

def test_a_head_the_page_saw_printing_is_asked_about_when_the_probe_fails():
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res, _ = _move(sm, probe=_probe_fails, seen_printing=["XL-1"])
    assert res.get("status") == "requires_confirm" and res.get("confirm_type") == "active_print", res
    assert [(a["toolhead"], a["role"], a["state"]) for a in res["active_prints"]] == [("XL-1", "feeds", "PRINTING")]
    assert res["can_store"] is True and res["title"] == "Load #42 onto XL-1?", res
    assert sm.writes == []


def test_without_what_the_page_saw_a_failing_probe_still_fails_open():
    """A control (unchanged behaviour): an unreachable printer never blocks a
    move by itself (L3)."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res, _ = _move(sm, probe=_probe_fails)
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res


def test_a_definite_idle_answer_wins_over_what_the_page_saw():
    """A control: the print ended between the page's check and the move's."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    res, _ = _move(sm, probe=IDLE, seen_printing=["XL-1"])
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res


def test_what_the_page_saw_lasts_one_move():
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}, 43: {"location": "CR-CT-2-R1", "extra": {}}})
    asked, _ = _move(sm, probe=_probe_fails, seen_printing=["XL-2"], slot="2")
    assert asked.get("status") == "requires_confirm", asked
    after, _ = _move(sm, probe=_probe_fails, spools=(43,), slot="2")
    assert after.get("status") == "success" and after.get("auto_deployed_to") == "XL-2", after


def test_the_deposit_door_asks_when_its_page_saw_the_print(client):
    """HEAD: the deposit's request loads #42 onto XL-1 with no question."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    r = run_move(sm, probe=_probe_fails, store=LocationsStore(ROWS_R), printer_map=PRINTER_MAP_F,
                 call=lambda: client.post("/api/identify_scan", json={
                     "text": "LOC:LR-MDB-1:SLOT:1", "source": "quickswap_deposit", "spool_id": 42,
                     "confirmed_toolheads": [], "confirmed_fed_heads": [], "expected_feed": "XL-1",
                     "seen_printing": ["XL-1"]}))
    body = r.get_json()
    assert body["action"] == "assignment_requires_confirm" and body["can_store"] is True, body
    assert sm.writes == [] and [i["id"] for i in state.GLOBAL_BUFFER] == [42]


@pytest.mark.parametrize("value, expected", [
    ({}, []), ({"seen_printing": None}, []), ({"seen_printing": "XL-1"}, []),
    ({"seen_printing": [" xl-1 ", '"XL-2"', "", 5, None, {"h": "XL-3"}]}, ["XL-1", "XL-2"]),
])
def test_seen_printing_from_reads_the_request(value, expected):
    assert logic.seen_printing_from(value) == expected
    assert logic.seen_printing_from(None) == []


# ---- the fix check (wf_0dddaf03-9a6) --------------------------------------------------------------

@pytest.mark.parametrize("where", ["CR-CT-2-R1", ""], ids=["on-a-cart-row", "unassigned"])
def test_a_stale_trail_never_blocks_a_load(where):
    """E1 / S1 (orange; a regression in f055def): #60 was loaded from LR-MDB-1
    slot 1, then moved off XL-1 by a Location edit, which keeps the trail. Slot 1
    still feeds XL-1 (empty, idle), so Derek's blind slot scan loads #42, as it
    did before f055def: a stale trail is not a spool in the slot."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}},
              60: {"location": where, "extra": _trail("LR-MDB-1", 1)}})
    res, _ = _move(sm)
    assert res.get("status") == "success" and res.get("auto_deployed_to") == "XL-1", res
    assert sm.direct_at("XL-1") == [42]


@pytest.mark.parametrize("where, said", [
    ("CR-CT-2-R1", "LR-MDB-1 slot 1 is still claimed by #60, whose record says it came from there, though it is "
                   "on CR-CT-2-R1: scan #60, then CR-CT-2-R1's label, to clear that, so nothing moved"),
    ("", "LR-MDB-1 slot 1 is still claimed by #60, whose record says it came from there, though it is in "
         "Unassigned: scan #60, then the label of where it sits, to clear that, so nothing moved"),
], ids=["on-a-cart-row", "unassigned"])
def test_a_store_over_a_stale_trail_says_what_it_is(where, said):
    """A store still refuses a slot a record claims (as before f055def), but no
    longer calls a cart row "loaded" or a blank location "a toolhead"."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}},
              60: {"location": where, "extra": _trail("LR-MDB-1", 1)}})
    res, _ = _move(sm, auto_deploy=False)
    assert logic.smart_move_failure(res, 42) == said, res
    assert sm.writes == []


def test_every_question_names_the_heads_its_spools_leave():
    """W4: `leaving` (printing or not), so a store's toast never says that a
    head the spool left "was left as it was"."""
    res, _ = _move(_sm({42: {"location": "RC-1", "extra": {}}}), probe=_probe_for({"RC"}))
    assert res.get("status") == "requires_confirm" and res["leaving"] == ["RC-1"], res
    fed, _ = _move(_sm({42: {"location": "CR-CT-2-R1", "extra": {}},
                        99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}}))
    assert fed.get("confirm_type") == "head_fed" and fed["leaving"] == [], fed


def test_a_repoint_back_to_a_confirmed_printing_head_is_drawn_printing():
    """S4: the XL prints; the user confirmed XL-1, the slot went to XL-2 and back
    to XL-1. Every head is covered, so active_prints is empty, yet the body says
    the XL is printing, and so must `printing`."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}, 99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    printing = _probe_for({"XL"})
    first, store = _move(sm, probe=printing)
    key = first["fed_heads"][0]["confirm_key"]
    store.row("LR-MDB-1")["extra"]["slot_targets"]["1"] = "XL-2"
    mid, _ = _move(sm, store=store, probe=printing, confirm_active_print=["XL-1"], confirmed_fed_heads=[key],
                   expected_feed="XL-1")
    assert mid.get("confirm_type") == "feed_changed", mid
    store.row("LR-MDB-1")["extra"]["slot_targets"]["1"] = "XL-1"
    back, _ = _move(sm, store=store, probe=printing, confirm_active_print=["XL-1", "XL-2"],
                    confirmed_fed_heads=[key], expected_feed="XL-2")
    assert back.get("confirm_type") == "feed_changed" and back["active_prints"] == [], back
    assert back["printing"] is True and "XL is PRINTING." in back["body"], back


def test_a_seen_printing_that_cannot_be_read_leaves_no_move_half_open():
    """E4: a value that isn't a list raises before the move counts as started,
    so the next move still owns its printer checks and its seen_printing."""
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    with pytest.raises(TypeError):
        _move(sm, probe=_probe_fails, seen_printing=5)
    assert getattr(logic._smart_move_depth, "n", 0) == 0
    res, _ = _move(sm, probe=_probe_fails, seen_printing=["XL-1"])
    assert res.get("status") == "requires_confirm", res


def test_what_the_page_saw_is_forgotten_outside_the_move():
    """S4: after a move with seen_printing, a printer check outside any move
    (eject, force-unassign) fails open again."""
    from unittest.mock import patch
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    _move(sm, probe=_probe_fails, seen_printing=["XL-1"])
    assert getattr(logic._move_seen_printing, "heads", None) is None
    with patch("prusalink_api._probe_printer_state", side_effect=_probe_fails), \
            patch.object(logic.config_loader, "get_api_urls", return_value=("http://spoolman", "http://fb")):
        assert logic._active_print_info_for_location("XL-1", PRINTER_MAP_F) is None
