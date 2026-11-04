"""Group 58 re-review, item 2g: a real double click on every control of an audit, at the
window sizes and list lengths where its buttons land on something, on the real dashboard
with Bootstrap.

A press that takes away, or brings, what lies under the pointer hands the second press of
a double click to whatever lies beneath: the deck behind the panel (Drop or Eject mode
armed, Undo asked, the weigh window, a new audit), the panel's own Cancel Audit under the
deck's AUDIT tile, the Last found strip's Needs a label under a tile. For every control, the
first click must do what one click does and the second nothing at all: the only request
sent is the first click's own, no command mode is armed, no window opened, and the
keyboard is where one click leaves it.

FCC's routes are answered in this browser on their real shapes (the audit's session,
question and answers, test_audit_page_58_js / test_audit_question_dialog_58_js), and every
request that isn't a GET is answered here and recorded, so nothing a stray press could do
reaches dev, and dev's own audit stays idle. A page per window size: each case puts the
page back as it was. The logic is pinned hermetically by test_audit_no_label_58_js.py's
double-click twins and test_audit_stacking_58_js.py's covers.

Derek's answers of 2026-11-03 add three: an Extra's tile, which a press takes back (A3,
`an-extra-tile`), the panel's 🔎 Find a spool, which a press opens over the panel (A2,
`find-open`), and a row of it, which a pick closes (`find-row`); and the panel's 🔎 button
among those a first click on the deck's AUDIT tile can bring up. The review of 7e3720f adds
Find's ↻ Try again (`try-again`, P-1), whose answer paints the rows under the pointer.
Their hermetic twins are in test_audit_find_and_tiles_58_js.py. Derek's second look
(2026-11-03, section H) adds a found tile's own 🏷️ (`a-tag`), whose mark grows its tile and
moves the tiles under it, and the Last found box's "↩ Put back" (`put-back`), which empties
the box; their hermetic twins are in test_audit_panel_look_58_js.py. Since the
dock (sample 1b), Done, Cancel Audit and Needs a label sit under the list, in view with no
scroll; when the panel comes up over the deck, only their QR boxes, which press nothing, lie
over its AUDIT tile at these five sizes, so where no button lands there `deck-tile` lays Cancel
Audit over the tile, as its hermetic twin in test_audit_no_label_58_js.py does, and its second
press waits until Cancel Audit is under the pointer: the shield that opens with the panel is
still proved on the real page.
"""
from __future__ import annotations

import json
import time

import pytest
from playwright.sync_api import Page

import conftest
from test_audit_page_58_e2e import _dashboard
from test_audit_page_58_js import SESSION, _row
from test_audit_find_and_tiles_58_js import search_row
from test_audit_question_dialog_58_js import _question
from test_scanner_safe_dialogs_61_js import LEGACY

pytestmark = pytest.mark.usefixtures("require_server")

SIZES = [(1366, 640), (1366, 768), (1280, 800), (1600, 900), (1600, 1300)]
LENGTHS = [3, 6, 10, 14, 24]
CONTROLS = ["done-ends", "done-asks", "cancel-audit", "hide", "needs-a-label", "a-tile", "undo-that",
            "back", "park", "deck-tile", "an-extra-tile", "find-open", "a-tag", "put-back"]
GAP_MS = 120                 # a person's double click (p12.py's)
SHIELD_S = 0.75              # DOUBLE_PRESS_MS (inv_cmd.js) and a little: a case starts past it

PANEL = "#fcc-audit-panel-overlay"
BODY = "#fcc-audit-panel-body"
QUESTION = "#fcc-audit-done-question"
CONTROL_SEL = {
    "done-ends": "#fcc-audit-panel-done", "done-asks": "#fcc-audit-panel-done",
    "cancel-audit": "#fcc-audit-panel-cancel", "hide": "#fcc-audit-panel-close",
    "needs-a-label": "#fcc-audit-panel-needlabel", "undo-that": "#fcc-audit-label-undo",
    "back": QUESTION + " .fcc-apc-no", "park": QUESTION + " .fcc-apc-yes", "deck-tile": "#btn-deck-audit",
    "find-open": "#fcc-audit-panel-find",
    "a-tag": "[data-audit-tag='100']", "put-back": "#fcc-audit-put-back",
}
# The panel's buttons a first click on the deck's AUDIT tile can bring up under the second.
PANEL_BUTTONS = ["#fcc-audit-panel-find", "#fcc-audit-panel-loose", "#fcc-audit-panel-close", "#fcc-audit-panel-done",
                 "#fcc-audit-panel-cancel", "#fcc-audit-panel-needlabel", ".fcc-audit-tile", ".fcc-audit-tile-tag",
                 "#fcc-audit-put-back"]

