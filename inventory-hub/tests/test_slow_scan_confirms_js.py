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

Round 5 (RED on 91e79e8, each test says how): the person's side. Two Spaces a
button press left made a person's Enter on YES, on the grid or in the three-way
a scan of "  "; two keys a person left (the shortcut list's "??", a stray "12",
the wizard's own E and C) held off Q, Shift+B and the wizard's next toggle for
2 s; a key left in front of the confirm's own "Scan to Cancel" stopped it; Q,
then a digit, then Enter opened the swap and also put that spool in the scan
buffer. Pinned too: a one-key label never answers a confirm, and a label's 'E'
right after its first key never toggles the wizard (both were unpinned).
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
<div id="fcc-shortcuts-overlay" style="display:none"><div id="fcc-shortcuts-list"></div></div>
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


# ---- Round 5: the person's side, and two unpinned scan rules -------------------------------------

def _wizard(page):
    """The wizard up with the focus on its button, nothing else open."""
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show');"
                  " document.getElementById('wizardModal').classList.add('show'); document.getElementById('wiz-btn').focus(); }")


def _q(page):
    """Q on the grid (the focus on slot 2): the focus goes to slot 1. A beat
    after, so Q's deferred buffer clear has run, as it has by the time a
    person's next key comes."""
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "q", 10, enter=False)
    page.wait_for_timeout(20)


@pytest.mark.parametrize("ms", [1, 26, 150])
def test_a_one_key_label_never_answers_a_confirm(scan_page, ms):
    """A one-key label ("7", an old bare spool id) scanned at the Quick-Swap
    confirm (YES focused), onto the grid after Q, and at the three-way: its
    Enter is the scan's (it is in flight), so nothing is answered and "7"
    reaches the scan path. Unpinned until round 5: without enterIsAScan's
    in-flight rule every test stayed green, and "7" confirmed the swap."""
    page = scan_page
    _fresh(page)
    _open_swap(page)
    _type(page, "7", ms)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == [] and s["open"] and s["scans"] == ["7"], (ms, s)
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    _q(page)
    _type(page, "7", ms)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert not s["open"] and s["scans"] == ["7"], (ms, s)
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    _type(page, "7", ms)
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__answer") is None and _seen(page)["scans"] == ["7"], ms


@pytest.mark.parametrize("left", ["x", " ", "x "])
def test_a_key_left_in_front_of_the_qrs_never_stops_them(scan_page, left):
    """A key a person pressed on the confirm (a stray letter, a Space, or
    both), then its own QR scanned a second later: "Scan to Cancel" cancels
    the swap and sends nothing, and the three-way's "Scan to Store" stores.
    RED on 91e79e8: the key sat in front of the payload, the anchored match
    missed it, and the dialog stayed up with nothing said."""
    page = scan_page
    _fresh(page)
    sid = _open_swap(page)
    _type(page, left, 100, enter=False)
    page.evaluate("() => { window.__T += 1000; }")
    _type(page, f"CMD:CANCEL:{sid}", 8)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == [] and not s["open"], (left, s)
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    sid = page.evaluate("() => Object.keys(window._fccActiveConfirms).slice(-1)[0]")
    _type(page, left, 100, enter=False)
    page.evaluate("() => { window.__T += 1000; }")
    _type(page, f"CMD:STORE:{sid}", 8)
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__answer") == "store", left


@pytest.mark.parametrize("left", ["  ", "x ", "x"])
def test_a_persons_enter_after_stray_keys_answers_the_dialog(scan_page, left):
    """Two Spaces pressed on a button (they press nothing here; a tile that
    takes no Space is the real case), a stray letter and a Space, or a stray
    letter, then a person's Enter 0.7 s later: YES swaps, the grid's
    highlighted slot opens its confirm, and the three-way stores, each on the
    first Enter, and the keys go with it (they would start the next scan). RED
    on 91e79e8: the blanks stayed in the scan buffer and counted, so the Enter
    was taken for a scan of "  " or "x " and lost; and the letter stayed."""
    page = scan_page
    _fresh(page)
    _open_swap(page)
    _type(page, left, 300, enter=False)
    _type(page, "", 700)
    page.wait_for_function("() => window.__posts.length === 1", timeout=3000)
    assert _seen(page)["buffer"] == "", left
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    _q(page)
    _type(page, left, 300, enter=False)
    _type(page, "", 700)
    page.wait_for_selector("#fcc-quickswap-confirm-overlay", timeout=3000)
    page.wait_for_timeout(20)
    assert (_seen(page)["buffer"], _seen(page)["scans"]) == ("", []), left
    _fresh(page)
    page.evaluate(THREE_WAY_JS)
    page.wait_for_selector("#fcc-three-way-probe")
    _type(page, left, 300, enter=False)
    _type(page, "", 700)
    page.wait_for_timeout(20)
    assert page.evaluate("() => window.__answer") == "store", left
    assert (_seen(page)["buffer"], _seen(page)["scans"]) == ("", []), left


