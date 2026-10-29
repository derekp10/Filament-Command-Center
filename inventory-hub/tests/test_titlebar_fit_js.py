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
spacing, then the icon and number alone with Settings -> Title bar buttons on
Automatic, then ADD, then a second line), each only once the title would be cut
without it, and never later; the version badge never shrinks and never goes,
and the title is never left cut (Group 57.3: the badge went as the third step,
and the title was then cut); Always words and Always icons skip the icon step;
a count that grows takes a step and one that shrinks gives it back (the bar
watches its buttons' text); a Text size change, or a title-bar setting's, fits
again through its own event; buttons that still don't fit put the bar on two
lines (⚙️ stays on screen) and give it back; the memo is kept per width, Text
size and settings; the version badge reads in local time before the first fit;
below 992 px the script takes no step (the CSS does, as before). The bar on dev at every Text
size is test_text_size_setting_e2e.py's.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import BASELINE_VIEWPORT

HUB = Path(__file__).resolve().parent.parent
BASELINE_WIDTH = BASELINE_VIEWPORT["width"]
MODULES = HUB / "static" / "js" / "modules"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"
DASHBOARD = HUB / "templates" / "dashboard.html"
STEPS = ["fcc-tb-tight", "fcc-tb-icons", "fcc-tb-add", "fcc-tb-shortver"]   # Automatic (no setting stored)
ALL_JS = "['fcc-tb-tight', 'fcc-tb-icons', 'fcc-tb-add', 'fcc-tb-nover']"
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


# Every error the page reports, a ResizeObserver loop among them (it is an
# ErrorEvent on window, never an exception a test would see).
ERRORS_JS = "window.__errs = []; window.addEventListener('error', (e) => window.__errs.push(String(e.message)));"


@pytest.fixture
def bar(isolated_page):
    page = isolated_page
    _page(page)
    page.add_script_tag(content=ERRORS_JS)
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
        return { steps: ['fcc-tb-tight', 'fcc-tb-icons', 'fcc-tb-add', 'fcc-tb-shortver', 'fcc-tb-nover'].filter((c) => bar.classList.contains(c)),
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


def _over_without_last_step(page):
    """Takes the last step off for a moment: how far over is the title then?"""
    return page.evaluate("""(overJs) => {
        const bar = document.querySelector('.fcc-titlebar');
        const on = ['fcc-tb-tight', 'fcc-tb-icons', 'fcc-tb-add', 'fcc-tb-shortver'].filter((c) => bar.classList.contains(c));
        const last = on[on.length - 1];
        bar.classList.remove(last);
        const over = (0, eval)('(' + overJs + ')')();
        bar.classList.add(last);
        return over;
    }""", OVER_JS)


def _cut_without_last_step(page):
    """Takes the last step off for a moment: is the title then cut?"""
    return _over_without_last_step(page) > 0.01


# How far the version badge's right edge is from the first of the buttons (the
# Spoolman light), and the root size: on one line it keeps 1rem (its margin).
BADGE_ROOM_JS = """() => { const ver = document.getElementById('fcc-build-version');
    const first = document.querySelector('.fcc-titlebar-actions').firstElementChild;
    return { gap: first.getBoundingClientRect().left - ver.getBoundingClientRect().right,
             rem: parseFloat(getComputedStyle(document.documentElement).fontSize) }; }"""


def _badge_room(page):
    return page.evaluate(BADGE_ROOM_JS)


def _check(page, px):
    """One width: the badge whole (never squeezed, never gone, 57.3) and, on one
    line, never under the buttons, and 1rem clear of them while the title is
    cut (review of 57.3: with the title cut to nothing it was drawn under the
    Spoolman light, and with the title cut it touched it); a step only where
    the title would be cut without it; the title cut only once every step is
    taken."""
    s = _width(page, px)
    assert s["badge"] == "whole", (px, s)
    if not s["wrap"]:
        room = _badge_room(page)
        least = room["rem"] - 0.75 if s["cut"] else -0.5
        assert room["gap"] >= least, f"{px} px: the badge is {room['gap']:.2f} px from the buttons: {s}"
    if s["steps"] and not s["wrap"]:
        assert _cut_without_last_step(page), f"{px} px: {s['steps'][-1]} taken with room to spare"
    # Always words and Always icons take no icon step.
    auto = page.evaluate("() => (document.documentElement.getAttribute('data-fcc-tb-buttons') || 'auto') === 'auto'")
    order = STEPS if auto else [c for c in STEPS if c != "fcc-tb-icons"]
    if len(s["steps"]) < len(order) and not s["wrap"]:
        assert not s["cut"], f"{px} px: the title is cut with a step still to take: {s}"
    return s


def test_no_step_while_the_title_fits(bar):
    s = _width(bar, 1900)
    assert s == {"steps": [], "wrap": False, "cut": False, "badge": "whole"}, s


def test_each_step_comes_in_order_only_once_the_title_would_be_cut(bar):
    """From wide to narrow: none, then tight, then tight + icons, then + ADD,
    then + the badge's date alone, and only then the title is cut (the last
    resort; 57.3: the badge went first). Each step is taken only
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
    assert seen[:5] == [[], STEPS[:1], STEPS[:2], STEPS[:3], STEPS], seen
    for edge in edges[:4]:
        for px in range(edge + 12, edge - 3, -1):
            _check(bar, px)


def test_a_growing_count_takes_a_step_and_a_shrinking_one_gives_it_back(bar):
    """The bar watches its buttons' text: a Queue of 10 or a Backlog of 153
    takes a step where the old fixed widths cut the title (Group 57 review)."""
    for px in range(1900, 899, -5):
        if _width(bar, px)["steps"]:
            break
    _width(bar, px + 5)                                          # the narrowest bar that needs no step
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
    _width(bar, 1900)
    assert _state(bar)["steps"] == []
    bar.evaluate("""() => { document.documentElement.setAttribute('data-fcc-text-size', 'xlarge');
                             document.dispatchEvent(new CustomEvent('fcc:text-size')); }""")
    _settle(bar)
    s = _state(bar)
    assert s["steps"] and not (len(s["steps"]) < len(STEPS) and s["cut"]), s


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
    _width(bar, px + 5)                                          # the narrowest bar that needs no step
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
    bar.evaluate(BIG_COUNTS_XL)
    one_line = bar.evaluate("() => document.querySelector('nav.navbar').getBoundingClientRect().height")
    s = _width(bar, 900)
    # On two lines the badge is whole again (the short step comes off).
    assert s["wrap"] and s["steps"] == STEPS[:3], s
    look = bar.evaluate("""() => { const bar = document.querySelector('.fcc-titlebar');
        const r = bar.getBoundingClientRect(); const cs = getComputedStyle(bar);
        const edge = r.right - parseFloat(cs.paddingRight);
        return { gear: document.getElementById('btn-config').getBoundingClientRect().right <= edge + 0.5,
                 nav: document.querySelector('nav.navbar').getBoundingClientRect().height }; }""")
    assert look["gear"] and look["nav"] > one_line, look
    assert not s["cut"] and s["badge"] == "whole", s
    s = _width(bar, 1900)
    assert not s["wrap"], s


# A count as its painter writes it: the word and brackets spans of their own,
# which the icon step drops (inv_backlog.js, inv_queue.js; 57.3).
def _count_html(icon, word, n):
    return (f'{icon}<span class="fcc-tb-word"> {word}</span> <span class="fcc-count-num">'
            f'<span class="fcc-tb-paren">(</span>{n}<span class="fcc-tb-paren">)</span></span>')


# The ⚠️ button's numbers, both forms (inv_stock.js paints both), painted.
LOW_JS = """(low, out) => { const b = document.getElementById('btn-low-stock-count');
    const put = (sel, t) => { const el = b.querySelector(sel); el.removeAttribute('data-count-pending'); el.textContent = t; };
    put('[data-low-count]', String(low)); put('[data-out-count]', String(out));
    put('[data-low-stock-count]', String(low + out)); }"""


def _counts_js(backlog, queue, low, out):
    return ("""() => { document.getElementById('btn-backlog-count').innerHTML = %s;
    document.getElementById('btn-queue-count').innerHTML = %s;
    (%s)(%d, %d); }""" % (json.dumps(_count_html('🏷️', 'Backlog', backlog)), json.dumps(_count_html('🛒', 'Queue', queue)),
                         LOW_JS, low, out))


BIG_COUNTS_XL = ("""() => { document.documentElement.setAttribute('data-fcc-text-size', 'xlarge');
    document.dispatchEvent(new CustomEvent('fcc:text-size')); (%s)(); }""" % _counts_js(1530, 25, 20, 100))

GEAR_INSIDE_JS = """() => { const bar = document.querySelector('.fcc-titlebar');
    const r = bar.getBoundingClientRect(); const cs = getComputedStyle(bar);
    return document.getElementById('btn-config').getBoundingClientRect().right
        - (r.right - parseFloat(cs.paddingRight)); }"""


def _widest(page, has, lo, hi, fine=False):
    """The widest bar in [lo, hi] for which `has(state)`, with `lo` having it and
    `hi` not: to the pixel, or to 1/64 px (Chrome's layout unit) with `fine`."""
    assert has(_width(page, lo)) and not has(_width(page, hi)), (lo, hi)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if has(_width(page, mid)) else (lo, mid)
    if fine:
        for _ in range(6):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if has(_width(page, mid)) else (lo, mid)
    return lo


def test_the_bar_wraps_as_soon_as_a_button_would_leave_it(bar):
    """Around the wrap's onset, 1 px at a time: at every width the bar is on two
    lines or ⚙️ is inside it (round 3: a wrap that waited for 30 px of overflow
    passed every test, and on the real page ⚙️ was past the window's edge at 14
    widths). And no ResizeObserver loop on the way into the band or out of it:
    the observer watches a zero-high marker, since a fit on the bar itself
    changes its height when it wraps (round 3: on the bar, every crossing
    logged "ResizeObserver loop completed with undelivered notifications")."""
    bar.evaluate(BIG_COUNTS_XL)
    onset = _widest(bar, lambda s: s["wrap"], 900, 1900)
    for px in list(range(onset - 5, onset + 41)) + [1900, onset - 1, 1900, onset]:
        s = _width(bar, px)
        past = bar.evaluate(GEAR_INSIDE_JS)
        assert s["wrap"] or past <= 0.5, f"{px} px: one line, and ⚙️ {past:.2f} px past the bar's edge: {s}"
    assert bar.evaluate("() => window.__errs") == []


def test_a_step_comes_within_a_sliver_of_the_title_being_cut(bar):
    """Chrome draws the title's "…" from 2/64 px over, so a step that waits for
    more leaves "Filament Command Cent…" with the step still free (round 2). At
    the widest bar that takes the first step, found to 1/64 px, the title would
    be over by under 3/64 px without it. RED with the cut measured 0.1 px
    coarser, which the 1 px sweep let through (round 3)."""
    edge = _widest(bar, lambda s: bool(s["steps"]), 900, 1900, fine=True)
    s = _width(bar, edge)
    assert s["steps"] == STEPS[:1] and not s["cut"], s
    over = _over_without_last_step(bar)
    assert 0.01 < over < 3 / 64, f"at {edge} px the first step waits until the title is {over:.4f} px over"


# A localStorage the page can use: `set_content` leaves it on about:blank, where
# the real one is refused. `data` is what it holds, kept across "loads" here.
STORE_JS = """(data) => { window.__store = data;
    Object.defineProperty(window, 'localStorage', { configurable: true, get: () => ({
        getItem: (k) => (k in window.__store ? window.__store[k] : null),
        setItem: (k, v) => { window.__store[k] = String(v); },
        removeItem: (k) => { delete window.__store[k]; } }) }); }"""

# The counts land, as their painters write them (each drops data-count-pending).
COUNTS_LAND = _counts_js(1530, 25, 20, 100)

# Small counts: under 10 each, as narrow as a count gets (round 4).
COUNTS_SMALL = _counts_js(0, 0, 1, 2)

MEMO = "fcc.titleBar.fit"


def _flush(page):
    """The page goes (pagehide): the bar writes the memo it was holding back (it
    waits a second after a fit, so a resize drag writes one entry). set_content
    doesn't fire it, and keeps the last load's timers, so each load flushes the
    one before it first."""
    page.evaluate("() => window.dispatchEvent(new Event('pagehide'))")


def _memo(page):
    _flush(page)
    raw = page.evaluate("(k) => window.__store ? window.__store[k] : null", MEMO)
    return json.loads(raw) if raw else None


def _load(page, store, width, size=None, attrs=None):
    """A fresh load: the placeholders from dashboard.html, `store` as this
    browser's localStorage, the Text size `size` (else Standard), `attrs` on
    <html> (the title-bar settings, as dashboard.html's <head> puts them) and
    the bar `width` px wide (None: as wide as the window) before the script
    fits it."""
    _flush(page)
    page.set_content(PAGE.format(bootstrap=BOOTSTRAP_BITS, css=GLOBAL_CSS.read_text(encoding="utf-8"),
                                 nav=_nav_markup()))
    page.evaluate(STORE_JS, store)
    page.evaluate("""([w, size, attrs]) => { if (size) document.documentElement.setAttribute('data-fcc-text-size', size);
        Object.entries(attrs || {}).forEach(([k, v]) => document.documentElement.setAttribute(k, v));
        if (w === null) return;
        const b = document.querySelector('.fcc-titlebar'); b.style.flex = '0 0 auto'; b.style.width = w + 'px'; }""",
                  [width, size, attrs])
    page.add_script_tag(content=(MODULES / "titlebar_fit.js").read_text(encoding="utf-8"))
    _settle(page)
    return _state(page)


def _landed(page, counts=COUNTS_LAND):
    page.evaluate(counts)
    _settle(page)
    return _state(page)


def test_the_bar_keeps_last_times_steps_until_the_counts_come(isolated_page):
    """The first paint is fitted to the counts' placeholders ("(…)", "…"), and
    the first heartbeat's counts then took a step half a second into every load
    at some widths: ADD INVENTORY read ADD and every button moved (round 3). The
    bar remembers the steps it took with the counts in (this browser, with the
    window's width and the Text size), and while a count is still on its
    placeholder it takes at least those, so the counts landing move nothing.
    Another Text size or another window width uses no memo. RED on 2749590:
    nothing remembered."""
    page = isolated_page
    # Backlog, Queue, and the ⚠️ button's Low, Out and one-number counts (57.3).
    assert _nav_markup().count("data-count-pending>") == 5
    # A width where the placeholders need no step and the big counts do.
    _load(page, {}, 1900)
    page.evaluate(COUNTS_LAND)
    _settle(page)
    edge = _widest(page, lambda s: bool(s["steps"]), 900, 1900)
    s = _width(page, edge)
    assert s["steps"], s
    memo = _memo(page)
    assert memo == [{"w": page.evaluate("() => window.innerWidth"), "size": "standard", "mode": "auto|both",
                     "level": len(s["steps"])}], memo
    store = page.evaluate("() => window.__store")

    first = _load(page, {}, edge)                    # never here before: fitted to the placeholders
    assert first["steps"] == [], first
    first = _load(page, dict(store), edge)           # been here: last time's steps from the first paint
    assert first["steps"] == s["steps"], first
    page.evaluate(COUNTS_LAND)
    _settle(page)
    assert _state(page)["steps"] == s["steps"]

    assert _load(page, dict(store), edge, size="small")["steps"] == [], "a memo from Standard was used at Small"
    page.set_viewport_size({"width": BASELINE_WIDTH - 100, "height": 900})
    assert _load(page, dict(store), edge)["steps"] == [], "a memo from another window width was used"


def test_small_counts_never_move_the_bar_on_load(isolated_page):
    """Round 4: round 3's placeholders, "(…)" and "…", were about 3 px wider
    than a count under 10, and the memo only sets the steps to take at least:
    within about 9 px above each step, a load with small counts took a step in
    its first paint that the counts gave back half a second later, every time
    (the version badge gone, then back; SEARCH and every button after it
    moving). With en dashes the placeholders never need a step the counts
    don't. Around each step, 1 px at a time: a second load's first paint has
    the steps the counts took, and keeps them when they land. RED on dd81587."""
    page = isolated_page
    _load(page, {}, 1900)
    _landed(page, COUNTS_SMALL)
    # (On two lines the short-badge step comes off: past every step.)
    edges = [_widest(page, lambda s, k=k: len(s["steps"]) >= k or s["wrap"], 900, 1900) for k in (1, 2, 3, 4)]
    look = lambda s: (s["steps"], s["wrap"])
    for edge in edges:
        for px in range(edge - 4, edge + 10):
            _load(page, {}, px)
            landed = look(_landed(page, COUNTS_SMALL))
            store = {MEMO: json.dumps(_memo(page))}
            first = look(_load(page, store, px))
            again = look(_landed(page, COUNTS_SMALL))
            assert first == landed == again, f"{px} px: {first} on load, {again} once the counts came ({landed} with no memo)"


def test_each_window_width_keeps_its_own_steps(isolated_page):
    """Round 4: the memo held one window, so two FCC windows at different widths
    each wrote over the other's, and a reload moved again. It keeps an entry
    per width and Text size (the newest 8)."""
    page = isolated_page
    _load(page, {}, 1900)
    _landed(page)
    edge = _widest(page, lambda s: bool(s["steps"]), 900, 1900)
    want = _width(page, edge)["steps"]
    store = {MEMO: json.dumps(_memo(page))}
    page.set_viewport_size({"width": BASELINE_WIDTH - 100, "height": 900})      # the other window
    assert _load(page, store, edge)["steps"] == []                             # no entry for this width
    assert _landed(page)["steps"] == want
    both = _memo(page)
    assert [(m["w"], m["level"]) for m in both] == [(BASELINE_WIDTH - 100, len(want)), (BASELINE_WIDTH, len(want))], both
    page.set_viewport_size({"width": BASELINE_WIDTH, "height": 900})          # back in the first window
    first = _load(page, {MEMO: json.dumps(both)}, edge)
    assert first["steps"] == want, f"the first window's steps were lost: {first}"
    # The newest 8 are kept.
    many = [{"w": 1000 + i, "size": "standard", "mode": "auto|both", "level": 1} for i in range(8)]
    _load(page, {MEMO: json.dumps(many)}, edge)
    _landed(page)
    kept = _memo(page)
    assert len(kept) == 8 and kept[0]["w"] == BASELINE_WIDTH and kept[1:] == many[:7], kept
    # A memo from before 57.3 (no settings in it; its steps counted the badge's)
    # is no use: round 3's one window, and round 4's list.
    for old in ({"w": BASELINE_WIDTH, "size": "standard", "level": len(want)},
                [{"w": BASELINE_WIDTH, "size": "standard", "level": len(want)}]):
        assert _load(page, {MEMO: json.dumps(old)}, edge)["steps"] == [], old


def test_another_windows_entry_written_meanwhile_is_kept(isolated_page):
    """The memo is read again just before it is written: another FCC window of
    this browser may have written its own entry since this one loaded. Round 5:
    nothing pinned that; with the load-time memo in its place every test passed,
    and the other window's entry was dropped, so that window moved on its next
    load. Here this window fits, another writes its entry, this one fits again
    (a Text size change): both entries are kept."""
    page = isolated_page
    _load(page, {}, 1900)
    _landed(page)
    edge = _widest(page, lambda s: bool(s["steps"]), 900, 1900)
    want = _width(page, edge)["steps"]
    _flush(page)                                                  # this window's entry is written
    other = {"w": 1440, "size": "standard", "mode": "auto|both", "level": 2}
    page.evaluate("""([k, e]) => { const m = JSON.parse(window.__store[k] || '[]');
        window.__store[k] = JSON.stringify([e].concat(m)); }""", [MEMO, other])      # the other window's
    page.evaluate("() => document.dispatchEvent(new Event('fcc:text-size'))")       # this one fits again
    _settle(page)
    kept = _memo(page)
    assert sorted((m["w"], m["level"]) for m in kept) == sorted([(BASELINE_WIDTH, len(want)), (1440, 2)]), kept


HOLD_TIMERS_JS = """() => { window.__held = []; const real = window.setTimeout.bind(window);
    window.setTimeout = (fn, ms, ...a) => (ms === 1000 ? (window.__held.push(fn), 0) : real(fn, ms, ...a)); }"""


def test_a_window_resized_by_dragging_keeps_one_entry(isolated_page):
    """The memo waits a second after a fit (held back here, so the test isn't
    a race): a window dragged through ten widths writes one entry, for where it
    stopped, not one for each width it passed, which would have pushed the
    other windows' entries out. The page going writes it at once."""
    page = isolated_page
    page.set_viewport_size({"width": 1700, "height": 900})
    other = [{"w": 1440, "size": "standard", "mode": "auto|both", "level": 2}]
    _load(page, {MEMO: json.dumps(other)}, None)
    page.evaluate(HOLD_TIMERS_JS)
    _landed(page)
    for w in range(1700, 1599, -10):
        page.set_viewport_size({"width": w, "height": 900})
        _settle(page)
    assert page.evaluate("() => window.__held.length") >= 10
    assert page.evaluate("(k) => window.__store[k]", MEMO) == json.dumps(other)      # nothing written yet
    kept = _memo(page)
    assert [m["w"] for m in kept] == [1600, 1440], kept


def test_a_remembered_second_line_comes_from_the_first_paint(isolated_page):
    """Extra Large in a narrow window with big counts takes the second line
    (round 2). Remembered, the next load is on two lines from its first paint,
    though the placeholders alone would fit on one (round 4: unpinned; without
    the memo's wrap it went one line, then two half a second later, the navbar
    growing under the page)."""
    page = isolated_page
    _load(page, {}, 1900, size="xlarge")
    _landed(page)
    onset = _widest(page, lambda s: s["wrap"], 900, 1900)
    assert _width(page, onset)["wrap"]
    store = {MEMO: json.dumps(_memo(page))}
    assert not _load(page, {}, onset, size="xlarge")["wrap"], "the placeholders alone should fit on one line"
    first = _load(page, store, onset, size="xlarge")
    assert first["wrap"], f"one line on load, two once the counts came: {first}"
    assert _landed(page)["wrap"]


def test_counts_that_shrink_give_their_steps_back(isolated_page):
    """The memo holds only while a count is pending: once the counts have come,
    a count that shrinks gives a step back, and the lower steps are what's
    remembered (round 4: unpinned; held for good, a step the counts no longer
    need stayed for the whole session, and was remembered)."""
    page = isolated_page
    _load(page, {}, 1900)
    _landed(page)
    edge = _widest(page, lambda s: bool(s["steps"]), 900, 1900)
    want = _width(page, edge)["steps"]
    store = {MEMO: json.dumps(_memo(page))}
    assert _load(page, store, edge)["steps"] == want
    assert _landed(page)["steps"] == want
    small = _landed(page, COUNTS_SMALL)["steps"]
    assert len(small) < len(want), (small, want)
    assert _memo(page)[0]["level"] == len(small)


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


@pytest.mark.parametrize("case", ("Extra Large", "Always words"))
def test_the_badge_never_runs_under_the_buttons(bar, case):
    """The title's group may shrink to a stub and the badge never shrinks, so
    with the title cut to nothing the badge spilled out of its group and was
    drawn under the Spoolman light and SEARCH, while the buttons still fitted
    the bar and it stayed on one line (review of 57.3: Extra Large in a window
    of 992-1112 px with the defaults; Always words at every size). Swept from
    a whole title to the second line: on one line the badge is never under the
    buttons, and keeps 1rem from the light while the title is cut; where it
    can't, the bar takes its second line, the title whole with the whole badge
    beside it. RED on 41b819d: 0 px from the light once the title was cut,
    then up to 125 px under the buttons. The gap comes only with a cut title,
    so no step comes sooner (a margin at every width took ADD's step at Large
    on a 1600 px window: test_text_size_setting_e2e.py)."""
    if case == "Extra Large":
        bar.evaluate("""() => { document.documentElement.setAttribute('data-fcc-text-size', 'xlarge');
            document.dispatchEvent(new CustomEvent('fcc:text-size')); }""")
    else:
        _set(bar, buttons="words")
    bar.evaluate(COUNTS_LAND)
    _settle(bar)
    seen = set()
    for px in range(1500, 899, -3):
        s = _check(bar, px)
        if s["wrap"]:
            assert not s["cut"] and s["badge"] == "whole", (px, s)
            seen.add("wrap")
        elif s["cut"]:
            seen.add("cut")
    assert seen == {"cut", "wrap"}, f"the sweep should cross a cut title and the second line: {seen}"
    assert bar.evaluate("() => window.__errs") == []


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
        more: getComputedStyle(document.querySelector('.fcc-titlebar-more')).display,
        word: getComputedStyle(document.querySelector('#btn-backlog-count .fcc-tb-word')).display })""")
    assert look == {"gap": "8px", "more": "none", "word": "none"}, look
    # Always words keeps the words there too (review of 57.3: unpinned).
    bar.evaluate("() => document.documentElement.setAttribute('data-fcc-tb-buttons', 'words')")
    assert _word_shown(bar) != "none"


# --- Group 57.3: the settings ----------------------------------------------------------

def _set(page, buttons=None, count=None):
    """A title-bar setting changed (titlebar_prefs.js puts it on <html> and
    says so with fcc:title-bar)."""
    page.evaluate("""([b, c]) => { const r = document.documentElement;
        if (b) r.setAttribute('data-fcc-tb-buttons', b); if (c) r.setAttribute('data-fcc-low-count', c);
        document.dispatchEvent(new CustomEvent('fcc:title-bar')); }""", [buttons, count])
    _settle(page)


def _word_shown(page):
    return page.evaluate("() => getComputedStyle(document.querySelector('#btn-backlog-count .fcc-tb-word')).display")


def test_always_words_never_takes_the_icon_step(bar):
    """Always words: the words stay; the bar takes the spacing, ADD, then the
    second line, the badge whole and the title never cut on the way."""
    bar.evaluate(COUNTS_LAND)
    _set(bar, buttons="words")
    seen = []
    for px in range(1900, 899, -10):
        s = _width(bar, px)
        assert s["badge"] == "whole", (px, s)
        assert "fcc-tb-icons" not in s["steps"] and _word_shown(bar) != "none", (px, s)
        look = (tuple(s["steps"]), s["wrap"])
        if not seen or seen[-1] != look:
            seen.append(look)
    assert seen[:4] == [((), False), (("fcc-tb-tight",), False), (("fcc-tb-tight", "fcc-tb-add"), False),
                        (("fcc-tb-tight", "fcc-tb-add", "fcc-tb-shortver"), False)], seen


def test_always_icons_shows_the_icon_and_number_with_room_to_spare(bar):
    bar.evaluate(COUNTS_LAND)
    _set(bar, buttons="icons")
    s = _width(bar, 1900)
    assert s["steps"] == [] and _word_shown(bar) == "none", s


def test_automatic_drops_the_words_as_its_second_step(bar):
    """The icon step comes after the spacing and before ADD: at the widest bar
    that takes it, the words are gone and ADD INVENTORY is whole."""
    bar.evaluate(COUNTS_LAND)
    edge = _widest(bar, lambda s: "fcc-tb-icons" in s["steps"], 900, 1900)
    s = _width(bar, edge)
    assert s["steps"] == STEPS[:2] and not s["cut"], s
    assert _word_shown(bar) == "none"
    assert bar.evaluate("() => getComputedStyle(document.querySelector('.fcc-titlebar-more')).display") != "none"
    assert _width(bar, edge + 1)["steps"] == STEPS[:1] and _word_shown(bar) != "none"


def test_a_settings_change_fits_the_bar_again(bar):
    """Words are wider than icons: switching Always icons to Always words at
    the narrowest bar with no step fits again, through fcc:title-bar (an
    attribute on <html> is no text change in the buttons the MutationObserver
    sees). RED with the listener removed."""
    bar.evaluate(COUNTS_LAND)
    _set(bar, buttons="icons")
    for px in range(1900, 899, -5):
        if _width(bar, px)["steps"]:
            break
    _width(bar, px + 5)                                          # the narrowest bar that needs no step, with icons
    assert _state(bar)["steps"] == []
    bar.evaluate("() => document.documentElement.setAttribute('data-fcc-tb-buttons', 'words')")
    _settle(bar)
    assert _state(bar)["steps"] == [] and _state(bar)["cut"], "it should wait for the event"
    bar.evaluate("() => document.dispatchEvent(new CustomEvent('fcc:title-bar'))")
    _settle(bar)
    s = _state(bar)
    assert s["steps"] and not s["cut"], s


def test_each_setting_keeps_its_own_memo(isolated_page):
    """The labels change the bar's width, so a memo taken with one setting
    isn't used with another (57.3)."""
    page = isolated_page
    _load(page, {}, 1900)
    _landed(page)
    edge = _widest(page, lambda s: bool(s["steps"]), 900, 1900)
    want = _width(page, edge)["steps"]
    store = {MEMO: json.dumps(_memo(page))}
    assert _load(page, store, edge)["steps"] == want
    assert _load(page, store, edge, attrs={"data-fcc-tb-buttons": "words"})["steps"] == []


def _badge_text(page):
    return page.evaluate("() => document.getElementById('fcc-build-version').innerText.trim()")


def test_the_badge_shows_its_date_alone_before_the_title_is_cut(bar):
    """Group 57.3: the badge never goes (Derek reads the build's date at a
    glance): as the last step before the title is cut it shows its date and
    time alone, the commit in its tooltip (and Settings -> Build Info). On two
    lines (buttons that don't fit, below) it is whole again, beside the title."""
    bar.evaluate(COUNTS_LAND)
    edge = _widest(bar, lambda s: "fcc-tb-shortver" in s["steps"] or s["wrap"], 900, 1900)
    s = _width(bar, edge)
    assert s["steps"] == STEPS and not s["wrap"] and not s["cut"] and s["badge"] == "whole", s
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", _badge_text(bar)), _badge_text(bar)
    assert bar.locator("#fcc-build-version").get_attribute("title").endswith("UTC")
    s = _width(bar, edge + 1)
    assert "fcc-tb-shortver" not in s["steps"] and _badge_text(bar).startswith("commit abcdef01 • "), s
    bar.evaluate(BIG_COUNTS_XL)
    assert _width(bar, 900)["wrap"] and _badge_text(bar).startswith("commit abcdef01 • ")
