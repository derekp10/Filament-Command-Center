"""Group 58, Derek's second look (2026-11-03, section H), on the real dashboard with Bootstrap
and the page's own polls: the dock (sample 1b) at the five window sizes the double-click
sweep uses, on a short list and a big shelf, and the 🏷️ (and the Admin window's 🔎) centred on
its dark round backing (sample 4(ii); drawn, not the emoji, since review 3), measured from its
pixels.

FCC's routes are answered in this browser on their real shapes
(test_audit_double_click_58_e2e.Sweep, every request that isn't a GET answered there), so
nothing reaches dev but reads, and dev's own audit stays idle.

The rules are proved hermetically in test_audit_panel_look_58_js.py; a real double click on
every control of the panel, the dock's included, in test_audit_double_click_58_e2e.py.
"""
from __future__ import annotations

import io

import pytest
from playwright.sync_api import Page

from test_audit_double_click_58_e2e import BODY, START, Sweep, _session, board  # noqa: F401  (board: the fixture)

pytestmark = pytest.mark.usefixtures("require_server")

DOCK = "#fcc-audit-panel-dock"
TALLY = "#fcc-audit-panel-tally"
CONTROLS = ["#fcc-audit-panel-needlabel", "#fcc-audit-panel-done", "#fcc-audit-panel-cancel",
            "#fcc-audit-panel-qr-needlabel", "#fcc-audit-panel-qr-done", "#fcc-audit-panel-qr-cancel"]
QRS = CONTROLS[3:]

# What is wholly seen of each of `sels`: its four corners (2 px in) and its middle hit-test to it.
UNSEEN = r"""(sels) => sels.filter((s) => { const e = document.querySelector(s); if (!e) return true;
    const r = e.getBoundingClientRect(); if (r.width < 4 || r.height < 4) return true;
    return ![[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2],
             [r.left + r.width / 2, r.top + r.height / 2]].every(([x, y]) => {
        const h = document.elementFromPoint(x, y); return !!h && e.contains(h); }); })"""
# The tiles wholly in the body's view now, and the QR boxes' top edges.
GEOMETRY = r"""([body, qrs, dock]) => { const b = document.querySelector(body).getBoundingClientRect();
    const whole = Array.from(document.querySelectorAll(body + ' .fcc-audit-tile')).filter((t) => {
        const r = t.getBoundingClientRect(); return r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5; }).length;
    return { whole, tops: qrs.map((q) => document.querySelector(q).getBoundingClientRect().top),
             dock: document.querySelector(dock).getBoundingClientRect().top,
             flow: document.getElementById('fcc-audit-panel-scroll').classList.contains('fcc-audit-scroll-flow') }; }"""


@pytest.mark.parametrize("rows", [6, 24], ids=["6-spools", "24-spools"])
def test_the_dock_keeps_the_exits_and_the_tally_in_view_at_every_size(board, rows):
    """At the top of a big shelf, its middle and its end: Needs a label, Done and Cancel
    Audit and their three QRs, in one row, and the tally above the list, wholly seen with
    no scroll of their own, and the list keeps at least a tile row. RED on 517abe1: Done,
    Cancel and their QRs were seen only at the list's end."""
    page = board.page
    board.begin(rows, rows // 2, last=0)
    what = f"{board.size[0]}x{board.size[1]}, {rows} spools"
    docks = []
    for at in ("0", "b.scrollHeight / 2", "b.scrollHeight"):
        page.evaluate(f"(s) => {{ const b = document.querySelector(s); b.scrollTop = {at}; }}", BODY)
        page.wait_for_timeout(50)
        assert page.evaluate(UNSEEN, CONTROLS + [TALLY, "#fcc-audit-last-found"]) == [], (what, at)
        got = page.evaluate(GEOMETRY, [BODY, QRS, DOCK])
        assert got["flow"] is False, (what, got)
        assert max(got["tops"]) - min(got["tops"]) <= 1, (what, got)
        assert got["whole"] >= min(2, rows), (what, at, got)
        docks.append(got["dock"])
    assert docks[0] == docks[1] == docks[2], (what, docks)      # the dock never scrolled


# --- P5: an icon on its dark round backing, centred (Derek, 2026-11-03) --------------------
# He saw sample 4b(a)'s ⚠️ sit off the middle of its circle. Measured from the pixels, at
# four times the window's scale: the ink of the icon (every pixel inside the circle, clear
# of its anti-aliased edge, that differs from the backing) against the circle's middle. The
# icon was the emoji until review 3 (Derek, 2026-11-04: "that same label icon not centered in
# circle thing"), and is drawn since; test_icon_on_dark_circle_js.py measures the drawing's
# box and weight hermetically, at 1x and 2x.

SCALE = 4
INK_FROM_BG = 48            # a channel this far from the backing's #1e1e1e is the emoji's ink
CENTRED_PX = 1.0


def _ink_offset(page: Page, sel: str):
    """How far the icon's ink sits from the middle of its backing, in CSS px (dx, dy)."""
    from PIL import Image
    box = page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect();"
                        " return { x: r.left, y: r.top, w: r.width, h: r.height }; }", sel)
    png = page.screenshot(clip={"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"]})
    img = Image.open(io.BytesIO(png)).convert("RGB")
    width, height = img.size
    cx, cy = width / 2, height / 2
    radius = min(width, height) / 2 - 2.5 * SCALE
    px = img.load()
    xs, ys = [], []
    for y in range(height):
        for x in range(width):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 > radius * radius:
                continue
            if max(abs(c - 0x1e) for c in px[x, y]) > INK_FROM_BG:
                xs.append(x)
                ys.append(y)
    assert xs, f"{sel}: no ink inside its backing"
    return ((min(xs) + max(xs) + 1) / 2 - cx) / SCALE, ((min(ys) + max(ys) + 1) / 2 - cy) / SCALE


