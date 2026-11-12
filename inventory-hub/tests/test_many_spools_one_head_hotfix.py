"""Hotfix round 2, R3 (Derek's picture check, 2026-11-12): any number of spools on
one head.

Derek: "is this bound to only work with 2 spools or is it unbound ... if I'm
trying to use up 3 or more low count spools on a print, it might happen.
Probably should make sure that it can handle n+ spools."

The code is meant to be unbounded (_compute_swap_split makes one segment per
recorded swap, _card_heads offers every start and swap spool, a set is a list,
the confirm takes one pick per spool). Until now nothing tested more than two.
Pinned here, on the real monitor, edge, review and Apply code over the wire
harness (tests/deduct_wire_harness.py), with the G-code walk the real one where
the split is the point (only the download is stubbed, and counted):

  - two recorded run-outs on one head (#42 to #229 at 10%, #229 to #300 at 25%),
    then a cancel at 42%: a split of three rows from ONE download, each with its
    stretch of the print, the run-out spools each taking the path remnant, the
    stretches adding up to the head's partial; its Apply charges all three;
  - the same on a completion: a split of three rows, reviewed (a recorded swap
    always asks), from one download;
  - three recorded swaps: a split of four rows (it isn't capped at three);
  - three spools held (the walk couldn't measure the swaps) on a cancel and on a
    completion: a set of all three, its note naming every swap, and an Apply
    with a pick per spool charging each, the ledger and the shortfall right;
  - four spools held (a fourth spool on the head at the end, put there in FCC
    with no pause): a set of four, and an Apply with four picks;
  - three spools on one head when the print ended (FCC's record assigned all
    three there): one held line offering all three, its words counting them, on
    a review and on the automatic deduct's uncharged-grams card;
  - two heads, each with a recorded swap, in one print: each split from the one
    download, on a cancel and on a completion;
  - a split whose run-out spools can't take their stretches (Derek's "use up 3 or
    more low count spools"): what they couldn't take goes on one uncharged-grams
    card, which names every one of them, marks each as run out where FCC saw it,
    and still offers the spool on the head when the print ended (the card used to
    name only the last, and wrote it over the head's own entry, so that spool was
    no longer offered);
  - round 2's review: the print-end read's own entry for a head is never written
    over on that card, when the head held two spools at the end (both stay
    offered) or when the spool that couldn't take its grams was picked by its
    number (it isn't called the spool on the head); the line's cause names it.

HEAD proof: run on 780a892 (R2, before R3), the tests marked "passes by design"
pass, because the code already handled them; the rest fail, on the words for more
than one swap or two spools, or on the uncharged-grams card, as each test's
comment says.
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
from test_print_end_heads_hotfix import FILE, INDX, JOB, USAGE, Indx, _job, _offered, _rec, _rows, _spool, _tick  # noqa: E402
from test_swap_split_sets_hotfix import _gcode, _measured  # noqa: E402

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
    monkeypatch.setattr(print_deduct.config_loader, "load_config",
                        lambda: {"path_filament_g": {INDX: PATH_G}})
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


def _put(p, head, sid):
    """`sid` onto `head`; the spool that was there goes to a cart (Spoolman's record)."""
    for old in p.at.get(head) or []:
        if old in p.sm.spools:
            p.sm.spools[old]["location"] = "CR-CT-2-R1"
    if sid not in p.sm.spools:
        p.sm.spools[sid] = _spool(10.0, head)
    p.sm.spools[sid]["location"] = head
    p.at[head] = [sid]


def _swap(p, head, sid, at):
    """A run-out on `head` at `at`: the printer parks, `sid` goes on, it resumes and
    FCC records the swap."""
    _tick("ATTENTION", _job(at))
    _put(p, head, sid)
    _tick("PRINTING", _job(at))


def _two_run_outs(p, until=0.42):
    """RCOI-5 ran out twice: #42 to #229 at 10%, #229 to #300 at 25%."""
    _tick("PRINTING", _job(0.05))
    _swap(p, "RCOI-5", 229, 0.10)
    _tick("PRINTING", _job(0.20))
    _swap(p, "RCOI-5", 300, 0.25)
    _tick("PRINTING", _job(until))


def _download(text):
    return patch.object(prusalink_api, "_download_file_bytes", return_value=text.encode())


def _confirm(body):
    return app_module.app.test_client().post(
        "/api/cancel_deduct/confirm", json=dict({"printer_name": INDX, "job_id": str(JOB)}, **body)).get_json()


def _set(rec, pos=4):
    return [(e["sid"], e["when"]) for e in (rec.get("unresolved_sets") or {}).get(str(pos), [])]


def _ledger():
    return print_deduct_ledger._load()[print_deduct_ledger._key(INDX, str(JOB))]


def _seg(frm, to, runout):
    return {"from": frm, "to": to, "runout": runout}


# --------------------------------------------------------------------------- #
# Recorded swaps: a split of one row per spool                                 #
# --------------------------------------------------------------------------- #

def test_two_run_outs_on_one_head_then_a_cancel_split_three_ways_from_one_download(logs):
    """Passes by design on 780a892."""
    text = _gcode()
    with Indx() as p, _download(text) as dl:
        _two_run_outs(p)
        _tick("STOPPED")
        assert dl.call_count == 1
        rec = _rec()
        assert rec is not None, logs
        part, at10, at25 = prusalink_api.measure_filament_usage(text, [0.42, 0.10, 0.25])["partials"]
        assert _rows(rec) == [
            (42, "RCOI-5", round(at10[4] + PATH_G, 2)),
            (229, "RCOI-5", round(at25[4] - at10[4] + PATH_G, 2)),
            (300, "RCOI-5", round(part[4] - at25[4], 2)),
            (243, "RCOI-7", round(part[6], 2)), (231, "RCOI-8", round(part[7], 2))]
        by = {r["sid"]: r for r in rec["spools"]}
        assert by[42]["segments"] == [_seg(None, 0.1, True)]
        assert by[229]["segments"] == [_seg(0.1, 0.25, True)]
        assert by[300]["segments"] == [_seg(0.25, 0.42, False)]
        assert all(by[s]["auto_split"] for s in (42, 229, 300))
        # The stretches add up to the head's partial; each run-out spool also took the
        # path remnant.
        assert sum(by[s]["grams"] for s in (42, 229, 300)) == pytest.approx(part[4] + 2 * PATH_G, abs=0.02)
        assert not rec.get("unresolved_usage") and not rec.get("unresolved_sets"), rec
        assert p.sm.patches == []
        # Confirm as drawn: each spool is charged its own stretch.
        body = _confirm({"updates": {str(r["sid"]): r["grams"] for r in rec["spools"]}})
        assert body["status"] == "confirmed" and body["shortfall_g"] == pytest.approx(0.0), body
        for sid in (42, 229, 300, 243, 231):
            before = 10.0 if sid in (229, 300) else 700.0
            assert p.sm.used(sid) == pytest.approx(before + by[sid]["grams"]), sid
    assert _ledger()["grams"] == pytest.approx(sum(r["grams"] for r in rec["spools"]), abs=0.02)
    assert not [m for m in logs if "wasn't charged to any spool" in m]


def test_two_run_outs_on_one_head_then_a_completion_split_three_ways_from_one_download(logs):
    """Passes by design on 780a892."""
    text = _gcode()
    with Indx() as p, _download(text) as dl:
        _two_run_outs(p, until=0.9)
        _tick("FINISHED")
        assert dl.call_count == 1
        rec = _rec()
        assert rec["kind"] == "spool_changed" and rec["auto_split"] is True, rec
        at10, at25 = prusalink_api.measure_filament_usage(text, [0.10, 0.25])["partials"]
        by = {r["sid"]: r for r in rec["spools"]}
        assert by[42]["grams"] == pytest.approx(round(at10[4] + PATH_G, 2))
        assert by[229]["grams"] == pytest.approx(round(at25[4] - at10[4] + PATH_G, 2))
        assert by[300]["grams"] == pytest.approx(round(84.28 - at25[4], 2))
        assert by[300]["segments"] == [_seg(0.25, None, False)]
        assert by[243]["grams"] == pytest.approx(75.32) and by[231]["grams"] == pytest.approx(21.9)
        assert p.sm.patches == []                 # reviewed, never auto-applied
        body = _confirm({"updates": {str(r["sid"]): r["grams"] for r in rec["spools"]}})
        assert body["status"] == "confirmed", body
        assert p.sm.used(300) == pytest.approx(10.0 + by[300]["grams"])
    assert print_deduct_ledger.was_deducted(INDX, JOB)


def test_three_recorded_swaps_split_four_ways(logs):
    """Passes by design on 780a892: it isn't capped at three."""
    text = _gcode()
    with Indx() as p, _download(text) as dl:
        _tick("PRINTING", _job(0.05))
        _swap(p, "RCOI-5", 229, 0.10)
        _swap(p, "RCOI-5", 300, 0.20)
        _swap(p, "RCOI-5", 301, 0.30)
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
    assert dl.call_count == 1
    rec = _rec()
    part, *cut = prusalink_api.measure_filament_usage(text, [0.42, 0.10, 0.20, 0.30])["partials"]
    by = {r["sid"]: r for r in rec["spools"] if r["position"] == 4}
    assert sorted(by) == [42, 229, 300, 301]
    assert [by[s]["segments"] for s in (42, 229, 300, 301)] == [
        [_seg(None, 0.1, True)], [_seg(0.1, 0.2, True)], [_seg(0.2, 0.3, True)], [_seg(0.3, 0.42, False)]]
    assert by[300]["grams"] == pytest.approx(round(cut[2][4] - cut[1][4] + PATH_G, 2))
    assert by[301]["grams"] == pytest.approx(round(part[4] - cut[2][4], 2))
    assert sum(r["grams"] for r in by.values()) == pytest.approx(part[4] + 3 * PATH_G, abs=0.02)


@pytest.mark.parametrize("end_state", ["STOPPED", "FINISHED"])
def test_two_heads_each_with_a_swap_are_each_split_from_the_one_download(logs, end_state):
    """RCOI-5 ran out at 10% (#42 to #229), RCOI-7 at 25% (#243 to #302). Passes by
    design on 780a892."""
    text = _gcode()
    with Indx() as p, _download(text) as dl:
        _tick("PRINTING", _job(0.05))
        _swap(p, "RCOI-5", 229, 0.10)
        _tick("PRINTING", _job(0.20))
        _swap(p, "RCOI-7", 302, 0.25)
        _tick("PRINTING", _job(0.42 if end_state == "STOPPED" else 0.9))
        _tick(end_state)
    assert dl.call_count == 1
    rec = _rec()
    if end_state == "STOPPED":
        part, at10, at25 = prusalink_api.measure_filament_usage(text, [0.42, 0.10, 0.25])["partials"]
    else:
        at10, at25 = prusalink_api.measure_filament_usage(text, [0.10, 0.25])["partials"]
        part = {4: 84.28, 6: 75.32, 7: 21.9}
        assert rec["kind"] == "spool_changed" and rec["auto_split"] is True, rec
    assert _rows(rec) == [
        (42, "RCOI-5", round(at10[4] + PATH_G, 2)), (229, "RCOI-5", round(part[4] - at10[4], 2)),
        (243, "RCOI-7", round(at25[6] + PATH_G, 2)), (302, "RCOI-7", round(part[6] - at25[6], 2)),
        (231, "RCOI-8", round(part[7], 2))]
    assert not rec.get("unresolved_usage"), rec


# --------------------------------------------------------------------------- #
# Held sets: every spool, each its own box, nothing pre-filled                 #
# --------------------------------------------------------------------------- #

def test_three_spools_held_on_a_cancel_take_a_pick_each(logs):
    """The walk couldn't measure the two swaps: a set of the three spools."""
    # On 780a892: AssertionError: (the note said "couldn't split its grams at the swap", one swap,
    # for two)
    with Indx() as p, _measured(USAGE, {}):
        _two_run_outs(p)
        _tick("STOPPED")
        rec = _rec()
        assert _set(rec) == [(42, "start"), (229, "during"), (300, "during")]
        assert rec["unresolved_usage"] == {"4": 84.28}
        assert {(42, "start"), (229, "during")} <= _offered(rec, 4)
        assert rec["unresolved_notes"]["4"] == (
            "RCOI-5's spool was swapped during the print (#42 to #229 at ~10%, then #229 to #300 at "
            "~25%), but FCC couldn't split its grams at the swaps: split the 84.28 g among them, or "
            "put it all on one.")
        body = _confirm({"charges": [
            {"row": 243, "sid": 243, "grams": 75.32}, {"row": 231, "sid": 231, "grams": 21.9},
            {"position": 4, "sid": 42, "grams": 10.0}, {"position": 4, "sid": 229, "grams": 30.0},
            {"position": 4, "sid": 300, "grams": 40.0}]})
        assert body["status"] == "confirmed", body
        assert p.sm.used(42) == pytest.approx(710.0)
        assert p.sm.used(229) == pytest.approx(40.0) and p.sm.used(300) == pytest.approx(50.0)
    # RCOI-5's 84.28 g: 80 placed, 4.28 the job's shortfall.
    assert body["shortfall_g"] == pytest.approx(4.28), body
    assert _ledger()["grams"] == pytest.approx(177.22) and _ledger()["shortfall"] == pytest.approx(4.28)
    assert [m for m in logs if "wasn't charged to any spool" in m] == [
        f"⚠️ {INDX}: 4.28g of '{FILE}' wasn't charged to any spool: 4.28 g on T4 · RCOI-5, "
        f"which had #42, #229 and #300 — weigh them to true up."]


def test_three_spools_held_on_a_completion_take_a_pick_each(logs):
    # On 780a892: AssertionError: (the note said "at the swap" for two swaps)
    with Indx() as p, _measured(USAGE, {}):
        _two_run_outs(p, until=0.9)
        _tick("FINISHED")
        rec = _rec()
        assert rec["kind"] == "spool_changed" and rec["auto_split"] is False, rec
        assert _set(rec) == [(42, "start"), (229, "during"), (300, "during")]
        assert [r["sid"] for r in rec["spools"]] == [243, 231]
        assert "at the swaps: split the 84.28 g among them" in rec["unresolved_notes"]["4"]
        assert p.sm.patches == []
        body = _confirm({"charges": [
            {"row": 243, "sid": 243, "grams": 75.32}, {"row": 231, "sid": 231, "grams": 21.9},
            {"position": 4, "sid": 42, "grams": 20.0}, {"position": 4, "sid": 229, "grams": 30.0},
            {"position": 4, "sid": 300, "grams": 34.28}]})
        assert body["status"] == "confirmed", body
        assert [p.sm.used(s) for s in (42, 229, 300)] == pytest.approx([720.0, 40.0, 44.28])
    assert body["shortfall_g"] == pytest.approx(0.0), body
    assert _ledger()["grams"] == pytest.approx(181.5) and "shortfall" not in _ledger()


def test_four_spools_held_take_four_picks(logs):
    """After the second swap, #301 was put on RCOI-5 in FCC with no pause: FCC can't
    vouch for a split, so the head is a set of all four. Passes by design on
    780a892."""
    with Indx() as p, _measured(USAGE, {0.1: {4: 15.0}, 0.25: {4: 40.0}}):
        _two_run_outs(p, until=0.30)
        _put(p, "RCOI-5", 301)
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
        rec = _rec()
        assert _set(rec) == [(42, "start"), (229, "during"), (300, "during"), (301, "end")]
        assert rec["unresolved_notes"]["4"] == (
            "RCOI-5's spool was swapped during the print (#42 to #229 at ~10%, then #229 to #300 at "
            "~25%), but #301 was on it when the print ended: split the 84.28 g among them, or put it "
            "all on one.")
        body = _confirm({"charges": [
            {"row": 243, "sid": 243, "grams": 75.32}, {"row": 231, "sid": 231, "grams": 21.9},
            {"position": 4, "sid": 42, "grams": 10.0}, {"position": 4, "sid": 229, "grams": 20.0},
            {"position": 4, "sid": 300, "grams": 30.0}, {"position": 4, "sid": 301, "grams": 24.28}]})
        assert body["status"] == "confirmed", body
        assert [p.sm.used(s) for s in (42, 229, 300, 301)] == pytest.approx([710.0, 30.0, 40.0, 34.28])
    assert body["shortfall_g"] == pytest.approx(0.0), body
    assert _ledger()["grams"] == pytest.approx(181.5)
    assert not [m for m in logs if "wasn't charged to any spool" in m]


def test_three_spools_on_one_head_at_the_end_are_one_held_line_that_counts_them(logs):
    """FCC's record had all three on RCOI-5 when the print ended: it can't tell which
    printed, so one held line offers all three, and its words count three."""
    # On 780a892: AssertionError: (the note read "RCOI-5 had two spools when the print ended
    # (#42 and #229 and #300)")
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        for sid in (229, 300):
            p.sm.spools[sid] = _spool(10.0, "RCOI-5")
        p.at["RCOI-5"] = [42, 229, 300]
        _tick("STOPPED")
        rec = _rec()
        assert rec["unresolved_usage"] == {"4": 84.28} and not rec.get("unresolved_sets"), rec
        end = [h for h in rec["heads_at_end"] if h.get("position") == 4 and not h.get("when")]
        assert end and end[0]["sids"] == [42, 229, 300], end
        assert rec["unresolved_notes"]["4"] == (
            "RCOI-5 had 3 spools when the print ended (#42, #229 and #300), so FCC can't tell which one "
            "printed. Pick the spool it used.")
        assert any("84.28g on T4 RCOI-5, which had 3 spools when the print ended (#42, #229 and #300)" in m
                   for m in logs), logs
        body = _confirm({"charges": [
            {"row": 243, "sid": 243, "grams": 75.32}, {"row": 231, "sid": 231, "grams": 21.9},
            {"position": 4, "sid": 300, "grams": 84.28}]})
        assert body["status"] == "confirmed", body
        assert p.sm.used(300) == pytest.approx(94.28)
    assert body["shortfall_g"] == pytest.approx(0.0), body


def test_a_completion_with_three_spools_on_one_head_says_three_on_its_card(logs):
    """The automatic deduct skips a head that held more than one spool and opens a
    card for its grams: its line counts the spools on that head."""
    # On 780a892: AssertionError: (the line read "RCOI-5 had two spools (#42, #229, #300)")
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.5))
        for sid in (229, 300):
            p.sm.spools[sid] = _spool(10.0, "RCOI-5")
        p.at["RCOI-5"] = [42, 229, 300]
        _tick("FINISHED")
        assert [p.sm.used(s) for s in (42, 229, 300)] == pytest.approx([700.0, 10.0, 10.0])
        assert p.sm.used(243) == pytest.approx(775.32)
    card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
    assert card["unresolved_usage"] == {"4": 84.28}, card
    assert card["shortfall_causes"]["4"]["sids"] == [42, 229, 300], card
    assert any("84.28g of" in m and "(RCOI-5 had 3 spools (#42, #229, #300))" in m for m in logs), logs


