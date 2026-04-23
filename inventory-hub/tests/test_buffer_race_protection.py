"""
Buffer race protection tests — covers Feature-Buglist line 16.

The race: when a user types/scans a spool ID into the dashboard input *during*
an in-flight loadBuffer, the persist call is gated and the subsequent
loadBuffer .then overwrites the local heldSpools with stale server state,
silently dropping the user's add.

Fix in inv_cmd.js:
  - renderBuffer bumps `window.lastLocalBufferChange` and queues
    `window.pendingPersist` when a user mutation lands during a sync.
  - loadBuffer skips its server-overwrite if the local change is < 3s old.
  - loadBuffer flushes any queued persist once the sync window releases.

These tests probe each of those guarantees directly via page.evaluate, which
keeps them fast and deterministic without needing to seed real spools or
race actual network timing.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


def _wait_app_ready(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof window.processScan === 'function' && typeof loadBuffer === 'function' && Array.isArray(state?.heldSpools)",
        timeout=10000,
    )
    # Settle: let any startup loadBuffer/persistBuffer cycle complete.
    page.wait_for_timeout(300)


@pytest.mark.usefixtures("require_server")
def test_render_during_sync_marks_dirty_and_queues_persist(page: Page, base_url: str):
    """Mutating state during a sync (isBufferSyncing=true) bumps the timestamp
    and sets pendingPersist instead of silently dropping the persist."""
    _wait_app_ready(page, base_url)

    result = page.evaluate(
        """() => {
            // Reset gates and simulate an in-flight sync.
            window.lastLocalBufferChange = 0;
            window.pendingPersist = false;
            window.isBufferSyncing = true;
            window.suppressBufferDirty = false;

            const before = window.lastLocalBufferChange;
            // User adds a spool — renderBuffer hits the "syncing" branch.
            state.heldSpools = [{
                id: 99991, type: 'spool', display: 'PROBE', color: 'ff00ff',
                remaining_weight: 100, details: 'Probe'
            }];
            window.renderBuffer();

            const after = window.lastLocalBufferChange;
            const queued = window.pendingPersist;

            // Cleanup: drop the probe and release the sync gate.
            state.heldSpools = [];
            window.isBufferSyncing = false;
            window.pendingPersist = false;
            window.lastLocalBufferChange = 0;

            return { before, after, queued };
        }"""
    )

    assert result["before"] == 0, "Sanity: timestamp started at 0"
    assert result["after"] > 0, (
        "renderBuffer should bump lastLocalBufferChange when a user mutation "
        f"lands during a sync. Got: {result}"
    )
    assert result["queued"] is True, (
        "renderBuffer should queue pendingPersist when sync gate is held. "
        f"Got: {result}"
    )


@pytest.mark.usefixtures("require_server")
def test_loadbuffer_skips_overwrite_when_local_change_is_fresh(page: Page, base_url: str):
    """If lastLocalBufferChange is < 3s ago, loadBuffer must NOT overwrite
    state.heldSpools with stale server data."""
    _wait_app_ready(page, base_url)

    # Stub fetch so /api/state/buffer GET returns a deliberately-different payload.
    # POST is counted so we can verify the queued persist actually flushed.
    result = page.evaluate(
        """async () => {
            // Snapshot to restore later.
            const originalFetch = window.fetch;
            const originalHeld = state.heldSpools.slice();
            let postCount = 0;

            // Pre-state: we have a "user-added" spool locally, fresh timestamp.
            state.heldSpools = [{
                id: 88881, type: 'spool', display: 'LOCAL', color: '00ff00',
                remaining_weight: 200, details: 'Local'
            }];
            window.lastLocalBufferChange = Date.now();
            window.pendingPersist = false;
            window.isBufferSyncing = false;

            // Server replies with a different (stale) buffer.
            window.fetch = function(url, opts) {
                if (typeof url === 'string' && url.includes('/api/state/buffer')) {
                    if (opts && opts.method === 'POST') {
                        postCount += 1;
                        return Promise.resolve(new Response('{}', { status: 200 }));
                    }
                    return Promise.resolve(new Response(
                        JSON.stringify([{
                            id: 77770, type: 'spool', display: 'STALE',
                            color: 'ff0000', remaining_weight: 0, details: 'Stale'
                        }]),
                        { status: 200, headers: { 'Content-Type': 'application/json' } }
                    ));
                }
                return originalFetch.call(window, url, opts);
            };

            // Trigger a sync.
            loadBuffer();
            // Give the .then + the queued persist time to resolve.
            await new Promise(r => setTimeout(r, 250));

            const ids = state.heldSpools.map(s => s.id);

            // Restore.
            window.fetch = originalFetch;
            state.heldSpools = originalHeld;
            window.lastLocalBufferChange = 0;
            window.pendingPersist = false;
            window.isBufferSyncing = false;
            if (window.renderBuffer) window.renderBuffer();

            return { ids, postCount };
        }"""
    )

    assert 88881 in result["ids"], (
        f"Local item (id 88881) should survive the stale server payload. Got ids: {result['ids']}"
    )
    assert 77770 not in result["ids"], (
        f"Stale server payload (id 77770) should NOT have overwritten the local buffer. Got ids: {result['ids']}"
    )
    assert result["postCount"] >= 1, (
        f"persistBuffer should have flushed after the sync resolved. POSTs seen: {result['postCount']}"
    )


@pytest.mark.usefixtures("require_server")
def test_loadbuffer_overwrites_when_no_recent_local_change(page: Page, base_url: str):
    """Outside the 3s grace window, server state DOES win — multi-tab sync
    must keep working. Verifies we didn't make the buffer stick forever."""
    _wait_app_ready(page, base_url)

    result = page.evaluate(
        """async () => {
            const originalFetch = window.fetch;
            const originalHeld = state.heldSpools.slice();

            // Old local state — simulate a tab idle for a while.
            state.heldSpools = [{
                id: 66660, type: 'spool', display: 'OLD', color: '0000ff',
                remaining_weight: 100, details: 'Old'
            }];
            window.lastLocalBufferChange = Date.now() - 10000;  // 10s ago — stale.
            window.pendingPersist = false;
            window.isBufferSyncing = false;

            window.fetch = function(url, opts) {
                if (typeof url === 'string' && url.includes('/api/state/buffer') && (!opts || !opts.method || opts.method === 'GET')) {
                    return Promise.resolve(new Response(
                        JSON.stringify([{
                            id: 55550, type: 'spool', display: 'FRESH-FROM-SERVER',
                            color: 'ffff00', remaining_weight: 300, details: 'Fresh'
                        }]),
                        { status: 200, headers: { 'Content-Type': 'application/json' } }
                    ));
                }
                if (typeof url === 'string' && url.includes('/api/state/buffer')) {
                    return Promise.resolve(new Response('{}', { status: 200 }));
                }
                return originalFetch.call(window, url, opts);
            };

            loadBuffer();
            await new Promise(r => setTimeout(r, 200));

            const heldAfter = state.heldSpools.slice();

            // Restore.
            window.fetch = originalFetch;
            state.heldSpools = originalHeld;
            window.lastLocalBufferChange = 0;
            window.pendingPersist = false;
            window.isBufferSyncing = false;
            if (window.renderBuffer) window.renderBuffer();

            return { heldAfter };
        }"""
    )

    assert len(result["heldAfter"]) == 1, f"Server overwrite should land, got {result['heldAfter']}"
    assert result["heldAfter"][0]["id"] == 55550, (
        f"Stale local should be replaced by fresh server payload. Got: {result['heldAfter']}"
    )


