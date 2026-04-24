"""
Visual regression snapshots for the Edit Filament modal.

Each snapshot exercises one tab with representative data so the modal's
active-tab styling, placeholder visibility, badge rendering, combobox,
chip picker, and max-temp layout are all captured.

Baselines live at inventory-hub/tests/__screenshots__/chromium-1600x1300/
and are PIL-diffed with 1% pixel tolerance. Re-capture with
UPDATE_VISUAL_BASELINES=1 when a visual change is intentional.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _stub_editfil_fetches(page: Page):
    page.evaluate(
        """
        const orig = window.fetch;
        window.fetch = async (url, opts) => {
            const method = (opts && opts.method) || 'GET';
            if (url === '/api/vendors' && method === 'GET') {
                return new Response(JSON.stringify({
                    success: true,
                    vendors: [
                        {id: 1, name: 'Overture', empty_spool_weight: 165},
                        {id: 2, name: 'Polymaker'},
                        {id: 3, name: 'eSUN'}
                    ]
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/materials') {
                return new Response(JSON.stringify({
                    success: true, materials: ['PLA', 'PETG', 'ABS', 'TPU', 'PLA+']
                }), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            if (url === '/api/external/fields') {
                return new Response(JSON.stringify({success: true, fields: {filament: [
                    {key: 'filament_attributes', field_type: 'choice', multi_choice: true,
                     choices: ['Silk', 'Matte', 'Carbon Fiber', 'Glow', 'Shimmer']}
                ], spool: []}}), {status: 200, headers: {'Content-Type': 'application/json'}});
            }
            return orig(url, opts);
        };
        """
    )


def _open_modal(page: Page, fil: dict):
    page.evaluate("(fil) => window.openEditFilamentForm(fil)", fil)
    expect(page.locator("#editFilamentModal.show")).to_have_count(1)
    # Let fetches + renders settle before screenshotting.
    page.wait_for_timeout(400)


def test_editfilament_basic_tab_snapshot(page: Page, snapshot):
    """Basic tab: name, material+badge, vendor+info pill, nozzle/bed area (moved
    back to Specs so Basic shows original_color + attribute chips instead)."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 900, "name": "Silk Gold", "material": "PLA",
        "vendor": {"id": 1, "name": "Overture", "empty_spool_weight": 165},
        "comment": "Fan: On",
        "extra": {
            "original_color": '"Silk Gold"',
            "filament_attributes": '["Silk","Shimmer"]',
        },
    }
    _open_modal(page, fil)
    snapshot(page.locator("#editFilamentModal .modal-content"), "editfil-basic-tab")


def test_editfilament_specs_tab_snapshot(page: Page, snapshot):
    """Specs tab: spool weight w/ Use-Vendor button, density, diameter, net
    weight, price (placeholder visible), nozzle min+max, bed min+max."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 901, "name": "Test", "material": "PLA",
        "vendor": {"id": 1, "name": "Overture", "empty_spool_weight": 165},
        "spool_weight": 150, "density": 1.24,
        "diameter": 1.75, "weight": 1000,
        "settings_extruder_temp": 210, "settings_bed_temp": 60,
        "extra": {"nozzle_temp_max": '"230"', "bed_temp_max": '"70"'},
    }
    _open_modal(page, fil)
    page.locator("#editfil-tab-specs-btn").click()
    page.wait_for_timeout(250)
    snapshot(page.locator("#editFilamentModal .modal-content"), "editfil-specs-tab")


def test_editfilament_colors_tab_snapshot(page: Page, snapshot):
    """Colors tab: primary row + 3 extras + direction selector visible."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 902, "name": "Rainbow", "material": "PLA",
        "multi_color_hexes": "ff0000,00ff00,0000ff,ff00ff",
        "multi_color_direction": "coaxial",
    }
    _open_modal(page, fil)
    page.locator("#editfil-tab-colors-btn").click()
    page.wait_for_timeout(250)
    snapshot(page.locator("#editFilamentModal .modal-content"), "editfil-colors-tab")


def test_editfilament_advanced_tab_snapshot(page: Page, snapshot):
    """Advanced tab: URLs + legacy ID (now that original_color + attributes
    moved to Basic, Advanced is just metadata links)."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    _stub_editfil_fetches(page)

    fil = {
        "id": 903, "name": "Test", "material": "PLA",
        "external_id": "LEGACY-42",
        "extra": {
            "product_url": '"https://vendor.example/product"',
            "purchase_url": '"https://shop.example/buy"',
            "sheet_link": '"https://docs.example/sheet"',
        },
    }
    _open_modal(page, fil)
    page.locator("#editfil-tab-advanced-btn").click()
    page.wait_for_timeout(250)
    snapshot(page.locator("#editFilamentModal .modal-content"), "editfil-advanced-tab")
