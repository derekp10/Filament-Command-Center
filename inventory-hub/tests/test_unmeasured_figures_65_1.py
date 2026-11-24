"""Group 65.1 (1c): the ❓ "couldn't measure" card gets figures where its file can give
them. Offline.

  - An ambiguous end whose moves FCC can't read (`unreadable_moves`) keeps its footer as
    figures: Charge the whole print only (no percent can be placed in moves FCC can't
    read; a percentage is refused in words).
  - An ambiguous end FCC never sampled (`unsampled`: the print ended, or FCC restarted,
    before FCC read its progress; the printer is idle) reads its file once, on the end's
    own thread right after its card is stashed, and the card gets figures for every
    percent (its revision one up, one INFO line). A download that fails, no login, or a
    card settled meanwhile leaves things as they were. A `replaced` end (the next print
    running) downloads nothing (a follow-up).
  - Worked out, a "couldn't measure" card becomes a card to pick on (`no_spool`), each
    head's line unpicked (FCC never read the heads for such an end), and its Apply
    charges the picks with the basis as the ledger's scale.

Red on 60985046 (no figures on such a card; a recompute refused it).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import app as app_module
import cancel_fetch_store
import cancel_review_store
import print_deduct
import print_deduct_ledger
import print_monitor
import prusalink_api

TWO = {"XL-1": {"printer_name": "XL", "position": 0}, "XL-2": {"printer_name": "XL", "position": 1}}
FOOT = "; filament used [mm] = 10, 10\n; filament used [g] = 10, 10\n"
GOOD = "M83\nT0\n" + "G1 E1\n" * 10 + "T1\n" + "G1 E1\n" * 10 + FOOT
UNREADABLE = "M83\nT0\nG5 E10\nT1\nG5 E10\n" + FOOT


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


def _world(gcode, creds=True, fetch_ok=True, calls=None):
    def fetch(ip, key, fn, f, **k):
        if calls is not None:
            calls.append(fn)
        return {"gcode": gcode, "fraction": f, "remap": lambda p: p} if fetch_ok else None
    return [
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=TWO),
        patch.object(prusalink_api, "fetch_printer_credentials",
                     return_value={"ip_address": "1.2.3.4", "api_key": "k"} if creds else None),
        patch.object(prusalink_api, "fetch_cancel_gcode", side_effect=fetch),
    ]


def _run(ctx, fn):
    for m in ctx:
        m.start()
    try:
        return fn()
    finally:
        for m in reversed(ctx):
            m.stop()


def _unmeasured(reason="unsampled", **world):
    return _run(_world(GOOD, **world), lambda: app_module._create_pending_cancel_review(
        "XL", "/usb/A.BGC", "J-1", 0.0, fb_url="http://fb", ambiguous=True, progress_unknown=True,
        unmeasured_reason=reason))


def test_moves_fcc_cant_read_keep_the_footer_for_charge_the_whole_print(logs):
    _run(_world(UNREADABLE), lambda: app_module._create_pending_cancel_review(
        "XL", "/usb/A.BGC", "J-1", 0.5, fb_url="http://fb", ambiguous=True))
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec["kind"] == "progress_unknown" and rec["unmeasured_reason"] == "unreadable_moves", rec
    assert rec["figures"] == {"footer": {"0": 10.0, "1": 10.0}}, rec


def test_an_unsampled_end_reads_its_file_once_for_its_cards_figures(logs):
    calls = []
    _unmeasured(calls=calls)
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert calls == ["/usb/A.BGC"], calls
    assert rec["kind"] == "progress_unknown" and rec["rev"] == 1, rec
    assert rec["figures"]["footer"] == {"0": 10.0, "1": 10.0} and len(rec["figures"]["by_pct"]["0"]) == 101, rec
    assert logs[-1] == ("📝 XL: read '/usb/A.BGC' for its review: Charge the whole print, or the percentage it got "
                        "to, can now be worked out on its card."), logs


@pytest.mark.parametrize("world", [{"fetch_ok": False}, {"creds": False}], ids=["download failed", "no login"])
def test_a_download_that_cant_be_made_leaves_the_card_as_it_was(world, logs):
    _unmeasured(**world)
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert "figures" not in rec and "rev" not in rec, rec
    assert not any("can now be worked out" in m for m in logs), logs


def test_a_replaced_end_downloads_nothing():
    calls = []
    _unmeasured(reason="replaced", calls=calls)
    assert calls == [] and "figures" not in cancel_review_store.get_pending("XL", "J-1")


def test_a_card_settled_while_its_file_was_read_is_left_alone(monkeypatch):
    real = print_deduct._compute_cancel_usage

    def settle_meanwhile(*a, **k):
        out = real(*a, **k)
        cancel_review_store.pop_pending("XL", "J-1")       # Discarded while the file was read
        return out
    monkeypatch.setattr(print_deduct, "_compute_cancel_usage", settle_meanwhile)
    _unmeasured()
    assert cancel_review_store.get_pending("XL", "J-1") is None


def _post(**body):
    r = app_module.app.test_client().post("/api/cancel_deduct/recompute",
                                          json=dict({"printer_name": "XL", "job_id": "J-1"}, **body))
    return r.get_json()


def test_worked_out_it_becomes_a_card_to_pick_on_and_its_apply_charges_the_picks(logs):
    _unmeasured()
    ans = _post(rev=1, whole=True)
    assert ans["status"] == "recomputed", ans
    rec = cancel_review_store.get_pending("XL", "J-1")
    assert rec["kind"] == "no_spool" and rec["usage_map"] == {"0": 10.0, "1": 10.0}, rec
    assert rec["unmeasured_was"] == "unsampled" and "unmeasured_reason" not in rec, rec
    assert (rec["basis"], rec["progress"], rec["rev"], rec["total_grams"]) == ("whole", 1.0, 2, 20.0), rec
    spools = {57: {"id": 57, "used_weight": 100.0, "initial_weight": 1000.0},
              58: {"id": 58, "used_weight": 50.0, "initial_weight": 1000.0}}
    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=lambda sid, data: {"id": sid, **data}), \
         patch.object(app_module.spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "f00"}):
        ok = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-1", "rev": 2,
            "charges": [{"position": "0", "sid": 57, "grams": 10.0},
                        {"position": "1", "sid": 58, "grams": 10.0}]}).get_json()
    assert ok["status"] == "confirmed", ok
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-1")]
    assert entry["scale"] == 1.0 and entry["grams"] == 20.0, entry


def test_a_footer_only_card_refuses_a_percentage_in_words():
    _run(_world(UNREADABLE), lambda: app_module._create_pending_cancel_review(
        "XL", "/usb/A.BGC", "J-1", 0.5, fb_url="http://fb", ambiguous=True))
    ans = _post(rev=0, percent=62)
    assert ans["status"] == "error" and "can only charge the whole print" in ans["msg"], ans
    ok = _post(rev=0, whole=True)
    assert ok["status"] == "recomputed" and ok["record"]["usage_map"] == {"0": 10.0, "1": 10.0}, ok
