"""What test_spool_swap_22_3.py and test_spool_swap_22_3b.py share (Group 64.3 (9)):
their isolation fixture, the latch driver, the completion's mocks and the made-up
two-head XL. Each file used to carry its own copy.

Not a test module (no test_ prefix): the two files import from it, and the
fixture is picked up where it is imported (`from spool_swap_harness import reset`).
"""
from __future__ import annotations

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
import print_monitor  # noqa: E402
import print_tracker_store  # noqa: E402

PM = {"XL-1": {"printer_name": "XL", "position": 0},
      "XL-2": {"printer_name": "XL", "position": 1}}
ACTIVE = [("XL-1", {"position": 0}), ("XL-2", {"position": 1})]


@pytest.fixture(autouse=True)
def reset(tmp_path, monkeypatch):
    """Every store in the test's own folder, the edge actions synchronous, no heads
    read at a print's end (the hotfix of 2026-11-11 reads them on FINISHED and on a
    job change: these files keep them off locations.json and Spoolman), and the
    latch empty before and after. It deliberately does NOT stub
    _snapshot_active_spools: the files drive the snapshots themselves."""
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    monkeypatch.setattr(print_deduct, "_capture_print_heads", lambda *a, **k: None)
    monkeypatch.setattr(print_monitor, "_CANCEL_DEDUCT_RUN_ASYNC", False)
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()
    yield
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()


def creds(*a, **k):
    return {"ip_address": "1.2.3.4", "api_key": "k"}


def latch(state, job, fb="http://fb"):
    """One monitor tick of the made-up XL in `state`, with `job` as its job read."""
    with patch.object(app_module.prusalink_api, "get_printer_job", return_value=job):
        app_module._track_print_edge("XL", {"state": state}, fb)


def completion_ctx(usage_map, end_snap, rows=None, default_sid=999):
    """Mocks for deduct_completed_print's swap-detection path: creds, the footer
    compute, the printer-map resolve, the COMPLETION snapshot, and the preview-row
    builder (one row of 25 g on XL-1 for `default_sid` unless `rows` says).
    Returns (ctx managers to start / stop, the _apply_usage_to_printer mock)."""
    apply_mock = MagicMock(name="_apply_usage_to_printer")
    ctx = [
        patch.object(app_module.config_loader, "get_api_urls", return_value=("http://sm", "http://fb")),
        patch.object(app_module.prusalink_api, "fetch_printer_credentials", creds),
        patch.object(print_deduct, "_compute_cancel_usage", return_value=(dict(usage_map), None)),
        patch.object(app_module.locations_db, "get_active_printer_map", return_value=PM),
        patch.object(print_deduct, "_resolve_active_locs_for_printer", return_value=ACTIVE),
        patch.object(print_deduct, "_snapshot_active_spools", return_value=dict(end_snap)),
        patch.object(print_deduct, "_resolve_usage_to_spools",
                     return_value=(rows if rows is not None else
                                   [{"sid": default_sid, "grams": 25.0, "color": "ff0000",
                                     "toolhead": "XL-1", "position": 0}])),
        patch.object(print_deduct, "_apply_usage_to_printer", apply_mock),
        patch.object(app_module.state, "add_log_entry"),
    ]
    return ctx, apply_mock
