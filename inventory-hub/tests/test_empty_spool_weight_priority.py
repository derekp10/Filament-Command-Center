"""
Tests for the empty-spool-weight inheritance helper (wizard.js).

The inheritance chain is:  Spool > Filament > Vendor (manufacturer).
A blank / null / 0 value at any level falls through to the next level.
This matches Spoolman's native "pull-down" pattern and is the fix for
the "Empty Spool Weight on manufacturer doesn't pull down" backlog item.

The helper is exposed as `window.resolveEmptySpoolWeight` so these tests
exercise the real JS function inside Chromium — no shimming.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


def _open_and_load_helper(page: Page):
    """Navigate to dashboard so inv_wizard.js is loaded and the helper is on window."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    # Wait until the helper is defined (module loads async on some builds).
    page.wait_for_function("typeof window.resolveEmptySpoolWeight === 'function'", timeout=5_000)


@pytest.mark.parametrize(
    "args,expected",
    [
        # Spool wins when present
        ({"spoolWt": 220, "filamentWt": 180, "vendor": {"empty_spool_weight": 167}}, 220),
        # Falls through to filament when spool is null
        ({"spoolWt": None, "filamentWt": 180, "vendor": {"empty_spool_weight": 167}}, 180),
        # Falls through to vendor when spool AND filament are null
        ({"spoolWt": None, "filamentWt": None, "vendor": {"empty_spool_weight": 167}}, 167),
        # 0 counts as unset at every level
        ({"spoolWt": 0, "filamentWt": 0, "vendor": {"empty_spool_weight": 167}}, 167),
        # Empty string counts as unset
        ({"spoolWt": "", "filamentWt": "", "vendor": {"empty_spool_weight": 167}}, 167),
        # All unset returns null
        ({"spoolWt": None, "filamentWt": None, "vendor": {"empty_spool_weight": 0}}, None),
        ({"spoolWt": None, "filamentWt": None, "vendor": None}, None),
        # Vendor without empty_spool_weight key is treated as unset
        ({"spoolWt": None, "filamentWt": None, "vendor": {"name": "Overture"}}, None),
        # Numeric strings are coerced
        ({"spoolWt": None, "filamentWt": "250", "vendor": None}, 250),
    ],
    ids=[
        "spool-wins",
        "filament-fallback",
        "vendor-fallback",
        "zero-is-unset",
        "empty-string-is-unset",
        "all-unset-returns-null",
        "missing-vendor-returns-null",
        "vendor-without-key-returns-null",
        "numeric-strings-coerced",
    ],
)
def test_resolve_empty_spool_weight_priority(page: Page, args, expected):
    _open_and_load_helper(page)
    result = page.evaluate("(a) => window.resolveEmptySpoolWeight(a)", args)
    assert result == expected, (
        f"resolveEmptySpoolWeight({args}) returned {result!r}, expected {expected!r}"
    )


def test_resolver_handles_undefined_keys(page: Page):
    """Omitting keys entirely should work the same as null."""
    _open_and_load_helper(page)
    # Only vendor provided -> should still fall through to it.
    result = page.evaluate(
        "() => window.resolveEmptySpoolWeight({ vendor: { empty_spool_weight: 167 } })"
    )
    assert result == 167

    # Nothing provided at all.
    result = page.evaluate("() => window.resolveEmptySpoolWeight()")
    assert result is None
