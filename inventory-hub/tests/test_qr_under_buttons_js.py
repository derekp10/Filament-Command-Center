"""Each "📷 Scan to …" QR sits under its own button (Derek, 2026-10-22).

"It'd be nice if we could get the QR codes to also align under the button they
correspond to. We could add some space between the buttons so they align
better to the QR code, otherwise they are slightly skewed, and not directly
under their button."

Hermetic: the real inv_core.js / inv_cmd.js under node's `vm` (the stub DOM of
test_core1_return_ejectall_js.py), no browser, no container, so it runs under
--offline. What it pins is the wiring the layout rests on:
  - attachConfirmQRs({alignTo}) puts the QR row INTO the buttons' row, marks
    that row .fcc-qr-align with one column per QR (--fcc-qr-cols), and only
    when the browser lays out a subgrid and the row holds exactly one
    <button> per QR; otherwise the row goes into `host` as before;
  - its cleanup gives the buttons their own row back;
  - every move question (confirmActivePrint: the three-way, its printing
    variant, the store-only question, Load it instead / Cancel, the
    active-print yes / no) hands it its buttons' row, holding the buttons in
    QR order;
  - "Record it as coming from…" puts the buttons with a QR (the one free slot,
    No box, Cancel) in that row and the slots without one on a line above,
    in feed order;
  - (review, 2026-10-22) the store button and the record source's slots keep
    each box id and "slot N" whole (window.fccKeepWhole: a span that doesn't
    break; the label's text unchanged), and fccFitQuestion lets them break
    again only where they can't fit the screen, and makes a question taller
    than the window scroll inside itself (only then: a scroller loses the
    screen's sub-pixel text smoothing). RED on c5c9d1f (no spans, no
    helper).
The geometry (each QR's centre under its button's, at every Text size and on
a 412 px phone, nothing sticking out) is test_qr_under_buttons_e2e.py, in a
real browser.

HEAD proof (0c965c7, this file alone in a throwaway worktree at HEAD): all 4
RED. attachConfirmQRs ignored `alignTo` (the row went into `host`, nothing was
marked), confirmActivePrint's buttons row had no class to hand over, and the
record-source dialog drew every slot in one row with No box and Cancel.
"""
from __future__ import annotations

import re

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

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
// A row the helper can align into: real-looking children and a style that
// takes custom properties, as a browser's does.
const styled = (el) => {
  el.style.setProperty = (k, v) => { el.style[k] = String(v); };
  el.style.removeProperty = (k) => { delete el.style[k]; };
  return el;
};
const buttonsRow = (n, extra) => {
  const row = styled(document.createElement('div'));
  for (let i = 0; i < n; i++) row.appendChild(document.createElement('button'));
  if (extra) row.appendChild(document.createElement(extra));
  return row;
};
const where = (row, host, alignTo) => ({
  inAlign: (alignTo.children || []).includes(row), inHost: (host.children || []).includes(row) });
// The helper's own call record, for the dialogs.
const __qrCalls = [];
const __realAttach = window.attachConfirmQRs;
const recordAttach = () => {
  window.attachConfirmQRs = (opts) => { __qrCalls.push(opts); return __realAttach(opts); };
};
"""


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


SUBGRID = "window.CSS = { supports: (p, v) => p === 'grid-template-columns' && v === 'subgrid' };"


def test_the_row_joins_its_buttons_only_when_it_can(tmp_path):
    """One <button> per QR and a browser with subgrid: the row goes into the
    buttons' row, marked with one column per QR, with no flex of its own. No
    subgrid (an old browser), a row that isn't one button per QR, or no
    alignTo at all: the row goes into `host`, as before, nothing marked."""
    res = _run(tmp_path, ["inv_core.js"], """
const out = {};
const cases = [
  ['three', 'sub', 3, null, true], ['two', 'sub', 2, null, false],
  ['no CSS', null, 3, null, true], ['no subgrid', { supports: () => false }, 3, null, true],
  ['too few buttons', 'sub', 2, null, true], ['a div among them', 'sub', 3, 'div', true],
  ['no alignTo', 'sub', -1, null, true]];
