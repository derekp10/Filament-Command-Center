"""Review round 2 of Group 66 (Q1-06): the weigh-out list hears a manufacturer's new empty
weight.

The post-archive prompt's "also the brand's default" saves the brand's empty weight and
tells every window (`vendor:updated`, Group 66.1), but the weigh-out list it opens over kept
each spool's details as it read them: its other spools of that brand still had no empty
weight, so a Gross reading asked for one again, for a brand that now has it (its Skip saves
the reading as filament left).

Hermetic, on test_weigh_out_scan_focus_js.py's page (the real weigh-out markup and modules,
the page's own fetch, a fake clock), so it runs under --offline. RED on f09bdc9c: the
missing-tare question opened and nothing was saved.
"""
from __future__ import annotations

from test_quick_weigh_scan_js import press
from test_weigh_out_scan_focus_js import _saved, _updates, wo  # noqa: F401

SECOND_ACME = r"""() => {
    window.__spools[11] = { id: 11, initial_weight: 1000, used_weight: 0,
        filament: { id: 6, name: 'Grey Two', material: 'PLA', vendor: { id: 9, name: 'Acme' } } };
    window.__rows[11] = { id: 11, display: 'Acme - PLA - Grey Two', color: '888888', remaining_weight: 1000 };
}"""


def test_a_brands_new_weight_reaches_the_lists_spools_of_that_brand(wo):
    page, open_ = wo
    page.evaluate(SECOND_ACME)
    open_(held=(8, 11), mode="gross")
    page.evaluate("""() => document.dispatchEvent(new CustomEvent('vendor:updated', { detail: {
        id: '9', vendor: { id: 9, name: 'Acme', empty_spool_weight: 167 } } }))""")
    page.focus('.weigh-input[data-id="11"]')
    press(page, "1167", 150)            # 1167 g on the scale, less Acme's 167 g: 1000 g left
    _saved(page)
    ups = _updates(page)
    assert [u["id"] for u in ups] == [11] and ups[0]["updates"]["used_weight"] == 0, ups
    assert not page.evaluate("() => !!(window.getOverlay && window.getOverlay('fcc-missing-empty-weight-overlay'))")
    assert page.evaluate("() => window.__errors") == []


def test_another_brands_save_changes_nothing(wo):
    """A pin: a save of another manufacturer leaves the list's spools as they were read."""
    page, open_ = wo
    page.evaluate(SECOND_ACME)
    open_(held=(8, 11), mode="gross")
    page.evaluate("""() => document.dispatchEvent(new CustomEvent('vendor:updated', { detail: {
        id: '4', vendor: { id: 4, name: 'Other', empty_spool_weight: 167 } } }))""")
    page.focus('.weigh-input[data-id="11"]')
    press(page, "1167", 150)
    page.wait_for_timeout(400)
    assert _updates(page) == []         # no empty weight known: it asks for one first
    assert page.evaluate("() => !!(window.getOverlay && window.getOverlay('fcc-missing-empty-weight-overlay'))")
