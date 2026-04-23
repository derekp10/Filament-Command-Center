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
