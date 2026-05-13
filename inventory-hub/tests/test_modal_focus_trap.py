"""Group 8.1 follow-up — modal focus-trap regression coverage.

Locks in the audit findings from feature/keyboard-nav-polish:
  - Bootstrap modals trap Tab cycling within the modal subtree (no leak
    to background page elements or browser chrome).
  - Stacked modals (modal-on-modal, modal-on-offcanvas) trap focus in the
    topmost overlay; the background overlay does not steal focus.
  - Escape dismisses the modal — including the spool/filament details
    modals which carry data-bs-keyboard="false" and rely on a custom
    Escape handler.

Why it matters: Derek reported one occurrence where Tab leaked from a
modal into background modals or the browser UI. The audit could not
reproduce it, but these tests would catch a regression that reintroduces
the leak (e.g. a modal added without `tabindex="-1"`, a custom keydown
handler that swallows Tab, or a Bootstrap upgrade that breaks
_enforceFocus).
"""
from __future__ import annotations

from playwright.sync_api import Page, expect
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Bootstrap modal fade is 300ms. _enforceFocus and any custom
# shown.bs.modal listeners run after the fade, so wait 500ms before
# Tab-pressing.
_BS_MODAL_FADE_MS = 500

# How many Tab presses to count as "trapped". 30 is more than the
# focusable count of every modal in the app at the time of writing
# (max ~17 in manageModal; locMgrModal has 240 nested but they're all
# inside the modal so cycling stays in scope).
_TAB_SWEEP = 30


def _wait_app_ready(page: Page, reset_js: str = "") -> None:
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    # Defensive cross-test pollution teardown (Group 16.3). Optional so old
    # callers stay compatible during the migration window.
    if reset_js:
        page.evaluate(reset_js)
        page.wait_for_timeout(200)
    page.wait_for_function("typeof bootstrap !== 'undefined'")
    page.wait_for_function("typeof window.openAddModal === 'function'")
    page.wait_for_function("typeof window.openVendorCreateModal === 'function'")


