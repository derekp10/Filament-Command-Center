"""Group 65 fix review, round 4: the print watch, over the fetch-off-watcher rig
(WeightWireSpoolman over the wire, the real edges, recovery and deducts; only the download is
stubbed, 50 g a print). Offline.

  - WY1 (red, from fix review 3's WX4): a restart that finds FCC already held the latched
    print, with another print waiting at its run-out prompt, latches that print at its park by
    the first tick, so its park read takes its start: a cancel from the prompt opens its card
    on the run-out spool, and a resume after a swap there records the swap.
  - WY7 (red, older than the group): a print FCC first meets at its park with nothing latched
    (the printer was idle when FCC lost sight of it) is latched there the same way.
  - WY3 (red): a park read that keeps nothing (a Spoolman blip) of a print FCC has no start
    for is read again at the next tick at the prompt, five reads a park at most; a print FCC
    met at its park that resumes with no read says which charge may be wrong.
  - WY6 (red): the run-out spool of a print FCC first met at its park, weighed at the prompt
    before FCC saw the park, is marked on the card as a weighing FCC can't place (its grams
    filled in, loud), never filled in unmarked; one weighed after FCC saw the park keeps
    Group 64's mark (0 g).
  - WY2 (red): restart recovery's completion of a print FCC had lost sight of holds a spool
    FCC weighed meanwhile, as the live door does (RX2), never charged on top.

Red on cbfea058 (fix review 3's fixes).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

import cancel_fetch_store
import cancel_review_store
import print_deduct
import print_monitor
import weigh_stamps
from test_fetch_off_watcher_hotfix import (  # noqa: F401  (fixtures used by name)
    _isolated, logs, Rig, _tick, _job, _restart, XL)


def _snap(rig):
    def _read(*a, **k):
        return {0: rig.on["XL-1"]} if rig.on.get("XL-1") is not None else {}
    return _read


def _download(*a, **k):
    """The print's figures: 50 g on T0, and the walk's grams at each swap asked for."""
    cums = k.get("cums_out")
    for p in k.get("swap_points") or []:
        if cums is not None:
            cums[p] = {0: round(50.0 * p, 4)}
    return {0: 50.0}, None


def _rigged(rig):
    return (patch.object(print_deduct, "_snapshot_active_spools", side_effect=_snap(rig)),
            patch.object(print_deduct, "_compute_cancel_usage", side_effect=_download))


def _held_restart_at_the_prompt():
    """FCC saw job 7 finish and queued its completion, then stopped before its reset latch was
    saved; while FCC was down job 8 started on #100 and ran out at 20%. The restart finds XL at
    job 8's run-out prompt."""
    cancel_fetch_store.add_pending({"printer_name": XL, "job_id": "7", "filename": "x.gcode",
                                    "progress": 1.0, "first_seen": time.time(), "kind": "complete",
                                    "ambiguous": False, "attempts": 1, "last_status": "awaiting_fetch"})
    job8 = _job(0.20, job_id=8, filename="y.gcode")
    with patch.object(print_monitor.prusalink_api, "get_printer_state", return_value={"state": "ATTENTION"}), \
            patch.object(print_monitor.prusalink_api, "get_printer_job", return_value=job8):
        print_monitor._recover_one_print_latch(
            XL, {"state": "PRINTING", "job_id": 7, "filename": "x.gcode", "progress": 0.97,
                 "seen_at": time.time() - 600, "start_spools": {"0": 100}, "snapshot_job": "7"},
            "http://fb")
    _tick(XL, "ATTENTION", job8)


