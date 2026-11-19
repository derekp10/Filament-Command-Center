"""Group 63.1 / 63.2 / 63.4: what an archived spool remembers, and where a refill puts it.

The archive edge (`spoolman_api._auto_archive_on_empty`) writes the place a spool
left into its "Pre-Archive Location (system)" note; the refill edge
(`_refill_outcome`, behind `_auto_unarchive_on_refill`) reads it when a weigh (or
an untick of Archived) brings the spool back into stock.

Derek, 2026-11-18 (the group's first call, and its follow-up): *"I think if we ask
on a spool correction that adds weight back, to either place it back where it was
(Possibly a toolhead) or just assign to the room for now, or possibly scann/select
a new location from a list. would probably be the best option instead of just auto
assigning"*, then *"I'd say only after a tool head"*. So:
  - the note keeps the place it left, a toolhead included (the question offers it);
  - a refill after a toolhead moves the spool nowhere: it stays Unassigned and
    update_spool's answer carries `fcc_refill_ask` (the head, its room, the spools
    on it now) for the page to ask with (test_one_spool_per_toolhead_42_3 too);
  - a refill after a box, cart or shelf goes back there, as before.

Claude's calls (no veto, 2026-11-18), pinned here:
  1. a spool moved while archived stays where it was moved when refilled;
  2. Unknown is never a home: no note at Unknown, an old "UNKNOWN" note reads as none;
  3. a spool that leaves the archive uses its note up (a refill naming a place, an
     untick at 0 g), and Undo doesn't bring back a note the move used up;
  4. every archive writes its note, so no older note outlives it (dev's #108 holds
     "PJ-CT-1" while filed at CR-CT-2-R2).
63.4: the archive edge uses the before-the-box note up (42.6's rule for any move).
63.2's protection: a refill never lands where another spool is now: a single-slot
dryer box or a Max Spools 1 row another spool is in (or was deployed from), a box
slot another spool claims, a place FCC can't read; a spool archived ON a head is
taken off it and asked about.

The REAL update_spool runs over tests/deduct_wire_harness.WeightWireSpoolman (only
requests.get / requests.patch answered, extras stored as Spoolman 0.27 stores
them); Undo runs the REAL engine over tests/move_engine_harness.
Tests marked RED fail on dev @ e1b22f4 (the branch's base).
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import ExitStack
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402
import routes_inventory  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman  # noqa: E402
import move_engine_harness as meh  # noqa: E402

PRINTER_MAP = {
    "XL-1": {"printer_name": "XL", "position": 0},
    "XL-2": {"printer_name": "XL", "position": 1},
}
LOCATIONS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "XL-1", "position": 0}, {"location_id": "XL-2", "position": 1}]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "PM-DB-9", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {}}},
    {"LocationID": "CR-CT-2-R2", "Type": "Cart Row", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "PJ-CT-1", "Type": "Cart", "Max Spools": "0", "parent_id": "CR"},
    {"LocationID": "CR-SHELF-1", "Type": "Shelf", "Max Spools": "1", "parent_id": "CR"},
]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(state, "GLOBAL_BUFFER", [])
    monkeypatch.setattr(state, "BULK_MOVE_SESSION", {"active": False})
    monkeypatch.setattr(state, "AUDIT_SESSION", {"active": False})


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _spool(location="", *, archived=False, used=700, note=None, sid=57, **extra):
    ex = dict(extra)
    if note is not None:
        ex["fcc_pre_archive_location"] = note
    return {sid: {"location": location, "archived": archived, "initial_weight": 1000, "used_weight": used,
                  "filament": {"weight": 1000}, "extra": ex}}


def _wire(sm, residents=None, read_fails=False):
    """The real update_spool over the wire. The strict location read answers from
    `residents` ({LOC: [id | item dict]}); a bare id is a spool filed there."""
    reads, detached = [], []

    def strict(loc):
        reads.append(str(loc).upper())
        if read_fails:
            raise spoolman_api.requests.ConnectionError("Spoolman unreachable (test)")
        out = []
        for it in (residents or {}).get(str(loc).upper(), []):
            out.append(dict(it) if isinstance(it, dict)
                       else {"id": it, "location": str(loc).upper(), "is_ghost": False, "slot": ""})
        return out

    ctx = [
        patch.object(spoolman_api.requests, "get", side_effect=sm._get),
        patch.object(spoolman_api.requests, "patch", side_effect=sm._patch),
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(spoolman_api.locations_db, "get_active_printer_map", return_value=PRINTER_MAP),
        patch.object(spoolman_api.locations_db, "load_locations_list", return_value=LOCATIONS),
        patch.object(spoolman_api, "get_spools_at_location_detailed_strict", side_effect=strict),
        patch.object(spoolman_api.locations_db, "detach_single_slot_box",
                     side_effect=lambda box, head: detached.append((box, head)) or True),
    ]
    return ctx, reads, detached


def _write(sm, ctx, data, sid=57):
    with ExitStack() as st:
        for p in ctx:
            st.enter_context(p)
        return spoolman_api.update_spool(sid, dict(data))


def _body(sm, n=-1):
    return sm.patches[n][1]


def _note(sm, sid=57):
    return sm.spools[sid]["extra"].get("fcc_pre_archive_location")


# ---- the note an archive writes ----------------------------------------------------------------------

def test_control_an_archive_off_a_toolhead_keeps_the_head_as_its_note(logs):
    """Control (green on e1b22f4): the note names the head, so a refill can offer it."""
    sm = WeightWireSpoolman(_spool("XL-1"))
    ctx, _r, _d = _wire(sm)
    assert _write(sm, ctx, {"used_weight": 1000}) is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    assert sm.spools[57]["archived"] is True and sm.spools[57]["location"] == ""
    assert _note(sm) == "XL-1"


@pytest.mark.parametrize("older", [None, "LR-MDB-1"], ids=["no-older-note", "older-note"])
def test_an_archive_at_unknown_notes_nothing(logs, older):
    """Claude's call 2: Unknown is never a home. RED on e1b22f4: the note said
    "UNKNOWN", and a refill sent the spool back to the lost list."""
    sm = WeightWireSpoolman(_spool("UNKNOWN", note=older))
    ctx, _r, _d = _wire(sm)
    assert _write(sm, ctx, {"used_weight": 1000}) is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    assert sm.spools[57]["archived"] is True and sm.spools[57]["location"] == ""
    if older is None:
        assert "fcc_pre_archive_location" not in _body(sm).get("extra", {}), _body(sm)
    else:
        assert _note(sm) == "", "the older note can't outlive this archive (call 4)"


def test_an_archive_in_place_clears_an_older_note_and_a_refill_leaves_it_there(logs):
    """The #108 shape (Claude's call 4, then call 1): in stock at CR-CT-2-R2 with an
    old note "PJ-CT-1", archived where it is by a tick (no weight), then weighed
    back. RED on e1b22f4: the tick kept "PJ-CT-1", and the refill moved the spool
    to PJ-CT-1."""
    sm = WeightWireSpoolman(_spool("CR-CT-2-R2", note="PJ-CT-1"))
    ctx, _r, _d = _wire(sm)
    assert _write(sm, ctx, {"archived": True}) is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    assert sm.spools[57]["archived"] is True and sm.spools[57]["location"] == "CR-CT-2-R2"
    assert _note(sm) == ""
    assert _write(sm, ctx, {"used_weight": 600}) is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    assert sm.spools[57]["archived"] is False and sm.spools[57]["location"] == "CR-CT-2-R2"


def test_the_archive_edge_uses_the_before_the_box_note_up(logs):
    """63.4: the archive is a move to Unassigned, and 42.6's rule uses the
    before-the-box note up on any move elsewhere. RED on e1b22f4: the edge left it,
    and only the weigh page's force-unassign (its redundant WARNING line) used it up."""
    sm = WeightWireSpoolman(_spool("XL-1", fcc_pre_box_location="CR-CT-2-R2", physical_source="PM-DB-9",
                                   physical_source_slot="1"))
    ctx, _r, detached = _wire(sm)
    assert _write(sm, ctx, {"used_weight": 1000}) is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    extra = sm.spools[57]["extra"]
    assert extra["fcc_pre_box_location"] == "" and extra["physical_source"] == "", extra
    assert _note(sm) == "XL-1"
    assert detached == [("PM-DB-9", "XL-1")], detached


