"""Hotfix 2026-11-11: a print's grams go to the spools that were on its heads
when it ended, read when FCC sees the end, before any download.

Prod job 1141 on the INDX was cancelled at 42%. FCC's cancel review downloads and
walks the whole file first (about 20 minutes at PrusaLink's ~15 KB/s) and only
then read which spool was on each head, live. Derek had loaded #229 on RCOI-5
three minutes after the cancel, so the card named #229 instead of #42, the spool
that printed. FCC had the right answer: the print-start snapshot and the
resume-time swap log, which only completions used.

Pinned here, on the real edge, deduct and review code over the wire harness
(tests/deduct_wire_harness.py; only the G-code compute is stubbed):
  - the print-end read (`print_deduct._capture_print_heads`, taken by
    `print_monitor._capture_end_heads` on the edge thread before the download)
    names the spools the cancel, ambiguous and completion cards and the
    completion's auto-apply use; it rides the deferred-fetch record (the first
    read wins on a re-queue), restart recovery (`restart`) and a job change
    (`job_change`);
  - a change AFTER the end is charged to the print-end spool and said: a
    completion logs one Activity Log line per such head, a card a note under the
    row (Derek's rule D1);
  - a change DURING the print always asks: the start snapshot (advanced by the
    swap log) against the print-end read, a recorded swap, two spools on one head
    or a spool FCC can't read holds that head for a pick, with every spool it had
    offered and a note saying why; a completion never auto-applies it;
  - without a print-end read, a cancel's start snapshot is checked against a read
    made then (`late`); with neither, every function runs main's code;
  - an Apply without picks on a no_spool card built from the read is refused.

HEAD proof: run on main 626a10e before the change, 29 of these 31 tests fail.
Job 1141's replay names #229: `(229, 'RCOI-5', 84.28) != (42, 'RCOI-5', 84.28)`;
its completion twin charges nothing to #42 (`700.0 == 750.0`); the rest fail on
the missing keys and keywords. The two marked "passes on main by design" pass.
"""
from __future__ import annotations

import copy
import os
import sys
import threading
import time
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
import prusalink_api  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop  # noqa: E402

INDX = "🦝 Core One INDX"
FILE = "/usb/SCP-04~4.BGC"
JOB = 1141
HEADS = tuple((f"RCOI-{i + 1}", i) for i in range(8))
ON_HEAD = {"RCOI-1": 72, "RCOI-2": 77, "RCOI-3": 71, "RCOI-4": 26,
           "RCOI-5": 42, "RCOI-6": 96, "RCOI-7": 243, "RCOI-8": 231}
USAGE = {4: 84.28, 6: 75.32, 7: 21.9}          # T4 RCOI-5, T6 RCOI-7, T7 RCOI-8
CREDS = {"ip_address": "1.2.3.4", "api_key": "k"}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_monitor, "_FETCH_CLAIMS", set())   # scope C: no claim outlives a test
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


@pytest.fixture
def hublog(monkeypatch):
    lines = []
    monkeypatch.setattr(state.logger, "info", lambda msg, *a, **k: lines.append(str(msg)))
    return lines


def _spool(used, loc):
    return {"used_weight": used, "initial_weight": 1000.0, "archived": False,
            "location": loc, "filament": {"weight": 1000.0}, "extra": {}}


class Indx:
    """The INDX's eight heads, with #229 waiting on a shelf. `at` is what
    Spoolman says is on each head (mutable: a test loads #229 on RCOI-5 mid-way)."""

    def __init__(self):
        spools = {sid: _spool(700.0, th) for th, sid in ON_HEAD.items()}
        spools[229] = _spool(10.0, "INBXX-1")
        self.sm = WeightWireSpoolman(spools)
        self.at = {th: [sid] for th, sid in ON_HEAD.items()}
        self.blip = False            # every head read answers [] (a Spoolman blip)
        self.reads = []              # every head read, in order

    def load_229(self):
        """What Derek did: #229 onto RCOI-5, #42 off to the cart."""
        self.at["RCOI-5"] = [229]
        self.sm.spools[42]["location"] = "CR-CT-2-R1"
        self.sm.spools[229]["location"] = "RCOI-5"

    def _at(self, loc):
        loc = str(loc).upper()
        self.reads.append(loc)
        return [] if self.blip else list(self.at.get(loc, []))

    def _targets(self, loc):
        sids = self._at(loc)
        return sids, len(sids) > 1

    def ctx(self):
        active = [(loc, {"position": pos, "printer_name": INDX}) for loc, pos in HEADS]
        return [
            patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}),
            patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
            patch.object(spoolman_api, "get_spools_at_location", side_effect=self._at),
            patch.object(spoolman_api, "select_deduct_targets", side_effect=self._targets),
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
            patch.object(spoolman_api.requests, "get", side_effect=self.sm._get),
            patch.object(spoolman_api.requests, "patch", side_effect=self.sm._patch),
            patch.object(print_deduct.prusalink_api, "fetch_printer_credentials", return_value=dict(CREDS)),
            patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=True),
        ]

    def __enter__(self):
        self._ctx = self.ctx()
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


