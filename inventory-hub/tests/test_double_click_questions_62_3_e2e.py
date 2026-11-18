"""Group 62.3: a real double click on the button that asks answers no question, on the
real dashboard with Bootstrap.

A question can open with its yes under the pointer; the second click of a double click on
the button that asked it then answers a question nobody has read. Where a question opens
depends on its words, the window size and the Text size (Group 58's lesson), so each case
here lays the button that asks exactly where the question's answer opens, measured from
the question itself (test_audit_done_question_58_e2e.py's LAY_AT): the worst place it can
be. Then a real mouse double click (GAP_MS apart) on it: the first click asks, and the
second must answer nothing; a click 700 ms later (a person who read it) answers.

Each door's real opener is called by the laid button:
  - the printing yes / no (window.confirmActivePrint, as every printing door shows it);
  - the three-way (window.confirmHeadLoad, as a slot scan onto a fed head shows it);
  - the Printer picker's head question and, after its "Load it instead", the "Record it as
    coming from…" question that opens where it was (inv_cmd.js's _confirmHeadPick and
    _askRecordSource);
  - the Quick-Swap confirm (window.quickSwapTap);
and the Print Queue's 📄 Send, whose window closes under the pointer once its files are
written: a second press while it sends sends nothing more, and one after it closed
reaches nothing behind it.

Read-only: every request that isn't a GET is answered in this browser and recorded, the
heartbeat is quieted, and no fixed id of dev's is used. The default arming is what runs
(the conftest's `window.fccQuestionArmMs = 0` for other tests is taken away here). RED on
the commit before 62.3 for every case: the second click answered.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.usefixtures("require_server")

SIZES = [(1366, 640), (1366, 768), (1280, 800), (1600, 900), (1600, 1300)]
GAP_MS = 120                 # a person's double click (Group 58's sweep's)
PAST_A_DOUBLE_PRESS = 750    # the 700 ms arming and a little

RECT = """(sel) => { const e = document.querySelector(sel); if (!e) return null;
    const r = e.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }; }"""
LAY_AT = r"""([sel, r]) => { const st = document.createElement('style'); st.id = 'fcc-test-lay-at';
    st.textContent = `${sel} { position: fixed !important; margin: 0 !important; left: ${r.left}px !important;
        top: ${r.top}px !important; width: ${r.right - r.left}px !important; height: ${r.bottom - r.top}px !important;
        z-index: 5 !important; }`;
    document.head.appendChild(st); }"""
UNLAY = "() => { const st = document.getElementById('fcc-test-lay-at'); if (st) st.remove(); }"
ON_TOP = """([x, y]) => { const e = document.elementFromPoint(x, y); const b = e && e.closest('button');
    return b ? (b.id || b.className) : (e ? (e.id || e.tagName) : ''); }"""

# An asker: a plain button on the page that runs a door's real opener when clicked.
ASKER = "#fcc-test-asker"
MAKE_ASKER = r"""(js) => { let b = document.getElementById('fcc-test-asker');
    if (!b) { b = document.createElement('button'); b.id = 'fcc-test-asker'; b.type = 'button'; b.textContent = 'Ask';
              document.body.appendChild(b); }
    b.onclick = new Function(js); }"""

FED = {"status": "requires_confirm", "confirm_type": "head_fed", "can_store": True, "target_slot": "1", "spools": [57],
       "fed_heads": [{"toolhead": "XL-1", "printer_name": "XL", "box": "LR-MDB-1", "slot": "1",
                      "resident": {"id": 99, "from": "PM-DB-2", "goes": "back to PM-DB-2"},
                      "residents": [{"id": 99, "from": "PM-DB-2", "goes": "back to PM-DB-2"}], "confirm_key": "XL-1#99"}],
       "active_prints": [], "active_print": None, "title": "Load #57 onto XL-1?",
       "body": "LR-MDB-1 slot 1 feeds XL-1, and XL-1 is running #99 (from PM-DB-2). Loading #57 sends #99 back to PM-DB-2."}

DOORS = {
    # door: (what the asker runs, the question's answer to lay it under, what an answer records)
    "yes-no": ("window.__said = window.__said || []; window.confirmActivePrint({"
               " activePrint: { toolhead: 'XL-3', printer_name: 'XL', state: 'PRINTING' },"
               " msg: 'Moving #57 now will disrupt the print. Continue?',"
               " onConfirm: () => window.__said.push('yes'), onCancel: () => window.__said.push('no') });",
               "#fcc-active-print-confirm-overlay .fcc-apc-yes"),
    "three-way": ("window.__said = window.__said || []; window.confirmHeadLoad({ answer: " + json.dumps(FED) + ","
                  " onLoad: () => window.__said.push('load'), onStore: () => window.__said.push('store'),"
                  " onCancel: () => window.__said.push('no') });",
                  "#fcc-active-print-confirm-overlay .fcc-apc-store"),
    "head-pick": ("window.__said = window.__said || []; const pick = { head: 'XL-1', spool_location: '',"
                  " resident: { id: 99, display: '#99' }, residents: [{ id: 99, display: '#99' }],"
                  " feeds: [{ box: 'LR-MDB-1', slot: '1', free: true }] };"
                  " _confirmHeadPick(pick, 57, null).then((ok) => { window.__said.push(ok ? 'load' : 'no');"
                  " return ok ? _askRecordSource(pick, 57, null) : null; })"
                  ".then((r) => { if (r !== null && r !== undefined) window.__said.push(JSON.stringify(r)); });",
                  "#fcc-head-pick-confirm .fcc-apc-yes"),
    "quick-swap": ("window.checkPrinterForHead = () => Promise.resolve({ active: false, known: true, state: 'IDLE', printer_name: 'XL' });"
                   " const b = document.createElement('button');"
                   " Object.assign(b.dataset, { toolhead: 'XL-1', box: 'LR-MDB-1', slot: '1', spoolId: '57' });"
                   " window.quickSwapTap(b);",
                   "#fcc-quickswap-yes"),
}


class Recorder:
    """Every request that isn't a GET answered here (an empty success) and recorded, but
    a read sent as a POST: the buffer cards' refresh (routes_state_pulse.api_spools_refresh)
    writes nothing, and goes out whenever dev's shared buffer holds a spool, which another
    test in a batch can leave there (the second review of Group 62: two of these were red
    in a batch, on `['/api/spools/refresh']`, and passed alone)."""

    READS = {"/api/spools/refresh"}

    def __init__(self, page: Page, delay_ms: int = 0):
        self.posts: list[tuple[str, object]] = []
        self.delay_ms = delay_ms
        page.route("**/*", self._handle)

    def _handle(self, route, request):
        if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
            route.continue_()
            return
        path = request.url.split("://", 1)[-1].split("/", 1)[-1].split("?")[0]
        if "/" + path in self.READS:
            route.continue_()
            return
        try:
            body = json.loads(request.post_data or "null")
        except ValueError:
            body = request.post_data
        self.posts.append(("/" + path, body))
        payload = {"success": True, "status": "success"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    def moves(self):
        return [p for p, _ in self.posts if p != "/api/log_event"]


def _dashboard(page: Page, base_url: str, width: int, height: int):
    import conftest   # local: keeps this file's header out of other branches' merges
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script("delete window.fccQuestionArmMs;")      # the default arming, here
    server = Recorder(page)
    conftest.quiet_heartbeat(page)
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.confirmActivePrint === 'function' && typeof window.quickSwapTap === 'function'"
                           " && typeof state !== 'undefined'", timeout=45_000)
    assert page.evaluate("() => window.fccQuestionArmMs") is None
    return server


def _press(page: Page, x: float, y: float, second: bool = False):
    count = 2 if second else 1
    page.mouse.move(x, y)
    page.mouse.down(click_count=count)
    page.mouse.up(click_count=count)


def _measure(page: Page, js: str, answer: str):
    """Where `answer` opens: the door asked once by script, measured, and put away."""
    page.evaluate(MAKE_ASKER, js)
    page.evaluate("() => document.getElementById('fcc-test-asker').onclick()")
    page.wait_for_selector(answer, state="visible", timeout=10_000)
    page.wait_for_timeout(250)                 # QR codes draw two frames later, and it moves
    box = page.evaluate(RECT, answer)
    page.keyboard.press("Escape")
    page.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    page.evaluate("() => { window.__said = []; }")
    return box


@pytest.mark.parametrize("size", SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
@pytest.mark.parametrize("door", list(DOORS))
def test_a_double_click_on_the_button_that_asks_answers_nothing(page: Page, base_url: str, door, size):
    server = _dashboard(page, base_url, *size)
    js, answer = DOORS[door]
    box = _measure(page, js, answer)
    x, y = (box["left"] + box["right"]) / 2, (box["top"] + box["bottom"]) / 2
    page.evaluate(LAY_AT, [ASKER, box])
    try:
        assert page.evaluate(ON_TOP, [x, y]) == ASKER[1:]
        _press(page, x, y)                          # the first click asks
        page.wait_for_selector(answer, state="visible", timeout=10_000)
        page.wait_for_timeout(GAP_MS)
        _press(page, x, y, second=True)             # the second lands on the answer
        page.wait_for_timeout(200)
        assert page.evaluate("() => window.__said || []") == [], f"{door}: the second click answered"
        assert server.moves() == [], f"{door}: the second click sent {server.moves()}"
        expect(page.locator(answer)).to_be_visible()
        page.wait_for_timeout(PAST_A_DOUBLE_PRESS)  # a person who has read it
        _press(page, x, y)
        if door == "quick-swap":
            page.wait_for_function("() => true")
            page.wait_for_timeout(200)
            assert server.moves() == ["/api/quickswap"]
        else:
            page.wait_for_function("() => (window.__said || []).length > 0")
            assert page.evaluate("() => window.__said")[0] in ("yes", "store", "load")
    finally:
        page.evaluate(UNLAY)


@pytest.mark.parametrize("size", [(1366, 768), (1600, 1300)], ids=["1366x768", "1600x1300"])
def test_load_it_instead_double_clicked_records_no_home_in_the_question_after_it(page: Page, base_url: str, size):
    """The Printer picker's head question, answered by a real double click on "Load it
    instead": the first click loads, and "Record it as coming from…" opens where the
    question was. Its pre-selected slot is laid under the pointer; the second click must
    record nothing. RED before 62.3: the slot was recorded as the spool's home."""
    server = _dashboard(page, base_url, *size)
    js, _ = DOORS["head-pick"]
    page.evaluate(MAKE_ASKER, js)
    page.evaluate("() => document.getElementById('fcc-test-asker').onclick()")
    load = "#fcc-head-pick-confirm .fcc-apc-yes"
    page.wait_for_selector(load, state="visible", timeout=10_000)
    page.wait_for_timeout(PAST_A_DOUBLE_PRESS)      # the question read: Load takes a click
    lbox = page.evaluate(RECT, load)
    x, y = (lbox["left"] + lbox["right"]) / 2, (lbox["top"] + lbox["bottom"]) / 2
    # The record-source question's pre-selected slot, laid where Load is (the worst place).
    slot = "#fcc-record-source .fcc-rs-opt[data-rs-i='0']"
    page.add_style_tag(content=f"{slot} {{ position: fixed !important; left: {lbox['left']}px !important;"
                               f" top: {lbox['top']}px !important; width: {lbox['right'] - lbox['left']}px !important;"
                               f" height: {lbox['bottom'] - lbox['top']}px !important; z-index: 30000 !important; }}")
    _press(page, x, y)
    page.wait_for_selector(slot, state="visible", timeout=10_000)
    page.wait_for_timeout(GAP_MS)
    _press(page, x, y, second=True)
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__said") == ["load"], "the second click recorded a home nobody read"
    expect(page.locator("#fcc-record-source")).to_be_visible()
    assert server.moves() == []


