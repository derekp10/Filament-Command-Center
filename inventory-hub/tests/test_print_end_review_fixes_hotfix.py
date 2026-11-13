"""Hotfix 2026-11-11, the review's findings on the print-end deduct.

Three reviewers (the money path, what a person reads, the proofs) read scopes A to
D of the hotfix. The backend findings this file pins, each on the real edge,
deduct, review and confirm code over the wire harness of
test_print_end_heads_hotfix.py (only the download and walk are stubbed):

  - a completion whose split at a recorded swap names a spool that also has a
    plain row on the card (one spool feeding two heads) gave the card two rows of
    one spool; the confirm keys rows by spool, so one row's grams were lost and a
    false uncharged-grams card opened. The split is refused there, as the cancel's
    is (_accept_splits): with the print-end read the head is a set to split by
    hand, without it the head gets the review's plain rows;
  - the apply without a print-end read read Spoolman's error body as the spool
    (get_spool returns the body whatever the status) and wrote the print's grams
    as the spool's whole used weight;
  - a print-end read that found no spool on any head (a Spoolman blip) was stored
    on the print's record and, as the first read, beat a later usable one;
  - after a restart, a queued print's retry at IDLE logged the "clear the cancel
    screen" nudge;
  - restart recovery's "a different job is printing now" line said a print was
    "not auto-deducted, weigh the spool" while its queued record would still be
    charged;
  - two deducts of one spool on two threads (scope C runs each retry on its own
    thread) read the same used weight, and one charge was lost;
  - guards no test reached: the split's refusals when the print-end read finds the
    swapped head empty or holding two spools, _accept_splits' one-row-per-spool
    rule, and the completion apply over a spool Spoolman no longer has.

HEAD proof: each test's comment gives its failure line on d213cf7 (the branch
before these fixes); the guard tests pass there by design (they pin code that
already works, so a later change can't drop it unseen).
"""
from __future__ import annotations

import copy
import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import print_monitor  # noqa: E402
import print_tracker_store  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman  # noqa: E402
from test_print_end_heads_hotfix import (  # noqa: E402
    FILE, INDX, JOB, USAGE, Indx, _compute, _job, _rec, _rows, _spool, _tick)


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
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct.config_loader, "load_config", lambda: {})
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()
    yield
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER.clear()


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append(msg))
    return calls


def _measured(usage, cums):
    """The download and walk, measuring the swap points it is asked for in the same
    pass, as the real one does: `cums` is {swap point: {tool: grams}}."""
    def _run(*a, **k):
        out = k.get("cums_out")
        if out is not None:
            out.update({p: dict(c) for p, c in cums.items() if p in (k.get("swap_points") or [])})
        return dict(usage), None
    return patch.object(print_deduct, "_compute_cancel_usage", side_effect=_run)


def _confirm(body):
    return app_module.app.test_client().post(
        "/api/cancel_deduct/confirm", json=dict({"printer_name": INDX, "job_id": str(JOB)}, **body)).get_json()


# --------------------------------------------------------------------------- #
# A completion split whose spool also has a plain row on the card              #
# --------------------------------------------------------------------------- #

def _shared_230(p):
    """#230 feeds RCOI-4 (T3) and RCOI-5 (T4), a shared-spool setup FCC supports;
    at a pause halfway through, RCOI-5 got #229 and FCC recorded the swap."""
    p.sm.spools[230] = _spool(100.0, "RCOI-4")
    p.at["RCOI-4"] = [230]
    p.at["RCOI-5"] = [229]
    p.sm.spools[229]["location"] = "RCOI-5"
    start = {"3": 230, "4": 230}
    swap_log = [{"seq": 0, "position": 4, "progress": 0.5, "from_sid": 230, "to_sid": 229,
                 "runout": False}]
    return start, swap_log


