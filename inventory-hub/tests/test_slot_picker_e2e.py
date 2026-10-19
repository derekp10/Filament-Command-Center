"""Group 40.1 — the shared slot picker (static/js/modules/slot_picker.js) in a
real browser, over stubbed data.

HERMETIC AGAINST DEV DATA: a context route answers /api/placement_options with
a model built by the REAL placement.build_placement_options (fixed rows +
spools, so the stub can't drift from what the server sends), answers
/api/printer_state/* with a fixed state, serves an empty buffer, and answers
every non-GET synthetically (recorded, never forwarded). The picker has no
caller yet (40.2, 40.4-40.7 wire it in); these tests open it the way a caller
will: window.openSlotPicker(opts) and the Promise it returns.

Pinned here: the keys (arrows wrap, a digit only highlights, Enter picks,
Escape cancels), scan-to-select (a slot label, CMD:SLOT:n, a head label, a pool
slot label), the refusal of every other scan while the picker is open, a
scanner burst's Enter left to the scan, the per-printer "checking…" state and
its timeout, an unreadable Spoolman, an rtl box, the printer and return modes,
the bulk-move guard, the host-close cancel, and no text input anywhere.

HEAD proof: slot_picker.js and /api/placement_options don't exist on HEAD, so
every test here fails there (window.openSlotPicker is undefined).
"""
from __future__ import annotations

import copy
import json
import re
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

import placement

pytestmark = pytest.mark.usefixtures("require_server")

PRINTER = "FCC Test XL"


def _box(lid, max_spools, targets, **extra):
    return {"LocationID": lid, "Name": f"{lid} (test)", "Type": "Dryer Box", "Max Spools": str(max_spools),
            "extra": {"slot_targets": targets, **extra}}


ROWS = [
    {"LocationID": "FCCX", "Name": PRINTER, "Type": "Printer", "Max Spools": "0",
     "toolheads": [{"location_id": f"FCCX-{i}", "position": i - 1} for i in (1, 2, 3)]},
    *[{"LocationID": f"FCCX-{i}", "Name": f"FCCX-{i}", "Type": "Tool Head", "Max Spools": "1"} for i in (1, 2, 3)],
    _box("FCC-TEST-BOX", 4, {"1": "FCCX-1", "2": "FCCX-2", "3": "FCCX-3", "4": "PRINTER:FCCX"}),
    _box("FCC-TEST-RTL", 3, {}, slot_order="rtl"),
    _box("FCC-TEST-PM", 1, {}),
    {"LocationID": "FCC-TEST-SHELF", "Name": "Shelf (test)", "Type": "Shelf", "Max Spools": "0"},
]


def _sp(sid, loc, slot="", src="", src_slot="", name="Test Red", color="cc2222"):
    extra = {}
    if slot:
        extra["container_slot"] = str(slot)
    if src:
        extra["physical_source"] = src
    if src_slot:
        extra["physical_source_slot"] = str(src_slot)
    return {"id": sid, "location": loc, "remaining_weight": 640, "extra": extra,
            "filament": {"name": name, "material": "PLA", "color_hex": color, "vendor": {"name": "FCC Test"}}}


SPOOLS = [
    _sp(999202, "FCC-TEST-BOX", slot=2, name="Test Blue", color="2255cc"),
    _sp(999299, "FCCX-1", src="FCC-TEST-PM", src_slot=1, name="Test Green", color="22aa44"),
    _sp(999201, "FCC-TEST-SHELF"),
]


def build_model(location, rows=ROWS, spools=SPOOLS, fail=False, **kwargs):
    """The model the real server would answer for these rows + spools."""
    def _list(*a, **k):
        if fail:
            raise placement.spoolman_api.requests.ConnectionError("Spoolman down (test)")
        return copy.deepcopy(spools)
    by_id = {s["id"]: s for s in spools}
    with ExitStack() as st:
        st.enter_context(patch.object(placement.locations_db, "load_locations_list",
                                      side_effect=lambda *a, **k: copy.deepcopy(rows)))
        st.enter_context(patch.object(placement.spoolman_api, "get_all_spools_strict", side_effect=_list))
        st.enter_context(patch.object(placement.spoolman_api, "get_spool",
                                      side_effect=lambda sid: copy.deepcopy(by_id.get(int(sid)))))
        st.enter_context(patch.object(placement.locations_db, "is_descendant", return_value=False))
        model, status = placement.build_placement_options(location, **kwargs)
    assert status == 200, model
    return model


