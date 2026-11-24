"""Group 65.1 (1a) (Derek, 2026-11-09: "the 30% last seen is the real issue"): an end
FCC saw only after it lost sight of the print says so. Offline.

The latch stamps each failed probe while it holds a print (`misses`, and the first
one's `lost_at`) and each good one (`seen_at`, the stamps cleared); they ride the latch
file. An end (or a job change, or restart recovery's review) after 3 failed probes or
more carries `lost_contact` {progress, seen_at, lost_at, back_at, back_state, why} to its
handler, the print's fetch record and its review, with its heads read labelled `back`
("when FCC saw the printer again"); the review's Activity Log line and the acknowledging
line say it with durations, and the card says it in the browser's clock
(test_lost_contact_65_1_js.py). A two-probe blip carries nothing.

Red on 0fa8afd2 (15 of 18; the three that pass are controls: an idle printer, a blip, a review without it).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import app as app_module
import cancel_fetch_store
import cancel_review_store
import print_deduct
import print_deduct_ledger
import print_monitor
import print_tracker_store
import prusalink_api
import state
from test_cancel_review import _cancelled_gcode, _preview_ctx

LC = {"progress": 0.3, "seen_at": 900.0, "lost_at": 1000.0, "back_at": 10480.0, "back_state": "IDLE",
      "why": "lost"}
WORDS = "FCC lost contact at ~30% and saw it again 2 h 38 min later"


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {})
    print_monitor._PRINT_TRACKER.clear()
    yield
    print_monitor._PRINT_TRACKER.clear()


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(print_monitor.time, "time", lambda: now["t"])
    return now


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append(msg))
    return calls


@pytest.fixture
def dispatched(monkeypatch):
    calls = []
    monkeypatch.setattr(print_monitor, "_dispatch_ambiguous_edge",
                        lambda *a, **k: calls.append(("ambiguous", a, k)))
    monkeypatch.setattr(print_monitor, "_dispatch_cancel_edge",
                        lambda *a, **k: calls.append(("cancel", a, k)))
    return calls


def _latch(**more):
    print_monitor._PRINT_TRACKER["XL"] = dict(
        {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.3, "seen_at": 900.0}, **more)


def _miss(n, clock, step=10.0):
    for _ in range(n):
        print_monitor._track_print_edge("XL", None, "fb")
        clock["t"] += step


def _printing(monkeypatch, job_id=7, progress=0.35):
    monkeypatch.setattr(prusalink_api, "get_printer_job",
                        lambda fb, name: {"job_id": job_id, "filename": f"/usb/J{job_id}.BGC", "progress": progress})
    return {"state": "PRINTING", "is_active": True}


# --------------------------------------------------------------------------- #
# The latch's stamps                                                          #
# --------------------------------------------------------------------------- #

def test_failed_probes_stamp_the_latch_and_a_good_one_clears_the_stamps(monkeypatch, clock):
    _latch()
    _miss(2, clock)
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert (entry["misses"], entry["lost_at"]) == (2, 1000.0), entry
    clock["t"] = 5000.0
    print_monitor._track_print_edge("XL", _printing(monkeypatch), "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert "misses" not in entry and "lost_at" not in entry and entry["seen_at"] == 5000.0, entry


def test_an_idle_printer_with_no_print_gets_no_stamps(clock):
    # Group 65 fix review 4 (WY6): no lost-contact stamps, only when FCC first missed the idle
    # printer (`unseen_since`), for a print it then meets at a park.
    print_monitor._PRINT_TRACKER["XL"] = {"state": "IDLE"}
    _miss(4, clock)
    assert print_monitor._PRINT_TRACKER["XL"] == {"state": "IDLE", "unseen_since": 1000.0}


def test_the_stamps_ride_the_latch_file(clock):
    _latch()
    _miss(3, clock)
    print_tracker_store.save({k: dict(v) for k, v in print_monitor._PRINT_TRACKER.items()})
    back = print_tracker_store.load()["XL"]
    assert (back["misses"], back["lost_at"], back["seen_at"]) == (3, 1000.0, 900.0), back


# --------------------------------------------------------------------------- #
# The edge carries it                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("end,kind", [("IDLE", "ambiguous"), ("READY", "ambiguous"), ("STOPPED", "cancel")])
def test_an_end_seen_after_lost_contact_carries_it_and_reads_the_heads_as_back(monkeypatch, clock, dispatched,
                                                                              end, kind):
    _latch()
    _miss(3, clock)
    # Group 65 review (RW7): a STOPPED after lost contact is the latched print's only when
    # a job read names it (test_print_watch_65_r1.py has the other answers).
    monkeypatch.setattr(prusalink_api, "get_printer_job",
                        lambda fb, name: {"job_id": 7, "filename": "part.bgcode", "progress": 0.3})
    clock["t"] = 10480.0
    print_monitor._track_print_edge("XL", {"state": end}, "fb")
    ((got, _a, k),) = dispatched
    assert got == kind
    assert k["lost_contact"] == {"progress": 0.3, "seen_at": 900.0, "lost_at": 1000.0, "back_at": 10480.0,
                                 "back_state": end, "why": "lost"}, k
    assert k["heads_when"] == "back", k


def test_a_two_probe_blip_carries_nothing(clock, dispatched):
    _latch()
    _miss(2, clock)
    print_monitor._track_print_edge("XL", {"state": "IDLE"}, "fb")
    ((_kind, _a, k),) = dispatched
    assert "lost_contact" not in k and "heads_when" not in k, k


def test_a_job_change_after_lost_contact_carries_it(monkeypatch, clock, dispatched):
    _latch()
    _miss(3, clock)
    clock["t"] = 10480.0
    print_monitor._track_print_edge("XL", _printing(monkeypatch, job_id=8, progress=0.05), "fb")
    ((kind, a, k),) = dispatched
    assert kind == "ambiguous" and a[2] == 7, (a, k)
    assert k["lost_contact"]["back_state"] == "PRINTING" and k["lost_contact"]["why"] == "lost", k
    assert k["heads_when"] == "job_change", k


def test_restart_recovery_says_fcc_last_saw_it_before_it_restarted(monkeypatch, clock, dispatched):
    entry = {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.3, "seen_at": 900.0}
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": "IDLE"})
    clock["t"] = 20000.0
    assert print_monitor._recover_one_print_latch("XL", entry, "fb") is True
    ((kind, _a, k),) = dispatched
    assert kind == "ambiguous" and k["heads_when"] == "restart", k
    assert k["lost_contact"] == {"progress": 0.3, "seen_at": 900.0, "lost_at": None, "back_at": 20000.0,
                                 "back_state": "IDLE", "why": "restart"}, k


# --------------------------------------------------------------------------- #
# Its handler, the print's record and its review                              #
# --------------------------------------------------------------------------- #

def test_the_ambiguous_handler_queues_it_with_the_print_and_hands_it_to_the_review(monkeypatch, logs):
    seen = {}

    def review(*a, **k):
        seen["review"] = k
        seen["record"] = cancel_fetch_store.get_pending("XL", "7")
        return {"status": "pending"}
    monkeypatch.setattr(print_deduct, "_create_pending_cancel_review", review)
    monkeypatch.setattr(print_monitor, "_capture_end_heads",
                        lambda printer, job, fb, heads_when=None: seen.setdefault("when", heads_when))
    print_monitor._on_ambiguous_edge("XL", "/usb/A.BGC", 7, 0.3, "fb", heads_when="back", lost_contact=LC)
    assert seen["when"] == "back"
    assert seen["review"]["lost_contact"] == LC and seen["record"]["lost_contact"] == LC, seen
    assert logs[0] == (f"❓ Print on XL reached idle without a clear cancel/finish signal (~30% reached) — "
                       f"{WORDS} — computing a review (couldn't confirm completed vs cancelled)…"), logs


def test_the_queued_retry_hands_it_on(monkeypatch):
    seen = {}
    monkeypatch.setattr(print_deduct, "_create_pending_cancel_review",
                        lambda *a, **k: seen.update(k) or {"status": "pending"})
    print_monitor._compute_fetch({"printer_name": "XL", "job_id": "7", "filename": "/usb/A.BGC", "progress": 0.3,
                                  "kind": "cancel", "ambiguous": True, "lost_contact": LC}, "fb")
    assert seen["lost_contact"] == LC, seen


def test_a_review_fcc_couldnt_measure_keeps_it_and_says_it(logs):
    print_deduct._create_pending_cancel_review("XL", "/usb/A.BGC", "7", 0.3, fb_url="fb", ambiguous=True,
                                               progress_unknown=True, unmeasured_reason="unsampled",
                                               lost_contact=LC)
    assert cancel_review_store.get_pending("XL", "7")["lost_contact"] == LC
    assert logs[-1].endswith(f" {WORDS}."), logs


def test_a_computed_review_keeps_it_and_its_line_says_it(logs):
    gcode, frac = _cancelled_gcode()
    ctx = _preview_ctx(gcode, {"XL-1": {"printer_name": "XL", "position": 0}},
                       {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}},
                       {"XL-1": [100]}, {"updates": []})
    for m in ctx:
        m.start()
    try:
        out = app_module._create_pending_cancel_review("XL", "f.gcode", "J-1", frac, fb_url="http://fb",
                                                       ambiguous=True, lost_contact=LC)
    finally:
        for m in reversed(ctx):
            m.stop()
    assert out["status"] == "pending", out
    assert cancel_review_store.get_pending("XL", "J-1")["lost_contact"] == LC
    line = next(m for m in logs if "review computed" in m)
    assert line.startswith(f"❓ Print on XL reached idle (~{frac * 100:.0f}%, couldn't confirm cancel vs complete) — "
                           f"{WORDS} — review computed"), line


def test_a_review_from_the_print_end_read_keeps_it(logs):
    gcode, frac = _cancelled_gcode()
    ctx = _preview_ctx(gcode, {"XL-1": {"printer_name": "XL", "position": 0}},
                       {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}},
                       {"XL-1": [100]}, {"updates": []})
    end_heads = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 100, "sids": [100]}],
                 "source": "back", "at": "2026-11-23 10:00:00", "at_s": 10480.0}
    for m in ctx:
        m.start()
    try:
        out = app_module._create_pending_cancel_review("XL", "f.gcode", "J-2", frac, fb_url="http://fb",
                                                       end_heads=end_heads, lost_contact=LC)
    finally:
        for m in reversed(ctx):
            m.stop()
    assert out["status"] == "pending", out
    rec = cancel_review_store.get_pending("XL", "J-2")
    assert rec["lost_contact"] == LC and rec["heads_words"]["end"] == "when FCC saw the printer again", rec
    assert any(m.startswith(f"🛑 Cancelled print on XL (~{frac * 100:.0f}%) — {WORDS} — review partial") for m in logs), logs


def test_a_review_without_it_keeps_todays_record_and_line(logs):
    print_deduct._create_pending_cancel_review("XL", "/usb/A.BGC", "8", 0.3, fb_url="fb", ambiguous=True,
                                               progress_unknown=True, unmeasured_reason="unsampled")
    assert "lost_contact" not in cancel_review_store.get_pending("XL", "8")
    assert "lost contact" not in logs[-1], logs


def test_the_words_with_durations():
    assert print_deduct._lost_contact_words(LC) == f" — {WORDS}"
    assert print_deduct._lost_contact_words(dict(LC, why="restart")) == " — FCC last saw it at ~30%, before FCC restarted"
    assert print_deduct._lost_contact_words(None) == ""
    assert print_deduct._lost_contact_words(dict(LC, lost_at=None)) == " — FCC lost contact at ~30% and saw it again"
    assert print_deduct._HEADS_WORDS["back"] == "when FCC saw the printer again"
