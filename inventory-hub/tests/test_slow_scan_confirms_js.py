"""A slower scanner's Enter never answers a confirm (Group 57 review, round 4),
hermetic.

Runs the REAL scan accumulator (scripts.html's keydown block, lifted as
test_slow_scan_slash_js.py lifts it) with the REAL overlay_mount.js, inv_core.js
and inv_quickswap.js, and the REAL Shift+B block of inv_cmd.js and Shift+E /
Shift+C block of inv_wizard.js (each lifted as it is), in `isolated_page` (a
chromium with no route to any network), so it RUNS under --offline. The keys are
typed on a fake clock, one every `ms`, so a scanner's speed is exact whatever the
machine's load.

The defect (found in round 3, reproduced on dev in round 4): the Quick-Swap
confirm overlay's Enter (showConfirmOverlay: the swap, the deposit, the Return
and the server's re-ask) and the slot grid's Enter asked only isScanInFlight,
which counts 500 ms from a scan's FIRST key. The overlay's "Scan to Cancel" is
about 30 characters, so a scanner slower than about 17 ms a key was still typing
it, and its Enter pressed the focused YES: during a print, scanning the cancel
loaded a spool onto the printing head (POST /api/quickswap with the head in
confirmed_toolheads). After Q, a slow scan's Enter opened a swap nobody asked
for, and the next slow scan answered it. The shared move question
(window.confirmActivePrint) caught a slow payload only by its ':', so a slower
scanner's bare-number label ("57") answered its focused button: "Just store it".
Shift+B (Bulk Moves) fired on a slow label's 'B' and cut the scan, and the
wizard's Shift+E / Shift+C on its 'E' or 'C'. The grid's Q kept its 'q' in the
scan buffer (a label scanned within 2 s of it arrived as "qLOC:…") and took any
'q' inside a label for a person's.

Pinned, from 1 to 150 ms a key: the CANCEL scan cancels and the CONFIRM scan
confirms (through routeConfirmScan), nothing else; a person's Enter on YES
confirms and on NO cancels; after Q no slow scan opens or answers a swap, Q
leaves no 'q' behind, and a 'q' inside a label moves nothing; the
shared question's Enter never answers a slow scan, a bare number's included;
Shift+B and Shift+E / Shift+C never fire inside a slow label, and still do for a
person. RED on dd81587 (each test says from what speed).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_slow_scan_slash_js import TYPE_JS, _accumulator

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
SPEEDS = [1, 8, 13, 18, 26, 40, 60, 150]

STUBS = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__posts = [];
window.__scans = [];
window.showToast = function () {};
window.fetch = function (url, opts) {
    url = String(url);
    if (opts && opts.method && opts.method !== 'GET') window.__posts.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
    return Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve('{}'),
                             json: () => Promise.resolve({ status: 'success', success: true }) });
};
// The scan path, as inv_cmd.js's processScan starts: a CMD:CONFIRM / CMD:CANCEL
// / CMD:STORE for an open dialog goes to it.
window.processScan = function (t) { window.__scans.push(t); if (window.routeConfirmScan) window.routeConfirmScan(t); };
"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="manageModal" class="modal show"><div id="quickswap-grid">
  <button class="fcc-qs-slot" data-toolhead="XL-1" data-box="LR-MDB-1" data-slot="1" data-spool-id="57">slot 1</button>
  <button class="fcc-qs-slot" data-toolhead="XL-1" data-box="LR-MDB-1" data-slot="2" data-spool-id="58">slot 2</button>
</div></div>
<div id="wizardModal" class="modal"><button id="wiz-btn">wizard</button></div>
</body></html>"""

# Answers the printer check as the page's own module would, after inv_core.js.
PRINTING_JS = """(printing) => { window.checkPrinterForHead = () => Promise.resolve(printing
    ? { active: true, known: true, state: 'PRINTING', printer_name: 'XL' }
    : { active: false, known: true, state: 'IDLE', printer_name: 'XL' }); }"""


def _block(path, start, end):
    """The source from `start` up to (not including) `end`, as it is."""
    src = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    a = src.index(start)
    return src[a:src.index(end, a)]


SHIFT_B = _block(MODULES / "inv_cmd.js", "(function () {\n    // Delegates to the canonical definition",
                 "// --- L298 Phase 3")
WIZARD_KEYS = _block(MODULES / "inv_wizard.js", "(function() {\n    if (window._wizExpandShortcutWired) return;",
                     "    // Register with the shortcuts registry") + "})();\n"


