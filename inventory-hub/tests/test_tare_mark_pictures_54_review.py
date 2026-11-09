"""Group 54 review (L1): Derek's pictures of the closed Weight & Scale summary, before
and after it marks an inherited empty weight.

Not a check. The standing order is that no look changes without a sample, so this
draws the wizard's two spool sections closed, Weight & Scale above Pricing &
Metadata, and writes the pictures into review-samples/2026-11-08-group54/
(git-ignored). It runs only when asked:

    G54_TARE_PICS=1 G54_PICS_PHASE=before "C:/Python314/python.exe" -m pytest \
        tests/test_tare_mark_pictures_54_review.py -p no:cacheprovider -q

(`G54_PICS_PHASE=after` for the build's pictures; the before ones were taken on
the code before L1, at 76a39af.) It writes only these four, never 54.8's:

  6a / 6b  Edit Spool of a spool with no price and no empty weight of its own
           (its filament: 25.00 and 200 g), both sections closed
  7a / 7b  a new spool of that filament (the filament window's New Spool), both
           sections closed

Each picture is the wizard's window as it shows on the 1600x1300 dashboard at 1x,
cropped to the window's visible part, never scaled. The real dashboard on the dev
container; the spool and filament the wizard reads are made up and served in the
browser, the wizard's other reads go to dev, and every request that isn't a read is
answered in the browser (test_text_size_guard._read_only). Save is never pressed.
Nothing reaches dev.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page

import conftest

pytestmark = [
    pytest.mark.skipif(os.environ.get("G54_TARE_PICS") != "1",
                       reason="The Group 54 review's L1 pictures for Derek: run with G54_TARE_PICS=1 (see the docstring)"),
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
# No price and no empty weight of its own: Spoolman leaves a field with no value out.
SPOOL = {
    "id": 9001, "archived": False, "location": "", "comment": "", "used_weight": 250.0,
    "initial_weight": 1000.0, "remaining_weight": 750.0, "tags": [], "extra": {},
    "filament": FILAMENT,
}
WEIGHT_TOGGLE = 'button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-weight-panel"]'
PRICE_TOGGLE = 'button.fcc-wiz-section-toggle[data-bs-target="#wiz-spool-metadata-panel"]'


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


def _both_closed(page: Page) -> None:
    for panel in ("wiz-spool-weight-panel", "wiz-spool-metadata-panel"):
        assert page.evaluate("(id) => !document.getElementById(id).classList.contains('show')", panel), panel


def _shot(page: Page, name: str) -> Path:
    """The wizard's window as it shows, the Weight & Scale toggle in the middle of
    the screen, the Pricing & Metadata toggle under it."""
    page.mouse.move(2, 2)
    page.evaluate("(s) => document.querySelector(s).scrollIntoView({ block: 'center' })", WEIGHT_TOGGLE)
    page.wait_for_timeout(400)
    assert page.locator(PRICE_TOGGLE).is_visible()
    box = page.locator("#wizardModal .modal-content").bounding_box()
    vp = page.viewport_size
    x0, y0 = max(0.0, box["x"]), max(0.0, box["y"])
    x1 = min(float(vp["width"]), box["x"] + box["width"])
    y1 = min(float(vp["height"]), box["y"] + box["height"])
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    page.screenshot(path=str(path), clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
    return path


def _summaries(page: Page) -> list:
    return [page.locator(f"{t} .fcc-wiz-section-summary").inner_text().strip() for t in (WEIGHT_TOGGLE, PRICE_TOGGLE)]


def test_picture_of_an_edits_closed_sections(page: Page, base_url: str):
    _ready(page, base_url)
    page.evaluate("() => { window.openEditWizard(9001); }")
    _wait_open(page, "() => wizardState.mode === 'edit_spool'"
                     " && document.getElementById('wiz-spool-empty_weight').value === '200'"
                     " && !document.getElementById('btn-wiz-submit').disabled")
    _both_closed(page)
    shot = _shot(page, f"6{LETTER[PHASE]}-edit-closed-tare-{PHASE}.png")
    print(PHASE, "edit:", _summaries(page))
    assert shot.exists(), shot
    conftest.close_wizard(page)


def test_picture_of_a_new_spools_closed_sections(page: Page, base_url: str):
    _ready(page, base_url)
    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(9002); }")
    _wait_open(page, "() => document.getElementById('wiz-status-msg').innerText.includes('pre-filled')"
                     " && document.getElementById('wiz-spool-empty_weight').value === '200'")
    _both_closed(page)
    shot = _shot(page, f"7{LETTER[PHASE]}-new-spool-closed-tare-{PHASE}.png")
    print(PHASE, "new spool:", _summaries(page))
    assert shot.exists(), shot
    conftest.close_wizard(page)
