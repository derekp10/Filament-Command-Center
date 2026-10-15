"""Group 40.3 — a slot re-pointed while its question was open asks again
(Derek, 2026-10-14: "multi-user awareness"; he fills slot 1 because a slicer
file depends on it).

Every question about a box slot carries what the slot fed (`feed`: a head id,
or "" for a Printer Pool / unbound slot / no slot). Every replay sends it back
as `expected_feed`; a screen that showed the feed (a deposit tile) sends it on
its first request too. When the slot feeds something else now, the engine
writes nothing and answers `confirm_type: "feed_changed"`, naming both:
"LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked). Load #42
onto XL-2?", even for an empty, idle XL-2, on a store as on a load. A new feed
that loads nothing (a pool, no toolhead, a binding to a non-head) offers only
the store. A blind slot scan sends no expected_feed, so Derek's first scans stay
prompt-free.

The REAL engine runs over tests/move_engine_harness.py with a live locations
store; the doors run through the Flask client.
HEAD proof (d2f076f): the engine tests fail on the signature there (no
`expected_feed` keyword: a signature-only red, a control in the review's
terms); the door tests T1-15 / T1-16 / T1-17 are the behavioural proofs (HEAD's
doors ignore the field and load or store over the re-point unasked), and
T1-19 fails there because the slot door dropped the new keys.
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
from test_fed_head_confirm_40_0c import FROM_POLYDRYER, PRINTER_MAP, ROWS  # noqa: E402

# A second printer, RC (head RC-1), so a spool can leave a printing head while
# the XL is idle; and a full-sized box for the full-box case.
ROWS_F = ROWS + [
    {"LocationID": "RC", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "RC-1", "position": 0}]},
    {"LocationID": "RC-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "RC"},
]
PRINTER_MAP_F = dict(PRINTER_MAP, **{"RC-1": {"printer_name": "RC", "position": 0}})
FROM_PM3 = {"physical_source": "PM-DB-3", "physical_source_slot": "1", "container_slot": ""}


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


def _base(more=None):
    """#42 waits in the cart row; XL-1 runs #99 from the PolyDryer PM-DB-2."""
    spools = {42: {"location": "CR-CT-2-R1", "extra": {}},
              99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}}
    spools.update(more or {})
    return _sm(spools)


def _move(sm, store=None, probe=IDLE, slot="1", target="LR-MDB-1", spools=(42,), **kw):
    store = store or LocationsStore(ROWS_F)
    res = run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP_F,
                   target=target, raw_spools=list(spools), target_slot=slot, origin="test", **kw)
    return res, store


def _repoint(store, slot, to, box="LR-MDB-1"):
    targets = store.row(box)["extra"].setdefault("slot_targets", {})
    if to is None:
        targets.pop(str(slot), None)
    else:
        targets[str(slot)] = to


def _slot_of(sm, sid):
    return str((sm.spools[sid].get("extra") or {}).get("container_slot") or "").strip('"')


def _first_fed_question(sm, store=None, **kw):
    res, store = _move(sm, store=store, **kw)
    assert res.get("confirm_type") == "head_fed" and res["feed"] == "XL-1", res
    return res, store


# ---- the re-pointed slot asks again ------------------------------------------------------------

def test_a_slot_repointed_to_an_empty_idle_head_is_asked_again_naming_both():
    sm = _base()
    first, store = _first_fed_question(sm)
    key = first["fed_heads"][0]["confirm_key"]
    _repoint(store, 1, "XL-2")
    again, _ = _move(sm, store=store, confirmed_fed_heads=[key], expected_feed="XL-1")
    assert again == {
        "status": "requires_confirm", "confirm_type": "feed_changed",
        "feed_changed": {"was": "XL-1", "now": "XL-2"},
        "fed_heads": [], "active_prints": [], "active_print": None,
        "can_store": True, "can_load": True,
        "target": "LR-MDB-1", "target_slot": "1", "slot_picked": False, "feed": "XL-2",
        "spools": [42],
        "title": "Load #42 onto XL-2?",
        "body": "LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked).",
        "msg": "LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked). Load #42 onto XL-2?",
    }, again
    assert sm.writes == []
    # The Yes to the new question (naming XL-2) loads XL-2; XL-1 keeps #99.
    done, _ = _move(sm, store=store, confirmed_fed_heads=[key], expected_feed="XL-2")
    assert done.get("status") == "success" and done.get("auto_deployed_to") == "XL-2", done
    assert sm.direct_at("XL-2") == [42] and sm.direct_at("XL-1") == [99]
    assert store.bound("PM-DB-2") == "XL-1"     # #99 never left, so its PolyDryer stays attached


