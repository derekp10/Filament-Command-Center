"""
Tests for Quick-Swap grid enhancements:
- Empty slots show a "Deposit from buffer" affordance when the user has
  a spool in the buffer, and become disabled again when the buffer empties.
- Box subheaders in the Quick-Swap grid are clickable and open the box
  in the manage modal (breadcrumb sends Close → back to the toolhead).
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


TEST_TOOLHEAD = "XL-1"


def _open_manage(page: Page, base_url: str, loc_id: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_function("() => typeof window.openManage === 'function'", timeout=5000)
    page.wait_for_timeout(500)
    page.evaluate(f"window.openManage({loc_id!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=8000)
    page.wait_for_timeout(700)


def _find_empty_bound_slot(api_base_url):
    """Return (box, slot, toolhead) for a slot that is bound but empty in
    the current dev state."""
    payload = requests.get(f"{api_base_url}/api/dryer_boxes/slots", timeout=5).json()
    for entry in payload.get("slots", []):
        if not entry.get("target"):
            continue
        contents = requests.get(
            f"{api_base_url}/api/get_contents?id={entry['box']}", timeout=5
        ).json()
        has_spool = any(
            str(it.get("slot", "")).replace('"', '').strip() == str(entry["slot"])
            for it in contents or []
        )
        if not has_spool:
            return entry["box"], str(entry["slot"]), entry["target"]
    return None


def _find_spool_for_buffer(api_base_url):
    """Pick any spool that's currently sitting at Unassigned (cheap to
    grab, doesn't disturb a toolhead binding). Returns the id."""
    items = requests.get(f"{api_base_url}/api/get_contents?id=Unassigned", timeout=5).json()
    for it in items or []:
        sid = it.get("id")
        if sid:
            return int(sid)
    return None


# ---------------------------------------------------------------------------
# Empty-slot deposit affordance
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server", "clean_buffer")
def test_empty_slot_disabled_when_buffer_empty(page: Page, base_url: str, api_base_url):
    hit = _find_empty_bound_slot(api_base_url)
    if not hit:
        pytest.skip("No bound + empty slot in the current dev state.")
    box, slot, toolhead = hit
    _open_manage(page, base_url, toolhead)
    # Make absolutely sure no spool is in the buffer (past test bleed).
    page.evaluate("() => { state.heldSpools = []; if (window.renderBuffer) window.renderBuffer(); }")
    page.wait_for_timeout(500)
    btn = page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first
    expect(btn).to_be_visible(timeout=3000)
    expect(btn).to_be_disabled()
    expect(btn).to_contain_text("empty slot")


@pytest.mark.usefixtures("require_server")
def test_empty_slot_becomes_deposit_target_when_buffer_has_spool(page: Page, base_url: str, api_base_url):
    hit = _find_empty_bound_slot(api_base_url)
    if not hit:
        pytest.skip("No bound + empty slot in the current dev state.")
    box, slot, toolhead = hit
    spool_id = _find_spool_for_buffer(api_base_url)
    if not spool_id:
        pytest.skip("No unassigned spool to park in the buffer for this test.")

    _open_manage(page, base_url, toolhead)

    # Put a spool in the buffer via the same path the scan handler uses,
    # then wait for the Quick-Swap grid to re-render via the
    # inventory:buffer-updated event.
    page.evaluate(f"""
        () => {{
            state.heldSpools = [{{id: {spool_id}, display: 'Test Deposit Spool', color: 'ff00ff'}}];
            if (window.renderBuffer) window.renderBuffer();
        }}
    """)
    page.wait_for_timeout(800)

    btn = page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first
    expect(btn).to_be_visible(timeout=3000)
    expect(btn).not_to_be_disabled()
    expect(btn).to_contain_text("Deposit from buffer")
    # Click handler should be the deposit variant, not the swap variant.
    onclick = btn.get_attribute("onclick")
    assert onclick and "quickSwapDeposit" in onclick, f"Expected deposit onclick, got {onclick!r}"


@pytest.mark.usefixtures("require_server")
def test_deposit_confirm_overlay_names_the_spool_and_toolhead(page: Page, base_url: str, api_base_url):
    hit = _find_empty_bound_slot(api_base_url)
    if not hit:
        pytest.skip("No bound + empty slot in the current dev state.")
    box, slot, toolhead = hit
    spool_id = _find_spool_for_buffer(api_base_url)
    if not spool_id:
        pytest.skip("No unassigned spool to park in the buffer for this test.")

    _open_manage(page, base_url, toolhead)
    page.evaluate(f"""
        () => {{
            state.heldSpools = [{{id: {spool_id}, display: 'Confirm Body Spool', color: 'abcdef'}}];
            if (window.renderBuffer) window.renderBuffer();
        }}
    """)
    page.wait_for_timeout(800)
    btn = page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first
    expect(btn).to_be_visible(timeout=3000)
    btn.click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    expect(overlay).to_be_visible(timeout=2000)
    title = page.locator("#fcc-quickswap-confirm-title")
    body = page.locator("#fcc-quickswap-confirm-body")
    expect(title).to_contain_text(box)
    expect(title).to_contain_text(slot)
    expect(body).to_contain_text(toolhead)
    # Cancel out — we don't want this test to actually move a real spool.
    page.locator("#fcc-quickswap-no").click()


# ---------------------------------------------------------------------------
# Clickable box header
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_clicking_box_header_opens_manage_on_that_box(page: Page, base_url: str, api_base_url):
    # Any bound slot works — we just need a box label to click.
    payload = requests.get(f"{api_base_url}/api/dryer_boxes/slots", timeout=5).json()
    bound = next((e for e in payload.get("slots", []) if e.get("target")), None)
    if not bound:
        pytest.skip("No bindings in current dev state to render a header.")
    box, toolhead = bound["box"], bound["target"]

    _open_manage(page, base_url, toolhead)
    # Click the dotted-underline anchor inside the grid.
    link = page.locator(f"#quickswap-grid a[onclick*=\"openManage('{box}')\"]").first
    expect(link).to_be_visible(timeout=3000)
    link.click()
    page.wait_for_timeout(800)
    expect(page.locator("#manage-loc-id")).to_have_value(box)
    # Close the box → breadcrumb sends us back to the toolhead.
    page.locator("#manageModal .modal-header .btn-close").click()
    page.wait_for_timeout(700)
    expect(page.locator("#manageModal")).to_be_visible()
    expect(page.locator("#manage-loc-id")).to_have_value(toolhead)
