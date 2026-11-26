"""Group 65.1 (2) (Derek, 2026-11-09: "the biggest problem, is if the network drops mid
print, and fcc doesn't receive data when everything re-connects"): one line when FCC
loses contact with a printer and one when it's back, kept by the print monitor. Offline.

Three failed monitor probes in a row count as lost: a WARNING while a print is latched,
INFO when the printer was idle. Back is one INFO line with the gap; a print that ended
while FCC couldn't see it is named from the latch, before its edge's own line. Silent
for a printer with no PrusaLink IP saved, one that hasn't answered since FCC started,
and a one- or two-probe blip. Restart recovery says once that a latched print's printer
is silent. The probe notes why it failed (prusalink_api.last_probe_failure) beside its
unchanged answer.

Driven through the real _cancel_monitor_tick with a scripted probe; the edge itself is a
stand-in that latches and clears as the real one does, except where a test says.
Red on 1be96d6e (no line at all; no last_probe_failure).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

import app as app_module  # noqa: F401  (the route modules, as the monitor imports them)
import print_monitor
import prusalink_api
import state

NASTY = "<b>&x.gcode"
NASTY_ESC = "&lt;b&gt;&amp;x.gcode"
PM = {"XL-1": {"printer_name": "XL", "position": 0}}


@pytest.fixture(autouse=True)
def _monitor(monkeypatch):
    print_monitor._PRINT_TRACKER.clear()
    print_monitor._CONTACT.clear()
    prusalink_api._LAST_PROBE_FAILURE.clear()
    monkeypatch.setattr(print_monitor.locations_db, "get_active_printer_map", lambda: dict(PM))
    monkeypatch.setattr(print_monitor.config_loader, "get_api_urls", lambda: ("http://sm", "http://fb"))
    monkeypatch.setattr(print_monitor.print_tracker_store, "save", lambda snap: None)
    monkeypatch.setattr(print_monitor, "_process_pending_cancel_fetches", lambda *a, **k: None)
    yield
    print_monitor._PRINT_TRACKER.clear()
    print_monitor._CONTACT.clear()
    prusalink_api._LAST_PROBE_FAILURE.clear()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a[0] if a else None)))
    return calls


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(print_monitor.time, "time", lambda: now["t"])
    return now


class Edge:
    """The edge as the real one keeps the latch: a print state latches the file and
    progress, anything else clears it (and says so, the way an edge's own line would)."""

    def __init__(self, logs):
        self.logs = logs

    def __call__(self, name, state_info, fb_url):
        if state_info is None:
            return
        cur = state_info["state"]
        with print_monitor._PRINT_TRACKER_LOCK:
            if cur in ("PRINTING", "PAUSED", "ATTENTION"):
                entry = print_monitor._PRINT_TRACKER.setdefault(name, {})
                entry.update(state=cur, filename=state_info.get("file", NASTY), job_id=7,
                             progress=state_info.get("progress", 0.3))
            else:
                had = print_monitor._PRINT_TRACKER.pop(name, None)
                if had and had.get("filename"):
                    self.logs.append((f"EDGE {cur}", "INFO"))


def _tick(monkeypatch, logs, *answers, why=None):
    """One monitor tick per answer: a dict is a good probe, None a failed one (`why`
    the probe's own reason)."""
    monkeypatch.setattr(print_monitor, "_track_print_edge", Edge(logs))
    for ans in answers:
        def probe(fb, name, ans=ans):
            prusalink_api._note_probe_failure(name, None if ans else (why or "timeout"))
            return ans
        monkeypatch.setattr(prusalink_api, "get_printer_state", probe)
        print_monitor._cancel_monitor_tick()


def _p(state_, **more):
    return dict({"state": state_, "is_active": state_ == "PRINTING"}, **more)


LOST_PRINTING = f"📡 Lost contact with XL: it was printing '{NASTY_ESC}' (~30%) when FCC last saw it."


def test_three_failed_probes_while_printing_say_lost_once(monkeypatch, logs):
    _tick(monkeypatch, logs, _p("PRINTING"), None, None)
    assert logs == []                                      # a two-probe blip: nothing
    _tick(monkeypatch, logs, None, None, None)
    assert logs == [(LOST_PRINTING, "WARNING")]            # the third says it, and only once


def test_a_blip_of_two_says_nothing_lost_or_back(monkeypatch, logs):
    _tick(monkeypatch, logs, _p("PRINTING"), None, None, _p("PRINTING"), None, None, _p("PRINTING"))
    assert logs == []


def test_an_idle_printer_lost_is_info(monkeypatch, logs):
    _tick(monkeypatch, logs, _p("IDLE"), None, None, None)
    assert logs == [("📡 Lost contact with XL (it was idle).", "INFO")]


def test_back_mid_print_says_the_gap_and_the_progress_its_job_read_saw(monkeypatch, logs, clock):
    _tick(monkeypatch, logs, _p("PRINTING"))
    clock["t"] += 10
    _tick(monkeypatch, logs, None)                         # contact lost from here
    clock["t"] += 9480                                     # 2 h 38 min later, at the third miss and on
    _tick(monkeypatch, logs, None, None)
    _tick(monkeypatch, logs, _p("PRINTING", progress=0.62))
    assert logs[1:] == [("📡 XL is back after 2 h 38 min (PRINTING, ~62%).", "INFO")]


@pytest.mark.parametrize("back,fate", [
    ("IDLE", "ended while FCC couldn't see it; 🛑 Review will ask about it."),
    # Group 65 review (WD3 / WD10): a finished, stopped or busy screen may be another
    # print's, or no end at all: only what FCC last saw.
    ("FINISHED", "when FCC last saw it, it was printing '{f}' (~30%)."),
    ("STOPPED", "when FCC last saw it, it was printing '{f}' (~30%)."),
    ("BUSY", "when FCC last saw it, it was printing '{f}' (~30%)."),
])
def test_a_print_that_ended_unseen_is_named_before_its_edges_line(monkeypatch, logs, clock, back, fate):
    _tick(monkeypatch, logs, _p("PRINTING"), None, None, None)
    clock["t"] += 600
    _tick(monkeypatch, logs, _p(back))
    lead = "the print FCC last saw at ~30% " if back == "IDLE" else ""
    assert logs[1:] == [(f"📡 XL is back after 10 min ({back}): {lead}{fate.format(f=NASTY_ESC)}", "INFO"),
                        (f"EDGE {back}", "INFO")]


def test_back_idle_with_nothing_latched_is_one_plain_line(monkeypatch, logs, clock):
    _tick(monkeypatch, logs, _p("IDLE"), None, None, None)
    clock["t"] += 90
    _tick(monkeypatch, logs, _p("IDLE"))
    assert logs == [("📡 Lost contact with XL (it was idle).", "INFO"),
                    ("📡 XL is back after 1 min (IDLE).", "INFO")]


def test_no_ip_saved_says_nothing(monkeypatch, logs):
    _tick(monkeypatch, logs, _p("PRINTING"))
    _tick(monkeypatch, logs, None, None, None, None, why="no_ip")
    assert logs == []


def test_a_printer_that_never_answered_since_fcc_started_says_nothing(monkeypatch, logs):
    _tick(monkeypatch, logs, None, None, None, None, None)
    assert logs == []


def test_a_printer_removed_from_the_map_loses_its_record(monkeypatch, logs):
    _tick(monkeypatch, logs, _p("IDLE"))
    assert "XL" in print_monitor._CONTACT
    monkeypatch.setattr(print_monitor.locations_db, "get_active_printer_map",
                        lambda: {"MK4-1": {"printer_name": "MK4", "position": 0}})
    _tick(monkeypatch, logs, _p("IDLE"))
    assert "XL" not in print_monitor._CONTACT


def test_the_real_edge_brings_the_progress_up_to_date_before_back_is_said(monkeypatch, logs):
    """With the real _track_print_edge: the back line's percentage is the job read the
    edge made on this tick, not the one FCC last saw."""
    monkeypatch.setattr(print_monitor, "_track_print_edge", print_monitor._track_print_edge)
    jobs = {"p": 0.3}
    monkeypatch.setattr(prusalink_api, "get_printer_job",
                        lambda fb, name: {"job_id": 7, "filename": NASTY, "progress": jobs["p"]})
    monkeypatch.setattr(print_monitor.print_deduct, "_snapshot_active_spools", lambda *a, **k: {})
    for ans in (_p("PRINTING"), None, None, None):
        monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name, ans=ans: ans)
        if ans is None:
            prusalink_api._note_probe_failure("XL", "timeout")
        print_monitor._cancel_monitor_tick()
    jobs["p"] = 0.62
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: _p("PRINTING"))
    print_monitor._cancel_monitor_tick()
    msgs = [m for m, lvl in logs]
    assert msgs[0] == LOST_PRINTING, msgs
    assert msgs[-1].startswith("📡 XL is back after") and msgs[-1].endswith("(PRINTING, ~62%)."), msgs


