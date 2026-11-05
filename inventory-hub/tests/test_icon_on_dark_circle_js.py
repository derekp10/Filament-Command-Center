"""Review 3 (Derek, 2026-11-04): the icon on its small dark round backing is drawn, and sits in
the middle of it.

Derek, on the round's pictures: "that same label icon not centered in circle thing". P5 put the
🏷️ (and Settings' 🔎) on a dark round backing (.fcc-ico-on-light) and measured the emoji's box
within a pixel of the circle's middle; but the emoji is drawn on a slant, its body low-left and
its ring up-right, so even centred by its box it read as off, and each system draws its own
emoji. Those three spots (the dock's Needs a label, a found tile's 🏷️ once marked, Settings' Load
report) now draw an inline SVG (inv_cmd.js TAG_ICON, modals_config.html's magnifier): a tag in
the emoji's warm yellow and orange with its dark hole, a magnifier, each balanced about the
circle's middle. Every other 🏷️ in FCC, and the words beside these, stay emoji.

The drawing is as big as its backing, its 32 units the circle, so where it sits in the circle
is the drawing's own coordinates (centred on 16, 16). Painted a fraction of a pixel off the
device's grid, the circle can take a whole pixel more at an edge, which moves its middle by up
to half a pixel; the sub-pixel sweep below holds the drawing to the same limits there.

Measured from the pixels, at 1x and 2x and at each Text size: the drawn ink (every pixel inside
the circle, clear of its anti-aliased edge, that differs from the backing's #1e1e1e) has its box
within 1 px of the circle's middle and its weight (the ink's colour-weighted centre) within
0.75 px, and fills at least half the circle's width. On a real DOM, hermetic: the REAL
inv_cmd.js dock and tile (test_audit_panel_58_js's `audit`, page61's modules) and the REAL Load
report button from modals_config.html, with global.css and Bootstrap 5.3's button rules, in an
isolated browser (no network), so it runs under --offline. The real dashboard's twin is
test_audit_panel_look_58_e2e.py's. RED on 76fb961 (27 of 31; the two pins pass): the backing
held the emoji, not a drawing, and the 🔎's ink, its box within half a pixel of the middle (as
P5 measured it), had its weight 0.6 to 1.25 px up-right of it at every position.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from PIL import Image

import conftest
from test_audit_page_58_js import SESSION
from test_audit_panel_58_js import audit  # noqa: F401  (audit: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (page61: the fixture)

HUB = Path(__file__).resolve().parent.parent
BACKING = "#1e1e1e"
BOX_PX = 1.0                    # the ink's box, from the circle's middle
WEIGHT_PX = 0.75                # the ink's weight, from the circle's middle
SIZES = ["standard", "large", "xlarge"]
NEED = "#fcc-audit-panel-needlabel .fcc-ico-on-light"
LOAD = "#btn-config-attrs-scan .fcc-ico-on-light"

# Bootstrap 5.3's button rules, as the page has them from its CDN (the hermetic page has no
# network): the size, the padding and the fill of .btn, .btn-sm, .btn-warning and .btn-info,
# so each icon's backing sits in its real button.
BOOTSTRAP_BUTTONS = """
*, ::before, ::after { box-sizing: border-box; }
.btn { display: inline-block; padding: .375rem .75rem; font-family: system-ui, -apple-system, "Segoe UI", Roboto,
       "Helvetica Neue", "Noto Sans", "Liberation Sans", Arial, sans-serif; font-size: 1rem; font-weight: 400;
       line-height: 1.5; color: #212529; text-align: center; vertical-align: middle; border: 1px solid transparent;
       border-radius: .375rem; background-color: transparent; }
