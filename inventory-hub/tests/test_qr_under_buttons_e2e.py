"""Each "📷 Scan to …" QR sits directly under its own button, on the real page
(Derek, 2026-10-22).

"It'd be nice if we could get the QR codes to also align under the button they
correspond to. We could add some space between the buttons so they align
better to the QR code, otherwise they are slightly skewed, and not directly
under their button."

Every question with a QR row is opened on the dev container's page and
measured: the move question's three-way (Load it instead / Just store it /
Cancel) and its printing variant, the store-only question, Load it instead /
Cancel (the Printer picker's head question), the active-print yes / no, "Record
it as coming from…" with one free slot (and a held one) and with two free, and
the Quick-Swap confirm while its printer prints (its QRs are above its buttons,
as before; each button stays centred under its QR). On Derek's 1600 x 1300
window at Standard and Extra Large, and on a 412 px phone at Standard and
Extra Large:
  - each QR card's centre is within 1 px of its own button's centre
    (TOLERANCE_PX), and below it (above it in the Quick-Swap);
  - nothing sticks out sideways: the page doesn't scroll sideways, the dialog
    is inside the window, and every button and QR card is inside the dialog;
  - "Record it as coming from…" still starts on the slot it pre-selects (else
    No box) and its arrow keys still go slots, No box, Cancel, as drawn;
  - (review, 2026-10-22) on a 360 x 640 phone at Standard, Large and Extra
    Large every question is inside the window, a tall one scrolling inside
    itself to its last line, nothing sticks out sideways, each QR is still
    under its button, and no button breaks a box id or "slot N" over a line.
    RED on c5c9d1f: at Extra Large both record-source dialogs were cut by the
    window (y -13 to 653 of 640 px), and at every size the store buttons and
    the record source's slot split "LR-MDB- / 1" (or "slot / 1").
The hermetic proof of the wiring is test_qr_under_buttons_js.py.

READ-ONLY, like test_text_size_guard.py: every request that isn't a read is
answered inside the browser. The questions are opened with no-op answers (no
door behind them) and closed with Escape; the Quick-Swap confirm is closed
before its Yes. The size is this test browser's own localStorage.

HEAD proof (0c965c7: the product edits stashed for one run against the live
container, restored after): all 4 RED. On 1600 px at Standard the three-way's
Load QR sat 19.8 px right of its button's centre, Store's 17.6 px left and
Cancel's 37.5 px left; "Record it as coming from…"'s No box QR was 76 px off
(180 px with two free slots); at Extra Large up to 221 px; and on a 412 px
phone the three buttons wrapped onto two or three lines over one row of three
QRs (the Cancel QR up to 121 px off). The Quick-Swap confirm was already
aligned and stays so.
"""
from __future__ import annotations

import pytest
import requests
from playwright.sync_api import Page

from test_text_size_guard import _read_only

pytestmark = pytest.mark.usefixtures("require_server")

TOLERANCE_PX = 1.0
KEY = "fcc.textSize"

# The answers the doors pass to confirmHeadLoad (the fed dialog, a printing
# one, and a slot that now feeds nothing: Just store it / Cancel).
FED_IDLE = {
    "status": "requires_confirm", "confirm_type": "head_fed",
    "fed_heads": [{"toolhead": "XL-1", "printer_name": "XL", "box": "LR-MDB-1", "slot": "1",
                   "resident": {"id": 1, "from": "PM-DB-3"}, "residents": [{"id": 1, "from": "PM-DB-3"}],
                   "confirm_key": "XL-1#1"}],
    "active_prints": [], "active_print": None, "can_store": True, "target_slot": None, "spools": [57],
    "title": "Load #57 onto XL-1?",
    "body": "LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #1 (from PM-DB-3). Loading #57 sends #1 back to PM-DB-3.",
}
PRINTING = {
    "status": "requires_confirm", "confirm_type": "active_print",
    "active_prints": [{"toolhead": "XL-2", "printer_name": "XL", "state": "PRINTING", "role": "feeds", "spools": [57]}],
    "active_print": {"toolhead": "XL-2", "printer_name": "XL", "state": "PRINTING"},
    "fed_heads": [], "can_store": True, "target_slot": "2", "target": "LR-MDB-1", "spools": [57],
    "title": "Load #57 onto XL-2?",
    "body": "XL is PRINTING. LR-MDB-1 slot 2 feeds XL-2, so this also loads #57 onto XL-2.",
}
STORE_ONLY = {
    "status": "requires_confirm", "confirm_type": "feed_changed", "feed": "", "can_load": False, "can_store": True,
    "feed_changed": {"was": "XL-1", "now": ""}, "fed_heads": [], "active_prints": [], "target": "LR-MDB-1",
    "target_slot": "1", "spools": [57], "title": "Store #57 in LR-MDB-1 slot 1?",
    "body": "LR-MDB-1 slot 1 now feeds nothing (it fed XL-1 when you were asked).",
}

