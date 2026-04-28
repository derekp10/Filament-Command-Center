"""
Tests for the Phase-2 <WeightEntry> overlay (modules/weight_entry.js).

Exercises the wiring layer above the unit-tested computeUsedWeight() math:
  - The overlay opens at the right surface IDs
  - Mode tabs swap the input label, formula hint, input type, and preview
  - +/- prefix syntax in Additive mode flows through parseAdditiveInput
  - The preview panel reflects computeUsedWeight's verdict (used / remaining)
  - Submit + Cancel close the overlay and fire the supplied callbacks
  - Gross mode + missing tare triggers promptMissingEmptyWeight inline
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _open_dashboard(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.WeightEntry === 'object' && "
        "typeof window.WeightEntry.openModal === 'function'",
        timeout=5_000,
    )


def _open_overlay_with(page: Page, options_js: str) -> None:
    """Open the WeightEntry overlay with the supplied JS-literal options dict.

    The caller's `options_js` is inlined into a `() => window.WeightEntry.openModal({...})`
    arrow function body, so it can reference window callbacks defined in the
    same evaluate (e.g. window._fccLastSubmit = ...).
    """
    page.evaluate(f"() => {{ window.WeightEntry.openModal({options_js}); }}")
    page.wait_for_selector("#fcc-weight-entry-overlay", state="visible", timeout=3_000)


def test_overlay_opens_with_default_additive_mode(page: Page) -> None:
    _open_dashboard(page)
    _open_overlay_with(page, """{
        title: 'Quick Weigh',
        spool: { id: 101, initial_weight: 1000, used_weight: 575,
                 display: 'CC3D - PLA - Crimson Red', color_hex: 'cc3300' },
        empty_spool_weight: 220,
        empty_source: 'filament',
    }""")
    # Default mode is Additive — input label and formula hint should match.
    expect(page.locator("#fcc-we-input-label")).to_contain_text("Delta consumed")
    expect(page.locator("#fcc-we-hint")).to_contain_text("current_used + delta")
    # Tare badge visible because source = filament.
    expect(page.locator("#fcc-we-tare-badge")).to_be_visible()
    # Active tab marker:
    active = page.evaluate(
        "() => document.querySelector('.fcc-we-tab.btn-info').dataset.mode"
    )
    assert active == "additive"


def test_mode_tab_switch_updates_label_and_input_type(page: Page) -> None:
    _open_dashboard(page)
    _open_overlay_with(page, """{
        title: 'Quick Weigh',
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        empty_spool_weight: 220,
    }""")
    page.click(".fcc-we-tab[data-mode='gross']")
    expect(page.locator("#fcc-we-input-label")).to_contain_text("Scale reading WITH spool")
    expect(page.locator("#fcc-we-hint")).to_contain_text("(gross − empty_tare)")
    assert page.evaluate("() => document.getElementById('fcc-we-input').type") == "number"

    page.click(".fcc-we-tab[data-mode='additive']")
    assert page.evaluate("() => document.getElementById('fcc-we-input').type") == "text"


@pytest.mark.parametrize(
    "mode,raw,expected_used,expected_remaining",
    [
        ("additive", "+50", 625, 375),     # 575 + 50
        ("additive", "-100", 475, 525),    # 575 - 100
        ("gross", "645", 575, 425),        # 1000 - (645 - 220)
        ("net", "425", 575, 425),          # 1000 - 425
        ("set_used", "800", 800, 200),     # used = value
    ],
)
def test_preview_reflects_computed_used_and_remaining(
    page: Page, mode, raw, expected_used, expected_remaining
) -> None:
    _open_dashboard(page)
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        empty_spool_weight: 220,
    }""")
    page.click(f".fcc-we-tab[data-mode='{mode}']")
    page.fill("#fcc-we-input", raw)
    # Preview is computed synchronously on input. Check both numbers appear.
    preview_txt = page.locator("#fcc-we-preview").inner_text()
    assert f"{expected_used}g" in preview_txt, (
        f"mode={mode} raw={raw}: preview {preview_txt!r} missing used={expected_used}g"
    )
    assert f"{expected_remaining}g" in preview_txt, (
        f"mode={mode} raw={raw}: preview {preview_txt!r} missing remaining={expected_remaining}g"
    )