def test_a_legacy_labels_question_mark_never_opens_the_shortcut_list(scan_page):
    """A legacy Google Sheets label is a URL with a '?' after its "https:".
    Scanned slowly, with the scanner pausing 200 ms (real time: the list waits
    120 ms for a next key) right after the '?': the list stays shut and the
    scan arrives whole. RED on 91e79e8: the '?' asked only whether a scan was
    in flight (500 ms from its first key), so the list opened over the scan."""
    page = scan_page
    page.add_script_tag(content=(MODULES / "shortcuts_registry.js").read_text(encoding="utf-8"))
    _fresh(page)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    url = "https://docs.google.com/spreadsheets/d/1AbC/edit?gid=304905527#gid=304905527&range=98:98"
    at = url.index("?") + 1
    _type(page, url[:at], 26, enter=False)
    page.wait_for_timeout(200)
    _type(page, url[at:], 26)
    assert page.evaluate("() => document.getElementById('fcc-shortcuts-overlay').style.display") != "block"
    assert _seen(page)["scans"] == [url]


def test_keys_a_person_left_never_stop_q_shift_b_or_the_wizard(scan_page):
    """Two keys a person pressed and left ("??", "12"), then Q 0.6 s later:
    the focus goes to the grid; then Shift+B 0.6 s after "12" with nothing
    open: a bulk move arms; the wizard's Shift+E, Shift+C, Shift+E, Shift+C
    0.6 s apart: all four act (the wizard keeps its own keys in the buffer, so
    a label's first key is never cut). RED on 91e79e8: any two characters in
    the buffer held these keys off for 2 s, and each blocked press restarted
    it."""
    page = scan_page
    _fresh(page)
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "??", 600, enter=False)
    _type(page, "q", 600, enter=False)
    assert page.evaluate("() => document.activeElement.dataset.slot") == "1"
    assert _seen(page)["buffer"] == ""
    _fresh(page)
    page.evaluate("() => { document.getElementById('manageModal').classList.remove('show'); document.activeElement.blur(); }")
    _type(page, "12", 600, enter=False)
    _type(page, "B", 600, enter=False)
    assert page.evaluate("() => window.__bulk") == 1
    _fresh(page)
    _wizard(page)
    _type(page, "ECEC", 600, enter=False)
    assert page.evaluate("() => window.__wiz") == ["expand", "collapse", "expand", "collapse"]


def test_the_help_key_takes_its_question_marks_back(scan_page):
    """'?' opens the shortcut list and '?' closes it (nothing followed either
    within 120 ms, so both were a person's): neither stays in the scan buffer,
    and Q 0.6 s later moves the focus to the grid. RED on 91e79e8: "??" stayed
    for 2 s, held Q off, and a person's next Enter scanned it."""
    page = scan_page
    page.add_script_tag(content=(MODULES / "shortcuts_registry.js").read_text(encoding="utf-8"))
    _fresh(page)
    shown = "document.getElementById('fcc-shortcuts-overlay').style.display"
    page.locator(".fcc-qs-slot").nth(1).focus()
    _type(page, "?", 10, enter=False)
    page.wait_for_function(f"() => {shown} === 'block'", timeout=3000)
    assert _seen(page)["buffer"] == ""
    _type(page, "?", 600, enter=False)
    page.wait_for_function(f"() => {shown} === 'none'", timeout=3000)
    assert _seen(page)["buffer"] == ""
    _type(page, "q", 600, enter=False)
    assert page.evaluate("() => document.activeElement.dataset.slot") == "1"