APC = {"confirm": ".fcc-apc-yes", "store": ".fcc-apc-store", "cancel": ".fcc-apc-no"}

# name -> (JS that opens it (no return value: a door's Promise must not be
# awaited), the overlay's id, {QR role: its button's selector}).
DIALOGS = {
    "three-way (Load it instead / Just store it / Cancel)": (
        "(a) => { window.confirmHeadLoad({ answer: a, box: 'LR-MDB-1', onLoad() {}, onStore() {}, onCancel() {} }); }",
        FED_IDLE, "fcc-active-print-confirm-overlay", APC),
    "three-way while printing": (
        "(a) => { window.confirmHeadLoad({ answer: a, box: 'LR-MDB-1', onLoad() {}, onStore() {}, onCancel() {} }); }",
        PRINTING, "fcc-active-print-confirm-overlay", APC),
    "store only (Just store it / Cancel)": (
        "(a) => { window.confirmHeadLoad({ answer: a, box: 'LR-MDB-1', onLoad() {}, onStore() {}, onCancel() {} }); }",
        STORE_ONLY, "fcc-active-print-confirm-overlay", {"confirm": ".fcc-apc-store", "cancel": ".fcc-apc-no"}),
    "Load it instead / Cancel (a head that holds a spool)": (
        "() => { window.__qaPick = _confirmHeadPick({ head: 'XL-3', residents: [{ id: 99, from: 'LR-MDB-1 slot 3' }] },"
        " 42, null); }", None, "fcc-head-pick-confirm", {"confirm": ".fcc-apc-yes", "cancel": ".fcc-apc-no"}),
    "active-print yes / no": (
        "() => { window.confirmActivePrint({ activePrint: { printer_name: 'XL', state: 'PRINTING', toolhead: 'XL-1' },"
        " msg: 'Moving a spool now will disrupt the print. Continue?', onConfirm() {}, onCancel() {} }); }",
        None, "fcc-active-print-confirm-overlay", {"confirm": ".fcc-apc-yes", "cancel": ".fcc-apc-no"}),
    "Record it as coming from… (one free slot, one held)": (
        "() => { window.__qaRs = _askRecordSource({ head: 'XL-1', spool_location: '', feeds: ["
        "{ box: 'LR-MDB-1', slot: '1', free: true }, { box: 'LR-MDB-1', slot: '2', free: false, claimed_by: 99 }] },"
        " 57, null); }", None, "fcc-record-source",
        {"confirm": ".fcc-rs-opt:not([disabled])", "store": ".fcc-rs-none", "cancel": ".fcc-rs-cancel"}),
    "Record it as coming from… (two free slots)": (
        "() => { window.__qaRs = _askRecordSource({ head: 'XL-1', spool_location: '', feeds: ["
        "{ box: 'LR-MDB-1', slot: '1', free: true }, { box: 'PM-DB-XL-L', slot: '1', free: true }] }, 57, null); }",
        None, "fcc-record-source", {"confirm": ".fcc-rs-none", "cancel": ".fcc-rs-cancel"}),
}

# Each QR cell's card against the button it stands for, plus what sticks out.
MEASURE_JS = r"""([id, map]) => {
    const root = document.getElementById(id);
    const panel = root.firstElementChild;
    const box = (el) => { const r = el.getBoundingClientRect();
        return { l: r.left, r: r.right, t: r.top, b: r.bottom, c: r.left + r.width / 2 }; };
    const p = box(panel);
    const vw = document.documentElement.clientWidth;
    const inside = (b) => b.l >= p.l - 0.5 && b.r <= p.r + 0.5;
    const out = { vw, panel: p, sideways: document.documentElement.scrollWidth > vw + 1, cells: [], strays: [] };
    root.querySelectorAll('.fcc-confirm-qr-cell').forEach((cell) => {
        const role = cell.dataset.qr;
        const card = box(cell.querySelector('.fcc-qr-card'));
        const btnEl = root.querySelector(map[role]);
        const btn = btnEl ? box(btnEl) : null;
        out.cells.push({ role, caption: cell.innerText.replace(/\s+/g, ' ').trim(), card, btn,
                         button: btnEl ? btnEl.innerText.replace(/\s+/g, ' ').trim() : null });
        if (!inside(card)) out.strays.push('QR ' + role);
    });
    root.querySelectorAll('button').forEach((b) => {
        if (b.getClientRects().length && !inside(box(b))) out.strays.push('button ' + b.innerText.trim());
    });
    return out;
}"""