def test_the_store_replay_is_asked_again_too():
    """Claude's call (Derek can veto): a stored spool is staged for whatever the
    slot feeds, so a store into a re-pointed slot asks too."""
    sm = _base()
    _, store = _first_fed_question(sm)
    _repoint(store, 1, "XL-2")
    again, _ = _move(sm, store=store, auto_deploy=False, expected_feed="XL-1")
    assert again.get("confirm_type") == "feed_changed" and again["feed"] == "XL-2", again
    assert sm.writes == []
    stored, _ = _move(sm, store=store, auto_deploy=False, expected_feed="XL-2")
    assert stored.get("status") == "success" and "auto_deployed_to" not in stored, stored
    assert sm.spools[42]["location"] == "LR-MDB-1" and _slot_of(sm, 42) == "1"
    assert sm.direct_at("XL-2") == [] and sm.direct_at("XL-1") == [99]


def test_a_repointed_slot_whose_new_head_runs_a_spool_from_elsewhere_is_one_question():
    sm = _base({77: {"location": "XL-2", "extra": dict(FROM_PM3)}})
    first, store = _first_fed_question(sm)
    _repoint(store, 1, "XL-2")
    again, _ = _move(sm, store=store, confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]],
                     expected_feed="XL-1")
    assert again.get("confirm_type") == "feed_changed", again
    assert [(f["toolhead"], f["confirm_key"]) for f in again["fed_heads"]] == [("XL-2", "XL-2#77")], again
    assert again["body"] == ("LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked). XL-2 is "
                             "running #77 (from PM-DB-3). Loading #42 sends #77 back to PM-DB-3."), again["body"]
    keys = [first["fed_heads"][0]["confirm_key"], again["fed_heads"][0]["confirm_key"]]
    done, _ = _move(sm, store=store, confirmed_fed_heads=keys, expected_feed="XL-2")
    assert done.get("auto_deployed_to") == "XL-2", done
    assert sm.direct_at("XL-2") == [42] and sm.spools[77]["location"] == "PM-DB-3"


def test_a_repointed_slot_on_a_printing_xl_names_the_print_once():
    sm = _base()
    probe = _probe_for({"XL"})
    first, store = _first_fed_question(sm, probe=probe)
    _repoint(store, 1, "XL-2")
    heads = ["XL-1"]
    again, _ = _move(sm, store=store, probe=probe, confirm_active_print=heads,
                     confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]], expected_feed="XL-1")
    assert again.get("confirm_type") == "feed_changed", again
    assert [(a["toolhead"], a["role"]) for a in again["active_prints"]] == [("XL-2", "feeds")], again
    assert again["body"] == "LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked). XL is PRINTING."
    assert again["body"].count("PRINTING") == 1
    done, _ = _move(sm, store=store, probe=probe, confirm_active_print=["XL-1", "XL-2"],
                    confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]], expected_feed="XL-2")
    assert done.get("auto_deployed_to") == "XL-2", done


def test_the_same_head_with_a_new_spool_is_one_head_fed_question():
    """No double prompt: the feed still holds, and the confirm key (XL-1#99) is
    what no longer covers XL-1 once it runs #7 instead."""
    sm = _base()
    first, store = _first_fed_question(sm)
    sm.spools[99]["location"] = "PM-DB-2"
    sm.spools[7] = {"location": "XL-1", "extra": {}}
    again, _ = _move(sm, store=store, confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]],
                     expected_feed="XL-1")
    assert again.get("confirm_type") == "head_fed", again
    assert [r["id"] for r in again["fed_heads"][0]["residents"]] == [7]


