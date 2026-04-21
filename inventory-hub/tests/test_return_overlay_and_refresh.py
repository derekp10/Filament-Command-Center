"""
Tests for:
- Return-to-slot confirm overlay naming the resolved toolhead (not the
  virtual-printer prefix) when opened from a virtual-printer view.
- Post-swap manage-view refresh so the user sees the new active spool
  without having to close and reopen the modal.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


VIRTUAL_PRINTER = "XL"


def _open_manage(page: Page, base_url: str, loc_id: str) -> None:
    page.goto(base_url)
    page.wait_for_selector("#command-buffer, #buffer-zone", timeout=10000)
    page.wait_for_timeout(500)
    page.evaluate(f"window.openManage({loc_id!r})")
    expect(page.locator("#manageModal")).to_be_visible(timeout=5000)
    page.wait_for_timeout(600)


def _find_loaded_toolhead_on_printer(api_base_url: str, prefix: str):
    pm = requests.get(f"{api_base_url}/api/printer_map", timeout=5).json().get("printers", {})
    for entries in pm.values():
        for e in entries:
            if str(e.get("location_id", "")).upper().startswith(prefix.upper() + "-"):
                contents = requests.get(
                    f"{api_base_url}/api/get_contents?id={e['location_id']}", timeout=5
                ).json()
                if contents:
                    return str(e["location_id"]).upper()
    return None


# ---------------------------------------------------------------------------
# Return overlay text — virtual printer
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_server")
def test_return_overlay_names_specific_toolhead_on_virtual_printer(page: Page, base_url: str, api_base_url):
    """From the XL virtual-printer view, clicking Return to Slot should
    resolve and display the concrete toolhead that'll be acted on — not
    the ambiguous 'XL' prefix."""
    loaded = _find_loaded_toolhead_on_printer(api_base_url, VIRTUAL_PRINTER)
    if not loaded:
        pytest.skip(f"No toolhead under {VIRTUAL_PRINTER}- currently has a spool loaded.")
    _open_manage(page, base_url, VIRTUAL_PRINTER)
    page.locator("#quickswap-return-btn").click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    expect(overlay).to_be_visible(timeout=4000)
    title = page.locator("#fcc-quickswap-confirm-title")
    # Title must name the specific toolhead (e.g. XL-3), NOT the prefix (XL).
    expect(title).to_contain_text(loaded)
    # And the body should mention that we resolved it from the virtual printer.
    body = page.locator("#fcc-quickswap-confirm-body")
    expect(body).to_contain_text(VIRTUAL_PRINTER)


@pytest.mark.usefixtures("require_server")
def test_return_overlay_explains_when_virtual_printer_has_no_loaded_toolhead(page: Page, base_url: str, api_base_url):
    """If nothing is loaded on any toolhead of the virtual printer, the
    overlay should say so explicitly instead of pretending there's
    something to return."""
    loaded = _find_loaded_toolhead_on_printer(api_base_url, VIRTUAL_PRINTER)
    if loaded:
        pytest.skip(f"{VIRTUAL_PRINTER}- has a loaded toolhead; can't test the empty case.")
    _open_manage(page, base_url, VIRTUAL_PRINTER)
    page.locator("#quickswap-return-btn").click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    expect(overlay).to_be_visible(timeout=4000)
    body = page.locator("#fcc-quickswap-confirm-body")
    expect(body).to_contain_text("No toolhead")


# ---------------------------------------------------------------------------
# Post-swap refresh
# ---------------------------------------------------------------------------

def _find_bound_and_loaded(api_base_url):
    payload = requests.get(f"{api_base_url}/api/dryer_boxes/slots", timeout=5).json()
    for entry in payload.get("slots", []):
        if not entry.get("target"):
            continue
        contents = requests.get(
            f"{api_base_url}/api/get_contents?id={entry['box']}", timeout=5
        ).json()
        for it in contents or []:
            if str(it.get("slot", "")).replace('"', '').strip() == str(entry["slot"]):
                return entry["box"], str(entry["slot"]), entry["target"], it.get("id")
    return None


@pytest.mark.usefixtures("require_server")
def test_quickswap_refreshes_manage_view_after_yes(page: Page, base_url: str, api_base_url):
    """After confirming a swap, the manage view should re-render on its own
    without the user closing and reopening the modal. We verify by asserting
    that the list/grid section inside the modal gets a fresh render after
    the Yes click — watched via a DOM mutation on #manage-grid-view /
    #manage-list-view — and that the swapped spool's Spoolman location
    actually changed to the target toolhead."""
    hit = _find_bound_and_loaded(api_base_url)
    if not hit:
        pytest.skip("No bound+loaded slot available to exercise the swap.")
    box, slot, toolhead, spool_id = hit

    _open_manage(page, base_url, toolhead)

    # Plant a sentinel in whichever render container is currently visible.
    # refreshManageView rewrites that container's innerHTML when a move
    # happens, so a post-swap presence check tells us whether a re-render
    # actually ran.
    page.evaluate("""
        () => {
            const tag = '<span class="fcc-test-preswap" style="display:none;"></span>';
            const grid = document.getElementById('manage-grid-view');
            const list = document.getElementById('manage-list-view');
            const isListVisible = list && list.offsetParent !== null;
            const target = isListVisible
                ? document.getElementById('manage-contents-list')
                : document.getElementById('slot-grid-container');
            if (target) target.insertAdjacentHTML('beforeend', tag);
        }
    """)

    btn = page.locator(f".fcc-qs-slot[data-box='{box}'][data-slot='{slot}']").first
    expect(btn).to_be_visible(timeout=3000)
    btn.click()
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=2000)
    page.locator("#fcc-quickswap-yes").click()

    # Wait for the follow-up refresh (immediate + 450 ms delayed).
    page.wait_for_timeout(1200)

    # Any sentinel surviving means the containers weren't re-rendered, so
    # the user would have had to close + reopen to see the new state.
    still_marked = page.evaluate(
        "() => !!document.querySelector('.fcc-test-preswap')"
    )
    assert not still_marked, "manage view did not re-render after swap"

    # And Spoolman should confirm the spool actually moved to the toolhead.
    residents = requests.get(
        f"{api_base_url}/api/get_contents?id={toolhead}", timeout=5
    ).json()
    resident_ids = {str(r.get("id")) for r in (residents or [])}
    assert str(spool_id) in resident_ids, (
        f"spool {spool_id} did not end up at {toolhead} after swap "
        f"(residents: {resident_ids})"
    )

    # Restore by returning the spool back to the box.
    try:
        requests.post(
            f"{api_base_url}/api/quickswap/return",
            json={"toolhead": toolhead},
            timeout=5,
        )
    except Exception:
        pass