# What one click leaves: the requests it sends ((path, scan text)), the overlays up, and
# where the keyboard is.
ONE_CLICK = {
    "done-ends": ([("/api/identify_scan", "CMD:DONE")], [], "BODY"),
    "done-asks": ([("/api/identify_scan", "CMD:DONE")], [PANEL[1:], QUESTION[1:]], "back"),
    "cancel-audit": ([("/api/identify_scan", "CMD:CANCEL")], [], "BODY"),
    "hide": ([], [], "BODY"),
    "needs-a-label": ([("/api/identify_scan", "CMD:NEEDLABEL")], [PANEL[1:]], "fcc-audit-panel-needlabel"),
    "a-tile": ([("/api/audit/found", None)], [PANEL[1:]], "tile"),
    "undo-that": ([("/api/audit/needs_label_undo", None)], [PANEL[1:]], "fcc-audit-panel-needlabel"),
    "back": ([("/api/log_event", None)], [PANEL[1:]], "fcc-audit-panel-done"),
    "park": ([("/api/audit/park", None)], [], "BODY"),
    "deck-tile": ([], [PANEL[1:]], "BODY"),
    # Taken back, its tile goes: the keyboard is nowhere, as after any tile that goes.
    "an-extra-tile": ([("/api/audit/found", None)], [PANEL[1:]], "BODY"),
    # Find opens over the panel, its box takes the keyboard, and the second click finds it there.
    "find-open": ([], [PANEL[1:], "fcc-audit-find"], "find-box"),
    # A found tile's 🏷️: marked once, the keyboard kept on it through the redraw.
    "a-tag": ([("/api/audit/needs_label", None)], [PANEL[1:]], "tag:100"),
    # Put back: the find taken back once, and the keyboard nowhere, as after any button that goes.
    "put-back": ([("/api/audit/found", None)], [PANEL[1:]], "BODY"),
}

# What sits over the panel (item 2f): its first click closes it, and the second lands on
# the panel. Measured on this page at these sizes: the 🧺 list's ✕ lies on the panel's own
# 🧺 button and the ⌨️ list's ✕ on Hide, at every length; the legacy picker's buttons on the
# strip, or on tiles (1280 x 800 with 10 spools or more). A row of the 🧺 list opens nothing
# during an audit, so the list stays and takes the second click too.
COVERS = ["loose-close", "loose-row", "shortcut-close", "picker-use", "picker-print", "picker-cancel", "find-row",
          "try-again"]
COVER_LENGTHS = [6, 14]
LOOSE_LIST = "#fcc-loose-list"
PICKER = "#fcc-legacy-picker-overlay"
FIND = "#fcc-audit-find"
FIND_BOX = FIND + " [data-find-box]"
PICKED = 101                 # the first spool not found in every audit below: a Find row picks it
EXTRA = 900                  # the first Extra
COVER_CONTROL = {
    "loose-close": LOOSE_LIST + " [data-loose-close]", "loose-row": LOOSE_LIST + " .fcc-loose-row",
    "shortcut-close": "#fcc-shortcuts-overlay .btn-close", "picker-use": "#fcc-legacy-picker-use",
    "picker-print": "#fcc-legacy-picker-print", "picker-cancel": "#fcc-legacy-picker-cancel",
    "find-row": f"{FIND} .fcc-find-row[data-find-id='{PICKED}']",
    "try-again": f"{FIND} [data-find-retry]",
}
# One click's requests (None: Print new label's, the label queue's own, which it skips for a
# spool already queued), overlays and keyboard.
COVER_CLICK = {
    "loose-close": ([], [PANEL[1:]], "fcc-audit-panel-loose"),
    "loose-row": ([], [PANEL[1:], LOOSE_LIST[1:]], "loose-row"),
    "shortcut-close": ([], [PANEL[1:]], "fcc-audit-panel-done"),
    "picker-use": ([("/api/identify_scan", "ID:134")], [PANEL[1:]], "BODY"),
    "picker-print": (None, [PANEL[1:]], "BODY"),
    "picker-cancel": ([], [PANEL[1:]], "BODY"),
    # The pick, and the keyboard back on 🔎, which opened Find.
    "find-row": ([("/api/identify_scan", f"ID:{PICKED}")], [PANEL[1:]], "fcc-audit-panel-find"),
    # Review of 7e3720f, P-1: the search again (a GET, not recorded), its rows painted
    # where the button was, Find still up and the keyboard in its box.
    "try-again": ([], [PANEL[1:], FIND[1:]], "find-box"),
}
LABEL_QUEUE = {"/api/print_queue/set_flag", "/api/state/queue"}
LOOSE_SPOOLS = {"read_ok": True, "read_error": None, "count": 1, "places": [
    {"id": "A-ROOM", "name": "A Room", "type": "Room", "spools": [
        {"id": 8001, "display": "#8001 Some Brand PLA (Gold)", "color": "F9E352",
         "color_direction": "longitudinal", "remaining_weight": 912}]}]}


