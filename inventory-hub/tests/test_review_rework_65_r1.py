"""Group 65 review, round 1: working a 🛑 card out again (65.1 (1b) / (1c)), the server.
Offline.

  - RW4 / CM2 (red): a head first used past the point FCC saw is judged by the builder's
    own rule (Derek's D1: a change during the print always asks), from the start snapshot
    and swap log the card now keeps: its spool changed (an end FCC saw only after it lost
    sight of the print, a spool put on for the next job) makes it a held set with the
    builder's note and the start spool offered, never a row pre-filled with the spool on
    it now. An unchanged head is a row, as the builder makes it; a card that kept no
    snapshot gives such a head a line.
  - CM1: a head split at its swaps on a real card (its last stretch ends at the card's
    progress, not at the print's end) is worked out again, the run-out remnant left out
    of the walk's grams before its last stretch.
  - CM3 / OR7: a set's note, and a weighed row's mark, name the new grams; a row the
    rescale adds for a spool FCC weighed after the print ended is marked before Confirm.
  - OR2: a recompute never takes its card out of the store: a Discard or another tab's
    Apply while it works acts on the card it finds, and the recompute says so.
  - RW6 / PI5: after an Apply that charged nothing and still holds its whole ask (a
    Decision 1 hold), the card can be worked out again; otherwise the refusal says what
    happened (charged, a write that may have landed, a spool held or settled), and the
    pending list says it for each card with figures.
  - CM6 / RW5: an end FCC never sampled is said as "FCC never read its progress"; the
    "couldn't measure" card's figures line offers a percentage only when it can.
  - OR1 (red): a "couldn't measure" card keeps its end moment, and its Apply holds a pick
    FCC weighed after it at 0 g, as a card built from a print-end read does.

Red on 681601f6 (the reviewed head), all but one: an unchanged head's row
(test_a_head_whose_spool_stayed_the_same_is_a_row_as_the_builder_makes_it) is a guard
that the fix keeps the builder's own row, green there too.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest

import app as app_module
import cancel_fetch_store
import cancel_review_store
import print_deduct
import print_deduct_ledger
import print_monitor
import spoolman_api
import weigh_stamps
from spoolman_extra_fake import SpoolmanHTTPFake
from test_cancel_review import _cancelled_gcode, _preview_ctx


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    monkeypatch.setattr(print_deduct.stock_report, "check_after_deduct", lambda *a, **k: None)


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(print_deduct.state, "add_log_entry", lambda msg, *a, **k: calls.append(msg))
    return calls


TWO = {"XL-1": {"printer_name": "XL", "position": 0}, "XL-2": {"printer_name": "XL", "position": 1}}


def _start(ctx):
    for m in ctx:
        m.start()


def _stop(ctx):
    for m in reversed(ctx):
        m.stop()


@contextmanager
def _spoolman(spools):
    """A Spoolman over HTTP ({id: used_weight}): the rescale's reads (a new row's spool, a
    set's spools) and Decision 1's list read all go through it."""
    sm = SpoolmanHTTPFake()
    for sid, used in spools.items():
        sm.add("spool", sid, location="", used_weight=used, initial_weight=1000.0, archived=False,
               filament={"weight": 1000.0})
    ctx = [patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
           patch.object(spoolman_api, "format_spool_display",
                        return_value={"text": "#s", "color": "ff0000", "slot": "", "details": {}}),
           patch.object(spoolman_api.requests, "get", side_effect=sm.get),
           patch.object(spoolman_api.requests, "patch", side_effect=sm.patch)]
    _start(ctx)
    try:
        yield sm
    finally:
        _stop(ctx)


def _recompute(job="J-1", **body):
    return app_module.app.test_client().post(
        "/api/cancel_deduct/recompute", json=dict({"printer_name": "XL", "job_id": job}, **body)).get_json()


# --------------------------------------------------------------------------- #
# RW4 / CM2: a head first used past the point FCC saw                          #
# --------------------------------------------------------------------------- #

SPOOLS = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
          200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0},
          300: {"id": 300, "used_weight": 0.0, "initial_weight": 1000.0}}


def _lost_card(end_sid):
    """FCC saw an XL print start (XL-1 #100, XL-2 #200), lost contact at ~25% while only
    XL-1 had printed, and saw the printer idle again with `end_sid` on XL-2: the real
    builder's card (65.1's own case, RW4's scenario)."""
    gcode, cut = _cancelled_gcode()
    now = time.time()
    end = {"heads": [{"toolhead": "XL-1", "position": 0, "sid": 100, "sids": [100], "used": {"100": 100.0}},
                     {"toolhead": "XL-2", "position": 1, "sid": end_sid, "sids": [end_sid],
                      "used": {str(end_sid): SPOOLS[end_sid]["used_weight"]}}],
           "source": "back", "at": now - 60}
    lost = {"progress": cut, "seen_at": now - 9000, "lost_at": now - 8990, "back_at": now - 60,
            "back_state": "IDLE", "why": "lost"}
    ctx = _preview_ctx(gcode, TWO, SPOOLS, {"XL-1": [100], "XL-2": [end_sid]}, {"updates": []})
    ctx.append(patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                            side_effect=lambda ip, key, fn, f: {"gcode": gcode, "fraction": f, "remap": lambda p: p}))
    ctx.append(patch.object(print_deduct.state, "add_log_entry", lambda *a, **k: None))
    _start(ctx)
    try:
        app_module._create_pending_cancel_review("XL", "f.gcode", "J-1", cut, fb_url="http://fb", ambiguous=True,
                                                 end_heads=end, start_spools={"0": 100, "1": 200}, lost_contact=lost)
    finally:
        _stop(ctx)
    return cancel_review_store.get_pending("XL", "J-1")


