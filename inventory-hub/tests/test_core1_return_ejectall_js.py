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
      // Like a real Response: Quick-Swap / Return read text and parse it, so a
      // non-JSON answer can be reported (Group 39.8).
      text: () => Promise.resolve(JSON.stringify(payload)),
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
# ({id: extra}); clicks Yes on whatever overlay it shows. Group 40.6: the
# server's dry run says where the spool goes (its recorded source, else the
# first slot in `slots` bound to the head), as the real route does for these
# one-tap cases; the Return itself answers return_done.
RETURN_SCENARIO = PRINTERS_JS + """
const ROW = __ROW__;
const loaded = __LOADED__;
const spools = __SPOOLS__;
const slots = __SLOTS__;
const unq = (v) => String(v == null ? '' : v).replace(/"/g, '').trim();
window.__respond = (url, method, body) => {
  if (url.startsWith('/api/machine/')) return { status: 404, body: { toolheads: {} } };
  const gc = url.match(/^\\/api\\/get_contents\\?id=(.+)$/);
  if (gc) {
    const th = decodeURIComponent(gc[1]);
    return { body: loaded[th] ? [{ id: loaded[th], display: 'Test spool #' + loaded[th], location: th, slot: '' }] : [] };
  }
  if (url === '/api/quickswap/return' && body && body.dry_run) {
    const th = body.toolhead;
    const sid = loaded[th];
    const extra = spools[String(sid)] || {};
    const bound = slots.find(s => s.target === th);
    const plan = unq(extra.physical_source)
      ? { box: unq(extra.physical_source), slot: unq(extra.physical_source_slot), source: 'physical_source' }
      : (bound ? { box: bound.box, slot: bound.slot, source: 'feed_slot' } : null);
    if (!plan) return { status: 404, body: { action: 'return_no_binding', toolhead: th, active_toolhead: th, requested: th } };
    return { body: Object.assign({ action: 'return_plan', toolhead: th, active_toolhead: th, requested: th,
                                   spool: sid, display: 'Test spool #' + sid, needs_choice: false, note: '' }, plan) };
  }
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
    without a single request, and its Yes posted nothing.

    Group 40.6 (deliberate): the preview comes from the server's dry run (one
    get_contents, by the head lookup; the preview's own second read is gone),
    and the Yes sends the slot the confirm named and the spool it showed."""
    res = run_js(tmp_path, ["inv_quickswap.js"], _return_scenario(
        "CORE1", loaded={"CORE1": 912},
        spools={"912": {"physical_source": '"CR-DB-1"', "physical_source_slot": '"2"'}}))

    assert _titles(res) == ["Return the spool on CORE1?"], res["overlays"]
    assert "CR-DB-1 slot 2" in res["overlays"][0]
    assert _gets(res, "/api/get_contents?id=") == ["/api/get_contents?id=CORE1"], res["fetches"]
    assert _posts(res, "/api/quickswap/return") == [
        {"toolhead": "CORE1", "dry_run": True},
        {"toolhead": "CORE1", "box": "CR-DB-1", "slot": "2", "expected_spool": 912, "confirmed_toolheads": []}]
    assert any(t["type"] == "success" for t in res["toasts"]), res["toasts"]
    assert res["unhandled"] == []


def test_return_on_xl_still_picks_its_first_loaded_head(tmp_path):
    """XL behaviour is unchanged: probe XL-1, then XL-2, act on XL-2. PASSES
    on the old module too. (Group 40.6: the dry run for XL-2 names the slot.)"""
    res = run_js(tmp_path, ["inv_quickswap.js"], _return_scenario(
        "XL", loaded={"XL-2": 913}, slots=[{"box": "LR-DB-1", "slot": "3", "target": "XL-2"}]))

    assert _titles(res) == ["Return the spool on XL-2?"], res["overlays"]
    assert "virtual printer" in res["overlays"][0]
    assert _gets(res, "/api/get_contents?id=") == [
        "/api/get_contents?id=XL-1", "/api/get_contents?id=XL-2"], res["fetches"]
    assert _posts(res, "/api/quickswap/return") == [
        {"toolhead": "XL-2", "dry_run": True},
        {"toolhead": "XL-2", "box": "LR-DB-1", "slot": "3", "expected_spool": 913, "confirmed_toolheads": []}]
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
# Group 41.1 / 41.2: the browser asks the server first (check_only), and only a
# view Eject All may sweep gets "Nuke all unslotted in …?". The run then reports
# what it did, prompts once for the homeless spools, and asks first on a head
# that is printing. Each POST is answered by its kind: __CHECK__ for the check,
# then __RUNS__ in order for the runs.

