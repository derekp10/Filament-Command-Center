"""Regression guard for buglist L36 — search FAB blocking the WEIGH QR.

The bug: `.fcc-fab-search` was anchored at `bottom: 30px; right: 30px`
(65×65px circle), which sat directly on top of the rightmost button in
the dashboard's bottom-pinned `.cmd-deck` (the WEIGH button containing
`#qr-weigh`) on shorter / Windows-scaled viewports.

Fix landed 2026-04-28: a `body:has(.cmd-deck) .fcc-fab-search` rule lifts
the FAB to `bottom: 180px` only on pages that include the cmd-deck, so
other pages keep the standard bottom-right anchor.

These tests assert the bounding boxes don't overlap at three viewport
heights spanning the failure mode (small phone-portrait, default 1600×1300
shop window, large desktop).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _rects_overlap(a: dict, b: dict) -> bool:
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


def _check_no_overlap(page: Page, viewport: dict):
    page.set_viewport_size(viewport)
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_selector("#qr-weigh", timeout=10000)

    qr = page.locator("#qr-weigh")
    fab = page.locator(".fcc-fab-search")
    expect(qr).to_be_visible()
    expect(fab).to_be_visible()

    qr_box = qr.bounding_box()
    fab_box = fab.bounding_box()
    assert qr_box, "qr-weigh has no bounding box"
    assert fab_box, "fcc-fab-search has no bounding box"

    assert not _rects_overlap(qr_box, fab_box), (
        f"FAB at {fab_box} overlaps WEIGH QR at {qr_box} on viewport {viewport}. "
        "Search badge must not block the weight QR — see buglist L36."
    )


def test_fab_does_not_overlap_weigh_qr_at_default_viewport(page: Page):
    """1600×1300 — the canonical dev viewport per CLAUDE.md."""
    _check_no_overlap(page, {"width": 1600, "height": 1300})


def test_fab_does_not_overlap_weigh_qr_at_short_viewport(page: Page):
    """Short viewport (700px tall) reproduces the original failure mode
    on Windows-scaled / laptop displays."""
    _check_no_overlap(page, {"width": 1280, "height": 700})


def test_fab_does_not_overlap_weigh_qr_at_tall_viewport(page: Page):
    """Tall viewport must still keep the FAB clear of the deck — proves
    the fix isn't viewport-height-dependent (the cmd-deck is always
    bottom-pinned regardless of screen size)."""
    _check_no_overlap(page, {"width": 1920, "height": 1600})
