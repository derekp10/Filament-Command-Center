"""The title bar takes each of its steps only while the title is cut short
(titlebar_fit.js, Group 57 review, 2026-10-26), hermetic.

Runs the REAL static/js/modules/titlebar_fit.js on the REAL title bar markup
(lifted from templates/dashboard.html, its Jinja values filled in) with the
real static/css/global.css and the few Bootstrap 5.3 rules the bar leans on
(the real page loads Bootstrap from a CDN, which `isolated_page` can't reach),
so it RUNS under --offline. The bar's width is set directly, so the steps are
measured on this page's layout, not dev's.

Pinned: no step while the title fits; the steps come in their order (tighter
spacing, then ADD, then no version badge), each only once the title would be
cut without it; a count that grows takes a step and one that shrinks gives it
back (the bar watches its buttons' text); a Text size change fits again; below
992 px the script takes no step (the CSS does, as before); the version badge
never shrinks on the one-line bar. The bar on dev at every Text size is
test_text_size_setting_e2e.py's.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"
DASHBOARD = HUB / "templates" / "dashboard.html"
STEPS = ["fcc-tb-tight", "fcc-tb-add", "fcc-tb-nover"]

# What the bar takes from Bootstrap 5.3 (navbar, utilities, buttons).
BOOTSTRAP_BITS = """
*, ::before, ::after { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.navbar { position: relative; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; padding: .5rem 0; }
.navbar > .container-fluid { display: flex; flex-wrap: inherit; align-items: center; justify-content: space-between; }
@media (min-width: 992px) { .navbar-expand-lg { flex-wrap: nowrap; justify-content: flex-start; } }
.container-fluid { width: 100%; padding-right: .75rem; padding-left: .75rem; margin-right: auto; margin-left: auto; }
.navbar-brand { padding-top: .3125rem; padding-bottom: .3125rem; margin-right: 1rem; font-size: 1.25rem; white-space: nowrap; }
.badge { display: inline-block; padding: .35em .65em; font-size: .75em; font-weight: 700; line-height: 1; white-space: nowrap; border-radius: .375rem; }
.btn { display: inline-block; padding: .375rem .75rem; font-size: 1rem; line-height: 1.5; border: 1px solid #888; border-radius: .375rem; }
.d-flex { display: flex !important; } .d-inline-flex { display: inline-flex !important; }
.align-items-center { align-items: center !important; } .justify-content-center { justify-content: center !important; }
.gap-3 { gap: 1rem !important; }
.ms-2 { margin-left: .5rem !important; } .ms-3 { margin-left: 1rem !important; } .ms-4 { margin-left: 1.5rem !important; }
.border { border: 1px solid #ccc !important; }
"""


def _nav_markup():
    html = DASHBOARD.read_text(encoding="utf-8")
    m = re.search(r"<nav class=\"navbar.*?</nav>", html, re.S)
    assert m, "dashboard.html has no <nav class=\"navbar…\">"
    nav = m.group(0)
    nav = re.sub(r"\{\{\s*version\s*\}\}", "commit abcdef01 · 2026-10-26 20:00", nav)
    return re.sub(r"\{\{[^}]*\}\}", "0", nav)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{bootstrap}{css}</style></head><body>
{nav}
</body></html>"""


@pytest.fixture
def bar(isolated_page):
    page = isolated_page
    page.set_content(PAGE.format(bootstrap=BOOTSTRAP_BITS, css=GLOBAL_CSS.read_text(encoding="utf-8"),
                                 nav=_nav_markup()))
    page.evaluate("""() => { const n = document.querySelector('#btn-low-stock-count [data-low-stock-count]');
                             if (n) n.textContent = '12'; }""")
    page.add_script_tag(content=(MODULES / "titlebar_fit.js").read_text(encoding="utf-8"))
    return page


def _settle(page):
    """Two frames: the ResizeObserver and MutationObserver have run."""
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


def _state(page):
    return page.evaluate("""() => {
        const bar = document.querySelector('.fcc-titlebar');
        const brand = bar.querySelector('.navbar-brand');
        const ver = document.getElementById('fcc-build-version');
        return { steps: ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-nover'].filter((c) => bar.classList.contains(c)),
                 cut: brand.scrollWidth > brand.clientWidth + 1,
                 badge: getComputedStyle(ver).display === 'none' ? 'hidden'
                     : (ver.scrollWidth > ver.clientWidth + 1 ? 'squeezed' : 'whole') };
    }""")


def _width(page, px):
    page.evaluate("(w) => { document.querySelector('.fcc-titlebar').style.width = w + 'px'; }", px)
    _settle(page)
    return _state(page)


def _cut_without_last_step(page):
    """Takes the last step off for a moment: is the title then cut?"""
    return page.evaluate("""() => {
        const bar = document.querySelector('.fcc-titlebar');
        const brand = bar.querySelector('.navbar-brand');
        const on = ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-nover'].filter((c) => bar.classList.contains(c));
        const last = on[on.length - 1];
        bar.classList.remove(last);
        const cut = brand.scrollWidth > brand.clientWidth + 1;
        bar.classList.add(last);
        return cut;
    }""")


def test_no_step_while_the_title_fits(bar):
    s = _width(bar, 1900)
    assert s == {"steps": [], "cut": False, "badge": "whole"}, s


def test_each_step_comes_in_order_only_once_the_title_would_be_cut(bar):
    """From wide to narrow: none, then tight, then tight + ADD, then all three,
    and only then the title is cut (the last resort). Each step is taken only
    where the title would be cut without it. RED on 2d166e5 (fixed widths):
    the steps came at set widths, whatever the title had."""
    seen = []
    for px in range(1900, 899, -10):
        s = _width(bar, px)
        assert s["badge"] != "squeezed", (px, s)
        if s["steps"]:
            assert _cut_without_last_step(bar), f"{px} px: {s['steps'][-1]} taken with room to spare"
        if len(s["steps"]) < 3:
            assert not s["cut"], f"{px} px: the title is cut with a step still to take: {s}"
        if not seen or seen[-1] != s["steps"]:
            seen.append(s["steps"])
    assert seen[:4] == [[], STEPS[:1], STEPS[:2], STEPS], seen


def test_a_growing_count_takes_a_step_and_a_shrinking_one_gives_it_back(bar):
    """The bar watches its buttons' text: a Queue of 10 or a Backlog of 153
    takes a step where the old fixed widths cut the title (Group 57 review)."""
    for px in range(1900, 899, -5):
        if _width(bar, px)["steps"]:
            break
    _width(bar, px + 5)                                          # the widest bar that needs no step
    assert _state(bar)["steps"] == []
    bar.evaluate("() => { document.getElementById('btn-backlog-count').textContent = '🏷️ Backlog (1530)'; }")
    _settle(bar)
    grown = _state(bar)
    assert grown["steps"] == STEPS[:1] and not grown["cut"], grown
    bar.evaluate("() => { document.getElementById('btn-backlog-count').textContent = '🏷️ Backlog (0)'; }")
    _settle(bar)
    assert _state(bar)["steps"] == []


def test_a_text_size_change_fits_again(bar):
    """Settings' Text size changes the root size, not the bar's width: the
    fcc:text-size event (text_size.js) fits it again."""
    _width(bar, 1600)
    assert _state(bar)["steps"] == []
    bar.evaluate("""() => { document.documentElement.setAttribute('data-fcc-text-size', 'xlarge');
                             document.dispatchEvent(new CustomEvent('fcc:text-size')); }""")
    _settle(bar)
    s = _state(bar)
    assert s["steps"] and not (len(s["steps"]) < 3 and s["cut"]), s


def test_below_992_px_the_script_takes_no_step(bar):
    """There the buttons have a line of their own and the CSS tightens them
    and reads ADD, as it always did."""
    bar.set_viewport_size({"width": 900, "height": 900})
    bar.evaluate("() => { document.querySelector('.fcc-titlebar').style.width = ''; }")
    _settle(bar)
    assert _state(bar)["steps"] == []
    look = bar.evaluate("""() => ({ gap: getComputedStyle(document.querySelector('.fcc-titlebar-actions')).columnGap,
        more: getComputedStyle(document.querySelector('.fcc-titlebar-more')).display })""")
    assert look == {"gap": "8px", "more": "none"}, look
