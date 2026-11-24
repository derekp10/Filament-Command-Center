"""Group 65.3 (weigh-in drift, step 1; Derek, 2026-11-03): each weigh save says what
FCC expected, or that it was a hand edit. Offline (Flask test client, Spoolman
stood in).

A weigh screen sends what it did as a top-level `weigh` ({source, mode, reading, tare,
tare_skipped}) beside `id` and `updates`. A Gross or Net reading is a weighing:
"⚖️ Weighed — Spool #57: 655.0 g left (scale 875 g − empty spool 220 g). FCC expected
654.7 g: 0.3 g heavier. (used 345.3g ➔ 345.0g)". Additive, Set Used and a skipped
empty weight are "✏️ Weight edited by hand". "FCC expected" comes only from the
spool's own record (get_spool hands back Spoolman's 404 or 5xx body as a dict, which
also gave the old line made-up 0.0g "before" figures), and a print FCC hasn't charged
yet that used the spool is named instead of a comparison. No `weigh`, or one FCC
can't read: today's line, byte for byte.

Red on 1be96d6e (every line is "✏️ Weight updated"; a 404 body's "before" is 0.0g).
"""
from __future__ import annotations

import pytest

import app as app_module
import cancel_fetch_store
import cancel_review_store
import print_deduct
import stock_report

PRE = {"id": 57, "archived": False, "initial_weight": 1000, "used_weight": 345.3, "remaining_weight": 654.7}