def test_control_a_spool_with_no_box_note_gets_none(logs):
    sm = WeightWireSpoolman(_spool("XL-1"))
    ctx, _r, _d = _wire(sm)
    _write(sm, ctx, {"used_weight": 1000})
    assert "fcc_pre_box_location" not in _body(sm)["extra"], _body(sm)


def test_control_an_archived_spool_weighed_to_nothing_again_keeps_its_note(logs):
    """Control: weighed to 0 g again while archived and Unassigned, it left no place
    now, so its note stays."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="LR-MDB-1"))
    ctx, _r, _d = _wire(sm)
    assert _write(sm, ctx, {"used_weight": 1000}) is not None, spoolman_api.LAST_SPOOLMAN_ERROR
    assert _note(sm) == "LR-MDB-1"


def test_the_wizards_take_off_writes_an_empty_note_and_uses_the_box_note_up(logs):
    """The wizard's take-off of a spool its Save archived (moving it elsewhere) goes
    through the same rule: no place noted, an older note cleared, the box note used
    up. RED on e1b22f4: both notes stayed."""
    sm = WeightWireSpoolman(_spool("XL-1", archived=True, used=1000, note="PJ-CT-1",
                                   fcc_pre_box_location="CR-CT-2-R2"))
    ctx, _r, _d = _wire(sm)
    original = {"id": 57, "location": "XL-1", "archived": False,
                "extra": {"fcc_pre_archive_location": "PJ-CT-1", "fcc_pre_box_location": "CR-CT-2-R2"}}
    with ExitStack() as st:
        for p in ctx:
            st.enter_context(p)
        st.enter_context(patch.object(routes_inventory.logic, "release_box_after_direct_write"))
        st.enter_context(patch.object(routes_inventory.locations_db, "get_active_printer_map",
                                      return_value=PRINTER_MAP))
        took = routes_inventory._take_archived_off(57, original, {"archived": True}, {"archived": True})
    assert took == "XL-1"
    extra = sm.spools[57]["extra"]
    assert extra["fcc_pre_archive_location"] == "" and extra["fcc_pre_box_location"] == "", extra
    assert sm.spools[57]["location"] == ""


# ---- where a refill puts it ----------------------------------------------------------------------------

def test_an_old_unknown_note_reads_as_none(logs):
    """Claude's call 2. RED on e1b22f4: "UNKNOWN" has no row, so the refill read
    the lost list and warned that "UNKNOWN no longer exists"."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="UNKNOWN"))
    ctx, reads, _d = _wire(sm)
    out = _write(sm, ctx, {"used_weight": 600})
    assert out is not None and not out.get("fcc_warning") and not out.get("fcc_refill_ask"), out
    assert sm.spools[57]["archived"] is False and sm.spools[57]["location"] == ""
    assert _note(sm) == "" and reads == []