def _session(audit_id, rows, found, last=None, flagged=False, extras=0):
    """/api/audit_session's shape: `rows` expected, the first `found` found, and the Last
    found strip on row `last` (`flagged`: marked in this audit, so it shows undo that).
    `extras`: Extras found here, filed in another box."""
    expected = [_row(100 + n, str(n + 1), found=n < found) for n in range(rows)]
    rogue = [dict(_row(EXTRA + n, str(n + 1), found=True, rogue=True), location="LR-MDB-2",
                  where=f"LR-MDB-2 slot {n + 1}", at_done={"files": True}) for n in range(extras)]
    last_found = None
    if last is not None:
        last_found = dict(expected[last], label_read=True, flagged_here=flagged,
                          label_status=True if flagged else None)
    return dict(SESSION, audit_id=audit_id, expected=expected, rogue=rogue, trail=[], note="",
                stats={"total_expected": rows, "found": found, "missing": rows - found, "rogue": extras, "trail": 0},
                last_found=last_found)


class Sweep:
    """What this page hears from FCC. Every request that isn't a GET is answered here and
    recorded in `sent` ((path, the scan's text or None)), so nothing reaches dev but reads.
    Done answers the question (`asks`) or ends the audit; the answers keep the session in
    step, as the server's would."""

    def __init__(self, page):
        self.sent = []
        self.audit_id = None
        self.session = {"active": False, "audit_end": None}
        self.asks = False
        self.search_fails = False                       # Find's search answers success: false
        page.route("**/*", self._any)                   # first: the routes below win
        page.route("**/api/logs*", lambda route: self._json(route, self._payload()))
        page.route("**/api/dashboard_pulse*", lambda route: self._json(route, {"logs": self._payload()}))
        page.route("**/api/audit_session*", lambda route: self._json(route, self.session))
        page.route("**/api/identify_scan", self._scan)
        page.route("**/api/audit/found", self._found)
        page.route("**/api/audit/needs_label_undo", self._undo_that)
        page.route("**/api/audit/needs_label", self._tag)
        page.route("**/api/audit/park", self._park)
        page.route("**/api/loose_spools*", lambda route: self._json(route, LOOSE_SPOOLS))
        page.route("**/api/search*", self._search)

    @staticmethod
    def _json(route, body):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def _payload(self):
        on = bool(self.session.get("active"))
        return {"logs": [], "status": {"spoolman": True}, "audit_active": on,
                "audit_id": self.audit_id if on else None,
                "audit_location": "LR-MDB-1" if on else "", "audit_end": self.session.get("audit_end")}

    def _record(self, route, text=None):
        path = "/" + route.request.url.split("/", 3)[3].split("?")[0]
        self.sent.append((path, text))

    def _any(self, route):
        if route.request.method == "GET":
            route.continue_()
            return
        self._record(route)
        self._json(route, {"success": True, "status": "success"})

    def _end(self, why):
        end = {"id": self.audit_id, "why": why, "location": "LR-MDB-1"}
        self.session = {"active": False, "audit_end": end}
        return {"id": self.audit_id, "why": why}

    def _scan(self, route):
        text = (route.request.post_data_json or {}).get("text")
        self._record(route, text)
        answer = {"type": "command", "cmd": "audit_scan"}
        if text == "CMD:DONE":
            if self.asks:
                rows = self.session["expected"]
                answer = dict(_question(park=sum(1 for r in rows if not r["found"])), audit_id=self.audit_id)
            else:
                answer = dict(answer, audit_ended=self._end("done"))
        elif text == "CMD:CANCEL":
            answer = dict(answer, audit_ended=self._end("cancel"))
        elif text == "LEG:120":                         # a legacy label two spools share
            answer = LEGACY
        elif text.startswith("ID:") and self.session.get("active"):   # a Find pick: found, the last found
            self._turn(int(text[3:]), True)
        elif text == "CMD:NEEDLABEL" and self.session.get("last_found"):
            self.session = dict(self.session, last_found=dict(self.session["last_found"], flagged_here=True,
                                                              label_status=True))
            answer = dict(answer, said=f"#{self.session['last_found']['id']} needs a label: it is in the Backlog.")
        self._json(route, answer)

    def _turn(self, sid, found):
        """A spool found or taken back, as the routes turn the session: an Extra taken back
        leaves the Extras (and the strip, if it was there)."""
        rogue = self.session.get("rogue") or []
        if any(r["id"] == sid for r in rogue):
            if not found:
                rogue = [r for r in rogue if r["id"] != sid]
                last = self.session.get("last_found")
                self.session = dict(self.session, rogue=rogue, stats=dict(self.session["stats"], rogue=len(rogue)),
                                    last_found=None if last and last["id"] == sid else last)
            return
        if not any(r["id"] == sid for r in self.session.get("expected") or []):
            return                                      # off the list (the legacy picker's #134): as it was
        rows = [dict(r, found=found) if r["id"] == sid else r for r in self.session["expected"]]
        hit = next(r for r in rows if r["id"] == sid)
        n = sum(1 for r in rows if r["found"])
        last = self.session.get("last_found")
        if found:
            last = dict(hit, label_read=False, flagged_here=False)
        elif last and last["id"] == sid:                # taken back: nothing is selected, as the route leaves it
            last = None
        self.session = dict(self.session, expected=rows, last_found=last,
                            stats=dict(self.session["stats"], found=n, missing=len(rows) - n))

    def _found(self, route):
        self._record(route)
        body = route.request.post_data_json or {}
        self._turn(body.get("id"), bool(body.get("found")))
        self._json(route, {"success": True, "found": bool(body.get("found"))})

    def _search(self, route):
        """/api/search's answer on its real shape: every spool of the audit, newest first.
        `search_fails`: the strict search's answer when Spoolman didn't answer."""
        if self.search_fails:
            self._json(route, {"success": False, "msg": "Spoolman didn't answer (timed out)."})
            return
        rows = [search_row(r["id"], f"Red {r['id']}", "LR-MDB-1", r["slot"])
                for r in (self.session.get("expected") or [])]
        self._json(route, {"success": True, "results": sorted(rows, key=lambda r: -r["id"])})

    def _tag(self, route):
        """A found tile's 🏷️, as the route marks it: the row flagged here, the last found as it was."""
        self._record(route)
        sid = (route.request.post_data_json or {}).get("id")
        self.session = dict(self.session, expected=[dict(r, label_status=True, flagged_here=True) if r["id"] == sid else r
                                                    for r in self.session.get("expected") or []])
        self._json(route, {"success": True, "msg": f"#{sid} is marked: it needs a label."})

    def _undo_that(self, route):
        self._record(route)
        last = self.session.get("last_found")
        self.session = dict(self.session, last_found=dict(last, flagged_here=False, label_status=None))
        self._json(route, {"success": True, "msg": f"#{last['id']} is back as it was."})

    def _park(self, route):
        self._record(route)
        ids = (route.request.post_data_json or {}).get("ids") or []
        self._json(route, {"success": True, "parked": ids, "stayed": [], "failed": [],
                           "msg": f"Parked {len(ids)} spools at Unknown. Undo Last Move puts them back.",
                           "audit_ended": self._end("done")})


