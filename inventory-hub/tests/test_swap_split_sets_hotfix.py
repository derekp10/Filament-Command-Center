"""Hotfix 2026-11-11, scope B: the split at a recorded swap, and a head's spools as
a set on the 🛑 Review card.

Derek's rule (D1): a change of spool DURING a print always asks; it is never
guessed or auto-applied. Scope A held such a head for one pick. Scope B:

  - a cancel (or an ambiguous end) whose head ran out, or was swapped at a pause,
    and that FCC recorded (the swap log), is split at the swap: each spool is
    pre-filled with its own segment's grams, the run-out spool taking the
    printer's path remnant as a completion's does. The grams at each swap come
    from the cancel's OWN download and walk (`_compute_cancel_usage`'s
    `swap_points` / `cums_out`), as a completion's do now: `_compute_swap_split`
    downloads nothing, so a completion downloads its file once (D5; it used to
    download it twice, ~40 minutes on the INDX);
  - the split is refused, and the head held, when the walk's figures go backwards
    or past the cancel, or when the spool the print-end read names isn't the one
    the last swap loaded;
  - a head FCC can't split, and a head whose spool changed with no swap recorded
    (FCC saw one spool at the start and another at the end), is a SET: every spool
    it had, each with its own grams box and nothing pre-filled, and a note saying
    what FCC saw. The confirm takes one pick per spool for that head (picks are
    keyed per (position, spool)), and the grams of a set nobody places count as
    the job's shortfall, as unpicked grams always have.

Over the real edge, review and confirm code on the wire harness of
test_print_end_heads_hotfix.py; only the download (or, where the walk is not
the point, the compute) is stubbed.

HEAD proof: run on the branch before scope B (6a9b3ef = main 626a10e + scopes A
and C), every test here fails; the failure lines are in each test's comment.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

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
from test_print_end_heads_hotfix import (  # noqa: E402
    FILE, INDX, JOB, USAGE, Indx, _job, _offered, _rec, _rows, _spool, _tick)

PATH_G = 2.0          # the INDX's sensor-to-nozzle remnant, charged to a run-out spool


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(spoolman_api, "LAST_SPOOLMAN_ERROR", None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_monitor, "_FETCH_CLAIMS", set(), raising=False)
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
def path_g(monkeypatch):
    monkeypatch.setattr(print_deduct.config_loader, "load_config",
                        lambda: {"path_filament_g": {INDX: PATH_G}})


def _measured(usage, cums, seen=None, during=None):
    """A stand-in for the download and walk that also measures the swap points it
    is asked for, as the real one does in the same pass: `cums` is
    {swap point: {tool: grams}}."""
    def _run(*a, **k):
        if seen is not None:
            seen.append(dict(k))
        if during:
            during()
        out = k.get("cums_out")
        if out is not None:
            out.update({p: dict(c) for p, c in cums.items() if p in (k.get("swap_points") or [])})
        return dict(usage), None
    return patch.object(print_deduct, "_compute_cancel_usage", side_effect=_run)


def _run_out_at_19(p):
    """Job 1141 as it could have gone: #42 ran out on RCOI-5 at 19%, Derek loaded
    #229 at the pause, and FCC recorded the swap when the print resumed."""
    _tick("PRINTING", _job(0.10))
    _tick("ATTENTION", _job(0.19))
    p.load_229()
    _tick("PRINTING", _job(0.19))
    _tick("PRINTING", _job(0.42))


def _gcode(cycles=60):
    """A made-up INDX file: three of its eight tools take turns all through it, a
    millimetre each per turn, so each has used about the same share of its own
    filament at any point; the footer gives each `cycles` millimetres."""
    turn = "T4\nG1 E1\nT6\nG1 E1\nT7\nG1 E1\n"
    return ("M83\n" + turn * cycles
            + "; filament used [mm] = 0, 0, 0, 0, %d, 0, %d, %d\n" % (cycles, cycles, cycles)
            + "; filament used [g] = 0, 0, 0, 0, 84.28, 0, 75.32, 21.9\n")


def _set(rec, pos=4):
    return [(e["sid"], e["when"]) for e in (rec.get("unresolved_sets") or {}).get(str(pos), [])]


def _confirm(body):
    return app_module.app.test_client().post(
        "/api/cancel_deduct/confirm", json=dict({"printer_name": INDX, "job_id": str(JOB)}, **body)).get_json()


