"""Tests for the cancelled-print preview-and-confirm UX (FilaBridge absorption
§9.7 / build slice 5): the persistent pending store, the _create_pending_cancel_
review compute-but-don't-write path, and the confirm/dismiss endpoints.

All Spoolman/PrusaLink surfaces are mocked so the whole preview→confirm flow is
validated without a physical cancelled print (Derek's "active test pattern").
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import cancel_review_store  # noqa: E402
import cancel_fetch_store  # noqa: E402
import print_deduct_ledger  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
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
        patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                     side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}),
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


def test_create_pending_download_fail_queues_deferred_fetch():
    # A locked selected-file download (§9.10) is RETRYABLE: don't give up — queue
    # a deferred fetch + nudge to clear the screen, NO review/ledger yet.
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode", return_value=None), \
         patch.object(app_module.state, "add_log_entry") as log:
        out = app_module._create_pending_cancel_review("XL", "p.bgcode", "J-4", 0.5, fb_url="http://fb")
    assert out["status"] == "awaiting_fetch"
    assert cancel_fetch_store.has_pending("XL", "J-4") is True       # queued for retry
    assert cancel_review_store.has_pending("XL", "J-4") is False     # not computed yet
    assert print_deduct_ledger.was_deducted("XL", "J-4") is False    # retryable, not recorded
    # The one nudge logged is the clear-the-screen WARNING with the awaiting meta.
    assert log.call_args.args[1] == "WARNING"
    assert log.call_args.kwargs["meta"]["type"] == "cancel_deduct_awaiting"


def test_create_pending_no_creds_queues_deferred_fetch():
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", return_value=None), \
         patch.object(app_module.state, "add_log_entry"):
        out = app_module._create_pending_cancel_review("XL", "f.gcode", "J-4b", 0.5, fb_url="http://fb")
    assert out["status"] == "awaiting_fetch"
    assert cancel_fetch_store.has_pending("XL", "J-4b") is True


def test_no_spool_stashes_recoverable_review_no_ledger():
    """Usage WAS computed but no spool is bound to the toolhead. Instead of burning
    a terminal grams=0 ledger entry (the 2026-06-13 silent-loss bug), stash a
    RECOVERABLE `no_spool` review carrying the computed usage_map — so binding the
    toolhead later + Apply can re-resolve and deduct it. No ledger write."""
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
    assert out["status"] == "pending_unresolved" and out["kind"] == "no_spool"
    assert cancel_review_store.has_pending("XL", "J-6") is True
    assert print_deduct_ledger.was_deducted("XL", "J-6") is False   # NOT terminal-0g'd
    rec = cancel_review_store.get_pending("XL", "J-6")
    assert rec["kind"] == "no_spool"
    assert rec["spools"] == []
    # usage_map carries the computed grams (T0 = 10mm * 2.0 g/mm = 20g), keyed by
    # position — JSON-serialized so the key is a STRING (the confirm path int()s it).
    assert rec["usage_map"] == {"0": 20.0}
    assert log.call_args.kwargs["meta"]["type"] == "cancel_deduct_pending"


def test_progress_unknown_short_circuits_to_review_no_compute():
    """progress_unknown=True must NOT fetch creds or download/compute (the prefix-
    parse at 0% would fold to a misleading no_usage 0g and lose it permanently) —
    it stashes a non-destructive progress_unknown review directly: no usage_map, no
    ledger, recoverable by weighing."""
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials") as creds, \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode") as dl, \
         patch.object(app_module.state, "add_log_entry"):
        out = app_module._create_pending_cancel_review(
            "XL", "f.gcode", "PU-2", 0.0, fb_url="http://fb",
            ambiguous=True, progress_unknown=True)
    assert out["status"] == "pending_unresolved" and out["kind"] == "progress_unknown"
    creds.assert_not_called()    # no credentials fetch
    dl.assert_not_called()       # no download/compute
    rec = cancel_review_store.get_pending("XL", "PU-2")
    assert rec["kind"] == "progress_unknown" and rec["usage_map"] is None
    assert rec["spools"] == []
    assert print_deduct_ledger.was_deducted("XL", "PU-2") is False


def test_confirm_no_spool_reresolves_and_applies():
    """Apply on a no_spool review re-resolves the stored usage_map to whatever spool
    is bound NOW (toolhead just bound) and deducts additively. Exercises the
    int-key coercion (usage_map key "0" → position 0) end to end."""
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "NS-1", "filename": "f.gcode", "progress": 0.4,
        "total_grams": 20.0, "spools": [], "kind": "no_spool",
        "usage_map": {"0": 20.0}, "created": "2026-06-13 00:00:00"})
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}}
    captured = []
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.locations_db, "get_active_printer_map",
                      return_value={"XL-1": {"printer_name": "XL", "position": 0}}), \
         patch.object(app_module, "_resolve_active_locs_for_printer",
                      return_value=[("XL-1", {"position": 0})]), \
         patch.object(app_module.spoolman_api, "get_spools_at_location",
                      side_effect=lambda loc: [100] if str(loc).upper() == "XL-1" else []), \
         patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool",
                      side_effect=lambda sid, data: captured.append((sid, dict(data))) or {"id": sid}), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#100", "color": "ff0000"}), \
         patch.object(app_module.state, "add_log_entry"):
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm",
                                               json={"printer_name": "XL", "job_id": "NS-1", "updates": {}})
    d = r.get_json()
    assert d["status"] == "confirmed"
    assert captured == [(100, {"used_weight": 120.0})]   # 100 + 20g, ONLY used_weight
    assert print_deduct_ledger.was_deducted("XL", "NS-1") is True
    assert cancel_review_store.has_pending("XL", "NS-1") is False


def test_confirm_no_spool_partial_apply_warns_shortfall():
    """no_spool review with multi-position usage_map; on Apply only ONE position
    resolves to a bound spool, so part of the computed usage can't be applied. The
    applied grams are recorded, and the shortfall is surfaced (WARNING + shortfall_g
    in the response) rather than silently lost (review findings F5/F6, 2026-06-13)."""
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "NS-P", "filename": "f.gcode", "progress": 1.0,
        "total_grams": 30.0, "spools": [], "kind": "no_spool",
        "usage_map": {"0": 20.0, "1": 10.0}, "created": "2026-06-13 00:00:00"})
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module, "_resolve_usage_to_spools",
                      return_value=[{"sid": 100, "grams": 20.0, "position": 0, "toolhead": "XL-1"}]), \
         patch.object(app_module, "_apply_usage_to_printer",
                      return_value=(1, [{"sid": 100, "grams": 20.0, "remaining": 880.0}])), \
         patch.object(app_module.state, "add_log_entry") as log:
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm",
                                               json={"printer_name": "XL", "job_id": "NS-P", "updates": {}})
    d = r.get_json()
    assert d["status"] == "confirmed"
    assert d["shortfall_g"] == 10.0                                  # 30 requested - 20 applied
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "NS-P")]
    assert entry["grams"] == 20.0                                    # only the applied 20g
    assert any(len(c.args) > 1 and c.args[1] == "WARNING" and "couldn't be applied" in str(c.args[0])
               for c in log.call_args_list), log.call_args_list


def test_apply_usage_records_clamped_grams_not_requested():
    """_apply_usage_to_printer records the ACTUALLY-absorbed grams, not the requested
    amount: Spoolman caps used_weight ≤ initial, so a near-empty spool (5g left) given
    a 20g deduct absorbs only 5g. details must report 5g so the ledger + the callers'
    shortfall math reflect reality, instead of reading the over-capacity deduct as
    fully applied (review finding F-clamp, 2026-06-13)."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    spools = {100: {"id": 100, "used_weight": 995.0, "initial_weight": 1000.0}}  # 5g remaining
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module, "_resolve_active_locs_for_printer",
                      return_value=[("XL-1", {"position": 0})]), \
         patch.object(app_module.spoolman_api, "get_spools_at_location", side_effect=lambda loc: [100]), \
         patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "update_spool", return_value={"id": 100}), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#100", "color": "ff0000"}), \
         patch.object(app_module.state, "add_log_entry"):
        spools_updated, details = app_module._apply_usage_to_printer("XL", {0: 20.0}, "http://fb")
    assert spools_updated == 1
    assert len(details) == 1
    assert details[0]["grams"] == 5.0          # absorbed 5g (clamped), NOT the requested 20g