def _store(page: Page, name: str):
    page.add_init_script("(() => { try { localStorage.setItem(%r, %r); } catch (e) {} })();" % (KEY, name))


def _load(page: Page, base_url: str):
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof state !== 'undefined' && state.locationsLoaded"
                           " && typeof window.confirmHeadLoad === 'function' && typeof _askRecordSource === 'function'",
                           timeout=45_000)
    page.wait_for_timeout(800)


def _qrs_drawn(page: Page, oid: str):
    """The row is there and every QR has drawn (generateSafeQR draws on a
    double animation frame; an undrawn card is smaller)."""
    page.wait_for_function("""(id) => { const r = document.querySelector('#' + id + ' .fcc-confirm-qr-row');
        return !!r && Array.from(r.querySelectorAll('.fcc-qr-card > div')).every((d) => d.children.length > 0); }""",
                           arg=oid, timeout=8000)
    page.wait_for_timeout(200)


def _check(got: dict, where: str, qr_above: bool = False) -> list:
    """Sentences for everything wrong with one measured dialog."""
    wrong = []
    if not got["cells"]:
        return [f"{where}: no QR codes on screen"]
    for c in got["cells"]:
        if not c["btn"]:
            wrong.append(f"{where}: the {c['caption']!r} QR has no button on screen")
            continue
        off = c["card"]["c"] - c["btn"]["c"]
        if abs(off) > TOLERANCE_PX:
            wrong.append(f"{where}: the {c['caption']!r} QR is {off:+.1f} px off the centre of "
                         f"its button {c['button']!r}")
        if qr_above and c["card"]["b"] > c["btn"]["t"] + 0.5:
            wrong.append(f"{where}: the {c['caption']!r} QR is not above its button")
        if not qr_above and c["card"]["t"] < c["btn"]["b"] - 0.5:
            wrong.append(f"{where}: the {c['caption']!r} QR is not under its button")
    if got["sideways"]:
        wrong.append(f"{where}: the page scrolls sideways")
    if got["panel"]["l"] < -0.5 or got["panel"]["r"] > got["vw"] + 0.5:
        wrong.append(f"{where}: the dialog sticks out of the window ({got['panel']['l']:.0f}-{got['panel']['r']:.0f} "
                     f"of {got['vw']} px)")
    if got["strays"]:
        wrong.append(f"{where}: outside the dialog: {got['strays']}")
    return wrong


def _record_source_keys(page: Page, two_free: bool) -> list:
    """The keys still go in the order drawn: the pre-selected slot (else No
    box) has the focus, and → steps slots, No box, Cancel, round again."""
    def focused():
        return page.evaluate("""() => { const a = document.activeElement;
            if (!a || !a.closest('#fcc-record-source')) return null;
            if (a.classList.contains('fcc-rs-none')) return 'No box';
            if (a.classList.contains('fcc-rs-cancel')) return 'Cancel';
            return a.innerText.split('\\n')[0].trim(); }""")
    want = (["No box", "Cancel", "LR-MDB-1 slot 1", "PM-DB-XL-L slot 1", "No box"] if two_free
            else ["LR-MDB-1 slot 1", "No box", "Cancel", "LR-MDB-1 slot 1"])
    got = [focused()]
    for _ in want[1:]:
        page.keyboard.press("ArrowRight")
        got.append(focused())
    return [] if got == want else [f"Record it as coming from… ({'two free' if two_free else 'one free'}): "
                                   f"the keys went {got}, not {want}"]