# --------------------------------------------------------------------------- #
# The cancel's split at a recorded swap                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("end_state", ["STOPPED", "IDLE"])
def test_job_1141_with_a_run_out_recorded_at_19_percent_is_split_at_the_swap(logs, path_g, end_state):
    # On 6a9b3ef: AssertionError: At index 0 diff: (243, 'RCOI-7', 75.32) != (42, 'RCOI-5', 32.0)
    # (RCOI-5 was held for one pick; nothing was split).
    seen = []
    with Indx() as p, _measured(USAGE, {0.19: {4: 30.0, 6: 25.0, 7: 7.0}}, seen):
        _run_out_at_19(p)
        _tick(end_state)
    rec = _rec()
    assert rec is not None, logs
    assert _rows(rec) == [(42, "RCOI-5", 32.0), (229, "RCOI-5", 54.28),
                          (243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    # The swap's point was measured in the cancel's own walk, not in a second download.
    assert seen[-1].get("swap_points") == [0.19], seen
    by = {r["sid"]: r for r in rec["spools"]}
    # #42 printed up to the swap (30 g) and lost the path remnant to the run-out;
    # #229 printed from the swap to the cancel.
    assert by[42]["segments"] == [{"from": None, "to": 0.19, "runout": True}]
    assert by[229]["segments"] == [{"from": 0.19, "to": 0.42, "runout": False}]
    assert by[42]["runout"] is True and by[229]["runout"] is False
    assert by[42]["auto_split"] is True and by[229]["auto_split"] is True
    assert not rec.get("unresolved_usage") and not rec.get("unresolved_sets"), rec
    assert rec["total_grams"] == pytest.approx(183.5)
    assert rec["ambiguous"] is (end_state == "IDLE")
    assert p.sm.patches == []


def test_the_swap_points_are_measured_in_the_cancels_own_download_and_walk():
    # On 6a9b3ef: TypeError: _compute_cancel_usage() got an unexpected keyword argument 'swap_points'
    text = _gcode()
    pm = {f"RCOI-{i + 1}": {"printer_name": INDX, "position": i} for i in range(8)}
    cums = {}
    with patch.object(prusalink_api, "_download_file_bytes", return_value=text.encode()) as dl, \
            patch.object(prusalink_api, "_walk_extrusion", wraps=prusalink_api._walk_extrusion) as walk, \
            patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm):
        usage, terminal = print_deduct._compute_cancel_usage(
            INDX, FILE, JOB, 0.42, "1.2.3.4", "k", swap_points=[0.19], cums_out=cums)
    assert terminal is None
    assert dl.call_count == 1 and walk.call_count == 1
    expected = prusalink_api.measure_filament_usage(text, [0.42, 0.19])["partials"]
    assert usage == expected[0]
    assert cums == {0.19: expected[1]}
    assert 0 < cums[0.19][4] < usage[4]


def test_a_stand_in_download_that_measures_no_swap_points_leaves_them_unmeasured():
    """A download that hands back no figure per swap point (an older stand-in, or a
    file FCC can't walk) measures nothing for them: the review then holds the head."""
    # On 6a9b3ef: TypeError: _compute_cancel_usage() got an unexpected keyword argument 'swap_points'
    text = _gcode()
    cums = {}
    with patch.object(prusalink_api, "fetch_cancel_gcode",
                      side_effect=lambda ip, key, fn, f, **k: {"gcode": text, "fraction": f}), \
            patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}):
        usage, terminal = print_deduct._compute_cancel_usage(
            INDX, FILE, JOB, 0.42, "1.2.3.4", "k", swap_points=[0.19], cums_out=cums)
    assert terminal is None and usage and cums == {}


def test_a_completion_split_downloads_the_print_once(logs):
    """D5: the completion's split at the swap comes from the download its footer was
    read from. It used to download the file a second time for the split (another
    20 minutes on the INDX)."""
    # On 6a9b3ef: AssertionError: assert 2 == 1 (the split downloaded the file again)
    text = _gcode()
    with Indx() as p, patch.object(prusalink_api, "_download_file_bytes", return_value=text.encode()) as dl:
        _run_out_at_19(p)
        _tick("PRINTING", _job(0.9))
        _tick("FINISHED")
    assert dl.call_count == 1
    rec = _rec()
    assert rec["kind"] == "spool_changed" and rec["auto_split"] is True, rec
    cum = prusalink_api.measure_filament_usage(text, [0.19])["partials"][0][4]
    by = {r["sid"]: r for r in rec["spools"]}
    assert by[42]["grams"] == pytest.approx(round(cum, 2))
    assert by[229]["grams"] == pytest.approx(round(84.28 - cum, 2))
    assert by[229]["segments"] == [{"from": 0.19, "to": None, "runout": False}]
    assert by[243]["grams"] == pytest.approx(75.32) and by[231]["grams"] == pytest.approx(21.9)
    assert p.sm.patches == []


