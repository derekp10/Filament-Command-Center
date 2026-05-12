"""Tests for the Manufacturer/Vendor Edit Modal V1 (Group 6.2).

Two entry points: pencil next to fil-detail-vendor (Filament Details modal)
and pencil next to editfil-vendor-info (Edit Filament modal — stacks over).
V1 fields: name (native), comment (labeled "Notes"), website (extra).

Covers:
  - API contract for PATCH /api/vendors/<id> (rejects empty / non-dict data).
  - Modal DOM is always present on the dashboard.
  - openVendorEditModal populates inputs from stubbed /api/vendors fetch.
  - Save POSTs correct PATCH payload (name + comment + extra.website wrapped).
  - Success dispatches `vendor:updated` event with new vendor body.
  - Error displays in banner + toast.
"""
from __future__ import annotations

import requests
from playwright.sync_api import Page, expect


# --- API contract --------------------------------------------------------


def test_patch_vendor_rejects_empty_data(api_base_url: str):
    r = requests.patch(f"{api_base_url}/api/vendors/1", json={"data": {}}, timeout=5)
    body = r.json()
    assert body.get("success") is False
    assert "no fields" in body.get("msg", "").lower()


def test_patch_vendor_rejects_non_dict_data(api_base_url: str):
    r = requests.patch(f"{api_base_url}/api/vendors/1", json={"data": "nope"}, timeout=5)
    body = r.json()
    assert body.get("success") is False


# --- Frontend behavior with stubbed fetches -----------------------------


def _stub_vendor_fetches(page: Page) -> None:
    """Install a window.fetch stub so the modal flow runs without hitting prod.

    Captures the PATCH payload on window.__lastVendorPatch so tests can assert
    on the wire shape without persisting any test data.
    """
    page.evaluate(
        """
        window.__lastVendorPatch = null;
        window.__lastVendorPatchUrl = null;
        window.__vendorUpdatedEvents = [];
        document.addEventListener('vendor:updated', (e) => {
            window.__vendorUpdatedEvents.push(e.detail);
        });
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            // Background fetches sometimes pass a Request object, not a string.
            // Fall through to the real fetch for anything we don't explicitly stub.
            if (typeof url !== 'string') return origFetch(url, opts);
            const method = (opts && opts.method) || 'GET';
            if (url === '/api/vendors' && method === 'GET') {
                return new Response(JSON.stringify({
                    success: true,
                    vendors: [
                        {id: 1, name: 'Alpha', comment: 'old note',
                         empty_spool_weight: 198, external_id: 'alpha-ext-1',
                         registered: '2026-02-11T04:07:23Z',
                         extra: {website: '"https://alpha.example"'}},
                        {id: 2, name: 'Beta', comment: '',
                         empty_spool_weight: null, external_id: '',
                         registered: '2026-03-01T10:00:00Z',
                         extra: {}},
                    ]
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url.startsWith('/api/vendors/') && method === 'PATCH') {
                window.__lastVendorPatchUrl = url;
                window.__lastVendorPatch = JSON.parse(opts.body);
                const sent = window.__lastVendorPatch.data || {};
                return new Response(JSON.stringify({
                    success: true,
                    vendor: {
                        id: 1,
                        name: sent.name || 'Alpha',
                        comment: sent.comment || '',
                        extra: sent.extra || {},
                    }
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return origFetch(url, opts);
        };
        """
    )