class PickerStub:
    """Answers the picker's GETs from fixed models and every non-GET with a
    synthetic OK (recorded). `models`: {location or (location, mode): model, or a
    callable(query) -> model}. `answers` (Group 40.2): {path: callable(body) ->
    payload or None} for the POSTs a door test needs answered (None: the
    synthetic OK). The buffer endpoint is the page's own (it starts as `buffer`
    and follows the page's saves), never dev's shared one."""

    def __init__(self, page: Page, models, printer_state=None, answers=None, buffer=None):
        self.models = dict(models)
        self.printer_state = printer_state or (lambda head: {
            "known": True, "is_active": False, "state": "IDLE", "printer_name": PRINTER})
        self.answers = dict(answers or {})
        self.buffer = list(buffer or [])
        self.queries: list[dict] = []
        self.probes: list[str] = []
        self.posts: list[tuple[str, dict]] = []
        page.context.route("**/*", self._handle)

    @staticmethod
    def _json(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def _handle(self, route):
        try:
            self._route(route)
        except PlaywrightError as e:
            if "closed" not in str(e).lower():
                raise

    def _route(self, route):
        req = route.request
        parts = urlsplit(req.url)
        path = parts.path
        if req.method in ("GET", "HEAD", "OPTIONS"):
            if path == "/api/placement_options":
                q = {k: v[0] for k, v in parse_qs(parts.query).items()}
                self.queries.append(q)
                key = (q.get("location", "").upper(), q.get("mode", ""))
                model = self.models.get(key, self.models.get(key[0]))
                if model is None:
                    self._json(route, {"error": "not_found", "msg": "not in this stub"}, 404)
                    return
                self._json(route, model(q) if callable(model) else model)
                return
            if path.startswith("/api/printer_state/"):
                head = unquote(path[len("/api/printer_state/"):])
                self.probes.append(head)
                self._json(route, self.printer_state(head))
                return
            if path == "/api/state/buffer":
                self._json(route, self.buffer)
                return
            route.continue_()
            return
        try:
            body = json.loads(req.post_data or "{}")
        except (TypeError, ValueError):
            body = {}
        self.posts.append((path, body if isinstance(body, dict) else {"_raw": body}))
        if path == "/api/state/buffer" and isinstance(body, dict):
            self.buffer = list(body.get("buffer") or [])
        answer = self.answers.get(path)
        payload = answer(body) if answer else None
        self._json(route, payload if payload is not None else {"success": True})

    def posted(self, path):
        return [b for p, b in self.posts if p == path]


# An in-page delay on the printer probe (the Group 38 lever): the route answers
# at once, the page's fetch waits `window.__printerDelayMs` first.
DELAY_JS = """
(() => {
  const real = window.fetch.bind(window);
  window.__printerDelayMs = 0;
  window.__placementDelayMs = 0;
  window.fetch = (url, opts) => {
    const u = String(url && url.url ? url.url : url);
    if (u.includes('/api/printer_state/') && window.__printerDelayMs > 0) {
      return new Promise((r) => setTimeout(r, window.__printerDelayMs)).then(() => real(url, opts));
    }
    if (u.includes('/api/placement_options') && window.__placementDelayMs > 0) {
      return new Promise((r) => setTimeout(r, window.__placementDelayMs)).then(() => real(url, opts));
    }
    return real(url, opts);
  };
  window.__toastLog = [];
  const append = Node.prototype.appendChild;
  Node.prototype.appendChild = function (child) {
    const out = append.call(this, child);
    if (child && child.nodeType === 1 && child.classList && child.classList.contains('toast-msg')) {
      const cls = Array.from(child.classList).find(c => c.startsWith('toast-') && c !== 'toast-msg');
      window.__toastLog.push({ text: child.textContent, type: cls ? cls.slice(6) : null });
    }
    return out;
  };
})();
"""

OPEN_JS = """(opts) => {
  window.__pick = undefined; window.__pickDone = false;
  window.openSlotPicker(opts).then((r) => { window.__pick = r; window.__pickDone = true; });
}"""

READY = "#fcc-slot-picker [data-sp-state='ready']"
CHOICE = "#fcc-slot-picker [data-sp-state='choice']"
STATUS = "#fcc-slot-picker .fcc-sp-status"
# The highlighted tile is `arg` (a slot, a head or a kind).
ACTIVE_IS = """(want) => { const t = document.querySelector('#fcc-slot-picker .fcc-sp-tile.kb-active');
  return !!t && (t.dataset.spSlot || t.dataset.spHead || t.dataset.spKind) === want; }"""


@pytest.fixture
def picker_page(page: Page, base_url, request):
    """The dashboard with the stub installed; returns (page, open, stub)."""
    from conftest import quiet_heartbeat

    holder = {}

    def _setup(models, printer_state=None, answers=None, buffer=None):
        stub = PickerStub(page, models, printer_state=printer_state, answers=answers, buffer=buffer)
        quiet_heartbeat(page)
        page.add_init_script(DELAY_JS)
        page.goto(base_url)
        page.wait_for_function("() => typeof window.openSlotPicker === 'function'"
                               " && typeof window.processScan === 'function'", timeout=15_000)
        holder["stub"] = stub
        return stub

    def _open(opts, ready=True):
        page.evaluate(OPEN_JS, opts)
        if ready:
            page.wait_for_selector(READY, timeout=10_000)

    yield page, _setup, _open
    try:
        page.close()
    except PlaywrightError:
        pass
    try:
        page.context.unroute_all(behavior="ignoreErrors")
    except PlaywrightError:
        pass


def _pick(page, timeout=5_000):
    page.wait_for_function("() => window.__pickDone === true", timeout=timeout)
    return page.evaluate("() => window.__pick")


def _active(page):
    return page.evaluate("() => { const t = document.querySelector('#fcc-slot-picker .fcc-sp-tile.kb-active');"
                         " return t ? (t.dataset.spSlot || t.dataset.spHead || t.dataset.spKind) : null; }")


def _order(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#fcc-slot-picker .fcc-sp-tile'))"
                         ".map(t => t.dataset.spSlot || t.dataset.spHead || t.dataset.spKind)")


# ---- box mode: render + keys -------------------------------------------------------------------

def test_box_picker_shows_the_slots_and_highlights_the_star(picker_page):
    page, setup, open_ = picker_page
    model = build_model("FCC-TEST-BOX", spool=999201)
    # Slot 1's head runs #999299 from a PolyDryer, slot 2 is taken: the ⭐ is slot 3.
    assert model["recommended"]["slot"] == "3"
    setup({"FCC-TEST-BOX": model})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    assert _order(page) == ["1", "2", "3", "4"]
    assert _active(page) == "3"
    tile1 = page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='1']")
    expect(tile1).to_contain_text("→ FCCX-1")
    expect(tile1).to_contain_text("FCCX-1 runs #999299 (from FCC-TEST-PM)")
    expect(page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']")).to_contain_text("#999202")
    expect(page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='3']")).to_contain_text("Recommended")
    expect(page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='4']")).to_contain_text("Printer Pool")
    expect(page.locator("#fcc-slot-picker")).to_contain_text("Which slot of FCC-TEST-BOX should #999201 go in?")
    # Mounted through mountOverlay, with no text input anywhere (an input disarms the scanner).
    assert page.evaluate("() => document.getElementById('fcc-slot-picker').dataset.overlayMount") == "1"
    assert page.locator("#fcc-slot-picker input, #fcc-slot-picker textarea").count() == 0


def test_arrows_wrap_a_digit_highlights_and_enter_picks(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.keyboard.press("ArrowRight")
    assert _active(page) == "4"
    page.keyboard.press("ArrowRight")
    assert _active(page) == "1"      # wraps
    page.keyboard.press("ArrowLeft")
    assert _active(page) == "4"
    page.keyboard.press("ArrowUp")
    assert _active(page) == "3"
    page.keyboard.press("2")         # highlights after a 50 ms beat (D1), never picks
    page.wait_for_function(ACTIVE_IS, arg="2", timeout=2_000)
    assert page.evaluate("() => window.__pickDone") is False
    # A lone digit is dropped from the scan buffer once nothing followed it.
    page.wait_for_function("() => state.scanBuffer === ''", timeout=2_000)
    page.keyboard.press("Enter")
    # Deliberately changed (Group 40.2, Q2 + D4): slot 2 holds #999202, so Enter
    # asks what happens to it first; Swap is the first answer and has the focus.
    page.wait_for_selector(CHOICE, timeout=5_000)
    assert page.evaluate("() => window.__pickDone") is False
    page.keyboard.press("Enter")
    got = _pick(page)
    assert got["kind"] == "slot" and got["box"] == "FCC-TEST-BOX" and got["slot"] == "2"
    assert got["occupant"]["id"] == 999202 and got["free"] is False and got["via"] == "key"
    assert got["choice"] == "swap" and got["send"] == {"slot": "2"} and got["swap"] is True
    expect(page.locator("#fcc-slot-picker")).to_have_count(0)


def test_escape_cancels_and_a_click_picks(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.keyboard.press("Escape")
    assert _pick(page) is None
    expect(page.locator("#fcc-slot-picker")).to_have_count(0)
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='4']").click()
    got = _pick(page)
    assert got["slot"] == "4" and got["via"] == "click" and got["feeds"]["kind"] == "pool"


# ---- scans ---------------------------------------------------------------------------------------

def test_a_slot_label_scan_picks_that_slot_and_reaches_no_server_door(picker_page):
    page, setup, open_ = picker_page
    stub = setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.evaluate("() => processScan('LOC:FCC-TEST-BOX:SLOT:4', 'barcode')")
    got = _pick(page)
    assert got["kind"] == "slot" and got["slot"] == "4" and got["via"] == "scan"
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.evaluate("() => processScan('CMD:SLOT:1', 'barcode')")
    assert _pick(page)["slot"] == "1"
    assert stub.posted("/api/identify_scan") == []


def test_any_other_scan_is_refused_while_the_picker_is_open(picker_page):
    page, setup, open_ = picker_page
    stub = setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    for text in ("ID:999201", "LOC:FCC-TEST-SHELF", "LOC:OTHER-BOX:SLOT:1", "CMD:EJECT"):
        page.evaluate("(t) => processScan(t, 'barcode')", text)
    toasts = page.evaluate("() => window.__toastLog")
    refusals = [t for t in toasts if "Finish or cancel the slot picker first" in t["text"]]
    assert len(refusals) == 4 and all(t["type"] == "warning" for t in refusals), toasts
    assert page.evaluate("() => window.__pickDone") is False
    assert stub.posted("/api/identify_scan") == []
    # The refusal is in the Activity Log too.
    logged = [b.get("msg", "") for b in stub.posted("/api/log_event")]
    assert sum("Finish or cancel the slot picker first" in m for m in logged) == 4
    page.evaluate("() => processScan('CMD:CANCEL', 'barcode')")
    assert _pick(page) is None


def test_a_scanner_bursts_enter_is_the_scans_not_the_highlights(picker_page):
    """The highlight sits on slot 3 (the ⭐). A scanner types slot 1's label at
    scanner speed and ends it with Enter: that Enter submits the scan (slot 1),
    and must not also pick the highlight."""
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    assert _active(page) == "3"
    page.keyboard.type("LOC:FCC-TEST-BOX:SLOT:1", delay=0)
    page.keyboard.press("Enter")
    got = _pick(page)
    assert got["slot"] == "1" and got["via"] == "scan", got


# ---- printers ----------------------------------------------------------------------------------

def test_each_printer_reads_checking_then_its_state(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)},
          printer_state=lambda head: {"known": True, "is_active": True, "state": "PRINTING", "printer_name": PRINTER})
    page.evaluate("() => { window.__printerDelayMs = 1500; }")
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    chip = page.locator("#fcc-slot-picker .fcc-sp-pchip .fcc-sp-pstate")
    expect(chip).to_have_text("checking…")
    expect(page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='1'] .fcc-sp-pstate")).to_have_text("checking…")
    expect(chip).to_have_text("printing", timeout=5_000)
    expect(page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='1'] .fcc-sp-pstate")).to_have_class(
        "fcc-sp-pstate is-printing")


