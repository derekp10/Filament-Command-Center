"""Group 22.4 — deduct-path code-review follow-ups.

Pins the robustness/cleanup fixes layered onto the FCC-native print-deduct path:

  22.4(1) Multi-spool-at-one-toolhead: a stale physical_source GHOST + the current
          load no longer N×-over-deducts a position (select_deduct_targets prefers
          the directly-loaded spool); a genuinely-ambiguous 2+-loaded toolhead is
          WARNed + SKIPPED in the autonomous apply, KEPT (flagged) in the preview.
          The legitimate shared-spool-feeding-two-positions accumulation is preserved
          (the load-bearing guard, with a STATEFUL spool mock so a stale re-read
          can't pass vacuously).
  22.4(2) _record_applied_deduct records the APPLIED grams (not the requested sum) —
          erases deduct_cancelled_print's ledger drift.
  22.4(3) shortfall computed over KNOWN toolhead positions so an orphan tool index
          isn't double-warned.
  22.4(4) shortfall WARN is 2dp (matches the shortfall_g API field).
  22.4(5) the no_spool confirm probes info.mmu ONCE (threaded active_locs).
  22.4(6) the live active→IDLE ambiguous edge AND restart recovery thread
          progress_unknown for an unsampled latch (non-destructive review, not a 0%
          compute).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
import print_deduct  # L316: patch targets / live seams for moved symbols
import print_monitor  # L316: patch targets for moved symbols  # noqa: E402
import spoolman_api  # noqa: E402
import print_deduct_ledger  # noqa: E402
import cancel_review_store  # noqa: E402
import cancel_fetch_store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_tracker():
    app_module._PRINT_TRACKER.clear()
    prev_async = print_monitor._CANCEL_DEDUCT_RUN_ASYNC
    print_monitor._CANCEL_DEDUCT_RUN_ASYNC = False  # synchronous dispatch
    try:
        yield
    finally:
        print_monitor._CANCEL_DEDUCT_RUN_ASYNC = prev_async
        app_module._PRINT_TRACKER.clear()


@pytest.fixture
def stores_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))


class _Spools:
    """Stateful spool store: update_spool mutates used_weight so a later get_spool
    RE-READS the new value — required for the shared-spool accumulation test (a
    naive constant-return mock would make a stale-read regression pass vacuously)."""

    def __init__(self, init):
        self.d = {int(sid): dict(v) for sid, v in init.items()}
        self.updates = []

    def get(self, sid):
        v = self.d.get(int(sid))
        return {"id": int(sid), **v} if v else None

    def update(self, sid, data):
        self.updates.append((int(sid), dict(data)))
        self.d[int(sid)].update(data)
        return {"id": int(sid), **data}


def _apply_ctx(printer_map, active_locs, detailed_at, spools, logs=None):
    """Patch the Spoolman/printer surface _apply_usage_to_printer touches. `detailed_at`
    is {LOC: [{'id', 'is_ghost'}, ...]}; get_spools_at_location is derived from it so
    the IDs path and the detailed/select path stay consistent."""
    def _ids(loc):
        return [it["id"] for it in detailed_at.get(str(loc).upper(), [])]

    ctx = [
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map),
        patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active_locs),
        patch.object(app_module.spoolman_api, "get_spools_at_location", side_effect=_ids),
        patch.object(app_module.spoolman_api, "get_spools_at_location_detailed",
                     side_effect=lambda loc: detailed_at.get(str(loc).upper(), [])),
        patch.object(app_module.spoolman_api, "get_spool", side_effect=spools.get),
        patch.object(app_module.spoolman_api, "update_spool", side_effect=spools.update),
        patch.object(app_module.spoolman_api, "format_spool_display",
                     return_value={"text": "#s", "color": "ff0000", "slot": "", "details": {}}),
    ]
    if logs is not None:
        ctx.append(patch.object(app_module.state, "add_log_entry",
                                side_effect=lambda *a, **k: logs.append(a)))
    else:
        ctx.append(patch.object(app_module.state, "add_log_entry"))
    return ctx


def _with(ctx):
    for m in ctx:
        m.start()


def _without(ctx):
    for m in reversed(ctx):
        m.stop()


# --------------------------------------------------------------------------- #
# 22.4(0/1) — spoolman_api.select_deduct_targets                              #
# --------------------------------------------------------------------------- #

def _detailed(*pairs):
    return [{"id": sid, "is_ghost": g} for sid, g in pairs]


def test_select_direct_wins_over_ghost():
    with patch.object(spoolman_api, "get_spools_at_location_detailed",
                      return_value=_detailed((100, False), (999, True))):
        sids, amb = spoolman_api.select_deduct_targets("XL-1")
    assert sids == [100] and amb is False   # ghost dropped, single direct


def test_select_single_direct_common_case():
    with patch.object(spoolman_api, "get_spools_at_location_detailed",
                      return_value=_detailed((100, False))):
        assert spoolman_api.select_deduct_targets("XL-1") == ([100], False)


def test_select_ghost_only_still_returned():
    with patch.object(spoolman_api, "get_spools_at_location_detailed",
                      return_value=_detailed((999, True))):
        assert spoolman_api.select_deduct_targets("XL-1") == ([999], False)


def test_select_two_distinct_direct_flags_ambiguous():
    with patch.object(spoolman_api, "get_spools_at_location_detailed",
                      return_value=_detailed((100, False), (200, False))):
        sids, amb = spoolman_api.select_deduct_targets("XL-1")
    assert sorted(sids) == [100, 200] and amb is True


def test_select_no_match_empty():
    with patch.object(spoolman_api, "get_spools_at_location_detailed", return_value=[]):
        assert spoolman_api.select_deduct_targets("XL-1") == ([], False)


def test_select_two_distinct_ghosts_flags_ambiguous():
    """No direct match + 2 distinct ghosts -> the ghost-only `else` arm still flags
    ambiguous (len(out) > 1)."""
    with patch.object(spoolman_api, "get_spools_at_location_detailed",
                      return_value=_detailed((998, True), (999, True))):
        sids, amb = spoolman_api.select_deduct_targets("XL-1")
    assert sorted(sids) == [998, 999] and amb is True


# --------------------------------------------------------------------------- #
# 22.4(1) — _apply_usage_to_printer multi-spool resolution                     #
# --------------------------------------------------------------------------- #

def test_apply_ghost_plus_current_deducts_once():
    spools = _Spools({100: {"used_weight": 100.0, "initial_weight": 1000.0},
                      999: {"used_weight": 50.0, "initial_weight": 1000.0}})
    ctx = _apply_ctx(
        {"XL-1": {"printer_name": "XL", "position": 0}},
        [("XL-1", {"position": 0})],
        {"XL-1": _detailed((100, False), (999, True))}, spools)
    _with(ctx)
    try:
        updated, details, known = app_module._apply_usage_to_printer("XL", {0: 30.0}, "http://fb")
    finally:
        _without(ctx)
    assert updated == 1
    assert spools.updates == [(100, {"used_weight": 130.0})]   # current only, NOT the ghost 999
    assert known == {0}


def test_apply_shared_spool_two_positions_accumulates():
    """The load-bearing guard (job-690): one spool feeding two positions is deducted
    once PER position, ADDITIVELY against the live used_weight (re-read between
    writes). Asserts the ORDERED writes, not just the total, so a stale-read can't
    pass vacuously."""
    spools = _Spools({230: {"used_weight": 700.0, "initial_weight": 1258.0}})
    ctx = _apply_ctx(
        {"XL-4": {"printer_name": "XL", "position": 3},
         "XL-5": {"printer_name": "XL", "position": 4}},
        [("XL-4", {"position": 3}), ("XL-5", {"position": 4})],
        {"XL-4": _detailed((230, False)), "XL-5": _detailed((230, False))}, spools)
    _with(ctx)
    try:
        updated, details, known = app_module._apply_usage_to_printer("XL", {3: 5.0, 4: 7.0}, "http://fb")
    finally:
        _without(ctx)
    assert updated == 2
    # pos3 first (700→705), pos4 re-reads 705 → 712 — NOT 707 (stale) and NOT 705 twice.
    assert spools.updates == [(230, {"used_weight": 705.0}), (230, {"used_weight": 712.0})]


def test_apply_two_distinct_direct_warns_and_skips():
    """2+ distinct LOADED spools at one toolhead is unresolvable — the autonomous
    apply must NOT guess (which over-deducts or hits the wrong spool): warn + skip,
    so the grams surface as a shortfall in the caller."""
    spools = _Spools({100: {"used_weight": 100.0, "initial_weight": 1000.0},
                      200: {"used_weight": 100.0, "initial_weight": 1000.0}})
    logs = []
    ctx = _apply_ctx(
        {"XL-1": {"printer_name": "XL", "position": 0}},
        [("XL-1", {"position": 0})],
        {"XL-1": _detailed((100, False), (200, False))}, spools, logs=logs)
    _with(ctx)
    try:
        updated, details, known = app_module._apply_usage_to_printer("XL", {0: 30.0}, "http://fb")
    finally:
        _without(ctx)
    assert updated == 0 and details == []
    assert spools.updates == []   # NOTHING deducted
    assert any(len(a) > 1 and a[1] == "WARNING" and "100" in a[0] and "200" in a[0]
               and "not deducted" in a[0] for a in logs), logs


def test_apply_multitool_one_ghost_only_position_both_deduct():
    """Multi-tool: pos0 has the current load, pos1 has only a stale ghost (len==1, so
    select isn't invoked) — both deduct their own per-position grams (ghost-only
    fallback preserves today's recoverability across positions)."""
    spools = _Spools({100: {"used_weight": 10.0, "initial_weight": 1000.0},
                      999: {"used_weight": 10.0, "initial_weight": 1000.0}})
    ctx = _apply_ctx(
        {"XL-1": {"printer_name": "XL", "position": 0},
         "XL-2": {"printer_name": "XL", "position": 1}},
        [("XL-1", {"position": 0}), ("XL-2", {"position": 1})],
        {"XL-1": _detailed((100, False)), "XL-2": _detailed((999, True))}, spools)
    _with(ctx)
    try:
        updated, details, known = app_module._apply_usage_to_printer("XL", {0: 10.0, 1: 20.0}, "http://fb")
    finally:
        _without(ctx)
    assert updated == 2
    assert {sid for sid, _ in spools.updates} == {100, 999}


def test_apply_orphan_tool_warns_and_returns_known():
    """A tool index mapping to no toolhead position gets the orphan WARNING and is
    excluded from known_positions (so the caller's shortfall won't double-warn it)."""
    spools = _Spools({100: {"used_weight": 10.0, "initial_weight": 1000.0}})
    logs = []
    ctx = _apply_ctx(
        {"XL-1": {"printer_name": "XL", "position": 0}},
        [("XL-1", {"position": 0})],
        {"XL-1": _detailed((100, False))}, spools, logs=logs)
    _with(ctx)
    try:
        updated, details, known = app_module._apply_usage_to_printer("XL", {0: 40.0, 9: 30.0}, "http://fb")
    finally:
        _without(ctx)
    assert updated == 1 and known == {0}
    assert any(len(a) > 1 and a[1] == "WARNING" and "no toolhead position" in a[0] for a in logs), logs


# --------------------------------------------------------------------------- #
# 22.4(1) — _resolve_usage_to_spools mirrors the resolution (preview)          #
# --------------------------------------------------------------------------- #

def test_resolve_ghost_dropped_single_row():
    spools = _Spools({100: {"used_weight": 100.0, "initial_weight": 1000.0},
                      999: {"used_weight": 50.0, "initial_weight": 1000.0}})
    ctx = _apply_ctx(
        {"XL-1": {"printer_name": "XL", "position": 0}},
        [("XL-1", {"position": 0})],
        {"XL-1": _detailed((100, False), (999, True))}, spools)
    _with(ctx)
    try:
        rows = app_module._resolve_usage_to_spools("XL", {0: 30.0}, "http://fb")
    finally:
        _without(ctx)
    assert [r["sid"] for r in rows] == [100]
    assert rows[0]["ambiguous"] is False


def test_resolve_two_distinct_direct_keeps_both_flagged():
    """Unlike the apply (which skips), the interactive preview KEEPS both rows so the
    reviewer can resolve the bad assignment — each flagged ambiguous."""
    spools = _Spools({100: {"used_weight": 100.0, "initial_weight": 1000.0},
                      200: {"used_weight": 100.0, "initial_weight": 1000.0}})
    ctx = _apply_ctx(
        {"XL-1": {"printer_name": "XL", "position": 0}},
        [("XL-1", {"position": 0})],
        {"XL-1": _detailed((100, False), (200, False))}, spools)
    _with(ctx)
    try:
        rows = app_module._resolve_usage_to_spools("XL", {0: 30.0}, "http://fb")
    finally:
        _without(ctx)
    assert {r["sid"] for r in rows} == {100, 200}
    assert all(r["ambiguous"] is True for r in rows)


# --------------------------------------------------------------------------- #
# 22.4(2)/(3)/(4) — _record_applied_deduct                                     #
# --------------------------------------------------------------------------- #

def test_record_applied_records_applied_not_requested(stores_tmp):
    details = [{"sid": 100, "grams": 40.0, "remaining": 800.0}]
    with patch.object(app_module.state, "add_log_entry"):
        applied, shortfall = app_module._record_applied_deduct(
            "XL", "J-1", filename="f", scale=1.0, details=details,
            usage_map={0: 40.0, 1: 25.0}, known_positions={0, 1})
    assert applied == 40.0 and shortfall == 25.0
    assert print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-1")]["grams"] == 40.0


def test_record_applied_shortfall_warns_2dp(stores_tmp):
    logs = []
    details = [{"sid": 100, "grams": 10.0, "remaining": 0.0}]
    with patch.object(app_module.state, "add_log_entry", side_effect=lambda *a, **k: logs.append(a)):
        _, shortfall = app_module._record_applied_deduct(
            "XL", "J-2", filename="f", scale=1.0, details=details,
            usage_map={0: 35.5}, known_positions={0})
    assert shortfall == 25.5
    assert any(len(a) > 1 and a[1] == "WARNING" and "25.50" in a[0] for a in logs), logs


def test_record_applied_orphan_excluded_no_warn(stores_tmp):
    """Tool 9 is an orphan (not in known_positions); its 30g must NOT create a
    phantom shortfall on top of the apply loop's own orphan WARNING (22.4(3))."""
    logs = []
    details = [{"sid": 100, "grams": 40.0, "remaining": 800.0}]
    with patch.object(app_module.state, "add_log_entry", side_effect=lambda *a, **k: logs.append(a)):
        _, shortfall = app_module._record_applied_deduct(
            "XL", "J-3", filename="f", scale=1.0, details=details,
            usage_map={0: 40.0, 9: 30.0}, known_positions={0})
    assert shortfall == 0.0
    assert not any(len(a) > 1 and a[1] == "WARNING" for a in logs), logs


def test_record_applied_confirmed_flag(stores_tmp):
    with patch.object(app_module.state, "add_log_entry"):
        app_module._record_applied_deduct(
            "XL", "J-4", filename="f", scale=1.0,
            details=[{"sid": 1, "grams": 5.0, "remaining": 1.0}],
            usage_map={0: 5.0}, known_positions={0}, confirmed=True)
    assert print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-4")]["confirmed"] is True


def test_record_applied_unconfirmed_omits_flag(stores_tmp):
    with patch.object(app_module.state, "add_log_entry"):
        app_module._record_applied_deduct(
            "XL", "J-5", filename="f", scale=1.0,
            details=[{"sid": 1, "grams": 5.0, "remaining": 1.0}],
            usage_map={0: 5.0}, known_positions={0})
    # Same shape as the pre-22.4 sites — no `confirmed` key when not confirmed.
    assert "confirmed" not in print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-5")]


def test_cancelled_print_ledger_records_applied_not_requested(stores_tmp):
    """deduct_cancelled_print used to record sum(usage_map) (the full requested) — the
    drift. With a near-empty spool capping the absorbed grams, applied < requested,
    so the ledger must record the APPLIED grams (22.4(2))."""
    spools = _Spools({100: {"used_weight": 995.0, "initial_weight": 1000.0}})  # 5g left
    gcode = "M83\nT0\nG1 X10 E10\n; filament used [mm] = 10\n; filament used [g] = 20\n"
    ctx = _apply_ctx(
        {"XL-1": {"printer_name": "XL", "position": 0}},
        [("XL-1", {"position": 0})],
        {"XL-1": _detailed((100, False))}, spools)
    ctx.append(patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                            side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": 1.0}))
    _with(ctx)
    try:
        res = app_module.deduct_cancelled_print(
            "XL", "f.gcode", "C-1", 1.0, fb_url="http://fb", ip_address="1.2.3.4", api_key="k")
    finally:
        _without(ctx)
    assert res["status"] == "deducted"
    # Footer/prefix computes 20g but the spool caps at 5g remaining → applied 5g.
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "C-1")]
    assert entry["grams"] == 5.0, entry   # APPLIED 5g, NOT requested 20g