def test_a_completion_split_whose_spool_has_a_plain_row_is_a_set_to_split_by_hand(logs):
    # On d213cf7: AssertionError: assert [229, 230, 230] == [230] (two rows of #230:
    # the confirm keys rows by spool, so one row's grams were lost).
    with Indx() as p:
        start, swap_log = _shared_230(p)
        heads = print_deduct._capture_print_heads(INDX, "http://fb")
        with _measured({3: 20.0, 4: 40.0}, {0.5: {4: 15.0}}):
            out = print_deduct.deduct_completed_print(
                INDX, FILE, JOB, fb_url="http://fb", start_spools=start, swap_log=swap_log,
                end_heads={"heads": heads, "source": "print_end", "at": "now"})
        assert out["status"] == "pending_spool_changed", out
        rec = _rec()
        sids = [r["sid"] for r in rec["spools"]]
        assert sorted(sids) == [230], rec["spools"]          # one row per spool
        assert _rows(rec) == [(230, "RCOI-4", 20.0)]
        # T4 is asked about: both spools it had, nothing pre-filled, and why.
        assert rec["unresolved_usage"] == {"4": 40.0}
        assert [(e["sid"], e["when"]) for e in rec["unresolved_sets"]["4"]] == [(230, "start"), (229, "during")]
        assert "#230 also printed on another head" in rec["unresolved_notes"]["4"], rec["unresolved_notes"]
        assert rec["auto_split"] is False
        # The page's Apply with the set split by hand: #230 takes its row and its share.
        body = _confirm({"charges": [{"row": 230, "sid": 230, "grams": 20.0},
                                     {"position": 4, "sid": 230, "grams": 15.0},
                                     {"position": 4, "sid": 229, "grams": 25.0}]})
        assert body["status"] == "confirmed", body
        assert p.sm.used(230) == pytest.approx(135.0) and p.sm.used(229) == pytest.approx(35.0)
    assert body["shortfall_g"] == pytest.approx(0.0)
    assert cancel_review_store.get_pending(INDX, f"{JOB}#shortfall") is None


def test_a_completion_card_applied_as_shown_reports_the_sets_grams_and_opens_no_false_card(logs):
    # On d213cf7: AssertionError: ... 35.0 == 10.0 (the card's #229 split row was
    # charged as shown, and its two #230 rows were charged once).
    with Indx() as p:
        start, swap_log = _shared_230(p)
        heads = print_deduct._capture_print_heads(INDX, "http://fb")
        with _measured({3: 20.0, 4: 40.0}, {0.5: {4: 15.0}}):
            print_deduct.deduct_completed_print(
                INDX, FILE, JOB, fb_url="http://fb", start_spools=start, swap_log=swap_log,
                end_heads={"heads": heads, "source": "print_end", "at": "now"})
        rec = _rec()
        updates = {str(r["sid"]): r["grams"] for r in rec["spools"]}     # the page's `updates`
        body = _confirm({"updates": updates})
        assert body["status"] == "confirmed", body
        assert p.sm.used(230) == pytest.approx(120.0) and p.sm.used(229) == pytest.approx(10.0)
    # T4's 40 g were placed on no spool: reported as the job's shortfall, never lost.
    assert body["shortfall_g"] == pytest.approx(40.0), body
    assert cancel_review_store.get_pending(INDX, f"{JOB}#shortfall") is None


def test_without_the_print_end_read_a_shared_spools_split_falls_back_to_plain_rows(logs):
    """No print-end read (a record queued before the hotfix, or a failed read): the
    head whose split names a spool with another row gets the review's plain rows,
    so every spool has one row."""
    # On d213cf7: AssertionError: assert [229, 230, 230] == [229, 230]
    with Indx() as p:
        start, swap_log = _shared_230(p)
        with _measured({3: 20.0, 4: 40.0}, {0.5: {4: 15.0}}):
            out = print_deduct.deduct_completed_print(
                INDX, FILE, JOB, fb_url="http://fb", start_spools=start, swap_log=swap_log)
        assert out["status"] == "pending_spool_changed", out
        rec = _rec()
    assert sorted(r["sid"] for r in rec["spools"]) == [229, 230]
    assert sum(r["grams"] for r in rec["spools"]) == pytest.approx(60.0)
    assert rec["auto_split"] is False


# --------------------------------------------------------------------------- #
# The apply without a print-end read, over Spoolman's error body               #
# --------------------------------------------------------------------------- #

