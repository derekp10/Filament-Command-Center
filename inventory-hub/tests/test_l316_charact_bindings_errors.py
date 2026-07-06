"""L316 characterization tests — pins pre-carve behavior of the bindings/quickswap
error taxonomy (app.py 3116-3819: api_quickswap_return + api_put_printer_creds).
Generated from the 2026-07-01 coverage audit. Do not weaken these to make a
refactor pass.

Pinned here (host-runnable, everything outbound mocked):

POST /api/quickswap/return — the FOUR error paths the frontend return overlay
switches on, plus the subtle non-dryer-box physical_source fallback:
  * missing toolhead      -> 400 return_bad_request  (+ ERROR activity log)
  * unregistered toolhead -> 404 return_bad_toolhead (+ WARNING activity log)
  * all candidates empty  -> 404 return_no_spool     (+ sorted candidates list)
  * no source, no binding -> 404 return_no_binding   (toolhead = ACTIVE, not requested)
  * physical_source points at a NON-dryer-box row (or a ghost row) -> silently
    falls through to the first_binding scan instead of erroring.

PUT /api/printer_creds — the 500 failure branches (happy paths live in
test_phase2_creds_gate.py; not duplicated here):
  * locations.json unreadable      -> 500 {ok: False, error: "could not read locations: ..."}
  * save_locations_list -> False   -> 500 + the "save FAILED" ERROR activity log
  * identical creds (changed=False) -> 200 WITHOUT calling save (the changed-guard).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


# ---------------------------------------------------------------------------
# /api/quickswap/return — error taxonomy
# ---------------------------------------------------------------------------

def _return_harness(printer_map, locs, residents, spool, move_return=None):
    """The standard patch stack from test_return_and_breadcrumb.py: config +
    active printer_map + locations rows + Spoolman residents/spool + smart-move.
    `residents` may be a list (same for every toolhead) or a callable(loc)."""
    side = residents if callable(residents) else (lambda loc: list(residents))
    return (
        patch.object(app_module.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(app_module.locations_db, "get_active_printer_map",
                     return_value=printer_map),
        patch.object(app_module.locations_db, "load_locations_list", return_value=locs),
        patch.object(app_module.spoolman_api, "get_spools_at_location", side_effect=side),
        patch.object(app_module.spoolman_api, "get_spool", return_value=spool),
        patch.object(app_module.logic, "perform_smart_move",
                     return_value=move_return or {"status": "success"}),
    )


def test_return_missing_toolhead_is_400_bad_request(client):
    """Empty/absent toolhead must 400 with action=return_bad_request and the
    exact error string the overlay displays, write an ERROR activity-log line,
    and never reach perform_smart_move."""
    with patch.object(app_module.state, "add_log_entry") as log, \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        r = client.post("/api/quickswap/return", json={})
    assert r.status_code == 400
    body = r.get_json()
    assert body["action"] == "return_bad_request"
    assert body["error"] == "toolhead required"
    mv.assert_not_called()
    log.assert_called_once()
    msg, level, color = log.call_args[0]
    assert "Return rejected: missing toolhead" in msg
    assert level == "ERROR"
    assert color == "ff0000"


def test_return_whitespace_toolhead_is_400_bad_request(client):
    """'   ' strips to empty -> same 400 as an absent field (pins the strip)."""
    with patch.object(app_module.state, "add_log_entry"), \
         patch.object(app_module.logic, "perform_smart_move") as mv:
        r = client.post("/api/quickswap/return", json={"toolhead": "   "})
    assert r.status_code == 400
    assert r.get_json()["action"] == "return_bad_request"
    mv.assert_not_called()


def test_return_unregistered_toolhead_is_404_bad_toolhead(client):
    """A toolhead that is neither a printer_map key nor a prefix of one must
    404 with action=return_bad_toolhead. The echoed toolhead is UPPERCASED
    (input normalization), a WARNING log fires, and no Spoolman probe or
    smart-move happens."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    patches = _return_harness(printer_map, [], [], {})
    with patches[0], patches[1], patches[2], \
         patch.object(app_module.spoolman_api, "get_spools_at_location") as probe, \
         patch.object(app_module.logic, "perform_smart_move") as mv, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/quickswap/return", json={"toolhead": "ghost"})
    assert r.status_code == 404
    body = r.get_json()
    assert body["action"] == "return_bad_toolhead"
    assert body["toolhead"] == "GHOST"
    probe.assert_not_called()
    mv.assert_not_called()
    msg, level, color = log.call_args[0]
    assert "GHOST is not a registered toolhead or printer" in msg
    assert level == "WARNING"
    assert color == "ffaa00"