def test_confirm_no_spool_unexpected_raise_restashes_review():
    """If _confirm_no_spool_review raises unexpectedly after the record was popped
    (the claim), the review must be RE-STASHED (kept recoverable) not lost — the
    pop-without-guard silent-loss the review flagged (2026-06-13)."""
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "NS-R", "filename": "f.gcode", "progress": 1.0,
        "total_grams": 20.0, "spools": [], "kind": "no_spool",
        "usage_map": {"0": 20.0}, "created": "2026-06-13 00:00:00"})
    with patch.object(app_module, "_confirm_no_spool_review", side_effect=RuntimeError("boom")), \
         patch.object(app_module.state, "add_log_entry"):
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm",
                                               json={"printer_name": "XL", "job_id": "NS-R", "updates": {}})
    assert r.status_code == 500 and r.get_json()["status"] == "error"
    assert cancel_review_store.has_pending("XL", "NS-R") is True     # re-stashed, recoverable
    assert print_deduct_ledger.was_deducted("XL", "NS-R") is False


def test_stash_unresolved_neither_flag_defaults_progress_unknown():
    """Defensive (review finding F8): a caller-error call with NEITHER no_spool nor
    progress_unknown must NOT produce a kind='partial' record (empty spools + no
    usage_map) — that would route into the confirm partial loop and 0g-burn the
    ledger. Default to the non-destructive progress_unknown kind."""
    with patch.object(app_module.state, "add_log_entry"):
        out = app_module._stash_unresolved_review("XL", "f.gcode", "NF-1", 0.5)
    assert out["status"] == "pending_unresolved"
    rec = cancel_review_store.get_pending("XL", "NF-1")
    assert rec["kind"] == "progress_unknown"                         # NOT 'partial'
    assert rec["spools"] == [] and rec["usage_map"] is None


