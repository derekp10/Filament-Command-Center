"""Integration tests for the Spool > Filament > Vendor empty-weight cascade
across the Edit Spool and Clone Spool wizard update flows.

The helper (`resolveEmptySpoolWeightSource`) is unit-tested in
test_empty_spool_weight_priority.py. The wizard's New Spool prefill is
covered in test_wizard_auto_prefill_empty_weight.py. The two paths still
lacking coverage — and the ones the user explicitly flagged as needing
verification — are the update flows:

  - Edit Spool wizard (window.openEditWizard at inv_wizard.js:2064 →
    cascade at inv_wizard.js:2184)
  - Clone Spool wizard (window.openCloneWizard at inv_wizard.js:1925 →
    cascade at inv_wizard.js:1942)

Both fetch /api/spool_details?id=... and pipe the result through
resolveEmptySpoolWeightSource. If the spool has no spool_weight AND the
filament has no spool_weight, the manufacturer (vendor) value MUST cascade
down so the user doesn't lose the inheritance after opening an existing
record for edit.

The scaffolding here stubs /api/spool_details with controlled fixtures so
the test runs against a deterministic record without polluting Spoolman.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


def _stub_spool_details(page: Page, spool: dict) -> None:
    """Install a fetch stub returning the given spool record from
    /api/spool_details. All other URLs fall through to the real handler so
    /api/external/vendors, /api/external/fields, /api/materials, etc. still
    populate the wizard's combobox state correctly.
    """
    page.evaluate(
        """
        (spool) => {
            window.__stubSpoolDetails = spool;
            const origFetch = window.fetch;
            window.fetch = async (url, opts) => {
                if (typeof url !== 'string') return origFetch(url, opts);
                if (url.startsWith('/api/spool_details')) {
                    return new Response(JSON.stringify(window.__stubSpoolDetails),
                        {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                return origFetch(url, opts);
            };
        }
        """,
        spool,
    )


def _wait_ready(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openCloneWizard === 'function'")
    page.wait_for_function("typeof window.openEditWizard === 'function'")
    page.wait_for_function("typeof window.resolveEmptySpoolWeightSource === 'function'")


# ---------------------------------------------------------------------------
# Clone wizard — opening a spool to clone walks the cascade
# ---------------------------------------------------------------------------


def test_clone_falls_back_to_vendor_when_spool_and_filament_blank(page: Page):
    """Spool has no spool_weight; filament has no spool_weight; vendor has 167.
    Cloning the spool should auto-fill the wizard's empty-weight field with
    167 and badge the source as 'vendor'."""
    _wait_ready(page)
    _stub_spool_details(page, {
        "id": 1001,
        "spool_weight": None,
        "filament": {
            "id": 501,
            "name": "Galaxy Black",
            "material": "PLA",
            "spool_weight": None,
            "color_hex": "112233",
            "vendor": {"id": 11, "name": "CC3D", "empty_spool_weight": 167},
        },
    })
    page.evaluate("() => window.openCloneWizard(1001)")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    # Cascade is async (clone flow .then() chain). Wait for the empty-weight
    # field to populate before asserting.
    page.wait_for_function(
        "() => document.getElementById('wiz-spool-empty_weight').value === '167'"
    )
    # Badge surfaces the resolution source so the user can see it came from
    # the vendor, not from the filament (which was blank).
    source_text = page.locator("#wiz-spool-empty-inherited-source").inner_text()
    assert source_text == "vendor", f"Expected source 'vendor', got {source_text!r}"


def test_clone_filament_wins_over_vendor(page: Page):
    """If the filament has a spool_weight, the clone cascade stops there
    instead of falling through to the vendor."""
    _wait_ready(page)
    _stub_spool_details(page, {
        "id": 1002,
        "spool_weight": None,
        "filament": {
            "id": 502,
            "name": "Galaxy White",
            "material": "PLA",
            "spool_weight": 195,
            "color_hex": "FFFFFF",
            "vendor": {"id": 12, "name": "CC3D", "empty_spool_weight": 167},
        },
    })
    page.evaluate("() => window.openCloneWizard(1002)")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => document.getElementById('wiz-spool-empty_weight').value === '195'"
    )
    assert page.locator("#wiz-spool-empty-inherited-source").inner_text() == "filament"


def test_clone_spool_wins_over_filament_and_vendor(page: Page):
    """If the spool itself has a spool_weight, it wins outright. The
    inherited badge is intentionally HIDDEN in this case — the value isn't
    inherited from anywhere else, it's the spool's own setting
    (wizardSetSpoolEmptyWeightInherited only shows the badge for
    'filament' or 'vendor' sources, per inv_wizard.js:50)."""
    _wait_ready(page)
    _stub_spool_details(page, {
        "id": 1003,
        "spool_weight": 220,
        "filament": {
            "id": 503,
            "name": "Galaxy Red",
            "material": "PLA",
            "spool_weight": 195,
            "color_hex": "FF0000",
            "vendor": {"id": 13, "name": "CC3D", "empty_spool_weight": 167},
        },
    })
    page.evaluate("() => window.openCloneWizard(1003)")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => document.getElementById('wiz-spool-empty_weight').value === '220'"
    )
    badge_hidden = page.evaluate(
        "() => { const b = document.getElementById('wiz-spool-empty-inherited-badge');"
        "  return !b || b.style.display === 'none'; }"
    )
    assert badge_hidden, "Inherited badge should be hidden when the spool itself supplies the value"


def test_clone_zero_treated_as_unset_falls_to_vendor(page: Page):
    """0 at the spool and filament levels should fall through to the vendor
    (matches the helper's `has()` predicate at weight_utils.js:14)."""
    _wait_ready(page)
    _stub_spool_details(page, {
        "id": 1004,
        "spool_weight": 0,
        "filament": {
            "id": 504,
            "name": "Galaxy Blue",
            "material": "PLA",
            "spool_weight": 0,
            "color_hex": "0066FF",
            "vendor": {"id": 14, "name": "CC3D", "empty_spool_weight": 167},
        },
    })
    page.evaluate("() => window.openCloneWizard(1004)")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => document.getElementById('wiz-spool-empty_weight').value === '167'"
    )
    assert page.locator("#wiz-spool-empty-inherited-source").inner_text() == "vendor"


def test_clone_all_unset_leaves_field_blank(page: Page):
    """When nothing in the chain has a value, the wizard's empty-weight
    field stays blank and no source badge is shown (the inherited-badge
    container is hidden by wizardSetSpoolEmptyWeightInherited)."""
    _wait_ready(page)
    _stub_spool_details(page, {
        "id": 1005,
        "spool_weight": None,
        "filament": {
            "id": 505,
            "name": "Galaxy Mystery",
            "material": "PLA",
            "spool_weight": None,
            "color_hex": "888888",
            "vendor": {"id": 15, "name": "CC3D"},  # no empty_spool_weight
        },
    })
    page.evaluate("() => window.openCloneWizard(1005)")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    # Give the .then() handler a chance to run; assert the field is blank.
    page.wait_for_timeout(500)
    assert page.locator("#wiz-spool-empty_weight").input_value() == ""
    badge_hidden = page.evaluate(
        "() => { const b = document.getElementById('wiz-spool-empty-inherited-badge');"
        "  return !b || b.style.display === 'none'; }"
    )
    assert badge_hidden, "Inherited badge should be hidden when nothing cascades"


# ---------------------------------------------------------------------------
# Edit Spool wizard — same cascade as clone, exercised via openEditWizard
# ---------------------------------------------------------------------------


def test_edit_spool_falls_back_to_vendor_when_spool_and_filament_blank(page: Page):
    """The Edit Spool wizard flow also walks Spool > Filament > Vendor. This
    is the primary case the user flagged: opening an existing record for
    editing must not lose the manufacturer-default empty weight."""
    _wait_ready(page)
    _stub_spool_details(page, {
        "id": 2001,
        "spool_weight": None,
        "initial_weight": 1000,
        "used_weight": 0,
        "filament": {
            "id": 601,
            "name": "Galaxy Black",
            "material": "PLA",
            "spool_weight": None,
            "color_hex": "112233",
            "vendor": {"id": 21, "name": "CC3D", "empty_spool_weight": 187},
        },
    })
    page.evaluate("() => window.openEditWizard(2001)")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => document.getElementById('wiz-spool-empty_weight').value === '187'"
    )
    assert page.locator("#wiz-spool-empty-inherited-source").inner_text() == "vendor"


def test_edit_spool_does_not_clobber_existing_spool_weight(page: Page):
    """Opening a spool that already has its own spool_weight must NOT
    overwrite that with the vendor's value — the spool's explicit setting
    is the user's source of truth. Badge stays hidden because the value
    isn't inherited (it's the spool's own field)."""
    _wait_ready(page)
    _stub_spool_details(page, {
        "id": 2002,
        "spool_weight": 210,
        "initial_weight": 1000,
        "used_weight": 50,
        "filament": {
            "id": 602,
            "name": "Galaxy White",
            "material": "PLA",
            "spool_weight": 195,
            "color_hex": "FFFFFF",
            "vendor": {"id": 22, "name": "CC3D", "empty_spool_weight": 167},
        },
    })
    page.evaluate("() => window.openEditWizard(2002)")
    expect(page.locator("#wizardModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => document.getElementById('wiz-spool-empty_weight').value === '210'"
    )
    badge_hidden = page.evaluate(
        "() => { const b = document.getElementById('wiz-spool-empty-inherited-badge');"
        "  return !b || b.style.display === 'none'; }"
    )
    assert badge_hidden, "Inherited badge should be hidden when the spool itself supplies the value"
