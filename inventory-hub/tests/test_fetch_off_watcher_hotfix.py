"""Hotfix 2026-11-11, scope C: downloads never block the watcher, and a restart
mid-download loses nothing.

PrusaLink serves a print file at about 15 KB/s, so the INDX's take 20 minutes
(prod job 1141). Two things went wrong around that wait:

  - A queued fetch (a file locked behind the cancel or finish screen at its edge)
    was retried INSIDE the monitor tick, so while one printer's file trickled in no
    printer was watched at all: another printer's cancel or finish was seen up to
    20 minutes late. Derek: "waiting on one download shouldn't stop prints from
    other printers being processed when they complete in FCC".
  - The live edge kept the print only in its thread's memory until the review was
    stashed (or a download failed), and the latch was already reset at the edge, so
    a restart or an update during those 20 minutes lost the print: no review, no
    ledger entry, no warning.

Pinned here:
  - the edge writes the print's fetch record BEFORE its download (status
    "in_flight", no "clear the screen" nudge; the nudge is logged once, the first
    time a download really fails), and the record is dropped when the compute
    reaches an outcome;
  - a thread of this process computing a print claims it: the loop skips a claimed
    print, starts no second download on a printer that has one in flight, and a
    second edge for a print being computed leaves it to that thread;
  - the loop only decides which records are due; each due retry runs on its own
    daemon thread, so the tick returns at once (inline when _CANCEL_DEDUCT_RUN_ASYNC
    is False, as tests run), and a raise keeps its meaning there;
  - the live completion stamps `charging_since` before its first spool write, as
    the queue's retry does, so a restart mid-charge never charges twice (the next
    tick, or a restart's recovery firing the edge again, gives it up);
  - a re-queue's read-modify-write is one locked store step, and each store keeps
    every record written at once.

`_Died` stands for FCC stopping mid-way: a BaseException, so it passes every
`except Exception` on its way out, as the real stop does.

HEAD proof: run on the branch before scope C (dbd9669 = main 626a10e + scope A),
every test here fails except the two marked "passes before the change by design".
"""
from __future__ import annotations

import os
import sys
import threading
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import config_loader  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import print_monitor  # noqa: E402
import print_tracker_store  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop  # noqa: E402

XL = "XL"
INDX = "🦝 Core One INDX"
CREDS = {"ip_address": "1.2.3.4", "api_key": "k"}
NUDGE = "Clear it on the printer"


class _Died(BaseException):
    """FCC stopping mid-way (a restart, a deploy, the TrueNAS update cron)."""


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    # This process's claims and given-up completions start empty, as at boot.
    monkeypatch.setattr(print_monitor, "_FETCH_CLAIMS", set(), raising=False)
    monkeypatch.setattr(print_monitor, "_ABANDONED_COMPLETIONS", set())
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    monkeypatch.setattr(config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
    monkeypatch.setattr(config_loader, "load_config", lambda: {})
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    # No Spoolman read unless a test's rig answers it.
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {})
    monkeypatch.setattr(print_deduct, "_heads_snapshot", lambda *a, **k: [])
    monkeypatch.setattr(print_deduct, "_capture_print_heads", lambda *a, **k: None, raising=False)
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()
    before = set(threading.enumerate())
    yield
    _join_new(before)
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append(msg))
    return calls


@pytest.fixture
def hublog(monkeypatch):
    lines = []
    monkeypatch.setattr(state.logger, "info", lambda msg, *a, **k: lines.append(str(msg)))
    return lines


def _join_new(before, timeout=10.0):
    """Wait for every thread started since `before` (a test's edge or retry
    threads), so none runs on into the next test's stores."""
    for t in list(threading.enumerate()):
        if t not in before and t is not threading.current_thread():
            t.join(timeout)


def _within(seconds, fn, *args):
    """Run fn on a helper thread: True when it returned within `seconds`."""
    done, box = threading.Event(), {}

    def _run():
        try:
            fn(*args)
        except BaseException as e:  # noqa: BLE001 - handed back to the test below
            box["error"] = e
        finally:
            done.set()
    threading.Thread(target=_run, daemon=True).start()
    finished = done.wait(seconds)
    if finished and "error" in box:
        raise box["error"]
    return finished


