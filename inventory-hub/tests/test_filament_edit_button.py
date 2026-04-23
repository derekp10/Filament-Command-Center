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
        window.__lastFetchUrl = null;
        window.__createdVendor = null;
        window.__addedChoices = [];
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
            if (url === '/api/external/fields') {
                return new Response(JSON.stringify({success: true, fields: {filament: [
                    {key: 'filament_attributes', field_type: 'choice', multi_choice: true,
                     choices: ['Silk', 'Matte', 'Carbon Fiber', 'Glow']}
                ], spool: []}}), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/external/fields/add_choice') {
                window.__addedChoices.push(JSON.parse(opts.body));
                return new Response(JSON.stringify({success: true}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/update_filament' || url === '/api/create_filament') {
                window.__lastFetchUrl = url;
                window.__lastFetchPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({success: true, filament: {id: 999}}),
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
    # Attributes now render as chips (wizard-style), not a comma string.
    chip_values = page.evaluate(
        "() => Array.from(document.querySelectorAll('#editfil-attr-chips .editfil-chip'))"
        ".map(c => c.getAttribute('data-value'))"
    )
    assert chip_values == ["Silk", "Shimmer"]
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
    # Rows now have Up/Down/Remove buttons — click the explicit remove (trash).
    page.locator("#editfil-color-extras .editfil-color-row [data-role='remove']").first.click()
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
    # multi_color_direction lives in extras now (Spoolman schema doesn't accept
    # it as a top-level filament field). Stored with surrounding quotes per
    # Spoolman's extras convention.
    assert data["extra"]["multi_color_direction"] == '"coaxial"'


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
    """Typing tags into the chip-picker and pressing Enter should add chips
    and serialize to a JSON array in the extras payload on Save."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 204, "name": "T", "material": "PLA", "extra": {}}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()

    # Type + Enter twice to commit two chips.
    attr_input = page.locator("#editfil-attr-input")
    attr_input.fill("Silk")
    attr_input.press("Enter")
    attr_input.fill("Matte")
    attr_input.press("Enter")

    # Verify chips rendered.
    chip_values = page.evaluate(
        "() => Array.from(document.querySelectorAll('#editfil-attr-chips .editfil-chip'))"
        ".map(c => c.getAttribute('data-value'))"
    )
    assert chip_values == ["Silk", "Matte"]

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
        # Wait for the vendor dropdown fetch to complete. The combobox populates
        # the dropdown lazily on focus, but the vendorCache is filled by the
        # /api/vendors fetch callback. We focus the input to render the
        # dropdown, then check for the expected option's DOM presence.
        "() => { const el = document.getElementById('editfil-vendor-name'); el && el.focus(); const dd = document.getElementById('editfil-vendor-dropdown'); return dd && dd.querySelector('[data-label=\\'Alpha\\']') !== null; }",
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
        # Wait for the vendor dropdown fetch to complete. The combobox populates
        # the dropdown lazily on focus, but the vendorCache is filled by the
        # /api/vendors fetch callback. We focus the input to render the
        # dropdown, then check for the expected option's DOM presence.
        "() => { const el = document.getElementById('editfil-vendor-name'); el && el.focus(); const dd = document.getElementById('editfil-vendor-dropdown'); return dd && dd.querySelector('[data-label=\\'Alpha\\']') !== null; }",
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
    # Poll: type "Beta" into the vendor input, fire the input event, and
    # check whether the hidden id resolved. This races the /api/vendors
    # fetch — once the cache populates, refreshVendorBadge matches and
    # writes "2" into the hidden field.
    page.wait_for_function(
        "() => { const n = document.getElementById('editfil-vendor-name'); n.value = 'Beta'; n.dispatchEvent(new Event('input', {bubbles:true})); return document.getElementById('editfil-vendor-id').value === '2'; }",
        timeout=3_000,
    )
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


# ---------------------------------------------------------------------------
# 2nd iteration (2026-04-23 pm): max-temp fields, color reorder, Add mode,
# chip-picker with known choices, material + NEW badge.
# ---------------------------------------------------------------------------


def test_modal_populates_max_temps_from_extras(page: Page):
    """Specs tab now has nozzle_max and bed_max inputs reading from extras."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 401, "name": "Red", "material": "PLA",
        "settings_extruder_temp": 210, "settings_bed_temp": 60,
        "extra": {
            "nozzle_temp_max": '"230"',
            "bed_temp_max": '"70"',
        },
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-specs-btn").click()
    assert page.locator("#editfil-nozzle").input_value() == "210"
    assert page.locator("#editfil-bed").input_value() == "60"
    assert page.locator("#editfil-nozzle-max").input_value() == "230"
    assert page.locator("#editfil-bed-max").input_value() == "70"


def test_modal_saves_max_temps_into_extras(page: Page):
    """Changing max temps should land them in the extras merge payload."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 402, "name": "Red", "material": "PLA",
        "settings_extruder_temp": 210, "settings_bed_temp": 60,
        "extra": {},
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-specs-btn").click()
    page.locator("#editfil-nozzle-max").fill("240")
    page.locator("#editfil-bed-max").fill("75")
    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    extra = page.evaluate("() => window.__lastFetchPayload.data.extra")
    assert extra["nozzle_temp_max"] == '"240"'
    assert extra["bed_temp_max"] == '"75"'


def test_modal_color_down_button_reorders_primary(page: Page):
    """Clicking ▼ on the primary row should swap it with the first extra."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 403, "name": "Two", "material": "PLA",
        "multi_color_hexes": "aa0000,00aa00",
        "multi_color_direction": "longitudinal",
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()

    assert page.locator("#editfil-color-hex").input_value().lower() == "#aa0000"
    page.locator("#editfil-color-row-primary [data-role='down']").click()
    assert page.locator("#editfil-color-hex").input_value().lower() == "#00aa00"


def test_modal_color_up_button_reorders_extras(page: Page):
    """Clicking ▲ on an extra row swaps it with the row above."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 404, "name": "Three", "material": "PLA",
        "multi_color_hexes": "aa0000,00aa00,0000aa",
        "multi_color_direction": "longitudinal",
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()

    # Click ▲ on the third row (the second extra) — it should swap with the
    # first extra, landing in the "position 1" extra slot.
    rows = page.locator("#editfil-color-extras .editfil-color-row")
    expect(rows).to_have_count(2)
    rows.nth(1).locator("[data-role='up']").click()
    # Re-query rows (DOM was re-rendered) and check the first extra's hex.
    rows = page.locator("#editfil-color-extras .editfil-color-row")
    first_extra_hex = rows.nth(0).locator("input[id^='editfil-color-hex-']").input_value().lower()
    assert first_extra_hex == "#0000aa"


def test_modal_color_reorder_submits_in_new_order(page: Page):
    """After reordering, Save should POST the hexes in the new order."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 405, "name": "Two", "material": "PLA",
        "multi_color_hexes": "aa0000,00aa00",
        "multi_color_direction": "longitudinal",
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()
    page.locator("#editfil-color-row-primary [data-role='down']").click()
    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    data = page.evaluate("() => window.__lastFetchPayload.data")
    assert data["multi_color_hexes"] == "00aa00,aa0000"


def test_modal_material_new_badge_hides_for_known(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 406, "name": "T", "material": "PLA"}
    _open_modal_with(page, fil)
    # Wait for /api/materials to populate the datalist.
    page.wait_for_function(
        "() => { const el = document.getElementById('editfil-material'); el && el.focus(); const dd = document.getElementById('editfil-material-dropdown'); return dd && dd.querySelector('[data-label=\\'PLA\\']') !== null; }",
        timeout=3_000,
    )
    # PLA is known → no badge. Typing "PolyCarbonate" (not in stub list) → badge.
    assert not page.locator("#editfil-material-new-badge").is_visible()
    page.locator("#editfil-material").fill("PolyCarbonate")
    page.wait_for_timeout(100)
    expect(page.locator("#editfil-material-new-badge")).to_be_visible()


def test_modal_add_mode_title_and_create_post(page: Page):
    """openAddFilamentForm() opens modal in Add mode and POSTs /api/create_filament."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openAddFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    page.evaluate("() => window.openAddFilamentForm()")
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)

    # Title starts with the plus icon when in create mode.
    title_text = page.locator("#editFilamentModalLabel").text_content() or ""
    assert "Add" in title_text
    # Save button shows "Create" in Add mode.
    assert page.locator("#editfil-save").get_attribute("data-mode") == "create"

    # Fill the required fields + save.
    page.locator("#editfil-name").fill("New Filament")
    page.locator("#editfil-material").fill("PLA")
    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)

    url = page.evaluate("() => window.__lastFetchUrl")
    payload = page.evaluate("() => window.__lastFetchPayload")
    assert url == "/api/create_filament"
    assert payload["data"]["name"] == "New Filament"
    assert payload["data"]["material"] == "PLA"


def test_modal_add_mode_requires_material(page: Page):
    """Add-mode Save with empty material should surface an inline error."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openAddFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    page.evaluate("() => window.openAddFilamentForm()")
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)
    # Leave material empty.
    page.locator("#editfil-material").fill("")
    page.locator("#editfil-save").click()
    expect(page.locator("#editfil-error")).to_be_visible()
    text = page.locator("#editfil-error").text_content() or ""
    assert "material" in text.lower()


def test_modal_attr_chip_picker_clicking_known_choice(page: Page):
    """Clicking a known-choice row in the dropdown should add the chip
    WITHOUT firing a POST /api/external/fields/add_choice."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 407, "name": "T", "material": "PLA", "extra": {}}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()

    # Focus the chip input to pop the dropdown, then click a known choice.
    page.locator("#editfil-attr-input").click()
    page.wait_for_selector("#editfil-attr-dropdown .dropdown-item", timeout=3_000)
    page.locator("#editfil-attr-dropdown .dropdown-item[data-value='Silk']").click()

    chip_values = page.evaluate(
        "() => Array.from(document.querySelectorAll('#editfil-attr-chips .editfil-chip'))"
        ".map(c => c.getAttribute('data-value'))"
    )
    assert chip_values == ["Silk"]

    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    # No new-choice POST should have fired for a known tag.
    added = page.evaluate("() => window.__addedChoices")
    assert added == []


def test_modal_attr_chip_picker_adds_new_tag_and_registers_it(page: Page):
    """Typing a brand-new tag and pressing Enter should chip it, POST /api/
    external/fields/add_choice on save, and include the tag in extras."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 408, "name": "T", "material": "PLA", "extra": {}}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()

    # Wait for known choices to load so our typed tag is distinguishable.
    page.wait_for_function("() => document.querySelectorAll('#editfil-attr-dropdown').length > 0")
    page.locator("#editfil-attr-input").click()
    page.locator("#editfil-attr-input").fill("Glossy")
    page.locator("#editfil-attr-input").press("Enter")

    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)

    # Chip present in the payload.
    attrs_raw = page.evaluate("() => window.__lastFetchPayload.data.extra.filament_attributes")
    import json
    assert json.loads(attrs_raw) == ["Glossy"]

    # New-choice registration fired once for the new tag.
    added = page.evaluate("() => window.__addedChoices")
    assert added == [{"entity_type": "filament", "key": "filament_attributes", "new_choice": "Glossy"}]


def test_modal_chip_picker_remove_chip(page: Page):
    """Clicking the × on a chip should remove it from the selected list."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 409, "name": "T", "material": "PLA",
        "extra": {"filament_attributes": '["Silk","Matte"]'},
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()

    # Verify both chips present, then remove the first one.
    page.wait_for_selector("#editfil-attr-chips .editfil-chip")
    page.locator("#editfil-attr-chips .editfil-chip .chip-x").first.click()

    remaining = page.evaluate(
        "() => Array.from(document.querySelectorAll('#editfil-attr-chips .editfil-chip'))"
        ".map(c => c.getAttribute('data-value'))"
    )
    assert remaining == ["Matte"]


def test_create_filament_rejects_missing_material(api_base_url: str):
    r = requests.post(f"{api_base_url}/api/create_filament", json={"data": {"name": "X"}}, timeout=5)
    assert r.status_code == 400
    body = r.json()
    assert body.get("success") is False
    assert "material" in body.get("msg", "").lower()


def test_create_filament_rejects_empty_data(api_base_url: str):
    r = requests.post(f"{api_base_url}/api/create_filament", json={"data": {}}, timeout=5)
    assert r.status_code == 400
    body = r.json()
    assert body.get("success") is False


# ---------------------------------------------------------------------------
# Wave 5 (2026-04-23 pm): combobox keyboard nav, Escape scoping, copy-from-
# vendor button, multi_color_direction routed through extras, Spoolman error
# surfacing.
# ---------------------------------------------------------------------------


def test_modal_vendor_combobox_escape_closes_dropdown_not_modal(page: Page):
    """Escape while the vendor dropdown is open should close the dropdown
    only — the Bootstrap modal must stay visible."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 501, "name": "T", "material": "PLA", "vendor": {"id": 1, "name": "Alpha"}}
    _open_modal_with(page, fil)

    # Focus vendor + clear text to force the full dropdown to render.
    vendor_input = page.locator("#editfil-vendor-name")
    vendor_input.click()
    vendor_input.fill("")
    page.wait_for_selector("#editfil-vendor-dropdown .dropdown-item", timeout=3_000)
    # Dropdown visible, modal visible.
    expect(page.locator("#editfil-vendor-dropdown")).to_be_visible()
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)

    # Escape: dropdown closes, modal stays.
    vendor_input.press("Escape")
    expect(page.locator("#editfil-vendor-dropdown")).to_be_hidden()
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)


