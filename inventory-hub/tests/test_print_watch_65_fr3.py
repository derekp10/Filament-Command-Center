"""Group 65 fix review, round 3: the print watch. Offline.

  - WX1 (red, older than the group): a print FCC first meets at a park (another print
    found there after it lost sight of the printer) takes the spools read at that park
    as its start snapshot, so the resume records a spool changed at the prompt and the
    print is split at the park, never charged whole to the spool loaded there.
  - WX7: that print's latch has the park's frozen progress, a real sample.
  - WX2: a lost latch at a park that shows BUSY now (a filament loaded at the prompt)
    reads its job, and the stretch ends with the park's read kept when the job is still
    at that park.
  - WX6: a resume whose last tick was BUSY at a park checks for a swap, as one from
    PAUSED or ATTENTION does.
  - WX3 / AX3: restart recovery at a prompt restores the latch unstamped, its park read
    kept, when a job read names the latched print at the park's frozen progress.
  - WX4: restart recovery at a prompt asks what FCC already holds first (a queued
    completion stays the queue's), and an ambiguous edge leaves a queued completion to
    the queue.
  - AX4: a job change at a park with no lost contact says nothing of losing sight.
  - WX5: a plain job change's review is said as a print another print replaced.
  - WX8: a finished screen after a restart that is another print's is said, whatever
    FCC holds for the latched print.
  - RX2: a finish FCC sees only after lost contact goes to the completion with its lost
    contact facts, its heads read when FCC saw the printer again.

Red on dcfa4a4b (the third fix review's head).
"""
from __future__ import annotations

import app as app_module  # noqa: F401  (the route modules, as the monitor imports them)
import cancel_fetch_store
import print_deduct
import print_monitor
import prusalink_api
from test_lost_contact_65_1 import _iso, _latch, _miss, _printing, clock, dispatched  # noqa: F401
from test_print_watch_65_r1 import PARK, _contact, _job, completions, words  # noqa: F401

PARK_8 = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 100, "sids": [100]}], "source": "park"}


