"""Round trips through BOTH halves of a move question (Group 40.3 review, C6;
adopted from the review's C-contract probes).

The browser half and the engine half of 40.3 were built and pinned
separately, with hand-made JS fixtures, so a composition bug ("Load it
instead" after "Just store it" went out as a store) passed every test. Here the
REAL browser modules run under node's vm (the stub DOM of
tests/test_core1_return_ejectall_js.py), and every fetch they make goes, over a
stdin / stdout pipe, to tests/roundtrip_bridge.py: the REAL Flask app and the
REAL engine over the move_engine_harness fakes. Every answer the browser
handles is the engine's own, and every replay it builds is posted back. No
network, no container; everything is written under the test's tmp_path.

A scenario drives the dialogs (click / key) and can change the world between
rounds with ctl(): ctl('repoint', {box, slot, to}), ctl('printing', {printers}),
ctl('move_probe_fail', {printers}), ctl('move', {sid, location, extra}),
ctl('state') (spools, writes, bindings, buffer, logs, requests).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_core1_return_ejectall_js import DRIVER_JS, NODE, RESULT_MARK

HERE = Path(__file__).resolve().parent
HUB = HERE.parent
MODULES = HUB / "static" / "js" / "modules"
BRIDGE = HERE / "roundtrip_bridge.py"

BRIDGE_JS = r"""
const { spawn } = require('child_process');
const __py = spawn(__PYTHON__, [__BRIDGE__, __HUB__, __SETUP__], { cwd: __RUN__, stdio: ['pipe', 'pipe', 'pipe'] });
let __pyBuf = ''; let __pyErr = ''; const __waiters = new Map(); let __seq = 0;
__py.stderr.on('data', d => { __pyErr += d; });
// A bridge that dies early says why (Group 40.3 fix check, S5): it used to
// surface as 'rc=0' with nothing to go on.
let __bridgeDone = false;
__py.on('exit', (code) => {
  if (__bridgeDone) return;
  console.error('roundtrip bridge exited (' + code + ') before the scenario finished:\n' + __pyErr.slice(-4000));
  process.exit(4);
});
__py.stdout.on('data', d => {
  __pyBuf += d;
  let i;
  while ((i = __pyBuf.indexOf('\n')) >= 0) {
    const line = __pyBuf.slice(0, i); __pyBuf = __pyBuf.slice(i + 1);
    if (!line.startsWith('@@')) continue;
    const msg = JSON.parse(line.slice(2));
    const w = __waiters.get(msg.id);
    if (w) { __waiters.delete(msg.id); w(JSON.stringify(msg)); }
  }
});
function __bridgeCall(method, url, bodyStr) {
  return new Promise((resolve) => {
    const id = ++__seq;
    __waiters.set(id, resolve);
    __py.stdin.write(JSON.stringify({ id, method, url, body: bodyStr ? JSON.parse(bodyStr) : null }) + '\n');
  });
}
"""

PRELUDE = r"""
__rec.answers = [];
window.fetch = (url, opts) => {
  const o = opts || {};
  const u = String(url);
  const method = String(o.method || 'GET').toUpperCase();
  let body = null;
  if (o.body) { try { body = JSON.parse(o.body); } catch (e) { body = o.body; } }
  __rec.fetches.push({ url: u, method, body });
  return __bridgeCall(method, u, o.body ? String(o.body) : '').then(txt => {
    const r = JSON.parse(txt);
    const status = r.status || 200;
    const payload = (r.body === undefined || r.body === null) ? {} : r.body;
    __rec.answers.push({ url: u, method, status, body: payload });
    return { ok: status < 400, status,
             json: () => Promise.resolve(JSON.parse(JSON.stringify(payload))),
             text: () => Promise.resolve(JSON.stringify(payload)) };
  });
};
window.fetchT = (u, o) => window.fetch(u, o);
const ctl = (op, body) => __bridgeCall('POST', '/__ctl/' + op, JSON.stringify(body || {})).then(t => JSON.parse(t).body);
const __mounts = [];
const __stubMount = window.mountOverlay;
window.mountOverlay = (opts) => {
  const h = __stubMount(opts);
  h.panel = h.element;
  const ls = [];
  h.element.addEventListener = (t, fn) => ls.push([t, fn]);
  __mounts.push({ opts, el: h.element, ls });
  return h;
};
const lastMount = () => __mounts[__mounts.length - 1];
const btn = (sel) => lastMount().el.querySelector(sel);
const click = async (sel, ms) => { const b = btn(sel); if (b && typeof b.onclick === 'function') b.onclick(); await __settle(ms || 900); };
const key = async (k, extra) => {
  const m = lastMount();
  m.ls.filter(([t]) => t === 'keydown').forEach(([, fn]) => fn(Object.assign(
    { key: k, shiftKey: false, preventDefault() {}, stopPropagation() {} }, extra || {})));
  await __settle(900);
};
const toasts = () => (document.getElementById('toast-container').children || [])
  .map(c => ({ msg: c.innerText, type: String(c.className).replace('toast-msg toast-', '') }))
  .concat((__rec.toasts || []).map(t => ({ msg: t.msg, type: t.type })));