TRIGGER_SCENARIO = """
const check = __CHECK__;
const runs = __RUNS__;
let runIdx = 0;
window.__respond = (url, method, body) => {
    if (url !== '/api/manage_contents') return { body: [] };
    if (body && body.check_only) return { body: check };
    return { body: runs[Math.min(runIdx++, runs.length - 1)] };
};
const confirms = [];
globalThis.requestConfirmation = (msg, cb) => { confirms.push(String(msg)); window.__confirmCb = cb; };
const printAsks = [];
window.confirmActivePrint = (o) => { printAsks.push(o.msg); window.__printYes = o.onConfirm; };
window.triggerEjectAll(__LOC__);
await __settle(40);
if (typeof window.__safetyCb === 'function') window.__safetyCb();
await __settle(60);
if (__PRINT_YES__ && typeof window.__printYes === 'function') { window.__printYes(); await __settle(60); }
if (__CONFIRM_YES__ && typeof window.__confirmCb === 'function') { window.__confirmCb(); await __settle(60); }
return { safety: __rec.safety, toasts: __rec.toasts, logs: __rec.logs, confirms, printAsks,
         posts: __rec.fetches.filter(f => f.method === 'POST').map(f => [f.url, f.body]) };
"""

CHECK_OK = {"success": True, "check_only": True}
POST_CHECK = ["/api/manage_contents", {"action": "clear_location", "location": "PM-DB-1", "check_only": True}]
POST_RUN = ["/api/manage_contents", {"action": "clear_location", "location": "PM-DB-1"}]


def _result(msg, **lists):
    out = {"success": not lists.get("failed") and not lists.get("needs_unassign"),
           "ejected": [], "needs_unassign": [], "failed": [], "skipped_slotted": [],
           "skipped_loaded": [], "msg": msg}
    out.update(lists)
    return out


def _trigger(tmp_path, loc, check=CHECK_OK, runs=(), confirm_yes=False, print_yes=False) -> dict:
    return run_js(tmp_path, ["inv_loc_mgr.js"], (TRIGGER_SCENARIO
                                                 .replace("__LOC__", json.dumps(loc))
                                                 .replace("__CHECK__", json.dumps(check))
                                                 .replace("__RUNS__", json.dumps(list(runs) or [{}]))
                                                 .replace("__CONFIRM_YES__", "true" if confirm_yes else "false")
                                                 .replace("__PRINT_YES__", "true" if print_yes else "false")))


@pytest.mark.parametrize("loc", ["", "   ", None])
def test_trigger_eject_all_refuses_a_blank_location(tmp_path, loc):
    """FAILS on the old module: it prompted "Nuke all unslotted in ?" (or
    "in null") and, confirmed, posted clear_location for that location."""
    res = _trigger(tmp_path, loc)

    assert res["safety"] == [], res
    assert res["posts"] == [], res
    warnings = [t for t in res["toasts"] if t["type"] == "warning"]
    assert len(warnings) == 1 and warnings[0]["duration"] >= 7000, res["toasts"]
    assert [lg["level"] for lg in res["logs"]] == ["WARNING"], res["logs"]
    assert res["unhandled"] == []


def test_a_view_the_server_refuses_never_shows_the_nuke_prompt(tmp_path):
    """Group 41.1, FAILS on the old module: it asked "Nuke all unslotted in
    LR?" and the refusal (if any) came after the user had said yes."""
    msg = "Eject All is off for rooms, so nothing was moved. Eject from LR's boxes, drawers and shelves."
    res = _trigger(tmp_path, "PM-DB-1", check={"success": False, "blocked_reason": "room_view", "msg": msg})

    assert res["safety"] == [], res
    assert res["posts"] == [POST_CHECK], res
    assert [t["msg"] for t in res["toasts"]] == [msg], res["toasts"]
    assert res["toasts"][0]["type"] == "warning" and res["toasts"][0]["duration"] >= 7000
    assert res["unhandled"] == []