def test_completed_ambiguous_skip_surfaces_shortfall(stores_tmp):
    """End-to-end: an ambiguous toolhead (2 distinct direct spools) is skipped by the
    apply loop; because known_positions still includes it, its grams surface as a
    shortfall WARNING in the caller (not silently lost). Pins the integration the
    unit-level skip test only claims (22.4(1)+(3))."""
    spools = _Spools({100: {"used_weight": 0.0, "initial_weight": 1000.0},
                      200: {"used_weight": 0.0, "initial_weight": 1000.0},
                      300: {"used_weight": 0.0, "initial_weight": 1000.0}})
    detailed_at = {"XL-1": _detailed((100, False)),
                   "XL-2": _detailed((200, False), (300, False))}   # pos1 = 2 distinct direct
    gcode = "; filament used [g] = 25, 40\n"
    logs = []
    ctx = _apply_ctx({"XL-1": {"printer_name": "XL", "position": 0},
                      "XL-2": {"printer_name": "XL", "position": 1}},
                     [("XL-1", {"position": 0}), ("XL-2", {"position": 1})],
                     detailed_at, spools, logs=logs)
    ctx += [
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.prusalink_api, "fetch_printer_credentials",
                     return_value={"ip_address": "1.2.3.4", "api_key": "k"}),
        patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                     side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}),
    ]
    _with(ctx)
    try:
        res = app_module.deduct_completed_print("XL", "done.gcode", "J-AS")
    finally:
        _without(ctx)
    assert res["status"] == "deducted"
    assert spools.updates == [(100, {"used_weight": 25.0})]          # pos0 only; pos1 skipped
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-AS")]
    assert entry["grams"] == 25.0                                    # applied, not the full 65
    # the 40g of the skipped ambiguous toolhead surfaces as a shortfall WARNING...
    assert any(len(a) > 1 and a[1] == "WARNING" and "40.00" in a[0] and "wasn't deducted" in a[0]
               for a in logs), logs
    # ...AND the ambiguous-skip WARNING names both contending spools.
    assert any(len(a) > 1 and a[1] == "WARNING" and "200" in a[0] and "300" in a[0] for a in logs), logs