def test_a_spool_moved_while_archived_stays_where_it_was_moved(logs):
    """Claude's call 1. RED on e1b22f4: the refill dragged it back to LR-MDB-1."""
    sm = WeightWireSpoolman(_spool("CR-CT-2-R2", archived=True, used=1000, note="LR-MDB-1"))
    ctx, _r, _d = _wire(sm)
    out = _write(sm, ctx, {"used_weight": 600})
    assert out is not None and not out.get("fcc_warning"), out
    assert sm.spools[57]["archived"] is False and sm.spools[57]["location"] == "CR-CT-2-R2"
    assert _note(sm) == ""


def test_a_refill_naming_a_place_uses_the_note_up(logs):
    """Claude's call 3. RED on e1b22f4: the caller's place won, but the note stayed."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="LR-MDB-1"))
    ctx, _r, _d = _wire(sm)
    assert _write(sm, ctx, {"used_weight": 600, "location": "CR-CT-2-R2"}) is not None
    assert sm.spools[57]["location"] == "CR-CT-2-R2" and _note(sm) == ""


def test_an_untick_at_nothing_left_uses_the_note_up(logs):
    """Claude's call 3. RED on e1b22f4: an untick of a spool still at 0 g kept it."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="LR-MDB-1"))
    ctx, _r, _d = _wire(sm)
    assert _write(sm, ctx, {"archived": False}) is not None
    assert sm.spools[57]["archived"] is False and sm.spools[57]["location"] == ""
    assert _note(sm) == ""