@pytest.mark.parametrize("to, lead, token", [
    ("PRINTER:XL", "LR-MDB-1 slot 1 is now a Printer Pool slot (it fed XL-1 when you were asked).", ""),
    (None, "LR-MDB-1 slot 1 now feeds no toolhead (it fed XL-1 when you were asked).", ""),
    ("XL-9", "LR-MDB-1 slot 1 now points at XL-9, which isn't a toolhead (it fed XL-1 when you were asked).", "XL-9"),
], ids=["pool", "unbound", "non-head"])
def test_a_repoint_to_a_pool_unbound_or_non_head_offers_only_the_store(to, lead, token):
    sm = _base()
    first, store = _first_fed_question(sm)
    _repoint(store, 1, to)
    again, _ = _move(sm, store=store, confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]],
                     expected_feed="XL-1")
    assert again.get("confirm_type") == "feed_changed", again
    assert again["body"] == lead and again["title"] == "Store #42 in LR-MDB-1 slot 1?", again
    assert again["can_load"] is False and again["can_store"] is True and again["feed"] == token
    stored, _ = _move(sm, store=store, auto_deploy=False, expected_feed=token)
    assert stored.get("status") == "success", stored
    assert sm.spools[42]["location"] == "LR-MDB-1" and _slot_of(sm, 42) == "1"
    assert sm.direct_at("XL-1") == [99]


def test_an_auto_picked_slot_repointed_meanwhile_keeps_the_pick_and_asks_again():
    sm = _base({50: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}},
                  51: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}},
                  52: {"location": "LR-MDB-1", "extra": {"container_slot": "4"}}})
    first, store = _move(sm, slot=None)
    assert first.get("confirm_type") == "head_fed" and first["target_slot"] == "1", first
    assert first["slot_picked"] is True and first["feed"] == "XL-1"
    _repoint(store, 1, "XL-2")
    again, _ = _move(sm, store=store, slot=None, picked_slot="1",
                     confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]], expected_feed="XL-1")
    assert again.get("confirm_type") == "feed_changed", again
    assert again["target_slot"] == "1" and again["slot_picked"] is True and again["feed"] == "XL-2"
    assert sm.writes == []


class _Reads(FakeSpoolman):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.read_locs = []

    def at_location_detailed_strict(self, loc):
        self.read_locs.append(str(loc).upper())
        return super().at_location_detailed_strict(loc)