def test_a_printer_that_never_answers_reads_couldnt_reach(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    page.evaluate("() => { window.__printerDelayMs = 6000; }")   # past the 3 s client budget
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    chip = page.locator("#fcc-slot-picker .fcc-sp-pchip .fcc-sp-pstate")
    expect(chip).to_have_text("checking…")
    expect(chip).to_have_text("couldn't reach", timeout=6_000)


def test_printer_mode_picks_a_head_or_a_pool_slot_by_scan(picker_page):
    page, setup, open_ = picker_page
    model = build_model("FCCX", spool=999201)
    setup({"FCCX": model})
    open_({"location": "FCCX", "spool": 999201})
    assert _order(page) == ["FCCX-1", "FCCX-2", "FCCX-3", "4"]
    expect(page.locator("#fcc-slot-picker .fcc-sp-section")).to_contain_text("PRINTER POOL")
    head1 = page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-head='FCCX-1']")
    expect(head1).to_contain_text("FCCX-1 runs #999299 (from FCC-TEST-PM)")
    expect(head1).to_contain_text("Fed by FCC-TEST-BOX slot 1 (free)")
    page.evaluate("() => processScan('LOC:FCCX-2', 'barcode')")
    got = _pick(page)
    assert got["kind"] == "head" and got["head"] == "FCCX-2" and got["printer"] == "FCCX"
    assert got["feeds"] == [{"box": "FCC-TEST-BOX", "slot": "2", "spool": got["feeds"][0]["spool"],
                             "claimed_by": 999202, "free": False}]
    open_({"location": "FCCX", "spool": 999201})
    page.evaluate("() => processScan('LOC:FCC-TEST-BOX:SLOT:4', 'barcode')")
    got = _pick(page)
    assert got["kind"] == "pool" and got["box"] == "FCC-TEST-BOX" and got["slot"] == "4"
    # Group 40.5: a free Printer Pool slot is sent as a pick, with its (no-head) feed.
    assert got["send"] == {"picked_slot": "4"} and got["expected_feed"] == "", got


