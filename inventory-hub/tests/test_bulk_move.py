"""
Unit tests for the L298 Bulk Moves backend endpoint — POST /api/bulk_move
(routes_scan.api_bulk_move).

The endpoint is a WRAPPER around logic.perform_smart_move (the real move
engine). It must:

  - resolve the source FAIL-CLOSED (a Spoolman outage must not make the source
    look empty and silently "succeed" moving nothing);
  - apply the clear_location skip classes (ghost / archived / buffered /
    toolhead-loaded), reporting each as "left in place";
  - run the four pre-flights the single-move path lacks — self/descendant,
    single-occupancy dest, capacity (D3, BLOCK + report), source-side
    active-print;
  - delegate the actual move to ONE perform_smart_move call (never hand-roll
    spool writes), and return an HONEST per-spool tally derived from a readback
    (perform_smart_move reports a bare {status:success} even on partial failure).

Every collaborator is patched on its DEFINING module object so the tests need
no live container (mirrors test_auto_slot_pick + test_active_print_backend_
enforcement). Both source-resolve and capacity-occupancy go through the SAME
spoolman_api.get_spools_at_location_detailed_strict, so the strict patch uses a
per-location side_effect; the tally readback uses the fail-open
get_spools_at_location_detailed patched separately.
"""
from __future__ import annotations

import contextlib
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import logic  # noqa: E402
import locations_db  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402


# CR (room) ⊃ CR-CT-1 (cart, explicit parent) ⊃ CR-CT-1-R1 (row) — a real nested
# chain so is_descendant runs for real in the self/descendant tests. PM-DB-A/B
# are dryer boxes (bounded, Max Spools 4); SHELF-B + CR are unbounded; XL-1 is a
# single-occupancy toolhead in the printer_map.
FAKE_LOCATIONS = [
    {"LocationID": "PM-DB-A", "Type": "Dryer Box", "Max Spools": "4", "Name": "Box A"},
    {"LocationID": "PM-DB-B", "Type": "Dryer Box", "Max Spools": "4", "Name": "Box B"},
    {"LocationID": "SHELF-B", "Type": "Wall Shelf", "Max Spools": "0", "Name": "Shelf B"},
    {"LocationID": "CR", "Type": "Room", "Max Spools": "0", "Name": "Computer Room"},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "Name": "XL-1"},
    {"LocationID": "CR-CT-1", "Type": "Cart", "Max Spools": "0", "Name": "Cart 1",
     "parent_id": "CR"},
    {"LocationID": "CR-CT-1-R1", "Type": "Cart Row", "Max Spools": "0", "Name": "Row 1",
     "parent_id": "CR-CT-1"},
]
FAKE_PRINTER_MAP = {"XL-1": {"printer_name": "XL", "position": 0}}


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _spool(sid, location="PM-DB-A", is_ghost=False, archived=False):
    """A detailed-item dict shaped like get_spools_at_location_detailed emits."""
    return {"id": sid, "location": location, "is_ghost": is_ghost,
            "archived": archived, "slot": "", "display": f"#{sid}", "color": "ffffff"}


@contextlib.contextmanager
def _bulk_env(*, strict_map=None, raise_locs=None, readback=None,
              printer_map=None, locations=None, active_print_for=None,
              move_result=None, move_side_effect=None, last_error=None, buffer=None):
    """Patch every collaborator and yield the mocked perform_smart_move.

    strict_map:  {LOC_UPPER: [item, ...]} returned by the fail-closed reader
                 (drives BOTH source resolve and capacity occupancy).
    raise_locs:  {LOC_UPPER} for which the strict reader RAISES (outage sim).
    readback:    {LOC_UPPER: [item, ...]} for the fail-open post-move readback.
    active_print_for: {LOC_UPPER: ap_dict} the active-print helper returns.
    """
    strict_map = strict_map or {}
    raise_locs = raise_locs or set()
    readback = readback or {}
    printer_map = FAKE_PRINTER_MAP if printer_map is None else printer_map
    locations = FAKE_LOCATIONS if locations is None else locations

    def _strict(loc):
        u = str(loc).upper()
        if u in raise_locs:
            raise RuntimeError("spoolman transport error")
        return list(strict_map.get(u, []))

    def _detailed(loc):
        return list(readback.get(str(loc).upper(), []))

    def _ap(loc, pm=None):
        return (active_print_for or {}).get(str(loc).upper())

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(locations_db, "load_locations_list", return_value=locations))
        stack.enter_context(patch.object(locations_db, "get_active_printer_map", return_value=printer_map))
        stack.enter_context(patch.object(spoolman_api, "get_spools_at_location_detailed_strict", side_effect=_strict))
        stack.enter_context(patch.object(spoolman_api, "get_spools_at_location_detailed", side_effect=_detailed))
        stack.enter_context(patch.object(logic, "_active_print_info_for_location", side_effect=_ap))
        stack.enter_context(patch.object(state, "add_log_entry"))
        stack.enter_context(patch.object(state, "GLOBAL_BUFFER", buffer or []))
        stack.enter_context(patch.object(spoolman_api, "LAST_SPOOLMAN_ERROR", last_error))
        if move_side_effect is not None:
            mv = stack.enter_context(patch.object(logic, "perform_smart_move", side_effect=move_side_effect))
        else:
            mv = stack.enter_context(patch.object(
                logic, "perform_smart_move", return_value=(move_result or {"status": "success"})))
        yield mv