def test_control_a_refill_after_a_box_goes_back_there(logs):
    """Control (green on e1b22f4): a box, cart or shelf is restored as before."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="LR-MDB-1"))
    ctx, reads, _d = _wire(sm)
    out = _write(sm, ctx, {"used_weight": 600})
    assert out is not None and not out.get("fcc_warning") and not out.get("fcc_refill_ask"), out
    assert sm.spools[57]["location"] == "LR-MDB-1" and _note(sm) == "" and reads == []


# ---- 63.2's protection: never where another spool is now ---------------------------------------------

@pytest.mark.parametrize("held", [
    [12],
    [{"id": 12, "location": "PM-DB-9", "is_ghost": True, "slot": "1", "deployed_to": "XL-2"}],
], ids=["filed-there", "deployed-from-there"])
def test_a_refill_never_goes_back_into_a_one_spool_box_another_spool_holds(logs, held):
    """RED on e1b22f4: a dryer box was restored with no read, so #57 went back into
    the PolyDryer beside #12 (deployed from it or not: either is in the box)."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="PM-DB-9"))
    ctx, reads, _d = _wire(sm, residents={"PM-DB-9": held})
    out = _write(sm, ctx, {"used_weight": 600})
    assert out["fcc_warning"] == ("#57 is back in stock (400 g), but PM-DB-9 now holds #12, "
                                  "so it is Unassigned — scan it to where you put it."), out
    assert sm.spools[57]["location"] == "" and reads == ["PM-DB-9"]
    assert any(m == f"⚠️ {out['fcc_warning']}" for m, _a in logs), logs


def test_a_refill_never_goes_back_onto_a_one_spool_row_another_spool_is_on(logs):
    """A row whose Max Spools is 1. RED on e1b22f4 (restored with no read)."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="CR-SHELF-1"))
    ctx, _r, _d = _wire(sm, residents={"CR-SHELF-1": [12]})
    out = _write(sm, ctx, {"used_weight": 600})
    assert "CR-SHELF-1 now holds #12, so it is Unassigned" in out["fcc_warning"], out
    assert sm.spools[57]["location"] == ""


def test_control_a_free_one_spool_box_takes_it_back(logs):
    """Control for the spool's place (back in PM-DB-9 on e1b22f4 too); RED there only
    for the read, since a dryer box was restored with none."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="PM-DB-9"))
    ctx, reads, _d = _wire(sm)
    out = _write(sm, ctx, {"used_weight": 600})
    assert not out.get("fcc_warning") and sm.spools[57]["location"] == "PM-DB-9", out
    assert reads == ["PM-DB-9"]


