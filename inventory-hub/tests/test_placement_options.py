"""Group 40.1 — the placement model behind the slot picker (placement.py and
GET /api/placement_options).

Hermetic: locations.json is a fixed row list, Spoolman's spool list a fixed
list of parsed records. Everything between them is real: the bucket matcher
(spoolman_api.bucket_spools_by_location / _build_location_match), the display
formatter, the printer map built from the Printer rows, and the shared ⭐ rule
(logic.recommend_box_slot over box_slot_claims and slot_would_prompt). One
test runs the REAL move engine over the same data and checks that the ⭐ is
the slot a slotless move takes ([[mocked engine hides chain bugs]]).
"""
import copy
from contextlib import ExitStack
from unittest.mock import patch

import pytest

import app as app_module
import logic
import placement

from move_engine_harness import FakeSpoolman, IDLE, run_move


def _box(lid, max_spools, targets=None, **extra):
    ex = dict(extra)
    if targets is not None:
        ex["slot_targets"] = targets
    return {"LocationID": lid, "Name": lid, "Type": "Dryer Box", "Max Spools": str(max_spools), "extra": ex}


def _head(lid):
    return {"LocationID": lid, "Name": lid, "Type": "Tool Head", "Max Spools": "1"}


def _printer(lid, name, heads, max_spools="0"):
    return {"LocationID": lid, "Name": name, "Type": "Printer", "Max Spools": max_spools,
            "toolheads": [{"location_id": h, "position": i} for i, h in enumerate(heads)]}


XL_HEADS = ["XL-1", "XL-2", "XL-3", "XL-4", "XL-5"]

ROWS = [
    {"LocationID": "LR", "Name": "Living Room", "Type": "Room", "Max Spools": "0"},
    _printer("XL", "🦝 XL", XL_HEADS),
    *[_head(h) for h in XL_HEADS],
    _printer("CORE1", "Core One", ["CORE1"], max_spools="1"),
    _printer("MK4", "MK4", []),
    _box("LR-MDB-1", 4, {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}),
    _box("LR-MDB-2", 2, {"1": "XL-4", "2": "XL-5"}),
    _box("TST-MDB-1", 6, {"1": "PRINTER:XL"}),
    _box("CR-MDB-1", 4, {"1": "CORE1"}),
    _box("RTL-BOX", 3, {}, slot_order="rtl"),
    _box("PM-DB-2", 1, {}),
    {"LocationID": "CR-CT-2-R1", "Name": "Cart row 1", "Type": "Cart", "Max Spools": "0"},
]


def _sp(sid, loc, slot="", src="", src_slot="", name="Galaxy Black", color="222222"):
    extra = {}
    if slot:
        extra["container_slot"] = str(slot)
    if src:
        extra["physical_source"] = src
    if src_slot:
        extra["physical_source_slot"] = str(src_slot)
    return {"id": sid, "location": loc, "remaining_weight": 500, "extra": extra,
            "filament": {"name": name, "material": "PLA", "color_hex": color,
                         "vendor": {"name": "Prusament"}}}


def _build(spools, location, rows=None, archived=(), fail=False, **kwargs):
    """placement.build_placement_options over fixed rows + spools. `archived`
    spools are readable by id but missing from the (non-archived) list."""
    rows = copy.deepcopy(ROWS if rows is None else rows)
    listed = [copy.deepcopy(s) for s in spools if s["id"] not in set(archived)]
    by_id = {s["id"]: copy.deepcopy(s) for s in spools}

    def _list(*a, **k):
        if fail:
            raise placement.spoolman_api.requests.ConnectionError("Spoolman down (test)")
        return copy.deepcopy(listed)

    with ExitStack() as st:
        st.enter_context(patch.object(placement.locations_db, "load_locations_list",
                                      side_effect=lambda *a, **k: copy.deepcopy(rows)))
        st.enter_context(patch.object(placement.spoolman_api, "get_all_spools_strict", side_effect=_list))
        st.enter_context(patch.object(placement.spoolman_api, "get_spool",
                                      side_effect=lambda sid: copy.deepcopy(by_id.get(int(sid)))))
        st.enter_context(patch.object(placement.locations_db, "is_descendant", return_value=False))
        return placement.build_placement_options(location, **kwargs)


