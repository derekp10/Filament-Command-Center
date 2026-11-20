"""Group 64.4 and 64.2 (3): a print file FCC can't read, and a deduct compute that
always raises, are tried 3 times, not for 72 hours.

Before this group:
  - `prusalink_api.fetch_cancel_gcode` answered None for a failed download, an empty
    decode and a decode exception alike, so a `.bgcode` FCC can't decode was read as
    "the file is locked behind the printer's screen" and downloaded again on every
    idle tick (30 s) until the 72-hour give-up (the 11 MB raccoon file takes about
    20 minutes each time on the INDX).
  - A queued print whose compute raised was retried on every idle tick for 72 hours
    too, with only a debug line in hub.log.
  - Since the print-end hotfix (scope C) a printer gets one download at a time, so
    either one also held the printer's other queued prints behind it.

Pinned here:
  - a file that downloads and can't be read is told apart from a failed download
    (`decode_error`), counted on the print's record (`decode_failures`), said once in
    a WARNING line (not the "clear the screen" nudge: the file wasn't locked), and
    given up after 3 downloads, before a 4th;
  - a compute that raises is counted (`raises`), said once at WARNING (a live edge's
    raise is its own ERROR line and counts as the first try), and given up after 3;
  - each gives up the way the 72-hour window does: a completion FCC owns and an
    ambiguous end get the "couldn't measure" review ("no_download" for a file,
    "compute_failed" for a compute), a true cancel a 0 g entry and one "weigh the
    spool" line;
  - a plain failed download still waits the 72 hours, and only then gives up;
  - the printer's other queued print is computed once the stuck one is given up.

HEAD proof: every test here fails on `dev` eb94846 (before Group 64) except the two
marked "passes before the change by design".
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
import prusalink_api  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402

XL = "XL"
INDX = "INDX"
CREDS = {"ip_address": "1.2.3.4", "api_key": "k"}
IDLE = {XL: {"state": "IDLE"}, INDX: {"state": "IDLE"}}
NUDGE = "Clear it on the printer"
UNREADABLE = {"gcode": None, "decode_error": "its binary G-code decoded to no G-code"}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_monitor, "_FETCH_CLAIMS", set(), raising=False)
    monkeypatch.setattr(print_monitor, "_ABANDONED_COMPLETIONS", set())
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    monkeypatch.setattr(config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
    monkeypatch.setattr(config_loader, "load_config", lambda: {})
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {})
    monkeypatch.setattr(print_deduct, "_heads_snapshot", lambda *a, **k: [])
    monkeypatch.setattr(print_deduct, "_capture_print_heads", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(print_deduct.prusalink_api, "fetch_printer_credentials",
                        lambda *a, **k: dict(CREDS))
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()
    before = set(threading.enumerate())
    yield
    for t in list(threading.enumerate()):
        if t not in before and t is not threading.current_thread():
            t.join(10)
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry",
                        lambda msg, level="INFO", *a, **k: calls.append((msg, level)))
    return calls


def _queue(printer, job_id, kind="cancel", filename="x.bgcode", **extra):
    rec = {"printer_name": printer, "job_id": str(job_id), "filename": filename, "progress": 0.5,
           "first_seen": time.time(), "kind": kind, "ambiguous": False, "attempts": 1,
           "last_status": "awaiting_fetch"}
    rec.update(extra)
    cancel_fetch_store.add_pending(rec)


def _fetch(answer):
    """A stand-in for the download + decode that counts each download."""
    calls = []

    def _run(ip, key, filename, fraction, **kw):
        calls.append(filename)
        return answer(filename) if callable(answer) else answer
    return calls, _run


def _ticks(n, states=IDLE):
    for _ in range(n):
        print_monitor._process_pending_cancel_fetches(states, "http://fb")


def _lines(logs, words, level=None):
    return [m for m, lvl in logs if words in m and (level is None or lvl == level)]


# --------------------------------------------------------------------------- #
# The download tells a file FCC can't read from a failed download              #
# --------------------------------------------------------------------------- #

def test_a_file_that_downloads_and_cant_be_read_is_not_a_failed_download():
    with patch.object(prusalink_api, "_download_file_bytes", return_value=None):
        assert prusalink_api.fetch_cancel_gcode("ip", "k", "a.bgcode", 0.5) is None
    with patch.object(prusalink_api, "_download_file_bytes", return_value=b"GCDE..."), \
            patch.object(prusalink_api.bgcode_decode, "is_bgcode", return_value=True), \
            patch.object(prusalink_api.bgcode_decode, "decode_bgcode", return_value={"gcode": ""}):
        got = prusalink_api.fetch_cancel_gcode("ip", "k", "a.bgcode", 0.5)
    assert got == {"gcode": None, "decode_error": "its binary G-code decoded to no G-code"}
    with patch.object(prusalink_api, "_download_file_bytes", return_value=b"GCDE..."), \
            patch.object(prusalink_api.bgcode_decode, "is_bgcode", return_value=True), \
            patch.object(prusalink_api.bgcode_decode, "decode_bgcode",
                         side_effect=ValueError("bad block checksum")):
        got = prusalink_api.fetch_cancel_gcode("ip", "k", "a.bgcode", 0.5)
    assert got == {"gcode": None, "decode_error": "ValueError: bad block checksum"}
    # A plain-text file reads as before, and an empty body is still a failed download.
    with patch.object(prusalink_api, "_download_file_bytes", return_value=b"G1 E1\n"):
        assert prusalink_api.fetch_cancel_gcode("ip", "k", "a.gcode", 0.5)["gcode"] == "G1 E1\n"
    with patch.object(prusalink_api, "_download_file_bytes", return_value=b""):
        assert prusalink_api.fetch_cancel_gcode("ip", "k", "a.gcode", 0.5)["gcode"] == ""


def test_the_compute_says_undecodable_apart_from_download_failed():
    with patch.object(prusalink_api, "fetch_cancel_gcode", return_value=dict(UNREADABLE)):
        usage, terminal = print_deduct._compute_cancel_usage(XL, "a.bgcode", "7", 0.5, "ip", "k")
    assert usage is None
    assert terminal == {"status": "error", "reason": "undecodable", "job_id": "7",
                        "decode_error": "its binary G-code decoded to no G-code"}
    for answer in (None, {"gcode": "", "fraction": 0.5}):
        with patch.object(prusalink_api, "fetch_cancel_gcode", return_value=answer):
            _, terminal = print_deduct._compute_cancel_usage(XL, "a.gcode", "7", 0.5, "ip", "k")
        assert terminal["reason"] == "download_failed", answer


# --------------------------------------------------------------------------- #
# A file FCC can't read: 3 downloads, one WARNING, then the give-up            #
# --------------------------------------------------------------------------- #

def test_a_completion_whose_file_never_decodes_is_downloaded_3_times_then_asks(logs):
    _queue(INDX, 1141, kind="complete")
    calls, fetch = _fetch(dict(UNREADABLE))
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        _ticks(3)
        assert len(calls) == 3
        rec = cancel_fetch_store.get_pending(INDX, "1141")
        assert rec["decode_failures"] == 3, rec
        assert not cancel_review_store.has_pending(INDX, "1141")
        _ticks(3)
    assert len(calls) == 3, "a 4th download started"
    assert not cancel_fetch_store.has_pending(INDX, "1141")
    card = cancel_review_store.get_pending(INDX, "1141")
    assert card["kind"] == "progress_unknown" and card["unmeasured_reason"] == "no_download", card
    assert print_deduct_ledger.was_deducted(INDX, "1141") is False, "a completion is never 0 g unasked"
    warned = _lines(logs, "couldn't read it", "WARNING")
    assert len(warned) == 1, logs
    assert "its binary G-code decoded to no G-code" in warned[0] and "3 times in all" in warned[0]
    assert not _lines(logs, NUDGE), "the file wasn't locked: no 'clear the screen' nudge"


def test_an_ambiguous_end_whose_file_never_decodes_gets_the_flagged_card(logs):
    _queue(XL, 7, ambiguous=True)
    calls, fetch = _fetch(dict(UNREADABLE))
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        _ticks(5)
    assert len(calls) == 3
    card = cancel_review_store.get_pending(XL, "7")
    assert card["unmeasured_reason"] == "no_download" and card["ambiguous"] is True, card
    assert not cancel_fetch_store.has_pending(XL, "7")


def test_a_true_cancel_whose_file_never_decodes_is_recorded_at_0g_with_one_line(logs):
    _queue(XL, 7)
    calls, fetch = _fetch(dict(UNREADABLE))
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        _ticks(5)
    assert len(calls) == 3
    assert print_deduct_ledger.was_deducted(XL, "7") is True
    assert not cancel_review_store.has_pending(XL, "7")
    gave_up = _lines(logs, "Gave up on the cancelled print's deduct", "WARNING")
    assert len(gave_up) == 1, logs
    assert "downloaded its file 3 times and couldn't read it" in gave_up[0], gave_up
    assert "Weigh the spool" in gave_up[0]


def test_the_first_failure_of_an_in_flight_record_that_cant_be_read_is_no_nudge(logs):
    """The live edge writes its record "in_flight" before the download; a first
    failure that is a file FCC can't read says so, not "clear the screen"."""
    print_deduct._hold_fetch_in_flight(XL, "x.bgcode", 7, 0.4, kind="cancel")
    print_deduct._enqueue_cancel_fetch(XL, "x.bgcode", 7, 0.4, decode_error="bad block")
    assert not _lines(logs, NUDGE), logs
    assert len(_lines(logs, "couldn't read it (bad block)", "WARNING")) == 1, logs
    rec = cancel_fetch_store.get_pending(XL, "7")
    assert rec["decode_failures"] == 1 and rec["last_error"] == "bad block"


