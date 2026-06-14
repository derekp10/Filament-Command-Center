"""Slice 7 — power-loss / restart latch persistence + recovery
(`print_tracker_store` + `_recover_print_tracker_on_start`).

The in-memory `_PRINT_TRACKER` is otherwise lost on an FCC / host restart, so a
cancel that happened (or a print that was running) during the outage would be
missed. The latch is persisted each monitor tick and reconciled on monitor start
against the printer's CURRENT state — resume → restore, no-resume → recover the
cancel from the last pulled progress, genuinely-ambiguous → manual review.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import print_tracker_store  # noqa: E402
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct_ledger  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    # Isolate the deduct stores too — a recovery test that drives the real
    # IDLE→ambiguous / STOPPED→cancel path reaches _create_pending_cancel_review and,
    # with no creds for the test printer, _enqueue_cancel_fetch — which must land in a
    # tmp store, NOT the live bind-mounted data/ queue (the XL::J9 leak, 2026-06-14).
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    # Run the deduct synchronously so a recovered cancel is observable inline.
    monkeypatch.setattr(app_module, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()
    yield
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()


def _entry(state="PRINTING", job_id="J9", filename="/usb/F.BGC", progress=0.4):
    e = {"state": state, "progress": progress}
    if job_id is not None:
        e["job_id"] = job_id
    if filename is not None:
        e["filename"] = filename
    return e


# ---------------------------------------------------------------------------
# print_tracker_store round-trip
# ---------------------------------------------------------------------------

def test_store_round_trip_and_clear():
    snap = {"XL": _entry()}
    print_tracker_store.save(snap)
    assert print_tracker_store.load() == snap
    print_tracker_store.clear()
    assert print_tracker_store.load() == {}


def test_load_missing_or_garbage_is_empty(tmp_path):
    assert print_tracker_store.load() == {}             # missing file
    with open(print_tracker_store._STORE_PATH, "w") as f:
        f.write("{ not json")
    assert print_tracker_store.load() == {}             # corrupt file


# ---------------------------------------------------------------------------
# Each tick persists the latch snapshot
# ---------------------------------------------------------------------------

def test_tick_persists_tracker_snapshot():
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "IDLE"}), \
         patch.object(app_module.prusalink_api, "get_printer_job", return_value=None), \
         patch.object(app_module, "_process_pending_cancel_fetches"):
        app_module._cancel_monitor_tick()
    saved = print_tracker_store.load()
    assert "XL" in saved and saved["XL"]["state"] == "IDLE"


# ---------------------------------------------------------------------------
# Recovery resolution table
# ---------------------------------------------------------------------------

def _recover_with(persisted, cur_state, cur_job=None):
    with patch.object(print_tracker_store, "load", return_value=persisted), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "get_printer_state",
                      return_value=({"state": cur_state} if cur_state is not None else None)), \
         patch.object(app_module.prusalink_api, "get_printer_job", return_value=cur_job), \
         patch.object(app_module, "_dispatch_cancel_edge") as dispatch, \
         patch.object(app_module.state, "add_log_entry") as log:
        app_module._recover_print_tracker_on_start()
    return dispatch, log


def test_recover_cancel_when_still_stopped_fires_deduct():
    """in-progress persisted + now STOPPED → it didn't resume → fire the deduct
    from the persisted progress."""
    dispatch, log = _recover_with({"XL": _entry(progress=0.4)}, "STOPPED")
    dispatch.assert_called_once()
    args = dispatch.call_args.args
    assert args[0] == "XL" and args[1] == "/usb/F.BGC" and args[2] == "J9"
    assert abs(args[3] - 0.4) < 1e-6
    assert log.call_args.args[1] == "WARNING"


def test_recover_error_state_also_fires():
    dispatch, _ = _recover_with({"XL": _entry()}, "ERROR")
    dispatch.assert_called_once()


def test_recover_resume_same_job_restores_latch_no_fire():
    """now PRINTING with the SAME job_id → it resumed → restore the latch,
    don't deduct."""
    dispatch, _ = _recover_with(
        {"XL": _entry(job_id="J9", progress=0.4)}, "PRINTING",
        cur_job={"job_id": "J9", "filename": "/usb/F.BGC", "progress": 0.5})
    dispatch.assert_not_called()
    assert app_module._PRINT_TRACKER["XL"]["job_id"] == "J9"