def test_q_then_a_digit_then_enter_opens_the_swap_and_nothing_else(scan_page):
    """Q, then 2 (a person expecting slot 2), then Enter 0.7 s later: the
    highlighted slot's confirm opens, and the "2" goes nowhere. RED on 91e79e8:
    the grid's Enter left the event to the accumulator too, which submitted
    "2" (on dev, spool #2 into the scan buffer, unseen behind the dialog)."""
    page = scan_page
    _fresh(page)
    page.evaluate(PRINTING_JS, False)
    _q(page)
    _type(page, "2", 300, enter=False)
    _type(page, "", 700)
    page.wait_for_selector("#fcc-quickswap-confirm-overlay", timeout=3000)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["scans"] == [] and s["buffer"] == "", s


@pytest.mark.parametrize("ms", [13, 80])
def test_a_labels_e_right_after_its_first_key_never_toggles_the_wizard(scan_page, ms):
    """"LEG:120" with the wizard up: its 'E' is a Shift+E one key in, with
    nothing in the buffer that looks like a scan yet, so only the in-flight
    rule keeps it the scan's. Unpinned until round 5 (scanIsArriving without it
    kept every test green, and the 'E' expanded the wizard)."""
    page = scan_page
    _fresh(page)
    _wizard(page)
    _type(page, "LEG:120", ms)
    assert page.evaluate("() => window.__wiz") == [] and _seen(page)["scans"] == ["LEG:120"], ms


# The shared move question's two-way (a print running: Yes / No), which has its
# own Enter branch.
TWO_WAY_JS = """() => { window.__answer = null;
    window.confirmActivePrint({ activePrint: { printer_name: 'XL', state: 'PRINTING' }, activePrints: [],
        msg: 'Load #57 onto XL-1?', ids: { overlay: 'fcc-two-way-probe' },
        onConfirm: () => { window.__answer = 'load'; }, onCancel: () => { window.__answer = 'cancel'; } }); }"""


def test_a_persons_enter_on_no_or_the_two_way_takes_a_key_left_too(scan_page):
    """A key a person left, then their Enter 0.7 s later on the Quick-Swap
    confirm's NO, or on the two-way question's Yes or No: the Enter answers it
    and the key goes with it, so it can't start the next scan. Unpinned until
    round 6: those three Enters each left the key in the scan buffer and every
    test stayed green (round 5 drove YES and the three-way only)."""
    page = scan_page
    _fresh(page)
    _open_swap(page)
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "fcc-quickswap-no"
    _type(page, "x", 300, enter=False)
    _type(page, "", 700)
    page.wait_for_timeout(50)
    s = _seen(page)
    assert s["posts"] == [] and not s["open"] and s["buffer"] == "", s
    for answer in ("load", "cancel"):
        _fresh(page)
        page.evaluate(TWO_WAY_JS)
        page.wait_for_selector("#fcc-two-way-probe")
        page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('fcc-apc-yes')")
        if answer == "cancel":
            page.keyboard.press("Tab")
        _type(page, "x", 300, enter=False)
        _type(page, "", 700)
        page.wait_for_timeout(20)
        assert page.evaluate("() => window.__answer") == answer
        assert _seen(page)["buffer"] == "", answer


def test_two_glued_qrs_are_read_by_the_last(scan_page):
    """A stale cancel QR whose Enter a dialog ate, glued to the live confirm
    scanned after it: the live one answers (the session id holds no ':').
    Unpinned until round 6: an id read as "everything to the end" kept every
    test green and read the pair as one cancel with a session nobody had."""
    page = scan_page
    _fresh(page)
    sid = _open_swap(page)
    page.evaluate("(t) => window.processScan(t)", f"CMD:CANCEL:fcc-cqr-0-oldCMD:CONFIRM:{sid}")
    page.wait_for_function("() => window.__posts.length === 1")
    s = _seen(page)
    assert s["posts"] == ["/api/quickswap"] and not s["open"], s


