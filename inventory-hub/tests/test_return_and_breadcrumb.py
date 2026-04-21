"""
Tests for return-to-slot preferring physical_source, closeManage
breadcrumb navigation, and the Bind picker's virtual-printer toolhead
selector.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
import requests
from playwright.sync_api import Page, expect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import locations_db  # noqa: E402
import logic  # noqa: E402


TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"
VIRTUAL_PRINTER = "XL"


# ---------------------------------------------------------------------------
# Return-to-slot: physical_source preference
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_return_prefers_physical_source_over_first_binding(client):
    """When a spool on XL-4 has physical_source=LR-MDB-2 slot 1, Return
    should send it there — NOT to LR-MDB-1 slot 2 (which is also bound
    to XL-4 but isn't where the spool came from)."""
    printer_map = {"XL-4": {"printer_name": "🦝 XL", "position": 3}}
    locs = [
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"2": "XL-4"}}},
        {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2",
         "extra": {"slot_targets": {"1": "XL-4"}}},
        {"LocationID": "XL-4", "Type": "Tool Head", "Max Spools": "1"},
    ]
    fake_spool = {"id": 77, "location": "XL-4",
                  "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "1"}}
    move_calls = []

    def fake_move(target, spools, target_slot=None, origin=None):
        move_calls.append((target, list(spools), target_slot, origin))
        return {"status": "success"}

    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}), \
         patch.object(app_module.locations_db, "load_locations_list", return_value=locs), \
         patch.object(app_module.spoolman_api, "get_spools_at_location", return_value=[77]), \
         patch.object(app_module.spoolman_api, "get_spool", return_value=fake_spool), \
         patch.object(app_module.logic, "perform_smart_move", side_effect=fake_move):
        r = client.post("/api/quickswap/return", json={"toolhead": "XL-4"})

    assert r.status_code == 200
    body = r.get_json()
    assert body["action"] == "return_done"
    assert body["box"] == "LR-MDB-2"
    assert body["slot"] == "1"
    assert body["source"] == "physical_source"
    # And perform_smart_move was called with the physical_source target.
    assert move_calls[0][0] == "LR-MDB-2"
    assert move_calls[0][2] == "1"


def test_return_falls_back_to_first_binding_when_no_source(client):
    """Spool with no physical_source (e.g. manually placed before the
    bindings system): Return uses the first bound slot."""
    printer_map = {"XL-4": {"printer_name": "🦝 XL", "position": 3}}
    locs = [
        {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4",
         "extra": {"slot_targets": {"2": "XL-4"}}},
        {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2",
         "extra": {"slot_targets": {"1": "XL-4"}}},
        {"LocationID": "XL-4", "Type": "Tool Head", "Max Spools": "1"},
    ]
    fake_spool = {"id": 77, "location": "XL-4", "extra": {}}

    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}), \
         patch.object(app_module.locations_db, "load_locations_list", return_value=locs), \
         patch.object(app_module.spoolman_api, "get_spools_at_location", return_value=[77]), \
         patch.object(app_module.spoolman_api, "get_spool", return_value=fake_spool), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}):
        r = client.post("/api/quickswap/return", json={"toolhead": "XL-4"})

    assert r.status_code == 200
    body = r.get_json()
    assert body["source"] == "first_binding"
    assert body["box"] == "LR-MDB-1"  # first in loc_list iteration order
    assert body["slot"] == "2"


def test_return_from_virtual_printer_uses_first_loaded_toolhead_then_source(client):
    """Virtual-printer prefix: pick the first loaded toolhead, then honor
    its spool's physical_source."""
    printer_map = {
        "XL-1": {"printer_name": "🦝 XL", "position": 0},
        "XL-2": {"printer_name": "🦝 XL", "position": 1},
    }
    locs = [
        {"LocationID": "LR-MDB-2", "Type": "Dryer Box", "Max Spools": "2",
         "extra": {"slot_targets": {"1": "XL-2"}}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},
    ]
    fake_spool = {"id": 88, "location": "XL-2",
                  "extra": {"physical_source": "LR-MDB-2", "physical_source_slot": "1"}}

    def resident_for(loc):
        return [88] if str(loc).upper() == "XL-2" else []

    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}), \
         patch.object(app_module.locations_db, "load_locations_list", return_value=locs), \
         patch.object(app_module.spoolman_api, "get_spools_at_location", side_effect=resident_for), \
         patch.object(app_module.spoolman_api, "get_spool", return_value=fake_spool), \
         patch.object(app_module.logic, "perform_smart_move", return_value={"status": "success"}):
        r = client.post("/api/quickswap/return", json={"toolhead": "XL"})

    assert r.status_code == 200
    body = r.get_json()
    assert body["toolhead"] == "XL-2"
    assert body["box"] == "LR-MDB-2"
    assert body["slot"] == "1"
    assert body["source"] == "physical_source"


