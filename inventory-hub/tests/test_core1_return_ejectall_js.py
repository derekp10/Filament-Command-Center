"""Hermetic JS checks for the CORE1 Return and the Eject All scan guard (2026-09-13).

Runs the REAL frontend modules (inv_quickswap.js, inv_cmd.js, inv_loc_mgr.js)
under node's `vm` module with a minimal DOM + network stub, so both frontend
fixes are proven without a browser or the dev container:

  - Quick-Swap Return on a Printer row whose single toolhead shares its id (the
    Core One: row CORE1, head CORE1) reaches /api/quickswap/return. It used to
    stop at "Nothing to return on CORE1" because it only looked for "CORE1-*";
  - the Bind-a-Slot picker opens on that row (it used to throw on an empty
    toolhead list), and neither view picks up another printer's "XL-*" lookalike;
  - a CMD:EJECTALL scan with no location open in the Location Manager, through
    either route (the exact client-side match or the backend's substring match),
    never reaches triggerEjectAll, and says so with a >= 7 s warning plus an
    Activity Log line;
  - triggerEjectAll refuses a blank location and never says "Cleared!" over a
    backend refusal.

The stub is deliberately dumb: getElementById always returns a fake element,
fetch answers from a per-scenario responder, mountOverlay records the overlay
HTML, and nothing renders. These tests pin the modules' own decisions; what a
real browser shows is covered by test_core1_return_ejectall_e2e.py (deferred).

Needs node (Node.js) on PATH, see CLAUDE.md "Testing". These are the only
hermetic proofs of the frontend fixes above, so a missing node is not silent:
  - by default the module skips AND emits a PytestWarning, which shows in the
    run's warnings summary;
  - with FCC_REQUIRE_NODE=1 a missing node is a collection error instead.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

NODE = shutil.which("node")
NODE_MISSING_MSG = (
    "node is not on PATH: the hermetic checks of the CORE1 Return and Eject All "
    "frontend fixes (test_core1_return_ejectall_js.py) did NOT run. Install "
    "Node.js (see CLAUDE.md Testing), or set FCC_REQUIRE_NODE=1 to fail instead of skipping."
)
if NODE is None:
    if os.environ.get("FCC_REQUIRE_NODE", "").strip() not in ("", "0"):
        pytest.fail(NODE_MISSING_MSG, pytrace=False)
    warnings.warn(NODE_MISSING_MSG, pytest.PytestWarning)
pytestmark = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

MODULES = Path(__file__).resolve().parent.parent / "static" / "js" / "modules"
RESULT_MARK = "__FCC_RESULT__"

# The driver. `prelude` and `scenario` are stringified and evaluated INSIDE the
# vm context, so every object they build belongs to the modules' realm.
DRIVER_JS = r"""
const vm = require('vm');
const fs = require('fs');

const MODULE_PATHS = __MODULE_PATHS__;