def test_confirm_no_spool_still_unbound_restashes_no_ledger():
    """If still no spool is bound at Apply time, the review is RE-STASHED (kept
    recoverable) and reports still_no_spool — never a terminal 0g, never popped."""
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "NS-2", "filename": "f.gcode", "progress": 0.4,
        "total_grams": 20.0, "spools": [], "kind": "no_spool",
        "usage_map": {"0": 20.0}, "created": "2026-06-13 00:00:00"})
    captured = []
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.locations_db, "get_active_printer_map",
                      return_value={"XL-1": {"printer_name": "XL", "position": 0}}), \
         patch.object(app_module, "_resolve_active_locs_for_printer",
                      return_value=[("XL-1", {"position": 0})]), \
         patch.object(app_module.spoolman_api, "get_spools_at_location", side_effect=lambda loc: []), \
         patch.object(app_module.spoolman_api, "update_spool",
                      side_effect=lambda sid, data: captured.append((sid, data))), \
         patch.object(app_module.state, "add_log_entry"):
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm",
                                               json={"printer_name": "XL", "job_id": "NS-2", "updates": {}})
    d = r.get_json()
    assert d["status"] == "still_no_spool"
    assert captured == []                                            # nothing written
    assert print_deduct_ledger.was_deducted("XL", "NS-2") is False   # no terminal 0g
    assert cancel_review_store.has_pending("XL", "NS-2") is True     # re-stashed, recoverable


def test_confirm_progress_unknown_is_manual_only_and_restashes():
    """A progress_unknown review has no usage to auto-apply — confirm must NOT
    0g-'confirm' it (re-loses it). It re-stashes and reports manual_only."""
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "PU-1", "filename": "f.gcode", "progress": 0.0,
        "total_grams": 0.0, "spools": [], "kind": "progress_unknown",
        "usage_map": None, "created": "2026-06-13 00:00:00"})
    r = app_module.app.test_client().post("/api/cancel_deduct/confirm",
                                           json={"printer_name": "XL", "job_id": "PU-1", "updates": {}})
    d = r.get_json()
    assert d["status"] == "manual_only"
    assert print_deduct_ledger.was_deducted("XL", "PU-1") is False
    assert cancel_review_store.has_pending("XL", "PU-1") is True     # kept


def test_dismiss_unresolved_records_zero_ledger():
    """Dismiss is the LEGITIMATE terminal-0g for an unresolved review (user says
    'already handled') — records dismissed + pops it."""
    for jid, kind in (("D-NS", "no_spool"), ("D-PU", "progress_unknown")):
        cancel_review_store.add_pending({
            "printer_name": "XL", "job_id": jid, "filename": "f.gcode", "progress": 0.0,
            "total_grams": 0.0, "spools": [], "kind": kind, "created": "2026-06-13 00:00:00"})
        with patch.object(app_module.state, "add_log_entry"):
            r = app_module.app.test_client().post("/api/cancel_deduct/dismiss",
                                                   json={"printer_name": "XL", "job_id": jid})
        assert r.get_json()["status"] == "dismissed"
        assert print_deduct_ledger.was_deducted("XL", jid) is True
        assert cancel_review_store.has_pending("XL", jid) is False


