"""The shared spool card (ui_builder.js, SpoolCardBuilder) draws Spoolman's free text as
text in every mode (Group 58 review of 7e3720f, R-6), hermetic.

The REAL inv_core.js (escHtml, getFilamentStyle, makeSwatchHtml, auditLostWords) and
ui_builder.js, in `isolated_page` (a chromium with no route to any network) through
test_slow_scan_slash_js's `scan_page`, so it runs under --offline; each card goes into
a real DOM, so markup in a name would make real elements.

The defect: the core card (search, a location's list, the buffer), the grid's tiles
(a spool stored in a slot, and one deployed from it), the Quick-Swap card and the
buffer's nav cards put the colour name, brand, material, legacy id and display into
their HTML as they came. After Done filed a spool whose filament is "Robin's <Egg> &
Blue" into a box, its Unslotted Items card read "Robin'S & Blue" and held a real <egg>
element. The picker and Printer Status variants already escaped theirs: they are
pinned here not to escape twice. RED on 99f4827 unless a test says it pins what was
already right.
"""
from __future__ import annotations

import pytest

from test_slow_scan_slash_js import MODULES, scan_page  # noqa: F401  (scan_page: the fixture)

COLOUR = "Robin's <Egg> & Blue"
BRAND = "Brand<brandx>X</brandx>"
MATERIAL = "PLA<matx>+</matx>"
LEGACY = "LEG<legx>1</legx>"
ITEM = {"id": 303, "type": "spool", "display": f"#303 {BRAND} {MATERIAL} ({COLOUR})", "color": "72071C",
        "color_direction": "longitudinal", "location": "CR-MDB-1", "slot": "2", "remaining_weight": 500,
        "details": {"color_name": COLOUR, "brand": BRAND, "material": MATERIAL, "external_id": LEGACY,
                    "weight": 500}}
LINE2 = f"{BRAND} {MATERIAL}"

# Each mode and the free text it shows, as the person must read it.
CASES = [
    ("search", {}, {}, [MATERIAL, BRAND, COLOUR]),
    ("loc_list", {"locId": "CR-MDB-1", "index": 0}, {}, [MATERIAL, BRAND, COLOUR]),
    ("buffer", {"isFirst": True, "index": 0}, {}, [MATERIAL, BRAND, COLOUR]),
    ("loc_grid", {"slotNum": 2, "locId": "CR-MDB-1"}, {}, [f"#303 [Legacy: {LEGACY}]", LINE2, COLOUR]),
    ("loc_grid", {"slotNum": 2, "locId": "CR-MDB-1"}, {"is_ghost": True, "deployed_to": "XL-1"},
     [f"#303 [Legacy: {LEGACY}]", LINE2, COLOUR]),
    ("quickswap", {"box": "CR-MDB-1", "slot": "2", "toolhead": "XL-1"}, {}, [COLOUR, LINE2]),
    ("buffer_nav", {"navDirection": "prev", "navAction": "window.prevBuffer()"}, {}, [f"{BRAND} {MATERIAL} ({COLOUR})"]),
    ("buffer_nav", {"navDirection": "next", "navAction": "window.nextBuffer()"}, {}, [f"{BRAND} {MATERIAL} ({COLOUR})"]),
]
# Already escaped (Groups 40.1 and 50.4): the same words, never escaped twice.
ESCAPED_ALREADY = [("picker", {}, {}, [COLOUR, LINE2]), ("printer-status", {}, {}, [COLOUR, MATERIAL])]

BUILD = """([item, mode, opts]) => {
    const host = document.createElement('div');
    host.id = 'fcc-card-host';
    document.body.appendChild(host);
    host.innerHTML = window.SpoolCardBuilder.buildCard(item, mode, opts);
    const made = Array.from(host.querySelectorAll('egg, brandx, matx, legx')).map((e) => e.tagName.toLowerCase());
    const text = host.textContent.replace(/\\s+/g, ' ');
    host.remove();
    return { made, text };
}"""


@pytest.fixture
def cards(scan_page):
    scan_page.add_script_tag(content=(MODULES / "ui_builder.js").read_text(encoding="utf-8"))
    return scan_page


def _card(page, mode, opts, more):
    return page.evaluate(BUILD, [dict(ITEM, **more), mode, opts])


@pytest.mark.parametrize("mode, opts, more, shows", CASES,
                         ids=[f"{c[0]}{'-' + c[1]['navDirection'] if 'navDirection' in c[1] else ''}"
                              f"{'-deployed' if c[2].get('is_ghost') else ''}" for c in CASES])
def test_every_card_draws_spoolmans_free_text_as_text(cards, mode, opts, more, shows):
    got = _card(cards, mode, opts, more)
    assert got["made"] == [], (mode, got)
    for words in shows:
        assert words in got["text"], (mode, words, got["text"])


@pytest.mark.parametrize("mode, opts, more, shows", ESCAPED_ALREADY, ids=[c[0] for c in ESCAPED_ALREADY])
def test_the_variants_that_escaped_already_still_escape_once(cards, mode, opts, more, shows):
    """Pins what was already right: no element, the words as they are, and no "&amp;"
    or "&lt;" from a second escape."""
    got = _card(cards, mode, opts, more)
    assert got["made"] == [], (mode, got)
    for words in shows:
        assert words in got["text"], (mode, words, got["text"])
    assert "&amp;" not in got["text"] and "&lt;" not in got["text"], got["text"]


def test_an_ordinary_spools_card_is_the_same_words(cards):
    """Pins what was already right: an ordinary name reads exactly as before, with no
    escape showing."""
    item = dict(ITEM, display="#57 Some Brand PLA (Red)",
                details={"color_name": "Red", "brand": "Some Brand", "material": "PLA", "weight": 500})
    got = cards.evaluate(BUILD, [item, "loc_list", {"locId": "LR-MDB-1", "index": 0}])
    assert "PLA Some Brand Red" in got["text"] and "&" not in got["text"], got["text"]
