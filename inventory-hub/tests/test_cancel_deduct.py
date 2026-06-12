"""Simulation tests for the cancelled-print partial deduct (FilaBridge
absorption §9) — the whole backend path with a MOCKED PrusaLink + Spoolman, so
the deduct math, the per-tool untouched-head skip, and the exactly-once ledger
are validated WITHOUT a physical cancelled print (Derek's "active test pattern":
catch issues in CI, burn filament only for a final sign-off).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import print_deduct_ledger  # noqa: E402


_DEAD = "; " + ("pad " * 40) + "\n"   # ~165-byte no-extrusion dead zone


def _cancelled_gcode():
    """A 2-tool print where T0 extrudes 10mm before the cancel and another 10mm
    after (so the cancel catches HALF of T0), and T1 only ever runs after the
    cancel. footer: mm=[20,16] g=[40,32] -> g/mm = 2.0 both. Returns
    (gcode, reached_fraction-at-cancel)."""
    prefix = "M83\nT0\nG1 X10 E5\nG1 X20 E5\n"            # T0 reaches 10mm
    suffix = (
        "G1 X30 E5\nG1 X40 E5\n"                          # T0 +10mm (not reached)
        "T1\nG1 E16\n"                                    # T1 16mm (not reached)
        "; filament used [mm] = 20, 16\n"
        "; filament used [g] = 40, 32\n"
    )
    gcode = prefix + _DEAD + suffix
    cut = len(prefix.encode("utf-8")) + len(_DEAD.encode("utf-8")) // 2
    return gcode, cut / len(gcode.encode("utf-8"))


@pytest.fixture
def ledger_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH",
                        str(tmp_path / "ledger.json"))


@pytest.fixture
def deduct_mocks():
    """Mock the PrusaLink + Spoolman surface deduct_cancelled_print touches.
    Returns a dict carrying the captured update_spool calls."""
    captured = {"updates": []}

    gcode, _ = _cancelled_gcode()
    printer_map = {
        "XL-1": {"printer_name": "XL", "position": 0},
        "XL-2": {"printer_name": "XL", "position": 1},
    }
    spools = {
        100: {"id": 100, "used_weight": 100.0, "initial_weight": 1000.0},
        200: {"id": 200, "used_weight": 50.0, "initial_weight": 1000.0},
    }
    spools_at = {"XL-1": [100], "XL-2": [200]}

    def _update(sid, data):
        captured["updates"].append((sid, dict(data)))
        return {"id": sid, **data}

    ctx = [
        patch.object(app_module.prusalink_api, "fetch_cancel_gcode",
                     side_effect=lambda ip, key, fn, frac: {"gcode": gcode, "fraction": frac}),
        patch.object(app_module.locations_db, "get_active_printer_map",
                     return_value=printer_map),
        patch.object(app_module.spoolman_api, "get_spools_at_location",
                     side_effect=lambda loc: spools_at.get(str(loc).upper(), [])),
        patch.object(app_module.spoolman_api, "get_spool",
                     side_effect=lambda sid: spools.get(int(sid))),
        patch.object(app_module.spoolman_api, "update_spool", side_effect=_update),
        patch.object(app_module.spoolman_api, "format_spool_display",
                     return_value={"text": "#spool", "color": "ff0000"}),
    ]
    for m in ctx:
        m.start()
    try:
        yield captured
    finally:
        for m in reversed(ctx):
            m.stop()


def test_cancel_deducts_partial_per_tool_and_skips_untouched_head(ledger_tmp, deduct_mocks):
    _, frac = _cancelled_gcode()
    result = app_module.deduct_cancelled_print(
        "XL", "job.gcode", "job-1", frac,
        fb_url="http://fb", ip_address="1.2.3.4", api_key="k")

    assert result["status"] == "deducted", result
    assert result["spools_updated"] == 1, result
    # T0 reached 10mm * 2.0 g/mm = 20g -> spool 100 used 100 -> 120.
    updates = {sid: data for sid, data in deduct_mocks["updates"]}
    assert 100 in updates, deduct_mocks["updates"]
    assert abs(updates[100]["used_weight"] - 120.0) < 1e-6, updates[100]
    # T1 never ran before the cancel -> spool 200 (XL-2) must NOT be deducted.
    assert 200 not in updates, "untouched toolhead's spool must not be deducted"
    # The deduct PATCH carries ONLY used_weight (archive-on-empty discipline).
    assert set(updates[100].keys()) == {"used_weight"}, updates[100]


def test_cancel_is_exactly_once_via_ledger(ledger_tmp, deduct_mocks):
    _, frac = _cancelled_gcode()
    first = app_module.deduct_cancelled_print(
        "XL", "job.gcode", "job-7", frac,
        fb_url="http://fb", ip_address="1.2.3.4", api_key="k")
    assert first["status"] == "deducted"
    n_after_first = len(deduct_mocks["updates"])

    # Same (printer, job_id) again — must be a ledger no-op, no second deduct.
    second = app_module.deduct_cancelled_print(
        "XL", "job.gcode", "job-7", frac,
        fb_url="http://fb", ip_address="1.2.3.4", api_key="k")
    assert second["status"] == "skipped", second
    assert len(deduct_mocks["updates"]) == n_after_first, \
        "a re-fired cancel must not deduct twice (Spoolman /use is non-idempotent)"


def test_cancel_before_first_extrusion_records_zero(ledger_tmp, deduct_mocks):
    # reached_fraction ~0 -> no extrusion -> no_usage, but recorded so it
    # doesn't re-fire.
    result = app_module.deduct_cancelled_print(
        "XL", "job.gcode", "job-9", 0.0,
        fb_url="http://fb", ip_address="1.2.3.4", api_key="k")
    assert result["status"] == "no_usage", result
    assert deduct_mocks["updates"] == [], "nothing should be deducted"
    assert print_deduct_ledger.was_deducted("XL", "job-9") is True


def test_ledger_blank_job_id_not_recorded(ledger_tmp):
    # A blank/zero job_id can't be deduped restart-safely.
    assert print_deduct_ledger.was_deducted("XL", "") is False
    print_deduct_ledger.record_deduct("XL", "", filename="x")
    assert print_deduct_ledger.was_deducted("XL", "") is False  # still no-op
    # A real id round-trips.
    assert print_deduct_ledger.was_deducted("XL", "55") is False
    print_deduct_ledger.record_deduct("XL", "55", filename="x")
    assert print_deduct_ledger.was_deducted("XL", "55") is True
