"""The per-browser Text size on the real page (Derek, 2026-10-21).

Settings -> 🖥️ This Browser -> "Text size": Small (the compact look FCC had
before the readability rule), Standard (the rule; the default), Large and
Extra Large (the root grows, so everything grows together and keeps its
proportions). Kept per browser in localStorage 'fcc.textSize'.

  - the stored size is on <html> before <body> exists, so nothing paints at
    the wrong size and then jumps;
  - each size's root and named sizes, and Bootstrap's badge and small text;
  - the Settings control: by mouse and by keyboard it changes the page at
    once and keeps the size with no Save, and a reload keeps it (its contrast
    is test_contrast_guard.py::test_settings_this_browser_section_is_readable);
  - the title bar keeps every button on one line at every size (it tightens,
    then ADD INVENTORY reads ADD), and is unchanged at Small and Standard;
  - at Extra Large the slot picker fits the window, scrolls inside its cap
    and keeps every tile's content inside the tile.
The hermetic proof of the <head> script and text_size.js is
test_text_size_setting_js.py; the floor at Standard is test_text_size_guard.py.

READ-ONLY, like test_text_size_guard.py: every request that isn't a read is
answered inside the browser and never reaches the server. The size is this
test browser's own localStorage (a fresh context per test); Save is never
clicked.

HEAD proof (feat/readability-2026-10-21 cab9127, before the setting: the
product edits stashed for one run against the live container, restored
after): 12 of 13 RED. No size was applied (no attribute, the root stayed
16 px at every stored size), Settings had no Text size control, and the title
bar had no tightening steps. The slot-picker check passed there only because
nothing was bigger; it now first checks that Extra Large is on, which HEAD
fails. With the size applied but the title bar not yet fixed, its buttons
wrapped at Extra Large (SEARCH / ADD INVENTORY onto 2 lines, Backlog / Queue
onto 3, sticking out of the 70 px bar), and the slot picker's ⭐ Recommended
stuck out of its 205 px tile (the walkthrough's pictures 2 and 6).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from test_text_size_guard import _read_only, dev_ids, _open_picker, _close_picker  # noqa: F401  (dev_ids: fixture)

pytestmark = pytest.mark.usefixtures("require_server")

KEY = "fcc.textSize"
SELECT = '.cfgset-input[data-key="fcc.textSize"]'
SIZES = ("Small", "Standard", "Large", "Extra Large")
SLUG = {"Small": "small", "Standard": "standard", "Large": "large", "Extra Large": "xlarge"}

# What each size comes to in px (browser default 16 px): the root, the three
# names, a badge, a badge and small text inside small text, a badge in an h5.
EXPECTED = {
    "Small":       {"root": 16, "label": 12.0, "small": 12.8, "row": 13.6, "badge": 12.0, "badge_in_small": 12.0,
                    "small_in_small": 12.8, "badge_in_h5": 15.0},
    "Standard":    {"root": 16, "label": 12.8, "small": 13.6, "row": 14.4, "badge": 12.8, "badge_in_small": 12.8,
                    "small_in_small": 13.6, "badge_in_h5": 15.0},
    "Large":       {"root": 18, "label": 14.4, "small": 15.3, "row": 16.2, "badge": 14.4, "badge_in_small": 14.4,
                    "small_in_small": 15.3, "badge_in_h5": 16.875},
    "Extra Large": {"root": 20, "label": 16.0, "small": 17.0, "row": 18.0, "badge": 16.0, "badge_in_small": 16.0,
                    "small_in_small": 17.0, "badge_in_h5": 18.75},
}

SIZES_JS = """() => {
    const host = document.createElement('div');
    host.innerHTML = '<span id="t-l" style="font-size:var(--fcc-fs-label)">a</span>'
        + '<span id="t-s" style="font-size:var(--fcc-fs-small)">a</span>'
        + '<span id="t-r" style="font-size:var(--fcc-fs-row)">a</span>'
        + '<span class="badge" id="t-b">a</span>'
        + '<span class="small"><span class="badge" id="t-bs">a</span><span class="small" id="t-ss">a</span></span>'
        + '<h5><span class="badge" id="t-bh">a</span></h5>';
    document.body.appendChild(host);
    const px = (id) => parseFloat(getComputedStyle(document.getElementById(id)).fontSize);
    const out = { root: parseFloat(getComputedStyle(document.documentElement).fontSize),
                  label: px('t-l'), small: px('t-s'), row: px('t-r'), badge: px('t-b'),
                  badge_in_small: px('t-bs'), small_in_small: px('t-ss'), badge_in_h5: px('t-bh') };
    host.remove();
    return out; }"""


def _store(page: Page, name):
    """This browser's stored size, before the page's own scripts run."""
    page.add_init_script("(() => { try { localStorage.setItem(%r, %r); } catch (e) {} })();" % (KEY, name))


def _load(page: Page, base_url: str):
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof state !== 'undefined' && state.locationsLoaded"
                           " && typeof window.openConfigModal === 'function'", timeout=45_000)
    page.wait_for_timeout(800)


def _attr(page: Page):
    return page.evaluate("() => document.documentElement.getAttribute('data-fcc-text-size')")


# ---------------------------------------------------------------------------
# Applied before the first paint
# ---------------------------------------------------------------------------

def test_the_stored_size_is_on_html_before_the_body_exists(page: Page, base_url: str):
    """Nothing can paint before <body> is in the document; the size is already
    on <html> by then (recorded by a MutationObserver from before any page
    script), so the page never draws at Standard and then jumps."""
    _read_only(page)
    _store(page, "Extra Large")
    page.add_init_script("""(() => {
        window.__tsAtBody = 'no body seen';
        const mo = new MutationObserver(() => {
            if (document.body) {
                window.__tsAtBody = document.documentElement.getAttribute('data-fcc-text-size');
                window.__tsRootAtBody = getComputedStyle(document.documentElement).fontSize;
                mo.disconnect();
            }
        });
        mo.observe(document, { childList: true, subtree: true });
    })();""")
    _load(page, base_url)
    assert page.evaluate("() => window.__tsAtBody") == "xlarge"
    assert page.evaluate("() => window.__tsRootAtBody") == "20px"
    assert _attr(page) == "xlarge"


def test_no_stored_size_is_standard(page: Page, base_url: str):
    _read_only(page)
    _load(page, base_url)
    assert _attr(page) == "standard"
    assert page.evaluate(SIZES_JS) == EXPECTED["Standard"]


# ---------------------------------------------------------------------------
# Each size's values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", SIZES)
def test_each_size_sets_the_root_and_the_named_sizes(page: Page, base_url: str, name):
    _read_only(page)
    _store(page, name)
    _load(page, base_url)
    assert _attr(page) == SLUG[name]
    got = page.evaluate(SIZES_JS)
    want = EXPECTED[name]
    assert {k: round(v, 3) for k, v in got.items()} == pytest.approx(want, abs=0.01), (name, got)


# ---------------------------------------------------------------------------
# The Settings control
# ---------------------------------------------------------------------------

def _open_settings(page: Page):
    page.evaluate("() => window.openConfigModal()")
    page.wait_for_function("() => { const m = document.getElementById('configModal');"
                           " return m && m.classList.contains('show'); }", timeout=10_000)
    page.wait_for_selector(SELECT, state="visible", timeout=15_000)
    page.wait_for_timeout(400)


def _state(page: Page):
    return page.evaluate("""(k) => ({ attr: document.documentElement.getAttribute('data-fcc-text-size'),
        stored: localStorage.getItem(k),
        root: parseFloat(getComputedStyle(document.documentElement).fontSize) })""", KEY)


def test_the_settings_control_works_by_mouse_and_keyboard(page: Page, base_url: str):
    _read_only(page)
    puts = []
    page.on("request", lambda r: puts.append(r.url) if r.method != "GET" and "/api/config" in r.url else None)
    _load(page, base_url)
    _open_settings(page)
    sel = page.locator(SELECT)
    assert sel.evaluate("(el) => Array.from(el.options).map((o) => o.value)") == list(SIZES)
    assert sel.input_value() == "Standard"
    label = page.locator("label[for='%s']" % sel.get_attribute("id"))
    assert label.inner_text().startswith("Text size")
    # It sits in the This Browser section (its contrast:
    # test_contrast_guard.py::test_settings_this_browser_section_is_readable).
    section = page.locator("#config-generated-settings > div.mb-3", has=sel)
    assert "This Browser" in section.inner_text()

    # Mouse: pick Large from the list. The page changes at once, no Save.
    sel.select_option("Large")
    page.wait_for_function("() => document.documentElement.getAttribute('data-fcc-text-size') === 'large'",
                           timeout=3000)
    assert _state(page) == {"attr": "large", "stored": "Large", "root": 18}

    # Keyboard: focus the select, one step down is Extra Large.
    sel.focus()
    page.keyboard.press("ArrowDown")
    page.wait_for_function("() => document.documentElement.getAttribute('data-fcc-text-size') === 'xlarge'",
                           timeout=3000)
    assert _state(page) == {"attr": "xlarge", "stored": "Extra Large", "root": 20}
    page.keyboard.press("Home")
    page.wait_for_function("() => document.documentElement.getAttribute('data-fcc-text-size') === 'small'",
                           timeout=3000)
    assert _state(page) == {"attr": "small", "stored": "Small", "root": 16}
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.wait_for_function("() => document.documentElement.getAttribute('data-fcc-text-size') === 'large'",
                           timeout=3000)
    # Its data-initial follows, so Save settings would have nothing left to do for it.
    assert sel.get_attribute("data-initial") == "Large"
    assert puts == [], f"picking a text size must not save anything on the server: {puts}"

    # A reload keeps it, and the reopened Settings shows it.
    page.keyboard.press("Escape")
    _load(page, base_url)
    assert _state(page) == {"attr": "large", "stored": "Large", "root": 18}
    _open_settings(page)
    assert page.locator(SELECT).input_value() == "Large"


# ---------------------------------------------------------------------------
# The title bar never wraps
# ---------------------------------------------------------------------------

NAV_JS = """() => {
    const nav = document.querySelector('nav.navbar');
    const nr = nav.getBoundingClientRect();
    const lines = (el) => {
        const r = document.createRange(); r.selectNodeContents(el);
        return new Set(Array.from(r.getClientRects()).filter((x) => x.width > 0.5)
            .map((x) => Math.round(x.top + x.height / 2))).size;
    };
    const btns = Array.from(nav.querySelectorAll('.btn')).map((b) => {
        const r = b.getBoundingClientRect();
        return { text: b.innerText.replace(/\\s+/g, ' ').trim(), lines: lines(b),
                 inside: r.top >= nr.top - 1 && r.bottom <= nr.bottom + 1 && r.left >= nr.left - 1 && r.right <= nr.right + 1 };
    });
    const actions = nav.querySelector('.fcc-titlebar-actions');
    const search = Array.from(nav.querySelectorAll('.btn')).find((b) => /SEARCH/.test(b.innerText));
    return { btns, navH: Math.round(nr.height),
             overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
             gap: getComputedStyle(actions).columnGap, searchMargin: getComputedStyle(search).marginLeft };
}"""


@pytest.mark.parametrize("name", SIZES)
def test_the_title_bar_keeps_its_buttons_on_one_line(page: Page, base_url: str, name):
    _read_only(page)
    _store(page, name)
    _load(page, base_url)
    nav = page.evaluate(NAV_JS)
    wrapped = [b for b in nav["btns"] if b["lines"] != 1 or not b["inside"]]
    assert not wrapped, f"{name}: title-bar buttons that wrap or stick out of the bar: {wrapped}"
    assert nav["navH"] == 70 and not nav["overflow"], nav
    texts = [b["text"] for b in nav["btns"]]
    if name in ("Small", "Standard"):
        # The classic bar, unchanged.
        assert "➕ ADD INVENTORY" in texts, texts
        assert (nav["gap"], nav["searchMargin"]) == ("16px", "24px"), nav
    if name == "Extra Large":
        assert "➕ ADD" in texts, texts


# ---------------------------------------------------------------------------
# Tall windows at Extra Large: the slot picker
# ---------------------------------------------------------------------------

FIT_JS = """() => {
    const panel = document.querySelector('#fcc-slot-picker .fcc-sp-panel');
    const pr = panel.getBoundingClientRect();
    const out = { panel: [Math.round(pr.top), Math.round(pr.bottom), Math.round(pr.left), Math.round(pr.right)],
                  vw: innerWidth, vh: innerHeight, spill: [], wraps: [] };
    for (const tile of panel.querySelectorAll('.fcc-sp-tile')) {
        const tr = tile.getBoundingClientRect();
        for (const el of tile.querySelectorAll('*')) {
            if (!el.getClientRects().length) continue;
            const r = el.getBoundingClientRect();
            if (r.width < 1 || r.height < 1) continue;
            if (r.right > tr.right + 1 || r.left < tr.left - 1)
                out.spill.push((el.className || el.tagName) + ' ' + (el.textContent || '').trim().slice(0, 30));
        }
        const num = tile.querySelector('.fcc-sp-num');
        if (num && tile.querySelector('.fcc-sp-star')) {
            const rg = document.createRange(); rg.selectNodeContents(num);
            const n = new Set(Array.from(rg.getClientRects()).map((x) => Math.round(x.top))).size;
            if (n !== 1) out.wraps.push(num.textContent.trim());
        }
    }
    const sc = panel.querySelector('.fcc-sp-scroll');
    out.scroll = sc ? { sh: sc.scrollHeight, ch: sc.clientHeight, oy: getComputedStyle(sc).overflowY } : null;
    const foot = panel.querySelector('.fcc-sp-footer');
    const fr = foot.getBoundingClientRect();
    out.footer = [Math.round(fr.top), Math.round(fr.bottom)];
    return out;
}"""


def test_the_slot_picker_fits_at_extra_large(page: Page, base_url: str, dev_ids):
    """Box mode and printer mode: the panel fits the 1600 x 1300 window (it
    scrolls inside its 90 % cap instead), its footer is on screen, nothing
    sticks out of a tile, and SLOT 1 stays on one line beside ⭐ Recommended."""
    _read_only(page)
    _store(page, "Extra Large")
    _load(page, base_url)
    # Extra Large really is on: a fit check at 16 px would prove nothing.
    assert _attr(page) == "xlarge" and page.evaluate(SIZES_JS)["root"] == 20
    for loc in filter(None, (dev_ids["box"], dev_ids["printer"])):
        _open_picker(page, loc, dev_ids["incoming"])
        fit = page.evaluate(FIT_JS)
        top, bottom, left, right = fit["panel"]
        assert top >= 0 and bottom <= fit["vh"] and left >= 0 and right <= fit["vw"], (loc, fit)
        assert fit["footer"][1] <= bottom, (loc, fit)
        assert not fit["spill"], f"{loc}: content sticking out of a tile at Extra Large: {fit['spill']}"
        assert not fit["wraps"], f"{loc}: the starred slot's number wraps: {fit['wraps']}"
        if fit["scroll"] and fit["scroll"]["sh"] > fit["scroll"]["ch"] + 1:
            assert fit["scroll"]["oy"] in ("auto", "scroll"), (loc, fit)
        _close_picker(page)