function prelude() {
  globalThis.window = globalThis;
  globalThis.self = globalThis;
  const rec = globalThis.__rec = { toasts: [], logs: [], fetches: [], overlays: [], safety: [], ejectAll: [] };
  globalThis.__overlayEls = [];

  const makeClassList = () => {
    const set = new Set();
    return {
      add: (...c) => c.forEach(x => set.add(x)),
      remove: (...c) => c.forEach(x => set.delete(x)),
      contains: (c) => set.has(c),
      toggle: (c, force) => {
        const on = force === undefined ? !set.has(c) : !!force;
        if (on) set.add(c); else set.delete(c);
        return on;
      },
    };
  };
  const makeElement = (tag, id) => {
    const cache = new Map();
    const attrs = new Map();
    const el = {
      tagName: String(tag || 'div').toUpperCase(), id: id || '', nodeType: 1,
      style: {}, dataset: {}, innerHTML: '', innerText: '', textContent: '', value: '', className: '',
      children: [], childNodes: [], options: [], disabled: false, checked: false, parentNode: null,
      appendChild(c) { this.children.push(c); return c; },
      removeChild(c) { return c; }, remove() {}, prepend() {}, append() {}, insertBefore(c) { return c; },
      setAttribute(k, v) { attrs.set(k, String(v)); },
      getAttribute(k) { return attrs.has(k) ? attrs.get(k) : null; },
      hasAttribute(k) { return attrs.has(k); }, removeAttribute(k) { attrs.delete(k); },
      addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
      querySelector(sel) { if (!cache.has(sel)) cache.set(sel, makeElement('div', sel)); return cache.get(sel); },
      querySelectorAll() { return []; }, closest() { return null; }, contains() { return false; },
      focus() {}, blur() {}, click() {}, scrollIntoView() {},
      getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; },
    };
    el.classList = makeClassList();
    return el;
  };
  const byId = new Map();
  globalThis.document = {
    body: makeElement('body'), head: makeElement('head'), documentElement: makeElement('html'),
    activeElement: null, readyState: 'complete',
    getElementById(id) { if (!byId.has(id)) byId.set(id, makeElement('div', id)); return byId.get(id); },
    createElement(tag) { return makeElement(tag); },
    createTextNode(t) { return { textContent: t }; },
    querySelector(sel) { return globalThis.document.getElementById('query:' + sel); },
    querySelectorAll() { return []; },
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
  };

  globalThis.state = { heldSpools: [], allLocations: [], printerMap: null };
  globalThis.CustomEvent = class CustomEvent { constructor(t, o) { this.type = t; this.detail = o && o.detail; } };
  globalThis.Event = class Event { constructor(t) { this.type = t; } };
  globalThis.MutationObserver = class { observe() {} disconnect() {} };
  globalThis.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
  globalThis.sessionStorage = globalThis.localStorage;
  globalThis.navigator = {};
  globalThis.location = { href: 'http://fcc.test/', pathname: '/', search: '' };
  globalThis.setInterval = () => 0;
  globalThis.clearInterval = () => {};
  globalThis.requestAnimationFrame = () => 0;
  globalThis.modals = new Proxy({}, { get: () => ({ show() {}, hide() {} }) });
  globalThis.bootstrap = { Modal: { getInstance: () => null, getOrCreateInstance: () => ({ show() {}, hide() {} }) } };
  globalThis.generateSafeQR = () => {};
  globalThis.setProcessing = () => {};
  globalThis.showToast = (msg, type = 'info', duration = 2000) => { rec.toasts.push({ msg: String(msg), type, duration }); };
  globalThis.logClientEvent = (msg, level = 'INFO') => { rec.logs.push({ msg: String(msg), level }); };
  globalThis.promptSafety = (msg, cb) => { rec.safety.push(String(msg)); globalThis.__safetyCb = cb; };
  globalThis.requestConfirmation = () => {};
  globalThis.__respond = () => null;
  globalThis.fetch = (url, opts) => {
    const o = opts || {};
    const u = String(url);
    const method = String(o.method || 'GET').toUpperCase();
    let body = null;
    if (o.body) { try { body = JSON.parse(o.body); } catch (e) { body = o.body; } }
    rec.fetches.push({ url: u, method, body });
    const r = globalThis.__respond(u, method, body) || {};
    const status = r.status || 200;
    const payload = r.body === undefined ? {} : r.body;
    return Promise.resolve({
      ok: status < 400, status,
      json: () => Promise.resolve(JSON.parse(JSON.stringify(payload))),
    });
  };
  globalThis.fetchT = (url, opts) => globalThis.fetch(url, opts);
  globalThis.mountOverlay = (opts) => {
    const element = makeElement('div', opts.id);
    element.innerHTML = String(opts.content || '');
    const entry = { id: opts.id, content: element.innerHTML, closed: false };
    rec.overlays.push(entry);
    globalThis.__overlayEls.push(element);
    return { element, cleanup: () => { entry.closed = true; } };
  };
  globalThis.__settle = async (ms) => {
    const end = Date.now() + (ms || 60);
    while (Date.now() < end) await new Promise(r => setTimeout(r, 5));
  };
}

async function scenario() {
__SCENARIO__
}