def test_the_apply_never_reads_spoolmans_error_body_as_the_spool(logs):
    # On d213cf7: AssertionError: assert 12.5 == 700.0 (the 500 body read as the
    # spool: used_weight 0, so #42's 700 g used was overwritten with 12.5 g).
    sm = WeightWireSpoolman({42: _spool(700.0, "XL-1")})
    locked = {"n": 0}

    def _get(url, *a, **k):
        tail = str(url).split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if tail == "42" and locked["n"] < 2:          # the apply's read, and update_spool's own
            locked["n"] += 1
            body = {"message": "database is locked"}
            return MagicMock(ok=False, status_code=500, json=MagicMock(return_value=body))
        return sm._get(url, *a, **k)
    active = [("XL-1", {"position": 0, "printer_name": "XL"})]
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}), \
            patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active), \
            patch.object(spoolman_api, "get_spools_at_location", return_value=[42]), \
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}), \
            patch.object(spoolman_api.requests, "get", side_effect=_get), \
            patch.object(spoolman_api.requests, "patch", side_effect=sm._patch):
        n, details, _known = print_deduct._apply_usage_to_printer("XL", {0: 12.5}, "http://fb")
    assert sm.used(42) == 700.0
    assert sm.patches == [] and n == 0 and details == []


def test_a_completion_over_a_spool_spoolman_no_longer_has_writes_nothing_to_it(logs):
    """The print-end read names #999 on RCOI-5, and Spoolman answers 404 for it now:
    nothing is written to it, and its grams wait on the uncharged-grams card."""
    # Passes on d213cf7 by design (pins _spool_read on the apply's print-end branch).
    with Indx() as p, _compute({4: 50.0, 6: 20.0}):
        p.at["RCOI-5"] = [999]
        _tick("PRINTING", _job(0.5))
        _tick("FINISHED")
        assert all(sid != 999 for sid, _ in p.sm.patches), p.sm.patches
        assert p.sm.used(243) == pytest.approx(720.0)
    card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
    assert card is not None and card["unresolved_usage"] == {"4": 50.0}, card
    assert not card.get("spools"), card


# --------------------------------------------------------------------------- #
# A print-end read that found no spool on any head                             #
# --------------------------------------------------------------------------- #

_EMPTY = [{"toolhead": "XL-1", "position": 0, "sid": None, "sids": []},
          {"toolhead": "XL-2", "position": 1, "sid": None, "sids": []}]
_GOOD = [{"toolhead": "XL-1", "position": 0, "sid": 100, "sids": [100]},
         {"toolhead": "XL-2", "position": 1, "sid": None, "sids": []}]


def test_a_print_end_read_that_found_no_spool_on_any_head_is_no_read():
    # On d213cf7: AssertionError: assert {'at': ..., 'heads': [...], 'source': 'print_end'} is None
    with patch.object(print_deduct, "_capture_print_heads", return_value=copy.deepcopy(_EMPTY)):
        assert print_monitor._capture_end_heads("XL", 7, "http://fb") is None


def test_a_stored_read_that_found_no_spool_gives_way_to_a_later_usable_one(logs):
    """A record an older process wrote with such a read (or a damaged one): a later
    usable read (restart recovery's) is stored and computed with."""
    # On d213cf7: AssertionError: assert {... 'source': 'print_end'} == {... 'source': 'restart'}
    # (the stored read stayed the empty one).
    blip = {"heads": copy.deepcopy(_EMPTY), "source": "print_end", "at": "2026-11-11 10:00:00"}
    good = {"heads": copy.deepcopy(_GOOD), "source": "restart", "at": "2026-11-11 10:05:00"}
    rec = print_monitor._hold_edge_fetch("XL", "x.gcode", 7, 0.4, "cancel", end_heads=blip)
    assert rec["end_heads"] == blip
    _rec2, _s, _w, used = print_monitor._hold_end_heads(rec, "XL", "x.gcode", 7, 0.4, "cancel", False,
                                                        None, None, good)
    assert cancel_fetch_store.get_pending("XL", "7")["end_heads"] == good
    assert used == good
    # A re-queue keeps the usable read, and replaces an unusable one too.
    print_deduct._enqueue_cancel_fetch("XL", "x.gcode", 7, 0.4, end_heads=blip)
    assert cancel_fetch_store.get_pending("XL", "7")["end_heads"] == good
    cancel_fetch_store.pop_pending("XL", "7")
    print_deduct._enqueue_cancel_fetch("XL", "x.gcode", 7, 0.4, end_heads=blip)
    print_deduct._enqueue_cancel_fetch("XL", "x.gcode", 7, 0.4, end_heads=good)
    assert cancel_fetch_store.get_pending("XL", "7")["end_heads"] == good


