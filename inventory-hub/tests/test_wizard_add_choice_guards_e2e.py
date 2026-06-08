"""Group 10.9 — End-to-end coverage of the +Add Choice validation guards
on the wizard's `wizardPromptNewChoice` overlay.

Exercises the four acceptance criteria from the task spec:
- Single-char inputs rejected with inline error.
- Leading/trailing punctuation rejected.
- Fuzzy-match prompt fires for near-duplicates.
- Two-step confirm before a new choice is committed to Spoolman.

We never actually POST to /api/external/fields/add_choice because that would
permanently add junk to Derek's dev Spoolman. Instead we stub `fetch` inside
the page context to capture the payload.
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


def _force_close_wizard(page: Page) -> None:
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        if (m) {
            try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}
            m.hide();
        }
    """)
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5_000)


def _open_add_new_choice_for_filament_attributes(page: Page) -> None:
    """Open the +Add Choice overlay seeded as the filament_attributes target.
    We invoke the function directly here for stability (no dependence on the
    extras section being expanded). The multi-choice path now ALSO renders a
    real ➕ button wired to this same wizardPromptNewChoice — that button is
    exercised directly in test_wizard_multichoice_add_button_e2e.py. The
    overlay UI is identical regardless of which field opened it."""
    page.evaluate("""
        // Ensure schema is loaded so the overlay's existingChoices lookup works.
        wizardFetchExtraFields();
    """)
    page.wait_for_function(
        "wizardState && wizardState.extraFields && wizardState.extraFields.filament && wizardState.extraFields.filament.length > 0",
        timeout=5_000,
    )
    page.evaluate("window.wizardPromptNewChoice('fil', 'filament_attributes')")
    expect(page.locator("#fcc-wiz-newchoice")).to_be_visible(timeout=2_000)


def test_single_char_rejected_inline(page: Page):
    _open_wizard(page)
    _open_add_new_choice_for_filament_attributes(page)

    page.locator("#fcc-wiz-newchoice-input").fill("F")
    page.locator("#fcc-wiz-newchoice-confirm").click()

    msg = page.locator("#fcc-wiz-newchoice-msg")
    expect(msg).to_have_text(
        "Must be at least 3 characters",
        timeout=2_000,
    )
    # Overlay stays open on the input stage — user can correct without losing the modal.
    expect(page.locator("#fcc-wiz-newchoice")).to_be_visible()
    expect(page.locator("#fcc-wiz-newchoice")).to_have_attribute("data-stage", "input")

    _force_close_wizard(page)


def test_leading_punctuation_rejected_inline(page: Page):
    _open_wizard(page)
    _open_add_new_choice_for_filament_attributes(page)

    page.locator("#fcc-wiz-newchoice-input").fill(";Transparent")
    page.locator("#fcc-wiz-newchoice-confirm").click()

    msg = page.locator("#fcc-wiz-newchoice-msg")
    expect(msg).to_contain_text("punctuation", timeout=2_000)
    expect(page.locator("#fcc-wiz-newchoice")).to_be_visible()

    _force_close_wizard(page)


def test_fuzzy_match_shows_suggestion_panel(page: Page):
    _open_wizard(page)
    _open_add_new_choice_for_filament_attributes(page)

    # Find an existing attribute we can prefix-typo on.
    existing = page.evaluate("""
        () => {
            const list = wizardState.extraFields.filament.find(f => f.key === 'filament_attributes');
            const choices = list?.choices || [];
            // Pick first choice that is >= 5 chars so we can take its first 4 as a prefix.
            return choices.find(c => c && c.length >= 5) || null;
        }
    """)
    if not existing:
        pytest.skip("no existing filament_attribute long enough for a prefix typo test")
    typo = existing[:4]

    page.locator("#fcc-wiz-newchoice-input").fill(typo)
    page.locator("#fcc-wiz-newchoice-confirm").click()

    # The overlay swaps content rather than mounting a nested overlay
    # (avoids the Escape capture-phase race when nested).
    overlay = page.locator("#fcc-wiz-newchoice")
    expect(overlay).to_be_visible(timeout=2_000)
    expect(overlay).to_have_attribute("data-stage", "suggestion")
    expect(overlay).to_contain_text(existing)

    # Escape closes the single overlay — no race.
    page.keyboard.press("Escape")
    expect(overlay).not_to_be_attached(timeout=2_000)

    _force_close_wizard(page)