@pytest.fixture
def scan_page(isolated_page):
    page = isolated_page
    page.set_content(PAGE)
    page.add_script_tag(content=STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "inv_quickswap.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content=SHIFT_B)
    page.add_script_tag(content=WIZARD_KEYS)
    page.add_script_tag(content=_accumulator())          # last, as on the page
    page.evaluate("""() => { window.__bulk = 0; window.toggleBulkMove = () => { window.__bulk += 1; };
        window.__wiz = []; window.wizardExpandAllSections = () => window.__wiz.push('expand');
        window.wizardCollapseAllSections = () => window.__wiz.push('collapse'); }""")
    page.evaluate(PRINTING_JS, True)
    page.evaluate(TYPE_JS, ["", 0, False, {}])            # the fake clock, before anything is typed
    return page


def _type(page, text, ms, enter=True):
    page.evaluate(TYPE_JS, [text, ms, enter, {}])


def _fresh(page):
    """Nothing pending: no dialog, an empty buffer, no record, the clock moved on."""
    page.evaluate("""() => { if (window.closeQuickswapConfirm) window.closeQuickswapConfirm();
        document.querySelectorAll('[data-overlay-mount="1"]').forEach((n) => n.remove());
        window.__posts = []; window.__scans = []; window.__T += 5000;
        state.scanBuffer = ''; state.scanStartTime = 0; }""")


def _open_swap(page, slot=0):
    """The real tap on a slot, with XL-1 printing: the confirm with its QRs."""
    page.evaluate("(i) => window.quickSwapTap(document.querySelectorAll('.fcc-qs-slot')[i])", slot)
    page.wait_for_selector("#fcc-quickswap-confirm-overlay .fcc-confirm-qr-row", timeout=5000)
    return page.evaluate("() => Object.keys(window._fccActiveConfirms).slice(-1)[0]")


def _seen(page):
    return page.evaluate("""() => ({ posts: window.__posts.map((p) => p.url), scans: window.__scans.slice(),
        open: !!document.getElementById('fcc-quickswap-confirm-overlay'), buffer: state.scanBuffer,
        bodies: window.__posts.map((p) => p.body) })""")


@pytest.mark.parametrize("ms", SPEEDS)
def test_a_slow_scanners_cancel_never_confirms_a_swap(scan_page, ms):
    """XL-1 printing, the swap's confirm up with YES focused, and its own "Scan
    to Cancel" scanned: the swap is cancelled, and nothing is sent. RED on
    dd81587 from 18 ms a key: POST /api/quickswap with confirmed_toolheads
    ["XL-1"], and routeConfirmScan never saw the cancel."""
    page = scan_page
    _fresh(page)
    sid = _open_swap(page)
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "fcc-quickswap-yes"
    _type(page, f"CMD:CANCEL:{sid}", ms)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == [] and s["scans"] == [f"CMD:CANCEL:{sid}"] and not s["open"], (ms, s)


@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_slow_scanners_confirm_still_confirms_once(scan_page, ms):
    """The CONFIRM QR is the scan's own answer: it confirms through the scan
    path, once, with the printing head confirmed."""
    page = scan_page
    _fresh(page)
    sid = _open_swap(page)
    _type(page, f"CMD:CONFIRM:{sid}", ms)
    page.wait_for_function("() => window.__posts.length >= 1")
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == ["/api/quickswap"] and s["scans"] == [f"CMD:CONFIRM:{sid}"], (ms, s)
    assert s["bodies"][0]["confirmed_toolheads"] == ["XL-1"], s


def test_a_persons_enter_still_answers_the_focused_button(scan_page):
    """Keyboard use is unaffected: Enter by hand finds the buffer empty. On YES
    it swaps; on NO (Tab) it cancels and sends nothing."""
    page = scan_page
    _fresh(page)
    _open_swap(page)
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__posts.length === 1")
    assert _seen(page)["posts"] == ["/api/quickswap"]
    _fresh(page)
    _open_swap(page)
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "fcc-quickswap-no"
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    s = _seen(page)
    assert s["posts"] == [] and not s["open"], s


@pytest.mark.parametrize("ms", [13, 26, 60])
def test_slow_scans_after_q_never_open_or_answer_a_swap(scan_page, ms):
    """Q puts the focus on the grid's first slot; then two spool QRs scanned
    slowly. Neither opens "Load LR-MDB-1 slot 1 into XL-1?", and both reach the
    scan path whole. RED on dd81587 at 26 ms a key: the first scan opened the
    confirm and the second, never reaching the scan path, performed it (POST
    /api/quickswap, nobody having pressed anything)."""
    page = scan_page
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    page.locator(".fcc-qs-slot").first.focus()
    page.keyboard.press("q")                         # its 'q' stays out of the scan buffer
    page.wait_for_timeout(50)
    url = "https://prusament.com/spool/17705/5b1a183b26/"
    for _ in range(2):
        _type(page, url, ms)
        page.wait_for_timeout(100)
    s = _seen(page)
    assert s["posts"] == [] and not s["open"] and s["scans"] == [url, url], (ms, s)
    # A person's Enter on the highlighted slot still opens it.
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Enter")
    page.wait_for_selector("#fcc-quickswap-confirm-overlay", timeout=5000)


def test_q_leaves_no_q_for_the_next_scan(scan_page):
    """Q jumps to the grid and keeps its 'q' out of the scan buffer: a label
    scanned straight after it arrives as it is. RED on dd81587: "qLOC:LR-MDB-1"
    (an unknown code) for 2 s after Q."""
    page = scan_page
    _fresh(page)
    page.locator(".fcc-qs-slot").nth(1).focus()
    page.keyboard.press("q")
    assert page.evaluate("() => document.activeElement.dataset.slot") == "1"     # the grid's first slot
    _type(page, "LOC:LR-MDB-1", 13)
    assert _seen(page)["scans"] == ["LOC:LR-MDB-1"]


@pytest.mark.parametrize("ms", [13, 60])
def test_a_q_inside_a_slow_label_moves_nothing(scan_page, ms):
    """A label with a 'q' in it (a confirm's session id has one), scanned with
    the grid up and no dialog: the focus stays where it was and the scan is
    whole. RED on dd81587 at every speed: Q had no scan check at all, and the
    'q' jumped the focus to the first slot."""
    page = scan_page
    _fresh(page)
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "CMD:CANCEL:fcc-cqr-1-abc", ms)
    assert page.evaluate("() => document.activeElement.dataset.slot") == "2", ms
    assert _seen(page)["scans"] == ["CMD:CANCEL:fcc-cqr-1-abc"], ms