def test_a_head_whose_spool_changed_unseen_is_a_set_never_a_row_for_the_spool_on_it_now(logs):
    card = _lost_card(300)
    assert [r["sid"] for r in card["spools"]] == [100] and not card.get("unresolved_usage"), card
    with _spoolman({100: 100.0, 200: 50.0, 300: 0.0}):
        ans = _recompute(rev=card.get("rev", 0), whole=True)
    assert ans["status"] == "recomputed", ans
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert [(r["sid"], r["grams"]) for r in rec["spools"]] == [(100, 40.0)], rec["spools"]
    assert rec["unresolved_usage"] == {"1": 32.0}, rec
    assert [(m["sid"], m["when"]) for m in rec["unresolved_sets"]["1"]] == [(200, "start"), (300, "end")], rec
    assert rec["unresolved_notes"]["1"] == ("FCC saw #200 when the print started and #300 when FCC saw the "
                                            "printer again, but not when it changed: split the 32 g between them, "
                                            "or put it all on one."), rec["unresolved_notes"]
    assert {"toolhead": "XL-2", "position": 1, "sid": 200, "when": "start"} in rec["heads_at_end"], rec


def test_a_head_whose_spool_stayed_the_same_is_a_row_as_the_builder_makes_it(logs):
    card = _lost_card(200)
    with _spoolman({100: 100.0, 200: 50.0}):
        ans = _recompute(rev=card.get("rev", 0), whole=True)
    assert ans["status"] == "recomputed", ans
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert [(r["sid"], r["grams"]) for r in rec["spools"]] == [(100, 40.0), (200, 32.0)], rec["spools"]
    assert not rec.get("unresolved_usage") and not rec.get("unresolved_sets"), rec


def _card(**more):
    rec = {"printer_name": "XL", "job_id": "J-1", "filename": "f.bgcode", "progress": 0.3, "kind": "partial",
           "ambiguous": True, "total_grams": 12.0, "created": "2026-11-23 00:00:00",
           "spools": [{"sid": 57, "toolhead": "XL-1", "position": 0, "grams": 12.0, "current_used": 100.0,
                       "initial_weight": 1000.0, "remaining_before": 900.0, "remaining_after": 888.0,
                       "display": "#57", "color": "ff0000", "ambiguous": False}],
           "heads_at_end": [{"toolhead": "XL-1", "position": 0, "sid": 57, "sids": [57]},
                            {"toolhead": "XL-2", "position": 1, "sid": 58, "sids": [58]}],
           "figures": {"footer": {"0": 40.0, "1": 20.0},
                       "by_pct": {"0": [round(0.4 * i, 4) for i in range(101)],
                                  "1": [0.0 if i < 50 else round(0.4 * (i - 50), 4) for i in range(101)]}}}
    rec.update(more)
    cancel_review_store.add_pending(rec)
    return rec


