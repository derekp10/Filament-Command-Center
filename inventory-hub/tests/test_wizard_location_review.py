"""Group 40.7 review — the server half of the wizard Location fixes, through the
Flask client and the REAL move engine (tests/move_engine_harness.py; nothing here
mocks perform_smart_move, perform_force_unassign or _perform_smart_move_impl).

Findings pinned here (each test names its own):
  - wizard-resave-unloads-head: an edit whose move landed answers `location_now`,
    the LocationID the spool is filed on now (the head its slot loaded), and a
    Save of that moves nothing. The page puts it in the Location field (the
    browser half is in test_wizard_location_review_js.py).
  - wizard-archive-before-asked-move: an edit that archives the spool and changes
    its Location takes it off where it is first (location '', trail cleared, its
    single-slot box released), then moves it as a store, so no question and no
    refusal can leave an archived spool on a head; it stays archived where it
    lands.
  - wizard-refused-pick-resent: a refusal over the picker's own choice answers
    `pick_refused` (the page drops the choice); any other refusal doesn't.
  - wizard-slotless-create-loads-empty-head (belt and braces): a create's
    placement into a multi-slot box that names no slot is a store, never a load
    of the head the engine's chosen slot feeds.
  - wizard-stale-page-create-onto-head: a create without `placements` (a page
    from before 40.7) never puts a spool on a toolhead.
  - wizard-loop-undo-buffer-top (control): Undo of a 'wizard_create' move leaves
    the scan buffer alone; the browser's fix sends that origin.

Base proof (7976b72): every test fails there except the three marked "control"
in their docstrings, each on what happened to the spools or on the answer key
the fix adds (`location_now`, `pick_refused`).
Adopted from the reviewers' probes: test_probe_wizard_resave (its premise, a
second Save that still names the box, is the browser bug: here the second Save
names `location_now`, as the fixed page does), test_probe_wizard_archive_then_
question (its "asks first" precondition is gone by design: the spool leaves the
head before the move, so the move asks nothing about the head it left; the
question case is pinned with a destination that asks), test_probe_wizard_create_
typed_box, and the server half of test_probe_wizard_loop_undo_buffer (as the
control, with the origin the fixed page sends).
"""
from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

import spoolman_api  # noqa: E402
import state  # noqa: E402
from move_engine_harness import IDLE, FakeSpoolman, LocationsStore, WeighedWireSpoolman, _probe_for, run_move  # noqa: E402
from test_wizard_location_through_engine import DOOR, FROM_POLYDRYER, PRINTER_MAP, ROWS, _Maker  # noqa: E402


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


def _post(client, sm, url, body, probe=IDLE, store=None):
    return run_move(sm, probe=probe, store=store or LocationsStore(ROWS), printer_map=PRINTER_MAP,
                    call=lambda: client.post(url, json=body)).get_json()


def _edit(client, sm, spool_data, sid=57, probe=IDLE, store=None, **extra):
    return _post(client, sm, "/api/edit_spool_wizard", dict({"spool_id": sid, "spool_data": spool_data}, **extra),
                 probe=probe, store=store)


def _create(client, sm, body, probe=IDLE, store=None):
    maker = _Maker(sm)
    with patch.object(spoolman_api, "create_spool", side_effect=maker.create_spool), \
         patch.object(spoolman_api, "create_filament", side_effect=maker.create_filament):
        return _post(client, sm, "/api/create_inventory_wizard", body, probe=probe, store=store), maker


# ---- wizard-resave-unloads-head ---------------------------------------------------------

