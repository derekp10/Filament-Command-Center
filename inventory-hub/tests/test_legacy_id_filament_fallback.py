"""Legacy-id scan should fall back to surfacing the FILAMENT when the legacy
id resolves to a filament that currently has no spools.

Derek 2026-06-02: a Google-Sheets `range=98:98` link dead-ended with "unknown
error" because the filament had zero active spools. `find_spools_by_legacy_id`
returns [] when the matched filament has no spools, so `_resolve_legacy_spool_lookup`
returned None and the URL / explicit-LEGACY branches errored out. The pure-number
branch already had a filament fallback (Priority 4); this adds the same fallback
to the URL/range and explicit-LEGACY branches.

Host-runnable unit tests (no live container) — `spoolman_api` legacy lookups are
mocked so the resolution logic is exercised in isolation.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logic import resolve_scan  # noqa: E402

GSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1Vb_9nodO1cr2-1qbtvkgYRNuNU_F3O62yayd7_uOIAg/"
    "edit?gid=304905527#gid=304905527&range=98:98"
)


@pytest.fixture
def no_spools_one_filament():
    """No spool matches any legacy id, but the legacy id maps to filament 42."""
    with patch("spoolman_api.find_spools_by_legacy_id", return_value=[]), \
         patch("spoolman_api.find_filament_by_legacy_id",
               side_effect=lambda lid: 42 if str(lid).strip() == "98" else None):
        yield


@pytest.fixture
def nothing_matches():
    with patch("spoolman_api.find_spools_by_legacy_id", return_value=[]), \
         patch("spoolman_api.find_filament_by_legacy_id", return_value=None):
        yield


def test_gsheet_range_url_falls_back_to_filament(no_spools_one_filament):
    assert resolve_scan(GSHEET_URL) == {"type": "filament", "id": 42}


def test_explicit_legacy_prefix_falls_back_to_filament(no_spools_one_filament):
    assert resolve_scan("LEGACY:98") == {"type": "filament", "id": 42}
    assert resolve_scan("LEG:98") == {"type": "filament", "id": 42}
    assert resolve_scan("OLD:98") == {"type": "filament", "id": 42}


def test_url_with_no_spool_and_no_filament_still_errors(nothing_matches):
    res = resolve_scan(GSHEET_URL)
    assert res["type"] == "error"
    assert res["msg"] == "Unknown/Invalid Link"


def test_explicit_legacy_with_no_match_still_errors(nothing_matches):
    res = resolve_scan("LEGACY:98")
    assert res["type"] == "error"
    assert "not found" in res["msg"]


def test_url_prefers_spool_when_one_exists():
    """Regression guard: when the legacy id DOES resolve to a spool, the spool
    wins — the filament fallback must not shadow it."""
    with patch("spoolman_api.find_spools_by_legacy_id", return_value=[{"id": 7}]), \
         patch("spoolman_api.find_filament_by_legacy_id", return_value=42) as fil_lookup:
        assert resolve_scan(GSHEET_URL) == {"type": "spool", "id": 7}
        fil_lookup.assert_not_called()
