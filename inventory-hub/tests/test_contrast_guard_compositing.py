"""The contrast guard judges text against its COMPOSITED background.

2026-09-13 sweep triage, item 1. `assert_contrast` used to take the first
ancestor background with alpha > 0.01 and treat its RGB as solid. The
printer-status PRINTING chip (#4ade80 text on rgba(16,185,129,0.18)) therefore
scored 1.46:1, although over the black dashboard it renders at ~9.7:1, so both
test_contrast_guard printer-status tests went red whenever a sweep overlapped a
real print. PAUSED, ATTENTION and IDLE were false reds the same way; OFFLINE
was the only state that passed.

Hermetic, and it RUNS under --offline: `isolated_page` is a private chromium
with no route to any network, the markup comes from set_content, and the
real static/css/global.css is read from disk. Nothing reaches the container.

On the pre-fix guard: the chip test reports four chips (PRINTING 1.46, PAUSED
1.32, ATTENTION 1.36, IDLE 1.0), the stacking and default-ground tests report
the bare translucent colour as the background, and the mixed-root test also
flags the bright chip.

Group 45.3 (2026-10-13) composites the FOREGROUND the same way: translucent
text is painted onto its composited background before it is scored. Before
that, the faint-text test's 2.24:1 pair scored 18.36:1 and passed. The OFFLINE
chip's text went from alpha 0.45 (4.41:1 as painted) to 0.50 (5.28:1; filed as 5.29) with it.

Group 58's review reads a computed `filter: brightness(n)`. Before that a filter was
invisible to the guard: the audit tile's whole hover is one, so a brightness(40) tile,
white on white, scored as its unlit colours and passed. The cases here are each held
to the pixels Chromium paints, so the guard's model can't drift from the browser's.
"""
from __future__ import annotations

import io
import os

import pytest
from PIL import Image

import conftest

GLOBAL_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "css", "global.css")
STATES = ("printing", "paused", "idle", "attention", "offline")


def _printer_status_widget_html() -> str:
    """The widget's expanded rows as inv_printer_status.js renders them
    (_renderRow + _renderStateBadge: the name, then the info line with the
    badge in its slot, 2026-10-24), plus the collapsed-strip chip variant."""
    rows = []
    for s in STATES:
        rows.append(f"""
          <div class="fcc-ps-row" data-printer="FCC Test {s}">
            <div class="fcc-ps-reorder-stack"></div>
            <div class="fcc-ps-name text-info fw-bold" title="FCC Test {s}">FCC Test {s}</div>
            <div class="fcc-ps-info">
              <span class="fcc-ps-state-slot"><span class="fcc-ps-state fcc-ps-state-{s}">{s.upper()}</span></span>
              <span class="fcc-ps-count"></span>
              <span class="fcc-ps-state fcc-ps-state-chip fcc-ps-state-{s}">{s.upper()}</span>
            </div>
            <div class="fcc-ps-toolheads"></div>
          </div>""")
    return (f'<div id="printer-status-widget" class="fcc-ps-widget">'
            f'<div class="fcc-ps-body">{"".join(rows)}</div></div>')


def test_translucent_printer_state_chips_pass_over_the_dark_dashboard(isolated_page, assert_contrast):
    page = isolated_page
    with open(GLOBAL_CSS, encoding="utf-8") as fh:
        css = fh.read()
    page.set_content(f"<style>{css}</style>{_printer_status_widget_html()}")

    # Preconditions: the real stylesheet applied, and the chips really are translucent tints.
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 0, 0)"
    assert page.evaluate(
        "getComputedStyle(document.querySelector('.fcc-ps-state-printing')).backgroundColor"
    ) == "rgba(16, 185, 129, 0.18)"

    widget = page.locator("#printer-status-widget")
    offenders = conftest.contrast_offenders(widget)
    assert offenders == [], f"translucent chip tints were judged as solid colours: {offenders}"
    assert_contrast(widget)   # the fixture the E2E tests use agrees


def test_stacked_translucent_layers_composite_bottom_up_onto_the_nearest_opaque_ancestor(isolated_page):
    """white@0.5 over the opaque black panel = 127.5 grey; red@0.5 over that =
    (191.25, 63.75, 63.75). The white page beyond the black panel is hidden by it."""
    page = isolated_page
    page.set_content("""
      <style>html, body { background: #000; margin: 0; font: 16px sans-serif; }</style>
      <div id="root" style="background: #ffffff; padding: 8px">
        <div style="background: #000000; padding: 8px">
          <div style="background: rgba(255, 255, 255, 0.5); padding: 8px">
            <div style="background: rgba(255, 0, 0, 0.5); padding: 8px">
              <span id="probe" style="color: rgb(191, 64, 64)">probe</span>
            </div>
          </div>
        </div>
      </div>""")
    offenders = conftest.contrast_offenders(page.locator("#root"))
    assert [o["id"] for o in offenders] == ["probe"], offenders
    assert offenders[0]["bg"] == "rgb(191, 64, 64)", offenders[0]
    assert offenders[0]["bgLayers"] == 2, offenders[0]
    assert offenders[0]["ratio"] == 1.0, offenders[0]


