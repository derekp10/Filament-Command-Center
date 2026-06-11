"""Tests for the cancelled-print preview-and-confirm UX (FilaBridge absorption
§9.7 / build slice 5): the persistent pending store, the _create_pending_cancel_
review compute-but-don't-write path, and the confirm/dismiss endpoints.

All Spoolman/PrusaLink surfaces are mocked so the whole preview→confirm flow is
validated without a physical cancelled print (Derek's "active test pattern").
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct_ledger  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))


@pytest.fixture
def client():
    return app_module.app.test_client()


def _row(sid, grams=20.0, used=100.0, initial=1000.0):
    return {"sid": sid, "toolhead": "XL-1", "position": 0, "grams": grams,
            "current_used": used, "initial_weight": initial,
            "remaining_before": initial - used, "remaining_after": initial - used - grams,
            "display": f"#{sid}", "color": "ff0000"}


def _record(printer="XL", job_id="J-5", spools=None):
    return {"printer_name": printer, "job_id": job_id, "filename": "f.gcode",
            "progress": 0.4, "total_grams": 20.0,
            "spools": spools or [_row(100)], "created": "2026-06-10 00:00:00"}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def test_store_round_trip_and_atomic_pop():
    cancel_review_store.add_pending(_record(job_id="A"))
    assert cancel_review_store.has_pending("XL", "A") is True
    assert cancel_review_store.get_pending("XL", "A")["job_id"] == "A"
    assert len(cancel_review_store.list_pending()) == 1

    popped = cancel_review_store.pop_pending("XL", "A")
    assert popped["job_id"] == "A"
    # Second pop gets None — the atomic claim that prevents double-apply.
    assert cancel_review_store.pop_pending("XL", "A") is None
    assert cancel_review_store.has_pending("XL", "A") is False


def test_store_add_is_idempotent_by_key():
    cancel_review_store.add_pending(_record(job_id="B"))
    cancel_review_store.add_pending(_record(job_id="B"))
    assert len(cancel_review_store.list_pending()) == 1


# ---------------------------------------------------------------------------
# _create_pending_cancel_review
# ---------------------------------------------------------------------------

_DEAD = "; " + ("pad " * 40) + "\n"


def _cancelled_gcode():
    prefix = "M83\nT0\nG1 X10 E5\nG1 X20 E5\n"
    suffix = ("G1 X30 E5\nG1 X40 E5\nT1\nG1 E16\n"
              "; filament used [mm] = 20, 16\n; filament used [g] = 40, 32\n")
    gcode = prefix + _DEAD + suffix
    cut = len(prefix.encode("utf-8")) + len(_DEAD.encode("utf-8")) // 2
    return gcode, cut / len(gcode.encode("utf-8"))


def _creds(*a, **k):
    return {"ip_address": "1.2.3.4", "api_key": "k"}


def _preview_ctx(gcode, printer_map, spools, spools_at, captured):
    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}
    return [
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map),
        patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds),
        patch.object(app_module.prusalink_api, "download_gcode_content", return_value=gcode),
        patch.object(app_module.spoolman_api, "get_spools_at_location",
                     side_effect=lambda loc: spools_at.get(str(loc).upper(), [])),
        patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))),
        patch.object(app_module.spoolman_api, "update_spool", side_effect=_update),
        patch.object(app_module.spoolman_api, "format_spool_display",
                     return_value={"text": "#s", "color": "ff0000"}),
    ]


def test_create_pending_computes_per_tool_no_write():
    gcode, frac = _cancelled_gcode()
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0},
                   "XL-2": {"printer_name": "XL", "position": 1}}
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
              200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0}}
    spools_at = {"XL-1": [100], "XL-2": [200]}
    captured = {"updates": []}
    ctx = _preview_ctx(gcode, printer_map, spools, spools_at, captured)
    for m in ctx:
        m.start()
    try:
        out = app_module._create_pending_cancel_review("XL", "f.gcode", "J-1", frac, fb_url="http://fb")
    finally:
        for m in reversed(ctx):
            m.stop()
    assert out["status"] == "pending"
    assert captured["updates"] == [], "preview must not write to Spoolman"
    rec = cancel_review_store.get_pending("XL", "J-1")
    rows = {r["sid"]: r for r in rec["spools"]}
    assert 100 in rows and abs(rows[100]["grams"] - 20.0) < 1e-6
    assert 200 not in rows, "untouched head omitted from the preview"
    assert abs(rows[100]["remaining_before"] - 900.0) < 1e-6
    assert abs(rows[100]["remaining_after"] - 880.0) < 1e-6


def test_create_pending_idempotent_and_ledger_guarded():
    gcode, frac = _cancelled_gcode()
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}}
    ctx = _preview_ctx(gcode, printer_map, spools, {"XL-1": [100]}, {"updates": []})
    for m in ctx:
        m.start()
    try:
        first = app_module._create_pending_cancel_review("XL", "f.gcode", "J-2", frac, fb_url="http://fb")
        assert first["status"] == "pending"
        # Same job already pending → skip (don't re-queue / re-log).
        second = app_module._create_pending_cancel_review("XL", "f.gcode", "J-2", frac, fb_url="http://fb")
        assert second["status"] == "skipped" and second["reason"] == "already pending"
        # Already in the ledger (confirmed/dismissed earlier) → skip.
        print_deduct_ledger.record_deduct("XL", "J-3", filename="f.gcode")
        third = app_module._create_pending_cancel_review("XL", "f.gcode", "J-3", frac, fb_url="http://fb")
        assert third["status"] == "skipped" and third["reason"] == "already processed"
    finally:
        for m in reversed(ctx):
            m.stop()


def test_create_pending_download_fail_no_pending_no_ledger():
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "download_gcode_content", return_value=None), \
         patch.object(app_module.state, "add_log_entry") as log:
        out = app_module._create_pending_cancel_review("XL", "p.bgcode", "J-4", 0.5, fb_url="http://fb")
    assert out["status"] == "error"
    assert cancel_review_store.has_pending("XL", "J-4") is False
    assert print_deduct_ledger.was_deducted("XL", "J-4") is False   # retryable
    assert log.call_args.args[1] == "WARNING"


def test_create_pending_no_mapped_spool_records_and_warns():
    gcode, frac = _cancelled_gcode()
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    # get_spools_at_location returns nothing → no spool to deduct from.
    ctx = _preview_ctx(gcode, printer_map, {}, {}, {"updates": []})
    for m in ctx:
        m.start()
    try:
        with patch.object(app_module.state, "add_log_entry") as log:
            out = app_module._create_pending_cancel_review("XL", "f.gcode", "J-6", frac, fb_url="http://fb")
    finally:
        for m in reversed(ctx):
            m.stop()
    assert out["status"] == "no_spools"
    assert cancel_review_store.has_pending("XL", "J-6") is False
    assert print_deduct_ledger.was_deducted("XL", "J-6") is True   # recorded, won't re-queue
    assert log.call_args.args[1] == "WARNING"


# ---------------------------------------------------------------------------
# Endpoints: confirm / dismiss / pending
# ---------------------------------------------------------------------------

def test_pending_endpoint_lists(client):
    cancel_review_store.add_pending(_record(job_id="P1"))
    r = client.get("/api/cancel_deduct/pending")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["pending"]) == 1 and body["pending"][0]["job_id"] == "P1"


def test_confirm_applies_additive_nudged_and_pops(client):
    cancel_review_store.add_pending(_record(job_id="C1", spools=[_row(100, grams=20.0, used=100.0)]))
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}}
    captured = {"updates": []}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=_update), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#s", "color": "ff0000"}):
        # Nudge 100 from 20 → 25g.
        r = client.post("/api/cancel_deduct/confirm",
                        json={"printer_name": "XL", "job_id": "C1", "updates": {"100": 25}})
    body = r.get_json()
    assert body["status"] == "confirmed"
    assert len(captured["updates"]) == 1
    sid, data = captured["updates"][0]
    assert sid == 100
    assert abs(data["used_weight"] - 125.0) < 1e-6        # 100 (re-read) + 25 nudged
    assert set(data.keys()) == {"used_weight"}            # archive-on-empty discipline
    assert cancel_review_store.has_pending("XL", "C1") is False
    assert print_deduct_ledger.was_deducted("XL", "C1") is True
    # Second confirm is an atomic-claim no-op (pending already popped).
    r2 = client.post("/api/cancel_deduct/confirm",
                     json={"printer_name": "XL", "job_id": "C1", "updates": {"100": 25}})
    assert r2.get_json()["status"] == "already_handled"
    assert len(captured["updates"]) == 1, "must not double-apply"


def test_confirm_clamps_nudge_to_remaining(client):
    """A nudge above the spool's real remaining is clamped so the deduct never
    exceeds capacity and the reported grams match what Spoolman stores."""
    cancel_review_store.add_pending(_record(job_id="CL", spools=[_row(100, grams=10.0)]))
    spools = {100: {"id": 100, "used_weight": 990.0, "initial_weight": 1000.0}}  # 10g left
    captured = {"updates": []}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=_update), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#s", "color": "ff0000"}):
        r = client.post("/api/cancel_deduct/confirm",
                        json={"printer_name": "XL", "job_id": "CL", "updates": {"100": 50}})
    body = r.get_json()
    assert body["status"] == "confirmed"
    sid, data = captured["updates"][0]
    assert abs(data["used_weight"] - 1000.0) < 1e-6        # clamped to initial, not 990+50
    assert abs(body["applied"][0]["grams"] - 10.0) < 1e-6  # reported the true 10g, not 50
    assert abs(body["applied"][0]["remaining"]) < 1e-6


def test_confirm_rejects_out_of_review_spool(client):
    """A confirm carrying a sid that wasn't in the reviewed preview must NOT
    deduct from it (no deducting a wrong/crafted spool)."""
    cancel_review_store.add_pending(_record(job_id="OO", spools=[_row(100)]))
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
              999: {"id": 999, "used_weight": 0.0, "initial_weight": 1000.0}}
    captured = {"updates": []}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=_update), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#s", "color": "ff0000"}):
        r = client.post("/api/cancel_deduct/confirm",
                        json={"printer_name": "XL", "job_id": "OO", "updates": {"100": 20, "999": 500}})
    body = r.get_json()
    touched = {sid for sid, _ in captured["updates"]}
    assert 999 not in touched, "out-of-review spool must never be deducted"
    assert 100 in touched
    assert any(e["sid"] == 999 and e["error"] == "not in this review" for e in body["errors"])


def test_confirm_re_reads_current_used(client):
    """Confirm must use the spool's CURRENT used_weight (re-read now), not the
    snapshot in the pending record — so a weigh-out between preview and confirm
    isn't clobbered."""
    cancel_review_store.add_pending(_record(job_id="RR", spools=[_row(100, grams=25.0, used=100.0)]))
    calls = {"n": 0}

    def _get(sid):
        calls["n"] += 1
        # Preview snapshot said used=100; the spool was weighed since → now 110.
        return {"id": int(sid), "used_weight": 110.0, "initial_weight": 1000.0}

    captured = {"updates": []}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    with patch.object(app_module.spoolman_api, "get_spool", side_effect=_get), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=_update), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#s", "color": "ff0000"}):
        client.post("/api/cancel_deduct/confirm",
                    json={"printer_name": "XL", "job_id": "RR", "updates": {"100": 25}})
    sid, data = captured["updates"][0]
    assert abs(data["used_weight"] - 135.0) < 1e-6, "must be 110 (re-read) + 25, not 100 + 25"