def test_recover_different_job_warns_and_latches_new_no_fire():
    """now PRINTING with a DIFFERENT job → old outcome unknown → warn (manual),
    latch the new job, don't deduct the old."""
    dispatch, log = _recover_with(
        {"XL": _entry(job_id="J9")}, "PRINTING",
        cur_job={"job_id": "J10", "filename": "/usb/N.BGC", "progress": 0.1})
    dispatch.assert_not_called()
    assert log.call_args.args[1] == "WARNING"
    assert app_module._PRINT_TRACKER["XL"]["job_id"] == "J10"


def test_recover_idle_after_inprogress_surfaces_ambiguous_review():
    """now IDLE → cleared during the outage, can't tell cancel vs completion →
    route to the AMBIGUOUS REVIEW (2026-06-13): download the now-unlocked file →
    compute → review flagged 'couldn't confirm'. NOT a silent 'weigh the spool'
    and NOT the auto-deduct cancel edge, but NEVER a phantom deduct either."""
    with patch.object(print_tracker_store, "load", return_value={"XL": _entry()}), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "IDLE"}), \
         patch.object(app_module, "_dispatch_cancel_edge") as cancel_disp, \
         patch.object(app_module, "_dispatch_ambiguous_edge") as amb_disp, \
         patch.object(app_module.state, "add_log_entry") as log:
        app_module._recover_print_tracker_on_start()
    cancel_disp.assert_not_called()
    amb_disp.assert_called_once()
    args = amb_disp.call_args.args
    # _dispatch_ambiguous_edge(name, filename, job_id, progress, fb_url)
    assert args[0] == "XL" and args[1] == "/usb/F.BGC" and args[2] == "J9"
    assert abs(args[3] - 0.4) < 1e-6
    assert log.call_args.args[1] == "WARNING"


def test_recover_attention_restores_latch_no_fire():
    """now ATTENTION (filament-prompt still up) on restart → the print is still
    mid-something, NOT ended → restore the latch and defer to LIVE edge-detection;
    neither a cancel nor an ambiguous review fires (no premature surface). The
    live monitor fires the real edge when it later reaches IDLE/STOPPED."""
    persisted = {"XL": _entry(state="ATTENTION", job_id="J9",
                              filename="/usb/F.BGC", progress=0.91)}
    with patch.object(print_tracker_store, "load", return_value=persisted), \
         patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "ATTENTION"}), \
         patch.object(app_module, "_dispatch_cancel_edge") as cancel_disp, \
         patch.object(app_module, "_dispatch_ambiguous_edge") as amb_disp:
        app_module._recover_print_tracker_on_start()
    cancel_disp.assert_not_called()
    amb_disp.assert_not_called()
    assert app_module._PRINT_TRACKER["XL"]["job_id"] == "J9"
    assert app_module._PRINT_TRACKER["XL"]["filename"] == "/usb/F.BGC"


def test_recover_finished_no_fire_no_warn():
    """now FINISHED → completed → leave to FilaBridge (no deduct, no warning) when
    the cutover flag is OFF (the pre-Phase-C behavior). The flag is mocked off so
    this stays deterministic regardless of the live config value (dev currently
    runs with fcc_owns_completion_deduct ON for the Phase-D rehearsal)."""
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=False):
        dispatch, log = _recover_with({"XL": _entry()}, "FINISHED")
    dispatch.assert_not_called()
    log.assert_not_called()


def test_recover_offline_restores_latch_no_fire():
    """offline on restart → restore the latch, defer to normal edge-detection."""
    dispatch, _ = _recover_with({"XL": _entry(job_id="J9")}, None)
    dispatch.assert_not_called()
    assert app_module._PRINT_TRACKER["XL"]["job_id"] == "J9"


def test_recover_bare_entry_seeds_baseline_no_fire():
    """A persisted entry with no latched job (already fired + reset) → just seed
    the baseline state, nothing to recover."""
    dispatch, log = _recover_with({"XL": {"state": "STOPPED"}}, "IDLE")
    dispatch.assert_not_called()
    assert app_module._PRINT_TRACKER["XL"] == {"state": "STOPPED"}


def test_recover_empty_store_is_noop():
    dispatch, _ = _recover_with({}, "IDLE")
    dispatch.assert_not_called()