const posts = (url) => __rec.fetches.filter(f => f.method === 'POST' && f.url === url).map(f => f.body);
const answersOf = (url) => __rec.answers.filter(a => a.method === 'POST' && a.url === url).map(a => a.body);
const html = () => __rec.overlays.map(o => o.content);
// What a mounted dialog offers: its buttons by class, and its title.
const offered = (h) => ({ load: /fcc-apc-yes/.test(h), store: /fcc-apc-store/.test(h), cancel: /fcc-apc-no/.test(h),
                          title: ((h.match(/fcc-apc-title"[^>]*>([^<]*)</) || [])[1] || '').trim() });
window.refreshManageView = () => {}; window.fetchLocations = () => {}; window.openSpoolDetails = () => {};
await ctl('state');   // wait for the bridge (it imports the app first)
"""

# The world (as tests/test_fed_head_confirm_40_0c.py and test_expected_feed_40_3.py).
PRINTER_MAP = {f"XL-{n}": {"printer_name": "XL", "position": n - 1} for n in (1, 2, 3)}
PRINTER_MAP["RC-1"] = {"printer_name": "RC", "position": 0}
ROWS = [
    {"LocationID": "LR", "Type": "Room", "Max Spools": "0"},
    {"LocationID": "XL", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": f"XL-{n}", "position": n - 1} for n in (1, 2, 3)]},
    {"LocationID": "XL-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-2", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "XL-3", "Type": "Tool Head", "Max Spools": "1", "parent_id": "XL"},
    {"LocationID": "LR-MDB-1", "Type": "Dryer Box", "Max Spools": "4", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1", "2": "XL-2", "3": "XL-3", "4": "PRINTER:XL"}}},
    {"LocationID": "PM-DB-2", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {"1": "XL-1"}}},
    {"LocationID": "PM-DB-3", "Type": "Dryer Box", "Max Spools": "1", "parent_id": "LR",
     "extra": {"slot_targets": {}}},
    {"LocationID": "CR-CT-2-R1", "Type": "Cart Row", "Max Spools": "0", "parent_id": "LR"},
    {"LocationID": "RC", "Type": "Printer", "Max Spools": "0", "parent_id": "LR",
     "toolheads": [{"location_id": "RC-1", "position": 0}]},
    {"LocationID": "RC-1", "Type": "Tool Head", "Max Spools": "1", "parent_id": "RC"},
]
FROM_POLYDRYER = {"physical_source": "PM-DB-2", "physical_source_slot": "1", "container_slot": ""}
# The browser's own view of the locations (state.allLocations): the same rows.
ALL_LOCATIONS_JS = "state.allLocations = " + json.dumps(ROWS) + ";\n"

SCAN = ["inv_core.js", "ui_builder.js", "inv_cmd.js"]
LM = ["inv_core.js", "ui_builder.js", "inv_loc_mgr.js"]
QS = ["inv_core.js", "ui_builder.js", "inv_quickswap.js"]


def world(spools=None, printing=(), move_probe_fail=(), buffer=None):
    return {"rows": ROWS, "printer_map": PRINTER_MAP, "spools": spools or {},
            "printing": list(printing), "move_probe_fail": list(move_probe_fail), "buffer": buffer or []}


def run(tmp_path: Path, setup: dict, modules: list, scenario: str) -> dict:
    """Run `scenario` (an async JS body that returns a JSON-able value) against
    the real modules, with the real app answering every fetch."""
    setup_path = tmp_path / "setup.json"
    setup_path.write_text(json.dumps(setup), encoding="utf-8")
    driver = (DRIVER_JS
              .replace("__MODULE_PATHS__", json.dumps([str(MODULES / m) for m in modules]))
              .replace("__SCENARIO__", PRELUDE + scenario))
    bridge = (BRIDGE_JS
              .replace("__PYTHON__", json.dumps(sys.executable))
              .replace("__BRIDGE__", json.dumps(str(BRIDGE)))
              .replace("__HUB__", json.dumps(str(HUB)))
              .replace("__SETUP__", json.dumps(str(setup_path)))
              .replace("__RUN__", json.dumps(str(tmp_path))))
    for anchor in ("const vm = require('vm');", "vm.createContext({ console, setTimeout, clearTimeout })",
                   "  process.exit(0);", "  process.exit(3);"):
        assert anchor in driver, f"the node driver changed shape: {anchor!r} is gone"
    driver = driver.replace("const vm = require('vm');", "const vm = require('vm');\n" + bridge, 1)
    driver = driver.replace("vm.createContext({ console, setTimeout, clearTimeout })",
                            "vm.createContext({ console, setTimeout, clearTimeout, __bridgeCall })", 1)
    driver = driver.replace("  process.exit(0);", "  __bridgeDone = true; __py.kill();\n  process.exit(0);", 1)
    driver = driver.replace("  process.exit(3);",
                            "  __bridgeDone = true; try { __py.kill(); } catch (_) {}\n"
                            "  console.error(__pyErr.slice(-4000));\n  process.exit(3);", 1)
    script = tmp_path / "driver.js"
    script.write_text(driver, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180, cwd=str(tmp_path))
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and lines, (
        f"round-trip driver failed (rc={proc.returncode})\nstdout:\n{proc.stdout[-6000:]}\n"
        f"stderr:\n{proc.stderr[-6000:]}")
    out = json.loads(lines[-1][len(RESULT_MARK):])
    return {**out["result"], "unhandled": out["unhandled"]}