# Puts the page back as a case found it: no panel, no question, no mode, no window.
RESET = r"""() => {
    // A legacy picker left up holds every scan off until it is answered: its own Cancel.
    const picker = document.getElementById('fcc-legacy-picker-cancel');
    if (picker) picker.click();
    window.closeAuditPanel();
    window.resetCommandModes();
    document.querySelectorAll('.modal.show').forEach((el) => {
        try { bootstrap.Modal.getOrCreateInstance(el).hide(); } catch (_) { /* noop */ } });
    document.querySelectorAll('.offcanvas.show').forEach((el) => {
        try { bootstrap.Offcanvas.getOrCreateInstance(el).hide(); } catch (_) { /* noop */ } });
    document.querySelectorAll('.modal-backdrop, .offcanvas-backdrop').forEach((b) => b.remove());
    document.querySelectorAll('[data-overlay-mount="1"]').forEach((el) => el.remove());
    state.activeModal = null;
    const list = document.getElementById('fcc-shortcuts-overlay');
    if (list && list.style.display === 'block') window.toggleShortcutsOverlay();
    document.querySelectorAll('#toast-container .toast-msg').forEach((t) => t.remove());
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
}"""

# The audit this page believes in, its panel up: as a heartbeat that saw it start.
START = r"""([id]) => {
    state.auditActive = true;
    state.lastAuditState = true;
    state.auditId = id;
    state.auditLocation = 'LR-MDB-1';
    window.updateAuditVisuals();
}"""
# The same audit with its panel hidden (Hide), the AUDIT tile lit and the pill showing.
HIDDEN = r"""([id]) => {
    state.auditActive = true;
    state.lastAuditState = true;
    state.auditId = id;
    state.auditLocation = 'LR-MDB-1';
    window.updateAuditPill();
}"""