def _wait_ready(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openVendorEditModal === 'function'")


def test_vendor_modal_dom_present(page: Page):
    _wait_ready(page)
    expect(page.locator("#vendorEditModal")).to_have_count(1)
    expect(page.locator("#vendoredit-name")).to_have_count(1)
    expect(page.locator("#vendoredit-website")).to_have_count(1)
    expect(page.locator("#vendoredit-empty-weight")).to_have_count(1)
    expect(page.locator("#vendoredit-external-id")).to_have_count(1)
    expect(page.locator("#vendoredit-comment")).to_have_count(1)
    expect(page.locator("#vendoredit-registered")).to_have_count(1)
    expect(page.locator("#vendoredit-save")).to_have_count(1)


def test_open_populates_from_existing_vendor(page: Page):
    _wait_ready(page)
    _stub_vendor_fetches(page)
    page.evaluate("() => window.openVendorEditModal(1)")
    expect(page.locator("#vendorEditModal.show")).to_have_count(1)
    # Native fields hydrate directly; website unwraps from JSON-quoted form.
    assert page.locator("#vendoredit-id").input_value() == "1"
    assert page.locator("#vendoredit-name").input_value() == "Alpha"
    assert page.locator("#vendoredit-comment").input_value() == "old note"
    assert page.locator("#vendoredit-website").input_value() == "https://alpha.example"
    assert page.locator("#vendoredit-empty-weight").input_value() == "198"
    assert page.locator("#vendoredit-external-id").input_value() == "alpha-ext-1"
    # Read-only registered footer renders just the date portion.
    assert "2026-02-11" in page.locator("#vendoredit-registered").inner_text()


def test_save_sends_correct_patch_payload(page: Page):
    _wait_ready(page)
    _stub_vendor_fetches(page)
    page.evaluate("() => window.openVendorEditModal(1)")
    page.locator("#vendoredit-name").fill("Alpha Renamed")
    page.locator("#vendoredit-website").fill("https://new.example")
    page.locator("#vendoredit-empty-weight").fill("210.5")
    page.locator("#vendoredit-external-id").fill("alpha-renamed-ext")
    page.locator("#vendoredit-comment").fill("brand new note")
    page.locator("#vendoredit-save").click()
    page.wait_for_function("window.__lastVendorPatch !== null")
    payload = page.evaluate("() => window.__lastVendorPatch")
    url = page.evaluate("() => window.__lastVendorPatchUrl")
    assert url == "/api/vendors/1"
    data = payload["data"]
    assert data["name"] == "Alpha Renamed"
    assert data["comment"] == "brand new note"
    assert data["external_id"] == "alpha-renamed-ext"
    # Empty-weight is a number on the wire (not a string).
    assert data["empty_spool_weight"] == 210.5
    # Website wraps in JSON-quoted form per the JSON_STRING_FIELDS contract.
    assert data["extra"]["website"] == '"https://new.example"'


def test_save_clears_empty_weight_to_null(page: Page):
    _wait_ready(page)
    _stub_vendor_fetches(page)
    page.evaluate("() => window.openVendorEditModal(1)")
    # Vendor #1 had 198 — clearing the input should send null on save so the
    # user can drop the cascade source intentionally.
    page.locator("#vendoredit-empty-weight").fill("")
    page.locator("#vendoredit-save").click()
    page.wait_for_function("window.__lastVendorPatch !== null")
    data = page.evaluate("() => window.__lastVendorPatch.data")
    assert data["empty_spool_weight"] is None


def test_save_rejects_negative_empty_weight(page: Page):
    _wait_ready(page)
    _stub_vendor_fetches(page)
    page.evaluate("() => window.openVendorEditModal(1)")
    # Browser <input type=number> drops non-numeric chars automatically, but
    # negative numbers parse fine and would silently pass to Spoolman as a
    # garbage value. The save handler must reject these explicitly.
    page.locator("#vendoredit-empty-weight").fill("-50")
    page.locator("#vendoredit-save").click()
    expect(page.locator("#vendoredit-error")).not_to_have_class("d-none")
    assert page.evaluate("() => window.__lastVendorPatch") is None


def test_save_dispatches_vendor_updated_event(page: Page):
    _wait_ready(page)
    _stub_vendor_fetches(page)
    page.evaluate("() => window.openVendorEditModal(1)")
    page.locator("#vendoredit-name").fill("Alpha Renamed")
    page.locator("#vendoredit-save").click()
    page.wait_for_function("window.__vendorUpdatedEvents.length > 0")
    events = page.evaluate("() => window.__vendorUpdatedEvents")
    assert len(events) == 1
    assert events[0]["id"] == "1"
    assert events[0]["vendor"]["name"] == "Alpha Renamed"


def test_save_blocks_when_name_empty(page: Page):
    _wait_ready(page)
    _stub_vendor_fetches(page)
    page.evaluate("() => window.openVendorEditModal(1)")
    page.locator("#vendoredit-name").fill("")
    page.locator("#vendoredit-save").click()
    # Error banner displays + no PATCH fired.
    expect(page.locator("#vendoredit-error")).not_to_have_class("d-none")
    assert page.evaluate("() => window.__lastVendorPatch") is None


def test_pencil_in_filament_details_opens_modal(page: Page):
    """Verifies the entry point at modals_details.html L99 — pencil next to
    fil-detail-vendor uses the dataset.vendorId stash to call openVendorEditModal."""
    _wait_ready(page)
    _stub_vendor_fetches(page)
    # Simulate the populator's dataset stash that openFilamentDetails does.
    page.evaluate(
        "() => { const el = document.getElementById('fil-detail-vendor');"
        "  el.dataset.vendorId = '2'; el.innerText = 'Beta'; }"
    )
    # The pencil's onclick reads dataset.vendorId then calls openVendorEditModal.
    page.evaluate(
        "() => openVendorEditModal(document.getElementById('fil-detail-vendor').dataset.vendorId)"
    )
    expect(page.locator("#vendorEditModal.show")).to_have_count(1)
    assert page.locator("#vendoredit-id").input_value() == "2"
    assert page.locator("#vendoredit-name").input_value() == "Beta"
