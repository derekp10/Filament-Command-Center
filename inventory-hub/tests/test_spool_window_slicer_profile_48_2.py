"""Group 48.2 — the filament's slicer profile on the spool window.

Derek, 2026-10-19: "I wanted to see what spool profile I should use … only to
find that I have to open the spool, click the swatch button, then find the
profile suggestion there." His answer: read-only on the spool window, saying it
comes from the filament (so he knows to edit it there). The note opens the
filament window.

Stubbed /api/spool_details and /api/filament_details (the pattern of
test_detail_modal_attributes.py), so dev data can't change what is drawn.
Base proof (52741e6): the row doesn't exist there, so every test fails.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.usefixtures("require_server")


def _route_json(page: Page, url_glob: str, payload: dict):
    page.route(url_glob, lambda route: route.fulfill(status=200, content_type="application/json",
                                                     body=json.dumps(payload)))


def _spool(profile):
    extra = {} if profile is None else {"slicer_profile": profile}
    return {"id": 999001, "archived": False, "location": "Room LR", "comment": "", "used_weight": 100.0,
            "remaining_weight": 900.0, "extra": {},
            "filament": {"id": 555001, "name": "Galaxy Black", "material": "PLA", "color_hex": "222222",
                         "weight": 1000, "vendor": {"name": "Prusament"}, "extra": extra}}


def _open(page: Page, base_url: str, profile):
    _route_json(page, "**/api/spool_details*", _spool(profile))
    page.goto(base_url)
    page.wait_for_function("typeof openSpoolDetails === 'function' && modals && modals.spoolModal", timeout=10000)
    page.evaluate("openSpoolDetails(999001)")
    expect(page.locator("#spoolModal")).to_be_visible(timeout=5000)


@pytest.mark.parametrize("profile", ['"Prusament PLA"', "Prusament PLA"], ids=["json-quoted", "plain"])
def test_the_profile_shows_from_the_filament(page: Page, base_url: str, profile):
    _open(page, base_url, profile)
    expect(page.locator("#spool-detail-slicer-profile")).to_have_text("Prusament PLA")
    expect(page.locator("#spool-detail-slicer-profile-src")).to_have_text("(from the filament)")


def test_a_blank_profile_reads_dashes(page: Page, base_url: str):
    _open(page, base_url, None)
    expect(page.locator("#spool-detail-slicer-profile")).to_have_text("--")


def test_the_note_opens_the_filament_window_where_it_is_edited(page: Page, base_url: str):
    _route_json(page, "**/api/filament_details*", {
        "id": 555001, "name": "Galaxy Black", "material": "PLA", "color_hex": "222222", "weight": 1000,
        "vendor": {"name": "Prusament", "id": 3}, "extra": {"slicer_profile": '"Prusament PLA"'}})
    _open(page, base_url, '"Prusament PLA"')
    # A real button: Tab reaches it and Space presses it. (Enter can't: the scan
    # accumulator in scripts.html preventDefaults every Enter outside a text
    # field, app-wide, so a scanner's Enter never presses a focused button.)
    page.locator("#spool-detail-slicer-profile-src").focus()
    page.keyboard.press("Space")
    expect(page.locator("#filamentModal")).to_be_visible(timeout=5000)
    expect(page.locator("#fil-detail-slicer-profile")).to_have_text("Prusament PLA")
    expect(page.locator("#spoolModal")).to_be_hidden(timeout=5000)
