"""FilaBridge Phase-2 cutover — FINISHED-completion ownership (deployed DARK).

When the `fcc_owns_completion_deduct` flag is ON, an in-progress→FINISHED edge
fires FCC's own completion deduct using the slicer FOOTER (the full per-tool
estimate, exact = what FilaBridge billed; neither side handles M486). It
auto-applies SILENTLY (no preview/confirm — grams are exact) and is exactly-once
via the (printer, job_id) ledger. Default OFF so the code ships dark.

Pinned here:
- the edge fires a COMPLETION (not a cancel) only when the flag is on
- deduct_completed_print: footer-based apply / skipped / awaiting_fetch (lock)
- _compute_cancel_usage(use_footer=True) parses the footer, not the prefix
- the deferred-fetch queue carries kind and routes a 'complete' retry
- restart recovery fires the missed completion only when the flag is on
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
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_tracker():
    app_module._PRINT_TRACKER.clear()
    prev_async = app_module._CANCEL_DEDUCT_RUN_ASYNC
    app_module._CANCEL_DEDUCT_RUN_ASYNC = False  # synchronous dispatch
    try:
        yield
    finally:
        app_module._CANCEL_DEDUCT_RUN_ASYNC = prev_async
        app_module._PRINT_TRACKER.clear()


@pytest.fixture
def stores_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))


def _creds(*a, **k):
    return {"ip_address": "1.2.3.4", "api_key": "k"}


def _state(s):
    return {"state": s, "is_active": s in ("PRINTING", "PAUSING", "RESUMING")}


def _job(filename="/usb/print.gcode", job_id=7, progress=0.5, meta=None):
    return {"filename": filename, "job_id": job_id, "progress": progress,
            "file_meta": meta or {}}


def _drive(states, jobs=None):
    jobs = jobs or {}
    for i, st in enumerate(states):
        job_ret = jobs.get(i, _job())
        with patch.object(app_module.prusalink_api, "get_printer_job", return_value=job_ret):
            app_module._track_print_edge("XL", _state(st) if st else None, "http://fb")


# --------------------------------------------------------------------------- #
# Edge gating: FINISHED fires a COMPLETION only when the flag is on            #
# --------------------------------------------------------------------------- #

def test_finished_does_not_fire_when_flag_off():
    comp = MagicMock()
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=False), \
         patch.object(app_module, "_on_completion_edge", comp):
        _drive(["PRINTING", "FINISHED"], jobs={0: _job(job_id=9)})
    assert comp.call_count == 0


def test_finished_fires_completion_when_flag_on():
    comp = MagicMock()
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_on_completion_edge", comp):
        _drive(["PRINTING", "FINISHED"],
               jobs={0: _job(filename="/usb/done.gcode", job_id=9, progress=0.95)})
    assert comp.call_count == 1
    args = comp.call_args.args
    # _on_completion_edge(printer, filename, job_id, fb_url)
    assert args[0] == "XL" and args[1] == "/usb/done.gcode" and args[2] == 9


def test_finished_with_flag_on_does_not_fire_a_cancel():
    cancel, comp = MagicMock(), MagicMock()
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_on_cancel_edge", cancel), \
         patch.object(app_module, "_on_completion_edge", comp):
        _drive(["PRINTING", "FINISHED"])
    assert cancel.call_count == 0 and comp.call_count == 1


def test_stopped_still_fires_cancel_not_completion_with_flag_on():
    cancel, comp = MagicMock(), MagicMock()
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "_on_cancel_edge", cancel), \
         patch.object(app_module, "_on_completion_edge", comp):
        _drive(["PRINTING", "STOPPED"])
    assert cancel.call_count == 1 and comp.call_count == 0


# --------------------------------------------------------------------------- #
# deduct_completed_print — footer-based auto-apply                            #
# --------------------------------------------------------------------------- #

def test_completed_print_deducts_footer(stores_tmp):
    captured = {}

    def _apply(printer, usage_map, fb_url, strategy_label=""):
        captured["usage_map"] = dict(usage_map)
        captured["label"] = strategy_label
        return 2, [{"sid": 100, "grams": 25.0, "remaining": 900.0},
                   {"sid": 200, "grams": 40.0, "remaining": 800.0}]

    pm = {"XL-1": {"printer_name": "XL", "position": 0},
          "XL-2": {"printer_name": "XL", "position": 1}}
    gcode = "; header\nG1 X1 E1\n; filament used [g] = 25, 40\n"
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}), \
         patch.object(app_module, "_apply_usage_to_printer", side_effect=_apply):
        res = app_module.deduct_completed_print("XL", "done.gcode", "J-9")
    assert res["status"] == "deducted"
    # The FOOTER array (25, 40) is deducted — NOT a prefix-parse of the 1mm body.
    assert captured["usage_map"] == {0: 25.0, 1: 40.0}
    assert captured["label"] == "Complete"
    assert print_deduct_ledger.was_deducted("XL", "J-9") is True


def test_completed_print_exactly_once(stores_tmp):
    print_deduct_ledger.record_deduct("XL", "J-9", filename="done.gcode", scale=1.0, grams=65)
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module, "_apply_usage_to_printer") as apply_mock:
        res = app_module.deduct_completed_print("XL", "done.gcode", "J-9")
    assert res["status"] == "skipped"
    apply_mock.assert_not_called()


def test_completed_print_download_lock_defers_with_complete_kind(stores_tmp):
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode", return_value=None), \
         patch.object(app_module, "_apply_usage_to_printer") as apply_mock:
        res = app_module.deduct_completed_print("XL", "done.gcode", "J-9")
    assert res["status"] == "awaiting_fetch"
    apply_mock.assert_not_called()
    rec = cancel_fetch_store.get_pending("XL", "J-9")
    assert rec and rec.get("kind") == "complete"
    # Not yet in the ledger — a deferred completion can still deduct later.
    assert print_deduct_ledger.was_deducted("XL", "J-9") is False


def test_completed_print_no_spool_surfaces_warning_not_silent(stores_tmp):
    """Footer has usage but no spool is loaded at the active position → must NOT
    log a green '0.0g' SUCCESS + record the full footer; surface a WARNING and
    record grams=0 (honest, can't re-fire). Mirrors the cancel no_spools path."""
    pm = {"XL-1": {"printer_name": "XL", "position": 0}}
    gcode = "; filament used [g] = 25\n"
    logs = []
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}), \
         patch.object(app_module, "_apply_usage_to_printer", return_value=(0, [])), \
         patch.object(app_module.state, "add_log_entry", side_effect=lambda *a, **k: logs.append(a)):
        res = app_module.deduct_completed_print("XL", "done.gcode", "J-9")
    assert res["status"] == "no_spools"
    assert print_deduct_ledger.was_deducted("XL", "J-9") is True  # honest grams=0, no re-fire
    assert any("no mapped spool" in str(a[0]) and len(a) > 1 and a[1] == "WARNING" for a in logs), logs


