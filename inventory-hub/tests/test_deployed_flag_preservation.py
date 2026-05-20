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


def test_perform_smart_move_auto_deploys_when_slot_is_bound():
    """Regression + centralization guard: when perform_smart_move drops a
    spool into a Dryer Box slot that's bound to a toolhead, the function
    itself must chain a second move to ghost-deploy onto the toolhead.
    Previously this logic lived only in api_identify_scan's assignment
    branch, so non-scan callers (manage_contents, feeds editor, etc.)
    silently skipped the deploy. This test covers any direct perform_smart_move
    caller, proving the behavior is now universal."""
    printer_map = {"XL-1": {"printer_name": "🦝 XL", "position": 0}}
    loc_list = [
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1",
         "extra": {"slot_targets": {"1": "XL-1"}}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
    ]
    spool_data = {"id": 42, "location": "", "extra": {}}
    update_calls = []

    def fake_update(sid, data):
        update_calls.append((sid, data))
        return {"id": sid, **data}

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_data),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "Test", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    for m in ctx: m.start()
    try:
        result = logic.perform_smart_move("PM-DB-1", [42], target_slot="1", origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    assert result.get("status") == "success"
    # Auto-deploy hint should surface the toolhead target.
    assert result.get("auto_deployed_to") == "XL-1", f"expected auto-deploy hint, got {result!r}"
    # Two update_spool calls happened: one for the slot placement (PM-DB-1)
    # and one for the chained toolhead deploy (XL-1).
    locations = [data.get("location") for sid, data in update_calls]
    assert "PM-DB-1" in locations, f"missing slot placement call; got {update_calls!r}"
    assert "XL-1" in locations, f"missing toolhead deploy call; got {update_calls!r}"


def test_perform_smart_move_skips_auto_deploy_when_slot_unbound():
    """Complementary: if the slot has no binding, no chained move."""
    printer_map = {"XL-1": {"printer_name": "🦝 XL", "position": 0}}
    loc_list = [
        {"LocationID": "PM-DB-1", "Type": "Dryer Box", "Max Spools": "1",
         "extra": {"slot_targets": {}}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
    ]
    spool_data = {"id": 42, "location": "", "extra": {}}
    update_calls = []

    def fake_update(sid, data):
        update_calls.append((sid, data))
        return {"id": sid, **data}

    ctx = [
        patch.object(logic.config_loader, "load_config",
                     return_value={"printer_map": printer_map}),
        patch.object(logic.config_loader, "get_api_urls",
                     return_value=("http://spoolman", "http://filabridge")),
        patch.object(logic.locations_db, "load_locations_list", return_value=loc_list),
        patch.object(logic.spoolman_api, "get_spool", return_value=spool_data),
        patch.object(logic.spoolman_api, "get_spools_at_location", return_value=[]),
        patch.object(logic.spoolman_api, "get_spools_at_location_detailed", return_value=[]),
        patch.object(logic.spoolman_api, "format_spool_display",
                     return_value={"text": "Test", "color": "ff0000"}),
        patch.object(logic.spoolman_api, "update_spool", side_effect=fake_update),
        patch.object(logic.requests, "post", return_value=MagicMock(ok=True)),
    ]
    for m in ctx: m.start()
    try:
        result = logic.perform_smart_move("PM-DB-1", [42], target_slot="1", origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    assert result.get("status") == "success"
    assert "auto_deployed_to" not in result
    # Only the slot placement happened.
    assert len(update_calls) == 1, f"expected one update, got {update_calls!r}"
    assert update_calls[0][1].get("location") == "PM-DB-1"


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
# 13.6 Part A — toolhead-direct assign synthesizes ghost binding
# ---------------------------------------------------------------------------

def test_smart_move_to_bound_toolhead_synthesizes_ghost_when_source_unknown():
    """13.6 Part A — when a spool is moved DIRECTLY to a toolhead (e.g.
    scan from buffer / force-move) and that toolhead is the target of some
    dryer-box slot's slot_targets, the spool's physical_source /
    physical_source_slot must be set to that box+slot so the box card
    renders the spool as a ghost in the bound slot.

    Pre-fix: a fresh spool deployed to XL-3 left physical_source='' (came
    from UNASSIGNED) so the box never showed it. User had to manually
    re-assign on the box for the binding to appear correct."""
    printer_map = {"XL-3": {"printer_name": "🦝 XL", "position": 2}}
    loc_list = [
        {"LocationID": "PM-DB-XL-L", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3"}}},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
    ]
    # Spool currently UNASSIGNED — no meaningful physical_source.
    spool_data = {"id": 42, "location": "", "extra": {}}
    captured = {}
    ctx = _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured)
    for m in ctx: m.start()
    try:
        logic.perform_smart_move("XL-3", [42], target_slot=None, origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    _, patch_data = captured['update']
    # Without 13.6 Part A: physical_source would be '' (the spool's prior
    # location, UNASSIGNED). With the reverse-binding synthesis, it's the
    # box+slot that feeds the destination toolhead.
    assert patch_data["extra"]["physical_source"] == "PM-DB-XL-L"
    assert patch_data["extra"]["physical_source_slot"] == "3"


def test_smart_move_to_bound_toolhead_preserves_real_source():
    """13.6 Part A guard — when the spool already has a meaningful
    physical_source (e.g. it came from a different box), the reverse-
    binding synthesis must NOT clobber it. The existing source wins so
    Return-to-Slot still sends the spool home, not to the synthesized
    box+slot of the destination toolhead."""
    printer_map = {
        "XL-3": {"printer_name": "🦝 XL", "position": 2},
        "XL-5": {"printer_name": "🦝 XL", "position": 4},
    }
    loc_list = [
        {"LocationID": "PM-DB-XL-L", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"3": "XL-3"}}},
        {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2",
         "extra": {"slot_targets": {"1": "XL-5"}}},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-5", "Type": "Tool Head", "Max Spools": "1"},
    ]
    # Spool currently at LR-MDB-2 (real source).
    spool_data = {
        "id": 88, "location": "LR-MDB-2",
        "extra": {"container_slot": "1"},
    }
    captured = {}
    ctx = _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured)
    for m in ctx: m.start()
    try:
        logic.perform_smart_move("XL-3", [88], target_slot=None, origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    _, patch_data = captured['update']
    # Real source preserved — Return-to-Slot will send it back to LR-MDB-2.
    assert patch_data["extra"]["physical_source"] == "LR-MDB-2"
    assert patch_data["extra"]["physical_source_slot"] == "1"


def test_force_move_to_room_clears_ghost_trail():
    """L130 fix — force-locating a spool that was deployed to a toolhead
    (physical_source=LR-MDB-1:2) into a Room/Cart must clear physical_source
    and physical_source_slot. Otherwise search_inventory.is_deployed still
    reports the spool as deployed because its ghost source is still a
    toolhead, and the details modal keeps showing "Deployed: XL-3"
    after the user explicitly forced it elsewhere."""
    printer_map = {"XL-3": {"printer_name": "🦝 XL", "position": 2}}
    loc_list = [
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4"},
        # Generic room — not Printer, not Dryer Box, not Tool Head.
        {"LocationID": "LR", "Type": "Room", "Max Spools": ""},
    ]
    spool_data = {
        "id": 99, "location": "LR-MDB-1",  # ghost-deployed to XL-3 via this box
        "extra": {
            "physical_source": "LR-MDB-1",
            "physical_source_slot": "2",
            "container_slot": "2",
        }
    }
    captured = {}
    ctx = _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured)
    for m in ctx: m.start()
    try:
        logic.perform_smart_move("LR", [99], target_slot=None, origin="manual_override")
    finally:
        for m in reversed(ctx): m.stop()

    _, patch_data = captured['update']
    extras = patch_data["extra"]
    # THE regression: the prior ghost trail must be gone now that the user
    # explicitly relocated the spool to a non-toolhead.
    assert "physical_source" not in extras or extras.get("physical_source") in (None, ""), \
        f"physical_source should be cleared on force-move to non-toolhead, got {extras.get('physical_source')!r}"
    assert "physical_source_slot" not in extras or extras.get("physical_source_slot") in (None, ""), \
        f"physical_source_slot should be cleared, got {extras.get('physical_source_slot')!r}"
    # Sanity: the destination was actually written.
    assert patch_data["location"] == "LR"


def test_smart_move_to_unbound_toolhead_no_ghost_synthesis():
    """13.6 Part A complement — if the destination toolhead has no
    reverse-binding from any dryer-box slot, the spool's physical_source
    stays at its actual prior location (which for an UNASSIGNED spool is
    just '')."""
    printer_map = {"XL-9": {"printer_name": "🦝 XL", "position": 8}}
    loc_list = [
        # No slot_targets entry points to XL-9.
        {"LocationID": "PM-DB-XL-L", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"1": "XL-1"}}},
        {"LocationID": "XL-9", "Type": "Tool Head", "Max Spools": "1"},
    ]
    spool_data = {"id": 42, "location": "", "extra": {}}
    captured = {}
    ctx = _setup_smartmove_mocks(spool_data, printer_map, loc_list, captured)
    for m in ctx: m.start()
    try:
        logic.perform_smart_move("XL-9", [42], target_slot=None, origin="test")
    finally:
        for m in reversed(ctx): m.stop()

    _, patch_data = captured['update']
    # No reverse binding to synthesize — physical_source stays empty.
    assert patch_data["extra"].get("physical_source", "") == ""


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