def test_a_split_head_shared_by_three_spools_lists_them_once_each():
    """The note for a split refused because its spools also printed on another
    head lists them as a list, however many there are."""
    # On 780a892: AssertionError: (", and #42 and #229 and #300 also printed on another head")
    heads = [{"toolhead": "RCOI-5", "position": 4, "sid": 300, "sids": [300]}]
    events = [{"seq": 0, "position": 4, "progress": 0.1, "from_sid": 42, "to_sid": 229, "runout": True},
              {"seq": 1, "position": 4, "progress": 0.25, "from_sid": 229, "to_sid": 300, "runout": True}]
    held = {4: {"toolhead": "RCOI-5", "sids": [300], "start": 42, "why": "swapped", "events": events,
                "split": "shared", "shared": [42, 229, 300]}}
    notes, _ = print_deduct._explain_unresolved_lines({"4": 84.28}, heads, held, {"4": 42}, set(),
                                                     print_deduct._heads_words("print_end"))
    assert notes["4"] == (
        "RCOI-5's spool was swapped during the print (#42 to #229 at ~10%, then #229 to #300 at ~25%), "
        "and #42, #229 and #300 also printed on another head, so FCC didn't split it there: split the "
        "84.28 g among them, or put it all on one.")


def test_two_run_out_spools_that_cannot_take_their_split_are_both_named_on_one_card(logs):
    """#42 and #229 both ran out, and FCC's records give each 3 g: Confirm as drawn
    charges each what it has, and both remainders go on the uncharged-grams card
    (the money passed on 780a892). The card names both run-out spools, marks each
    as run out where FCC saw it, and still offers #300, the spool on the head when
    the print ended."""
    # On 780a892: AssertionError: {'why': 'ran_out', 'sid': 229, ...} != {..., 'sids': [42, 229]}
    # (only the last of the two was named; the head's own entry was overwritten with #229, archived,
    # so the card no longer offered #300 and called #229 the spool there when the print ended)
    text = _gcode()
    with Indx() as p, _download(text):
        _two_run_outs(p)
        _tick("STOPPED")
        rec = _rec()
        by = {r["sid"]: r for r in rec["spools"]}
        p.sm.spools[42]["used_weight"] = 997.0
        p.sm.spools[229]["used_weight"] = 997.0
        body = _confirm({"updates": {str(r["sid"]): r["grams"] for r in rec["spools"]}})
        assert body["status"] == "confirmed" and body["shortfall_card"] == f"{JOB}#shortfall", body
        assert p.sm.used(42) == pytest.approx(1000.0) and p.sm.used(229) == pytest.approx(1000.0)
        assert p.sm.used(300) == pytest.approx(10.0 + by[300]["grams"])
    left = round(by[42]["grams"] - 3.0 + by[229]["grams"] - 3.0, 2)
    card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
    assert card["unresolved_usage"] == {"4": pytest.approx(left)}, card
    assert body["shortfall_g"] == pytest.approx(left), body
    assert _ledger()["shortfall"] == pytest.approx(left)
    assert card["shortfall_causes"]["4"] == {"why": "ran_out", "sid": 42, "sids": [42, 229],
                                             "toolhead": "RCOI-5", "archived": True}, card
    at4 = sorted((h.get("sid"), h.get("when") or "", bool(h.get("archived")))
                 for h in card["heads_at_end"] if h.get("position") == 4)
    assert at4 == [(42, "start", True), (229, "during", True), (300, "", False)], card["heads_at_end"]
    assert [m for m in logs if "couldn't be charged to the spool(s) picked" in m] == [
        f"⚠️ {INDX}: {left:.2f}g of '{FILE}' couldn't be charged to the spool(s) picked (the records "
        f"of #42 and #229 hit 0 g on RCOI-5) — pick another in 🛑 Review, or Discard."]