@pytest.mark.parametrize("html_bg, expected_bg", [
    ("transparent", "rgb(137, 137, 137)"),   # nothing opaque anywhere: default dark ground (18, 18, 18)
    ("#ffffff", "rgb(255, 255, 255)"),       # an opaque <html> background is the ground
])
def test_with_no_opaque_ancestor_the_ground_is_html_then_the_default_dark(isolated_page, html_bg, expected_bg):
    page = isolated_page
    page.set_content(f"""
      <style>html {{ background: {html_bg}; }} body {{ background: transparent; margin: 0; }}</style>
      <div id="root" style="background: rgba(255, 255, 255, 0.5); padding: 8px">
        <span id="probe" style="color: rgb(137, 137, 137)">probe</span>
      </div>""")
    offenders = conftest.contrast_offenders(page.locator("#root"))
    assert [o["id"] for o in offenders] == ["probe"], offenders
    assert offenders[0]["bg"] == expected_bg, offenders[0]


def test_genuinely_low_contrast_text_is_still_reported(isolated_page, assert_contrast):
    """Compositing must not hide real offenders, on an opaque or a tinted ground."""
    page = isolated_page
    page.set_content("""
      <style>html, body { background: #000; margin: 0; font: 16px sans-serif; }</style>
      <div id="root" style="background: #222222; padding: 8px">
        <span id="dim-opaque" style="color: #444444">dim on the opaque panel</span>
        <span id="dim-tint" style="background: rgba(255, 255, 255, 0.1); color: #3a3a3a">dim on a tint</span>
        <span id="bright-tint" style="background: rgba(16, 185, 129, 0.18); color: #4ade80">bright on a tint</span>
      </div>""")
    root = page.locator("#root")
    offenders = conftest.contrast_offenders(root)
    assert sorted(o["id"] for o in offenders) == ["dim-opaque", "dim-tint"], offenders

    with pytest.raises(AssertionError) as exc:
        assert_contrast(root)
    msg = str(exc.value)
    assert "2 element(s)" in msg and "dim-opaque" in msg and "dim-tint" in msg, msg
    assert "composited from 1 translucent layer(s)" in msg, msg
    assert "bright-tint" not in msg, msg


def test_translucent_text_is_scored_as_painted_onto_its_background(isolated_page, assert_contrast):
    """Group 45.3. White text at 25% on a white 8% tint over black paints as
    rgb(79, 79, 79) on rgb(20, 20, 20): 2.24:1. Scored at full strength, as the
    guard used to, it read as 18.36:1 and passed."""
    page = isolated_page
    page.set_content("""
      <style>html, body { background: #000; margin: 0; font: 16px sans-serif; }</style>
      <div id="root" style="background: rgba(255, 255, 255, 0.08); padding: 8px">
        <span id="faint" style="color: rgba(255, 255, 255, 0.25)">faint</span>
        <span id="solid" style="color: #ffffff">solid</span>
      </div>""")
    root = page.locator("#root")
    offenders = conftest.contrast_offenders(root)
    assert [o["id"] for o in offenders] == ["faint"], offenders
    faint = offenders[0]
    assert faint["ratio"] == 2.24, faint
    assert faint["fg"] == "rgb(79, 79, 79)" and faint["bg"] == "rgb(20, 20, 20)", faint
    assert faint["fgAlpha"] == 0.25, faint

    with pytest.raises(AssertionError) as exc:
        assert_contrast(root)
    assert "(text at alpha 0.25, as painted)" in str(exc.value), str(exc.value)


def test_the_offline_chip_passes_as_painted_and_stays_dimmer_than_idle(isolated_page):
    """The CSS half of 45.3: OFFLINE's text alpha 0.50 paints at 5.28:1 over
    the dashboard (0.45 was 4.41:1, under AA). It must stay the dimmest state."""
    page = isolated_page
    with open(GLOBAL_CSS, encoding="utf-8") as fh:
        css = fh.read()
    page.set_content(f"<style>{css}</style>{_printer_status_widget_html()}")
    alpha = page.evaluate("""() => {
        const a = s => parseFloat(getComputedStyle(document.querySelector('.fcc-ps-state-' + s))
                                  .color.split(',')[3]);
        return { offline: a('offline'), idle: a('idle') };
    }""")
    assert alpha == {"offline": 0.5, "idle": 0.6}, alpha
    widget = page.locator("#printer-status-widget")
    assert conftest.contrast_offenders(widget, min_ratio=5.25) == [], "OFFLINE paints under 5.28:1"
    assert [o["text"] for o in conftest.contrast_offenders(widget, min_ratio=5.35)
            if "OFFLINE" in o["text"]] == ["OFFLINE", "OFFLINE"], "OFFLINE got brighter than 0.50"


# --- a computed filter: brightness(n) ---------------------------------------------------

# `#probe` holds the text. Its top-left corner shows the background behind the text, and
# its `.ink` block is painted in the text's own colour, so both can be read off a real
# screenshot: (markup around the probe, the probe's own style, painted text, painted back).
_PROBE = ('<div id="probe" style="width: 120px; padding: 12px; font: 16px sans-serif; {style}">probe'
          '<div class="ink" style="width: 16px; height: 16px; background: currentColor"></div></div>')
