"""Group 64.4 and 64.2 (3): a print file FCC can't read, and a deduct compute that
always raises, are tried less often, never given up before the 72-hour window.

Before this group:
  - `prusalink_api.fetch_cancel_gcode` answered None for a failed download, an empty
    decode and a decode exception alike, so a `.bgcode` FCC can't decode was read as
    "the file is locked behind the printer's screen" and downloaded again on every
    idle tick (30 s) for 72 hours (the 11 MB raccoon file takes about 20 minutes each
    time on the INDX).
  - A queued print whose compute raised was retried on every idle tick for 72 hours
    too, with only a debug line in hub.log.
  - Since the print-end hotfix (scope C) FCC downloads one file per printer at a
    time, so either one also held the deducts of the printer's other finished prints
    behind it in FCC's queue.

Derek, 2026-11-20 (the first build gave such a print up after 3 tries): "Trying for
30s for 72 is just to make sure we get the file ... And I'd rather do that than just
stop because something isn't working", and he wants a way to recover once he is
awake and has fixed the cause. Pinned here:
  - a file that downloads and can't be read is told apart from a failed download
    (`decode_error`), counted on the print's record (`decode_failures`), and said
    once in a WARNING line with a "↻ Try again now" button (not the "clear the
    screen" nudge: the file wasn't locked);
  - a compute that raises is counted (`raises`) and said once the same way (a live
    edge's raise is its own ERROR line and counts as the first try);
  - either is tried at the queue's pace 3 times, then waits 5 minutes, doubling to
    at most an hour (`next_try_at`), and is given up only when the 72 hours are out,
    the way the window always gave a print up (the "couldn't measure" card for a
    completion or an ambiguous end, a 0 g entry and one line for a true cancel);
  - a locked file (a plain failed download) keeps the 30-second pace, and ends a
    wait;
  - the printer's other queued print goes while the stuck one waits;
  - "Try again now" (POST /api/cancel_deduct/retry_fetch) ends the wait at once.

HEAD proof: the tests marked "red on d16b858" fail on the branch before this
revision (the 3-try give-up), and those marked "red on eb94846" on `dev` before
Group 64 too.
"""
from __future__ import annotations

import os
import sys
import threading
import time as _real_time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
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
WINDOW = 72 * 3600


class Clock:
    """The modules' `time`, its time() under the test's hand; the rest is real."""

    def __init__(self, now=1_000_000.0):
        self.now = now

    def time(self):
        return self.now

    def __getattr__(self, name):
        return getattr(_real_time, name)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(print_monitor, "time", c)
    monkeypatch.setattr(print_deduct, "time", c)
    return c


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


def _queue(printer, job_id, kind="cancel", filename="x.bgcode", first_seen=None, **extra):
    rec = {"printer_name": printer, "job_id": str(job_id), "filename": filename, "progress": 0.5,
           "first_seen": first_seen if first_seen is not None else print_monitor.time.time(),
           "kind": kind, "ambiguous": False, "attempts": 1, "last_status": "awaiting_fetch"}
    rec.update(extra)
    cancel_fetch_store.add_pending(rec)


def _fetch(answer, clock=None):
    """A stand-in for the download + decode that notes when each download began."""
    calls = []

    def _run(ip, key, filename, fraction, **kw):
        calls.append(clock.now if clock is not None else filename)
        return answer(filename) if callable(answer) else answer
    return calls, _run


def _tick(states=IDLE):
    print_monitor._process_pending_cancel_fetches(states, "http://fb")


def _run_ticks(clock, until_s, step_s):
    end = clock.now + until_s
    while clock.now < end:
        _tick()
        clock.now += step_s


def _lines(logs, words, level=None):
    return [m for m, lvl in logs if words in m and (level is None or lvl == level)]


# --------------------------------------------------------------------------- #
# The download tells a file FCC can't read from a failed download              #
# --------------------------------------------------------------------------- #

def test_a_file_that_downloads_and_cant_be_read_is_not_a_failed_download():
    """Red on eb94846."""
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
    with patch.object(prusalink_api, "_download_file_bytes", return_value=b"G1 E1\n"):
        assert prusalink_api.fetch_cancel_gcode("ip", "k", "a.gcode", 0.5)["gcode"] == "G1 E1\n"
    with patch.object(prusalink_api, "_download_file_bytes", return_value=b""):
        assert prusalink_api.fetch_cancel_gcode("ip", "k", "a.gcode", 0.5)["gcode"] == ""