def test_a_held_restart_latches_the_print_at_its_prompt_so_a_cancel_there_opens_its_card(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        _held_restart_at_the_prompt()
        e = dict(print_monitor._PRINT_TRACKER[XL])
        assert (str(e.get("job_id")), (e.get("start_spools") or {}).get("0")) == ("8", 100), e
        _tick(XL, "STOPPED", None)
    rev = cancel_review_store.get_pending(XL, "8")
    assert rev and [r.get("sid") for r in rev.get("spools") or []] == [100], rev
    assert not any("no active job was latched" in m for m in logs), logs


def test_a_held_restart_records_a_swap_made_at_the_prompt(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        _held_restart_at_the_prompt()
        rig.on["XL-1"] = 200                        # Derek loads #200 at the prompt
        _tick(XL, "PRINTING", _job(0.21, job_id=8, filename="y.gcode"))
        e = dict(print_monitor._PRINT_TRACKER[XL])
    assert [(ev["from_sid"], ev["to_sid"]) for ev in e.get("swap_log") or []] == [(100, 200)], e


def test_a_print_first_met_at_its_park_with_nothing_latched_is_latched_there(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        _tick(XL, "IDLE", None)
        for _ in range(3):
            print_monitor._track_print_edge(XL, None, "http://fb")      # FCC loses sight of the idle XL
        _tick(XL, "ATTENTION", _job(0.20, job_id=8, filename="y.gcode"))
        e = dict(print_monitor._PRINT_TRACKER[XL])
        assert (str(e.get("job_id")), (e.get("start_spools") or {}).get("0"), e.get("progress")) == ("8", 100, 0.2), e
        rig.on["XL-1"] = 200
        _tick(XL, "PRINTING", _job(0.21, job_id=8, filename="y.gcode"))
        e = dict(print_monitor._PRINT_TRACKER[XL])
        _tick(XL, "PRINTING", _job(0.95, job_id=8, filename="y.gcode"))
        _tick(XL, "FINISHED", _job(1.0, job_id=8, filename="y.gcode"))
        used200 = rig.sm.used(200)
    assert [(ev["from_sid"], ev["to_sid"]) for ev in e.get("swap_log") or []] == [(100, 200)], e
    assert used200 == 10.0, used200                   # never charged the whole print
    assert (cancel_review_store.get_pending(XL, "8") or {}).get("kind") == "spool_changed"


def test_a_park_read_that_kept_nothing_is_read_again_at_the_next_tick(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    reads = {"n": 0}

    def _flaky(*a, **k):
        reads["n"] += 1
        return None if reads["n"] == 1 else rig._capture(*a, **k)
    with rig, snap, dl, patch.object(print_deduct, "_capture_print_heads", side_effect=_flaky):
        _tick(XL, "IDLE", None)
        _tick(XL, "ATTENTION", _job(0.20, job_id=8, filename="y.gcode"))
        first = dict(print_monitor._PRINT_TRACKER[XL])
        _tick(XL, "ATTENTION", _job(0.20, job_id=8, filename="y.gcode"))
        second = dict(print_monitor._PRINT_TRACKER[XL])
    assert first.get("start_spools") is None and (second.get("start_spools") or {}).get("0") == 100, (first, second)


def test_a_print_met_at_its_park_resuming_with_no_read_says_which_charge_may_be_wrong(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl, patch.object(print_deduct, "_capture_print_heads", return_value=None) as cap:
        _tick(XL, "IDLE", None)
        for _ in range(8):
            _tick(XL, "ATTENTION", _job(0.20, job_id=8, filename="y.gcode"))
        reads = cap.call_count
        rig.on["XL-1"] = 200
        _tick(XL, "PRINTING", _job(0.21, job_id=8, filename="y.gcode"))
    assert reads == 5, reads                          # _PARK_READ_TRIES
    said = [m for m in logs if "couldn't read which spools were on the heads while job 8 was parked" in m]
    assert len(said) == 1 and "T0 #200" in said[0] and "weigh it to true it up" in said[0], logs


def _weigh(rig, sid, grams):
    rig.sm.spools[sid]["used_weight"] = float(rig.sm.spools[sid]["used_weight"]) + grams
    weigh_stamps.note(sid, "Quick-Weigh")
    time.sleep(0.02)


def _run_out_card(rig, weigh_before_park, relatch=False):
    """Job 8 met at its park (FCC lost sight of the idle XL, or with `relatch` of job 7
    printing, the park's job change taking job 8 up): #100 ran out at 45%; Derek weighs #100
    (its share: +22.5 g) before FCC sees the park, or after; then loads #200 at the prompt
    and resumes; job 8 finishes. Its card's #100 row."""
    if relatch:
        _tick(XL, "PRINTING", _job(0.30, job_id=7, filename="a.gcode"))
    else:
        _tick(XL, "IDLE", None)
    for _ in range(3):
        print_monitor._track_print_edge(XL, None, "http://fb")
    time.sleep(0.02)
    if weigh_before_park:
        _weigh(rig, 100, 22.5)
    _tick(XL, "ATTENTION", _job(0.45, job_id=8, filename="b.gcode"))
    time.sleep(0.02)
    if not weigh_before_park:
        _weigh(rig, 100, 22.5)
    rig.on["XL-1"] = 200
    _tick(XL, "PRINTING", _job(0.46, job_id=8, filename="b.gcode"))
    _tick(XL, "PRINTING", _job(0.95, job_id=8, filename="b.gcode"))
    _tick(XL, "FINISHED", _job(1.0, job_id=8, filename="b.gcode"))
    rev = cancel_review_store.get_pending(XL, "8") or {}
    return next((r for r in rev.get("spools") or [] if r.get("sid") == 100), None), rev


@pytest.mark.parametrize("relatch", [False, True])
def test_a_run_out_spool_weighed_before_fcc_saw_the_park_is_marked_unsure(logs, relatch):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        row, rev = _run_out_card(rig, weigh_before_park=True, relatch=relatch)
    assert row is not None, rev
    mark = row.get("weighed") or {}
    assert mark.get("unseen") and mark.get("known_order") is False, row
    assert "before it first saw this print, at its park" in mark.get("words", ""), mark
    assert row.get("prefill") == row.get("grams"), row          # its grams filled in, marked


def test_a_run_out_spool_weighed_after_fcc_saw_the_park_keeps_0g(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        row, rev = _run_out_card(rig, weigh_before_park=False)
    assert row is not None and (row.get("weighed") or {}).get("left") and row.get("prefill") == 0.0, (row, rev)


def test_restart_recovery_holds_a_spool_weighed_while_fcc_couldnt_see_the_print(logs):
    rig = Rig()
    snap, dl = _rigged(rig)
    with rig, snap, dl:
        _tick(XL, "PRINTING", _job(0.30, job_id=7))
        for _ in range(3):
            print_monitor._track_print_edge(XL, None, "http://fb")      # the printer drops off
        time.sleep(0.02)
        _weigh(rig, 100, 50.0)                 # the print finished unseen; Derek weighs #100
        latch = dict(print_monitor._PRINT_TRACKER[XL])
        _restart()                             # FCC restarts before it sees XL again
        with patch.object(print_monitor.prusalink_api, "get_printer_state", return_value={"state": "FINISHED"}), \
                patch.object(print_monitor.prusalink_api, "get_printer_job", return_value=_job(1.0, job_id=7)):
            print_monitor._recover_one_print_latch(XL, latch, "http://fb")
        used = rig.sm.used(100)
    assert used == 750.0, used                 # held, never charged on top of the weighing
    card = cancel_review_store.get_pending(XL, "7#shortfall") or {}
    assert (card.get("shortfall_causes") or {}).get("0", {}).get("unseen"), card