def test_one_run_out_spool_of_a_split_keeps_the_heads_own_spool_offered(logs):
    """The same with only #42 short: the card names #42 and marks it run out where
    FCC saw it (the print's start), and the head's own entry still names #300."""
    # On 780a892: AssertionError: (the head's own entry was overwritten: sid 42, archived, so #300
    # was no longer offered and #42 was called the spool there when the print ended)
    text = _gcode()
    with Indx() as p, _download(text):
        _two_run_outs(p)
        _tick("STOPPED")
        rec = _rec()
        p.sm.spools[42]["used_weight"] = 997.0
        body = _confirm({"updates": {str(r["sid"]): r["grams"] for r in rec["spools"]}})
        assert body["status"] == "confirmed" and body["shortfall_card"] == f"{JOB}#shortfall", body
    card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
    assert card["shortfall_causes"]["4"] == {"why": "ran_out", "sid": 42, "toolhead": "RCOI-5",
                                             "archived": True}, card
    at4 = sorted((h.get("sid"), h.get("when") or "", bool(h.get("archived")))
                 for h in card["heads_at_end"] if h.get("position") == 4)
    assert at4 == [(42, "start", True), (229, "during", False), (300, "", False)], card["heads_at_end"]
    assert any("(#42's record hit 0 g on RCOI-5)" in m for m in logs), logs