def test_a_blip_at_the_finish_and_a_good_read_at_the_restart_charge_the_spool_that_printed(logs):
    """Spoolman is down when the INDX finishes (every head reads empty), the finish
    screen locks the file, FCC restarts before the reset latch was saved and reads
    the heads again (#42 on RCOI-5). Later #229 goes on RCOI-5 and the queue
    retries: #42 is charged, never #229."""
    # On d213cf7: AssertionError: assert 'print_end' == 'restart' (the empty read was
    # kept; the retry then charged #229 50 g and #42 nothing).
    with Indx() as p, patch.object(print_deduct, "_snapshot_active_spools", return_value={}):
        _tick("PRINTING", _job(0.5))
        latch = copy.deepcopy(print_monitor._PRINT_TRACKER[INDX])
        p.blip = True
        with _compute({4: 50.0}, error=True):
            _tick("FINISHED")
        p.blip = False
        print_monitor._FETCH_CLAIMS.clear()
        with patch.object(print_tracker_store, "load", return_value={INDX: latch}), \
                patch.object(print_monitor.prusalink_api, "get_printer_state",
                             return_value={"state": "FINISHED"}), \
                _compute({4: 50.0}, error=True):
            print_monitor._recover_print_tracker_on_start()
        stored = cancel_fetch_store.get_pending(INDX, str(JOB))["end_heads"]
        assert stored["source"] == "restart"
        p.load_229()
        with _compute({4: 50.0}):
            print_monitor._process_pending_cancel_fetches({INDX: {"state": "IDLE"}}, "http://fb")
        assert (p.sm.used(42), p.sm.used(229)) == (pytest.approx(750.0), pytest.approx(10.0))


# --------------------------------------------------------------------------- #
# The queue after a restart                                                    #
# --------------------------------------------------------------------------- #

class _Died(BaseException):
    """FCC stopping mid-download: nothing after it in that thread runs."""