# ---------------------------------------------------------------------------
# _resolve_usage_to_spools — same-spool-across-positions merge (job 690 fix)
# ---------------------------------------------------------------------------

def test_resolve_usage_merges_same_spool_across_positions():
    """One physical spool feeding TWO toolhead positions (the dev XL-4/XL-5=#230
    case, or any many-positions-one-spool config) must produce ONE row with the
    grams SUMMED. Two rows for one sid would collapse to a single deduct on
    confirm (frontend `updates[sid]` + backend `rec_rows={sid:row}`), the silent
    under-deduct found 2026-06-12 (job 690: 1.65g preview → ~0.8g applied)."""
    printer_map = {"XL-4": {"printer_name": "XL", "position": 3},
                   "XL-5": {"printer_name": "XL", "position": 4}}
    usage_map = {3: 0.84, 4: 0.81}   # both positions feed the SAME spool #230
    spools = {230: {"id": 230, "used_weight": 700.0, "initial_weight": 1258.0}}
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module, "_resolve_active_locs_for_printer",
                      return_value=[("XL-4", {"position": 3}), ("XL-5", {"position": 4})]), \
         patch.object(app_module.spoolman_api, "get_spools_at_location", side_effect=lambda loc: [230]), \
         patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#230", "color": "ff0000"}):
        rows = app_module._resolve_usage_to_spools("XL", usage_map, "http://fb")
    assert len(rows) == 1, "same spool across two positions must merge to one row"
    r = rows[0]
    assert r["sid"] == 230
    assert abs(r["grams"] - 1.65) < 1e-6, "grams summed across both positions (0.84 + 0.81)"
    assert abs(r["remaining_before"] - 558.0) < 1e-6      # 1258 - 700
    assert abs(r["remaining_after"] - 556.35) < 0.06      # 558.0 - 1.65 (rounded to .1)
    assert "XL-4" in r["toolhead"] and "XL-5" in r["toolhead"]


def test_resolve_usage_distinct_spools_stay_separate():
    """Two positions feeding DIFFERENT spools stay as two rows (the normal XL
    toolchanger case — the merge must not over-collapse)."""
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0},
                   "XL-2": {"printer_name": "XL", "position": 1}}
    usage_map = {0: 1.0, 1: 2.0}
    spools = {100: {"id": 100, "used_weight": 50.0, "initial_weight": 1000.0},
              200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0}}
    at = {"XL-1": [100], "XL-2": [200]}
    with patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module, "_resolve_active_locs_for_printer",
                      return_value=[("XL-1", {"position": 0}), ("XL-2", {"position": 1})]), \
         patch.object(app_module.spoolman_api, "get_spools_at_location", side_effect=lambda loc: at.get(str(loc).upper(), [])), \
         patch.object(app_module.spoolman_api, "get_spool", side_effect=lambda sid: spools.get(int(sid))), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#s", "color": "ff0000"}):
        rows = app_module._resolve_usage_to_spools("XL", usage_map, "http://fb")
    assert {r["sid"] for r in rows} == {100, 200}
    assert abs(next(r["grams"] for r in rows if r["sid"] == 100) - 1.0) < 1e-6
    assert abs(next(r["grams"] for r in rows if r["sid"] == 200) - 2.0) < 1e-6


# ---------------------------------------------------------------------------
# Deferred-fetch retry queue (§9.10 — the selected-file download LOCK)
# ---------------------------------------------------------------------------

def _queue(job_id, first_seen=None, progress=0.5):
    cancel_fetch_store.add_pending({
        "printer_name": "XL", "job_id": job_id, "filename": "f.gcode",
        "progress": progress, "first_seen": first_seen if first_seen is not None else time.time(),
        "attempts": 1, "last_status": "awaiting_fetch"})


def test_enqueue_is_idempotent_and_nudges_once():
    with patch.object(app_module.state, "add_log_entry") as log:
        assert app_module._enqueue_cancel_fetch("XL", "f.gcode", "Q-1", 0.5) is True
        first_seen = cancel_fetch_store.get_pending("XL", "Q-1")["first_seen"]
        # Re-queue: bumps attempts, preserves first_seen, does NOT re-nudge.
        assert app_module._enqueue_cancel_fetch("XL", "f.gcode", "Q-1", 0.7) is False
    rec = cancel_fetch_store.get_pending("XL", "Q-1")
    assert rec["attempts"] == 2 and rec["first_seen"] == first_seen
    assert log.call_count == 1   # nudged exactly once


