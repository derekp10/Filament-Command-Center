"""
Regression tests for the buffer-shift-before-success bug.

Earlier code in handleSlotInteraction shifted the held spool out of the
buffer BEFORE the doAssign POST returned. That meant any failure path
(active-print prompt cancelled, network error, Spoolman 422, swap-cancel-
swap-continue race) silently lost the spool. The fix defers buffer
mutation until _doAssignFinalize's success branch.

These tests stub fetch responses so we can drive each path through
window.doAssign directly without needing a live Spoolman/printer.
"""
from __future__ import annotations

from playwright.sync_api import Page


def _setup_page_with_held_spool(page: Page, spool_id=42):
    """Open the dashboard, prime state.heldSpools with one spool, return."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.doAssign === 'function'")
    # Inject a known spool into the buffer state object.
    page.evaluate(
        "(sid) => { state.heldSpools = [{id: sid, display: '#' + sid, color: 'ff0000'}]; }",
        spool_id,
    )


def test_doassign_does_not_shift_buffer_on_failed_response(page: Page):
    """If /api/manage_contents returns failure, the spool must remain in
    the buffer (no eager shift)."""
    _setup_page_with_held_spool(page, 42)

    page.evaluate(
        """
        const orig = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u === '/api/manage_contents') {
                return new Response(JSON.stringify({status: 'error', msg: 'simulated failure'}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        """
    )

    # Use a non-toolhead target so doAssign skips the active-print pre-check
    # and goes straight to _doAssignFinalize.
    page.evaluate("() => { window.doAssign('LR-MDB-1', 42, 1, true); }")
    # Give the fetch a moment.
    page.wait_for_timeout(400)
    buffer_ids = page.evaluate("() => state.heldSpools.map(s => s.id)")
    assert 42 in buffer_ids, (
        "Spool 42 should still be in the buffer after a failed assign; "
        "the eager shift bug pulled it out before the POST returned."
    )


def test_doassign_shifts_buffer_only_on_success(page: Page):
    """Successful assign should remove the spool from the buffer."""
    _setup_page_with_held_spool(page, 43)

    page.evaluate(
        """
        const orig = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u === '/api/manage_contents') {
                return new Response(JSON.stringify({status: 'success'}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            // Stub get_contents so refreshManageView doesn't hammer the live API.
            if (u.startsWith('/api/get_contents')) {
                return new Response(JSON.stringify([]),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        """
    )

    page.evaluate("() => { window.doAssign('LR-MDB-1', 43, 1, true); }")
    page.wait_for_timeout(400)
    buffer_ids = page.evaluate("() => state.heldSpools.map(s => s.id)")
    assert 43 not in buffer_ids, "Spool 43 should be removed from the buffer on successful assign"


def test_doassign_swap_pushes_displaced_only_on_success(page: Page):
    """Swap path: the displaced item is provided via options.swapDisplaced.
    On a FAILED assign it must NOT land in the buffer (the eager push
    earlier left it stranded)."""
    _setup_page_with_held_spool(page, 44)

    page.evaluate(
        """
        const orig = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u === '/api/manage_contents') {
                return new Response(JSON.stringify({status: 'error', msg: 'fail'}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        """
    )

    # Simulate a Swap: spool 44 was held, slot already had spool 99.
    page.evaluate(
        """() => {
            window.doAssign('LR-MDB-1', 44, 1, true, {
                swapDisplaced: {id: 99, display: '#99', color: '00ff00'}
            });
        }"""
    )
    page.wait_for_timeout(400)
    buffer_ids = page.evaluate("() => state.heldSpools.map(s => s.id)")
    # Spool 44 stays (move failed), spool 99 must NOT be added (no success).
    assert 44 in buffer_ids
    assert 99 not in buffer_ids, "Displaced spool must not enter buffer when assign fails"



def test_doassign_swap_pushes_displaced_on_success(page: Page):
    """Swap path success: displaced item lands in buffer alongside removal
    of the assigned spool."""
    _setup_page_with_held_spool(page, 45)

    page.evaluate(
        """
        const orig = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u === '/api/manage_contents') {
                return new Response(JSON.stringify({status: 'success'}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (u.startsWith('/api/get_contents')) {
                return new Response(JSON.stringify([]),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        """
    )

    page.evaluate(
        """() => {
            window.doAssign('LR-MDB-1', 45, 1, true, {
                swapDisplaced: {id: 99, display: '#99', color: '00ff00'}
            });
        }"""
    )
    page.wait_for_timeout(400)
    buffer_ids = page.evaluate("() => state.heldSpools.map(s => s.id)")
    assert 45 not in buffer_ids, "Assigned spool should be removed from buffer on success"
    assert 99 in buffer_ids, "Displaced spool should land in buffer on success"


# ---------------------------------------------------------------------------
# Active-print confirm overlay: keyboard contract.
# ---------------------------------------------------------------------------
#
# The dialog focuses Continue Anyway by default so keyboard users get the
# standard "Enter activates the default action" UX. Cancel is one Tab away,
# Escape always cancels. Native <button> Enter-activation handles Enter on
# the focused button — no document-level keyHandler override.
#
# Earlier history: a document-capture keyHandler unconditionally mapped
# Enter → proceed, which meant Enter on a focused Cancel button still
# fired the assign. That bug was fixed by removing the Enter handler;
# this test set guards against the regression AND verifies the restored
# keyboard-accept UX still works.


def _setup_active_print_overlay(page: Page):
    """Open the active-print confirm overlay by stubbing the printer probe
    and manage_contents endpoint, then triggering doAssign on a fake
    toolhead. Exposes window.__assignHits as a counter.

    NOTE: _confirmActivePrintAssign mounts the overlay inside #manageModal
    (the Location Manager modal). In production the user has that modal
    open, so focus works fine. In this test we force #manageModal visible
    via inline display:block — otherwise focus on overlay descendants
    silently fails because focus can't land on a hidden ancestor's child.
    """
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.doAssign === 'function'")
    page.evaluate(
        """
        const orig = window.fetch;
        window.__assignHits = 0;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u.startsWith('/api/printer_state/')) {
                return new Response(JSON.stringify({
                    known: true, is_active: true, state: 'PRINTING', printer_name: 'TestPrinter'
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (u === '/api/manage_contents') {
                window.__assignHits += 1;
                return new Response(JSON.stringify({status: 'success'}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (u.startsWith('/api/get_contents')) {
                return new Response(JSON.stringify([]),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        state.heldSpools = [{id: 99, display: '#99', color: 'ff0000'}];
        state.allLocations = (state.allLocations || []).filter(l => l.LocationID !== 'XL-1');
        state.allLocations.push({LocationID: 'XL-1', Type: 'Tool Head', 'Max Spools': '1', Name: 'XL-1'});
        const m = document.getElementById('manage-loc-id');
        if (m) m.value = 'XL-1';
        // Force manageModal visible so the overlay's focus calls actually land.
        const mm = document.getElementById('manageModal');
        if (mm) { mm.style.display = 'block'; mm.style.visibility = 'visible'; }
        """
    )
    page.evaluate("() => window.doAssign('XL-1', 99, 1, true)")
    page.wait_for_selector("#fcc-apc-yes", state="attached", timeout=3_000)


def test_active_print_confirm_continue_focused_by_default(page: Page):
    """Restored keyboard-accept UX: Continue Anyway is focused on dialog
    open so keyboard users get the standard 'press Enter to accept the
    default action' behavior. Cancel is one Tab away."""
    _setup_active_print_overlay(page)
    focused_id = page.evaluate("() => document.activeElement && document.activeElement.id")
    assert focused_id == "fcc-apc-yes", (
        f"Expected #fcc-apc-yes (Continue Anyway) focused on dialog open; "
        f"got {focused_id!r}. Default focus drives Enter-to-accept."
    )


def test_active_print_confirm_enter_default_focus_assigns(page: Page):
    """Keyboard accept: with default focus on Continue, pressing Enter
    activates Continue and the assign goes through. This is the UX the
    user explicitly asked to restore."""
    _setup_active_print_overlay(page)
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    assigns = page.evaluate("() => window.__assignHits")
    assert assigns == 1, (
        f"Enter on the default-focused Continue button should fire ONE assign POST. "
        f"Saw {assigns}. Native <button> Enter-activation isn't firing onclick."
    )


def test_active_print_confirm_enter_on_focused_cancel_does_not_assign(page: Page):
    """Original-bug guard: Enter on a focused Cancel must NOT trigger the
    assign. After Tab moves focus to Cancel, Enter activates Cancel's
    onclick (cleanup), not the document-level proceed path that the old
    keyHandler implemented."""
    _setup_active_print_overlay(page)
    page.locator("#fcc-apc-no").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    assigns = page.evaluate("() => window.__assignHits")
    assert assigns == 0, (
        f"Enter on a focused Cancel button must NOT trigger manage_contents POST. "
        f"Saw {assigns} POST(s) — keyHandler is overriding native button activation."
    )
    overlay_count = page.locator("#fcc-active-print-confirm-overlay").count()
    assert overlay_count == 0, "Cancel via Enter on focused Cancel should close the overlay"


def test_active_print_confirm_escape_always_cancels(page: Page):
    """Escape unconditionally cancels regardless of which button is focused."""
    _setup_active_print_overlay(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    assigns = page.evaluate("() => window.__assignHits")
    assert assigns == 0
    overlay_count = page.locator("#fcc-active-print-confirm-overlay").count()
    assert overlay_count == 0
