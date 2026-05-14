"""Group 10.8 — Wizard nested-Swal migration to mountOverlay.

Three Swal.fire sites were replaced with `window.mountOverlay()` overlays:
- Unsaved-changes confirm on hide.bs.modal (the known cmd-deck-shift offender).
- `wizardPromptFieldSync` — pick a filament field to bind to a spool field.
- `wizardPromptNewChoice` — add a new value to a choice field.

These tests exercise the new overlays' presence, button behavior, and the
Escape contract (Escape closes ONLY the overlay, not the wizard itself).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _open_wizard_fresh(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible()


def _force_close_wizard(page: Page) -> None:
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        if (m) {
            try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}
            m.hide();
        }
    """)
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5_000)


def test_unsaved_changes_overlay_is_mountoverlay_not_swal(page: Page):
    """When isDirty is true and the user tries to close, the unsaved-changes
    overlay should render through mountOverlay (data-overlay-mount attribute),
    NOT through SweetAlert2's `.swal2-popup`."""
    _open_wizard_fresh(page)
    page.evaluate("wizardState.isDirty = true")

    # Trigger hide.bs.modal — the listener fires preventDefault + overlay.
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        m.hide();
    """)

    overlay = page.locator("#fcc-wiz-unsaved-changes")
    expect(overlay).to_be_visible(timeout=2_000)
    expect(overlay).to_have_attribute("data-overlay-mount", "1")
    # SweetAlert2 should NOT have rendered the dialog.
    expect(page.locator(".swal2-popup")).not_to_be_attached()

    # The wizard modal stays open behind the overlay.
    expect(page.locator("#wizardModal")).to_be_visible()

    # Keep Editing → overlay closes, wizard stays open.
    overlay.locator("#fcc-wiz-dirty-cancel").click()
    expect(overlay).not_to_be_attached(timeout=2_000)
    expect(page.locator("#wizardModal")).to_be_visible()

    _force_close_wizard(page)


def test_unsaved_changes_overlay_escape_keeps_editing(page: Page):
    """Escape on the unsaved-changes overlay closes only the overlay, leaving
    the wizard modal open (mountOverlay's stopImmediatePropagation contract)."""
    _open_wizard_fresh(page)
    page.evaluate("wizardState.isDirty = true")
    page.evaluate("""
        bootstrap.Modal.getInstance(document.getElementById('wizardModal')).hide();
    """)
    overlay = page.locator("#fcc-wiz-unsaved-changes")
    expect(overlay).to_be_visible(timeout=2_000)

    page.keyboard.press("Escape")
    expect(overlay).not_to_be_attached(timeout=2_000)
    expect(page.locator("#wizardModal")).to_be_visible()

    _force_close_wizard(page)


def test_unsaved_changes_confirm_actually_closes_wizard(page: Page):
    """Discard & Close → overlay AND wizard both go away."""
    _open_wizard_fresh(page)
    page.evaluate("wizardState.isDirty = true")
    page.evaluate("""
        bootstrap.Modal.getInstance(document.getElementById('wizardModal')).hide();
    """)
    overlay = page.locator("#fcc-wiz-unsaved-changes")
    expect(overlay).to_be_visible(timeout=2_000)

    overlay.locator("#fcc-wiz-dirty-confirm").click()
    expect(overlay).not_to_be_attached(timeout=2_000)
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5_000)


def test_no_more_swal_fire_in_wizard_js(page: Page):
    """Guard: any future regression that reintroduces a nested Swal.fire
    inside inv_wizard.js should fail loudly here."""
    page.goto("http://localhost:8000")
    js_source = page.evaluate("""
        fetch('/static/js/modules/inv_wizard.js').then(r => r.text())
    """)
    # The migration left explanatory comments referencing the old pattern.
    # Strip comments before counting so the guard catches real calls only.
    lines = [
        ln for ln in js_source.split("\n")
        if "Swal.fire" in ln and not ln.lstrip().startswith("//")
    ]
    assert lines == [], (
        f"Found {len(lines)} non-comment Swal.fire reference(s) in inv_wizard.js — "
        f"every wizard prompt must route through window.mountOverlay() per Group 10.8.\n"
        f"Offenders:\n" + "\n".join(lines)
    )