for (const [key, css, n, extra, store] of cases) {
  window.CSS = css === 'sub' ? { supports: (p, v) => p === 'grid-template-columns' && v === 'subgrid' } : (css || undefined);
  const host = document.createElement('div');
  const alignTo = n < 0 ? styled(document.createElement('div')) : buttonsRow(n, extra);
  const s = window.attachConfirmQRs({ host, alignTo: n < 0 ? undefined : alignTo, onConfirm() {}, onCancel() {},
                                      onStore: store ? () => {} : undefined });
  const row = (alignTo.children || []).find((c) => c.id === s.sessionId + '-row')
           || (host.children || []).find((c) => c.id === s.sessionId + '-row');
  out[key] = Object.assign(where(row, host, alignTo), {
    marked: alignTo.classList.contains('fcc-qr-align'), cols: alignTo.style['--fcc-qr-cols'] || null,
    rowAligned: row.classList.contains('fcc-qr-aligned'),
    flex: row.style.cssText.replace(/ /g, '').includes('display:flex') });
}
return out;
""")
    for key, cols in (("three", "3"), ("two", "2")):
        assert res[key] == {"inAlign": True, "inHost": False, "marked": True, "cols": cols, "rowAligned": True,
                            "flex": False}, (key, res[key])
    for key in ("no CSS", "no subgrid", "too few buttons", "a div among them", "no alignTo"):
        assert res[key] == {"inAlign": False, "inHost": True, "marked": False, "cols": None, "rowAligned": False,
                            "flex": True}, (key, res[key])


def test_cleanup_gives_the_buttons_their_row_back(tmp_path):
    res = _run(tmp_path, ["inv_core.js"], SUBGRID + """
const host = document.createElement('div');
const alignTo = buttonsRow(2);
const s = window.attachConfirmQRs({ host, alignTo, onConfirm() {}, onCancel() {} });
const before = { marked: alignTo.classList.contains('fcc-qr-align'), cols: alignTo.style['--fcc-qr-cols'] };
s.cleanup();
return { before, after: { marked: alignTo.classList.contains('fcc-qr-align'),
                          cols: alignTo.style['--fcc-qr-cols'] === undefined ? null : alignTo.style['--fcc-qr-cols'],
                          registered: !!window._fccActiveConfirms[s.sessionId] } };
""")
    assert res["before"] == {"marked": True, "cols": "2"}, res
    assert res["after"] == {"marked": False, "cols": None, "registered": False}, res


# The move questions: the button classes in the .fcc-apc-btns row, in order,
# and the QR the helper draws for each (confirm, [store], cancel).
QUESTIONS = {
    "three-way, idle": ("{ title: 'Load #57 onto XL-1?', msg: 'm', printing: false,"
                        " onConfirm() {}, onCancel() {}, onStore() {} }",
                        ["fcc-apc-yes", "fcc-apc-store", "fcc-apc-no"]),
    "three-way, printing": ("{ title: 'Load #57 onto XL-1?', msg: 'm', printing: true,"
                            " onConfirm() {}, onCancel() {}, onStore() {} }",
                            ["fcc-apc-yes", "fcc-apc-store", "fcc-apc-no"]),
    "store only": ("{ title: 'Store #57 in LR-MDB-1 slot 1?', msg: 'm', noLoad: true, printing: false,"
                   " onConfirm() {}, onCancel() {}, onStore() {} }",
                   ["fcc-apc-store", "fcc-apc-no"]),
    "load or cancel": ("{ title: 'Load #42 onto XL-3?', msg: 'm', printing: false, loadLabel: 'Load it instead',"
                       " onConfirm() {}, onCancel() {} }",
                       ["fcc-apc-yes", "fcc-apc-no"]),
    "active-print yes / no": ("{ activePrint: { printer_name: 'XL', state: 'PRINTING', toolhead: 'XL-1' },"
                              " msg: 'm', onConfirm() {}, onCancel() {} }",
                              ["fcc-apc-yes", "fcc-apc-no"]),
}


def _buttons_in(html: str, cls: str) -> list:
    """The buttons of the first <div class="<cls>"> in `html`, in order: each
    as its class list (the buttons hold no <div>, so the first </div> ends it)."""
    m = re.search(r'<div class="' + re.escape(cls) + r'"[^>]*>(.*?)</div>', html, re.S)
    assert m, f"no .{cls} row in: {html[:400]}"
    return re.findall(r'<button\b[^>]*\bclass="([^"]*)"', m.group(1))


def test_every_move_question_hands_its_buttons_row_to_the_qrs(tmp_path):
    body = "recordAttach();\nconst out = {};\n"
    for key, (opts, _) in QUESTIONS.items():
        body += (f"window.confirmActivePrint({opts});\n"
                 f"out[{key!r}] = {{ content: lastMount().opts.content,"
                 f" same: __qrCalls[__qrCalls.length - 1].alignTo === lastMount().el.querySelector('.fcc-apc-btns'),"
                 f" store: typeof __qrCalls[__qrCalls.length - 1].onStore === 'function' }};\n")
    body += "return out;"
    res = _run(tmp_path, ["inv_core.js"], body)
    for key, (_, want) in QUESTIONS.items():
        got = res[key]
        assert got["same"], f"{key}: the QRs were not handed the buttons' row"
        classes = _buttons_in(got["content"], "fcc-apc-btns")
        order = [next(c for c in w.split() if c.startswith("fcc-apc-")) for w in classes]
        assert order == want, (key, order)
        # One button per QR: confirm, store when there is one, cancel.
        assert len(order) == (3 if got["store"] else 2), (key, order, got["store"])


def test_record_source_draws_the_qr_buttons_on_their_own_row(tmp_path):
    """One free slot: [that slot, No box, Cancel] share the QRs' row and a held
    slot sits on the line above. Several free: [No box, Cancel] share it and
    every slot sits above, in feed order. One free slot alone: no line above."""
    res = _run(tmp_path, ["inv_core.js", "ui_builder.js", "inv_cmd.js"], """
