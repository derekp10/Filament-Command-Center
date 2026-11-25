"""The Edit Filament window, hermetic (Group 66): one shared page for its tests.

The REAL templates/components/modals_details.html (Edit Filament, the vendor editor,
the spool and filament windows) and the REAL overlay_mount.js, inv_core.js,
weight_utils.js, empty_weight_field.js and inv_details.js, in `isolated_page` (no
network), so a test runs under --offline. `fetch` answers from `window.__answers` by
path. Only Bootstrap is a stand-in (the page has no CDN), and it takes Bootstrap 5.3's
own paths, so a close by Escape, by ✕ or Cancel (`data-bs-dismiss`) and by a click
outside the dialog all reach the window the way they do in the browser:

  - `FakeModal`: a cancelable `show.bs.modal` then `shown.bs.modal`; a cancelable
    `hide.bs.modal` (prevented: the window stays) then `hidden.bs.modal`; all bubble.
    Escape on the window hides it (Bootstrap's own keydown listener, on the element, in
    the bubble phase, so a capture listener of the page's runs first), and so does a
    mousedown and a click both on the `.modal` itself (the backdrop: the CSS below
    makes the dialog's surround hit the `.modal`). `getInstance` / `getOrCreateInstance`
    keep one instance per element. `window.__dropNextHide = true` drops the next
    `hide()`, as Bootstrap 5.3 drops a hide while the window is still fading in.
  - a delegated document click for `[data-bs-dismiss="modal"]`;
  - `FakeTab`, `FakeOffcanvas`: enough for the calls the page makes.

The fetch stub: every request in `__fetches` ({url, method, body}), every non-GET in
`__posts`; an answer is `__answers[path]` (or `__answers['POST /path']` for one method;
default `{success: true}`), a function of {url, method, body}, the string '__reject__' (a
fetch that fails, as with no network), '__hold__' (answered later by the test:
`window.__held[path](body, status)`), or `{__status: 409, __body: {...}}` for an answer
with that HTTP status. Page errors and unhandled rejections land in `__errors`.

Created by Group 66.6 (the first member that needed it); 66.1, 66.7, 66.8 and 66.9
reuse it (the grounding's cross-check, C14).
"""
from __future__ import annotations

import json
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
DETAILS_HTML = HUB / "templates" / "components" / "modals_details.html"

CSS = (".modal{display:none}"
       ".modal.show{display:block;position:fixed;inset:0;overflow:auto}"
       ".modal-dialog{max-width:800px;margin:40px auto}"
       ".fade{transition:none}")

