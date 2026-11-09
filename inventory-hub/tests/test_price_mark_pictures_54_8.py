"""Group 54.8: Derek's pictures of the spool's price box, before and after.

Not a check. The standing order is that no look changes without a sample, so this
draws the wizard's "Pricing & Metadata" section for him and writes the pictures
into review-samples/2026-11-08-group54/ (git-ignored). It runs only when asked:

    G54_PICS=1 G54_PICS_PHASE=before "C:/Python314/python.exe" -m pytest \
        tests/test_price_mark_pictures_54_8.py -p no:cacheprovider -q

(`G54_PICS_PHASE=after` for the build's pictures; the before ones were taken on
the code before 54.8.) Each picture is the wizard's window as it shows on the
1600x1300 dashboard at 1x, cropped to the window's visible part, never scaled:

  1a / 1b  a new spool of a filament priced 25.00, the section closed (its summary)
  2a / 2b  the same, the section open (the price box)
  3a / 3b  an edit of a spool with no price of its own, its filament priced 25.00, closed
  4a / 4b  the same, open
  5        the same edit's empty-weight box: the spool has none of its own, so it
           shows its filament's 200 g with the "from filament" badge, as before
           (only what Save sends changed; taken in both phases, so the two can be
           compared)

The real dashboard on the dev container. The spool and filament the wizard reads
are made up and served in the browser (`/api/spool_details`,
`/api/filament_details`); the wizard's other reads (fields, brands, locations) go
to dev, and every request that isn't a read is answered in the browser
(test_text_size_guard._read_only). Save is never pressed. Nothing reaches dev.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page

import conftest

pytestmark = [
    pytest.mark.skipif(os.environ.get("G54_PICS") != "1",
                       reason="Group 54.8's pictures for Derek: run with G54_PICS=1 (see the docstring)"),
    pytest.mark.usefixtures("require_server"),
]

OUT = Path(__file__).resolve().parents[2] / "review-samples" / "2026-11-08-group54"
PHASE = os.environ.get("G54_PICS_PHASE", "after")
LETTER = {"before": "a", "after": "b"}

FILAMENT = {
    "id": 9002, "name": "Ocean Blue", "material": "PLA", "color_hex": "1E6FD9",
    "density": 1.24, "diameter": 1.75, "weight": 1000.0, "spool_weight": 200.0, "price": 25.0,
    "settings_extruder_temp": 215, "settings_bed_temp": 60, "comment": "", "tags": [],
    "vendor": {"id": 9003, "name": "Example Brand", "extra": {}},
    "extra": {},
}
# A spool with no price and no empty weight of its own: Spoolman leaves a field
# with no value out of the record.
SPOOL = {
    "id": 9001, "archived": False, "location": "", "comment": "", "used_weight": 250.0,
    "initial_weight": 1000.0, "remaining_weight": 750.0, "tags": [], "extra": {},
    "filament": FILAMENT,
}


def _ready(page: Page, base_url: str) -> None:
    from test_text_size_guard import _read_only

    _read_only(page, extra_get={"/api/spool_details": SPOOL, "/api/filament_details": FILAMENT})
    page.goto(base_url)
    page.wait_for_function("() => typeof window.openEditWizard === 'function' && typeof state !== 'undefined'"
                           " && state.locationsLoaded", timeout=45_000)


def _wait_open(page: Page, done_js: str) -> None:
    page.wait_for_selector("#wizardModal.show", timeout=15_000)
    page.wait_for_function(done_js, timeout=15_000)
    conftest.wait_modal_settled(page, "wizardModal")
    page.wait_for_timeout(500)


def _open_section(page: Page, panel_id: str) -> None:
    page.evaluate("(id) => bootstrap.Collapse.getOrCreateInstance(document.getElementById(id),"
                  " { toggle: false }).show()", panel_id)
    page.wait_for_function("(id) => { const p = document.getElementById(id);"
                           " return p.classList.contains('show') && !p.classList.contains('collapsing'); }",
                           arg=panel_id)
    page.wait_for_timeout(700)          # the section's own smooth scroll, when it takes one


def _shot(page: Page, name: str, centre: str) -> Path:
    """The wizard's window as it shows, with `centre` in the middle of the screen."""
    page.mouse.move(2, 2)
    page.evaluate("(s) => document.querySelector(s).scrollIntoView({ block: 'center' })", centre)
    page.wait_for_timeout(400)
    box = page.locator("#wizardModal .modal-content").bounding_box()
    vp = page.viewport_size
    x0, y0 = max(0.0, box["x"]), max(0.0, box["y"])
    x1 = min(float(vp["width"]), box["x"] + box["width"])
    y1 = min(float(vp["height"]), box["y"] + box["height"])
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    page.screenshot(path=str(path), clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
    return path


TOGGLE = 'button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-metadata-panel"]'


def test_pictures_of_a_new_spools_price(page: Page, base_url: str):
    _ready(page, base_url)
    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(9002); }")
    _wait_open(page, "() => document.getElementById('wiz-status-msg').innerText.includes('pre-filled')"
                     " && document.getElementById('wiz-spool-price').value === '25'")
    shots = [_shot(page, f"1{LETTER[PHASE]}-new-spool-closed-{PHASE}.png", TOGGLE)]
    _open_section(page, "wiz-spool-metadata-panel")
    shots.append(_shot(page, f"2{LETTER[PHASE]}-new-spool-open-{PHASE}.png", "#wiz-spool-price"))
    assert all(p.exists() for p in shots), shots
    conftest.close_wizard(page)


def test_pictures_of_an_edited_spools_price_and_empty_weight(page: Page, base_url: str):
    _ready(page, base_url)
    page.evaluate("() => { window.openEditWizard(9001); }")
    _wait_open(page, "() => wizardState.mode === 'edit_spool'"
                     " && document.getElementById('wiz-spool-price').value === '25'"
                     " && !document.getElementById('btn-wiz-submit').disabled")
    shots = [_shot(page, f"3{LETTER[PHASE]}-edit-closed-{PHASE}.png", TOGGLE)]
    _open_section(page, "wiz-spool-metadata-panel")
    shots.append(_shot(page, f"4{LETTER[PHASE]}-edit-open-{PHASE}.png", "#wiz-spool-price"))
    _open_section(page, "wiz-spool-weight-panel")
    assert page.locator("#wiz-spool-empty_weight").input_value() == "200"
    shots.append(_shot(page, f"5-edit-empty-weight-inherited-{PHASE}.png", "#wiz-spool-empty_weight"))
    assert all(p.exists() for p in shots), shots
    conftest.close_wizard(page)
