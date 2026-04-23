"""
Tests for the confirmed-label ✅ indicator on spool cards.

Contract:
  - format_spool_display now emits a `needs_label_print` bool inside
    details (false when the label is already verified, true when a
    reprint is pending).
  - SpoolCardBuilder.buildCard renders a ✅ indicator next to the
    🖨️ button when !isFil && details.needs_label_print === false.
  - Filaments never get the indicator.
  - Spools marked as needing reprint also never get the indicator.
"""
from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import Page, expect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import spoolman_api  # noqa: E402


# ---------------------------------------------------------------------------
# format_spool_display: normalize loose values into a strict bool.
# ---------------------------------------------------------------------------

def _make_spool(extra_label_flag):
    return {
        "id": 1,
        "remaining_weight": 500,
        "extra": {"needs_label_print": extra_label_flag} if extra_label_flag is not None else {},
        "filament": {
            "id": 10,
            "material": "PLA",
            "name": "Red",
            "vendor": {"name": "TestVendor"},
            "settings_extruder_temp": 210,
            "extra": {},
        },
    }


@pytest.mark.parametrize("flag,expected", [
    (True, True),
    ("true", True),
    ("True", True),
    (1, True),
    (False, False),
    ("false", False),
    (0, False),
    ("", False),
    (None, False),
])
def test_needs_label_print_normalization(flag, expected):
    info = spoolman_api.format_spool_display(_make_spool(flag))
    assert info["details"]["needs_label_print"] is expected


# ---------------------------------------------------------------------------
# Frontend rendering: ✅ appears only for spool + !needs_label_print.
# ---------------------------------------------------------------------------

def _fake_spool_item(needs_label_print):
    return {
        "id": 42,
        "type": "spool",
        "display": "#42 Red PLA",
        "color": "ff0000",
        "color_direction": "longitudinal",
        "remaining_weight": 500,
        "archived": False,
        "details": {
            "id": 42,
            "brand": "TestVendor",
            "material": "PLA",
            "color_name": "Red",
            "weight": 500,
            "temp": "210°C",
            "needs_label_print": needs_label_print,
        },
    }


def test_card_shows_checkmark_when_label_confirmed(page: Page):
    """details.needs_label_print === false → ✅ indicator rendered in the nav row."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof SpoolCardBuilder !== 'undefined'")

    html = page.evaluate(
        "(item) => SpoolCardBuilder.buildCard(item, 'search', {})",
        _fake_spool_item(False),
    )
    assert "fcc-card-label-ok" in html
    assert "Label confirmed printed" in html


def test_card_omits_checkmark_when_label_needs_reprint(page: Page):
    """details.needs_label_print === true → no ✅ indicator."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof SpoolCardBuilder !== 'undefined'")

    html = page.evaluate(
        "(item) => SpoolCardBuilder.buildCard(item, 'search', {})",
        _fake_spool_item(True),
    )
    assert "fcc-card-label-ok" not in html


def test_card_omits_checkmark_for_filaments(page: Page):
    """Filaments never get the label indicator regardless of the flag."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof SpoolCardBuilder !== 'undefined'")

    fil_item = _fake_spool_item(False)
    fil_item["type"] = "filament"
    html = page.evaluate(
        "(item) => SpoolCardBuilder.buildCard(item, 'search', {})",
        fil_item,
    )
    assert "fcc-card-label-ok" not in html


def test_card_omits_checkmark_when_details_missing(page: Page):
    """Legacy callers that don't pass a `details` dict shouldn't 💥."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof SpoolCardBuilder !== 'undefined'")

    bare_item = {"id": 99, "type": "spool", "display": "#99", "color": "000000"}
    html = page.evaluate(
        "(item) => SpoolCardBuilder.buildCard(item, 'search', {})",
        bare_item,
    )
    # No crash, no indicator.
    assert "fcc-card-label-ok" not in html