def test_modal_attr_chip_escape_closes_dropdown_not_modal(page: Page):
    """Same scoping for the filament-attributes chip picker."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 502, "name": "T", "material": "PLA", "extra": {}}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()

    attr_input = page.locator("#editfil-attr-input")
    attr_input.click()
    page.wait_for_selector("#editfil-attr-dropdown .dropdown-item", timeout=3_000)
    expect(page.locator("#editfil-attr-dropdown")).to_be_visible()

    attr_input.press("Escape")
    expect(page.locator("#editfil-attr-dropdown")).to_be_hidden()
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)


def test_modal_vendor_combobox_keyboard_arrow_and_enter_selects(page: Page):
    """ArrowDown highlights the first option, Enter commits it and sets
    the hidden id — matches the wizard's combobox keyboard contract."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 503, "name": "T", "material": "PLA"}
    _open_modal_with(page, fil)
    vendor_input = page.locator("#editfil-vendor-name")
    vendor_input.click()
    # Wait for the vendors fetch + render.
    page.wait_for_selector("#editfil-vendor-dropdown [data-label='Alpha']", timeout=3_000)

    vendor_input.press("ArrowDown")
    vendor_input.press("Enter")

    # Hidden id should be 1 (Alpha).
    assert page.locator("#editfil-vendor-id").input_value() == "1"
    assert vendor_input.input_value() == "Alpha"