PICKER_STUBS = r"""
window.showToast = function () {};
window.logClientEvent = function () {};
window.fetch = function () { return new Promise(() => {}); };     // the slots never load: the picker waits
"""


@pytest.fixture
def picker(isolated_page):
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=PICKER_STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "slot_picker.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    return page


def _open_picker(page):
    page.evaluate("""() => { window.__picked = undefined;
        window.openSlotPicker({ location: 'CR-MDB-1', spool: 6 }).then((r) => { window.__picked = r; }); }""")
    page.wait_for_selector("#fcc-slot-picker")


@pytest.mark.parametrize("left", ["", "q", "x"])
def test_a_key_left_in_front_of_the_pickers_own_cancel_never_stops_it(picker, left):
    """The slot picker's own "Scan to cancel" (a bare CMD:CANCEL) cancels it
    with a key a person left glued in front ('q', the Quick-Swap grid's key,
    say). RED on 5b5a18e: the picker read the scan from its start, refused it
    ("Ignored: qCMD:CANCEL") and stayed up. A stale session's cancel QR is
    still only flashed, however it starts."""
    page = picker
    _open_picker(page)
    assert page.evaluate("(t) => window.routePickerScan(t)", left + "CMD:CANCEL") is True
    page.wait_for_function("() => window.__picked === null")
    assert page.locator("#fcc-slot-picker").count() == 0
    _open_picker(page)
    assert page.evaluate("(t) => window.routePickerScan(t)", left + "CMD:CANCEL:fcc-cqr-1-x") is True
    page.wait_for_timeout(50)
    assert page.locator("#fcc-slot-picker").count() == 1 and page.evaluate("() => window.__picked") is None


# The slot picker on a model, as /api/placement_options answers (Group 57
# review, round 7): a box with four free slots, the same box named XLOC, and a
# printer with two empty heads.
_SLOTS = [{"blocked": None, "claimants": [], "current": False, "feeds": None, "free": True, "occupant_state": None,
           "slot": str(n), "spool": None, "stores_only": False, "swap_to": None, "would_prompt": False}
          for n in (1, 2, 3, 4)]
BOX_MODEL = {"allow_none": False, "location": "CR-MDB-1", "max_slots": 4, "mode": "box", "name": "CR box",
             "printers": [], "read_error": None, "read_ok": True, "recommend_reason": "no_prompt", "recommend_text": "",
             "recommended": {"box": "CR-MDB-1", "kind": "slot", "slot": "1"}, "slot_order": "ltr", "slots": _SLOTS,
             "spool": 6, "spool_display": "#6", "spool_location": "CR-CT-4", "toolhead": None, "type": "Dryer Box",
             "unslotted": []}
PRINTER_MODEL = {"heads": [{"current": False, "feeds": [], "id": f"XL-{n}", "position": n - 1, "resident": None,
                            "residents": []} for n in (1, 2)],
                 "location": "XL", "mode": "printer", "msg": "", "name": "XL", "pool": [], "printers": [],
                 "read_error": None, "read_ok": True, "recommend_reason": "several_free", "recommend_text": "",
                 "recommended": None, "self_head": False, "spool": 6, "spool_display": "#6",
                 "spool_keeps_trail": "", "spool_location": "CR-CT-4", "type": "Printer"}

MODEL_STUBS = r"""
window.showToast = function () {};
window.logClientEvent = function () {};
window.__hold = false;
window.__held = [];
window.fetch = function (url) {
    const loc = (new URL(String(url), 'http://x/')).searchParams.get('location');
    const body = window.__models[loc] || { read_ok: false, read_error: 'no model' };
    const answer = { ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(body))) };
    if (window.__hold) return new Promise((r) => window.__held.push(() => r(answer)));
    return Promise.resolve(answer);
};
"""


@pytest.fixture
def picker_models(isolated_page):
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=MODEL_STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "slot_picker.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    xloc = dict(BOX_MODEL, location="XLOC", name="XLOC", recommended={"box": "XLOC", "kind": "slot", "slot": "1"})
    shelf = dict(BOX_MODEL, location="GARAGE SHELF", name="GARAGE SHELF",
                 recommended={"box": "GARAGE SHELF", "kind": "slot", "slot": "1"})
    page.evaluate("(m) => { window.__models = m; }",
                  {"CR-MDB-1": BOX_MODEL, "XLOC": xloc, "GARAGE SHELF": shelf, "XL": PRINTER_MODEL})
    return page


