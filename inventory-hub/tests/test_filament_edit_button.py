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


def test_openEditFilamentForm_has_vendor_and_color_inputs(page: Page):
    """Both Vendor dropdown and Color hex fields should be rendered."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {
        "id": 101,
        "name": "Green",
        "material": "PLA",
        "color_hex": "00ff00",
        "vendor": {"id": 1, "name": "TestVendor"},
    }
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-name", state="visible", timeout=3_000)

    expect(page.locator("#edit-fil-vendor")).to_have_count(1)
    expect(page.locator("#edit-fil-color-picker")).to_have_count(1)
    expect(page.locator("#edit-fil-color-hex")).to_have_count(1)

    # color_hex input should be pre-populated with #rrggbb from the raw hex.
    hex_val = page.locator("#edit-fil-color-hex").input_value()
    assert hex_val.lower() == "#00ff00", f"expected #00ff00, got {hex_val!r}"

    # color picker should match.
    picker_val = page.locator("#edit-fil-color-picker").input_value()
    assert picker_val.lower() == "#00ff00"


def test_openEditFilamentForm_color_picker_syncs_hex_field(page: Page):
    """Changing the <input type=color> should update the hex text field."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {"id": 102, "name": "Test", "material": "PLA", "color_hex": "000000"}
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-color-picker", state="visible", timeout=3_000)

    # Simulate the color picker changing value and dispatching the input event
    # (page.locator.fill doesn't trigger color-picker 'input' cleanly in headless).
    page.evaluate(
        """
        const p = document.querySelector('#edit-fil-color-picker');
        p.value = '#ff00aa';
        p.dispatchEvent(new Event('input', {bubbles: true}));
        """
    )
    hex_val = page.locator("#edit-fil-color-hex").input_value()
    assert hex_val.lower() == "#ff00aa"


