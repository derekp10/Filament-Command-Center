"""Group 65 fix review, round 1: the print watch. Offline.

  - WT1 (red, older than the group): restart recovery charges a print it finds on a finished
    screen only when a job read names it; another print's finish opens the latched print's
    ❓ review, said, as a live end after lost contact does (RW7).
  - WT6 (red, older): a resume FCC sees only after lost contact cuts a run-out swap at the
    park's frozen progress (where the spool was changed), never at the progress read on
    return; with no such point no swap is recorded, and the end's Decision 1 holds the head.
  - WT3: a park whose job read names another print writes nothing into the latched print
    (its frozen progress, its line, its read).
  - WT5: a short blip at a park keeps the park's read when the printer is still in that park.
  - WT2: a stopped screen after lost contact opens the cancel review as before (PrusaLink
    names no job after a stop); a finished screen FCC can't tie to the print says so.
  - WT4: an answer that isn't PrusaLink's is said as the address's problem, with no ping.

Red on fddf1ceb (the fix review's head).
"""
from __future__ import annotations

import pytest

import app as app_module  # noqa: F401  (the route modules, as the monitor imports them)
import print_deduct
import print_monitor
import prusalink_api
import state
from test_lost_contact_65_1 import _iso, _latch, _miss, _printing, clock, dispatched  # noqa: F401
from test_print_watch_65_r1 import PARK, _contact, _job, completions, words  # noqa: F401


# --------------------------------------------------------------------------- #
# WT1: a finished screen after FCC's restart                                   #
# --------------------------------------------------------------------------- #

def _recover(monkeypatch, job):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": "FINISHED"})
    _job(monkeypatch, job)
    latched = {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.3, "seen_at": 900.0}
    return print_monitor._recover_one_print_latch("XL", dict(latched), "fb")


def test_a_finish_after_a_restart_that_isnt_the_latched_print_opens_its_review(monkeypatch, clock, dispatched,
                                                                               completions, words):
    assert _recover(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 1.0}) is True
    assert completions == [] and [(kind, a[2]) for kind, a, _k in dispatched] == [("ambiguous", 7)], dispatched
    assert dispatched[0][2]["lost_contact"]["why"] == "restart" and dispatched[0][2]["heads_when"] == "restart"
    assert words[0].startswith("📡 XL: the print that finished while FCC couldn't see the printer is job 8"), words


def test_a_finish_after_a_restart_fcc_cant_tie_to_the_latched_print_opens_its_review(monkeypatch, clock,
                                                                                     dispatched, completions, words):
    assert _recover(monkeypatch, None) is True
    assert completions == [] and [kind for kind, _a, _k in dispatched] == ["ambiguous"], dispatched


# --------------------------------------------------------------------------- #
# WT6: a resume FCC sees only after lost contact                              #
# --------------------------------------------------------------------------- #

def _resume(monkeypatch, clock, **latch):
    swaps = []
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {"0": 58})
    monkeypatch.setattr(print_deduct, "_record_swap_events",
                        lambda e, snap, progress, **k: swaps.append(progress) or [])
    _latch(state="ATTENTION", snapshot_job="7", start_spools={"0": 57}, **latch)
    _miss(3, clock)
    print_monitor._track_print_edge("XL", _printing(monkeypatch, job_id=7, progress=0.6), "fb")
    return swaps


def test_a_run_out_swap_seen_after_lost_contact_is_cut_at_the_park(monkeypatch, clock, words):
    assert _resume(monkeypatch, clock, saw_attention=True, pause_progress=0.31) == [0.31]


def test_a_swap_fcc_cant_place_after_lost_contact_is_not_recorded(monkeypatch, clock, words):
    assert _resume(monkeypatch, clock) == []


# --------------------------------------------------------------------------- #
# WT3 / WT5: the park's facts                                                 #
# --------------------------------------------------------------------------- #

def test_another_prints_park_after_lost_contact_writes_nothing_into_the_latched_print(monkeypatch, clock, words):
    _latch()
    _miss(3, clock)
    reads = []
    monkeypatch.setattr(print_monitor, "_capture_end_heads", lambda *a, **k: reads.append(a) or None)
    _job(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 0.8})
    print_monitor._track_print_edge("XL", {"state": "ATTENTION"}, "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert not any(k in entry for k in ("pause_progress", "saw_attention", "park_read", "paused_at")), entry
    assert entry["misses"] == 3 and reads == [] and not any("parked at ATTENTION" in w for w in words), (entry, words)


def test_a_short_blip_at_a_park_keeps_the_parks_read(monkeypatch, clock):
    _latch(state="ATTENTION", park_heads=dict(PARK), park_read=True)
    _miss(3, clock)
    _job(monkeypatch, {"job_id": 7, "filename": "/usb/A.BGC", "progress": 0.31})
    print_monitor._track_print_edge("XL", {"state": "ATTENTION"}, "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert entry.get("park_heads") == PARK and "misses" not in entry, entry


# --------------------------------------------------------------------------- #
# WT2 / WT4: what FCC says                                                     #
# --------------------------------------------------------------------------- #

def test_a_stopped_screen_after_lost_contact_opens_the_cancel_review_as_before(monkeypatch, clock, dispatched):
    _latch()
    _miss(3, clock)
    reads = []
    monkeypatch.setattr(prusalink_api, "get_printer_job", lambda fb, name: reads.append(name) or None)
    print_monitor._track_print_edge("XL", {"state": "STOPPED"}, "fb")
    assert [kind for kind, _a, _k in dispatched] == ["cancel"] and reads == [], (dispatched, reads)


def test_a_finished_screen_fcc_cant_tie_to_the_print_is_said_as_that(monkeypatch, words):
    monkeypatch.setattr(print_monitor, "_claim_edge", lambda *a, **k: (False, None))
    print_monitor._on_ambiguous_edge(
        "XL", "/usb/A.BGC", 7, 0.3, "fb",
        lost_contact={"progress": 0.3, "seen_at": 900.0, "lost_at": 910.0, "back_at": 9000.0,
                      "back_state": "FINISHED", "why": "lost"})
    assert words[0].startswith("❓ XL is on its finished screen, which FCC can't tie to the print it last saw "
                               "('/usb/A.BGC', ~30%) — FCC lost contact at ~30%"), words


def test_an_answer_that_isnt_prusalinks_is_said_as_the_addresss_problem(monkeypatch):
    pings = []
    monkeypatch.setattr(prusalink_api, "icmp_echo", lambda *a, **k: pings.append(a) or True)
    prusalink_api._note_probe_failure("XL", "unreadable")
    assert print_monitor._reach_verdict("XL") == "address" and pings == []
    assert print_monitor._reach_words("XL", "address", True) == (
        "Something answers at XL's address, but not as PrusaLink: check the address in Settings, "
        "🔌 Printer Connections.")
