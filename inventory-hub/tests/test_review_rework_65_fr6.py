"""Group 65 fix review, round 6: the seen share of a completion FCC saw only after it lost
sight of the print. Offline: the real print-monitor ticks over the wire harnesses, the real
completion deduct and the real confirm route; only the download is stubbed, measuring each
recorded swap and the progress FCC last saw, as production's walk does.

  - RU1 (orange): the share is each spool's own: a spool a swap FCC watched put on counts from
    that swap, never the head's grams from the print's start (the run-out spool's stretch
    credited to it, held at 0 g under words saying the scale counted grams FCC never saw it
    print). A split row and a set's pick both.
  - RU2 (orange): the completion's no-spool card opened with no print-end read (a one-head
    printer whose only spool came off unseen) keeps the share too; its start spool's pick was
    filled in with the whole line.

Red on 04ce498f (fix review 5's fixes).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import app as app_module
import cancel_review_store
import print_deduct
import print_monitor
import spoolman_api
import weigh_stamps
from deduct_wire_harness import WeightWireSpoolman, _start, _stop
from test_print_end_heads_hotfix import (  # noqa: F401  (_isolated: the autouse isolation)
    CREDS, INDX, JOB, Indx, _isolated, _job, _spool, _tick, logs)

USAGE = {4: 84.28, 6: 75.32, 7: 21.9}
CUMS = {0.3: {4: 25.0, 6: 22.0, 7: 6.0}, 0.8: {4: 70.0, 6: 60.0, 7: 18.0}}


def _compute_with_cums(usage, cums):
    def _run(*a, **k):
        out = k.get("cums_out")
        if out is not None:
            for p in k.get("swap_points") or []:
                out[p] = dict(cums[round(float(p), 6)])
        return dict(usage), None
    return patch.object(print_deduct, "_compute_cancel_usage", side_effect=_run)


def _lose_sight(printer, now):
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER[printer]["seen_at"] = now - 3600
    for _ in range(3):
        print_monitor._track_print_edge(printer, None, "http://fb")


def _confirm(printer, job, rev, charges):
    return app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
        "printer_name": printer, "job_id": job, "rev": rev, "charges": charges}).get_json()


def test_a_sets_pick_after_a_seen_swap_gets_its_own_seen_share(logs):
    with Indx() as p, _compute_with_cums(USAGE, CUMS):
        p.sm.spools[500] = _spool(10.0, "INBXX-2")
        _tick("PRINTING", _job(0.10))
        _tick("ATTENTION", _job(0.30))           # #42 runs out on RCOI-5: FCC watches the park
        p.load_229()                             # #229 loaded at the prompt
        _tick("PRINTING", _job(0.30))            # the resume records #42 -> #229 at 30 %
        _tick("PRINTING", _job(0.80))
        now = time.time()
        _lose_sight(INDX, now)                   # FCC loses sight at 80 %
        p.at["RCOI-5"] = [500]                   # unseen: #229 off, #500 on; #229 weighed
        p.sm.spools[500]["location"] = "RCOI-5"
        p.sm.spools[229]["location"] = "CR-CT-2-R1"
        weigh_stamps.note(229, "the Quick-Weigh", at=now - 1800)
        p.sm.spools[229]["used_weight"] = 59.28
        _tick("FINISHED", _job(1.0))
        card = cancel_review_store.get_pending(INDX, str(JOB))
        assert (card.get("seen_by_head") or {}).get("4") == {"42": 25.0, "229": 45.0}, card
        ans = _confirm(INDX, str(JOB), card.get("rev"),
                       [{"row": 243, "sid": 243, "grams": 75.32}, {"row": 231, "sid": 231, "grams": 21.9},
                        {"position": 4, "sid": 42, "grams": 25.0}, {"position": 4, "sid": 229, "grams": 49.28},
                        {"position": 4, "sid": 500, "grams": 10.0}])
        kept = cancel_review_store.get_pending(INDX, str(JOB)) or {}
    row = next((r for r in kept.get("spools") or [] if r.get("sid") == 229), {})
    w = row.get("weighed") or {}
    assert 229 in {h.get("sid") for h in ans.get("held") or []}, ans
    assert row.get("prefill") == 4.28 and not w.get("known_order"), row     # 49.28 less #229's own 45 g


ONE = "CORE1"


class OneHead:
    """A one-head printer over the wire harness: CORE1-T0 holds #42."""

    def __init__(self):
        self.sm = WeightWireSpoolman({42: _spool(700.0, "CORE1-T0")})
        self.at = {"CORE1-T0": [42]}

    def _at(self, loc):
        return list(self.at.get(str(loc).upper(), []))

    def _targets(self, loc):
        sids = self._at(loc)
        return sids, len(sids) > 1

    def __enter__(self):
        active = [("CORE1-T0", {"position": 0, "printer_name": ONE})]
        self._ctx = [
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
        _start(self._ctx)
        return self

    def __exit__(self, *exc):
        _stop(self._ctx)


def _tick1(st, job=None):
    with patch.object(print_monitor.prusalink_api, "get_printer_job", return_value=job):
        print_monitor._track_print_edge(ONE, {"state": st}, "http://fb")


def test_a_split_rows_spool_put_on_at_a_watched_swap_gets_its_own_seen_share(logs):
    with OneHead() as p, _compute_with_cums({0: 84.28}, {0.3: {0: 25.0}, 0.8: {0: 70.0}}):
        p.sm.spools[229] = _spool(10.0, "SHELF")
        _tick1("PRINTING", _job(0.10))
        _tick1("ATTENTION", _job(0.30))            # #42 runs out; FCC watches the park
        p.at["CORE1-T0"] = [229]                   # #229 loaded at the prompt
        p.sm.spools[229]["location"] = "CORE1-T0"
        p.sm.spools[42]["location"] = "CR-CT-2-R1"
        _tick1("PRINTING", _job(0.30))             # the resume records #42 -> #229
        _tick1("PRINTING", _job(0.80))
        now = time.time()
        _lose_sight(ONE, now)
        p.at["CORE1-T0"] = []                      # unseen: #229 taken off at the end and weighed
        p.sm.spools[229]["location"] = "CR-CT-2-R1"
        weigh_stamps.note(229, "the Quick-Weigh", at=now - 1800)
        p.sm.spools[229]["used_weight"] = 69.28
        _tick1("FINISHED", _job(1.0))
        card = cancel_review_store.get_pending(ONE, str(JOB))
        rows = {r["sid"]: r for r in card.get("spools") or []}
        _confirm(ONE, str(JOB), card.get("rev"), [{"row": s, "sid": s, "grams": r["grams"]} for s, r in rows.items()])
        kept = cancel_review_store.get_pending(ONE, str(JOB)) or {}
    row = next((r for r in kept.get("spools") or [] if r.get("sid") == 229), {})
    w = row.get("weighed") or {}
    g229 = rows[229]["grams"]
    assert not w.get("known_order") and abs(row.get("prefill", -1) - round(g229 - 45.0, 2)) < 0.011, row


def test_a_one_head_printers_no_spool_card_keeps_the_seen_share(logs):
    with OneHead() as p, _compute_with_cums({0: 84.28}, {0.8: {0: 70.0}}):
        _tick1("PRINTING", _job(0.30))
        _tick1("PRINTING", _job(0.80))
        now = time.time()
        _lose_sight(ONE, now)
        p.at["CORE1-T0"] = []                       # #42 taken off unseen and weighed
        p.sm.spools[42]["location"] = "CR-CT-2-R1"
        weigh_stamps.note(42, "the Quick-Weigh", at=now - 1800)
        p.sm.spools[42]["used_weight"] = 784.28
        _tick1("FINISHED", _job(1.0))
        card = (cancel_review_store.get_pending(ONE, str(JOB))
                or cancel_review_store.get_pending(ONE, f"{JOB}#shortfall"))
        before = p.sm.used(42)
        _confirm(ONE, card["job_id"], card.get("rev"), [{"position": 0, "sid": 42, "grams": 84.28}])
        after = p.sm.used(42)
        kept = cancel_review_store.get_pending(ONE, card["job_id"]) or {}
    row = next((r for r in kept.get("spools") or [] if r.get("sid") == 42), {})
    w = row.get("weighed") or {}
    assert after == before
    assert row.get("prefill") == 14.28 and "the scale counted the 70.00 g FCC saw printed by then" in w.get(
        "words", ""), row