def test_return_all_toolheads_empty_is_404_no_spool_with_sorted_candidates(client):
    """Virtual-printer fan-out where every toolhead is empty must 404 with
    action=return_no_spool. Pins: `toolhead` in the body is the REQUESTED
    prefix, `candidates` is the sorted fan-out list, every candidate was probed
    in that sorted order, and a WARNING log names them comma-joined.

    # 29.B1 FIX: the sort is now NATURAL/numeric (XL-2 before XL-10), not
    # lexicographic. On a 10+ toolhead printer (indxx) this fixes both the
    # probe order and which loaded toolhead the return acts on.
    """
    printer_map = {
        "XL-1": {"printer_name": "XL", "position": 0},
        "XL-2": {"printer_name": "XL", "position": 1},
        "XL-10": {"printer_name": "XL", "position": 9},
    }
    patches = _return_harness(printer_map, [], [], {})
    with patches[0], patches[1], patches[2], \
         patch.object(app_module.spoolman_api, "get_spools_at_location",
                      return_value=[]) as probe, \
         patch.object(app_module.logic, "perform_smart_move") as mv, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/quickswap/return", json={"toolhead": "XL"})
    assert r.status_code == 404
    body = r.get_json()
    assert body["action"] == "return_no_spool"
    assert body["toolhead"] == "XL"  # requested prefix, NOT an active toolhead
    assert body["candidates"] == ["XL-1", "XL-2", "XL-10"]  # natural/numeric sort
    assert [c.args[0] for c in probe.call_args_list] == ["XL-1", "XL-2", "XL-10"]
    mv.assert_not_called()
    msg, level, color = log.call_args[0]
    assert "XL-1, XL-2, XL-10 is empty" in msg  # multi-candidate comma join
    assert level == "WARNING"
    assert color == "ffaa00"


def test_return_single_toolhead_empty_no_spool_names_it_bare(client):
    """Exact-toolhead request with an empty toolhead: candidates == [that
    toolhead] and the WARNING log names it WITHOUT the comma-join path."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    patches = _return_harness(printer_map, [], [], {})
    with patches[0], patches[1], patches[2], \
         patch.object(app_module.spoolman_api, "get_spools_at_location",
                      return_value=[]), \
         patch.object(app_module.logic, "perform_smart_move") as mv, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/quickswap/return", json={"toolhead": "xl-1"})
    assert r.status_code == 404
    body = r.get_json()
    assert body["action"] == "return_no_spool"
    assert body["candidates"] == ["XL-1"]
    mv.assert_not_called()
    assert "XL-1 is empty" in log.call_args[0][0]


def test_return_no_source_and_no_binding_is_404_reporting_active_toolhead(client):
    """Loaded spool with no physical_source and NO dryer box bound to the
    active toolhead must 404 with action=return_no_binding.

    # 29.B3 FIX: `toolhead` is now the REQUESTED value in EVERY error branch
    # (consistent with return_no_spool). The resolved active toolhead the
    # fan-out landed on is reported separately as `active_toolhead`;
    # `requested` is retained as a back-compat alias."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    locs = [
        # A dryer box exists but is bound to a DIFFERENT toolhead.
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"1": "XL-2"}}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
    ]
    fake_spool = {"id": 77, "location": "XL-1", "extra": {}}
    p = _return_harness(printer_map, locs, [77], fake_spool)
    with p[0], p[1], p[2], p[3], p[4], \
         patch.object(app_module.logic, "perform_smart_move") as mv, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/quickswap/return", json={"toolhead": "XL"})
    assert r.status_code == 404
    body = r.get_json()
    assert body["action"] == "return_no_binding"
    assert body["toolhead"] == "XL"            # 29.B3: now the REQUESTED value, uniform across branches
    assert body["active_toolhead"] == "XL-1"   # the resolved toolhead, reported separately
    assert body["requested"] == "XL"           # back-compat alias, unchanged
    mv.assert_not_called()
    msg, level, color = log.call_args[0]
    assert "XL-1 has no bound dryer box slot and no physical_source" in msg
    assert level == "WARNING"
    assert color == "ffaa00"


# ---------------------------------------------------------------------------
# /api/quickswap/return — non-dryer-box physical_source fallback
# ---------------------------------------------------------------------------

