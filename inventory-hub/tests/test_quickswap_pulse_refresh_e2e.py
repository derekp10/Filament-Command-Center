"""L352 — the Quick-Swap grid now refreshes its live spool weights on the
dashboard heartbeat (inventory:sync-pulse), so a weight changed elsewhere
(weigh-out / filabridge deduct / Prusament correction) no longer shows stale
while a toolhead manage view stays open.

Guards under test:
  - idle (no toolhead/printer manage view open) → the pulse is a no-op,
  - silent mode is plumbed end-to-end without throwing,
  - the refresh is SKIPPED while the user is keyboard-navigating inside the
    grid (focus lives in the grid) so it never yanks focus mid-interaction.

The quickswap DOM (#manage-quickswap-section / #quickswap-grid) is static in the
manage-modal template, so we drive window.renderQuickSwapSection directly
instead of needing a fully bound dryer-box slot in dev data.
"""
from __future__ import annotations

from playwright.sync_api import Page


def _goto(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.renderQuickSwapSection === 'function'", timeout=5_000)


def _install_spy(page: Page) -> None:
    page.evaluate(
        """() => {
            window.__qsSilentCalls = 0;
            const orig = window.renderQuickSwapSection;
            window.renderQuickSwapSection = function(loc, opts) {
                if (opts && opts.silent) window.__qsSilentCalls++;
                return orig.apply(this, arguments);
            };
        }"""
    )


def test_sync_pulse_idle_is_a_noop(page: Page):
    """With no toolhead/printer manage view open (currentLoc null), the pulse
    must not invoke a silent quickswap render."""
    _goto(page)
    _install_spy(page)
    page.evaluate("document.dispatchEvent(new CustomEvent('inventory:sync-pulse'))")
    assert page.evaluate("window.__qsSilentCalls") == 0


def test_silent_render_is_plumbed_and_safe(page: Page):
    """Calling the function in silent mode with a toolhead loc must not throw
    (the opts param is accepted and a non-resolving loc is handled gracefully)."""
    _goto(page)
    # If this threw synchronously, page.evaluate would raise.
    page.evaluate(
        "window.renderQuickSwapSection({Type:'Tool Head', LocationID:'ZZ-TH-TEST'}, {silent:true})"
    )
    # Sanity: the call returns control (fire-and-forget) and the page is alive.
    assert page.evaluate("typeof window.renderQuickSwapSection") == "function"


def test_sync_pulse_skips_while_grid_focused(page: Page):
    """The refresh must NOT fire while focus is inside the grid (the user is
    mid keyboard-navigation) — re-rendering would yank their focus."""
    _goto(page)
    # Set the module-private currentLoc by rendering a toolhead view, and force
    # the manage modal + section + grid visible so the grid is focusable.
    page.evaluate(
        """() => {
            window.renderQuickSwapSection({Type:'Tool Head', LocationID:'ZZ-TH-TEST'});
            const mm = document.getElementById('manageModal');
            if (mm) { mm.style.display = 'block'; mm.classList.add('show'); }
            const sec = document.getElementById('manage-quickswap-section');
            if (sec) sec.style.display = 'block';
        }"""
    )
    _install_spy(page)

    # Focus the grid → simulates in-progress keyboard nav.
    page.evaluate(
        """() => {
            const grid = document.getElementById('quickswap-grid');
            grid.tabIndex = 0;
            grid.focus();
        }"""
    )
    assert page.evaluate("document.getElementById('quickswap-grid').contains(document.activeElement)") is True

    page.evaluate("document.dispatchEvent(new CustomEvent('inventory:sync-pulse'))")
    assert page.evaluate("window.__qsSilentCalls") == 0, "pulse refreshed the grid while it was focused"

    # Blur out of the grid → the pulse now refreshes.
    page.evaluate("if (document.activeElement && document.activeElement.blur) document.activeElement.blur();")
    page.evaluate("document.dispatchEvent(new CustomEvent('inventory:sync-pulse'))")
    assert page.evaluate("window.__qsSilentCalls") >= 1, "pulse failed to refresh after focus left the grid"
