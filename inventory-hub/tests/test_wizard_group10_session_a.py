"""Group 10 Session A regression tests.

Covers:
  10.2 + 10.10 — wizardBindCombobox shows the full list on focus
                 (not the prior selection's filtered view) and highlights the
                 currently-selected row.
  10.3        — Location combobox placeholder reads "Unassigned (default)"
                 to make the no-selection default visible.
  10.11       — Wizard cancel only re-opens a details modal when the wizard
                 was launched from one. Launching from the dashboard FAB or
                 directly calling openEditWizard with no source modal visible
                 closes silently on cancel.

These tests hit the live dev server at http://localhost:8000 — they require
the inventory_hub container to be running.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


# --- Helpers ----------------------------------------------------------------

def _open_wizard_fresh(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible()


def _force_close_wizard(page: Page) -> None:
    """Dismiss the wizard without the unsaved-changes guard tripping.

    Bootstrap swallows `.hide()` when the modal is still mid-transition (its
    `_isTransitioning` guard), which intermittently left the wizard `.show`
    so the chained `hidden.bs.modal` reopen never fired (Group 26.7). Hide,
    and if a transition race ate the call, settle briefly and retry."""
    def _hide():
        page.evaluate("""
            const el = document.getElementById('wizardModal');
            const m = bootstrap.Modal.getInstance(el) || bootstrap.Modal.getOrCreateInstance(el);
            // wizardState is script-scoped, not on window — reference by name.
            try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}
            if (m) m.hide();
        """)
    for attempt in range(3):
        _hide()
        if attempt == 2:
            # Final attempt: let the assertion raise directly if it still fails.
            expect(page.locator("#wizardModal")).not_to_be_visible(timeout=3_000)
            return
        try:
            expect(page.locator("#wizardModal")).not_to_be_visible(timeout=2_500)
            return
        except AssertionError:
            page.wait_for_timeout(300)  # let the in-flight transition settle, then retry


def _pick_first_real_location(page: Page) -> str:
    """Open the location combobox and select option index 1 (the first
    non-Unassigned row). Returns the selected option's label."""
    search = page.locator("#wiz-spool-location-search")
    search.click()
    dropdown = page.locator("#dropdown-location")
    expect(dropdown).to_be_visible()
    opts = dropdown.locator(".autocomplete-option")
    if opts.count() < 2:
        pytest.skip("need at least 2 location options (Unassigned + 1 real)")
    label = opts.nth(1).inner_text().strip()
    # Click the second option via mousedown (the combobox listens for mousedown)
    opts.nth(1).dispatch_event("mousedown")
    expect(dropdown).not_to_be_visible()
    expect(search).to_have_value(label)
    return label


# --- 10.3 — placeholder copy -----------------------------------------------

def test_location_placeholder_advertises_default(page: Page):
    _open_wizard_fresh(page)
    search = page.locator("#wiz-spool-location-search")
    expect(search).to_have_attribute("placeholder", "Unassigned (default)")


# --- 10.2 + 10.10 — focus shows full list, highlights selection ------------

def test_location_combobox_focus_shows_full_list_after_selection(page: Page):
    """After selecting a location, re-focusing the search input must show ALL
    options — not just the one matching the selected label.

    Strategy: capture the canonical full-list count from a fresh wizard open
    (before any selection), then re-open the wizard, make a selection,
    re-focus, and confirm the rendered option count matches the canonical."""
    # Baseline: fresh wizard, no selection → click input → count
    _open_wizard_fresh(page)
    baseline_search = page.locator("#wiz-spool-location-search")
    baseline_search.click()
    baseline_dropdown = page.locator("#dropdown-location")
    expect(baseline_dropdown).to_be_visible()
    canonical_full = baseline_dropdown.locator(".autocomplete-option").count()
    _force_close_wizard(page)

    # Real run: open wizard, select option 1, re-focus, count must match
    _open_wizard_fresh(page)
    label = _pick_first_real_location(page)

    search = page.locator("#wiz-spool-location-search")
    dropdown = page.locator("#dropdown-location")

    # Click the input again to re-open the dropdown. The selection is still
    # populated, so under the pre-fix behavior this would render only the
    # one matching option. Post-fix it renders the full list.
    search.click()
    expect(dropdown).to_be_visible()
    visible_after_focus = dropdown.locator(".autocomplete-option").count()

    assert visible_after_focus == canonical_full, (
        f"focus after selection rendered {visible_after_focus} options, "
        f"expected the full list ({canonical_full})"
    )
    # And the visible input still shows the selected label — no clobbering.
    expect(search).to_have_value(label)


def test_location_combobox_highlights_current_selection_on_focus(page: Page):
    """The currently-selected option must render with the .active class on
    focus so the user can hit Enter to re-confirm without re-picking."""
    _open_wizard_fresh(page)
    _pick_first_real_location(page)

    search = page.locator("#wiz-spool-location-search")
    dropdown = page.locator("#dropdown-location")
    hidden = page.locator("#wiz-spool-location")
    selected_value = hidden.input_value()

    search.click()  # re-focus
    expect(dropdown).to_be_visible()

    active = dropdown.locator(".autocomplete-option.active")
    assert active.count() == 1, "expected exactly one .active option"
    assert active.first.get_attribute("data-value") == selected_value