def test_a_card_that_kept_no_start_snapshot_gives_such_a_head_a_line_never_a_row(logs):
    _card()
    with _spoolman({57: 100.0, 58: 50.0}):
        ans = _recompute(rev=0, whole=True)
    rec = ans["record"]
    assert [r["sid"] for r in rec["spools"]] == [57] and rec["unresolved_usage"] == {"1": 20.0}, rec
    assert rec["unresolved_notes"]["1"] == ("FCC hadn't seen XL-2 print when it last saw this print, and this card "
                                            "keeps no record of the spools it had then: pick the spool it used."), rec


# --------------------------------------------------------------------------- #
# CM1: a real split card's last stretch                                        #
# --------------------------------------------------------------------------- #

def _split_card():
    """Job 1141's shape: #42 ran out on XL-1 at 19% (its stretch 16.86 g walked, plus the
    printer's 2 g remnant), #229 went on, and the print ended at ~42% (the builder ends the
    last stretch at the card's progress, never at None)."""
    by4 = [round(min(i, 19) * 16.86 / 19 + max(0, i - 19) * (84.28 - 16.86) / 81, 4) for i in range(101)]
    return _card(progress=0.42, spools=[
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


def test_a_split_heads_last_stretch_ending_at_the_cards_progress_moves_without_the_remnant(logs, monkeypatch):
    monkeypatch.setattr(print_deduct, "_path_filament_g", lambda printer: 2.0)
    _split_card()
    with _spoolman({42: 900.0, 229: 10.0}):
        ans = _recompute(rev=0, whole=True)
    assert ans["status"] == "recomputed", ans
    by = {r["sid"]: r for r in ans["record"]["spools"]}
    assert by[42]["grams"] == 18.86, by[42]                     # its stretch and remnant stay
    assert by[229]["grams"] == 67.42 and by[229]["segments"][0]["to"] is None, by[229]   # 84.28 - 16.86
    with _spoolman({42: 900.0, 229: 10.0}):
        ans = _recompute(rev=1, percent=10)
    assert ans["status"] == "error" and "spool was changed later in the print" in ans["msg"], ans


# --------------------------------------------------------------------------- #
# CM3 / OR7: words and marks at the new grams                                  #
# --------------------------------------------------------------------------- #

def test_a_sets_note_names_its_new_grams(logs):
    note = ("FCC saw #42 when the print started and #229 when the print ended, but not when it changed: "
            "split the 8 g between them, or put it all on one.")
    _card(spools=[], unresolved_usage={"1": 8.0}, unresolved_notes={"1": note},
          unresolved_sets={"1": [{"sid": 42, "when": "start"}, {"sid": 229, "when": "end"}]},
          start_spools={"0": 57, "1": 42}, swap_log=[], kind="partial")
    with _spoolman({57: 100.0, 42: 100.0, 229: 10.0}):
        ans = _recompute(rev=0, whole=True)
    assert ans["record"]["unresolved_usage"] == {"1": 20.0}, ans
    assert ans["record"]["unresolved_notes"]["1"] == note.replace("split the 8 g", "split the 20 g"), ans


def test_a_weighed_rows_words_and_a_new_rows_mark_follow_the_new_grams(logs):
    end_at = time.time() - 3600
    _card(end_at_s=end_at, heads_source="print_end", start_spools={"0": 57, "1": 58}, swap_log=[],
          heads_at_end=[{"toolhead": "XL-1", "position": 0, "sid": 57, "sids": [57], "used": {"57": 100.0}},
                        {"toolhead": "XL-2", "position": 1, "sid": 58, "sids": [58], "used": {"58": 50.0}}])
    weigh_stamps.note(57, "Quick Weigh", at=end_at + 600)
    weigh_stamps.note(58, "Quick Weigh", at=end_at + 1800)
    with _spoolman({57: 160.0, 58: 70.0}):
        ans = _recompute(rev=0, whole=True)
    by = {r["sid"]: r for r in ans["record"]["spools"]}
    assert (by[57]["grams"], by[57]["prefill"]) == (40.0, 0.0), by[57]
    assert by[57]["weighed"]["words"].endswith("so the scale already counted its 40.00 g"), by[57]
    assert (by[58]["grams"], by[58]["prefill"]) == (20.0, 0.0), by[58]
    assert by[58]["weighed"]["words"].endswith("so the scale already counted its 20.00 g"), by[58]


# --------------------------------------------------------------------------- #
# OR2: a recompute never takes its card out of the store                       #
# --------------------------------------------------------------------------- #

def _racing(meanwhile):
    """A recompute that reads Spoolman for a new head's row, and `meanwhile` run at that
    moment (another request on the same card)."""
    _card(start_spools={"0": 57, "1": 58}, swap_log=[])
    seen = {}
    real = print_deduct._new_row_for

    def _slow(*a, **k):
        seen.setdefault("answer", meanwhile(app_module.app.test_client()))
        return real(*a, **k)
    with _spoolman({57: 100.0, 58: 50.0}), patch.object(print_deduct, "_new_row_for", side_effect=_slow):
        ans = _recompute(rev=0, whole=True)
    return ans, seen.get("answer")


def test_a_discard_while_a_recompute_works_discards_the_card_and_the_recompute_says_so(logs):
    ans, discard = _racing(lambda c: c.post("/api/cancel_deduct/dismiss",
                                            json={"printer_name": "XL", "job_id": "J-1"}).get_json())
    assert discard == {"status": "dismissed"}, discard
    assert ans == {"status": "already_handled"}, ans
    assert cancel_review_store.get_pending("XL", "J-1") is None
    assert print_deduct_ledger.was_deducted("XL", "J-1")


def test_another_tabs_apply_while_a_recompute_works_is_applied_and_the_recompute_says_so(logs):
    ans, apply = _racing(lambda c: c.post("/api/cancel_deduct/confirm", json={
        "printer_name": "XL", "job_id": "J-1", "rev": 0, "updates": {"57": 12.0}}).get_json())
    assert apply["status"] == "confirmed", apply
    assert ans == {"status": "already_handled"}, ans
    assert print_deduct_ledger.was_deducted("XL", "J-1")


# --------------------------------------------------------------------------- #
# RW6 / PI5: after an Apply                                                    #
# --------------------------------------------------------------------------- #

def test_after_an_apply_that_only_held_its_row_the_card_can_be_worked_out_again(logs):
    _card(start_spools={"0": 57, "1": 58}, swap_log=[])
    late = {"sid": 57, "toolhead": "XL-1", "then": 100.0, "now": 160.0, "ours": 0.0,
            "stamp": {"at": time.time() - 10, "how": "Quick Weigh"}, "ended": time.time() - 100,
            "source": "print_end"}
    with _spoolman({57: 160.0, 58: 50.0}), patch.object(print_deduct, "_held_at_apply", return_value=late):
        held = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-1", "rev": 0, "updates": {"57": 12.0}}).get_json()
    assert held["applied"] == [] and held.get("held"), held
    kept = cancel_review_store.get_pending("XL", "J-1")
    assert kept["requested_total"] is not None and float(kept.get("applied_g") or 0) == 0.0, kept
    with _spoolman({57: 160.0, 58: 50.0}):
        ans = _recompute(rev=kept["rev"], whole=True)
    assert ans["status"] == "recomputed", ans
    assert "requested_total" not in ans["record"] and "requested_keys" not in ans["record"], ans
    assert [r["grams"] for r in ans["record"]["spools"]] == [40.0, 20.0], ans


@pytest.mark.parametrize("more,words", [
    ({"requested_total": 15.0, "applied_g": 4.0}, "4.00g of this print is already charged"),
    ({"requested_total": 15.0, "applied_g": 0.0,
      "spools": [{"sid": 57, "position": 0, "grams": 12.0, "attempt_used_before": 100.0,
                  "attempt_used_after": 112.0}]}, "write may still have landed"),
    ({"requested_total": 15.0, "applied_g": 0.0, "requested_keys": ["0:57", "1:58"]}, "held or settled a spool"),
], ids=["charged", "write may have landed", "held or settled"])
def test_the_refusal_after_an_apply_says_what_happened(more, words):
    before = _card(**more)
    ans = _recompute(rev=0, whole=True)
    assert ans["status"] == "error" and words in ans["msg"], ans
    assert cancel_review_store.get_pending("XL", "J-1") == before
    pending = app_module.app.test_client().get("/api/cancel_deduct/pending").get_json()["pending"]
    assert words in pending[0]["rework_refused"], pending


def test_the_pending_list_says_a_card_can_be_worked_out_again():
    _card()
    (rec,) = app_module.app.test_client().get("/api/cancel_deduct/pending").get_json()["pending"]
    assert "rework_refused" in rec and rec["rework_refused"] is None, rec


# --------------------------------------------------------------------------- #
# CM6 / RW5 / OR1: the "couldn't measure" card                                 #
# --------------------------------------------------------------------------- #

FOOT = "; filament used [mm] = 10, 10\n; filament used [g] = 10, 10\n"
GOOD = "M83\nT0\n" + "G1 E1\n" * 10 + "T1\n" + "G1 E1\n" * 10 + FOOT
UNREADABLE = "M83\nT0\nG5 E10\nT1\nG5 E10\n" + FOOT


def _unsampled(gcode):
    ctx = [patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
           patch.object(app_module.locations_db, "get_active_printer_map", return_value=TWO),
           patch.object(app_module.prusalink_api, "fetch_printer_credentials",
                        return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
           patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                        side_effect=lambda ip, key, fn, f, **k: {"gcode": gcode, "fraction": f, "remap": lambda p: p})]
    _start(ctx)
    try:
        app_module._create_pending_cancel_review("XL", "/usb/A.BGC", "J-1", 0.0, fb_url="http://fb", ambiguous=True,
                                                 progress_unknown=True, unmeasured_reason="unsampled")
    finally:
        _stop(ctx)
    return cancel_review_store.get_pending("XL", "J-1")


def test_an_end_fcc_never_sampled_says_it_never_read_its_progress(logs):
    card = _unsampled(GOOD)
    ans = _recompute(rev=card["rev"], whole=True)
    assert ans["record"]["seen_progress"] is None, ans
    assert logs[-1].startswith("📝 XL: job J-1's review worked out again for the whole print (FCC never read its "
                               "progress): 20.00g"), logs
    spools = {57: {"id": 57, "used_weight": 100.0, "initial_weight": 1000.0},
              58: {"id": 58, "used_weight": 50.0, "initial_weight": 1000.0}}
    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: dict(spools[int(sid)])), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=lambda sid, data: {"id": sid, **data}), \
         patch.object(app_module.spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "f00"}):
        ok = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-1", "rev": ans["record"]["rev"],
            "charges": [{"position": "0", "sid": 57, "grams": 10.0}, {"position": "1", "sid": 58, "grams": 10.0}]})
    assert ok.get_json()["status"] == "confirmed", ok.get_json()
    assert any(m.endswith("as its review was worked out again (FCC never read its progress).") for m in logs), logs


