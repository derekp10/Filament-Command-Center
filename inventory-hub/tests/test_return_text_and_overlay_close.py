"""
Tests for the friendlier Return-to-Slot body text (names box + slot,
never exposes "physical_source" jargon) and for dismissing inline
overlays when the manage modal closes.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


VIRTUAL_PRINTER = "XL"


def _find_loaded_toolhead(api_base_url, prefix):
    pm = requests.get(f"{api_base_url}/api/printer_map", timeout=5).json().get("printers", {})
    for entries in pm.values():
        for e in entries:
            th = str(e.get("location_id", "")).upper()
            if th.startswith(prefix.upper() + "-"):
                contents = requests.get(
                    f"{api_base_url}/api/get_contents?id={th}", timeout=5
                ).json()
                if contents:
                    return th
    return None


# ---------------------------------------------------------------------------
# Return overlay body: box + slot, no jargon
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_return_overlay_shows_concrete_box_and_slot(page: Page, open_manage_modal, api_base_url):
    loaded_th = _find_loaded_toolhead(api_base_url, VIRTUAL_PRINTER)
    if not loaded_th:
        pytest.skip(f"No toolhead on {VIRTUAL_PRINTER}- currently loaded.")
    # Fetch the spool and its source metadata up-front so we know what
    # the UI *should* display.
    contents = requests.get(f"{api_base_url}/api/get_contents?id={loaded_th}", timeout=5).json()
    resident = (contents or [{}])[0]
    reported_box = str(resident.get("location", "")).upper()
    reported_slot = str(resident.get("slot", "")).replace('"', '').strip() or None

    open_manage_modal(loaded_th)
    page.locator("#quickswap-return-btn").click()
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=4000)
    body = page.locator("#fcc-quickswap-confirm-body")
    body_text = body.inner_text()
    # Jargon has no place in a user-facing overlay.
    assert "physical_source" not in body_text.lower(), (
        f"Return overlay still exposes internal jargon: {body_text!r}"
    )
    # The destination line should mention the box by name. Slot mention is
    # conditional (a single-spool box may not carry a slot in get_contents).
    if reported_box and reported_box != loaded_th:
        assert reported_box in body_text, (
            f"Return overlay body doesn't name the destination box "
            f"(expected {reported_box}): {body_text!r}"
        )
    if reported_slot:
        assert reported_slot in body_text, (
            f"Return overlay body doesn't mention the destination slot "
            f"(expected {reported_slot}): {body_text!r}"
        )


@pytest.mark.usefixtures("require_server")
def test_return_overlay_flags_missing_origin_explicitly(page: Page, open_manage_modal, api_base_url):
    """If there's no spool at all, the overlay should clearly say nothing
    can be returned rather than rendering a confirm prompt."""
    # Find a toolhead that is DEFINITELY empty.
    pm = requests.get(f"{api_base_url}/api/printer_map", timeout=5).json().get("printers", {})
    empty_toolhead = None
    for entries in pm.values():
        for e in entries:
            th = str(e.get("location_id", "")).upper()
            contents = requests.get(f"{api_base_url}/api/get_contents?id={th}", timeout=5).json()
            if not contents:
                empty_toolhead = th
                break
        if empty_toolhead:
            break
    if not empty_toolhead:
        pytest.skip("No empty toolhead available for this test case.")

    open_manage_modal(empty_toolhead)
    page.locator("#quickswap-return-btn").click()
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=4000)
    body = page.locator("#fcc-quickswap-confirm-body")
    text = body.inner_text()
    # Either "nothing to return to" (no spool case) or a specific
    # "sending back to X slot Y" message — but definitely no jargon.
    assert "physical_source" not in text.lower()


# ---------------------------------------------------------------------------
# Overlay close-with-manage-modal
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_confirm_overlay_dismisses_when_modal_closes_via_x(page: Page, open_manage_modal, bound_loaded_slot):
    """Open a confirm, X-close the manage modal. Re-opening the same
    toolhead must not inherit the stale confirm overlay."""
    box, slot, toolhead = (
        bound_loaded_slot["box"], bound_loaded_slot["slot"], bound_loaded_slot["toolhead"]
    )
    open_manage_modal(toolhead)
    btn = page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first
    btn.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # ~3s active-print probe before the overlay mounts (offline dev printers).
    expect(overlay).to_be_visible(timeout=8000)

    # Hide the manage modal without dismissing the confirm first.
    # Group 15 — the confirm overlay's full-screen backdrop now correctly
    # intercepts pointer events, so a real user can't click the modal X
    # through it. The behavior under test is "if the modal hides for any
    # reason, the confirm overlay cleans up too"; we drive the hide
    # programmatically to match that contract.
    page.evaluate(
        "() => bootstrap.Modal.getOrCreateInstance(document.getElementById('manageModal')).hide()"
    )
    page.wait_for_timeout(500)
    expect(page.locator("#manageModal")).to_be_hidden()
    # The confirm overlay should be hidden too.
    expect(overlay).to_be_hidden()

    # Re-open — the overlay must NOT pop back up.
    page.evaluate(f"window.openManage({toolhead!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(500)
    expect(overlay).to_be_hidden()


@pytest.mark.usefixtures("require_server")
def test_bind_picker_dismisses_when_modal_closes_via_x(page: Page, open_manage_modal, real_toolhead):
    """Same discipline for the Bind-a-Slot picker."""
    toolhead = real_toolhead
    open_manage_modal(toolhead)
    page.locator("#quickswap-bind-slot-btn").click()
    picker = page.locator("#fcc-bind-picker-overlay")
    expect(picker).to_be_visible(timeout=5000)

    page.locator("#manageModal .modal-header .btn-close").click()
    page.wait_for_timeout(500)
    expect(page.locator("#manageModal")).to_be_hidden()
    expect(picker).to_be_hidden()

    page.evaluate(f"window.openManage({toolhead!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(500)
    expect(picker).to_be_hidden()