def test_the_compute_says_undecodable_apart_from_download_failed():
    """Red on eb94846."""
    with patch.object(prusalink_api, "fetch_cancel_gcode", return_value=dict(UNREADABLE)):
        usage, terminal = print_deduct._compute_cancel_usage(XL, "a.bgcode", "7", 0.5, "ip", "k")
    assert usage is None
    assert terminal == {"status": "error", "reason": "undecodable", "job_id": "7",
                        "decode_error": "its binary G-code decoded to no G-code"}
    for answer in (None, {"gcode": "", "fraction": 0.5}):
        with patch.object(prusalink_api, "fetch_cancel_gcode", return_value=answer):
            _, terminal = print_deduct._compute_cancel_usage(XL, "a.gcode", "7", 0.5, "ip", "k")
        assert terminal["reason"] == "download_failed", answer


def test_the_wait_after_each_failure():
    """3 at the queue's pace, then 5 minutes, doubling, never more than an hour.
    Red on d16b858 (no waits: the print was given up after 3)."""
    now = 100.0
    assert [print_deduct._fetch_next_try_at(n, now) for n in (1, 2)] == [None, None]
    assert [print_deduct._fetch_next_try_at(n, now) - now for n in (3, 4, 5, 6, 7, 8, 40)] == \
        [300, 600, 1200, 2400, 3600, 3600, 3600]


# --------------------------------------------------------------------------- #
# A file FCC can't read: 3 quick tries, then slower, for the whole 72 hours    #
# --------------------------------------------------------------------------- #

def _never_reads(clock, logs, kind="complete", job=1141, printer=INDX, **extra):
    _queue(printer, job, kind=kind, **extra)
    calls, fetch = _fetch(dict(UNREADABLE), clock)
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        start = clock.now
        _run_ticks(clock, 3600, 60)                       # the first hour, a tick a minute
        _run_ticks(clock, WINDOW - 3600 - 600, 600)        # the rest, a tick per 10 minutes
        assert cancel_fetch_store.has_pending(printer, str(job)), "given up before the 72 hours"
        _run_ticks(clock, 1800, 600)                       # past the 72 hours
    return calls, start


def test_a_completion_whose_file_never_decodes_keeps_trying_for_72_hours_then_asks(clock, logs):
    """Red on d16b858: the first build gave it up after 3 downloads."""
    calls, start = _never_reads(clock, logs)
    offsets = [t - start for t in calls]
    assert offsets[:3] == [0, 60, 120], offsets[:6]           # 3 at the queue's pace
    assert offsets[3] >= 120 + 300, offsets[:6]               # then 5 minutes
    gaps = [b - a for a, b in zip(offsets[2:], offsets[3:])]
    assert all(300 <= g <= 3600 + 600 for g in gaps), gaps    # never faster, at most hourly
    assert 70 <= len(calls) <= 90, len(calls)                 # not thousands
    assert not cancel_fetch_store.has_pending(INDX, "1141")
    card = cancel_review_store.get_pending(INDX, "1141")
    assert card["kind"] == "progress_unknown" and card["unmeasured_reason"] == "no_download", card
    assert print_deduct_ledger.was_deducted(INDX, "1141") is False
    warned = _lines(logs, "couldn't read it", "WARNING")
    assert len(warned) == 1, logs
    assert "less often (at most once an hour) for up to 72 hours" in warned[0], warned
    assert 'class="btn btn-sm btn-outline-warning ms-2 py-0 px-1 fcc-fetch-retry-btn"' in warned[0]
    assert 'data-fetch-printer="INDX" data-fetch-job="1141"' in warned[0], warned
    assert not _lines(logs, NUDGE), "the file wasn't locked: no 'clear the screen' nudge"


def test_a_true_cancel_whose_file_never_decodes_is_recorded_at_0g_after_72_hours(clock, logs):
    """Red on d16b858 (given up after 3, with other words)."""
    calls, _ = _never_reads(clock, logs, kind="cancel", job=7, printer=XL)
    assert len(calls) > 3
    assert print_deduct_ledger.was_deducted(XL, "7") is True
    gave_up = _lines(logs, "Gave up fetching the cancelled print's gcode", "WARNING")
    assert len(gave_up) == 1 and "after 72h (its file downloaded but couldn't be read)" in gave_up[0], logs


def test_an_ambiguous_end_whose_file_never_decodes_gets_the_flagged_card_after_72_hours(clock, logs):
    """Red on d16b858 (given up after 3)."""
    calls, _ = _never_reads(clock, logs, kind="cancel", job=8, printer=XL, ambiguous=True)
    assert len(calls) > 3
    card = cancel_review_store.get_pending(XL, "8")
    assert card["unmeasured_reason"] == "no_download" and card["ambiguous"] is True, card