def test_an_occupied_printer_pool_slot_asks_swap_or_overwrite(picker_page):
    """Group 40.5: a Printer Pool slot is a box slot like any other (Q2): one that
    holds a stored spool asks Swap / Overwrite, and a Swap is sent as the
    engine's Overwrite `slot` with `swap` (Swap option C)."""
    page, setup, open_ = picker_page
    spools = SPOOLS + [_sp(999244, "FCC-TEST-BOX", slot=4, name="Test Grey", color="777777")]
    setup({"FCCX": build_model("FCCX", spools=spools, spool=999201)})
    open_({"location": "FCCX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-kind='pool'][data-sp-slot='4']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    labels = page.evaluate("() => Array.from(document.querySelectorAll('#fcc-slot-picker [data-sp-choice]'))"
                           ".map(b => b.dataset.spChoice)")
    assert labels == ["swap", "overwrite", "back"], labels
    page.locator("#fcc-slot-picker [data-sp-choice='swap']").click()
    got = _pick(page)
    assert got["kind"] == "pool" and got["send"] == {"slot": "4"} and got["swap"] is True, got
    assert got["displaced"]["id"] == 999244 and got["expected_feed"] == "", got


def test_a_printer_pool_slot_whose_spool_is_loaded_elsewhere_is_greyed_out(picker_page):
    """Group 40.5: the engine refuses a slot whose own spool runs on a head, so the
    picker greys the pool tile out and says why, as in box mode."""
    page, setup, open_ = picker_page
    spools = SPOOLS + [_sp(999245, "FCCX-2", src="FCC-TEST-BOX", src_slot=4, name="Test Grey", color="777777")]
    setup({"FCCX": build_model("FCCX", spools=spools, spool=999201)})
    open_({"location": "FCCX", "spool": 999201})
    tile = page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-kind='pool'][data-sp-slot='4']")
    expect(tile).to_have_class(re.compile(r"\bis-blocked\b"))
    expect(tile).to_contain_text("#999245 from this slot is loaded on FCCX-2")
    tile.click(force=True)
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__pickDone") is False