@pytest.mark.parametrize("target, fields, now", [
    ("LR-MDB-1", {"picked_slot": "1", "expected_feed": "XL-1"}, "XL-1"),     # the chain loaded XL-1
    ("LR-MDB-1", {"picked_slot": "4", "expected_feed": ""}, "LR-MDB-1"),     # a Printer Pool slot: stored
    ("", {}, ""),                                                             # Unassigned
], ids=["deployed", "stored", "unassigned"])
def test_a_landed_move_answers_location_now_and_saving_that_moves_nothing(client, target, fields, now):
    """Save 1 moves #57 and answers where it is now. Save 2 (only the comment
    changed) sends what the page now shows, `location_now`: nothing moves. The
    page used to keep the box in the field, and Save 2 stored #57 back in its
    slot, unloading XL-1 with no question (the reviewers' probe)."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}})
    store = LocationsStore(ROWS)
    first = _edit(client, sm, {"location": target, "comment": "a"}, store=store, **dict(fields, **DOOR))
    assert first["success"] is True and first["location_moved"] is True, first
    assert first["location_now"] == now and sm.spools[57]["location"] == now, (first, sm.spools)
    writes = len(sm.writes)

    second = _edit(client, sm, {"location": first["location_now"], "comment": "b"}, store=store, **DOOR)
    # `archived_now`: the page sets its Archived box from it (2026-10-20 review).
    assert second == {"success": True, "spool_id": 57, "archived_now": False}, second
    assert sm.writes[writes:] == [(57, {"comment": "b"})], sm.writes[writes:]
    assert sm.spools[57]["location"] == now, sm.spools


# ---- wizard-archive-before-asked-move ----------------------------------------------------

_WeighedSpoolman = WeighedWireSpoolman   # moved to the shared harness (Group 51.1)


def _on_xl1(trail, used=100):
    return _WeighedSpoolman({57: {"location": "XL-1", "initial_weight": 1000, "used_weight": used,
                                  "archived": False, "extra": dict(trail)}})


@pytest.mark.parametrize("new_loc", ["", "CR-CT-2-R1"])
def test_an_emptied_spool_moved_off_a_printing_head_is_taken_off_it_first(client, new_loc):
    """#57 runs on XL-1 from its PolyDryer PM-DB-2, and the XL is printing. The
    edit weighs it out to empty and sets the Location. The first write names
    XL-1, so the archive edge archived it IN PLACE, and the engine then asked
    about leaving a printing head: cancelled, or never answered, #57 stayed
    archived on XL-1 with its trail and its box attached (the reviewers' probe).
    Now it leaves XL-1 first, as any used-up spool does (unasked), and lands
    where the user asked, archived. No question, since it leaves no head."""
    sm = _on_xl1(FROM_POLYDRYER)
    store = LocationsStore(ROWS)
    body = _edit(client, sm, {"location": new_loc, "used_weight": 1000}, probe=_probe_for({"XL"}),
                 store=store, **DOOR)
    spool = sm.spools[57]
    assert not (spool.get("archived") and spool["location"] == "XL-1"), ("archived on XL-1", spool)
    assert spool["archived"] is True and spool["location"] == new_loc, spool
    assert spool["extra"]["physical_source"] == "" and spool["extra"]["physical_source_slot"] == "", spool
    assert store.bound("PM-DB-2") == "", "its PolyDryer still points at XL-1"
    assert body["success"] is True and body["location_moved"] is True, body
    assert body["location_now"] == new_loc, body
    # The archive edge's own outcome, minus the pre-archive note: the user asked
    # for the spool elsewhere, so a later refill mustn't put it back on XL-1.
    assert not spool["extra"].get("fcc_pre_archive_location"), spool


def test_an_emptied_spool_sent_to_a_head_is_refused_archived_and_unassigned(client):
    """The destination is a head (XL-2, printing). It used to ask about the
    print, and its Yes loaded the archived spool onto XL-2, where no reader of a
    head sees it. An archived spool is never loaded onto a head now (Group 51
    review, engine-1): refused before any question. #57 is off XL-1 already,
    archived and Unassigned, and `msg` says both."""
    sm = _on_xl1({"physical_source": "LR-MDB-1", "physical_source_slot": "1", "container_slot": ""})
    body = _edit(client, sm, {"location": "XL-2", "used_weight": 1000}, probe=_probe_for({"XL"}), **DOOR)
    assert body["location_result"]["status"] == "error", body
    assert body["location_result"]["blocked_reason"] == "archived", body
    assert body["success"] is False and body["location_moved"] is False, body
    spool = sm.spools[57]
    assert spool["archived"] is True and spool["location"] == "", spool
    assert spool["extra"]["physical_source"] == "", spool
    assert ("#57 is archived with no filament left on its record (0 g), so it was not loaded onto XL-2"
            in body["msg"]), body
    assert "#57 is archived (used up), so it was taken off XL-1: it is Unassigned." in body["msg"], body


def test_an_archived_ticked_spool_sent_to_a_head_stays_archived(client):
    """Archived ticked (300 g left) and the Location set to XL-2 in one Save.
    A head un-archives a spool with filament on its record to load it (Derek,
    2026-10-20), but not this one: the same Save archived it, so the move keeps
    it archived (`keep_archived`) and the answer says to untick Archived."""
    sm = _on_xl1({"physical_source": "LR-MDB-1", "physical_source_slot": "1", "container_slot": ""}, used=700)
    body = _edit(client, sm, {"location": "XL-2", "archived": True}, **DOOR)
    assert body["location_result"]["blocked_reason"] == "archived", body
    assert body["success"] is False and body["location_moved"] is False, body
    spool = sm.spools[57]
    assert spool["archived"] is True and spool["location"] == "", spool
    assert sm.direct_at("XL-2") == [], sm.spools
    assert "#57 is archived, so it was not loaded onto XL-2: untick Archived to load it" in body["msg"], body


def test_an_archived_ticked_spool_stays_archived_where_its_move_lands(client):
    """Archived ticked (weight left) and the Location changed, the XL idle. The
    move's own write used to unarchive it (update_spool read any write to an
    archived spool with weight left as a refill), so it landed on the cart row
    active and the wizard archived it again. Since Group 51.1 a move's write is
    no refill: it lands archived, with no second write."""
    sm = _on_xl1({"physical_source": "LR-MDB-1", "physical_source_slot": "1", "container_slot": ""})
    body = _edit(client, sm, {"location": "CR-CT-2-R1", "archived": True}, **DOOR)
    spool = sm.spools[57]
    assert spool["location"] == "CR-CT-2-R1" and spool["archived"] is True, spool
    assert body["success"] is True and body["location_now"] == "CR-CT-2-R1", body


def test_an_emptied_spool_moved_into_a_bound_slot_is_stored_not_loaded(client):
    """LR-MDB-1 slot 1 feeds XL-1, empty and idle: a spool moved there is loaded
    onto XL-1 by the chain, which for a used-up spool is the archived-on-a-head
    state again. It is stored in the slot; XL-1 stays empty."""
    sm = _WeighedSpoolman({57: {"location": "CR-CT-2-R1", "initial_weight": 1000, "used_weight": 100,
                                "archived": False, "extra": {}}})
    body = _edit(client, sm, {"location": "LR-MDB-1", "used_weight": 1000}, picked_slot="1",
                 expected_feed="XL-1", **DOOR)
    spool = sm.spools[57]
    assert sm.direct_at("XL-1") == [], sm.spools
    assert spool["location"] == "LR-MDB-1" and spool["extra"]["container_slot"] == "1", spool
    assert spool["archived"] is True and body["location_now"] == "LR-MDB-1", body


# ---- wizard-refused-pick-resent ----------------------------------------------------------

def test_a_picked_slot_taken_meanwhile_is_a_refused_pick(client):
    """The picker chose LR-MDB-1 slot 2; #77 was stored there before Save."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}},
                       77: {"location": "LR-MDB-1", "extra": {"container_slot": "2"}}})
    body = _edit(client, sm, {"location": "LR-MDB-1"}, picked_slot="2", expected_feed="XL-2", **DOOR)
    assert body["location_result"]["blocked_reason"] == "picked_slot_taken", body
    assert body["success"] is False and body.get("pick_refused") is True, body
    assert sm.spools[57]["location"] == "CR-CT-2-R1"