PRELUDE = r"""
window.__pendingShortcuts = [];
window.registerShortcut = function (s) { window.__pendingShortcuts.push(s); };
window.__fetches = [];
window.__posts = [];
window.__answers = {};
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection', (e) => window.__errors.push(String(e.reason)));
window.fetch = function (url, opts) {
    url = String(url);
    const method = ((opts && opts.method) || 'GET').toUpperCase();
    let body = null;
    if (opts && opts.body) { try { body = JSON.parse(opts.body); } catch (_) { body = opts.body; } }
    window.__fetches.push({ url, method, body });
    if (method !== 'GET') window.__posts.push({ url, method, body });
    const path = url.split('?')[0];
    const key = (method + ' ' + path) in window.__answers ? method + ' ' + path : path;
    let answer = key in window.__answers ? window.__answers[key] : { success: true };
    if (typeof answer === 'function') answer = answer({ url, method, body });
    if (answer === '__reject__') return Promise.reject(new TypeError('Failed to fetch'));
    if (answer === '__hold__') {
        // An answer the test sends later: window.__held[path](body, status).
        return new Promise((resolve) => {
            (window.__held = window.__held || {})[path] = (b, st) => {
                const s = st || 200;
                const t = JSON.stringify(b === undefined ? null : b);
                resolve({ ok: s >= 200 && s < 300, status: s,
                    json: () => Promise.resolve(JSON.parse(t)), text: () => Promise.resolve(t) });
            };
        });
    }
    let status = 200;
    if (answer && typeof answer === 'object' && '__status' in answer) {
        status = answer.__status;
        answer = answer.__body;
    }
    const text = JSON.stringify(answer === undefined ? null : answer);
    return Promise.resolve({ ok: status >= 200 && status < 300, status,
        json: () => Promise.resolve(JSON.parse(text)), text: () => Promise.resolve(text) });
};
try {
    const mem = {};
    const store = {
        getItem: (k) => (k in mem ? mem[k] : null),
        setItem: (k, v) => { mem[k] = String(v); },
        removeItem: (k) => { delete mem[k]; },
        clear: () => { Object.keys(mem).forEach((k) => delete mem[k]); },
        key: (i) => Object.keys(mem)[i] || null,
        get length() { return Object.keys(mem).length; },
    };
    Object.defineProperty(window, 'localStorage', { value: store, configurable: true });
} catch (_) { /* the page's own storage stays */ }

(function () {
    const instances = new WeakMap();
    const fire = (el, type, cancelable) => {
        const ev = new Event(type, { bubbles: true, cancelable: !!cancelable });
        el.dispatchEvent(ev);
        return ev;
    };
    class FakeModal {
        constructor(el) {
            this.el = el;
            instances.set(el, this);
            // Bootstrap 5.3: keydown Escape on the window hides it (keyboard: true).
            el.addEventListener('keydown', (e) => { if (e.key === 'Escape') this.hide(); });
            // Bootstrap 5.3: a mousedown and its click both on the .modal itself (the
            // backdrop) hide it (backdrop: true).
            el.addEventListener('mousedown', (e) => {
                if (e.target !== el) return;
                el.addEventListener('click', (e2) => {
                    if (e.target === el && e2.target === el) this.hide();
                }, { once: true });
            });
        }
        static getInstance(el) { return instances.get(el) || null; }
        static getOrCreateInstance(el) { return instances.get(el) || new FakeModal(el); }
        show() {
            if (this.el.classList.contains('show')) return;
            if (fire(this.el, 'show.bs.modal', true).defaultPrevented) return;
            this.el.classList.add('show');
            this.el.removeAttribute('aria-hidden');
            setTimeout(() => fire(this.el, 'shown.bs.modal', false), 0);
        }
        hide() {
            if (window.__dropNextHide) { window.__dropNextHide = false; window.__droppedHides = (window.__droppedHides || 0) + 1; return; }
            if (!this.el.classList.contains('show')) return;
            if (fire(this.el, 'hide.bs.modal', true).defaultPrevented) return;
            this.el.classList.remove('show');
            this.el.setAttribute('aria-hidden', 'true');
            setTimeout(() => fire(this.el, 'hidden.bs.modal', false), 0);
        }
        toggle() { if (this.el.classList.contains('show')) this.hide(); else this.show(); }
        dispose() { instances.delete(this.el); }
    }
    // Bootstrap's data API: a click on [data-bs-dismiss="modal"] hides its window.
    document.addEventListener('click', (e) => {
        const btn = e.target && e.target.closest ? e.target.closest('[data-bs-dismiss="modal"]') : null;
        if (!btn) return;
        const m = btn.closest('.modal');
        if (m) FakeModal.getOrCreateInstance(m).hide();
    });
    class FakeTab {
        constructor(el) { this.el = el; }
        static getInstance(el) { return new FakeTab(el); }
        static getOrCreateInstance(el) { return new FakeTab(el); }
        show() { window.__tabShown = this.el.id || null; }
    }
    class FakeOffcanvas {
        constructor(el) { this.el = el; }
        static getInstance(el) { return new FakeOffcanvas(el); }
        static getOrCreateInstance(el) { return new FakeOffcanvas(el); }
        show() { this.el.classList.add('show'); }
        hide() { this.el.classList.remove('show'); }
    }
    window.bootstrap = { Modal: FakeModal, Tab: FakeTab, Offcanvas: FakeOffcanvas };
})();
"""

VENDOR = {"id": 2, "name": "Some Brand", "empty_spool_weight": None, "external_id": "", "extra": {},
          "registered": "2026-02-11T04:07:24Z"}

# /api/external/fields as Edit Filament reads it: the attributes chip field, the
# slicer profile and the label status.
FIELDS = {"success": True, "fields": {
    "filament": [
        {"entity_type": "filament", "field_type": "choice", "multi_choice": True,
         "key": "filament_attributes", "name": "Attributes", "choices": ["Silk", "Matte", "Glow"], "order": 1},
        {"entity_type": "filament", "field_type": "choice", "multi_choice": False,
         "key": "slicer_profile", "name": "Slicer Profile", "choices": ["Basic PLA"], "order": 2},
        {"entity_type": "filament", "field_type": "text", "key": "product_url", "name": "Product Link", "order": 3},
    ],
    "spool": [],
}}

