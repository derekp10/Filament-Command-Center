"""
Capture baseline screenshots of every weight-entry UI surface.

Run from the host (not Docker), with the dev container up at localhost:8000:

    cd inventory-hub
    python ../docs/agent_docs/phase-2-baseline/capture_baseline.py

Writes PNGs to ../docs/agent_docs/phase-2-baseline/screenshots/. Re-running
clobbers prior captures — copy the directory first if you want to keep them.

Each surface is rendered from stubbed fetch fixtures so the layout is
deterministic and reproducible.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:8000"
VIEWPORT = {"width": 1600, "height": 1300}
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"


def _wait_for_dashboard(page: Page) -> None:
    page.goto(BASE_URL)
    page.wait_for_selector("#buffer-zone", timeout=10_000)
    page.wait_for_function(
        "typeof window.openWeighOutModal === 'function'", timeout=5_000
    )


def _stub_fetch(page: Page, fixtures_js: str) -> None:
    """Inject a window.fetch override using the supplied JS routing logic."""
    page.evaluate(
        f"""
        (() => {{
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {{
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                {fixtures_js}
                return origFetch(url, opts);
            }};
        }})();
        """
    )


def _save(page: Page, filename: str, locator: str | None = None) -> None:
    """Snapshot the page or a specific locator into screenshots/<filename>."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SCREENSHOTS_DIR / filename
    if locator:
        page.locator(locator).screenshot(path=str(out_path))
    else:
        page.screenshot(path=str(out_path), full_page=False)
    print(f"  -> {out_path.relative_to(SCREENSHOTS_DIR.parent.parent.parent)}")


# --- Surface captures -------------------------------------------------------


def capture_bulk_weigh_out(page: Page) -> None:
    """01 — Bulk Weigh-Out modal with a couple of held spools.

    The module's `state` is a script-scoped `let` (not on window), so we mutate
    it via bare reference inside page.evaluate — this works because non-module
    script `let` bindings are reachable from any same-context evaluate.
    """
    print("Capturing 01 — Bulk Weigh-Out modal")
    _wait_for_dashboard(page)
    _stub_fetch(page, """
        if (u.startsWith('/api/spool_details')) {
            const id = parseInt(new URL(u, location.origin).searchParams.get('id'));
            return new Response(JSON.stringify({
                id, remaining_weight: 425, used_weight: 575, initial_weight: 1000,
                filament: { id: 7, name: 'Crimson Red', material: 'PLA',
                            spool_weight: 220, vendor: { name: 'CC3D' } }
            }), { status: 200, headers: {'Content-Type': 'application/json'} });
        }
    """)
    # Seed buffer with realistic spools. Use bare `state` (script-scoped let).
    # Field shape matches inv_cmd.js:255 — `display` (formatted vendor-mat-name),
    # `color` (bare hex), `color_direction`, `remaining_weight`, etc.
    page.evaluate("""() => {
        state.heldSpools = [
            { id: 101, display: 'CC3D - PLA - Crimson Red',
              color: 'cc3300', color_direction: 'longitudinal',
              remaining_weight: 425, archived: false, is_ghost: false },
            { id: 102, display: 'Polymaker - PETG - Cobalt Blue',
              color: '2266aa', color_direction: 'longitudinal',
              remaining_weight: 712, archived: false, is_ghost: false },
            { id: 103, display: 'Sunlu - PLA+ - Forest Green',
              color: '2d7a3d', color_direction: 'longitudinal',
              remaining_weight: 188, archived: false, is_ghost: false },
        ];
        window.openWeighOutModal();
    }""")
    page.wait_for_selector("#weighOutModal.show", timeout=5_000)
    # Wait for at least one spool row to render so we don't snapshot the
    # "0 Spools Ready / No Spools in Buffer" empty state.
    try:
        page.wait_for_function(
            "document.querySelectorAll('#weighOutModal .modal-body input[type=\"number\"]').length >= 1",
            timeout=3_000,
        )
    except Exception:
        print("  [warn] No spool rows rendered — capturing whatever state the modal is in")
    time.sleep(0.4)
    _save(page, "01_bulk_weigh_out.png", locator="#weighOutModal .modal-dialog")
    page.evaluate("() => window.modals?.weighOutModal?.hide()")
    try:
        page.wait_for_selector("#weighOutModal.show", state="detached", timeout=3_000)
    except Exception:
        pass  # animation overlap is harmless for the next capture