# Round 2's review (2026-11-12): the print-end read's entry for a head is what the
# head held when the print ended. An uncharged-grams card never writes another spool
# over it: R3 kept it only where the run-out spool had an entry of its own.

def _offered_on_card(card, pos):
    """The spools the card's picker offers for a head, by its rule (cancel_review.js
    pickSelectHtml: an entry's `sid`, else its `sids`)."""
    out = set()
    for h in card["heads_at_end"]:
        if h.get("position") == pos:
            out.update([h["sid"]] if h.get("sid") is not None else (h.get("sids") or []))
    return out


def test_a_clamp_on_a_two_spool_heads_pick_keeps_both_spools_offered(logs):
    """RCOI-5 held #42 and #229 when the print ended (one held line). #229 is picked
    for its 84.28 g and has 3 g left: the new card still offers both spools, and its
    line's cause says #229's record hit 0 g."""
    # On e777bcd: AssertionError: [(229, [42, 229], True)] (the head's entry was written over with
    # #229, so its picker offered #229 alone: #42, on the head when the print ended, was gone)
    with Indx() as p, _measured(USAGE, {}):
        _tick("PRINTING", _job(0.42))
        p.at["RCOI-5"] = [42, 229]
        p.sm.spools[229]["location"] = "RCOI-5"
        p.sm.spools[229]["used_weight"] = 997.0
        _tick("STOPPED")
        body = _confirm({"charges": [{"row": 243, "sid": 243, "grams": 75.32},
                                     {"row": 231, "sid": 231, "grams": 21.9},
                                     {"position": 4, "sid": 229, "grams": 84.28}]})
    assert body["status"] == "confirmed" and body.get("shortfall_card") == f"{JOB}#shortfall", body
    card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
    at4 = [(h.get("sid"), h.get("sids"), bool(h.get("archived")))
           for h in card["heads_at_end"] if h.get("position") == 4]
    assert at4 == [(None, [42, 229], False)], card["heads_at_end"]
    assert _offered_on_card(card, 4) == {42, 229}
    assert card["shortfall_causes"]["4"] == {"why": "ran_out", "sid": 229, "toolhead": "RCOI-5",
                                             "archived": True}, card
    assert card["unresolved_usage"] == {"4": pytest.approx(81.28)}, card