def test_a_named_slot_whose_own_spool_runs_on_a_head_is_a_refused_pick(client):
    """The picker's slot 2 of CR-MDB-1 (Overwrite / Swap: an explicit `slot`) is
    claimed by #60, which was deployed from it to XL-3 meanwhile: the engine's
    ghost guard refuses it with `blocked_reason: slot_claimed` (Group 51.3; the
    server used to tell it by its words), and the page drops the pick."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}},
                       60: {"location": "XL-3", "extra": {"physical_source": "CR-MDB-1",
                                                          "physical_source_slot": "2", "container_slot": ""}}})
    body = _edit(client, sm, {"location": "CR-MDB-1"}, slot="2", expected_feed="", **DOOR)
    assert body["location_moved"] is False, body
    assert "CR-MDB-1 slot 2 still holds #60, loaded on XL-3" in body["msg"], body
    assert body["location_result"]["blocked_reason"] == "slot_claimed", body
    assert body.get("pick_refused") is True, body


def test_a_refusal_that_isnt_about_the_pick_keeps_it(client):
    """Control (passes on the base too): Spoolman rejects #57's write. Saving
    again may work, so the page keeps the pick: no `pick_refused`."""
    sm = FakeSpoolman({57: {"location": "CR-CT-2-R1", "extra": {}}}, reject_ids=(57,))
    body = _edit(client, sm, {"location": "LR-MDB-1"}, picked_slot="2", expected_feed="XL-2", **DOOR)
    assert body["location_moved"] is False and "rejected by test" in body["msg"], body
    assert "pick_refused" not in body, body


# ---- wizard-slotless-create-loads-empty-head (server belt and braces) --------------------

_TWO_HEADS_RUN = {
    60: {"location": "XL-2", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "2",
                                       "container_slot": ""}},
    61: {"location": "XL-3", "extra": {"physical_source": "LR-MDB-1", "physical_source_slot": "3",
                                       "container_slot": ""}},
}


@pytest.mark.parametrize("with_placements", [True, False], ids=["40.7-page", "older-page"])
def test_a_slotless_create_into_a_bound_box_stores_the_new_spool(client, with_placements):
    """LR-MDB-1: slot 1 -> XL-1 (EMPTY), 2 and 3 run their own spools, 4 is the
    pool. A create into LR-MDB-1 that names no slot (a Clone's pre-fill, a Tab,
    or a page from before 40.7) took slot 1 and loaded the sealed spool onto
    XL-1 with no question (the reviewers' probe). It is stored there now."""
    sm = FakeSpoolman(copy.deepcopy(_TWO_HEADS_RUN))
    body = {"filament_id": 7, "quantity": 1, "spool_data": {"location": "LR-MDB-1", "extra": {}}}
    if with_placements:
        body = dict(body, placements=[{"location": "LR-MDB-1"}], **DOOR)
    out, _ = _create(client, sm, body)
    assert sm.spools[501]["location"] == "LR-MDB-1", ("loaded onto a head", out, sm.spools[501])
    assert sm.direct_at("XL-1") == [], sm.spools
    assert out["placed"] == {"501": "LR-MDB-1 slot 1"}, out
    assert out["placement_requests"]["501"].get("auto_deploy") is False, out


def test_a_create_into_a_picked_slot_still_loads_its_head(client):
    """Control (passes on the base too): the picker named slot 1, so the chain
    loads XL-1 as the user chose; only a slotless placement stores."""
    sm = FakeSpoolman(copy.deepcopy(_TWO_HEADS_RUN))
    out, _ = _create(client, sm, dict({
        "filament_id": 7, "quantity": 1, "spool_data": {"location": "LR-MDB-1", "extra": {}},
        "placements": [{"location": "LR-MDB-1", "picked_slot": "1", "expected_feed": "XL-1"}]}, **DOOR))
    assert sm.direct_at("XL-1") == [501] and out["placed"] == {"501": "LR-MDB-1 slot 1 → XL-1"}, out


# ---- wizard-stale-page-create-onto-head --------------------------------------------------

@pytest.mark.parametrize("head", ["XL-1", "CORE1"])
def test_a_page_from_before_40_7_never_creates_onto_a_toolhead(client, head):
    """An older page's reset left the last edited spool's head in its hidden
    Location, so it can send XL-1 while showing Unassigned. The engine's Smart
    Load would send #99 home and file the sealed spool on the head, unasked
    while idle. The new spool is created Unassigned, and `warning` (which an
    older page toasts for 7 s) says to reload."""
    sm = FakeSpoolman({99: {"location": head, "extra": dict(FROM_POLYDRYER)}})
    out, maker = _create(client, sm, {"filament_id": 7, "quantity": 1,
                                      "spool_data": {"location": head, "extra": {}}})
    assert sm.direct_at(head) == [99] and sm.spools[501]["location"] == "", sm.spools
    assert out["success"] is True and out["created_spools"] == [501] and out["unplaced"] == [501], out
    assert out["placed"] == {} and out["placements_ok"] is False, out
    assert out["warning"] == (f"#501 was created but is Unassigned, not on {head}: this page is out of date, so "
                              f"FCC won't load {head} from it. Reload the page (Ctrl+F5), then scan #501 onto "
                              f"{head}."), out
    assert any("this page is out of date" in str(e.get("msg")) for e in state.RECENT_LOGS), state.RECENT_LOGS


def test_a_40_7_page_still_creates_onto_a_toolhead_through_the_engine(client):
    """Control (passes on the base too): a page that sends `placements` (the
    Printer picker's head) gets Smart Load: #99 goes home, #501 is loaded."""
    sm = FakeSpoolman({99: {"location": "XL-1", "extra": dict(FROM_POLYDRYER)}})
    out, _ = _create(client, sm, dict({"filament_id": 7, "quantity": 1,
                                       "spool_data": {"location": "XL-1", "extra": {}},
                                       "placements": [{"location": "XL-1"}]}, **DOOR))
    assert sm.direct_at("XL-1") == [501] and sm.spools[99]["location"] == "PM-DB-2", sm.spools
    assert out["placed"] == {"501": "XL-1"}, out


# ---- wizard-loop-undo-buffer-top (server contract) ---------------------------------------

def test_undo_of_a_wizard_create_move_leaves_the_buffer_as_it_was(client):
    """Control (passes on the base too: the fix is the page's origin). The
    per-spool picker loop's move, sent as the fixed page sends it (origin
    'wizard_create'), then Undo: the never-buffered new spool goes back to
    Unassigned and the buffer keeps only what was in it. With origin 'buffer'
    (performContextAssign's default) Undo put #502 at the TOP of the buffer, the
    spool the next toolhead scan loads (the reviewers' probe)."""
    state.GLOBAL_BUFFER = [{"id": 57, "display": "#57"}]
    sm = FakeSpoolman({57: {"location": "", "extra": {}}, 502: {"location": "", "extra": {}}})
    store = LocationsStore(ROWS)
    placed = _post(client, sm, "/api/smart_move", {
        "location": "CR-MDB-1", "spools": [502], "slot": None, "origin": "wizard_create",
        "confirmed_toolheads": [], "confirmed_fed_heads": [], "picked_slot": "3", "expected_feed": ""}, store=store)
    assert placed["status"] == "success" and sm.spools[502]["location"] == "CR-MDB-1", placed
    asked = _post(client, sm, "/api/undo", {}, store=store)
    _post(client, sm, "/api/undo", {"confirm": True, "undo_id": asked.get("undo_id"),
                                    "confirmed_toolheads": []}, store=store)
    assert sm.spools[502]["location"] == "", sm.spools
    assert [b["id"] for b in state.GLOBAL_BUFFER] == [57], state.GLOBAL_BUFFER


# ---- 2026-10-20 review: in the wizard the form's Archived box decides -----------------------

class _ArchivingMaker(_Maker):
    """_Maker that keeps what Spoolman would: the weights and `archived`."""

    def create_spool(self, data):
        res = super().create_spool(data)
        rec = self.sm.spools[res["id"]]
        for key in ("initial_weight", "used_weight", "archived"):
            if key in data:
                rec[key] = data[key]
        return res


def _hand_archived(location="CR-CT-2-R1"):
    """#57 archived by hand with 300 g left on its record."""
    return _WeighedSpoolman({57: {"location": location, "initial_weight": 1000, "used_weight": 700,
                                  "archived": True, "extra": {}}})


def test_a_ticked_archived_box_keeps_the_spool_off_a_head(client):
    """engine-1: the box is still ticked (the prefill, not dirty) and the
    Location set to XL-2. RED on b779b84: the move un-archived and loaded it, and
    the next Save of the same page (the box still ticked) archived it ON XL-2."""
    sm = _hand_archived()
    body = _edit(client, sm, {"location": "XL-2", "archived": True}, **DOOR)
    assert body["location_result"]["blocked_reason"] == "archived", body
    assert "#57 is archived, so it was not loaded onto XL-2: untick Archived to load it" in body["msg"], body
    assert body["archived_now"] is True, body
    assert sm.spools[57]["location"] == "CR-CT-2-R1" and sm.spools[57]["archived"] is True, sm.spools[57]
    assert sm.direct_at("XL-2") == []


def test_unticking_archived_with_a_head_loads_it_in_stock(client):
    """The way to load it from the wizard: untick Archived. (On b779b84 it fails
    only on the answer's new `archived_now`.)"""
    sm = _hand_archived()
    body = _edit(client, sm, {"location": "XL-2", "archived": False}, **DOOR)
    assert body["success"] is True and body["location_now"] == "XL-2", body
    assert body["archived_now"] is False, body
    assert sm.spools[57]["archived"] is False and sm.direct_at("XL-2") == [57], sm.spools[57]


def test_ticking_archived_on_an_unassigned_spool_sent_to_a_head_is_refused(client):
    """engine-2 (a): nothing to take it off (it was Unassigned), so keep_archived
    used to be False and the same Save un-archived it onto XL-2. RED on b779b84."""
    sm = _WeighedSpoolman({57: {"location": "", "initial_weight": 1000, "used_weight": 700,
                                "archived": False, "extra": {}}})
    body = _edit(client, sm, {"location": "XL-2", "archived": True}, **DOOR)
    assert body["location_result"]["blocked_reason"] == "archived", body
    assert body["archived_now"] is True, body
    assert sm.spools[57]["archived"] is True and sm.direct_at("XL-2") == [], sm.spools[57]


def test_a_save_that_archives_a_spool_on_a_head_takes_it_off(client):
    """engine-1's belt: ticking Archived on #57 on XL-1 with no Location change
    used to archive it ON XL-1, invisible to Smart Load and the print charge.
    Now it is taken off, as an archive-and-move is. RED on b779b84."""
    sm = _on_xl1({"physical_source": "LR-MDB-1", "physical_source_slot": "1", "container_slot": ""}, used=700)
    body = _edit(client, sm, {"location": "XL-1", "archived": True}, **DOOR)
    spool = sm.spools[57]
    assert spool["archived"] is True and spool["location"] == "", spool
    assert spool["extra"]["physical_source"] == "", spool
    assert body["success"] is True and body["location_now"] == "" and body["archived_now"] is True, body
    assert "#57 is archived (Archived is ticked), so it was taken off XL-1: it is Unassigned." in body["warning"], body


def test_control_ticking_archived_on_a_shelf_leaves_it_filed_there(client):
    """Control: off a head, a Save that archives a spool leaves it where it is.
    (On b779b84 it fails only on the answer's new `archived_now`.)"""
    sm = _WeighedSpoolman({57: {"location": "CR-CT-2-R1", "initial_weight": 1000, "used_weight": 700,
                                "archived": False, "extra": {}}})
    body = _edit(client, sm, {"location": "CR-CT-2-R1", "archived": True}, **DOOR)
    assert body["success"] is True and "location_now" not in body and body["archived_now"] is True, body
    assert sm.spools[57]["location"] == "CR-CT-2-R1" and sm.spools[57]["archived"] is True


def test_a_create_ticked_archived_onto_a_head_stays_archived_and_unassigned(client):
    """engine-2 (c): the create door passed no keep_archived, so a new spool made
    archived and placed on XL-2 was un-archived onto it. RED on b779b84."""
    sm = _WeighedSpoolman({})
    maker = _ArchivingMaker(sm)
    body = dict({"filament_id": 7, "quantity": 1,
                 "spool_data": {"location": "XL-2", "archived": True, "initial_weight": 1000, "used_weight": 0,
                                "extra": {}},
                 "placements": [{"location": "XL-2"}]}, **DOOR)
    with patch.object(spoolman_api, "create_spool", side_effect=maker.create_spool), \
         patch.object(spoolman_api, "create_filament", side_effect=maker.create_filament):
        out = _post(client, sm, "/api/create_inventory_wizard", body)
    assert out["unplaced"] == [501], out
    assert out["location_results"]["501"]["blocked_reason"] == "archived", out
    assert sm.spools[501]["archived"] is True and sm.direct_at("XL-2") == [], sm.spools[501]