# ---------------------------------------------------------------------------
# closeManage breadcrumb
# ---------------------------------------------------------------------------

@pytest.fixture
def bindings_for_breadcrumb(api_base_url):
    snap = requests.get(f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": TEST_TOOLHEAD}},
        timeout=5,
    )
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


@pytest.mark.usefixtures("require_server", "bindings_for_breadcrumb")
def test_close_manage_after_edit_full_bindings_returns_to_toolhead(page: Page, base_url: str):
    """Open toolhead XL-1 → click Edit Full Bindings (navigates to some
    bound box) → click the manage-modal Close button → should pop back
    to XL-1, not close the modal entirely."""
    _open_manage(page, base_url, TEST_TOOLHEAD)
    # Navigate away from the toolhead into whichever box the Edit Full
    # Bindings button jumps to (depends on runtime binding order).
    page.locator("#quickswap-edit-bindings-btn").click()
    page.wait_for_timeout(600)
    new_loc = page.locator("#manage-loc-id").input_value()
    assert new_loc and new_loc != TEST_TOOLHEAD, (
        f"Edit Full Bindings should have navigated away from {TEST_TOOLHEAD}; "
        f"we're still on {new_loc!r}."
    )
    # Close → breadcrumb pops → we should be back on the toolhead.
    page.locator("#manageModal .modal-header .btn-close").click()
    page.wait_for_timeout(600)
    expect(page.locator("#manageModal")).to_be_visible()
    expect(page.locator("#manage-loc-id")).to_have_value(TEST_TOOLHEAD)


@pytest.mark.usefixtures("require_server", "bindings_for_breadcrumb")
def test_close_manage_from_top_of_stack_closes_modal(page: Page, base_url: str):
    """No breadcrumb → Close button should actually close the modal."""
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator("#manageModal .modal-header .btn-close").click()
    page.wait_for_timeout(600)
    expect(page.locator("#manageModal")).to_be_hidden()


# ---------------------------------------------------------------------------
# Bind-slot picker — virtual printer toolhead selector
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_bind_picker_shows_toolhead_select_on_virtual_printer(page: Page, base_url: str):
    _open_manage(page, base_url, VIRTUAL_PRINTER)
    page.locator("#quickswap-bind-slot-btn").click()
    expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
    # Virtual printer has 5 toolheads → selector should be visible.
    row = page.locator("#fcc-bind-picker-toolhead-row")
    expect(row).to_be_visible()
    sel = page.locator("#fcc-bind-picker-toolhead-select")
    options = sel.locator("option")
    assert options.count() >= 2, "virtual printer should list multiple toolhead options"


@pytest.mark.usefixtures("require_server")
def test_bind_picker_hides_toolhead_select_on_specific_toolhead(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator("#quickswap-bind-slot-btn").click()
    expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
    expect(page.locator("#fcc-bind-picker-toolhead-row")).to_be_hidden()


@pytest.mark.usefixtures("require_server")
def test_bind_picker_virtual_printer_selector_changes_target(page: Page, base_url: str):
    _open_manage(page, base_url, VIRTUAL_PRINTER)
    page.locator("#quickswap-bind-slot-btn").click()
    expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
    label = page.locator("#fcc-bind-picker-toolhead")
    first = label.text_content()
    # Pick the second option in the select.
    sel = page.locator("#fcc-bind-picker-toolhead-select")
    options = sel.locator("option")
    if options.count() < 2:
        pytest.skip("virtual printer doesn't have multiple toolheads")
    second_value = options.nth(1).get_attribute("value")
    sel.select_option(second_value)
    page.wait_for_timeout(200)
    assert label.text_content() == second_value
    assert label.text_content() != first
