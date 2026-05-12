"""
Tests for the canonical mountOverlay() helper (Group 15).

Exercises the behaviors documented in modules/overlay_mount.js:
  - Mount target is document.body (lesson from 13.1 mount-inside-modal revert)
  - Z-index ladder: STANDARD=20000 / CONFIRM=20100
  - Focus guard defeats Bootstrap's _enforceFocus
  - Host-close cascade (hidden.bs.modal / hidden.bs.offcanvas) removes overlay
  - Idempotent cleanup
  - Occlusion (pointer-events:none) applied + restored
  - Backdrop click dismiss
  - Re-mount with same id tears down prior handle
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _open_dashboard(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.mountOverlay === 'function' && "
        "typeof window.OVERLAY_Z === 'object'",
        timeout=5_000,
    )


def test_mount_target_is_document_body(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window.mountOverlay({
            id: 'fcc-test-mt',
            content: '<div class="panel">hello</div>',
        });
    }""")
    parent_tag = page.evaluate(
        "() => document.getElementById('fcc-test-mt').parentElement.tagName"
    )
    assert parent_tag == "BODY", "overlays must mount at document.body, not modal subtree"


def test_z_index_ladder_standard_and_confirm(page: Page) -> None:
    _open_dashboard(page)
    z_standard = page.evaluate("() => window.OVERLAY_Z.standard")
    z_confirm = page.evaluate("() => window.OVERLAY_Z.confirm")
    assert z_standard == 20000
    assert z_confirm == 20100
    assert z_confirm > z_standard

    page.evaluate("""() => {
        window.mountOverlay({ id: 'fcc-test-zs', content: '<div>std</div>' });
        window.mountOverlay({ id: 'fcc-test-zc', content: '<div>cnf</div>', tier: 'confirm' });
    }""")
    zs = page.evaluate("() => getComputedStyle(document.getElementById('fcc-test-zs')).zIndex")
    zc = page.evaluate("() => getComputedStyle(document.getElementById('fcc-test-zc')).zIndex")
    assert int(zs) == 20000
    assert int(zc) == 20100


def test_cleanup_removes_overlay_and_is_idempotent(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window._fccHandle = window.mountOverlay({
            id: 'fcc-test-cleanup',
            content: '<div>x</div>',
        });
    }""")
    expect(page.locator("#fcc-test-cleanup")).to_be_visible()

    page.evaluate("() => window._fccHandle.cleanup()")
    expect(page.locator("#fcc-test-cleanup")).to_have_count(0)

    # Second cleanup is a no-op (does not throw).
    err = page.evaluate("""() => {
        try { window._fccHandle.cleanup(); return null; }
        catch (e) { return String(e); }
    }""")
    assert err is None


def test_remount_with_same_id_tears_down_prior(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window.mountOverlay({ id: 'fcc-test-remount', content: '<div class="v1">first</div>' });
        window.mountOverlay({ id: 'fcc-test-remount', content: '<div class="v2">second</div>' });
    }""")
    # Only one overlay with that id exists; it's the second one.
    assert page.locator("#fcc-test-remount").count() == 1
    expect(page.locator("#fcc-test-remount .v2")).to_be_visible()
    expect(page.locator("#fcc-test-remount .v1")).to_have_count(0)


