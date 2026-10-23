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
The readability review (2026-10-21) added the bigger sizes in smaller windows
and the setting's own edges:
  - below 992 px ⚙️ Settings stays on screen (the buttons wrap, the bar grows);
  - 992-1280 px: the title shortens with "…" and the version badge goes,
    instead of running under the buttons;
  - on a short laptop window the open Printer Status scrolls inside itself, so
    the command deck and a strip of the log and buffer stay on screen, and on
    1600 x 1300 it keeps its room;
  - the search panel's filters show their whole values at Large and Extra
    Large; dialogs and the wizard's section toggles fit a 412 px phone; the
    Location Manager's nav deck grows with the text;
  - a scan typed while the Text size select has the focus changes nothing,
    and an unknown stored size reads Standard in Settings, where Save leaves it.
The hermetic proof of the <head> script and text_size.js is
test_text_size_setting_js.py; the floor at Standard is test_text_size_guard.py.

READ-ONLY, like test_text_size_guard.py: every request that isn't a read is
answered inside the browser and never reaches the server (Save settings, which
one test clicks, included). The size is this test browser's own localStorage
(a fresh context per test).

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
Review proof (4729579's frontend served in the browser over this checkout by
a route, nothing on disk changed): 34 of the 40 new or changed tests RED. The
six that pass there are the four 1600 px title-bar checks (the version badge
was already whole at 1600 px), the before-paint check (it no longer reads the
root at <body> time) and the long-summary check, which guards the new wizard
CSS from shortening a title on a wide window.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page