# The shared move question (window.confirmActivePrint), in its three-way:
# Load it instead / Just store it / Cancel, Enter storing. Records the answer.
THREE_WAY_JS = """() => { window.__answer = null;
    window.confirmActivePrint({ title: 'XL-1 is running #99', msg: 'Load #57 onto XL-1?',
        ids: { overlay: 'fcc-three-way-probe' },
        onConfirm: () => { window.__answer = 'load'; }, onStore: () => { window.__answer = 'store'; },
        onCancel: () => { window.__answer = 'cancel'; } }); }"""


@pytest.mark.parametrize("label", ["57", "1024", "LOC:LR-MDB-1"])
@pytest.mark.parametrize("ms", [1, 26, 60, 150, 250])
def test_the_shared_question_never_answers_a_slow_scan(scan_page, label, ms):
    """The three-way up (Enter would store), and a label scanned at every
    speed: the question stays unanswered and the label reaches the scan path.
    RED on dd81587 for a bare number whose Enter came 500 ms or more after its
    first key ("1024" at 150 ms a key, "57" at 250): "Just store it". (A label
    with a ':' was caught there already.)"""
    page = scan_page
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    _type(page, label, ms)
    page.wait_for_timeout(50)
    got = page.evaluate("() => ({ answer: window.__answer, scans: window.__scans.slice(),"
                        " open: !!document.getElementById('fcc-three-way-probe') })")
    assert got == {"answer": None, "scans": [label], "open": True}, (label, ms, got)
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Enter")                       # a person's Enter: the focused store
    assert page.evaluate("() => window.__answer") == "store"


@pytest.mark.parametrize("ms", [13, 26, 75, 150])
def test_shift_b_never_fires_inside_a_slow_label(scan_page, ms):
    """Nothing open, "LOC:LR-MDB-1" scanned: its 'B' is a Shift+B, and past the
    first 500 ms it armed a bulk move and cut the scan to "-1" (RED on
    dd81587 at 75 ms a key). A person's Shift+B still arms one."""
    page = scan_page
    _fresh(page)
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show'); document.activeElement.blur(); }")
    _type(page, "LOC:LR-MDB-1", ms)
    s = _seen(page)
    assert page.evaluate("() => window.__bulk") == 0 and s["scans"] == ["LOC:LR-MDB-1"], (ms, s)
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Shift+B")
    assert page.evaluate("() => window.__bulk") == 1


@pytest.mark.parametrize("ms", [13, 80, 150])
def test_the_wizards_shift_e_and_c_never_fire_inside_a_slow_label(scan_page, ms):
    """The wizard up with the focus on a button, "LOC:CR-CT-2-R1" scanned: its
    capital C's are Shift+C. Past the first 500 ms each collapsed the wizard's
    sections (RED on dd81587 at 80 ms a key). A person's Shift+E still
    expands them."""
    page = scan_page
    _fresh(page)
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show');"
                  " document.getElementById('wizardModal').classList.add('show'); document.getElementById('wiz-btn').focus(); }")
    _type(page, "LOC:CR-CT-2-R1", ms)
    assert page.evaluate("() => window.__wiz") == [] and _seen(page)["scans"] == ["LOC:CR-CT-2-R1"], ms
    page.evaluate("() => { window.__T += 3000; }")
    page.keyboard.press("Shift+E")
    assert page.evaluate("() => window.__wiz") == ["expand"]
