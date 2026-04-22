"""
Tests for perform_smart_move preserving physical_source when a spool is
moved to the toolhead it's already on, and for the Quick-Swap grid
showing spool info on each button.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest
import requests
from playwright.sync_api import Page, expect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logic  # noqa: E402


# ---------------------------------------------------------------------------
# perform_smart_move — deployed-flag preservation
# ---------------------------------------------------------------------------

def _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured):
    """Install the minimum set of mocks perform_smart_move needs."""
    def _fake_update(sid, data):
        captured['update'] = (sid, data)
        return {"id": sid, **data}

    mocks = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_data),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "Test Spool", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=_fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    return mocks


def test_perform_smart_move_preserves_physical_source_when_already_deployed():
    """Spool is already at XL-4 with physical_source=LR-MDB-1:2. Moving to
    XL-4 again (e.g. user scanned toolhead to 'confirm') must NOT overwrite
    physical_source with XL-4 — that would kill the deployed flag."""
    printer_map = {"XL-4": {"printer_name": "🦝 XL", "position": 3}}
    loc_list = [{"LocationID": "XL-4", "Type": "Tool Head", "Max Spools": "1"}]
    spool_data = {
        "id": 77, "location": "XL-4",
        "extra": {
            "physical_source": "LR-MDB-1",
            "physical_source_slot": "2",
            "container_slot": "",
        }
    }
    captured = {}
    ctx = _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured)
    for m in ctx: m.start()
    try:
        result = logic.perform_smart_move("XL-4", [77], target_slot=None, origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    assert result["status"] == "success"
    sid, patch_data = captured['update']
    assert sid == 77
    # THE regression: physical_source must remain LR-MDB-1 (the original
    # box), not get overwritten to XL-4.
    assert patch_data["extra"]["physical_source"] == "LR-MDB-1"
    assert patch_data["extra"]["physical_source_slot"] == "2"


def test_perform_smart_move_sets_physical_source_on_first_deploy():
    """Spool is at PM-DB-1. Moving to XL-1 should set physical_source=PM-DB-1
    (the actual origin). This is the normal fresh-deploy case."""
    printer_map = {"XL-1": {"printer_name": "🦝 XL", "position": 0}}
    loc_list = [{"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"}]
    spool_data = {
        "id": 42, "location": "PM-DB-1",
        "extra": {"container_slot": "1"}
    }
    captured = {}
    ctx = _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured)
    for m in ctx: m.start()
    try:
        logic.perform_smart_move("XL-1", [42], target_slot=None, origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    _, patch_data = captured['update']
    # physical_source should be set to the original box.
    assert patch_data["extra"]["physical_source"] == "PM-DB-1"
    assert patch_data["extra"]["physical_source_slot"] == "1"


def test_perform_smart_move_overwrites_source_when_moving_to_a_different_toolhead():
    """Spool deployed to XL-3 (physical_source=LR-MDB-1:1). User moves it to
    XL-1. physical_source should update to XL-3 (the spool's current location
    before this move), not stay at LR-MDB-1. Otherwise Return-to-Slot would
    send it to the wrong box."""
    printer_map = {
        "XL-1": {"printer_name": "🦝 XL", "position": 0},
        "XL-3": {"printer_name": "🦝 XL", "position": 2},
    }
    loc_list = [
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
    ]
    spool_data = {
        "id": 99, "location": "XL-3",
        "extra": {
            "physical_source": "LR-MDB-1",
            "physical_source_slot": "1",
            "container_slot": "",
        }
    }
    captured = {}
    ctx = _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured)
    for m in ctx: m.start()
    try:
        logic.perform_smart_move("XL-1", [99], target_slot=None, origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    _, patch_data = captured['update']
    # Moving from XL-3 → XL-1 is a fresh move, not a re-deploy to same place.
    # physical_source tracks where-from, which is now XL-3.
    assert patch_data["extra"]["physical_source"] == "XL-3"


# ---------------------------------------------------------------------------
# Quick-Swap grid — spool info on each button
# ---------------------------------------------------------------------------

TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_and_live(api_base_url):
    """Bind PM-DB-1 slot 1 → XL-1, skip the test if PM-DB-1 is empty so
    we can assert on the rendered spool info."""
    snap = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": TEST_TOOLHEAD}},
        timeout=5,
    )
    contents = requests.get(f"{api_base_url}/api/get_contents?id={TEST_BOX}", timeout=5).json()
    has_slot_1 = any(str(it.get("slot", "")).replace('"', '').strip() == "1"
                     for it in contents or [])
    if not has_slot_1:
        # Put the binding back the way it was and skip.
        requests.put(
            f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
            json={"slot_targets": original},
            timeout=5,
        )
        pytest.skip(f"{TEST_BOX} slot 1 is empty; can't exercise spool-info rendering.")
    yield
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": original},
        timeout=5,
    )


@pytest.mark.usefixtures("require_server", "bound_and_live")
def test_quickswap_button_shows_spool_info_when_slot_loaded(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(500)
    page.evaluate(f"window.openManage({TEST_TOOLHEAD!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(1200)  # give the fetch chain time to finish
    btn = page.locator(f".fcc-qs-slot[data-box='{TEST_BOX}'][data-slot='1']").first
    expect(btn).to_be_visible(timeout=3000)
    text = btn.inner_text()
    # Either a spool ID (#<n>) or a filament name — "empty slot" means we
    # failed to surface spool info.
    assert "empty slot" not in text.lower(), (
        f"Button text didn't surface spool info: {text!r}"
    )


@pytest.mark.usefixtures("require_server", "clean_buffer")
def test_quickswap_button_disabled_when_slot_empty(page: Page, base_url: str, api_base_url):
    # Bind a slot that's known to be empty, verify the rendered button is
    # disabled and no-ops on click. Note: the button is only disabled when
    # BOTH the slot AND the user's buffer are empty — a buffered spool
    # flips the same button into a Deposit target.
    victim_box, victim_slot = "PM-DB-2", "1"
    contents = requests.get(f"{api_base_url}/api/get_contents?id={victim_box}", timeout=5).json()
    has_spool = any(str(it.get("slot", "")).replace('"', '').strip() == victim_slot
                    for it in contents or [])
    if has_spool:
        pytest.skip(f"{victim_box} slot {victim_slot} has a spool; can't test empty-slot rendering.")
    snap = requests.get(f"{api_base_url}/api/dryer_box/{victim_box}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    requests.put(
        f"{api_base_url}/api/dryer_box/{victim_box}/bindings",
        json={"slot_targets": {victim_slot: TEST_TOOLHEAD}},
        timeout=5,
    )
    try:
        page.goto(base_url)
        page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
        page.wait_for_timeout(500)
        page.evaluate(f"window.openManage({TEST_TOOLHEAD!r})")
        expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
        # Force an empty buffer before asserting disabled — otherwise a
        # buffered spool would enable the same button as a Deposit target.
        page.evaluate("() => { state.heldSpools = []; if (window.renderBuffer) window.renderBuffer(); }")
        page.wait_for_timeout(1200)
        btn = page.locator(f".fcc-qs-slot[data-box='{victim_box}'][data-slot='{victim_slot}']").first
        expect(btn).to_be_visible(timeout=3000)
        expect(btn).to_be_disabled()
    finally:
        requests.put(
            f"{api_base_url}/api/dryer_box/{victim_box}/bindings",
            json={"slot_targets": original},
            timeout=5,
        )