def test_a_matching_store_replay_reads_no_head():
    """The check is pure: a store whose feed still holds reads no toolhead."""
    sm = _Reads({42: {"location": "CR-CT-2-R1", "extra": {}},
                 99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    res, _ = _move(sm, auto_deploy=False, expected_feed="XL-1")
    assert res.get("status") == "success", res
    assert "XL-1" not in sm.read_locs, sm.read_locs


def test_a_single_slot_box_and_a_head_target_ignore_expected_feed():
    sm = _base()
    res, _ = _move(sm, target="PM-DB-3", slot=None, expected_feed="XL-2")
    assert res.get("status") == "success" and res.get("confirm_type") is None, res
    sm2 = _base()
    res2, _ = _move(sm2, target="XL-2", slot=None, expected_feed="XL-1")
    assert res2.get("status") == "success" and sm2.direct_at("XL-2") == [42], res2


def test_a_repoint_back_names_the_spool_an_old_key_covers():
    sm = _base()
    first, store = _first_fed_question(sm)
    key = first["fed_heads"][0]["confirm_key"]
    _repoint(store, 1, "XL-2")
    mid, _ = _move(sm, store=store, confirmed_fed_heads=[key], expected_feed="XL-1")
    assert mid["feed"] == "XL-2"
    _repoint(store, 1, "XL-1")
    back, _ = _move(sm, store=store, confirmed_fed_heads=[key], expected_feed="XL-2")
    assert back.get("confirm_type") == "feed_changed", back
    assert back["body"] == ("LR-MDB-1 slot 1 now feeds XL-1 (it fed XL-2 when you were asked). XL-1 is "
                            "running #99 (from PM-DB-2). Loading #42 sends #99 back to PM-DB-2."), back["body"]
    assert [f["confirm_key"] for f in back["fed_heads"]] == ["XL-1#99"]


def test_a_pool_slot_repointed_to_a_head_asks_before_loading():
    """#42 leaves the printing RC-1 for LR-MDB-1 slot 4, a Printer Pool slot:
    the source question names no feed (""). Someone binds slot 4 to XL-1
    meanwhile; without the check the Yes would load #42 onto XL-1 unasked."""
    sm = _sm({42: {"location": "RC-1", "extra": {}}})
    probe = _probe_for({"RC"})
    first, store = _move(sm, probe=probe, slot="4")
    assert first.get("confirm_type") == "active_print" and first["feed"] == "", first
    assert [(a["toolhead"], a["role"]) for a in first["active_prints"]] == [("RC-1", "source")]
    _repoint(store, 4, "XL-1")
    again, _ = _move(sm, store=store, probe=probe, slot="4", confirm_active_print=["RC-1"], expected_feed="")
    assert again.get("confirm_type") == "feed_changed", again
    assert again["feed_changed"] == {"was": "", "now": "XL-1"}
    assert again["body"].startswith("LR-MDB-1 slot 4 now feeds XL-1 (it fed no toolhead when you were asked).")
    assert sm.writes == []


def test_a_full_box_that_frees_a_feed_slot_asks_before_loading():
    sm = _sm({42: {"location": "RC-1", "extra": {}},
              **{50 + n: {"location": "LR-MDB-1", "extra": {"container_slot": str(n)}} for n in (1, 2, 3, 4)}})
    probe = _probe_for({"RC"})
    first, store = _move(sm, probe=probe, slot=None)
    assert first.get("confirm_type") == "active_print" and first["target_slot"] is None, first
    assert first["feed"] == "" and first["slot_picked"] is False
    sm.spools[51]["location"] = "CR-CT-2-R1"        # slot 1 frees up
    again, _ = _move(sm, store=store, probe=probe, slot=None, confirm_active_print=["RC-1"], expected_feed="")
    assert again.get("confirm_type") == "feed_changed", again
    assert again["target_slot"] == "1" and again["slot_picked"] is True
    assert again["body"].startswith(
        "LR-MDB-1 slot 1 is free now, and it feeds XL-1 (the box was full when you were asked)."), again["body"]


def test_every_question_carries_what_its_replay_sends():
    fed, _ = _move(_base())
    assert (fed["target"], fed["target_slot"], fed["slot_picked"], fed["feed"], fed["can_load"]) \
        == ("LR-MDB-1", "1", False, "XL-1", True)
    printing, _ = _move(_sm({42: {"location": "CR-CT-2-R1", "extra": {}}}), probe=_probe_for({"XL"}), slot="2")
    assert printing.get("confirm_type") == "active_print", printing
    assert (printing["feed"], printing["can_load"], printing["slot_picked"]) == ("XL-2", True, False)
    head, _ = _move(_sm({42: {"location": "CR-CT-2-R1", "extra": {}}, 7: {"location": "XL-2", "extra": {}}}),
                    probe=_probe_for({"XL"}), target="XL-2", slot=None)
    assert head.get("confirm_type") == "active_print", head
    assert (head["target"], head["feed"], head["can_load"]) == ("XL-2", None, False)
    picked, _ = _move(_sm({42: {"location": "CR-CT-2-R1", "extra": {}}}), probe=_probe_for({"XL"}), slot=None)
    assert picked["slot_picked"] is True and picked["target_slot"] == "1" and picked["feed"] == "XL-1", picked


@pytest.mark.parametrize("value, expected", [
    ({}, None), ({"expected_feed": None}, None),
    ({"expected_feed": " xl-1 "}, "XL-1"), ({"expected_feed": '"XL-1"'}, "XL-1"),
    ({"expected_feed": ""}, ""), ({"expected_feed": "PRINTER:XL"}, ""), ({"expected_feed": "null"}, ""),
    ({"expected_feed": 5}, ""), ({"expected_feed": []}, ""), ({"expected_feed": {"toolhead": "XL-1"}}, ""),
])
def test_expected_feed_from_reads_the_request(value, expected):
    assert logic.expected_feed_from(value) == expected
    assert logic.expected_feed_from(None) is None


# ---- the doors ------------------------------------------------------------------------------------

def _door(sm, client, path, body, store=None, probe=IDLE):
    store = store or LocationsStore(ROWS_F)
    return run_move(sm, probe=probe, store=store, printer_map=PRINTER_MAP_F,
                    call=lambda: client.post(path, json=body)), store


def test_the_slot_scan_replay_is_asked_again_when_the_slot_was_repointed(client):
    """Derek's own door. HEAD: the replay loads #42 onto XL-2 unasked."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _base()
    scan = {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []}
    r, store = _door(sm, client, "/api/identify_scan", scan)
    first = r.get_json()
    assert first["confirm_type"] == "head_fed", first
    _repoint(store, 1, "XL-2")
    r, _ = _door(sm, client, "/api/identify_scan", dict(
        scan, spool_id=42, confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]], expected_feed="XL-1"),
        store=store)
    again = r.get_json()
    assert again["action"] == "assignment_requires_confirm" and again["confirm_type"] == "feed_changed", again
    assert first["feed"] == "XL-1", first
    assert again["msg"] == "LR-MDB-1 slot 1 now feeds XL-2 (it fed XL-1 when you were asked). Load #42 onto XL-2?"
    assert again["feed"] == "XL-2" and again["can_load"] is True
    assert sm.writes == [] and [i["id"] for i in state.GLOBAL_BUFFER] == [42]


@pytest.mark.parametrize("path, body", [
    ("/api/manage_contents", {"action": "add", "location": "LR-MDB-1", "spool_id": "ID:42", "slot": None}),
    ("/api/smart_move", {"location": "LR-MDB-1", "spools": [42], "slot": None}),
], ids=["manage_contents", "smart_move"])
def test_the_box_doors_ask_again_about_a_repointed_picked_slot(client, path, body):
    """HEAD: the replay loads #42 onto XL-2 unasked."""
    sm = _base({50: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}},
                  51: {"location": "LR-MDB-1", "extra": {"container_slot": "3"}},
                  52: {"location": "LR-MDB-1", "extra": {"container_slot": "4"}}})
    r, store = _door(sm, client, path, dict(body, confirmed_toolheads=[], confirmed_fed_heads=[]))
    first = r.get_json()
    assert first["confirm_type"] == "head_fed" and first["target_slot"] == "1", first
    _repoint(store, 1, "XL-2")
    r, _ = _door(sm, client, path, dict(body, confirmed_toolheads=[], picked_slot=first["target_slot"],
                                        confirmed_fed_heads=[first["fed_heads"][0]["confirm_key"]],
                                        expected_feed="XL-1"), store=store)
    again = r.get_json()
    assert again.get("confirm_type") == "feed_changed", again
    assert first["slot_picked"] is True and again["slot_picked"] is True and again["target_slot"] == "1", again
    assert sm.writes == []


