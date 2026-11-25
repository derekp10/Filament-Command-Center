"""Group 65.1 (1b) (Derek, 2026-11-09: "the 30% last seen is the real issue, we should have
a charge the whole print, or a way to change the percentage"), the server. Offline.

The figures: a review that may have gone further than FCC saw (an ambiguous end, a cancel
FCC saw after it lost contact, a restart's review) keeps, from its one download and walk,
every head's grams at each whole percent and its footer ({"footer", "by_pct"}). A plain
cancel keeps none, and a download stand-in with no `remap` gives none.

The recompute, POST /api/cancel_deduct/recompute {printer_name, job_id, rev, percent |
whole}: the card is worked out again from its figures, its own rows and lines kept (never
a spool read from the heads now): one row takes the new figure, a head split at its swaps
moves only the stretch ending at the print's end (a basis before that stretch began is
refused), a line takes its new total, a head with grams only at the new basis gets a row
for the one spool the print-end read found there, else a line; `progress` is the basis,
`seen_progress` what FCC saw, `basis` "whole" or the percent, `rev` one up. Refused, the
card left as it was: a stale rev, no figures, a card part-applied, an uncharged-grams
card, a percentage outside 0-100 (400, the card untouched). The Apply after it records
the basis as the ledger's scale, says it in its line, and an older view is refused.

Red on 5b97b2d4 (no figures, no route).
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

import app as app_module
import cancel_fetch_store
import cancel_review_store
import print_deduct
import print_deduct_ledger
import print_monitor
import prusalink_api
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
FOOT = "; filament used [mm] = 10, 10\n; filament used [g] = 10, 10\n"


def _figs(gcode, frac, pm=TWO, remap=True):
    figs = {}
    fetch = (lambda ip, key, fn, f: {"gcode": gcode, "fraction": f, "remap": lambda p: p}) if remap \
        else (lambda ip, key, fn, f: {"gcode": gcode, "fraction": f})
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch), \
         patch.object(print_deduct.state, "add_log_entry", lambda *a, **k: None):
        usage, terminal = print_deduct._compute_cancel_usage("XL", "f.gcode", "J", frac, "1.2.3.4", "k",
                                                            figures_out=figs)
    return usage, terminal, figs


# --------------------------------------------------------------------------- #
# The figures                                                                  #
# --------------------------------------------------------------------------- #

def test_every_whole_percent_from_the_one_walk():
    g = "M83\nT0\n" + "G1 E1\n" * 10 + "T1\n" + "G1 E1\n" * 10 + FOOT
    usage, terminal, figs = _figs(g, 0.5)
    assert terminal is None and figs["footer"] == {"0": 10.0, "1": 10.0}, figs
    for pos in ("0", "1"):
        vals = figs["by_pct"][pos]
        assert len(vals) == 101 and vals[0] == 0.0 and vals[100] == 10.0, vals
        assert all(b >= a for a, b in zip(vals, vals[1:])), vals            # never goes back
    # The card's grams at the cut FCC saw are the partial's own, and the figure at that
    # percent is the same cut.
    assert {str(k): v for k, v in usage.items()} == {p: figs["by_pct"][p][50] for p in ("0", "1") if
                                                     figs["by_pct"][p][50] > 0}, (usage, figs)


def test_a_download_with_no_remap_keeps_no_figures():
    _usage, _terminal, figs = _figs("M83\nT0\nG1 E10\nT1\nG1 E10\n" + FOOT, 0.5, remap=False)
    assert figs == {}


def test_a_one_head_printers_lone_tool_is_keyed_by_its_position():
    g = "M83\nT1\nG1 E10\n; filament used [mm] = 0, 10\n; filament used [g] = 0, 10\n"
    _usage, _terminal, figs = _figs(g, 0.5, pm={"CORE1": {"printer_name": "XL", "position": 0}})
    assert set(figs["footer"]) == {"0"} and set(figs["by_pct"]) == {"0"}, figs


def test_a_head_the_walk_cant_see_keeps_its_footer_and_zeros():
    g = "M83\nT0\nG1 E10\nT1\nG5 E10\n" + FOOT
    _usage, _terminal, figs = _figs(g, 0.9)
    assert figs["footer"]["1"] == 10.0 and set(figs["by_pct"]["1"]) == {0.0}, figs


def _review(ambiguous=False, lost_contact=None, remap=True):
    gcode, frac = _cancelled_gcode()
    ctx = _preview_ctx(gcode, TWO, {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}},
                       {"XL-1": [100]}, {"updates": []})
    fetch = (lambda ip, key, fn, f: {"gcode": gcode, "fraction": f, "remap": lambda p: p}) if remap \
        else (lambda ip, key, fn, f: {"gcode": gcode, "fraction": f})
    ctx.append(patch.object(app_module.prusalink_api, "fetch_cancel_gcode", side_effect=fetch))
    ctx.append(patch.object(print_deduct.state, "add_log_entry", lambda *a, **k: None))
    for m in ctx:
        m.start()
    try:
        app_module._create_pending_cancel_review("XL", "f.gcode", "J-1", frac, fb_url="http://fb",
                                                 ambiguous=ambiguous, lost_contact=lost_contact)
    finally:
        for m in reversed(ctx):
            m.stop()
    return cancel_review_store.get_pending("XL", "J-1")


@pytest.mark.parametrize("ambiguous,lost,kept", [(True, None, True), (False, {"progress": 0.3, "why": "lost"}, True),
                                                 (False, None, False)],
                         ids=["ambiguous", "cancel seen late", "plain cancel"])
def test_which_reviews_keep_their_figures(ambiguous, lost, kept):
    rec = _review(ambiguous=ambiguous, lost_contact=lost)
    assert ("figures" in rec) is kept, rec
    if kept:
        assert len(rec["figures"]["by_pct"]["0"]) == 101 and rec["figures"]["footer"]["0"] == 40.0, rec["figures"]


# --------------------------------------------------------------------------- #
# The recompute                                                               #
# --------------------------------------------------------------------------- #

def _row(sid, pos, grams, before=900.0, **more):
    r = {"sid": sid, "toolhead": f"XL-{pos + 1}", "position": pos, "grams": grams, "current_used": 100.0,
         "initial_weight": 1000.0, "remaining_before": before, "remaining_after": round(before - grams, 1),
         "display": f"#{sid}", "color": "ff0000", "ambiguous": False}
    r.update(more)
    return r


FIG = {"footer": {"0": 40.0, "1": 10.0, "2": 5.0},
       "by_pct": {"0": [round(0.4 * i, 4) for i in range(101)], "1": [round(0.1 * i, 4) for i in range(101)],
                  "2": [0.0] * 101}}
HEADS = [{"toolhead": "XL-1", "position": 0, "sid": 57, "sids": [57]},
         {"toolhead": "XL-2", "position": 1, "sid": None, "sids": []}]


def _card(**more):
    rec = {"printer_name": "XL", "job_id": "J-1", "filename": "f.bgcode", "progress": 0.3, "kind": "partial",
           "ambiguous": True, "total_grams": 15.0, "spools": [_row(57, 0, 12.0)], "unresolved_usage": {"1": 3.0},
           "heads_at_end": HEADS, "figures": FIG, "created": "2026-11-23 00:00:00"}
    rec.update(more)
    cancel_review_store.add_pending(rec)
    return rec


def _post(**body):
    r = app_module.app.test_client().post("/api/cancel_deduct/recompute",
                                          json=dict({"printer_name": "XL", "job_id": "J-1", "rev": 0}, **body))
    return r.status_code, r.get_json()


def test_a_percentage_moves_the_rows_and_lines_and_says_so(logs):
    _card()
    code, body = _post(percent=62)
    assert code == 200 and body["status"] == "recomputed", body
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec == body["record"]
    (row,) = rec["spools"]
    assert (row["grams"], row["remaining_after"]) == (24.8, 875.2), row
    assert rec["unresolved_usage"] == {"1": 6.2} and rec["total_grams"] == 31.0, rec
    assert (rec["progress"], rec["seen_progress"], rec["basis"], rec["rev"]) == (0.62, 0.3, 62.0, 1), rec
    assert logs == ["📝 XL: job J-1's review worked out again at 62% (FCC last saw ~30%): 31.00g ('f.bgcode')."], logs


def test_a_decimal_is_read_between_its_whole_percents():
    _card()
    _post(percent=62.5)
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec["spools"][0]["grams"] == 25.0 and rec["unresolved_usage"] == {"1": 6.25}, rec


def test_the_whole_print_is_each_footer_head_one_the_walk_cant_see_included():
    _card()
    _post(whole=True)
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec["spools"][0]["grams"] == 40.0, rec
    assert rec["unresolved_usage"] == {"1": 10.0, "2": 5.0} and rec["total_grams"] == 55.0, rec
    assert (rec["progress"], rec["basis"]) == (1.0, "whole"), rec


def test_a_head_with_grams_only_at_the_new_basis_gets_the_spool_the_end_read_found(monkeypatch):
    heads = HEADS + [{"toolhead": "XL-3", "position": 2, "sid": 60, "sids": [60]}]
    # The start snapshot the builder kept (Group 65 review, RW4): #60 was on XL-3 when the
    # print started too, so the builder's rule makes it a row.
    _card(heads_at_end=heads, start_spools={"0": 57, "2": 60}, swap_log=[])
    monkeypatch.setattr(print_deduct, "_spool_read",
                        lambda sid: {"id": sid, "used_weight": 300.0, "initial_weight": 1000.0} if sid == 60 else None)
    monkeypatch.setattr(print_deduct.spoolman_api, "format_spool_display",
                        lambda s: {"text": f"#{s['id']} Test", "color": "00ff00"})
    _post(whole=True)
    rec = cancel_review_store.get_pending("XL", "J-1")
    new = next(r for r in rec["spools"] if r["sid"] == 60)
    assert (new["position"], new["grams"], new["remaining_before"], new["remaining_after"]) == (2, 5.0, 700.0, 695.0), new
    assert "2" not in rec["unresolved_usage"], rec


def test_a_split_head_moves_only_its_last_stretch_and_refuses_a_basis_before_it():
    split = [_row(57, 0, 8.0, segments=[{"from": None, "to": 0.2, "runout": True, "grams": 8.0}]),
             _row(61, 0, 4.0, segments=[{"from": 0.2, "to": None, "runout": False, "grams": 4.0}])]
    _card(spools=split, unresolved_usage={})
    _post(percent=62)
    rec = cancel_review_store.get_pending("XL", "J-1")
    by = {r["sid"]: r for r in rec["spools"]}
    assert by[57]["grams"] == 8.0 and by[61]["grams"] == 16.8, by
    assert by[61]["segments"][0]["grams"] == 16.8, by[61]
    code, body = _post(percent=10, rev=1)
    assert code == 200 and body["status"] == "error" and "spool was changed later in the print" in body["msg"], body
    assert cancel_review_store.get_pending("XL", "J-1")["rev"] == 1         # left as it was


def test_a_weighed_rows_0g_stays_and_an_unsure_holds_figure_follows(monkeypatch):
    # Group 65 review (CM3): the marks are worked out again from Decision 1's own check.
    at = 1795000000.0
    found = {0: {"sid": 57, "toolhead": "XL-1", "then": 100.0, "now": 160.0, "ours": 0.0,
                 "stamp": {"at": at + 60, "how": "Quick Weigh"}, "ended": at, "source": "print_end"},
             1: {"sid": 58, "toolhead": "XL-2", "then": 50.0, "now": 53.0, "ours": 0.0, "stamp": None,
                 "ended": at, "source": "print_end"}}
    monkeypatch.setattr(print_deduct, "_weighed_since_end", lambda heads, end_at, source=None: found)
    rows = [_row(57, 0, 12.0, prefill=0.0, weighed={"words": "w", "known_order": True}),
            _row(58, 1, 3.0, prefill=3.0, weighed={"words": "w", "known_order": False})]
    _card(spools=rows, unresolved_usage={}, end_at_s=at)
    _post(percent=62)
    by = {r["sid"]: r for r in cancel_review_store.get_pending("XL", "J-1")["spools"]}
    assert (by[57]["grams"], by[57]["prefill"]) == (24.8, 0.0), by[57]
    assert (by[58]["grams"], by[58]["prefill"]) == (6.2, 6.2), by[58]


def test_a_no_spool_cards_lines_take_their_new_totals():
    _card(kind="no_spool", spools=[], usage_map={"0": 12.0, "1": 3.0}, unresolved_usage=None)
    _post(whole=True)
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec["usage_map"] == {"0": 40.0, "1": 10.0, "2": 5.0} and rec["total_grams"] == 55.0, rec


@pytest.mark.parametrize("more,body,words", [
    ({"rev": 2}, {"percent": 62, "rev": 1}, "changed since it was drawn"),
    ({"figures": None}, {"percent": 62}, "kept no figures"),
    ({"requested_total": 15.0, "applied_g": 4.0}, {"percent": 62}, "already charged"),
    ({"kind": "shortfall"}, {"percent": 62}, "kept no figures"),
], ids=["stale rev", "no figures", "part-applied", "uncharged-grams card"])
def test_a_card_that_cant_be_worked_out_again_is_left_as_it_was(more, body, words):
    before = _card(**more)
    code, ans = _post(**body)
    assert code == 200 and ans["status"] == "error" and words in ans["msg"], ans
    assert cancel_review_store.get_pending("XL", "J-1") == before


@pytest.mark.parametrize("body", [{"percent": 150}, {"percent": -1}, {"percent": "abc"}, {}])
def test_a_percentage_outside_0_to_100_is_refused_before_the_card_is_touched(body):
    before = _card()
    code, ans = _post(**body)
    assert code == 400 and "from 0 to 100" in ans["msg"], ans
    assert cancel_review_store.get_pending("XL", "J-1") == before


def test_a_card_gone_is_already_handled():
    assert _post(percent=62) == (200, {"status": "already_handled"})


# --------------------------------------------------------------------------- #
# The Apply after it                                                          #
# --------------------------------------------------------------------------- #

def test_the_apply_records_the_basis_as_its_scale_and_an_older_view_is_refused(logs):
    _card(unresolved_usage={})
    _post(percent=62)
    spools = {57: {"id": 57, "used_weight": 100.0, "initial_weight": 1000.0}}
    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=lambda sid, data: {"id": sid, **data}), \
         patch.object(app_module.spoolman_api, "format_spool_display", return_value={"text": "#57", "color": "f00"}):
        client = app_module.app.test_client()
        old = client.post("/api/cancel_deduct/confirm",
                          json={"printer_name": "XL", "job_id": "J-1", "rev": 0, "updates": {"57": 12.0}}).get_json()
        none = client.post("/api/cancel_deduct/confirm",
                           json={"printer_name": "XL", "job_id": "J-1", "updates": {"57": 12.0}}).get_json()
        ok = client.post("/api/cancel_deduct/confirm",
                         json={"printer_name": "XL", "job_id": "J-1", "rev": 1, "updates": {"57": 24.8}}).get_json()
    assert old.get("stale") is True and none.get("stale_page") is True, (old, none)
    assert ok["status"] == "confirmed", ok
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-1")]
    assert entry["scale"] == 0.62 and entry["grams"] == 24.8, entry
    assert any(m.startswith("📝 XL: job J-1 charged 24.80g for 62% of the print, as its review was worked out again "
                            "(FCC last saw ~30%).") for m in logs), logs


# --------------------------------------------------------------------------- #
# The real download's wiring (Group 65 review, PR1)                           #
# --------------------------------------------------------------------------- #

GOOD = "M83\nT0\n" + "G1 E1\n" * 10 + "T1\n" + "G1 E1\n" * 10 + FOOT


@pytest.mark.parametrize("which", ["a plain file", "the repo's .bgcode"])
def test_the_real_download_gives_a_card_its_figures(monkeypatch, which):
    """Every other figures test stands in for fetch_cancel_gcode, its `remap` too, so
    deleting the one line that hands the real one back left them all green (the review's
    mutant: no card would keep figures, and Charge the whole print would never show).
    Here only the bytes' download is stood in: the real fetch, decode and remap give the
    card its figures, at the seen percent the very grams it charges, and the footer for
    the whole print. Green on 681601f6 too: a pin of the wiring, not a fix."""
    if which == "a plain file":
        data, pm = GOOD.encode(), TWO
    else:
        with open(os.path.join(os.path.dirname(os.path.abspath(print_deduct.__file__)), "tests", "fixtures",
                               "sample.bgcode"), "rb") as fh:
            data = fh.read()
        pm = {f"MMU-{i + 1}": {"printer_name": "XL", "position": i} for i in range(5)}
    monkeypatch.setattr(print_deduct.state, "add_log_entry", lambda *a, **k: None)
    monkeypatch.setattr(print_deduct, "_snapshot_active_spools", lambda *a, **k: {})
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(print_deduct.locations_db, "get_active_printer_map", return_value=pm), \
         patch.object(prusalink_api, "fetch_printer_credentials",
                      return_value={"ip_address": "203.0.113.9", "api_key": "k"}), \
         patch.object(prusalink_api, "_download_file_bytes", return_value=data), \
         patch.object(print_deduct, "_resolve_usage_to_spools", return_value=[]),          patch.object(print_deduct, "_heads_snapshot", return_value=[]):
        app_module._create_pending_cancel_review("XL", "/usb/A.gcode", "J-1", 0.3, fb_url="http://fb",
                                                 ambiguous=True)
    rec = cancel_review_store.get_pending("XL", "J-1")
    figs = rec.get("figures") or {}
    assert figs.get("by_pct") and figs.get("footer"), sorted(rec)
    for pos, grams in (rec.get("usage_map") or {}).items():
        assert abs(float(figs["by_pct"][str(pos)][30]) - float(grams)) < 0.01, (pos, grams, figs["by_pct"][str(pos)][30])
    for pos, vals in figs["by_pct"].items():
        assert abs(float(vals[100]) - float(figs["footer"][pos])) < 0.01, (pos, vals[100], figs["footer"])
    ans = app_module.app.test_client().post("/api/cancel_deduct/recompute", json={
        "printer_name": "XL", "job_id": "J-1", "rev": rec.get("rev", 0), "whole": True}).get_json()
    assert ans["status"] == "recomputed", ans
