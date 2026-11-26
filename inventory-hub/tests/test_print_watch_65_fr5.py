"""Group 65 fix review, round 5: the print watch, over the fetch-off-watcher rig (the real
edges, recovery and deducts; only the download is stubbed). Offline.

  - WZ1 (red) / AZ1: when FCC last saw the printer (the bound of a print it first meets at its
    park) survives a restart (the bare latch keeps it) and a park tick whose job read failed,
    so the run-out spool weighed at the prompt before FCC saw the park is marked on the card
    as a weighing FCC can't place. Both dropped it, and the row was filled in unmarked.
  - RZ4 (red): a restart with nothing latched and no bound takes the latch file's last save
    (FCC was down after it) as one.
  - WZ2 (red) / AZ2: a park read that landed only on a retry may postdate a spool changed at
    the prompt: when the resume finds no change, it says so, never "the same spool on every
    head".

Red on 22c87e02 (fix review 4's fixes).
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest

import cancel_review_store
import print_deduct
import print_monitor
import print_tracker_store
from test_fetch_off_watcher_hotfix import _isolated, logs, Rig, _tick, _job, _restart, XL  # noqa: F401
from test_print_watch_65_fr4 import _rigged, _weigh


def _met_at_park_and_finished(rig):
    """Job 8 is met at its run-out park (#100 at 45 %); #200 is loaded at the prompt, the
    print resumes and finishes. Its card's #100 row."""
    _tick(XL, "ATTENTION", _job(0.45, job_id=8, filename="b.gcode"))
    rig.on["XL-1"] = 200
    _tick(XL, "PRINTING", _job(0.46, job_id=8, filename="b.gcode"))
    _tick(XL, "PRINTING", _job(0.95, job_id=8, filename="b.gcode"))
    _tick(XL, "FINISHED", _job(1.0, job_id=8, filename="b.gcode"))
    rev = cancel_review_store.get_pending(XL, "8") or {}
    return next((r for r in rev.get("spools") or [] if r.get("sid") == 100), None), rev


def _marked_unsure(row, rev):
    assert row is not None, rev
    mark = row.get("weighed") or {}
    assert mark.get("unseen") and mark.get("known_order") is False, row
    assert "before it first saw this print, at its park" in mark.get("words", ""), mark


def _lose_the_idle_printer():
    _tick(XL, "IDLE", None)
    for _ in range(3):
        print_monitor._track_print_edge(XL, None, "http://fb")      # FCC loses sight of the idle XL
    time.sleep(0.02)


def test_the_bound_survives_a_restart(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        _lose_the_idle_printer()
        _weigh(rig, 100, 22.5)                          # at job 8's prompt, FCC still can't see XL
        latch = dict(print_monitor._PRINT_TRACKER[XL])
        _restart()                                      # FCC restarts before it sees XL again
        print_monitor._recover_one_print_latch(XL, latch, "http://fb")
        assert print_monitor._PRINT_TRACKER[XL].get("unseen_since") is not None, print_monitor._PRINT_TRACKER
        row, rev = _met_at_park_and_finished(rig)
    _marked_unsure(row, rev)


def test_the_bound_survives_a_park_tick_whose_job_read_failed(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        _lose_the_idle_printer()
        _weigh(rig, 100, 22.5)
        _tick(XL, "ATTENTION", None)                    # FCC sees the prompt, but the job read fails
        assert print_monitor._PRINT_TRACKER[XL].get("unseen_since") is not None, print_monitor._PRINT_TRACKER
        row, rev = _met_at_park_and_finished(rig)
    _marked_unsure(row, rev)


def test_an_idle_tick_still_spends_the_bound(logs):
    _lose_the_idle_printer()
    _tick(XL, "IDLE", None)
    assert print_monitor._PRINT_TRACKER[XL] == {"state": "IDLE"}, print_monitor._PRINT_TRACKER


def test_a_restart_with_nothing_latched_takes_the_latch_files_last_save_as_its_bound(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        print_tracker_store.save({XL: {"state": "IDLE"}})
        last = time.time() - 600
        os.utime(print_tracker_store._STORE_PATH, (last, last))     # FCC's last tick before it stopped
        _weigh(rig, 100, 22.5)
        _restart()
        print_monitor._recover_print_tracker_on_start()
        assert print_monitor._PRINT_TRACKER[XL].get("unseen_since") == pytest.approx(last, abs=1.0)
        assert print_monitor._LATCH_SAVED_AT is None                # recovery's own
        row, rev = _met_at_park_and_finished(rig)
    _marked_unsure(row, rev)


def test_a_park_read_landing_only_on_a_retry_never_says_no_spool_changed(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    reads = {"n": 0}

    def _flaky(*a, **k):
        reads["n"] += 1
        return None if reads["n"] == 1 else rig._capture(*a, **k)
    with rig, snap, dl, patch.object(print_deduct, "_capture_print_heads", side_effect=_flaky):
        _tick(XL, "IDLE", None)
        _tick(XL, "ATTENTION", _job(0.20, job_id=8, filename="y.gcode"))    # the read hits a blip
        rig.on["XL-1"] = 200                                              # a Quick-Swap at the prompt
        _tick(XL, "ATTENTION", _job(0.20, job_id=8, filename="y.gcode"))    # the retry reads #200
        _tick(XL, "PRINTING", _job(0.21, job_id=8, filename="y.gcode"))
    assert not any("same spool on every head" in m for m in logs), logs
    said = [m for m in logs if "only" in m and "after it first saw the print parked" in m]
    assert len(said) == 1 and "T0 #200" in said[0] and "weigh it to true it up" in said[0], logs
