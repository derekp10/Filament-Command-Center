"""The title bar's two per-browser settings (Group 57.3; Derek, 2026-10-28),
hermetic.

Settings -> This Browser -> "Title bar buttons" (Automatic, the default /
Always words / Always icons) and "Low stock count" (Low and Out, the default /
One number). Runs the REAL #fcc-title-bar-boot script lifted from
dashboard.html, the REAL titlebar_prefs.js, and the REAL inv_stock.js on the
REAL ⚠️ button markup (test_low_stock_glance_57_js.py's page), with the real
global.css.

Pinned: the fields exist as browser settings with their defaults; the <head>
script puts both settings on <html> before anything draws (an unknown value,
none, or storage FCC can't read gives the defaults); a pick in Settings applies
at once, is stored, and says so to the title bar (`fcc:title-bar`), while a
scan typed on the select picks nothing; out of the box the ⚠️ button shows Low
and Out apart in the Low stock window's words and count pills, with dashes
until the first count, a stale "?" after the Out number, and words that hold
what it shows; One number shows the two added up, and switching repaints the
words but never paints over the placeholders before a count.
"""
from __future__ import annotations

import json
import re

import pytest

import config_schema
from test_low_stock_glance_57_js import (BOOTSTRAP_HIDDEN, BTN, DASHBOARD, DOWN, GLOBAL_CSS, GOOD, MODULES, PAGE,
                                         PRELUDE, _button_markup, _render)


def _boot_script():
    html = DASHBOARD.read_text(encoding="utf-8")
    m = re.search(r'<script id="fcc-title-bar-boot">(.*?)</script>', html, re.S)
    assert m, "dashboard.html has no #fcc-title-bar-boot"
    return m.group(1)


def test_the_two_fields_are_browser_settings_with_their_defaults():
    buttons = config_schema.get_field("fcc.titleBar.buttons")
    count = config_schema.get_field("fcc.lowStock.count")
    assert (buttons.section, buttons.scope, buttons.type, buttons.default, buttons.choices) == (
        "client", "client", "select", "Automatic", ["Automatic", "Always words", "Always icons"])
    assert (count.section, count.scope, count.type, count.default, count.choices) == (
        "client", "client", "select", "Low and Out", ["Low and Out", "One number"])


# A localStorage the page can use (set_content leaves it on about:blank, where
# the real one is refused): `data`, or one that throws.
STORE_JS = """(data) => { Object.defineProperty(window, 'localStorage', { configurable: true, get: () => {
    if (data === null) throw new Error('blocked');
    return { getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); },
             removeItem: (k) => { delete data[k]; } }; } }); window.__store = data; }"""


@pytest.mark.parametrize("stored, want", [
    ({}, ["auto", "both"]),
    ({"fcc.titleBar.buttons": "Always words", "fcc.lowStock.count": "One number"}, ["words", "one"]),
    ({"fcc.titleBar.buttons": "Always icons"}, ["icons", "both"]),
    ({"fcc.titleBar.buttons": "always icons", "fcc.lowStock.count": "Both"}, ["auto", "both"]),
    (None, ["auto", "both"]),
])
def test_the_head_script_puts_both_settings_on_the_page_before_it_draws(isolated_page, stored, want):
    page = isolated_page
    page.set_content("<!doctype html><html><head></head><body></body></html>")
    page.evaluate(STORE_JS, stored)
    page.add_script_tag(content=_boot_script())
    got = page.evaluate("""() => [document.documentElement.getAttribute('data-fcc-tb-buttons'),
                                  document.documentElement.getAttribute('data-fcc-low-count')]""")
    assert got == want, (stored, got)


SELECTS = """<!doctype html><html><head></head><body>
<select class="cfgset-input" data-key="fcc.titleBar.buttons" data-initial="Automatic">
  <option>Automatic</option><option>Always words</option><option>Always icons</option></select>
<select class="cfgset-input" data-key="fcc.lowStock.count" data-initial="Low and Out">
  <option>Low and Out</option><option>One number</option></select>
</body></html>"""


@pytest.fixture
def prefs(isolated_page):
    page = isolated_page
    page.set_content(SELECTS)
    page.evaluate(STORE_JS, {})
    page.evaluate("""() => { window.__events = []; window.__toasts = [];
        window.showToast = (m, t, ms) => window.__toasts.push({m, t, ms});
        document.addEventListener('fcc:title-bar', (e) => window.__events.push(e.detail)); }""")
    page.add_script_tag(content=_boot_script())
    page.add_script_tag(content=(MODULES / "titlebar_prefs.js").read_text(encoding="utf-8"))
    return page