# The middle of what can be pressed of `sel` now: its box cut to the window and to the
# panel's scrolling body, then the point nearest that middle that hits it. null: none.
POINT = r"""(sel) => {
    const el = typeof sel === 'string' ? document.querySelector(sel) : sel;
    if (!el) return null;
    let r = el.getBoundingClientRect();
    let box = { left: Math.max(r.left, 0), top: Math.max(r.top, 0),
                right: Math.min(r.right, innerWidth), bottom: Math.min(r.bottom, innerHeight) };
    const body = el.closest('#fcc-audit-panel-body');
    if (body) {
        const b = body.getBoundingClientRect();
        box = { left: Math.max(box.left, b.left), top: Math.max(box.top, b.top),
                right: Math.min(box.right, b.right), bottom: Math.min(box.bottom, b.bottom) };
    }
    if (box.right - box.left < 2 || box.bottom - box.top < 2) return null;
    const cx = (box.left + box.right) / 2, cy = (box.top + box.bottom) / 2;
    const hits = (x, y) => { const e = document.elementFromPoint(x, y); return !!e && el.contains(e); };
    if (hits(cx, cy)) return [cx, cy];
    let best = null;
    for (let y = box.top + 2; y < box.bottom - 1; y += 4) {
        for (let x = box.left + 2; x < box.right - 1; x += 4) {
            if (!hits(x, y)) continue;
            const d = (x - cx) ** 2 + (y - cy) ** 2;
            if (!best || d < best[2]) best = [x, y, d];
        }
    }
    return best ? [best[0], best[1]] : null;
}"""

AFTER = r"""() => {
    const a = document.activeElement;
    const focus = !a || a === document.body ? 'BODY'
        : (a.classList.contains('fcc-apc-no') ? 'back' : (a.classList.contains('fcc-apc-yes') ? 'park'
        : (a.classList.contains('fcc-loose-row') ? 'loose-row'
        : (a.matches('[data-find-box]') ? 'find-box'
        : (a.dataset && a.dataset.auditTile ? 'tile:' + a.dataset.auditTile
        : (a.dataset && a.dataset.auditTag ? 'tag:' + a.dataset.auditTag : (a.id || a.tagName)))))));
    const list = document.getElementById('fcc-shortcuts-overlay');
    return {
        overlays: Array.from(document.querySelectorAll('[data-overlay-mount="1"]')).map((e) => e.id),
        windows: Array.from(document.querySelectorAll('.modal.show, .offcanvas.show')).map((e) => e.id)
            .concat(document.querySelector('.swal2-container') ? ['swal'] : [])
            .concat(list && list.style.display === 'block' ? ['shortcut-list'] : []),
        modes: { drop: !!state.dropMode, eject: !!state.ejectMode },
        focus,
        audit: !!state.auditActive,
    };
}"""


# Every double-press window the page keeps (the shields, a tile's and the strip's own, the
# question's yes) reads Date.now(); the heartbeat's order and its staleness don't (the page
# clock is performance.now(), and the stale mark a timer). So a case starts past them as a
# person who waited would, with the page's Date.now() moved on instead of a sleep. Never
# inside a case: a double click's two presses are 120 ms apart in real time.
SKEW = r"""() => {
    if (window.__fccSkew !== undefined) return;
    const real = Date.now.bind(Date);
    window.__fccSkew = 0;
    Date.now = () => real() + window.__fccSkew;
}"""


class Board:
    """One page at one window size."""

    def __init__(self, page: Page, server: Sweep, size):
        self.page, self.server, self.size = page, server, size
        self.pressed = 0.0
        self.cases = 0
        page.evaluate(SKEW)

    def settle(self):
        """Past the windows a press left open: the next press is a person's first."""
        self.page.evaluate("(ms) => { window.__fccSkew += ms; }", int(SHIELD_S * 1000))

    def double_click(self, xy):
        x, y = xy
        self.page.mouse.move(x, y)
        self.page.mouse.down(click_count=1)
        self.page.mouse.up(click_count=1)
        self.page.wait_for_timeout(GAP_MS)
        self.page.mouse.down(click_count=2)
        self.page.mouse.up(click_count=2)
        self.pressed = time.monotonic()

    def double_click_over(self, xy, brought):
        """A double click whose first press brings `brought` (a selector) under the
        pointer: its second press waits for it to be there, as when an answer comes
        inside a person's double click, and stays a double click by the clock too."""
        x, y = xy
        self.page.mouse.move(x, y)
        start = time.monotonic()
        self.page.mouse.down(click_count=1)
        self.page.mouse.up(click_count=1)
        self.page.wait_for_function("([x, y, sel]) => { const e = document.elementFromPoint(x, y);"
                                    " return !!(e && e.closest(sel)); }", arg=[x, y, brought], timeout=600)
        assert time.monotonic() - start < SHIELD_S - 0.1, "the second press came too late to be one"
        self.page.mouse.down(click_count=2)
        self.page.mouse.up(click_count=2)
        self.pressed = time.monotonic()

    def click(self, xy):
        self.page.mouse.click(*xy)
        self.pressed = time.monotonic()

    def begin(self, rows, found, last=None, flagged=False, asks=False, extras=0):
        """A new audit of `rows` spools (and `extras` Extras), its panel up and drawn."""
        page, server = self.page, self.server
        self.settle()
        page.evaluate(RESET)
        self.cases += 1
        server.audit_id = f"boot-{self.cases}"
        server.asks = asks
        server.session = _session(server.audit_id, rows, found, last, flagged, extras)
        page.evaluate(START, [server.audit_id])
        page.wait_for_function("(n) => document.querySelectorAll('.fcc-audit-tile').length === n", arg=rows + extras)
        if last is not None:
            page.wait_for_selector("#fcc-audit-last-found")
        page.wait_for_timeout(120)              # the panel's QR codes draw two frames later

    def redraw(self, rows, found, last=None, flagged=False):
        self.server.session = _session(self.server.audit_id, rows, found, last, flagged)
        self.page.evaluate("window.refreshAuditSession()")
        want = "!!document.querySelector('#fcc-audit-last-found')" if last is not None \
            else "!document.querySelector('#fcc-audit-last-found')"
        self.page.wait_for_function(f"() => {want}")
        self.page.wait_for_timeout(120)