def _slot(model, n):
    return next(s for s in model["slots"] if s["slot"] == str(n))


# ---- box mode: what each slot shows -----------------------------------------------------------

def test_box_mode_shows_each_slot_its_spool_feed_and_the_head_resident():
    spools = [
        _sp(57, "LR-MDB-1", slot=2),                                   # in slot 2
        _sp(60, "XL-3", src="LR-MDB-1", src_slot=3),                   # deployed from slot 3
        _sp(99, "XL-1", src="PM-DB-2", src_slot=1),                    # XL-1 runs a PolyDryer spool
        _sp(42, "CR-CT-2-R1"),                                         # the spool being placed
    ]
    model, status = _build(spools, "LR-MDB-1", spool=42)
    assert status == 200
    assert model["mode"] == "box" and model["read_ok"] is True
    assert model["max_slots"] == 4 and model["slot_order"] == "ltr"
    assert [s["slot"] for s in model["slots"]] == ["1", "2", "3", "4"]

    s1, s2, s3, s4 = (_slot(model, n) for n in (1, 2, 3, 4))
    assert s1["spool"] is None and s1["free"] is True
    assert s1["feeds"]["kind"] == "toolhead" and s1["feeds"]["id"] == "XL-1"
    assert s1["feeds"]["printer"] == "🦝 XL"
    res = s1["feeds"]["residents"]
    assert [r["id"] for r in res] == [99] and res[0]["from"] == "PM-DB-2"
    assert s1["would_prompt"] is True          # XL-1 holds a spool

    assert s2["spool"]["id"] == 57 and s2["free"] is False and s2["spool"]["is_ghost"] is False
    assert s3["spool"]["id"] == 60 and s3["spool"]["is_ghost"] is True
    assert s3["spool"]["deployed_to"] == "XL-3" and s3["free"] is False
    # A head's resident is the spool whose OWN record is on it: #60 is XL-3's.
    assert [r["id"] for r in s3["feeds"]["residents"]] == [60]

    assert s4["feeds"] == {"kind": "pool", "printer": "XL", "printer_name": "🦝 XL"}
    assert s4["free"] is True and s4["would_prompt"] is False
    # The pick: slot 1 would ask (XL-1 runs #99), slot 4 loads nothing.
    assert model["recommended"] == {"kind": "slot", "box": "LR-MDB-1", "slot": "4"}
    assert model["recommend_reason"] == "no_prompt"
    assert model["printers"] == [{"name": "🦝 XL", "head": "XL-1"}]
    assert model["spool_location"] == "CR-CT-2-R1"
    assert model["spool_display"].startswith("#42 ")


def test_a_spool_already_in_the_box_is_recommended_its_own_slot():
    spools = [_sp(42, "LR-MDB-1", slot=3)]
    model, _ = _build(spools, "LR-MDB-1", spool=42)
    assert model["recommended"]["slot"] == "3" and model["recommend_reason"] == "own_slot"
    assert _slot(model, 3)["current"] is True and _slot(model, 3)["free"] is True


def test_a_spool_deployed_from_the_box_is_recommended_the_slot_it_came_from():
    """It still holds its slot physically; putting it back there from its head
    only stores it (the engine's store_only), so the tile says the head is its
    own (`is_source`)."""
    spools = [_sp(42, "XL-3", src="LR-MDB-1", src_slot=3)]
    model, _ = _build(spools, "LR-MDB-1", spool=42)
    assert model["recommended"]["slot"] == "3" and model["recommend_reason"] == "own_slot"
    s3 = _slot(model, 3)
    assert s3["current"] is True and s3["free"] is True
    assert s3["feeds"]["is_source"] is True
    assert model["spool_location"] == "XL-3"


def test_when_every_free_slot_would_ask_the_lowest_free_slot_is_recommended():
    spools = [
        _sp(57, "LR-MDB-1", slot=2), _sp(58, "LR-MDB-1", slot=4),
        _sp(99, "XL-1"), _sp(98, "XL-3"),
        _sp(42, "CR-CT-2-R1"),
    ]
    model, _ = _build(spools, "LR-MDB-1", spool=42)
    assert model["recommended"]["slot"] == "1" and model["recommend_reason"] == "lowest_empty"
    assert _slot(model, 1)["would_prompt"] is True and _slot(model, 3)["would_prompt"] is True


