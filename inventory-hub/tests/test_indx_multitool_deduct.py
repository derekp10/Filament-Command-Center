"""Multi-toolhead (Core One INDX, 8 slots) print-deduct correctness.

Derek's Core One became a Core One Plus Gen2 INDX on 2026-09-29: one toolhead
became eight. Two deduct defects are structurally UNREACHABLE on a one-head
printer and become live the moment a printer has several positions. Both write
wrong weights silently, which is the failure mode that corrupts inventory
without telling anyone.

  1. A mid-print spool swap on ONE head dropped every other head from the
     deduct. `_compute_swap_split` only builds rows for positions present in
     `swap_log`, and a truthy result short-circuited the full-footer resolve —
     so an 8-colour print with one runout billed one head and silently lost the
     other seven.
  2. `_tool_grams`' sole-entry fold ("a sole entry IS this position") was only
     true for a one-position printer. With several positions it hands EVERY
     position the one used tool's full grams, so a swap on a head that printed
     nothing invents a charge against an uninvolved spool.

The footer shapes below are the real numbers from Derek's INDX raccoon print
(`racoon_v4-INDX_..._PLA,PLA,PLA_COREONEINDX_5h14m.bgcode`, read off the printer
2026-10-08): `filament used [g]=18.83, 24.44, 9.00, 0.00, 0.00, 0.00, 0.00, 0.00`
— eight slots, zero-padded, three used.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import print_deduct  # noqa: E402
import print_monitor  # noqa: E402
import prusalink_api  # noqa: E402
import config_loader  # noqa: E402
import locations_db  # noqa: E402
import spoolman_api  # noqa: E402
import print_deduct_ledger  # noqa: E402
import cancel_review_store  # noqa: E402
import cancel_fetch_store  # noqa: E402
import print_tracker_store  # noqa: E402

INDX = "INDX"
# The raccoon print: three slots used of eight.
RACOON_FOOTER = {0: 18.83, 1: 24.44, 2: 9.00}


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    monkeypatch.setattr(print_deduct_ledger, "_LEDGER_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(cancel_review_store, "_STORE_PATH", str(tmp_path / "review.json"))
    monkeypatch.setattr(cancel_fetch_store, "_STORE_PATH", str(tmp_path / "fetch.json"))
    monkeypatch.setattr(print_tracker_store, "_STORE_PATH", str(tmp_path / "latch.json"))
    prev = print_monitor._CANCEL_DEDUCT_RUN_ASYNC
    print_monitor._CANCEL_DEDUCT_RUN_ASYNC = False
    with app_module._PRINT_TRACKER_LOCK:
        app_module._PRINT_TRACKER.clear()
    try:
        yield
    finally:
        print_monitor._CANCEL_DEDUCT_RUN_ASYNC = prev
        with app_module._PRINT_TRACKER_LOCK:
            app_module._PRINT_TRACKER.clear()


def _map(n_heads, printer=INDX):
    """A printer_map with `n_heads` positions, the way the INDX's RCOI-1..8 rows
    produce it (1-based names, 0-based positions)."""
    return {f"{printer}-{i + 1}": {"printer_name": printer, "position": i}
            for i in range(n_heads)}


def _spool(sid):
    return {"id": sid, "initial_weight": 1000, "used_weight": 100,
            "filament": {"name": f"F{sid}", "color_hex": "ABCDEF"}}


# --------------------------------------------------------------------------- #
# _tool_grams — the fold is only legitimate on a one-position printer          #
# --------------------------------------------------------------------------- #
def test_tool_grams_folds_a_sole_entry_only_when_allowed():
    sole = {3: 42.0}
    # One-position printer (an MMU-profile file marking slot 3): fold is right.
    assert print_deduct._tool_grams(sole, 0, allow_fold=True) == 42.0
    # Multi-head printer: position 0 printed nothing and must be charged nothing.
    assert print_deduct._tool_grams(sole, 0, allow_fold=False) == 0.0
    # An exact hit is unaffected either way.
    assert print_deduct._tool_grams(sole, 3, allow_fold=False) == 42.0


def test_tool_grams_never_folds_a_multi_entry_map():
    assert print_deduct._tool_grams(RACOON_FOOTER, 5, allow_fold=True) == 0.0


# --------------------------------------------------------------------------- #
# _printer_is_single_position                                                  #
# --------------------------------------------------------------------------- #
def test_printer_is_single_position_true_for_one_head():
    with patch.object(locations_db, "get_active_printer_map", return_value=_map(1)):
        assert print_deduct._printer_is_single_position(INDX) is True


def test_printer_is_single_position_false_for_eight_heads():
    with patch.object(locations_db, "get_active_printer_map", return_value=_map(8)):
        assert print_deduct._printer_is_single_position(INDX) is False


def test_printer_is_single_position_fails_closed():
    """Unreadable map must NOT enable the fold: not folding costs a degrade to the
    manual review, folding wrongly writes a wrong weight."""
    with patch.object(locations_db, "get_active_printer_map", side_effect=RuntimeError):
        assert print_deduct._printer_is_single_position(INDX) is False


# --------------------------------------------------------------------------- #
# Bug 1 — a swap on one head must not drop the other heads                     #
# --------------------------------------------------------------------------- #
def test_swap_on_one_head_still_charges_the_other_heads():
    """The raccoon print: heads 0, 1 and 2 all printed; head 1 ran out and was
    swapped. Head 1 splits across two spools; heads 0 and 2 must STILL be billed."""
    swap_log = [{"position": 1, "progress": 0.5, "from_sid": 201, "to_sid": 202, "runout": True}]
    seg = {"footer": dict(RACOON_FOOTER), "cums": [{1: 10.0}]}
    seen = {}

    def fake_resolve(printer_name, usage_map, fb_url, active_locs=None):
        seen["usage"] = dict(usage_map)
        return [{"sid": 300 + p, "grams": g, "position": p} for p, g in sorted(usage_map.items())]

    with patch.object(prusalink_api, "compute_segment_usage", return_value=seg), \
         patch.object(locations_db, "get_active_printer_map", return_value=_map(8)), \
         patch.object(spoolman_api, "get_spool", side_effect=lambda sid: _spool(sid)), \
         patch.object(spoolman_api, "format_spool_display",
                      return_value={"text": "x", "color": "AAA"}), \
         patch.object(config_loader, "load_config", return_value={}), \
         patch.object(print_deduct, "_resolve_usage_to_spools", side_effect=fake_resolve):
        res = print_deduct._route_completion_to_review(
            INDX, "racoon.bgcode", 9001, dict(RACOON_FOOTER), "http://fb", [1],
            swap_log=swap_log, ip_address="ip", api_key="k", start_spools={"1": 201})

    assert res["auto_split"] is True
    rec = cancel_review_store.get_pending(INDX, 9001)
    charged = {r["sid"] for r in rec["spools"]}
    # Head 1's two segments...
    assert {201, 202} <= charged
    # ...AND the un-swapped heads 0 and 2. Pre-fix this set was exactly {201, 202}.
    assert {300, 302} <= charged, (
        f"heads 0 and 2 printed but were dropped from the deduct: {sorted(charged)}")
    # The full-footer resolve must be asked for exactly the UN-swapped positions.
    assert seen["usage"] == {0: 18.83, 2: 9.00}


def test_swap_split_total_covers_every_printing_head():
    """The review's total must account for all three heads (52.27 g), not just the
    swapped one (24.44 g)."""
    swap_log = [{"position": 1, "progress": 0.5, "from_sid": 201, "to_sid": 202}]
    seg = {"footer": dict(RACOON_FOOTER), "cums": [{1: 10.0}]}

    def fake_resolve(printer_name, usage_map, fb_url, active_locs=None):
        return [{"sid": 300 + p, "grams": g, "position": p} for p, g in sorted(usage_map.items())]

    with patch.object(prusalink_api, "compute_segment_usage", return_value=seg), \
         patch.object(locations_db, "get_active_printer_map", return_value=_map(8)), \
         patch.object(spoolman_api, "get_spool", side_effect=lambda sid: _spool(sid)), \
         patch.object(spoolman_api, "format_spool_display",
                      return_value={"text": "x", "color": "AAA"}), \
         patch.object(config_loader, "load_config", return_value={}), \
         patch.object(print_deduct, "_resolve_usage_to_spools", side_effect=fake_resolve):
        print_deduct._route_completion_to_review(
            INDX, "racoon.bgcode", 9002, dict(RACOON_FOOTER), "http://fb", [1],
            swap_log=swap_log, ip_address="ip", api_key="k", start_spools={"1": 201})

    rec = cancel_review_store.get_pending(INDX, 9002)
    assert rec["total_grams"] == pytest.approx(sum(RACOON_FOOTER.values()), abs=0.01)


# --------------------------------------------------------------------------- #
# Bug 2 — a swap on a head that printed nothing must not invent a charge       #
# --------------------------------------------------------------------------- #
def test_swap_on_a_head_that_printed_nothing_is_ignored():
    """Single-material print on head 3. You pause, replace head 3's spool AND
    re-scan one onto head 0. `_record_swap_events` logs BOTH, but head 0 extruded
    nothing — pre-fix the sole-entry fold handed it head 3's full 42 g."""
    usage = {3: 42.0}
    swap_log = [
        {"position": 3, "progress": 0.5, "from_sid": 401, "to_sid": 402},
        {"position": 0, "progress": 0.5, "from_sid": 500, "to_sid": 501},
    ]
    seg = {"footer": dict(usage), "cums": [{3: 20.0}]}

    def fake_resolve(printer_name, usage_map, fb_url, active_locs=None):
        return []

    with patch.object(prusalink_api, "compute_segment_usage", return_value=seg), \
         patch.object(locations_db, "get_active_printer_map", return_value=_map(8)), \
         patch.object(spoolman_api, "get_spool", side_effect=lambda sid: _spool(sid)), \
         patch.object(spoolman_api, "format_spool_display",
                      return_value={"text": "x", "color": "AAA"}), \
         patch.object(config_loader, "load_config", return_value={}), \
         patch.object(print_deduct, "_resolve_usage_to_spools", side_effect=fake_resolve):
        print_deduct._route_completion_to_review(
            INDX, "single.bgcode", 9003, dict(usage), "http://fb", [3],
            swap_log=swap_log, ip_address="ip", api_key="k",
            start_spools={"3": 401, "0": 500})

    rec = cancel_review_store.get_pending(INDX, 9003)
    charged = {r["sid"]: r["grams"] for r in rec["spools"]}
    assert 500 not in charged and 501 not in charged, (
        f"head 0 printed nothing but was charged: {charged}")
    # The whole 42 g stays on head 3's two spools and nowhere else.
    assert sum(charged.values()) == pytest.approx(42.0, abs=0.01)


