"""Group 65 fix review, round 5: a set's spool that left its head at a park FCC first saw only
when it got there, held at the Apply. Offline: a no-spool set card as the builder writes it,
the real confirm route over SpoolmanHTTPFake.

  - RZ3 (yellow): a pick of the run-out spool, weighed at the prompt before FCC saw the park
    it first met the print at, is held at the Apply as a weighing FCC can't place, as the
    builder marks such a row; it was charged with no hold. Group 64's left kind (weighed after
    FCC saw the park) is held as before. A card that kept only its swap log (built before the
    spans were kept) holds it too.

Red on 22c87e02 (fix review 4's fixes).
"""
from __future__ import annotations

import time

import pytest

import app as app_module
import cancel_review_store
import print_deduct
import weigh_stamps
from test_review_rework_65_r1 import _iso, _spoolman, logs  # noqa: F401


def _card(weighed_at_offset, keep_spans):
    now = time.time()
    unseen_from, at = now - 7200, now - 3600          # FCC last saw the printer; FCC saw the park
    weigh_stamps.note(100, "Quick Weigh", at=at + weighed_at_offset)
    swap = [{"seq": 0, "position": "0", "progress": 0.45, "from_sid": 100, "to_sid": 200,
             "at": at, "back_at": at + 120, "unseen_from": unseen_from}]
    rec = {"printer_name": "XL", "job_id": "J-9", "filename": "f.gcode", "progress": 1.0,
           "total_grams": 40.0, "spools": [], "ambiguous": True, "kind": "no_spool", "rev": 0,
           "usage_map": {"0": 40.0},
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 300, "sids": [300], "used": {"300": 0.0}},
                            {"toolhead": "XL-1", "position": 0, "sid": 100, "when": "start"},
                            {"toolhead": "XL-1", "position": 0, "sid": 200, "when": "swap"}],
           "heads_source": "print_end", "end_at_s": now - 60,
           "unresolved_sets": {"0": [{"sid": 100, "when": "start"}, {"sid": 200, "when": "swap"},
                                     {"sid": 300, "when": "end"}]},
           "swap_left_at": {"100": at}, "swap_log": swap, "start_spools": {"0": 100},
           "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    if keep_spans:
        rec["swap_left_unseen"] = print_deduct._swap_left_unseen(swap)
    cancel_review_store.add_pending(rec)
    return rec


def _apply(rec):
    return app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
        "printer_name": "XL", "job_id": "J-9", "rev": rec.get("rev", 0),
        "charges": [{"position": 0, "sid": 100, "grams": 18.0}, {"position": 0, "sid": 200, "grams": 12.0},
                    {"position": 0, "sid": 300, "grams": 10.0}]}).get_json()


@pytest.mark.parametrize("keep_spans", [True, False])
def test_a_sets_spool_weighed_before_fcc_saw_the_park_is_held_at_the_apply(logs, keep_spans):
    rec = _card(-600, keep_spans)                     # weighed at the prompt BEFORE FCC saw the park
    with _spoolman({100: 100.0, 200: 0.0, 300: 0.0}):
        ans = _apply(rec)
    held = {h.get("sid"): h for h in ans.get("held") or []}
    assert 100 in held and held[100].get("known_order") is False, ans
    assert "before it first saw this print, at its park" in held[100].get("words", ""), held[100]


def test_group_64s_left_kind_is_still_held_at_the_apply(logs):
    rec = _card(+600, True)                           # weighed AFTER FCC saw the park
    with _spoolman({100: 100.0, 200: 0.0, 300: 0.0}):
        ans = _apply(rec)
    held = {h.get("sid"): h for h in ans.get("held") or []}
    assert 100 in held and held[100].get("known_order") is True, ans
