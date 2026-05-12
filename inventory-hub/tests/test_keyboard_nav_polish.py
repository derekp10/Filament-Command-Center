"""Group 8 — Keyboard Navigation & Dialog Polish regression tests.

Covers three independent fixes shipped on feature/keyboard-nav-polish:

  8.1 — locModal auto-focuses its primary input on open (Edit → name field,
        Add → ID field). Other modals were audited and already focus or have
        no clear primary input; only locModal needed the change.

  8.3 — Spool details and filament details modals must not stack. A
        user-initiated open of one forcibly hides the sibling. The silent
        refresh path (sync-pulse re-render) is intentionally exempt so it
        only re-paints whichever modal is currently visible.

  8.4 — Internal text inputs (scanner / picker / search / color-hex) carry
        autocomplete="off" so the browser's past-value dropdown stops
        getting in the way. Free-form notes intentionally keep the default.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect


# ---------------------------------------------------------------------------
# 8.4 — autofill suppression on internal text inputs
# ---------------------------------------------------------------------------


# (selector, autocomplete-attr-expected) pairs that should now carry off.
_AUTOFILL_OFF_INPUTS = [
    "#edit-id",
    "#edit-name",
    "#manual-spool-id",
    "#wiz-search-existing",
    "#wiz-search-external",
    "#wiz-fil-color_name",
    "#wiz-fil-color_hex_0",
    "#editfil-color-hex",
    "#editfil-external-query",
    "#global-search-query",
    "#global-search-color-hex",
]


def test_autofill_suppressed_on_internal_inputs(page: Page):
    """Each input in _AUTOFILL_OFF_INPUTS must have autocomplete='off'."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    for sel in _AUTOFILL_OFF_INPUTS:
        loc = page.locator(sel)
        # Inputs may live inside hidden modals — they're still attached to
        # the DOM, so attribute reads work without opening anything.
        expect(loc).to_have_count(1)
        attr = loc.get_attribute("autocomplete")
        assert attr == "off", (
            f"{sel} expected autocomplete='off', got {attr!r}. "
            f"Group 8.4 protects scanner/picker/search/color-hex inputs."
        )


def test_freeform_comments_keep_browser_autofill(page: Page):
    """Comment fields are intentionally NOT suppressed — history may help."""
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    for sel in ("#editfil-comment", "#vendoredit-comment", "#wiz-spool-comment"):
        loc = page.locator(sel)
        expect(loc).to_have_count(1)
        attr = loc.get_attribute("autocomplete")
        assert attr in (None, ""), (
            f"{sel} should be left with default autocomplete (free-form notes), "
            f"got {attr!r}. If you want this suppressed, update the 8.4 policy."
        )


# ---------------------------------------------------------------------------
# 8.1 — locModal auto-focus
# ---------------------------------------------------------------------------


def _wait_loc_mgr_ready(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof window.openAddModal === 'function'")
    page.wait_for_function("typeof window.openEdit === 'function'")
    # openEdit needs at least one entry in state.allLocations; the dashboard
    # populates this on load. `state` is module-scoped in inv_core.js so
    # it's accessible without window. (matches test_quickswap_visual.py).
    page.wait_for_function(
        "() => typeof state === 'object' && Array.isArray(state.allLocations) && state.allLocations.length > 0"
    )


def test_loc_modal_add_focuses_id_field(page: Page):
    _wait_loc_mgr_ready(page)
    page.evaluate("() => window.openAddModal()")
    expect(page.locator("#locModal.show")).to_have_count(1)
    # shown.bs.modal fires after the fade; wait for it via the focus check.
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.id === 'edit-id'"
    )