def _quickswap_head(api_base_url: str):
    """A toolhead with a Quick-Swap card: a multi-slot Dryer Box slot bound to
    it that holds a stored spool (dev's own data). None when dev has none."""
    try:
        rows = requests.get(api_base_url + "/api/locations", timeout=20).json()
        heads = {str(r.get("LocationID")) for r in rows if r.get("Type") == "Tool Head"}
        for row in rows:
            if row.get("Type") != "Dryer Box":
                continue
            targets = (row.get("extra") or {}).get("slot_targets") or {}
            if not isinstance(targets, dict) or int(str(row.get("Max Spools") or "0") or 0) < 2:
                continue
            for s in requests.get(api_base_url + "/api/get_contents?id=" + str(row["LocationID"]), timeout=20).json():
                head = str(targets.get(str(s.get("slot") or "")) or "")
                if head in heads and not s.get("is_ghost"):
                    return head
    except (requests.RequestException, ValueError):
        return None
    return None


def _quickswap(page: Page, head: str, where: str) -> list:
    """The Quick-Swap confirm while the head's printer answers PRINTING (this
    page only): its QRs above, each button centred under its QR."""
    page.route("**/api/printer_state/" + head, lambda route: route.fulfill(
        status=200, content_type="application/json",
        body='{"is_active": true, "known": true, "printer_name": "XL", "state": "PRINTING"}'))
    page.evaluate("""(id) => { window.__qaShown = false; document.getElementById('manageModal')
        .addEventListener('shown.bs.modal', () => { window.__qaShown = true; }, { once: true });
        window.openManage(id); }""", head)
    page.wait_for_function("() => window.__qaShown === true", timeout=15_000)
    page.wait_for_function("() => document.querySelectorAll('#quickswap-grid .fcc-qs-card').length > 0", timeout=15_000)
    page.wait_for_timeout(800)
    page.locator("#quickswap-grid .fcc-qs-card").first.click()
    _qrs_drawn(page, "fcc-quickswap-confirm-overlay")
    got = page.evaluate(MEASURE_JS, ["fcc-quickswap-confirm-overlay",
                                     {"confirm": "#fcc-quickswap-yes", "cancel": "#fcc-quickswap-no"}])
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('fcc-quickswap-confirm-overlay')", timeout=5000)
    page.evaluate("() => { window.manageNavStack = []; closeManage(); }")
    return _check(got, where, qr_above=True)


@pytest.mark.parametrize("size, width", [("Standard", 1600), ("Extra Large", 1600),
                                         ("Standard", 412), ("Extra Large", 412)])
def test_every_qr_sits_under_its_own_button(page: Page, base_url: str, api_base_url: str, size, width):
    _read_only(page)
    _store(page, size)
    page.set_viewport_size({"width": width, "height": 1300 if width > 800 else 915})
    _load(page, base_url)
    assert page.evaluate("() => document.documentElement.getAttribute('data-fcc-text-size')") == \
        {"Standard": "standard", "Extra Large": "xlarge"}[size]
    wrong = []
    for name, (opener, answer, oid, buttons) in DIALOGS.items():
        where = f"{size} @ {width} px, {name}"
        page.evaluate(opener, answer)
        _qrs_drawn(page, oid)
        wrong += _check(page.evaluate(MEASURE_JS, [oid, buttons]), where)
        if name.startswith("Record it"):
            wrong += _record_source_keys(page, "two free" in name)
        page.keyboard.press("Escape")
        page.wait_for_function("(id) => !document.getElementById(id)", arg=oid, timeout=5000)
    head = _quickswap_head(api_base_url)
    if head:
        wrong += _quickswap(page, head, f"{size} @ {width} px, Quick-Swap confirm ({head})")
    assert not wrong, "QR codes not under their buttons:\n  " + "\n  ".join(wrong)


# --- a short phone (review, 2026-10-22) -----------------------------------------
# On a 360 x 640 phone at Extra Large "Record it as coming from…" was 667 px
# high, centred, so its top and bottom were cut where nothing scrolls; and
# button labels broke box ids at a hyphen ("LR-MDB- / 1 slot 1").