def test_a_spool_archived_on_a_head_is_taken_off_and_asked_about(logs):
    """63.2's spool: FCC couldn't take it off XL-1, so it is archived there with its
    trail (from PM-DB-9, attached to XL-1). Weighed back, it is taken off the head,
    its trail cleared and PM-DB-9 released, and the page asks where it goes. RED on
    e1b22f4: it came back in stock on XL-1, beside whatever was loaded since."""
    sm = WeightWireSpoolman(_spool("XL-1", archived=True, used=1000, physical_source="PM-DB-9",
                                   physical_source_slot="1"))
    ctx, _r, detached = _wire(sm, residents={"XL-1": [99]})
    out = _write(sm, ctx, {"used_weight": 600})
    assert out["fcc_refill_ask"] == {"place": "XL-1", "room": "LR", "held_by": [99]}, out
    rec = sm.spools[57]
    assert rec["archived"] is False and rec["location"] == "", rec
    assert rec["extra"]["physical_source"] == "" and rec["extra"]["physical_source_slot"] == "", rec
    assert detached == [("PM-DB-9", "XL-1")], detached
    assert any("weighed back into stock off it" in m for m, _a in logs), logs


def test_a_spool_archived_in_a_box_slot_another_spool_claims_now_goes_unassigned(logs):
    """63.2's spool in LR-MDB-1 slot 2, which #12 holds now. RED on e1b22f4: it came
    back in stock claiming slot 2 beside #12."""
    sm = WeightWireSpoolman(_spool("LR-MDB-1", archived=True, used=1000, container_slot="2"))
    ctx, _r, _d = _wire(sm, residents={"LR-MDB-1": [
        {"id": 12, "location": "LR-MDB-1", "is_ghost": False, "slot": "2"}]})
    out = _write(sm, ctx, {"used_weight": 600})
    assert "LR-MDB-1 slot 2 now holds #12, so it is Unassigned" in out["fcc_warning"], out
    rec = sm.spools[57]
    assert rec["location"] == "" and rec["extra"]["container_slot"] == "", rec


def test_control_a_spool_archived_in_a_free_box_slot_stays(logs):
    sm = WeightWireSpoolman(_spool("LR-MDB-1", archived=True, used=1000, container_slot="2"))
    ctx, _r, _d = _wire(sm, residents={"LR-MDB-1": [
        {"id": 12, "location": "LR-MDB-1", "is_ghost": False, "slot": "3"}]})
    out = _write(sm, ctx, {"used_weight": 600})
    assert not out.get("fcc_warning"), out
    assert sm.spools[57]["location"] == "LR-MDB-1" and sm.spools[57]["extra"]["container_slot"] == "2"


def test_a_one_spool_place_fcc_cant_read_counts_as_taken(logs):
    """RED on e1b22f4 (a spool archived in a single-slot box came back there unread)."""
    sm = WeightWireSpoolman(_spool("PM-DB-9", archived=True, used=1000, container_slot="1"))
    ctx, _r, _d = _wire(sm, read_fails=True)
    out = _write(sm, ctx, {"used_weight": 600})
    assert "FCC couldn't read PM-DB-9 from Spoolman, so it is Unassigned" in out["fcc_warning"], out
    assert sm.spools[57]["location"] == ""


# ---- Undo brings no used-up note back (Claude's call 3) ----------------------------------------------

def test_undo_of_a_load_that_unarchived_a_spool_brings_no_note_back(logs):
    """An archived spool with 300 g left, filed at CR-CT-2-R2 with an old note, is
    loaded onto XL-2: the engine un-archives it and uses the note up. Undo puts it
    back at CR-CT-2-R2, in stock (Undo never re-archives), and its note stays used
    up. RED on e1b22f4: Undo wrote "LR-MDB-1" back from its snapshot."""
    store = meh.LocationsStore(LOCATIONS)
    sm = meh.WeighedWireSpoolman({57: {"location": "CR-CT-2-R2", "archived": True, "initial_weight": 1000,
                                       "used_weight": 700, "extra": {"fcc_pre_archive_location": "LR-MDB-1"}}})
    res = meh.run_move(sm, probe=meh.IDLE, store=store, printer_map=PRINTER_MAP, target="XL-2", raw_spools=[57])
    assert logic.smart_move_failure(res, 57) == "", res
    assert sm.spools[57]["archived"] is False and sm.spools[57]["location"] == "XL-2"
    assert sm.spools[57]["extra"]["fcc_pre_archive_location"] == ""
    record = state.UNDO_STACK[-1]
    out = meh.run_move(sm, probe=meh.IDLE, store=store, printer_map=PRINTER_MAP,
                       call=lambda: logic.perform_undo(expected_id=record["id"]))
    assert out["success"] is True, out
    assert sm.spools[57]["location"] == "CR-CT-2-R2" and sm.spools[57]["archived"] is False
    assert sm.spools[57]["extra"]["fcc_pre_archive_location"] == "", sm.spools[57]["extra"]


