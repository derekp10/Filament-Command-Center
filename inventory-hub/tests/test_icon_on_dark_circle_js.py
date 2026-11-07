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
0.8 px (0.75 until 2026-11-05: WEIGHT_PX), and fills at least half the circle's width. On a
real DOM, hermetic: the REAL
inv_cmd.js dock and tile (test_audit_panel_58_js's `audit`, page61's modules) and the REAL Load
report button from modals_config.html, with global.css and Bootstrap 5.3's button rules, in an
isolated browser (no network), so it runs under --offline. The real dashboard's twin is
test_audit_panel_look_58_e2e.py's. RED on 76fb961 (27 of 31; the two pins pass): the backing
held the emoji, not a drawing, and the 🔎's ink, its box within half a pixel of the middle (as
P5 measured it), had its weight 0.6 to 1.25 px up-right of it at every position.

Derek's pick of 2026-11-05, (c) of four: "Slanted, no loop: the body itself centred". The tag
had an orange ring of string at its point, and its body sat low-left of the middle so that body
and ring together were balanced; now it is the body and its hole alone, still slanted as the
emoji, the body with its stroke centred on (16, 16) in the drawing's own units, and its weight
0.4 of a unit up-right of it (the hole is dark). Two tests read the drawing itself: what it is
made of, and where its body sits, measured at 40 px a unit. Both RED on 96d488b (the ring was
there, and the body alone sat 1.16 units left and 1.16 down of the middle). The screen tests
above hold the tag to the same limits as before; only their "not a speck" floor is the tag's own
now (PIN UPDATED DELIBERATELY: with no ring it spans 15 of the circle's 32 units, under half).

Derek's look at that picture, 2026-11-05: "the circle isn't center in the button, its more on the
left side" (a marked tile's 🏷️), and Needs a label's circle "isn't center to the button, it is to
the text, but it's more on the lower end" ("just looks a little sloppy in the shots"). The drawing
was centred in its circle; the circle wasn't in its button. The tests at the end measure that,
from the layout: in the square the circle's box has its middle on the button's content box's,
both ways, within half a pixel; in Needs a label and Load report its middle is on the content
box's top to bottom within half a pixel, the words' too within a pixel, and the space from the
button's edge to its left is the space above it, within a pixel. At 1x and 2x, at each Text size
(Small, Standard, Large, Extra Large). RED on 8a28c5b (24 of 24), in a scratch `git archive`:
the circle sat in the line of words, its middle on their x-height, 2 px under the button's, 9.4
px from Needs a label's edge against 6.3 above it, and the square's centring took the margins
made for words after it, 2.5 px left of its middle. One pin with them: on a phone the circle
stays in Needs a label's line of words, as it was (8 of 8 pass on 8a28c5b). The ink's weight
limit is 0.8 px since (WEIGHT_PX: the SVG is painted at whole CSS pixels at 2x).
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
# The ink's weight, from the circle's middle. PIN UPDATED DELIBERATELY (2026-11-05): 0.75 until
# the circle was centred in its button. At 2x the SVG is painted at whole CSS pixels and its
# circle (a background) at device pixels: a marked tile nudged a quarter pixel at a time at 2x
# Extra Large, the drawing stayed put while its circle moved a device pixel, and no placement of
# the SVG (absolute, in a grid, given a transform of its own) changed that. So where the circle
# lands moves the drawing against it by up to half a CSS pixel, and the square's centred circle
# lands, at 2x Extra Large, where the tag's weight (0.4 of a unit up-right by its drawing)
# measures 0.76 px; the margins it had put it near a whole pixel, by chance.
WEIGHT_PX = 0.8
TAG_LEAST = 0.42                # the tag's width against the circle's: 15 of 32 units, less a pixel
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


def _centred(got, what, least=0.5):
    (bx, by), (wx, wy) = got["box"], got["weight"]
    assert abs(bx) <= BOX_PX and abs(by) <= BOX_PX, (what, got)
    assert abs(wx) <= WEIGHT_PX and abs(wy) <= WEIGHT_PX, (what, got)
    assert got["width"] >= least, (what, got)                # an icon, not a speck


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
    _centred(ink(icons, NEED), f"Needs a label at {size}", TAG_LEAST)
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
    _centred(ink(icons, sel), f"a marked tile's tag at {size}", TAG_LEAST)


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
    _centred(ink(icons, NEED), f"Needs a label nudged {left - 20.0} px", TAG_LEAST)


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


# --- Derek's pick of 2026-11-05, (c): "Slanted, no loop: the body itself centred" ----------

UNIT_PX = 40                    # the drawing measured at 40 px a unit: 1280 px for its 32
UNITS_BOX = 0.05                # its box, from (16, 16), in units


def _tag_markup():
    """TAG_ICON as inv_cmd.js builds it (its string literals joined)."""
    js = (HUB / "static" / "js" / "modules" / "inv_cmd.js").read_text(encoding="utf-8")
    expr = re.search(r"const TAG_ICON = (.*?);\r?\n", js, re.S).group(1)
    return "".join(re.findall(r"'([^']*)'", expr))


def _shapes(markup):
    """Each shape the drawing paints, in order: (its tag, its attributes)."""
    return [(tag, dict(re.findall(r'([\w-]+)="([^"]*)"', attrs)))
            for tag, attrs in re.findall(r"<(path|circle|ellipse|rect|line|polyline|polygon)\b([^>]*)>", markup)]


def test_the_tag_is_its_body_and_its_hole_alone():
    """No ring of string at its point: the body (the emoji's warm yellow in its orange stroke)
    and its dark hole on the tag's axis, slanted as the emoji. RED on 96d488b: a third shape,
    the orange ring, hung at the point."""
    markup = _tag_markup()
    assert '<g transform="rotate(-45 16 16)">' in markup, markup
    shapes = _shapes(markup)
    assert [tag for tag, _ in shapes] == ["path", "circle"], shapes
    body, hole = shapes[0][1], shapes[1][1]
    assert {k: body.get(k) for k in ("fill", "stroke", "stroke-width", "stroke-linejoin")} == {
        "fill": "#FFC83D", "stroke": "#E57C00", "stroke-width": "1.6", "stroke-linejoin": "round"}, body
    assert hole.get("fill") == "#2B1A08" and "stroke" not in hole and hole.get("cy") == "16", hole


def _in_units(page, markup, body_only=False):
    """The drawing painted at UNIT_PX a unit on the backing: its ink's box (every pixel more
    than 48 off the backing in a channel) and its weight (each pixel past 12, by how far),
    as (dx, dy) from (16, 16) in the drawing's units. `body_only` paints its path alone."""
    from PIL import ImageChops
    side = 32 * UNIT_PX
    page.set_content(f"<html><body style='margin:0;background:{BACKING}'>"
                     f"<div id='ico' style='width:{side}px;height:{side}px'>{markup}</div></body></html>")
    page.add_style_tag(content="#ico > svg { display: block; width: 100%; height: 100%; }"
                       + (" #ico circle { display: none; }" if body_only else ""))
    png = page.screenshot(clip={"x": 0, "y": 0, "width": side, "height": side})
    img = Image.open(io.BytesIO(png)).convert("RGB")
    back = tuple(int(BACKING[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = ImageChops.difference(img, Image.new("RGB", img.size, back)).split()
    d = ImageChops.lighter(ImageChops.lighter(r, g), b)
    left, top, right, bottom = d.point(lambda v: 255 if v > 48 else 0).getbbox()
    total = sx = sy = 0.0
    for i, v in enumerate(d.getdata()):
        if v > 12:
            y, x = divmod(i, side)
            total += v
            sx += v * (x + 0.5)
            sy += v * (y + 0.5)
    return {"box": ((left + right) / 2 / UNIT_PX - 16, (top + bottom) / 2 / UNIT_PX - 16),
            "weight": (sx / total / UNIT_PX - 16, sy / total / UNIT_PX - 16)}


def test_the_tags_body_with_its_stroke_is_centred_in_the_drawings_own_units(_isolated_chromium):
    """Derek's (c), "the body itself centred": the body, its stroke included, has its box on
    the circle's middle to 0.05 of a unit on each axis, and so does the whole drawing (the hole
    is inside the body). Its weight lies on the tag's own diagonal, at most half a unit off the
    middle on each axis (0.4 up-right: the hole is dark), well inside the screen tests' 0.8 px.
    RED on 96d488b: the body alone sat 1.16 units left and 1.16 down of the middle, the ring at
    its point balancing it."""
    side = 32 * UNIT_PX
    context = _isolated_chromium.new_context(viewport={"width": side, "height": side}, device_scale_factor=1)
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    try:
        markup = _tag_markup()
        body = _in_units(page, markup, body_only=True)
        assert all(abs(c) <= UNITS_BOX for c in body["box"]), ("the body alone", body)
        whole = _in_units(page, markup)
        assert all(abs(c) <= UNITS_BOX for c in whole["box"]), ("the whole drawing", whole)
        wx, wy = whole["weight"]
        assert abs(wx + wy) <= UNITS_BOX, ("its weight off the tag's diagonal", whole)
        assert abs(wx) <= 0.5 and abs(wy) <= 0.5, ("its weight", whole)
    finally:
        context.close()


# --- Derek's look of 2026-11-05: the circle sits in its button ------------------------------

ALL_SIZES = ["small", "standard", "large", "xlarge"]
MIDDLE_PX = 0.5                 # the circle's middle, from its button's content box's
WORDS_PX = 1.0                  # the words' middle, from the same (the font's own box)
EVEN_PX = 1.0                   # the space to the circle's left, against the space above it

# How the circle `s` sits in its button, from the layout, in CSS px: its box's middle against
# the button's content box's (dx, dy); the space from the button's edge (its border is its
# fill's colour) to the circle's left, top and bottom; and the middle of the words' own boxes
# (each line of text the button draws, the circle's none) against the content box's.
SITS = r"""(s) => { const c = document.querySelector(s); const b = c.closest('button');
    const r = b.getBoundingClientRect(), q = c.getBoundingClientRect(), cs = getComputedStyle(b);
    const n = (k) => parseFloat(cs[k]);
    const box = { left: r.left + n('borderLeftWidth') + n('paddingLeft'), right: r.right - n('borderRightWidth') - n('paddingRight'),
                  top: r.top + n('borderTopWidth') + n('paddingTop'), bottom: r.bottom - n('borderBottomWidth') - n('paddingBottom') };
    const lines = []; const walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT); let node;
    while ((node = walker.nextNode())) {
        if (!node.data.trim() || node.parentElement.closest('.fcc-ico-on-light')) continue;
        const range = document.createRange(); range.selectNodeContents(node);
        lines.push(...Array.from(range.getClientRects()).filter((x) => x.width > 0 && x.height > 0));
    }
    const f = (v) => Math.round(v * 1000) / 1000;
    return { dx: f((q.left + q.right) / 2 - (box.left + box.right) / 2), dy: f((q.top + q.bottom) / 2 - (box.top + box.bottom) / 2),
             left: f(q.left - r.left), top: f(q.top - r.top), bottom: f(r.bottom - q.bottom),
             words: lines.length ? f((Math.min(...lines.map((x) => x.top)) + Math.max(...lines.map((x) => x.bottom))) / 2
                                     - (box.top + box.bottom) / 2) : null,
             right: lines.length ? f(r.right - Math.max(...lines.map((x) => x.right))) : null,
             gap: lines.length ? f(Math.min(...lines.map((x) => x.left)) - q.right) : null,
             button: [f(r.width), f(r.height)], circle: f(q.width) }; }"""


@pytest.mark.parametrize("size", ALL_SIZES)
def test_a_marked_tiles_circle_sits_in_the_middle_of_its_square(icons, size):
    """Derek: "the circle isn't center in the button, its more on the left side". A found
    tile's 🏷️ once marked is a square holding the circle alone: the circle's middle is the
    square's, both ways, within half a pixel. RED on 8a28c5b: the square centred the circle's
    margins, made for words after it (0.3em to its left reaching into a padding, 0.05em to its
    right), so the circle sat 2.4 to 3.1 px left of the middle at every Text size."""
    _text_size(icons, size)
    got = icons.evaluate(SITS, _marked_tile(icons))
    assert abs(got["dx"]) <= MIDDLE_PX and abs(got["dy"]) <= MIDDLE_PX, (size, got)


@pytest.mark.parametrize("size", ALL_SIZES)
@pytest.mark.parametrize("which", ["needs-a-label", "load-report"])
def test_the_circle_sits_centred_top_to_bottom_with_even_space_to_its_left(icons, which, size):
    """Derek, on Needs a label: "it isn't center to the button, it is to the text, but it's more
    on the lower end". In the dock's Needs a label and Settings' Load report the circle's middle
    is the content box's top to bottom, within half a pixel, and the words beside it are
    centred too (their own box, within a pixel: the font's ascent and descent, as in any
    button); the space from the button's edge to the circle's left is the space above it,
    within a pixel. RED on 8a28c5b: the circle sat in the line of words, its middle on their
    x-height (vertical-align: middle), 2 to 2.5 px under the button's; and Needs a label's
    line, centred in its wide button, left 9.4 px to the circle's left against 6.3 above it."""
    sel = NEED if which == "needs-a-label" else _load_report(icons)
    _text_size(icons, size)
    got = icons.evaluate(SITS, sel)
    what = f"{which} at {size}: {got}"
    assert abs(got["dy"]) <= MIDDLE_PX, what
    assert got["words"] is not None and abs(got["words"]) <= WORDS_PX, what
    if which == "load-report":
        # A button as wide as what it holds: the space to the circle's left is the space above it.
        assert abs(got["left"] - got["top"]) <= EVEN_PX, what
    else:
        # The dock's column is wider than what it holds (Derek, 2026-11-06: tighten the gap):
        # the circle and its words are centred together, the space to the circle's left the
        # space to the words' right, and they are one word space apart, as in Load report.
        other = icons.evaluate(SITS, _load_report(icons))
        assert abs(got["left"] - got["right"]) <= EVEN_PX, what
        assert abs(got["gap"] - other["gap"]) <= EVEN_PX, (what, other)


# The phone's dock: how far Needs a label runs out of its column, and whether its circle's
# middle is above the button's (in the first of its lines).
NARROW = r"""() => { const b = document.getElementById('fcc-audit-panel-needlabel'); const col = b.parentElement;
    const r = b.getBoundingClientRect(), k = col.getBoundingClientRect();
    const q = b.querySelector('.fcc-ico-on-light').getBoundingClientRect();
    return { over: Math.max(k.left - r.left, r.right - k.right), high: (q.top + q.bottom) / 2 < (r.top + r.bottom) / 2 - 2,
             button: [r.width, r.height], column: k.width }; }"""


@pytest.mark.parametrize("size", ["standard", "xlarge"])
@pytest.mark.parametrize("width", [390, 360])
def test_on_a_phone_the_circle_stays_in_the_line_of_words(icons, width, size):
    """A pin: on a phone (the narrow dock) Needs a label's words wrap to two lines or three, and
    its circle stays in their line, riding the first, as before 2026-11-05; the button stays in
    its column. Kept beside the words, as on the wide dock, the circle couldn't wrap away from
    "Needs" at Extra Large, and the button ran out of its column, 8.8 px past it at 360 px wide
    (seen while building this)."""
    icons.set_viewport_size({"width": width, "height": 844})
    icons.wait_for_timeout(100)
    _text_size(icons, size)
    got = icons.evaluate(NARROW)
    assert got["high"] is True, (width, size, got)
    assert got["over"] <= 0.5, (width, size, got)
