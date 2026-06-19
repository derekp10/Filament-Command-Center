"""Detail-modal footer button standardization (Option-B sweep, 2026-06-16).

The spool-details and filament-details modal footers must place their shared
actions in the SAME order so the user navigates consistently between the two:

    [Spoolman ↗️]  …  [type-specific create/nav]  ✏️ Edit  ➕ Queue Label  ⚙️ more  Close

These tests pin the relative DOM order by the byte offset of each button id in
the template (ids are unique across the file, and the spool footer precedes the
filament footer), so a future re-order that breaks the standardization fails
here instead of silently regressing the UX.
"""
from __future__ import annotations

import os

TEMPLATE = os.path.join(
    os.path.dirname(__file__), "..", "templates", "components", "modals_details.html"
)


def _html():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def _offsets(html, ids):
    """Byte offset of each id, asserting each appears exactly once."""
    out = []
    for i in ids:
        needle = f'id="{i}"'
        assert html.count(needle) == 1, f"{needle} should appear exactly once in the template"
        out.append(html.index(needle))
    return out


def test_spool_footer_canonical_order():
    order = _offsets(_html(), [
        "btn-open-spoolman",       # Spoolman link — far left
        "btn-spool-to-filament",   # 🧬 Swatch (type-specific)
        "btn-clone-spool",         # 🐑 Clone   (type-specific)
        "btn-edit-spool",          # ✏️ Edit
        "btn-print-action",        # ➕ Queue Label
        "btn-spool-gear",          # ⚙️ more-actions (destructive) menu
        "btn-spool-close",         # Close — right-anchored last
    ])
    assert order == sorted(order), "spool-details footer buttons are out of canonical order"


def test_filament_footer_canonical_order():
    order = _offsets(_html(), [
        "btn-fil-open-spoolman",   # Spoolman link — far left
        "btn-fil-new-spool",       # ➕ New Spool (type-specific)
        "btn-fil-edit",            # ✏️ Edit Filament
        "btn-fil-print-action",    # ➕ Queue Label
        "btn-fil-gear",            # ⚙️ more-actions (merge + destructive) menu
        "btn-fil-close",           # Close — right-anchored last
    ])
    assert order == sorted(order), "filament-details footer buttons are out of canonical order"


def test_shared_cluster_consistent_across_modals():
    """The cross-modal invariant the standardization exists to guarantee: in
    BOTH footers the Spoolman link leads and Edit → Queue Label → ⚙️ menu run
    in that order, so muscle memory transfers between the two detail modals."""
    html = _html()
    spool = _offsets(html, [
        "btn-open-spoolman", "btn-edit-spool", "btn-print-action", "btn-spool-gear", "btn-spool-close",
    ])
    assert spool == sorted(spool)
    fil = _offsets(html, [
        "btn-fil-open-spoolman", "btn-fil-edit", "btn-fil-print-action", "btn-fil-gear", "btn-fil-close",
    ])
    assert fil == sorted(fil)