FILTER_CASES = {
    "no-filter": ("{probe}", "background: #202020; color: #404040", 64, 32),
    "a-filter-function-it-doesnt-model": ("{probe}", "filter: saturate(0.5); background: #202020; color: #404040", 64, 32),
    "on-the-element-and-its-own-background": ("{probe}", "filter: brightness(2); background: #202020; color: #404040", 128, 64),
    "a-percentage": ("{probe}", "filter: brightness(50%); background: #404040; color: #808080", 64, 32),
    "two-of-them": ("{probe}", "filter: brightness(2) brightness(1.5); background: #202020; color: #404040", 192, 96),
    "on-the-text-never-the-background-behind-it": (
        '<div style="background: #202020">{probe}</div>', "filter: brightness(2); color: #404040", 128, 32),
    "on-an-ancestor-reaches-all-it-holds": (
        '<div style="filter: brightness(2)"><div style="background: #202020">{probe}</div></div>',
        "color: #404040", 128, 64),
    "on-a-layer-between-the-two": (
        '<div style="background: #202020"><div style="filter: brightness(2); background: #202020">'
        '<div style="background: rgba(64, 64, 64, 0.5)">{probe}</div></div></div>', "color: #404040", 128, 96),
    "a-translucent-layer-over-an-unlit-ground": (
        '<div style="background: #202020">{probe}</div>',
        "filter: brightness(2); background: rgba(64, 64, 64, 0.5); color: #404040", 128, 80),
    "translucent-text": (
        '<div style="background: #202020">{probe}</div>',
        "filter: brightness(2); color: rgba(64, 64, 64, 0.5)", 80, 32),
    "clamped-at-255": ("{probe}", "filter: brightness(40); background: #1a1a1a; color: #ffffff", 255, 255),
    "clamped-at-each-step": (
        '<div style="filter: brightness(0.5)">{probe}</div>',
        "filter: brightness(40); background: #1a1a1a; color: #808080", 128, 128),
}


def _painted(page, selector, x=2, y=2):
    """What the browser really painted at a point of `selector`: a grey level."""
    box = page.locator(selector).bounding_box()
    png = page.screenshot(clip={"x": box["x"] + x, "y": box["y"] + y, "width": 1, "height": 1})
    r, g, b = Image.open(io.BytesIO(png)).convert("RGB").getpixel((0, 0))
    assert r == g == b, (r, g, b)
    return r


@pytest.mark.parametrize("markup, style, text, back", FILTER_CASES.values(), ids=FILTER_CASES.keys())
def test_a_brightness_filter_is_scored_as_the_browser_paints_it(isolated_page, markup, style, text, back):
    """RED before the guard read `filter`: every case but the first two scored its unlit
    colours. Each `fg` and `bg` is the guard's; what it is held to is the screenshot."""
    page = isolated_page
    page.set_content('<style>html, body { background: #000; margin: 0; }</style><div id="root">'
                     + markup.replace("{probe}", _PROBE.format(style=style)) + "</div>")
    assert abs(_painted(page, "#probe") - back) <= 1          # the expectation is the browser's
    assert abs(_painted(page, "#probe .ink", 8, 8) - text) <= 1
    offender = next(o for o in conftest.contrast_offenders(page.locator("#root"), min_ratio=100) if o["id"] == "probe")
    assert offender["fg"] == f"rgb({text}, {text}, {text})", offender
    assert offender["bg"] == f"rgb({back}, {back}, {back})", offender


def test_a_filter_that_washes_a_tile_out_is_an_offender_and_the_real_one_isnt(isolated_page):
    """Findings 14 and 43, on a tile as the audit panel draws it under the real
    global.css. RED before the guard read `filter`: brightness(40) paints white on white
    and scored as the unlit tile, with nothing reported.
    test_audit_panel_58_js has it on the real panel."""
    page = isolated_page
    with open(GLOBAL_CSS, encoding="utf-8") as fh:
        css = fh.read()
    page.set_content(f"""<style>{css}</style>
      <div id="root" style="background: #000; padding: 8px">
        <button type="button" class="fcc-audit-tile-box fcc-audit-tile" style="background: #1a1a1a; border: 1px solid #555">
          <span id="name" style="color: #fff">#99 Some Brand PLA (Red)</span>
          <span id="word" class="fcc-audit-tile-word">found, no label read</span>
        </button>
      </div>""")
    page.hover("button.fcc-audit-tile")
    assert page.evaluate("getComputedStyle(document.querySelector('button.fcc-audit-tile')).filter") == "brightness(1.3)"
    root = page.locator("#root")
    assert conftest.contrast_offenders(root) == []
    page.add_style_tag(content="button.fcc-audit-tile:hover { filter: brightness(40); }")
    offenders = conftest.contrast_offenders(root)
    assert sorted(o["id"] for o in offenders) == ["name", "word"], offenders
    assert all(o["bg"] == "rgb(255, 255, 255)" and o["ratio"] < 1.5 for o in offenders), offenders
