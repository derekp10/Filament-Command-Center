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

import copy
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import cancel_fetch_store  # noqa: E402
import cancel_review_store  # noqa: E402
import print_deduct  # noqa: E402
import print_deduct_ledger  # noqa: E402
import spoolman_api  # noqa: E402
import state  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_stores(tmp_path, monkeypatch):
    """The pending-review, deferred-fetch and ledger stores are JSON files under
    data/; never let a test touch the real ones."""
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "pending.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetches.json"))
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))


def _unwire(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


class WeightWireSpoolman:
    """Spoolman over the wire, weights included. get_spool / update_spool run for
    real; only `requests.get` / `requests.patch` are answered here, from records
    shaped like Spoolman's (own initial_weight may be null; filament.weight is the
    inherited net weight). A PATCH applies what Spoolman would store."""

    def __init__(self, spools, patch_fails=()):
        self.spools = {int(k): copy.deepcopy(v) for k, v in spools.items()}
        self.patches = []
        self.patch_fails = set(patch_fails)   # sids whose PATCH lands but answers as a failure

    def _get(self, url, *a, **k):
        tail = str(url).split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        rec = self.spools.get(int(tail)) if tail.isdigit() else None
        if rec is None:
            return MagicMock(ok=False, status_code=404, text="not found", json=MagicMock(return_value={}))
        body = copy.deepcopy(rec)
        body["id"] = int(tail)
        body["extra"] = {key: json.dumps(val) for key, val in (rec.get("extra") or {}).items()}
        return MagicMock(ok=True, status_code=200, json=MagicMock(return_value=body))

    def _patch(self, url, json=None, **k):  # noqa: A002 — mirrors requests' kwarg
        sid = int(str(url).rstrip("/").rsplit("/", 1)[-1])
        body = copy.deepcopy(json)
        self.patches.append((sid, body))
        rec = self.spools[sid]
        for key in ("used_weight", "initial_weight", "archived", "location"):
            if key in body:
                rec[key] = body[key]
        if "extra" in body:
            rec["extra"] = {key: _unwire(val) for key, val in body["extra"].items()}
        if sid in self.patch_fails:
            # The write LANDED, but the answer reads as a failure (a timeout after
            # commit) — the 43.6 hazard.
            raise spoolman_api.requests.exceptions.ReadTimeout("read timed out (test)")
        return MagicMock(ok=True, status_code=200, json=MagicMock(return_value={"id": sid, **copy.deepcopy(rec)}))

    def used(self, sid):
        return self.spools[int(sid)]["used_weight"]


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


def _wire_ctx(sm, at=None, toolheads=(("XL-1", 0),), printer="XL"):
    at = at or {"XL-1": [100]}
    active = [(loc, {"position": pos, "printer_name": printer}) for loc, pos in toolheads]
    return [
        patch.object(print_deduct.locations_db, "get_active_printer_map", return_value={}),
        patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=active),
        patch.object(spoolman_api, "get_spools_at_location", side_effect=lambda loc: list(at.get(str(loc).upper(), []))),
        patch.object(spoolman_api.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(spoolman_api, "format_spool_display", return_value={"text": "#s", "color": "ff0000"}),
        patch.object(spoolman_api.requests, "get", side_effect=sm._get),
        patch.object(spoolman_api.requests, "patch", side_effect=sm._patch),
    ]


def _start(ctx):
    for m in ctx:
        m.start()


def _stop(ctx):
    for m in reversed(ctx):
        m.stop()


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