def test_restart_recovery_says_once_that_a_latched_prints_printer_is_silent(monkeypatch, logs):
    entry = {"state": "PRINTING", "job_id": 7, "filename": NASTY, "progress": 0.3}
    monkeypatch.setattr(prusalink_api, "get_printer_state",
                        lambda fb, name: prusalink_api._note_probe_failure(name, "timeout"))
    assert print_monitor._recover_one_print_latch("XL", entry, "http://fb") is True
    assert logs == [(f"📡 XL hasn't answered since FCC restarted; it was printing '{NASTY_ESC}' (~30%) "
                     "when FCC last saw it.", "WARNING")]
    _tick(monkeypatch, logs, None, None, None)              # still silent: said already
    assert len(logs) == 1
    _tick(monkeypatch, logs, _p("PRINTING", progress=0.5))
    assert logs[1][0].startswith("📡 XL is back after") and logs[1][0].endswith("(PRINTING, ~50%)."), logs


def test_restart_recovery_says_nothing_without_an_ip(monkeypatch, logs):
    entry = {"state": "PRINTING", "job_id": 7, "filename": NASTY, "progress": 0.3}
    monkeypatch.setattr(prusalink_api, "get_printer_state",
                        lambda fb, name: prusalink_api._note_probe_failure(name, "no_ip"))
    print_monitor._recover_one_print_latch("XL", entry, "http://fb")
    assert logs == []