# ---------------------------------------------------------------------------
# Happy path + delegation contract
# ---------------------------------------------------------------------------

def test_happy_path_moves_all_movable(client):
    """Two direct spools → SHELF-B (unbounded) → one perform_smart_move call
    with exactly the movable ids; honest all-moved tally."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 2
    assert body["moved_ids"] == [1, 2]
    assert body["skipped"] == []
    assert body["failed"] == []
    # Delegated exactly once with (dest, movable_ids) and the opt-in flag.
    mv.assert_called_once()
    args, kwargs = mv.call_args
    assert args[0] == "SHELF-B"
    assert args[1] == [1, 2]
    assert kwargs.get("confirm_active_print") is False
    assert kwargs.get("origin") == "bulk_move"
    # A bulk move parks/relocates — it must NOT chain-deploy onto a live toolhead.
    assert kwargs.get("auto_deploy") is False


def test_lowercase_and_whitespace_normalized(client):
    """source/dest are upper-cased + stripped before use."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]}) as mv:
        r = client.post("/api/bulk_move", json={"source": " pm-db-a ", "dest": "shelf-b"})
    body = r.get_json()
    assert body["success"] is True
    assert body["source"] == "PM-DB-A"
    assert body["dest"] == "SHELF-B"
    assert mv.call_args[0][0] == "SHELF-B"


# ---------------------------------------------------------------------------
# Skip classes (mirror clear_location)
# ---------------------------------------------------------------------------

def test_skips_ghost_archived_buffered_and_toolhead_loaded(client):
    """Only the plain direct spool is movable; the other four are each skipped
    with a distinct reason. (id 5 carries a toolhead location to exercise the
    D2 flat-scope Printer-source guard without a printer source.)"""
    contents = [
        _spool(1),                                  # movable
        _spool(2, is_ghost=True),                   # deployed → live feed
        _spool(3, archived=True),                   # archived
        _spool(4),                                  # in the buffer
        _spool(5, location="XL-1"),                 # loaded in a toolhead slot
    ]
    with _bulk_env(strict_map={"PM-DB-A": contents}, buffer=[{"id": 4}]) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["moved_ids"] == [1]
    reasons = {s["id"]: s["reason"] for s in body["skipped"]}
    assert reasons == {
        2: "deployed to a live toolhead",
        3: "archived",
        4: "in the scan buffer",
        5: "loaded in a toolhead slot",
    }
    assert mv.call_args[0][1] == [1]


def test_all_skipped_is_a_clean_noop(client):
    """Every spool skipped → success + moved 0 + perform_smart_move NOT called."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1, is_ghost=True)]}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 0
    assert len(body["skipped"]) == 1
    assert "Nothing to move" in body["msg"]
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# Fail-closed source resolve
# ---------------------------------------------------------------------------

def test_fail_closed_when_source_unreadable(client):
    """A Spoolman outage on the source resolve must BLOCK (not silently move
    nothing and report success). perform_smart_move never runs."""
    with _bulk_env(raise_locs={"PM-DB-A"}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is False
    assert "Could not read" in body["msg"]
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# Pre-flight: self / descendant
# ---------------------------------------------------------------------------

def test_reject_same_source_and_dest(client):
    with _bulk_env() as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "PM-DB-A"})
    body = r.get_json()
    assert body["success"] is False
    assert "same location" in body["msg"].lower()
    mv.assert_not_called()


def test_reject_dest_is_descendant_of_source(client):
    """Moving a Room's contents INTO its own nested cart is paradoxical."""
    with _bulk_env(strict_map={"CR": [_spool(1, location="CR")]}) as mv:
        r = client.post("/api/bulk_move", json={"source": "CR", "dest": "CR-CT-1"})
    body = r.get_json()
    assert body["success"] is False
    assert "inside" in body["msg"].lower()
    mv.assert_not_called()


