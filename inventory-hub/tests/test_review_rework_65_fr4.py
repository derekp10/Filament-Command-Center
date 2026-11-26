"""Group 65 fix review, round 4: a completion FCC saw only after it lost sight of the print,
its cards and their words. Offline: the real print-monitor ticks over the wire harness, the
real completion deduct and the real confirm route; only the download is stubbed.

  - RY1 (orange): the cards such a completion opens keep its lost-contact facts: the
    uncharged-grams card (a head left with no spool) and the no-spool card (every used head
    held). A pick there of a spool FCC weighed while it couldn't see the print is held at the
    Apply, as a cancel's card holds one, never charged on top of that weighing.
  - RY3 (yellow): a kept card's Activity Log line says a line held for a weighing while FCC
    couldn't see the print as that, never as a weight that "changed after the print ended".

Red on cbfea058 (fix review 3's fixes).
"""
from __future__ import annotations

import time

import app as app_module
import cancel_review_store
import print_deduct
import print_monitor
import weigh_stamps
from test_print_end_heads_hotfix import (  # noqa: F401  (_isolated: the autouse isolation)
    INDX, JOB, Indx, _compute, _isolated, _job, _rec, _tick, logs)


def _lose_sight(now):
    with print_monitor._PRINT_TRACKER_LOCK:
        print_monitor._PRINT_TRACKER[INDX]["seen_at"] = now - 3600   # FCC last saw it an hour ago
    for _ in range(3):                                               # the printer drops off the network
        print_monitor._track_print_edge(INDX, None, "http://fb")


def _confirm(job_id, rev, charges, **more):
    return app_module.app.test_client().post("/api/cancel_deduct/confirm", json=dict(
        {"printer_name": INDX, "job_id": job_id, "rev": rev, "charges": charges}, **more)).get_json()


def test_a_completion_shortfall_cards_pick_of_a_spool_weighed_unseen_is_held(logs):
    with Indx() as p, _compute({4: 84.28, 6: 75.32, 7: 21.9}):
        _tick("PRINTING", _job(0.30))
        _tick("PRINTING", _job(0.80))
        now = time.time()
        _lose_sight(now)
        # The print finishes unseen. Derek unloads #42 from RCOI-5 to the cart and weighs it on
        # the Quick-Weigh: the scale counts the whole print's 84.28 g (700 -> 784.28 g used).
        p.at["RCOI-5"] = []
        p.sm.spools[42]["location"] = "CR-CT-2-R1"
        weigh_stamps.note(42, "the Quick-Weigh", at=now - 1800)
        p.sm.spools[42]["used_weight"] = 784.28
        _tick("FINISHED", _job(1.0))                 # FCC sees the finished screen
        card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
        assert (card or {}).get("lost_contact", {}).get("why") == "lost", card
        before = p.sm.used(42)
        ans = _confirm(f"{JOB}#shortfall", card.get("rev", 0), [{"position": 4, "sid": 42, "grams": 84.28}])
        after = p.sm.used(42)
    assert after == before, (before, after, ans)
    assert 42 in {h.get("sid") for h in ans.get("held") or []}, ans


def test_a_completion_whose_every_used_head_is_held_keeps_its_lost_contact(logs):
    with Indx() as p, _compute({4: 84.28}):
        _tick("PRINTING", _job(0.30))
        _tick("PRINTING", _job(0.80))
        now = time.time()
        _lose_sight(now)
        p.load_229()                                   # #229 onto RCOI-5, #42 off to the cart
        weigh_stamps.note(42, "the Quick-Weigh", at=now - 1800)
        p.sm.spools[42]["used_weight"] = 730.0         # the scale counted #42's share (30 g)
        _tick("FINISHED", _job(1.0))
        card = _rec()
        assert (card or {}).get("lost_contact", {}).get("why") == "lost", card
        before = p.sm.used(42)
        _confirm(str(JOB), card.get("rev"), [{"position": 4, "sid": 42, "grams": 30.0},
                                             {"position": 4, "sid": 229, "grams": 54.28}])
        after = p.sm.used(42)
    assert after == before, (before, after)


def test_a_kept_cards_words_for_a_line_weighed_while_fcc_couldnt_see_the_print(logs):
    with Indx() as p, _compute({4: 84.28, 6: 75.32}):
        _tick("PRINTING", _job(0.30))
        _tick("PRINTING", _job(0.80))
        now = time.time()
        _lose_sight(now)
        # While FCC can't see the printer: #42 (RCOI-5) is weighed on the Quick-Weigh, and #243
        # is taken off RCOI-7 to the cart with 10 g left on its record.
        weigh_stamps.note(42, "the Quick-Weigh", at=now - 1800)
        p.sm.spools[42]["used_weight"] = 784.28
        p.at["RCOI-7"] = []
        p.sm.spools[243]["location"] = "CR-CT-2-R1"
        p.sm.spools[243]["used_weight"] = 990.0
        _tick("FINISHED", _job(1.0))
        card = cancel_review_store.get_pending(INDX, f"{JOB}#shortfall")
        logs.clear()
        _confirm(f"{JOB}#shortfall", card.get("rev", 0), [{"position": 6, "sid": 243, "grams": 75.32}],
                 settle_held=True)
    line = next(m for m in logs if "stay on" in m)
    assert "after the print ended" not in line, line
    assert "on #42, weighed while FCC couldn't see the print, stay on the card" in line, line


def test_the_kept_words_say_each_kind_and_keep_group_64s_for_one():
    known = [{"sid": 200, "grams": 12.4, "known_order": True}]
    unsure = [{"sid": 201, "grams": 3.0, "known_order": False}]
    unseen = [{"sid": 42, "grams": 84.28, "known_order": False, "unseen": True}]
    seen = [{"sid": 43, "grams": 5.0, "known_order": True, "seen": True}]
    assert print_deduct._kept_card_words(12.4, known) == (
        "12.40g on #200, weighed after the print ended, stay on the card: Apply again to leave them "
        "uncharged, or Discard")
    assert print_deduct._kept_card_words(3.0, unsure) == (
        "3.00g on #201, whose weight changed after the print ended, stay on the card: check them, then "
        "Apply again or Discard")
    both = print_deduct._kept_card_words(89.28, seen + unseen)
    assert both == ("5.00g on #43, weighed after FCC last saw the print, and 84.28g on #42, weighed while "
                    "FCC couldn't see the print, stay on the card: check them, then Apply again or Discard"), both