from conftest import close_wizard, own_the_buffer
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
    script), so the page never draws at Standard and then jumps. global.css
    blocks rendering, so the attribute being there first is the whole
    guarantee; the root's px is checked after load (each size's test below).
    The root is NOT read at <body> time: global.css is the last stylesheet in
    <head>, after a CDN script, so on a busy run the parser can reach <body>
    before it has applied, and the root read 16 px with nothing wrong
    (readability review, 2026-10-21)."""
    _read_only(page)
    _store(page, "Extra Large")
    page.add_init_script("""(() => {
        window.__tsAtBody = 'no body seen';
        const mo = new MutationObserver(() => {
            if (document.body) {
                window.__tsAtBody = document.documentElement.getAttribute('data-fcc-text-size');
                mo.disconnect();
            }
        });
        mo.observe(document, { childList: true, subtree: true });
    })();""")
    _load(page, base_url)
    assert page.evaluate("() => window.__tsAtBody") == "xlarge"
    assert _attr(page) == "xlarge"
    assert page.evaluate("() => getComputedStyle(document.documentElement).fontSize") == "20px"


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
    const ver = document.getElementById('fcc-build-version');
    return { btns, navH: Math.round(nr.height),
             overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
             gap: getComputedStyle(actions).columnGap, searchMargin: getComputedStyle(search).marginLeft,
             version: getComputedStyle(ver).display === 'none' ? 'hidden'
                 : (ver.scrollWidth > ver.clientWidth + 1 ? 'squeezed' : 'whole') };
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
    # 1600 px wide: the version badge is whole at every size.
    assert nav["version"] == "whole", nav
    texts = [b["text"] for b in nav["btns"]]
    if name in ("Small", "Standard"):
        # The classic bar, unchanged.
        assert "➕ ADD INVENTORY" in texts, texts
        assert (nav["gap"], nav["searchMargin"]) == ("16px", "24px"), nav
    if name == "Extra Large":
        assert "➕ ADD" in texts, texts


# ---------------------------------------------------------------------------
# The readability review (2026-10-21): the bigger sizes in smaller windows
# ---------------------------------------------------------------------------

GEAR_JS = """() => {
    const cfg = document.getElementById('btn-config');
    const r = cfg.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const hit = (x >= 0 && x <= innerWidth && y >= 0 && y <= innerHeight) ? document.elementFromPoint(x, y) : null;
    const nav = document.querySelector('nav.navbar').getBoundingClientRect();
    const bottoms = Array.from(document.querySelectorAll('nav.navbar .btn')).map((b) => b.getBoundingClientRect().bottom);
    const ps = document.getElementById('printer-status-widget').getBoundingClientRect();
    return { rect: [r.left, r.top, r.right, r.bottom], vw: innerWidth, vh: innerHeight,
             hit: !!hit && (hit === cfg || cfg.contains(hit)),
             navBottom: nav.bottom, lowestButton: Math.max(...bottoms), psTop: ps.top };
}"""


@pytest.mark.parametrize("width", (744, 800, 820))
@pytest.mark.parametrize("name", ("Large", "Extra Large"))
def test_settings_stays_on_screen_in_a_narrow_window(page: Page, base_url: str, name, width):
    """Below 992 px Bootstrap puts the title bar's buttons on a line of their
    own, and at Large / Extra Large that line is wider than a tablet in
    portrait: ⚙️ Settings, the only way back to a smaller size, ran off the
    screen, where nothing scrolls to it (HEAD: x 810-857 at Extra Large, the
    window 744-820 px). The buttons now wrap onto another line, and the bar
    grows to hold them instead of drawing them over Printer Status."""
    _read_only(page)
    _store(page, name)
    page.set_viewport_size({"width": width, "height": 1100})
    _load(page, base_url)
    g = page.evaluate(GEAR_JS)
    left, top, right, bottom = g["rect"]
    assert left >= -0.5 and right <= g["vw"] + 0.5 and top >= -0.5 and bottom <= g["vh"] + 0.5, (name, width, g)
    assert g["hit"], f"{name} @ {width} px: ⚙️ isn't the thing under its own centre: {g}"
    assert g["lowestButton"] <= g["navBottom"] + 0.5 and g["navBottom"] <= g["psTop"] + 1, (
        f"{name} @ {width} px: title-bar buttons below the bar, over Printer Status: {g}")


BRAND_JS = """() => {
    const nav = document.querySelector('nav.navbar');
    const brand = nav.querySelector('.navbar-brand');
    const bcs = getComputedStyle(brand);
    const actions = nav.querySelector('.fcc-titlebar-actions').getBoundingClientRect();
    const ver = document.getElementById('fcc-build-version');
    return { brandRight: brand.getBoundingClientRect().right, actionsLeft: actions.left,
             brandClips: bcs.overflowX !== 'visible' && bcs.textOverflow === 'ellipsis',
             brandTitle: brand.getAttribute('title'),
             version: getComputedStyle(ver).display === 'none' ? 'hidden'
                 : (ver.scrollWidth > ver.clientWidth + 1 ? 'squeezed' : 'whole') };
}"""


@pytest.mark.parametrize("width", (1024, 1100, 1280))
@pytest.mark.parametrize("name", ("Large", "Extra Large"))
def test_the_title_gives_way_without_running_under_the_buttons(page: Page, base_url: str, name, width):
    """992-1280 px wide (an iPad in landscape, a small laptop): the title ran
    on under the Spoolman light and SEARCH (HEAD: 225 px of it at Extra Large,
    1024 px), and the version badge was squeezed to an empty bordered box over
    the light. Now the badge goes first (its text is its tooltip, and in
    Settings -> Build Info), then the title shortens with "…" inside its own
    box (its full text is its tooltip)."""
    _read_only(page)
    _store(page, name)
    page.set_viewport_size({"width": width, "height": 900})
    _load(page, base_url)
    b = page.evaluate(BRAND_JS)
    assert b["brandRight"] <= b["actionsLeft"] + 0.5, f"{name} @ {width} px: the title runs under the buttons: {b}"
    assert b["brandClips"] and b["brandTitle"] == "Filament Command Center", b
    assert b["version"] in ("hidden", "whole"), f"{name} @ {width} px: the version badge is squeezed: {b}"


DECK_JS = """() => {
    const q = (s) => document.querySelector(s);
    const main = q('.main-container').getBoundingClientRect();
    const deck = q('.cmd-deck').getBoundingClientRect();
    const body = q('#printer-status-widget .fcc-ps-body');
    const labels = Array.from(document.querySelectorAll('.cmd-deck .deck-label')).map((l) => l.getBoundingClientRect().bottom);
    const qrs = Array.from(document.querySelectorAll('.cmd-deck .deck-qr')).map((l) => l.getBoundingClientRect().bottom);
    return { vh: innerHeight, root: parseFloat(getComputedStyle(document.documentElement).fontSize),
             deck: [deck.top, deck.bottom], main: [main.top, main.bottom],
             row: q('.content-row').getBoundingClientRect().height,
             bufferHeader: q('.buffer-header').getBoundingClientRect().bottom,
             lowest: Math.max(...labels, ...qrs),
             body: { sh: body.scrollHeight, ch: body.clientHeight, oy: getComputedStyle(body).overflowY,
                     maxH: getComputedStyle(body).maxHeight },
             collapsed: q('#printer-status-widget').classList.contains('collapsed') };
}"""


def _load_with_printers(page: Page, base_url: str):
    _load(page, base_url)
    page.wait_for_function(
        "() => { const w = document.getElementById('printer-status-widget');"
        " return w && !w.classList.contains('fcc-ps-loading') && w.querySelectorAll('.fcc-ps-th').length > 0; }",
        timeout=45_000)
    page.wait_for_timeout(800)


# Three made-up printers of eight heads each (conftest.stub_printer_fleet): more
# Printer Status than any short window holds, whatever dev's own fleet is.
BIG_FLEET = {"ZZ Big %s" % p: {"state": {"state": "IDLE", "is_active": False},
                               "heads": [("Z%s-%d" % (p, i), False, None) for i in range(1, 9)]}
             for p in "ABC"}


# Each printer row's tiles (Derek, 2026-10-22: even rows beside the name): the
# count on each line of tiles, and whether every tile sits right of the name.
PS_ROWS_JS = r"""() => Array.from(document.querySelectorAll('#printer-status-widget .fcc-ps-row')).map((row) => {
    const nameR = row.querySelector('.fcc-ps-name-col').getBoundingClientRect();
    const tiles = Array.from(row.querySelectorAll('.fcc-ps-th')).map((t) => t.getBoundingClientRect());
    const lines = [];
    tiles.forEach((r) => { const l = lines.find((x) => Math.abs(x.top - r.top) < 2); if (l) l.n++; else lines.push({ top: r.top, n: 1 }); });
    lines.sort((a, b) => a.top - b.top);
    return { printer: row.dataset.printer, rows: lines.map((l) => l.n),
             beside: tiles.every((r) => r.left >= nameR.right - 0.5) }; })"""


def _uneven(rows: list) -> list:
    """The printer rows whose tiles aren't in even rows beside the name: the
    lines differ by more than one, a longer line follows a shorter one, or one
    tile sits alone under fuller lines."""
    bad = []
    for r in rows:
        n = r["rows"]
        if not n:
            continue   # a printer with no heads draws no tiles
        if not r["beside"] or max(n) - min(n) > 1 or n != sorted(n, reverse=True) or (len(n) > 1 and n[-1] == 1):
            bad.append(r)
    return bad


@pytest.mark.parametrize("window", ((1366, 657), (1280, 689)))
@pytest.mark.parametrize("name", ("Standard", "Large", "Extra Large"))
def test_printer_status_leaves_the_deck_and_the_buffer_on_screen(page: Page, base_url: str, name, window):
    """The dashboard doesn't scroll, and the open Printer Status had no height
    limit: at Extra Large on a 1366 x 768 laptop (or a Framework 12 at 150 %)
    it pushed the command deck half off the bottom, cutting the QR codes that
    are scanned from the screen and every deck label, and at Large it left
    Live Activity and the Buffer Zone 2-23 px tall (HEAD, on dev's fleet). Now
    the open widget scrolls inside itself, so the whole deck and a 7rem strip
    of the log and the buffer stay on screen. Checked on a fleet bigger than
    the window (BIG_FLEET), so the limit is always in play. Since 2026-10-22
    each printer's 8 heads are 4 + 4 beside its name (they were 7 + 1, or a
    line of 8, under it)."""
    from conftest import stub_printer_fleet
    _read_only(page)
    stub_printer_fleet(page, BIG_FLEET)
    _store(page, name)
    page.set_viewport_size({"width": window[0], "height": window[1]})
    _load_with_printers(page, base_url)
    d = page.evaluate(DECK_JS)
    assert not d["collapsed"], "Printer Status should start open in a fresh browser"
    top, bottom = d["deck"]
    assert top >= d["main"][0] - 0.5 and bottom <= min(d["main"][1], d["vh"]) + 0.5, f"{name} {window}: the deck is cut: {d}"
    assert d["lowest"] <= d["vh"] + 0.5, f"{name} {window}: a deck QR or label is below the window: {d}"
    assert d["row"] >= 7 * d["root"] - 2, f"{name} {window}: Live Activity / Buffer Zone squeezed to {d['row']} px: {d}"
    assert d["bufferHeader"] <= top, d
    assert d["body"]["sh"] > d["body"]["ch"] + 1 and d["body"]["oy"] in ("auto", "scroll"), (
        f"{name} {window}: Printer Status should scroll inside itself here: {d}")
    rows = page.evaluate(PS_ROWS_JS)
    assert len(rows) == 3 and all(r["rows"] == [4, 4] and r["beside"] for r in rows), (
        f"{name} {window}: the 8 heads should be 4 + 4 beside each name: {rows}")


@pytest.mark.parametrize("name", SIZES)
def test_on_a_tall_window_printer_status_keeps_its_room(page: Page, base_url: str, name):
    """Derek's 1600 x 1300 window: the limit is 40 % of the window (520 px),
    more than the open widget needs at any size, so nothing changes there.
    And dev's own fleet sits in even rows beside each name (2026-10-22: the
    INDX's 8 heads 4 + 4, never 7 + 1)."""
    _read_only(page)
    _store(page, name)
    _load_with_printers(page, base_url)
    d = page.evaluate(DECK_JS)
    assert d["body"]["maxH"] == "520px", d
    rows = page.evaluate(PS_ROWS_JS)
    assert rows and not _uneven(rows), f"{name}: printers whose tiles aren't even rows beside the name: {_uneven(rows)}"