def test_a_full_box_recommends_nothing_and_never_assumes_a_free_slot():
    spools = [_sp(50 + n, "LR-MDB-1", slot=n) for n in (1, 2, 3, 4)] + [_sp(42, "CR-CT-2-R1")]
    model, _ = _build(spools, "LR-MDB-1", spool=42)
    assert model["recommended"] is None and model["recommend_reason"] == "full"
    assert all(s["free"] is False for s in model["slots"])
    assert model["recommend_text"] == "every slot is taken"


def test_two_spools_claiming_one_slot_are_both_named_and_the_overflow_is_unslotted():
    spools = [_sp(57, "LR-MDB-1", slot=2), _sp(58, "LR-MDB-1", slot=2),
              _sp(59, "LR-MDB-1"), _sp(61, "LR-MDB-1", slot=9)]
    model, _ = _build(spools, "LR-MDB-1")
    assert sorted(_slot(model, 2)["claimants"]) == [57, 58]
    assert sorted(c["id"] for c in model["unslotted"]) == [59, 61]


def test_an_rtl_box_says_so_so_the_picker_draws_it_like_its_grid():
    model, _ = _build([], "RTL-BOX")
    assert model["slot_order"] == "rtl"
    assert [s["slot"] for s in model["slots"]] == ["1", "2", "3"]
    assert model["recommended"]["slot"] == "1"     # nothing feeds: the lowest free slot


def test_a_spool_on_a_printer_row_itself_or_ghosted_to_a_head_is_not_that_heads_resident():
    """Exact location only: the flat prefix matcher lists XL-n spools "at XL",
    and a trail naming XL-2 lists that spool "at XL-2" as a ghost; neither runs
    on XL-2."""
    spools = [_sp(70, "XL"), _sp(71, "LR-MDB-2", slot=1, src="XL-2"), _sp(72, "XL-2-OLD")]
    model, _ = _build(spools, "LR-MDB-1")
    assert _slot(model, 2)["feeds"]["residents"] == []
    assert _slot(model, 2)["would_prompt"] is False


def test_a_dash_free_heads_prefix_hits_are_not_its_residents():
    """The flat matcher's first-segment hit only reaches a dash-free id, so the
    case above can't show it (Group 40.3 review, D6): CORE1 is its own head and
    CR-MDB-1 slot 1 feeds it; a spool filed on "CORE1-SHELF" is listed "at
    CORE1" by prefix, but it doesn't run on CORE1."""
    spools = [_sp(80, "CORE1-SHELF"), _sp(42, "CR-CT-2-R1")]
    model, _ = _build(spools, "CR-MDB-1", spool=42)
    assert _slot(model, 1)["feeds"]["residents"] == [], _slot(model, 1)
    printer, _ = _build(spools, "CORE1", spool=42)
    assert printer["heads"][0]["resident"] is None and printer["heads"][0]["residents"] == [], printer["heads"]


def test_an_archived_spool_still_gets_its_title_from_a_direct_read():
    spools = [_sp(42, "LR-MDB-2", slot=1)]
    model, _ = _build(spools, "LR-MDB-1", spool=42, archived=(42,))
    assert model["spool_display"].startswith("#42 ")
    assert model["spool_location"] == "LR-MDB-2"


def test_the_strict_spool_read_raises_instead_of_answering_nothing():
    """Group 40.3 review, D5: every other test patches get_all_spools_strict, so
    a fail-open rewrite ("except: return []") passed the whole suite while the
    picker drew every slot empty under a confident star. A 5xx and a dropped
    connection raise; a 200 parses."""
    from unittest.mock import MagicMock
    api = placement.spoolman_api
    ok = MagicMock(status_code=200, json=MagicMock(return_value=[{"id": 1, "location": "X", "extra": {}}]))
    bad = MagicMock(status_code=500)
    bad.raise_for_status = MagicMock(side_effect=api.requests.HTTPError("500 (test)"))
    with patch.object(api.config_loader, "get_api_urls", return_value=("http://spoolman", "")):
        with patch.object(api.requests, "get", return_value=ok) as get:
            assert [s["id"] for s in api.get_all_spools_strict()] == [1]
            assert get.call_args[0][0] == "http://spoolman/api/v1/spool"
        with patch.object(api.requests, "get", return_value=bad):
            with pytest.raises(api.requests.HTTPError):
                api.get_all_spools_strict()
        with patch.object(api.requests, "get", side_effect=api.requests.ConnectionError("down (test)")):
            with pytest.raises(api.requests.ConnectionError):
                api.get_all_spools_strict()