def test_a_decode_failure_after_a_locked_download_is_said_once_too(logs):
    """A first download at the cancel screen fails (the lock: the nudge), then the
    file comes in and can't be read: one WARNING, then nothing more until the give-up."""
    print_deduct._enqueue_cancel_fetch(XL, "x.bgcode", 7, 0.4)
    print_deduct._enqueue_cancel_fetch(XL, "x.bgcode", 7, 0.4, decode_error="bad block")
    print_deduct._enqueue_cancel_fetch(XL, "x.bgcode", 7, 0.4, decode_error="bad block")
    assert len(_lines(logs, NUDGE)) == 1
    assert len(_lines(logs, "couldn't read it")) == 1, logs
    assert cancel_fetch_store.get_pending(XL, "7")["decode_failures"] == 2


# --------------------------------------------------------------------------- #
# A compute that always raises: 3 tries, one WARNING, then the give-up         #
# --------------------------------------------------------------------------- #

def test_a_queued_cancel_whose_compute_always_raises_is_tried_3_times_then_recorded(logs):
    _queue(XL, 7)
    calls = []

    def _review(*a, **k):
        calls.append(a)
        raise KeyError("heads")
    with patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        _ticks(3)
        assert len(calls) == 3 and cancel_fetch_store.get_pending(XL, "7")["raises"] == 3
        _ticks(3)
    assert len(calls) == 3, "a 4th compute started"
    warned = _lines(logs, "couldn't work out the deduct", "WARNING")
    assert len(warned) == 1, logs
    assert "KeyError: 'heads'" in warned[0] and "3 times in all" in warned[0], warned
    gave_up = _lines(logs, "Gave up on the cancelled print's deduct", "WARNING")
    assert len(gave_up) == 1 and "its deduct failed 3 times" in gave_up[0], logs
    assert print_deduct_ledger.was_deducted(XL, "7") is True
    assert not cancel_fetch_store.has_pending(XL, "7")


