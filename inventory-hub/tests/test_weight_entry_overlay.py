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


def test_stored_default_mode_wins_over_caller_default_mode(page: Page) -> None:
    """13.9 — when the user has clicked "Set as default" on Gross, opening the
    overlay (even when the caller passes defaultMode: 'additive') should land
    on Gross. Stored preference > caller option > first available mode."""
    _open_dashboard(page)
    page.evaluate(
        "() => window.localStorage.setItem('fcc.weighEntry.defaultMode', 'gross')"
    )
    try:
        _open_overlay_with(page, """{
            spool: { id: 101, initial_weight: 1000, used_weight: 575 },
            empty_spool_weight: 220,
            defaultMode: 'additive',
        }""")
        active = page.evaluate(
            "() => document.querySelector('.fcc-we-tab.btn-info').dataset.mode"
        )
        assert active == "gross", (
            f"expected stored default 'gross' to win over caller 'additive'; got {active!r}"
        )
    finally:
        page.evaluate(
            "() => window.localStorage.removeItem('fcc.weighEntry.defaultMode')"
        )


def test_invalid_stored_default_falls_back_to_caller_default(page: Page) -> None:
    """13.9 — corrupt/unknown stored value silently falls through to the
    caller's defaultMode instead of breaking the open. Defensive against
    a future enum change or a user fiddling with devtools."""
    _open_dashboard(page)
    page.evaluate(
        "() => window.localStorage.setItem('fcc.weighEntry.defaultMode', 'nonsense')"
    )
    try:
        _open_overlay_with(page, """{
            spool: { id: 101, initial_weight: 1000, used_weight: 575 },
            empty_spool_weight: 220,
            defaultMode: 'gross',
        }""")
        active = page.evaluate(
            "() => document.querySelector('.fcc-we-tab.btn-info').dataset.mode"
        )
        assert active == "gross", (
            f"corrupt stored value should fall back to caller default 'gross'; got {active!r}"
        )
    finally:
        page.evaluate(
            "() => window.localStorage.removeItem('fcc.weighEntry.defaultMode')"
        )


def test_set_as_default_button_persists_current_mode(page: Page) -> None:
    """13.9 — clicking 'Set as default' writes the current mode to localStorage."""
    _open_dashboard(page)
    page.evaluate(
        "() => window.localStorage.removeItem('fcc.weighEntry.defaultMode')"
    )
    try:
        _open_overlay_with(page, """{
            spool: { id: 101, initial_weight: 1000, used_weight: 575 },
            empty_spool_weight: 220,
            defaultMode: 'additive',
        }""")
        page.click(".fcc-we-tab[data-mode='gross']")
        page.click("#fcc-we-set-default")
        stored = page.evaluate(
            "() => window.localStorage.getItem('fcc.weighEntry.defaultMode')"
        )
        assert stored == "gross", f"expected 'gross' persisted; got {stored!r}"
    finally:
        page.evaluate(
            "() => window.localStorage.removeItem('fcc.weighEntry.defaultMode')"
        )


def test_d_shortcut_sets_current_mode_as_default(page: Page) -> None:
    """13.9 — pressing D (with focus outside the value input) persists the
    current mode as the default. Mirrors the 'Set as default' click path."""
    _open_dashboard(page)
    page.evaluate(
        "() => window.localStorage.removeItem('fcc.weighEntry.defaultMode')"
    )
    try:
        _open_overlay_with(page, """{
            spool: { id: 101, initial_weight: 1000, used_weight: 575 },
            empty_spool_weight: 220,
            defaultMode: 'set_used',
        }""")
        # Move focus off the value input so D isn't typed into it.
        page.locator("#fcc-we-title").click()
        page.keyboard.press("d")
        stored = page.evaluate(
            "() => window.localStorage.getItem('fcc.weighEntry.defaultMode')"
        )
        assert stored == "set_used", f"expected 'set_used' persisted via D; got {stored!r}"
    finally:
        page.evaluate(
            "() => window.localStorage.removeItem('fcc.weighEntry.defaultMode')"
        )