def test_escape_key_calls_on_escape(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window._fccEscFired = false;
        window.mountOverlay({
            id: 'fcc-test-esc',
            content: '<div>x</div>',
            onEscape: () => { window._fccEscFired = true; window.closeOverlay('fcc-test-esc'); },
        });
    }""")
    page.keyboard.press("Escape")
    page.wait_for_function("() => window._fccEscFired === true", timeout=2_000)
    expect(page.locator("#fcc-test-esc")).to_have_count(0)


def test_escape_default_behavior_cleans_up(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window.mountOverlay({ id: 'fcc-test-esc-def', content: '<div>x</div>' });
    }""")
    expect(page.locator("#fcc-test-esc-def")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-test-esc-def")).to_have_count(0)


def test_backdrop_click_dismiss(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window.mountOverlay({
            id: 'fcc-test-bd',
            content: '<div style="width:100px;height:100px;background:#fff;">panel</div>',
            backdropDismiss: true,
        });
    }""")
    # Click the backdrop (top-left corner is outside the white panel).
    page.locator("#fcc-test-bd").click(position={"x": 5, "y": 5})
    expect(page.locator("#fcc-test-bd")).to_have_count(0)


def test_focus_guard_neutralizes_external_focusin(page: Page) -> None:
    """Capture-phase focusin listener should swallow events targeting the overlay
    subtree so an outer Bootstrap modal's _enforceFocus can't steal focus."""
    _open_dashboard(page)
    page.evaluate("""() => {
        window._fccBubbleFired = false;
        // A bubble-phase listener stands in for Bootstrap's _enforceFocus.
        window._fccBubbleListener = () => { window._fccBubbleFired = true; };
        document.addEventListener('focusin', window._fccBubbleListener, false);
        window.mountOverlay({
            id: 'fcc-test-fg',
            content: '<input id="fcc-test-fg-input" />',
            focusGuard: true,
            initialFocus: '#fcc-test-fg-input',
        });
    }""")
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.id === 'fcc-test-fg-input'",
        timeout=2_000,
    )
    fired = page.evaluate("() => window._fccBubbleFired")
    assert fired is False, "focusGuard should stop the bubble-phase listener from firing"

    # Cleanup
    page.evaluate("""() => {
        document.removeEventListener('focusin', window._fccBubbleListener, false);
        window.closeOverlay('fcc-test-fg');
    }""")


def test_focus_guard_disabled_allows_external_focusin(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window._fccBubbleFired2 = false;
        window._fccBubbleListener2 = () => { window._fccBubbleFired2 = true; };
        document.addEventListener('focusin', window._fccBubbleListener2, false);
        window.mountOverlay({
            id: 'fcc-test-fg2',
            content: '<input id="fcc-test-fg2-input" />',
            focusGuard: false,
            initialFocus: '#fcc-test-fg2-input',
        });
    }""")
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.id === 'fcc-test-fg2-input'",
        timeout=2_000,
    )
    fired = page.evaluate("() => window._fccBubbleFired2")
    assert fired is True, "with focusGuard:false, external focusin listeners should fire normally"

    page.evaluate("""() => {
        document.removeEventListener('focusin', window._fccBubbleListener2, false);
        window.closeOverlay('fcc-test-fg2');
    }""")


def test_host_close_cascade_removes_overlay(page: Page) -> None:
    """When a host Bootstrap modal is hidden, the overlay must cleanup automatically."""
    _open_dashboard(page)
    page.evaluate("""() => {
        // Create a stub Bootstrap-like modal element.
        const modal = document.createElement('div');
        modal.id = 'fcc-test-host';
        document.body.appendChild(modal);
        window._fccHost = modal;
        window.mountOverlay({
            id: 'fcc-test-cascade',
            content: '<div>x</div>',
            host: modal,
        });
    }""")
    expect(page.locator("#fcc-test-cascade")).to_be_visible()

    page.evaluate("""() => {
        window._fccHost.dispatchEvent(new Event('hidden.bs.modal'));
    }""")
    expect(page.locator("#fcc-test-cascade")).to_have_count(0)

    page.evaluate("() => { window._fccHost.remove(); }")


def test_occlusion_applies_and_restores_pointer_events(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        // Inject a target select with a known starting pointer-events value.
        const sel = document.createElement('select');
        sel.id = 'fcc-test-occlude-target';
        sel.style.pointerEvents = 'auto';
        document.body.appendChild(sel);
        window.mountOverlay({
            id: 'fcc-test-occlude',
            content: '<div>x</div>',
            occlude: '#fcc-test-occlude-target',
        });
    }""")
    pe_open = page.evaluate(
        "() => document.getElementById('fcc-test-occlude-target').style.pointerEvents"
    )
    assert pe_open == "none"

    page.evaluate("() => window.closeOverlay('fcc-test-occlude')")
    pe_closed = page.evaluate(
        "() => document.getElementById('fcc-test-occlude-target').style.pointerEvents"
    )
    assert pe_closed == "auto", "occlusion must restore the previous pointer-events value"
    page.evaluate("() => document.getElementById('fcc-test-occlude-target').remove()")


def test_set_content_replaces_panel(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window._fccH = window.mountOverlay({
            id: 'fcc-test-setc',
            content: '<div class="orig">orig</div>',
        });
    }""")
    expect(page.locator("#fcc-test-setc .orig")).to_be_visible()
    page.evaluate("() => window._fccH.setContent('<div class=\"upd\">updated</div>')")
    expect(page.locator("#fcc-test-setc .orig")).to_have_count(0)
    expect(page.locator("#fcc-test-setc .upd")).to_be_visible()
    page.evaluate("() => window.closeOverlay('fcc-test-setc')")


def test_initial_focus_selector(page: Page) -> None:
    _open_dashboard(page)
    page.evaluate("""() => {
        window.mountOverlay({
            id: 'fcc-test-if',
            content: '<input id="fcc-test-if-input" />',
            initialFocus: '#fcc-test-if-input',
        });
    }""")
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.id === 'fcc-test-if-input'",
        timeout=2_000,
    )
    page.evaluate("() => window.closeOverlay('fcc-test-if')")


def test_missing_id_throws(page: Page) -> None:
    _open_dashboard(page)
    err = page.evaluate("""() => {
        try { window.mountOverlay({ content: 'x' }); return null; }
        catch (e) { return String(e.message || e); }
    }""")
    assert err is not None and "id" in err.lower()
