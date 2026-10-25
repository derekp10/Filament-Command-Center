""""Record it as coming from…": what a slot and No box mean, and No box's own
colour (Derek, 2026-10-23).

"QR Codes look good. I think no box color is a bit close to the cancel color
that it might be a little confusing ... Also return and eject sends it back
there is a bit ambiguous. back where?"

The dialog (inv_cmd.js _askRecordSource) asks which slot feeding the head a
spool put on it from no box (Unassigned, or another head) should be recorded
as coming from. It said "Which slot feeding XL-1 is its home? Return and eject
send it back there.": the spool was never in that slot, so "back there" read
as nowhere. What the answers do later (CLAUDE.md, routes_bindings.py
_return_plan, logic.py _eject_destination):
  - a slot: ↩️ Return and ⏏️ Eject put the spool in that slot;
  - No box: nothing is recorded, so Return uses the only free slot feeding the
    head (when no single-slot box is attached to it) or asks which slot, and
    Eject asks, then leaves the spool Unassigned (Group 41.8).

Hermetic: the real inv_core.js / inv_cmd.js under node's `vm` (the stub DOM of
test_core1_return_ejectall_js.py) and a read of global.css; no browser, no
container, so it runs under --offline. Pinned here:
  - the message, word for word, in every shape (one free slot pre-selected,
    several free, the wizard's "the new spool"): it names the spool and the
    head (escaped), says a slot means Return and Eject put the spool IN that
    slot later, never "back", and what No box means;
  - No box is a .btn-purple, and global.css's .btn-purple is Bootstrap's
    purple with white text that reads (WCAG AA, 4.5:1) in every state, a
    colour far from Cancel's dark grey, the slot's cyan, the old grey and the
    amber Load (CIE76, as test_qr_button_tones_js.py);
  - its QR's border is the button's own purple and its caption a purple that
    reads on the dialog (#1e1e1e).
The QR tones as drawn: test_qr_button_tones_js.py. On the page:
test_contrast_guard.py::test_qr_questions_are_readable (computed colours),
test_text_size_guard.py::test_qr_codes_take_their_buttons_colour and
test_qr_under_buttons_e2e.py (each QR still under its button, the longer
message on a phone included).

RED on 15ce8f4 (this file and test_qr_button_tones_js.py, whose ΔE helper it
uses, copied into a throwaway worktree): all 4 (the old message; a grey No
box, no .btn-purple in global.css, no purple QR tone).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_qr_button_tones_js import OWN_COLOUR_DE, _delta_e

GLOBAL_CSS = Path(__file__).resolve().parents[1] / "static" / "css" / "global.css"

# The dialog's own background (inv_cmd.js .fcc-rs-panel).
PANEL_BG = "#1e1e1e"

# Bootstrap 5.3.0's button colours the purple must stand apart from: Cancel
# (btn-dark), the slot (btn-info), the move questions' Load (btn-warning) and
# No box's old grey (btn-secondary).
NEIGHBOURS = {"btn-dark": "#212529", "btn-info": "#0dcaf0", "btn-warning": "#ffc107", "btn-secondary": "#6c757d"}


def _message(who: str, head: str) -> str:
    return (f"{who} isn't coming from a box, so pick a slot feeding {head}: ↩️ Return and ⏏️ Eject will put it in "
            "that slot later. With No box, Return will ask which slot (or use the only free one), and Eject will "
            "leave it Unassigned.")


PRELUDE = r"""
const __mounts = [];
const __stubMount = window.mountOverlay;
window.mountOverlay = (opts) => {
  const h = __stubMount(opts);
  h.panel = h.element;
  __mounts.push({ opts, el: h.element });
  return h;
};
const lastMount = () => __mounts[__mounts.length - 1];
const between = (html, cls) => {
  const m = new RegExp('<div class="' + cls + '"[^>]*>([\\s\\S]*?)</div>').exec(html);
  return m ? m[1] : null;
};
"""

SHAPES = r"""
state.allLocations = [];
const out = {};
for (const [key, head, sid, feeds] of [
    ['one free', 'XL-1', 57, [{ box: 'LR-MDB-1', slot: '1', free: true },
                              { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }]],
    ['two free', 'XL-1', 57, [{ box: 'LR-MDB-1', slot: '1', free: true }, { box: 'PM-DB-XL-L', slot: '1', free: true }]],
    ['the new spool', 'XL-3', null, [{ box: 'LR-MDB-1', slot: '3', free: true }]],
    ['an odd head id', 'XL<b>&1', 7, [{ box: 'LR-MDB-1', slot: '1', free: true }]]]) {
  _askRecordSource({ head, spool_location: '', feeds }, sid, null);
  const html = lastMount().opts.content;
  const none = /<button[^>]*class="([^"]*\bfcc-rs-none\b[^"]*)"/.exec(html);
  out[key] = { msg: between(html, 'fcc-rs-msg'), title: between(html, 'fcc-rs-title'),
               noneClass: none ? none[1] : null };
}
out.tones = window.FCC_QR_TONES || null;
return out;
"""


def _run(tmp_path, body):
    res = run_js(tmp_path, ["inv_core.js", "ui_builder.js", "inv_cmd.js"], PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _contrast(a: str, b: str) -> float:
    def lum(hex_):
        h = hex_.strip().lstrip("#")
        lin = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
               for c in (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _hex(value: str) -> str:
    """'#fff' / '#FFFFFF' -> '#ffffff'."""
    h = value.strip().lower().lstrip("#")
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h)


def _btn_purple_vars() -> dict:
    css = GLOBAL_CSS.read_text(encoding="utf-8")
    m = re.search(r"(?m)^\.btn-purple\s*\{([^}]*)\}", css)
    assert m, "global.css has no .btn-purple rule"
    return dict(re.findall(r"--bs-btn-([a-z-]+)\s*:\s*([^;]+);", m.group(1)))


def test_the_message_says_where_return_and_eject_put_it(tmp_path):
    """Word for word in every shape: the spool and the head named (the head
    escaped), a slot means Return and Eject put the spool IN that slot later,
    and what No box means. Never "back": the spool was never in the slot."""
    res = _run(tmp_path, SHAPES)
    want = {
        "one free": _message("#57", "XL-1"),
        "two free": _message("#57", "XL-1"),
        "the new spool": _message("The new spool", "XL-3"),
        "an odd head id": _message("#7", "XL&lt;b&gt;&amp;1"),
    }
    got = {k: res[k]["msg"] for k in want}
    assert got == want, json.dumps(got, ensure_ascii=False, indent=1)
    for key in want:
        assert not re.search(r"\bback\b", res[key]["msg"], re.I), (key, res[key]["msg"])
    # The title is the same question as before.
    assert res["one free"]["title"] == "🔗 Record #57 as coming from…", res["one free"]["title"]
    assert res["the new spool"]["title"] == "🔗 Record the new spool as coming from…", res["the new spool"]["title"]


def test_no_box_is_the_purple_button_in_every_shape(tmp_path):
    res = _run(tmp_path, SHAPES)
    for key in ("one free", "two free", "the new spool", "an odd head id"):
        classes = (res[key]["noneClass"] or "").split()
        assert "btn-purple" in classes and "btn-secondary" not in classes, (key, classes)


def test_btn_purple_is_bootstraps_purple_and_reads_in_every_state(tmp_path):
    """global.css: white on Bootstrap's purple #6f42c1 (6.5:1), and on its
    hover / active / disabled shades; a colour far from Cancel's, the slot's,
    the amber Load's and the old grey's."""
    v = _btn_purple_vars()
    assert _hex(v["bg"]) == "#6f42c1" and _hex(v["border-color"]) == "#6f42c1", v
    low = []
    for state, fg, bg in (("normal", "color", "bg"), ("hover", "hover-color", "hover-bg"),
                          ("active", "active-color", "active-bg"), ("disabled", "disabled-color", "disabled-bg")):
        r = _contrast(_hex(v[fg]), _hex(v[bg]))
        if r < 4.5:
            low.append(f"{state}: {v[fg]} on {v[bg]} is {r:.2f}:1")
    assert not low, low
    near = {name: round(_delta_e(_hex(v["bg"]), hexv), 1) for name, hexv in NEIGHBOURS.items()
            if _delta_e(_hex(v["bg"]), hexv) < OWN_COLOUR_DE}
    assert not near, f"btn-purple is too close to {near}"


def test_its_qr_wears_the_buttons_purple(tmp_path):
    """The purple QR tone: the card's border is the button's own purple, the
    caption a purple that reads on the dialog (4.5:1 on #1e1e1e)."""
    tones = _run(tmp_path, SHAPES)["tones"]
    assert tones and "purple" in tones, tones
    purple = tones["purple"]
    assert _hex(purple["border"]) == _hex(_btn_purple_vars()["bg"]), purple
    assert _contrast(_hex(purple["caption"]), PANEL_BG) >= 4.5, purple