# The button as it is, and a twin with its text alone, as before the backing (its words since
# review 3, the icon being drawn): the fill, the text colour and the height must be the same.
TWIN = r"""(sel) => { const b = document.querySelector(sel);
    const twin = b.cloneNode(false); twin.removeAttribute('id'); twin.removeAttribute('onclick');
    twin.textContent = b.textContent.replace(/\s+/g, ' ').trim();
    b.after(twin);
    const look = (e) => { const c = getComputedStyle(e); return { fill: c.backgroundColor, text: c.color,
        height: Math.round(e.getBoundingClientRect().height * 2) / 2 }; };
    const got = { button: look(b), twin: look(twin), circle: getComputedStyle(b.querySelector('.fcc-ico-on-light')).backgroundColor };
    twin.remove();
    return got; }"""


@pytest.fixture
def sharp(browser, base_url, require_server):
    """The real dashboard at four times the scale, FCC's routes answered in this browser."""
    context = browser.new_context(viewport={"width": 1366, "height": 768}, device_scale_factor=SCALE)
    page = context.new_page()
    server = Sweep(page)
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.openAuditPanel === 'function' && typeof window.openConfigModal === 'function'",
                           timeout=45_000)
    page.wait_for_function("() => state.lastAuditState === false", timeout=30_000)
    yield page, server
    context.close()


def test_the_tag_sits_in_the_middle_of_its_dark_backing_on_needs_a_label(sharp):
    """And the button keeps its yellow fill, its black text and its height. RED on fed9646:
    the 🏷️ was bare on the yellow."""
    page, server = sharp
    server.audit_id = "boot-1"
    server.session = _session("boot-1", 6, 3, last=0)
    page.evaluate(START, ["boot-1"])
    page.wait_for_selector("#fcc-audit-last-found")
    page.wait_for_timeout(300)
    sel = "#fcc-audit-panel-needlabel .fcc-ico-on-light"
    dx, dy = _ink_offset(page, sel)
    assert abs(dx) <= CENTRED_PX and abs(dy) <= CENTRED_PX, (dx, dy)
    got = page.evaluate(TWIN, "#fcc-audit-panel-needlabel")
    assert got["button"] == got["twin"], got
    assert got["button"]["fill"] == "rgb(255, 193, 7)" and got["button"]["text"] == "rgb(0, 0, 0)", got
    assert got["circle"] == "rgb(30, 30, 30)"


def test_the_lens_sits_in_the_middle_of_its_dark_backing_on_load_report(sharp):
    """The look's other light-fill spot: 🔎 on the cyan Load report (Admin / Config). RED on
    fed9646."""
    page, _server = sharp
    page.evaluate("() => window.openConfigModal()")
    page.wait_for_selector("#btn-config-attrs-scan", state="visible")
    page.wait_for_function("() => document.getElementById('configModal').classList.contains('show')")
    page.wait_for_timeout(400)                          # the window's fade
    sel = "#btn-config-attrs-scan .fcc-ico-on-light"
    dx, dy = _ink_offset(page, sel)
    assert abs(dx) <= CENTRED_PX and abs(dy) <= CENTRED_PX, (dx, dy)
    got = page.evaluate(TWIN, "#btn-config-attrs-scan")
    assert got["button"] == got["twin"], got
    assert got["button"]["fill"] == "rgb(13, 202, 240)" and got["button"]["text"] == "rgb(0, 0, 0)", got
