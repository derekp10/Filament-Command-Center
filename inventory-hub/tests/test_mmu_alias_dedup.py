"""
MMU M0/M1 alias dedup — tests for `_resolve_active_locs_for_printer` in app.py.

Background: printer_map can have two LocationIDs at the same position (e.g.
CORE1-M0 direct-feed and CORE1-M1 MMU-routed). Only one is physically active
per print. The resolver consults PrusaLink `/api/v1/info.mmu` (via
prusalink_api.get_printer_mmu_flag) to re-order candidates so the preferred
alias is iterated first — then the usage-deduction loop processes each
position exactly once and no spool gets double-deducted.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402


@pytest.fixture
def aliased_printer_map():
    return {
        "CORE1-M0": {"printer_name": "🦝 Core One", "position": 0},
        "CORE1-M1": {"printer_name": "🦝 Core One", "position": 0},
        "CORE1-M2": {"printer_name": "🦝 Core One", "position": 1},
        "XL-1":     {"printer_name": "🦝 XL", "position": 0},
        "XL-2":     {"printer_name": "🦝 XL", "position": 1},
    }


def test_resolver_filters_by_printer_name(aliased_printer_map):
    with patch("prusalink_api.get_printer_mmu_flag", return_value=None):
        result = app_module._resolve_active_locs_for_printer(
            aliased_printer_map, "🦝 XL", "http://fb.invalid"
        )
    loc_ids = [loc for loc, _ in result]
    assert set(loc_ids) == {"XL-1", "XL-2"}


def test_resolver_preserves_order_when_no_aliases(aliased_printer_map):
    # XL has no aliased positions; the helper should short-circuit and
    # return candidates in insertion order without probing PrusaLink.
    with patch("prusalink_api.get_printer_mmu_flag") as mmu_probe:
        result = app_module._resolve_active_locs_for_printer(
            aliased_printer_map, "🦝 XL", "http://fb.invalid"
        )
        assert mmu_probe.call_count == 0, "MMU probe should not fire without aliases"
    loc_ids = [loc for loc, _ in result]
    assert loc_ids == ["XL-1", "XL-2"]


def test_resolver_prefers_m1_when_mmu_true(aliased_printer_map):
    with patch("prusalink_api.get_printer_mmu_flag", return_value=True):
        result = app_module._resolve_active_locs_for_printer(
            aliased_printer_map, "🦝 Core One", "http://fb.invalid"
        )
    loc_ids = [loc for loc, _ in result]
    # The MMU-routed alias (-M1) must come before the direct-feed one (-M0)
    # for position 0; M2 ordering is irrelevant — it has no aliases.
    assert loc_ids.index("CORE1-M1") < loc_ids.index("CORE1-M0")


def test_resolver_prefers_m0_when_mmu_false(aliased_printer_map):
    with patch("prusalink_api.get_printer_mmu_flag", return_value=False):
        result = app_module._resolve_active_locs_for_printer(
            aliased_printer_map, "🦝 Core One", "http://fb.invalid"
        )
    loc_ids = [loc for loc, _ in result]
    assert loc_ids.index("CORE1-M0") < loc_ids.index("CORE1-M1")


def test_resolver_falls_back_to_insertion_order_when_probe_unknown(aliased_printer_map):
    with patch("prusalink_api.get_printer_mmu_flag", return_value=None):
        result = app_module._resolve_active_locs_for_printer(
            aliased_printer_map, "🦝 Core One", "http://fb.invalid"
        )
    loc_ids = [loc for loc, _ in result]
    # With an unknown probe, the dict's insertion order (M0 first) is kept.
    assert loc_ids[0] == "CORE1-M0"


def test_resolver_swallows_probe_exceptions(aliased_printer_map):
    with patch("prusalink_api.get_printer_mmu_flag", side_effect=RuntimeError("boom")):
        result = app_module._resolve_active_locs_for_printer(
            aliased_printer_map, "🦝 Core One", "http://fb.invalid"
        )
    loc_ids = [loc for loc, _ in result]
    assert loc_ids[0] == "CORE1-M0"  # fallback to insertion order


def test_resolver_empty_for_unknown_printer(aliased_printer_map):
    with patch("prusalink_api.get_printer_mmu_flag", return_value=None):
        result = app_module._resolve_active_locs_for_printer(
            aliased_printer_map, "nonexistent", "http://fb.invalid"
        )
    assert result == []
