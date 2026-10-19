"""Group 43: deduct recovery and attribution.

Every test here drives the REAL deduct loop (`print_deduct._apply_usage_to_printer`)
and the REAL `spoolman_api.get_spool` / `update_spool`, with only the HTTP layer
faked ([[mocked engine hides chain bugs]]). That matters for 43.1 above all: the
bug lives in update_spool's `used_weight <= initial_weight` cap, which applies
only when the spool carries its OWN initial_weight.

43.1 — a spool with no initial_weight of its own (it inherits its filament's net
weight, exactly how Spoolman computes remaining_weight). The deduct computed
`initial = 0`, so it recorded 0 g applied (and a full-size shortfall WARNING),
while the write itself was unclamped and charged the spool in full. Once a
shortfall becomes actionable (43.2) that is a double-deduct generator. Now the
deduct clamps against the EFFECTIVE initial weight (own, else filament), the
write is clamped to it too, and a spool with no known capacity at all is charged
as before but recorded in full and logged as such.

HEAD proof: on the pre-fix print_deduct.py the 43.1 tests record 0 g, raise the
shortfall WARNING, and leave the near-empty spool's used_weight above its
filament weight.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402
from deduct_wire_harness import WeightWireSpoolman, _start, _stop, _wire_ctx  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    """The pending-review, deferred-fetch and ledger stores are JSON files under
    data/; never let a test touch the real ones."""
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))


@pytest.fixture
def ledger_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))


@pytest.fixture
def logs(monkeypatch):
    calls = []
    monkeypatch.setattr(state, "add_log_entry", lambda msg, *a, **k: calls.append((msg, a)))
    return calls


def _apply(sm, usage_map, toolheads=(("XL-1", 0),), at=None, printer="XL", label="Complete"):
    """Run the real deduct loop against `sm` for `printer`'s heads."""
    at = at or {"XL-1": [100]}
    active = [(loc, {"position": pos, "printer_name": printer}) for loc, pos in toolheads]
    with patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}), \
         patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active), \
         patch.object(spoolman_api, "get_spools_at_location", side_effect=lambda loc: list(at.get(str(loc).upper(), []))), \
         patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")), \
         patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}), \
         patch.object(spoolman_api.requests, "get", side_effect=sm._get), \
         patch.object(spoolman_api.requests, "patch", side_effect=sm._patch):
        return print_deduct._apply_usage_to_printer(printer, usage_map, "http://fb", strategy_label=label)


def _inherit_spool(used, filament_weight=1000.0):
    return {"used_weight": used, "initial_weight": None, "archived": False, "location": "XL-1",
            "filament": {"id": 7, "weight": filament_weight}, "extra": {}}


# --------------------------------------------------------------------------- #
# 43.1 — clamp against the EFFECTIVE initial weight                           #
# --------------------------------------------------------------------------- #

def test_inherit_weight_spool_records_what_it_absorbed(ledger_tmp, logs):
    """The task file's pin: initial_weight null + a 1000 g filament takes 50 g →
    the ledger records 50 g, with no shortfall WARNING. HEAD recorded 0 g."""
    sm = WeightWireSpoolman({100: _inherit_spool(used=100.0)})
    updated, details, known = _apply(sm, {0: 50.0})
    assert updated == 1 and details[0]["grams"] == 50.0, details
    assert sm.used(100) == 150.0
    applied, shortfall = print_deduct._record_applied_deduct(
        "XL", "J-431", filename="f.bgcode", scale=1.0, details=details,
        usage_map={0: 50.0}, known_positions=known)
    assert applied == 50.0 and shortfall == 0.0
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-431")]
    assert entry["grams"] == 50.0
    assert not any("wasn't deducted" in m for m, _ in logs), logs


