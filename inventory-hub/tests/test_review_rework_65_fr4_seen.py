"""Group 65 fix review, round 4: the share of a print FCC saw printed before it lost sight of
it (RX4's), only for the spool FCC saw print it; and a weighing of a swapped-off spool FCC
can't place against a park it first saw late. Offline.

  - RY2 (orange): on a card seen only after lost contact, a pick of a spool that went on its
    head while FCC couldn't see the print (a set's spool loaded at an unseen prompt) printed
    none of what FCC saw, so a weighing of it then is held unsure, its grams filled in; the
    start spool keeps its share. It was said to have printed what FCC saw the start spool
    print, 0 g filled in under words saying FCC knew the order.
  - WY6 (red, the card's half): a spool that left its head at a swap at a park FCC first saw
    only when it got there, weighed before FCC saw that park, is marked as a weighing FCC
    can't place; weighed after, it keeps Group 64's left mark.

Red on cbfea058 (fix review 3's fixes).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import app as app_module
import cancel_review_store
import print_deduct
import weigh_stamps
from test_cancel_review import _cancelled_gcode, _preview_ctx
from test_review_rework_65_r1 import TWO, _iso, _recompute, _spoolman, _start, _stop, logs  # noqa: F401

SPOOLS = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
          200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0},
          300: {"id": 300, "used_weight": 0.0, "initial_weight": 1000.0}}


def _set_card():
    """FCC saw an XL print start (XL-1 #100, XL-2 #200) and watched it part-way, then lost sight
    of the printer. Meanwhile #100 ran out; Derek weighed a fresh #300 on the Quick-Weigh (0 g
    used) and loaded it on XL-1 at the prompt. FCC sees the printer idle again with #300 on XL-1."""
    gcode, cut = _cancelled_gcode()
    now = time.time()
    seen, back = now - 9000, now - 60
    weigh_stamps.note(300, "Quick Weigh", at=seen + 1800)        # weighed BEFORE it was loaded
    end = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 300, "sids": [300], "used": {"300": 0.0}},
                     {"toolhead": "XL-2", "position": 1, "sid": 200, "sids": [200], "used": {"200": 50.0}}],
           "source": "back", "at": back}
    lost = {"progress": cut, "seen_at": seen, "lost_at": seen + 10, "back_at": back, "back_state": "IDLE",
            "why": "lost"}
    ctx = _preview_ctx(gcode, TWO, SPOOLS, {"XL-1": [300], "XL-2": [200]}, {"updates": []})
    ctx.append(patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                            side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f, "remap": lambda p: p}))
    ctx.append(patch.object(print_deduct.state, "add_log_entry", lambda *a, **k: None))
    _start(ctx)
    try:
        with _spoolman({100: 100.0, 200: 50.0, 300: 0.0}):
            app_module._create_pending_cancel_review("XL", "f.gcode", "J-1", cut, fb_url="http://fb",
                                                     ambiguous=True, end_heads=end,
                                                     start_spools={"0": 100, "1": 200}, lost_contact=lost)
    finally:
        _stop(ctx)
    return cancel_review_store.get_pending("XL", "J-1")


def test_a_sets_spool_loaded_unseen_never_takes_the_start_spools_seen_share(logs):
    card = _set_card()
    with _spoolman({100: 100.0, 200: 50.0, 300: 0.0}):
        ans = _recompute(rev=card.get("rev", 0), whole=True)     # Charge the whole print
    rec = ans.get("record") or {}
    lines = rec.get("unresolved_usage") or rec.get("usage_map")
    line = float(lines["0"])
    charges = [{"position": 0, "sid": 100, "grams": round(line - 15.0, 2)},   # #100 ran out part-way
               {"position": 0, "sid": 300, "grams": 15.0}]                    # #300 printed the rest
    charges += [{"row": r["sid"], "sid": r["sid"], "grams": r["grams"]} for r in rec.get("spools") or []]
    if rec.get("kind") == "no_spool":
        charges += [{"position": int(k), "sid": 200, "grams": float(v)} for k, v in lines.items() if str(k) == "1"]
    with _spoolman({100: 100.0, 200: 50.0, 300: 0.0}):
        out = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-1", "rev": rec.get("rev"), "charges": charges}).get_json()
    kept = cancel_review_store.get_pending("XL", "J-1") or {}
    row300 = next((r for r in kept.get("spools") or [] if r.get("sid") == 300), None) or {}
    w = row300.get("weighed") or {}
    assert 300 in {h.get("sid") for h in out.get("held") or []}, out
    assert not w.get("seen") and w.get("known_order") is False and row300.get("prefill") == 15.0, row300


def test_the_seen_share_is_only_the_spool_fcc_saw_on_the_head():
    row = {"sid": 300, "position": 0, "grams": 15.0}
    figures = {"footer": {"0": 40.0}, "by_pct": {"0": [round(0.4 * i, 4) for i in range(101)]}}
    # FCC saw #100 on XL-1 (its start), no swap recorded by the progress it last saw (50 %).
    assert print_deduct._seen_share_on_head(row, 300, 1.0, 0.5, figures, {"0": 100}, []) == 0.0
    assert print_deduct._seen_share_on_head(dict(row, sid=100), 100, 1.0, 0.5, figures, {"0": 100}, []) == 15.0
    # A swap FCC recorded at 30 % put #300 on: by 50 % FCC saw #300 on the head.
    swap = [{"seq": 0, "position": "0", "progress": 0.3, "from_sid": 100, "to_sid": 300}]
    assert print_deduct._seen_share_on_head(row, 300, 1.0, 0.5, figures, {"0": 100}, swap) == 15.0
    # No start snapshot: FCC can't say which spool printed what it saw.
    assert print_deduct._seen_share_on_head(dict(row, sid=100), 100, 1.0, 0.5, figures, None, []) == 0.0


def test_a_swapped_off_spool_weighed_before_fcc_saw_a_late_park_is_marked_unsure():
    now = time.time()
    unseen_from, at = now - 3600, now - 600
    swap = [{"seq": 0, "position": "0", "progress": 0.45, "from_sid": 100, "to_sid": 200,
             "at": at, "unseen_from": unseen_from}]
    weigh_stamps.note(100, "Quick Weigh", at=at - 300)               # at the prompt, before FCC saw it
    rows = [{"sid": 100, "toolhead": "XL-1", "position": 0, "grams": 23.0}]
    print_deduct._mark_weighed_rows(rows, [], None, print_deduct._swap_left_at(swap), None, None,
                                    left_unseen=print_deduct._swap_left_unseen(swap))
    mark = rows[0].get("weighed") or {}
    assert mark.get("unseen") and mark.get("known_order") is False and rows[0]["prefill"] == 23.0, rows
    assert "before it first saw this print, at its park" in mark["words"], mark


def test_a_swapped_off_spool_weighed_after_fcc_saw_a_late_park_keeps_its_left_mark():
    now = time.time()
    unseen_from, at = now - 3600, now - 600
    swap = [{"seq": 0, "position": "0", "progress": 0.45, "from_sid": 100, "to_sid": 200,
             "at": at, "unseen_from": unseen_from}]
    weigh_stamps.note(100, "Quick Weigh", at=at + 60)                # after FCC saw the park
    rows = [{"sid": 100, "toolhead": "XL-1", "position": 0, "grams": 23.0}]
    print_deduct._mark_weighed_rows(rows, [], None, print_deduct._swap_left_at(swap), None, None,
                                    left_unseen=print_deduct._swap_left_unseen(swap))
    mark = rows[0].get("weighed") or {}
    assert mark.get("left") and mark.get("known_order") is True and rows[0]["prefill"] == 0.0, rows