def test_a_spoolman_blip_says_so_instead_of_drawing_empty_slots():
    model, status = _build([_sp(57, "LR-MDB-1", slot=1)], "LR-MDB-1", spool=42, fail=True)
    assert status == 200
    assert model["read_ok"] is False and "couldn't read Spoolman" in model["read_error"]
    assert model["slots"] == [] and model["recommended"] is None


# ---- the ⭐ and the engine's auto-slot are one rule ---------------------------------------------

@pytest.mark.parametrize("spools,expected", [
    # Slot 1's head runs a PolyDryer spool, slots 2-3 are full: the pool slot.
    ([_sp(57, "LR-MDB-1", slot=2), _sp(58, "LR-MDB-1", slot=3), _sp(99, "XL-1", src="PM-DB-2", src_slot=1),
      _sp(42, "CR-CT-2-R1")], "4"),
    # Everything free and idle: slot 1.
    ([_sp(42, "CR-CT-2-R1")], "1"),
    # Only slots whose heads hold spools are free: the lowest.
    ([_sp(57, "LR-MDB-1", slot=2), _sp(58, "LR-MDB-1", slot=4), _sp(99, "XL-1"), _sp(98, "XL-3"),
      _sp(42, "CR-CT-2-R1")], "1"),
    # Deployed from slot 3 onto XL-3: back into slot 3.
    ([_sp(42, "XL-3", src="LR-MDB-1", src_slot=3)], "3"),
])
def test_the_star_is_the_slot_a_slotless_move_takes(spools, expected):
    """The picker's ⭐ and the engine's auto-slot (40.0e) share box_slot_claims,
    slot_would_prompt and recommend_box_slot. Run both on the same data: the
    real engine (Spoolman faked) answers with the slot it picked."""
    model, _ = _build(spools, "LR-MDB-1", spool=42)
    assert model["recommended"]["slot"] == expected

    sm = FakeSpoolman({s["id"]: {"location": s["location"], "extra": dict(s["extra"])} for s in spools})
    printer_map = logic.locations_db.build_printer_map_from_rows(copy.deepcopy(ROWS))
    result = run_move(sm, probe=IDLE, printer_map=printer_map, locations=copy.deepcopy(ROWS),
                      target="LR-MDB-1", raw_spools=[42], auto_deploy=True)
    # The engine either asked (naming its pick) or moved the spool into it.
    picked = result.get("target_slot") if result.get("status") == "requires_confirm" else \
        str((sm.spools[42].get("extra") or {}).get("container_slot") or "").strip('"')
    if result.get("status") != "requires_confirm" and sm.spools[42]["location"] != "LR-MDB-1":
        # Loaded onto the slot's head by the chain: the trail names the slot.
        picked = str(sm.spools[42]["extra"].get("physical_source_slot") or "").strip('"')
    assert picked == expected, result


# ---- printer mode --------------------------------------------------------------------------------