recordAttach();
state.allLocations = [];
const out = {};
for (const [key, feeds] of [
    ['free and held', [{ box: 'LR-MDB-1', slot: '1', free: false, claimed_by: 99 }, { box: 'LR-MDB-1', slot: '2', free: true }]],
    ['two free', [{ box: 'LR-MDB-1', slot: '1', free: true }, { box: 'PM-DB-XL-L', slot: '1', free: true },
                  { box: 'LR-MDB-9', slot: '3', free: false, claimed_by: 61 }]],
    ['one free', [{ box: 'LR-MDB-1', slot: '1', free: true }]]]) {
  _askRecordSource({ head: 'XL-1', spool_location: '', feeds }, 57, null);
  const m = lastMount();
  const call = __qrCalls[__qrCalls.length - 1];
  out[key] = { content: m.opts.content, same: call.alignTo === m.el.querySelector('.fcc-rs-btns'),
               store: typeof call.onStore === 'function', initialFocus: m.opts.initialFocus };
}
return out;
""")
    def names(classes):
        return ["none" if "fcc-rs-none" in c else "cancel" if "fcc-rs-cancel" in c else "opt" for c in classes]

    def opt_ids(html, cls):
        m = re.search(r'<div class="' + re.escape(cls) + r'"[^>]*>(.*?)</div>', html, re.S)
        return re.findall(r'data-rs-i="(\d+)"', m.group(1)) if m else []

    fh = res["free and held"]
    assert fh["same"] and fh["store"], fh
    assert names(_buttons_in(fh["content"], "fcc-rs-btns")) == ["opt", "none", "cancel"]
    assert opt_ids(fh["content"], "fcc-rs-btns") == ["1"] and opt_ids(fh["content"], "fcc-rs-slots") == ["0"]
    assert fh["initialFocus"] == '.fcc-rs-opt[data-rs-i="1"]', fh["initialFocus"]

    two = res["two free"]
    assert two["same"] and not two["store"], two
    assert names(_buttons_in(two["content"], "fcc-rs-btns")) == ["none", "cancel"]
    assert opt_ids(two["content"], "fcc-rs-slots") == ["0", "1", "2"]
    assert two["initialFocus"] == ".fcc-rs-none"

    one = res["one free"]
    assert names(_buttons_in(one["content"], "fcc-rs-btns")) == ["opt", "none", "cancel"]
    assert "fcc-rs-slots" not in one["content"]


# --- a box id kept whole (review, 2026-10-22) ----------------------------------
# On a phone the aligned buttons wrap, and a line may break after any hyphen:
# "Just store it in LR-MDB-1 slot 1" read "in LR- / MDB-1 slot / 1", and the
# record source's slot "LR-MDB- / 1 slot 1" (360 px, Extra Large).

def _keep_whole_spans(html: str) -> list:
    return re.findall(r'<span class="fcc-keep-whole">([^<]*)</span>', html)


def _text(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def test_box_ids_and_slots_stay_whole_on_the_buttons(tmp_path):
    """The store button and the record source's slots wrap each box id and
    "slot N" in a span that doesn't break (global.css .fcc-keep-whole); the
    label's text is the same. Ids the escaping touched stay escaped."""
    res = _run(tmp_path, ["inv_core.js", "ui_builder.js", "inv_cmd.js"], """
const out = {};
window.confirmHeadLoad({ answer: { status: 'requires_confirm', confirm_type: 'head_fed', can_store: true,
    spools: [57], title: 'Load #57 onto XL-1?', body: 'b', fed_heads: [{ toolhead: 'XL-1', box: 'PM-DB-XL-L',
    slot: '2', confirm_key: 'XL-1#99' }], active_prints: [] }, box: 'PM-DB-XL-L', onLoad() {}, onStore() {}, onCancel() {} });
out.threeWay = lastMount().opts.content;
state.allLocations = [];
_askRecordSource({ head: 'XL-1', spool_location: '', feeds: [{ box: 'LR-MDB-1', slot: '1', free: true },
    { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }] }, 57, null);
out.recordSource = lastMount().opts.content;
out.escaped = window.fccKeepWhole ? window.fccKeepWhole("Tom&#39;s A-B &amp; <b> slot 12 x-") : null;
return out;
""")
    store = re.search(r'<button[^>]*fcc-apc-store[^>]*>(.*?)</button>', res["threeWay"], re.S).group(1)
    assert _keep_whole_spans(store) == ["PM-DB-XL-L", "slot 2"], store
    assert _text(store) == "Just store it in PM-DB-XL-L slot 2", store
    load = re.search(r'<button[^>]*fcc-apc-yes[^>]*>(.*?)</button>', res["threeWay"], re.S).group(1)
    assert _text(load) == "Load it instead", load
    opts = re.findall(r'<button[^>]*fcc-rs-opt[^>]*>(.*?)</button>', res["recordSource"], re.S)
    assert [_keep_whole_spans(o) for o in opts] == [["LR-MDB-1", "slot 2"], ["LR-MDB-1", "slot 1"]], opts
    assert [_text(o) for o in opts] == ["LR-MDB-1 slot 2holds #99", "LR-MDB-1 slot 1free"], opts
    # Escaped text in, escaped text out: an entity is never split or wrapped.
    assert res["escaped"] == ('Tom&#39;s <span class="fcc-keep-whole">A-B</span> &amp; <b> '
                              '<span class="fcc-keep-whole">slot 12</span> x-'), res["escaped"]