# ---- Group 63 review ----------------------------------------------------------------------------------

def _unreadable_locations(shape):
    """locations.json as FCC fails to read it: corrupt (load_locations_list raises),
    or refused by the disk (it answers [] and says so, locations_db.last_read_failed)."""
    if shape == "corrupt":
        def load(*a, **k):
            raise spoolman_api.locations_db.LocationsCorruptError(
                "data/locations.json", json.JSONDecodeError("Expecting value (test)", "{", 1))
    else:
        def load(*a, **k):
            flag = getattr(spoolman_api.locations_db, "_LAST_READ", None)   # (none before the fix)
            if flag is not None:
                flag.failed = True
            return []
    return patch.object(spoolman_api.locations_db, "load_locations_list", side_effect=load)


@pytest.mark.parametrize("shape", ["corrupt", "disk-refused"])
def test_a_spool_archived_on_a_head_fcc_cant_read_the_places_for_is_taken_off(logs, shape):
    """K18 / K35. 63.2's spool, archived ON XL-1 (from PM-DB-9) with #99 loaded there
    since, is weighed back while locations.json can't be read: FCC can't tell what
    XL-1 is, so it is taken off with the 42.3c warning, as a place it can't read is
    taken (the note branch already did this). RED on 8153b81: it came back in stock
    on XL-1, its trail kept, beside #99, with no warning; the disk-refused shape read
    the [] as "no such head" the same way."""
    sm = WeightWireSpoolman(_spool("XL-1", archived=True, used=1000, physical_source="PM-DB-9",
                                   physical_source_slot="1"))
    ctx, _r, _d = _wire(sm, residents={"XL-1": [99]})
    # The printer map is read from the same file, so it fails with it.
    ctx = [p for p in ctx if getattr(p, "attribute", "") not in ("load_locations_list", "get_active_printer_map")]
    ctx.append(_unreadable_locations(shape))
    try:
        out = _write(sm, ctx, {"used_weight": 600})
    finally:
        flag = getattr(spoolman_api.locations_db, "_LAST_READ", None)
        if flag is not None:
            flag.failed = False
    assert "FCC couldn't check where it was, so it is Unassigned" in (out.get("fcc_warning") or ""), out
    rec = sm.spools[57]
    assert rec["archived"] is False and rec["location"] == "", rec
    assert rec["extra"]["physical_source"] == "" and rec["extra"]["physical_source_slot"] == "", rec


def test_control_a_place_with_no_rows_is_still_read_as_a_spoolman_place(logs):
    """Control: a locations.json that is simply absent (no rows, read fine) is no
    failure: a spool archived on a Spoolman-native shelf stays there, as before."""
    sm = WeightWireSpoolman(_spool("GARAGE SHELF", archived=True, used=1000))
    ctx, _r, _d = _wire(sm)
    ctx = [p for p in ctx if getattr(p, "attribute", "") not in ("load_locations_list", "get_active_printer_map")]
    ctx += [patch.object(spoolman_api.locations_db, "load_locations_list", return_value=[]),
            patch.object(spoolman_api.locations_db, "get_active_printer_map", return_value={})]
    out = _write(sm, ctx, {"used_weight": 600})
    assert not out.get("fcc_warning"), out
    assert sm.spools[57]["location"] == "GARAGE SHELF" and sm.spools[57]["archived"] is False


