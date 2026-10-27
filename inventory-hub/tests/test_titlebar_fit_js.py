"""The title bar takes each of its steps only while the title is cut short
(titlebar_fit.js, Group 57 review, 2026-10-26), hermetic.

Runs the REAL static/js/modules/titlebar_fit.js on the REAL title bar markup
(lifted from templates/dashboard.html, its Jinja values filled in) with the
real static/css/global.css and the few Bootstrap 5.3 rules the bar leans on
(the real page loads Bootstrap from a CDN, which `isolated_page` can't reach),
so it RUNS under --offline. The bar's width is set directly, so the steps are
measured on this page's layout, not dev's.

"Cut" is measured below the pixel, as the script measures it (round 2: on
whole pixels a title up to 1.5 px too wide read as fitting, and Chrome drew its
"…" with a step still free), and the steps are swept 1 px at a time around
each one.

Pinned: no step while the title fits; the steps come in their order (tighter
spacing, then ADD, then no version badge), each only once the title would be
cut without it, and never later; a count that grows takes a step and one that
shrinks gives it back (the bar watches its buttons' text); a Text size change
fits again, through its own event when the bar's box doesn't change; buttons
that still don't fit with every step taken put the bar on two lines (⚙️ stays
on screen) and give it back; the version badge reads in local time before the
first fit; below 992 px the script takes no step (the CSS does, as before); the
version badge never shrinks on the one-line bar. The bar on dev at every Text
size is test_text_size_setting_e2e.py's.
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
COMMIT_TS = 1793044800          # 2026-10-26, a fixed commit time for the badge

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
    nav = re.sub(r"\{\{\s*version\s*\}\}", "commit abcdef01 · 2026-10-26 20:00 UTC", nav)
    nav = re.sub(r"\{\{\s*build_commit_sha[^}]*\}\}", "abcdef01", nav)
    nav = re.sub(r"\{\{\s*build_commit_ts[^}]*\}\}", str(COMMIT_TS), nav)
    return re.sub(r"\{\{[^}]*\}\}", "0", nav)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>{bootstrap}{css}</style></head><body>
{nav}
</body></html>"""


def _page(page):
    page.set_content(PAGE.format(bootstrap=BOOTSTRAP_BITS, css=GLOBAL_CSS.read_text(encoding="utf-8"),
                                 nav=_nav_markup()))
    page.evaluate("""() => { const n = document.querySelector('#btn-low-stock-count [data-low-stock-count]');
                             if (n) n.textContent = '12'; }""")


@pytest.fixture
def bar(isolated_page):
    page = isolated_page
    _page(page)
    page.add_script_tag(content=(MODULES / "titlebar_fit.js").read_text(encoding="utf-8"))
    return page


def _settle(page):
    """Two frames: the ResizeObserver and MutationObserver have run."""
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")


# How much wider the title's text is than its box, below the pixel: a hidden
# copy with the title's own class (its own font), as titlebar_fit.js measures.
OVER_JS = """() => {
    const brand = document.querySelector('.fcc-titlebar .navbar-brand');
    const probe = document.createElement('span');
    probe.className = brand.className;
    probe.style.cssText = 'position:absolute;left:0;top:0;visibility:hidden;white-space:nowrap;min-width:0;max-width:none;';
    probe.textContent = brand.textContent;
    brand.parentNode.appendChild(probe);
    const need = probe.getBoundingClientRect().width;
    probe.remove();
    return need - brand.getBoundingClientRect().width;
}"""


def _over(page):
    return page.evaluate(OVER_JS)


def _state(page):
    s = page.evaluate("""() => {
        const bar = document.querySelector('.fcc-titlebar');
        const ver = document.getElementById('fcc-build-version');
        return { steps: ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-nover'].filter((c) => bar.classList.contains(c)),
                 wrap: bar.classList.contains('fcc-tb-wrap'),
                 badge: getComputedStyle(ver).display === 'none' ? 'hidden'
                     : (ver.scrollWidth > ver.clientWidth + 1 ? 'squeezed' : 'whole') };
    }""")
    s["cut"] = _over(page) > 0.01
    return s