# ---- return mode, rtl, unreadable ----------------------------------------------------------------

def test_return_mode_offers_no_slot_and_names_the_overcount(picker_page):
    page, setup, open_ = picker_page
    spools = SPOOLS + [_sp(999203, "FCC-TEST-BOX", slot=1), _sp(999204, "FCC-TEST-BOX", slot=3),
                       _sp(999205, "FCC-TEST-BOX", slot=4), _sp(999206, "FCCX-2")]
    model = build_model("FCC-TEST-BOX", spools=spools, spool=999206, toolhead="FCCX-2", mode="return")
    assert model["recommended"] == {"kind": "none", "box": "FCC-TEST-BOX"}
    setup({("FCC-TEST-BOX", "return"): model})
    open_({"location": "FCC-TEST-BOX", "spool": 999206, "toolhead": "FCCX-2", "mode": "return"})
    assert _order(page) == ["1", "2", "3", "4", "none"]
    assert _active(page) == "none"
    none = page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-kind='none']")
    expect(none).to_contain_text("FCC-TEST-BOX will show 5/4")
    expect(page.locator("#fcc-slot-picker")).to_contain_text("Return #999206 to which slot of FCC-TEST-BOX?")
    page.keyboard.press("Enter")
    assert _pick(page) == {"kind": "none", "recommended": True, "via": "key", "box": "FCC-TEST-BOX"}


