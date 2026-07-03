"""Group 22.3(b) → runout / mid-print-swap AUTO-SPLIT (feature/runout-auto-split, 2026-07-03).

A COMPLETED print whose toolhead spool CHANGED mid-print (a filament runout or a deliberate
early swap) now auto-computes the per-segment grams: the run-out spool is charged its own
segment (0→swap) plus an optional per-printer sensor→nozzle path remnant, the replacement its
segment (swap→end). BOTH rows are surfaced in the `spool_changed` review for a one-tap
confirm/adjust (Derek's ask: show + settle both spools together, incl. an early swap of a
nearly-empty spool). Degrades to the legacy full-footer manual review when the gcode can't be
fetched/parsed.

Validated 2026-07-02 against a real Core One runout (job 1078): fed the true cut, the
prefix-parse reproduced the weighed replacement to 0.08 g; the whole error was the CAPTURED
swap progress (19% vs true 21.7%), which the ATTENTION-park progress refinement closes.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import print_deduct  # noqa: E402
import print_monitor  # noqa: E402
import prusalink_api  # noqa: E402
import config_loader  # noqa: E402
import spoolman_api  # noqa: E402
import print_deduct_ledger  # noqa: E402
import cancel_review_store  # noqa: E402
import cancel_fetch_store  # noqa: E402
import print_tracker_store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    prev_async = print_monitor._CANCEL_DEDUCT_RUN_ASYNC
    print_monitor._CANCEL_DEDUCT_RUN_ASYNC = False
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()
    try:
        yield
    finally:
        print_monitor._CANCEL_DEDUCT_RUN_ASYNC = prev_async
        with app_module._PRINT_TRACKER_LOCK:
            app_module._PRINT_TRACKER.clear()


def _spool(sid, initial, used, name=None, color="ABCDEF"):
    return {"id": sid, "initial_weight": initial, "used_weight": used,
            "filament": {"name": name or f"F{sid}", "color_hex": color}}


# The real job-1078 numbers: footer 109.76 g, prefix-parse to the captured 19% = 23.78 g.
SEG = {"footer": {0: 109.76}, "cums": [{0: 23.78}]}


# --------------------------------------------------------------------------- #
# _tool_grams                                                                  #
# --------------------------------------------------------------------------- #
def test_tool_grams_single_tool_folds_to_position():
    assert print_deduct._tool_grams({0: 5.0}, 0) == 5.0
    assert print_deduct._tool_grams({3: 7.0}, 3) == 7.0
    # a sole entry folds onto any position (single-extruder print)
    assert print_deduct._tool_grams({0: 9.0}, 1) == 9.0
    assert print_deduct._tool_grams({}, 0) == 0.0


# --------------------------------------------------------------------------- #
# _compute_swap_split                                                          #
# --------------------------------------------------------------------------- #
def test_compute_swap_split_runout_single_swap():
    swap_log = [{"position": 0, "progress": 0.19, "from_sid": 126, "to_sid": 127, "runout": True}]
    with patch.object(prusalink_api, "compute_segment_usage", return_value=SEG):
        out = print_deduct._compute_swap_split("ip", "k", "f.bgcode", {0: 109.76},
                                               swap_log, {"0": 126}, path_filament_g=0)
    assert out[0][0] == {"sid": 126, "grams": 23.78, "segment": 0, "runout": True}
    assert out[0][1] == {"sid": 127, "grams": 85.98, "segment": 1, "runout": False}


def test_compute_swap_split_adds_path_filament_on_runout():
    swap_log = [{"position": 0, "progress": 0.19, "from_sid": 126, "to_sid": 127, "runout": True}]
    with patch.object(prusalink_api, "compute_segment_usage", return_value=SEG):
        out = print_deduct._compute_swap_split("ip", "k", "f.bgcode", {0: 109.76},
                                               swap_log, {"0": 126}, path_filament_g=2.0)
    assert out[0][0]["grams"] == 25.78   # 23.78 deposited + 2.0 path remnant
    assert out[0][1]["grams"] == 85.98   # replacement unchanged (footer - deposited)


def test_compute_swap_split_no_path_on_manual_early_swap():
    """A deliberate PAUSED swap (runout=False) gets NO path remnant on the old spool."""
    swap_log = [{"position": 0, "progress": 0.19, "from_sid": 126, "to_sid": 127, "runout": False}]
    with patch.object(prusalink_api, "compute_segment_usage", return_value=SEG):
        out = print_deduct._compute_swap_split("ip", "k", "f.bgcode", {0: 109.76},
                                               swap_log, {"0": 126}, path_filament_g=2.0)
    assert out[0][0]["grams"] == 23.78   # no path added on a non-runout swap


def test_compute_swap_split_none_on_fetch_failure():
    with patch.object(prusalink_api, "compute_segment_usage", return_value=None):
        assert print_deduct._compute_swap_split(
            "ip", "k", "f", {0: 1}, [{"position": 0, "progress": 0.5, "to_sid": 2}], {"0": 1}) is None


def test_compute_swap_split_empty_swap_log():
    assert print_deduct._compute_swap_split("ip", "k", "f", {0: 1}, [], {"0": 1}) is None


def test_compute_swap_split_rejects_cum_over_footer():
    """A bad remap/parse that overshoots the footer → None (don't trust the split)."""
    bad = {"footer": {0: 10.0}, "cums": [{0: 12.0}]}
    with patch.object(prusalink_api, "compute_segment_usage", return_value=bad):
        assert print_deduct._compute_swap_split(
            "ip", "k", "f", {0: 10}, [{"position": 0, "progress": 0.5, "to_sid": 2}], {"0": 1}) is None


# --------------------------------------------------------------------------- #
# _split_to_review_rows                                                        #
# --------------------------------------------------------------------------- #
def test_split_to_review_rows_both_spools():
    split = {0: [{"sid": 126, "grams": 25.78, "segment": 0, "runout": True},
                 {"sid": 127, "grams": 85.98, "segment": 1, "runout": False}]}

    def gs(sid):
        return _spool(126, 1000, 976) if sid == 126 else _spool(127, 1162.5, 148.6)

    with patch.object(spoolman_api, "get_spool", side_effect=gs), \
         patch.object(spoolman_api, "format_spool_display", return_value={"text": "x", "color": "AAA"}):
        rows = print_deduct._split_to_review_rows(split)
    by = {r["sid"]: r for r in rows}
    assert by[126]["grams"] == 25.78 and by[126]["runout"] is True
    assert by[127]["grams"] == 85.98
    assert by[126]["remaining_before"] == 24.0   # 1000 - 976


def test_split_to_review_rows_same_sid_summed():
    """A→B→A: the original spool fed two segments — collapse to ONE row (confirm keys by sid)."""
    split = {0: [{"sid": 100, "grams": 10.0, "segment": 0, "runout": False},
                 {"sid": 200, "grams": 5.0, "segment": 1, "runout": False},
                 {"sid": 100, "grams": 7.0, "segment": 2, "runout": False}]}
    with patch.object(spoolman_api, "get_spool", side_effect=lambda s: _spool(s, 1000, 0)), \
         patch.object(spoolman_api, "format_spool_display", return_value={"text": "x", "color": "AAA"}):
        rows = print_deduct._split_to_review_rows(split)
    by = {r["sid"]: r for r in rows}
    assert by[100]["grams"] == 17.0   # 10 + 7 summed onto one row
    assert by[200]["grams"] == 5.0


def test_split_to_review_rows_none_on_missing_spool():
    split = {0: [{"sid": 1, "grams": 5.0, "segment": 0, "runout": False}]}
    with patch.object(spoolman_api, "get_spool", return_value=None):
        assert print_deduct._split_to_review_rows(split) is None


# --------------------------------------------------------------------------- #
# _path_filament_g                                                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cfg,name,exp", [
    ({"path_filament_g": {"XL": 4, "default": 1}}, "XL", 4.0),
    ({"path_filament_g": {"XL": 4, "default": 1}}, "Other", 1.0),
    ({"path_filament_g": 3}, "Anything", 3.0),
    ({}, "XL", 0.0),
    ({"path_filament_g": {"XL": 4}}, "Other", 0.0),   # no default → 0
    ({"path_filament_g": "bad"}, "XL", 0.0),           # malformed → 0, never raises
])
def test_path_filament_g(cfg, name, exp):
    with patch.object(config_loader, "load_config", return_value=cfg):
        assert print_deduct._path_filament_g(name) == exp