def test_near_empty_inherit_spool_is_clamped_and_the_rest_is_a_shortfall(ledger_tmp, logs):
    """10 g left on the filament's 1000 g: the spool takes 10 g (its used_weight
    stops at 1000, not 1040) and the other 40 g is the shortfall. HEAD charged all
    50 g to the spool while recording 0 g: the double-deduct shape."""
    sm = WeightWireSpoolman({100: _inherit_spool(used=990.0)})
    updated, details, known = _apply(sm, {0: 50.0})
    assert details[0]["grams"] == 10.0, details
    assert sm.used(100) == 1000.0, "the write must be clamped to the effective initial weight"
    applied, shortfall = print_deduct._record_applied_deduct(
        "XL", "J-432", filename="f.bgcode", scale=1.0, details=details,
        usage_map={0: 50.0}, known_positions=known)
    assert (applied, shortfall) == (10.0, 40.0)
    assert sm.spools[100]["archived"] is True, "emptied → auto-archived (the real update_spool rule)"


def test_unknown_capacity_is_charged_in_full_and_recorded_in_full(ledger_tmp, logs):
    """Neither the spool nor its filament has a weight: the remaining is unknown.
    Charge the grams as before, record them as applied, and say so."""
    sm = WeightWireSpoolman({100: _inherit_spool(used=100.0, filament_weight=None)})
    updated, details, known = _apply(sm, {0: 50.0})
    assert details[0]["grams"] == 50.0 and sm.used(100) == 150.0
    _, shortfall = print_deduct._record_applied_deduct(
        "XL", "J-433", filename="f.bgcode", scale=1.0, details=details,
        usage_map={0: 50.0}, known_positions=known)
    assert shortfall == 0.0
    assert any("no known capacity" in m.lower() for m, _ in logs), logs


def test_own_initial_weight_is_unchanged(ledger_tmp, logs):
    """Regression: a spool with its own initial_weight clamps exactly as before."""
    sm = WeightWireSpoolman({100: {"used_weight": 995.0, "initial_weight": 1000.0, "archived": False,
                                   "location": "XL-1", "filament": {"weight": 750.0}, "extra": {}}})
    _, details, _ = _apply(sm, {0: 20.0})
    assert details[0]["grams"] == 5.0 and sm.used(100) == 1000.0


@pytest.mark.parametrize("spool,expected", [
    ({"initial_weight": 1000.0, "filament": {"weight": 750.0}}, 1000.0),   # own wins
    ({"initial_weight": None, "filament": {"weight": 750.0}}, 750.0),      # inherited
    ({"initial_weight": 0, "filament": {"weight": 750.0}}, 0.0),           # an own 0 is a real 0
    ({"initial_weight": None, "filament": {"weight": None}}, None),
    ({"initial_weight": None}, None),
    ({"initial_weight": "abc"}, None),
    (None, None),
])
def test_effective_initial_weight_mirrors_the_auto_archive_rule(spool, expected):
    assert spoolman_api.effective_initial_weight(spool) == expected


def test_review_preview_shows_an_inherit_weight_spools_real_remaining(logs):
    """The same `initial_weight or 0` read sat in the review PREVIEW: the card said
    "0 g left" for every inherit-weight spool."""
    sm = WeightWireSpoolman({100: _inherit_spool(used=100.0)})
    ctx = _wire_ctx(sm)
    _start(ctx)
    try:
        rows = print_deduct._resolve_usage_to_spools("XL", {0: 50.0}, "http://fb")
    finally:
        _stop(ctx)
    assert rows[0]["initial_weight"] == 1000.0
    assert rows[0]["remaining_before"] == 900.0 and rows[0]["remaining_after"] == 850.0


def test_review_preview_with_no_known_capacity_says_so(logs):
    sm = WeightWireSpoolman({100: _inherit_spool(used=100.0, filament_weight=None)})
    ctx = _wire_ctx(sm)
    _start(ctx)
    try:
        rows = print_deduct._resolve_usage_to_spools("XL", {0: 50.0}, "http://fb")
    finally:
        _stop(ctx)
    assert rows[0]["remaining_before"] is None and rows[0]["remaining_after"] is None