DEFAULT_ANSWERS = {
    "/api/vendors": {"success": True, "vendors": [VENDOR]},
    "/api/materials": {"success": True, "materials": ["PLA", "PETG"]},
    "/api/external/fields": FIELDS,
    "/api/update_filament": {"success": True},
}


def filament(**over):
    """A filament as /api/filament_details hands it to Edit Filament (FCC's parsed
    form: each extra decoded once), with `over` laid on top."""
    fil = {
        "id": 7, "name": "Red", "material": "PLA", "color_hex": "72071C", "multi_color_hexes": None,
        "multi_color_direction": None, "density": 1.24, "diameter": 1.75, "weight": 1000.0,
        "spool_weight": 150.0, "price": 20.0, "external_id": "", "comment": "",
        "settings_extruder_temp": 215, "settings_bed_temp": 60,
        "vendor": dict(VENDOR), "extra": {},
    }
    fil.update(over)
    return fil


def load(page, answers=None):
    """The window's page: the modal markup, the stand-ins, then the modules in the
    dashboard's order, inv_details.js's ready handlers run by hand (the page has
    loaded already, as in test_enter_presses_buttons_50_6.py's `_load_details`)."""
    page.set_content('<!doctype html><html><head><meta charset="utf-8"><style>' + CSS + '</style></head><body>'
                     '<div id="toast-container"></div>' + DETAILS_HTML.read_text(encoding="utf-8")
                     + '</body></html>')
    page.add_script_tag(content=PRELUDE)
    page.evaluate("(a) => { Object.assign(window.__answers, a); }", {**DEFAULT_ANSWERS, **(answers or {})})
    for name in ("overlay_mount.js", "inv_core.js", "weight_utils.js", "empty_weight_field.js"):
        page.add_script_tag(content=(MODULES / name).read_text(encoding="utf-8"))
    page.evaluate("""() => { window.__add = document.addEventListener; window.__ready = [];
        document.addEventListener = function (t, f, o) {
            if (t === 'DOMContentLoaded') window.__ready.push(f); else window.__add.call(document, t, f, o); }; }""")
    page.add_script_tag(content=(MODULES / "inv_details.js").read_text(encoding="utf-8"))
    page.evaluate("() => { document.addEventListener = window.__add; window.__ready.forEach((f) => f()); }")
    return page


def open_form(page, fil):
    """Open Edit Filament on `fil` and wait until it is shown and its three reads
    (materials, vendors, extra fields) have landed."""
    page.evaluate("(f) => window.openEditFilamentForm(f)", fil)
    page.wait_for_function("() => document.getElementById('editFilamentModal').classList.contains('show')")
    page.wait_for_function("""() => ['/api/materials', '/api/vendors', '/api/external/fields'].every(
        (p) => window.__fetches.some((f) => f.url.split('?')[0] === p))""")
    page.wait_for_timeout(50)   # the reads' .then() handlers and shown.bs.modal
    return page


def shown(page):
    return page.evaluate("() => document.getElementById('editFilamentModal').classList.contains('show')")


def asked(page):
    """Is Edit Filament's "Close without saving?" question up?"""
    return page.evaluate("() => !!(window.getOverlay && window.getOverlay('editfil-esc-confirm'))")


def chips(page):
    """The attribute chips Edit Filament shows, in order."""
    return page.evaluate("""() => Array.from(document.querySelectorAll('#editfil-attr-chips .editfil-chip'))
        .map((c) => c.getAttribute('data-value'))""")


def save(page):
    """Press the real Save and answer with every post it made."""
    before = page.evaluate("window.__posts.length")
    page.locator("#editfil-save").click()
    page.wait_for_timeout(100)
    return page.evaluate("(n) => window.__posts.slice(n)", before)


def posts_to(page, path):
    return page.evaluate("(p) => window.__posts.filter((x) => x.url.split('?')[0] === p)", path)


def errors(page):
    return page.evaluate("window.__errors")


def js(value):
    return json.dumps(value)