def test_trigger_eject_all_reports_a_backend_refusal_instead_of_cleared(tmp_path):
    """A refusal on the run itself (an unreadable location) is reported, never
    "Cleared!"."""
    msg = "Couldn't read PM-DB-1 from Spoolman, so nothing was ejected. Try again."
    res = _trigger(tmp_path, "PM-DB-1", runs=[{"success": False, "msg": msg}])

    assert res["safety"] == ["Nuke all unslotted in PM-DB-1?"]
    assert res["posts"] == [POST_CHECK, POST_RUN]
    assert [t["msg"] for t in res["toasts"]] == [msg], res["toasts"]
    assert res["toasts"][0]["type"] == "warning" and res["toasts"][0]["duration"] >= 7000
    assert res["unhandled"] == []


def test_a_clean_eject_all_says_what_it_did(tmp_path):
    """Group 41.2, FAILS on the old module: it toasted a bare "Cleared!"."""
    msg = "Eject All on PM-DB-1: ejected 2."
    res = _trigger(tmp_path, "PM-DB-1", runs=[_result(msg, ejected=[1, 2])])

    assert res["posts"] == [POST_CHECK, POST_RUN]
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(msg, "success")], res["toasts"]
    assert res["confirms"] == [] and res["unhandled"] == []


def test_a_failed_eject_raises_an_error_toast(tmp_path):
    msg = "Eject All on PM-DB-1: ejected 1, 1 failed (#33: its eject failed (see the Activity Log))."
    res = _trigger(tmp_path, "PM-DB-1", runs=[_result(msg, ejected=[1], failed=[{"id": 33, "err": "x"}])])

    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(msg, "error")], res["toasts"]
    assert res["toasts"][0]["duration"] >= 7000
    assert res["unhandled"] == []


def test_the_homeless_spools_get_one_prompt_and_its_yes_names_them(tmp_path):
    """Derek's Q1: one "unassign?" prompt for the batch; Yes posts exactly the
    ids it named."""
    ask = "2 spools on PM-DB-1 have no saved home (#32, #35). Unassign them?"
    first = dict(_result("Eject All on PM-DB-1: ejected 1, 2 need a decision.",
                         ejected=[31], needs_unassign=[32, 35]), unassign_msg=ask)
    second = _result("Eject All on PM-DB-1: ejected 2.", ejected=[32, 35])
    res = _trigger(tmp_path, "PM-DB-1", runs=[first, second], confirm_yes=True)

    assert res["confirms"] == [ask], res
    assert res["posts"] == [POST_CHECK, POST_RUN,
                            ["/api/manage_contents", {"action": "clear_location", "location": "PM-DB-1",
                                                      "confirmed_unassign_ids": [32, 35]}]], res["posts"]
    assert [t["type"] for t in res["toasts"]] == ["warning", "success"], res["toasts"]
    assert res["unhandled"] == []


def test_a_printing_head_asks_first_and_its_yes_retries_with_the_flag(tmp_path):
    """Group 41.2, FAILS on the old module: a require_confirm answer was left
    unhandled (the old code returned without a word)."""
    ask = {"success": False, "require_confirm": True, "confirm_type": "active_print",
           "active_print": {"printer_name": "XL", "state": "PRINTING"},
           "msg": "XL is PRINTING — clearing this location will disrupt the print."}
    done = _result("Eject All on PM-DB-1: ejected 1.", ejected=[1])
    res = _trigger(tmp_path, "PM-DB-1", runs=[ask, done], print_yes=True)

    assert res["printAsks"] == [ask["msg"]], res
    assert res["posts"][-1] == ["/api/manage_contents", {"action": "clear_location", "location": "PM-DB-1",
                                                         "confirm_active_print": True}], res["posts"]
    assert [t["type"] for t in res["toasts"]] == ["success"], res["toasts"]
    assert res["unhandled"] == []


# ---------------------------------------------------------------------------
# Undo Last Move (inv_cmd.js), Group 41.4
# ---------------------------------------------------------------------------
# The first press only asks: the server answers the question naming the move
# (and the record's number), the Yes quotes that number, and a printing head
# goes through the shared active-print confirm with its heads. Each POST
# /api/undo is answered by the next of __ANSWERS__.