def _wait_for(cond, seconds=10.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def _spool(used, loc):
    return {"used_weight": used, "initial_weight": 1000.0, "archived": False,
            "location": loc, "filament": {"weight": 1000.0}, "extra": {}}


def _job(progress=0.4, job_id=7, filename="x.gcode"):
    return {"filename": filename, "job_id": job_id, "progress": progress}


def _tick(printer, st, job=None):
    with patch.object(print_monitor.prusalink_api, "get_printer_job", return_value=job):
        print_monitor._track_print_edge(printer, {"state": st}, "http://fb")


def _queue(printer, job_id, kind="cancel", **extra):
    rec = {"printer_name": printer, "job_id": str(job_id), "filename": "x.gcode", "progress": 0.5,
           "first_seen": time.time(), "kind": kind, "ambiguous": False, "attempts": 1,
           "last_status": "awaiting_fetch"}
    rec.update(extra)
    cancel_fetch_store.add_pending(rec)


def _restart():
    """A fresh FCC process: no thread holds a print, nothing given up yet."""
    print_monitor._FETCH_CLAIMS.clear()
    print_monitor._ABANDONED_COMPLETIONS.clear()
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()


class Rig:
    """The XL's two heads as the deduct reads them (`on`: what Spoolman says is on
    each head now) and Spoolman's spool records over the wire (#200 waits on a
    shelf). Only the download is stubbed, by each test."""

    def __init__(self):
        self.sm = WeightWireSpoolman({100: _spool(700.0, "XL-1"), 200: _spool(10.0, "SHELF-1")})
        self.on = {"XL-1": 100, "XL-2": None}

    def _capture(self, printer_name, fb_url):
        return [{"toolhead": th, "position": pos, "sid": self.on.get(th),
                 "sids": [self.on[th]] if self.on.get(th) is not None else []}
                for th, pos in (("XL-1", 0), ("XL-2", 1))]

    def __enter__(self):
        self._ctx = [
            patch.object(print_deduct, "_capture_print_heads", side_effect=self._capture, create=True),
            patch.object(print_deduct.prusalink_api, "fetch_printer_credentials", return_value=dict(CREDS)),
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
            patch.object(spoolman_api.requests, "get", side_effect=self.sm._get),
            patch.object(spoolman_api.requests, "patch", side_effect=self.sm._patch),
        ]
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


# --------------------------------------------------------------------------- #
# Retries run off the monitor thread                                           #
# --------------------------------------------------------------------------- #

def test_a_tick_returns_while_a_queued_download_blocks_and_another_printers_cancel_is_still_seen(monkeypatch):
    """The INDX's queued cancel is retried once its screen is cleared, and its file
    takes 20 minutes to come in. The tick must not wait for it: the XL's cancel
    two ticks later is still seen, and the claimed retry gets no second download."""
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", True)
    _queue(INDX, 1141)
    states = {INDX: "IDLE", XL: "PRINTING"}
    started, release = threading.Event(), threading.Event()
    computes, edges = [], []

    def _review(printer, filename, job_id, progress, **kw):
        computes.append((printer, str(job_id)))
        started.set()
        release.wait(30)                       # PrusaLink at ~15 KB/s
        return {"status": "pending", "job_id": str(job_id)}
    pm = {"RCOI-1": {"printer_name": INDX, "position": 0}, "XL-1": {"printer_name": XL, "position": 0}}
    before = set(threading.enumerate())
    with patch.object(print_monitor.locations_db, "get_active_printer_map", return_value=pm), \
            patch.object(print_monitor.prusalink_api, "get_printer_state",
                         side_effect=lambda fb, name: {"state": states[name]}), \
            patch.object(print_monitor.prusalink_api, "get_printer_job",
                         side_effect=lambda fb, name: _job(0.5) if name == XL else None), \
            patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review), \
            patch.object(print_monitor, "_dispatch_cancel_edge",
                         side_effect=lambda *a, **k: edges.append(a[:3])):
        try:
            assert _within(3, print_monitor._cancel_monitor_tick), "the tick waited for the INDX's download"
            assert started.wait(5)
            states[XL] = "STOPPED"             # the XL's print is cancelled meanwhile
            assert _within(3, print_monitor._cancel_monitor_tick), "the second tick waited too"
            assert edges == [(XL, "x.gcode", 7)]
            assert computes == [(INDX, "1141")], "a second download started for the claimed print"
            assert cancel_fetch_store.has_pending(INDX, "1141")
        finally:
            release.set()
            _join_new(before)
    assert not cancel_fetch_store.has_pending(INDX, "1141")
    assert print_monitor._FETCH_CLAIMS == set()