(async () => {
  const unhandled = [];
  process.on('unhandledRejection', (e) => unhandled.push(String((e && e.stack) || e)));
  const ctx = vm.createContext({ console, setTimeout, clearTimeout });
  vm.runInContext('(' + prelude.toString() + ')()', ctx, { filename: 'prelude.js' });
  for (const p of MODULE_PATHS) {
    vm.runInContext(fs.readFileSync(p, 'utf8'), ctx, { filename: p });
  }
  const result = await vm.runInContext('(' + scenario.toString() + ')()', ctx, { filename: 'scenario.js' });
  console.log('__FCC_RESULT__' + JSON.stringify({ result, unhandled }));
  process.exit(0);
})().catch((e) => {
  console.error((e && e.stack) || e);
  process.exit(3);
});
"""


def run_js(tmp_path: Path, modules: list[str], scenario: str) -> dict:
    driver = (DRIVER_JS
              .replace("__MODULE_PATHS__", json.dumps([str(MODULES / m) for m in modules]))
              .replace("__SCENARIO__", scenario))
    script = tmp_path / "driver.js"
    script.write_text(driver, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and lines, (
        f"node driver failed (rc={proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    out = json.loads(lines[-1][len(RESULT_MARK):])
    return {**out["result"], "unhandled": out["unhandled"]}


# ---------------------------------------------------------------------------
# Quick-Swap Return + Bind picker on Printer rows
# ---------------------------------------------------------------------------

PRINTERS_JS = """
const core1 = { LocationID: 'CORE1', Name: 'Core One Upgraded', Type: 'Printer',
                toolheads: [{ location_id: 'CORE1', position: 0 }] };
const xl = { LocationID: 'XL', Name: 'XL', Type: 'Printer',
             toolheads: [{ location_id: 'XL-1', position: 0 }, { location_id: 'XL-2', position: 1 }] };
const xlb = { LocationID: 'XLB', Name: 'XL B', Type: 'Printer',
              toolheads: [{ location_id: 'XL-B1', position: 0 }] };