def _job(progress=0.42, job_id=JOB, filename=FILE):
    return {"filename": filename, "job_id": job_id, "progress": progress}


def _tick(st, job=None):
    with patch.object(print_monitor.prusalink_api, "get_printer_job", return_value=job):
        print_monitor._track_print_edge(INDX, {"state": st}, "http://fb")


def _compute(usage, during=None, error=False):
    """A stand-in for the slow download and walk: `during` runs while it "downloads"
    (Derek loading #229), then the walk's answer."""
    def _run(*a, **k):
        if during:
            during()
        if error:
            return None, {"status": "error", "reason": "download_failed", "job_id": str(JOB)}
        return dict(usage), None
    return patch.object(print_deduct, "_compute_cancel_usage", side_effect=_run)


def _rec(job=JOB):
    return cancel_review_store.get_pending(INDX, str(job))


def _rows(rec):
    return [(r["sid"], r["toolhead"], r["grams"]) for r in rec.get("spools") or []]


def _offered(rec, pos):
    return {(h.get("sid"), h.get("when")) for h in rec.get("heads_at_end") or []
            if h.get("position") == pos}


# --------------------------------------------------------------------------- #
# Job 1141, replayed                                                           #
# --------------------------------------------------------------------------- #

def test_job_1141_review_names_the_spool_that_printed_not_the_one_loaded_during_the_download(logs):
    with Indx() as p, _compute(USAGE, during=p.load_229):
        _tick("PRINTING", _job(0.30))
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
    rec = _rec()
    assert rec is not None, logs
    assert _rows(rec) == [(42, "RCOI-5", 84.28), (243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    assert not rec.get("unresolved_usage"), rec
    assert rec["heads_source"] == "print_end"
    assert rec["heads_read_at"]
    end = {h["position"]: h["sid"] for h in rec["heads_at_end"] if not h.get("when")}
    assert end[4] == 42
    assert all(h.get("sid") != 229 for h in rec["heads_at_end"]), rec["heads_at_end"]
    # D1: the change after the end is said under the row it concerns.
    assert rec["row_notes"] == {"42": "#229 is on RCOI-5 now; #42 was on it when the print ended."}
    assert p.sm.patches == []
    assert any("181.50g across 3 spool(s)" in m for m in logs), logs


@pytest.mark.parametrize("end_state", ["STOPPED", "IDLE"])
def test_job_1141_a_load_inside_the_poll_window_is_held_for_a_pick(logs, end_state):
    with Indx() as p, _compute(USAGE):
        _tick("PRINTING", _job(0.30))
        _tick("PRINTING", _job(0.42))
        p.load_229()                            # before FCC saw the end
        _tick(end_state)
    rec = _rec()
    assert rec is not None, logs
    assert _rows(rec) == [(243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert (229, None) in _offered(rec, 4) and (42, "start") in _offered(rec, 4)
    assert rec["unresolved_notes"]["4"] == (
        "RCOI-5 had #42 when the print started and #229 when the print ended. Pick the spool it used.")
    assert rec["total_grams"] == pytest.approx(181.5)
    assert rec["ambiguous"] is (end_state == "IDLE")
    assert any("84.28g on T4 RCOI-5" in m and "pick it in the review" in m for m in logs), logs
    assert p.sm.patches == []


# --------------------------------------------------------------------------- #
# Completions                                                                  #
# --------------------------------------------------------------------------- #

def test_a_completion_charges_the_spool_on_the_head_when_it_finished(logs):
    with Indx() as p, _compute({4: 50.0}, during=p.load_229):
        _tick("PRINTING", _job(0.5))
        _tick("FINISHED")
    assert p.sm.used(42) == pytest.approx(750.0)
    assert p.sm.used(229) == pytest.approx(10.0)
    assert print_deduct_ledger.was_deducted(INDX, JOB)
    assert _rec() is None
    assert any("RCOI-5" in m and "Spool #42" in m and "auto-deducted 50.0g" in m for m in logs), logs
    # D1: said, once, in the words of Derek's rule.
    said = [m for m in logs if "now holds" in m]
    assert said == [f"ℹ️ {INDX}: RCOI-5 now holds #229; FCC charged #42, which was on it when the print ended."], logs


def test_a_completion_with_a_load_inside_the_poll_window_holds_that_head(logs):
    """Critique hole 0: the edge read names #229 (loaded between the print's end and
    the edge), the start snapshot #42. The completion is not auto-applied, and its
    card pre-fills neither spool: RCOI-5's grams are a held line offering both."""
    with Indx() as p, _compute({4: 50.0, 6: 20.0}):
        _tick("PRINTING", _job(0.5))
        p.load_229()
        _tick("FINISHED")
    rec = _rec()
    assert rec is not None and rec["kind"] == "spool_changed", logs
    assert _rows(rec) == [(243, "RCOI-7", 20.0)]
    assert rec["unresolved_usage"] == {"4": 50.0}
    assert (229, None) in _offered(rec, 4) and (42, "start") in _offered(rec, 4)
    assert "#42" in rec["unresolved_notes"]["4"] and "#229" in rec["unresolved_notes"]["4"]
    assert p.sm.patches == []
    assert not print_deduct_ledger.was_deducted(INDX, JOB)


def test_a_completion_whose_every_used_head_changed_is_a_no_spool_card_to_pick_on(logs):
    with Indx() as p, _compute({4: 50.0}):
        _tick("PRINTING", _job(0.5))
        p.load_229()
        _tick("FINISHED")
    rec = _rec()
    assert rec["kind"] == "no_spool" and rec["usage_map"] == {"4": 50.0}
    assert rec["heads_source"] == "print_end"
    assert (42, "start") in _offered(rec, 4)
    assert "#42" in rec["unresolved_notes"]["4"]
    assert p.sm.patches == []


def test_a_completion_whose_head_held_two_spools_names_both_on_its_uncharged_grams_card(logs):
    """The apply skips a head that held two spools (its WARNING, as before); the
    43.2 card's line takes its cause from the print-end read, not a read after the
    download (by then only #229 is there), and offers both, and the start spool."""
    def _unload_300():
        p.at["RCOI-5"] = [229]
    with Indx() as p, _compute({4: 50.0, 6: 20.0}, during=_unload_300):
        _tick("PRINTING", _job(0.5))
        p.at["RCOI-5"] = [229, 300]
        p.sm.spools[300] = _spool(10.0, "RCOI-5")
        _tick("FINISHED")
    assert p.sm.used(243) == pytest.approx(720.0)          # RCOI-7 charged as usual
    assert p.sm.used(229) == pytest.approx(10.0) and p.sm.used(42) == pytest.approx(700.0)
    assert any("RCOI-5 has 2 spools assigned" in m for m in logs), logs
    card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
    assert card["shortfall_causes"]["4"]["why"] == "two_spools"
    assert card["shortfall_causes"]["4"]["sids"] == [229, 300]
    assert card["heads_source"] == "print_end"
    head = next(h for h in card["heads_at_end"] if h["position"] == 4 and not h.get("when"))
    assert head["sids"] == [229, 300]
    assert (42, "start") in _offered(card, 4)


def test_a_completion_with_no_start_snapshot_never_charges_a_spool_loaded_after_it(logs):
    with Indx() as p, _compute({4: 50.0}, during=p.load_229), \
            patch.object(print_deduct, "_snapshot_active_spools", return_value={}):
        _tick("PRINTING", _job(0.5))
        _tick("FINISHED")
    assert p.sm.used(42) == pytest.approx(750.0)
    assert p.sm.used(229) == pytest.approx(10.0)
    assert print_deduct_ledger.was_deducted(INDX, JOB) and _rec() is None


def test_a_completion_split_whose_print_end_read_disagrees_with_the_last_swap_keeps_the_split(logs):
    """Critique hole 1: #42 ran out at 50% and #229 was loaded at the pause (a recorded
    swap), then #77 turned up on RCOI-5 before FCC saw the end. The split charges #42
    and #229, which printed it; #77 gets nothing, and the card says what it saw."""
    split = {4: [{"sid": 42, "grams": 20.0, "segment": 0, "runout": True},
                 {"sid": 229, "grams": 30.0, "segment": 1, "runout": False}]}
    with Indx() as p, _compute({4: 50.0}), \
            patch.object(print_deduct, "_compute_swap_split", return_value=split):
        _tick("PRINTING", _job(0.3))
        _tick("ATTENTION", _job(0.5))
        p.load_229()
        _tick("PRINTING", _job(0.5))            # the resume records #42 -> #229
        _tick("PRINTING", _job(0.9))
        p.at["RCOI-5"] = [77]                   # unrecorded, before the edge
        _tick("FINISHED")
    rec = _rec()
    assert rec["kind"] == "spool_changed" and rec["auto_split"] is True
    assert sorted(r["sid"] for r in rec["spools"]) == [42, 229]
    assert "#77" in rec["row_notes"]["229"], rec.get("row_notes")
    assert p.sm.patches == []


# --------------------------------------------------------------------------- #
# The deferred fetch                                                           #
# --------------------------------------------------------------------------- #

def test_a_cancel_queued_behind_the_screen_lock_keeps_its_print_end_heads(logs):
    with Indx() as p:
        with _compute(USAGE, error=True):
            _tick("PRINTING", _job(0.42))
            _tick("STOPPED")
        queued = cancel_fetch_store.get_pending(INDX, str(JOB))
        assert queued["end_heads"]["source"] == "print_end"
        assert {h["position"]: h["sid"] for h in queued["end_heads"]["heads"]}[4] == 42
        assert queued["start_spools"]["4"] == 42
        # A re-queue that brings another read keeps the first one.
        other = copy.deepcopy(queued["end_heads"])
        other["heads"][4]["sid"], other["heads"][4]["sids"] = 229, [229]
        print_deduct._enqueue_cancel_fetch(INDX, FILE, JOB, 0.42, end_heads=other)
        assert cancel_fetch_store.get_pending(INDX, str(JOB))["end_heads"]["heads"][4]["sid"] == 42
        p.load_229()
        with _compute(USAGE):
            print_monitor._process_pending_cancel_fetches({INDX: {"state": "IDLE"}}, "http://fb")
    rec = _rec()
    assert _rows(rec) == [(42, "RCOI-5", 84.28), (243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    assert rec["heads_source"] == "print_end"
    assert not cancel_fetch_store.has_pending(INDX, str(JOB))


def test_a_completion_queued_behind_the_finish_screen_charges_the_print_end_spool(logs):
    stamped_before_write = []
    with Indx() as p:
        real_patch = p.sm._patch

        def _patch(url, json=None, **k):
            rec = cancel_fetch_store.get_pending(INDX, str(JOB)) or {}
            stamped_before_write.append(bool(rec.get("charging_since")))
            return real_patch(url, json=json, **k)
        with patch.object(spoolman_api.requests, "patch", side_effect=_patch):
            with _compute({4: 50.0}, error=True):
                _tick("PRINTING", _job(0.5))
                _tick("FINISHED")
            assert cancel_fetch_store.get_pending(INDX, str(JOB))["end_heads"]["source"] == "print_end"
            p.load_229()
            with _compute({4: 50.0}):
                print_monitor._process_pending_cancel_fetches({INDX: {"state": "IDLE"}}, "http://fb")
        assert p.sm.used(42) == pytest.approx(750.0) and p.sm.used(229) == pytest.approx(10.0)
    assert stamped_before_write == [True]
    assert print_deduct_ledger.was_deducted(INDX, JOB)
    assert not cancel_fetch_store.has_pending(INDX, str(JOB))


# --------------------------------------------------------------------------- #
# Restart recovery and the job change                                          #
# --------------------------------------------------------------------------- #

def _latched(**extra):
    entry = {"state": "PRINTING", "job_id": JOB, "filename": FILE, "progress": 0.42,
             "start_spools": {str(pos): ON_HEAD[th] for th, pos in HEADS}, "snapshot_job": str(JOB),
             "swap_log": []}
    entry.update(extra)
    return entry


@pytest.mark.parametrize("moved", [False, True])
def test_a_cancel_recovered_after_a_restart_reads_the_heads_then_and_checks_them_against_the_start(logs, moved):
    with Indx() as p, _compute(USAGE), \
            patch.object(print_tracker_store, "load", return_value={INDX: _latched()}), \
            patch.object(print_monitor.prusalink_api, "get_printer_state", return_value={"state": "STOPPED"}):
        if moved:
            p.load_229()
        print_monitor._recover_print_tracker_on_start()
    rec = _rec()
    assert rec["heads_source"] == "restart"
    if not moved:
        assert _rows(rec) == [(42, "RCOI-5", 84.28), (243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    else:
        assert _rows(rec) == [(243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
        assert rec["unresolved_usage"] == {"4": 84.28}
        assert (42, "start") in _offered(rec, 4) and (229, None) in _offered(rec, 4)
        assert rec["unresolved_notes"]["4"] == ("RCOI-5 had #42 when the print started and #229 "
                                                "when FCC restarted after the print. Pick the spool it used.")


def test_the_job_change_review_keeps_the_outgoing_jobs_start_snapshot():
    with Indx():
        _tick("PRINTING", _job(0.42))
        with patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp:
            _tick("PRINTING", _job(0.01, job_id=1142, filename="/usb/NEXT.BGC"))
    disp.assert_called_once()
    assert disp.call_args.args[:3] == (INDX, FILE, JOB)
    assert disp.call_args.kwargs.get("start_spools", {}).get("4") == 42
    assert disp.call_args.kwargs.get("heads_when") == "job_change"
    entry = print_monitor._PRINT_TRACKER[INDX]
    assert entry["snapshot_job"] == "1142"             # the new job's own snapshot


def test_a_job_change_review_holds_a_head_changed_during_the_outgoing_print(logs):
    """Critique (d): end to end, the next job's start reads the heads and the
    outgoing job's review checks them against that job's start snapshot."""
    with Indx() as p, _compute(USAGE):
        _tick("PRINTING", _job(0.42))
        p.load_229()
        _tick("PRINTING", _job(0.01, job_id=1142, filename="/usb/NEXT.BGC"))
    rec = _rec()
    assert rec["ambiguous"] is True and rec["heads_source"] == "job_change"
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert rec["unresolved_notes"]["4"] == ("RCOI-5 had #42 when the print started and #229 "
                                            "when the next print started. Pick the spool it used.")


# --------------------------------------------------------------------------- #
# Without a print-end read                                                     #
# --------------------------------------------------------------------------- #

def test_when_the_print_end_read_fails_the_start_snapshot_is_checked_against_a_read_now(logs):
    real = getattr(print_deduct, "_capture_print_heads", None)
    calls = {"n": 0}

    def _first_fails(*a, **k):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*a, **k)
    with Indx() as p, _compute(USAGE, during=p.load_229), \
            patch.object(print_deduct, "_capture_print_heads", side_effect=_first_fails, create=True):
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
    rec = _rec()
    assert rec["heads_source"] == "late"
    assert _rows(rec) == [(243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert (42, "start") in _offered(rec, 4)
    assert rec["unresolved_notes"]["4"] == ("RCOI-5 had #42 when the print started and #229 "
                                            "when FCC logged the print. Pick the spool it used.")


def test_an_all_empty_print_end_read_counts_as_a_failed_read(logs, hublog):
    def _blip_then_load():
        p.blip = False
        p.load_229()
    with Indx() as p, _compute(USAGE, during=_blip_then_load):
        _tick("PRINTING", _job(0.42))
        p.blip = True                           # Spoolman answers [] for every head
        _tick("STOPPED")
    rec = _rec()
    assert rec["heads_source"] == "late"
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert [ln for ln in hublog if "heads at the end of job" in ln].__len__() == 1, hublog
    # The edge path wrote no Activity Log line of its own: the ack and the review's.
    assert len([m for m in logs if INDX in m]) == 2, logs


def test_with_no_print_end_read_and_no_start_snapshot_the_review_reads_the_heads_as_main_does(logs, monkeypatch):
    """Passes on main by design: the last fallback is main's code unchanged."""
    monkeypatch.setattr(print_deduct, "_capture_print_heads", lambda *a, **k: None, raising=False)
    with Indx() as p, _compute(USAGE, during=p.load_229), \
            patch.object(print_monitor, "_fcc_owns_completion_deduct", return_value=False):
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
    rec = _rec()
    assert _rows(rec) == [(229, "RCOI-5", 84.28), (243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    for key in ("heads_source", "unresolved_notes", "row_notes", "heads_words", "heads_at_end"):
        assert key not in rec, key


def test_a_completion_without_a_print_end_read_keeps_the_22_3_check(monkeypatch):
    """Passes on main by design: no end read, so main's 22.3 start-vs-live check."""
    resolve = MagicMock(return_value=[{"sid": 999, "grams": 5.0, "color": "ff0000",
                                       "position": 0, "toolhead": "XL-1"}])
    apply_ = MagicMock()
    with patch.object(print_deduct.prusalink_api, "fetch_printer_credentials", return_value=dict(CREDS)), \
            patch.object(print_deduct, "_compute_cancel_usage", return_value=({0: 5.0}, None)), \
            patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}), \
            patch.object(print_deduct, "_resolve_active_locs_for_printer",
                         return_value=[("XL-1", {"position": 0, "printer_name": "XL"})]), \
            patch.object(print_deduct, "_snapshot_active_spools", return_value={0: 999}), \
            patch.object(print_deduct, "_resolve_usage_to_spools", resolve), \
            patch.object(print_deduct, "_apply_usage_to_printer", apply_), \
            patch.object(print_deduct, "_heads_snapshot", return_value=[]):
        out = print_deduct.deduct_completed_print("XL", "f.gcode", "C-1", fb_url="http://fb",
                                                  start_spools={"0": 100})
    assert out["status"] == "pending_spool_changed", out
    apply_.assert_not_called()
    assert "heads" not in resolve.call_args.kwargs


# --------------------------------------------------------------------------- #
# Held heads                                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("end_state", ["STOPPED", "IDLE"])
def test_a_recorded_swap_on_a_used_head_holds_that_head_on_a_cancel(logs, end_state):
    with Indx() as p, _compute(USAGE):
        _tick("PRINTING", _job(0.10))
        _tick("ATTENTION", _job(0.19))
        p.load_229()
        _tick("PRINTING", _job(0.19))           # the resume records #42 -> #229
        _tick("PRINTING", _job(0.42))
        _tick(end_state)
    rec = _rec()
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert (42, "start") in _offered(rec, 4) and (229, None) in _offered(rec, 4)
    assert rec["unresolved_notes"]["4"] == ("RCOI-5's spool was swapped during the print "
                                            "(#42 to #229 at ~19%). Pick the spool it used, or weigh both.")
    assert all(r["sid"] not in (42, 229) for r in rec["spools"])


def test_a_two_spool_head_is_held_as_one_line(logs):
    """Two spools on one head are one held line offering both, never two rows of
    the head's whole grams (a plain Confirm charged both)."""
    with Indx() as p, _compute(USAGE):
        _tick("PRINTING", _job(0.42))
        p.at["RCOI-5"] = [42, 229]
        _tick("STOPPED")
    rec = _rec()
    assert _rows(rec) == [(243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    assert rec["unresolved_usage"] == {"4": 84.28}
    head = next(h for h in rec["heads_at_end"] if h["position"] == 4 and not h.get("when"))
    assert head["sids"] == [42, 229] and head["sid"] is None
    assert rec["unresolved_notes"]["4"] == ("RCOI-5 had two spools when the print ended (#42 and #229), "
                                            "so FCC can't tell which one printed. Pick the spool it used.")


def test_a_print_end_spool_that_is_gone_is_treated_like_an_empty_head_with_a_note(logs):
    def _delete_42():
        del p.sm.spools[42]
    with Indx() as p, _compute(USAGE, during=_delete_42):
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
    rec = _rec()
    assert all(r["sid"] != 42 for r in rec["spools"])
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert rec["unresolved_notes"]["4"] == ("#42 was on RCOI-5 when the print ended, but FCC couldn't "
                                            "read it from Spoolman. Pick the spool it used.")


def test_an_empty_used_head_says_which_spool_it_had_at_the_start(logs):
    with Indx() as p, _compute(USAGE):
        _tick("PRINTING", _job(0.42))
        p.at["RCOI-5"] = []
        _tick("STOPPED")
    rec = _rec()
    assert rec["unresolved_notes"]["4"] == ("No spool was loaded on RCOI-5 when the print ended; "
                                            "#42 was on it when the print started.")
    assert (42, "start") in _offered(rec, 4)


# --------------------------------------------------------------------------- #
# The pieces                                                                   #
# --------------------------------------------------------------------------- #

def test_the_capture_mirrors_the_deduct_pick():
    """Critique (c): the real resolver over an aliased printer map, so its one
    info.mmu probe is counted. M0 is empty, so the position falls through to M1."""
    pm = {"CORE1-M0": {"printer_name": "P", "position": 0},
          "CORE1-M1": {"printer_name": "P", "position": 0},
          "XL-2": {"printer_name": "P", "position": 1},
          "XL-3": {"printer_name": "P", "position": 2},
          "XL-4": {"printer_name": "P", "position": 3}}
    at = {"CORE1-M1": [5], "XL-2": [200, 999], "XL-3": [300, 302]}
    picks = {"XL-2": ([200], False), "XL-3": ([300, 302], True)}
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm), \
            patch.object(prusalink_api, "get_printer_mmu_flag", return_value=False) as mmu, \
            patch.object(spoolman_api, "get_spools_at_location", side_effect=lambda loc: list(at.get(loc, []))), \
            patch.object(spoolman_api, "select_deduct_targets", side_effect=lambda loc: picks[loc]):
        heads = print_deduct._capture_print_heads("P", "http://fb")
    assert heads == [
        {"toolhead": "CORE1-M1", "position": 0, "sid": 5, "sids": [5]},
        {"toolhead": "XL-2", "position": 1, "sid": 200, "sids": [200]},
        {"toolhead": "XL-3", "position": 2, "sid": None, "sids": [300, 302]},
        {"toolhead": "XL-4", "position": 3, "sid": None, "sids": []},
    ]
    assert mmu.call_count == 1
    with patch.object(print_deduct.locations_db, "get_active_printer_map", side_effect=OSError("locked")):
        assert print_deduct._capture_print_heads("P", "http://fb") is None


def test_the_apply_with_print_end_heads_never_reads_a_head(logs):
    sm = WeightWireSpoolman({42: _spool(700.0, "RCOI-5"), 243: _spool(10.0, "RCOI-7"),
                             250: _spool(10.0, "RCOI-7")})
    heads = [{"toolhead": "RCOI-5", "position": 4, "sid": 42, "sids": [42]},
             {"toolhead": "RCOI-6", "position": 5, "sid": None, "sids": []},
             {"toolhead": "RCOI-7", "position": 6, "sid": None, "sids": [243, 250]}]
    boom = AssertionError("read a head")
    with patch.object(spoolman_api, "get_spools_at_location", side_effect=boom), \
            patch.object(spoolman_api, "select_deduct_targets", side_effect=boom), \
            patch.object(print_deduct, "_resolve_active_locs_for_printer", side_effect=boom), \
            patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
            patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}), \
            patch.object(spoolman_api.requests, "get", side_effect=sm._get), \
            patch.object(spoolman_api.requests, "patch", side_effect=sm._patch):
        n, details, known = print_deduct._apply_usage_to_printer(
            INDX, {4: 10.0, 5: 3.0, 6: 2.0}, "http://fb", heads=heads)
    assert n == 1 and [(d["sid"], d["grams"]) for d in details] == [(42, 10.0)]
    assert sm.used(42) == pytest.approx(710.0)
    assert sm.used(243) == pytest.approx(10.0) and sm.used(250) == pytest.approx(10.0)
    assert known == {4, 5, 6}
    assert any("RCOI-7" in m and "2.00g not deducted" in m for m in logs), logs


def test_dispatchers_add_nothing_new_without_a_capture(monkeypatch):
    """Critique (b): main's cancel thread has no kwargs at all, so it is read as {}."""
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", True)
    with patch.object(print_monitor.threading, "Thread") as thread:
        print_monitor._dispatch_cancel_edge("XL", "f", "J", 0.5, "http://fb")
        assert thread.call_args.kwargs.get("kwargs", {}) == {}
        print_monitor._dispatch_ambiguous_edge("XL", "f", "J", 0.5, "http://fb")
        assert thread.call_args.kwargs["kwargs"] == {"progress_unknown": False, "unmeasured_reason": "replaced"}
        print_monitor._dispatch_completion_edge("XL", "f", "J", "http://fb")
        assert thread.call_args.kwargs["kwargs"] == {"start_spools": None, "swap_log": None}
        print_monitor._dispatch_cancel_edge("XL", "f", "J", 0.5, "http://fb", start_spools={"0": 1},
                                            swap_log=[], heads_when="restart")
        assert thread.call_args.kwargs["kwargs"] == {"start_spools": {"0": 1}, "swap_log": [],
                                                     "heads_when": "restart"}
        print_monitor._dispatch_ambiguous_edge("XL", "f", "J", 0.5, "http://fb", heads_when="job_change")
        assert thread.call_args.kwargs["kwargs"]["heads_when"] == "job_change"
        print_monitor._dispatch_completion_edge("XL", "f", "J", "http://fb", heads_when="restart")
        assert thread.call_args.kwargs["kwargs"]["heads_when"] == "restart"
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    with Indx(), patch.object(print_monitor, "_on_cancel_edge") as edge:
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
        assert edge.call_args.kwargs.get("start_spools", {}).get("4") == 42
        print_monitor._PRINT_TRACKER.clear()
        _tick("PRINTING", _job(0.42))
        print_monitor._PRINT_TRACKER[INDX]["snapshot_job"] = "another job"
        _tick("STOPPED")
        assert "start_spools" not in edge.call_args.kwargs


def test_the_print_end_read_runs_on_the_edge_thread_before_the_download(monkeypatch):
    """Critique (e): the dispatcher's own thread reads the heads, then downloads."""
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", True)
    order, done = [], threading.Event()
    real = getattr(print_deduct, "_capture_print_heads", None)

    def _capture(*a, **k):
        order.append(("read", threading.current_thread().name))
        return real(*a, **k)

    def _download(*a, **k):
        order.append(("download", threading.current_thread().name))
        done.set()
        return dict(USAGE), None
    with Indx(), patch.object(print_deduct, "_capture_print_heads", side_effect=_capture, create=True), \
            patch.object(print_deduct, "_compute_cancel_usage", side_effect=_download):
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
        assert done.wait(10), order
        for _ in range(200):                    # the review is stashed right after
            if _rec() is not None:
                break
            time.sleep(0.01)
    assert [what for what, _ in order][:2] == ["read", "download"], order
    assert order[0][1] == order[1][1] != threading.current_thread().name, order
    assert _rec()["heads_source"] == "print_end"


def test_an_apply_without_picks_on_a_card_built_from_the_print_end_read_is_refused(logs):
    """A stale page (or a script) that sends no picks must not charge whatever is
    loaded at Apply time: the very spool the hold exists to avoid."""
    cancel_review_store.add_pending({
        "printer_name": INDX, "job_id": str(JOB), "filename": FILE, "progress": 0.42,
        "total_grams": 84.28, "spools": [], "ambiguous": False, "kind": "no_spool",
        "usage_map": {"4": 84.28}, "heads_source": "print_end", "heads_read_at": "2026-11-11 14:30:48",
        "heads_at_end": [{"toolhead": "RCOI-5", "position": 4, "sid": 229, "sids": [229]},
                         {"toolhead": "RCOI-5", "position": 4, "sid": 42, "when": "start"}],
        "unresolved_notes": {"4": "RCOI-5 had #42 when the print started and #229 when the print ended. "
                                  "Pick the spool it used."}})
    with Indx() as p:
        p.load_229()
        body = app_module.app.test_client().post(
            "/api/cancel_deduct/confirm", json={"printer_name": INDX, "job_id": str(JOB), "updates": {}}).get_json()
    assert body["status"] == "error" and "pick" in body["msg"].lower(), body
    assert p.sm.patches == []
    assert _rec() is not None and not print_deduct_ledger.was_deducted(INDX, JOB)


def test_a_failed_read_before_the_stash_writes_no_note(logs):
    calls = {"n": 0}
    real = getattr(print_deduct, "_capture_print_heads", None)

    def _second_fails(*a, **k):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("Spoolman blip")
        return real(*a, **k)
    with Indx() as p, _compute(USAGE, during=p.load_229), \
            patch.object(print_deduct, "_capture_print_heads", side_effect=_second_fails, create=True):
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
    rec = _rec()
    assert _rows(rec) == [(42, "RCOI-5", 84.28), (243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    assert not rec.get("row_notes")


def test_the_card_carries_the_words_for_where_the_heads_were_read():
    """One map from source to words: the server's notes use it, and so does the
    card (it reads `heads_words` off the record)."""
    words = print_deduct._HEADS_WORDS
    assert words["print_end"] == "when the print ended"
    assert words["restart"] == "when FCC restarted after the print"
    assert words["job_change"] == "when the next print started"
    assert words["late"] == "when FCC logged the print"
    assert words["start"] == "when the print started" and words["during"] == "during the print"
    assert print_deduct._heads_words("restart") == {"end": words["restart"], "start": words["start"],
                                                    "during": words["during"]}