def test_an_rtl_box_draws_right_to_left(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-RTL": build_model("FCC-TEST-RTL", spool=999201)})
    open_({"location": "FCC-TEST-RTL", "spool": 999201})
    assert _order(page) == ["3", "2", "1"]
    assert _active(page) == "1"


def test_an_unreadable_spoolman_says_so_and_retry_reloads(picker_page):
    page, setup, open_ = picker_page
    calls = {"n": 0}
    bad = build_model("FCC-TEST-BOX", fail=True)
    good = build_model("FCC-TEST-BOX", spool=999201)

    def _model(_q):
        calls["n"] += 1
        return bad if calls["n"] == 1 else good

    setup({"FCC-TEST-BOX": _model})
    open_({"location": "FCC-TEST-BOX", "spool": 999201}, ready=False)
    msg = page.locator("#fcc-slot-picker [data-sp-state='message']")
    expect(msg).to_contain_text("Couldn't read Spoolman")
    assert page.locator("#fcc-slot-picker .fcc-sp-tile").count() == 0
    page.locator("#fcc-slot-picker [data-sp-act='retry']").click()
    page.wait_for_selector(READY, timeout=10_000)
    assert _order(page) == ["1", "2", "3", "4"]


def test_a_place_no_picker_opens_on_shows_the_servers_reason(picker_page):
    page, setup, open_ = picker_page
    setup({})
    open_({"location": "NOPE-1"}, ready=False)
    expect(page.locator("#fcc-slot-picker [data-sp-state='message']")).to_contain_text("not in this stub")
    page.keyboard.press("Escape")
    assert _pick(page) is None


# ---- guards ---------------------------------------------------------------------------------------

def test_the_picker_never_opens_during_a_bulk_move(picker_page):
    page, setup, open_ = picker_page
    stub = setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX")})
    page.evaluate("() => { state.bulkMoveActive = true; }")
    try:
        open_({"location": "FCC-TEST-BOX"}, ready=False)
        assert _pick(page) is None
        assert page.locator("#fcc-slot-picker").count() == 0
        assert stub.queries == []
    finally:
        page.evaluate("() => { state.bulkMoveActive = false; }")


def test_closing_the_host_modal_cancels_the_picker(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    page.evaluate("""() => {
        const host = document.createElement('div');
        host.id = 'fcc-test-host';
        document.body.appendChild(host);
        window.__pick = undefined; window.__pickDone = false;
        window.openSlotPicker({ location: 'FCC-TEST-BOX', spool: 999201, host })
            .then((r) => { window.__pick = r; window.__pickDone = true; });
    }""")
    page.wait_for_selector(READY, timeout=10_000)
    page.evaluate("() => document.getElementById('fcc-test-host').dispatchEvent(new Event('hidden.bs.modal'))")
    assert _pick(page) is None
    expect(page.locator("#fcc-slot-picker")).to_have_count(0)


# ---- Group 40.2: the picker follow-ups (D1–D4, the 40.1 + 40.3 review) ---------------------------
# HEAD proof (d8f6128): each of these fails there: a short numeric scan moved the
# highlight and its Enter picked (D1), the picker opened over another dialog,
# during an audit and while busy, and stayed open when a bulk move started (D2),
# a refusal was only a toast under the panel, a label scanned while loading was
# refused, CMD:CANCEL was silent (D3), and an occupied or greyed-out slot
# resolved at once with no `send` (D4).

# Slot 1 feeds FCCX-1 while its own spool runs on FCCX-2 (greyed out); slot 3's
# own spool runs on FCCX-3, the head it feeds (the same-slot swap).
D4_SPOOLS = SPOOLS[:1] + [
    _sp(999211, "FCCX-2", src="FCC-TEST-BOX", src_slot=1, name="Test Orange", color="ee8822"),
    _sp(999213, "FCCX-3", src="FCC-TEST-BOX", src_slot=3, name="Test Teal", color="22aaaa"),
    _sp(999201, "FCC-TEST-SHELF"),
]


def test_a_short_numeric_scan_neither_moves_the_highlight_nor_picks(picker_page):
    """D1: a 1–2 digit spool label typed at scanner speed is a scan: it is
    refused like any other foreign scan, and its Enter picks nothing."""
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    assert _active(page) == "3"
    page.keyboard.type("42", delay=0)
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__pickDone") is False
    assert _active(page) == "3"
    expect(page.locator(STATUS)).to_contain_text("Finish or cancel the slot picker first. (Ignored: 42)")


def test_keys_aimed_at_a_field_behind_the_picker_never_drive_it(picker_page):
    """D1: focus in a field outside the panel (the Location Manager's ID box)
    owns its keys; its Enter and digits neither pick nor move the highlight."""
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.evaluate("""() => { const i = document.createElement('input'); i.id = 'fcc-test-behind';
        document.body.appendChild(i); i.focus(); }""")
    page.keyboard.press("1")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__pickDone") is False
    assert _active(page) == "3"


@pytest.mark.parametrize("flag, why", [
    ("auditActive", "waits until the audit is finished"),
    ("activeModal", "Answer the dialog on screen first"),
    ("processing", "still handling the last scan"),
], ids=["audit", "gating-dialog", "busy"])
def test_the_picker_wont_open_during_an_audit_a_gating_dialog_or_a_scan(picker_page, flag, why):
    page, setup, open_ = picker_page
    stub = setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX")})
    page.evaluate(f"() => {{ state.{flag} = {'true' if flag != 'activeModal' else repr('confirm')}; }}")
    try:
        open_({"location": "FCC-TEST-BOX"}, ready=False)
        assert _pick(page) is None
        assert page.locator("#fcc-slot-picker").count() == 0 and stub.queries == []
        assert any(why in t["text"] and t["type"] == "warning" for t in page.evaluate("() => window.__toastLog"))
    finally:
        page.evaluate(f"() => {{ state.{flag} = {'false' if flag != 'activeModal' else 'null'}; }}")


def test_the_picker_never_stacks_over_another_dialog(picker_page):
    """D2: one Escape used to cancel the dialog underneath, a second the picker."""
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX")})
    page.evaluate("() => window.mountOverlay({ id: 'fcc-test-under', content: '<div>a dialog</div>' })")
    open_({"location": "FCC-TEST-BOX"}, ready=False)
    assert _pick(page) is None
    assert page.locator("#fcc-slot-picker").count() == 0
    toasts = page.evaluate("() => window.__toastLog")
    assert any("won't open over it" in t["text"] for t in toasts), toasts


def test_the_picker_closes_itself_when_a_bulk_move_starts(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    try:
        page.evaluate("() => { state.bulkMoveActive = true;"
                      " document.dispatchEvent(new CustomEvent('inventory:sync-pulse')); }")
        assert _pick(page) is None
        expect(page.locator("#fcc-slot-picker")).to_have_count(0)
        toasts = page.evaluate("() => window.__toastLog")
        assert any(t["text"] == "Slot picker closed: a bulk move started, so nothing was placed" for t in toasts), toasts
    finally:
        page.evaluate("() => { state.bulkMoveActive = false; }")


def test_cmd_cancel_says_the_picker_was_cancelled(picker_page):
    page, setup, open_ = picker_page
    stub = setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.evaluate("() => processScan('CMD:CANCEL', 'barcode')")
    assert _pick(page) is None
    toasts = page.evaluate("() => window.__toastLog")
    assert any(t["text"] == "Slot picker cancelled — nothing moved" for t in toasts), toasts
    assert any("cancelled by a CMD:CANCEL scan" in b.get("msg", "") for b in stub.posted("/api/log_event"))


def test_a_slot_label_scanned_while_the_slots_load_is_picked_once_they_are_drawn(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    page.evaluate("() => { window.__placementDelayMs = 1500; }")   # the in-page delay lever
    page.evaluate(OPEN_JS, {"location": "FCC-TEST-BOX", "spool": 999201})
    page.wait_for_selector("#fcc-slot-picker [data-sp-state='loading']", timeout=5_000)
    page.evaluate("() => processScan('LOC:FCC-TEST-BOX:SLOT:4', 'barcode')")
    expect(page.locator("#fcc-slot-picker .fcc-sp-msg")).to_contain_text("is picked once it has loaded")
    got = _pick(page, timeout=10_000)
    assert got["slot"] == "4" and got["via"] == "scan" and got["send"] == {"picked_slot": "4"}, got


def test_a_free_pick_tells_the_caller_to_send_picked_slot_and_the_feed(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.keyboard.press("Enter")                       # the ⭐, slot 3 (feeds FCCX-3)
    got = _pick(page)
    assert got["send"] == {"picked_slot": "3"} and got["expected_feed"] == "FCCX-3", got
    assert got["choice"] is None and got["swap"] is False and got["displaced"] is None
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='4']").click()   # a Printer Pool slot
    got = _pick(page)
    assert got["send"] == {"picked_slot": "4"} and got["expected_feed"] == "", got


def test_a_greyed_out_slot_says_why_and_is_never_picked(picker_page):
    page, setup, open_ = picker_page
    model = build_model("FCC-TEST-BOX", spools=D4_SPOOLS, spool=999201)
    assert _slot_of(model, "1")["blocked"], model["slots"]
    setup({"FCC-TEST-BOX": model})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    tile = page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='1']")
    expect(tile).to_have_class(re.compile(r"\bis-blocked\b"))
    expect(tile).to_contain_text("#999211 from this slot is loaded on FCCX-2, but the slot feeds FCCX-1")
    tile.click(force=True)     # aria-disabled: Playwright won't click it unforced; a person's click lands
    page.evaluate("() => processScan('LOC:FCC-TEST-BOX:SLOT:1', 'barcode')")
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__pickDone") is False
    expect(page.locator(STATUS)).to_contain_text("FCC-TEST-BOX slot 1: #999211 from this slot is loaded on FCCX-2")


def test_an_occupied_slot_asks_swap_or_overwrite_and_back_returns(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    choice = page.locator(CHOICE)
    expect(choice).to_contain_text("Slot 2 holds #999202")
    labels = page.evaluate("() => Array.from(document.querySelectorAll('#fcc-slot-picker [data-sp-choice]'))"
                           ".map(b => b.dataset.spChoice)")
    assert labels == ["swap", "overwrite", "back"], labels
    page.locator("#fcc-slot-picker [data-sp-choice='back']").click()
    page.wait_for_selector(READY, timeout=5_000)
    assert _active(page) == "2"                          # Back lands on the slot it came from
    page.keyboard.press("Enter")
    page.wait_for_selector(CHOICE, timeout=5_000)
    page.locator("#fcc-slot-picker [data-sp-choice='overwrite']").click()
    got = _pick(page)
    assert got["choice"] == "overwrite" and got["send"] == {"slot": "2"} and got["swap"] is False, got


@pytest.mark.parametrize("swap_to, text", [
    ("CR-CT-2-R1", "#999202 → your buffer, filed back in CR-CT-2-R1"),
    ("", "#999202 → your buffer (Unassigned until you scan it somewhere)"),
], ids=["filed-back", "no-record"])
def test_the_swap_says_where_the_old_spool_is_filed(picker_page, swap_to, text):
    """Swap option C (Derek, 2026-10-15): a Swap hands the slot's stored spool to
    the buffer AND files it back where it sat before the slot; the model's
    `swap_to` (the engine's own rule) is what the Swap button says."""
    page, setup, open_ = picker_page
    model = build_model("FCC-TEST-BOX", spool=999201)
    next(s for s in model["slots"] if s["slot"] == "2")["swap_to"] = swap_to
    setup({"FCC-TEST-BOX": model})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    expect(page.locator("#fcc-slot-picker [data-sp-choice='swap']")).to_contain_text(text)


def test_the_choice_qrs_answer_it(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.evaluate("() => processScan('CMD:SLOT:2', 'barcode')")
    page.wait_for_selector(CHOICE, timeout=5_000)
    sid = page.evaluate("() => Object.keys(window._fccActiveConfirms || {}).pop()")
    page.evaluate("(sid) => processScan('CMD:CONFIRM:' + sid, 'barcode')", sid)
    got = _pick(page)
    assert got["choice"] == "swap" and got["displaced"]["id"] == 999202, got
    # The session ended with the picker: the same QR scanned again does nothing.
    assert page.evaluate("(sid) => !(window._fccActiveConfirms || {})[sid]", sid) is True


def test_the_same_slot_swap_has_one_answer(picker_page):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spools=D4_SPOOLS, spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='3']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    expect(page.locator(CHOICE)).to_contain_text("#999213 comes off into your scan buffer")
    labels = page.evaluate("() => Array.from(document.querySelectorAll('#fcc-slot-picker [data-sp-choice]'))"
                           ".map(b => b.dataset.spChoice)")
    assert labels == ["swap_out", "back"], labels
    page.keyboard.press("Enter")
    got = _pick(page)
    assert got["choice"] == "swap_out" and got["send"] == {"slot": "3"} and got["expected_feed"] == "FCCX-3", got


def test_a_slow_scanners_digit_label_is_still_a_scan(picker_page):
    """The review's D1 gap (wf_0b3cc1a9-578): a scanner slower than 50 ms a key
    typed "12": the "1" became a hotkey, its clear emptied the scan buffer, the
    "2" became a hotkey too, and Enter picked slot 2. Now the second digit puts
    the highlight back and the Enter is the scan's (refused). HEAD proof
    (f5f3ba2): both digits are hotkeys and the Enter acts on slot 2 (here it
    holds a spool, so it opens its Swap / Overwrite step); "12" is never refused."""
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    assert _active(page) == "3"
    page.keyboard.type("12", delay=90)
    page.keyboard.press("Enter")
    expect(page.locator(STATUS)).to_contain_text("(Ignored: 12)")
    assert page.evaluate("() => window.__pickDone") is False
    assert _active(page) == "3"


def test_a_lone_digit_on_the_choice_step_doesnt_spoil_the_next_scan(picker_page):
    """The review's stray-digit regression: a digit pressed on the Swap /
    Overwrite step stayed in the scan buffer, so the next scan read
    "2CMD:CONFIRM:…" and was refused. HEAD proof (f5f3ba2): the buffer keeps it."""
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    page.keyboard.press("2")
    # Well inside the accumulator's own 2 s timeout, which would clear it anyway.
    page.wait_for_timeout(700)
    assert page.evaluate("() => state.scanBuffer") == ""
    expect(page.locator(CHOICE)).to_have_count(1)


def test_a_stale_cancel_qr_does_not_cancel_the_picker(picker_page):
    """The Back QR read twice: the first goes back to the slots, the second (its
    session gone) used to cancel the whole picker. HEAD proof (f5f3ba2): the
    picker closes."""
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    sid = page.evaluate("() => Object.keys(window._fccActiveConfirms || {}).pop()")
    page.evaluate("(sid) => processScan('CMD:CANCEL:' + sid, 'barcode')", sid)
    page.wait_for_selector(READY, timeout=5_000)
    page.evaluate("(sid) => processScan('CMD:CANCEL:' + sid, 'barcode')", sid)
    page.wait_for_timeout(200)
    assert page.evaluate("() => window.__pickDone") is False
    expect(page.locator(STATUS)).to_contain_text("belongs to a step that has closed")


def test_an_occupied_slot_that_only_stores_sends_a_store(picker_page):
    """The review's yellow: #999201 runs on FCCX-2, and slot 2 (fed FCCX-2 here)
    holds a stored spool. The tile says it is stored, not loaded back, and Swap /
    Overwrite now send a store (auto_deploy false); {slot} alone loaded it back.
    HEAD proof (f5f3ba2): no auto_deploy in the send."""
    page, setup, open_ = picker_page
    rows = [r for r in copy.deepcopy(ROWS) if r["LocationID"] != "FCC-TEST-BOX"] + [
        _box("FCC-TEST-BOX", 4, {"1": "FCCX-1", "2": "FCCX-2", "3": "FCCX-3", "4": "PRINTER:FCCX"})]
    spools = [_sp(999202, "FCC-TEST-BOX", slot=2), _sp(999201, "FCCX-2", src="FCC-TEST-PM", src_slot=1)]
    model = build_model("FCC-TEST-BOX", rows=rows, spools=spools, spool=999201)
    assert _slot_of(model, "2")["stores_only"] is True
    setup({"FCC-TEST-BOX": model})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    expect(page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']")).to_contain_text(
        "stored here, not loaded back")
    page.locator("#fcc-slot-picker .fcc-sp-tile[data-sp-slot='2']").click()
    page.wait_for_selector(CHOICE, timeout=5_000)
    expect(page.locator(CHOICE)).to_contain_text("It is stored there, not loaded onto FCCX-2.")
    page.locator("#fcc-slot-picker [data-sp-choice='overwrite']").click()
    got = _pick(page)
    assert got["send"] == {"slot": "2", "auto_deploy": False}, got


def _slot_of(model, slot):
    return next(s for s in model["slots"] if s["slot"] == str(slot))


# ---- visual (stubbed data only; never dev contents) ----------------------------------------------

def test_box_picker_visual(picker_page, snapshot):
    page, setup, open_ = picker_page
    setup({"FCC-TEST-BOX": build_model("FCC-TEST-BOX", spool=999201)},
          printer_state=lambda head: {"known": True, "is_active": False, "state": "IDLE", "printer_name": PRINTER})
    open_({"location": "FCC-TEST-BOX", "spool": 999201})
    expect(page.locator("#fcc-slot-picker .fcc-sp-pchip .fcc-sp-pstate")).to_have_text("idle")
    page.wait_for_timeout(400)   # the QR codes draw on a double rAF
    snapshot(page.locator("#fcc-slot-picker .fcc-sp-panel"), "slot-picker-box")