def test_the_first_failure_of_an_in_flight_record_that_cant_be_read_is_no_nudge(logs):
    """The live edge writes its record "in_flight" before the download; a first
    failure that is a file FCC can't read says so, not "clear the screen". Red on
    eb94846."""
    print_deduct._hold_fetch_in_flight(XL, "x.bgcode", 7, 0.4, kind="cancel")
    print_deduct._enqueue_cancel_fetch(XL, "x.bgcode", 7, 0.4, decode_error="bad block")
    assert not _lines(logs, NUDGE), logs
    assert len(_lines(logs, "couldn't read it (bad block)", "WARNING")) == 1, logs
    rec = cancel_fetch_store.get_pending(XL, "7")
    assert rec["decode_failures"] == 1 and rec["last_error"] == "bad block"
    assert rec["last_failure"] == "decode" and "next_try_at" not in rec


def test_a_locked_file_keeps_the_30_second_pace_and_ends_a_wait(clock, logs):
    """A plain failed download is the file locked behind the printer's screen:
    tried at every idle tick for the whole window, so clearing the screen gets it at
    the next tick. A record waiting out an unreadable file whose next download fails
    plainly is back at that pace. Passes on d16b858 for its first half by design."""
    _queue(XL, 7)
    calls, fetch = _fetch(None, clock)
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        _run_ticks(clock, 1800, 30)
    assert len(calls) == 60, len(calls)
    rec = cancel_fetch_store.get_pending(XL, "7")
    assert rec["last_failure"] == "download" and "next_try_at" not in rec, rec
    for _ in range(3):
        print_deduct._enqueue_cancel_fetch(XL, "x.bgcode", 7, 0.5, decode_error="bad block")
    assert cancel_fetch_store.get_pending(XL, "7")["next_try_at"] > clock.now
    print_deduct._enqueue_cancel_fetch(XL, "x.bgcode", 7, 0.5)
    assert "next_try_at" not in cancel_fetch_store.get_pending(XL, "7")


# --------------------------------------------------------------------------- #
# A compute that always raises                                                 #
# --------------------------------------------------------------------------- #

def test_a_queued_cancel_whose_compute_always_raises_slows_down_and_is_recorded_after_72_hours(clock, logs):
    """Red on d16b858 (given up after 3)."""
    _queue(XL, 7)
    calls = []

    def _review(*a, **k):
        calls.append(clock.now)
        raise KeyError("heads")
    with patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        start = clock.now
        _run_ticks(clock, 3600, 60)
        early = len(calls)
        _run_ticks(clock, WINDOW - 3600 + 1800, 600)
    assert early == 3 + 3, early        # 3 at once, then after 5, 10 and 20 more minutes
    assert calls[3] - start >= 120 + 300
    warned = _lines(logs, "couldn't work out the deduct", "WARNING")
    assert len(warned) == 1, logs
    assert "KeyError: 'heads'" in warned[0] and "for up to 72 hours" in warned[0], warned
    assert "fcc-fetch-retry-btn" in warned[0]
    gave_up = _lines(logs, "Gave up fetching the cancelled print's gcode", "WARNING")
    assert len(gave_up) == 1 and "(its deduct kept failing)" in gave_up[0], logs
    assert print_deduct_ledger.was_deducted(XL, "7") is True


def test_a_queued_completion_whose_compute_always_raises_asks_with_its_own_words_after_72_hours(clock, logs):
    """Red on d16b858 (given up after 3)."""
    _queue(INDX, 1141, kind="complete")
    calls = []

    def _complete(*a, **k):
        calls.append(clock.now)
        raise RuntimeError("review store busy")
    with patch.object(print_deduct, "deduct_completed_print", side_effect=_complete):
        _run_ticks(clock, 3600, 60)
        assert cancel_fetch_store.has_pending(INDX, "1141")
        _run_ticks(clock, WINDOW - 3600 + 1800, 600)
    assert len(calls) > 3
    card = cancel_review_store.get_pending(INDX, "1141")
    assert card["unmeasured_reason"] == "compute_failed", card
    assert print_deduct._UNMEASURED_WHY["compute_failed"] == "FCC's deduct of it kept failing"
    assert print_deduct_ledger.was_deducted(INDX, "1141") is False