def test_the_store_replay_at_the_slot_scan_is_asked_again(client):
    """HEAD: the store lands in a slot that now feeds XL-2, unasked."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _base()
    scan = {"text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []}
    r, store = _door(sm, client, "/api/identify_scan", scan)
    _repoint(store, 1, "XL-2")
    r, _ = _door(sm, client, "/api/identify_scan", dict(scan, spool_id=42, auto_deploy=False,
                                                        expected_feed="XL-1"), store=store)
    again = r.get_json()
    assert again["action"] == "assignment_requires_confirm" and again["confirm_type"] == "feed_changed", again
    assert sm.writes == []


def test_a_first_slot_scan_never_gets_a_feed_change(client):
    """Derek's S1: a 40.3 page's first scan (both lists, no expected_feed) into
    an empty idle head's slot loads it with no question. A control."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _sm({42: {"location": "CR-CT-2-R1", "extra": {}}})
    r, _ = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:2", "source": "barcode", "confirmed_toolheads": [], "confirmed_fed_heads": []})
    body = r.get_json()
    assert body["action"] == "assignment_done" and body["auto_deployed_to"] == "XL-2", body


def test_the_slot_scan_relays_every_key_of_the_engines_question(client):
    """HEAD: the door copied a fixed list, so `feed`, `slot_picked`, `target`,
    `can_load` and `feed_changed` never reached the browser."""
    state.GLOBAL_BUFFER = [{"id": 42, "display": "#42"}]
    sm = _base()
    r, store = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "confirmed_fed_heads": []})
    fed = r.get_json()
    engine, _ = _move(_base())
    assert set(engine) - {"status"} <= set(fed), set(engine) - set(fed)
    _repoint(store, 1, "XL-2")
    r, _ = _door(sm, client, "/api/identify_scan", {
        "text": "LOC:LR-MDB-1:SLOT:1", "source": "barcode", "spool_id": 42,
        "confirmed_fed_heads": [fed["fed_heads"][0]["confirm_key"]], "expected_feed": "XL-1"}, store=store)
    changed = r.get_json()
    for key in ("feed_changed", "feed", "slot_picked", "target", "can_load", "title", "body"):
        assert key in changed, key