def test_allow_child_up_to_ancestor(client):
    """The reverse — cart contents UP to the room — is legitimate and proceeds."""
    with _bulk_env(strict_map={"CR-CT-1": [_spool(1, location="CR-CT-1")]}) as mv:
        r = client.post("/api/bulk_move", json={"source": "CR-CT-1", "dest": "CR"})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 1
    mv.assert_called_once()


# ---------------------------------------------------------------------------
# Pre-flight: single-occupancy destination
# ---------------------------------------------------------------------------

def test_reject_single_occupancy_dest(client):
    """A bulk move onto a Tool Head would chain-unseat all but the last spool."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "XL-1"})
    body = r.get_json()
    assert body["success"] is False
    assert "single-spool" in body["msg"].lower()
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# Pre-flight: destination must be a known location (review finding #1)
# ---------------------------------------------------------------------------

def test_reject_unknown_dest(client):
    """An unknown/stale/typo'd dest must be rejected BEFORE any move — else
    perform_smart_move writes the garbage LocationID to every source spool,
    orphaning them, while the source-only readback masks it as success."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "PM-DB-GONE"})
    body = r.get_json()
    assert body["success"] is False
    assert "not a known location" in body["msg"].lower()
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# Buffer-id coercion robustness (review finding #2)
# ---------------------------------------------------------------------------

def test_buffer_string_id_still_skips(client):
    """A buffer id serialized as a numeric string still skips that spool."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1), _spool(2)]}, buffer=[{"id": "1"}]) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["moved_ids"] == [2]
    assert any(s["id"] == 1 and s["reason"] == "in the scan buffer" for s in body["skipped"])


def test_malformed_buffer_id_does_not_500(client):
    """A poisoned buffer entry (non-numeric id) must not crash the endpoint —
    the coercion is guarded like the per-spool check."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]},
                   buffer=[{"id": "abc"}, {"id": None}, {"not_id": 5}]) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert r.status_code == 200
    assert body["success"] is True
    assert body["moved_ids"] == [1]


# ---------------------------------------------------------------------------
# Pre-flight: capacity (D3)
# ---------------------------------------------------------------------------

def test_capacity_block_bounded_dest_overflow(client):
    """PM-DB-B has 4 slots, 3 occupied (1 free); source has 2 → BLOCK the batch."""
    strict = {
        "PM-DB-A": [_spool(1), _spool(2)],
        "PM-DB-B": [_spool(10, location="PM-DB-B"), _spool(11, location="PM-DB-B"),
                    _spool(12, location="PM-DB-B")],
    }
    with _bulk_env(strict_map=strict) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "PM-DB-B"})
    body = r.get_json()
    assert body["success"] is False
    assert body["moved"] == 0
    assert "free" in body["msg"].lower()
    mv.assert_not_called()


def test_capacity_ok_bounded_dest_exact_fit(client):
    """4 slots, 2 occupied (2 free); source has 2 → proceeds (exact fit)."""
    strict = {
        "PM-DB-A": [_spool(1), _spool(2)],
        "PM-DB-B": [_spool(10, location="PM-DB-B"), _spool(11, location="PM-DB-B")],
    }
    with _bulk_env(strict_map=strict) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "PM-DB-B"})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 2
    mv.assert_called_once()


def test_capacity_unbounded_dest_never_caps(client):
    """A Room (Max Spools 0) accepts any count."""
    strict = {"PM-DB-A": [_spool(i) for i in range(1, 21)]}
    with _bulk_env(strict_map=strict) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "CR"})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 20
    mv.assert_called_once()