def test_clean_new_value_requires_two_step_confirm(page: Page):
    """A clean, suggestion-free value should require a SECOND click on the
    permanent-add confirm overlay before the POST fires."""
    _open_wizard(page)
    _open_add_new_choice_for_filament_attributes(page)

    # Stub fetch BEFORE we trigger commit so we can assert it didn't fire
    # until the user confirmed in the second overlay.
    page.evaluate("""
        window.__addChoiceCalls = [];
        const origFetch = window.fetch;
        window.fetch = function(url, opts) {
            if (typeof url === 'string' && url.includes('/api/external/fields/add_choice')) {
                window.__addChoiceCalls.push({ url, body: opts && opts.body });
                // Return a successful response without actually hitting Spoolman.
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ success: true })
                });
            }
            return origFetch.apply(this, arguments);
        };
    """)

    # Pick a guaranteed-not-in-list value.
    unique_value = "ZZ_FCC_TEST_VALUE_DO_NOT_KEEP"
    page.locator("#fcc-wiz-newchoice-input").fill(unique_value)
    page.locator("#fcc-wiz-newchoice-confirm").click()

    # The overlay swaps in-place to the confirm stage (data-stage="confirm")
    # rather than mounting a nested overlay — avoids Escape capture-phase race.
    overlay = page.locator("#fcc-wiz-newchoice")
    expect(overlay).to_be_visible(timeout=2_000)
    expect(overlay).to_have_attribute("data-stage", "confirm")
    expect(overlay).to_contain_text(unique_value)

    # No POST yet — guarded behind the second step.
    calls_so_far = page.evaluate("() => window.__addChoiceCalls.length")
    assert calls_so_far == 0, "POST fired before two-step confirm"

    # Confirm the second step.
    overlay.locator("#fcc-wiz-addnew-confirm").click()

    # Now the POST should have fired.
    page.wait_for_function(
        "() => window.__addChoiceCalls.length === 1",
        timeout=2_000,
    )
    payload = page.evaluate("() => window.__addChoiceCalls[0]")
    assert unique_value in payload["body"]
    assert "filament_attributes" in payload["body"]

    # Overlay closes after success.
    expect(overlay).not_to_be_attached(timeout=2_000)

    _force_close_wizard(page)


def test_two_step_cancel_does_not_commit(page: Page):
    """Cancelling the second confirm step should NOT fire the POST."""
    _open_wizard(page)
    _open_add_new_choice_for_filament_attributes(page)

    page.evaluate("""
        window.__addChoiceCalls = [];
        const origFetch = window.fetch;
        window.fetch = function(url, opts) {
            if (typeof url === 'string' && url.includes('/api/external/fields/add_choice')) {
                window.__addChoiceCalls.push({ url, body: opts && opts.body });
                return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) });
            }
            return origFetch.apply(this, arguments);
        };
    """)

    page.locator("#fcc-wiz-newchoice-input").fill("ZZ_FCC_TEST_CANCEL_PATH")
    page.locator("#fcc-wiz-newchoice-confirm").click()

    overlay = page.locator("#fcc-wiz-newchoice")
    expect(overlay).to_have_attribute("data-stage", "confirm", timeout=2_000)
    overlay.locator("#fcc-wiz-addnew-cancel").click()
    # Cancel closes the overlay so user can re-trigger from scratch.
    expect(overlay).not_to_be_attached(timeout=2_000)

    calls = page.evaluate("() => window.__addChoiceCalls.length")
    assert calls == 0, "POST fired despite user cancelling the confirm step"

    _force_close_wizard(page)


def test_live_preview_shows_canonical_form(page: Page):
    """As the user types, the preview area should reflect the normalized
    canonical form so they see what will actually be stored."""
    _open_wizard(page)
    _open_add_new_choice_for_filament_attributes(page)

    inp = page.locator("#fcc-wiz-newchoice-input")
    preview = page.locator("#fcc-wiz-newchoice-preview")

    # Trigger oninput by typing.
    inp.fill("  Multi   Color  ")
    expect(preview).to_have_text("Stored as: Multi Color", timeout=2_000)

    # Clean input → no preview text.
    inp.fill("Cool Color")
    expect(preview).to_have_text("", timeout=2_000)

    _force_close_wizard(page)
