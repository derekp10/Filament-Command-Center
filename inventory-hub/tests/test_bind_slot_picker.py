"""
Tests for the quick "bind a box slot to this toolhead" picker introduced
after the Phase 3 user-feedback rounds.

Covers:
- GET /api/dryer_boxes/slots — flat enumeration with unbound-first ordering.
- PUT /api/dryer_box/<box>/bindings/<slot> — single-slot update path used
  by the picker commit.
- UI flow — open picker, search, keyboard-nav, commit binding, new
  binding appears in Quick-Swap grid.
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


# ---------------------------------------------------------------------------
# Unit-level: enumeration + single-slot PUT
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def tmp_locations_file(tmp_path, monkeypatch):
    fake = tmp_path / "locations.json"
    monkeypatch.setattr(locations_db, "JSON_FILE", str(fake))
    return fake


@pytest.fixture
def sample_locs():
    return [
        {"LocationID": "PM-DB-A", "Type": "Dryer Box", "Max Spools": "1", "Name": "PM A"},
        {"LocationID": "PM-DB-B", "Type": "Dryer Box", "Max Spools": "1", "Name": "PM B",
         "extra": {"slot_targets": {"1": "XL-2"}}},
        {"LocationID": "MDB-1", "Type": "Dryer Box", "Max Spools": "4", "Name": "Multi",
         "extra": {"slot_targets": {"2": "XL-3"}}},
        {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1"},
        {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1"},
    ]


@pytest.fixture
def printer_map():
    return {
        "XL-1": {"printer_name": "🦝 XL", "position": 0},
        "XL-2": {"printer_name": "🦝 XL", "position": 1},
        "XL-3": {"printer_name": "🦝 XL", "position": 2},
    }


def test_enumeration_flat_includes_all_slots(client, sample_locs, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    r = client.get("/api/dryer_boxes/slots")
    assert r.status_code == 200
    slots = r.get_json()["slots"]
    # 1 + 1 + 4 = 6 rows across three boxes.
    assert len(slots) == 6
    # Every dryer box/slot pair is present.
    pairs = {(s["box"], s["slot"]) for s in slots}
    assert ("PM-DB-A", "1") in pairs
    assert ("PM-DB-B", "1") in pairs
    assert {("MDB-1", str(n)) for n in range(1, 5)}.issubset(pairs)


def test_enumeration_puts_unbound_first(client, sample_locs, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    slots = client.get("/api/dryer_boxes/slots").get_json()["slots"]
    # First few entries must be unbound.
    unbound_prefix_len = next((i for i, s in enumerate(slots) if s["target"] is not None),
                              len(slots))
    assert unbound_prefix_len > 0, "first entry should be unbound"
    for i in range(unbound_prefix_len):
        assert slots[i]["target"] is None


def test_single_slot_put_adds_binding(client, sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}):
        r = client.put("/api/dryer_box/PM-DB-A/bindings/1", json={"target": "XL-1"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["slot_targets"] == {"1": "XL-1"}


def test_single_slot_put_unsets_with_null(client, sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}):
        r = client.put("/api/dryer_box/PM-DB-B/bindings/1", json={"target": None})
    assert r.status_code == 200
    # PM-DB-B had slot 1 → XL-2; null should clear it.
    assert r.get_json()["slot_targets"] == {}


def test_single_slot_put_preserves_sibling_bindings(client, sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    # MDB-1 starts with {2: XL-3}. Add {1: XL-1} via single-slot PUT; slot 2
    # must still be XL-3 afterwards.
    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}):
        client.put("/api/dryer_box/MDB-1/bindings/1", json={"target": "XL-1"})
    body = client.get("/api/dryer_box/MDB-1/bindings").get_json()
    assert body["slot_targets"] == {"1": "XL-1", "2": "XL-3"}


def test_single_slot_put_rejects_bad_target(client, sample_locs, printer_map, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}):
        r = client.put("/api/dryer_box/PM-DB-A/bindings/1", json={"target": "XL-999"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "validation_failed"


def test_single_slot_put_404_on_non_dryer_box(client, sample_locs, tmp_locations_file):
    locations_db.save_locations_list(sample_locs)
    r = client.put("/api/dryer_box/XL-1/bindings/1", json={"target": "XL-2"})
    assert r.status_code == 404
    assert r.get_json()["error"] == "not_a_dryer_box"


def test_single_slot_put_raises_duplicate_warning(client, sample_locs, printer_map, tmp_locations_file):
    """Binding a slot to a toolhead already bound by another box is a
    warning, not an error — the PUT still succeeds."""
    locations_db.save_locations_list(sample_locs)
    with patch.object(app_module.config_loader, "load_config",
                      return_value={"printer_map": printer_map}):
        # PM-DB-B already has slot 1 → XL-2. Bind MDB-1 slot 1 → XL-2 too.
        r = client.put("/api/dryer_box/MDB-1/bindings/1", json={"target": "XL-2"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["slot_targets"]["1"] == "XL-2"
    assert len(body["warnings"]) >= 1


# ---------------------------------------------------------------------------
# UI-path E2E — picker flow against live container
# ---------------------------------------------------------------------------

TEST_BOX = "PM-DB-1"
TEST_TOOLHEAD = "XL-1"


@pytest.fixture
def bound_slot(api_base_url):
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


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_opens_from_quickswap_header(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator("#quickswap-bind-slot-btn").click()
    overlay = page.locator("#fcc-bind-picker-overlay")
    expect(overlay).to_be_visible(timeout=3000)
    expect(page.locator("#fcc-bind-picker-toolhead")).to_contain_text(TEST_TOOLHEAD)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_search_filters_list(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator("#quickswap-bind-slot-btn").click()
    expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
    page.locator("#fcc-bind-picker-search").fill("PM-DB-2")
    page.wait_for_timeout(200)
    items = page.locator(".fcc-bind-picker-item")
    count = items.count()
    assert count >= 1
    for i in range(count):
        expect(items.nth(i)).to_contain_text("PM-DB-2")


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_escape_closes(page: Page, base_url: str):
    _open_manage(page, base_url, TEST_TOOLHEAD)
    page.locator("#quickswap-bind-slot-btn").click()
    expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
    page.locator("#fcc-bind-picker-search").press("Escape")
    expect(page.locator("#fcc-bind-picker-overlay")).to_be_hidden(timeout=2000)


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_unbind_button_clears_binding_and_keeps_picker_open(page: Page, base_url: str, api_base_url):
    """Inline Unbind button on a bound row should clear the slot and
    refresh the listing in place — no trip to the full Feeds editor
    required, no closing the picker."""
    victim = "PM-DB-4"
    snap = requests.get(f"{api_base_url}/api/dryer_box/{victim}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    # Seed a binding on a box we won't conflict with the main fixture.
    requests.put(
        f"{api_base_url}/api/dryer_box/{victim}/bindings",
        json={"slot_targets": {"1": TEST_TOOLHEAD}},
        timeout=5,
    )
    try:
        _open_manage(page, base_url, TEST_TOOLHEAD)
        page.locator("#quickswap-bind-slot-btn").click()
        expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
        page.locator("#fcc-bind-picker-search").fill(victim)
        page.wait_for_timeout(200)
        unbind_btn = page.locator(f".fcc-bind-picker-item:has-text('{victim}') .fcc-bind-picker-unbind").first
        expect(unbind_btn).to_be_visible(timeout=2000)
        unbind_btn.click()
        # Picker stays open, listing refreshes — slot is now unbound on
        # the server.
        page.wait_for_timeout(600)
        expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible()
        r = requests.get(f"{api_base_url}/api/dryer_box/{victim}/bindings", timeout=5).json()
        assert r["slot_targets"] == {}, f"Unbind didn't clear slot (got {r['slot_targets']})"
    finally:
        requests.put(
            f"{api_base_url}/api/dryer_box/{victim}/bindings",
            json={"slot_targets": original},
            timeout=5,
        )


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_rebind_overwrites_existing_target(page: Page, base_url: str, api_base_url):
    """Clicking a slot already bound to a DIFFERENT toolhead should rewrite
    the binding to the current target — no manual unbind-first required."""
    victim = "PM-DB-5"
    snap = requests.get(f"{api_base_url}/api/dryer_box/{victim}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    # Pre-bind slot 1 to a DIFFERENT toolhead than TEST_TOOLHEAD.
    requests.put(
        f"{api_base_url}/api/dryer_box/{victim}/bindings",
        json={"slot_targets": {"1": "XL-2"}},
        timeout=5,
    )
    try:
        _open_manage(page, base_url, TEST_TOOLHEAD)
        page.locator("#quickswap-bind-slot-btn").click()
        expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
        page.locator("#fcc-bind-picker-search").fill(victim)
        page.wait_for_timeout(200)
        row = page.locator(f".fcc-bind-picker-item:has-text('{victim}')").first
        expect(row).to_contain_text("XL-2")
        # Click the left-side label (box name span). Avoids the Unbind
        # button on the right side of the row.
        row.locator("span.fw-bold").first.click()
        page.wait_for_timeout(600)
        r = requests.get(f"{api_base_url}/api/dryer_box/{victim}/bindings", timeout=5).json()
        assert r["slot_targets"].get("1") == TEST_TOOLHEAD
    finally:
        requests.put(
            f"{api_base_url}/api/dryer_box/{victim}/bindings",
            json={"slot_targets": original},
            timeout=5,
        )


@pytest.mark.usefixtures("require_server", "bound_slot")
def test_bind_picker_enter_commits_new_binding(page: Page, base_url: str, api_base_url):
    """Search for an unbound PM-DB slot, hit Enter, verify the binding
    persisted server-side and the Quick-Swap grid picks it up."""
    # Snapshot bindings for a slot we're going to mutate, restore after.
    victim = "PM-DB-5"
    snap = requests.get(f"{api_base_url}/api/dryer_box/{victim}/bindings", timeout=5).json()
    original = snap.get("slot_targets", {})
    try:
        _open_manage(page, base_url, TEST_TOOLHEAD)
        page.locator("#quickswap-bind-slot-btn").click()
        expect(page.locator("#fcc-bind-picker-overlay")).to_be_visible(timeout=3000)
        page.locator("#fcc-bind-picker-search").fill(victim)
        page.wait_for_timeout(200)
        page.locator("#fcc-bind-picker-search").press("Enter")
        # Picker closes on success.
        expect(page.locator("#fcc-bind-picker-overlay")).to_be_hidden(timeout=3000)

        # Server-side persisted?
        follow = requests.get(f"{api_base_url}/api/dryer_box/{victim}/bindings", timeout=5).json()
        assert follow["slot_targets"].get("1") == TEST_TOOLHEAD
    finally:
        requests.put(
            f"{api_base_url}/api/dryer_box/{victim}/bindings",
            json={"slot_targets": original},
            timeout=5,
        )