def _post(used, initial=1000):
    return {"id": 57, "archived": False, "initial_weight": initial, "used_weight": used,
            "remaining_weight": round(initial - used, 4)}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(stock_report, "check_after_weight_change", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(app_module.state, "add_log_entry", lambda msg, *a, **k: calls.append(msg))
    box = {"pre": dict(PRE), "post": _post(345.0)}
    monkeypatch.setattr(app_module.spoolman_api, "get_spool", lambda sid: box["pre"])
    monkeypatch.setattr(app_module.spoolman_api, "update_spool", lambda sid, data, **k: box["post"])
    box["logs"] = calls
    return box


def _save(env, weigh=None, used=345.0, **more):
    body = {"id": 57, "updates": {"used_weight": used}}
    if weigh is not None:
        body["weigh"] = weigh
    body.update(more)
    r = app_module.app.test_client().post("/api/spool/update", json=body)
    assert r.get_json()["status"] == "success", r.get_json()
    return [m for m in env["logs"] if "Spool #57" in m and ("Weigh" in m or "Weight" in m)]


def _w(mode, reading=None, tare=None, **more):
    return dict({"source": "quick_weigh", "mode": mode, "reading": reading, "tare": tare,
                 "tare_skipped": False}, **more)


def test_a_gross_reading_is_a_weighing_with_what_fcc_expected(env):
    assert _save(env, _w("gross", 875, 220)) == [
        "⚖️ Weighed — Spool #57: 655.0 g left (scale 875 g − empty spool 220 g). FCC expected 654.7 g: "
        "0.3 g heavier. (used 345.3g ➔ 345.0g)"]


def test_a_net_reading_says_the_empty_spool_was_taken_off_by_hand(env):
    env["post"] = _post(345.5)
    assert _save(env, _w("net", 654.5), used=345.5) == [
        "⚖️ Weighed — Spool #57: 654.5 g left (empty spool taken off by hand). FCC expected 654.7 g: "
        "0.2 g lighter. (used 345.3g ➔ 345.5g)"]


def test_a_reading_that_matches_says_so(env):
    env["post"] = _post(345.3)
    assert _save(env, _w("net", 654.7), used=345.3)[0].endswith(
        "FCC expected 654.7 g: the same. (used 345.3g ➔ 345.3g)")


@pytest.mark.parametrize("weigh", [
    _w("additive"),
    _w("set_used", 406.6),
    _w("net", 593.4, tare_skipped=True),
], ids=["additive", "set_used", "skipped tare"])
def test_a_hand_edit_says_so_and_compares_nothing(env, weigh):
    env["post"] = _post(406.6)
    assert _save(env, weigh, used=406.6) == [
        "✏️ Weight edited by hand — Spool #57: [654.7g ➔ 593.4g remaining] (used 345.3g ➔ 406.6g)"]


def test_a_reading_over_the_spools_total_says_what_fcc_recorded(env):
    env["pre"] = dict(PRE, used_weight=20.0, remaining_weight=980.0)
    env["post"] = _post(0.0)
    (line,) = _save(env, _w("gross", 1250, 220), used=0.0)
    assert line == ("⚖️ Weighed — Spool #57: 1030.0 g left (scale 1250 g − empty spool 220 g). That's more "
                    "than its 1000 g total, so FCC recorded 1000.0 g. FCC expected 980.0 g: 50.0 g heavier. "
                    "(used 20.0g ➔ 0.0g)"), line


def test_a_reading_under_an_empty_spool_says_what_fcc_recorded(env):
    env["post"] = _post(1000.0)
    (line,) = _save(env, _w("gross", 200, 220), used=1000.0)
    assert ("-20.0 g left (scale 200 g − empty spool 220 g). The scale read less than the empty spool, so FCC "
            "recorded 0.0 g.") in line, line


def test_a_print_fcc_hasnt_charged_names_itself_instead_of_a_comparison(env, monkeypatch):
    monkeypatch.setattr(print_deduct, "uncharged_print_for",
                        lambda sid: {"job_id": "1144", "printer_name": "<b>INDX"})
    (line,) = _save(env, _w("gross", 875, 220))
    assert line == ("⚖️ Weighed — Spool #57: 655.0 g left (scale 875 g − empty spool 220 g). FCC expected "
                    "654.7 g, but job 1144 on &lt;b&gt;INDX, which used this spool, isn't charged yet. "
                    "(used 345.3g ➔ 345.0g)"), line


def test_no_weigh_keeps_todays_line_byte_for_byte(env):
    assert _save(env) == [
        "✏️ Weight updated — Spool #57: [654.7g ➔ 655.0g remaining] (used 345.3g ➔ 345.0g)"]


@pytest.mark.parametrize("weigh", [
    "gross", 5, True, {"mode": "scale"}, {"mode": "gross", "reading": -1, "tare": 220},
    {"mode": "gross", "reading": "875", "tare": 220}, {"mode": "gross", "reading": True, "tare": 220},
    {"mode": "net", "reading": float("inf")},
], ids=["text", "number", "bool", "unknown mode", "negative", "text reading", "bool reading", "infinite"])
def test_a_weigh_fcc_cant_read_is_ignored(env, weigh):
    # (Python's JSON carries the infinite reading as Infinity, and Flask reads it back.)
    assert _save(env, weigh) == [
        "✏️ Weight updated — Spool #57: [654.7g ➔ 655.0g remaining] (used 345.3g ➔ 345.0g)"]


def test_a_404_body_as_the_spool_gives_no_expectation_and_no_made_up_before(env):
    env["pre"] = {"detail": "Spool not found"}            # Spoolman's 404 body: a truthy dict with no id
    assert _save(env, _w("gross", 875, 220)) == [
        "⚖️ Weighed — Spool #57: 655.0 g left (scale 875 g − empty spool 220 g). (used 345.0g)"]
    env["logs"].clear()
    assert _save(env) == ["✏️ Weight updated — Spool #57: 655.0g remaining (used 345.0g)"]


def test_a_total_change_still_says_so(env):
    env["post"] = _post(345.0, initial=1200)
    (line,) = _save(env, _w("gross", 1075, 220), initial_weight=1200)
    assert line.endswith("(used 345.3g ➔ 345.0g)  [total 1000.0g ➔ 1200.0g]"), line


# --------------------------------------------------------------------------- #
# print_deduct.uncharged_print_for: FCC's own two files                         #
# --------------------------------------------------------------------------- #

def test_a_queued_print_whose_end_read_names_the_spool_is_found(env):
    cancel_fetch_store.add_pending({"printer_name": "INDX", "job_id": "1144", "filename": "f.bgcode",
                                    "kind": "complete",
                                    "end_heads": {"heads": [{"toolhead": "RCOI-1", "position": 0, "sids": [12, 57]}],
                                                  "source": "print_end", "at": "now"}})
    # Group 65 review (RW1): FCC hasn't read which heads a queued print used: "may have".
    assert print_deduct.uncharged_print_for(57) == {"job_id": "1144", "printer_name": "INDX", "sure": False}
    assert print_deduct.uncharged_print_for(58) is None


def test_an_open_review_naming_the_spool_is_found_as_its_print(env):
    cancel_review_store.add_pending({"printer_name": "XL", "job_id": "1145#shortfall", "kind": "shortfall",
                                     "filename": "f.bgcode", "spools": [{"sid": 57, "grams": 3.0}],
                                     "total_grams": 3.0})
    cancel_review_store.add_pending({"printer_name": "XL", "job_id": "1146", "kind": "partial",
                                     "filename": "g.bgcode", "spools": [], "unresolved_usage": {"1": 1.0},
                                     "heads_at_end": [{"toolhead": "XL-2", "position": 1, "sid": 61, "sids": [61]},
                                                      {"toolhead": "XL-3", "position": 2, "sid": 62, "sids": [62]}],
                                     "total_grams": 1.0})
    # Group 65 review (RW1): a row the card charges is "sure"; a spool its line offers
    # "may have"; a spool only on a head the card neither charges nor asks about is none.
    assert print_deduct.uncharged_print_for(57) == {"job_id": "1145", "printer_name": "XL", "sure": True}
    assert print_deduct.uncharged_print_for("61") == {"job_id": "1146", "printer_name": "XL", "sure": False}
    assert print_deduct.uncharged_print_for(62) is None
    assert print_deduct.uncharged_print_for(99) is None


def test_a_print_end_read_that_found_no_spool_names_nothing(env):
    cancel_fetch_store.add_pending({"printer_name": "INDX", "job_id": "1147", "filename": "f.bgcode",
                                    "end_heads": {"heads": [{"toolhead": "RCOI-1", "position": 0, "sids": []}]}})
    assert print_deduct.uncharged_print_for(57) is None


def test_the_real_lookup_runs_in_a_weigh_line(env):
    cancel_fetch_store.add_pending({"printer_name": "INDX", "job_id": "1144", "filename": "f.bgcode",
                                    "end_heads": {"heads": [{"toolhead": "RCOI-1", "position": 0, "sids": [57]}]}})
    (line,) = _save(env, _w("gross", 875, 220))
    # Group 65 review (RW1): a queued print may have used it: the comparison stays.
    assert "heavier. Job 1144 on INDX, which may have used this spool, isn't charged yet." in line, line