def test_review_confirm_charges_an_inherit_weight_spool(logs):
    """...and in the CONFIRM: grams were clamped to `0 - used`, so confirming a
    review for an inherit-weight spool charged NOTHING and still burned the
    ledger — a silent loss."""
    sm = WeightWireSpoolman({100: _inherit_spool(used=100.0)})
    cancel_review_store.add_pending({
        "printer_name": "XL", "job_id": "J-434", "filename": "f.bgcode", "progress": 0.5,
        "total_grams": 50.0, "ambiguous": False, "created": "2026-10-13 00:00:00",
        "spools": [{"sid": 100, "toolhead": "XL-1", "position": 0, "grams": 50.0}]})
    ctx = _wire_ctx(sm)
    _start(ctx)
    try:
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": "XL", "job_id": "J-434", "updates": {"100": 50.0}})
    finally:
        _stop(ctx)
    body = r.get_json()
    assert body["status"] == "confirmed", body
    assert body["applied"][0]["grams"] == 50.0, body
    assert sm.used(100) == 150.0
    entry = print_deduct_ledger._load()[print_deduct_ledger._key("XL", "J-434")]
    assert entry["grams"] == 50.0


# --------------------------------------------------------------------------- #
# 43.5 — deduct log lines name the printer and the toolhead                   #
# --------------------------------------------------------------------------- #
# Derek: "Because I'm running multiple printers with multiple toolheads we
# should probably change these log messages to report the toolhead/location and
# printer so it's clearer where the deduction occurred."

INDX = "🦝 Core One INDX"


def _full_spool(used=43.4, initial=1000.0):
    return {"used_weight": used, "initial_weight": initial, "archived": False,
            "location": "RCOI-2", "filament": {"weight": 1000.0}, "extra": {}}


def _msgs(logs):
    return [m for m, _ in logs]


def test_per_spool_line_names_printer_and_toolhead(logs):
    sm = WeightWireSpoolman({96: _full_spool()})
    _, details, _ = _apply(sm, {1: 7.4}, toolheads=(("RCOI-2", 1),), at={"RCOI-2": [96]}, printer=INDX)
    line = next(m for m in _msgs(logs) if "Spool #96" in m)
    assert line.startswith(f"✔️ {INDX} RCOI-2: auto-deducted 7.4g from Spool #96 (Complete)"), line
    assert details[0]["toolhead"] == "RCOI-2"


def test_failed_write_line_names_printer_and_toolhead(logs):
    sm = WeightWireSpoolman({96: _full_spool()}, patch_fails={96})
    with patch.object(spoolman_api, "get_spool", side_effect=lambda sid: {"id": 96, **_full_spool()}):
        updated, _, _ = _apply(sm, {1: 7.4}, toolheads=(("RCOI-2", 1),), at={"RCOI-2": [96]}, printer=INDX)
    assert updated == 0
    line = next(m for m in _msgs(logs) if m.startswith("❌"))
    assert line.startswith(f"❌ {INDX} RCOI-2: failed to auto-deduct from Spool #96"), line


def _summary_ctx(sm, usage_map, at, toolheads, printer):
    ctx = _wire_ctx(sm, at=at, toolheads=toolheads, printer=printer)
    ctx += [
        patch.object(print_deduct, "_compute_cancel_usage", return_value=(usage_map, None)),
        patch.object(print_deduct.prusalink_api, "fetch_printer_credentials",
                     return_value={"ip_address": "10.0.0.9", "api_key": "k"}),
    ]
    return ctx


def test_completion_summary_lists_the_toolheads_charged(logs):
    sm = WeightWireSpoolman({96: _full_spool(), 97: _full_spool()})
    ctx = _summary_ctx(sm, {1: 7.4, 3: 2.0}, at={"RCOI-2": [96], "RCOI-4": [97]},
                       toolheads=(("RCOI-2", 1), ("RCOI-4", 3)), printer=INDX)
    _start(ctx)
    try:
        res = print_deduct.deduct_completed_print(INDX, "/usb/STAND(~1.BGC", "J-435")
    finally:
        _stop(ctx)
    assert res["status"] == "deducted", res
    line = next(m for m in _msgs(logs) if m.startswith("✅ Completed-print deduct"))
    assert line.startswith(f"✅ Completed-print deduct on {INDX} [RCOI-2, RCOI-4]: 9.4g across 2 spool(s)"), line