def test_single_head_printer_keeps_the_fold():
    """Regression guard: the fold is load-bearing for Derek's old one-head Core One
    sliced with an MMU profile (tool index 1, position 0). Removing it entirely
    would silently stop deducting those prints."""
    swap_log = [{"position": 0, "progress": 0.5, "from_sid": 601, "to_sid": 602}]
    seg = {"footer": {1: 50.0}, "cums": [{1: 20.0}]}   # slicer says tool 1, printer has position 0

    with patch.object(prusalink_api, "compute_segment_usage", return_value=seg), \
         patch.object(locations_db, "get_active_printer_map", return_value=_map(1, "CoreOne")), \
         patch.object(spoolman_api, "get_spool", side_effect=lambda sid: _spool(sid)), \
         patch.object(spoolman_api, "format_spool_display",
                      return_value={"text": "x", "color": "AAA"}), \
         patch.object(config_loader, "load_config", return_value={}), \
         patch.object(print_deduct, "_resolve_usage_to_spools", return_value=[]):
        res = print_deduct._route_completion_to_review(
            "CoreOne", "mmu.bgcode", 9004, {1: 50.0}, "http://fb", [0],
            swap_log=swap_log, ip_address="ip", api_key="k", start_spools={"0": 601})

    assert res["auto_split"] is True
    rec = cancel_review_store.get_pending("CoreOne", 9004)
    charged = {r["sid"]: r["grams"] for r in rec["spools"]}
    assert charged == {601: pytest.approx(20.0, abs=0.01), 602: pytest.approx(30.0, abs=0.01)}
