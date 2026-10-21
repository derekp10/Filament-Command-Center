"""Each "📷 Scan to …" QR wears its button's colour (Derek, 2026-10-21).

"The LOAD QR's border and caption must match its amber 'Load it instead'
button, as Store's (cyan) and Cancel's (grey) already match theirs, so it's
clear at a glance what QR code matches the button." Hermetic: the real
inv_core.js / inv_cmd.js under node's `vm` (the stub DOM of
test_core1_return_ejectall_js.py), no browser, no container, so it runs
under --offline. The page-level proof, by computed colour on every QR
question (the slot picker's Swap panel and the Quick-Swap confirm included),
is test_text_size_guard.py::test_qr_codes_take_their_buttons_colour.

A QR cell is read from the HTML the helper writes: the last `border:2px solid`
before a "📷 …" caption is that QR card's border, and the caption's `color` its
caption colour, so the check reads any version of the row.

HEAD proof (dev 6e6bdd4 / c7dafaa, before the change; a throwaway worktree
with only this file copied in): all 7 RED. The idle question's Load QR was the
info blue #4fa2c9 (the Store QR's colour) and the printing one orange #ff8800,
both under an amber #ffc107 button, as was Continue Anyway's; a store-only
question's Store QR turned orange while printing; "Record it as coming from…"
drew its grey No box button's QR blue; the helper had no per-QR tones.
"""
from __future__ import annotations

import json
import re

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

# The colour each QR wears, by the Bootstrap variant of the button it stands
# for: (card border, caption). Amber is btn-warning's own #ffc107.
TONES = {
    "warning": ("#ffc107", "#ffc107"),
    "info": ("#4fa2c9", "#8fd3f0"),
    "secondary": ("#6c757d", "#adb5bd"),
    "light": ("#dee2e6", "#dee2e6"),
    "dark": ("#495057", "#f8f9fa"),
}

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
// Every QR row the helper appended, as HTML (the stub's appendChild keeps it).
const rowsUnder = (el) => (el.children || []).filter((c) => String(c.className) === 'fcc-confirm-qr-row')
  .map((c) => c.innerHTML);
"""


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def _qr_cells(row_html: str) -> list:
    """[(caption, border, caption colour)] in row order."""
    cells = []
    for m in re.finditer(r"color:\s*([^;\"]+);[^>]*>\s*📷\s*([^<]+?)\s*<", row_html):
        before = row_html[:m.start()]
        borders = re.findall(r"border:\s*2px solid\s*([^;\"]+);", before)
        cells.append((m.group(2), borders[-1].strip().lower() if borders else None, m.group(1).strip().lower()))
    return cells


def _variant(html: str, cls: str) -> str:
    """The Bootstrap variant of the button carrying class `cls` in `html`."""
    m = re.search(r'class="([^"]*\b' + re.escape(cls) + r'\b[^"]*)"', html)
    assert m, f"no button .{cls}"
    v = re.search(r"\bbtn-(?:outline-)?(warning|info|secondary|light|dark|danger|success|primary)\b", m.group(1))
    return v.group(1) if v else ""


def _check(cells, expected):
    """`expected`: [(caption, button variant)] in row order."""
    assert [c[0] for c in cells] == [e[0] for e in expected], cells
    wrong = []
    for (caption, border, colour), (_, variant) in zip(cells, expected):
        if (border, colour) != TONES[variant]:
            wrong.append(f"the {caption!r} QR is border {border} / caption {colour}; "
                         f"its button is btn-{variant} {TONES[variant]}")
    assert not wrong, "\n".join(wrong)


QUESTION = """
window.confirmActivePrint(__OPTS__);
const m = lastMount();
return { content: m.opts.content, rows: rowsUnder(m.el) };
"""


def _question(tmp_path, opts_js):
    return _run(tmp_path, ["inv_core.js"], QUESTION.replace("__OPTS__", opts_js))


def test_the_idle_questions_load_qr_is_amber_like_its_button(tmp_path):
    """The case Derek saw: Load it instead is amber, its QR was the Store QR's blue."""
    res = _question(tmp_path, "{ title: 'Load #57 onto XL-1?', msg: 'm', printing: false,"
                              " onConfirm() {}, onCancel() {}, onStore() {} }")
    h = res["content"]
    assert _variant(h, "fcc-apc-yes") == "warning" and _variant(h, "fcc-apc-store") == "info"
    assert _variant(h, "fcc-apc-no") == "secondary"
    _check(_qr_cells(res["rows"][0]), [("Scan to Load", "warning"), ("Scan to Store", "info"),
                                       ("Scan to Cancel", "secondary")])


