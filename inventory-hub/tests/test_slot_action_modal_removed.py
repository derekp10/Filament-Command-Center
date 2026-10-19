"""
Task 3 — Slot Actions Modal removed (Feature-Buglist line 55).

Clicking a filled loc_grid slot card (with the buffer empty) used to pop a
3-option modal (Pick Up / Eject / Details). All three are already on the
slot card as explicit buttons, so the modal was redundant. Clicking now
defaults to Pick Up, mirroring the new unslotted-card behavior (Task 1).

This test drives `window.handleSlotInteraction` directly with a seeded
currentGrid so it doesn't depend on a specific real spool living in a
specific slot in dev.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


def _wait_ready(page: Page, base_url: str) -> None:
    """handleSlotInteraction needs #manage-loc-id, state.currentGrid and, since
    2026-10-14, the Location Manager open (a CMD:SLOT scan with it closed moved
    the buffered spool to Unassigned). The tests mark #manageModal shown without
    opening it for real, and restore it."""
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof window.handleSlotInteraction === 'function' "
        "&& Array.isArray(state?.heldSpools) "
        "&& !!document.getElementById('manage-loc-id')",
        timeout=10000,
    )


@pytest.mark.usefixtures("require_server")
def test_filled_slot_click_picks_up_directly_no_modal(page: Page, base_url: str):
    _wait_ready(page, base_url)

    result = page.evaluate(
        """() => {
            const originalGrid = state.currentGrid;
            const originalHeld = state.heldSpools.slice();

            // Seed a filled slot for the interaction handler.
            state.currentGrid = { 3: { id: 77001, display: 'PROBE', color: 'abcdef' } };
            state.heldSpools = [];

            // Point manage-loc-id at something safe so locId lookup doesn't crash.
            const locIdEl = document.getElementById('manage-loc-id');
            const savedLocId = locIdEl ? locIdEl.value : '';
            if (locIdEl) locIdEl.value = 'PROBE-LOC';
            // A slot acts only while the Location Manager is open (2026-10-14).
            const mm = document.getElementById('manageModal');
            const wasShown = mm.classList.contains('show');
            mm.classList.add('show');

            // Call the interaction handler directly (simulates card-body click).
            window.handleSlotInteraction(3);
            if (!wasShown) mm.classList.remove('show');

            const pickedUp = state.heldSpools.some(s => s.id === 77001);
            const actionModalEl = document.getElementById('actionModal');
            const modalShown = !!(actionModalEl && actionModalEl.classList.contains('show'));

            // Restore.
            state.currentGrid = originalGrid;
            state.heldSpools = originalHeld;
            if (locIdEl) locIdEl.value = savedLocId;
            if (window.renderBuffer) window.renderBuffer();

            return { pickedUp, modalShown };
        }"""
    )

    assert result["pickedUp"] is True, (
        f"Clicking a filled slot with empty buffer should Pick Up directly. Got: {result}"
    )
    assert result["modalShown"] is False, (
        f"The old 3-option Slot Action modal must NOT show. Got: {result}"
    )


@pytest.mark.usefixtures("require_server")
def test_filled_slot_with_occupied_buffer_still_prompts_swap(page: Page, base_url: str):
    """Regression guard: the Swap/Overwrite/Cancel chooser is a separate,
    genuinely-destructive modal — it must still fire when both buffer and
    slot are occupied."""
    _wait_ready(page, base_url)

    result = page.evaluate(
        """async () => {
            const originalGrid = state.currentGrid;
            const originalHeld = state.heldSpools.slice();

            state.currentGrid = { 5: { id: 77002, display: 'SLOT-OCCUPANT', color: '112233' } };
            state.heldSpools = [{ id: 88002, display: 'BUFFERED', color: '445566' }];

            const locIdEl = document.getElementById('manage-loc-id');
            const savedLocId = locIdEl ? locIdEl.value : '';
            if (locIdEl) locIdEl.value = 'PROBE-LOC';
            // A slot acts only while the Location Manager is open (2026-10-14).
            const mm = document.getElementById('manageModal');
            const wasShown = mm.classList.contains('show');
            mm.classList.add('show');

            window.handleSlotInteraction(5);
            if (!wasShown) mm.classList.remove('show');
            // promptAction is synchronous DOM manipulation + modal.show(); give it a tick.
            await new Promise(r => setTimeout(r, 150));

            const actionModalEl = document.getElementById('actionModal');
            const modalShown = !!(actionModalEl && actionModalEl.classList.contains('show'));
            const title = (document.getElementById('action-title') || {}).innerText || '';

            // Close the modal cleanly.
            if (window.closeModal) window.closeModal('actionModal');
            await new Promise(r => setTimeout(r, 150));

            // Restore.
            state.currentGrid = originalGrid;
            state.heldSpools = originalHeld;
            if (locIdEl) locIdEl.value = savedLocId;
            if (window.renderBuffer) window.renderBuffer();

            return { modalShown, title };
        }"""
    )

    # The promptAction helper writes the title into #action-title before calling
    # modal.show(). A "Slot Occupied" title proves the Swap/Overwrite chooser
    # path was taken — that's the behavior we need to preserve.
    assert "occupied" in result["title"].lower(), (
        f"Swap/Overwrite prompt should still fire when both slot and buffer "
        f"are occupied (expected 'Slot Occupied' title). Got: {result}"
    )