def test_a_retry_on_its_own_thread_keeps_what_a_raise_means(monkeypatch, logs):
    """CompletionMayHaveCharged gives the job up (dropped, one ERROR line); anything
    else leaves it queued for the next tick. Both claims are released."""
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", True)
    _queue(XL, "C-1")
    _queue(INDX, "Q-1", kind="complete")
    ran_on = []

    def _review(*a, **k):
        ran_on.append(threading.current_thread())
        raise PermissionError("review store busy")

    def _complete(*a, **k):
        ran_on.append(threading.current_thread())
        raise print_deduct.CompletionMayHaveCharged("ledger write failed")
    before = set(threading.enumerate())
    with patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review), \
            patch.object(print_deduct, "deduct_completed_print", side_effect=_complete):
        print_monitor._process_pending_cancel_fetches(
            {XL: {"state": "IDLE"}, INDX: {"state": "IDLE"}}, "http://fb")
        _join_new(before)
    assert len(ran_on) == 2 and threading.current_thread() not in ran_on, ran_on
    assert cancel_fetch_store.has_pending(XL, "C-1")
    assert not cancel_fetch_store.has_pending(INDX, "Q-1")
    assert len([m for m in logs if "not retried" in m]) == 1, logs
    assert print_monitor._FETCH_CLAIMS == set()


# --------------------------------------------------------------------------- #
# The claim                                                                    #
# --------------------------------------------------------------------------- #

def test_the_loop_starts_no_second_download_for_a_claimed_print_or_a_busy_printer():
    _queue(INDX, 1141)
    _queue(INDX, 1142)
    _queue(XL, 7)
    calls = []

    def _review(printer, filename, job_id, progress, **kw):
        calls.append((printer, str(job_id)))
        return {"status": "pending"}
    key = print_monitor._claim_fetch(INDX, 1141)   # the INDX's edge thread is computing 1141
    assert key is not None
    idle = {INDX: {"state": "IDLE"}, XL: {"state": "IDLE"}}
    with patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        print_monitor._process_pending_cancel_fetches(idle, "http://fb")
        assert calls == [(XL, "7")]
        assert cancel_fetch_store.has_pending(INDX, "1141") and cancel_fetch_store.has_pending(INDX, "1142")
        assert print_monitor._claim_fetch(INDX, 1141) is None       # still that thread's
        print_monitor._release_fetch(key)
        print_monitor._process_pending_cancel_fetches(idle, "http://fb")
    assert calls == [(XL, "7"), (INDX, "1141"), (INDX, "1142")]
    assert cancel_fetch_store.list_pending() == []