UNDO_SCENARIO = """
const answers = __ANSWERS__;
let n = 0;
window.__respond = (url, method, body) =>
    url === '/api/undo' ? { body: answers[Math.min(n++, answers.length - 1)] } : { body: [] };
globalThis.updateLogState = () => {};
const confirms = [];
globalThis.requestConfirmation = (msg, cb) => { confirms.push(String(msg)); window.__yes = cb; };
const printAsks = [];
window.confirmActivePrint = (o) => { printAsks.push(o.msg); window.__yes = o.onConfirm; };
window.unionConfirmHeads = (prior, ans) => {
    const out = new Set(prior || []);
    (ans.active_prints || []).forEach(a => out.add(a.toolhead));
    return [...out];
};
triggerUndo();
await __settle(60);
if (__YES__ && typeof window.__yes === 'function') { window.__yes(); await __settle(60); }
return { confirms, printAsks, toasts: __rec.toasts,
         posts: __rec.fetches.filter(f => f.url === '/api/undo').map(f => f.body) };
"""

ASK = {"success": False, "requires_confirm": True, "undo_id": 7, "confirm_type": "undo",
       "active_prints": [], "msg": "Undo: put #57 back in LR-MDB-1 slot 2 and #196 back on XL-2?"}
DONE = {"success": True, "msg": "↩️ Undo: #57 is back in LR-MDB-1 slot 2 (it had been moved to XL-2)",
        "restored": [57]}


def _undo_js(tmp_path, answers, yes=False) -> dict:
    return run_js(tmp_path, ["inv_cmd.js"], (UNDO_SCENARIO
                                             .replace("__ANSWERS__", json.dumps(answers))
                                             .replace("__YES__", "true" if yes else "false")))


def test_undo_asks_first_and_the_yes_quotes_the_record(tmp_path):
    """FAILS on the old module: it posted once, read nothing, and said nothing."""
    res = _undo_js(tmp_path, [ASK, DONE], yes=True)

    assert res["confirms"] == [ASK["msg"]], res
    assert res["posts"] == [{}, {"confirm": True, "undo_id": 7, "confirmed_toolheads": []}], res["posts"]
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(DONE["msg"], "success")], res["toasts"]
    assert res["unhandled"] == []


def test_a_no_to_the_question_changes_nothing(tmp_path):
    res = _undo_js(tmp_path, [ASK, DONE], yes=False)

    assert res["posts"] == [{}], res["posts"]
    assert res["toasts"] == [] and res["unhandled"] == []


def test_a_printing_head_goes_through_the_shared_confirm(tmp_path):
    ask = dict(ASK, confirm_type="active_print",
               active_prints=[{"toolhead": "XL-2", "printer_name": "XL", "state": "PRINTING", "role": "source"}],
               msg="XL is PRINTING: this undo changes XL-2 mid-print. " + ASK["msg"])
    res = _undo_js(tmp_path, [ask, DONE], yes=True)

    assert res["printAsks"] == [ask["msg"]] and res["confirms"] == [], res
    assert res["posts"][-1] == {"confirm": True, "undo_id": 7, "confirmed_toolheads": ["XL-2"]}, res["posts"]
    assert res["unhandled"] == []


def test_nothing_to_undo_is_an_info_toast(tmp_path):
    msg = "Nothing to undo (Undo Last Move reverts spool moves only)."
    res = _undo_js(tmp_path, [{"success": False, "nothing": True, "msg": msg}])

    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(msg, "info")], res["toasts"]
    assert res["unhandled"] == []


def test_a_failed_undo_names_the_spool_at_seven_seconds(tmp_path):
    msg = "Undo could not put back #57 (400: rejected)."
    res = _undo_js(tmp_path, [ASK, {"success": False, "msg": msg}], yes=True)

    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(msg, "error")], res["toasts"]
    assert res["toasts"][0]["duration"] >= 7000
    assert res["unhandled"] == []


# ---------------------------------------------------------------------------
# Location delete (inv_loc_mgr.js), Group 41.3
# ---------------------------------------------------------------------------
# The prompt names what happens to the spools (one contents read); a 409
# requires_confirm (a toolhead whose printer is printing) goes through the
# shared confirm and retries with the flag; a success raises a toast.

DELETE_SCENARIO = """
state.allLocations = __ROWS__;
const contents = __CONTENTS__;
const deletes = __DELETES__;
let d = 0;
window.__respond = (url, method) => {
    if (url.startsWith('/api/get_contents')) return { body: contents };
    if (method === 'DELETE') { const a = deletes[Math.min(d++, deletes.length - 1)]; return { status: a.status || 200, body: a.body }; }
    return { body: [] };
};
globalThis.fetchLocations = () => {};
const confirms = [];
globalThis.requestConfirmation = (msg, cb) => { confirms.push(String(msg)); window.__yes = cb; };
const printAsks = [];
window.confirmActivePrint = (o) => { printAsks.push(o.msg); window.__print = o.onConfirm; };
window.deleteLoc(__LOC__);
await __settle(60);
if (typeof window.__yes === 'function') { window.__yes(); await __settle(60); }
if (typeof window.__print === 'function') { window.__print(); await __settle(60); }
return { confirms, printAsks, toasts: __rec.toasts,
         deletes: __rec.fetches.filter(f => f.method === 'DELETE').map(f => f.url) };
"""