def test_a_live_edges_raise_counts_as_the_first_try_and_is_said_only_once(clock, logs):
    """The edge's own ERROR line says it, so the queue's raises log no WARNING on
    top; the 3 quick tries include the edge's. Red on eb94846. Since the Group 64
    review (S5) that line says how the queue keeps trying and carries the "Try again
    now" button, which no line on this path offered."""
    calls = []

    def _review(*a, **k):
        calls.append(clock.now)
        raise RuntimeError("boom")
    with patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        print_monitor._on_cancel_edge(XL, "x.gcode", 7, 0.4, "http://fb")
        failed = _lines(logs, "review failed", "ERROR")
        assert len(failed) == 1, logs
        assert ("FCC tries again when the printer is idle, twice more right away, then less often "
                "(at most once an hour) for up to 72 hours." in failed[0]), failed
        assert failed[0].endswith("↻ Try again now</button>"), failed
        assert cancel_fetch_store.get_pending(XL, "7")["raises"] == 1
        clock.now += 60
        _tick()
        clock.now += 60
        _tick()
        assert cancel_fetch_store.get_pending(XL, "7")["next_try_at"] == clock.now + 300
        clock.now += 60
        _tick()
    assert len(calls) == 3, calls
    assert not _lines(logs, "couldn't work out the deduct"), logs


def test_compute_failed_has_words_on_the_card():
    with open(os.path.join(os.path.dirname(__file__), "..", "static", "js", "modules",
                           "cancel_review.js"), encoding="utf-8") as fh:
        src = fh.read()
    case = src.index("case 'compute_failed':")
    assert "kept failing" in src[case:case + 400]


# --------------------------------------------------------------------------- #
# What goes meanwhile, and Try again now                                       #
# --------------------------------------------------------------------------- #

def test_the_printers_other_queued_print_goes_while_the_stuck_one_waits(clock, monkeypatch, logs):
    """One download per printer at a time (scope C): the stuck file used to hold the
    printer's next queued deduct behind it for the whole 72 hours. Red on eb94846."""
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
        _tick()
        go.set()
        for t in list(threading.enumerate()):
            if t not in before:
                t.join(10)
        go.clear()
        clock.now += 60

    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch), \
            patch.object(print_deduct, "_create_pending_cancel_review", side_effect=_review):
        for _ in range(3):
            _tick_and_finish()
            assert computed == [], "the next print went while the stuck one was downloading"
        _tick_and_finish()                       # the stuck one waits: the next one goes
    assert calls == ["stuck.bgcode"] * 3
    assert computed == ["2"]
    assert cancel_fetch_store.has_pending(INDX, "1"), "the stuck one is still tried later"
    assert not cancel_fetch_store.has_pending(INDX, "2")


def test_try_again_now_ends_the_wait(clock, logs):
    """Derek, 2026-11-20: a way to recover once the cause is fixed. Red on d16b858."""
    _queue(INDX, 1141, kind="complete")
    calls, fetch = _fetch(dict(UNREADABLE), clock)
    with patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch):
        for _ in range(4):
            _tick()
            clock.now += 60
        assert len(calls) == 3                            # the 4th waits
        r = app_module.app.test_client().post(
            "/api/cancel_deduct/retry_fetch", json={"printer_name": INDX, "job_id": "1141"})
        body = r.get_json()
        assert body["success"] is True and "as soon as the printer is idle" in body["msg"], body
        rec = cancel_fetch_store.get_pending(INDX, "1141")
        assert "next_try_at" not in rec and rec["decode_failures"] == 0, rec
        _tick()
    assert len(calls) == 4
    assert _lines(logs, "will be tried again as soon as the printer is idle", "INFO")


def test_try_again_now_says_when_nothing_waits(logs):
    """Red on d16b858 (no route)."""
    client = app_module.app.test_client()
    body = client.post("/api/cancel_deduct/retry_fetch",
                       json={"printer_name": XL, "job_id": "9"}).get_json()
    assert body["success"] is False and "Nothing is waiting for job 9" in body["msg"], body
    print_deduct_ledger.record_deduct(XL, "9", filename="f", scale=1.0, grams=0)
    body = client.post("/api/cancel_deduct/retry_fetch",
                       json={"printer_name": XL, "job_id": "9"}).get_json()
    assert body["success"] is False and "settled already" in body["msg"], body
    body = client.post("/api/cancel_deduct/retry_fetch", json={"printer_name": XL}).get_json()
    assert body["success"] is False and "names no print" in body["msg"], body


def test_the_buttons_attributes_are_escaped():
    btn = print_deduct._fetch_retry_button('My "Big" <Printer>', "12&3")
    assert 'data-fetch-printer="My &quot;Big&quot; &lt;Printer&gt;"' in btn, btn
    assert 'data-fetch-job="12&amp;3"' in btn, btn