def test_a_footer_only_files_line_offers_no_percentage(logs):
    _unsampled(UNREADABLE)
    assert logs[-1] == ("📝 XL: read '/usb/A.BGC' for its review: Charge the whole print can now be worked out on "
                        "its card (FCC can't read this file's moves, so not a percentage)."), logs


def test_a_couldnt_measure_cards_apply_holds_a_spool_fcc_weighed_after_its_end(logs):
    card = _unsampled(GOOD)
    assert card.get("end_at_s") is not None, card
    weigh_stamps.note(57, "Quick Weigh", at=float(card["end_at_s"]) + 60)
    ans = _recompute(rev=card["rev"], whole=True)
    spools = {57: {"id": 57, "used_weight": 110.0, "initial_weight": 1000.0},
              58: {"id": 58, "used_weight": 50.0, "initial_weight": 1000.0}}
    writes = []
    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: dict(spools[int(sid)])), \
         patch.object(app_module.spoolman_api, "update_spool",
                      side_effect=lambda sid, data: writes.append((sid, data)) or {"id": sid, **data}), \
         patch.object(app_module.spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "f00"}):
        ok = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-1", "rev": ans["record"]["rev"],
            "charges": [{"position": "0", "sid": 57, "grams": 10.0}, {"position": "1", "sid": 58, "grams": 10.0}]}
                                               ).get_json()
    assert [h["sid"] for h in ok.get("held") or []] == [57], ok
    assert all(int(sid) != 57 for sid, _data in writes), writes
    assert "the scale already counted its 10.00 g" in ok["held"][0]["words"], ok
