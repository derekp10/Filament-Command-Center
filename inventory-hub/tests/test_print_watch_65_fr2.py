"""Group 65 fix review, round 2: the print watch. Offline.

  - AV2 (orange): restart recovery at a finished screen asks what FCC already holds for the
    print first: a completion it queued goes on as that completion whatever the job read
    says, and a ledger entry, a waiting review or a charge begun is said, nothing more
    dispatched.
  - WA1: a latch restored at a prompt (or any state that isn't an end) is stamped as lost
    across the restart, so the live edge reads which print a park is.
  - WA2: a short blip at the PAUSED state of the same park keeps the park's read.
  - WA6: a latched print another print replaced after lost contact is said as that, never
    as "reached idle".
  - WA4: a 2xx answer FCC can't read that says it is JSON is PrusaLink answering badly
    ("unreadable", pinged); one that doesn't is another device ("not_prusalink").

Red on 2363aba3 (the second fix review's head), all but one guard, green there too:
an answer that says it is JSON (the [application/json-unreadable] case).
"""
from __future__ import annotations

import pytest

import app as app_module  # noqa: F401  (the route modules, as the monitor imports them)
import cancel_fetch_store
import print_deduct_ledger
import print_monitor
import prusalink_api
from test_lost_contact_65_1 import _iso, _latch, _miss, clock, dispatched  # noqa: F401
from test_print_watch_65_r1 import PARK, _contact, _job, completions, words  # noqa: F401

LATCHED = {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.97, "seen_at": 900.0}


@pytest.fixture
def finished(monkeypatch):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": "FINISHED"})


def test_a_completion_fcc_queued_before_the_restart_is_charged_whatever_the_job_read_says(
        monkeypatch, clock, dispatched, completions, words, finished):
    cancel_fetch_store.add_pending({"printer_name": "XL", "job_id": "7", "filename": "/usb/A.BGC",
                                    "kind": "complete", "end_heads": {"heads": [], "source": "print_end"}})
    _job(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 1.0})
    assert print_monitor._recover_one_print_latch("XL", dict(LATCHED), "fb") is True
    assert dispatched == [] and [a[2] for a, _k in completions] == [7], (dispatched, completions)


def test_a_print_fcc_already_charged_is_said_and_nothing_more_is_dispatched(monkeypatch, clock, dispatched,
                                                                            completions, words, finished):
    print_deduct_ledger.record_deduct("XL", "7", filename="/usb/A.BGC", scale=1.0, grams=20.0)
    _job(monkeypatch, None)
    assert print_monitor._recover_one_print_latch("XL", dict(LATCHED), "fb") is True
    assert dispatched == [] and completions == [], (dispatched, completions)
    assert words == ["⚠️ XL: a print ('/usb/A.BGC', ~97%) was in progress when FCC restarted, and the printer is "
                     "on its finished screen. FCC had already recorded its deduct."], words


def test_a_latch_restored_at_a_prompt_is_lost_across_the_restart(monkeypatch, clock):
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": "ATTENTION"})
    assert print_monitor._recover_one_print_latch("XL", dict(LATCHED, state="ATTENTION"), "fb") is True
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert (entry["misses"], entry["lost_at"], entry["lost_why"]) == (3, 900.0, "restart"), entry


def test_a_short_blip_at_the_paused_state_of_the_same_park_keeps_its_read(monkeypatch, clock):
    _latch(state="ATTENTION", park_heads=dict(PARK), park_read=True)
    _miss(3, clock)
    _job(monkeypatch, {"job_id": 7, "filename": "/usb/A.BGC", "progress": 0.31})
    print_monitor._track_print_edge("XL", {"state": "PAUSED", "is_active": False}, "fb")
    entry = print_monitor._PRINT_TRACKER["XL"]
    assert entry.get("park_heads") == PARK and "misses" not in entry, entry


def test_a_print_another_print_replaced_after_lost_contact_is_said_as_that(monkeypatch, words):
    monkeypatch.setattr(print_monitor, "_claim_edge", lambda *a, **k: (False, None))
    print_monitor._on_ambiguous_edge(
        "XL", "/usb/A.BGC", 7, 0.3, "fb",
        lost_contact={"progress": 0.3, "seen_at": 900.0, "lost_at": 910.0, "back_at": 9000.0,
                      "back_state": "PRINTING", "why": "lost"})
    assert words[0].startswith("❓ XL moved on to another print, so FCC can't tell how '/usb/A.BGC' ended (~30%) "
                               "— FCC lost contact at ~30%"), words


class _R:
    def __init__(self, status, body=None, ctype=""):
        self.status_code, self.ok, self._body = status, 200 <= status < 300, body
        self.headers = {"Content-Type": ctype} if ctype else {}

    def json(self):
        if isinstance(self._body, BaseException):
            raise self._body
        return self._body


@pytest.mark.parametrize("ctype,why", [("application/json", "unreadable"), ("text/html", "not_prusalink")])
def test_an_answer_fcc_cant_read_is_prusalink_answering_badly_only_when_it_says_json(monkeypatch, ctype, why):
    monkeypatch.setattr(prusalink_api, "fetch_printer_credentials",
                        lambda fb, name: {"ip_address": "10.0.0.9", "api_key": "k"})
    answers = [_R(200, ValueError("not json"), ctype), _R(200, ValueError("not json"), ctype)]
    monkeypatch.setattr(prusalink_api.requests, "get", lambda *a, **k: answers.pop(0))
    assert prusalink_api.get_printer_state("http://fb", "XL") is None
    assert prusalink_api.last_probe_failure("XL") == why