def test_an_untick_at_nothing_left_on_a_head_takes_it_off_and_asks(logs):
    """C1. 63.2's stuck spool is always at 0 g: an untick of Archived in Edit Spool
    takes it out of the archive. On XL-1, with #99 loaded since, it is taken off the
    head and asked about, as a refill there is. RED on 8153b81: it came back in
    stock on XL-1, its trail kept, beside #99, with no question and no warning."""
    sm = WeightWireSpoolman(_spool("XL-1", archived=True, used=1000, physical_source="PM-DB-9",
                                   physical_source_slot="1"))
    ctx, _r, detached = _wire(sm, residents={"XL-1": [99]})
    out = _write(sm, ctx, {"archived": False})
    assert out["fcc_refill_ask"] == {"place": "XL-1", "room": "LR", "held_by": [99]}, out
    rec = sm.spools[57]
    assert rec["archived"] is False and rec["location"] == "", rec
    assert rec["extra"]["physical_source"] == "", rec
    assert detached == [("PM-DB-9", "XL-1")], detached


def test_an_untick_at_nothing_left_in_a_box_slot_another_spool_claims_goes_unassigned(logs):
    """C1, a box slot: #12 holds LR-MDB-1 slot 2 now. RED on 8153b81: back in stock
    claiming slot 2 beside #12."""
    sm = WeightWireSpoolman(_spool("LR-MDB-1", archived=True, used=1000, container_slot="2"))
    ctx, _r, _d = _wire(sm, residents={"LR-MDB-1": [
        {"id": 12, "location": "LR-MDB-1", "is_ghost": False, "slot": "2"}]})
    out = _write(sm, ctx, {"archived": False})
    assert out["fcc_warning"] == ("#57 is back in stock (0 g), but LR-MDB-1 slot 2 now holds #12, so it is "
                                  "Unassigned — scan it to where you put it."), out
    assert sm.spools[57]["location"] == "" and sm.spools[57]["extra"]["container_slot"] == ""


def test_control_an_untick_at_nothing_left_unassigned_stays_unassigned(logs):
    """Control (Claude's call 3): Unassigned, an untick at 0 g uses its note up and
    moves nowhere, asking nothing."""
    sm = WeightWireSpoolman(_spool("", archived=True, used=1000, note="XL-1"))
    ctx, reads, _d = _wire(sm)
    out = _write(sm, ctx, {"archived": False})
    assert not out.get("fcc_refill_ask") and not out.get("fcc_warning"), out
    assert sm.spools[57]["location"] == "" and _note(sm) == "", sm.spools[57]
    assert reads == []


@pytest.mark.parametrize("runs_from_box, released", [(True, []), (False, [("PM-DB-9", "XL-1")])],
                         ids=["another-spool-runs-from-the-box", "control-nothing-runs-from-it"])
def test_a_refill_off_a_head_keeps_the_box_another_spool_runs_from(logs, runs_from_box, released):
    """K24. #57 was archived on XL-1 from PM-DB-9 (63.2's stuck spool); since, #99
    went into PM-DB-9 and was loaded onto XL-1, which attached the box again. A
    refill takes #57 off the head and must leave PM-DB-9 attached for #99. RED on
    8153b81: PM-DB-9 was let go, and the Quick-Swap grid lost it for XL-1."""
    sm = WeightWireSpoolman(_spool("XL-1", archived=True, used=1000, physical_source="PM-DB-9",
                                   physical_source_slot="1"))
    box = [{"id": 99, "location": "PM-DB-9", "is_ghost": True, "slot": "1", "deployed_to": "XL-1"}]
    ctx, _r, detached = _wire(sm, residents={"XL-1": [99], "PM-DB-9": box if runs_from_box else []})
    out = _write(sm, ctx, {"used_weight": 600})
    assert out["fcc_refill_ask"]["place"] == "XL-1", out
    assert detached == released, detached