def test_cancel_summary_lists_the_toolheads_charged(logs):
    sm = WeightWireSpoolman({96: _full_spool()})
    ctx = _summary_ctx(sm, {1: 3.3}, at={"RCOI-2": [96]}, toolheads=(("RCOI-2", 1),), printer=INDX)
    _start(ctx)
    try:
        res = print_deduct.deduct_cancelled_print(INDX, "/usb/X.BGC", "J-436", 0.4)
    finally:
        _stop(ctx)
    assert res["status"] == "deducted", res
    line = next(m for m in _msgs(logs) if m.startswith("🛑 Cancelled-print partial deduct"))
    assert line.startswith(f"🛑 Cancelled-print partial deduct on {INDX} [RCOI-2]: 3.3g across 1 spool(s)"), line


def test_review_confirm_line_names_printer_and_toolhead(logs):
    sm = WeightWireSpoolman({96: _full_spool()})
    cancel_review_store.add_pending({
        "printer_name": INDX, "job_id": "J-437", "filename": "f.bgcode", "progress": 0.5,
        "total_grams": 2.5, "ambiguous": False, "created": "2026-10-13 00:00:00",
        "spools": [{"sid": 96, "toolhead": "RCOI-2", "position": 1, "grams": 2.5}]})
    ctx = _wire_ctx(sm, at={"RCOI-2": [96]}, toolheads=(("RCOI-2", 1),), printer=INDX)
    _start(ctx)
    try:
        r = app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": INDX, "job_id": "J-437", "updates": {"96": 2.5}})
    finally:
        _stop(ctx)
    assert r.get_json()["status"] == "confirmed"
    line = next(m for m in _msgs(logs) if "Spool #96" in m)
    assert line.startswith(f"✔️ {INDX} RCOI-2: cancel-deduct 2.50g from Spool #96 (confirmed)"), line


# --------------------------------------------------------------------------- #
# 43.6 — the cancel-review retry is idempotent                                #
# --------------------------------------------------------------------------- #
# update_spool's 15 s timeout is a READ timeout: a Spoolman that applies a PATCH
# but answers slowly reads as a rejection. The confirm then re-queued the spool,
# and the retry re-read the CURRENT used_weight (already including the write that
# landed) and added the grams again, charging one cancelled print twice.

def _pending_review(job="J-436X", sid=96, grams=2.5):
    cancel_review_store.add_pending({
        "printer_name": INDX, "job_id": job, "filename": "f.bgcode", "progress": 0.5,
        "total_grams": grams, "ambiguous": False, "created": "2026-10-13 00:00:00",
        "spools": [{"sid": sid, "toolhead": "RCOI-2", "position": 1, "grams": grams}]})


def _confirm(sm, job="J-436X", updates=None):
    ctx = _wire_ctx(sm, at={"RCOI-2": [96]}, toolheads=(("RCOI-2", 1),), printer=INDX)
    _start(ctx)
    try:
        return app_module.app.test_client().post("/api/cancel_deduct/confirm", json={
            "printer_name": INDX, "job_id": job, "updates": updates or {"96": 2.5}}).get_json()
    finally:
        _stop(ctx)


def _landed(sm, sid=96):
    return [b for s_, b in sm.patches if s_ == sid and s_ not in sm.patch_lost]


def test_a_write_that_landed_but_reported_a_timeout_is_charged_once(logs):
    """The task file's pin. Spoolman applies the PATCH but the answer times out.
    Whatever the first confirm reports, confirming again (as the card invites)
    must leave the spool charged exactly once."""
    sm = WeightWireSpoolman({96: _full_spool(used=43.4)}, patch_fails={96})
    _pending_review()
    first = _confirm(sm)
    sm.patch_fails.clear()   # Spoolman answers normally again
    if cancel_review_store.has_pending(INDX, "J-436X"):
        _confirm(sm)
    assert sm.used(96) == pytest.approx(45.9), (
        f"charged {sm.used(96) - 43.4:.2f} g, not 2.5 g; first confirm said {first}")
    assert len(sm.patches) == 1, "a second PATCH re-charged the spool"
    assert print_deduct_ledger.was_deducted(INDX, "J-436X")