FIELDS_JS = """() => {
    const c = document.createElement('canvas').getContext('2d');
    const textW = (el, text) => { const cs = getComputedStyle(el);
        c.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
        return c.measureText(text).width; };
    const room = (el) => { const cs = getComputedStyle(el);
        return el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight); };
    const out = {};
    for (const id of ['global-search-min-weight', 'global-search-max-weight', 'global-search-color-hex']) {
        const el = document.getElementById(id);
        out[id] = { value: el.value, scrollW: el.scrollWidth, clientW: el.clientWidth,
                    textW: textW(el, el.value), room: room(el) };
    }
    const sel = document.getElementById('global-search-material');
    out.material = Array.from(sel.options).map((o) => ({ text: o.text, textW: textW(sel, o.text) }));
    out.materialRoom = room(sel);
    return out;
}"""


@pytest.mark.parametrize("name", ("Large", "Extra Large"))
def test_the_search_filters_show_their_whole_values(page: Page, base_url: str, name):
    """The search panel's filter row kept px widths while its text grew: at
    Large 1000 g read "100", at Extra Large "10", #1A2B3C read #1A2B3 and the
    material select's own "Any Mat" read "Any M" (HEAD). The widths are rem
    now (the same at Standard), so what fits at Standard fits at every size.
    The searches the typing starts are reads."""
    _read_only(page)
    _store(page, name)
    _load(page, base_url)
    page.evaluate("() => SearchEngine.open()")
    page.wait_for_function("() => document.getElementById('offcanvasSearch').classList.contains('show')")
    page.wait_for_timeout(600)
    page.fill("#global-search-min-weight", "1000")
    page.fill("#global-search-max-weight", "2500")
    page.fill("#global-search-color-hex", "#1A2B3C")
    page.focus("#global-search-query")
    page.wait_for_timeout(400)
    f = page.evaluate(FIELDS_JS)
    for fid in ("global-search-min-weight", "global-search-max-weight", "global-search-color-hex"):
        x = f[fid]
        assert x["scrollW"] <= x["clientW"] and x["textW"] <= x["room"] + 0.5, f"{name}: {fid} cuts its value: {x}"
    # "Any Mat" (the default) and every material name as short as PA612 or PETG fits.
    short = [o for o in f["material"] if o["text"] == "Any Mat" or len(o["text"]) <= 5]
    assert any(o["text"] == "Any Mat" for o in short), f["material"][:3]
    cut = [o for o in short if o["textW"] > f["materialRoom"] + 0.5]
    assert not cut, f"{name}: the material select cuts {cut} (room {f['materialRoom']:.1f} px)"


