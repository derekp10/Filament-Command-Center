"""Group-34 sub-location add-redesign — S1/S2/S3 pins.

Sub-phases built on the authoritative explicit-parent model (Phase 0/Phase-5):
  S1  per-row "➕ Add child" that pre-seeds Parent = the clicked row + inferred
      Type/Max, SUPPRESSED on Printer / Tool Head / MMU Slot rows.
  S2  auto-generated editable LocationID (parent + type-abbrev + next index;
      new-rows-only, never all-numeric).
  S3  a mountOverlay tree picker over window.buildLocationTree, reachable via
      "🌳 Browse…", emitting the same parent save contract.

Source canaries pin the wiring offline; the live-DOM tests drive the real flow
(skip cleanly via require_server when the dev container is down).
"""
import os

from playwright.sync_api import Page

_HUB = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    path = os.path.join(_HUB, *parts)
    assert os.path.exists(path), f"missing: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Source canaries — wiring pins (no server needed)
# ---------------------------------------------------------------------------

def test_add_child_button_and_suppression_in_render():
    core = _read("static", "js", "modules", "inv_core.js")
    assert "btn-add-child" in core, "the per-row Add-child button must be rendered"
    assert "canAddChild" in core and "NO_ADD_CHILD_TYPES" in core, "suppression helper must exist"
    for suppressed in ("'printer'", "'tool head'", "'mmu slot'", "'no mmu direct load'"):
        assert suppressed in core, f"Add-child must be suppressed on {suppressed} rows"


def test_add_child_delegated_handler_wired():
    scripts = _read("templates", "components", "scripts.html")
    assert "btn-add-child" in scripts and "window.openAddChild(" in scripts, (
        "the tree table must delegate .btn-add-child clicks to window.openAddChild"
    )


def test_inference_and_autoid_helpers_present():
    mgr = _read("static", "js", "modules", "inv_loc_mgr.js")
    assert "_inferChildDefaults" in mgr, "Type/Max inference must exist (S4)"
    assert "window.openAddChild" in mgr and "_openLocModalForCreate" in mgr, "add-child flow (S1)"
    assert "_suggestChildId" in mgr and "_typeSegmentAbbr" in mgr, "auto-id generation (S2)"
    # the shelf-hierarchy inference chain Room→Wall Shelf→Row→Section
    for pair in ("case 'room':", "case 'wall shelf':", "case 'row':"):
        assert pair in mgr, f"inference chain missing {pair}"


def test_tree_picker_present_and_uses_shared_helper():
    mgr = _read("static", "js", "modules", "inv_loc_mgr.js")
    assert "window.openParentTreePicker" in mgr, "the Browse-tree picker must exist (S3)"
    assert "window.buildLocationTree(pickable" in mgr, "picker must reuse the shared tree helper"
    assert "window.mountOverlay(" in mgr, "picker must route through the canonical overlay mount"
    # emits the same save contract (sentinels), never a divergent one
    assert "_LOC_PARENT_NONE" in mgr and "_LOC_PARENT_AUTO" in mgr
    html = _read("templates", "components", "modals_loc_mgr.html")
    assert 'id="edit-parent-browse"' in html and "openParentTreePicker()" in html, (
        "the '🌳 Browse…' affordance must be wired next to the Parent select"
    )


def test_escattr_exported_and_picker_escapes_attributes():
    """Review fix (stored-XSS): window.escAttr must be exported from inv_core.js
    (it wasn't — cross-module callers got an identity fallback), and the picker's
    escA must fall back to window.escHtml, NEVER to identity — a raw LocationID in
    data-tp-val is a stored-XSS vector."""
    core = _read("static", "js", "modules", "inv_core.js")
    assert "window.escAttr = escAttr" in core, "inv_core.js must export window.escAttr"
    mgr = _read("static", "js", "modules", "inv_loc_mgr.js")
    assert "window.escAttr || window.escHtml" in mgr, (
        "the picker must fall back to window.escHtml (which escapes quotes), not identity"
    )


# ---------------------------------------------------------------------------
# Live-DOM behavior — drives the real Location Manager (require_server)
# ---------------------------------------------------------------------------

