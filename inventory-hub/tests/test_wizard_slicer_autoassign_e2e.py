"""Group 10.5 — Adding a new slicer_profile from inside the wizard should
auto-assign it to the filament being edited, rather than just registering it
with the Spoolman schema and leaving the user to re-pick.

The pattern mirrors `inv_details.js:promptEditSlicerProfile` which has done
this on the details modal for a while. The wizard's new
`window.wizardOnNewChoiceAdded` hook fires after the schema refresh completes
and selects the freshly-added value.

These tests stub `fetch` for the add_choice POST so we don't pollute Derek's
dev Spoolman with throwaway slicer profile names. The fake response also
mutates `wizardState.extraFields` so the field re-render picks up the new
option without hitting Spoolman.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _open_wizard(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.validateNewChoice === 'function'", timeout=5_000)
    page.evaluate("window.openWizardModal && window.openWizardModal()")
    expect(page.locator("#wizardModal")).to_be_visible()
    # Trigger field load
    page.evaluate("wizardFetchExtraFields()")
    page.wait_for_function(
        "wizardState && wizardState.extraFields && wizardState.extraFields.filament && wizardState.extraFields.filament.length > 0",
        timeout=5_000,
    )


def _force_close_wizard(page: Page) -> None:
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        if (m) {
            try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}
            m.hide();
        }
    """)
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5_000)


def _stub_add_choice_and_field_refresh(page: Page, new_value: str) -> None:
    """Stub the add_choice POST AND the subsequent /api/external/fields GET
    so the schema refresh returns the new option without actually mutating
    Spoolman."""
    page.evaluate(
        """([newVal]) => {
            window.__addChoiceCalls = [];
            const origFetch = window.fetch;
            window.fetch = function(url, opts) {
                if (typeof url === 'string' && url.includes('/api/external/fields/add_choice')) {
                    window.__addChoiceCalls.push({ url, body: opts && opts.body });
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve({ success: true })
                    });
                }
                if (typeof url === 'string' && url.endsWith('/api/external/fields') && (!opts || !opts.method || opts.method === 'GET')) {
                    // Return a synthetic schema with newVal appended to slicer_profile's choices.
                    return origFetch.apply(this, arguments).then(r => r.json()).then(data => {
                        try {
                            const sl = data.fields.filament.find(f => f.key === 'slicer_profile');
                            if (sl) {
                                const cs = Array.isArray(sl.choices) ? sl.choices.slice() : [];
                                if (!cs.includes(newVal)) cs.push(newVal);
                                sl.choices = cs;
                            }
                        } catch (_) {}
                        return {
                            ok: true,
                            json: () => Promise.resolve(data)
                        };
                    });
                }
                return origFetch.apply(this, arguments);
            };
        }""",
        [new_value],
    )


def test_new_slicer_profile_auto_selects_after_add(page: Page):
    _open_wizard(page)

    # Skip if the dev environment doesn't have a slicer_profile select rendered
    # (it depends on the schema actually having that field).
    has_slicer = page.evaluate(
        "document.getElementById('wiz_fil_ef_slicer_profile') !== null"
    )
    if not has_slicer:
        pytest.skip("wiz_fil_ef_slicer_profile not rendered in this env")

    new_profile = "FCC_TEST_PETG_0.4mm_ZZ"

    # Sanity: the new value isn't already an option.
    pre_options = page.evaluate(
        "Array.from(document.querySelectorAll('#wiz_fil_ef_slicer_profile option')).map(o => o.value)"
    )
    assert new_profile not in pre_options

    _stub_add_choice_and_field_refresh(page, new_profile)

    # Drive the +Add flow directly via the public function the ➕ button uses.
    page.evaluate("window.wizardPromptNewChoice('fil', 'slicer_profile')")
    expect(page.locator("#fcc-wiz-newchoice")).to_be_visible(timeout=2_000)

    page.locator("#fcc-wiz-newchoice-input").fill(new_profile)
    page.locator("#fcc-wiz-newchoice-confirm").click()

    # Two-step confirm.
    expect(page.locator("#fcc-wiz-newchoice")).to_have_attribute(
        "data-stage", "confirm", timeout=2_000
    )
    page.locator("#fcc-wiz-addnew-confirm").click()

    # POST captured.
    page.wait_for_function(
        "() => window.__addChoiceCalls.length === 1",
        timeout=3_000,
    )

    # After the refresh, the select should now (a) contain the new option,
    # AND (b) have it pre-selected.
    page.wait_for_function(
        """([val]) => {
            const sel = document.getElementById('wiz_fil_ef_slicer_profile');
            if (!sel) return false;
            const opts = Array.from(sel.options).map(o => o.value);
            return opts.includes(val) && sel.value === val;
        }""",
        arg=[new_profile],
        timeout=3_000,
    )

    # And dirty-tracking should have fired.
    is_dirty = page.evaluate("wizardState.isDirty === true")
    assert is_dirty, "wizardState.isDirty should be true after auto-assign"

    _force_close_wizard(page)


def test_use_existing_suggestion_auto_selects_existing_value(page: Page):
    """When the user types a near-duplicate and clicks "Use existing", the
    suggested existing value should be assigned to the wizard's field even
    though no POST fired (wasNew=false branch)."""
    _open_wizard(page)
    has_slicer = page.evaluate(
        "document.getElementById('wiz_fil_ef_slicer_profile') !== null"
    )
    if not has_slicer:
        pytest.skip("wiz_fil_ef_slicer_profile not rendered in this env")

    # Find an existing slicer profile to typo-prefix.
    existing = page.evaluate("""
        () => {
            const sl = wizardState.extraFields.filament.find(f => f.key === 'slicer_profile');
            const choices = sl?.choices || [];
            return choices.find(c => c && c.length >= 5) || null;
        }
    """)
    if not existing:
        pytest.skip("no slicer profile long enough for prefix typo")

    page.evaluate("window.wizardPromptNewChoice('fil', 'slicer_profile')")
    page.locator("#fcc-wiz-newchoice-input").fill(existing[:4])
    page.locator("#fcc-wiz-newchoice-confirm").click()

    # Should land on suggestion stage with the existing value.
    expect(page.locator("#fcc-wiz-newchoice")).to_have_attribute(
        "data-stage", "suggestion", timeout=2_000
    )

    # Click "Use existing".
    page.locator("#fcc-wiz-sugg-use").click()

    # The select should now have the suggestion value picked.
    page.wait_for_function(
        """([val]) => {
            const sel = document.getElementById('wiz_fil_ef_slicer_profile');
            return sel && sel.value === val;
        }""",
        arg=[existing],
        timeout=2_000,
    )

    _force_close_wizard(page)