const coreBox = { LocationID: 'CR-DB-1', Name: 'Core box', Type: 'Dryer Box', 'Max Spools': '4' };
state.allLocations = [core1, xl, xlb, coreBox];
state.printerMap = {
  'Core One Upgraded': [{ location_id: 'CORE1', position: 0 }],
  'XL': [{ location_id: 'XL-1', position: 0 }, { location_id: 'XL-2', position: 1 }],
  'XL B': [{ location_id: 'XL-B1', position: 0 }],
};
const rows = { CORE1: core1, XL: xl, XLB: xlb };
"""

# Opens Return on rows[ROW] with `loaded` ({toolhead: spool}) and `spools`
# ({id: extra}); clicks Yes on whatever overlay it shows.
RETURN_SCENARIO = PRINTERS_JS + """
const ROW = __ROW__;
const loaded = __LOADED__;
const spools = __SPOOLS__;
const slots = __SLOTS__;
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/machine/')) return { status: 404, body: { toolheads: {} } };
  const gc = url.match(/^\\/api\\/get_contents\\?id=(.+)$/);
  if (gc) {
    const th = decodeURIComponent(gc[1]);
    return { body: loaded[th] ? [{ id: loaded[th], display: 'Test spool #' + loaded[th], location: th, slot: '' }] : [] };
  }
  const sp = url.match(/^\\/api\\/spools\\/(\\d+)$/);
  if (sp) {
    const th = Object.keys(loaded).find(k => String(loaded[k]) === sp[1]);
    return { body: { success: true, data: { id: Number(sp[1]), location: th, extra: spools[sp[1]] || {} } } };
  }
  if (url === '/api/dryer_boxes/slots') return { body: { slots } };
  if (url === '/api/quickswap/return') return { body: { action: 'return_done', moved: 1, box: 'BOX', slot: '1' } };
  return { body: [] };
};
window.renderQuickSwapSection(rows[ROW]);
await __settle();
window.returnToolheadToSlot();
await __settle(200);
const overlays = __rec.overlays.map(o => o.content);
const last = __overlayEls[__overlayEls.length - 1];
const yes = last ? last.querySelector('#fcc-quickswap-yes') : null;
if (yes && typeof yes.onclick === 'function') yes.onclick();
await __settle(100);
return { overlays, fetches: __rec.fetches, toasts: __rec.toasts };
"""


def _return_scenario(row: str, loaded: dict, spools: dict | None = None, slots: list | None = None) -> str:
    return (RETURN_SCENARIO
            .replace("__ROW__", json.dumps(row))
            .replace("__LOADED__", json.dumps(loaded))
            .replace("__SPOOLS__", json.dumps(spools or {}))
            .replace("__SLOTS__", json.dumps(slots or [])))


TITLE_RE = re.compile(r'id="fcc-quickswap-confirm-title">([^<]*)<')


def _titles(res: dict) -> list[str]:
    return [m.group(1) for c in res["overlays"] for m in [TITLE_RE.search(c)] if m]


def _gets(res: dict, prefix: str) -> list[str]:
    return [f["url"] for f in res["fetches"] if f["method"] == "GET" and f["url"].startswith(prefix)]


def _posts(res: dict, url: str) -> list:
    return [f["body"] for f in res["fetches"] if f["method"] == "POST" and f["url"] == url]


def test_return_on_core1_reaches_the_backend_for_its_same_named_head(tmp_path):
    """The Core One: Printer row CORE1, single head CORE1, loaded, with a
    recorded source box. FAILS on the old module: "Nothing to return on CORE1"
    without a single request, and its Yes posted nothing."""
    res = run_js(tmp_path, ["inv_quickswap.js"], _return_scenario(
        "CORE1", loaded={"CORE1": 912},
        spools={"912": {"physical_source": '"CR-DB-1"', "physical_source_slot": '"2"'}}))

    assert _titles(res) == ["Return the spool on CORE1?"], res["overlays"]
    assert "CR-DB-1 slot 2" in res["overlays"][0]
    assert _gets(res, "/api/get_contents?id=") == ["/api/get_contents?id=CORE1"] * 2, res["fetches"]
    assert _posts(res, "/api/quickswap/return") == [{"toolhead": "CORE1"}]
    assert any(t["type"] == "success" for t in res["toasts"]), res["toasts"]
    assert res["unhandled"] == []


def test_return_on_xl_still_picks_its_first_loaded_head(tmp_path):
    """XL behaviour is unchanged: probe XL-1, then XL-2, act on XL-2. PASSES
    on the old module too."""
    res = run_js(tmp_path, ["inv_quickswap.js"], _return_scenario(
        "XL", loaded={"XL-2": 913}, slots=[{"box": "LR-DB-1", "slot": "3", "target": "XL-2"}]))

    assert _titles(res) == ["Return the spool on XL-2?"], res["overlays"]
    assert "virtual printer" in res["overlays"][0]
    assert _gets(res, "/api/get_contents?id=") == [
        "/api/get_contents?id=XL-1", "/api/get_contents?id=XL-2", "/api/get_contents?id=XL-2"], res["fetches"]
    assert _posts(res, "/api/quickswap/return") == [{"toolhead": "XL-2"}]
    assert res["unhandled"] == []


def test_return_on_xl_ignores_another_printers_lookalike_head(tmp_path):
    """Printer XLB owns XL-B1, which also starts with "XL-". Only XL-B1 is
    loaded, so XL has nothing to return. FAILS on the old module: it probed
    XL-B1 and offered to return the OTHER printer's spool."""
    res = run_js(tmp_path, ["inv_quickswap.js"], _return_scenario("XL", loaded={"XL-B1": 914}))

    assert _titles(res) == ["Nothing to return on XL"], res["overlays"]
    assert "/api/get_contents?id=XL-B1" not in _gets(res, "/api/get_contents?id=")
    assert _posts(res, "/api/quickswap/return") == []
    assert res["unhandled"] == []