def test_a_queued_retry_after_a_restart_never_says_the_screen_is_still_up(logs):
    """The live edge's download died with FCC, leaving its record "in_flight". The
    queue retries it only at IDLE / READY, where the screen is clear, so a failed
    retry there never logs the "clear the cancel screen" nudge."""
    # On d213cf7: AssertionError: assert not ["🛑 Cancelled print on ... the printer is still
    # showing the cancel screen, so the gcode is locked. Clear it on the printer ..."]
    calls = {"n": 0}

    def _download(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _Died()
        return None, {"status": "error", "reason": "download_failed", "job_id": str(JOB)}
    with Indx(), patch.object(print_deduct, "_compute_cancel_usage", side_effect=_download):
        _tick("PRINTING", _job(0.42))
        with pytest.raises(_Died):
            _tick("STOPPED")
        assert cancel_fetch_store.get_pending(INDX, str(JOB))["last_status"] == "in_flight"
        print_monitor._FETCH_CLAIMS.clear()                 # the restart
        print_monitor._process_pending_cancel_fetches({INDX: {"state": "IDLE"}}, "http://fb")
        rec = cancel_fetch_store.get_pending(INDX, str(JOB))
    assert rec is not None and rec["last_status"] == "awaiting_fetch", rec
    assert not [m for m in logs if "still showing the" in m], logs


def test_restart_recovery_says_a_queued_print_will_still_be_computed(logs):
    """The finish screen locked job 1141's file, so its record is queued; FCC
    restarts before the reset latch was saved, and the next job is printing. The
    line says the queue will finish it, never "not auto-deducted, weigh the spool"
    (the queue charges it once the printer is idle)."""
    # On d213cf7: AssertionError: assert ('not auto-deducted' not in '⚠️ ... its outcome is
    # unknown, not auto-deducted. Weigh the spool if that print was cancelled.')
    with Indx() as p, patch.object(print_deduct, "_snapshot_active_spools", return_value={}):
        _tick("PRINTING", _job(0.5))
        latch = copy.deepcopy(print_monitor._PRINT_TRACKER[INDX])
        with _compute({4: 50.0}, error=True):
            _tick("FINISHED")
        assert cancel_fetch_store.has_pending(INDX, str(JOB))
        print_monitor._FETCH_CLAIMS.clear()
        with patch.object(print_tracker_store, "load", return_value={INDX: latch}), \
                patch.object(print_monitor.prusalink_api, "get_printer_state",
                             return_value={"state": "PRINTING"}), \
                patch.object(print_monitor.prusalink_api, "get_printer_job",
                             return_value=_job(0.1, job_id=1142, filename="/usb/NEXT.BGC")):
            print_monitor._recover_print_tracker_on_start()
        said = [m for m in logs if "different job is printing now" in m]
        assert len(said) == 1, logs
        assert "not auto-deducted" not in said[0] and "Weigh the spool" not in said[0], said
        assert "records its deduct once the printer is idle" in said[0], said
        with _compute({4: 50.0}):
            print_monitor._process_pending_cancel_fetches({INDX: {"state": "IDLE"}}, "http://fb")
        assert p.sm.used(42) == pytest.approx(750.0)


def test_restart_recovery_with_nothing_queued_still_says_to_weigh(logs):
    # Passes on d213cf7 by design: with nothing queued the line is main's.
    with Indx(), patch.object(print_deduct, "_snapshot_active_spools", return_value={}):
        _tick("PRINTING", _job(0.5))
        latch = copy.deepcopy(print_monitor._PRINT_TRACKER[INDX])
        with patch.object(print_tracker_store, "load", return_value={INDX: latch}), \
                patch.object(print_monitor.prusalink_api, "get_printer_state",
                             return_value={"state": "PRINTING"}), \
                patch.object(print_monitor.prusalink_api, "get_printer_job",
                             return_value=_job(0.1, job_id=1142, filename="/usb/NEXT.BGC")):
            print_monitor._recover_print_tracker_on_start()
    said = [m for m in logs if "different job is printing now" in m]
    assert len(said) == 1 and "not auto-deducted" in said[0], logs


# --------------------------------------------------------------------------- #
# Two deducts of one spool on two threads                                      #
# --------------------------------------------------------------------------- #

def _racing_reads(sm, sid):
    """requests.get for the wire harness that holds the FIRST read of `sid` open
    (its answer already taken) for up to half a second, so a second thread's read of
    it comes in meanwhile and reads the same weight, unless something keeps it out."""
    count = {"n": 0}
    guard = threading.Lock()
    second = threading.Event()

    def _get(url, *a, **k):
        answer = sm._get(url, *a, **k)
        tail = str(url).split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if tail == str(sid):
            with guard:
                count["n"] += 1
                n = count["n"]
            if n == 1:
                second.wait(0.5)
            else:
                second.set()
        return answer
    return _get


def test_two_deducts_of_one_spool_on_two_threads_both_land(logs):
    # On d213cf7: AssertionError: assert 750.0 == 770.0 ± 7.7e-04 (both read 700 g
    # used, and the later write replaced the earlier one).
    sm = WeightWireSpoolman({42: _spool(700.0, "XL-1")})
    heads_a = [{"toolhead": "RCOI-5", "position": 4, "sid": 42, "sids": [42]}]
    heads_b = [{"toolhead": "XL-1", "position": 0, "sid": 42, "sids": [42]}]
    with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}), \
            patch.object(spoolman_api.requests, "get", side_effect=_racing_reads(sm, 42)), \
            patch.object(spoolman_api.requests, "patch", side_effect=sm._patch):
        ta = threading.Thread(target=print_deduct._apply_usage_to_printer,
                              args=(INDX, {4: 50.0}, "http://fb"), kwargs={"heads": heads_a})
        tb = threading.Thread(target=print_deduct._apply_usage_to_printer,
                              args=("XL", {0: 20.0}, "http://fb"), kwargs={"heads": heads_b})
        ta.start()
        tb.start()
        ta.join(10)
        tb.join(10)
    assert sm.used(42) == pytest.approx(770.0), sm.patches


