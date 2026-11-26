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

from test_quick_weigh_scan_js import later, press
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
    """A pin: a save of another manufacturer leaves the list's spools as they were read,
    even one of the same name (review round 3, R3-01: the D1 duplicates, two manufacturers
    called Sunlu; a listener that matched by name passed when the other one was "Other")."""
    page, open_ = wo
    page.evaluate(SECOND_ACME)
    open_(held=(8, 11), mode="gross")
    page.evaluate("""() => document.dispatchEvent(new CustomEvent('vendor:updated', { detail: {
        id: '4', vendor: { id: 4, name: 'Acme', empty_spool_weight: 167 } } }))""")
    page.focus('.weigh-input[data-id="11"]')
    press(page, "1167", 150)
    page.wait_for_timeout(400)
    assert _updates(page) == []         # no empty weight known: it asks for one first
    assert page.evaluate("() => !!(window.getOverlay && window.getOverlay('fcc-missing-empty-weight-overlay'))")


# Review round 3 (weights-vendor R3-01, its twin tests-adversary R3-06): a typed tare survives
# a brand's weight saved over the list.

REFUSE_FIRST_SAVE = r"""() => {
    const orig = window.fetch;
    window.__refused = 0;
    window.fetch = function (url, opts) {
        const u = String(url);
        if (u.includes('/api/spool/update') && window.__refused === 0) {
            window.__refused = 1;
            const body = opts && opts.body ? JSON.parse(opts.body) : null;
            window.__posts.push({ url: u, body });
            return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
                status: 'details_changed',
                msg: "#8's weight changed since this was read: press Enter in its box again",
                fresh: { initial: 1000, used: 0, archived: false } }) });
        }
        return orig.apply(this, arguments);
    };
}"""


def test_a_typed_tare_outlives_a_brands_weight_saved_over_the_list(wo):
    """The missing-tare question's answer is the spool's own (Group 63.7). A save that is
    refused and made again sends it as spool_weight, and the used weight worked out from it,
    whatever its brand's weight became meanwhile. RED: the listener recomputed the cached
    empty weight from the brand's new 200 g, and the retry sent spool_weight 210 beside a
    used weight worked out from 200 (90 g, not 100 g)."""
    page, open_ = wo
    page.evaluate(REFUSE_FIRST_SAVE)
    open_(held=(8, 6), mode="gross")
    press(page, "1110", 150)                    # #8 on the scale: 1110 g
    page.wait_for_function("() => document.activeElement"
                           " && document.activeElement.id === 'fcc-missing-empty-weight-overlay-input'")
    later(page, 800)
    press(page, "210", 150)                     # its empty spool weighs 210 g (the spool's own)
    _saved(page)                                # posted, and refused: details_changed
    first = _updates(page)[0]
    page.wait_for_timeout(300)
    # Another spool of Acme was weighed empty, and its post-archive prompt set Acme's default.
    page.evaluate("""() => document.dispatchEvent(new CustomEvent('vendor:updated', { detail: {
        id: '9', vendor: { id: 9, name: 'Acme', empty_spool_weight: 200 } } }))""")
    assert page.evaluate("() => weighOutDetailsCache.get(8).empty") == 210
    page.locator(".weigh-input[data-id='8']").focus()
    later(page, 800)
    press(page, "", 0)                          # Enter again in #8's box, as the toast asks
    _saved(page, 2)
    second = _updates(page)[1]
    assert second["updates"].get("spool_weight") == 210, second
    assert second["updates"]["used_weight"] == first["updates"]["used_weight"] == 100, (first, second)
    assert page.evaluate("() => window.__errors") == []
