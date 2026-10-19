"""Group 42 adversarial review (frontend-1): eject mode survives the eject's own
confirm.

The page-wide `show.bs.modal` listener (templates/components/scripts.html) turns
the deck modes off whenever any modal opens. A gating dialog (#confirmModal /
#safetyModal / #actionModal) is a step of the action that raised it, though: an
eject-mode toolhead-label eject that asked "unassign?" or "printing?" turned
eject mode off with no toast, so the next toolhead label assigned the buffer to
that head (Smart Load unloading its spool) instead of ejecting it (42.5b).

Runs in a real browser because the listener lives in the page template.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

import conftest

READY = ("typeof state !== 'undefined' && typeof modals !== 'undefined' && !!modals.confirmModal"
         " && typeof window.resetCommandModes === 'function' && typeof closeModal === 'function'")


def _boot(page: Page, api_base_url: str) -> None:
    conftest.quiet_heartbeat(page)
    page.goto(api_base_url + "/", wait_until="domcontentloaded")
    page.wait_for_function(READY, timeout=20_000)


@pytest.mark.usefixtures("require_server")
def test_a_gating_confirm_keeps_eject_mode_on(page: Page, api_base_url: str):
    _boot(page, api_base_url)
    page.evaluate("() => { state.ejectMode = true; state.dropMode = false; }")
    page.evaluate("() => requestConfirmation('Eject mode probe?', () => {})")
    page.wait_for_function("document.getElementById('confirmModal').classList.contains('show')", timeout=5_000)
    assert page.evaluate("state.ejectMode") is True, "the eject's own confirm turned eject mode off"
    conftest.wait_modal_settled(page, "confirmModal")
    page.evaluate("closeModal('confirmModal')")
    conftest.wait_modal_settled(page, "confirmModal")
    assert page.evaluate("state.ejectMode") is True


@pytest.mark.usefixtures("require_server")
def test_any_other_modal_still_turns_the_deck_modes_off(page: Page, api_base_url: str):
    """Control (passes before the fix too): opening another screen ends the mode."""
    _boot(page, api_base_url)
    page.evaluate("""() => {
        state.ejectMode = true;
        const el = document.createElement('div');
        el.id = 'fcc-test-plain-modal';
        document.body.appendChild(el);
        el.dispatchEvent(new Event('show.bs.modal', { bubbles: true }));
        el.remove();
    }""")
    assert page.evaluate("state.ejectMode") is False