def test_clamp_high_warns_in_preview(page: Page) -> None:
    _open_dashboard(page)
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 800 },
    }""")
    page.click(".fcc-we-tab[data-mode='additive']")
    page.fill("#fcc-we-input", "+500")  # 800 + 500 = 1300, clamps high to 1000
    expect(page.locator("#fcc-we-warn")).to_contain_text("clamped to initial")
    assert "1000g" in page.locator("#fcc-we-preview").inner_text()


def test_submit_fires_callback_with_payload_and_closes_overlay(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("() => { window._fccLastSubmit = null; }")
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        empty_spool_weight: 220,
        defaultMode: 'gross',
        showAutoArchive: true,
        onSubmit: (p) => { window._fccLastSubmit = p; },
    }""")
    page.fill("#fcc-we-input", "645")
    page.click("#fcc-we-save")
    # Overlay should be gone.
    page.wait_for_selector("#fcc-weight-entry-overlay", state="detached", timeout=3_000)
    payload = page.evaluate("() => window._fccLastSubmit")
    assert payload is not None
    assert payload["mode"] == "gross"
    assert payload["used_weight"] == 575
    assert payload["remaining"] == 425
    assert payload["empty_spool_weight"] == 220
    assert payload["auto_archive"] is True


def test_cancel_button_closes_overlay_without_callback(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("() => { window._fccLastSubmit = null; window._fccCancelled = false; }")
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        onSubmit: (p) => { window._fccLastSubmit = p; },
        onCancel: () => { window._fccCancelled = true; },
    }""")
    page.click("#fcc-we-cancel")
    page.wait_for_selector("#fcc-weight-entry-overlay", state="detached", timeout=3_000)
    assert page.evaluate("() => window._fccLastSubmit") is None
    assert page.evaluate("() => window._fccCancelled") is True


def test_escape_key_cancels_overlay(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("() => { window._fccCancelled = false; }")
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        onCancel: () => { window._fccCancelled = true; },
    }""")
    page.keyboard.press("Escape")
    page.wait_for_selector("#fcc-weight-entry-overlay", state="detached", timeout=3_000)
    assert page.evaluate("() => window._fccCancelled") is True


def test_arrow_key_swaps_mode_when_focus_outside_input(page: Page) -> None:
    _open_dashboard(page)
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        defaultMode: 'gross',
    }""")
    # Move focus off the input by clicking the dialog header so arrow keys swap modes.
    page.locator("#fcc-we-title").click()
    page.keyboard.press("ArrowRight")
    active = page.evaluate(
        "() => document.querySelector('.fcc-we-tab.btn-info').dataset.mode"
    )
    assert active == "net", f"expected next mode after gross to be net, got {active}"


def test_gross_mode_with_missing_tare_shows_prompt_on_save(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("() => { window._fccLastSubmit = null; }")
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 0,
                 color_hex: 'cc3300' },
        empty_spool_weight: null,
        defaultMode: 'gross',
        context: { vendor: 'CC3D', material: 'PLA', color: 'Crimson Red' },
        onSubmit: (p) => { window._fccLastSubmit = p; },
    }""")
    page.fill("#fcc-we-input", "645")
    # Preview should already hint that a prompt will fire.
    expect(page.locator("#fcc-we-preview")).to_contain_text("Empty-spool weight is missing")
    page.click("#fcc-we-save")
    # The shared promptMissingEmptyWeight overlay should be open.
    page.wait_for_selector("#fcc-missing-empty-weight-overlay", state="visible", timeout=3_000)
    page.fill("#fcc-missing-empty-weight-overlay-input", "220")
    page.click("#fcc-missing-empty-weight-overlay-save")
    # WeightEntry should re-compute and submit.
    page.wait_for_selector("#fcc-weight-entry-overlay", state="detached", timeout=3_000)
    payload = page.evaluate("() => window._fccLastSubmit")
    assert payload is not None
    assert payload["used_weight"] == 575  # 1000 - (645 - 220)
    assert payload["empty_spool_weight"] == 220


def test_gross_mode_missing_tare_cancel_keeps_overlay_open(page: Page) -> None:
    _open_dashboard(page)
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 0 },
        empty_spool_weight: null,
        defaultMode: 'gross',
    }""")
    page.fill("#fcc-we-input", "645")
    page.click("#fcc-we-save")
    page.wait_for_selector("#fcc-missing-empty-weight-overlay", state="visible", timeout=3_000)
    page.click("#fcc-missing-empty-weight-overlay-cancel")
    # The missing-tare overlay closes but WeightEntry remains so the user can
    # change input or mode without re-typing.
    page.wait_for_selector(
        "#fcc-missing-empty-weight-overlay", state="detached", timeout=3_000
    )
    expect(page.locator("#fcc-weight-entry-overlay")).to_be_visible()