def _width(page, px):
    """The bar exactly `px` wide (a flex item of the navbar, it would shrink to
    the 1600 px viewport)."""
    page.evaluate("(w) => { const b = document.querySelector('.fcc-titlebar'); b.style.flex = '0 0 auto';"
                  " b.style.width = w + 'px'; }", px)
    _settle(page)
    return _state(page)


def _cut_without_last_step(page):
    """Takes the last step off for a moment: is the title then cut?"""
    over = page.evaluate("""(overJs) => {
        const bar = document.querySelector('.fcc-titlebar');
        const on = ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-nover'].filter((c) => bar.classList.contains(c));
        const last = on[on.length - 1];
        bar.classList.remove(last);
        const over = (0, eval)('(' + overJs + ')')();
        bar.classList.add(last);
        return over;
    }""", OVER_JS)
    return over > 0.01


def _check(page, px):
    """One width: the badge never squeezed; a step only where the title would be
    cut without it; the title cut only once every step is taken."""
    s = _width(page, px)
    assert s["badge"] != "squeezed", (px, s)
    if s["steps"]:
        assert _cut_without_last_step(page), f"{px} px: {s['steps'][-1]} taken with room to spare"
    if len(s["steps"]) < 3:
        assert not s["cut"], f"{px} px: the title is cut with a step still to take: {s}"
    return s


def test_no_step_while_the_title_fits(bar):
    s = _width(bar, 1900)
    assert s == {"steps": [], "wrap": False, "cut": False, "badge": "whole"}, s


def test_each_step_comes_in_order_only_once_the_title_would_be_cut(bar):
    """From wide to narrow: none, then tight, then tight + ADD, then all three,
    and only then the title is cut (the last resort). Each step is taken only
    where the title would be cut without it, and never a pixel later: around
    each step the bar is checked 1 px at a time (round 2: on whole pixels the
    title stayed cut for 1 or 2 px above every step, "Filament Command Cent…"
    with the step still free). RED on 2d166e5 (fixed widths): the steps came at
    set widths, whatever the title had. RED on 6314386: the 1 px check."""
    seen, edges, last = [], [], None
    for px in range(1900, 899, -10):
        s = _check(bar, px)
        if last is not None and s["steps"] != last:
            edges.append(px)
        last = s["steps"]
        if not seen or seen[-1] != s["steps"]:
            seen.append(s["steps"])
    assert seen[:4] == [[], STEPS[:1], STEPS[:2], STEPS], seen
    for edge in edges[:3]:
        for px in range(edge + 12, edge - 3, -1):
            _check(bar, px)


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


def test_the_text_size_event_fits_the_bar_when_its_box_does_not_change(bar):
    """Small <-> Standard changes the badge's and labels' sizes but not the
    bar's box, so its ResizeObserver never fires: only the fcc:text-size event
    fits it again (round 2: the test above passed without the listener, the
    bar growing taller at Extra Large refitted it). Here the title grows wider
    and the box stays the same; nothing but the event fits it. RED with the
    listener removed."""
    for px in range(1900, 899, -5):
        if _width(bar, px)["steps"]:
            break
    _width(bar, px + 5)                                          # the widest bar that needs no step
    height = bar.evaluate("() => document.querySelector('.fcc-titlebar').getBoundingClientRect().height")
    bar.evaluate("""() => { const st = document.createElement('style');
        st.textContent = '.fcc-titlebar .navbar-brand { letter-spacing: 1px; }';
        document.head.appendChild(st); }""")
    _settle(bar)
    assert _state(bar)["steps"] == [] and _state(bar)["cut"], "the wider title should still wait for the event"
    assert bar.evaluate("() => document.querySelector('.fcc-titlebar').getBoundingClientRect().height") == height
    bar.evaluate("() => document.dispatchEvent(new CustomEvent('fcc:text-size'))")
    _settle(bar)
    s = _state(bar)
    assert s["steps"] == STEPS[:1] and not s["cut"], s