# --------------------------------------------------------------------------- #
# 22.4(5) — no_spool confirm probes info.mmu ONCE                              #
# --------------------------------------------------------------------------- #

def test_no_spool_confirm_probes_mmu_once(stores_tmp):
    """_confirm_no_spool_review resolves active_locs once and threads it to BOTH the
    preview resolve and the apply, so an MMU-aliased printer's info.mmu ordering probe
    runs once (was twice). Needs an ALIASED printer_map (two entries sharing a
    position) — else _resolve_active_locs_for_printer short-circuits with no probe and
    the test would prove nothing."""
    printer_map = {"CORE1-M0": {"printer_name": "CORE1", "position": 0},
                   "CORE1-M1": {"printer_name": "CORE1", "position": 0}}
    spools = _Spools({100: {"used_weight": 100.0, "initial_weight": 1000.0}})
    detailed_at = {"CORE1-M0": _detailed((100, False)), "CORE1-M1": []}
    cancel_review_store.add_pending({
        "printer_name": "CORE1", "job_id": "NS-1", "filename": "f.gcode", "progress": 1.0,
        "total_grams": 10.0, "spools": [], "kind": "no_spool",
        "usage_map": {"0": 10.0}, "created": "2026-06-14 00:00:00"})
    with patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(app_module.locations_db, "get_active_printer_map", return_value=printer_map), \
         patch.object(app_module.prusalink_api, "get_printer_mmu_flag", return_value=False) as mmu, \
         patch.object(app_module.spoolman_api, "get_spools_at_location",
                      side_effect=lambda loc: [it["id"] for it in detailed_at.get(str(loc).upper(), [])]), \
         patch.object(app_module.spoolman_api, "get_spools_at_location_detailed",
                      side_effect=lambda loc: detailed_at.get(str(loc).upper(), [])), \
         patch.object(app_module.spoolman_api, "get_spool", side_effect=spools.get), \
         patch.object(app_module.spoolman_api, "update_spool", side_effect=spools.update), \
         patch.object(app_module.spoolman_api, "format_spool_display",
                      return_value={"text": "#100", "color": "ff0000", "slot": "", "details": {}}), \
         patch.object(app_module.state, "add_log_entry"):
        r = app_module.app.test_client().post(
            "/api/cancel_deduct/confirm",
            json={"printer_name": "CORE1", "job_id": "NS-1", "updates": {}})
    assert r.get_json()["status"] == "confirmed"
    assert mmu.call_count == 1, f"expected ONE info.mmu probe, got {mmu.call_count}"