def test_the_edge_queues_its_print_before_the_download_and_no_tick_downloads_it_twice(monkeypatch, logs):
    """An ambiguous end is seen at IDLE, the very state the queue retries in, so the
    next tick would start a second download of the print being downloaded."""
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", True)
    started, release, seen = threading.Event(), threading.Event(), []

    def _download(*a, **k):
        seen.append(cancel_fetch_store.get_pending(XL, "7"))
        started.set()
        release.wait(30)
        return {0: 12.5}, None
    before = set(threading.enumerate())
    with Rig(), patch.object(print_deduct, "_compute_cancel_usage", side_effect=_download):
        try:
            print_monitor._dispatch_ambiguous_edge(XL, "x.gcode", 7, 0.4, "http://fb",
                                                   start_spools={"0": 100})
            assert started.wait(5)
            rec = seen[0]
            assert rec is not None, "nothing was queued before the download"
            assert rec["last_status"] == "in_flight" and rec["attempts"] == 0
            assert rec["kind"] == "cancel" and rec["ambiguous"] is True and rec["progress"] == 0.4
            assert rec["start_spools"] == {"0": 100} and rec["first_seen"]
            assert rec["end_heads"]["source"] == "print_end"
            assert {h["toolhead"]: h["sid"] for h in rec["end_heads"]["heads"]} == {"XL-1": 100, "XL-2": None}
            assert not [m for m in logs if "retry" in m.lower() or NUDGE in m], logs
            print_monitor._process_pending_cancel_fetches({XL: {"state": "IDLE"}}, "http://fb")
            time.sleep(0.2)
            assert len(seen) == 1, "a second download started for the print in flight"
        finally:
            release.set()
            _join_new(before)
    assert cancel_review_store.get_pending(XL, "7")["spools"][0]["sid"] == 100
    assert not cancel_fetch_store.has_pending(XL, "7")
    assert print_monitor._FETCH_CLAIMS == set()


def test_a_second_edge_for_a_print_being_computed_leaves_it_to_that_thread(logs, hublog):
    """Restart recovery can fire an edge again for a print a retry thread already
    holds (a restart within the tick that saw the end, before the reset latch was
    saved): two computes of one completion could both charge it."""
    key = print_monitor._claim_fetch(XL, 7)
    with patch.object(print_deduct, "_create_pending_cancel_review") as review, \
            patch.object(print_deduct, "deduct_completed_print") as complete, \
            patch.object(print_deduct, "_capture_print_heads", create=True) as read:
        print_monitor._on_cancel_edge(XL, "x.gcode", 7, 0.4, "http://fb", heads_when="restart")
        print_monitor._on_completion_edge(XL, "x.gcode", 7, "http://fb", heads_when="restart")
    review.assert_not_called()
    complete.assert_not_called()
    read.assert_not_called()
    assert len([ln for ln in hublog if "already" in ln]) == 2, hublog
    assert cancel_fetch_store.list_pending() == []
    print_monitor._release_fetch(key)


def test_a_print_without_a_job_id_is_neither_queued_nor_claimed_at_its_edge(logs):
    """Passes before the change by design: the queue drops a record with no job id
    (with a WARNING: FCC can't hold its deduct), so the edge writes none for such a
    print and takes no claim; its compute runs as it always did."""
    seen = []

    def _review(printer, filename, job_id, progress, **kw):
        seen.append((cancel_fetch_store.list_pending(), set(getattr(print_monitor, "_FETCH_CLAIMS", set()))))
        return {"status": "pending"}
    with patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        print_monitor._on_cancel_edge(XL, "x.gcode", "", 0.4, "http://fb")
    assert seen == [([], set())]


# --------------------------------------------------------------------------- #
# A restart mid-way loses nothing and charges nothing twice                    #
# --------------------------------------------------------------------------- #

