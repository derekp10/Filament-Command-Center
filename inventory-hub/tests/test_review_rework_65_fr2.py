"""Group 65 fix review, round 2: the 🛑 card's server. Offline.

  - AV3 / RE3 (orange): on every card FCC saw only after lost contact (not only a
    "couldn't measure" one), a spool FCC weighed while it couldn't see the print is marked
    unsure when the card is built, the print's grams filled in and the loud words said;
    an Apply on a card that didn't show it holds it.
  - RE1: such a mark is a kind of its own ("unseen"), and the Activity Log says what it
    was when an Apply leaves it uncharged.
  - RE4: a card that kept a swap log but no start snapshot still works out its rows' marks
    from the swap log when it is worked out again.

Red on 2363aba3 (the second fix review's head), all but one guard, green there too:
a spool weighed after FCC saw the printer again (test_a_spool_weighed_after_fcc_saw_the_printer_again_is_no_unseen_mark).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import app as app_module
import cancel_review_store
import print_deduct
import weigh_stamps
from test_cancel_review import _cancelled_gcode, _preview_ctx
from test_review_rework_65_r1 import (  # noqa: F401  (_iso: the autouse isolation)
    SPOOLS, TWO, _card, _iso, _recompute, _spoolman, _start, _stop, logs)


def _lost_card(weighed_at=None):
    """An XL print FCC lost sight of at ~25% and saw idle again later, its heads read then
    ('back', #100 on XL-1 with its used weight as it was then); #100 weighed on FCC at
    `weighed_at` (relative to the stretch)."""
    gcode, cut = _cancelled_gcode()
    now = time.time()
    seen, back = now - 9000, now - 60
    end = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 100, "sids": [100], "used": {"100": 140.0}},
                     {"toolhead": "XL-2", "position": 1, "sid": 200, "sids": [200], "used": {"200": 50.0}}],
           "source": "back", "at": back}
    lost = {"progress": cut, "seen_at": seen, "lost_at": seen + 10, "back_at": back, "back_state": "IDLE",
            "why": "lost"}
    if weighed_at is not None:
        weigh_stamps.note(100, "Quick Weigh", at=seen + weighed_at)
    spools = dict(SPOOLS)
    spools[100] = {"id": 100, "used_weight": 140.0, "initial_weight": 1000.0}
    ctx = _preview_ctx(gcode, TWO, spools, {"XL-1": [100], "XL-2": [200]}, {"updates": []})
    ctx.append(patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                            side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f, "remap": lambda p: p}))
    ctx.append(patch.object(print_deduct.state, "add_log_entry", lambda *a, **k: None))
    _start(ctx)
    try:
        with _spoolman({100: 140.0, 200: 50.0}):
            app_module._create_pending_cancel_review("XL", "f.gcode", "J-1", cut, fb_url="http://fb",
                                                     ambiguous=True, end_heads=end,
                                                     start_spools={"0": 100, "1": 200}, lost_contact=lost)
    finally:
        _stop(ctx)
    return cancel_review_store.get_pending("XL", "J-1")


def test_a_spool_weighed_while_fcc_couldnt_see_the_print_is_marked_when_the_card_is_built(logs):
    card = _lost_card(weighed_at=3600)
    row = next(r for r in card["spools"] if r["sid"] == 100)
    mark = row.get("weighed") or {}
    # Group 65 fix review 3 (RX4): the card is worked out at the progress FCC last saw, and
    # every gram on its row was printed before that weighing: 0 g, of known order.
    assert mark.get("seen") is True and mark.get("known_order") is True, row
    assert row["prefill"] == 0.0, row
    assert "after FCC last saw the print" in mark["words"] and "already counted" in mark["words"], mark


def test_a_spool_weighed_after_fcc_saw_the_printer_again_is_no_unseen_mark(logs):
    card = _lost_card(weighed_at=None)
    row = next(r for r in card["spools"] if r["sid"] == 100)
    assert not row.get("weighed"), row


def test_an_apply_on_a_card_that_didnt_show_the_unseen_weighing_holds_it(logs):
    card = _lost_card(weighed_at=3600)
    for r in card["spools"]:          # a card built before the mark: it showed nothing
        r.pop("weighed", None)
        r.pop("prefill", None)
    cancel_review_store.add_pending(card)
    held = print_deduct._held_at_apply(card, card["spools"][0], 100, 140.0)
    assert held and held["unsure"] is True and held["stamp"]["how"] == "Quick Weigh", held
    # Group 65 fix review 3 (RX4): at the progress FCC last saw, what the Apply asks was all
    # printed before that weighing: held at 0 g, of known order.
    mark = print_deduct._held_mark(held, 20.0)
    assert mark["weighed"]["seen"] is True and mark["prefill"] == 0.0, mark


def test_an_unseen_weighing_left_uncharged_is_said_as_that(logs):
    print_deduct._say_left_weighed("XL", "f.gcode", "J-1", [
        {"line": "0", "sid": 100, "grams": 20.0, "known_order": False, "unseen": True}])
    assert logs == ["✔️ XL: left 20.00g of 'f.gcode' uncharged on #100 (job J-1): weighed while FCC couldn't see "
                    "the print, so FCC couldn't tell whether the scale counted it: left as set on the card."], logs


def test_a_card_with_a_swap_log_but_no_snapshot_works_its_marks_out_from_it(logs, monkeypatch):
    now = time.time()
    t_off, t_back = now - 7200, now - 3600
    swaps = [{"position": 0, "from_sid": 42, "to_sid": 229, "progress": 0.2, "seq": 1, "at": t_off},
             {"position": 0, "from_sid": 229, "to_sid": 42, "progress": 0.5, "seq": 2, "at": t_back - 60,
              "back_at": t_back}]
    weigh_stamps.note(42, "Quick Weigh", at=t_off + 600)          # weighed while off its head
    by0 = [round(i * 0.4, 4) for i in range(101)]
    _card(progress=0.6, swap_log=swaps, spools=[
        {"sid": 42, "toolhead": "XL-1", "position": 0, "grams": 12.0, "current_used": 900.0,
         "initial_weight": 1000.0, "remaining_before": 100.0, "remaining_after": 88.0, "display": "#42",
         "color": "f00", "auto_split": True,
         "segments": [{"from": None, "to": 0.2, "runout": False, "grams": 8.0},
                      {"from": 0.5, "to": 0.6, "runout": False, "grams": 4.0}]},
        {"sid": 229, "toolhead": "XL-1", "position": 0, "grams": 12.0, "current_used": 10.0,
         "initial_weight": 1000.0, "remaining_before": 990.0, "remaining_after": 978.0, "display": "#229",
         "color": "0f0", "auto_split": True,
         "segments": [{"from": 0.2, "to": 0.5, "runout": False, "grams": 12.0}]}],
        heads_at_end=[{"toolhead": "XL-1", "position": 0, "sid": 42, "sids": [42]}],
        figures={"footer": {"0": 40.0}, "by_pct": {"0": by0}})
    with _spoolman({42: 900.0, 229: 10.0}):
        ans = _recompute(rev=0, whole=True)
    row = next(r for r in ans["record"]["spools"] if r["sid"] == 42)
    assert row["grams"] == 28.0 and (row.get("weighed") or {}).get("back") is True, row
    assert row["prefill"] == 20.0, row          # its stretch after going back on, 0.5 to the whole print