def test_a_queued_completion_whose_compute_always_raises_asks_with_its_own_words(logs):
    _queue(INDX, 1141, kind="complete")
    calls = []

    def _complete(*a, **k):
        calls.append(a)
        raise RuntimeError("review store busy")
    with patch.object(print_deduct, "deduct_completed_print", side_effect=_complete):
        _ticks(5)
    assert len(calls) == 3
    card = cancel_review_store.get_pending(INDX, "1141")
    assert card["unmeasured_reason"] == "compute_failed", card
    assert print_deduct_ledger.was_deducted(INDX, "1141") is False
    assert "failed 3 times" in print_deduct._UNMEASURED_WHY["compute_failed"]
    assert len(_lines(logs, "couldn't work out the deduct", "WARNING")) == 1, logs


def test_a_live_edges_raise_counts_as_the_first_try_and_is_said_only_once(logs):
    """The edge's own ERROR line says it (and how many tries are left), so the
    queue's first raise logs no WARNING on top; two more raises give it up."""
    calls = []

    def _review(*a, **k):
        calls.append(a)
        raise RuntimeError("boom")
    with patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        print_monitor._on_cancel_edge(XL, "x.gcode", 7, 0.4, "http://fb")
        failed = _lines(logs, "review failed", "ERROR")
        assert len(failed) == 1 and "(3 tries in all)" in failed[0], logs
        assert cancel_fetch_store.get_pending(XL, "7")["raises"] == 1
        _ticks(4)
    assert len(calls) == 3, calls
    assert not _lines(logs, "couldn't work out the deduct"), logs
    assert len(_lines(logs, "its deduct failed 3 times")) == 1, logs


