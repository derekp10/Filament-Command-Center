"""Group 10.1 Session C — wizard section-collapse UX.

The wizard's Step 2 / Step 3 field clusters now live in Bootstrap .collapse
panels with deliberate defaults:

  - Always-open (no collapse for required-everytime fields):
      • Step 2 Identity row (Vendor + Material)
      • Step 3 Quantity & Location row

  - Always-expanded in both create and edit:
      • Step 2 "Physical Specs" (#wiz-fil-physical-panel)

  - "Optional" — collapsed in create mode; smart-expanded on edit/clone/
    new-from-filament when the section contains any user-entered data:
      • Step 2 Color           (#wiz-fil-color-panel)
      • Step 2 Print Temperatures (#wiz-fil-temps-panel)
      • Step 2 Custom Filament Attributes (#wiz-fil-extras-panel)
      • Step 3 Weight & Scale  (#wiz-spool-weight-panel)
      • Step 3 Pricing & Metadata (#wiz-spool-metadata-panel)
      • Step 3 Custom Spool Attributes (#wiz-spool-extras-panel)

These tests stub spool/filament endpoints so they're independent of the
real Spoolman instance — the panel collapse state is the only thing being
asserted.
"""
from __future__ import annotations

import re
from playwright.sync_api import Page, expect


OPTIONAL_PANELS = [
    "wiz-fil-color-panel",
    "wiz-fil-temps-panel",
    "wiz-fil-extras-panel",
    "wiz-spool-weight-panel",
    "wiz-spool-metadata-panel",
    "wiz-spool-extras-panel",
]
ALWAYS_OPEN_PANELS = ["wiz-fil-physical-panel"]