def test_openEditFilamentForm_submits_vendor_and_color_changes(page: Page):
    """Changing vendor and color should include them in the dirty-diff POST body."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    # Stub /api/vendors so we get a known set of options regardless of live data.
    page.evaluate(
        """
        window.__lastFetchPayload = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            if (url === '/api/vendors') {
                return new Response(JSON.stringify({
                    success: true,
                    vendors: [{id: 1, name: 'Alpha'}, {id: 2, name: 'Beta'}]
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/update_filament') {
                window.__lastFetchPayload = JSON.parse(opts.body);
                return new Response(JSON.stringify({success: true, filament: {id: 55}}), {
                    status: 200, headers: {'Content-Type': 'application/json'}
                });
            }
            return origFetch(url, opts);
        };
        """
    )

    fil = {
        "id": 55,
        "name": "OldName",
        "material": "PLA",
        "color_hex": "112233",
        "vendor": {"id": 1, "name": "Alpha"},
    }
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-vendor", state="visible", timeout=3_000)
    # <option> elements are never 'visible' in Playwright; wait for the DOM node via JS.
    page.wait_for_function(
        "document.querySelector(\"#edit-fil-vendor option[value='2']\") !== null",
        timeout=3_000,
    )

    # Change vendor to Beta (id=2) and color to #aabbcc.
    page.locator("#edit-fil-vendor").select_option(value="2")
    page.locator("#edit-fil-color-hex").fill("#aabbcc")

    page.locator(".swal2-confirm").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)

    payload = page.evaluate("() => window.__lastFetchPayload")
    assert payload["id"] == 55
    data = payload["data"]
    # Only vendor_id and color_hex should have changed.
    assert set(data.keys()) == {"vendor_id", "color_hex"}, f"unexpected keys: {set(data.keys())}"
    assert data["vendor_id"] == 2
    assert data["color_hex"] == "aabbcc"


def test_openEditFilamentForm_rejects_invalid_hex(page: Page):
    """preConfirm should surface a validation message on bad hex input."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {"id": 99, "name": "Test", "material": "PLA", "color_hex": "112233"}
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-color-hex", state="visible", timeout=3_000)

    page.locator("#edit-fil-color-hex").fill("not-a-color")
    page.locator(".swal2-confirm").click()

    # Swal renders the validation message in .swal2-validation-message.
    page.wait_for_selector(".swal2-validation-message", timeout=3_000)
    msg = page.locator(".swal2-validation-message").text_content() or ""
    assert "hex" in msg.lower() or "color" in msg.lower()


# ---------------------------------------------------------------------------
# Wave 1 expansion: diameter/weight/price/external_id + multi-color.
# ---------------------------------------------------------------------------


def _stub_vendors_and_update(page):
    """Install fetch stubs for /api/vendors and /api/update_filament so the
    Edit Filament tests don't mutate live Spoolman."""
    page.evaluate(
        """
        window.__lastFetchPayload = null;
        const origFetch = window.fetch;
        window.fetch = async (url, opts) => {
            if (url === '/api/vendors') {
                return new Response(JSON.stringify({success: true, vendors: []}),
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


def test_openEditFilamentForm_has_diameter_weight_price_external_id(page: Page):
    """Wave 1 added four new top-level Spoolman default fields."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {
        "id": 201,
        "name": "Test",
        "material": "PLA",
        "diameter": 1.75,
        "weight": 1000,
        "price": 24.99,
        "external_id": "LEGACY-42",
    }
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-diameter", state="visible", timeout=3_000)

    assert page.locator("#edit-fil-diameter").input_value() == "1.75"
    assert page.locator("#edit-fil-weight").input_value() == "1000"
    assert page.locator("#edit-fil-price").input_value() == "24.99"
    assert page.locator("#edit-fil-external-id").input_value() == "LEGACY-42"


def test_openEditFilamentForm_submits_diameter_weight_price_external_id(page: Page):
    """Changing the new fields should include them in the dirty-diff POST body."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_vendors_and_update(page)

    fil = {
        "id": 202,
        "name": "Test",
        "material": "PLA",
        "diameter": 1.75,
        "weight": 1000,
        "price": 10.00,
        "external_id": "OLD",
    }
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-diameter", state="visible", timeout=3_000)

    page.locator("#edit-fil-diameter").fill("2.85")
    page.locator("#edit-fil-weight").fill("750")
    page.locator("#edit-fil-price").fill("15.50")
    page.locator("#edit-fil-external-id").fill("NEW-ID")

    page.locator(".swal2-confirm").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)

    payload = page.evaluate("() => window.__lastFetchPayload")
    data = payload["data"]
    assert data["diameter"] == 2.85
    assert data["weight"] == 750
    assert data["price"] == 15.5
    assert data["external_id"] == "NEW-ID"


def test_openEditFilamentForm_seeds_multi_color_from_multi_color_hexes(page: Page):
    """A filament with multi_color_hexes should render as primary + extras."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {
        "id": 203,
        "name": "Rainbow",
        "material": "PLA",
        "multi_color_hexes": "ff0000,00ff00,0000ff",
        "multi_color_direction": "coaxial",
    }
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-color-hex", state="visible", timeout=3_000)

    # Primary shows first hex.
    assert page.locator("#edit-fil-color-hex").input_value().lower() == "#ff0000"

    # Two extra rows for the remaining two hexes.
    extras = page.locator("#edit-fil-color-extras .edit-fil-color-row")
    assert extras.count() == 2

    # Direction select should be visible with coaxial selected.
    direction = page.locator("#edit-fil-color-direction")
    assert direction.is_visible()
    assert direction.input_value() == "coaxial"


def test_openEditFilamentForm_add_color_button_appends_row(page: Page):
    """The + button should add a new color row and reveal the direction select."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {"id": 204, "name": "Mono", "material": "PLA", "color_hex": "ff00ff"}
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-add-color", state="visible", timeout=3_000)

    # Direction starts hidden (only 1 color).
    assert not page.locator("#edit-fil-color-direction").is_visible()

    # Click +. One extra row appears, direction becomes visible.
    page.locator("#edit-fil-add-color").click()
    assert page.locator("#edit-fil-color-extras .edit-fil-color-row").count() == 1
    assert page.locator("#edit-fil-color-direction").is_visible()


def test_openEditFilamentForm_submits_multi_color_csv(page: Page):
    """Adding a second color should emit multi_color_hexes + direction in the POST."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_vendors_and_update(page)

    fil = {"id": 205, "name": "Mono", "material": "PLA", "color_hex": "ff0000"}
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-add-color", state="visible", timeout=3_000)

    page.locator("#edit-fil-add-color").click()
    # Fill the new extra's hex input (id depends on counter — query by class).
    extra_hex = page.locator("#edit-fil-color-extras input[id^='edit-fil-color-hex-']").first
    extra_hex.fill("#00ff00")
    # Pick direction.
    page.locator("#edit-fil-color-direction").select_option(value="coaxial")

    page.locator(".swal2-confirm").click()
    page.wait_for_function("window.__lastFetchPayload !== null", timeout=3_000)

    payload = page.evaluate("() => window.__lastFetchPayload")
    data = payload["data"]
    # CSV is lowercase, no-hash, in the order they appear.
    assert data["multi_color_hexes"] == "ff0000,00ff00"
    assert data["multi_color_direction"] == "coaxial"


def test_openEditFilamentForm_remove_extra_color_hides_direction(page: Page):
    """Removing the last extra color row should hide the direction select again."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")

    fil = {
        "id": 206,
        "name": "Two",
        "material": "PLA",
        "multi_color_hexes": "ff0000,00ff00",
        "multi_color_direction": "longitudinal",
    }
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    page.wait_for_selector("#edit-fil-color-extras .edit-fil-color-row", timeout=3_000)

    assert page.locator("#edit-fil-color-direction").is_visible()
    # Click the remove button on the one extra row.
    page.locator("#edit-fil-color-extras .edit-fil-color-row button").click()
    # Row is gone, direction select hidden.
    assert page.locator("#edit-fil-color-extras .edit-fil-color-row").count() == 0
    assert not page.locator("#edit-fil-color-direction").is_visible()
