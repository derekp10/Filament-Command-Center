"""Filament attributes (the `extra.filament_attributes` chip list) should
render read-only on BOTH the Filament Details modal and the Spool Details
modal (Derek 2026-05-28: "Assigned filament attributes should appear in the
spool detail modal as well as the filament modal").

These tests mock `/api/spool_details` and `/api/filament_details` so the chip
rendering is exercised deterministically regardless of whether the dev
environment happens to have any filaments tagged with attributes.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect


def _route_json(page: Page, url_glob: str, payload: dict):
    page.route(
        url_glob,
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        ),
    )


def _spool_payload(attrs):
    """Minimal spool_details payload with a parent filament carrying `attrs`
    in extra.filament_attributes. `attrs` may be a list (native JSON) or a
    JSON-string to mirror how Spoolman quotes choice-multi extras."""
    return {
        "id": 999001,
        "archived": False,
        "location": "Room LR",
        "comment": "",
        "used_weight": 100.0,
        "remaining_weight": 900.0,
        "extra": {},
        "filament": {
            "id": 555001,
            "name": "Test Color",
            "material": "PLA",
            "color_hex": "ff8800",
            "weight": 1000,
            "settings_extruder_temp": 210,
            "settings_bed_temp": 60,
            "vendor": {"name": "TestVendor"},
            "extra": {"filament_attributes": attrs},
        },
    }


def _filament_payload(attrs):
    return {
        "id": 555002,
        "name": "Test Color 2",
        "material": "PETG",
        "color_hex": "0088ff",
        "density": 1.27,
        "weight": 1000,
        "settings_extruder_temp": 230,
        "settings_bed_temp": 80,
        "vendor": {"name": "TestVendor"},
        "extra": {"filament_attributes": attrs},
    }


def _boot(page: Page, base_url: str, reset_dom_state_js: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.evaluate(reset_dom_state_js)


@pytest.mark.usefixtures("require_server")
def test_spool_details_modal_renders_attribute_chips(page: Page, base_url: str, reset_dom_state_js: str):
    _route_json(page, "**/api/spool_details*", _spool_payload(["Matte", "Recycled"]))
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof openSpoolDetails === 'function' && modals && modals.spoolModal", timeout=10000)
    page.evaluate("openSpoolDetails(999001)")
    expect(page.locator("#spoolModal")).to_be_visible(timeout=5000)

    row = page.locator("#spool-detail-attributes-row")
    expect(row).to_be_visible(timeout=3000)
    chips = page.locator("#spool-detail-attributes .fcc-attr-chip")
    expect(chips).to_have_count(2)
    assert chips.nth(0).inner_text().strip() == "Matte"
    assert chips.nth(1).inner_text().strip() == "Recycled"


@pytest.mark.usefixtures("require_server")
def test_spool_details_modal_hides_attribute_row_when_none(page: Page, base_url: str, reset_dom_state_js: str):
    _route_json(page, "**/api/spool_details*", _spool_payload([]))
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof openSpoolDetails === 'function' && modals && modals.spoolModal", timeout=10000)
    page.evaluate("openSpoolDetails(999001)")
    expect(page.locator("#spoolModal")).to_be_visible(timeout=5000)

    expect(page.locator("#spool-detail-attributes-row")).to_be_hidden()


@pytest.mark.usefixtures("require_server")
def test_filament_details_modal_renders_attribute_chips(page: Page, base_url: str, reset_dom_state_js: str):
    # JSON-string form (how Spoolman serializes a choice-multi extra on the
    # wire) to prove parseFilamentAttributes handles the quoted-array case too.
    _route_json(page, "**/api/filament_details*", _filament_payload(json.dumps(["Silk", "Glow", "PLA+"])))
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof openFilamentDetails === 'function' && modals && modals.filamentModal", timeout=10000)
    page.evaluate("openFilamentDetails(555002)")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)

    row = page.locator("#fil-detail-attributes-row")
    expect(row).to_be_visible(timeout=3000)
    chips = page.locator("#fil-detail-attributes .fcc-attr-chip")
    expect(chips).to_have_count(3)
    assert [chips.nth(i).inner_text().strip() for i in range(3)] == ["Silk", "Glow", "PLA+"]


@pytest.mark.usefixtures("require_server")
def test_filament_details_modal_hides_attribute_row_when_none(page: Page, base_url: str, reset_dom_state_js: str):
    _route_json(page, "**/api/filament_details*", _filament_payload(""))
    _boot(page, base_url, reset_dom_state_js)
    page.wait_for_function("typeof openFilamentDetails === 'function' && modals && modals.filamentModal", timeout=10000)
    page.evaluate("openFilamentDetails(555002)")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)

    expect(page.locator("#fil-detail-attributes-row")).to_be_hidden()
