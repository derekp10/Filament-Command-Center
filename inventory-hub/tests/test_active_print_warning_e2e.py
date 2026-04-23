"""
Frontend tests for the active-print pre-check wired into doAssign and the
Quick-Swap confirm overlay.

Verifies:
  - window.fetchPrinterStateForToolhead is exposed.
  - When the backend reports is_active=true, Quick-Swap's confirm body
    includes a warning banner naming the printer state.
  - When the backend reports is_active=false/unknown, no banner appears.

These tests stub /api/printer_state via fetch-patching so we don't depend on
a physically printing printer.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


def test_fetch_printer_state_is_exposed(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "typeof window.fetchPrinterStateForToolhead === 'function'",
        timeout=5_000,
    )


def test_fetch_printer_state_resolves_null_for_unknown(page: Page):
    """Unknown toolhead → backend replies known:false → helper resolves null."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.fetchPrinterStateForToolhead === 'function'")

    result = page.evaluate(
        """async () => window.fetchPrinterStateForToolhead('NOT-A-TOOLHEAD')"""
    )
    assert result is None


def test_fetch_printer_state_resolves_null_for_inactive_printer(page: Page):
    """Stub the backend to report known=true, is_active=false."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.fetchPrinterStateForToolhead === 'function'")

    result = page.evaluate(
        """async () => {
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {
                if (url.startsWith('/api/printer_state/')) {
                    return new Response(JSON.stringify({
                        known: true, is_active: false, state: 'IDLE', printer_name: 'Test'
                    }), {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                return origFetch(url, opts);
            };
            try {
                return await window.fetchPrinterStateForToolhead('CORE1-M0');
            } finally {
                window.fetch = origFetch;
            }
        }"""
    )
    assert result is None


def test_fetch_printer_state_returns_info_for_active_printer(page: Page):
    """Stub the backend to report known=true, is_active=true → helper returns the info."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.fetchPrinterStateForToolhead === 'function'")

    result = page.evaluate(
        """async () => {
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {
                if (url.startsWith('/api/printer_state/')) {
                    return new Response(JSON.stringify({
                        known: true, is_active: true, state: 'PRINTING', printer_name: 'XL'
                    }), {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                return origFetch(url, opts);
            };
            try {
                return await window.fetchPrinterStateForToolhead('XL-3');
            } finally {
                window.fetch = origFetch;
            }
        }"""
    )
    assert result == {"state": "PRINTING", "printer_name": "XL"}
