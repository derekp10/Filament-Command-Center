"""
Group 9.2 — Printer Pool banner row in the Quick-Swap grid.

A dryer-box slot bound to the `PRINTER:<id>` sentinel (vs. a specific
toolhead) is staging/drying space for that printer. The Quick-Swap grid
surfaces those slots in their own "🏭 Printer Pool" section so the user
can deposit buffered spools without leaving the toolhead view.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page, expect


TEST_BOX = "TST-MDB-1"  # max=6, baseline-empty bindings — safe to mutate per-test.
TEST_TOOLHEAD = "XL-1"
TEST_PRINTER_PREFIX = "XL"
POOL_SLOT = "4"


@pytest.fixture
def pool_binding(api_base_url):
    """Bind slot 1 → toolhead and slot 4 → PRINTER:XL on TEST_BOX. Restore
    the original bindings on teardown."""
    snap = requests.get(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings", timeout=5
    ).json()
    original = snap.get("slot_targets", {})
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": {"1": TEST_TOOLHEAD, POOL_SLOT: f"PRINTER:{TEST_PRINTER_PREFIX}"}},
        timeout=5,
    )
    yield
    requests.put(
        f"{api_base_url}/api/dryer_box/{TEST_BOX}/bindings",
        json={"slot_targets": original},
        timeout=5,
    )


@pytest.mark.usefixtures("require_server", "pool_binding")
def test_api_returns_printer_pool(api_base_url):
    """Backend smoke: /api/machine/<name>/toolhead_slots includes the
    printer_pool field with the seeded PRINTER:XL slot."""
    pm = requests.get(f"{api_base_url}/api/printer_map", timeout=5).json().get("printers", {})
    # Find the printer name whose toolheads start with "XL-".
    target_name = None
    for name, entries in pm.items():
        if any(str(e["location_id"]).upper().startswith(f"{TEST_PRINTER_PREFIX}-") for e in entries):
            target_name = name
            break
    if not target_name:
        pytest.skip(f"No printer with {TEST_PRINTER_PREFIX}- toolheads in printer_map.")
    body = requests.get(
        f"{api_base_url}/api/machine/{target_name}/toolhead_slots", timeout=5
    ).json()
    pool = body.get("printer_pool", [])
    pool_keys = {(e["box"], str(e["slot"])) for e in pool}
    assert (TEST_BOX, POOL_SLOT) in pool_keys, \
        f"PRINTER:{TEST_PRINTER_PREFIX} binding missing from printer_pool: {pool!r}"


def _wait_pool_btn(page: Page, box: str, slot: str, timeout: int = 8000):
    """Wait for the pool slot button to appear in the rendered grid. The
    grid render chain (printer_map → toolhead_slots → get_contents) is
    async — relying on a fixed sleep flakes when the sweep server is busy.
    """
    selector = f".fcc-qs-pool[data-box='{box}'][data-slot='{slot}']"
    page.wait_for_selector(selector, timeout=timeout, state="attached")
    return page.locator(selector).first


@pytest.mark.usefixtures("require_server", "pool_binding", "clean_buffer")
def test_quickswap_grid_renders_printer_pool_section(page: Page, open_manage_modal):
    """Opening a toolhead surfaces the Printer Pool header + a slot card
    for each PRINTER:<id> binding affiliated with that printer."""
    open_manage_modal(TEST_TOOLHEAD)
    grid = page.locator("#quickswap-grid")
    expect(grid).to_be_visible()
    pool_btn = _wait_pool_btn(page, TEST_BOX, POOL_SLOT)
    expect(pool_btn).to_be_visible()
    expect(grid).to_contain_text("Printer Pool")


@pytest.mark.usefixtures("require_server", "pool_binding", "clean_buffer")
def test_pool_slot_disabled_when_buffer_empty(page: Page, open_manage_modal):
    open_manage_modal(TEST_TOOLHEAD)
    page.evaluate("() => { state.heldSpools = []; if (window.renderBuffer) window.renderBuffer(); }")
    pool_btn = _wait_pool_btn(page, TEST_BOX, POOL_SLOT)
    expect(pool_btn).to_be_visible()
    expect(pool_btn).to_be_disabled()
    expect(pool_btn).to_contain_text("empty staging slot")


@pytest.mark.usefixtures("require_server", "pool_binding")
def test_pool_slot_becomes_deposit_target_when_buffer_has_spool(
    page: Page, open_manage_modal
):
    open_manage_modal(TEST_TOOLHEAD)
    # Wait for the grid's first render before mutating buffer state — the
    # buffer-updated re-render needs the prior render's currentLoc set.
    _wait_pool_btn(page, TEST_BOX, POOL_SLOT)
    page.evaluate("""
        () => {
            state.heldSpools = [{id: 99999, display: 'Pool Test Spool', color: '00ff88'}];
            if (window.renderBuffer) window.renderBuffer();
        }
    """)
    # Wait for the post-buffer-update render to swap "empty staging slot"
    # for the green deposit affordance. 8s tolerates the renderQuickSwapSection
    # async fetch chain racing with the initial open-modal render.
    page.wait_for_function(
        f"""() => {{
            const el = document.querySelector(
                ".fcc-qs-pool[data-box='{TEST_BOX}'][data-slot='{POOL_SLOT}']"
            );
            return el && el.textContent.includes('Deposit from buffer');
        }}""",
        timeout=8000,
    )
    pool_btn = page.locator(
        f".fcc-qs-pool[data-box='{TEST_BOX}'][data-slot='{POOL_SLOT}']"
    ).first
    expect(pool_btn).not_to_be_disabled()
    onclick = pool_btn.get_attribute("onclick")
    assert onclick and "quickSwapDeposit" in onclick, \
        f"Expected quickSwapDeposit onclick on pool slot, got {onclick!r}"