def test_a_print_first_met_at_a_park_takes_the_parks_spools_as_its_start(monkeypatch, clock, dispatched, words):
    _latch()
    _miss(3, clock)
    monkeypatch.setattr(print_monitor, "_capture_end_heads", lambda *a, **k: dict(PARK_8))
    _job(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 0.45})
    print_monitor._track_print_edge("XL", {"state": "ATTENTION"}, "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert entry.get("start_spools") == {"0": 100} and entry.get("snapshot_job") == "8", entry
    assert entry.get("progress") == 0.45, entry                        # WX7
    # Derek loads #200 at the prompt and resumes: the change is recorded at the park.
    swaps = []
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {"0": 200})
    real = print_deduct._record_swap_events
    monkeypatch.setattr(print_deduct, "_record_swap_events",
                        lambda e, snap, progress, **k: swaps.append(progress) or real(e, snap, progress, **k))
    print_monitor._track_print_edge("XL", _printing(monkeypatch, job_id=8, progress=0.46), "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert len(swaps) == 1 and 0.45 <= swaps[0] <= 0.46, swaps          # cut at the resume, as any resume
    assert [(e["from_sid"], e["to_sid"]) for e in entry.get("swap_log") or []] == [(100, 200)], entry


def test_a_lost_latch_at_a_park_showing_busy_ends_the_stretch_and_keeps_its_read(monkeypatch, clock):
    _latch(state="ATTENTION", park_heads=dict(PARK), park_read=True, saw_attention=True, pause_progress=0.31)
    _miss(3, clock)
    _job(monkeypatch, {"job_id": 7, "filename": "/usb/A.BGC", "progress": 0.31})
    print_monitor._track_print_edge("XL", {"state": "BUSY"}, "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert "misses" not in entry and entry.get("park_heads") == PARK, entry


def test_a_resume_from_busy_at_a_park_checks_for_a_swap(monkeypatch, clock, words):
    swaps = []
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {"0": 58})
    monkeypatch.setattr(print_deduct, "_record_swap_events", lambda e, snap, p, **k: swaps.append(p) or [])
    _latch(state="BUSY", snapshot_job="7", start_spools={"0": 57}, saw_attention=True, pause_progress=0.31,
           park_heads=dict(PARK), paused_at=950.0)
    print_monitor._track_print_edge("XL", _printing(monkeypatch, job_id=7, progress=0.32), "fb")
    assert swaps == [0.32], swaps


def _recover(monkeypatch, cur, job, **latch):
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": cur})
    _job(monkeypatch, job)
    entry = dict({"state": "ATTENTION", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.31,
                  "seen_at": 900.0}, **latch)
    return print_monitor._recover_one_print_latch("XL", entry, "fb")


def test_recovery_at_its_own_park_keeps_the_latch_unstamped_and_its_read(monkeypatch, clock):
    for cur in ("ATTENTION", "BUSY"):
        print_monitor._PRINT_TRACKER.clear()
        assert _recover(monkeypatch, cur, {"job_id": 7, "filename": "/usb/A.BGC", "progress": 0.31},
                        park_heads=dict(PARK), park_read=True) is True
        entry = print_monitor._PRINT_TRACKER["XL"]
        assert "misses" not in entry and entry.get("park_heads") == PARK, (cur, entry)


def test_recovery_at_a_prompt_leaves_a_queued_completion_to_the_queue(monkeypatch, clock, words, dispatched):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    cancel_fetch_store.add_pending({"printer_name": "XL", "job_id": "7", "filename": "/usb/A.BGC",
                                    "kind": "complete", "end_heads": {"heads": [], "source": "print_end"}})
    assert _recover(monkeypatch, "ATTENTION", {"job_id": 8, "filename": "/usb/B.BGC", "progress": 0.2}) is True
    assert print_monitor._PRINT_TRACKER["XL"] == {"state": "ATTENTION"}, print_monitor._PRINT_TRACKER
    assert any("records its deduct once the printer is idle" in w for w in words), words


def test_an_ambiguous_edge_leaves_a_queued_completion_to_the_queue(monkeypatch, words):
    made = []
    monkeypatch.setattr(print_deduct, "_create_pending_cancel_review", lambda *a, **k: made.append(a))
    cancel_fetch_store.add_pending({"printer_name": "XL", "job_id": "7", "filename": "/usb/A.BGC",
                                    "kind": "complete", "end_heads": {"heads": [], "source": "print_end"}})
    print_monitor._on_ambiguous_edge("XL", "/usb/A.BGC", 7, 0.97, "fb", heads_when="job_change")
    assert made == [], made
    assert (cancel_fetch_store.get_pending("XL", "7") or {}).get("kind") == "complete"


def test_a_job_change_at_a_park_with_no_lost_contact_says_nothing_of_losing_sight(monkeypatch, clock, dispatched,
                                                                                  words):
    _latch()
    monkeypatch.setattr(print_monitor, "_capture_end_heads", lambda *a, **k: None)
    _job(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 0.8})
    print_monitor._track_print_edge("XL", {"state": "ATTENTION"}, "fb")
    said = [w for w in words if "print job changed" in w]
    assert said and "losing sight" not in said[0], words


def test_a_plain_job_changes_review_is_said_as_a_print_another_replaced(monkeypatch, words):
    monkeypatch.setattr(print_monitor, "_claim_edge", lambda *a, **k: (False, None))
    print_monitor._on_ambiguous_edge("XL", "/usb/A.BGC", 7, 0.97, "fb", heads_when="job_change")
    assert words and words[0].startswith("❓ XL moved on to another print"), words
    assert print_deduct._ambiguous_lead("XL", 97.0, "job_change").startswith("❓ XL moved on to another print")


def test_a_finished_screen_after_a_restart_that_is_another_prints_is_said_whatever_fcc_holds(monkeypatch, clock,
                                                                                               words, dispatched):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    cancel_fetch_store.add_pending({"printer_name": "XL", "job_id": "7", "filename": "/usb/A.BGC",
                                    "kind": "cancel", "progress": 0.5})
    assert _recover(monkeypatch, "FINISHED", {"job_id": 8, "filename": "/usb/B.BGC", "progress": 1.0},
                    state="PRINTING") is True
    assert dispatched == [], dispatched
    assert any(w.startswith("📡 XL: the print that finished while FCC was restarting is job 8") for w in words), words


def test_a_finish_seen_after_lost_contact_goes_to_the_completion_with_its_facts(monkeypatch, clock, completions):
    _latch()
    _miss(3, clock)
    _job(monkeypatch, {"job_id": 7, "filename": "/usb/A.BGC", "progress": 1.0})
    print_monitor._track_print_edge("XL", {"state": "FINISHED"}, "fb")
    ((a, k),) = completions
    assert k.get("lost_contact", {}).get("why") == "lost" and k.get("heads_when") == "back", k