def test_a_review_apply_and_a_deduct_of_one_spool_both_land(logs):
    # On d213cf7: AssertionError: assert 720.0 == 770.0 ± 7.7e-04 (or 750.0)
    sm = WeightWireSpoolman({42: _spool(700.0, "XL-1")})
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "9", "filename": "x.gcode", "progress": 0.4,
        "total_grams": 50.0, "ambiguous": False, "created": "now",
        "spools": [{"sid": 42, "toolhead": "XL-1", "position": 0, "grams": 50.0,
                    "remaining_before": 300.0, "remaining_after": 250.0,
                    "display": "#42", "color": "ff0000", "ambiguous": False}]})
    heads_b = [{"toolhead": "XL-1", "position": 0, "sid": 42, "sids": [42]}]
    out = {}

    def _apply_review():
        out["body"] = app_module.app.test_client().post(
            "/api/cancel_deduct/confirm",
            json={"printer_name": "XL", "job_id": "9", "updates": {"42": 50.0}}).get_json()
    with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}), \
            patch.object(spoolman_api.requests, "get", side_effect=_racing_reads(sm, 42)), \
            patch.object(spoolman_api.requests, "patch", side_effect=sm._patch):
        ta = threading.Thread(target=_apply_review)
        tb = threading.Thread(target=print_deduct._apply_usage_to_printer,
                              args=("XL", {0: 20.0}, "http://fb"), kwargs={"heads": heads_b})
        ta.start()
        tb.start()
        ta.join(10)
        tb.join(10)
    assert out["body"]["status"] == "confirmed", out
    assert sm.used(42) == pytest.approx(770.0), sm.patches


# --------------------------------------------------------------------------- #
# Guards no test reached                                                       #
# --------------------------------------------------------------------------- #

def _run_out_at_19(p):
    _tick("PRINTING", _job(0.10))
    _tick("ATTENTION", _job(0.19))
    p.load_229()
    _tick("PRINTING", _job(0.19))
    _tick("PRINTING", _job(0.42))


@pytest.mark.parametrize("at_end", [[], [229, 300]], ids=["empty", "two_spools"])
def test_a_swapped_head_empty_or_doubled_at_the_end_is_held_never_split(logs, at_end):
    # Passes on d213cf7 by design: with the 'end_empty' refusal gone the review raised
    # IndexError and was never stashed; with 'end_two' gone the head was split.
    with Indx() as p, _measured(USAGE, {0.19: {4: 30.0, 6: 25.0, 7: 7.0}}):
        _run_out_at_19(p)
        p.at["RCOI-5"] = list(at_end)          # what the print-end read finds on T4
        p.sm.spools.setdefault(300, _spool(10.0, "RCOI-5"))
        _tick("STOPPED")
    rec = _rec()
    assert rec is not None, logs
    assert rec["unresolved_usage"] == {"4": 84.28}, rec
    assert all(r["sid"] not in (42, 229, 300) for r in rec["spools"]), rec["spools"]
    note = rec["unresolved_notes"]["4"]
    assert ("no spool was on it when the print ended" in note if not at_end
            else "it had two spools when the print ended (#229 and #300)" in note), note


def test_a_cancel_split_whose_spool_has_another_row_stays_a_set():
    # On d213cf7: AssertionError: assert 'unmeasured' == 'shared' (the rule held, but its
    # note said FCC couldn't split the grams; it now says the spool printed elsewhere too).
    split = {4: [{"sid": 42, "grams": 30.0, "segment": 0, "runout": True, "from": None, "to": 0.19},
                 {"sid": 229, "grams": 54.0, "segment": 1, "runout": False, "from": 0.19, "to": 0.42}]}
    rows = [{"sid": 42, "toolhead": "RCOI-7", "position": 6, "grams": 75.0}]
    held = {4: {"why": "swapped", "toolhead": "RCOI-5", "sids": [229], "start": 42, "events": []}}
    heads = [{"toolhead": "RCOI-5", "position": 4, "sid": 229, "sids": [229]},
             {"toolhead": "RCOI-7", "position": 6, "sid": 42, "sids": [42]}]
    sm = WeightWireSpoolman({42: _spool(100.0, "RCOI-7"), 229: _spool(10.0, "RCOI-5")})
    with patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "fff"}), \
            patch.object(spoolman_api.requests, "get", side_effect=sm._get):
        out = print_deduct._accept_splits("P", "J", split, rows, held, heads)
    assert out == []
    assert held[4]["split"] == "shared" and held[4]["shared"] == [42]