@pytest.mark.parametrize("start, scan", [("Standard", "LOC:LR-MDB-1"), ("Large", "SPOOL"), ("Standard", "EJECT")])
def test_a_scan_into_the_text_size_select_changes_nothing(page: Page, base_url: str, start, scan):
    """A scanner types into whatever has the focus, and the Text size select
    keeps it after a pick. Its own type-ahead took each character: "LOC:…"
    picked Large, "SPOOL" Small, "EJECT" Extra Large, applied and stored at
    once (HEAD). Now a typed character does nothing to it, and the scan still
    reaches the scan accumulator whole (its /api/identify_scan is answered in
    this browser)."""
    _read_only(page)
    _store(page, start)
    scans = []
    page.on("request", lambda r: scans.append(r.post_data or "")
            if r.method == "POST" and "/api/identify_scan" in r.url else None)
    _load(page, base_url)
    _open_settings(page)
    sel = page.locator(SELECT)
    sel.focus()
    before = _state(page)
    assert before["stored"] == start
    page.keyboard.type(scan, delay=5)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    assert _state(page) == before, f"the scan {scan!r} changed the size"
    assert sel.input_value() == start
    assert any(scan in s for s in scans), f"the scan {scan!r} never reached /api/identify_scan whole: {scans}"
    # The keyboard still picks a size.
    sel.focus()
    page.keyboard.press("ArrowDown")
    page.wait_for_function("(s) => localStorage.getItem('fcc.textSize') !== s", arg=start, timeout=3000)


