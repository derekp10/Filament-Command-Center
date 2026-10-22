"""The per-browser Text size (Derek, 2026-10-21): Settings -> 🖥️ This Browser ->
"Text size": Small / Standard (the default) / Large / Extra Large, kept in this
browser's localStorage under 'fcc.textSize'.

Hermetic: node's `vm` with a tiny stub DOM, no browser, no container, so it
runs under --offline. It checks:
  - the script in dashboard.html's <head> (#fcc-text-size-boot) that applies
    the stored size before the first paint: each name, nothing stored, a junk
    value, blocked storage; and that it sits in <head> before the stylesheets,
    so nothing can paint at the wrong size first;
  - text_size.js, which changes the size LIVE from Settings: a pick (by mouse
    or keyboard, both fire `change`) shows the size and stores it, Save then
    has nothing left to do for it, a junk value is ignored, and a browser that
    refuses to store it still shows the size and says it won't last;
  - config_schema.py's Field, the <head> script, text_size.js and global.css
    agree on the four names and what each one does.
The browser proof (applied before paint on the real page, the Settings control
by mouse and keyboard, each size's root and named sizes, the title bar on one
line) is test_text_size_setting_e2e.py.

HEAD proof (feat/readability-2026-10-21 cab9127, before the setting; a
throwaway worktree with only this file copied in): all 14 RED (5 failed, and
9 errors where the node run itself has no <head> script to run). There was no
#fcc-text-size-boot script, no text_size.js, no 'fcc.textSize' Field and no
size rules in global.css.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from test_core1_return_ejectall_js import NODE, pytestmark  # noqa: F401  (pytestmark: skip without node)

HUB = Path(__file__).resolve().parent.parent
DASHBOARD = HUB / "templates" / "dashboard.html"
MODULE = HUB / "static" / "js" / "modules" / "text_size.js"
GLOBAL_CSS = HUB / "static" / "css" / "global.css"

NAMES = {"Small": "small", "Standard": "standard", "Large": "large", "Extra Large": "xlarge"}
SELECT_SEL = '.cfgset-input[data-key="fcc.textSize"]'


def _boot_script() -> str:
    html = DASHBOARD.read_text(encoding="utf-8")
    m = re.search(r'<script id="fcc-text-size-boot">(.*?)</script>', html, re.S)
    assert m, "dashboard.html has no <script id=\"fcc-text-size-boot\">"
    return m.group(1)


# A stub page: <html>'s attributes, a localStorage (or one that throws), the
# document's listeners and dispatched events, and the toasts shown.
DRIVER = r"""
const vm = require('vm');
const fs = require('fs');
const BOOT = __BOOT__;
const MODULE = fs.readFileSync(__MODULE__, 'utf8');
const SELECT_SEL = __SELECT_SEL__;

function env(stored, opts) {
  opts = opts || {};
  const attrs = Object.assign({}, opts.attrs || {});
  const store = new Map();
  if (stored !== null && stored !== undefined) store.set('fcc.textSize', stored);
  const blocked = () => { throw new Error('storage blocked'); };
  const localStorage = opts.blockRead ? { getItem: blocked, setItem: blocked }
    : opts.blockWrite ? { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: blocked }
    : { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => { store.set(k, String(v)); } };
  const listeners = {};
  const events = [];
  const toasts = [];
  const documentElement = {
    setAttribute: (k, v) => { attrs[k] = String(v); },
    getAttribute: (k) => (Object.prototype.hasOwnProperty.call(attrs, k) ? attrs[k] : null),
    hasAttribute: (k) => Object.prototype.hasOwnProperty.call(attrs, k),
  };
  const document = {
    documentElement,
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    dispatchEvent: (e) => { events.push({ type: e.type, detail: e.detail }); return true; },
  };
  const window = { localStorage, showToast: (m, t, d) => toasts.push([m, t, d]) };
  window.window = window;
  window.document = document;
  class CustomEvent { constructor(type, init) { this.type = type; this.detail = init ? init.detail : undefined; } }
  const ctx = vm.createContext({ window, document, CustomEvent, console });
  return { ctx, attrs, store, listeners, events, toasts, window };
}

