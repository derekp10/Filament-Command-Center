"""
Tests for the QR-confirmable dialog helper (`window.attachConfirmQRs`) and
the matching CMD:CONFIRM:<sid> / CMD:CANCEL:<sid> scan-route handler.

The helper lets confirm overlays accept QR-code confirmations alongside
mouse/keyboard buttons. Each dialog gets a unique session id so a printed
or stale QR can't fire into a different dialog.

Coverage:
  - Helper mounts a QR row, registers callbacks, returns sessionId+cleanup.
  - QR row has both ✓ and ✗ tiles with readable labels.
  - routeConfirmScan(text) fires the matching callback and clears the entry.
  - cleanup() unregisters so subsequent scans no-op.
  - Unknown / stale session id → routeConfirmScan returns false.
  - Active-print confirm overlay (Location Manager) actually mounts the QRs
    when shown.
"""
from __future__ import annotations

from playwright.sync_api import Page


def _wait_helpers_ready(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.attachConfirmQRs === 'function'")
    page.wait_for_function("typeof window.routeConfirmScan === 'function'")


def test_attach_confirm_qrs_returns_session_id_and_cleanup(page: Page):
    _wait_helpers_ready(page)
    result = page.evaluate(
        """() => {
            const host = document.createElement('div');
            document.body.appendChild(host);
            const session = window.attachConfirmQRs({
                host: host,
                onConfirm: () => { window.__confirmFired = true; },
                onCancel: () => { window.__cancelFired = true; },
            });
            // Labels render with text-transform:uppercase, so innerText comes
            // back uppercase. Check case-insensitively.
            const text = (host.innerText || '').toLowerCase();
            const out = {
                sid: session.sessionId,
                hasCleanup: typeof session.cleanup === 'function',
                rowCount: host.querySelectorAll('.fcc-confirm-qr-row').length,
                yesLabel: text.includes('confirm'),
                cancelLabel: text.includes('cancel'),
                inRegistry: !!window._fccActiveConfirms[session.sessionId],
            };
            session.cleanup();
            host.remove();
            return out;
        }"""
    )
    assert result["sid"].startswith("fcc-cqr-")
    assert result["hasCleanup"] is True
    assert result["rowCount"] == 1
    assert result["yesLabel"] is True
    assert result["cancelLabel"] is True
    assert result["inRegistry"] is True


def test_route_confirm_scan_fires_callback(page: Page):
    """A scan of CMD:CONFIRM:<sid> triggers the registered onConfirm and
    clears the entry from the active registry."""
    _wait_helpers_ready(page)
    out = page.evaluate(
        """() => {
            const host = document.createElement('div');
            document.body.appendChild(host);
            window.__confirmFired = 0;
            window.__cancelFired = 0;
            const session = window.attachConfirmQRs({
                host: host,
                onConfirm: () => { window.__confirmFired += 1; },
                onCancel: () => { window.__cancelFired += 1; },
            });
            // Scan CMD:CONFIRM:<sid> — should fire onConfirm exactly once.
            const handled1 = window.routeConfirmScan('CMD:CONFIRM:' + session.sessionId);
            // Subsequent scan should NOT fire again — the entry was cleared.
            const handled2 = window.routeConfirmScan('CMD:CONFIRM:' + session.sessionId);
            host.remove();
            return {
                handled1, handled2,
                confirmFired: window.__confirmFired,
                cancelFired: window.__cancelFired,
                stillRegistered: !!window._fccActiveConfirms[session.sessionId],
            };
        }"""
    )
    assert out["handled1"] is True
    assert out["handled2"] is False, "Stale QR scan must not re-fire after first match"
    assert out["confirmFired"] == 1
    assert out["cancelFired"] == 0
    assert out["stillRegistered"] is False


def test_route_confirm_scan_cancel_path(page: Page):
    _wait_helpers_ready(page)
    out = page.evaluate(
        """() => {
            const host = document.createElement('div');
            document.body.appendChild(host);
            window.__confirmFired = 0;
            window.__cancelFired = 0;
            const session = window.attachConfirmQRs({
                host: host,
                onConfirm: () => { window.__confirmFired += 1; },
                onCancel: () => { window.__cancelFired += 1; },
            });
            const handled = window.routeConfirmScan('CMD:CANCEL:' + session.sessionId);
            host.remove();
            return {
                handled,
                confirmFired: window.__confirmFired,
                cancelFired: window.__cancelFired,
            };
        }"""
    )
    assert out["handled"] is True
    assert out["cancelFired"] == 1
    assert out["confirmFired"] == 0


def test_route_confirm_scan_returns_false_for_unknown_session(page: Page):
    _wait_helpers_ready(page)
    out = page.evaluate(
        """() => {
            return {
                badSid: window.routeConfirmScan('CMD:CONFIRM:does-not-exist'),
                badPrefix: window.routeConfirmScan('LOC:foo'),
                empty: window.routeConfirmScan(''),
                nullText: window.routeConfirmScan(null),
            };
        }"""
    )
    assert out["badSid"] is False
    assert out["badPrefix"] is False
    assert out["empty"] is False
    assert out["nullText"] is False


def test_attach_confirm_qrs_cleanup_removes_row_and_unregisters(page: Page):
    _wait_helpers_ready(page)
    out = page.evaluate(
        """() => {
            const host = document.createElement('div');
            document.body.appendChild(host);
            const session = window.attachConfirmQRs({
                host: host,
                onConfirm: () => { window.__shouldNotFire = true; },
                onCancel: () => {},
            });
            session.cleanup();
            const stillRegistered = !!window._fccActiveConfirms[session.sessionId];
            const rowGone = host.querySelectorAll('.fcc-confirm-qr-row').length === 0;
            // Late scan after cleanup must NOT fire callback.
            const handled = window.routeConfirmScan('CMD:CONFIRM:' + session.sessionId);
            host.remove();
            return { stillRegistered, rowGone, handled, fired: !!window.__shouldNotFire };
        }"""
    )
    assert out["stillRegistered"] is False
    assert out["rowGone"] is True
    assert out["handled"] is False
    assert out["fired"] is False


def test_active_print_overlay_mounts_qrs(page: Page):
    """When the Location Manager's active-print confirm overlay opens, it
    should mount the QR pair via attachConfirmQRs. We invoke
    _confirmActivePrintAssign through window.doAssign with a stubbed
    backend that returns requires_confirm so the overlay actually opens."""
    _wait_helpers_ready(page)

    # Stub /api/manage_contents to return requires_confirm so doAssign
    # surfaces the overlay. Stub /api/printer_state to return idle so the
    # frontend probe doesn't pre-empt with its own overlay.
    page.evaluate(
        """
        const orig = window.fetch;
        window.fetch = async (url, opts) => {
            const u = typeof url === 'string' ? url : (url && url.url) || '';
            if (u.startsWith('/api/printer_state/')) {
                return new Response(JSON.stringify({known: true, is_active: false, state: 'IDLE', printer_name: 'Test'}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (u === '/api/manage_contents') {
                return new Response(JSON.stringify({
                    status: 'requires_confirm', confirm_type: 'active_print',
                    active_print: {printer_name: 'TestPrinter', state: 'PRINTING', toolhead: 'XL-1'},
                    msg: 'TestPrinter is PRINTING'
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        // Seed a held spool so doAssign doesn't bail early.
        state.heldSpools = [{id: 99, display: '#99', color: 'ff0000'}];
        // Trigger the overlay.
        window.doAssign('LR-MDB-1', 99, 1, true);
        """
    )

    # Wait for the overlay to render with its QR row. The overlay mounts
    # under the manage modal element when present (which is in the static
    # template but display:none until opened) — fine in real usage where
    # the user has Location Manager open, but in this test the overlay
    # inherits display:none. We assert the QR row was actually wired
    # (presence + registry entry + label content) rather than visibility.
    page.wait_for_selector(
        "#fcc-active-print-confirm-overlay .fcc-confirm-qr-row",
        state="attached", timeout=3_000,
    )
    # Both QR tiles present, with their labels (case-insensitive — labels
    # render uppercase via text-transform).
    text = (page.locator(
        "#fcc-active-print-confirm-overlay .fcc-confirm-qr-row"
    ).text_content() or "").lower()
    assert "confirm" in text
    assert "cancel" in text
    # And the registry has one active session ready to route a scan into.
    active_count = page.evaluate("() => Object.keys(window._fccActiveConfirms).length")
    assert active_count >= 1