@pytest.mark.parametrize("junk", ("large", "Huge"))
def test_an_unknown_stored_size_reads_standard_and_save_leaves_it(page: Page, base_url: str, junk):
    """A stored size that isn't one of the four (typed by hand, or renamed in
    a later build) is Standard on the page, and Settings now says so too. It
    used to show Small with the junk value as its starting point, so Save
    settings, for any other setting, stored Small (HEAD)."""
    _read_only(page)
    _store(page, junk)
    _load(page, base_url)
    assert _attr(page) == "standard"
    _open_settings(page)
    sel = page.locator(SELECT)
    assert sel.input_value() == "Standard"
    assert sel.get_attribute("data-initial") == "Standard"
    page.click("#cfgset-save")
    page.wait_for_timeout(1000)
    assert page.evaluate("(k) => localStorage.getItem(k)", KEY) == junk, "Save stored a size nobody picked"
    assert _attr(page) == "standard"


PANEL_JS = """(sel) => { const el = document.querySelector(sel); if (!el) return null;
    const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, vw: innerWidth }; }"""


@pytest.mark.parametrize("name", ("Large", "Extra Large"))
def test_dialogs_fit_a_phone_at_the_bigger_sizes(page: Page, base_url: str, dev_ids, name):
    """412 px wide: rem min-widths with no cap made Quick Weigh 475 px wide
    at Extra Large, the Activity Log 525 px and the Quick-Swap confirm 525 px,
    cut on both sides where nothing scrolls (HEAD). Each is capped by the
    screen now. Nothing is saved or swapped: each is closed with Escape.
    Since 2026-10-22 the move question and "Record it as coming from…" lay
    their buttons over their QRs in shared columns: they fit too, every button
    and QR inside the dialog (each QR under its button:
    test_qr_under_buttons_e2e.py)."""
    _read_only(page)
    _store(page, name)
    page.set_viewport_size({"width": 412, "height": 915})
    _load(page, base_url)
    out = {}
    for label, opener, sel in (
            ("Move question", "() => { window.confirmHeadLoad({ answer: { status: 'requires_confirm',"
             " confirm_type: 'head_fed', can_store: true, spools: [57], title: 'Load #57 onto XL-1?',"
             " body: 'LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #1.', fed_heads: [{ toolhead: 'XL-1',"
             " box: 'LR-MDB-1', slot: '1', confirm_key: 'XL-1#1' }], active_prints: [] }, box: 'LR-MDB-1',"
             " onLoad() {}, onStore() {}, onCancel() {} }); }", "#fcc-active-print-confirm-overlay .fcc-apc-panel"),
            ("Record it as coming from", "() => { window.__tsRs = _askRecordSource({ head: 'XL-1', spool_location: '',"
             " feeds: [{ box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '2', free: false,"
             " claimed_by: 99 }] }, 57, null); }", "#fcc-record-source .fcc-rs-panel")):
        page.evaluate(opener)
        page.wait_for_selector(sel + " .fcc-confirm-qr-row", timeout=10_000)
        page.wait_for_timeout(400)
        box = page.evaluate(PANEL_JS, sel)
        if box:
            box["inside"] = page.evaluate("""(sel) => { const p = document.querySelector(sel).getBoundingClientRect();
                return Array.from(document.querySelectorAll(sel + ' button, ' + sel + ' .fcc-qr-card')).every((el) => {
                    const r = el.getBoundingClientRect(); return r.left >= p.left - 0.5 && r.right <= p.right + 0.5; }); }""",
                                          sel)
            box["sideways"] = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
        out[label] = box
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    cut = {k: v for k, v in out.items() if not v or not v["inside"] or v["sideways"]}
    assert not cut, f"{name} at 412 px: questions whose buttons or QRs stick out: {cut}"
    page.evaluate("""() => window.WeightEntry.openModal({ title: 'Quick Weigh', spool: { id: 57, display: 'A test spool',
        initial_weight: 1000, used_weight: 100, color_hex: 'ff0000' }, empty_spool_weight: 200, empty_source: 'spool' })""")
    page.wait_for_selector('[role=dialog][aria-labelledby="fcc-we-title"]', timeout=10_000)
    page.wait_for_timeout(400)
    out["Quick Weigh"] = page.evaluate(PANEL_JS, '[role=dialog][aria-labelledby="fcc-we-title"]')
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.evaluate("() => window.openLogPillOverlay()")
    page.wait_for_selector("#fcc-log-pill-close", timeout=10_000)
    page.wait_for_timeout(400)
    out["Activity Log"] = page.evaluate(PANEL_JS, "#fcc-log-pill-overlay > div")
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.evaluate("(id) => window.openManage(id)", dev_ids["head"])
    page.wait_for_function("() => document.querySelectorAll('#quickswap-grid .fcc-qs-card').length > 0", timeout=15_000)
    page.wait_for_timeout(800)
    page.locator("#quickswap-grid .fcc-qs-card").first.click()
    page.wait_for_function("() => !!document.getElementById('fcc-quickswap-confirm-overlay')", timeout=10_000)
    page.wait_for_timeout(400)
    out["Quick-Swap confirm"] = page.evaluate(PANEL_JS, "#fcc-quickswap-confirm-overlay > div")
    page.keyboard.press("Escape")
    cut = {k: v for k, v in out.items() if not v or v["left"] < -0.5 or v["right"] > v["vw"] + 0.5}
    assert not cut, f"{name} at 412 px: dialogs wider than the screen: {cut}"