def test_printer_mode_lists_the_heads_from_the_row_with_residents_feeds_and_the_pool():
    spools = [
        _sp(99, "XL-1", src="PM-DB-2", src_slot=1),
        _sp(57, "LR-MDB-2", slot=1),                 # LR-MDB-2 slot 1 feeds XL-4, taken
        _sp(60, "XL-3", src="LR-MDB-1", src_slot=3), # deployed from LR-MDB-1 slot 3
        _sp(61, "TST-MDB-1", slot=1),                # a pool slot, taken
        _sp(42, "CR-CT-2-R1"),
    ]
    model, status = _build(spools, "XL", spool=42)
    assert status == 200 and model["mode"] == "printer" and model["read_ok"] is True
    assert model["self_head"] is False and model["name"] == "🦝 XL"
    assert [h["id"] for h in model["heads"]] == XL_HEADS
    by = {h["id"]: h for h in model["heads"]}
    assert by["XL-1"]["resident"]["id"] == 99 and by["XL-1"]["resident"]["from"] == "PM-DB-2"
    assert by["XL-2"]["resident"] is None
    assert by["XL-1"]["feeds"] == [{"box": "LR-MDB-1", "slot": "1", "spool": None,
                                    "claimed_by": None, "free": True}]
    assert by["XL-4"]["feeds"][0]["claimed_by"] == 57 and by["XL-4"]["feeds"][0]["free"] is False
    # A deployed spool still claims the slot it came from.
    assert by["XL-3"]["feeds"][0]["claimed_by"] == 60
    pool = {(p["box"], p["slot"]): p for p in model["pool"]}
    assert set(pool) == {("LR-MDB-1", "4"), ("TST-MDB-1", "1")}
    assert pool[("TST-MDB-1", "1")]["free"] is False and pool[("LR-MDB-1", "4")]["free"] is True
    # Several free choices: nothing pre-selected (D3).
    assert model["recommended"] is None and model["recommend_reason"] == "several_free"
    assert model["printers"] == [{"name": "🦝 XL", "head": "XL-1"}]


def test_printer_mode_pre_selects_only_when_exactly_one_free_choice_exists():
    spools = [_sp(90 + i, h) for i, h in enumerate(XL_HEADS) if h != "XL-4"]
    spools += [_sp(61, "TST-MDB-1", slot=1), _sp(62, "LR-MDB-1", slot=4), _sp(42, "CR-CT-2-R1")]
    model, _ = _build(spools, "XL", spool=42)
    assert model["recommended"] == {"kind": "head", "head": "XL-4"}
    assert model["recommend_reason"] == "only_free"


def test_printer_mode_never_stars_the_head_the_spool_already_sits_on():
    """Group 40.3 review, D8: #42 is on XL-2 and every other choice is taken.
    XL-2 is where it is now, not "the only free choice" (Enter re-scanned it
    onto its own head)."""
    spools = [_sp(90 + i, h) for i, h in enumerate(XL_HEADS) if h != "XL-2"]
    spools += [_sp(61, "TST-MDB-1", slot=1), _sp(62, "LR-MDB-1", slot=4), _sp(42, "XL-2")]
    model, _ = _build(spools, "XL", spool=42)
    xl2 = next(h for h in model["heads"] if h["id"] == "XL-2")
    assert xl2["current"] is True and xl2["resident"] is None
    assert model["recommended"] is None and model["recommend_reason"] == "nothing_free", model["recommended"]


def test_core_one_is_its_own_head_with_its_feed_and_no_pool():
    spools = [_sp(99, "CORE1"), _sp(42, "CR-CT-2-R1")]
    model, _ = _build(spools, "CORE1", spool=42)
    assert model["mode"] == "printer" and model["self_head"] is True
    assert [h["id"] for h in model["heads"]] == ["CORE1"]
    assert model["heads"][0]["resident"]["id"] == 99
    assert model["heads"][0]["feeds"] == [{"box": "CR-MDB-1", "slot": "1", "spool": None,
                                          "claimed_by": None, "free": True}]
    assert model["pool"] == []


def test_a_printer_with_no_heads_says_where_to_add_them():
    model, status = _build([], "MK4", spool=42)
    assert status == 200 and model["heads"] == [] and model["pool"] == []
    assert "Settings → Toolheads" in model["msg"]


def test_printer_mode_blip_reads_as_unreadable():
    model, _ = _build([], "XL", spool=42, fail=True)
    assert model["read_ok"] is False and model["heads"] == [] and model["recommended"] is None


# ---- return mode (D5) ----------------------------------------------------------------------------

def test_return_recommends_the_slot_it_came_from_while_free():
    spools = [_sp(42, "XL-3", src="LR-MDB-1", src_slot=3)]
    model, _ = _build(spools, "LR-MDB-1", spool=42, toolhead="XL-3", mode="return")
    assert model["mode"] == "return" and model["allow_none"] is True
    assert model["recommended"] == {"kind": "slot", "box": "LR-MDB-1", "slot": "3"}
    assert model["recommend_reason"] == "recorded_slot"