def test_fetch_retry_complete_abandoned_when_flag_off(stores_tmp):
    """A completion queued behind the finish-screen lock must NOT fire if the
    cutover was rolled back (flag off) — FilaBridge owns completions again, so
    firing FCC's deduct would double-bill. The entry is abandoned (popped)."""
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-9", "filename": "done.gcode",
        "progress": 1.0, "first_seen": time.time(), "kind": "complete",
        "attempts": 1, "last_status": "awaiting_fetch"})
    states = {"XL": _state("IDLE")}  # unlocked, but flag is now OFF
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=False), \
         patch.object(app_module, "deduct_completed_print") as comp:
        app_module._process_pending_cancel_fetches(states, "http://fb")
    comp.assert_not_called()
    assert cancel_fetch_store.get_pending("XL", "J-9") is None  # abandoned


def test_completed_print_no_creds_defers(stores_tmp):
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", return_value=None):
        res = app_module.deduct_completed_print("XL", "done.gcode", "J-9")
    assert res["status"] == "awaiting_fetch"
    assert cancel_fetch_store.get_pending("XL", "J-9").get("kind") == "complete"


# --------------------------------------------------------------------------- #
# _compute_cancel_usage(use_footer=…) — footer vs prefix                       #
# --------------------------------------------------------------------------- #

def test_compute_use_footer_vs_prefix_differ():
    # Body extrudes only 1mm on T0; the FOOTER claims the full 25g. A completion
    # must take the footer (25g), the cancel prefix-parse takes the body (≈2.5g).
    gcode = ("M83\nT0\nG1 X10 E1\n"
             "; filament used [mm] = 10\n; filament used [g] = 25\n")
    pm = {"XL-1": {"printer_name": "XL", "position": 0}}
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}):
        footer_map, t1 = app_module._compute_cancel_usage(
            "XL", "f", "J", 1.0, "1.2.3.4", "k", use_footer=True)
        prefix_map, t2 = app_module._compute_cancel_usage(
            "XL", "f", "J", 1.0, "1.2.3.4", "k", use_footer=False)
    assert t1 is None and t2 is None
    assert footer_map == {0: 25.0}
    # prefix: 1mm * (25g/10mm) = 2.5g — strictly less than the footer.
    assert abs(prefix_map[0] - 2.5) < 1e-6
    assert footer_map[0] > prefix_map[0]


# --------------------------------------------------------------------------- #
# Deferred-fetch routing by kind                                              #
# --------------------------------------------------------------------------- #

def test_fetch_retry_routes_complete_to_completion_deduct(stores_tmp):
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-9", "filename": "done.gcode",
        "progress": 1.0, "first_seen": time.time(), "kind": "complete",
        "attempts": 1, "last_status": "awaiting_fetch"})
    calls = {}

    def _complete(printer, filename, job_id, fb_url=None):
        calls["complete"] = (printer, filename, job_id)
        return {"status": "deducted", "job_id": job_id}

    # Printer is IDLE → file unlocked → the retry should fire deduct_completed_print
    # (flag still ON — the cutover is in effect).
    states = {"XL": _state("IDLE")}
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module, "deduct_completed_print", side_effect=_complete) as comp, \
         patch.object(app_module, "_create_pending_cancel_review") as review:
        app_module._process_pending_cancel_fetches(states, "http://fb")
    assert calls.get("complete") == ("XL", "done.gcode", "J-9")
    review.assert_not_called()
    assert cancel_fetch_store.get_pending("XL", "J-9") is None  # resolved → popped


