"""L271 Phase 3.5 — live multi-level tree E2E (collapse + pin).

Drives the real Location Manager DOM to pin the interactive behaviors the
API/source tests can't: 3-level nesting, nested collapse (collapsing a room
hides its printer AND that printer's toolheads), and the pin-printers toggle
floating printer subtrees to the top. Skips cleanly when the dev server is
down (require_server).
"""
import pytest
from playwright.sync_api import Page


def _open_mgr(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_selector(".deck-btn, #command-buffer", timeout=10000)
    page.evaluate("window.openLocationsModal && window.openLocationsModal()")
    page.wait_for_selector("#location-table tr[data-locid]", timeout=5000)
    page.wait_for_timeout(400)


def _rows(page: Page):
    return page.evaluate("""() => [...document.querySelectorAll('#location-table tr')].map(tr => ({
        id: tr.dataset.locid || '',
        anc: tr.dataset.ancestors || '',
        divider: tr.classList.contains('loc-divider') ? tr.textContent.trim() : null,
        hidden: tr.style.display === 'none',
        toggle: !!tr.querySelector('.loc-toggle'),
    }))""")


def test_tree_is_multilevel(page: Page, base_url: str, require_server):
    """A toolhead nests under its printer under its room — a 3-level chain."""
    _open_mgr(page, base_url)
    rows = {r["id"]: r for r in _rows(page) if r["id"]}
    if "XL-1" in rows:  # depends on the seeded printer
        assert rows["XL-1"]["anc"].split() == ["LR", "XL"], (
            f"XL-1 should nest LR>XL>XL-1, got ancestors {rows['XL-1']['anc']!r}"
        )
        assert rows["XL"]["anc"].split() == ["LR"], "XL should nest under LR"
        assert rows["XL"]["toggle"], "XL has toolhead children → expand toggle"


def test_collapse_room_hides_whole_subtree(page: Page, base_url: str, require_server):
    """Collapsing a room hides every descendant (incl. deeply-nested cart-rows
    and the printer's toolheads); re-expanding restores them."""
    _open_mgr(page, base_url)
    page.evaluate("window.toggleLocNode('CR')")
    page.wait_for_timeout(200)
    after = _rows(page)
    leaked = [r["id"] for r in after if r["id"] and not r["hidden"] and "CR" in r["anc"].split()]
    assert not leaked, f"CR descendants still visible after collapse: {leaked}"
    hidden = [r for r in after if r["id"] and r["hidden"] and "CR" in r["anc"].split()]
    assert len(hidden) >= 5, "expected the whole CR subtree hidden"
    # re-expand
    page.evaluate("window.toggleLocNode('CR')")
    page.wait_for_timeout(200)
    reshown = [r["id"] for r in _rows(page) if r["id"] and not r["hidden"] and "CR" in r["anc"].split()]
    assert reshown, "re-expanding CR should restore its descendants"


def test_pin_printers_floats_to_top(page: Page, base_url: str, require_server):
    """The pin toggle lifts printer subtrees above the rooms under a divider."""
    _open_mgr(page, base_url)
    try:
        page.evaluate("window.toggleLocPinPrinters()")
        page.wait_for_timeout(500)
        rows = _rows(page)
        order = [r["divider"] or r["id"] for r in rows]
        # a "Printers" divider exists and the first printer precedes the first room
        assert any(d and "Printers" in d for d in order if d), "expected a Printers divider when pinned"
        def first_idx(pred):
            for i, r in enumerate(rows):
                if pred(r):
                    return i
            return 10**9
        first_printer = first_idx(lambda r: r["id"] in ("XL", "CORE1"))
        first_room = first_idx(lambda r: r["id"] in ("CR", "DR", "LR"))
        assert first_printer < first_room, "pinned printers must precede rooms"
    finally:
        page.evaluate("window.toggleLocPinPrinters()")  # restore default
