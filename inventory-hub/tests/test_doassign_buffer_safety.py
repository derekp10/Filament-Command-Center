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


def test_active_print_confirm_enter_on_focused_cancel_does_not_assign(page: Page):
    """Regression: user-reported bug where hitting Enter on the active-print
    confirm overlay — which focuses Cancel by default — would fire the
    Continue path instead of Cancel. The overlay's keyHandler was
    unconditionally mapping Enter → proceed, bypassing whichever button
    actually had focus. Barcode scanners that emit an Enter suffix hit the
    same trap.

    The fix relies on native <button> Enter-activation: Enter on a focused
    button fires that button's click, full stop. No override."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.doAssign === 'function'")

    # Stub /api/printer_state (frontend probe) to return ACTIVE so doAssign
    # opens the inline confirm overlay directly. Seed state.allLocations so
    # doAssign recognizes XL-1 as a toolhead-target and fires the probe.
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
        // Also seed the manage-loc-id input so doAssign's refresh tries to
        // refresh the right location (harmless otherwise).
        const m = document.getElementById('manage-loc-id');
        if (m) m.value = 'XL-1';
        """
    )
    # Trigger doAssign. Active-print probe resolves → overlay mounts.
    page.evaluate("() => window.doAssign('XL-1', 99, 1, true)")
    page.wait_for_selector("#fcc-apc-no", state="attached", timeout=3_000)
    # Cancel button is focused by default. Dispatch Enter and verify the
    # assign endpoint is NOT hit.
    page.evaluate(
        """() => {
            document.getElementById('fcc-apc-no').focus();
            // Fire Enter via keydown dispatch so the document-level capture
            // handler sees it (mirrors what a barcode scanner / hardware
            // Enter would produce).
            document.getElementById('fcc-apc-no').dispatchEvent(
                new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true})
            );
        }"""
    )
    page.wait_for_timeout(400)
    assigns = page.evaluate("() => window.__assignHits")
    assert assigns == 0, (
        f"Enter on the focused Cancel button should NOT trigger a manage_contents "
        f"POST. Saw {assigns} POST(s). This is the user-reported 'cancel still "
        f"assigns' bug — keyHandler was mapping Enter unconditionally to proceed."
    )


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