def test_a_landed_write_is_recognised_on_the_spot(logs):
    """Re-reading the spool right after a reported failure shows the write landed:
    the first confirm already counts it, so nothing is left pending."""
    sm = WeightWireSpoolman({96: _full_spool(used=43.4)}, patch_fails={96})
    _pending_review()
    body = _confirm(sm)
    assert body["status"] == "confirmed" and body["applied"][0]["grams"] == 2.5, body
    assert not cancel_review_store.has_pending(INDX, "J-436X")
    assert any("landed" in m for m in _msgs(logs)), _msgs(logs)


def test_a_landed_write_found_only_on_the_retry(logs):
    """The re-read after the failure ALSO fails (Spoolman unreachable), so the
    retry record must carry the attempt's baseline: the retry sees the spool
    already at the attempted weight and doesn't write again."""
    sm = WeightWireSpoolman({96: _full_spool(used=43.4)}, patch_fails={96})
    sm.blind_after_patch.add(96)
    _pending_review()
    first = _confirm(sm)
    assert first["status"] == "error" and cancel_review_store.has_pending(INDX, "J-436X"), first
    retry_row = cancel_review_store.list_pending()[0]["spools"][0]
    assert retry_row.get("attempt_used_before") == 43.4, retry_row
    assert retry_row.get("attempt_used_after") == pytest.approx(45.9), retry_row
    sm.blind.clear()
    sm.blind_after_patch.clear()
    sm.patch_fails.clear()
    second = _confirm(sm)
    assert second["status"] == "confirmed", second
    assert sm.used(96) == pytest.approx(45.9) and len(sm.patches) == 1
    assert print_deduct_ledger.was_deducted(INDX, "J-436X")


def test_a_write_that_never_landed_is_charged_on_the_retry(logs):
    sm = WeightWireSpoolman({96: _full_spool(used=43.4)}, patch_lost={96})
    _pending_review()
    _confirm(sm)
    assert cancel_review_store.has_pending(INDX, "J-436X")
    sm.patch_lost.clear()
    second = _confirm(sm)
    assert second["status"] == "confirmed", second
    assert sm.used(96) == pytest.approx(45.9)


def test_a_spool_changed_since_the_attempt_needs_a_second_apply(logs):
    """The spool was weighed between the failed attempt and the retry, and came
    out HEAVIER than before the attempt: FCC can't tell whether this print's grams
    were already taken, so the retry charges nothing and says so. Applying again
    charges it deliberately."""
    sm = WeightWireSpoolman({96: _full_spool(used=43.4)}, patch_lost={96})
    _pending_review()
    _confirm(sm)
    sm.patch_lost.clear()
    sm.spools[96]["used_weight"] = 40.0          # a weigh-out in between
    second = _confirm(sm)
    assert second["status"] != "confirmed" and sm.used(96) == 40.0, second
    assert cancel_review_store.has_pending(INDX, "J-436X")
    assert "changed" in (second.get("errors") or [{}])[0].get("error", ""), second
    third = _confirm(sm)
    assert third["status"] == "confirmed" and sm.used(96) == pytest.approx(42.5), third


def test_a_spool_past_the_attempted_weight_is_asked_about_not_skipped(logs):
    """Review finding deduct-math-1: the attempt never landed, then the next
    print on the head charged 20 g. "At or past the attempted weight" read that
    as "the earlier write landed", so this print's 2.5 g went to nobody while the
    ledger said they were charged. Only an exact match counts as landed; past it,
    the retry charges nothing, says why, and a second Apply charges it."""
    sm = WeightWireSpoolman({96: _full_spool(used=43.4)}, patch_lost={96})
    _pending_review()
    _confirm(sm)
    sm.patch_lost.clear()
    sm.spools[96]["used_weight"] = 63.4           # the next print's 20 g deduct
    second = _confirm(sm)
    assert second["status"] != "confirmed" and sm.used(96) == 63.4, second
    assert "changed" in (second.get("errors") or [{}])[0].get("error", ""), second
    assert not print_deduct_ledger.was_deducted(INDX, "J-436X")
    third = _confirm(sm)
    assert third["status"] == "confirmed" and sm.used(96) == pytest.approx(65.9), third
