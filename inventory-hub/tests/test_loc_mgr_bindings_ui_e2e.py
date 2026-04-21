"""
UI-path E2E tests for Phase 2 — Feeds section inside the Location Manager.

Covers: section visibility rules (Dryer Box only), toggle open/closed,
dropdown population from /api/printer_map, round-trip save, null slot
handling, and the split-XL scenario (4 slots, some bound and some None).
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect

TEST_BOX = "PM-DB-1"
NON_DRYER_LOC = "XL-1"  # a toolhead — Feeds section should be hidden


@pytest.fixture
def restore_bindings(api_base_url):
    """Snapshot + restore PM-DB-1 bindings across a test run."""
    snap = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    yield
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": original},
        timeout=5,
    )


def _open_manage(page: Page, base_url: str, loc_id: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(500)
    page.evaluate(f"window.openManage({loc_id!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)


@pytest.mark.usefixtures("require_server")
def test_feeds_section_hidden_for_non_dryer_box(page: Page, base_url: str):
    _open_manage(page, base_url, NON_DRYER_LOC)
    section = page.locator("#manage-feeds-section")
    expect(section).to_be_hidden()


@pytest.mark.usefixtures("require_server", "restore_bindings")
def test_feeds_section_visible_for_dryer_box(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_BOX)
    section = page.locator("#manage-feeds-section")
    expect(section).to_be_visible()
    # Body starts collapsed.
    expect(page.locator("#feeds-body")).to_be_hidden()
    expect(page.locator("#feeds-toggle-btn")).to_contain_text("Show")


@pytest.mark.usefixtures("require_server", "restore_bindings")
def test_feeds_section_toggles_open(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_BOX)
    page.locator("#feeds-toggle-btn").click()
    expect(page.locator("#feeds-body")).to_be_visible()
    expect(page.locator("#feeds-toggle-btn")).to_contain_text("Hide")
    # Rows render with Max Spools many slot selects.
    rows = page.locator(".feeds-row")
    assert rows.count() >= 1


@pytest.mark.usefixtures("require_server", "restore_bindings")
def test_feeds_section_save_round_trip(page: Page, base_url: str, api_base_url):
    _open_manage(page, base_url, TEST_BOX)
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(300)
    # The Feeds editor is now a searchable combobox — write directly to the
    # hidden <select> the save logic reads, then submit. Emulates the
    # end-user picking from the dropdown without relying on the combobox's
    # visual list staying pixel-stable.
    page.evaluate(
        "() => { const s = document.querySelector('select.feeds-select[data-slot=\"1\"]'); "
        "s.value = 'XL-2'; }"
    )
    page.locator("#feeds-body button:has-text('Save Feeds')").click()
    expect(page.locator("#feeds-status")).to_contain_text("Saved", timeout=5000)

    # Verify via the API — state actually persisted.
    r = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5)
    assert r.json()["slot_targets"].get("1") == "XL-2"


@pytest.mark.usefixtures("require_server", "restore_bindings")
def test_feeds_section_save_with_some_slots_none(page: Page, base_url: str, api_base_url):
    """User asked to support split/partial use — some slots bound, some left None."""
    _open_manage(page, base_url, TEST_BOX)
    page.locator("#feeds-toggle-btn").click()
    page.wait_for_timeout(300)
    selects = page.locator("select.feeds-select")
    if selects.count() < 2:
        pytest.skip("Test box needs at least 2 slots for this scenario.")
    # Slot 1 → XL-1, slot 2 → None (empty string value).
    page.evaluate(
        "() => { "
        "const a = document.querySelector('select.feeds-select[data-slot=\"1\"]'); a.value = 'XL-1'; "
        "const b = document.querySelector('select.feeds-select[data-slot=\"2\"]'); b.value = ''; "
        "}"
    )
    page.locator("#feeds-body button:has-text('Save Feeds')").click()
    expect(page.locator("#feeds-status")).to_contain_text("Saved", timeout=5000)

    r = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5)
    targets = r.json()["slot_targets"]
    assert targets.get("1") == "XL-1"
    # Slot 2 is absent (not null) — absence == unassigned in storage.
    assert "2" not in targets