def test_loc_modal_edit_focuses_name_field_and_selects(page: Page):
    _wait_loc_mgr_ready(page)
    # Use the first cached location so the test doesn't need to know IDs.
    page.evaluate("() => window.openEdit(state.allLocations[0].LocationID)")
    expect(page.locator("#locModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.id === 'edit-name'"
    )
    # Also verify select() ran — the field's value should be fully selected
    # so the user can immediately overtype.
    selection_len = page.evaluate("""() => {
        const el = document.getElementById('edit-name');
        return (el.selectionEnd || 0) - (el.selectionStart || 0);
    }""")
    name_len = page.evaluate("() => document.getElementById('edit-name').value.length")
    assert selection_len == name_len, (
        f"Friendly Name should be select()'d on edit open: selection={selection_len}, "
        f"value-length={name_len}"
    )


# ---------------------------------------------------------------------------
# 8.3 — spool/filament details modal cross-hide
# ---------------------------------------------------------------------------


def _stub_details_endpoints(page: Page, spool: dict, filament: dict) -> None:
    """Stub /api/spool_details and /api/filament_details with controlled
    fixtures so opening either modal succeeds without server data."""
    page.evaluate(
        """
        ([spool, fil]) => {
            window.__stubSpool = spool;
            window.__stubFil = fil;
            const orig = window.fetch;
            window.fetch = async (url, opts) => {
                const u = typeof url === 'string' ? url : (url && url.url) || '';
                if (u.startsWith('/api/spool_details')) {
                    return new Response(JSON.stringify(window.__stubSpool),
                        {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                if (u.startsWith('/api/filament_details')) {
                    return new Response(JSON.stringify(window.__stubFil),
                        {status: 200, headers: {'Content-Type': 'application/json'}});
                }
                return orig(url, opts);
            };
        }
        """,
        [spool, filament],
    )


def _wait_details_ready(page: Page) -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function("typeof openSpoolDetails === 'function'")
    page.wait_for_function("typeof openFilamentDetails === 'function'")


_STUB_SPOOL = {
    "id": 9001,
    "spool_weight": 250,
    "filament": {
        "id": 8001,
        "name": "Test Filament",
        "material": "PLA",
        "color_hex": "112233",
        "vendor": {"id": 91, "name": "TestVendor"},
    },
}
_STUB_FIL = {
    "id": 8001,
    "name": "Test Filament",
    "material": "PLA",
    "color_hex": "112233",
    "vendor": {"id": 91, "name": "TestVendor"},
    "extra": {},
}


def test_opening_filament_details_hides_spool_details(page: Page):
    """User-initiated openFilamentDetails must close any visible spoolModal."""
    _wait_details_ready(page)
    _stub_details_endpoints(page, _STUB_SPOOL, _STUB_FIL)
    page.evaluate("(id) => openSpoolDetails(id)", 9001)
    expect(page.locator("#spoolModal.show")).to_have_count(1)
    page.evaluate("(fid) => openFilamentDetails(fid)", 8001)
    expect(page.locator("#filamentModal.show")).to_have_count(1)
    # The spool modal must now be hidden — Bootstrap fade can take a beat.
    page.wait_for_function(
        "() => !document.getElementById('spoolModal').classList.contains('show')"
    )
    # Belt-and-suspenders: there's only one open modal, not two.
    assert page.locator(".modal.show").count() == 1


def test_opening_spool_details_hides_filament_details(page: Page):
    """Mirror direction — opening spool from filament closes filament."""
    _wait_details_ready(page)
    _stub_details_endpoints(page, _STUB_SPOOL, _STUB_FIL)
    page.evaluate("(fid) => openFilamentDetails(fid)", 8001)
    expect(page.locator("#filamentModal.show")).to_have_count(1)
    page.evaluate("(id) => openSpoolDetails(id)", 9001)
    expect(page.locator("#spoolModal.show")).to_have_count(1)
    page.wait_for_function(
        "() => !document.getElementById('filamentModal').classList.contains('show')"
    )
    assert page.locator(".modal.show").count() == 1


def test_silent_refresh_does_not_hide_sibling_modal(page: Page):
    """sync-pulse silent refresh re-renders content for whichever modal is
    visible; it must NOT perturb visibility. Without the silent guard, a
    refresh could close the active modal."""
    _wait_details_ready(page)
    _stub_details_endpoints(page, _STUB_SPOOL, _STUB_FIL)
    page.evaluate("(id) => openSpoolDetails(id)", 9001)
    expect(page.locator("#spoolModal.show")).to_have_count(1)
    # Silent refresh of the OTHER modal — must not close spoolModal.
    page.evaluate("(fid) => openFilamentDetails(fid, true)", 8001)
    # Give any racing fade a chance to misbehave.
    page.wait_for_timeout(150)
    assert page.locator("#spoolModal.show").count() == 1, (
        "silent=true openFilamentDetails closed spoolModal — the silent "
        "refresh path must not change modal visibility."
    )