@pytest.mark.parametrize("secs,words", [(40, "40 s"), (720, "12 min"), (9480, "2 h 38 min"),
                                        (7200, "2 h"), (3 * 86400 + 4 * 3600, "3 days 4 h"),
                                        (3 * 86400, "3 days")])
def test_how_long(secs, words):
    assert print_monitor._how_long(secs) == words


# --------------------------------------------------------------------------- #
# Why a probe failed                                                           #
# --------------------------------------------------------------------------- #

class _R:
    def __init__(self, status, body=None):
        self.status_code, self.ok, self._body = status, 200 <= status < 300, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.mark.parametrize("raise_or_answers,why", [
    (requests.exceptions.ConnectTimeout("timed out"), "timeout"),
    (requests.exceptions.ConnectionError("[Errno 111] Connection refused"), "refused"),
    (requests.exceptions.ConnectionError("[Errno 113] No route to host"), "no_route"),
    (requests.exceptions.ConnectionError("Max retries exceeded"), "connection"),
    ([_R(404), _R(404)], "http 404"),
    ([_R(200, ValueError("not json")), _R(500)], "http 500"),
    # Group 65 fix review 2 (WA4): answers that aren't JSON, and don't say they are, are no
    # PrusaLink's.
    ([_R(200, ValueError("not json")), _R(200, ValueError("not json"))], "not_prusalink"),
])
def test_a_failed_probe_says_why_and_still_answers_none(raise_or_answers, why):
    answers = list(raise_or_answers) if isinstance(raise_or_answers, list) else None

    def get(url, **k):
        if answers is None:
            raise raise_or_answers
        return answers.pop(0)
    with patch.object(prusalink_api, "fetch_printer_credentials",
                      return_value={"ip_address": "10.0.0.9", "api_key": "k"}), \
         patch.object(prusalink_api.requests, "get", side_effect=get):
        assert prusalink_api._probe_printer_state("fb", "XL") is None
    assert prusalink_api.last_probe_failure("XL") == why


def test_no_ip_saved_is_its_own_reason_and_an_answer_clears_it():
    with patch.object(prusalink_api, "fetch_printer_credentials", return_value={"ip_address": ""}):
        assert prusalink_api._probe_printer_state("fb", "XL") is None
    assert prusalink_api.last_probe_failure("XL") == "no_ip"
    with patch.object(prusalink_api, "fetch_printer_credentials",
                      return_value={"ip_address": "10.0.0.9", "api_key": "k"}), \
         patch.object(prusalink_api.requests, "get", return_value=_R(200, {"printer": {"state": "IDLE"}})):
        assert prusalink_api._probe_printer_state("fb", "XL") == {"state": "IDLE", "is_active": False}
    assert prusalink_api.last_probe_failure("XL") is None