# A part's own box, not its bounding box: a closed section's ▾ is rotated, and
# its rotated glyph box runs a few px past the toggle on dev too, fully drawn.
WIZ_TOGGLES_JS = """() => Array.from(document.querySelectorAll('#wizardModal .fcc-wiz-section-toggle'))
    .filter((t) => t.getClientRects().length && t.getBoundingClientRect().width > 0)
    .map((t) => { const tr = t.getBoundingClientRect();
        const title = t.querySelector('.fcc-wiz-section-title');
        const right = (p) => { const r = p.getBoundingClientRect(); return (r.left + r.right) / 2 + p.offsetWidth / 2; };
        const parts = Array.from(t.querySelectorAll('.fcc-wiz-section-chevron, .badge'));
        return { title: title.textContent.trim(), titleCut: title.scrollWidth > title.clientWidth + 1,
                 out: parts.filter((p) => right(p) > tr.right + 0.5)
                     .map((p) => [p.textContent.trim(), Math.round(right(p) - tr.right)]) }; })"""


def _open_wizard(page: Page, opener: str, arg=None):
    page.evaluate("""() => { window.__tsWiz = false; document.getElementById('wizardModal')
        .addEventListener('shown.bs.modal', () => { window.__tsWiz = true; }, { once: true }); }""")
    page.evaluate(opener, arg)
    page.wait_for_function("() => window.__tsWiz === true", timeout=15_000)
    page.wait_for_timeout(600)