def test_return_with_its_slot_taken_takes_a_free_slot_feeding_the_head_then_a_spare():
    rows = copy.deepcopy(ROWS)
    rows = [r for r in rows if r["LocationID"] != "TST-MDB-1"] + [
        _box("TST-MDB-1", 4, {"1": "XL-3", "2": "XL-3", "3": "PRINTER:XL"})]
    taken = [_sp(42, "XL-3", src="TST-MDB-1", src_slot=1), _sp(57, "TST-MDB-1", slot=1)]
    model, _ = _build(taken, "TST-MDB-1", rows=rows, spool=42, toolhead="XL-3", mode="return")
    assert model["recommended"]["slot"] == "2" and model["recommend_reason"] == "head_slot"
    assert model["recommend_text"] == "the free slot that feeds XL-3"

    both = taken + [_sp(58, "TST-MDB-1", slot=2)]
    model, _ = _build(both, "TST-MDB-1", rows=rows, spool=42, toolhead="XL-3", mode="return")
    assert model["recommended"]["slot"] == "3" and model["recommend_reason"] == "spare_slot"

    full = both + [_sp(59, "TST-MDB-1", slot=3), _sp(63, "TST-MDB-1", slot=4)]
    model, _ = _build(full, "TST-MDB-1", rows=rows, spool=42, toolhead="XL-3", mode="return")
    assert model["recommended"] == {"kind": "none", "box": "TST-MDB-1"}
    assert model["recommend_reason"] == "no_free_slot"


def test_return_never_recommends_a_slot_feeding_another_head_or_another_printers_pool():
    rows = [r for r in copy.deepcopy(ROWS) if r["LocationID"] != "TST-MDB-1"] + [
        _box("TST-MDB-1", 3, {"1": "XL-1", "2": "PRINTER:CORE1", "3": "XL-3"})]
    spools = [_sp(42, "XL-3"), _sp(57, "TST-MDB-1", slot=3)]
    model, _ = _build(spools, "TST-MDB-1", rows=rows, spool=42, toolhead="XL-3", mode="return")
    assert model["recommended"] == {"kind": "none", "box": "TST-MDB-1"}


# ---- refusals -------------------------------------------------------------------------------------

@pytest.mark.parametrize("location,kwargs,status,error", [
    ("NOPE", {}, 404, "not_found"),
    ("", {}, 404, "not_found"),
    ("XL-2", {}, 400, "not_pickable"),            # a toolhead: a spool goes straight there
    ("PM-DB-2", {}, 400, "not_pickable"),         # a single-slot box
    ("CR-CT-2-R1", {}, 400, "not_pickable"),
    ("XL", {"mode": "return", "toolhead": "XL-1"}, 400, "not_pickable"),
    ("LR-MDB-1", {"mode": "sideways"}, 400, "bad_mode"),
    ("LR-MDB-1", {"spool": "abc"}, 400, "bad_spool"),
])
def test_places_no_picker_opens_on_are_refused(location, kwargs, status, error):
    model, got = _build([], location, **kwargs)
    assert got == status and model["error"] == error and model["msg"]


# ---- the route --------------------------------------------------------------------------------------

def test_the_route_answers_the_model():
    rows = copy.deepcopy(ROWS)
    spools = [_sp(42, "CR-CT-2-R1"), _sp(57, "LR-MDB-1", slot=1)]
    with patch.object(placement.locations_db, "load_locations_list",
                      side_effect=lambda *a, **k: copy.deepcopy(rows)), \
         patch.object(placement.spoolman_api, "get_all_spools_strict",
                      side_effect=lambda *a, **k: copy.deepcopy(spools)), \
         patch.object(placement.locations_db, "is_descendant", return_value=False):
        client = app_module.app.test_client()
        r = client.get("/api/placement_options?location=lr-mdb-1&spool=42")
        assert r.status_code == 200
        body = r.get_json()
        assert body["mode"] == "box" and body["location"] == "LR-MDB-1"
        assert _slot(body, 1)["spool"]["id"] == 57
        assert body["recommended"]["slot"] == "2"
        r = client.get("/api/placement_options?location=XL-2")
        assert r.status_code == 400 and r.get_json()["error"] == "not_pickable"
