"""Group 65 fix review, round 4: what the print watch says, and one print it took for
another. Offline.

  - WY4 / AY3: restart recovery at an idle screen asks what FCC holds first: a queued
    completion opens no review, and no line says one opens or names a next print.
  - WY5: a queued completion recovered at another print's finished screen isn't said as a
    completion "missed ... printer still FINISHED".
  - WY8: a park job change found after a restart says FCC restarted, not that it lost sight
    of the printer.
  - AY1: a print with no job id never takes an earlier id-less print's queued completion for
    its own: its end opens its review.
  - Fix review 3's known gap: a job change of a print FCC queued as finished says nothing of
    reviewing it (the queue's line says what happens).
  - AY2: a job change whose end read FCC couldn't use is still said as a print another print
    replaced, never one that "reached idle".

Red on cbfea058 (fix review 3's fixes).
"""
from __future__ import annotations

import app as app_module  # noqa: F401  (the route modules, as the monitor imports them)
import cancel_fetch_store
import print_deduct
import print_monitor
import prusalink_api
from test_cancel_review import _cancelled_gcode, _preview_ctx
from test_lost_contact_65_1 import _iso, _latch, _printing, clock, dispatched  # noqa: F401
from test_print_watch_65_r1 import _contact, _job, words  # noqa: F401
from test_review_rework_65_r1 import SPOOLS, TWO, _start, _stop


def _queued_complete(job="7", filename="/usb/A.BGC"):
    cancel_fetch_store.add_pending({"printer_name": "XL", "job_id": job, "filename": filename,
                                    "kind": "complete", "end_heads": {"heads": [], "source": "print_end"}})


def test_restart_at_an_idle_screen_leaves_a_queued_completion_to_the_queue(monkeypatch, clock, words):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    made = []
    monkeypatch.setattr(print_deduct, "_create_pending_cancel_review", lambda *a, **k: made.append(a))
    _queued_complete()
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": "IDLE"})
    monkeypatch.setattr(prusalink_api, "get_printer_job", lambda fb, name: None)
    print_monitor._recover_one_print_latch(
        "XL", {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.97, "seen_at": 900.0}, "fb")
    assert made == [], made
    assert not any("surfacing a review" in w for w in words), words
    assert not any("next print" in w for w in words), words
    assert any("records its deduct once the printer is idle" in w for w in words), words
    assert (cancel_fetch_store.get_pending("XL", "7") or {}).get("kind") == "complete"


def test_a_queued_completion_at_another_prints_finish_isnt_said_as_missed(monkeypatch, clock, words):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    sent = []
    monkeypatch.setattr(print_monitor, "_dispatch_completion_edge", lambda *a, **k: sent.append((a, k)))
    _queued_complete()
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": "FINISHED"})
    monkeypatch.setattr(prusalink_api, "get_printer_job",
                        lambda fb, name: {"job_id": 8, "filename": "/usb/B.BGC", "progress": 1.0})
    print_monitor._recover_one_print_latch(
        "XL", {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.97, "seen_at": 900.0}, "fb")
    assert len(sent) == 1, sent                       # the queued deduct goes on
    assert not any("missed during an FCC restart" in w for w in words), words
    assert any("FCC saw '/usb/A.BGC' finish before it restarted" in w for w in words), words


def test_a_park_job_change_after_a_restart_says_fcc_restarted(monkeypatch, clock, words, dispatched):
    monkeypatch.setattr(print_monitor, "_capture_end_heads", lambda *a, **k: None)
    monkeypatch.setattr(prusalink_api, "get_printer_state", lambda fb, name: {"state": "ATTENTION"})
    _job(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 0.2})
    print_monitor._recover_one_print_latch(
        "XL", {"state": "PRINTING", "job_id": 7, "filename": "/usb/A.BGC", "progress": 0.97, "seen_at": 900.0}, "fb")
    assert print_monitor._PRINT_TRACKER["XL"].get("lost_why") == "restart"
    print_monitor._track_print_edge("XL", {"state": "ATTENTION"}, "fb")
    said = [w for w in words if "print job changed" in w]
    assert said and "after it restarted" in said[0] and "losing sight" not in said[0], words


def test_an_id_less_print_never_takes_an_earlier_id_less_prints_queued_completion(monkeypatch, words):
    made = []
    monkeypatch.setattr(print_deduct, "_create_pending_cancel_review",
                        lambda *a, **k: made.append(a) or {"status": "pending"})
    print_deduct._enqueue_cancel_fetch("XL", "/usb/A.BGC", None, 1.0, kind="complete")
    del words[:]
    print_monitor._on_ambiguous_edge("XL", "/usb/B.BGC", None, 0.5, "fb")
    assert [a[1] for a in made] == ["/usb/B.BGC"], made
    assert not any("already queued" in w for w in words), words


def test_a_job_change_of_a_print_fcc_queued_as_finished_claims_no_review(monkeypatch, clock, words):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    made = []
    monkeypatch.setattr(print_deduct, "_create_pending_cancel_review", lambda *a, **k: made.append(a))
    _queued_complete(filename="/usb/A.BGC")
    _latch()
    print_monitor._track_print_edge("XL", _printing(monkeypatch, job_id=8, progress=0.02), "fb")
    assert made == [], made
    changed = [w for w in words if "print job changed" in w]
    assert changed and not any("reviewing the previous job" in w for w in words), words
    assert any("FCC had already queued '/usb/A.BGC' as finished" in w for w in words), words


def test_a_park_job_change_of_a_print_fcc_queued_as_finished_claims_no_review(monkeypatch, clock, words):
    monkeypatch.setattr(print_monitor, "_fcc_owns_completion_deduct", lambda: True)
    monkeypatch.setattr(print_monitor, "_capture_end_heads", lambda *a, **k: None)
    made = []
    monkeypatch.setattr(print_deduct, "_create_pending_cancel_review", lambda *a, **k: made.append(a))
    _queued_complete(filename="/usb/A.BGC")
    _latch()
    _job(monkeypatch, {"job_id": 8, "filename": "/usb/B.BGC", "progress": 0.8})
    print_monitor._track_print_edge("XL", {"state": "ATTENTION"}, "fb")
    assert made == [], made
    assert any("print job changed" in w for w in words), words
    assert not any("reviewing the previous job" in w for w in words), words


def test_a_job_change_whose_end_read_failed_is_said_as_a_print_another_replaced(monkeypatch, words):
    gcode, cut = _cancelled_gcode()
    ctx = _preview_ctx(gcode, TWO, SPOOLS, {"XL-1": [100], "XL-2": [200]}, {"updates": []})
    _start(ctx)
    try:
        monkeypatch.setattr(print_monitor, "_capture_end_heads", lambda *a, **k: None)
        print_monitor._on_ambiguous_edge("XL", "/usb/A.BGC", 7, cut, "fb", heads_when="job_change")
    finally:
        _stop(ctx)
    review = [w for w in words if "couldn't confirm cancel vs complete" in w]
    assert review and all("moved on to another print" in w for w in review), words
    assert not any("reached idle" in w for w in words), words


def test_the_queued_check_is_for_the_same_file_and_never_a_blank_id():
    _queued_complete(filename="/usb/A.BGC")
    assert print_monitor._queued_completion("XL", "7", "/usb/A.BGC")
    assert not print_monitor._queued_completion("XL", "7", "/usb/OTHER.BGC")
    assert not print_monitor._queued_completion("XL", None)