@pytest.mark.parametrize("loc, scanned, hold, picked", [
    ("CR-MDB-1", "qLOC:CR-MDB-1:SLOT:2", False, {"box": "CR-MDB-1", "slot": "2"}),
    ("CR-MDB-1", "qLOC:CR-MDB-1:SLOT:2", True, {"box": "CR-MDB-1", "slot": "2"}),   # read while it loads
    ("XL", "qLOC:XL-1", False, {"head": "XL-1"}),
    ("XLOC", "LOC:XLOC:SLOT:2", False, {"box": "XLOC", "slot": "2"}),               # a box id ending in LOC
    ("CR-MDB-1", "LOC:BOXCMD:SLOT:2", False, None),                                 # another box, its id ending in CMD
    # Round 8: a LocationID may hold a Space (RED on b114fd7: "BOX CMD"'s label
    # read as CMD:SLOT:2, slot 2 of CR-MDB-1; GARAGE SHELF's own was refused).
    ("CR-MDB-1", "LOC:BOX CMD:SLOT:2", False, None),
    ("GARAGE SHELF", "qLOC:GARAGE SHELF:SLOT:2", False, {"box": "GARAGE SHELF", "slot": "2"}),
])
def test_the_picker_reads_a_scans_last_whole_label(picker_models, loc, scanned, hold, picked):
    """A slot's or a head's label with a key left in front ('qLOC:…') picks it,
    in box mode, in printer mode and read while the slots load. A box whose id
    ends in LOC or CMD is read whole: XLOC's own slot label picks its slot, and
    another box BOXCMD's slot label is refused, never a slot of the box the
    picker is for. RED on 4ac78d0 for the box ids (its last-"CMD:" read made
    LOC:BOXCMD:SLOT:2 into CMD:SLOT:2, slot 2 of CR-MDB-1, and refused XLOC's
    own label). The key-in-front cases were unpinned: the only test drove the
    picker's own cancel, whose slots never loaded."""
    page = picker_models
    page.evaluate("""([loc, hold]) => { window.__picked = undefined; window.__hold = hold; window.__held = [];
        window.openSlotPicker({ location: loc, spool: 6 }).then((r) => { window.__picked = r; }); }""", [loc, hold])
    page.wait_for_selector("#fcc-slot-picker")
    if not hold:
        page.wait_for_function("() => document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile').length > 0")
    # A refused label answers 'refused' (round 8: processScan doesn't count it
    # as that label's read).
    assert page.evaluate("(t) => window.routePickerScan(t)", scanned) == (True if picked else "refused")
    if hold:
        page.evaluate("() => { window.__hold = false; window.__held.forEach((f) => f()); }")
    page.wait_for_timeout(300)
    got = page.evaluate("""() => window.__picked === undefined ? 'open'
        : (window.__picked === null ? 'cancelled' : { box: window.__picked.box, slot: window.__picked.slot, head: window.__picked.head })""")
    if picked is None:
        assert got == "open" and page.locator("#fcc-slot-picker").count() == 1, got
    else:
        assert got != "open" and got != "cancelled", got
        assert {k: got.get(k) for k in picked} == picked, got


@pytest.mark.parametrize("text, label", [
    ("LOC:BOX CMD:SLOT:2", "LOC:BOX CMD:SLOT:2"),            # a Space in the id (round 8)
    ("qLOC:GARAGE SHELF:SLOT:2", "LOC:GARAGE SHELF:SLOT:2"),
    ("qLOC:GARAGE SHELF", "LOC:GARAGE SHELF"),
    ("ID:57 LOC:LR-MDB-1:SLOT:2", "LOC:LR-MDB-1:SLOT:2"),
    ("LOC:LR-MDB-1:SLOT:3LOC:LR-MDB-1:SLOT:2", "LOC:LR-MDB-1:SLOT:2"),
    ("LOC:XL-1 LOC:XL-2", "LOC:XL-2"),
    ("LOC:XL-1 CMD:CANCEL", "CMD:CANCEL"),
    ("LOC:BOXCMD:SLOT:2", "LOC:BOXCMD:SLOT:2"),
    ("ID:57", "ID:57"),
])
def test_a_scans_last_label(picker_models, text, label):
    """window.lastScanLabel, which the picker, the "Record it as coming from…"
    question and the double-read rule read: the whole label at the end of a
    scan, a LocationID with a Space in it too. RED on b114fd7 for the Space
    ids (the first three); the rest pin round 7's shapes."""
    assert picker_models.evaluate("(t) => window.lastScanLabel(t)", text) == label


