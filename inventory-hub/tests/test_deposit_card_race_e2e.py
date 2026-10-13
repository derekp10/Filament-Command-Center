"""Group 46.1: the Location Manager's DEPOSIT card deposited the PREVIOUS spool.

Derek, on prod (2026-10-08): "if you're too fast, you end up assigning the spool
you were previously on, instead of the spool you actively have in the center of
the carousel."

Mechanism (traced 2026-10-12): prev/next rotates state.heldSpools and dispatches
inventory:buffer-updated. The Location Manager listener re-rendered the carousel
(renderManagerNav) synchronously, but the DEPOSIT card was rebuilt only when
refreshManageView's /api/get_contents fetch resolved, and its click handler
captured the spool at render time (`doAssign(locId, item.id, null)` with
`item = state.heldSpools[0]`). While that fetch was outstanding, the centre card
showed the new spool and a DEPOSIT click wrote the old one.

The in-page fetch-delay lever (Group 38) makes the window deterministic: delay
/api/get_contents inside the page, rotate, click.

HERMETIC AGAINST DEV DATA: one context route answers every non-GET synthetically
and records it (including POST /api/state/buffer and /api/manage_contents);
GET /api/state/buffer serves the buffer the page last persisted to the fake;
GET /api/get_contents for FCC-TEST-* is stubbed; GET /api/locations passes
through read-only with a fake FCC-TEST-* row appended. Spool ids are fake
(9992xx). The fake location is a Cart, so doAssign never probes a printer.

HEAD proof: on the pre-fix inv_loc_mgr.js, test_deposit_click_writes_the_centre_spool
deposits #999201 (the previous spool) and test_deposit_card_redraws_synchronously
sees #999201 on the card for the whole delay.
"""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

LOC = "FCC-TEST-DEPOSIT-CART"
LOC_ROW = {"LocationID": LOC, "Name": "FCC Test Deposit Cart", "Type": "Cart", "Max Spools": ""}
OTHER = "FCC-TEST-OTHER-CART"
OTHER_ROW = {"LocationID": OTHER, "Name": "FCC Test Other Cart", "Type": "Cart", "Max Spools": ""}
A = {"id": 999201, "display": "FCC Test PLA #999201", "color": "ff0000"}
B = {"id": 999202, "display": "FCC Test PETG #999202", "color": "00ff00"}
OK = {"success": True}

pytestmark = pytest.mark.usefixtures("require_server")

# Delays /api/get_contents inside the page, the way a slow Spoolman (or a
# printer probe during an active print) delays it on prod. Group 38's lever:
# patch window.fetch rather than sleeping in a route handler, which would
# stall Playwright's sync dispatcher.
DELAY_CONTENTS_JS = """(ms) => {
    if (window.__fccDelayInstalled) return;
    window.__fccDelayInstalled = true;
    const orig = window.fetch;
    window.fetch = (url, opts) => {
        const u = typeof url === 'string' ? url : (url && url.url) || '';
        if (u.startsWith('/api/get_contents')) {
            return new Promise(resolve => setTimeout(() => resolve(orig(url, opts)), ms));
        }
        return orig(url, opts);
    };
}"""

DEPOSIT_CARD_TEXT_JS = """() => {
    const list = document.getElementById('manage-contents-list');
    if (!list) return null;
    const card = Array.from(list.querySelectorAll('.cham-card'))
        .find(c => (c.textContent || '').includes('DEPOSIT HERE'));
    return card ? card.textContent : null;
}"""

CLICK_DEPOSIT_JS = """() => {
    const list = document.getElementById('manage-contents-list');
    const card = Array.from(list.querySelectorAll('.cham-card'))
        .find(c => (c.textContent || '').includes('DEPOSIT HERE'));
    if (!card) throw new Error('no DEPOSIT card');
    card.click();
}"""


