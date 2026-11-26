"""Group 65 fix review, round 1: working a 🛑 card out again, the server. Offline.

  - RC1 / AD1 / RC4 (in test_review_rework_65_r1.py): every card an Apply kept is refused,
    in words that say what that Apply did.
  - AD2 (orange): a print FCC never snapshotted (no start snapshot, or an empty one) keeps
    no snapshot on its card, so a head first used past the point FCC saw gets a line to
    pick on, never a row pre-filled with the spool on it now.
  - RC2: a split head's last stretch leaves out the run-out remnant the card was built with,
    never the setting as it is now.
  - AD3 / RC3: a card worked out at a percentage typed with three decimals can be worked out
    again (its progress and its last stretch's end in one form).
  - RC5: on a "couldn't measure" card FCC saw only after losing contact, a spool weighed
    while FCC couldn't see the print is held unsure, the print's grams filled in; one
    weighed after FCC saw the printer again is held as counted (0 g).

Red on fddf1ceb (the fix review's head).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

import app as app_module
import cancel_review_store
import print_deduct
import weigh_stamps
from test_cancel_review import _cancelled_gcode, _preview_ctx
from test_review_rework_65_r1 import (  # noqa: F401  (_iso: the autouse isolation)
    GOOD, SPOOLS, TWO, _card, _iso, _recompute, _spoolman, _start, _stop, logs)


# --------------------------------------------------------------------------- #
# AD2: no snapshot is no snapshot                                              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("start", [None, {}], ids=["never taken", "empty (a blip at the start)"])
def test_a_card_whose_print_had_no_start_snapshot_gives_a_new_head_a_line(logs, start):
    gcode, cut = _cancelled_gcode()
    now = time.time()
    end = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 100, "sids": [100], "used": {"100": 100.0}},
                     {"toolhead": "XL-2", "position": 1, "sid": 300, "sids": [300], "used": {"300": 0.0}}],
           "source": "back", "at": now - 60}
    lost = {"progress": cut, "seen_at": now - 9000, "lost_at": now - 8990, "back_at": now - 60,
            "back_state": "IDLE", "why": "lost"}
    ctx = _preview_ctx(gcode, TWO, SPOOLS, {"XL-1": [100], "XL-2": [300]}, {"updates": []})
    ctx.append(patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                            side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f, "remap": lambda p: p}))
    ctx.append(patch.object(print_deduct.state, "add_log_entry", lambda *a, **k: None))
    _start(ctx)
    try:
        app_module._create_pending_cancel_review("XL", "f.gcode", "J-1", cut, fb_url="http://fb", ambiguous=True,
                                                 end_heads=end, start_spools=start, lost_contact=lost)
    finally:
        _stop(ctx)
    card = cancel_review_store.get_pending("XL", "J-1")
    assert "start_spools" not in card, card
    with _spoolman({100: 100.0, 300: 0.0}):
        ans = _recompute(rev=card.get("rev", 0), whole=True)
    rec = ans["record"]
    assert [r["sid"] for r in rec["spools"]] == [100] and rec["unresolved_usage"] == {"1": 32.0}, rec
    assert rec["unresolved_notes"]["1"].startswith("#300 was on XL-2 when FCC saw the printer again, but FCC has "
                                                   "no record of the spool XL-2 had when the print started"), rec


# --------------------------------------------------------------------------- #
# RC2 / AD3: a split head's last stretch                                       #
# --------------------------------------------------------------------------- #

def _split(path_g):
    by4 = [round(min(i, 19) * 16.86 / 19 + max(0, i - 19) * (84.28 - 16.86) / 81, 4) for i in range(101)]
    return _card(progress=0.42, path_g=path_g, spools=[
        {"sid": 42, "toolhead": "XL-1", "position": 0, "grams": 18.86, "current_used": 900.0,
         "initial_weight": 1000.0, "remaining_before": 100.0, "remaining_after": 81.1, "display": "#42",
         "color": "f00", "runout": True, "auto_split": True,
         "segments": [{"from": None, "to": 0.19, "runout": True, "grams": 18.86}]},
        {"sid": 229, "toolhead": "XL-1", "position": 0, "grams": 19.14, "current_used": 10.0,
         "initial_weight": 1000.0, "remaining_before": 990.0, "remaining_after": 970.9, "display": "#229",
         "color": "0f0", "auto_split": True,
         "segments": [{"from": 0.19, "to": 0.42, "runout": False, "grams": 19.14}]}],
        heads_at_end=[{"toolhead": "XL-1", "position": 0, "sid": 229, "sids": [229]}],
        figures={"footer": {"0": 84.28}, "by_pct": {"0": by4}}, start_spools={"0": 42}, swap_log=[])


def test_the_last_stretch_leaves_out_the_remnant_the_card_was_built_with(logs, monkeypatch):
    _split(path_g=2.0)
    monkeypatch.setattr(print_deduct, "_path_filament_g", lambda printer: 5.0)      # changed since
    with _spoolman({42: 900.0, 229: 10.0}):
        ans = _recompute(rev=0, whole=True)
    by = {r["sid"]: r["grams"] for r in ans["record"]["spools"]}
    assert by == {42: 18.86, 229: 67.42}, by


def test_a_card_worked_out_at_three_decimals_can_be_worked_out_again(logs):
    _split(path_g=2.0)
    with _spoolman({42: 900.0, 229: 10.0}):
        first = _recompute(rev=0, percent=42.345)
        second = _recompute(rev=1, whole=True)
    assert first["status"] == "recomputed" and second["status"] == "recomputed", (first, second)
    assert {r["sid"]: r["grams"] for r in second["record"]["spools"]} == {42: 18.86, 229: 67.42}, second


# --------------------------------------------------------------------------- #
# RC5: a weighing FCC can't place against the print                            #
# --------------------------------------------------------------------------- #

def test_a_spool_weighed_while_fcc_couldnt_see_the_print_is_held_unsure(logs):
    now = time.time()
    seen, back = now - 9000, now - 600
    ctx = [patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
           patch.object(app_module.locations_db, "get_active_printer_map", return_value=TWO),
           patch.object(app_module.prusalink_api, "fetch_printer_credentials",
                        return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
           patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                        side_effect=lambda ip, key, fn, f, **k: {"gcode": GOOD, "fraction": f, "remap": lambda p: p})]
    _start(ctx)
    try:
        app_module._create_pending_cancel_review(
            "XL", "/usb/A.BGC", "J-1", 0.0, fb_url="http://fb", ambiguous=True, progress_unknown=True,
            unmeasured_reason="unsampled",
            lost_contact={"progress": 0.0, "seen_at": seen, "lost_at": seen + 10, "back_at": back,
                          "back_state": "IDLE", "why": "lost"})
    finally:
        _stop(ctx)
    card = cancel_review_store.get_pending("XL", "J-1")
    assert (card["end_at_s"], card["end_back_at_s"], card["end_at_source"]) == (seen, back, "seen"), card
    weigh_stamps.note(57, "Quick Weigh", at=seen + 3600)          # while FCC couldn't see the print
    weigh_stamps.note(58, "Quick Weigh", at=back + 60)            # after FCC saw the printer again
    ans = _recompute(rev=card["rev"], whole=True)
    spools = {57: {"id": 57, "used_weight": 110.0, "initial_weight": 1000.0},
              58: {"id": 58, "used_weight": 60.0, "initial_weight": 1000.0}}
    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: dict(spools[int(sid)])), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=lambda sid, data: {"id": sid, **data}), \
         patch.object(app_module.spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "f00"}):
        ok = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-1", "rev": ans["record"]["rev"],
            "charges": [{"position": "0", "sid": 57, "grams": 10.0}, {"position": "1", "sid": 58, "grams": 10.0}]}
                                               ).get_json()
    held = {h["sid"]: h for h in ok.get("held") or []}
    assert held[57]["known_order"] is False and "FCC can't tell whether the scale counted" in held[57]["words"], ok
    assert held[58]["known_order"] is True and "the scale already counted its 10.00 g" in held[58]["words"], ok
    kept = {r["sid"]: r for r in cancel_review_store.get_pending("XL", "J-1")["spools"]}
    assert (kept[57]["prefill"], kept[58]["prefill"]) == (10.0, 0.0), kept