def test_the_printing_questions_load_qr_is_amber_too(tmp_path):
    res = _question(tmp_path, "{ title: 'Load #57 onto XL-1?', msg: 'm', printing: true,"
                              " onConfirm() {}, onCancel() {}, onStore() {} }")
    assert _variant(res["content"], "fcc-apc-yes") == "warning"
    _check(_qr_cells(res["rows"][0]), [("Scan to Load", "warning"), ("Scan to Store", "info"),
                                       ("Scan to Cancel", "secondary")])


def test_continue_anyway_and_its_qr_are_both_amber(tmp_path):
    res = _question(tmp_path, "{ activePrint: { printer_name: 'XL', state: 'PRINTING', toolhead: 'XL-1' },"
                              " msg: 'm', onConfirm() {}, onCancel() {} }")
    assert _variant(res["content"], "fcc-apc-yes") == "warning"
    _check(_qr_cells(res["rows"][0]), [("Scan to Confirm", "warning"), ("Scan to Cancel", "secondary")])


def test_a_store_only_questions_qr_is_cyan_like_just_store_it(tmp_path):
    """With no Load, the first QR stores: it wears the Store button's cyan, also
    while printing (it used to turn orange)."""
    for printing in ("false", "true"):
        res = _question(tmp_path, "{ title: 'Store #57 in LR-MDB-1 slot 1?', msg: 'm', noLoad: true,"
                                  " printing: " + printing + ", onConfirm() {}, onCancel() {}, onStore() {} }")
        assert "fcc-apc-yes" not in res["content"] and _variant(res["content"], "fcc-apc-store") == "info"
        _check(_qr_cells(res["rows"][0]), [("Scan to Store", "info"), ("Scan to Cancel", "secondary")])


def test_the_helper_gives_each_qr_the_tone_it_is_asked_for(tmp_path):
    """attachConfirmQRs: confirmTone / storeTone / cancelTone name the button's
    variant; without them the confirm QR follows the theme, the store QR is
    cyan and the cancel QR grey. Captions are label size."""
    res = _run(tmp_path, ["inv_core.js"], """
const host = document.createElement('div');
window.attachConfirmQRs({ host, onConfirm() {}, onCancel() {}, onStore() {},
  confirmTone: 'info', storeTone: 'secondary', cancelTone: 'light' });
window.attachConfirmQRs({ host, onConfirm() {}, onCancel() {}, cancelTone: 'dark', theme: 'warning' });
window.attachConfirmQRs({ host, onConfirm() {}, onCancel() {}, onStore() {}, theme: 'info' });
return { rows: host.children.map((c) => c.innerHTML) };
""")
    rows = res["rows"]
    _check(_qr_cells(rows[0]), [("Scan to Confirm", "info"), ("Scan to Store", "secondary"),
                                ("Scan to Cancel", "light")])
    _check(_qr_cells(rows[1]), [("Scan to Confirm", "warning"), ("Scan to Cancel", "dark")])
    _check(_qr_cells(rows[2]), [("Scan to Confirm", "info"), ("Scan to Store", "info"),
                                ("Scan to Cancel", "secondary")])
    for row in rows:
        assert row.count("font-size:var(--fcc-fs-label)") == len(_qr_cells(row)), row


def test_record_source_codes_wear_their_buttons_colours(tmp_path):
    """"Record it as coming from…": the free slot is cyan (btn-info), No box
    grey (btn-secondary) and Cancel dark (btn-dark); its No box QR was blue."""
    res = _run(tmp_path, ["inv_core.js", "ui_builder.js", "inv_cmd.js"], """
state.allLocations = [];
const out = {};
for (const [key, feeds] of [
    ['one', [{ box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }]],
    ['two', [{ box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '2', free: true }]]]) {
  _askRecordSource({ head: 'XL-1', spool_location: '', feeds }, 57, null);
  const m = lastMount();
  out[key] = { content: m.opts.content, rows: rowsUnder(m.el.querySelector('.fcc-rs-panel')) };
}
return out;
""")
    one, two = res["one"], res["two"]
    assert _variant(one["content"], "fcc-rs-opt") == "info"
    assert _variant(one["content"], "fcc-rs-none") == "secondary" and _variant(one["content"], "fcc-rs-cancel") == "dark"
    _check(_qr_cells(one["rows"][0]), [("Scan: LR-MDB-1 slot 1", "info"), ("Scan: No box", "secondary"),
                                       ("Scan to go Back", "dark")])
    _check(_qr_cells(two["rows"][0]), [("Scan: No box", "secondary"), ("Scan to go Back", "dark")])


def test_the_tones_are_published_for_the_page(tmp_path):
    """window.FCC_QR_TONES is the one palette (the browser test reads it)."""
    res = _run(tmp_path, ["inv_core.js"], "return { tones: window.FCC_QR_TONES || null };")
    got = {k: (v["border"].lower(), v["caption"].lower()) for k, v in (res["tones"] or {}).items() if k in TONES}
    assert got == TONES, json.dumps(res["tones"])