def _open_mgr(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector(".deck-btn, #command-buffer", timeout=10000)
    page.evaluate("window.openLocationsModal && window.openLocationsModal()")
    page.wait_for_selector("#location-table tr[data-locid]", timeout=5000)
    page.wait_for_timeout(300)


def _has_add_child(page: Page, locid: str):
    return page.evaluate(
        """(id) => { const tr = document.querySelector('#location-table tr[data-locid="' + id + '"]');
                     return tr ? !!tr.querySelector('.btn-add-child') : null; }""",
        locid,
    )


def test_add_child_offered_on_shelf_kinds_suppressed_on_printer_topology(page: Page, base_url: str, require_server):
    _open_mgr(page, base_url)
    assert _has_add_child(page, "CR") is True, "a Room row must offer ➕ Add child"
    # Printer + toolhead rows must NOT (their source of truth is the printer-map editor)
    for tid in ("XL", "XL-1", "CORE1"):
        present = _has_add_child(page, tid)
        if present is not None:
            assert present is False, f"{tid} (printer topology) must NOT offer ➕ Add child"


def test_add_child_preseeds_parent_type_and_autoid(page: Page, base_url: str, require_server):
    _open_mgr(page, base_url)
    page.evaluate("window.openAddChild('CR')")
    page.wait_for_selector("#locModal.show", timeout=4000)
    page.wait_for_timeout(200)
    vals = page.evaluate(
        """() => ({
            origId: document.getElementById('edit-original-id').value,
            parent: document.getElementById('edit-parent').value,
            type: document.getElementById('edit-type').value,
            id: document.getElementById('edit-id').value,
            max: document.getElementById('edit-max').value,
        })"""
    )
    assert vals["origId"] == "", "add-child must be a CREATE (no original id)"
    assert vals["parent"].upper() == "CR", "Parent must be pre-seeded to the clicked room"
    assert vals["type"] == "Wall Shelf", "a Room's child Type must infer to Wall Shelf"
    assert vals["max"] == "0", "a structural grouping child must default to Max 0 (unbounded)"
    assert vals["id"].upper().startswith("CR-WL"), f"auto-id should be CR-WL<n>, got {vals['id']!r}"
    page.evaluate("window.closeEdit && window.closeEdit()")


def test_escattr_is_defined_and_escapes_live(page: Page, base_url: str, require_server):
    """Live: window.escAttr is defined and escapes quotes + angle brackets, so the
    picker's data-tp-val interpolation can't break out of the attribute."""
    _open_mgr(page, base_url)
    result = page.evaluate(
        """() => {
            if (typeof window.escAttr !== 'function') return 'escAttr-not-exported';
            const out = window.escAttr('A"><img src=x>');
            return (out.indexOf('"') === -1 && out.indexOf('<') === -1 && out.indexOf('>') === -1)
                ? 'ok' : ('not-escaped:' + out);
        }"""
    )
    assert result == "ok", result


def test_tree_picker_opens_and_writes_back_the_contract(page: Page, base_url: str, require_server):
    _open_mgr(page, base_url)
    page.evaluate("window.openAddChild('CR')")
    page.wait_for_selector("#locModal.show", timeout=4000)
    page.evaluate("window.openParentTreePicker()")
    page.wait_for_selector("#fcc-parent-tree-picker .fcc-tp-node", timeout=5000)
    # Pick the "Top level" sentinel node → edit-parent becomes __none__, overlay closes.
    page.evaluate(
        """() => { const n = [...document.querySelectorAll('#fcc-parent-tree-picker .fcc-tp-node')]
                     .find(x => x.dataset.tpVal === '__none__'); if (n) n.click(); }"""
    )
    page.wait_for_timeout(250)
    assert page.evaluate("() => document.getElementById('edit-parent').value") == "__none__"
    assert page.evaluate("() => !document.getElementById('fcc-parent-tree-picker')"), (
        "the picker overlay must clean itself up after a pick"
    )
    page.evaluate("window.closeEdit && window.closeEdit()")
