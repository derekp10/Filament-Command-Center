"""
Structural test for the unslotted-card default action change.

Verifies that SpoolCardBuilder.buildCard(item, 'loc_list', ...) renders an
onclick handler that calls ejectSpool(...,true) (Pick Up) on the card body,
NOT openSpoolDetails(...). The 🔍 icon must still call openSpoolDetails.

Backs Feature-Buglist line 51: "The default action for an unslotted item in
the Manage Location Modal should be changed to pick up."
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.usefixtures("require_server")
def test_loc_list_card_body_default_is_pick_up(page: Page, base_url: str):
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof window.SpoolCardBuilder?.buildCard === 'function'",
        timeout=10000,
    )

    html = page.evaluate(
        """() => {
            const item = {
                id: 999, type: 'spool', display: 'Test Spool',
                color: 'ff0000', remaining_weight: 500,
                details: 'PLA / Test'
            };
            return window.SpoolCardBuilder.buildCard(
                item, 'loc_list', { locId: 'TEST-LOC', index: 0 }
            );
        }"""
    )

    # Card body's primary onclick now calls ejectSpool(...,true) — Pick Up.
    assert "ejectSpool(999, 'TEST-LOC', true)" in html, (
        "Unslotted card body should call ejectSpool(...true) for Pick Up. "
        "Got HTML:\n" + html[:1500]
    )

    # Details affordance must remain on the 🔍 button.
    assert "openSpoolDetails(999)" in html, (
        "🔍 button should still call openSpoolDetails(999). "
        "Got HTML:\n" + html[:1500]
    )

    # Sanity: the manage-list-item class is still present (loc_list selector
    # used by Location Manager logic and tests).
    assert "manage-list-item" in html


@pytest.mark.usefixtures("require_server")
def test_loc_list_card_body_no_longer_opens_details(page: Page, base_url: str):
    """The card body's PRIMARY onclick must not be openSpoolDetails anymore."""
    page.goto(base_url)
    page.wait_for_function(
        "() => typeof window.SpoolCardBuilder?.buildCard === 'function'",
        timeout=10000,
    )

    # Pull the data-spool-id wrapper's onclick attribute specifically — the
    # outer card div is the one whose click should now Pick Up. (Inner action
    # buttons stop propagation so they're independent.)
    onclick = page.evaluate(
        """() => {
            const item = { id: 42, type: 'spool', display: 'Probe',
                           color: '00ff00', remaining_weight: 100, details: 'X' };
            const html = window.SpoolCardBuilder.buildCard(
                item, 'loc_list', { locId: 'PROBE-LOC', index: 0 });
            const tmp = document.createElement('div');
            tmp.innerHTML = html;
            const card = tmp.querySelector('[data-spool-id="42"]');
            return card ? card.getAttribute('onclick') : null;
        }"""
    )

    assert onclick is not None, "Card with data-spool-id=42 not found in rendered HTML"
    assert "ejectSpool(42, 'PROBE-LOC', true)" in onclick, (
        f"Card body onclick should be ejectSpool(...true). Got: {onclick!r}"
    )
    assert "openSpoolDetails" not in onclick, (
        f"Card body onclick must no longer call openSpoolDetails. Got: {onclick!r}"
    )