@pytest.mark.usefixtures("require_server")
def test_pending_persist_flushes_after_sync_completes(page: Page, base_url: str):
    """If a persist was queued during a sync, loadBuffer's resolve path must
    actually call persistBuffer once the sync window releases."""
    _wait_app_ready(page, base_url)

    result = page.evaluate(
        """async () => {
            const originalFetch = window.fetch;
            const originalHeld = state.heldSpools.slice();
            let postCount = 0;

            // Same-state response so the .then doesn't try to overwrite —
            // we're isolating the pendingPersist-flush behavior.
            state.heldSpools = [];
            window.lastLocalBufferChange = 0;
            window.pendingPersist = true;     // pre-queued
            window.isBufferSyncing = false;
            window.suppressBufferDirty = false;

            window.fetch = function(url, opts) {
                if (typeof url === 'string' && url.includes('/api/state/buffer')) {
                    if (opts && opts.method === 'POST') {
                        postCount += 1;
                        return Promise.resolve(new Response('{}', { status: 200 }));
                    }
                    // GET — return matching empty buffer
                    return Promise.resolve(new Response(
                        '[]', { status: 200, headers: { 'Content-Type': 'application/json' } }
                    ));
                }
                return originalFetch.call(window, url, opts);
            };

            loadBuffer();
            await new Promise(r => setTimeout(r, 250));

            const flushed = !window.pendingPersist;

            // Restore.
            window.fetch = originalFetch;
            state.heldSpools = originalHeld;
            window.lastLocalBufferChange = 0;
            window.pendingPersist = false;
            window.isBufferSyncing = false;
            if (window.renderBuffer) window.renderBuffer();

            return { postCount, flushed };
        }"""
    )

    assert result["flushed"] is True, "pendingPersist should be reset after the sync resolves"
    assert result["postCount"] >= 1, (
        f"persistBuffer should fire once during sync resolution. POSTs seen: {result['postCount']}"
    )