def test_confirm_partial_failure_requeues_only_failed(client):
    """One spool succeeds, one fails: the succeeded one is deducted ONCE, the
    ledger is NOT burned, and ONLY the failed spool is re-queued (so a retry
    can't double-deduct the one that already applied)."""
    cancel_review_store.add_pending(_record(job_id="PF",
                                            spools=[_row(100, grams=20.0), _row(200, grams=15.0)]))
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
              200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0}}
    captured = {"updates": []}

    def _update(sid, data):
        if int(sid) == 200:
            return None   # spool 200 fails
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=_update), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "boom"), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#s", "color": "ff0000"}):
        r = client.post("/api/cancel_deduct/confirm",
                        json={"printer_name": "XL", "job_id": "PF", "updates": {"100": 20, "200": 15}})
    body = r.get_json()
    assert body["status"] == "confirmed"            # something applied
    assert {a["sid"] for a in body["applied"]} == {100}
    assert {e["sid"] for e in body["errors"]} == {200}
    # Ledger NOT burned (job not fully done) → edge stays blocked but retryable.
    assert print_deduct_ledger.was_deducted("XL", "PF") is False
    # ONLY the failed spool re-queued (not 100 → no double-deduct on retry).
    rec = cancel_review_store.get_pending("XL", "PF")
    assert rec is not None and {s["sid"] for s in rec["spools"]} == {200}