BIND_PICKER_SCENARIO = PRINTERS_JS + """
window.__respond = (url) => {
  if (url.startsWith('/api/machine/')) return { status: 404, body: { toolheads: {} } };
  if (url === '/api/dryer_boxes/slots') {
    return { body: { slots: [{ box: 'CR-DB-1', box_name: 'Core box', slot: '1', target: null }] } };
  }
  return { body: [] };
};
window.renderQuickSwapSection(rows[__ROW__]);
await __settle();
let error = null;
try { window.openBindSlotPicker(); } catch (e) { error = String((e && e.message) || e); }
await __settle();
return {
  error,
  toolhead: document.getElementById('fcc-bind-picker-toolhead').innerText,
  rowDisplay: document.getElementById('fcc-bind-picker-toolhead-row').style.display || null,
  options: document.getElementById('fcc-bind-picker-toolhead-select').innerHTML,
  overlayDisplay: document.getElementById('fcc-bind-picker-overlay').style.display || null,
  toasts: __rec.toasts,
};
"""


def test_bind_picker_opens_on_core1(tmp_path):
    """FAILS on the old module: the prefix-only match left no toolhead options
    and toolheadOptions[0].value threw, so the picker never opened."""
    res = run_js(tmp_path, ["inv_quickswap.js"], BIND_PICKER_SCENARIO.replace("__ROW__", json.dumps("CORE1")))

    assert res["error"] is None, res
    assert res["toolhead"] == "CORE1"
    assert res["rowDisplay"] == "none"          # one head: no selector row
    assert res["overlayDisplay"] == "block"
    assert res["unhandled"] == []


def test_bind_picker_on_xl_lists_only_its_own_heads(tmp_path):
    """XL's selector lists XL-1 and XL-2 with their printer labels, and not the
    lookalike XL-B1 from printer XLB. FAILS on the old module only because of
    the lookalike (it listed XL-B1 too); the XL-1 / XL-2 labels are unchanged."""
    res = run_js(tmp_path, ["inv_quickswap.js"], BIND_PICKER_SCENARIO.replace("__ROW__", json.dumps("XL")))

    assert res["error"] is None, res
    assert res["toolhead"] == "XL-1"
    assert res["rowDisplay"] == "block"
    assert "XL-1 — Toolhead 1 on XL" in res["options"]
    assert "XL-2 — Toolhead 2 on XL" in res["options"]
    assert "XL-B1" not in res["options"]
    assert res["unhandled"] == []


# ---------------------------------------------------------------------------
# CMD:EJECTALL scan guard (inv_cmd.js)
# ---------------------------------------------------------------------------

EJECTALL_SCAN_SCENARIO = """
window.triggerEjectAll = (loc) => { __rec.ejectAll.push(loc); };
// processScan's backend-answered command table names closeManage (inv_loc_mgr.js,
// not loaded here); without it the lookup throws into the "Scan Error" catch.
window.closeManage = () => {};
window.__respond = (url) => url === '/api/identify_scan'
  ? { body: { type: 'command', cmd: 'ejectall' } } : { body: {} };
if (__OPEN__) document.getElementById('manageModal').classList.add('show');
document.getElementById('manage-loc-id').value = __LOC__;
processScan(__TEXT__, 'barcode');
await __settle(80);
return { ejectAll: __rec.ejectAll, toasts: __rec.toasts, logs: __rec.logs, fetches: __rec.fetches };
"""

# The exact client-side match, and the backend-answered route (identify_scan's
# substring match returns cmd 'ejectall' for any text containing CMD:EJECTALL).
SCAN_ROUTES = [pytest.param("CMD:EJECTALL", id="client-match"),
               pytest.param("label CMD:EJECTALL", id="backend-answered")]


def _ejectall_scan(tmp_path, text: str, *, manager_open: bool, loc: str) -> dict:
    return run_js(tmp_path, ["inv_cmd.js"], (EJECTALL_SCAN_SCENARIO
                                             .replace("__OPEN__", json.dumps(manager_open))
                                             .replace("__LOC__", json.dumps(loc))
                                             .replace("__TEXT__", json.dumps(text))))