# --------------------------------------------------------------------------- #
# _route_completion_to_review — the auto-split path + fallback                 #
# --------------------------------------------------------------------------- #
def test_route_auto_split_builds_both_rows():
    swap_log = [{"position": 0, "progress": 0.19, "from_sid": 126, "to_sid": 127, "runout": True}]

    def gs(sid):
        return _spool(126, 1000, 976) if sid == 126 else _spool(127, 1162.5, 148.6)

    with patch.object(prusalink_api, "compute_segment_usage", return_value=SEG), \
         patch.object(spoolman_api, "get_spool", side_effect=gs), \
         patch.object(spoolman_api, "format_spool_display", return_value={"text": "x", "color": "AAA"}), \
         patch.object(config_loader, "load_config", return_value={"path_filament_g": {"CoreOne": 2}}):
        res = print_deduct._route_completion_to_review(
            "CoreOne", "f.bgcode", 1078, {0: 109.76}, "http://fb", [0],
            swap_log=swap_log, ip_address="ip", api_key="k", start_spools={"0": 126})
    assert res["status"] == "pending_spool_changed"
    assert res["auto_split"] is True
    rec = cancel_review_store.get_pending("CoreOne", 1078)
    assert rec["auto_split"] is True and rec["kind"] == "spool_changed"
    sids = {r["sid"]: r["grams"] for r in rec["spools"]}
    assert sids == {126: 25.78, 127: 85.98}   # 23.78 + 2 path remnant, and footer - 23.78