def _pick(page, key, value):
    page.evaluate("""([k, v]) => { const s = document.querySelector(`[data-key="${k}"]`); s.value = v;
        s.dispatchEvent(new Event('change', { bubbles: true })); }""", [key, value])


def test_a_pick_applies_at_once_is_stored_and_tells_the_title_bar(prefs):
    _pick(prefs, "fcc.titleBar.buttons", "Always icons")
    _pick(prefs, "fcc.lowStock.count", "One number")
    seen = prefs.evaluate("""() => ({ attrs: [document.documentElement.getAttribute('data-fcc-tb-buttons'),
                                               document.documentElement.getAttribute('data-fcc-low-count')],
        store: window.__store, events: window.__events,
        initial: Array.from(document.querySelectorAll('select')).map((s) => s.dataset.initial) })""")
    assert seen["attrs"] == ["icons", "one"]
    assert seen["store"] == {"fcc.titleBar.buttons": "Always icons", "fcc.lowStock.count": "One number"}
    assert [(e["pref"], e["value"]) for e in seen["events"]] == [("buttons", "icons"), ("count", "one")]
    assert seen["initial"] == ["Always icons", "One number"], "stored already: Save has nothing left to do"


def test_a_scan_typed_on_the_select_picks_nothing(prefs):
    """A scanner types into whatever has the focus, and a select takes each
    character as type-ahead ("A" would pick Always words): text_size.js's
    rule. The keys are not stopped, so the scan accumulator still reads them."""
    prefs.focus('[data-key="fcc.titleBar.buttons"]')
    prevented = prefs.evaluate("""() => ['A', 'l', ':', '5'].map((k) => {
        const e = new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true });
        document.activeElement.dispatchEvent(e); return e.defaultPrevented; })""")
    assert prevented == [True, True, True, True]
    down = prefs.evaluate("""() => { const e = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true,
        cancelable: true }); document.activeElement.dispatchEvent(e); return e.defaultPrevented; }""")
    assert down is False, "the arrow keys still pick"


def test_a_choice_the_select_doesnt_offer_changes_nothing(prefs):
    prefs.evaluate("""() => { const s = document.querySelector('[data-key="fcc.lowStock.count"]');
        const o = document.createElement('option'); o.textContent = 'Both'; s.appendChild(o); }""")
    _pick(prefs, "fcc.lowStock.count", "Both")
    assert prefs.evaluate("() => document.documentElement.getAttribute('data-fcc-low-count')") == "both"
    assert prefs.evaluate("() => window.__store") == {} and prefs.evaluate("() => window.__events") == []


def test_storage_that_refuses_still_shows_the_pick_and_says_it_wont_last(prefs):
    prefs.evaluate("""() => { Object.defineProperty(window, 'localStorage', { configurable: true,
        get: () => ({ getItem: () => null, setItem: () => { throw new Error('full'); } }) }); }""")
    _pick(prefs, "fcc.lowStock.count", "One number")
    assert prefs.evaluate("() => document.documentElement.getAttribute('data-fcc-low-count')") == "one"
    toasts = prefs.evaluate("() => window.__toasts")
    assert len(toasts) == 1 and toasts[0]["t"] == "warning" and toasts[0]["ms"] == 7000, toasts
    assert "Low stock count changed, but this browser could not keep it" in toasts[0]["m"], toasts


# --- the ⚠️ button out of the box: Low and Out apart --------------------------------