@pytest.mark.parametrize("text", SCAN_ROUTES)
@pytest.mark.parametrize("manager_open,loc", [
    pytest.param(False, "", id="manager-closed"),
    pytest.param(False, "PM-DB-1", id="manager-closed-stale-id"),
    pytest.param(True, "   ", id="manager-open-blank-id"),
])
def test_ejectall_scan_without_an_open_location_is_refused(tmp_path, text, manager_open, loc):
    """FAILS on the old module for every case: triggerEjectAll ran with the
    blank (or stale) id, which prompted "Nuke all unslotted in ?"."""
    res = _ejectall_scan(tmp_path, text, manager_open=manager_open, loc=loc)

    assert res["ejectAll"] == [], res
    warnings = [t for t in res["toasts"] if t["type"] == "warning" and "Eject All ignored" in t["msg"]]
    assert len(warnings) == 1, res["toasts"]
    assert warnings[0]["duration"] >= 7000
    assert [lg["level"] for lg in res["logs"] if "CMD:EJECTALL" in lg["msg"]] == ["WARNING"], res["logs"]
    assert res["unhandled"] == []


@pytest.mark.parametrize("text", SCAN_ROUTES)
def test_ejectall_scan_with_a_location_open_still_ejects_it(tmp_path, text):
    """Control, PASSES on the old module too: an open manager on PM-DB-1 hands
    PM-DB-1 to triggerEjectAll, with no warning."""
    res = _ejectall_scan(tmp_path, text, manager_open=True, loc="PM-DB-1")

    assert res["ejectAll"] == ["PM-DB-1"], res
    assert not [t for t in res["toasts"] if t["type"] == "warning"], res["toasts"]
    assert res["unhandled"] == []


# ---------------------------------------------------------------------------
# triggerEjectAll (inv_loc_mgr.js)
# ---------------------------------------------------------------------------

TRIGGER_SCENARIO = """
const answer = __ANSWER__;
window.__respond = (url) => url === '/api/manage_contents' ? { body: answer } : { body: [] };
window.triggerEjectAll(__LOC__);
if (typeof window.__safetyCb === 'function') window.__safetyCb();
await __settle(80);
return { safety: __rec.safety, toasts: __rec.toasts, logs: __rec.logs,
         posts: __rec.fetches.filter(f => f.method === 'POST').map(f => [f.url, f.body]) };
"""


def _trigger(tmp_path, loc, answer) -> dict:
    return run_js(tmp_path, ["inv_loc_mgr.js"], (TRIGGER_SCENARIO
                                                 .replace("__LOC__", json.dumps(loc))
                                                 .replace("__ANSWER__", json.dumps(answer))))


@pytest.mark.parametrize("loc", ["", "   ", None])
def test_trigger_eject_all_refuses_a_blank_location(tmp_path, loc):
    """FAILS on the old module: it prompted "Nuke all unslotted in ?" (or
    "in null") and, confirmed, posted clear_location for that location."""
    res = _trigger(tmp_path, loc, {"success": True})

    assert res["safety"] == [], res
    assert res["posts"] == [], res
    warnings = [t for t in res["toasts"] if t["type"] == "warning"]
    assert len(warnings) == 1 and warnings[0]["duration"] >= 7000, res["toasts"]
    assert [lg["level"] for lg in res["logs"]] == ["WARNING"], res["logs"]
    assert res["unhandled"] == []


def test_trigger_eject_all_reports_a_backend_refusal_instead_of_cleared(tmp_path):
    """FAILS on the old module: a {success: false} answer toasted "Cleared!"."""
    msg = "No location given. Open a location in the Location Manager, then use Eject All."
    res = _trigger(tmp_path, "PM-DB-1", {"success": False, "msg": msg})

    assert res["safety"] == ["Nuke all unslotted in PM-DB-1?"]
    assert res["posts"] == [["/api/manage_contents", {"action": "clear_location", "location": "PM-DB-1"}]]
    assert [t["msg"] for t in res["toasts"]] == [msg], res["toasts"]
    assert res["toasts"][0]["type"] == "warning" and res["toasts"][0]["duration"] >= 7000
    assert res["unhandled"] == []


def test_trigger_eject_all_success_still_says_cleared(tmp_path):
    """Control, PASSES on the old module too."""
    res = _trigger(tmp_path, "PM-DB-1", {"success": True})

    assert res["safety"] == ["Nuke all unslotted in PM-DB-1?"]
    assert res["posts"] == [["/api/manage_contents", {"action": "clear_location", "location": "PM-DB-1"}]]
    assert "Cleared!" in [t["msg"] for t in res["toasts"]], res["toasts"]
    assert res["unhandled"] == []