def capture_quick_weigh_nested(page: Page) -> None:
    """02 — Quick-Weigh nested modal (the +/- prefix delta entry surface)."""
    print("Capturing 02 — Quick-Weigh nested modal")
    _wait_for_dashboard(page)
    _stub_fetch(page, """
        if (u.startsWith('/api/spool_details')) {
            return new Response(JSON.stringify({
                id: 101, remaining_weight: 425, used_weight: 575, initial_weight: 1000,
                filament: { id: 7, name: 'Crimson Red', material: 'PLA',
                            spool_weight: 220, vendor: { name: 'CC3D' } }
            }), { status: 200, headers: {'Content-Type': 'application/json'} });
        }
    """)
    page.evaluate("""() => {
        state.heldSpools = [
            { id: 101, display: 'CC3D - PLA - Crimson Red',
              color: 'cc3300', color_direction: 'longitudinal',
              remaining_weight: 425, archived: false, is_ghost: false },
        ];
        window.openWeighOutModal();
    }""")
    page.wait_for_selector("#weighOutModal.show", timeout=5_000)
    # Drill into the Quick-Weigh nested modal for spool 101.
    page.evaluate("() => window.openQuickWeigh && window.openQuickWeigh(101)")
    # The nested modal element id varies; wait for any swal-like or modal element
    # with the deduction input field that's specific to Quick-Weigh.
    try:
        page.wait_for_selector("#quickWeighModal, .swal2-popup", timeout=3_000)
        time.sleep(0.4)
        _save(page, "02_quick_weigh_nested.png")
    except Exception as e:
        print(f"  [warn] Quick-Weigh open failed ({e}); capturing parent modal instead.")
        _save(page, "02_quick_weigh_nested.png", locator="#weighOutModal .modal-dialog")


def capture_wizard_empty_weight(page: Page) -> None:
    """03 — Wizard Spool tab showing the new Phase 1 inheritance badge."""
    print("Capturing 03 — Wizard empty-weight section (with Phase 1 badge)")
    _wait_for_dashboard(page)
    _stub_fetch(page, """
        if (u.startsWith('/api/filament_details')) {
            return new Response(JSON.stringify({
                id: 7, name: 'Crimson Red', material: 'PLA',
                spool_weight: 220, weight: 1000,
                vendor: { id: 1, name: 'CC3D', empty_spool_weight: 215 }
            }), { status: 200, headers: {'Content-Type': 'application/json'} });
        }
    """)
    page.evaluate("() => { window.openNewSpoolFromFilamentWizard(7); }")
    page.wait_for_selector("#wizardModal.show", timeout=5_000)
    page.wait_for_function(
        "document.getElementById('wiz-spool-empty_weight').value === '220'",
        timeout=5_000,
    )
    time.sleep(0.4)
    # Crop to the spool-weight row + a bit of context above and below.
    _save(page, "03_wizard_empty_weight.png",
          locator="#wiz-spool-empty_weight >> xpath=ancestor::div[contains(@class,'row')][1]")
    page.evaluate("() => window.modals?.wizardModal?.hide()")
    page.wait_for_selector("#wizardModal.show", state="detached", timeout=3_000)