@pytest.fixture(scope="module", params=SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
def board(request, browser, base_url, require_server):
    """The real dashboard at one window size, for every case at that size."""
    width, height = request.param
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.set_default_timeout(15_000)
    server = Sweep(page)
    conftest.own_the_buffer(page, [])
    _dashboard(page, base_url)
    page.wait_for_function("() => state.lastAuditState === false", timeout=30_000)
    try:
        yield Board(page, server, request.param)
    finally:
        try:
            page.unroute_all(behavior="ignoreErrors")
        except Exception:
            pass
        context.close()


def _scrolled_into_view(page, sel):
    """What can be pressed of `sel`, the body scrolled to its end first when nothing of it
    can (as a person would): an Extra's tile below the fold. Done, Cancel Audit and Needs a
    label sit in the dock under the list since Derek's 2026-11-03 look (sample 1b), in view
    with no scroll; they ended the body before."""
    if page.evaluate(POINT, sel) is None:
        page.evaluate("(b) => { const e = document.querySelector(b); e.scrollTop = e.scrollHeight; }", BODY)
        page.wait_for_timeout(60)
    return page.evaluate(POINT, sel)


def _tile_under_the_strip(board, rows):
    """The tile where Needs a label will land once a spool is found (finding 8: the sticky
    strip came up over the tiles), else the last tile on screen; and where to press it: on
    that spot. In the dock (sample 1b) it lands on no tile, but a first find moves the
    pressed tile to Found, slides the next one into its place and can grow the dock, so
    the last tile on screen is where the second press lands on something new."""
    page = board.page
    board.redraw(rows, 1, last=0)
    mark = page.evaluate(POINT, CONTROL_SEL["needs-a-label"])
    board.redraw(rows, 0)
    if mark:
        hit = page.evaluate("""([x, y]) => { const e = document.elementFromPoint(x, y);
            const t = e && e.closest('[data-audit-tile]'); return t ? t.dataset.auditTile : null; }""", mark)
        if hit:
            return hit, mark
    visible = page.evaluate("""() => Array.from(document.querySelectorAll('.fcc-audit-tile')).filter((t) => {
        const r = t.getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !!e && t.contains(e); }).map((t) => t.dataset.auditTile)""")
    sid = visible[-1]
    return sid, page.evaluate(POINT, f"[data-audit-tile='{sid}']")


def _deck_bands(board, rows):
    """Where the panel's buttons land on the deck's AUDIT tile when the panel comes up: the band
    of each that overlaps it, as {name: (x, y)}, with the panel hidden again."""
    page = board.page
    tile = page.evaluate("""() => { const r = document.querySelector('#btn-deck-audit').getBoundingClientRect();
        return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }; }""")
    bands = page.evaluate("""([sels, tile]) => {
        const out = {};
        for (const sel of sels) {
            document.querySelectorAll(sel).forEach((b, i) => {
                const r = b.getBoundingClientRect();
                const left = Math.max(r.left, tile.left), right = Math.min(r.right, tile.right);
                const top = Math.max(r.top, tile.top), bottom = Math.min(r.bottom, tile.bottom);
                if (right - left < 4 || bottom - top < 4) return;
                const x = (left + right) / 2, y = (top + bottom) / 2;
                const e = document.elementFromPoint(x, y);
                if (!e || !b.contains(e)) return;               // under the strip or scrolled away
                out[b.id || ('tile:' + b.dataset.auditTile)] = [x, y];
            });
        }
        return out; }""", [PANEL_BUTTONS, tile])
    page.evaluate("window.closeAuditPanel()")
    page.wait_for_selector(PANEL, state="detached")
    return bands


# Cancel Audit laid over the deck's AUDIT tile, for a size where no button of the panel lands
# there when it comes up (the dock, sample 1b). Answers the tile's middle.
LAY_CANCEL_OVER_TILE = r"""() => { const r = document.querySelector('#btn-deck-audit').getBoundingClientRect();
    const st = document.createElement('style'); st.id = 'fcc-test-lay-cancel';
    st.textContent = `#fcc-audit-panel-cancel { position: fixed !important; margin: 0 !important; left: ${r.left}px !important;
        top: ${r.top}px !important; width: ${r.width}px !important; height: ${r.height}px !important; z-index: 5 !important; }`;
    document.head.appendChild(st);
    return [r.left + r.width / 2, r.top + r.height / 2]; }"""


def _after(board, expected_requests, overlays, focus, what):
    """The second press did nothing: one click's requests, overlays and keyboard."""
    page = board.page
    page.wait_for_function("() => !state.processing && !(state.scanQueue || []).length")
    page.wait_for_timeout(250)
    got = page.evaluate(AFTER)
    sent = [(p, t) if p == "/api/identify_scan" else (p, None) for p, t in board.server.sent]
    if expected_requests is None:               # the label queue's, and only its
        assert all(p in LABEL_QUEUE for p, _ in sent), f"{what}: requests {sent}"
    else:
        assert sent == expected_requests, f"{what}: requests {sent}"
    assert got["overlays"] == overlays, f"{what}: overlays {got['overlays']}"
    assert got["windows"] == [], f"{what}: a window opened: {got['windows']}"
    assert got["modes"] == {"drop": False, "eject": False}, f"{what}: a mode armed: {got['modes']}"
    assert got["focus"] == focus, f"{what}: the keyboard is on {got['focus']}"
    return got


@pytest.mark.parametrize("control", CONTROLS)
@pytest.mark.parametrize("rows", LENGTHS, ids=[f"{n}-spools" for n in LENGTHS])
def test_a_real_double_click_does_what_one_click_does(board, rows, control):
    page, server = board.page, board.server
    requests, overlays, focus = ONE_CLICK[control]
    what = f"{board.size[0]}x{board.size[1]}, {rows} spools, {control}"

    if control == "deck-tile":
        board.begin(rows, 1, last=0)
        bands = _deck_bands(board, rows)
        laid = not bands
        if laid:                                    # the dock: lay Cancel Audit over the tile
            bands = {"fcc-audit-panel-cancel, laid over the tile": page.evaluate(LAY_CANCEL_OVER_TILE)}
        try:
            for name, xy in bands.items():
                board.settle()
                page.evaluate(RESET)
                page.evaluate(HIDDEN, [server.audit_id])
                assert page.evaluate("(xy) => !!document.elementFromPoint(xy[0], xy[1]).closest('#btn-deck-audit')", xy)
                server.sent.clear()
                if laid:                            # the second press lands on Cancel Audit
                    board.double_click_over(xy, "#fcc-audit-panel-cancel")
                else:
                    board.double_click(xy)
                page.wait_for_selector(PANEL)
                _after(board, requests, overlays, focus, f"{what} (where {name} lands)")
                assert page.evaluate("state.auditActive") is True, f"{what} (where {name} lands): the audit ended"
        finally:
            page.evaluate("() => { const st = document.getElementById('fcc-test-lay-cancel'); if (st) st.remove(); }")
        return

    if control == "a-tile":
        board.begin(rows, 0)
        sid, xy = _tile_under_the_strip(board, rows)
        focus = f"tile:{sid}"
    elif control in ("done-asks", "back", "park"):
        board.begin(rows, min(2, rows - 1), last=0, asks=True)
        if control != "done-asks":
            done = _scrolled_into_view(page, CONTROL_SEL["done-asks"])
            assert done, f"{what}: Done can't be pressed"
            board.click(done)
            page.wait_for_selector(QUESTION + " .fcc-apc-no")
            board.pressed = time.monotonic()    # the yes takes no click for 700 ms from here
            page.wait_for_timeout(200)          # its QR codes, and the question settled
            board.settle()
        xy = page.evaluate(POINT, CONTROL_SEL[control]) if control != "done-asks" \
            else _scrolled_into_view(page, CONTROL_SEL[control])
    elif control == "done-ends":
        board.begin(rows, rows, last=rows - 1)
        xy = _scrolled_into_view(page, CONTROL_SEL[control])
    elif control == "undo-that":
        board.begin(rows, 1, last=0, flagged=True)
        xy = page.evaluate(POINT, CONTROL_SEL[control])
    elif control == "find-open":                    # A2: its first press opens Find over the panel
        board.begin(rows, 1, last=0)
        xy = page.evaluate(POINT, CONTROL_SEL[control])
    elif control == "an-extra-tile":                # A3: its first press takes it back
        board.begin(rows, 1, last=0, extras=2)
        xy = _scrolled_into_view(page, f"[data-audit-tile='{EXTRA}']")
    elif control == "a-tag":                        # P6: its first press marks the spool, and grows its tile
        board.begin(rows, 1, last=0)
        xy = _scrolled_into_view(page, CONTROL_SEL[control])
    elif control == "put-back":                     # P7: its first press empties the Last found box
        board.begin(rows, min(2, rows), last=0)
        xy = page.evaluate(POINT, CONTROL_SEL[control])
    else:                                       # cancel-audit, hide, needs-a-label
        board.begin(rows, 1, last=0)
        xy = _scrolled_into_view(page, CONTROL_SEL[control])
    assert xy, f"{what}: the control can't be pressed"

    server.sent.clear()
    board.double_click(xy)
    _after(board, requests, overlays, focus, what)
    ends = control in ("done-ends", "cancel-audit", "park")
    assert page.evaluate("state.auditActive") is (not ends), f"{what}: the audit is {'on' if not ends else 'over'}"


def _cover_up(board, cover):
    """What `cover` belongs to, up over the panel as a person brings it up."""
    page = board.page
    if cover.startswith("loose"):
        board.click(page.evaluate(POINT, "#fcc-audit-panel-loose"))
        page.wait_for_selector(LOOSE_LIST + " .fcc-loose-row")
        board.pressed = time.monotonic()        # past the press that opened it
        board.settle()
    elif cover == "find-row":                       # A2: a pick closes it
        board.click(page.evaluate(POINT, "#fcc-audit-panel-find"))
        page.wait_for_selector(FIND_BOX)
        page.fill(FIND_BOX, str(PICKED))          # its number: its row comes first (the search finds them all)
        page.wait_for_selector(COVER_CONTROL[cover])
        board.pressed = time.monotonic()        # past the press that opened it
        board.settle()
    elif cover == "try-again":                      # P-1: a search that failed, Spoolman back
        board.server.search_fails = True
        board.click(page.evaluate(POINT, "#fcc-audit-panel-find"))
        page.wait_for_selector(FIND_BOX)
        page.fill(FIND_BOX, str(PICKED))
        page.wait_for_selector(COVER_CONTROL[cover])
        board.server.search_fails = False
        board.pressed = time.monotonic()
        board.settle()
    elif cover == "shortcut-close":
        page.focus("#fcc-audit-panel-done")     # where the keyboard was: it comes back there
        page.keyboard.press("?")
        page.wait_for_function("() => document.getElementById('fcc-shortcuts-overlay').style.display === 'block'")
    else:
        page.evaluate("() => window.processScan('LEG:120', 'barcode')")
        page.wait_for_selector(PICKER)
        page.wait_for_timeout(150)
        if cover != "picker-cancel":
            page.select_option("#fcc-legacy-picker-sel", "134")


@pytest.mark.parametrize("cover", COVERS)
@pytest.mark.parametrize("rows", COVER_LENGTHS, ids=[f"{n}-spools" for n in COVER_LENGTHS])
def test_a_real_double_click_on_what_sits_over_the_panel_presses_nothing_on_it(board, rows, cover):
    """Item 2f. RED before the re-review's fix: the 🧺 list's ✕ opened the list again, the ⌨️
    list's ✕ hid the panel, and at 1280 x 800 the picker's buttons found a spool nobody
    had touched. `try-again` (review of 7e3720f, P-1): Find's ↻ Try again, whose answer
    paints the rows under the pointer before the second press; RED on e7886e9, where
    that press picked the row (ID:<its spool>) and closed Find."""
    page, server = board.page, board.server
    requests, overlays, focus = COVER_CLICK[cover]
    what = f"{board.size[0]}x{board.size[1]}, {rows} spools, {cover}"
    board.begin(rows, 1, last=0)
    _cover_up(board, cover)
    xy = page.evaluate(POINT, COVER_CONTROL[cover])
    assert xy, f"{what}: the control can't be pressed"
    server.sent.clear()
    if cover == "try-again":
        board.double_click_over(xy, f"{FIND} .fcc-find-row")
    else:
        board.double_click(xy)
    _after(board, requests, overlays, focus, what)
    if cover == "try-again":
        assert page.evaluate("(s) => document.querySelectorAll(s).length", f"{FIND} .fcc-find-row") == rows, what
    assert page.evaluate("state.auditActive") is True, f"{what}: the audit ended"
    assert page.evaluate("() => document.querySelectorAll('.fcc-audit-tile').length") == rows