def test_a_spool_picked_by_its_number_that_runs_out_is_never_called_the_heads(logs):
    """#42's row is pointed at #500, a shelf spool with 3 g left: the new card's head
    entry still names #42 (on RCOI-5 when the print ended), and no entry calls #500
    the spool that was on the head; its line's cause names #500."""
    # On e777bcd: AssertionError: [(500, True)] (the head's entry was written over with #500, so the
    # card offered "#500 — on RCOI-5 when the print ended (ran out, archived)" and #42 was gone)
    with Indx() as p, _measured(USAGE, {}):
        p.sm.spools[500] = _spool(997.0, "SHELF-1")
        _tick("PRINTING", _job(0.42))
        _tick("STOPPED")
        body = _confirm({"charges": [{"row": 42, "sid": 500, "grams": 84.28},
                                     {"row": 243, "sid": 243, "grams": 75.32},
                                     {"row": 231, "sid": 231, "grams": 21.9}]})
        assert p.sm.used(500) == pytest.approx(1000.0)
    assert body["status"] == "confirmed" and body.get("shortfall_card") == f"{JOB}#shortfall", body
    card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
    at4 = [(h.get("sid"), bool(h.get("archived"))) for h in card["heads_at_end"] if h.get("position") == 4]
    assert at4 == [(42, False)], card["heads_at_end"]
    assert card["shortfall_causes"]["4"] == {"why": "ran_out", "sid": 500, "toolhead": "RCOI-5",
                                             "archived": True}, card
    assert any("(#500's record hit 0 g on RCOI-5)" in m for m in logs), logs