@pytest.fixture
def bar(isolated_page):
    """test_low_stock_glance_57_js.py's page with no setting stored: the
    defaults, Automatic and Low and Out."""
    page = isolated_page
    page.set_content(PAGE.format(css=GLOBAL_CSS.read_text(encoding="utf-8") + BOOTSTRAP_HIDDEN,
                                 button=_button_markup()))
    page.evaluate(STORE_JS, {})
    page.add_script_tag(content=_boot_script())
    page.add_script_tag(content=PRELUDE)
    for name in ("overlay_mount.js", "inv_core.js", "inv_stock.js", "titlebar_prefs.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("() => { window.__toasts = []; window.showToast = (m, t, ms) => window.__toasts.push({m, t, ms}); }")
    return page


def _shown(page):
    return page.evaluate("""(sel) => { const b = document.querySelector(sel);
        const vis = (el) => !!el && el.getClientRects().length > 0;
        const both = b.querySelector('.fcc-ls-both'), one = b.querySelector('.fcc-ls-one');
        const mark = (form) => !!form.querySelector('.fcc-tb-count > .fcc-stale-mark');
        return { form: vis(both) ? 'both' : (vis(one) ? 'one' : null),
                 low: b.querySelector('[data-low-count]').textContent,
                 out: b.querySelector('[data-out-count]').textContent,
                 total: b.querySelector('[data-low-stock-count]').textContent,
                 text: b.innerText.replace(/\\s+/g, ' ').trim().replace(/ \\?$/, Array.from(b.querySelectorAll('.fcc-stale-mark')).some((m) => m.getClientRects().length) ? '?' : ' ?'),
                 markBoth: mark(both), markOne: mark(one),
                 pending: b.querySelectorAll('[data-count-pending]').length,
                 label: b.getAttribute('aria-label'), title: b.title }; }""", BTN)


def test_out_of_the_box_it_reads_low_and_out_with_dashes_until_the_first_count(bar):
    s = _shown(bar)
    assert (s["form"], s["low"], s["out"], s["pending"]) == ("both", "–", "–", 3), s
    assert s["text"] == "⚠️ Low–Out–", s
    assert s["label"] == "Low stock: opens the list." == s["title"]


def test_the_count_paints_low_and_out_apart_with_words_that_hold_them(bar):
    assert _render(bar, GOOD) is True
    s = _shown(bar)
    assert (s["form"], s["low"], s["out"], s["total"], s["pending"]) == ("both", "1", "11", "12", 0), s
    assert s["label"] == "Low 1, Out 11 (1 low under 250 g, 11 out). Opens the list." == s["title"], s


def test_a_stale_count_puts_its_question_mark_after_the_out_number(bar):
    """The "?" after the shown form's last number, drawn in the button's padding
    (it takes no room, Group 57 review round 2), and the dashed border."""
    _render(bar, GOOD)
    fresh = bar.evaluate("(s) => document.querySelector(s).getBoundingClientRect().width", BTN)
    assert _render(bar, DOWN) is False
    s = _shown(bar)
    assert (s["markBoth"], s["text"]) == (True, "⚠️ Low1Out11?"), s
    assert s["label"] == ("Low 1, Out 11?, the last count (Spoolman didn't answer just now): "
                          "1 low under 250 g, 11 out. Opens the list."), s
    geo = bar.evaluate("""(sel) => { const b = document.querySelector(sel);
        const pill = b.querySelector('[data-out-count]').getBoundingClientRect();
        const m = b.querySelector('.fcc-ls-both .fcc-stale-mark').getBoundingClientRect();
        return { gap: m.left - pill.right, inside: m.right <= b.getBoundingClientRect().right,
                 width: b.getBoundingClientRect().width,
                 border: getComputedStyle(b).borderTopStyle }; }""", BTN)
    assert abs(geo["gap"]) < 0.5 and geo["inside"] and geo["border"] == "dashed", geo
    assert abs(geo["width"] - fresh) < 0.01, (geo, fresh)
    _render(bar, GOOD)
    s = _shown(bar)
    assert not s["markBoth"] and not s["markOne"], s


def test_one_number_shows_the_two_added_up_and_switching_repaints_the_words(bar):
    _render(bar, GOOD)
    bar.evaluate("() => window.fccTitleBarPrefs.set('count', 'One number')")
    s = _shown(bar)
    assert (s["form"], s["total"]) == ("one", "12"), s
    assert s["text"] == "⚠️ Low stock (12)", s
    assert s["label"] == "Low stock: 12 (1 low under 250 g, 11 out). Opens the list.", s
    bar.evaluate("() => window.fccTitleBarPrefs.set('count', 'Low and Out')")
    assert _shown(bar)["label"] == "Low 1, Out 11 (1 low under 250 g, 11 out). Opens the list."


def test_a_switch_before_the_first_count_leaves_the_placeholders(bar):
    """Repainting the words on a switch must not paint a "?" over the dashes
    before any count came (a stale-looking button on every load)."""
    bar.evaluate("() => window.fccTitleBarPrefs.set('count', 'One number')")
    s = _shown(bar)
    assert (s["form"], s["total"], s["pending"]) == ("one", "–", 3), s
    assert s["label"] == "Low stock: opens the list.", s


def test_always_icons_drops_the_words_and_brackets_but_never_low_and_out(bar):
    """Icons: "⚠️ 12" for one number; Low and Out keep their words, which are
    how the two numbers are told apart."""
    _render(bar, GOOD)
    bar.evaluate("() => window.fccTitleBarPrefs.set('buttons', 'Always icons')")
    assert _shown(bar)["text"] == "⚠️ Low1Out11"
    bar.evaluate("() => window.fccTitleBarPrefs.set('count', 'One number')")
    assert _shown(bar)["text"] == "⚠️ 12"
    bar.evaluate("() => window.fccTitleBarPrefs.set('buttons', 'Always words')")
    assert _shown(bar)["text"] == "⚠️ Low stock (12)"