def _open_via_bootstrap(page: Page, modal_id: str) -> None:
    page.evaluate(
        f"() => bootstrap.Modal.getOrCreateInstance(document.getElementById('{modal_id}')).show()"
    )
    page.wait_for_selector(f"#{modal_id}.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)


def _assert_tab_trapped(page: Page, container_selector: str, presses: int = _TAB_SWEEP) -> None:
    """Press Tab `presses` times and assert activeElement stays inside `container_selector`."""
    leaks = []
    for i in range(presses):
        page.keyboard.press("Tab")
        info = page.evaluate(
            f"""() => {{
                const c = document.querySelector('{container_selector}');
                const ae = document.activeElement;
                return {{
                    inside: c.contains(ae),
                    tag: ae && ae.tagName,
                    id: ae && ae.id,
                }};
            }}"""
        )
        if not info["inside"]:
            leaks.append({"step": i + 1, **info})
    assert not leaks, (
        f"Tab leaked {len(leaks)}/{presses} times outside {container_selector}. "
        f"First leak: {leaks[0]}"
    )


def _assert_shift_tab_trapped(page: Page, container_selector: str, presses: int = _TAB_SWEEP) -> None:
    leaks = []
    for i in range(presses):
        page.keyboard.press("Shift+Tab")
        info = page.evaluate(
            f"""() => {{
                const c = document.querySelector('{container_selector}');
                const ae = document.activeElement;
                return {{
                    inside: c.contains(ae),
                    tag: ae && ae.tagName,
                    id: ae && ae.id,
                }};
            }}"""
        )
        if not info["inside"]:
            leaks.append({"step": i + 1, **info})
    assert not leaks, (
        f"Shift+Tab leaked {len(leaks)}/{presses} times outside {container_selector}. "
        f"First leak: {leaks[0]}"
    )


def _assert_escape_dismisses(page: Page, modal_id: str) -> None:
    page.keyboard.press("Escape")
    page.wait_for_function(
        f"() => !document.getElementById('{modal_id}').classList.contains('show')",
        timeout=2_000,
    )


# ---------------------------------------------------------------------------
# Single-modal Tab trap — representative coverage across the modal types
# ---------------------------------------------------------------------------


# (modal_id, opener) — picks one modal from each category so we exercise
# every distinct opener path without over-multiplying test count.
_SINGLE_MODAL_CASES = [
    # Bootstrap-default Yes/No confirms (modals_core.html)
    ("confirmModal",       "_open_via_bootstrap"),
    # Larger lists / forms
    ("backlogModal",       "_open_via_bootstrap"),
    ("queueModal",         "_open_via_bootstrap"),
    ("manageModal",        "_open_via_bootstrap"),
    # Custom Escape handler (data-bs-keyboard=false)
    # — spoolModal / filamentModal handled in their own dedicated test
    # because they need stubbed fetches.
    # 8.1 auto-focus reference
    ("locModal",           "openAddModal"),
    # Vendor edit — auto-focuses #vendoredit-name on open
    ("vendorEditModal",    "openVendorCreateModal"),
]


@pytest.mark.parametrize("modal_id,opener", _SINGLE_MODAL_CASES, ids=[c[0] for c in _SINGLE_MODAL_CASES])
def test_single_modal_traps_tab(page: Page, modal_id: str, opener: str, reset_dom_state_js: str):
    _wait_app_ready(page, reset_dom_state_js)
    if opener == "_open_via_bootstrap":
        _open_via_bootstrap(page, modal_id)
    elif opener == "openAddModal":
        page.evaluate("() => window.openAddModal()")
        page.wait_for_selector(f"#{modal_id}.show", timeout=5_000)
        page.wait_for_timeout(_BS_MODAL_FADE_MS)
    elif opener == "openVendorCreateModal":
        page.evaluate("() => window.openVendorCreateModal({})")
        page.wait_for_selector(f"#{modal_id}.show", timeout=5_000)
        page.wait_for_timeout(_BS_MODAL_FADE_MS)
    _assert_tab_trapped(page, f"#{modal_id}")
    _assert_shift_tab_trapped(page, f"#{modal_id}")
    _assert_escape_dismisses(page, modal_id)


# ---------------------------------------------------------------------------
# spoolModal / filamentModal — custom Escape handler path
# ---------------------------------------------------------------------------


_DETAILS_STUB = """() => {
    const sp = {id:9001, spool_weight:250, filament:{id:8001,name:"T",material:"PLA",color_hex:"112233",vendor:{id:91,name:"V"}}};
    const fl = {id:8001,name:"T",material:"PLA",color_hex:"112233",vendor:{id:91,name:"V"},extra:{}};
    const orig = window.fetch;
    window.fetch = async (url, opts) => {
        const u = typeof url === "string" ? url : (url && url.url) || "";
        if (u.startsWith("/api/spool_details")) return new Response(JSON.stringify(sp), {status:200, headers:{"Content-Type":"application/json"}});
        if (u.startsWith("/api/filament_details")) return new Response(JSON.stringify(fl), {status:200, headers:{"Content-Type":"application/json"}});
        if (u.startsWith("/api/spools_by_filament")) return new Response(JSON.stringify([]), {status:200, headers:{"Content-Type":"application/json"}});
        return orig(url, opts);
    };
}"""


def _wait_details_ready(page: Page, reset_js: str = "") -> None:
    _wait_app_ready(page, reset_js)
    page.wait_for_function("typeof openSpoolDetails === 'function'")
    page.wait_for_function("typeof openFilamentDetails === 'function'")
    page.evaluate(_DETAILS_STUB)


def test_spool_modal_traps_tab_and_escape_dismisses(page: Page, reset_dom_state_js: str):
    """spoolModal has data-bs-keyboard='false'; relies on the custom
    Escape handler in inv_details.js DOMContentLoaded block."""
    _wait_details_ready(page, reset_dom_state_js)
    page.evaluate("(id) => openSpoolDetails(id)", 9001)
    page.wait_for_selector("#spoolModal.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    _assert_tab_trapped(page, "#spoolModal")
    _assert_escape_dismisses(page, "spoolModal")


def test_filament_modal_traps_tab_and_escape_dismisses(page: Page, reset_dom_state_js: str):
    _wait_details_ready(page, reset_dom_state_js)
    page.evaluate("(fid) => openFilamentDetails(fid)", 8001)
    page.wait_for_selector("#filamentModal.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    _assert_tab_trapped(page, "#filamentModal")
    _assert_escape_dismisses(page, "filamentModal")


# ---------------------------------------------------------------------------
# Multi-modal stacking — Derek's reported scenario
# ---------------------------------------------------------------------------


def test_stacked_locmgr_then_locmodal_traps_in_top(page: Page, reset_dom_state_js: str):
    """Open locMgrModal, then openAddModal stacks locModal on top.
    Tab must stay inside locModal, not leak back to locMgrModal."""
    _wait_app_ready(page, reset_dom_state_js)
    _open_via_bootstrap(page, "locMgrModal")
    page.evaluate("() => window.openAddModal()")
    page.wait_for_selector("#locModal.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    _assert_tab_trapped(page, "#locModal")


def test_stacked_queue_then_clear_confirm_traps_in_top(page: Page, reset_dom_state_js: str):
    _wait_app_ready(page, reset_dom_state_js)
    _open_via_bootstrap(page, "queueModal")
    _open_via_bootstrap(page, "clearQueueConfirmModal")
    _assert_tab_trapped(page, "#clearQueueConfirmModal")


def test_filament_modal_then_edit_filament_modal_stacked(page: Page, reset_dom_state_js: str):
    """Edit Filament opens via the pencil button inside Filament Details —
    a real-app stacking case for the data-bs-keyboard='false' modals."""
    _wait_details_ready(page, reset_dom_state_js)
    page.wait_for_function("typeof window.openEditFilamentForm === 'function'")
    page.evaluate("(fid) => openFilamentDetails(fid)", 8001)
    page.wait_for_selector("#filamentModal.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    page.evaluate(
        "() => window.openEditFilamentForm({id:8001, name:'T', material:'PLA', color_hex:'112233', extra:{}})"
    )
    page.wait_for_selector("#editFilamentModal.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    _assert_tab_trapped(page, "#editFilamentModal")


# ---------------------------------------------------------------------------
# Modal-on-offcanvas — Search offcanvas + Spool Details opened from inside
# ---------------------------------------------------------------------------


def test_offcanvas_search_alone_traps_tab(page: Page, reset_dom_state_js: str):
    _wait_app_ready(page, reset_dom_state_js)
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_selector("#offcanvasSearch.show")
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    _assert_tab_trapped(page, "#offcanvasSearch")


def test_modal_opened_from_offcanvas_keeps_focus_in_modal(page: Page, reset_dom_state_js: str):
    """Open Search offcanvas → click View Details on a result → Spool
    Details modal opens on top. Tab must stay inside the modal, not
    leak back into the offcanvas."""
    _wait_app_ready(page, reset_dom_state_js)
    page.locator('nav button:has-text("SEARCH")').click()
    page.wait_for_selector("#offcanvasSearch.show")
    page.locator("#global-search-query").fill("a")
    page.wait_for_selector(
        "#offcanvasSearch .fcc-card-action-btn[title='View Details']", timeout=10_000
    )
    page.click("#offcanvasSearch .fcc-card-action-btn[title='View Details']")
    page.wait_for_selector("#spoolModal.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    _assert_tab_trapped(page, "#spoolModal")


# ---------------------------------------------------------------------------
# Auto-focus lands inside the modal (not on body / background)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("modal_id", ["confirmModal", "backlogModal", "queueModal", "manageModal", "vendorEditModal", "locModal"])
def test_auto_focus_lands_inside_modal(page: Page, modal_id: str, reset_dom_state_js: str):
    """Bootstrap focuses the modal element itself on .show (the
    tabindex='-1' makes this possible). Custom openers (locModal,
    vendorEditModal) focus a specific input. Either way, focus must
    be inside the modal subtree before the user presses any key."""
    _wait_app_ready(page, reset_dom_state_js)
    if modal_id == "locModal":
        page.evaluate("() => window.openAddModal()")
    elif modal_id == "vendorEditModal":
        page.evaluate("() => window.openVendorCreateModal({})")
    else:
        page.evaluate(
            f"() => bootstrap.Modal.getOrCreateInstance(document.getElementById('{modal_id}')).show()"
        )
    page.wait_for_selector(f"#{modal_id}.show", timeout=5_000)
    page.wait_for_timeout(_BS_MODAL_FADE_MS)
    inside = page.evaluate(
        f"() => document.getElementById('{modal_id}').contains(document.activeElement)"
    )
    assert inside, f"Auto-focus did not land inside #{modal_id}"