def _delete_js(tmp_path, loc, rows, contents, deletes) -> dict:
    return run_js(tmp_path, ["inv_loc_mgr.js"], (DELETE_SCENARIO
                                                 .replace("__ROWS__", json.dumps(rows))
                                                 .replace("__CONTENTS__", json.dumps(contents))
                                                 .replace("__DELETES__", json.dumps(deletes))
                                                 .replace("__LOC__", json.dumps(loc))))


ROW = {"LocationID": "CR-CT-2-R1", "Type": "Cart Row"}
DELETED = {"status": 200, "body": {"success": True, "msg": "Deleted CR-CT-2-R1: 2 spool(s) → Unassigned."}}


def test_the_delete_prompt_says_what_happens_to_the_spools(tmp_path):
    """Claude's call 16, FAILS on the old module: it asked a bare "Delete
    CR-CT-2-R1?" and raised no toast after a successful delete."""
    contents = [{"id": 3, "location": "CR-CT-2-R1"}, {"id": 4, "location": "CR-CT-2-R1"},
                {"id": 5, "location": "CR-CT-2-R1", "is_ghost": True}]
    res = _delete_js(tmp_path, "CR-CT-2-R1", [ROW], contents, [DELETED])

    assert res["confirms"] == ["Delete CR-CT-2-R1? Its 2 spools go to Unassigned. "
                               "1 spool(s) deployed from it keep their place."], res
    assert res["deletes"] == ["/api/locations?id=CR-CT-2-R1"]
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(DELETED["body"]["msg"], "success")]
    assert res["unhandled"] == []


def test_an_emptied_rooms_prompt_counts_only_its_own_spools(tmp_path):
    rows = [{"LocationID": "DR", "Type": "Room"}]
    contents = [{"id": 1, "location": "DR"}, {"id": 2, "location": "DR-X-9"}]
    res = _delete_js(tmp_path, "DR", rows, contents, [{"body": {"success": True}}])

    assert res["confirms"] == ["Delete DR? Its spool #1 goes to Unassigned."], res
    assert res["unhandled"] == []


def test_a_printing_toolhead_asks_first_and_retries_with_the_flag(tmp_path):
    """Group 41.3, FAILS on the old module: the 409 was toasted as an error
    with no way to confirm and go on."""
    ask = {"status": 409, "body": {"success": False, "status": "requires_confirm",
                                   "confirm_type": "active_print",
                                   "active_print": {"printer_name": "XL", "state": "PRINTING", "toolhead": "XL-5"},
                                   "msg": "XL is PRINTING on XL-5 — deleting it orphans the running spool."}}
    rows = [{"LocationID": "XL-5", "Type": "Tool Head"}]
    res = _delete_js(tmp_path, "XL-5", rows, [{"id": 57, "location": "XL-5"}],
                     [ask, {"body": {"success": True, "msg": "Deleted toolhead XL-5: 1 spool(s) → UNASSIGNED."}}])

    assert res["confirms"] == ["Delete XL-5? Its spool #57 goes to Unassigned."], res
    assert res["printAsks"] == [ask["body"]["msg"]], res
    assert res["deletes"] == ["/api/locations?id=XL-5", "/api/locations?id=XL-5&confirm_active_print=1"]
    assert [t["type"] for t in res["toasts"]] == ["success"], res["toasts"]
    assert res["unhandled"] == []


def test_a_refused_delete_is_an_error_toast(tmp_path):
    msg = "CR-CT-2 still contains CR-CT-2-R1 — move or delete them first."
    rows = [{"LocationID": "CR-CT-2", "Type": "Cart"}]
    res = _delete_js(tmp_path, "CR-CT-2", rows, [], [{"status": 409, "body": {"success": False, "msg": msg}}])

    assert res["confirms"] == ["Delete CR-CT-2? It holds no spools."], res
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [(msg, "error")], res["toasts"]
    assert res["toasts"][0]["duration"] >= 7000
    assert res["unhandled"] == []