class FakeBackend:
    """Answers every non-GET synthetically (and records it); stubs the GETs
    whose real dev data would make these tests nondeterministic."""

    def __init__(self, page: Page):
        self.posts: list[tuple[str, dict]] = []
        self.buffer: list = []
        page.context.route("**/*", self._handle)

    @staticmethod
    def _json(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _handle(self, route):
        try:
            self._route(route)
        except PlaywrightError as e:
            # A heartbeat still in flight when the context closes.
            if "closed" not in str(e).lower():
                raise

    def _route(self, route):
        req = route.request
        parts = urlsplit(req.url)
        path = parts.path
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if path == "/api/state/buffer":
                self._json(route, self.buffer)
                return
            if path.startswith("/api/printer_state/"):
                self._json(route, {"known": True, "is_active": False, "state": "IDLE",
                                   "printer_name": "FCC Test Printer"})
                return
            if path == "/api/get_contents":
                loc = (parse_qs(parts.query).get("id") or [""])[0].upper()
                if loc.startswith("FCC-TEST-"):
                    self._json(route, [])
                    return
            if path == "/api/locations" and req.method == "GET":
                resp = route.fetch()
                rows = resp.json()
                if isinstance(rows, list):
                    have = {r.get("LocationID") for r in rows if isinstance(r, dict)}
                    rows.extend(dict(r) for r in (LOC_ROW, OTHER_ROW) if r["LocationID"] not in have)
                self._json(route, rows, status=resp.status)
                return
            route.continue_()
            return
        try:
            body = json.loads(req.post_data or "{}")
        except (TypeError, ValueError):
            body = {}
        if not isinstance(body, dict):
            body = {"_raw": body}
        self.posts.append((path, body))
        if path == "/api/state/buffer":
            buf = body.get("buffer")
            self.buffer = buf if isinstance(buf, list) else []
            payload = OK
        elif path == "/api/manage_contents":
            payload = {"status": "success"}
        elif path == "/api/identify_scan":
            # A Quick-Swap deposit: answer as the route would, for the spool named.
            moved = body.get("spool_id") or A["id"]
            payload = {"type": "assignment", "action": "assignment_done", "location": "FCC-TEST-BOX",
                       "slot": "2", "moved": moved}
        else:
            payload = OK
        self._json(route, payload)

    def bodies(self, path: str) -> list[dict]:
        return [b for p, b in self.posts if p == path]


@pytest.fixture(autouse=True)
def _drop_routes_in_flight(page: Page):
    """A route callback still running at context close otherwise surfaces its
    TargetClosedError in the NEXT test's setup. Close the page FIRST: un-routing
    a live page lets its next buffer poll or persist reach the real dev server."""
    yield
    try:
        page.close()
    except PlaywrightError:
        pass
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _until(page: Page, predicate, timeout_ms: int, what: str) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return
        page.wait_for_timeout(50)   # pumps the event loop so route handlers run
    assert predicate(), what


def _open_with_buffer(page: Page, base_url: str, reset_dom_state_js: str) -> FakeBackend:
    be = FakeBackend(page)
    page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded")
    page.wait_for_function(
        "typeof state !== 'undefined' && typeof modals !== 'undefined' && !!modals.manageModal"
        " && typeof window.openManage === 'function' && typeof window.nextBuffer === 'function'"
        " && typeof window.doAssign === 'function' && typeof window.renderBuffer === 'function'",
        timeout=20_000,
    )
    page.evaluate(reset_dom_state_js)
    page.wait_for_function(
        f"(state.allLocations || []).some(l => l.LocationID === {json.dumps(LOC)})",
        timeout=15_000,
    )
    page.evaluate("(spools) => { state.heldSpools = spools; renderBuffer(); }", [A, B])
    _until(page, lambda: [s.get("id") for s in be.buffer if isinstance(s, dict)] == [A["id"], B["id"]],
           5_000, "the seeded buffer was never persisted (to the fake)")
    page.evaluate("(id) => window.openManage(id)", LOC)
    page.wait_for_function("document.getElementById('manageModal').classList.contains('show')",
                           timeout=10_000)
    page.wait_for_function(
        f"(() => {{ const t = ({DEPOSIT_CARD_TEXT_JS})(); return !!t && t.includes('#{A['id']}'); }})()",
        timeout=10_000,
    )
    return be


def test_deposit_click_writes_the_centre_spool(page: Page, base_url, reset_dom_state_js):
    """Rotate, then click DEPOSIT while /api/get_contents is still outstanding:
    the deposit must write the spool now in the centre of the carousel."""
    be = _open_with_buffer(page, base_url, reset_dom_state_js)
    page.evaluate(DELAY_CONTENTS_JS, 4_000)

    page.evaluate("() => window.nextBuffer()")
    centre = page.evaluate("() => state.heldSpools[0].id")
    assert centre == B["id"], f"nextBuffer should put #{B['id']} in the centre, got #{centre}"

    page.evaluate(CLICK_DEPOSIT_JS)
    _until(page, lambda: be.bodies("/api/manage_contents"), 5_000,
           "the DEPOSIT click never POSTed /api/manage_contents")
    body = be.bodies("/api/manage_contents")[0]
    assert body.get("action") == "add" and body.get("location") == LOC, body
    assert body.get("spool_id") == f"ID:{B['id']}", (
        f"DEPOSIT wrote {body.get('spool_id')!r} — the PREVIOUS spool — although "
        f"#{B['id']} was in the centre of the carousel (Group 46.1)")


def test_deposit_card_redraws_synchronously(page: Page, base_url, reset_dom_state_js):
    """The card itself must follow the carousel at once, not when the delayed
    /api/get_contents fetch finally lands."""
    _open_with_buffer(page, base_url, reset_dom_state_js)
    page.evaluate(DELAY_CONTENTS_JS, 4_000)

    page.evaluate("() => window.nextBuffer()")
    text = page.evaluate(DEPOSIT_CARD_TEXT_JS)
    assert text and f"#{B['id']}" in text, (
        f"right after nextBuffer the DEPOSIT card still reads {text!r}; it must name "
        f"#{B['id']}, the spool in the centre of the carousel")
    assert f"#{A['id']}" not in text, text

    # The card's QR is the location's (LOC:<id>), so a redraw must keep it.
    has_qr = page.evaluate(
        "() => { const q = document.getElementById('qr-deposit-trigger'); return !!q; }")
    assert has_qr, "the redrawn DEPOSIT card lost its LOC: QR placeholder"


def test_deposit_card_disappears_when_the_buffer_empties(page: Page, base_url, reset_dom_state_js):
    """Emptying the buffer removes the card at once, and a click on a card that
    was rendered for a buffer that is now empty must not POST anything."""
    be = _open_with_buffer(page, base_url, reset_dom_state_js)
    page.evaluate(DELAY_CONTENTS_JS, 4_000)

    # Keep a handle on the card as rendered, then empty the buffer.
    page.evaluate("""() => {
        const list = document.getElementById('manage-contents-list');
        window.__staleDepositCard = Array.from(list.querySelectorAll('.cham-card'))
            .find(c => (c.textContent || '').includes('DEPOSIT HERE'));
        state.heldSpools = [];
        renderBuffer();
    }""")
    assert page.evaluate(DEPOSIT_CARD_TEXT_JS) is None, \
        "the DEPOSIT card is still on screen after the buffer emptied"

    page.evaluate("() => { if (window.__staleDepositCard) window.__staleDepositCard.click(); }")
    page.wait_for_timeout(300)
    assert not be.bodies("/api/manage_contents"), (
        "a click on a DEPOSIT card rendered for a now-empty buffer still POSTed "
        f"{be.bodies('/api/manage_contents')}")


# --------------------------------------------------------------------------- #
# Found by the Group 46 adversarial review                                    #
# --------------------------------------------------------------------------- #

QS_DEPOSIT_JS = """([box, slot, th]) => {
    let btn = document.getElementById('fcc-test-deposit-btn');
    if (!btn) {
        btn = document.createElement('button');
        btn.id = 'fcc-test-deposit-btn';
        btn.className = 'fcc-qs-slot';
        btn.dataset.box = box; btn.dataset.slot = slot; btn.dataset.toolhead = th;
        btn.hidden = true;
        document.body.appendChild(btn);
    }
    window.quickSwapDeposit(btn);
}"""


def test_quickswap_deposit_writes_the_spool_its_confirm_named(page: Page, base_url, reset_dom_state_js):
    """The Quick-Swap deposit names the buffered spool in its confirm, but used to
    post only LOC:<box>:SLOT:<n>, so the server deposited the first spool of its
    buffer replica. Rotate the carousel while the confirm is up, press Yes: the
    POST must still name the spool the confirm showed."""
    be = _open_with_buffer(page, base_url, reset_dom_state_js)
    page.evaluate(QS_DEPOSIT_JS, ["FCC-TEST-BOX", "2", "FCC-TEST-TH"])
    page.wait_for_selector("#fcc-quickswap-yes", timeout=8_000)
    title = page.evaluate("() => document.getElementById('fcc-quickswap-confirm-title').textContent")
    assert f"#{A['id']}" in title, title
    page.evaluate("() => window.nextBuffer()")
    assert page.evaluate("() => state.heldSpools[0].id") == B["id"]
    page.click("#fcc-quickswap-yes")
    _until(page, lambda: be.bodies("/api/identify_scan"), 5_000, "Yes never posted the deposit")
    body = be.bodies("/api/identify_scan")[0]
    assert body.get("spool_id") == A["id"], (
        f"the confirm named #{A['id']} but the deposit posted {body}")


def test_a_late_render_for_another_location_does_not_paint_over_the_open_one(
        page: Page, base_url, reset_dom_state_js):
    """A pulse or refresh fetched for the PREVIOUS location used to repaint the open
    view with it, and its DEPOSIT card then wrote into the old location."""
    be = _open_with_buffer(page, base_url, reset_dom_state_js)
    page.wait_for_function(
        f"(state.allLocations || []).some(l => l.LocationID === {json.dumps(OTHER)})", timeout=10_000)
    painted = page.evaluate(f"() => window._renderManagePayload({json.dumps(OTHER)}, [])")
    assert painted is False, "a payload for another location was painted into the open view"
    page.evaluate(CLICK_DEPOSIT_JS)
    _until(page, lambda: be.bodies("/api/manage_contents"), 5_000, "the DEPOSIT click never posted")
    assert be.bodies("/api/manage_contents")[0]["location"] == LOC
