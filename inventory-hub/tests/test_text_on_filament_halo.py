"""Group 50.8 (Derek, 2026-10-30): text drawn on a filament's colour has one look, defined once.

Derek: "Yes we should match the style if it's more readable and better. I think there's some design code shared
between these and the buffer cards, basically any filament representation ... Changes should be made there." The
look, white in a dark halo, is `--fcc-text-halo` in global.css's :root, the only place its value is written;
`.text-pop` and every class for card text on a filament colour use it (copies of it, and weaker shadows that left a
card's title, its legacy id, a backlog row and the Printer Status band's label faint on a light spool, went); and
getFilamentStyle (inv_core.js), the helper every filament card takes its colours from, names the class
(`text: 'text-pop'`), which the slot picker's and Quick-Swap's cards now put on their text (they had none).

Pinned two ways: the stylesheet itself (no browser), and every card SpoolCardBuilder draws, rendered with a white
spool in `isolated_page` with the real global.css, inv_core.js and ui_builder.js: each piece of text that sits on
the spool's colour (no box of its own under it) wears the halo, and so does the Printer Status band's label.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
CSS = HUB / "static" / "css" / "global.css"
MODULES = HUB / "static" / "js" / "modules"
HALO = "2px 2px 4px rgba(0, 0, 0, 0.9), -1px -1px 2px rgba(0, 0, 0, 0.6), 0 0 8px rgba(0, 0, 0, 0.8)"

# Every class for text on a filament card's colour (the nav deck's centre card, the backlog rows, the Location
# Manager's grid and list, the buffer and search cards, the Printer Status band).
ON_FILAMENT = [".text-pop", ".fcc-card-metric", ".fcc-card-title", ".cham-id-badge", ".cham-text", ".slot-num-gold",
               ".text-line-1", ".text-line-2", ".text-line-3", ".text-line-4", "#loc-mgr-nav-deck .nav-label",
               "#loc-mgr-nav-deck .nav-text-main", ".fcc-ps-th-id", ".fcc-ps-th-label", ".fcc-subtext"]


def _rules(css):
    """(selector, body) for every rule, those inside @media / @container blocks too."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)]


def test_the_halo_is_written_once_and_every_card_text_class_uses_it():
    css = CSS.read_text(encoding="utf-8")
    assert css.count(HALO) == 1, "the halo's value is written once, in :root"
    rules = _rules(css)
    assert any(f"--fcc-text-halo: {HALO};" in body for sel, body in rules if sel == ":root"), "not in :root"
    for sel in ON_FILAMENT:
        bodies = [body for s, body in rules if s == sel]
        shadows = [part.strip() for body in bodies for part in body.split(";") if part.strip().startswith("text-shadow")]
        assert shadows and all("var(--fcc-text-halo)" in x for x in shadows), (sel, shadows)


def test_the_colour_helper_names_the_class():
    src = (MODULES / "inv_core.js").read_text(encoding="utf-8")
    assert "isSolid: isSolid, text: 'text-pop' };" in src


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>
<body style="background:#111; margin:0;">
<div id="cards" style="display:flex; flex-wrap:wrap; gap:12px; padding:12px; width:1240px;"></div>
<div class="fcc-ps-th" style="width:10.5rem;"><div class="fcc-ps-th-body" id="band"
     style="background:linear-gradient(to bottom, rgba(245,245,245,1), rgba(245,245,245,0.6));">
  <div class="fcc-ps-th-id text-truncate">XL-1</div></div></div>
</body></html>"""

PRELUDE = r"""
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.registerShortcut = function () {};
"""

RENDER_JS = r"""(halo) => {
  const item = { id: 77, display: '#77 Elegoo White PLA', color: 'f5f5f5', color_direction: 'longitudinal',
                 remaining_weight: 640, initial_weight: 1000, archived: false,
                 details: { material: 'PLA', brand: 'Elegoo', color_name: 'White', external_id: 'L-12' } };
  const ghost = Object.assign({}, item, { id: 78, is_ghost: true, deployed_to: 'XL-1', location: 'BOX-1' });
  const host = document.getElementById('cards');
  const modes = [['search', item, {}], ['buffer', item, {}], ['loc_list', item, { locId: 'BOX-1' }],
                 ['loc_grid', item, { slotNum: 2, locId: 'BOX-1' }], ['loc_grid', ghost, { slotNum: 3, locId: 'BOX-1' }],
                 ['picker', item, {}], ['quickswap', item, { box: 'BOX-1', slot: '2', toolhead: 'XL-1' }]];
  modes.forEach(([mode, it, opts]) => {
    const w = document.createElement('div');
    w.dataset.mode = mode + (it.is_ghost ? '-deployed' : '');
    w.style.width = '18rem';
    w.innerHTML = window.SpoolCardBuilder.buildCard(it, mode, opts);
    host.appendChild(w);
  });
  const probe = document.createElement('span');
  probe.style.textShadow = halo;   // the look itself, as written in :root
  document.body.appendChild(probe);
  const want = getComputedStyle(probe).textShadow;
  const alpha = (c) => { const m = /rgba?\(([^)]+)\)/.exec(c || ''); if (!m) return 0;
                         const p = m[1].split(',').map(Number); return p.length > 3 ? p[3] : 1; };
  const emojiOnly = /^[\p{Extended_Pictographic}️‍\s]*$/u;
  const checked = {}; const out = [];
  host.querySelectorAll(':scope > div').forEach((w) => {
    checked[w.dataset.mode] = 0;
    w.querySelectorAll('*').forEach((el) => {
      const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
      if (!own || emojiOnly.test(own)) return;
      // A Bootstrap badge is a box of its own on the page (Bootstrap, from a CDN,
      // isn't in this one, so its background isn't drawn here).
      if (el.closest('.fcc-card-action-btn, button, [id^="qr-"], .badge')) return;
      // On a box of its own (a dark label, a badge), not on the spool's colour.
      for (let a = el; a && a !== w; a = a.parentElement) {
        if (alpha(getComputedStyle(a).backgroundColor) >= 0.5) return;
      }
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      checked[w.dataset.mode] += 1;
      const ts = getComputedStyle(el).textShadow;
      if (ts !== want) out.push({ mode: w.dataset.mode, text: own.slice(0, 40), cls: String(el.className), ts });
    });
  });
  const band = getComputedStyle(document.querySelector('#band .fcc-ps-th-id'));
  return { want, out, checked, band: { ts: band.textShadow, color: band.color } };
}"""


@pytest.fixture
def cards(isolated_page):
    page = isolated_page
    page.set_viewport_size({"width": 1280, "height": 1400})
    page.set_content(PAGE.format(css=CSS.read_text(encoding="utf-8")))
    page.add_script_tag(content=PRELUDE)
    for name in ("inv_core.js", "ui_builder.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    yield page
    assert page.evaluate("window.__errors") == []


def test_every_cards_text_on_a_white_spool_wears_the_halo(cards):
    got = cards.evaluate(RENDER_JS, HALO)
    assert got["want"] and got["want"] != "none", got["want"]
    # Each card had text on its colour to check (the walk didn't skip them all).
    assert all(n >= 2 for n in got["checked"].values()), got["checked"]
    assert got["out"] == [], got["out"]


def test_the_printer_status_bands_label_is_white_in_the_halo(cards):
    """Derek, 2026-10-30, of the band's toolhead label beside its material:
    match the material's more readable style (it was a softer shadow, faint
    on a white spool, in a translucent white)."""
    got = cards.evaluate(RENDER_JS, HALO)
    assert got["band"] == {"ts": got["want"], "color": "rgb(255, 255, 255)"}, got["band"]
