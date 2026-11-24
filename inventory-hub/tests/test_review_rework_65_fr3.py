"""Group 65 fix review, round 3: the 🛑 card's server and the completion. Offline.

  - AX1 / RX1 (orange): a spool FCC saw leave its head at a recorded swap and weighed
    while it couldn't see the print keeps Group 64's left-at-a-swap mark (known order,
    0 g): the swap came before the weighing. The unseen mark is worked out last.
  - RX4 (orange): what FCC saw printed before it lost sight of the print came before a
    weighing while it couldn't see it, so the scale counted it: on a card worked out at
    that progress the row is 0 g of known order ("seen"); worked out further, only the
    grams past it are filled in, as a weighing FCC can't place. The Apply's hold splits
    the same way.
  - RX2 (orange): a finish FCC saw only after it lost sight of the print holds a spool
    FCC weighed meanwhile, never charging it on top of that weighing, its grams split as
    RX4 splits them (from the same download).
  - RX6: a split head's spool left at 0 g beside its charged twin is named as left
    uncharged.
  - RX3: a card kept by an Apply Spoolman didn't answer is refused for rework in words
    that say so, never as an Apply that held a spool.

Red on dcfa4a4b (the third fix review's head).
"""
from __future__ import annotations

import time

import pytest

import app as app_module  # noqa: F401  (the routes)
import cancel_review_store
import print_deduct
import print_deduct_ledger
import prusalink_api
import weigh_stamps
from test_print_end_hardening_64 import (  # noqa: F401  (_isolated: the autouse isolation)
    JOB, XL, TwoHeadsOverHTTP, _download, _end_read, _isolated, _two_tool_gcode, stamps, warn_lines)
from test_review_rework_65_fr2 import _lost_card
from test_review_rework_65_r1 import _card, _recompute, _spoolman, logs  # noqa: F401


@pytest.fixture(autouse=True)
def _own_stamps(tmp_path, monkeypatch):
    monkeypatch.setattr(weigh_stamps, "_STORE_PATH", str(tmp_path / "weigh_stamps.json"))


# --------------------------------------------------------------------------- #
# AX1 / RX1: a mark FCC can place by a recorded swap stands                    #
# --------------------------------------------------------------------------- #

def test_a_spool_left_at_a_swap_and_weighed_unseen_keeps_its_left_mark():
    now = time.time()
    t_swap, seen_at, back_at = now - 7200, now - 3600, now - 60
    weigh_stamps.note(42, "Quick Weigh", at=seen_at + 600)        # weighed while FCC couldn't see the print
    rows = [{"sid": 42, "toolhead": "RCOI-5", "position": 4, "grams": 30.0}]
    print_deduct._mark_weighed_rows(rows, [], None, {"42": t_swap}, None, None, unseen=(seen_at, back_at))
    mark = rows[0]["weighed"]
    assert mark.get("left") is True and mark["known_order"] is True and not mark.get("unseen"), mark
    assert rows[0]["prefill"] == 0.0, rows


# --------------------------------------------------------------------------- #
# RX4: what FCC saw printed before it lost sight of the print                 #
# --------------------------------------------------------------------------- #

def test_a_card_at_the_progress_fcc_saw_holds_an_unseen_weighing_at_0g_of_known_order(logs):
    card = _lost_card(weighed_at=3600)
    row = next(r for r in card["spools"] if r["sid"] == 100)
    mark = row.get("weighed") or {}
    assert mark.get("seen") is True and mark.get("known_order") is True and not mark.get("unseen"), row
    assert row["prefill"] == 0.0, row
    assert "after FCC last saw the print" in mark["words"] and "already counted" in mark["words"], mark


def _lost(seen_at, back_at, progress=0.3):
    return {"progress": progress, "seen_at": seen_at, "lost_at": seen_at + 10, "back_at": back_at,
            "back_state": "IDLE", "why": "lost"}


def test_worked_out_for_the_whole_print_only_the_grams_past_what_fcc_saw_are_filled_in(logs):
    now = time.time()
    seen_at, back_at = now - 7200, now - 60
    weigh_stamps.note(57, "Quick Weigh", at=seen_at + 600)
    # Fix review 4 (RY2): the start snapshot FCC took names #57 on XL-1, so the share FCC saw
    # printed is #57's.
    _card(lost_contact=_lost(seen_at, back_at), start_spools={"0": 57})
    with _spoolman({57: 100.0, 58: 50.0}):
        ans = _recompute(rev=0, whole=True)
    row = next(r for r in ans["record"]["spools"] if r["sid"] == 57)
    mark = row.get("weighed") or {}
    assert row["grams"] == 40.0 and mark.get("unseen") is True and mark.get("known_order") is False, row
    assert row["prefill"] == 28.0 and mark.get("seen_g") == 12.0, row        # 12 g seen at 30 % of 40 g
    assert "the scale counted the 12.00 g FCC saw printed by then" in mark["words"], mark


