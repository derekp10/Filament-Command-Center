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
def test_return_overlay_names_specific_toolhead_on_virtual_printer(page: Page, open_manage_modal, api_base_url):
    """From the XL virtual-printer view, clicking Return to Slot should
    resolve and display the concrete toolhead that'll be acted on — not
    the ambiguous 'XL' prefix."""
    loaded = _find_loaded_toolhead_on_printer(api_base_url, VIRTUAL_PRINTER)
    if not loaded:
        pytest.skip(f"No toolhead under {VIRTUAL_PRINTER}- currently has a spool loaded.")
    open_manage_modal(VIRTUAL_PRINTER)
    page.locator("#quickswap-return-btn").click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # Group 40.6: a spool with no obvious slot (dev data decides) opens the slot
    # picker before the confirm. Enter takes its highlight (the ⭐, else the
    # first slot it can take, else No slot); nothing is written until the
    # confirm's Yes, which this test never clicks.
    page.wait_for_function(
        "!!document.getElementById('fcc-quickswap-confirm-overlay')"
        " || !!document.querySelector('#fcc-slot-picker [data-sp-state=\"ready\"]')", timeout=8000)
    if page.evaluate("!!document.querySelector('#fcc-slot-picker [data-sp-state=\"ready\"]')"):
        page.keyboard.press("Enter")
    # Group 38.5: same ~3s active-print probe floor as the other confirm-overlay
    # waits (inv_quickswap.js:340/368, mountOverlay at :468). These two sites
    # were latent siblings of the 38.5 flake — identical exposure, never yet
    # red. Raised to match the 8000ms precedent in test_quickswap_ui_e2e.py:79.
    expect(overlay).to_be_visible(timeout=8000)
    title = page.locator("#fcc-quickswap-confirm-title")
    # Title must name the specific toolhead (e.g. XL-3), NOT the prefix (XL).
    expect(title).to_contain_text(loaded)
    # And the body should mention that we resolved it from the virtual printer.
    body = page.locator("#fcc-quickswap-confirm-body")
    expect(body).to_contain_text(VIRTUAL_PRINTER)


@pytest.mark.usefixtures("require_server")
def test_return_overlay_explains_when_virtual_printer_has_no_loaded_toolhead(page: Page, open_manage_modal, api_base_url):
    """If nothing is loaded on any toolhead of the virtual printer, the
    overlay should say so explicitly instead of pretending there's
    something to return."""
    loaded = _find_loaded_toolhead_on_printer(api_base_url, VIRTUAL_PRINTER)
    if loaded:
        pytest.skip(f"{VIRTUAL_PRINTER}- has a loaded toolhead; can't test the empty case.")
    open_manage_modal(VIRTUAL_PRINTER)
    page.locator("#quickswap-return-btn").click()
    overlay = page.locator("#fcc-quickswap-confirm-overlay")
    # Group 38.5: same ~3s active-print probe floor as the other confirm-overlay
    # waits (inv_quickswap.js:340/368, mountOverlay at :468). These two sites
    # were latent siblings of the 38.5 flake — identical exposure, never yet
    # red. Raised to match the 8000ms precedent in test_quickswap_ui_e2e.py:79.
    expect(overlay).to_be_visible(timeout=8000)
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
def test_quickswap_refreshes_manage_view_after_yes(page: Page, open_manage_modal, api_base_url):
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

    open_manage_modal(toolhead)

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
    # showConfirmOverlay's 3s active-print probe runs first — overlay can take
    # up to ~3-4s to mount in a dev environment with no reachable PrusaLink.
    # Group 14.2.
    expect(page.locator("#fcc-quickswap-confirm-overlay")).to_be_visible(timeout=6000)
    page.locator("#fcc-quickswap-yes").click()

    # Wait for the follow-up refresh — the backend swap + Spoolman PATCH +
    # client refreshAfterMove() chain can take several seconds in a dev env
    # with a slow Spoolman. Poll for the sentinel disappearing instead of
    # a fixed sleep so we're robust to varying backend latency. Group 14.2.
    try:
        page.wait_for_function(
            "() => !document.querySelector('.fcc-test-preswap')",
            timeout=8000,
        )
    except Exception:
        pass  # fall through to the assertion for a clear failure message

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

    # Restore by returning the spool back to the box. Group 39.2: Return now asks
    # when the printer is printing, and a test must never confirm a real print, so
    # a printing printer fails loudly here. This used to sit in a bare try/except
    # with no check, which would have left the spool on the head silently.
    r = requests.post(
        f"{api_base_url}/api/quickswap/return",
        json={"toolhead": toolhead},
        timeout=15,
    )
    body = r.json()
    if body.get("action") == "return_choose_slot":
        # Group 40.6: no obvious slot (its own was taken meanwhile): the server
        # asks instead of picking one. Take its ⭐, else no slot, as Enter would.
        rec = body.get("recommended") or {}
        r = requests.post(
            f"{api_base_url}/api/quickswap/return",
            json={"toolhead": toolhead, "box": body.get("box"), "expected_spool": spool_id,
                  "slot": rec.get("slot") if rec.get("kind") == "slot" else "none"},
            timeout=15,
        )
        body = r.json()
    if body.get("action") == "return_requires_confirm":
        printer = (body.get("active_print") or {}).get("printer_name") or toolhead
        pytest.fail(f"{printer} is printing, so the restore Return needs a confirm, and a test never "
                    f"confirms a real print. Spool {spool_id} is still on {toolhead}: return it by hand.")
    assert body.get("action") == "return_done", f"the restore Return failed: {body}"
    home = body.get("box") or box
    back = requests.get(f"{api_base_url}/api/get_contents?id={home}", timeout=5).json()
    assert str(spool_id) in {str(x.get("id")) for x in (back or [])}, (
        f"spool {spool_id} did not go back to {home} (contents: {back})")