def test_a_question_is_fitted_to_the_screen(tmp_path):
    """fccFitQuestion: box ids stay whole unless that pushes the question past
    the screen's sides (then they break at their hyphens again,
    .fcc-keep-whole-off); a question taller than the window less 16 px scrolls
    inside itself (.fcc-question-scroll), and only then: a scroller draws its
    text without the screen's sub-pixel smoothing, so a question that fits
    must not be one. A question that fits loses both classes again."""
    res = _run(tmp_path, ["inv_core.js"], """
// A panel whose box answers by its classes: ids whole or broken, scrolling or not.
const panel = ({ wide, wideOff, tall, spans = true, classes = [] }) => {
  const el = document.createElement('div');
  classes.forEach((c) => el.classList.add(c));
  const w = () => (el.classList.contains('fcc-keep-whole-off') ? wideOff : wide);
  const scrolls = () => el.classList.contains('fcc-question-scroll');
  el.querySelector = (sel) => (sel === '.fcc-keep-whole' && spans ? {} : null);
  el.getBoundingClientRect = () => ({ width: scrolls() ? Math.min(w(), innerWidth) : w(),
                                      height: scrolls() ? Math.min(tall, innerHeight - 16) : tall });
  Object.defineProperty(el, 'scrollWidth', { get: () => w() });
  Object.defineProperty(el, 'clientWidth', { get: () => (scrolls() ? Math.min(w(), innerWidth) : w()) });
  return el;
};
const out = {};
for (const [key, vw, vh, spec] of [
    ['fits', 360, 640, { wide: 340, wideOff: 330, tall: 500 }],
    ['a very long id', 360, 640, { wide: 377, wideOff: 356, tall: 560 }],
    ['too tall', 360, 640, { wide: 356, wideOff: 340, tall: 667 }],
    ['a px of rounding', 360, 640, { wide: 360.4, wideOff: 340, tall: 624.4 }],
    ['no ids to break', 360, 640, { wide: 377, wideOff: 300, tall: 500, spans: false }],
    ["Derek's window, after a phone", 1600, 1300,
     { wide: 560, wideOff: 540, tall: 350, classes: ['fcc-keep-whole-off', 'fcc-question-scroll'] }]]) {
  window.innerWidth = vw; window.innerHeight = vh;
  const p = panel(spec);
  const said = window.fccFitQuestion ? window.fccFitQuestion(p) : null;
  out[key] = { said, off: p.classList.contains('fcc-keep-whole-off'), scroll: p.classList.contains('fcc-question-scroll') };
}
return out;
""")
    got = {k: v for k, v in res.items() if k != "unhandled"}
    want = {"fits": (False, False), "a very long id": (True, False), "too tall": (False, True),
            "a px of rounding": (False, False), "no ids to break": (False, False),
            "Derek's window, after a phone": (False, False)}
    assert {k: (v["off"], v["scroll"]) for k, v in got.items()} == want, got
    # It says what it did.
    assert all(got[k]["said"] == {"off": w[0], "scroll": w[1]} for k, w in want.items()), got
