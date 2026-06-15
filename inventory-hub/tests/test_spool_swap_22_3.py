"""Group 22.3 — mid-print spool-swap minimum-viable route-to-review.

When a USED toolhead's mapped spool CHANGED between print-START and completion (a
runout / M600 replace), the full slicer footer would dump the whole tool's usage on
the REPLACEMENT spool and record 0g on the run-out spool. Instead of auto-applying,
FCC routes that completion to the cancel-REVIEW pipeline (kind='spool_changed') so
the user splits the grams manually. Pins:

  - capture: a once-per-job start-spool snapshot taken ONLY on a true PRINTING tick,
    gated behind the completion-ownership flag, re-captured on a job change;
  - threading: the snapshot rides the fire dict (live edge) and the persisted entry
    (restart) into deduct_completed_print;
  - detection: a clean 1->1 sid change per used position flags; None on either side
    (empty/ambiguous) does NOT; same spool -> auto-apply unchanged;
  - routing: no ledger write, no auto-apply, exactly-once via the review store; the
    existing per-sid confirm loop applies it;
  - degradation: a missing snapshot (None) / a detection exception falls through to
    today's auto-apply, never crashes.
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import print_deduct_ledger  # noqa: E402
import cancel_review_store  # noqa: E402
import cancel_fetch_store  # noqa: E402
import print_tracker_store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    # NOTE: deliberately does NOT stub _snapshot_active_spools — this file exercises
    # the real capture/detection; each test controls the flag + snapshot explicitly.
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    prev_async = app_module._CANCEL_DEDUCT_RUN_ASYNC
    app_module._CANCEL_DEDUCT_RUN_ASYNC = False
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()
    try:
        yield
    finally:
        app_module._CANCEL_DEDUCT_RUN_ASYNC = prev_async
        with app_module._PRINT_TRACKER_LOCK:
            app_module._PRINT_TRACKER.clear()


def _creds(*a, **k):
    return {"ip_address": "1.2.3.4", "api_key": "k"}


PM = {"XL-1": {"printer_name": "XL", "position": 0},
      "XL-2": {"printer_name": "XL", "position": 1}}
ACTIVE = [("XL-1", {"position": 0}), ("XL-2", {"position": 1})]


def _completion_ctx(usage_map, end_snap, rows=None):
    """Mocks for deduct_completed_print's swap-detection path: creds, the footer
    compute, the printer-map resolve, the COMPLETION snapshot, and the preview-row
    builder. Returns the ctx managers list (start/stop)."""
    apply_mock = MagicMock(name="_apply_usage_to_printer")
    ctx = [
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds),
        patch.object(app_module, "_compute_cancel_usage", return_value=(dict(usage_map), None)),
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=PM),
        patch.object(app_module, "_resolve_active_locs_for_printer", return_value=ACTIVE),
        patch.object(app_module, "_snapshot_active_spools", return_value=dict(end_snap)),
        patch.object(app_module, "_resolve_usage_to_spools",
                     return_value=(rows if rows is not None else
                                   [{"sid": 999, "grams": 25.0, "color": "ff0000",
                                     "toolhead": "XL-1", "position": 0}])),
        patch.object(app_module, "_apply_usage_to_printer", apply_mock),
        patch.object(app_module.state, "add_log_entry"),
    ]
    return ctx, apply_mock


# --------------------------------------------------------------------------- #
# Detection + routing                                                          #
# --------------------------------------------------------------------------- #

def test_changed_spool_routes_to_review_not_auto_apply():
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0}, end_snap={0: 999})
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-1",
                                                start_spools={"0": 100})
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "pending_spool_changed", res
    apply_mock.assert_not_called()                                   # NO auto-apply
    assert print_deduct_ledger.was_deducted("XL", "J-1") is False    # NO ledger write
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec and rec["kind"] == "spool_changed"
    assert rec["changed_positions"] == [0]


def test_same_spool_auto_applies():
    """start sid == end sid for every used position -> no swap -> auto-apply (today)."""
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0}, end_snap={0: 100})
    apply_mock.return_value = (1, [{"sid": 100, "grams": 25.0, "remaining": 900.0}], {0})
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-2",
                                                start_spools={"0": 100})
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "deducted"
    apply_mock.assert_called_once()
    assert cancel_review_store.get_pending("XL", "J-2") is None


def test_no_snapshot_degrades_to_auto_apply():
    """start_spools=None (deferred-retry / pre-capture restart) -> skip detection
    entirely (the snapshot helper is never even consulted) -> auto-apply."""
    apply_mock = MagicMock(return_value=(1, [{"sid": 999, "grams": 25.0, "remaining": 900.0}], {0}))
    snap = MagicMock(return_value={0: 999})
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module, "_compute_cancel_usage", return_value=({0: 25.0}, None)), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=PM), \
         patch.object(app_module, "_resolve_active_locs_for_printer", return_value=ACTIVE), \
         patch.object(app_module, "_snapshot_active_spools", snap), \
         patch.object(app_module, "_apply_usage_to_printer", apply_mock), \
         patch.object(app_module.state, "add_log_entry"):
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-3", start_spools=None)
    assert res["status"] == "deducted"
    apply_mock.assert_called_once()
    snap.assert_not_called()                                         # detection block skipped


def test_changed_one_of_two_tools_routes_whole_completion():
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0, 1: 40.0}, end_snap={0: 100, 1: 888},
                                      rows=[{"sid": 100, "grams": 25.0, "color": "ff0000",
                                             "toolhead": "XL-1", "position": 0},
                                            {"sid": 888, "grams": 40.0, "color": "00ff00",
                                             "toolhead": "XL-2", "position": 1}])
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-4",
                                                start_spools={"0": 100, "1": 200})
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "pending_spool_changed"
    apply_mock.assert_not_called()
    assert cancel_review_store.get_pending("XL", "J-4")["changed_positions"] == [1]


def test_none_side_not_flagged_auto_applies():
    """end_snap has None for the position (empty/ambiguous) -> not a confident swap."""
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0}, end_snap={0: None})
    apply_mock.return_value = (1, [{"sid": 100, "grams": 25.0, "remaining": 900.0}], {0})
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-5",
                                                start_spools={"0": 100})
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "deducted"
    apply_mock.assert_called_once()


def test_detection_exception_falls_through_to_auto_apply():
    """A raise inside the snapshot/detection must never block the deduct."""
    apply_mock = MagicMock(return_value=(1, [{"sid": 100, "grams": 25.0, "remaining": 900.0}], {0}))
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module, "_compute_cancel_usage", return_value=({0: 25.0}, None)), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=PM), \
         patch.object(app_module, "_resolve_active_locs_for_printer", return_value=ACTIVE), \
         patch.object(app_module, "_snapshot_active_spools", side_effect=RuntimeError("boom")), \
         patch.object(app_module, "_apply_usage_to_printer", apply_mock), \
         patch.object(app_module.state, "add_log_entry"):
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-6", start_spools={"0": 100})
    assert res["status"] == "deducted"
    apply_mock.assert_called_once()


def test_restart_re_detect_does_not_double_surface():
    """A re-invocation (restart recovery) with the SAME still-changed snapshot must
    hit has_pending and NOT add a second review or write the ledger."""
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "J-7", "filename": "f.gcode", "progress": 1.0,
        "total_grams": 25.0, "spools": [{"sid": 999, "grams": 25.0}], "kind": "spool_changed",
        "changed_positions": [0], "created": "2026-06-14 00:00:00"})
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0}, end_snap={0: 999})
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-7", start_spools={"0": 100})
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "skipped"
    apply_mock.assert_not_called()
    assert print_deduct_ledger.was_deducted("XL", "J-7") is False
    assert len(cancel_review_store.list_pending()) == 1


def test_single_tool_core_one_rekey_and_swap_routes():
    """Headline scenario: a single-tool Core One footer (one tool) is re-keyed onto
    the sole printer position by _compute_cancel_usage; a start->end sid change on
    that position still routes to review (real footer parse, not mocked compute)."""
    pm = {"CORE1-M0": {"printer_name": "CORE1", "position": 0}}
    gcode = "; filament used [g] = 25\n"
    apply_mock = MagicMock(name="apply")
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(app_module, "_resolve_active_locs_for_printer",
                      return_value=[("CORE1-M0", {"position": 0})]), \
         patch.object(app_module, "_snapshot_active_spools", return_value={0: 999}), \
         patch.object(app_module, "_resolve_usage_to_spools",
                      return_value=[{"sid": 999, "grams": 25.0, "color": "ff0000",
                                     "toolhead": "CORE1-M0", "position": 0}]), \
         patch.object(app_module, "_apply_usage_to_printer", apply_mock), \
         patch.object(app_module.state, "add_log_entry"):
        res = app_module.deduct_completed_print("CORE1", "f.gcode", "J-8", start_spools={"0": 100})
    assert res["status"] == "pending_spool_changed"
    apply_mock.assert_not_called()


# --------------------------------------------------------------------------- #
# Snapshot capture in _track_print_edge                                        #
# --------------------------------------------------------------------------- #

def _latch(state, job, fb="http://fb"):
    with patch.object(app_module.prusalink_api, "get_printer_job", return_value=job):
        app_module._track_print_edge("XL", {"state": state}, fb)


def test_snapshot_captured_once_per_job():
    snap = MagicMock(return_value={0: 100})
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_snapshot_active_spools", snap):
        for _ in range(3):  # three PRINTING ticks, SAME job
            _latch("PRINTING", {"filename": "f.gcode", "job_id": 9, "progress": 0.4})
    assert snap.call_count == 1
    e = app_module._PRINT_TRACKER["XL"]
    assert e["start_spools"] == {"0": 100} and e["snapshot_job"] == "9"


def test_snapshot_recaptured_on_job_change():
    snap = MagicMock(side_effect=[{0: 100}, {0: 200}])
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_snapshot_active_spools", snap):
        _latch("PRINTING", {"filename": "a.gcode", "job_id": 9, "progress": 0.4})
        _latch("PRINTING", {"filename": "b.gcode", "job_id": 10, "progress": 0.1})
    assert snap.call_count == 2
    e = app_module._PRINT_TRACKER["XL"]
    assert e["snapshot_job"] == "10" and e["start_spools"] == {"0": 200}


def test_capture_skipped_when_flag_off():
    snap = MagicMock(return_value={0: 100})
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=False), \
         patch.object(app_module, "_snapshot_active_spools", snap):
        _latch("PRINTING", {"filename": "f.gcode", "job_id": 9, "progress": 0.4})
    snap.assert_not_called()
    assert "start_spools" not in app_module._PRINT_TRACKER["XL"]


def test_capture_skipped_when_first_seen_paused():
    """A job first SEEN mid-PAUSE (e.g. monitor started during a runout) must NOT
    snapshot the post-swap mapping as 'start'."""
    snap = MagicMock(return_value={0: 100})
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_snapshot_active_spools", snap):
        _latch("PAUSED", {"filename": "f.gcode", "job_id": 9, "progress": 0.4})
    snap.assert_not_called()
    assert "start_spools" not in app_module._PRINT_TRACKER.get("XL", {})


def test_fire_dict_threads_snapshot_to_completion():
    deduct = MagicMock(return_value={"status": "deducted"})
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_snapshot_active_spools", return_value={0: 100}), \
         patch.object(app_module, "deduct_completed_print", deduct), \
         patch.object(app_module.state, "add_log_entry"):
        _latch("PRINTING", {"filename": "f.gcode", "job_id": 9, "progress": 0.9})
        _latch("FINISHED", None)
    deduct.assert_called_once()
    assert deduct.call_args.kwargs.get("start_spools") == {"0": 100}


# --------------------------------------------------------------------------- #
# Restart recovery threads / degrades the persisted snapshot                    #
# --------------------------------------------------------------------------- #

def test_restart_recovery_threads_persisted_snapshot():
    entry = {"state": "PRINTING", "job_id": 9, "filename": "f.gcode", "progress": 0.9,
             "start_spools": {"0": 100}, "snapshot_job": "9"}
    disp = MagicMock()
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "FINISHED"}), \
         patch.object(app_module, "_dispatch_completion_edge", disp), \
         patch.object(app_module.state, "add_log_entry"):
        app_module._recover_one_print_latch("XL", entry, "http://fb")
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("start_spools") == {"0": 100}


def test_restart_recovery_no_snapshot_degrades():
    entry = {"state": "PRINTING", "job_id": 9, "filename": "f.gcode", "progress": 0.9}
    disp = MagicMock()
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "FINISHED"}), \
         patch.object(app_module, "_dispatch_completion_edge", disp), \
         patch.object(app_module.state, "add_log_entry"):
        app_module._recover_one_print_latch("XL", entry, "http://fb")
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("start_spools") is None


# --------------------------------------------------------------------------- #
# Helpers: _validated_start_spools + _snapshot_active_spools + persistence       #
# --------------------------------------------------------------------------- #

def test_validated_start_spools_int_job_id_coercion():
    src = {"start_spools": {"0": 100}, "snapshot_job": "9"}
    assert app_module._validated_start_spools(src, 9) == {"0": 100}   # int 9 vs str '9'
    assert app_module._validated_start_spools(src, 10) is None        # mismatch
    assert app_module._validated_start_spools(None, 9) is None


def test_snapshot_active_spools_resolution():
    detailed = {"XL-1": [{"id": 100, "is_ghost": False}],
                "XL-2": [{"id": 200, "is_ghost": False}, {"id": 999, "is_ghost": True}]}
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=PM), \
         patch.object(app_module, "_resolve_active_locs_for_printer", return_value=ACTIVE), \
         patch.object(app_module.spoolman_api, "get_spools_at_location",
                      side_effect=lambda loc: [d["id"] for d in detailed.get(str(loc).upper(), [])]), \
         patch.object(app_module.spoolman_api, "get_spools_at_location_detailed",
                      side_effect=lambda loc: detailed.get(str(loc).upper(), [])):
        snap = app_module._snapshot_active_spools("XL", "http://fb")
    assert snap == {0: 100, 1: 200}   # pos1 ghost dropped -> single direct sid


def test_snapshot_active_spools_best_effort_on_error():
    with patch.object(app_module.locations_db, "get_active_printer_map",
                      side_effect=RuntimeError("down")):
        assert app_module._snapshot_active_spools("XL", "http://fb") == {}


def test_snapshot_persists_round_trip():
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER["XL"] = {"state": "PRINTING", "job_id": 9,
                                           "filename": "f.gcode",
                                           "start_spools": {"0": 100}, "snapshot_job": "9"}
        snapshot = {k: dict(v) for k, v in app_module._PRINT_TRACKER.items()}
    print_tracker_store.save(snapshot)
    loaded = print_tracker_store.load()
    assert loaded["XL"]["start_spools"] == {"0": 100}
    assert loaded["XL"]["snapshot_job"] == "9"


# --------------------------------------------------------------------------- #
# Confirm a spool_changed review via the existing per-sid partial loop          #
# --------------------------------------------------------------------------- #

def test_spool_changed_confirm_via_partial_loop():
    spool = {"id": 999, "used_weight": 100.0, "initial_weight": 1000.0}
    captured = []
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "J-C", "filename": "f.gcode", "progress": 1.0,
        "total_grams": 25.0, "kind": "spool_changed", "changed_positions": [0],
        "spools": [{"sid": 999, "grams": 25.0, "color": "ff0000"}],
        "created": "2026-06-14 00:00:00"})
    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: dict(spool)), \
         patch.object(app_module.spoolman_api, "update_spool",
                      side_effect=lambda sid, data: captured.append((int(sid), dict(data))) or {"id": sid}), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#999", "color": "ff0000"}), \
         patch.object(app_module.state, "add_log_entry"):
        r = app_module.app.test_client().post(
            "/api/cancel_deduct/confirm",
            json={"printer_name": "XL", "job_id": "J-C", "updates": {"999": 18.0}})
    d = r.get_json()
    assert d["status"] == "confirmed", d
    assert captured == [(999, {"used_weight": 118.0})]               # 100 + nudged 18
    assert print_deduct_ledger.was_deducted("XL", "J-C") is True     # ledger on confirm
    assert cancel_review_store.get_pending("XL", "J-C") is None      # popped


# --------------------------------------------------------------------------- #
# Deferred-fetch ('complete') retry carries the snapshot (finish-screen lock)   #
# --------------------------------------------------------------------------- #

def test_deferred_complete_enqueue_persists_start_spools():
    """A completion that locks behind the finish screen defers — the start-spool
    snapshot must ride the fetch record (the live latch is gone by retry time)."""
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode", return_value=None), \
         patch.object(app_module.state, "add_log_entry"):
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-D", start_spools={"0": 100})
    assert res["status"] == "awaiting_fetch"
    rec = cancel_fetch_store.get_pending("XL", "J-D")
    assert rec and rec["kind"] == "complete"
    assert rec["start_spools"] == {"0": 100}


def test_deferred_complete_retry_routes_on_swap():
    """The deferred retry reads start_spools off the fetch record, so a finish-screen
    -locked completion STILL detects a mid-print swap and routes to review."""
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-R", "filename": "f.gcode", "progress": 1.0,
        "first_seen": time.time(), "kind": "complete", "start_spools": {"0": 100},
        "attempts": 1, "last_status": "awaiting_fetch"})
    apply_mock = MagicMock(name="apply")
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module, "_compute_cancel_usage", return_value=({0: 25.0}, None)), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=PM), \
         patch.object(app_module, "_resolve_active_locs_for_printer", return_value=ACTIVE), \
         patch.object(app_module, "_snapshot_active_spools", return_value={0: 999}), \
         patch.object(app_module, "_resolve_usage_to_spools",
                      return_value=[{"sid": 999, "grams": 25.0, "color": "ff0000",
                                     "toolhead": "XL-1", "position": 0}]), \
         patch.object(app_module, "_apply_usage_to_printer", apply_mock), \
         patch.object(app_module.state, "add_log_entry"):
        app_module._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    apply_mock.assert_not_called()
    rec = cancel_review_store.get_pending("XL", "J-R")
    assert rec and rec["kind"] == "spool_changed"
    assert cancel_fetch_store.get_pending("XL", "J-R") is None       # dequeued


def test_swap_detected_but_no_rows_routes_to_no_spool():
    """Swap detected but the replacement isn't bound right now (resolve returns [])
    -> the no-rows branch stashes a recoverable no_spool review (no ledger burn)."""
    ctx, apply_mock = _completion_ctx(usage_map={0: 25.0}, end_snap={0: 999}, rows=[])
    for m in ctx:
        m.start()
    try:
        res = app_module.deduct_completed_print("XL", "f.gcode", "J-N", start_spools={"0": 100})
    finally:
        for m in reversed(ctx):
            m.stop()
    assert res["status"] == "pending_unresolved" and res["kind"] == "no_spool"
    apply_mock.assert_not_called()
    assert print_deduct_ledger.was_deducted("XL", "J-N") is False


def test_capture_skips_storing_on_empty_snapshot_blip():
    """A transient empty snapshot ({} from a Spoolman blip) on the first PRINTING
    tick must NOT flag snapshot_job — so the next tick retries instead of permanently
    disabling detection for the whole job."""
    snap = MagicMock(side_effect=[{}, {0: 100}])
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_snapshot_active_spools", snap):
        _latch("PRINTING", {"filename": "f.gcode", "job_id": 9, "progress": 0.4})
        assert "snapshot_job" not in app_module._PRINT_TRACKER["XL"]   # blip -> not flagged
        _latch("PRINTING", {"filename": "f.gcode", "job_id": 9, "progress": 0.5})
        assert app_module._PRINT_TRACKER["XL"]["start_spools"] == {"0": 100}  # retried
    assert snap.call_count == 2