def test_return_physical_source_pointing_at_non_dryer_box_falls_back_to_binding(client):
    """physical_source names an EXISTING row that is NOT a Dryer Box (a Tool
    Head here — e.g. the extra drifted after a toolhead-to-toolhead move).
    The type-check `break` must abandon the physical_source path and fall
    through to the first_binding scan, returning 200 via the bound box —
    never a 404 and never a move to the non-box row."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    locs = [
        {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},  # the bogus source
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"2": "XL-1"}}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
    ]
    fake_spool = {"id": 77, "location": "XL-1",
                  "extra": {"physical_source": "XL-2", "physical_source_slot": "1"}}
    p = _return_harness(printer_map, locs, [77], fake_spool)
    with p[0], p[1], p[2], p[3], p[4], \
         patch.object(app_module.logic, "perform_smart_move",
                      return_value={"status": "success"}) as mv, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.post("/api/quickswap/return", json={"toolhead": "XL-1"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["action"] == "return_done"
    assert body["source"] == "first_binding"   # NOT physical_source
    assert body["box"] == "LR-MDB-1"
    assert body["slot"] == "2"                 # the bound slot, not the source slot
    mv.assert_called_once_with("LR-MDB-1", [77], target_slot="2",
                               origin="quickswap_return", confirm_active_print=True)
    # Success log flags the fallback provenance.
    success_msgs = [c.args[0] for c in log.call_args_list if c.args[1] == "SUCCESS"]
    assert success_msgs and "(first bound slot)" in success_msgs[0]


def test_return_physical_source_ghost_row_falls_back_to_binding(client):
    """physical_source names a LocationID with no row at all (box deleted
    since the deploy): the scan exhausts without a match and the fallback
    first_binding path still returns the spool via the bound box."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    locs = [
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"2": "XL-1"}}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
    ]
    fake_spool = {"id": 88, "location": "XL-1",
                  "extra": {"physical_source": "GONE-BOX", "physical_source_slot": "3"}}
    p = _return_harness(printer_map, locs, [88], fake_spool)
    with p[0], p[1], p[2], p[3], p[4], \
         patch.object(app_module.logic, "perform_smart_move",
                      return_value={"status": "success"}) as mv, \
         patch.object(app_module.state, "add_log_entry"):
        r = client.post("/api/quickswap/return", json={"toolhead": "XL-1"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "first_binding"
    assert body["box"] == "LR-MDB-1"
    assert body["slot"] == "2"
    mv.assert_called_once()


# ---------------------------------------------------------------------------
# PUT /api/printer_creds — 500 failure branches + the changed-guard
# ---------------------------------------------------------------------------

def _printer_rows():
    # Shape mirrors test_phase2_creds_gate._rows() (ASCII names — the handler
    # matches on Name verbatim, emoji not load-bearing for the failure paths).
    return [
        {"LocationID": "XL", "Type": "Printer", "Name": "XL Printer", "parent_id": "LR",
         "printer_creds": {"ip_address": "192.168.1.50", "api_key": "XLKEY"}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Name": "XL T1", "parent_id": "XL"},
    ]


def test_put_printer_creds_locations_unreadable_is_500_with_error_shape(client):
    """load_locations_list raising must 500 with ok:False and the exception
    text embedded in 'could not read locations: ...'. Nothing is saved —
    the read failure short-circuits before any write or existence check."""
    with patch.object(app_module.locations_db, "load_locations_list",
                      side_effect=OSError("disk gone")), \
         patch.object(app_module.locations_db, "save_locations_list") as save:
        r = client.put("/api/printer_creds", json={
            "printer_name": "XL Printer", "ip_address": "10.0.0.9", "api_key": "K"})
    assert r.status_code == 500
    body = r.get_json()
    assert body["ok"] is False
    assert "could not read locations" in body["error"]
    assert "disk gone" in body["error"]  # the raw exception is surfaced verbatim
    save.assert_not_called()


def test_put_printer_creds_save_failure_is_500_and_logs_error(client):
    """save_locations_list returning False on a changed write must 500 with
    the exact persist-failure error string and fire the ERROR activity-log
    line ('... save FAILED for <name>', ERROR, ff4444)."""
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=_printer_rows()), \
         patch.object(app_module.locations_db, "save_locations_list",
                      return_value=False) as save, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.put("/api/printer_creds", json={
            "printer_name": "XL Printer", "ip_address": "10.9.9.9",
            "api_key": "NEWKEY"})
    assert r.status_code == 500
    body = r.get_json()
    assert body["ok"] is False
    assert body["error"] == "could not persist printer connection"
    save.assert_called_once()
    log.assert_called_once()
    msg, level, color = log.call_args[0]
    assert "Printer connection save FAILED for XL Printer" in msg
    assert level == "ERROR"
    assert color == "ff4444"


def test_put_printer_creds_unchanged_skips_save_and_returns_200(client):
    """Sending creds identical to the stored ones -> changed=False, so the
    changed-guard must SKIP save entirely and return 200 ok:True (a broken
    save mock proves save was never consulted).

    # 29.B2 FIX: the 'Printer connection updated' INFO log no longer fires on
    # the no-op path — only on an actual change.
    """
    with patch.object(app_module.locations_db, "load_locations_list",
                      return_value=_printer_rows()), \
         patch.object(app_module.locations_db, "save_locations_list",
                      return_value=False) as save, \
         patch.object(app_module.state, "add_log_entry") as log:
        r = client.put("/api/printer_creds", json={
            "printer_name": "XL Printer", "ip_address": "192.168.1.50",
            "api_key": "XLKEY"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["error"] is None
    save.assert_not_called()
    # 29.B2: no "updated" log on the unchanged path.
    log.assert_not_called()