# The panel on screen, whether its content can be scrolled to, and where it
# sticks out; and every box id or "slot N" in a button that a line break splits.
PHONE_JS = r"""([id, words]) => {
    const root = document.getElementById(id);
    const panel = root.firstElementChild;
    const r = panel.getBoundingClientRect();
    const out = { top: r.top, bottom: r.bottom, vh: innerHeight, sh: panel.scrollHeight, ch: panel.clientHeight,
                  sw: panel.scrollWidth, cw: panel.clientWidth, split: [] };
    // Scrolled to the end, the last thing in the panel is inside it.
    panel.scrollTop = panel.scrollHeight;
    const last = Array.from(panel.querySelectorAll('*')).filter((el) => el.getClientRects().length)
        .reduce((m, el) => Math.max(m, el.getBoundingClientRect().bottom), 0);
    out.lastInside = last <= panel.getBoundingClientRect().bottom + 0.5;
    panel.scrollTop = 0;
    // Each character's line (its top), per button.
    root.querySelectorAll('button').forEach((b) => {
        const chars = [];
        const walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
        const range = document.createRange();
        let n;
        while ((n = walker.nextNode())) for (let i = 0; i < n.length; i++) {
            range.setStart(n, i); range.setEnd(n, i + 1);
            const rr = range.getClientRects()[0];
            chars.push({ c: n.data[i], top: rr ? Math.round(rr.top) : null });
        }
        const text = chars.map((x) => x.c).join('');
        words.forEach((w) => {
            for (let at = text.indexOf(w); at >= 0; at = text.indexOf(w, at + 1)) {
                const tops = new Set(chars.slice(at, at + w.length).map((x) => x.top));
                if (tops.size > 1) out.split.push(w + ' in "' + b.innerText.replace(/\s+/g, ' ').trim() + '"');
            }
        });
    });
    return out;
}"""
WORDS = ["LR-MDB-1", "PM-DB-XL-L", "slot 1", "slot 2"]


@pytest.mark.parametrize("size", ["Standard", "Large", "Extra Large"])
def test_a_short_phone_keeps_each_question_on_screen_and_box_ids_whole(page: Page, base_url: str, size):
    """360 x 640: every question is inside the window (a tall one scrolls inside
    itself, its last line reachable), nothing sticks out sideways, each QR is
    still under its button, and no button breaks a box id or "slot N"."""
    _read_only(page)
    _store(page, size)
    page.set_viewport_size({"width": 360, "height": 640})
    _load(page, base_url)
    wrong = []
    for name, (opener, answer, oid, buttons) in DIALOGS.items():
        where = f"{size} @ 360 x 640, {name}"
        page.evaluate(opener, answer)
        _qrs_drawn(page, oid)
        wrong += _check(page.evaluate(MEASURE_JS, [oid, buttons]), where)
        got = page.evaluate(PHONE_JS, [oid, WORDS])
        if got["top"] < -0.5 or got["bottom"] > got["vh"] + 0.5:
            wrong.append(f"{where}: cut by the window (y {got['top']:.1f} to {got['bottom']:.1f} of {got['vh']} px)")
        if not got["lastInside"]:
            wrong.append(f"{where}: its last line can't be scrolled to ({got['sh']} px of content in {got['ch']})")
        if got["sw"] > got["cw"] + 1:
            wrong.append(f"{where}: {got['sw']} px wide inside a {got['cw']} px dialog")
        wrong += [f"{where}: a line break splits {s}" for s in got["split"]]
        page.keyboard.press("Escape")
        page.wait_for_function("(id) => !document.getElementById(id)", arg=oid, timeout=5000)
    assert not wrong, "on a short phone:\n  " + "\n  ".join(wrong)


@pytest.mark.parametrize("size", ["Standard", "Extra Large"])
def test_a_question_that_fits_is_no_scroller(page: Page, base_url: str, size):
    """A scroller draws its text without the screen's sub-pixel smoothing
    (greyscale, not ClearType), even with nothing to scroll: the first version
    of the short-phone fix made every question one, and the move question's
    text lost its colour fringes on Derek's 1600 x 1300 window
    (head-load-confirm-fed.png). Only a question taller than the window
    scrolls (fccFitQuestion), so here none does."""
    _read_only(page)
    _store(page, size)
    _load(page, base_url)
    scrollers = []
    for name, (opener, answer, oid, _buttons) in DIALOGS.items():
        page.evaluate(opener, answer)
        _qrs_drawn(page, oid)
        page.wait_for_timeout(100)   # the fit's own check after the QRs are in
        got = page.evaluate("""(id) => { const p = document.getElementById(id).firstElementChild;
            return { oy: getComputedStyle(p).overflowY, cls: p.classList.contains('fcc-question-scroll') }; }""", oid)
        if got["oy"] != "visible" or got["cls"]:
            scrollers.append(f"{name}: {got}")
        page.keyboard.press("Escape")
        page.wait_for_function("(id) => !document.getElementById(id)", arg=oid, timeout=5000)
    assert not scrollers, f"{size} @ 1600 x 1300: questions drawn as scrollers: {scrollers}"