def test_overlay_mounts_at_document_body(page: Page) -> None:
    """13.1 — Overlay always mounts at document.body so its z-index sits
    cleanly above every other stacking context. Mounting INSIDE a parent
    modal caused a Z-order regression where the overlay rendered below
    sibling modal chrome; the focusGuard installed in openModal handles
    the focus-trap problem that originally motivated the mount-inside
    approach."""
    _open_dashboard(page)
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        empty_spool_weight: 220,
    }""")
    parent_tag = page.evaluate(
        "() => document.getElementById('fcc-weight-entry-overlay').parentElement.tagName"
    )
    assert parent_tag == "BODY", (
        f"overlay parent was <{parent_tag}>; must be <BODY> for z-index sanity"
    )


def test_value_input_accepts_keystrokes_inside_bootstrap_modal(page: Page) -> None:
    """13.1 end-to-end — typing digits into the value input updates the
    field even when a Bootstrap modal is open. The focusGuard prevents
    Bootstrap's `_enforceFocus` from yanking focus off the overlay's input.
    Pre-fix the value input was uneditable from any Location Manager
    filament card (text key events never reached the input).
    """
    _open_dashboard(page)
    page.evaluate(
        """() => {
            const m = document.createElement('div');
            m.id = 'fcc-test-host-modal';
            m.className = 'modal show';
            m.setAttribute('tabindex', '-1');
            m.style.cssText = 'display:block; position:fixed; inset:0;';
            // Real Bootstrap modals install an enforceFocus listener that
            // refocuses the modal whenever focusin fires outside it. Stand
            // in for that listener so the test exercises the actual focusGuard
            // behavior, not just a plain DOM with no trap.
            const enforceFocus = (e) => {
                if (!m.contains(e.target)) m.focus();
            };
            m.tabIndex = -1;
            document.addEventListener('focusin', enforceFocus, false);
            m._cleanup = () => document.removeEventListener('focusin', enforceFocus, false);
            document.body.appendChild(m);
        }"""
    )
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        empty_spool_weight: 220,
        defaultMode: 'gross',
    }""")
    # Give the autofocus setTimeout(0) a tick.
    page.wait_for_timeout(50)
    page.keyboard.type("645")
    value = page.locator("#fcc-we-input").input_value()
    assert value == "645", f"expected input value '645', got {value!r}"
    # Cleanup
    page.evaluate(
        """() => {
            const m = document.getElementById('fcc-test-host-modal');
            if (m) { try { m._cleanup && m._cleanup(); } catch(_){} m.remove(); }
        }"""
    )


def test_value_input_has_autocomplete_off(page: Page) -> None:
    """Browser-autocomplete dropdowns of past entries (+25, -50, etc.) used
    to clutter the Quick-Weigh value input. Confirm autocomplete='off' (plus
    the related anti-autofill attributes) on the input element."""
    _open_dashboard(page)
    _open_overlay_with(page, """{
        spool: { id: 101, initial_weight: 1000, used_weight: 575 },
        empty_spool_weight: 220,
    }""")
    attrs = page.evaluate(
        """() => {
            const inp = document.getElementById('fcc-we-input');
            return {
                autocomplete: inp.getAttribute('autocomplete'),
                autocorrect: inp.getAttribute('autocorrect'),
                autocapitalize: inp.getAttribute('autocapitalize'),
                spellcheck: inp.getAttribute('spellcheck'),
            };
        }"""
    )
    assert attrs["autocomplete"] == "off", f"autocomplete must be 'off'; got {attrs['autocomplete']!r}"
    assert attrs["autocorrect"] == "off"
    assert attrs["autocapitalize"] == "off"
    assert attrs["spellcheck"] == "false"


def test_gross_mode_missing_tare_skip_submits_as_net(page: Page) -> None:
    """13.7 — In Gross mode with no resolvable empty weight, the prompt offers
    a Skip button that downgrades the entry to Net for this submission only.
    The typed value (645) is then treated as filament remaining, yielding
    used = initial - net = 1000 - 645 = 355. No tare is persisted (payload's
    empty_spool_weight stays null) and the reported mode reflects the
    downgrade so the caller doesn't think Gross math ran.
    """
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
    page.click("#fcc-we-save")
    page.wait_for_selector("#fcc-missing-empty-weight-overlay", state="visible", timeout=3_000)
    # The Skip button is rendered only when allowSkip is true (Gross-mode path).
    expect(page.locator("#fcc-missing-empty-weight-overlay-skip")).to_be_visible()
    page.click("#fcc-missing-empty-weight-overlay-skip")
    page.wait_for_selector("#fcc-weight-entry-overlay", state="detached", timeout=3_000)
    payload = page.evaluate("() => window._fccLastSubmit")
    assert payload is not None, "Skip should still submit the overlay"
    assert payload["mode"] == "net", (
        f"Skip should downgrade to Net for this submission; got mode={payload['mode']!r}"
    )
    assert payload["used_weight"] == 355, (
        f"used_weight should be initial - net = 1000 - 645 = 355; got {payload['used_weight']}"
    )
    assert payload["empty_spool_weight"] is None, (
        "Skip must not persist a tare to the spool"
    )


def test_post_archive_prompt_has_no_skip_button(page: Page) -> None:
    """13.7 sibling — the Skip button is gated on allowSkip=true. The
    post-archive flow (and any other caller that doesn't opt in) must still
    see only Cancel + Save so users can't accidentally bypass the tare
    requirement on a path where the tare actually gets persisted.
    """
    _open_dashboard(page)
    page.evaluate(
        """() => {
            window._fccTareRes = null;
            window.promptMissingEmptyWeight({
                vendor: 'CC3D', material: 'PLA', color: 'Crimson Red'
            }).then(v => { window._fccTareRes = v; });
        }"""
    )
    page.wait_for_selector("#fcc-missing-empty-weight-overlay", state="visible", timeout=3_000)
    expect(page.locator("#fcc-missing-empty-weight-overlay-skip")).to_have_count(0)
    expect(page.locator("#fcc-missing-empty-weight-overlay-cancel")).to_be_visible()
    expect(page.locator("#fcc-missing-empty-weight-overlay-save")).to_be_visible()
    page.click("#fcc-missing-empty-weight-overlay-cancel")


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