def test_a_restart_mid_download_loses_nothing(logs):
    """The live edge's download is the one that died with FCC (job 1141's took 20
    minutes; an update can land in it). Its record was on disk, with the heads read
    when the print ended, so the queue finishes it after the restart."""
    calls = {"n": 0}

    def _download(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _Died()
        return {0: 12.5}, None
    with Rig() as rig, patch.object(print_deduct, "_compute_cancel_usage", side_effect=_download):
        _tick(XL, "PRINTING", _job(0.4))
        with pytest.raises(_Died):
            _tick(XL, "STOPPED")
        rec = cancel_fetch_store.get_pending(XL, "7")
        assert rec is not None, "the print died with the download"
        assert rec["end_heads"]["source"] == "print_end"
        _restart()
        rig.on["XL-1"] = 200                   # the next print's spool, loaded meanwhile
        print_monitor._process_pending_cancel_fetches({XL: {"state": "IDLE"}}, "http://fb")
    review = cancel_review_store.get_pending(XL, "7")
    assert [(r["sid"], r["toolhead"], r["grams"]) for r in review["spools"]] == [(100, "XL-1", 12.5)]
    assert review["heads_source"] == "print_end"
    assert review["row_notes"] == {"100": "#200 is on XL-1 now; #100 was on it when the print ended."}
    assert not cancel_fetch_store.has_pending(XL, "7")
    assert not [m for m in logs if NUDGE in m], logs


@pytest.mark.parametrize("then", ["the next tick", "restart recovery"])
def test_a_restart_mid_charge_never_charges_twice(logs, then):
    """The live completion stamps its record right before its first spool write,
    as the queue's retry does. FCC stops after the write and before the job is
    recorded: neither the next tick nor a restart's recovery firing the edge again
    charges it a second time; it is given up with one ERROR line."""
    stamped = []

    def _rig():
        rig = Rig()
        real_patch = rig.sm._patch

        def _write_then_die(url, json=None, **k):
            stamped.append(bool((cancel_fetch_store.get_pending(XL, "7") or {}).get("charging_since")))
            real_patch(url, json=json, **k)    # the write lands...
            raise _Died()                       # ...and FCC stops before it records the job
        return rig, _write_then_die
    rig, die = _rig()
    with rig, patch.object(print_deduct, "_compute_cancel_usage", return_value=({0: 50.0}, None)), \
            patch.object(spoolman_api.requests, "patch", side_effect=die):
        _tick(XL, "PRINTING", _job(0.5))
        with pytest.raises(_Died):
            _tick(XL, "FINISHED")
    assert stamped == [True], "the spool was charged before the print's record said so"
    assert rig.sm.used(100) == pytest.approx(750.0)
    _restart()
    with rig, patch.object(print_deduct, "_compute_cancel_usage", return_value=({0: 50.0}, None)):
        if then == "the next tick":
            print_monitor._process_pending_cancel_fetches({XL: {"state": "IDLE"}}, "http://fb")
        else:
            with patch.object(print_monitor.prusalink_api, "get_printer_state",
                              return_value={"state": "FINISHED"}):
                print_monitor._recover_one_print_latch(
                    XL, {"state": "PRINTING", "job_id": 7, "filename": "x.gcode", "progress": 0.5},
                    "http://fb")
        print_monitor._process_pending_cancel_fetches({XL: {"state": "IDLE"}}, "http://fb")
    assert rig.sm.used(100) == pytest.approx(750.0), "charged twice"
    assert len(rig.sm.patches) == 1
    assert not cancel_fetch_store.has_pending(XL, "7")
    lines = [m for m in logs if "not retried" in m]
    assert len(lines) == 1 and "weigh the spool" in lines[0], logs


def test_a_live_completion_stamps_its_record_before_the_first_charge_and_drops_it_once_recorded(logs):
    rig = Rig()
    real_patch = rig.sm._patch
    stamped = []

    def _patch(url, json=None, **k):
        stamped.append(bool((cancel_fetch_store.get_pending(XL, "7") or {}).get("charging_since")))
        return real_patch(url, json=json, **k)
    with rig, patch.object(print_deduct, "_compute_cancel_usage", return_value=({0: 50.0}, None)), \
            patch.object(spoolman_api.requests, "patch", side_effect=_patch):
        _tick(XL, "PRINTING", _job(0.5))
        _tick(XL, "FINISHED")
    assert stamped == [True]
    assert rig.sm.used(100) == pytest.approx(750.0)
    assert print_deduct_ledger.was_deducted(XL, 7)
    assert not cancel_fetch_store.has_pending(XL, "7")
    assert print_monitor._FETCH_CLAIMS == set()


def test_a_live_review_that_fails_stays_queued_and_the_loop_finishes_it(logs):
    """A review the store can't write at the edge used to be lost with an ERROR
    line (a person reading it would weigh the spool, and nothing came of the
    print). Its record is on disk now: the line says FCC will try again, and the
    next idle tick stashes the review."""
    real_save = cancel_review_store._save
    saves = {"n": 0}

    def _busy_once(data):
        saves["n"] += 1
        if saves["n"] == 1:
            raise PermissionError(13, "review store busy")
        return real_save(data)
    with Rig(), patch.object(print_deduct, "_compute_cancel_usage", return_value=({0: 12.5}, None)), \
            patch.object(cancel_review_store, "_save", side_effect=_busy_once):
        _tick(XL, "PRINTING", _job(0.4))
        _tick(XL, "STOPPED")
        line = next(m for m in logs if "review failed" in m)
        assert "try again" in line, line
        assert cancel_fetch_store.has_pending(XL, "7")
        print_monitor._process_pending_cancel_fetches({XL: {"state": "IDLE"}}, "http://fb")
    assert cancel_review_store.get_pending(XL, "7")["spools"][0]["sid"] == 100
    assert not cancel_fetch_store.has_pending(XL, "7")


# --------------------------------------------------------------------------- #
# The nudge                                                                    #
# --------------------------------------------------------------------------- #

def test_the_nudge_is_logged_once_the_first_time_a_download_really_fails(logs):
    """The record written before the download carries no nudge; the first failed
    download says "clear the screen" once, and a failed retry says nothing more."""
    seen = []

    def _locked(*a, **k):
        rec = cancel_fetch_store.get_pending(XL, "7") or {}
        seen.append((rec.get("last_status"), len([m for m in logs if NUDGE in m])))
        return None, {"status": "error", "reason": "download_failed", "job_id": "7"}
    with Rig(), patch.object(print_deduct, "_compute_cancel_usage", side_effect=_locked):
        _tick(XL, "PRINTING", _job(0.4))
        _tick(XL, "STOPPED")                   # the cancel screen locks the file
        print_monitor._process_pending_cancel_fetches({XL: {"state": "IDLE"}}, "http://fb")
    assert seen == [("in_flight", 0), ("awaiting_fetch", 1)]
    assert len([m for m in logs if NUDGE in m]) == 1, logs
    rec = cancel_fetch_store.get_pending(XL, "7")
    assert rec["attempts"] == 2 and rec["last_status"] == "awaiting_fetch"


# --------------------------------------------------------------------------- #
# The stores                                                                   #
# --------------------------------------------------------------------------- #

def test_two_requeues_of_one_print_at_once_keep_both_attempts(monkeypatch, logs):
    """A get then an add is two store steps; two writers of one record between
    them lost a bump. The re-queue is one locked step now."""
    print_deduct._enqueue_cancel_fetch(XL, "x.gcode", 7, 0.4)          # attempts 1
    real_get = cancel_fetch_store.get_pending
    meet = threading.Barrier(2, timeout=2)

    def _get_then_meet(*a, **k):
        rec = real_get(*a, **k)
        try:
            meet.wait()                       # both have read it before either writes
        except threading.BrokenBarrierError:
            pass
        return rec
    monkeypatch.setattr(cancel_fetch_store, "get_pending", _get_then_meet)
    workers = [threading.Thread(target=print_deduct._enqueue_cancel_fetch, args=(XL, "x.gcode", 7, 0.4))
               for _ in range(2)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(10)
    assert real_get(XL, "7")["attempts"] == 3


@pytest.mark.parametrize("store", ["cancel_fetch_store", "cancel_review_store", "print_deduct_ledger"])
def test_each_store_keeps_every_record_written_at_once(monkeypatch, store):
    """Passes before the change by design: each store already holds its lock across
    its read and its write. Pinned because the queue's retries now write from
    threads of their own, beside the edge threads."""
    mod = {"cancel_fetch_store": cancel_fetch_store, "cancel_review_store": cancel_review_store,
           "print_deduct_ledger": print_deduct_ledger}[store]
    real_load = mod._load

    def _slow_load():
        data = real_load()
        time.sleep(0.005)                     # a writer between this read and its write would be lost
        return data
    monkeypatch.setattr(mod, "_load", _slow_load)

    def _write(i):
        if mod is print_deduct_ledger:
            mod.record_deduct(XL, f"J-{i}", grams=1.0)
        else:
            mod.add_pending({"printer_name": XL, "job_id": f"J-{i}", "filename": "x.gcode"})
    workers = [threading.Thread(target=_write, args=(i,)) for i in range(8)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(10)
    for i in range(8):
        if mod is print_deduct_ledger:
            assert mod.was_deducted(XL, f"J-{i}"), i
        else:
            assert mod.has_pending(XL, f"J-{i}"), i