# --------------------------------------------------------------------------- #
# 22.4(6) — progress_unknown threaded to ambiguous edge + restart recovery     #
# --------------------------------------------------------------------------- #

def _latch(printer, state, job, fb="http://fb"):
    with patch.object(app_module.prusalink_api, "get_printer_job", return_value=job):
        app_module._track_print_edge(printer, {"state": state}, fb)


def test_live_ambiguous_unsampled_routes_progress_unknown():
    # PRINTING with progress=None → latch has filename but NO 'progress' key.
    _latch("XL", "PRINTING", {"filename": "f.gcode", "job_id": 7, "progress": None})
    with patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp:
        app_module._track_print_edge("XL", {"state": "IDLE"}, "http://fb")
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("progress_unknown") is True


def test_live_ambiguous_sampled_routes_normal():
    _latch("XL", "PRINTING", {"filename": "f.gcode", "job_id": 7, "progress": 0.5})
    with patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp:
        app_module._track_print_edge("XL", {"state": "IDLE"}, "http://fb")
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("progress_unknown") is False
    assert disp.call_args.args[3] == 0.5   # the sampled progress


def test_recover_idle_unsampled_progress_unknown():
    # Entry built WITHOUT a 'progress' key (the _entry helper elsewhere always sets
    # one, so construct it literally) → unsampled → progress_unknown=True.
    entry = {"state": "PRINTING", "job_id": 7, "filename": "f.gcode"}
    with patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "IDLE"}), \
         patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp, \
         patch.object(app_module.state, "add_log_entry"):
        acted = app_module._recover_one_print_latch("XL", entry, "http://fb")
    assert acted is True
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("progress_unknown") is True


def test_recover_idle_sampled_normal():
    entry = {"state": "PRINTING", "job_id": 7, "filename": "f.gcode", "progress": 0.6}
    with patch.object(app_module.prusalink_api, "get_printer_state", return_value={"state": "IDLE"}), \
         patch.object(print_monitor, "_dispatch_ambiguous_edge") as disp, \
         patch.object(app_module.state, "add_log_entry"):
        app_module._recover_one_print_latch("XL", entry, "http://fb")
    disp.assert_called_once()
    assert disp.call_args.kwargs.get("progress_unknown") is False
    assert disp.call_args.args[3] == 0.6