def test_buttons_that_still_do_not_fit_put_the_bar_on_two_lines(bar):
    """Extra Large in a window just over 992 px with big counts: every step
    taken and ⚙️ still ran past the edge, with no way to scroll to it (Group 57
    review, round 2). The bar takes a second line instead, as below 992 px: the
    title whole on its own line with the badge beside it, ⚙️ inside the bar.
    It gives the line back once the buttons fit."""
    bar.evaluate("""() => { document.documentElement.setAttribute('data-fcc-text-size', 'xlarge');
        document.dispatchEvent(new CustomEvent('fcc:text-size'));
        document.getElementById('btn-backlog-count').textContent = '🏷️ Backlog (1530)';
        document.getElementById('btn-queue-count').textContent = '🛒 Queue (25)';
        document.querySelector('#btn-low-stock-count [data-low-stock-count]').textContent = '120'; }""")
    one_line = bar.evaluate("() => document.querySelector('nav.navbar').getBoundingClientRect().height")
    s = _width(bar, 900)
    assert s["wrap"] and s["steps"] == STEPS[:2], s
    look = bar.evaluate("""() => { const bar = document.querySelector('.fcc-titlebar');
        const r = bar.getBoundingClientRect(); const cs = getComputedStyle(bar);
        const edge = r.right - parseFloat(cs.paddingRight);
        return { gear: document.getElementById('btn-config').getBoundingClientRect().right <= edge + 0.5,
                 nav: document.querySelector('nav.navbar').getBoundingClientRect().height }; }""")
    assert look["gear"] and look["nav"] > one_line, look
    assert not s["cut"] and s["badge"] == "whole", s
    s = _width(bar, 1900)
    assert not s["wrap"], s


def test_the_title_never_draws_over_the_spoolman_light(bar):
    """A title cut to nothing still draws its first letter (its glow's clip
    margin), and it ran over the Spoolman light (round 2): the brand group
    keeps the title's own right margin, so the light starts past the letter."""
    bar.evaluate("""() => { document.documentElement.setAttribute('data-fcc-text-size', 'xlarge');
        document.dispatchEvent(new CustomEvent('fcc:text-size')); }""")
    for px in range(1300, 899, -10):
        s = _width(bar, px)
        if s["wrap"]:
            break
        gap = bar.evaluate("""() => { const brand = document.querySelector('.fcc-titlebar .navbar-brand');
            const clip = parseFloat(getComputedStyle(brand).overflowClipMargin) || 0;
            return document.querySelector('#st-spoolman').getBoundingClientRect().left
                - (brand.getBoundingClientRect().right + clip); }""")
        assert gap >= -0.5, (px, s, gap)


def test_the_version_badge_reads_in_local_time_before_the_first_fit(isolated_page):
    """L42's local text was written at DOMContentLoaded, after the first paint:
    the bar was fitted to the server's longer UTC text, and the buttons moved
    about 100 ms into every load (round 2). The script writes it first."""
    page = isolated_page
    _page(page)
    page.add_script_tag(content="""(() => { const real = window.matchMedia.bind(window);
        window.__badgeAtFit = null;
        window.matchMedia = (q) => { if (window.__badgeAtFit === null)
            window.__badgeAtFit = document.getElementById('fcc-build-version').textContent; return real(q); }; })();""")
    page.add_script_tag(content=(MODULES / "titlebar_fit.js").read_text(encoding="utf-8"))
    shown = page.evaluate("() => window.__badgeAtFit")
    assert re.fullmatch(r"commit abcdef01 • \d{4}-\d{2}-\d{2} \d{2}:\d{2}", shown), shown
    assert page.locator("#fcc-build-version").get_attribute("title").endswith("UTC")


def test_below_992_px_the_script_takes_no_step(bar):
    """There the buttons have a line of their own and the CSS tightens them
    and reads ADD, as it always did."""
    bar.set_viewport_size({"width": 900, "height": 900})
    bar.evaluate("() => { document.querySelector('.fcc-titlebar').style.width = ''; }")
    _settle(bar)
    assert _state(bar)["steps"] == [] and not _state(bar)["wrap"]
    look = bar.evaluate("""() => ({ gap: getComputedStyle(document.querySelector('.fcc-titlebar-actions')).columnGap,
        more: getComputedStyle(document.querySelector('.fcc-titlebar-more')).display })""")
    assert look == {"gap": "8px", "more": "none"}, look
