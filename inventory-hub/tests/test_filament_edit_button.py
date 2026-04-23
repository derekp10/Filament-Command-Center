"""
Tests for the Edit Filament Bootstrap modal (promoted from Swal 2026-04-23).

Covers:
  - Modal DOM is always present on the dashboard.
  - window.openEditFilamentForm populates the modal from the filament arg.
  - Tabs (Basic / Colors / Specs / Advanced) hold the right inputs.
  - Color rows add/remove + direction selector visibility.
  - Vendor datalist + "+ NEW" badge + inline vendor-create.
  - Dirty-diff POST payload (no no-op writes).
  - Extras merge preserves unknown keys on the filament.
  - API contract tests for /api/update_filament and /api/vendors.
"""
from __future__ import annotations

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


def test_create_vendor_rejects_empty_name(api_base_url: str):
    r = requests.post(f"{api_base_url}/api/vendors", json={}, timeout=5)
    assert r.status_code == 400
    body = r.json()
    assert body.get("success") is False
    assert "name" in body.get("msg", "").lower()


def test_create_vendor_rejects_blank_name(api_base_url: str):
    r = requests.post(f"{api_base_url}/api/vendors", json={"name": "   "}, timeout=5)
    assert r.status_code == 400
    assert r.json().get("success") is False


# --- Frontend wiring -------------------------------------------------------