def test_capacity_fail_closed_on_dest_read_error(client):
    """If the dest occupancy read fails for a bounded dest, BLOCK rather than
    risk an overflow (nothing moved)."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]}, raise_locs={"PM-DB-B"}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "PM-DB-B"})
    body = r.get_json()
    assert body["success"] is False
    assert "capacity" in body["msg"].lower()
    mv.assert_not_called()


# ---------------------------------------------------------------------------
# Pre-flight: source-side active print
# ---------------------------------------------------------------------------

def test_source_active_print_requires_confirm(client):
    """A bulk move from an actively-printing source bails for confirmation."""
    ap = {"printer_name": "XL", "state": "PRINTING", "toolhead": "PM-DB-A"}
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]},
                   active_print_for={"PM-DB-A": ap}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is False
    assert body["require_confirm"] is True
    assert body["confirm_type"] == "active_print"
    assert body["active_print"]["printer_name"] == "XL"
    mv.assert_not_called()


def test_confirm_active_print_bypasses_source_guard(client):
    """confirm_active_print=True flows through the source active-print guard."""
    ap = {"printer_name": "XL", "state": "PRINTING", "toolhead": "PM-DB-A"}
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]},
                   active_print_for={"PM-DB-A": ap}) as mv:
        r = client.post("/api/bulk_move", json={
            "source": "PM-DB-A", "dest": "SHELF-B", "confirm_active_print": True})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 1
    assert mv.call_args[1].get("confirm_active_print") is True


def test_dest_active_print_from_engine_is_propagated(client):
    """perform_smart_move's own requires_confirm (eventual dest active) surfaces
    as a require_confirm response — no partial write happened."""
    engine = {"status": "requires_confirm", "confirm_type": "active_print",
              "active_print": {"printer_name": "Core One", "state": "PAUSED"}}
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]}, move_result=engine):
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is False
    assert body["require_confirm"] is True
    assert body["confirm_type"] == "active_print"
    assert body["active_print"]["printer_name"] == "Core One"


# ---------------------------------------------------------------------------
# Honest tally via readback
# ---------------------------------------------------------------------------

def test_partial_failure_reported_via_readback(client):
    """3 movable; the move engine reports bare success but spool 2 is still at
    the source afterward → it lands in `failed`, not `moved`."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1), _spool(2), _spool(3)]},
                   readback={"PM-DB-A": [_spool(2)]},
                   move_result={"status": "success",
                                "failures": {"2": "Spoolman 400: bad request"}}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is False           # a failure occurred
    assert body["moved"] == 2
    assert sorted(body["moved_ids"]) == [1, 3]
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == 2
    assert body["failed"][0]["err"] == "Spoolman 400: bad request"
    mv.assert_called_once()


def test_failed_rows_carry_their_OWN_spoolman_error(client):
    """PHASE 3 — per-spool error attribution.

    Phase 2 read the LAST_SPOOLMAN_ERROR module global ONCE, after the whole
    per-spool loop and one-to-two readbacks. That is wrong twice over: a later
    SUCCESS resets the global to None (every failed row got the useless "see
    Activity Log"), and a second failure overwrites the first (both rows blamed
    on whichever failed last). perform_smart_move now captures each error
    ADJACENT to its own failing write and returns the map.
    """
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1), _spool(2), _spool(3)]},
                   readback={"PM-DB-A": [_spool(1), _spool(3)]},
                   last_error=None,       # a trailing success cleared the global
                   move_result={"status": "success",
                                "failures": {"1": "HTTP 400: bad location",
                                             "3": "HTTP 409: conflict"}}):
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["moved"] == 1 and body["moved_ids"] == [2]
    assert {f["id"]: f["err"] for f in body["failed"]} == {
        1: "HTTP 400: bad location", 3: "HTTP 409: conflict"}


def test_failed_row_without_a_captured_error_falls_back(client):
    """No map entry (an older/odd engine return) must degrade to the Activity
    Log pointer rather than KeyError or publish a wrong attribution."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]},
                   readback={"PM-DB-A": [_spool(1)]},
                   last_error="a stale global that must NOT be used",
                   move_result={"status": "success"}):
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    assert r.get_json()["failed"][0]["err"] == "see Activity Log"


def test_ghost_at_source_after_move_is_not_a_failure(client):
    """A spool showing at the source only as a GHOST after the move (deployed
    elsewhere) must not be miscounted as failed — only DIRECT matches count."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]},
                   readback={"PM-DB-A": [_spool(1, is_ghost=True)]}) as mv:
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 1
    assert body["failed"] == []


def test_readback_subtracts_spools_that_landed_at_dest(client):
    """Review finding #3: the source readback matches by FLAT first-segment, so a
    prefix-colliding reparented dest can make a correctly-moved spool re-match the
    source. If it actually landed at dest it must NOT be counted as failed."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]},
                   readback={"PM-DB-A": [_spool(1)],          # flat-matches source...
                             "SHELF-B": [_spool(1)]}) as mv:   # ...but is really at dest
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is True
    assert body["moved"] == 1
    assert body["failed"] == []


def test_engine_error_status_surfaced(client):
    """A {status:error} from the engine is surfaced as a failed response."""
    with _bulk_env(strict_map={"PM-DB-A": [_spool(1)]},
                   move_result={"status": "error", "msg": "No spools found"}):
        r = client.post("/api/bulk_move", json={"source": "PM-DB-A", "dest": "SHELF-B"})
    body = r.get_json()
    assert body["success"] is False
    assert "No spools found" in body["msg"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"dest": "SHELF-B"},
    {"source": "PM-DB-A"},
    {"source": "", "dest": "SHELF-B"},
    {},
])
def test_missing_source_or_dest_rejected(client, payload):
    with _bulk_env() as mv:
        r = client.post("/api/bulk_move", json=payload)
    body = r.get_json()
    assert body["success"] is False
    assert "required" in body["msg"].lower()
    mv.assert_not_called()
