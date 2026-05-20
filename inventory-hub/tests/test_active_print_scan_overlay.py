"""L122 — the active-print confirm overlay shown after a buffer-assign
scan that targets a printing/paused toolhead. Previously the overlay
was a hand-rolled createElement + appendChild + document keydown
pattern, susceptible to z-index/focus blocks ("confirm change modal
is being blocked, canceled, or hidden"). Migrated to window.mountOverlay
so it inherits the canonical z-index ladder (`tier: 'confirm'`),
focus-guard, and Escape-via-onEscape discipline.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def _setup_page(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        "typeof window.processScan === 'function' && typeof window.mountOverlay === 'function'",
        timeout=10000,
    )


def _open_scan_overlay(page: Page):
    # Drive _confirmActivePrintScan directly with a synthetic invocation —
    # avoids needing a real PRINTING printer to trigger the requires_confirm
    # response. The overlay is defined as a module-scope `const`, so we have
    # to reach it through processScan's failure path. Instead expose a
    # one-off shim that calls the inner function via the same shape the
    # backend produces.
    return page.evaluate(
        """() => new Promise((resolve) => {
            window.__apsResult = null;
            // Replicate the call processScan would make on require_confirm.
            // We can't reach the module-local _confirmActivePrintScan
            // directly, so trigger via /api/identify_scan stub + processScan.
            const origFetch = window.fetch;
            let stage = 0;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u.endsWith('/api/identify_scan')) {
                    // First call resolves the scan as a location move,
                    // second call (smart_move) requires confirm.
                    return new Response(JSON.stringify({
                        type: 'location', id: 'XL-1', display: 'LOC: XL-1', contents: [],
                    }), { status: 200, headers: {'Content-Type':'application/json'} });
                }
                if (u.endsWith('/api/smart_move')) {
                    if (stage === 0) {
                        stage = 1;
                        return new Response(JSON.stringify({
                            status: 'requires_confirm',
                            confirm_type: 'active_print',
                            active_print: { printer_name: 'Test Printer', state: 'PRINTING' },
                            msg: 'Test Printer is PRINTING',
                        }), { status: 200, headers: {'Content-Type':'application/json'} });
                    }
                    return new Response(JSON.stringify({ status: 'success' }),
                        { status: 200, headers: {'Content-Type':'application/json'} });
                }
                return origFetch(url, opts);
            };
            // Seed buffer + trigger.
            window.lastLocalBufferChange = Date.now();
            state.heldSpools = [{ id: 8001, display: 'TEST', color: '#fff' }];
            // Add to allLocations so the LOC type lookup hits.
            if (!state.allLocations.find(l => l.LocationID === 'XL-1')) {
                state.allLocations.push({ LocationID: 'XL-1', Type: 'Tool Head', 'Max Spools': '1' });
            }
            window.processScan('LOC:XL-1', 'test');
            // Resolve once overlay shows up.
            const waiter = setInterval(() => {
                const ov = document.getElementById('fcc-active-print-scan-overlay');
                if (ov && (ov.style.display !== 'none')) {
                    clearInterval(waiter);
                    resolve(true);
                }
            }, 100);
            setTimeout(() => { clearInterval(waiter); resolve(false); }, 5000);
        })"""
    )


@pytest.mark.usefixtures("require_server")
def test_active_print_scan_overlay_mounts_via_mount_overlay(page: Page, base_url: str, reset_dom_state_js: str):
    _setup_page(page, base_url, reset_dom_state_js)
    shown = _open_scan_overlay(page)
    assert shown, "active-print scan overlay never appeared"

    ov = page.locator("#fcc-active-print-scan-overlay")
    expect(ov).to_be_visible()
    # mountOverlay marks the panel with the OVERLAY_Z confirm tier.
    z = page.evaluate("() => parseInt(getComputedStyle(document.getElementById('fcc-active-print-scan-overlay')).zIndex)")
    assert z >= 20100, f"expected confirm-tier z-index >= 20100, got {z}"

    # Cancel button cleans up.
    page.locator("#fcc-aps-no").click()
    expect(page.locator("#fcc-active-print-scan-overlay")).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server")
def test_active_print_scan_overlay_escape_cancels(page: Page, base_url: str, reset_dom_state_js: str):
    _setup_page(page, base_url, reset_dom_state_js)
    shown = _open_scan_overlay(page)
    assert shown, "active-print scan overlay never appeared"

    expect(page.locator("#fcc-active-print-scan-overlay")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#fcc-active-print-scan-overlay")).to_be_hidden(timeout=2000)