def capture_edit_filament_spool_weight(page: Page) -> None:
    """04 — Edit Filament modal Specs tab (vendor hint + Copy Vendor Weight btn)."""
    print("Capturing 04 — Edit Filament spool-weight area")
    _wait_for_dashboard(page)
    _stub_fetch(page, """
        if (u.startsWith('/api/filament_details')) {
            return new Response(JSON.stringify({
                id: 7, name: 'Crimson Red', material: 'PLA',
                spool_weight: 180, weight: 1000, density: 1.24, diameter: 1.75,
                color_hex: 'CC3300',
                vendor: { id: 1, name: 'CC3D', empty_spool_weight: 215 }
            }), { status: 200, headers: {'Content-Type': 'application/json'} });
        }
    """)
    # Open the edit-filament modal directly.
    page.evaluate("""async () => {
        const r = await fetch('/api/filament_details?id=7');
        const fil = await r.json();
        if (window.openEditFilamentForm) window.openEditFilamentForm(fil);
    }""")
    try:
        page.wait_for_selector("#editFilamentModal.show, .swal2-popup", timeout=5_000)
        time.sleep(0.4)
        # Navigate to the Specs tab where empty-spool-weight + vendor hint live.
        # Bootstrap tabs use data-bs-toggle="tab"; click the Specs trigger.
        try:
            specs_tab = page.locator("#editFilamentModal button:has-text('Specs')").first
            specs_tab.click()
            time.sleep(0.4)
        except Exception:
            print("  [warn] Could not navigate to Specs tab — capturing Basic tab")
        try:
            _save(page, "04_edit_filament_spool_weight.png",
                  locator="#editFilamentModal .modal-dialog")
        except Exception:
            _save(page, "04_edit_filament_spool_weight.png")
    except Exception as e:
        print(f"  [warn] Edit Filament open failed ({e}); skipping.")


def capture_post_archive_prompt(page: Page) -> None:
    """05 — Post-archive empty-weight Swal prompt (Phase 1 fixed Enter key)."""
    print("Capturing 05 — Post-archive empty-weight Swal")
    _wait_for_dashboard(page)
    _stub_fetch(page, """
        if (u.startsWith('/api/filament_details')) {
            return new Response(JSON.stringify({
                id: 7, name: 'Crimson Red', material: 'PLA',
                spool_weight: null,
                vendor: { id: 1, name: 'CC3D' }
            }), { status: 200, headers: {'Content-Type': 'application/json'} });
        }
    """)
    page.evaluate("() => { window.showArchiveEmptyWeightPrompt(99, 7); }")
    page.wait_for_selector("#fcc-archive-empty-wt", state="visible", timeout=5_000)
    time.sleep(0.4)
    _save(page, "05_post_archive_prompt.png", locator=".swal2-popup")


def capture_filabridge_manual_recovery(page: Page) -> None:
    """06 — FilaBridge Manual Recovery modal (per-spool weights table)."""
    print("Capturing 06 — FilaBridge Manual Recovery modal")
    _wait_for_dashboard(page)
    # Open via whatever entry point exists; if none, this surface is captured
    # at-rest via the modal element itself.
    has_modal = page.evaluate("""
        () => !!document.getElementById('filabridgeRecoveryModal') ||
              !!document.querySelector('[id*="filabridge"]')
    """)
    if has_modal:
        try:
            # Try to show the modal directly via Bootstrap.
            page.evaluate("""() => {
                const el = document.getElementById('filabridgeRecoveryModal') ||
                           document.querySelector('[id*="filabridge"]');
                if (el && window.bootstrap) {
                    const m = new bootstrap.Modal(el);
                    m.show();
                }
            }""")
            time.sleep(0.5)
            _save(page, "06_filabridge_manual_recovery.png")
        except Exception as e:
            print(f"  [warn] FilaBridge Recovery open failed ({e}); skipping.")
    else:
        print("  [warn] No FilaBridge Recovery modal in DOM; skipping (only renders when an error is active).")


# --- Driver -----------------------------------------------------------------


def main() -> int:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Capturing baseline -> {SCREENSHOTS_DIR}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        try:
            for fn in (
                capture_bulk_weigh_out,
                capture_quick_weigh_nested,
                capture_wizard_empty_weight,
                capture_edit_filament_spool_weight,
                capture_post_archive_prompt,
                capture_filabridge_manual_recovery,
            ):
                try:
                    fn(page)
                except Exception as e:
                    print(f"  [fail] {fn.__name__} failed: {e}")
        finally:
            ctx.close()
            browser.close()

    print(f"\nDone. {len(list(SCREENSHOTS_DIR.glob('*.png')))} screenshot(s) in {SCREENSHOTS_DIR}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