@pytest.mark.parametrize("name", ("Large", "Extra Large"))
def test_the_wizard_toggles_keep_their_badge_and_chevron_on_a_phone(page: Page, base_url: str, name):
    """412 px wide: a section title that couldn't shrink pushed its "optional"
    badge and its ▾ out of the toggle ("Custom Filament Attributes" at Large,
    four sections at Extra Large; HEAD). The title gives way with "…" now."""
    _read_only(page)
    _store(page, name)
    page.set_viewport_size({"width": 412, "height": 915})
    _load(page, base_url)
    _open_wizard(page, "() => window.openWizardModal()")
    page.evaluate("() => wizardSelectType('manual')")
    page.wait_for_timeout(1200)
    toggles = page.evaluate(WIZ_TOGGLES_JS)
    assert toggles, "no wizard section toggles on screen"
    out = [t for t in toggles if t["out"]]
    assert not out, f"{name} at 412 px: badges / chevrons outside their toggle: {out}"
    close_wizard(page)


def test_a_long_summary_never_shortens_a_wizard_title(page: Page, base_url: str, dev_ids):
    """The other side of that fix, on Derek's 1600 px window: a section's
    summary takes only the room left over, so however long it is, the title
    keeps its whole text (the edit wizard fills every summary)."""
    _read_only(page)
    _load(page, base_url)
    _open_wizard(page, "(id) => window.openEditWizard(id)", dev_ids["spool"])
    page.wait_for_timeout(1500)
    toggles = page.evaluate(WIZ_TOGGLES_JS)
    assert toggles, "no wizard section toggles on screen"
    cut = [t["title"] for t in toggles if t["titleCut"] or t["out"]]
    assert not cut, f"wizard titles shortened at 1600 px: {cut}"
    close_wizard(page)


