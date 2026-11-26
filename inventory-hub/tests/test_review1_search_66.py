"""Group 66, review round 1, R4-08: the search panel's cards are drawn for the mode it opens in.

A card's click is fixed when the card is drawn: in select mode (the wizard's Advanced
Search) it picks the item for the wizard, otherwise it opens the item. Reopened with its
query held, the panel kept the last mode's cards: the dashboard's search picked nothing,
and the wizard's opened a filament instead of picking it. The cards are drawn again when
the mode changes.

Hermetic: the real offcanvas_search.html and inv_search.js (Group 66.8's panel fixture),
the card builder a stand-in that records the click it was drawn with. Each case fails on
the commit before the fix for the reason it names.
"""
from __future__ import annotations

from test_wizard_advanced_search_66_8_js import panel  # noqa: F401  (the fixture)

CARDS = r"""() => {
    window.SpoolCardBuilder = { buildCard: (item, ctx, o) =>
        `<div class="fake-card" data-click="${(o && o.callbackFn) || ''}">${item.id}</div>` };
    document.getElementById('global-search-query').value = 'red';
}"""


def _clicks(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#global-search-results .fake-card'))"
                         ".map((c) => c.dataset.click)")


def test_cards_drawn_for_a_pick_open_the_item_when_the_panel_opens_plain(panel):  # noqa: F811
    """RED: the cards still picked for the wizard."""
    panel.evaluate(CARDS)
    panel.evaluate("() => window.SearchEngine.open({ type: 'filament', callback: () => {} })")
    panel.evaluate("() => window.SearchEngine.renderResults([{ id: 1, type: 'filament' }])")
    assert _clicks(panel) == ["SearchEngine.selectItem"]
    panel.evaluate("() => window.SearchEngine.offcanvas.hide()")
    panel.evaluate("() => window.SearchEngine.open({})")
    assert _clicks(panel) == [""]


def test_cards_drawn_plain_pick_when_the_panel_opens_for_a_pick(panel):  # noqa: F811
    """RED: the wizard's Advanced Search opened the filament instead of picking it."""
    panel.evaluate(CARDS)
    panel.evaluate("() => window.SearchEngine.open({})")
    panel.evaluate("() => window.SearchEngine.renderResults([{ id: 1, type: 'filament' }])")
    assert _clicks(panel) == [""]
    panel.evaluate("() => window.SearchEngine.offcanvas.hide()")
    panel.evaluate("() => window.SearchEngine.open({ type: 'filament', callback: () => {} })")
    assert _clicks(panel) == ["SearchEngine.selectItem"]
