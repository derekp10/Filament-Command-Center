"""
Visual regression snapshot for the QR-confirm row.

Locks in the look-and-feel so future tweaks (CSS bumps, label changes,
QR sizing) get caught by pixel diff. Standalone host (no overlay) so the
snapshot focuses on the QR row itself rather than the surrounding modal
chrome.
"""
from __future__ import annotations

from playwright.sync_api import Page


def test_confirm_qr_row_visual(page: Page, snapshot):
    """Mount a confirm-QR pair into a fixed-size, dark-bg host and snapshot
    just the row. Captures both QR tiles, both labels, the spacing, and
    the warning theme colors."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.attachConfirmQRs === 'function'")

    page.evaluate(
        """() => {
            const stage = document.createElement('div');
            stage.id = 'cqr-snapshot-stage';
            stage.style.cssText = 'position:fixed; top:60px; left:60px; z-index:30000;'
                + 'background:#1e1e1e; color:#fff; padding:24px;'
                + 'border:2px solid #ff8800; border-radius:8px; width:460px;';
            stage.innerHTML = `
                <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">
                    ⚠️ Test Printer is PRINTING
                </div>
                <div style="color:#ffc; margin-bottom:14px;">
                    Reassigning a spool now will disrupt the print. Continue anyway?
                </div>
                <div style="display:flex; gap:10px; justify-content:center;">
                    <button class="btn btn-warning btn-sm" style="min-width:120px;">Continue Anyway</button>
                    <button class="btn btn-secondary btn-sm" style="min-width:120px;">Cancel</button>
                </div>
            `;
            document.body.appendChild(stage);
            window.attachConfirmQRs({
                host: stage,
                onConfirm: () => {},
                onCancel: () => {},
                theme: 'warning',
            });
        }"""
    )
    # Give the QR codes a moment to render (generateSafeQR uses two RAFs).
    page.wait_for_timeout(400)
    snapshot(page.locator("#cqr-snapshot-stage"), "confirm-qr-row")