def _open_create_wizard(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.get_by_role("button", name=re.compile("ADD INVENTORY")).click()
    expect(page.locator("#wizardModal")).to_be_visible()
    # wizardApplyCollapseDefaults('create') runs at the end of openWizardModal
    # after the Promise.all of fetches. Give it a moment to settle.
    page.wait_for_function("typeof window.wizardApplyCollapseDefaults === 'function'", timeout=5_000)
    page.wait_for_timeout(300)


def _panel_is_open(page: Page, panel_id: str) -> bool:
    return page.evaluate(
        f"() => document.getElementById('{panel_id}').classList.contains('show')"
    )


def _wait_for_panel_open(page: Page, panel_id: str, *, timeout: int = 2_000) -> None:
    """Wait until the panel finishes Bootstrap's collapse animation (gains .show)."""
    page.wait_for_function(
        f"() => document.getElementById('{panel_id}').classList.contains('show')",
        timeout=timeout,
    )


def _wait_for_panel_closed(page: Page, panel_id: str, *, timeout: int = 2_000) -> None:
    """Wait until the panel finishes Bootstrap's collapse animation (loses .show)."""
    page.wait_for_function(
        f"() => !document.getElementById('{panel_id}').classList.contains('show')"
        f" && !document.getElementById('{panel_id}').classList.contains('collapsing')",
        timeout=timeout,
    )


def _toggle_button_aria(page: Page, panel_id: str) -> str:
    return page.evaluate(
        f"() => document.querySelector('[data-bs-target=\"#{panel_id}\"]').getAttribute('aria-expanded')"
    )


# ---------------------------------------------------------------------------
# Create-mode defaults
# ---------------------------------------------------------------------------


def test_optional_panels_collapsed_in_create_mode(page: Page):
    """All six "optional" panels start collapsed when the user opens a fresh
    wizard. Physical Specs stays open (always-open kind)."""
    _open_create_wizard(page)
    for pid in OPTIONAL_PANELS:
        assert not _panel_is_open(page, pid), f"{pid} should be collapsed in create mode"
        assert _toggle_button_aria(page, pid) == "false", (
            f"{pid} toggle button aria-expanded should be 'false'"
        )
    for pid in ALWAYS_OPEN_PANELS:
        assert _panel_is_open(page, pid), f"{pid} should always be open"


def test_section_toggle_buttons_are_keyboard_accessible(page: Page):
    """Each panel has a section-toggle button reachable by selector and
    Bootstrap's data-bs-toggle hooks. Clicking toggles the panel."""
    _open_create_wizard(page)
    for pid in OPTIONAL_PANELS:
        btn = page.locator(f'button.fcc-wiz-section-toggle[data-bs-target="#{pid}"]')
        expect(btn).to_have_count(1)
        # Programmatically open via Bootstrap (avoid animation race in CI).
        page.evaluate(
            f"() => bootstrap.Collapse.getOrCreateInstance("
            f"document.getElementById('{pid}'), {{toggle:false}}).show()"
        )
        # Bootstrap fires shown.bs.collapse after the transition — wait for the .show class.
        page.wait_for_function(
            f"() => document.getElementById('{pid}').classList.contains('show')",
            timeout=2_000,
        )


# ---------------------------------------------------------------------------
# Smart-expand on edit
# ---------------------------------------------------------------------------


def _stub_spool_details(page: Page, spool: dict) -> None:
    """Stub /api/spool_details so openEditWizard's prefill uses our fixture
    instead of the live database."""
    page.evaluate(
        """(s) => {
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u.startsWith('/api/spool_details')) {
                    return new Response(JSON.stringify(s),
                        { status: 200, headers: {'Content-Type': 'application/json'} });
                }
                return origFetch(url, opts);
            };
        }""",
        spool,
    )


def _dashboard_ready(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openEditWizard === 'function'", timeout=5_000)


def test_edit_with_price_auto_expands_metadata_panel(page: Page):
    """Editing a spool that has a non-zero price auto-expands the Pricing &
    Metadata panel so the user immediately sees the existing value."""
    _dashboard_ready(page)
    _stub_spool_details(page, {
        "id": 42,
        "price": 19.99,
        "comment": "",
        "used_weight": 0,
        "spool_weight": None,
        "initial_weight": None,
        "archived": False,
        "extra": {},
        "filament": {
            "id": 7, "name": "Crimson Red", "material": "PLA",
            "spool_weight": None,
            "vendor": {"id": 1, "name": "CC3D"},
            "extra": {},
        },
    })
    page.evaluate("() => window.openEditWizard(42)")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    page.wait_for_function(
        "document.getElementById('wiz-spool-price').value === '19.99'", timeout=3_000
    )
    # Give wizardApplyCollapseDefaults('edit') a moment to fire at end of .then.
    _wait_for_panel_open(page, "wiz-spool-metadata-panel")


def test_edit_with_archived_only_auto_expands_metadata_panel(page: Page):
    """Edge case: the smart-expand predicate must treat checked checkboxes
    as 'has data' even when all other inputs in the panel are empty."""
    _dashboard_ready(page)
    _stub_spool_details(page, {
        "id": 99,
        "price": None,
        "comment": "",
        "used_weight": 0,
        "spool_weight": None,
        "initial_weight": None,
        "archived": True,  # only this flag set
        "extra": {},
        "filament": {
            "id": 7, "name": "Crimson Red", "material": "PLA",
            "spool_weight": None,
            "vendor": {"id": 1, "name": "CC3D"},
            "extra": {},
        },
    })
    page.evaluate("() => window.openEditWizard(99)")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    page.wait_for_function(
        "document.getElementById('wiz-spool-archived').checked === true", timeout=3_000
    )
    _wait_for_panel_open(page, "wiz-spool-metadata-panel")


def test_edit_with_no_optional_data_keeps_metadata_collapsed(page: Page):
    """When a spool has no optional fields filled, the Pricing & Metadata
    panel remains collapsed in edit mode."""
    _dashboard_ready(page)
    _stub_spool_details(page, {
        "id": 77,
        "price": None,
        "comment": "",
        "used_weight": 0,
        "spool_weight": None,
        "initial_weight": None,
        "archived": False,
        "extra": {},
        "filament": {
            "id": 7, "name": "Crimson Red", "material": "PLA",
            "spool_weight": None,
            "vendor": {"id": 1, "name": "CC3D"},
            "extra": {},
        },
    })
    page.evaluate("() => window.openEditWizard(77)")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    # Wait for the edit-success message which is set right before the collapse
    # defaults fire, so we know prefill is done.
    page.wait_for_function(
        "document.getElementById('wiz-status-msg').innerText.indexOf('Editing Spool') !== -1",
        timeout=3_000,
    )
    # Confirm the panel is settled-closed (not mid-animation).
    page.wait_for_timeout(500)
    assert not _panel_is_open(page, "wiz-spool-metadata-panel"), (
        "Pricing & Metadata should stay collapsed when nothing optional is set"
    )


def test_new_spool_from_filament_auto_expands_weight_panel(page: Page):
    """openNewSpoolFromFilamentWizard prefills the spool empty_weight from
    the filament cascade — Weight & Scale should auto-expand to show it."""
    _dashboard_ready(page)
    page.evaluate(
        """(fil) => {
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u.startsWith('/api/filament_details')) {
                    return new Response(JSON.stringify(fil),
                        { status: 200, headers: {'Content-Type': 'application/json'} });
                }
                return origFetch(url, opts);
            };
        }""",
        {"id": 7, "name": "Crimson Red", "material": "PLA",
         "spool_weight": 180,
         "vendor": {"id": 1, "name": "CC3D"}},
    )
    page.evaluate("() => window.openNewSpoolFromFilamentWizard(7)")
    page.wait_for_selector("#wizardModal.show", timeout=3_000)
    page.wait_for_function(
        "document.getElementById('wiz-spool-empty_weight').value === '180'", timeout=3_000
    )
    _wait_for_panel_open(page, "wiz-spool-weight-panel")