// A Settings select as inv_settings.js draws it, after a pick.
function select(value, initial, key) {
  const dataKey = key || 'fcc.textSize';
  return { value, dataset: { initial, key: dataKey },
           matches: (sel) => sel === '.cfgset-input[data-key="' + dataKey + '"]' };
}

const out = {};

// 1. The <head> script.
out.boot = {};
for (const [label, stored, opts] of [
    ['none', null], ['Small', 'Small'], ['Standard', 'Standard'], ['Large', 'Large'],
    ['Extra Large', 'Extra Large'], ['junk', 'Huge'], ['lowercase', 'large'], ['slug', 'xlarge'],
    ['proto', '__proto__'], ['ctor', 'constructor'], ['empty', ''],
    ['blocked', 'Large', { blockRead: true }]]) {
  const e = env(stored, opts);
  vm.runInContext(BOOT, e.ctx);
  out.boot[label] = e.attrs['data-fcc-text-size'];
}

// 2. text_size.js, loaded on a page whose <head> script already ran.
function loaded(stored, opts) {
  const e = env(stored, opts);
  vm.runInContext(BOOT, e.ctx);
  vm.runInContext(MODULE, e.ctx);
  return e;
}
{
  const e = loaded('Large');
  const api = e.window.fccTextSize;
  out.api = { key: api.KEY, def: api.DEFAULT, sizes: Object.assign({}, api.SIZES), get: api.get(),
              frozen: Object.isFrozen(api) && Object.isFrozen(api.SIZES),
              changeListeners: (e.listeners.change || []).length, attr: e.attrs['data-fcc-text-size'],
              eventsAtLoad: e.events.length };
}
{
  // A pick in Settings: shown and stored at once, Save then sees no change.
  const e = loaded(null);
  const el = select('Extra Large', 'Standard');
  e.listeners.change.forEach((fn) => fn({ target: el }));
  out.pick = { attr: e.attrs['data-fcc-text-size'], stored: e.store.get('fcc.textSize'), initial: el.dataset.initial,
               events: e.events.slice(), toasts: e.toasts.length };
  // The keyboard walks the list one step at a time: each step fires change.
  const steps = [];
  for (const v of ['Large', 'Standard', 'Small']) {
    el.value = v;
    e.listeners.change.forEach((fn) => fn({ target: el }));
    steps.push([e.attrs['data-fcc-text-size'], e.store.get('fcc.textSize')]);
  }
  out.steps = steps;
  out.stepEvents = e.events.map((x) => x.detail.size);
}
{
  // Another setting's select, a junk value, a non-element: all ignored.
  const e = loaded('Large');
  e.listeners.change.forEach((fn) => fn({ target: select('net', 'additive', 'fcc.weighEntry.defaultMode') }));
  e.listeners.change.forEach((fn) => fn({ target: select('Gigantic', 'Large') }));
  e.listeners.change.forEach((fn) => fn({ target: null }));
  e.listeners.change.forEach((fn) => fn({ target: {} }));
  out.ignored = { attr: e.attrs['data-fcc-text-size'], stored: e.store.get('fcc.textSize'), events: e.events.length,
                  toasts: e.toasts.length };
}
{
  // The browser refuses to store it: the size still shows, a 7 s warning
  // says it won't last, and Save is left to try again.
  const e = loaded('Small', { blockWrite: true });
  const el = select('Large', 'Small');
  e.listeners.change.forEach((fn) => fn({ target: el }));
  out.refused = { attr: e.attrs['data-fcc-text-size'], stored: e.store.get('fcc.textSize'), initial: el.dataset.initial,
                  toasts: e.toasts };
}
{
  // set() / apply() / get() directly.
  const e = loaded(null);
  const api = e.window.fccTextSize;
  out.direct = { setJunk: api.set('Huge'), attrAfterJunk: e.attrs['data-fcc-text-size'],
                 setSmall: api.set('Small'), attrSmall: e.attrs['data-fcc-text-size'], get: api.get(),
                 applyJunk: api.apply('Huge'), attrApplyJunk: e.attrs['data-fcc-text-size'],
                 storedAfterApply: e.store.get('fcc.textSize') };
}
{
  // A page built without the <head> script: the module applies the stored size.
  const e = env('Extra Large');
  vm.runInContext(MODULE, e.ctx);
  out.noBoot = e.attrs['data-fcc-text-size'];
  const e2 = env(null, { blockRead: true });
  vm.runInContext(MODULE, e2.ctx);
  out.noBootBlocked = [e2.attrs['data-fcc-text-size'], e2.window.fccTextSize.get()];
}
console.log('@@RESULT@@' + JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    driver = (DRIVER.replace("__BOOT__", json.dumps(_boot_script()))
              .replace("__MODULE__", json.dumps(str(MODULE)))
              .replace("__SELECT_SEL__", json.dumps(SELECT_SEL)))
    script = tmp_path_factory.mktemp("text_size") / "driver.js"
    script.write_text(driver, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("@@RESULT@@")]
    assert proc.returncode == 0 and lines, f"node failed (rc={proc.returncode})\n{proc.stdout}\n{proc.stderr}"
    return json.loads(lines[-1][len("@@RESULT@@"):])


# ---------------------------------------------------------------------------
# The <head> script: the size is on <html> before the first paint
# ---------------------------------------------------------------------------

def test_the_head_script_applies_each_stored_size(run):
    boot = run["boot"]
    assert {k: boot[k] for k in NAMES} == NAMES, boot


def test_the_head_script_falls_back_to_standard(run):
    """Nothing stored, a value it doesn't know (wrong case, a slug, a name of
    Object's own), or a browser that won't let it read storage: Standard."""
    boot = run["boot"]
    for label in ("none", "junk", "lowercase", "slug", "proto", "ctor", "empty", "blocked"):
        assert boot[label] == "standard", (label, boot[label])


def test_the_head_script_runs_before_anything_can_paint():
    """In <head>, before the stylesheets and before <body>: the size is set
    before the browser has anything to draw."""
    html = DASHBOARD.read_text(encoding="utf-8")
    head_end = html.index("</head>")
    boot = html.index('<script id="fcc-text-size-boot">')
    first_css = min(html.index(m.group(0)) for m in re.finditer(r'<link[^>]+(?:stylesheet|\.css)[^>]*>', html))
    assert boot < first_css < head_end, (boot, first_css, head_end)
    assert boot < html.index("<body")
    # Inline, so there is no request to wait for; and plain ES5 (var), so it
    # can't fail to parse on an old browser and leave the page unsized.
    script = _boot_script()
    assert "src=" not in html[boot:boot + 60]
    assert "const " not in script and "let " not in script and "=>" not in script, script


# ---------------------------------------------------------------------------
# text_size.js: the live change from Settings
# ---------------------------------------------------------------------------

def test_the_module_reads_the_same_names_and_changes_nothing_at_load(run):
    api = run["api"]
    assert api["key"] == "fcc.textSize" and api["def"] == "Standard" and api["sizes"] == NAMES
    assert api["get"] == "Large" and api["attr"] == "large"
    assert api["frozen"] is True
    assert api["changeListeners"] == 1
    assert api["eventsAtLoad"] == 0, "loading the module must not announce a change"


def test_a_pick_in_settings_shows_and_keeps_the_size_at_once(run):
    """No Save needed: the attribute and localStorage change on the pick, and
    the select's data-initial follows, so Save settings sees nothing left to do."""
    pick = run["pick"]
    assert pick["attr"] == "xlarge" and pick["stored"] == "Extra Large", pick
    assert pick["initial"] == "Extra Large", pick
    assert pick["events"] == [{"type": "fcc:text-size", "detail": {"name": "Extra Large", "size": "xlarge"}}]
    assert pick["toasts"] == 0


def test_each_keyboard_step_shows_its_size(run):
    """Arrow keys on the focused select fire `change` once per step."""
    assert run["steps"] == [["large", "Large"], ["standard", "Standard"], ["small", "Small"]]
    assert run["stepEvents"] == ["xlarge", "large", "standard", "small"]


def test_other_selects_and_junk_values_are_left_alone(run):
    assert run["ignored"] == {"attr": "large", "stored": "Large", "events": 0, "toasts": 0}


def test_a_browser_that_will_not_store_it_still_shows_it_and_says_so(run):
    r = run["refused"]
    assert r["attr"] == "large" and r["stored"] == "Small", r
    assert r["initial"] == "Small", "Save must be left to try again"
    assert len(r["toasts"]) == 1, r["toasts"]
    msg, kind, ms = r["toasts"][0]
    assert kind == "warning" and ms >= 7000, r["toasts"]
    assert "could not keep it" in msg and "Small" in msg, msg


def test_set_apply_and_get(run):
    d = run["direct"]
    assert d["setJunk"] is False and d["attrAfterJunk"] == "standard"
    assert d["setSmall"] is True and d["attrSmall"] == "small" and d["get"] == "Small"
    assert d["applyJunk"] == "standard" and d["attrApplyJunk"] == "standard"
    assert d["storedAfterApply"] == "Small", "apply() shows a size without storing it"


def test_a_page_without_the_head_script_still_gets_its_size(run):
    assert run["noBoot"] == "xlarge"
    assert run["noBootBlocked"] == ["standard", "Standard"]


# ---------------------------------------------------------------------------
# One set of names everywhere
# ---------------------------------------------------------------------------

def _pairs(js: str) -> dict:
    return dict(re.findall(r"'([A-Za-z ]+)':\s*'([a-z]+)'", js))


def test_the_head_script_and_the_module_use_the_same_names():
    assert _pairs(_boot_script()) == NAMES
    assert _pairs(MODULE.read_text(encoding="utf-8")) == NAMES


def test_the_settings_field_offers_the_same_names():
    import config_schema
    f = next((f for f in config_schema.CONFIG_SCHEMA if f.key == "fcc.textSize"), None)
    assert f is not None, "config_schema has no fcc.textSize Field"
    assert (f.type, f.default, f.section, f.scope) == ("select", "Standard", "client", "client")
    assert f.choices == list(NAMES), f.choices
    assert any(s.key == f.section for s in config_schema.SECTIONS)


def test_scripts_html_loads_the_module():
    scripts = (HUB / "templates" / "components" / "scripts.html").read_text(encoding="utf-8")
    assert "js/modules/text_size.js" in scripts


def test_global_css_gives_each_size_its_values():
    """Small: the named sizes take FCC's compact sizes from before the rule
    (a badge 12 px, a note 12.8 px), root unchanged. Standard: the :root
    values (test_text_size_floor.py pins them). Large / Extra Large: only the
    root grows, as a percentage of the browser's own default."""
    css = GLOBAL_CSS.read_text(encoding="utf-8")

    def block(slug):
        m = re.search(r':root\[data-fcc-text-size="%s"\]\s*\{([^}]*)\}' % slug, css)
        assert m, f"global.css has no :root[data-fcc-text-size=\"{slug}\"] rule"
        return dict(re.findall(r"([-\w]+)\s*:\s*([^;]+);", m.group(1)))

    assert block("small") == {"--fcc-fs-label": "0.75rem", "--fcc-fs-small": "0.8rem", "--fcc-fs-row": "0.85rem"}
    assert block("large") == {"font-size": "112.5%"}
    assert block("xlarge") == {"font-size": "125%"}
    assert not re.search(r'data-fcc-text-size="standard"', css), "Standard is the plain :root values"