def test_the_split_itself_downloads_nothing_and_refuses_figures_it_cant_trust():
    # On 6a9b3ef: TypeError: _compute_swap_split() got an unexpected keyword argument 'end'
    # (its signature was (ip, key, filename, ...): it downloaded the file again).
    def _no_download(*a, **k):
        raise AssertionError("the split asked PrusaLink for the file")
    one = {"seq": 0, "position": 4, "progress": 0.19, "from_sid": 42, "to_sid": 229, "runout": True}
    two = {"seq": 1, "position": 4, "progress": 0.30, "from_sid": 229, "to_sid": 300, "runout": False}
    with patch.object(prusalink_api, "_download_file_bytes", side_effect=_no_download), \
            patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=_no_download):
        split = print_deduct._compute_swap_split({4: 84.28}, [one, two], {"4": 42},
                                                 {0.19: {4: 30.0}, 0.3: {4: 50.0}}, end=0.42)
        assert [(r["sid"], r["grams"], r["from"], r["to"]) for r in split[4]] == [
            (42, 30.0, None, 0.19), (229, 20.0, 0.19, 0.3), (300, 34.28, 0.3, 0.42)]
        # A figure that goes backwards, or past what the print used, is no split.
        assert print_deduct._compute_swap_split({4: 84.28}, [one, two], {"4": 42},
                                                {0.19: {4: 30.0}, 0.3: {4: 20.0}}, end=0.42) is None
        assert print_deduct._compute_swap_split({4: 84.28}, [one], {"4": 42},
                                                {0.19: {4: 90.0}}, end=0.42) is None
        # A swap the walk didn't measure is no split either.
        assert print_deduct._compute_swap_split({4: 84.28}, [one], {"4": 42}, {}, end=0.42) is None


def test_a_cancel_split_is_refused_when_the_print_end_read_isnt_the_last_swaps_spool(logs, path_g):
    """#300 turned up on RCOI-5 after the recorded swap, with no swap recorded: FCC
    can't vouch for the split, so the head is a set of every spool it had."""
    # On 6a9b3ef: AssertionError: assert [] == [(42, 'start'), (229, 'during'), (300, 'end')]
    with Indx() as p, _measured(USAGE, {0.19: {4: 30.0}}):
        _run_out_at_19(p)
        p.at["RCOI-5"] = [300]
        p.sm.spools[300] = _spool(10.0, "RCOI-5")
        _tick("STOPPED")
    rec = _rec()
    assert _set(rec) == [(42, "start"), (229, "during"), (300, "end")]
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert all(r["sid"] not in (42, 229, 300) for r in rec["spools"])
    assert rec["unresolved_notes"]["4"] == (
        "RCOI-5's spool was swapped during the print (#42 to #229 at ~19%), but #300 was on it "
        "when the print ended: split the 84.28 g among them, or put it all on one.")


def test_a_cancel_split_whose_figures_overshoot_the_cancel_is_held_as_a_set(logs):
    # On 6a9b3ef: AssertionError: assert [] == [(42, 'start'), (229, 'during')]
    with Indx() as p, _measured(USAGE, {0.19: {4: 90.0}}):
        _run_out_at_19(p)
        _tick("STOPPED")
    rec = _rec()
    assert _set(rec) == [(42, "start"), (229, "during")]
    assert rec["unresolved_notes"]["4"] == (
        "RCOI-5's spool was swapped during the print (#42 to #229 at ~19%), but FCC couldn't "
        "split its grams at the swap: split the 84.28 g between them, or put it all on one.")


def test_a_queued_cancel_is_split_from_its_retrys_own_download(logs):
    """Locked behind the cancel screen, the print is retried later; the retry's one
    download measures the swap, and the swap log rides the queued record."""
    # On 6a9b3ef: AssertionError: At index 0 diff: (243, 'RCOI-7', 75.32) != (42, 'RCOI-5', 30.0)
    with Indx() as p:
        with patch.object(print_deduct, "_compute_cancel_usage",
                          return_value=(None, {"status": "error", "reason": "download_failed"})):
            _run_out_at_19(p)
            _tick("STOPPED")
        assert cancel_fetch_store.get_pending(INDX, str(JOB))["swap_log"], "the swap rides the record"
        with _measured(USAGE, {0.19: {4: 30.0}}):
            print_monitor._process_pending_cancel_fetches({INDX: {"state": "IDLE"}}, "http://fb")
    rec = _rec()
    assert _rows(rec)[:2] == [(42, "RCOI-5", 30.0), (229, "RCOI-5", 54.28)]
    assert not rec.get("unresolved_usage")


def test_split_rows_never_name_a_spool_spoolman_no_longer_has():
    # On 6a9b3ef: AssertionError: assert [{'auto_split': True, ... 'sid': 42 ...}] is None
    # (Spoolman's 404 body was read as the spool).
    with patch.object(spoolman_api, "get_spool", return_value={"message": "Item not found"}):
        assert print_deduct._split_to_review_rows(
            {4: [{"sid": 42, "grams": 30.0, "segment": 0, "runout": True, "from": None, "to": 0.19}]}) is None