def test_the_applys_hold_splits_the_same_way(logs):
    now = time.time()
    seen_at, back_at = now - 7200, now - 60
    weigh_stamps.note(57, "Quick Weigh", at=seen_at + 600)
    rec = _card(lost_contact=_lost(seen_at, back_at), progress=1.0, basis="whole", start_spools={"0": 57},
                spools=[{"sid": 57, "toolhead": "XL-1", "position": 0, "grams": 40.0}])
    held = print_deduct._held_at_apply(rec, rec["spools"][0], 57, 100.0)
    mark = print_deduct._held_mark(held, 40.0)
    assert mark["weighed"]["unseen"] is True and mark["prefill"] == 28.0, mark


# --------------------------------------------------------------------------- #
# RX2: a finish FCC saw only after it lost sight of the print                 #
# --------------------------------------------------------------------------- #

def test_a_finish_seen_after_lost_contact_holds_a_spool_weighed_meanwhile(stamps, warn_lines):
    rig = TwoHeadsOverHTTP()
    end = _end_read(rig)
    now = end["at_s"]
    lost = _lost(now - 3600, now, progress=0.3)
    stamps.note(200, "the Quick-Weigh", at=now - 1800)        # while FCC couldn't see the print
    with rig, _download(_two_tool_gcode()):
        out = print_deduct.deduct_completed_print(XL, "x.gcode", JOB, fb_url="http://fb", end_heads=end,
                                                  lost_contact=lost)
    assert out["status"] == "deducted", out
    assert rig.used(200) == 100.0, "charged on top of the weighing"
    assert rig.used(300) == pytest.approx(53.6)
    card = cancel_review_store.get_pending(XL, f"{JOB}#shortfall")
    cause = card["shortfall_causes"]["0"]
    assert cause["why"] == "weighed" and cause["unseen"] is True and cause["known_order"] is False, cause
    seen = prusalink_api.measure_filament_usage(_two_tool_gcode(), [0.3])["partials"][0]
    seen_g = next(v for k, v in seen.items() if str(k) == "0")
    assert 0 < seen_g < 12.4
    assert card["shortfall_prefill"]["0"] == pytest.approx(12.4 - seen_g, abs=0.01), card
    assert print_deduct_ledger.was_deducted(XL, str(JOB))


# --------------------------------------------------------------------------- #
# RX6: a split head's spool left at 0 g                                       #
# --------------------------------------------------------------------------- #

def test_a_split_heads_spool_left_at_0g_beside_its_charged_twin_is_named(logs):
    now = time.time()
    weigh_stamps.note(42, "Quick Weigh", at=now - 600)
    row42 = {"sid": 42, "toolhead": "XL-1", "position": 0, "grams": 30.0, "current_used": 700.0,
             "initial_weight": 1000.0, "remaining_before": 300.0, "remaining_after": 270.0, "display": "#42",
             "color": "f00", "auto_split": True, "prefill": 0.0,
             "weighed": {"words": "#42 left XL-1 at a swap", "known_order": True, "left": True,
                         "stamp_at": now - 600}}
    row229 = {"sid": 229, "toolhead": "XL-1", "position": 0, "grams": 54.28, "current_used": 10.0,
              "initial_weight": 1000.0, "remaining_before": 990.0, "remaining_after": 935.72, "display": "#229",
              "color": "0f0", "auto_split": True}
    _card(progress=1.0, total_grams=84.28, spools=[row42, row229], swap_left_at={"42": now - 3600})
    with _spoolman({42: 730.0, 229: 10.0}):
        ans = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-1", "rev": 0, "updates": {"229": 54.28}}).get_json()
    assert [l["sid"] for l in ans.get("left_weighed") or []] == [42], ans
    assert any("uncharged on #42" in m for m in logs), logs


# --------------------------------------------------------------------------- #
# RX3: the words for a card an Apply kept                                      #
# --------------------------------------------------------------------------- #

def _kept(**more):
    rec = {"kind": "partial", "figures": {"footer": {"0": 40.0}}, "requested_total": 20.0, "applied_g": 0.0,
           "spools": [{"sid": 100, "grams": 20.0, "position": 0,
                       "weighed": {"words": "x", "known_order": False, "unseen": True}}]}
    rec.update(more)
    return rec


def test_a_card_kept_because_spoolman_didnt_answer_says_so():
    why = print_deduct._rework_refusal(_kept(kept_why=["failed"]))
    assert why.startswith("An earlier Apply couldn't charge part of this card"), why


def test_a_card_an_apply_held_a_spool_on_still_says_that():
    why = print_deduct._rework_refusal(_kept(kept_why=["held"]))
    assert why.startswith("An earlier Apply on this card held or left uncharged"), why
