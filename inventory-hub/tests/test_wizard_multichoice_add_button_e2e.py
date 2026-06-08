"""The multi-choice chip widget (e.g. filament_attributes) now renders a real
➕ "add new option" button — parity with the single-choice path, which always
had one. Closes the Feature-Buglist.md (2026-05-30) complaint that the wizard's
filament-attributes section "mentions using a + button … but there isn't a +
on the screen to add a new one."

The button is wired to the SAME wizardPromptNewChoice as the single-choice ➕,
but that function is now multi-choice aware: on success it drops a chip in
place + registers the new choice in the live schema/dropdown, instead of
refetching the field schema (a refetch wipes the in-progress wizard DOM).

We never let the real /api/external/fields/add_choice POST hit Spoolman — it's
stubbed inside the page so we don't pollute Derek's dev choice list.
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
    # Ensure the dynamic extra fields (incl. filament_attributes) are rendered.
    page.evaluate("wizardFetchExtraFields()")
    page.wait_for_function(
        "wizardState && wizardState.extraFields && wizardState.extraFields.filament "
        "&& wizardState.extraFields.filament.length > 0",
        timeout=5_000,
    )


def _require_multichoice_attr(page: Page) -> None:
    is_multi = page.evaluate(
        """() => {
            const f = (wizardState.extraFields.filament || [])
                .find(f => f.key === 'filament_attributes');
            return !!(f && f.multi_choice);
        }"""
    )
    if not is_multi:
        pytest.skip("filament_attributes is not multi_choice on this dev Spoolman")


def _force_close_wizard(page: Page) -> None:
    page.evaluate("""
        const m = bootstrap.Modal.getInstance(document.getElementById('wizardModal'));
        if (m) {
            try { wizardState.forceClose = true; wizardState.isDirty = false; } catch (_) {}
            m.hide();
        }
    """)
    expect(page.locator("#wizardModal")).not_to_be_visible(timeout=5_000)


def _stub_add_choice(page: Page) -> None:
    """Capture add_choice POSTs and count /api/external/fields refetches."""
    page.evaluate("""
        window.__addChoiceCalls = [];
        window.__fieldsRefetches = 0;
        const origFetch = window.fetch;
        window.fetch = function(url, opts) {
            if (typeof url === 'string' && url.includes('/api/external/fields/add_choice')) {
                window.__addChoiceCalls.push({ url, body: opts && opts.body });
                return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) });
            }
            if (typeof url === 'string' && url.endsWith('/api/external/fields')) {
                window.__fieldsRefetches++;
            }
            return origFetch.apply(this, arguments);
        };
    """)


def test_plus_button_renders_for_multichoice_field(page: Page):
    _open_wizard(page)
    _require_multichoice_attr(page)

    btn = page.locator("[data-extra-key='filament_attributes'] .wizard-multichoice-add")
    expect(btn).to_have_count(1)
    onclick = btn.get_attribute("onclick")
    assert "wizardPromptNewChoice" in (onclick or "")
    assert "filament_attributes" in (onclick or "")

    _force_close_wizard(page)


def test_plus_button_opens_overlay(page: Page):
    _open_wizard(page)
    _require_multichoice_attr(page)

    # The button uses onmousedown=preventDefault to keep focus on the chip input;
    # dispatch a real click so it opens regardless of section scroll state.
    page.locator("[data-extra-key='filament_attributes'] .wizard-multichoice-add").dispatch_event("click")
    expect(page.locator("#fcc-wiz-newchoice")).to_be_visible(timeout=2_000)
    expect(page.locator("#fcc-wiz-newchoice")).to_have_attribute("data-stage", "input")

    _force_close_wizard(page)


def test_plus_button_preseeds_typed_value(page: Page):
    _open_wizard(page)
    _require_multichoice_attr(page)

    # Simulate the user typing into the chip input then clicking ➕.
    page.evaluate("document.getElementById('wiz_fil_ef_filament_attributes').value = 'Silky Stuff'")
    page.locator("[data-extra-key='filament_attributes'] .wizard-multichoice-add").dispatch_event("click")

    overlay_input = page.locator("#fcc-wiz-newchoice-input")
    expect(overlay_input).to_be_visible(timeout=2_000)
    expect(overlay_input).to_have_value("Silky Stuff")
    # The chip input is cleared so the pending blur-commit can't double-add it.
    assert page.evaluate("document.getElementById('wiz_fil_ef_filament_attributes').value") == ""

    _force_close_wizard(page)


def test_multichoice_add_drops_chip_in_place_without_refetch(page: Page):
    """Full flow: a clean new value → two-step confirm → POST → a chip appears
    in the field WITHOUT a schema refetch (which would wipe the wizard DOM)."""
    _open_wizard(page)
    _require_multichoice_attr(page)
    _stub_add_choice(page)

    unique = "ZZ_FCC_MULTICHOICE_DO_NOT_KEEP"
    page.evaluate(f"window.wizardPromptNewChoice('fil', 'filament_attributes')")
    page.locator("#fcc-wiz-newchoice-input").fill(unique)
    page.locator("#fcc-wiz-newchoice-confirm").click()

    overlay = page.locator("#fcc-wiz-newchoice")
    expect(overlay).to_have_attribute("data-stage", "confirm", timeout=2_000)
    overlay.locator("#fcc-wiz-addnew-confirm").click()

    # add_choice POST fired exactly once.
    page.wait_for_function("() => window.__addChoiceCalls.length === 1", timeout=2_000)
    # A chip with the value now lives in the field's chip container.
    chip = page.locator(
        f"#chip-container-fil-filament_attributes .dynamic-chip[data-value='{unique}']"
    )
    expect(chip).to_have_count(1, timeout=2_000)
    # Overlay closed.
    expect(overlay).not_to_be_attached(timeout=2_000)
    # NO schema refetch happened (multi-choice path keeps the DOM intact).
    assert page.evaluate("() => window.__fieldsRefetches") == 0

    _force_close_wizard(page)


def test_multichoice_add_no_duplicate_post_on_known_value(page: Page):
    """If the typed value already exists as a choice, the overlay's fuzzy guard
    routes it to the suggestion panel rather than committing a fresh POST."""
    _open_wizard(page)
    _require_multichoice_attr(page)
    _stub_add_choice(page)

    existing = page.evaluate(
        """() => {
            const f = wizardState.extraFields.filament.find(f => f.key === 'filament_attributes');
            const c = f?.choices || [];
            return c.find(x => x && x.length >= 3) || null;
        }"""
    )
    if not existing:
        pytest.skip("no existing filament_attribute choice to test the known-value path")

    page.evaluate("window.wizardPromptNewChoice('fil', 'filament_attributes')")
    page.locator("#fcc-wiz-newchoice-input").fill(existing)
    page.locator("#fcc-wiz-newchoice-confirm").click()

    # An exact existing value trips the suggestion stage (it matches itself);
    # the important guarantee is no blind add_choice POST fired.
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__addChoiceCalls.length") == 0

    _force_close_wizard(page)