def test_modal_copy_vendor_weight_button(page: Page):
    """When the filament's vendor has an empty_spool_weight, clicking the ⇩
    button on the Specs tab should copy it into the spool-weight input."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 504, "name": "T", "material": "PLA",
        "vendor": {"id": 1, "name": "Alpha", "empty_spool_weight": 185},
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-specs-btn").click()
    expect(page.locator("#editfil-copy-vendor-wt")).to_be_visible()

    # Button should be clickable; clicking copies the value.
    page.locator("#editfil-copy-vendor-wt").click()
    assert page.locator("#editfil-spool-weight").input_value() == "185"


def test_modal_copy_vendor_weight_button_hidden_when_no_vendor_wt(page: Page):
    """No empty_spool_weight on the vendor → button stays hidden."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {"id": 505, "name": "T", "material": "PLA", "vendor": {"id": 1, "name": "Alpha"}}
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-specs-btn").click()
    expect(page.locator("#editfil-copy-vendor-wt")).to_be_hidden()


def test_modal_multi_color_direction_routes_through_extras(page: Page):
    """multi_color_direction was a top-level field; Spoolman's schema rejects
    it there (422). It now lives in extras, wrapped with Spoolman's string
    convention. This test guards the fix."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 506, "name": "Two", "material": "PLA",
        "multi_color_hexes": "ff0000,00ff00",
        "multi_color_direction": "longitudinal",
    }
    _open_modal_with(page, fil)
    page.locator("#editfil-tab-colors-btn").click()
    # Flip the direction.
    page.locator("#editfil-color-direction").select_option(value="coaxial")

    page.locator("#editfil-save").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)
    data = page.evaluate("() => window.__lastFetchPayload.data")
    # Must NOT be a top-level field.
    assert "multi_color_direction" not in data, \
        "multi_color_direction must not be sent as a top-level Spoolman field"
    # Must be in extras with the Spoolman-quoted format.
    assert data["extra"]["multi_color_direction"] == '"coaxial"'


def test_modal_surfaces_spoolman_error_body(page: Page):
    """When /api/update_filament returns a failure payload, the modal's
    error banner should show the actual message (not a generic one)."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    # Stub /api/update_filament to return a specific failure.
    page.evaluate(
        """
        const orig = window.fetch;
        window.fetch = async (url, opts) => {
            if (url === '/api/vendors') {
                return new Response(JSON.stringify({success: true, vendors: []}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/materials') {
                return new Response(JSON.stringify({success: true, materials: []}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/external/fields') {
                return new Response(JSON.stringify({success: true, fields: {filament: [], spool: []}}),
                    {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/update_filament') {
                return new Response(JSON.stringify({
                    success: false,
                    msg: 'Spoolman rejected update: HTTP 422: multi_color_direction is not a valid field'
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        """
    )

    fil = {"id": 507, "name": "T", "material": "PLA"}
    _open_modal_with(page, fil)
    page.locator("#editfil-name").fill("Changed")
    page.locator("#editfil-save").click()

    expect(page.locator("#editfil-error")).to_be_visible()
    text = page.locator("#editfil-error").text_content() or ""
    assert "multi_color_direction" in text or "422" in text
