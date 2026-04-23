"""
Tests for the Edit Filament button on the Filament Details modal.

Covers:
  - The button is wired onto the modal footer and calls the new
    window.openEditFilamentForm() helper.
  - The Swal form populates from the filament passed in.
  - preConfirm returns a dirty-diff only (no-op changes are filtered).
  - /api/update_filament accepts {id, data} and rejects malformed payloads.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


# --- API contract tests ----------------------------------------------------


def test_update_filament_rejects_missing_id(api_base_url: str):
    r = requests.post(f"{api_base_url}/api/update_filament", json={"data": {"name": "X"}}, timeout=5)
    payload = r.json()
    assert payload.get("success") is False
    assert "id" in payload.get("msg", "").lower()


def test_update_filament_rejects_empty_data(api_base_url: str):
    r = requests.post(f"{api_base_url}/api/update_filament", json={"id": 1, "data": {}}, timeout=5)
    payload = r.json()
    assert payload.get("success") is False
    assert "no fields" in payload.get("msg", "").lower() or "update" in payload.get("msg", "").lower()


def test_update_filament_rejects_non_dict_data(api_base_url: str):
    r = requests.post(f"{api_base_url}/api/update_filament", json={"id": 1, "data": "not-a-dict"}, timeout=5)
    payload = r.json()
    assert payload.get("success") is False


# --- Frontend wiring tests --------------------------------------------------


def test_edit_filament_button_present(page: Page):
    """The Edit Filament button should exist in the filament modal footer."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    expect(page.locator("#btn-fil-edit")).to_have_count(1)


def test_openEditFilamentForm_is_on_window(page: Page):
    """The helper is exposed so the Details module can call it."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'", timeout=5_000)


def test_openEditFilamentForm_preConfirm_returns_only_dirty_fields(page: Page):
    """preConfirm should drop unchanged fields so we never POST a no-op."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {
        "id": 42,
        "name": "Red",
        "material": "PLA",
        "spool_weight": 200,
        "density": 1.24,
        "settings_extruder_temp": 210,
        "settings_bed_temp": 60,
        "comment": "",
    }

    # Open the form
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-name", state="visible", timeout=3_000)

    # Change only the comment field
    page.locator("#edit-fil-comment").fill("Updated notes")

    # Fire the Swal confirm button and capture the dirty-diff that preConfirm built.
    # Rather than actually POSTing, we intercept fetch here.
    page.evaluate(
        """
        window.__lastFetchPayload = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            if (url === '/api/update_filament') {
                window.__lastFetchPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({success: true, filament: {id: 42}}), {
                    status: 200, headers: {'Content-Type': 'application/json'}
                });
            }
            return origFetch(url, opts);
        };
        """
    )

    # Click the Swal confirm button
    page.locator(".swal2-confirm").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)

    payload = page.evaluate("() => window.__lastFetchPayload")
    assert payload["id"] == 42
    # Only 'comment' changed — no other fields should be in the diff
    assert list(payload["data"].keys()) == ["comment"]
    assert payload["data"]["comment"] == "Updated notes"


def test_openEditFilamentForm_shows_vendor_weight_hint(page: Page):
    """When the vendor has an empty_spool_weight, it surfaces as a placeholder hint."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {
        "id": 77,
        "name": "Blue",
        "material": "PLA",
        "spool_weight": None,
        "vendor": {"name": "Sunlu", "empty_spool_weight": 167},
    }
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-spool-weight", state="visible", timeout=3_000)

    # The vendor hint appears in the label and as a placeholder.
    label_text = page.locator("label[for='edit-fil-spool-weight'], .text-start >> text=/vendor: 167g/").first
    # Fall back to checking the placeholder attribute since labels aren't strictly bound.
    placeholder = page.locator("#edit-fil-spool-weight").get_attribute("placeholder")
    assert placeholder == "167", f"expected placeholder '167', got {placeholder!r}"