def test_process_fetch_gated_off_while_locked():
    # STOPPED (cancel screen up) and PRINTING (new job) both keep the file
    # locked → no fetch attempt, entry stays queued. Offline (None) too.
    for st in ({"state": "STOPPED"}, {"state": "PRINTING"}, None):
        cancel_fetch_store.add_pending({"printer_name": "XL", "job_id": "G-1",
            "filename": "f.gcode", "progress": 0.5, "first_seen": time.time(), "attempts": 1})
        with patch.object(app_module, "_create_pending_cancel_review") as cpr:
            app_module._process_pending_cancel_fetches({"XL": st}, "http://fb")
            cpr.assert_not_called()
        assert cancel_fetch_store.has_pending("XL", "G-1") is True
        cancel_fetch_store.pop_pending("XL", "G-1")


def test_process_fetch_succeeds_when_idle_creates_review_and_dequeues():
    gcode, frac = _cancelled_gcode()
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}}
    _queue("U-1", progress=frac)
    ctx = _preview_ctx(gcode, printer_map, spools, {"XL-1": [100]}, {"updates": []})
    for m in ctx:
        m.start()
    try:
        app_module._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    finally:
        for m in reversed(ctx):
            m.stop()
    assert cancel_review_store.has_pending("XL", "U-1") is True   # computed + stashed
    assert cancel_fetch_store.has_pending("XL", "U-1") is False   # dequeued


def test_process_fetch_locked_then_unlocks_across_ticks():
    gcode, frac = _cancelled_gcode()
    printer_map = {"XL-1": {"printer_name": "XL", "position": 0}}
    spools = {100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0}}
    _queue("T-1", progress=frac)
    # tick 1 — still STOPPED (locked): no attempt, stays queued
    with patch.object(app_module, "_create_pending_cancel_review") as cpr:
        app_module._process_pending_cancel_fetches({"XL": {"state": "STOPPED"}}, "http://fb")
        cpr.assert_not_called()
    assert cancel_fetch_store.has_pending("XL", "T-1") is True
    # tick 2 — IDLE (unlocked): computes + dequeues
    ctx = _preview_ctx(gcode, printer_map, spools, {"XL-1": [100]}, {"updates": []})
    for m in ctx:
        m.start()
    try:
        app_module._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    finally:
        for m in reversed(ctx):
            m.stop()
    assert cancel_review_store.has_pending("XL", "T-1") is True
    assert cancel_fetch_store.has_pending("XL", "T-1") is False


def test_process_fetch_still_locked_when_idle_stays_queued():
    # IDLE but the download still fails (transient / file deleted) → re-queued,
    # not given up (until the max-age window).
    _queue("S-1")
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.prusalink_api, "fetch_printer_credentials", _creds), \
         patch.object(app_module.prusalink_api, "fetch_cancel_gcode", return_value=None), \
         patch.object(app_module.state, "add_log_entry"):
        app_module._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
    assert cancel_fetch_store.has_pending("XL", "S-1") is True
    assert cancel_review_store.has_pending("XL", "S-1") is False


def test_process_fetch_resolved_in_ledger_drops_entry():
    _queue("R-1")
    print_deduct_ledger.record_deduct("XL", "R-1", filename="f.gcode")
    with patch.object(app_module, "_create_pending_cancel_review") as cpr:
        app_module._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
        cpr.assert_not_called()   # already processed → no re-compute
    assert cancel_fetch_store.has_pending("XL", "R-1") is False


def test_process_fetch_max_age_gives_up_and_records():
    _queue("M-1", first_seen=time.time() - app_module._CANCEL_FETCH_MAX_AGE_S - 10)
    with patch.object(app_module, "_create_pending_cancel_review") as cpr, \
         patch.object(app_module.state, "add_log_entry") as log:
        app_module._process_pending_cancel_fetches({"XL": {"state": "IDLE"}}, "http://fb")
        cpr.assert_not_called()
    assert cancel_fetch_store.has_pending("XL", "M-1") is False
    assert print_deduct_ledger.was_deducted("XL", "M-1") is True   # grams=0 so it can't re-queue
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