.btn-sm { padding: .25rem .5rem; font-size: .875rem; border-radius: .25rem; }
.btn-warning { color: #000; background-color: #ffc107; border-color: #ffc107; }
.btn-info { color: #000; background-color: #0dcaf0; border-color: #0dcaf0; }
.fw-bold { font-weight: 700 !important; }
"""


@pytest.fixture(params=[1, 2], ids=["1x", "2x"])
def isolated_page(request, _isolated_chromium):
    """conftest's isolated_page (no route to any network), at 1x and at 2x."""
    context = _isolated_chromium.new_context(viewport=conftest.BASELINE_VIEWPORT, device_scale_factor=request.param)
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


@pytest.fixture
def icons(audit):
    """The panel up (`audit`), with Bootstrap's button rules."""
    audit.add_style_tag(content=BOOTSTRAP_BUTTONS)
    return audit


def _scale(page):
    return page.evaluate("() => window.devicePixelRatio")


def _disk(px, box, fill, back, scale):
    """The dark circle as painted: the middle of its coverage (each pixel's share of the
    backing's colour against the button's fill, read from its anti-aliased rim), so it is found
    to a fraction of a pixel wherever the device's pixels cut it. Pixels well inside the rim,
    where the icon is, count as covered; the band around the rim is read from their colours.
    Also its diameter (the coverage's area as a circle's, CSS px) and the darkest share in a
    ring just outside its rim, which is the button's fill unless something dark touches it."""
    ox, oy = box["x"] * scale, box["y"] * scale          # the screenshot's own origin, device px
    r = box["size"] * scale / 2
    mx, my = (box["left"] + box["size"] / 2) * scale - ox, (box["top"] + box["size"] / 2) * scale - oy
    span = [b - f for b, f in zip(back, fill)]
    norm = sum(c * c for c in span)
    area = sx = sy = outside = 0.0
    w, h = int(box["w"] * scale), int(box["h"] * scale)
    for y in range(h):
        for x in range(w):
            d = ((x + 0.5 - mx) ** 2 + (y + 0.5 - my) ** 2) ** 0.5
            if d > r + 2.0 * scale:
                continue
            a = sum((p - f) * s for p, f, s in zip(px[x, y], fill, span)) / norm
            a = min(1.0, max(0.0, a))
            if d > r + 1.25 * scale:                     # the ring outside the rim
                outside = max(outside, a)
                continue
            if d < r - 2.5 * scale:
                a = 1.0
            area += a
            sx += a * (x + 0.5)
            sy += a * (y + 0.5)
    return sx / area, sy / area, 2 * (area / 3.14159265) ** 0.5 / scale, outside


def ink(page, sel):
    """How the drawn ink sits in the backing `sel`, in CSS px: its box's middle and its weight
    against the middle of the dark circle as drawn (found from its pixels, so a circle and an
    icon painted a fraction of a pixel apart are measured as the eye sees them), (dx, dy) each,
    and its width against the circle's."""
    scale = _scale(page)
    box = page.evaluate("""(s) => { const e = document.querySelector(s); const r = e.getBoundingClientRect();
        const fill = getComputedStyle(e.closest('button')).backgroundColor.match(/\\d+/g).slice(0, 3).map(Number);
        const x = Math.floor(r.left - 2), y = Math.floor(r.top - 2);
        return { x, y, w: Math.ceil(r.right + 2) - x, h: Math.ceil(r.bottom + 2) - y, left: r.left, top: r.top,
                 size: r.width, fill }; }""", sel)
    # A clip on whole CSS px (whole device px at 1x and 2x), so the capture is the screen's own.
    png = page.screenshot(clip={"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"]})
    img = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = img.size
    back = tuple(int(BACKING[i:i + 2], 16) for i in (1, 3, 5))
    px = img.load()
    near = lambda p: max(abs(c - b) for c, b in zip(p, back))   # noqa: E731
    cx, cy, across, outside = _disk(px, box, box["fill"], back, scale)
    # Only the circle is that dark here: the button's fill all round it, and its coverage a
    # circle of its own size, to the device pixels its edges may be painted out to (a fill a
    # fraction of a pixel off the grid can cover the whole pixel at each edge). Anything dark
    # beside it (a backing that overflows its button onto a dark panel) would move the middle
    # this measures from.
    assert outside < 0.25, (f"{sel}: something dark touches its circle (a share of {outside:.2f} of the "
                            "backing's colour just outside its rim)")
    assert abs(across - box["size"]) <= 2 / scale + 0.25,         (f"{sel}: its circle is {across:.2f} px across for a {box['size']:.2f} px backing: it is cut")
    radius = box["size"] * scale / 2 - 1.5 * scale
    xs, ys, total, sx, sy = [], [], 0.0, 0.0, 0.0
    for y in range(h):
        for x in range(w):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 > radius * radius:
                continue
            d = near(px[x, y])
            if d > 48:
                xs.append(x)
                ys.append(y)
            if d > 12:
                total += d
                sx += d * (x + 0.5)
                sy += d * (y + 0.5)
    assert xs, f"{sel}: no ink inside its backing"
    return {"box": (((min(xs) + max(xs) + 1) / 2 - cx) / scale, ((min(ys) + max(ys) + 1) / 2 - cy) / scale),
            "weight": ((sx / total - cx) / scale, (sy / total - cy) / scale),
            "width": (max(xs) - min(xs) + 1) / (box["size"] * scale),
            "across": across}


def _centred(got, what):
    (bx, by), (wx, wy) = got["box"], got["weight"]
    assert abs(bx) <= BOX_PX and abs(by) <= BOX_PX, (what, got)
    assert abs(wx) <= WEIGHT_PX and abs(wy) <= WEIGHT_PX, (what, got)
    assert got["width"] >= 0.5, (what, got)                  # an icon, not a speck


def _drawn(page, sel):
    """The backing holds the drawing alone, as big as the backing itself (to 1/64 px)."""
    return page.evaluate("""(s) => { const b = document.querySelector(s); const svg = b.querySelector(':scope > svg.fcc-ico-svg');
        if (!svg) return { svg: false, text: b.textContent };
        const r = b.getBoundingClientRect(), q = svg.getBoundingClientRect();
        return { svg: true, text: b.textContent, same: ['left', 'top', 'width', 'height'].every((k) => Math.abs(r[k] - q[k]) < 1 / 64),
                 hidden: svg.getAttribute('aria-hidden'), focusable: svg.getAttribute('focusable') }; }""", sel)


def _text_size(page, size):
    page.evaluate("(s) => document.documentElement.setAttribute('data-fcc-text-size', s)", size)
    page.wait_for_timeout(60)


def _marked_tile(page):
    """The panel with #57 found and marked here: its tile's 🏷️ wears the backing."""
    session = dict(SESSION, expected=[dict(r, found=True, flagged_here=True, label_status=True)
                                      if r["id"] == 57 else r for r in SESSION["expected"]])
    page.evaluate("(s) => { window.__session = s; window.refreshAuditSession(); }", session)
    page.wait_for_selector("[data-audit-tag='57'][data-audit-tag-state='marked']")
    return "[data-audit-tag='57'] .fcc-ico-on-light"


def _load_report(page, left=20.0):
    """Settings' Load report button, as modals_config.html draws it, in its card header (the
    header's own #1a1a1a), `left` px from the window's edge."""
    src = (HUB / "templates" / "components" / "modals_config.html").read_text(encoding="utf-8")
    button = re.search(r'<button[^>]*id="btn-config-attrs-scan".*?</button>', src, re.S).group(0)
    button = re.sub(r"\{#.*?#\}", "", button, flags=re.S)            # Jinja's comments
    page.evaluate("""([b, left]) => { let host = document.getElementById('fcc-test-config');
        if (!host) { host = document.createElement('div'); host.id = 'fcc-test-config'; document.body.appendChild(host); }
        host.style.cssText = `position:fixed; left:${left}px; top:20px; z-index:30000; padding:8px; background:#1a1a1a;`;
        host.innerHTML = b; }""", [button, left])
    return LOAD


@pytest.mark.parametrize("size", SIZES)
def test_needs_a_labels_tag_is_drawn_in_the_middle_of_its_backing(icons, size):
    """The dock's Needs a label: a drawn tag, its box and its weight in the middle of the
    circle, at 1x and 2x. The button's words and name are as they were."""
    _text_size(icons, size)
    assert _drawn(icons, NEED) == {"svg": True, "text": "", "same": True, "hidden": "true", "focusable": "false"}
    _centred(ink(icons, NEED), f"Needs a label at {size}")
    got = icons.evaluate("""(s) => { const b = document.querySelector(s); const ico = b.querySelector('.fcc-ico-on-light');
        return { text: b.textContent.replace(/\\s+/g, ' ').trim(), hidden: ico.getAttribute('aria-hidden'),
                 fill: getComputedStyle(b).backgroundColor }; }""", "#fcc-audit-panel-needlabel")
    assert got == {"text": "Needs a label", "hidden": "true", "fill": "rgb(255, 193, 7)"}, got


@pytest.mark.parametrize("size", SIZES)
def test_a_marked_tiles_tag_is_drawn_in_the_middle_of_its_backing(icons, size):
    """A found tile's 🏷️ once marked here (P6, its yellow button): the same drawn tag."""
    _text_size(icons, size)
    sel = _marked_tile(icons)
    assert _drawn(icons, sel)["same"] is True
    _centred(ink(icons, sel), f"a marked tile's tag at {size}")


@pytest.mark.parametrize("size", SIZES)
def test_load_reports_magnifier_is_drawn_in_the_middle_of_its_backing(icons, size):
    """Settings' Load report: a drawn magnifier, its lens and handle balanced about the middle."""
    _load_report(icons)
    _text_size(icons, size)
    assert _drawn(icons, LOAD) == {"svg": True, "text": "", "same": True, "hidden": "true", "focusable": "false"}
    _centred(ink(icons, LOAD), f"Load report at {size}")
    got = icons.evaluate("""(s) => { const b = document.querySelector(s);
        return { text: b.textContent.replace(/\\s+/g, ' ').trim(), fill: getComputedStyle(b).backgroundColor }; }""",
                         "#btn-config-attrs-scan")
    assert got == {"text": "Load report", "fill": "rgb(13, 202, 240)"}, got


@pytest.mark.parametrize("left", [20.0, 20.25, 20.5, 20.75])
def test_the_drawing_stays_in_the_middle_wherever_the_button_lands(icons, left):
    """A button a fraction of a pixel off the device's grid (as layout puts one, beside text of
    any width): the drawing is centred to the same limits there."""
    _load_report(icons, left)
    _centred(ink(icons, LOAD), f"Load report at left {left}")
    _load_report(icons, 20.0)
    icons.evaluate("(dx) => { const b = document.getElementById('fcc-audit-panel-needlabel'); b.style.position = 'relative';"
                   " b.style.left = dx + 'px'; }", left - 20.0)
    _centred(ink(icons, NEED), f"Needs a label nudged {left - 20.0} px")


def test_the_buttons_keep_their_size(icons):
    """The drawing changes no button's size: each is as tall as its twin with words alone (the
    backing's negative margins, as with the emoji; a pin)."""
    _load_report(icons)
    got = icons.evaluate("""(sels) => sels.map((s) => { const b = document.querySelector(s);
        const twin = b.cloneNode(false); twin.removeAttribute('id'); twin.removeAttribute('onclick');
        twin.textContent = b.textContent.replace(/\\s+/g, ' ').trim(); b.after(twin);
        const h = [b.getBoundingClientRect().height, twin.getBoundingClientRect().height]; twin.remove(); return h; })""",
                         ["#fcc-audit-panel-needlabel", "#btn-config-attrs-scan"])
    for mine, twin in got:
        assert abs(mine - twin) < 0.5, got


def test_every_other_tag_stays_an_emoji(icons):
    """Only the backing's tag is drawn: a found tile's 🏷️ not marked here stays the emoji, as
    does every 🏷️ in FCC's words (a pin: review 3 changed only the backing)."""
    session = dict(SESSION, expected=[dict(r, found=True, flagged_here=False, label_status=None)
                                      if r["id"] == 57 else r for r in SESSION["expected"]])
    icons.evaluate("(s) => { window.__session = s; window.refreshAuditSession(); }", session)
    icons.wait_for_selector("[data-audit-tag='57'][data-audit-tag-state='none']")
    assert icons.evaluate("() => document.querySelector(\"[data-audit-tag='57']\").textContent.trim()") == "🏷️"
    assert not icons.evaluate("() => !!document.querySelector(\"[data-audit-tag='57'] svg\")")


def _contrast(a, b):
    def lum(hexc):
        rgb = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_each_drawn_colour_stands_out_from_the_backing():
    """Readable contrast for a drawing (WCAG's 3:1 for a graphic): every colour the two icons
    draw stands out from the #1e1e1e backing, but the tag's dark hole, which is meant to read
    as the backing through it."""
    js = (HUB / "static" / "js" / "modules" / "inv_cmd.js").read_text(encoding="utf-8")
    tag = re.search(r"const TAG_ICON = (.*?);\r?\n", js, re.S).group(1)
    html = (HUB / "templates" / "components" / "modals_config.html").read_text(encoding="utf-8")
    lens = re.search(r'id="btn-config-attrs-scan".*?(<svg.*?</svg>)', html, re.S).group(1)
    for name, svg in (("tag", tag), ("magnifier", lens)):
        colours = set(re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', svg)) - {"#2B1A08"}
        assert colours, name
        for c in colours:
            assert _contrast(c, BACKING) >= 3.0, (name, c, round(_contrast(c, BACKING), 2))
