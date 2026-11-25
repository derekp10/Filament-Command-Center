"""Group 65 fix review, round 5: the seen share on a completion's uncharged-grams card. Offline:
the real print-monitor ticks over the INDX wire harness, the real completion deduct and the real
confirm route; only the download is stubbed, measuring the progress FCC last saw as production
does (beside the swaps).

  - RZ1 (orange): a pick of the start spool on a completion's uncharged-grams line (seen only
    after lost contact, the spool weighed while FCC couldn't see the print) is held with RX4's
    seen share: what FCC saw it print before it lost sight counted, only the rest filled in.
    The card kept no figures, so the whole line was filled in.

Red on 22c87e02 (fix review 4's fixes).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import app as app_module
import cancel_review_store
import print_deduct
import print_monitor
import weigh_stamps
from test_print_end_heads_hotfix import (  # noqa: F401  (_isolated: the autouse isolation)
    INDX, JOB, Indx, _isolated, _job, _tick, logs)

USAGE = {4: 84.28, 6: 75.32, 7: 21.9}
AT_SEEN = {4: 70.0, 6: 60.0, 7: 18.0}         # the walk's grams at 80 %, as the download measures them


def _compute_with_cums():
    def _run(*a, **k):
        cums = k.get("cums_out")
        if cums is not None:
            for p in k.get("swap_points") or []:
                cums[p] = dict(AT_SEEN)
        return dict(USAGE), None
    return patch.object(print_deduct, "_compute_cancel_usage", side_effect=_run)


def _lose_sight(now):
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER[INDX]["seen_at"] = now - 3600
    for _ in range(3):
        print_monitor._track_print_edge(INDX, None, "http://fb")


def test_a_start_spools_pick_on_a_completions_uncharged_line_gets_its_seen_share(logs):
    with Indx() as p, _compute_with_cums():
        _tick("PRINTING", _job(0.30))
        _tick("PRINTING", _job(0.80))
        now = time.time()
        _lose_sight(now)
        p.at["RCOI-5"] = []                               # #42 taken off RCOI-5 unseen
        p.sm.spools[42]["location"] = "CR-CT-2-R1"
        weigh_stamps.note(42, "the Quick-Weigh", at=now - 1800)
        p.sm.spools[42]["used_weight"] = 784.28
        _tick("FINISHED", _job(1.0))
        card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
        # Fix review 6 (RU1): per spool, each spool's own stretches before FCC lost sight.
        assert (card.get("seen_by_head") or {}).get("4") == {"42": 70.0}, card
        before = p.sm.used(42)
        app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": INDX, "job_id": f"{JOB}#shortfall", "rev": card.get("rev", 0),
            "charges": [{"position": 4, "sid": 42, "grams": 84.28}]}).get_json()
        after = p.sm.used(42)
        kept = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall") or {}
    row = next((r for r in kept.get("spools") or [] if r.get("sid") == 42), {})
    w = row.get("weighed") or {}
    assert after == before, (before, after)
    assert w.get("unseen") and row.get("prefill") == 14.28, row
    assert "the scale counted the 70.00 g FCC saw printed by then" in w.get("words", ""), w
