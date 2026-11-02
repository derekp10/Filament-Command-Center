"""
Tests for the confirmed-label ✅ indicator on spool cards.

Contract:
  - format_spool_display emits `needs_label_print` inside details through
    spoolman_api.label_flag: False when the label is confirmed, True when one
    needs printing, None when the record has no status at all (Group 58.5: a
    missing flag read as False, so a spool nobody had checked drew the tick).
  - SpoolCardBuilder.buildCard renders a ✅ indicator next to the
    🖨️ button when !isFil && details.needs_label_print === false.
  - Filaments never get the indicator.
  - Spools marked as needing reprint also never get the indicator, and nor
    does a spool with no status (no marker of its own: Claude's call, for veto).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routes_print_queue  # noqa: E402
import spoolman_api  # noqa: E402

MODULES = Path(__file__).resolve().parent.parent / "static" / "js" / "modules"


# ---------------------------------------------------------------------------
# format_spool_display: three states, never a guess.
# ---------------------------------------------------------------------------

# What Spoolman really sends for a spool with no status: the key isn't in `extra`
# at all (read on dev 0.27.0, 2026-11-01).
ABSENT = object()


def _make_spool(extra_label_flag=ABSENT):
    return {
        "id": 1,
        "remaining_weight": 500,
        "extra": {} if extra_label_flag is ABSENT else {"needs_label_print": extra_label_flag},
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
    # Still in its JSON quotes (a raw extra, as a record reads before
    # parse_inbound_data). A quoted "true" used to read as False.
    ('"true"', True),
    ('"false"', False),
    # No status on record reads as None, never as False. An intended change from
    # the pin this file carried until Group 58.5 ("" and None read as False, the
    # green tick on a spool nobody had checked).
    (ABSENT, None),
    (None, None),
    ("", None),
    ("  ", None),
    ('""', None),
    ("maybe", None),
])
def test_needs_label_print_normalization(flag, expected):
    info = spoolman_api.format_spool_display(_make_spool(flag))
    assert info["details"]["needs_label_print"] is expected


@pytest.mark.parametrize("extra", [None, "not a dict", 7, []])
def test_label_flag_reads_a_bad_extra_as_no_status(extra):
    """The reader answers for any record: its caller may hand it whatever a
    hand-edited or half-written record holds."""
    assert spoolman_api.label_flag(extra) is None


class _Filaments:
    """The tick's shared spoolman_api.FilamentListRead, already read."""
    error = None

    def __init__(self, records):
        self._records = records

    def get(self):
        return self._records


def test_a_record_with_no_flag_is_unknown_on_a_card_and_stays_out_of_the_backlog():
    """One record, the three readers (Group 58.5): the card's reader says "no
    status", the Backlog's test says no, and the 🏷️ count leaves it out. A flagged
    spool beside it is the control: the count still counts one."""
    none_on_record = _make_spool()
    flagged = dict(_make_spool("true"), id=2)
    confirmed = dict(_make_spool("false"), id=3)

    assert spoolman_api.format_spool_display(none_on_record)["details"]["needs_label_print"] is None
    assert routes_print_queue._needs_label(none_on_record) is False

    count = routes_print_queue.backlog_count([none_on_record, flagged, confirmed],
                                             filaments_read=_Filaments([{"id": 9, "extra": {}}]))
    assert count == {"read_ok": True, "count": 1, "spools": 1, "filaments": 0}


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


def test_card_omits_checkmark_when_the_spool_has_no_status(page: Page):
    """details.needs_label_print === null (no status on record) → no ✅ indicator."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof SpoolCardBuilder !== 'undefined'")

    html = page.evaluate(
        "(item) => SpoolCardBuilder.buildCard(item, 'search', {})",
        _fake_spool_item(None),
    )
    assert "fcc-card-label-ok" not in html


def _card_in_a_page(page, details):
    """The real ui_builder.js in a page with no network: what buildCard draws for
    a spool whose details are `details`."""
    page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>')
    page.add_script_tag(content="window.__pendingShortcuts = []; window.registerShortcut = function () {};")
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    item = dict(_fake_spool_item(None), details=details)
    return page.evaluate("(item) => SpoolCardBuilder.buildCard(item, 'search', {})", item)


def test_the_server_and_the_card_together_draw_no_tick_for_no_status(isolated_page):
    """Hermetic, and end to end: the REAL format_spool_display's answer for a spool
    with no flag, drawn by the REAL card. The false tick of dev's 189 spools
    (14 had earned it)."""
    details = spoolman_api.format_spool_display(_make_spool())["details"]
    assert "fcc-card-label-ok" not in _card_in_a_page(isolated_page, details)


def test_the_server_and_the_card_together_keep_a_confirmed_tick(isolated_page):
    """The control: a spool whose label IS confirmed keeps its tick."""
    details = spoolman_api.format_spool_display(_make_spool("false"))["details"]
    assert "fcc-card-label-ok" in _card_in_a_page(isolated_page, details)


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