def test_route_falls_back_to_full_footer_when_gcode_unavailable():
    """compute_segment_usage None (printer offline / decode fail) → the legacy manual review
    (single replacement row, full footer, auto_split False)."""
    full_row = [{"sid": 127, "grams": 109.76, "toolhead": "C", "position": 0,
                 "current_used": 148.6, "initial_weight": 1162.5, "remaining_before": 1013.9,
                 "remaining_after": 904.1, "display": "x", "color": "AAA", "ambiguous": False}]
    with patch.object(prusalink_api, "compute_segment_usage", return_value=None), \
         patch.object(print_deduct, "_resolve_usage_to_spools", return_value=full_row):
        res = print_deduct._route_completion_to_review(
            "CoreOne", "f.bgcode", 1080, {0: 109.76}, "http://fb", [0],
            swap_log=[{"position": 0, "progress": 0.19, "to_sid": 127}],
            ip_address="ip", api_key="k", start_spools={"0": 126})
    assert res["auto_split"] is False
    rec = cancel_review_store.get_pending("CoreOne", 1080)
    assert rec["auto_split"] is False
    assert [r["sid"] for r in rec["spools"]] == [127]


def test_route_no_ip_key_falls_back():
    """No ip/api_key (can't fetch the gcode) → the legacy manual review, not a crash."""
    full_row = [{"sid": 127, "grams": 109.76, "toolhead": "C", "position": 0,
                 "current_used": 0, "initial_weight": 1000, "remaining_before": 1000,
                 "remaining_after": 890.24, "display": "x", "color": "AAA", "ambiguous": False}]
    with patch.object(print_deduct, "_resolve_usage_to_spools", return_value=full_row):
        res = print_deduct._route_completion_to_review(
            "CoreOne", "f.bgcode", 1081, {0: 109.76}, "http://fb", [0],
            swap_log=[{"position": 0, "progress": 0.19, "to_sid": 127}])
    assert res["auto_split"] is False


# --------------------------------------------------------------------------- #
# _record_swap_events — the runout flag                                        #
# --------------------------------------------------------------------------- #
def test_record_swap_event_carries_runout_flag():
    entry = {"start_spools": {"0": 100}}
    app_module._record_swap_events(entry, {0: 200}, 0.5, runout=True)
    assert entry["swap_log"][0]["runout"] is True
    entry2 = {"start_spools": {"0": 100}}
    app_module._record_swap_events(entry2, {0: 200}, 0.5)   # default
    assert entry2["swap_log"][0]["runout"] is False


# --------------------------------------------------------------------------- #
# ATTENTION-park progress capture in _track_print_edge                         #
# --------------------------------------------------------------------------- #
def _latch_job(state, job):
    with patch.object(app_module.prusalink_api, "get_printer_job", return_value=job):
        app_module._track_print_edge("XL", {"state": state}, "http://fb")


def test_attention_park_captures_frozen_progress_and_runout():
    """A runout ATTENTION park FREEZES progress ABOVE the last PRINTING sample; the swap
    event must cut at the frozen pause progress (not the stale resume value) and be flagged
    runout. This is the ~3 g accuracy fix (job 1078: captured 19% vs true 21.7%)."""
    snap = MagicMock(side_effect=[{0: 100}, {0: 200}])
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", snap):
        _latch_job("PRINTING",  {"filename": "f", "job_id": 9, "progress": 0.19})   # start
        _latch_job("ATTENTION", {"filename": "f", "job_id": 9, "progress": 0.22})   # runout park (frozen)
        _latch_job("PRINTING",  {"filename": "f", "job_id": 9, "progress": 0.19})   # resume (reports stale)
    ev = app_module._PRINT_TRACKER["XL"]["swap_log"][0]
    assert ev["progress"] == 0.22      # the FROZEN pause value, not the stale 0.19
    assert ev["runout"] is True
    # markers consumed so a subsequent pause in the same job starts clean
    assert "pause_progress" not in app_module._PRINT_TRACKER["XL"]
    assert "saw_attention" not in app_module._PRINT_TRACKER["XL"]


def test_paused_manual_swap_not_flagged_runout():
    """A deliberate PAUSED swap (no ATTENTION) is captured but NOT flagged runout, so its
    old spool won't be charged the path remnant."""
    snap = MagicMock(side_effect=[{0: 100}, {0: 200}])
    with patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(print_deduct, "_snapshot_active_spools", snap):
        _latch_job("PRINTING", {"filename": "f", "job_id": 9, "progress": 0.30})
        _latch_job("PAUSED",   {"filename": "f", "job_id": 9, "progress": 0.30})
        _latch_job("PRINTING", {"filename": "f", "job_id": 9, "progress": 0.30})
    ev = app_module._PRINT_TRACKER["XL"]["swap_log"][0]
    assert ev["runout"] is False
