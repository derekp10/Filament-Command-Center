"""Escape closes an open combobox dropdown, not the whole modal.

Option-B standalone sweep (2026-06-16). A custom combobox (input + a div
dropdown list) keeps focus on its <input>, so an Escape used to bubble up to
the enclosing Bootstrap modal and dismiss the ENTIRE modal instead of just the
dropdown (both manageModal and wizardModal default to data-bs-keyboard="true").
The fix adds preventDefault + stopPropagation to each custom combobox's Escape
branch so the dropdown closes and the modal stays open.

Surfaces covered here: the wizard location combobox (wizardBindCombobox), the
wizard material autocomplete (wizardMaterialKeydown), and the dryer-box
slot→toolhead feeds combobox (inv_loc_mgr) — both its populated and its empty
("No matches") list states, since the empty-list path was a separate gap. The
bind-slot-picker Escape (also part of this sweep) is covered by
test_bind_slot_picker.py::test_bind_picker_escape_closes; the wizard
multi-choice chip picker (wizardMultiselectKeydown) got the identical fix.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


def _first_dryer_box_with_slots(api_base_url):
    """Return the first Dryer Box row with Max Spools > 0, or None."""
    locs = requests.get(f"{api_base_url}/api/locations", timeout=5).json()
    rows = locs if isinstance(locs, list) else (locs.get("locations") or locs.get("rows") or [])

    def _slots(r):
        try:
            return int(str(r.get("Max Spools") or "0").strip() or 0)
        except (TypeError, ValueError):
            return 0

    return next((r for r in rows if r.get("Type") == "Dryer Box" and _slots(r) > 0), None)


@pytest.mark.usefixtures("require_server")
def test_escape_closes_wizard_location_dropdown_not_modal(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function("() => typeof window.openWizardModal === 'function'", timeout=10000)
    page.evaluate("() => window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible(timeout=8000)
    page.wait_for_selector("#wiz-spool-location-search", timeout=8000)

    # Open the location dropdown via ArrowDown on the focused search input.
    page.focus("#wiz-spool-location-search")
    page.keyboard.press("ArrowDown")
    page.wait_for_function(
        "() => { const d = document.getElementById('dropdown-location');"
        "        return d && d.style.display !== 'none'; }",
        timeout=4000,
    )

    # Escape: the dropdown closes; the wizard modal stays open.
    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => { const d = document.getElementById('dropdown-location');"
        "        return d && d.style.display === 'none'; }",
        timeout=4000,
    )
    assert page.evaluate(
        "() => document.getElementById('wizardModal').classList.contains('show')"
    ), "Escape on the open wizard combobox dropdown must NOT close the wizard modal"


@pytest.mark.usefixtures("require_server")
def test_escape_closes_wizard_material_dropdown_not_modal(page: Page, base_url):
    """The material autocomplete (wizardMaterialKeydown) had NO Escape branch —
    Escape there used to dismiss the whole wizard (caught by the review)."""
    page.goto(base_url)
    page.wait_for_selector("#buffer-zone", timeout=10000)
    page.wait_for_function("() => typeof window.openWizardModal === 'function'", timeout=10000)
    page.evaluate("() => window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible(timeout=8000)
    page.wait_for_selector("#wiz-fil-material", timeout=8000)

    mat = page.locator("#wiz-fil-material")
    mat.focus()
    # Typing fires wizardMaterialFilter() which opens the suggestion dropdown.
    mat.press_sequentially("P", delay=30)
    page.wait_for_function(
        "() => { const d = document.getElementById('dropdown-material');"
        "        return d && d.style.display !== 'none'; }",
        timeout=4000,
    )

    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => { const d = document.getElementById('dropdown-material');"
        "        return d && d.style.display === 'none'; }",
        timeout=4000,
    )
    assert page.evaluate(
        "() => document.getElementById('wizardModal').classList.contains('show')"
    ), "Escape on the open material combobox dropdown must NOT close the wizard modal"


@pytest.mark.usefixtures("require_server")
def test_escape_closes_feeds_combobox_not_manage_modal(page: Page, api_base_url, open_manage_modal):
    box = _first_dryer_box_with_slots(api_base_url)
    if not box:
        pytest.skip("no Dryer Box with slots seeded on dev")

    open_manage_modal(box["LocationID"])
    # Reveal the feeds section so the slot comboboxes are visible/focusable.
    page.evaluate("() => window.toggleFeedsSection && window.toggleFeedsSection()")
    page.wait_for_selector(".feeds-combo-input", timeout=6000)

    # Focusing a feeds combo input opens its dropdown list.
    page.locator(".feeds-combo-input").first.focus()
    page.wait_for_function(
        "() => { const l = document.querySelector('.feeds-combo-list');"
        "        return l && l.style.display === 'block'; }",
        timeout=4000,
    )

    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => { const l = document.querySelector('.feeds-combo-list');"
        "        return l && l.style.display === 'none'; }",
        timeout=4000,
    )
    assert page.evaluate(
        "() => document.getElementById('manageModal').classList.contains('show')"
    ), "Escape on the open feeds combobox must NOT close the Location Manager modal"


@pytest.mark.usefixtures("require_server")
def test_escape_closes_feeds_combobox_empty_list_not_manage_modal(page: Page, api_base_url, open_manage_modal):
    """The empty-list ('No matches') path: the feeds-combo Escape branch used to
    sit AFTER the `if (!items.length) return` guard, so Escape with a no-match
    filter bubbled to and closed the manage modal (caught by the review)."""
    box = _first_dryer_box_with_slots(api_base_url)
    if not box:
        pytest.skip("no Dryer Box with slots seeded on dev")

    open_manage_modal(box["LocationID"])
    page.evaluate("() => window.toggleFeedsSection && window.toggleFeedsSection()")
    page.wait_for_selector(".feeds-combo-input", timeout=6000)

    combo = page.locator(".feeds-combo-input").first
    combo.focus()
    # Type a filter that matches nothing → list renders the "No matches" state
    # (display:block, zero .feeds-combo-item) — the empty-list edge case.
    combo.press_sequentially("zzz-no-such-toolhead", delay=10)
    page.wait_for_function(
        "() => { const l = document.querySelector('.feeds-combo-list');"
        "        return l && l.style.display === 'block'"
        "          && l.querySelectorAll('.feeds-combo-item').length === 0; }",
        timeout=4000,
    )

    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => { const l = document.querySelector('.feeds-combo-list');"
        "        return l && l.style.display === 'none'; }",
        timeout=4000,
    )
    assert page.evaluate(
        "() => document.getElementById('manageModal').classList.contains('show')"
    ), "Escape on the empty 'No matches' feeds list must NOT close the Location Manager modal"