def test_edit_filament_modal_exists_in_dom(page: Page):
    """Bootstrap modal is part of the static template, always in the DOM."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    expect(page.locator("#editFilamentModal")).to_have_count(1)
    # All four tab buttons present.
    expect(page.locator("#editfil-tab-basic-btn")).to_have_count(1)
    expect(page.locator("#editfil-tab-colors-btn")).to_have_count(1)
    expect(page.locator("#editfil-tab-specs-btn")).to_have_count(1)
    expect(page.locator("#editfil-tab-advanced-btn")).to_have_count(1)


def test_openEditFilamentForm_is_on_window(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'", timeout=5_000)


def _stub_editfil_fetches(page: Page):
    """Install fetch stubs so the modal never mutates live Spoolman or
    waits for a slow /api/vendors. Exposes window.__lastFetchPayload."""
    page.evaluate(
        """
        window.__lastFetchPayload = null;
        window.__createdVendor = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            const method = (opts && opts.method) || 'GET';
            if (url === '/api/vendors' && method === 'GET') {
                return new Response(JSON.stringify({
                    success: true,
                    vendors: [{id: 1, name: 'Alpha'}, {id: 2, name: 'Beta'}]
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/vendors' && method === 'POST') {
                const body = JSON.parse(opts.body);
                window.__createdVendor = body;
                return new Response(JSON.stringify({
                    success: true, vendor: {id: 42, name: body.name}
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/materials') {
                return new Response(JSON.stringify({success: true, materials: ['PLA', 'PETG', 'ABS']}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/update_filament') {
                window.__lastFetchPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({success: true, filament: {id: 1}}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return origFetch(url, opts);
        };
        """
    )


def _open_modal_with(page: Page, fil: dict):
    """Open the modal, wait for the basic tab to be visible."""
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)
    expect(page.locator("#editfil-name")).to_be_visible()


def test_modal_populates_basic_tab_from_fil(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 101,
        "name": "Gold",
        "material": "PLA",
        "settings_extruder_temp": 200,
        "settings_bed_temp": 60,
        "comment": "Fan: On",
        "vendor": {"id": 1, "name": "Alpha"},
    }
    _open_modal_with(page, fil)

    assert page.locator("#editfil-name").input_value() == "Gold"
    assert page.locator("#editfil-material").input_value() == "PLA"
    assert page.locator("#editfil-nozzle").input_value() == "200"
    assert page.locator("#editfil-bed").input_value() == "60"
    assert page.locator("#editfil-comment").input_value() == "Fan: On"
    assert page.locator("#editfil-vendor-name").input_value() == "Alpha"


def test_modal_specs_tab_populates_and_renders(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 102,
        "name": "Blue",
        "material": "PLA",
        "spool_weight": 180,
        "density": 1.24,
        "diameter": 1.75,
        "weight": 1000,
        "price": 24.99,
    }
    _open_modal_with(page, fil)
    # Switch to Specs tab.
    page.locator("#editfil-tab-specs-btn").click()
    assert page.locator("#editfil-spool-weight").input_value() == "180"
    assert page.locator("#editfil-density").input_value() == "1.24"
    assert page.locator("#editfil-diameter").input_value() == "1.75"
    assert page.locator("#editfil-weight").input_value() == "1000"
    assert page.locator("#editfil-price").input_value() == "24.99"


def test_modal_advanced_tab_populates_extras(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 103,
        "name": "Red",
        "material": "PLA",
        "external_id": "LEGACY-7",
        "extra": {
            "product_url": '"https://vendor.example/product"',
            "purchase_url": '"https://shop.example/buy"',
            "sheet_link": '"https://docs.example/sheet"',
            "original_color": '"Silk Gold"',
            "filament_attributes": '["Silk","Shimmer"]',
        },
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()
    assert page.locator("#editfil-original-color").input_value() == "Silk Gold"
    assert page.locator("#editfil-attributes").input_value() == "Silk, Shimmer"
    assert page.locator("#editfil-product-url").input_value() == "https://vendor.example/product"
    assert page.locator("#editfil-purchase-url").input_value() == "https://shop.example/buy"
    assert page.locator("#editfil-sheet-link").input_value() == "https://docs.example/sheet"
    assert page.locator("#editfil-external-id").input_value() == "LEGACY-7"


def test_modal_colors_seed_from_multi_color_hexes(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 104, "name": "Rainbow", "material": "PLA",
        "multi_color_hexes": "ff0000,00ff00,0000ff",
        "multi_color_direction": "coaxial",
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()

    assert page.locator("#editfil-color-hex").input_value().lower() == "#ff0000"
    assert page.locator("#editfil-color-extras .editfil-color-row").count() == 2
    direction = page.locator("#editfil-color-direction")
    expect(page.locator("#editfil-direction-wrap")).to_be_visible()
    assert direction.input_value() == "coaxial"


def test_modal_add_color_button_appends_row_and_reveals_direction(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 105, "name": "Mono", "material": "PLA", "color_hex": "ff00ff"}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()

    assert not page.locator("#editfil-direction-wrap").is_visible()
    page.locator("#editfil-add-color").click()
    assert page.locator("#editfil-color-extras .editfil-color-row").count() == 1
    expect(page.locator("#editfil-direction-wrap")).to_be_visible()


def test_modal_remove_last_extra_hides_direction(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 106, "name": "Two", "material": "PLA",
        "multi_color_hexes": "ff0000,00ff00",
        "multi_color_direction": "longitudinal",
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()

    expect(page.locator("#editfil-direction-wrap")).to_be_visible()
    page.locator("#editfil-color-extras .editfil-color-row button").first.click()
    assert page.locator("#editfil-color-extras .editfil-color-row").count() == 0
    assert not page.locator("#editfil-direction-wrap").is_visible()


def test_modal_save_posts_dirty_diff_only(page: Page):
    """Changing only the comment field should POST only {comment}."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 200, "name": "Red", "material": "PLA",
        "spool_weight": 200, "density": 1.24,
        "settings_extruder_temp": 210, "settings_bed_temp": 60,
        "comment": "",
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-comment").fill("Updated notes")
    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    payload = page.evaluate("() => window.__lastFetchPayload")
    assert payload["id"] == 200
    assert list(payload["data"].keys()) == ["comment"]
    assert payload["data"]["comment"] == "Updated notes"


def test_modal_save_submits_multi_color_csv(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 201, "name": "Mono", "material": "PLA", "color_hex": "ff0000"}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()
    page.locator("#editfil-add-color").click()
    # The newly added row's hex input.
    extra_hex = page.locator("#editfil-color-extras input[id^='editfil-color-hex-']").first
    extra_hex.fill("#00ff00")
    page.locator("#editfil-color-direction").select_option(value="coaxial")

    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    data = page.evaluate("() => window.__lastFetchPayload.data")
    assert data["multi_color_hexes"] == "ff0000,00ff00"
    assert data["multi_color_direction"] == "coaxial"


def test_modal_save_rejects_invalid_hex(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 202, "name": "T", "material": "PLA", "color_hex": "112233"}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()
    page.locator("#editfil-color-hex").fill("not-a-color")
    page.locator("#editfil-save").click()
    # Error banner becomes visible with "hex" in the message.
    expect(page.locator("#editfil-error")).to_be_visible()
    text = page.locator("#editfil-error").text_content() or ""
    assert "hex" in text.lower() or "color" in text.lower()


def test_modal_save_merged_extras_preserve_unknown_keys(page: Page):
    """Editing one URL must NOT wipe other Spoolman keys in extra."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 203, "name": "T", "material": "PLA",
        "extra": {
            "product_url": '"https://old.example"',
            "price_total": '"$19.99"',
            "some_custom_key": '"preserve-me"',
        },
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()
    page.locator("#editfil-product-url").fill("https://new.example")
    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    extra = page.evaluate("() => window.__lastFetchPayload.data.extra")
    assert extra["product_url"] == '"https://new.example"'
    assert extra["price_total"] == '"$19.99"'
    assert extra["some_custom_key"] == '"preserve-me"'


def test_modal_filament_attributes_serialize_to_json_array(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 204, "name": "T", "material": "PLA", "extra": {}}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()
    page.locator("#editfil-attributes").fill("Silk, Matte")
    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    attrs_raw = page.evaluate("() => window.__lastFetchPayload.data.extra.filament_attributes")
    import json
    assert json.loads(attrs_raw) == ["Silk", "Matte"]


def test_modal_typing_new_vendor_shows_badge(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 205, "name": "T", "material": "PLA", "vendor": {"id": 1, "name": "Alpha"}}
    _open_modal_with(page, fil)
    # Wait for vendor datalist to load.
    page.wait_for_function(
        "document.querySelector(\"#editfil-vendor-dl option[value='Alpha']\") !== null",
        timeout=3_000,
    )
    assert not page.locator("#editfil-vendor-new-badge").is_visible()

    page.locator("#editfil-vendor-name").fill("BrandNewCo")
    page.wait_for_timeout(100)
    expect(page.locator("#editfil-vendor-new-badge")).to_be_visible()
    assert page.locator("#editfil-vendor-id").input_value() == ""


def test_modal_creates_new_vendor_then_patches(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 206, "name": "T", "material": "PLA", "vendor": {"id": 1, "name": "Alpha"}}
    _open_modal_with(page, fil)
    page.wait_for_function(
        "document.querySelector(\"#editfil-vendor-dl option[value='Alpha']\") !== null",
        timeout=3_000,
    )
    page.locator("#editfil-vendor-name").fill("FreshBrand")
    page.wait_for_timeout(100)
    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=5_000)

    created = page.evaluate("() => window.__createdVendor")
    assert created == {"name": "FreshBrand"}
    payload = page.evaluate("() => window.__lastFetchPayload")
    assert payload["data"]["vendor_id"] == 42


def test_modal_select_existing_vendor_sets_hidden_id(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 207, "name": "T", "material": "PLA", "vendor": {"id": 1, "name": "Alpha"}}
    _open_modal_with(page, fil)
    page.wait_for_function(
        "document.querySelector(\"#editfil-vendor-dl option[value='Beta']\") !== null",
        timeout=3_000,
    )
    page.locator("#editfil-vendor-name").fill("Beta")
    page.wait_for_timeout(100)
    assert page.locator("#editfil-vendor-id").input_value() == "2"


def test_modal_no_changes_saves_nothing(page: Page):
    """Opening the modal and hitting Save without changes should skip POST."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 208, "name": "Static", "material": "PLA", "color_hex": "112233"}
    _open_modal_with(page, fil)
    page.locator("#editfil-save").click()
    # Give the save handler a moment; payload should remain null.
    page.wait_for_timeout(500)
    payload = page.evaluate("() => window.__lastFetchPayload")
    assert payload is None