# The slot picker behind the REAL scan router, inv_cmd.js's processScan (Group
# 57 review, round 8): what reaches the server is recorded.
PICKER_SCAN_STUBS = r"""
window.__posts = [];
window.fetch = function (url, opts) {
    url = String(url);
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    if (opts && opts.method && opts.method !== 'GET') window.__posts.push({ url, body });
    let ans = { status: 'success' };
    const model = url.includes('/api/placement_options');
    if (model) {
        const loc = (new URL(url, 'http://x/')).searchParams.get('location');
        ans = window.__models[loc] || { read_ok: false, read_error: 'no model' };
    } else if (url.includes('/api/identify_scan')) {
        ans = { type: 'error', msg: 'Unknown Code' };
    }
    const answer = { ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(ans))) };
    // The slots' read held until the test lets it go (window.__loadModels()).
    if (model && window.__holdModels) return new Promise((r) => window.__heldModels.push(() => r(answer)));
    return Promise.resolve(answer);
};
window.__holdModels = false;
window.__heldModels = [];
window.__loadModels = () => { const fs = window.__heldModels; window.__heldModels = []; fs.forEach((f) => f()); };
window.__si = window.setInterval; window.setInterval = () => 0;   // inv_cmd.js's 2 s buffer poll: off
"""


@pytest.fixture
def picker_scan(isolated_page):
    """The page, and open_(model): the picker opened for CR-MDB-1 on `model`."""
    page = isolated_page
    page.set_content("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>")
    page.add_script_tag(content=PICKER_SCAN_STUBS)
    for name in ("overlay_mount.js", "inv_core.js", "ui_builder.js", "slot_picker.js", "inv_cmd.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.add_script_tag(content="window.setInterval = window.__si;")

    def open_(model=BOX_MODEL, loaded=True):
        page.evaluate("(m) => { window.__models = m; }", {"CR-MDB-1": model})
        page.evaluate("""() => { window.__picked = undefined;
            window.openSlotPicker({ location: 'CR-MDB-1', spool: 6 }).then((r) => { window.__picked = r; }); }""")
        if loaded:
            page.wait_for_function("() => document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile').length > 0")
        else:
            page.wait_for_selector("#fcc-slot-picker")

    return page, open_


def _server_scans(page):
    return page.evaluate("() => window.__posts.filter((p) => p.url === '/api/identify_scan').map((p) => p.body.text)")


@pytest.mark.parametrize("first", ["qLOC:LR-MDB-1:SLOT:2", "LOC:LR-MDB-1:SLOT:2"])
def test_a_label_the_picker_refused_acts_once_it_has_closed(picker_scan, first):
    """The picker open for CR-MDB-1, another box's slot label scanned (a key
    in front, or none): refused. The picker cancelled, and the same label
    scanned on purpose a moment later: it goes to the server and acts. RED on
    b114fd7: the refused read counted as that label's read, and the deliberate
    scan, inside 1.5 s, was dropped as its second read."""
    page, open_ = picker_scan
    open_()
    page.evaluate("(t) => window.processScan(t, 'barcode')", first)
    assert page.locator("#fcc-slot-picker").count() == 1 and _server_scans(page) == []
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_function("() => window.__picked === null")
    page.wait_for_timeout(300)
    page.evaluate("() => window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_timeout(100)
    assert _server_scans(page) == ["LOC:LR-MDB-1:SLOT:2"]


def test_a_glued_read_the_picker_took_by_its_last_label_drops_the_second_read(picker_scan):
    """A scan whose Enter was lost, slot 2's label glued after it
    ('LOC:CR-MDB-1:SLOT:3LOC:CR-MDB-1:SLOT:2'): the picker picks slot 2, and
    the scanner's second read of slot 2's label 20 ms later is dropped. RED on
    b114fd7: the read was remembered as its whole text, so the second read went
    on to the server as a slot scan (one that loads the buffer's spool into
    that slot)."""
    page, open_ = picker_scan
    open_()
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:3LOC:CR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_function("() => window.__picked !== undefined")
    assert page.evaluate("() => window.__picked && window.__picked.slot") == "2"
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode', Date.now() + 20)")
    page.wait_for_timeout(100)
    assert _server_scans(page) == []


def test_a_label_the_picker_took_counts_as_read_for_one_and_a_half_seconds(picker_scan):
    """The picker takes 'qLOC:CR-MDB-1:SLOT:2' (a key left in front): the
    label read again a second later is dropped as the scanner's second read,
    and the label scanned 1.6 s after the first acts. Pins the window's end
    (round 8: a record that never ended passed every scan-path test, and would
    have dropped every later scan of the label, the hidden stop Derek ruled
    out)."""
    page, open_ = picker_scan
    open_()
    page.evaluate("() => window.processScan('qLOC:CR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_function("() => window.__picked !== undefined")
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode', Date.now() + 1000)")
    page.wait_for_timeout(50)
    assert _server_scans(page) == []
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode', Date.now() + 1600)")
    page.wait_for_timeout(100)
    assert _server_scans(page) == ["LOC:CR-MDB-1:SLOT:2"]


def test_a_label_the_pickers_swap_question_refused_acts_once_it_has_closed(picker_scan):
    """The picker asking what happens to slot 2's spool (#99 stored there: Swap,
    Overwrite or Back), another box's slot label scanned: refused. The picker
    cancelled, and the same label scanned on purpose a moment later: it goes to
    the server and acts. Pins the question's refusal as the grid's: it answers
    'refused', not a read."""
    page, open_ = picker_scan
    held = [dict(s) for s in _SLOTS]
    held[1] = dict(held[1], free=False, spool={"id": 99, "display": "Acme PLA Red"}, occupant_state="stored",
                   claimants=[99])
    open_(dict(BOX_MODEL, slots=held))
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_function("() => document.querySelectorAll('#fcc-slot-picker .fcc-sp-choice-btn').length > 0")
    page.evaluate("() => window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode')")
    assert page.locator("#fcc-slot-picker .fcc-sp-choice-btn").count() > 0 and _server_scans(page) == []
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_function("() => window.__picked === null")
    page.wait_for_timeout(300)
    page.evaluate("() => window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_timeout(100)
    assert _server_scans(page) == ["LOC:LR-MDB-1:SLOT:2"]


# Group 57 review, round 9: the refusals that still counted as a read.


def _cancel_then_scan_again(page, label):
    page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_function("() => window.__picked === null")
    page.wait_for_timeout(300)
    page.evaluate("(t) => window.processScan(t, 'barcode')", label)
    page.wait_for_timeout(100)


def test_a_greyed_out_tiles_label_the_picker_refused_acts_once_it_has_closed(picker_scan):
    """The picker open for CR-MDB-1, its slot 2 greyed out (its spool runs on
    another head), and slot 2's label scanned: refused, nothing picked. The
    picker cancelled, and the label scanned on purpose a moment later: it goes
    to the server. RED on 66f2c44: that refusal answered as a pick would, so
    the read counted as that label's, and the deliberate scan, inside 1.5 s,
    was dropped as its second read."""
    page, open_ = picker_scan
    slots = [dict(s) for s in _SLOTS]
    slots[1] = dict(slots[1], free=False, blocked="its spool #60 runs on XL-3")
    open_(dict(BOX_MODEL, slots=slots))
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__picked === undefined") and page.locator("#fcc-slot-picker").count() == 1
    _cancel_then_scan_again(page, "LOC:CR-MDB-1:SLOT:2")
    assert _server_scans(page) == ["LOC:CR-MDB-1:SLOT:2"]


@pytest.mark.parametrize("load", ["loaded", "failed"])
def test_a_label_held_while_the_picker_loads_and_then_refused_acts_once_it_has_closed(picker_scan, load):
    """The picker for CR-MDB-1 still loading its slots, and another box's slot
    label scanned (held, to be picked once they are drawn): once they are in,
    it is refused (not one of this box's slots), or they never come (a failed
    read) and it is refused too. The picker cancelled, and the label scanned on
    purpose a moment later: it goes to the server. RED on 66f2c44: the read
    counted as that label's from the moment it was held, and the deliberate
    scan was dropped as its second read."""
    page, open_ = picker_scan
    page.evaluate("() => { window.__holdModels = true; }")
    open_(BOX_MODEL if load == "loaded" else {"read_ok": False, "read_error": "Spoolman didn't answer"}, loaded=False)
    page.evaluate("() => window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode')")
    page.evaluate("() => { window.__holdModels = false; window.__loadModels(); }")
    page.wait_for_timeout(100)
    assert page.evaluate("() => window.__picked === undefined") and _server_scans(page) == [], load
    _cancel_then_scan_again(page, "LOC:LR-MDB-1:SLOT:2")
    assert _server_scans(page) == ["LOC:LR-MDB-1:SLOT:2"], load


@pytest.mark.parametrize("how", ["CMD:CANCEL", "Escape"])
def test_a_label_held_while_the_picker_loads_is_no_read_when_it_closes_first(picker_scan, how):
    """The picker for CR-MDB-1 still loading its slots, another box's slot
    label scanned (held, to be applied once they are drawn), and the picker
    closed before they come (CMD:CANCEL, or Escape): the label scanned on
    purpose a moment later goes to the server. RED on 2942ba1: the held read
    still counted as that label's, and the deliberate scan, inside 1.5 s, was
    dropped as its second read."""
    page, open_ = picker_scan
    page.evaluate("() => { window.__holdModels = true; }")
    open_(BOX_MODEL, loaded=False)
    page.evaluate("() => window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode')")
    if how == "Escape":
        page.keyboard.press("Escape")
    else:
        page.evaluate("() => window.processScan('CMD:CANCEL', 'barcode')")
    page.wait_for_function("() => window.__picked === null")
    page.evaluate("() => { window.__holdModels = false; window.__loadModels(); }")
    page.wait_for_timeout(300)
    page.evaluate("() => window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_timeout(100)
    assert _server_scans(page) == ["LOC:LR-MDB-1:SLOT:2"], how


def test_a_refused_read_between_a_pick_and_its_second_read_leaves_that_read_dropped(picker_scan):
    """Slot 2 picked by its label; the next spool's picker opens and refuses
    another box's slot label; then the scanner's second read of slot 2's label
    arrives: it is still dropped, never picking slot 2 for the next spool. Pins
    the refusal's hand-back of the read before it (round 8: b114fd7 picked the
    slot for the next spool)."""
    page, open_ = picker_scan
    open_()
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_function("() => window.__picked !== undefined")
    open_()                                           # the next spool's picker
    page.evaluate("() => window.processScan('LOC:LR-MDB-1:SLOT:2', 'barcode')")     # refused
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode', Date.now() + 20)")
    page.wait_for_timeout(100)
    assert page.evaluate("() => window.__picked === undefined") and page.locator("#fcc-slot-picker").count() == 1


def test_a_plain_label_the_picker_took_counts_as_read_for_one_and_a_half_seconds(picker_scan):
    """The picker takes 'LOC:CR-MDB-1:SLOT:2' as printed: read again a second
    later it is dropped as the scanner's second read; scanned 1.6 s after the
    first, it acts. Pins the window's end for a plain label (round 8 pinned
    only a key in front: a record that never ended would have dropped every
    later scan of the label, the hidden stop Derek ruled out)."""
    page, open_ = picker_scan
    open_()
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode')")
    page.wait_for_function("() => window.__picked !== undefined")
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode', Date.now() + 1000)")
    page.wait_for_timeout(50)
    assert _server_scans(page) == []
    page.evaluate("() => window.processScan('LOC:CR-MDB-1:SLOT:2', 'barcode', Date.now() + 1600)")
    page.wait_for_timeout(100)
    assert _server_scans(page) == ["LOC:CR-MDB-1:SLOT:2"]