def test_compute_failed_has_words_on_the_card():
    with open(os.path.join(os.path.dirname(__file__), "..", "static", "js", "modules",
                           "cancel_review.js"), encoding="utf-8") as fh:
        src = fh.read()
    case = src.index("case 'compute_failed':")
    assert "failed 3 times" in src[case:case + 400]


# --------------------------------------------------------------------------- #
# What still waits the 72 hours, and what goes after the give-up               #
# --------------------------------------------------------------------------- #

def test_a_plain_failed_download_still_waits_the_72_hours(logs):
    """Passes before the change by design: a locked file keeps its 72 hours."""
    _queue(XL, 7)
    calls, fetch = _fetch(None)
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        _ticks(6)
        assert len(calls) == 6
        assert cancel_fetch_store.has_pending(XL, "7")
        assert not print_deduct_ledger.was_deducted(XL, "7")
        old = dict(cancel_fetch_store.get_pending(XL, "7"),
                   first_seen=time.time() - print_monitor._CANCEL_FETCH_MAX_AGE_S - 60)
        cancel_fetch_store.add_pending(old)
        _ticks(1)
    assert len(calls) == 6
    assert len(_lines(logs, "Gave up fetching the cancelled print's gcode", "WARNING")) == 1, logs
    assert print_deduct_ledger.was_deducted(XL, "7") is True


def test_the_72_hour_give_up_of_a_completion_keeps_its_review(logs):
    """Passes before the change by design: the factored give-up keeps 56.3's rule."""
    _queue(INDX, 1141, kind="complete", first_seen=time.time() - print_monitor._CANCEL_FETCH_MAX_AGE_S - 60)
    calls, fetch = _fetch(None)
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        _ticks(1)
    assert calls == []
    assert cancel_review_store.get_pending(INDX, "1141")["unmeasured_reason"] == "no_download"


def test_the_printers_other_queued_print_goes_after_the_stuck_one_is_given_up(monkeypatch, logs):
    """One download per printer at a time (scope C): the stuck file used to hold
    the printer's next queued print behind it for the whole 72 hours."""
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", True)
    _queue(INDX, 1, filename="stuck.bgcode")
    _queue(INDX, 2, filename="next.gcode")
    real_review = print_deduct._create_pending_cancel_review
    go = threading.Event()
    computed = []
    calls, fetch = _fetch(lambda name: (go.wait(10), dict(UNREADABLE))[1])

    def _review(printer, filename, job_id, progress, **kw):
        if str(job_id) == "2":
            computed.append(str(job_id))
            return {"status": "pending", "job_id": "2"}
        return real_review(printer, filename, job_id, progress, **kw)

    def _tick_and_finish():
        before = set(threading.enumerate())
        print_monitor._process_pending_cancel_fetches(IDLE, "http://fb")
        go.set()
        for t in list(threading.enumerate()):
            if t not in before:
                t.join(10)
        go.clear()

    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch), \
            patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        for _ in range(3):
            _tick_and_finish()
            assert computed == [], "the next print went while the stuck one was downloading"
        _tick_and_finish()
    assert calls == ["stuck.bgcode"] * 3
    assert computed == ["2"]
    assert not cancel_fetch_store.has_pending(INDX, "1")
    assert not cancel_fetch_store.has_pending(INDX, "2")