# --------------------------------------------------------------------------- #
# A change FCC saw no time for: the set                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("end_state", ["STOPPED", "IDLE"])
def test_a_change_with_no_swap_recorded_is_a_set_with_nothing_pre_filled(logs, end_state):
    # On 6a9b3ef: AssertionError: assert [] == [(42, 'start'), (229, 'end')]
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        p.load_229()                            # before FCC saw the end, no pause
        _tick(end_state)
    rec = _rec()
    assert _set(rec) == [(42, "start"), (229, "end")]
    assert _rows(rec) == [(243, "RCOI-7", 75.32), (231, "RCOI-8", 21.9)]
    assert rec["unresolved_usage"] == {"4": 84.28}
    assert rec["unresolved_notes"]["4"] == (
        "FCC saw #42 when the print started and #229 when the print ended, but not when it "
        "changed: split the 84.28 g between them, or put it all on one.")
    # Each spool of the set as Spoolman has it, for the card.
    first = rec["unresolved_sets"]["4"][0]
    assert first["display"] == "#s" and first["remaining"] == pytest.approx(300.0)
    assert (42, "start") in _offered(rec, 4)
    assert p.sm.patches == []


def test_a_completion_whose_head_changed_with_no_swap_is_a_set_on_its_card(logs):
    # On 6a9b3ef: AssertionError: assert [] == [(42, 'start'), (229, 'end')]
    with Indx() as p, _measured({4: 50.0, 6: 20.0}, {}):
        _tick("PRINTING", _job(0.5))
        p.load_229()
        _tick("FINISHED")
    rec = _rec()
    assert rec["kind"] == "spool_changed"
    assert _set(rec) == [(42, "start"), (229, "end")]
    assert rec["unresolved_notes"]["4"].startswith("FCC saw #42 when the print started and #229 when "
                                                   "the print ended, but not when it changed: split the 50 g")


# --------------------------------------------------------------------------- #
# The confirm: one pick per spool of a set                                     #
# --------------------------------------------------------------------------- #

def test_a_set_takes_a_pick_per_spool_and_what_nobody_places_is_the_jobs_shortfall(logs):
    # On 6a9b3ef: AssertionError: assert 'error' == 'confirmed' ("tool 4 was picked twice")
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        p.load_229()
        _tick("STOPPED")
        body = _confirm({"charges": [
            {"row": 243, "sid": 243, "grams": 75.32}, {"row": 231, "sid": 231, "grams": 21.9},
            {"position": 4, "sid": 42, "grams": 30.0}, {"position": 4, "sid": 229, "grams": 50.0}]})
        assert body["status"] == "confirmed", body
        assert p.sm.used(42) == pytest.approx(730.0) and p.sm.used(229) == pytest.approx(60.0)
        assert p.sm.used(243) == pytest.approx(775.32) and p.sm.used(231) == pytest.approx(721.9)
    # 84.28 g were RCOI-5's; 80 g were placed.
    assert body["shortfall_g"] == pytest.approx(4.28), body
    assert print_deduct_ledger.was_deducted(INDX, JOB)


def test_one_spool_picked_twice_for_one_head_is_refused(logs):
    # On 6a9b3ef: AssertionError: assert 'spool #42 was picked twice for tool 4' in 'tool 4 was picked twice'
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        p.load_229()
        _tick("STOPPED")
        body = _confirm({"charges": [{"position": 4, "sid": 42, "grams": 30.0},
                                     {"position": 4, "sid": 42, "grams": 5.0}]})
        assert p.sm.patches == []
    assert body["status"] == "error" and "spool #42 was picked twice for tool 4" in body["msg"], body
    assert _rec() is not None


def test_a_no_spool_card_s_set_takes_a_pick_per_spool(logs):
    """A completion whose only used head changed with no swap recorded: a no_spool
    card whose line is a set; one pick per spool charges both."""
    # On 6a9b3ef: AssertionError: assert [] == [(42, 'start'), (229, 'end')]
    with Indx() as p, _measured({4: 50.0}, {}):
        _tick("PRINTING", _job(0.5))
        p.load_229()
        _tick("FINISHED")
        rec = _rec()
        assert rec["kind"] == "no_spool"
        assert _set(rec) == [(42, "start"), (229, "end")]
        body = _confirm({"charges": [{"position": 4, "sid": 42, "grams": 20.0},
                                     {"position": 4, "sid": 229, "grams": 30.0}]})
        assert body["status"] == "confirmed", body
        assert p.sm.used(42) == pytest.approx(720.0) and p.sm.used(229) == pytest.approx(40.0)
    assert body["shortfall_g"] == pytest.approx(0.0)