QUEUE_SEND = "#queueModal button[onclick*='printQueueCSV']"


@pytest.mark.parametrize("answer_ms", [0, 400], ids=["fast-answer", "slow-answer"])
def test_a_double_click_on_the_queues_send_sends_once_and_presses_nothing_behind(page: Page, base_url: str, answer_ms):
    """The Print Queue's 📄 Send closes its window once its files are written. A double
    click: while the first send is out, the second sends nothing more (slow answer); once
    the window has closed under the pointer, the second press reaches nothing behind it
    (fast answer: the deck's DROP tile is laid under Send, as something lies there on the
    dashboard). RED before 62.3: a second batch went out, or the tile behind was pressed."""
    import conftest
    page.set_viewport_size({"width": 1366, "height": 768})
    server = Recorder(page)
    conftest.quiet_heartbeat(page)
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.printQueueCSV === 'function' && typeof window.addToQueue === 'function'",
                           timeout=45_000)
    # The batch's answer comes `answer_ms` later, in the page itself: a route handler
    # that slept would stall the browser, and the second press with it.
    page.evaluate("""(ms) => { window.__batches = 0; const real = window.fetch;
        window.fetch = (url, opts) => {
            if (!String(url).includes('/api/print_batch_csv')) return real(url, opts);
            window.__batches += 1;
            return new Promise((r) => setTimeout(() => r(new Response(JSON.stringify({ success: true }),
                { status: 200, headers: { 'Content-Type': 'application/json' } })), ms));
        }; }""", answer_ms)
    page.evaluate("() => { labelQueue.length = 0; labelQueue.push({ id: 999701, type: 'spool', display: 'Test spool' });"
                  " window.updateQueueUI && window.updateQueueUI(); window.openQueueModal(); }")
    page.wait_for_selector(QUEUE_SEND, state="visible", timeout=10_000)
    page.wait_for_timeout(500)
    box = page.evaluate(RECT, QUEUE_SEND)
    x, y = (box["left"] + box["right"]) / 2, (box["top"] + box["bottom"]) / 2
    page.evaluate("() => { window.__deckPressed = 0; document.getElementById('btn-deck-drop')"
                  ".addEventListener('click', () => { window.__deckPressed += 1; }, true); }")
    if not answer_ms:
        page.evaluate(LAY_AT, ["#btn-deck-drop", box])
    try:
        _press(page, x, y)
        page.wait_for_timeout(GAP_MS if answer_ms else 450)    # the window closes, fast answer
        _press(page, x, y, second=True)
        page.wait_for_timeout(answer_ms + 500)
        sends = page.evaluate("() => window.__batches")
        assert sends == 1, f"{sends} batches went out"
        assert [p for p, _ in server.posts if p == "/api/print_batch_csv"] == []    # none reached dev
        assert page.evaluate("() => window.__deckPressed") == 0, "the second press reached the deck behind the window"
        assert page.evaluate("() => !!state.dropMode") is False
    finally:
        page.evaluate(UNLAY)