# --- 10.11 — source-aware cancel restore -----------------------------------

def test_dashboard_fab_cancel_does_not_pop_details_modal(page: Page):
    """Opening the wizard with no source details modal visible (dashboard FAB
    flow) must close silently — no spool/filament details modal should pop."""
    _open_wizard_fresh(page)

    # Confirm both details modals are not currently visible
    expect(page.locator("#spoolModal")).not_to_be_visible()
    expect(page.locator("#filamentModal")).not_to_be_visible()

    _force_close_wizard(page)

    # After the wizard closes, neither details modal should have popped
    # (give the hidden.bs.modal listener its 200ms setTimeout to fire)
    page.wait_for_timeout(400)
    expect(page.locator("#spoolModal")).not_to_be_visible()
    expect(page.locator("#filamentModal")).not_to_be_visible()


def test_edit_wizard_cancel_with_no_source_modal_does_not_pop_details(
    page: Page, api_base_url: str
):
    """Reproduces the 10.11 buglist scenario: search FAB / Location Manager
    / grid card click → Edit → wizard opens → cancel → no details modal pops.

    We simulate the launch by directly calling window.openEditWizard with
    both spoolModal and filamentModal hidden — the same state those entry
    points produce."""
    r = requests.get(f"{api_base_url}/api/search?q=", timeout=5)
    if not r.ok:
        pytest.skip("search API unavailable")
    results = (r.json() or {}).get("results") or []
    if not results:
        pytest.skip("no spools available to edit in this environment")
    spool_id = results[0].get("id")
    if not spool_id:
        pytest.skip("search result missing id")

    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")

    # Confirm precondition: no details modal visible
    expect(page.locator("#spoolModal")).not_to_be_visible()
    expect(page.locator("#filamentModal")).not_to_be_visible()

    page.evaluate(f"window.openEditWizard && window.openEditWizard({spool_id})")
    expect(page.locator("#wizardModal")).to_be_visible()
    expect(page.locator("#step-2-filament")).to_be_visible(timeout=10_000)

    # Verify the source-aware fix left both return-ids null
    # (wizardState is `let` at script scope — reference by bare name.)
    return_state = page.evaluate("""({
        spool: wizardState.returnToSpoolId,
        filament: wizardState.returnToFilamentId
    })""")
    assert return_state["spool"] in (None, ""), (
        f"returnToSpoolId should be null when launched without a source modal, "
        f"got {return_state['spool']!r}"
    )
    assert return_state["filament"] in (None, ""), (
        f"returnToFilamentId should be null when launched without a source modal, "
        f"got {return_state['filament']!r}"
    )

    _force_close_wizard(page)
    page.wait_for_timeout(400)

    expect(page.locator("#spoolModal")).not_to_be_visible()
    expect(page.locator("#filamentModal")).not_to_be_visible()


def test_edit_wizard_cancel_from_spool_details_reopens_details(
    page: Page, api_base_url: str
):
    """Preserved behavior: when the wizard IS launched from an open spool
    details modal, cancel must re-open that details modal."""
    r = requests.get(f"{api_base_url}/api/search?q=", timeout=5)
    if not r.ok:
        pytest.skip("search API unavailable")
    results = (r.json() or {}).get("results") or []
    if not results:
        pytest.skip("no spools available to edit in this environment")
    spool_id = results[0].get("id")
    if not spool_id:
        pytest.skip("search result missing id")

    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")

    # Open the spool details modal FIRST so it's the source surface.
    # openSpoolDetails is declared with `const` in inv_details.js, so it lives
    # in script scope (not on window) — call by bare identifier, the same way
    # production inline onclick handlers do.
    page.evaluate(f"openSpoolDetails({spool_id})")
    expect(page.locator("#spoolModal")).to_be_visible(timeout=5_000)

    # Now launch the edit wizard — openEditWizard should detect spoolModal
    # is visible and set returnToSpoolId
    page.evaluate(f"window.openEditWizard && window.openEditWizard({spool_id})")
    expect(page.locator("#wizardModal")).to_be_visible()
    expect(page.locator("#step-2-filament")).to_be_visible(timeout=10_000)

    return_state = page.evaluate("({ spool: wizardState.returnToSpoolId })")
    assert str(return_state["spool"]) == str(spool_id), (
        f"returnToSpoolId should match the source spool, got {return_state['spool']!r}"
    )

    _force_close_wizard(page)
    # The hidden.bs.modal listener fires openSpoolDetails after a 200ms setTimeout.
    # Wait long enough for that AND for the modal to re-render.
    expect(page.locator("#spoolModal")).to_be_visible(timeout=5_000)