NAVDECK_JS = r"""() => {
    const deck = document.getElementById('loc-mgr-nav-deck');
    const out = { deckH: deck.getBoundingClientRect().height, cards: [] };
    for (const card of deck.querySelectorAll('.nav-card')) {
        const cr = card.getBoundingClientRect();
        const cut = [];
        for (const el of card.querySelectorAll('*')) {
            if (!el.getClientRects().length) continue;
            const r = el.getBoundingClientRect();
            if (r.width < 1 || r.height < 1) continue;
            const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
            if (own && (r.top < cr.top - 0.5 || r.bottom > cr.bottom + 0.5)) cut.push(el.textContent.trim().slice(0, 30));
        }
        const badge = Array.from(card.querySelectorAll('.badge')).find((b) => /ARCHIVED/.test(b.textContent));
        const btn = card.querySelector('.fcc-card-action-btn');
        let overlap = 0;
        if (badge && btn) {
            const i = btn.parentElement.getBoundingClientRect(), b = badge.getBoundingClientRect();
            if (i.left < b.right && b.left < i.right) overlap = Math.max(0, Math.min(i.bottom, b.bottom) - Math.max(i.top, b.top));
        }
        out.cards.push({ fits: card.scrollHeight <= card.clientHeight + 1, cut, badge: !!badge, overlap });
    }
    return out;
}"""


def test_the_location_manager_nav_deck_grows_with_the_text(page: Page, base_url: str, api_base_url, dev_ids):
    """Extra Large: the nav deck stayed 200 px tall, and the centre card of an
    archived buffered spool held 197 px of content in 190: READY TO SLOT
    started above the card, its last line lost its descenders, and the
    ❌🔍✏️🖨️ icons sat on the ARCHIVED badge (HEAD). The deck is 12.5rem now
    (200 px at Standard). This page's own buffer: the box's spools, the first
    one marked archived in this browser only."""
    import json as _json
    contents = requests.get(api_base_url + "/api/get_contents?id=" + dev_ids["box"], timeout=20).json()
    spools = [s for s in contents if s.get("id") is not None and not s.get("is_ghost")][:3]
    if not spools:
        pytest.skip(f"{dev_ids['box']} holds no spool to buffer")
    arch = spools[0]["id"]

    def mark(o):
        if isinstance(o, dict):
            for k in list(o):
                if str(k) == str(arch) and isinstance(o[k], dict):
                    o[k]["archived"] = True
            if o.get("id") == arch:
                o["archived"] = True
            for v in o.values():
                mark(v)
        elif isinstance(o, list):
            for v in o:
                mark(v)
        return o

    _read_only(page)
    own_the_buffer(page, [dict(spools[0], archived=True)] + spools[1:])

    def refresh(route, request):
        if request.method.upper() != "POST":
            route.continue_()
            return
        resp = route.fetch()
        try:
            route.fulfill(response=resp, body=_json.dumps(mark(resp.json())))
        except ValueError:
            route.fulfill(response=resp)
    page.route("**/api/spools/refresh", refresh)
    _store(page, "Extra Large")
    _load(page, base_url)
    page.wait_for_function("(id) => (state.heldSpools || []).length >= 1 && state.heldSpools[0].archived === true",
                           arg=arch, timeout=20_000)
    page.evaluate("(b) => window.openManage(b)", dev_ids["box"])
    page.wait_for_function("() => { const m = document.getElementById('manageModal'); return m && m.classList.contains('show'); }",
                           timeout=15_000)
    page.wait_for_timeout(2000)
    d = page.evaluate(NAVDECK_JS)
    assert d["deckH"] == pytest.approx(250, abs=1), d
    assert any(c["badge"] for c in d["cards"]), f"no card shows the ARCHIVED badge: {d}"
    bad = [c for c in d["cards"] if not c["fits"] or c["cut"] or c["overlap"] > 4]
    assert not bad, f"nav cards that clip their text or put their icons on the badge at Extra Large: {bad}"


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