def test_fetch_retry_ambiguous_routes_to_review_flagged(stores_tmp):
    """A deferred-fetch entry flagged ambiguous (kind='cancel', ambiguous=True —
    an in-progress→IDLE that hit a transient blip) must route the retry to
    _create_pending_cancel_review WITH ambiguous=True, so a review queued behind a
    blip stays flagged 'couldn't confirm' — never the completion auto-apply."""
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-7", "filename": "amb.gcode",
        "progress": 0.26, "first_seen": time.time(), "kind": "cancel",
        "ambiguous": True, "attempts": 1, "last_status": "awaiting_fetch"})
    states = {"XL": _state("IDLE")}  # unlocked
    with patch.object(app_module, "deduct_completed_print") as comp, \
         patch.object(app_module, "_create_pending_cancel_review",
                      return_value={"status": "pending", "job_id": "J-7"}) as review:
        app_module._process_pending_cancel_fetches(states, "http://fb")
    comp.assert_not_called()
    review.assert_called_once()
    assert review.call_args.kwargs.get("ambiguous") is True
    assert cancel_fetch_store.get_pending("XL", "J-7") is None  # resolved → popped


def test_fetch_retry_plain_cancel_routes_with_ambiguous_false(stores_tmp):
    """A normal cancel fetch (no ambiguous flag) routes the retry with
    ambiguous=False (the default), so the wording stays the plain cancel review."""
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-8", "filename": "x.gcode",
        "progress": 0.5, "first_seen": time.time(), "kind": "cancel",
        "attempts": 1, "last_status": "awaiting_fetch"})
    states = {"XL": _state("IDLE")}
    with patch.object(app_module, "_create_pending_cancel_review",
                      return_value={"status": "pending", "job_id": "J-8"}) as review:
        app_module._process_pending_cancel_fetches(states, "http://fb")
    review.assert_called_once()
    assert review.call_args.kwargs.get("ambiguous") is False


def test_fetch_retry_waits_while_finished_locked(stores_tmp):
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": "J-9", "filename": "done.gcode",
        "progress": 1.0, "first_seen": time.time(), "kind": "complete",
        "attempts": 1, "last_status": "awaiting_fetch"})
    # Still FINISHED (finish screen up) → file locked → must NOT attempt yet.
    states = {"XL": _state("FINISHED")}
    with patch.object(app_module, "deduct_completed_print") as comp:
        app_module._process_pending_cancel_fetches(states, "http://fb")
    comp.assert_not_called()
    assert cancel_fetch_store.get_pending("XL", "J-9") is not None  # still queued


# --------------------------------------------------------------------------- #
# _enqueue_cancel_fetch kind                                                   #
# --------------------------------------------------------------------------- #

def test_enqueue_stores_complete_kind(stores_tmp):
    with patch.object(app_module.state, "add_log_entry"):
        app_module._enqueue_cancel_fetch("XL", "done.gcode", "J-9", 1.0, kind="complete")
    assert cancel_fetch_store.get_pending("XL", "J-9").get("kind") == "complete"


def test_enqueue_default_kind_is_cancel(stores_tmp):
    with patch.object(app_module.state, "add_log_entry"):
        app_module._enqueue_cancel_fetch("XL", "x.gcode", "J-1", 0.5)
    assert cancel_fetch_store.get_pending("XL", "J-1").get("kind") == "cancel"


# --------------------------------------------------------------------------- #
# Restart recovery — FINISHED branch is flag-gated                            #
# --------------------------------------------------------------------------- #

def test_recover_finished_fires_completion_when_flag_on():
    entry = {"state": "PRINTING", "job_id": "J-9", "filename": "done.gcode", "progress": 0.9}
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=True), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value=_state("FINISHED")), \
         patch.object(app_module, "_dispatch_completion_edge") as disp:
        acted = app_module._recover_one_print_latch("XL", entry, "http://fb")
    assert acted is True
    disp.assert_called_once()
    assert disp.call_args.args[:3] == ("XL", "done.gcode", "J-9")


def test_recover_finished_noop_when_flag_off():
    entry = {"state": "PRINTING", "job_id": "J-9", "filename": "done.gcode", "progress": 0.9}
    with patch.object(app_module, "_fcc_owns_completion_deduct", return_value=False), \
         patch.object(app_module.prusalink_api, "get_printer_state", return_value=_state("FINISHED")), \
         patch.object(app_module, "_dispatch_completion_edge") as disp:
        acted = app_module._recover_one_print_latch("XL", entry, "http://fb")
    assert acted is False
    disp.assert_not_called()
