"""
Group 21 — frontend regression tests (card / modal + buffer load-unload).

Covers the JS-side fixes that don't have a natural home in an existing suite:
  21.4 — queueing a label from the spool-details modal must keep it OPEN.
  21.5 — double-clicking a force-location entry commits the override.
  21.6 — a spool just assigned OUT of the buffer must not be resurrected by a
         stale /api/state/buffer heartbeat payload.

These stub fetch so they run against the live container without mutating data.
"""
from __future__ import annotations

from playwright.sync_api import Page


# ---------------------------------------------------------------------------
# 21.6 — buffer "recently assigned out" guard
# ---------------------------------------------------------------------------

def _install_buffer_stub(page: Page, stale_ids):
    """Stub /api/state/buffer GET to return a stale payload and swallow POSTs."""
    stale = [{"id": i, "display": "#%d" % i, "color": "888888"} for i in stale_ids]
    page.evaluate(
        """
        (stale) => {
            const orig = window.fetch;
            window.__persisted = null;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u === '/api/state/buffer' && (!opts || (opts.method || 'GET') === 'GET')) {
                    return new Response(JSON.stringify(stale),
                        {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                if (u === '/api/state/buffer' && opts && opts.method === 'POST') {
                    window.__persisted = JSON.parse(opts.body).buffer.map(s => s.id);
                    return new Response('{}', {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                if (u.startsWith('/api/spools/refresh')) {
                    return new Response('{}', {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                return orig(url, opts);
            };
        }
        """,
        stale,
    )


def _prime_buffer_dashboard(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof loadBuffer === 'function' && typeof state === 'object'")


def test_assigned_out_spool_not_resurrected_by_stale_pulse(page: Page):
    """21.6 — server still lists #255, but we just assigned it out. A
    loadBuffer sync past the grace window must NOT add it back."""
    _prime_buffer_dashboard(page)
    _install_buffer_stub(page, [255])
    page.evaluate(
        """() => {
            state.heldSpools = [];                         // assigned out locally
            window._recentlyAssignedOut.set('255', Date.now());
            window.lastLocalBufferChange = 0;              // grace window lapsed
            window.isBufferSyncing = false;
            loadBuffer();
        }"""
    )
    page.wait_for_timeout(600)
    ids = page.evaluate("() => state.heldSpools.map(s => s.id)")
    assert 255 not in ids, f"assigned-out #255 was resurrected by a stale pulse: {ids}"
    # And the corrected (empty) buffer was re-asserted to the server.
    assert page.evaluate("() => window.__persisted") == [], "stale server should be re-corrected via persist"


def test_unmarked_spool_still_syncs_in_from_server(page: Page):
    """21.6 control — a spool NOT assigned out (e.g. added on another tab)
    must still sync into the buffer; the guard must not over-suppress."""
    _prime_buffer_dashboard(page)
    _install_buffer_stub(page, [254])
    page.evaluate(
        """() => {
            state.heldSpools = [];
            window._recentlyAssignedOut.clear();
            window.lastLocalBufferChange = 0;
            window.isBufferSyncing = false;
            loadBuffer();
        }"""
    )
    page.wait_for_timeout(600)
    ids = page.evaluate("() => state.heldSpools.map(s => s.id)")
    assert 254 in ids, f"unmarked #254 should have synced in from the server: {ids}"


def test_rebuffering_clears_assigned_out_mark(page: Page):
    """21.6 — re-picking a spool back into the buffer clears its suppression
    so it isn't filtered out on the next sync."""
    _prime_buffer_dashboard(page)
    page.evaluate(
        """() => {
            window._recentlyAssignedOut.set('255', Date.now());
            state.heldSpools = [{id: 255, display: '#255', color: '888888'}];
            renderBuffer();
        }"""
    )
    has_mark = page.evaluate("() => window._recentlyAssignedOut.has('255')")
    assert not has_mark, "re-buffering #255 should have cleared its assigned-out mark"


# ---------------------------------------------------------------------------
# 21.4 — queue-label keeps the spool-details modal open
# ---------------------------------------------------------------------------

def test_queue_label_keeps_spool_details_modal_open(page: Page):
    """21.4 — clicking 'Queue Label' on the spool-details modal queues the
    label and leaves the modal open (was calling spoolModal.hide())."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#spoolModal", state="attached")
    page.wait_for_function("typeof modals === 'object' && modals.spoolModal")
    page.evaluate(
        """() => {
            window.__queued = [];
            window.addToQueue = (item) => window.__queued.push(item);
            window.showToast = () => {};
            document.getElementById('detail-id').innerText = '4242';
            document.getElementById('detail-color-name').innerText = 'Test Color';
            modals.spoolModal.show();
        }"""
    )
    page.wait_for_selector("#spoolModal.show", timeout=4000)
    page.eval_on_selector("#btn-print-action", "el => el.click()")
    page.wait_for_timeout(400)
    assert page.evaluate("() => document.getElementById('spoolModal').classList.contains('show')"), \
        "spool-details modal should stay OPEN after queueing a label (21.4)"
    assert page.evaluate("() => window.__queued.length") == 1, "the label should have been queued"


# ---------------------------------------------------------------------------
# 21.5 — double-click a force-location entry commits the override
# ---------------------------------------------------------------------------

def test_dblclick_force_location_entry_commits(page: Page):
    """21.5 — double-clicking a location row in the Force-Location dialog
    commits that override in one gesture (no separate Force-Move click)."""
    page.goto("http://localhost:8000")
    page.wait_for_function("typeof window.promptEditLocation === 'function'")
    page.evaluate(
        """() => {
            window.__forced = null;
            const orig = window.fetch;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u === '/api/locations') {
                    return new Response(JSON.stringify([
                        {LocationID: 'PM-DB-1', Name: 'Dry Box', Type: 'Dryer Box', 'Max Spools': '1'},
                    ]), {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                if (u === '/api/manage_contents') {
                    window.__forced = JSON.parse(opts.body);
                    return new Response(JSON.stringify({status: 'success'}),
                        {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                return orig(url, opts);
            };
            window.showToast = () => {};
            window.setProcessing = () => {};
            window.openSpoolDetails = () => {};
            window.promptEditLocation(777, 'Unassigned');
        }"""
    )
    # Wait for the Swal list to render, then double-click the PM-DB-1 row.
    page.wait_for_selector(".swal-loc-item[data-id='PM-DB-1']", state="attached", timeout=4000)
    page.dispatch_event(".swal-loc-item[data-id='PM-DB-1']", "dblclick")
    page.wait_for_function("() => window.__forced !== null", timeout=4000)
    forced = page.evaluate("() => window.__forced")
    assert forced["location"] == "PM-DB-1", f"dblclick should commit the PM-DB-1 override: {forced}"
    assert forced["spool_id"] == 777