def test_confirm_total_failure_restores_pending(client):
    cancel_review_store.add_pending(_record(job_id="C2", spools=[_row(100)]))
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}}
    with patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", return_value=None), \
         patch.object(app_module.spoolman_api, "LAST_SPOOLMAN_ERROR", "boom"), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#s", "color": "ff0000"}):
        r = client.post("/api/cancel_deduct/confirm",
                        json={"printer_name": "XL", "job_id": "C2", "updates": {"100": 20}})
    assert r.get_json()["status"] == "error"
    # Restored so Derek can retry; ledger NOT burned.
    assert cancel_review_store.has_pending("XL", "C2") is True
    assert print_deduct_ledger.was_deducted("XL", "C2") is False


def test_dismiss_records_ledger_pops_no_write(client):
    cancel_review_store.add_pending(_record(job_id="D1"))
    with patch.object(app_module.spoolman_api, "update_spool") as upd:
        r = client.post("/api/cancel_deduct/dismiss",
                        json={"printer_name": "XL", "job_id": "D1"})
    assert r.get_json()["status"] == "dismissed"
    assert upd.call_count == 0
    assert cancel_review_store.has_pending("XL", "D1") is False
    assert print_deduct_ledger.was_deducted("XL", "D1") is True


def test_confirm_missing_params_400(client):
    r = client.post("/api/cancel_deduct/confirm", json={"job_id": "x"})
    assert r.status_code == 400


def test_dismiss_already_handled(client):
    r = client.post("/api/cancel_deduct/dismiss",
                    json={"printer_name": "XL", "job_id": "nope"})
    assert r.get_json()["status"] == "already_handled"
