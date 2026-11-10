"""No script on the page reads, while it loads, a name a later script defines
(Group 53.3, the load-order canary).

Why: the dashboard loads about forty classic scripts in a fixed order
(templates/dashboard.html, which includes templates/components/scripts.html at
the end of its body). A script that, WHILE IT LOADS, reads a window property or
a bare global that a LATER script defines gets `undefined`, so an
`if (window.X)` guard silently does nothing. Real precedent: shortcuts
registered at load before shortcuts_registry.js loaded were silently dropped
from the ? overlay, until the queueing shim at the top of scripts.html
(2026-08-05). Splitting the big modules is safe once this canary guards it.

How (node's `vm`: no browser, no container, so it runs under --offline):
  1. read_page_scripts() reads the page's real script order from the templates:
     dashboard.html with every {% include %} expanded in place, Jinja and HTML
     comments dropped, then every <script> in document order: a file under
     static/, a CDN library (stood in for by the globals it sets, CDN_GLOBALS),
     or an inline script with each {{ ... }} replaced by null.
  2. Pass 1 loads every script over a browser stub (STUB_JS) and records which
     script first defines each name: a new property of window (a function
     declaration, a var, a `window.X = ...`), or a new top-level const / let /
     class (those never land on window: V8 is asked which names resolve after
     the script that didn't before).
  3. Pass 2 loads them again in a fresh context where each of those names is
     first planted on window as an accessor that records who read it and
     returns undefined. The defining script's own definition replaces it (a
     const / let / class shadows it), so a read recorded while an EARLIER
     script runs is an early read.
The stub runs only what runs at load: document.readyState is 'loading',
DOMContentLoaded never fires, timers and animation frames never fire, fetch
never answers. Promise callbacks run when each script ends, as at the
browser's microtask checkpoint, and count as that script's load.

What it catches: a script that throws while loading; a load-time read (window.X,
a bare X, typeof X) of a name a later script defines, in a script's top-level
code or anything that code calls; a load-time window.X read of a name that is
only a top-level const / let / class (never on window, so always undefined); a
file under static/js that the page doesn't load, or loads twice, and a page
script missing from disk (a module split that forgets scripts.html); and
template constructs it can't model (a <script> inside {% if %} / {% for %},
Jinja control flow in an inline script, an async / defer / module script, a CDN
library it doesn't know), which fail loudly with "teach the canary".

What it can't see:
  - code paths the stub doesn't take: getElementById always finds a dummy
    element, querySelector never finds one, matchMedia never matches, storage
    starts empty;
  - reads inside handlers, timers and fetch callbacks: those run at call time,
    after every script has loaded, which is exactly where this canary asks a
    read to move;
  - an `'X' in window` / hasOwnProperty / getOwnPropertyDescriptor check of a
    name pass 2 planted: the accessor is there, so the check says "present"
    before the defining script has run, and no read is recorded.

When it fails:
  - an early read: move the read into a function that runs later (on
    DOMContentLoaded, or in a handler such as a click), or load the defining
    script earlier in scripts.html. A deliberate, harmless early read (a guard
    meant to find nothing at load and retried later) goes in
    ALLOWED_EARLY_READS as (reader script, name): the reason, named as the
    failure names them. The list starts empty, an entry needs a reason, and an
    entry no longer read early fails too.
  - a throw: either a gap in the stub (a browser feature STUB_JS lacks: add a
    plain stand-in that does nothing, never one for an FCC name) or a real
    load-time error (it would throw in a browser too: fix the script).
  - a CDN library it doesn't know: add a part of its URL to CDN_GLOBALS with
    every global the real bundle sets on window (its UMD line,
    `global.X = factory()`, or a top-level var), and a stand-in for each to
    STUB_JS's cdnStandIns.

Needs node on PATH (skips with a PytestWarning without it, as
test_core1_return_ejectall_js.py does; FCC_REQUIRE_NODE=1 makes that an error).
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from test_core1_return_ejectall_js import NODE, pytestmark  # noqa: F401  (pytestmark: skip without node)

HUB = Path(__file__).resolve().parent.parent
TEMPLATES = HUB / "templates"
STATIC = HUB / "static"
ENTRY = "dashboard.html"
SCRIPTS_HTML = "templates/components/scripts.html"
RESULT_MARK = "__FCC_LOAD_ORDER__"

# Every CDN library the page loads, by a part of its URL, with every global the
# real bundle sets on window (read from the bundles themselves, 2026-11-09). FCC
# reads only bootstrap, Swal and QRCode; the rest are listed so an early read
# of them would be seen too. Each needs a stand-in in STUB_JS's cdnStandIns.
CDN_GLOBALS = {
    # UMD: (globalThis).bootstrap = factory(). Popper is bundled inside it, not a global.
    "bootstrap.bundle": ("bootstrap",),
    # UMD: (globalThis).Sweetalert2 = factory(), then
    # this.swal = this.sweetAlert = this.Swal = this.SweetAlert = this.Sweetalert2.
    "sweetalert2": ("Sweetalert2", "Swal", "SweetAlert", "swal", "sweetAlert"),
    # `var QRCode;` at the top of qrcode.min.js; the rest is inside its IIFE.
    "qrcodejs": ("QRCode",),
}

# (reader script, name) -> why that early read is safe, both named as the
# failure names them ("js/modules/inv_cmd.js", "templates/components/
# scripts.html:103 (inline)"). Starts empty: an entry is an early read someone
# looked at and judged harmless (a guard meant to find nothing at load that is
# tried again later), never a way to quiet a read nobody understood.
ALLOWED_EARLY_READS: dict = {}

# Browser names the stub provides that a page script replaces on purpose
# (window.onerror = ..., a wrapped fetch), each with why. Starts empty.
STUB_NAMES_THE_PAGE_SETS: dict = {}

_TEACH = "teach the canary"


class CanaryCannotRead(Exception):
    """The templates hold something read_page_scripts can't model."""


# ---------------------------------------------------------------------------
# The page's scripts, in order, read from the templates
# ---------------------------------------------------------------------------

_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.S)
_JINJA_STATEMENT = re.compile(r"\{%-?\s*([A-Za-z_]\w*)(.*?)-?%\}", re.S)
_JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.S)
_INCLUDE_TARGET = re.compile(r"""\s*(['"])([^'"]+)\1""")
# A <script> inside these never runs at load: a <template>'s content is inert,
# and the others hold raw text.
_INERT = ("template", "textarea", "style", "title", "noscript")
_TOKEN = re.compile(r"<!--|\{%|<(script|" + "|".join(_INERT) + r")\b", re.I)
_SCRIPT_OPEN = re.compile(r"<script\b([^>]*)>", re.I)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.I)
_ATTRIBUTE = re.compile(r"""([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?""")
_STATIC_SRC = re.compile(
    r"""\{\{\s*url_for\(\s*['"]static['"]\s*,\s*filename\s*=\s*['"]([^'"]+)['"]\s*\)\s*\}\}(?:\?\S*)?""")
_JS_TYPES = {"text/javascript", "application/javascript", "application/x-javascript",
             "text/ecmascript", "application/ecmascript", "text/jscript"}
# Jinja statements that open a block closed by an {% end... %}.
_BLOCKS = {"if", "for", "block", "macro", "call", "filter", "with", "autoescape", "raw", "trans"}


def _blank(text: str) -> str:
    """Spaces for all but line breaks, so lines and columns stay where they were."""
    return re.sub(r"[^\n]", " ", text)


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def read_page_scripts(templates: Path = TEMPLATES, static: Path = STATIC, entry: str = ENTRY) -> list:
    """The page's <script>s in the order the browser runs them.

    Each is a dict: kind ("file", "cdn" or "inline"), name (how failures name
    it: "js/modules/inv_core.js", a CDN URL, "templates/components/
    scripts.html:18 (inline)"), where (the template line of its tag), and per
    kind file / globals / code, plus the filename and line offsets node gives
    its stack frames. Raises CanaryCannotRead on anything it can't model.
    """
    scripts: list = []
    _read_template(templates, static, entry, scripts, inside=None, chain=())
    return scripts


def _read_template(templates: Path, static: Path, rel: str, scripts: list, inside, chain: tuple) -> None:
    if rel in chain:
        raise CanaryCannotRead(f"templates/{rel} includes itself: {' -> '.join(chain + (rel,))}.")
    path = templates / rel
    if not path.is_file():
        by = f"templates/{chain[-1]}" if chain else "the page"
        raise CanaryCannotRead(f"{by} includes templates/{rel}, which is not on disk.")
    text = _JINJA_COMMENT.sub(lambda m: _blank(m.group(0)), path.read_text(encoding="utf-8"))
    here = f"templates/{rel}"
    blocks: list = []  # the Jinja blocks open at this point: (statement, line)
    pos = 0
    while True:
        m = _TOKEN.search(text, pos)
        if not m:
            return
        line = _line(text, m.start())
        if m.group(0) == "<!--":
            end = text.find("-->", m.end())
            pos = len(text) if end < 0 else end + 3
            continue
        if m.group(0) == "{%":
            st = _JINJA_STATEMENT.match(text, m.start())
            if not st:
                raise CanaryCannotRead(f"{here}:{line}: a {{% with no %}}.")
            pos = st.end()
            keyword, args = st.group(1), st.group(2)
            if keyword == "include":
                target = _INCLUDE_TARGET.match(args)
                if not target:
                    raise CanaryCannotRead(
                        f"{here}:{line}: {st.group(0)!r} names its template in a way the canary can't read; "
                        f"{_TEACH} (read_page_scripts) how to find it.")
                opened = inside or (f"{{% {blocks[-1][0]} %}} at {here}:{blocks[-1][1]}" if blocks else None)
                _read_template(templates, static, target.group(2), scripts, opened, chain + (rel,))
            elif keyword == "extends":
                raise CanaryCannotRead(
                    f"{here}:{line}: {{% extends %}} puts this template's blocks into another one; "
                    f"{_TEACH} (read_page_scripts) how the page is put together.")
            elif keyword.startswith("end"):
                if blocks:
                    blocks.pop()
            elif keyword in _BLOCKS or (keyword == "set" and "=" not in args):
                blocks.append((keyword, line))
            continue
        tag = m.group(1).lower()
        if tag != "script":
            pos = _skip_element(text, m.start(), tag)
            continue
        opened_tag = _SCRIPT_OPEN.match(text, m.start())
        closed_tag = _SCRIPT_CLOSE.search(text, opened_tag.end()) if opened_tag else None
        if not closed_tag:
            raise CanaryCannotRead(f"{here}:{line}: a <script> with no </script>.")
        pos = closed_tag.end()
        where = f"{here}:{line}"
        condition = inside or (f"{{% {blocks[-1][0]} %}} at {here}:{blocks[-1][1]}" if blocks else None)
        if condition:
            raise CanaryCannotRead(
                f"{where}: this <script> sits inside {condition}, so whether (and how often) it loads depends on "
                f"the template's data, while the canary reads the page as one fixed list. Move the <script> out "
                f"of the block, or {_TEACH} (read_page_scripts) how to read it.")
        attrs = _attributes(opened_tag.group(1))
        for flag in ("async", "defer", "nomodule"):
            if flag in attrs:
                raise CanaryCannotRead(
                    f"{where}: a <script {flag}> doesn't run in the page's order; "
                    f"{_TEACH} (read_page_scripts) when it runs.")
        kind = (attrs.get("type") or "").strip().lower()
        if kind == "module":
            raise CanaryCannotRead(
                f'{where}: a <script type="module"> runs once the page is parsed, in a scope of its own; '
                f"{_TEACH} (read_page_scripts) how to load it.")
        if kind and kind not in _JS_TYPES:
            continue  # a data block (type="application/json" and the like): never run
        if "src" in attrs:
            scripts.append(_src_script((attrs["src"] or "").strip(), static, where))
            continue
        body = text[opened_tag.end():closed_tag.start()]
        if "{%" in body:
            raise CanaryCannotRead(
                f"{where}: this inline script holds Jinja control flow ({{% ... %}}), so its code depends on the "
                f"template's data. Move the logic out of the script, or {_TEACH} (read_page_scripts) how to "
                f"read it.")
        # A value from the server becomes null; its line breaks stay, so the
        # script's lines are still the template's.
        code = _JINJA_EXPRESSION.sub(lambda e: "null" + "\n" * e.group(0).count("\n"), body)
        script_id = attrs.get("id")
        scripts.append({
            "kind": "inline",
            "name": f"{where} (inline{' #' + script_id if script_id else ''})",
            "where": where,
            "code": code,
            "filename": here,
            "lineOffset": _line(text, opened_tag.end()) - 1,
            "columnOffset": opened_tag.end() - (text.rfind("\n", 0, opened_tag.end()) + 1),
        })


def _skip_element(text: str, start: int, tag: str) -> int:
    """The end of an element whose content never runs as script (nested <template>s too)."""
    pattern = re.compile(r"<(/?)" + tag + r"\b[^>]*>", re.I)
    depth = 0
    for m in pattern.finditer(text, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return m.end()
    return len(text)


def _attributes(raw: str) -> dict:
    attrs: dict = {}
    for m in _ATTRIBUTE.finditer(raw):
        value = next((v for v in m.group(2, 3, 4) if v is not None), None)
        attrs.setdefault(m.group(1).lower(), value)
    return attrs


def _src_script(src: str, static: Path, where: str) -> dict:
    local = _STATIC_SRC.fullmatch(src)
    if local or (src.startswith("/static/") and "{" not in src):
        name = local.group(1) if local else src.split("?", 1)[0][len("/static/"):]
        return {"kind": "file", "name": name, "where": where, "file": str(static / name), "filename": name}
    if src.startswith(("http://", "https://", "//")) and "{" not in src:
        known = [part for part in CDN_GLOBALS if part in src]
        if len(known) == 1:
            return {"kind": "cdn", "name": src, "where": where, "globals": list(CDN_GLOBALS[known[0]]),
                    "filename": src}
        raise CanaryCannotRead(
            f'{where}: <script src="{src}"> is a CDN library the canary doesn\'t know ({_TEACH} what it '
            f"defines): add a part of its URL to CDN_GLOBALS in this file with every global the real bundle "
            f"sets on window (its UMD line, `global.X = factory()`, or a top-level var), and a stand-in for "
            f"each to STUB_JS's cdnStandIns." + (f" It matches more than one entry ({known}): make the parts "
                                                 f"distinct." if known else ""))
    raise CanaryCannotRead(
        f'{where}: <script src="{src}">: the canary reads a local src only as {{{{ url_for(\'static\', '
        f"filename='...') }}}} or /static/...; {_TEACH} (read_page_scripts) where this one points.")


def _index(scripts: list, name: str) -> int:
    for i, s in enumerate(scripts):
        if s["name"] == name:
            return i
    raise AssertionError(f"the page has no script named {name!r} any more: point this proof at one it loads")


def with_fake(scripts: list, code: str, name: str, *, before: str = None, after: str = None) -> list:
    """The page plus one fake inline script, right before or right after a named one."""
    at = _index(scripts, before) if before else _index(scripts, after) + 1
    fake = {"kind": "inline", "name": name, "where": name, "code": code, "filename": name,
            "lineOffset": 0, "columnOffset": 0}
    return scripts[:at] + [fake] + scripts[at:]


def with_moved(scripts: list, name: str, *, before: str) -> list:
    """The page with one script moved to right before another."""
    moving = scripts[_index(scripts, name)]
    rest = [s for s in scripts if s is not moving]
    at = _index(rest, before)
    return rest[:at] + [moving] + rest[at:]


# ---------------------------------------------------------------------------
# The browser stub. It runs inside the vm context (its objects belong to the
# page's realm) and returns the hook the driver uses for CDN scripts. Only a
# stand-in for the browser goes here: a stand-in for one of FCC's own names
# would hide every early read of it (test_the_stub_stands_in_only_for_the_browser).
# ---------------------------------------------------------------------------

STUB_JS = r"""
(function () {
  'use strict';
  const g = globalThis;
  const noop = () => {};
  const never = () => new Promise(noop);
  g.window = g; g.self = g; g.top = g; g.parent = g; g.frames = g;

  const rect = () => ({ top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0 });
  const classList = () => {
    const set = new Set();
    return {
      add: (...c) => c.forEach((x) => set.add(x)),
      remove: (...c) => c.forEach((x) => set.delete(x)),
      contains: (c) => set.has(c),
      toggle: (c, force) => { const on = force === undefined ? !set.has(c) : !!force; if (on) set.add(c); else set.delete(c); return on; },
      replace: () => false, forEach: (fn) => set.forEach(fn), item: () => null,
      get length() { return set.size; }, get value() { return Array.from(set).join(' '); },
    };
  };
  const styleDecl = () => new Proxy({ setProperty: noop, removeProperty: () => '', getPropertyValue: () => '', cssText: '' }, {
    get: (t, k) => (k in t ? t[k] : ''), set: (t, k, v) => { t[k] = v; return true; },
  });
  const makeEl = (tag, id) => {
    const attrs = new Map();
    const kids = [];
    const name = String(tag || 'div').toUpperCase();
    return {
      tagName: name, nodeName: name, nodeType: 1, id: id || '', className: '',
      innerHTML: '', innerText: '', textContent: '', outerHTML: '', value: '', type: '', name: '', title: '',
      checked: false, disabled: false, hidden: false, tabIndex: -1, href: '', src: '',
      style: styleDecl(), dataset: {}, classList: classList(),
      children: kids, childNodes: kids, options: [], selectedOptions: [], files: [],
      firstChild: null, lastChild: null, firstElementChild: null, lastElementChild: null,
      nextSibling: null, previousSibling: null, nextElementSibling: null, previousElementSibling: null,
      parentNode: null, parentElement: null, ownerDocument: null, isConnected: false,
      offsetWidth: 0, offsetHeight: 0, offsetTop: 0, offsetLeft: 0, offsetParent: null,
      clientWidth: 0, clientHeight: 0, scrollWidth: 0, scrollHeight: 0, scrollTop: 0, scrollLeft: 0,
      selectionStart: 0, selectionEnd: 0, selectedIndex: -1,
      appendChild(c) { kids.push(c); return c; }, append(...c) { kids.push(...c); }, prepend(...c) { kids.unshift(...c); },
      removeChild(c) { return c; }, replaceChild(c) { return c; }, insertBefore(c) { return c; },
      insertAdjacentHTML: noop, insertAdjacentElement: (p, e) => e, insertAdjacentText: noop,
      remove: noop, replaceWith: noop, before: noop, after: noop, replaceChildren: noop,
      cloneNode() { return makeEl(tag); },
      setAttribute(k, v) { attrs.set(k, String(v)); }, getAttribute(k) { return attrs.has(k) ? attrs.get(k) : null; },
      hasAttribute(k) { return attrs.has(k); }, removeAttribute(k) { attrs.delete(k); }, toggleAttribute: () => false,
      addEventListener: noop, removeEventListener: noop, dispatchEvent: () => true,
      querySelector: () => null, querySelectorAll: () => [], getElementsByTagName: () => [], getElementsByClassName: () => [],
      closest: () => null, matches: () => false, contains: () => false, hasChildNodes: () => false,
      focus: noop, blur: noop, click: noop, select: noop, setSelectionRange: noop,
      scrollIntoView: noop, scrollTo: noop, scrollBy: noop,
      getBoundingClientRect: rect, getClientRects: () => [],
      animate: () => ({ finished: Promise.resolve(), cancel: noop }),
      showModal: noop, show: noop, close: noop, attachShadow: () => makeEl('#shadow'),
      checkValidity: () => true, reportValidity: () => true, setCustomValidity: noop,
    };
  };

  class EventTarget { addEventListener() {} removeEventListener() {} dispatchEvent() { return true; } }
  class Node extends EventTarget {}
  Object.assign(Node, { ELEMENT_NODE: 1, TEXT_NODE: 3, COMMENT_NODE: 8, DOCUMENT_NODE: 9, DOCUMENT_FRAGMENT_NODE: 11 });
  class Element extends Node {}
  class HTMLElement extends Element {}
  Object.assign(g, { EventTarget, Node, Element, HTMLElement });
  for (const n of ['HTMLInputElement', 'HTMLTextAreaElement', 'HTMLSelectElement', 'HTMLButtonElement',
                   'HTMLDivElement', 'HTMLAnchorElement', 'HTMLFormElement', 'HTMLOptionElement',
                   'HTMLImageElement', 'HTMLCanvasElement', 'HTMLDialogElement', 'SVGElement']) g[n] = class extends HTMLElement {};
  g.NodeFilter = { SHOW_ALL: 0xFFFFFFFF, SHOW_ELEMENT: 1, SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2, FILTER_SKIP: 3 };

  // The page has its elements (getElementById finds a dummy for any id), but
  // nothing matches a selector, and it is still loading.
  const byId = new Map();
  const body = makeEl('body');
  g.document = {
    nodeType: 9, body, head: makeEl('head'), documentElement: makeEl('html'), defaultView: g,
    activeElement: body, currentScript: null,
    readyState: 'loading', visibilityState: 'visible', hidden: false,
    title: '', cookie: '', referrer: '', URL: 'http://fcc.test/', characterSet: 'UTF-8',
    fonts: { ready: never(), check: () => true, addEventListener: noop, removeEventListener: noop },
    getElementById(id) { if (!byId.has(id)) byId.set(id, makeEl('div', id)); return byId.get(id); },
    createElement: (tag) => makeEl(tag), createElementNS: (ns, tag) => makeEl(tag),
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t), data: String(t) }),
    createComment: () => ({ nodeType: 8 }), createDocumentFragment: () => makeEl('#fragment'),
    createTreeWalker: () => ({ nextNode: () => null, currentNode: null }),
    createRange: () => ({ selectNodeContents: noop, collapse: noop, setStart: noop, setEnd: noop, getBoundingClientRect: rect }),
    createEvent: () => ({ initEvent: noop }),
    querySelector: () => null, querySelectorAll: () => [], getElementsByTagName: () => [],
    getElementsByClassName: () => [], getElementsByName: () => [],
    addEventListener: noop, removeEventListener: noop, dispatchEvent: () => true,
    hasFocus: () => true, elementFromPoint: () => null, elementsFromPoint: () => [], getSelection: () => null,
    execCommand: () => false,
  };

  class Event {
    constructor(type, init) { this.type = type; Object.assign(this, init || {}); }
    preventDefault() { this.defaultPrevented = true; } stopPropagation() {} stopImmediatePropagation() {}
  }
  class CustomEvent extends Event { constructor(type, init) { super(type, init); this.detail = init && init.detail; } }
  Object.assign(g, { Event, CustomEvent });
  for (const n of ['KeyboardEvent', 'MouseEvent', 'PointerEvent', 'FocusEvent', 'InputEvent', 'UIEvent',
                   'TouchEvent', 'WheelEvent', 'ErrorEvent', 'PromiseRejectionEvent']) g[n] = class extends Event {};
  for (const n of ['MutationObserver', 'ResizeObserver', 'IntersectionObserver']) {
    g[n] = class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } };
  }

  // Storage starts empty, as on a first visit.
  const storage = () => {
    const m = new Map();
    return {
      getItem: (k) => (m.has(String(k)) ? m.get(String(k)) : null), setItem: (k, v) => { m.set(String(k), String(v)); },
      removeItem: (k) => { m.delete(String(k)); }, clear: () => m.clear(),
      key: (i) => { const keys = Array.from(m.keys()); return i < keys.length ? keys[i] : null; },
      get length() { return m.size; },
    };
  };
  g.localStorage = storage();
  g.sessionStorage = storage();

  g.navigator = {
    userAgent: 'fcc-load-order-canary', platform: 'Win32', vendor: '', language: 'en-US', languages: ['en-US', 'en'],
    maxTouchPoints: 0, hardwareConcurrency: 4, onLine: true, cookieEnabled: true,
    clipboard: { writeText: () => Promise.resolve(), readText: () => Promise.resolve('') },
    wakeLock: { request: never }, permissions: { query: never }, mediaDevices: {}, sendBeacon: () => true,
  };
  g.location = {
    href: 'http://fcc.test/', origin: 'http://fcc.test', protocol: 'http:', host: 'fcc.test', hostname: 'fcc.test',
    port: '', pathname: '/', search: '', hash: '', reload: noop, assign: noop, replace: noop,
    toString() { return this.href; },
  };
  g.history = { length: 1, state: null, pushState: noop, replaceState: noop, back: noop, forward: noop, go: noop };
  g.screen = { width: 1600, height: 1300, availWidth: 1600, availHeight: 1300, colorDepth: 24,
               orientation: { type: 'landscape-primary', angle: 0, addEventListener: noop } };
  Object.assign(g, {
    innerWidth: 1600, innerHeight: 1300, outerWidth: 1600, outerHeight: 1300, devicePixelRatio: 1,
    scrollX: 0, scrollY: 0, pageXOffset: 0, pageYOffset: 0, name: '', closed: false, isSecureContext: true,
    origin: 'http://fcc.test',
  });

  // Timers and frames never fire, and fetch never answers: what they would
  // run is call time, not load time. A microtask runs when the script that
  // queued it ends (the context's microtaskMode), as in a browser.
  let timerId = 0;
  Object.assign(g, {
    setTimeout: () => ++timerId, clearTimeout: noop, setInterval: () => ++timerId, clearInterval: noop,
    requestAnimationFrame: () => ++timerId, cancelAnimationFrame: noop,
    requestIdleCallback: () => ++timerId, cancelIdleCallback: noop,
    queueMicrotask: (fn) => { Promise.resolve().then(fn); },
    fetch: never,
    performance: { now: () => 0, timeOrigin: 0, mark: noop, measure: noop, getEntriesByName: () => [], getEntriesByType: () => [] },
    alert: noop, confirm: () => false, prompt: () => null, open: () => null, print: noop, focus: noop, blur: noop,
    close: noop, stop: noop, scroll: noop, scrollTo: noop, scrollBy: noop, postMessage: noop,
    getSelection: () => null, getComputedStyle: () => styleDecl(),
    matchMedia: (q) => ({ matches: false, media: String(q), onchange: null, addEventListener: noop,
                          removeEventListener: noop, addListener: noop, removeListener: noop }),
    addEventListener: noop, removeEventListener: noop, dispatchEvent: () => true,
    CSS: { supports: () => true, escape: (s) => String(s) },
  });
  g.Image = class Image { constructor() { this.complete = false; } };
  g.Audio = class Audio { play() { return Promise.resolve(); } pause() {} };
  g.AbortController = class AbortController {
    constructor() { this.signal = { aborted: false, addEventListener: noop, removeEventListener: noop }; }
    abort() { this.signal.aborted = true; }
  };
  g.AbortSignal = { timeout: () => ({ aborted: false, addEventListener: noop, removeEventListener: noop }) };
  g.FormData = class FormData { append() {} set() {} get() { return null; } };
  g.Headers = class Headers { append() {} set() {} get() { return null; } has() { return false; } };
  g.Blob = class Blob {};
  g.File = class File {};
  g.FileReader = class FileReader { readAsText() {} readAsDataURL() {} };
  g.DOMParser = class DOMParser { parseFromString() { return g.document; } };
  g.BroadcastChannel = class BroadcastChannel { postMessage() {} close() {} addEventListener() {} };

  // What each CDN library sets on window (CDN_GLOBALS in the test names them).
  class Widget {
    show() {} hide() {} toggle() {} dispose() {} handleUpdate() {} update() {}
    static getInstance() { return null; }
    static getOrCreateInstance() { return new this(); }
  }
  const bootstrap = {};
  for (const n of ['Modal', 'Offcanvas', 'Tooltip', 'Popover', 'Toast', 'Collapse', 'Dropdown', 'Tab',
                   'ScrollSpy', 'Alert', 'Button', 'Carousel']) bootstrap[n] = class extends Widget {};
  const swal = {
    fire: never, mixin: () => swal, close: noop, isVisible: () => false, isLoading: () => false,
    getPopup: () => null, getContainer: () => null, getHtmlContainer: () => null, getInput: () => null,
    getConfirmButton: () => null, getCancelButton: () => null, getDenyButton: () => null,
    showLoading: noop, hideLoading: noop, update: noop, showValidationMessage: noop, resetValidationMessage: noop,
    clickConfirm: noop, clickCancel: noop,
    DismissReason: { cancel: 'cancel', backdrop: 'backdrop', close: 'close', esc: 'esc', timer: 'timer' },
  };
  class QRCode {
    clear() {} makeCode() {}
    static get CorrectLevel() { return { L: 1, M: 0, Q: 3, H: 2 }; }
  }
  const cdnStandIns = { bootstrap, Sweetalert2: swal, Swal: swal, SweetAlert: swal, swal, sweetAlert: swal, QRCode };

  return {
    cdn(names) {
      for (const n of names) {
        if (!Object.prototype.hasOwnProperty.call(cdnStandIns, n)) {
          throw new Error('the stub has no stand-in for the CDN global ' + n + ': add one to cdnStandIns in STUB_JS');
        }
        g[n] = cdnStandIns[n];
      }
    },
  };
})()
"""

# ---------------------------------------------------------------------------
# The driver: both passes over the page it is given, one JSON line out.
# ---------------------------------------------------------------------------

DRIVER_JS = r"""
'use strict';
const vm = require('vm');
const fs = require('fs');

const page = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const scripts = page.scripts;
const tick = () => new Promise((resolve) => setImmediate(resolve));

function quietConsole() {
  const out = {};
  for (const k of ['log', 'info', 'warn', 'error', 'debug', 'trace', 'dir', 'dirxml', 'table', 'group',
                   'groupCollapsed', 'groupEnd', 'time', 'timeEnd', 'timeLog', 'count', 'countReset',
                   'assert', 'clear']) out[k] = () => {};
  return out;
}

// A vm context has only the language's own built-ins: these few come from
// node, everything else browser-like from the stub. Promise callbacks run
// when each script ends, as at the browser's microtask checkpoint.
function freshContext() {
  const sandbox = { console: quietConsole(), URL, URLSearchParams, TextEncoder, TextDecoder, structuredClone, atob, btoa };
  const ctx = vm.createContext(sandbox, { microtaskMode: 'afterEvaluate' });
  const stub = vm.runInContext(page.stub, ctx, { filename: 'load-order-stub.js' });
  return { sandbox, ctx, stub };
}

const sources = scripts.map((s) => {
  if (s.kind === 'inline') return s.code;
  if (s.kind !== 'file') return null;
  try { return fs.readFileSync(s.file, 'utf8'); } catch (e) { return { missing: String((e && e.code) || e) }; }
});

const PAGE_FILES = new Set(scripts.map((s) => s.filename || s.name));
const frameFile = (frame) => { const m = /\(?([^()]+?):(\d+):(\d+)\)?$/.exec(frame); return m ? m[1] : ''; };
const framesOf = (stack) => String(stack || '').split('\n').filter((l) => /^\s+at /.test(l)).map((l) => l.trim().slice(3));
// The first frame in the page's own code (not the stub, the driver or node).
const pageFrame = (frames) => frames.find((f) => PAGE_FILES.has(frameFile(f))) || '';
function describe(e, phase) {
  const isObject = e !== null && (typeof e === 'object' || typeof e === 'function');
  const message = isObject && 'message' in e ? `${e.name || 'Error'}: ${e.message}` : `threw ${String(e)}`;
  const stack = String((isObject && e.stack) || '');
  const frames = framesOf(stack);
  // A syntax error's stack starts "file:line", over the line and a caret.
  const first = stack.split('\n')[0];
  const at = (phase === 'compile' && /:\d+$/.test(first) ? first : '') || pageFrame(frames) || frames[0] || '';
  return { message, at, stack: frames.slice(0, 5) };
}

let current = -1;      // the script running now; pass 2 charges every read to it
let errorsNow = null;  // where a promise rejected at load is filed
process.on('unhandledRejection', (reason) => {
  if (errorsNow && current >= 0) errorsNow.push(Object.assign({ script: scripts[current].name, phase: 'promise' }, describe(reason, 'promise')));
});

function runOne(env, i, errors) {
  const s = scripts[i];
  const src = sources[i];
  const fail = (phase, e) => errors.push(Object.assign({ script: s.name, phase }, describe(e, phase)));
  if (s.kind === 'cdn') { try { env.stub.cdn(s.globals); } catch (e) { fail('run', e); } return; }
  if (src && typeof src === 'object') {
    errors.push({ script: s.name, phase: 'read', message: `not on disk (${src.missing})`, at: s.where || s.file, stack: [] });
    return;
  }
  let compiled;
  try {
    compiled = new vm.Script(src, { filename: s.filename || s.name, lineOffset: s.lineOffset || 0, columnOffset: s.columnOffset || 0 });
  } catch (e) { fail('compile', e); return; }
  try { compiled.runInContext(env.ctx); } catch (e) { fail('run', e); }
}

// Loads script i, then waits a turn so a promise it rejected is reported
// while it is still the script charged.
async function load(env, i, errors) {
  current = i; errorsNow = errors;
  runOne(env, i, errors);
  await tick();
  current = -1; errorsNow = null;
}

function ownValues(obj) {
  const m = new Map();
  for (const k of Object.getOwnPropertyNames(obj)) {
    const d = Object.getOwnPropertyDescriptor(obj, k);
    m.set(k, d ? ('value' in d ? d.value : d.get) : undefined);  // never runs a getter
  }
  return m;
}

const RESERVED = new Set((
  'break case catch class const continue debugger default delete do else enum export extends false finally for ' +
  'function if import in instanceof new null return super switch this throw true try typeof var void while with ' +
  'yield let static implements interface package private protected public await arguments eval undefined NaN Infinity'
).split(' '));
// Every name a const / let / class anywhere in the source declares, a
// destructuring pattern's names included: a superset of the script's
// top-level lexical names, which V8 is then asked about (resolvable below).
function declaredNames(src) {
  const out = new Set();
  const add = (n) => { if (!RESERVED.has(n) && !n.startsWith('__fccProbe')) out.add(n); };
  const re = /\b(?:const|let|class)(?:\s+([A-Za-z_$][\w$]*)|\s*([\[{]))/g;
  let m;
  while ((m = re.exec(src))) {
    if (m[1]) { add(m[1]); continue; }
    let depth = 0;
    let j = m.index + m[0].length - 1;
    for (; j < src.length; j++) {
      const c = src[j];
      if (c === '{' || c === '[') depth += 1;
      else if ((c === '}' || c === ']') && --depth === 0) break;
    }
    for (const n of src.slice(m.index + m[0].length, j).match(/[A-Za-z_$][\w$]*/g) || []) add(n);
  }
  return out;
}
function probe(env, names, test) {
  const run = (list) => vm.runInContext('(() => { const __fccProbeFound = [];\n' +
    list.map((n) => `try { if (${test(n)}) __fccProbeFound.push(${JSON.stringify(n)}); } catch (__fccProbeErr) {}`).join('\n') +
    '\nreturn __fccProbeFound; })()', env.ctx, { filename: 'load-order-probe.js' });
  if (!names.length) return new Set();
  try { return new Set(run(names)); } catch (e) {
    const found = new Set();
    for (const n of names) { try { for (const f of run([n])) found.add(f); } catch (e2) { /* not a name to read bare */ } }
    return found;
  }
}
// The names a bare read resolves now, other than window's own properties
// (counted another way; reading one could run a getter).
const resolvable = (env, names) =>
  probe(env, [...names].filter((n) => !Object.prototype.hasOwnProperty.call(env.sandbox, n)), (n) => `(${n}, true)`);
// The stub's names that a top-level const / let / class now shadows.
const shadowed = (env, names) =>
  probe(env, [...names].filter((n) => Object.prototype.hasOwnProperty.call(env.sandbox, n)),
        (n) => `!Object.is(${n}, globalThis[${JSON.stringify(n)}])`);

// Pass 1: which script first defines each name.
async function pass1() {
  const env = freshContext();
  const errors = [];
  const definers = new Map();
  const lexical = new Set();
  const stubNames = new Set(Object.getOwnPropertyNames(env.sandbox));
  const overlaps = [];
  const overlapping = new Set();
  let before = ownValues(env.sandbox);
  for (let i = 0; i < scripts.length; i++) {
    const src = sources[i];
    const names = typeof src === 'string' ? declaredNames(src) : new Set();
    const resolvedBefore = resolvable(env, names);
    await load(env, i, errors);
    const after = ownValues(env.sandbox);
    for (const [name, value] of after) {
      if (!before.has(name)) { if (!definers.has(name)) definers.set(name, i); }
      else if (stubNames.has(name) && !Object.is(before.get(name), value) && !overlapping.has(name)) {
        overlapping.add(name);
        overlaps.push({ name, script: scripts[i].name, how: 'sets it on window' });
      }
    }
    for (const name of resolvable(env, names)) {
      if (!resolvedBefore.has(name) && !definers.has(name)) { definers.set(name, i); lexical.add(name); }
    }
    for (const name of shadowed(env, names)) {
      if (!overlapping.has(name)) {
        overlapping.add(name);
        overlaps.push({ name, script: scripts[i].name, how: 'declares it as a top-level const / let / class' });
      }
    }
    before = after;
  }
  return { errors, definers, lexical, overlaps };
}

// Pass 2: every defined name planted on window, each read charged to the
// script running when it happens (with the line, for any read but the
// definer's own).
async function pass2(definers) {
  const env = freshContext();
  const errors = [];
  const reads = [];
  for (const [name, definer] of definers) {
    if (Object.prototype.hasOwnProperty.call(env.sandbox, name)) continue;
    Object.defineProperty(env.sandbox, name, {
      configurable: true, enumerable: false,
      get() {
        if (current >= 0) reads.push([name, current, current === definer ? '' : pageFrame(framesOf(new Error().stack))]);
        return undefined;
      },
      set(value) { Object.defineProperty(env.sandbox, name, { value, writable: true, configurable: true, enumerable: true }); },
    });
  }
  for (let i = 0; i < scripts.length; i++) await load(env, i, errors);
  return { errors, reads };
}

(async () => {
  const one = await pass1();
  const two = await pass2(one.definers);
  const named = (i) => scripts[i].name;
  const early = [];
  const late = [];
  const seen = new Set();
  let selfReads = 0;
  for (const [name, reader, at] of two.reads) {
    const definer = one.definers.get(name);
    const key = reader + ' ' + name;
    if (reader === definer) { selfReads += 1; continue; }
    // Past its definer, a planted name is read only off window, and only one
    // that is a top-level const / let / class there is still planted.
    if (reader > definer && !one.lexical.has(name)) continue;
    if (seen.has(key)) continue;
    seen.add(key);
    const read = { reader: named(reader), name, definer: named(definer), lexical: one.lexical.has(name), at };
    (reader < definer ? early : late).push(read);
  }
  const definers = {};
  for (const [name, i] of one.definers) definers[name] = named(i);
  console.log('__RESULT_MARK__' + JSON.stringify({
    order: scripts.map((s) => s.name),
    errors: one.errors,
    errors_pass2: two.errors,
    early_reads: early,
    late_reads: late,
    reads_recorded: two.reads.length,
    self_reads: selfReads,
    definers,
    lexical: [...one.lexical],
    stub_overlaps: one.overlaps,
  }));
})().catch((e) => { console.error((e && e.stack) || e); process.exitCode = 3; });
""".replace("__RESULT_MARK__", RESULT_MARK)


def run_page(scripts: list, work: Path, label: str, stub: str = STUB_JS) -> dict:
    """Loads `scripts` in order under node, both passes, and returns the driver's result."""
    page = work / f"{label}.json"
    page.write_text(json.dumps({"stub": stub, "scripts": scripts}), encoding="utf-8")
    driver = work / "load_order_driver.js"
    driver.write_text(DRIVER_JS, encoding="utf-8")
    proc = subprocess.run([NODE, str(driver), str(page)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and lines, (
        f"the load-order driver failed (rc={proc.returncode})\n"
        f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}")
    return json.loads(lines[-1][len(RESULT_MARK):])


# ---------------------------------------------------------------------------
# What a failure says
# ---------------------------------------------------------------------------

_PHASES = {"compile": "a syntax error", "run": "an error while it loads",
           "promise": "an error in a promise callback while it loads"}


def _at(read: dict) -> str:
    return f" (at {read['at']})" if read.get("at") else ""


def load_error_problems(result: dict) -> list:
    out = []
    for e in result["errors"]:
        if e["phase"] == "read":
            out.append(f"  - {e['script']} (a missing file): {e['at']} loads it, but it is not on disk.")
            continue
        text = f"  - {e['script']} ({_PHASES.get(e['phase'], e['phase'])}): {e['message']}"
        if e.get("at"):
            text += f"\n      at {e['at']}"
        out.append(text)
    return out


def early_read_problems(result: dict, allowed: dict) -> list:
    out = []
    for r in result["early_reads"]:
        if (r["reader"], r["name"]) in allowed:
            continue
        text = (f"  - {r['reader']} reads {r['name']} while it loads{_at(r)}, but {r['name']} is defined "
                f"later, by {r['definer']}.")
        if r["lexical"]:
            text += (f" (If that read is window.{r['name']}, loading earlier won't help: {r['name']} is a "
                     f"top-level const / let / class there, never a window property. Read it bare, or have "
                     f"{r['definer']} also set window.{r['name']}.)")
        out.append(text)
    return out


def late_read_problems(result: dict) -> list:
    return [f"  - {r['reader']} reads window.{r['name']} while it loads{_at(r)}, but {r['name']} is a top-level "
            f"const / let / class in {r['definer']}, which never becomes a window property, so the read is "
            f"always undefined. Read it bare ({r['name']}), or have {r['definer']} also set "
            f"window.{r['name']}." for r in result["late_reads"]]


# ---------------------------------------------------------------------------
# The real page
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def page_scripts() -> list:
    return read_page_scripts()


@pytest.fixture(scope="module")
def load_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("load_order")


@pytest.fixture(scope="module")
def page_load(page_scripts, load_dir) -> dict:
    return run_page(page_scripts, load_dir, "page")


def test_every_script_loads_without_throwing(page_load):
    problems = load_error_problems(page_load)
    assert not problems, (
        "These scripts failed while the canary loaded the page:\n" + "\n".join(problems) + "\n"
        "A missing file: fix that <script>'s src. Any other is either a gap in the stub (the script used a "
        "browser feature STUB_JS doesn't have: add a plain stand-in for it to STUB_JS in "
        "tests/test_load_order_canary_js.py, never a stand-in for one of FCC's own names) or a real load-time "
        "error (it would throw in a browser too: fix the script). Until it loads, the early-read check can't "
        "see past the throw.")


def test_every_inline_script_parses_with_its_server_values_as_null(page_scripts, page_load):
    """The canary runs an inline script with each {{ ... }} replaced by null;
    that must leave it valid JavaScript, or nothing after the broken line is
    checked. (Today the last script's server values are in `= {{ ... }};`
    and inside a string, both fine as null.)"""
    inline = [s for s in page_scripts if s["kind"] == "inline"]
    assert any("= null;" in s["code"] for s in inline), "no inline script holds a server value any more"
    broken = [e for e in page_load["errors"]
              if e["phase"] == "compile" and e["script"] in {s["name"] for s in inline}]
    assert not broken, "\n".join(
        [f"  - {e['script']}: {e['message']} (at {e['at']})" for e in broken]
        + ["With each {{ ... }} as null these inline scripts don't parse. If the template's own JavaScript is "
           "fine, a value sits where null isn't valid (a name, `{{ a }}{{ b }}`): put the value in a string or "
           "a JSON value (|tojson), or teach the canary (read_page_scripts) a placeholder that parses there."])


def test_no_script_reads_at_load_a_name_a_later_script_defines(page_load):
    problems = early_read_problems(page_load, ALLOWED_EARLY_READS)
    assert not problems, (
        "These scripts read, while they load, a name a later script on the page defines, so they get "
        "undefined there (an `if (window.X)` guard silently does nothing):\n" + "\n".join(problems) + "\n"
        "Move the read into a function that runs later (on DOMContentLoaded, or in a handler such as a "
        "click), or load the defining script earlier in templates/components/scripts.html. If the early read "
        "is deliberate and harmless (a guard meant to find nothing at load that is tried again later), add it "
        "to ALLOWED_EARLY_READS in tests/test_load_order_canary_js.py as (reader, name): the reason.")


def test_each_allowed_early_read_is_still_read_early_and_says_why(page_load):
    found = {(r["reader"], r["name"]) for r in page_load["early_reads"]}
    stale = [key for key in ALLOWED_EARLY_READS if key not in found]
    unexplained = [key for key, why in ALLOWED_EARLY_READS.items() if not str(why or "").strip()]
    assert not stale, (
        f"ALLOWED_EARLY_READS lists {stale}, but no script reads that name early any more: remove the "
        f"entry, so a new early read of it is caught again.")
    assert not unexplained, f"ALLOWED_EARLY_READS entries {unexplained} have no reason: say why the read is safe."


def test_no_script_reads_window_dot_a_top_level_const_at_load(page_load):
    problems = late_read_problems(page_load)
    assert not problems, "\n".join(["These reads are always undefined in a browser:"] + problems)


def test_the_stub_stands_in_only_for_the_browser(page_load):
    """Pass 2 plants only the names the stub doesn't have, so a stub copy of
    one of FCC's own names (added to get a script to load, say) would hide
    every early read of that name."""
    overlaps = [o for o in page_load["stub_overlaps"] if o["name"] not in STUB_NAMES_THE_PAGE_SETS]
    assert not overlaps, "\n".join(
        [f"  - the stub puts {o['name']} on window, and {o['script']} {o['how']}." for o in overlaps]
        + ["Take an FCC name out of STUB_JS: the canary must see it go undefined until its own script defines "
           "it. A browser API that FCC replaces on purpose goes in STUB_NAMES_THE_PAGE_SETS with why."])
    unexplained = [name for name, why in STUB_NAMES_THE_PAGE_SETS.items() if not str(why or "").strip()]
    assert not unexplained, f"STUB_NAMES_THE_PAGE_SETS entries {unexplained} have no reason."


def test_every_file_under_static_js_is_on_the_page_exactly_once(page_scripts):
    """A module split that forgets to add its new file to scripts.html, or a
    script added twice (its listeners and shortcuts would register twice)."""
    loads = Counter(s["name"] for s in page_scripts if s["kind"] in ("file", "cdn"))
    where: dict = {}
    for s in page_scripts:
        where.setdefault(s["name"], []).append(s["where"])
    files = sorted(p.relative_to(STATIC).as_posix() for p in (STATIC / "js").rglob("*.js"))
    missing = [f for f in files if not loads[f]]
    twice = {name: where[name] for name, n in loads.items() if n > 1}
    assert not missing, (
        f"These files are under static/js but no <script> on the page loads them: {missing}. Add each to "
        f"templates/components/scripts.html where it belongs in the order (a module split must add its new "
        f"file), or delete it if nothing uses it.")
    assert not twice, (
        f"These scripts load more than once: {twice}. A second load runs the whole file again (its "
        f"listeners and shortcuts register twice): keep one <script> for each.")


def test_every_script_the_page_loads_is_on_disk(page_scripts):
    """Compared by exact name, so a wrong letter case is caught on Windows too
    (the container's file system is case-sensitive)."""
    on_disk = {p.relative_to(STATIC).as_posix() for p in STATIC.rglob("*") if p.is_file()}
    absent = [f"{s['where']} loads {s['name']}" for s in page_scripts
              if s["kind"] == "file" and s["name"] not in on_disk]
    assert not absent, (
        f"These scripts are not on disk under static/ (a renamed or moved module, or a wrong letter "
        f"case): {absent}.")


def test_the_instrument_sees_each_kind_of_definition(page_scripts, page_load):
    """The definer map, which every early read is judged against."""
    d = page_load["definers"]
    lexical = set(page_load["lexical"])
    assert d["showToast"] == "js/modules/inv_core.js", d.get("showToast")          # const + window.showToast =
    assert d["openSlotPicker"] == "js/modules/slot_picker.js", d.get("openSlotPicker")  # window.X = in an IIFE
    # registerShortcut is first defined by the queueing shim near the top of
    # scripts.html, not by shortcuts_registry.js, which replaces it later.
    shim = [s["name"] for s in page_scripts
            if s["kind"] == "inline" and "window.__pendingShortcuts = []" in s["code"]]
    assert len(shim) == 1 and shim[0].startswith(SCRIPTS_HTML + ":"), shim
    assert d["registerShortcut"] == shim[0], d.get("registerShortcut")
    # A top-level let (never on window), and an indented const in an inline
    # script, which a column-0 search for declarations would miss.
    assert d["state"] == "js/modules/inv_core.js" and "state" in lexical
    tail = [s["name"] for s in page_scripts if s["kind"] == "inline" and "const SPOOLMAN_URL" in s["code"]]
    assert len(tail) == 1 and tail[0].startswith("templates/dashboard.html:"), tail
    assert d["SPOOLMAN_URL"] == tail[0] and "SPOOLMAN_URL" in lexical
    # Each CDN library defines what the real bundle defines.
    for part, names in CDN_GLOBALS.items():
        cdn = [s["name"] for s in page_scripts if s["kind"] == "cdn" and part in s["name"]]
        assert len(cdn) == 1, (part, cdn)
        assert {n: d.get(n) for n in names} == {n: cdn[0] for n in names}
    # And reads are seen at all: the modules that check a flag of their own
    # before setting it.
    assert page_load["self_reads"] > 0 and page_load["reads_recorded"] >= page_load["self_reads"]


# ---------------------------------------------------------------------------
# Mutation proofs: the real page plus one change
# ---------------------------------------------------------------------------

def _early(result: dict) -> set:
    return {(r["reader"], r["name"], r["definer"]) for r in result["early_reads"]}


def test_a_window_read_before_its_definer_is_reported(page_scripts, load_dir):
    fake = "FAKE script before inv_core.js reading window.openSlotPicker"
    result = run_page(with_fake(page_scripts, "if (window.openSlotPicker) {}", fake,
                                before="js/modules/inv_core.js"), load_dir, "fake-window-read")
    assert _early(result) == {(fake, "openSlotPicker", "js/modules/slot_picker.js")}, result["early_reads"]
    assert result["early_reads"][0]["at"].startswith(fake + ":1:"), result["early_reads"]
    problems = early_read_problems(result, ALLOWED_EARLY_READS)
    assert len(problems) == 1 and fake in problems[0] and "js/modules/slot_picker.js" in problems[0], problems
    assert result["errors"] == [], result["errors"]


def test_a_bare_typeof_before_its_definer_is_reported(page_scripts, load_dir):
    fake = "FAKE script before inv_core.js testing typeof processScan"
    result = run_page(with_fake(page_scripts, "if (typeof processScan === 'function') {}", fake,
                                before="js/modules/inv_core.js"), load_dir, "fake-typeof")
    assert _early(result) == {(fake, "processScan", "js/modules/inv_cmd.js")}, result["early_reads"]
    assert result["errors"] == [], result["errors"]


def test_the_same_read_after_its_definer_is_not_reported(page_scripts, load_dir):
    """The read of window.mountOverlay is fine right after overlay_mount.js and
    reported right before it: what the canary judges is the order."""
    fake = "FAKE script reading window.mountOverlay"
    after = run_page(with_fake(page_scripts, "if (window.mountOverlay) {}", fake,
                               after="js/modules/overlay_mount.js"), load_dir, "fake-after")
    assert after["early_reads"] == [] and after["errors"] == [], after
    before = run_page(with_fake(page_scripts, "if (window.mountOverlay) {}", fake,
                                before="js/modules/overlay_mount.js"), load_dir, "fake-before")
    assert _early(before) == {(fake, "mountOverlay", "js/modules/overlay_mount.js")}, before["early_reads"]


def test_moving_inv_core_late_is_reported(page_scripts, load_dir):
    """The real reorder: inv_core.js loaded just before titlebar_prefs.js."""
    result = run_page(with_moved(page_scripts, "js/modules/inv_core.js", before="js/modules/titlebar_prefs.js"),
                      load_dir, "inv-core-late")
    early = _early(result)
    assert ("js/modules/inv_stock.js", "installFieldScanCapture", "js/modules/inv_core.js") in early, early
    assert ("js/modules/inv_loc_mgr.js", "state", "js/modules/inv_core.js") in early, early
    at = {(r["reader"], r["name"]): r["at"] for r in result["early_reads"]}
    assert "(js/modules/inv_stock.js:" in at["js/modules/inv_stock.js", "installFieldScanCapture"], at
    assert at["js/modules/inv_loc_mgr.js", "state"].startswith("js/modules/inv_loc_mgr.js:"), at
    errors = [e for e in result["errors"] if e["script"] == "js/modules/inv_loc_mgr.js"]
    assert errors and errors[0]["message"] == "ReferenceError: state is not defined", result["errors"]
    problems = early_read_problems(result, ALLOWED_EARLY_READS)
    assert any(p.startswith("  - js/modules/inv_stock.js reads installFieldScanCapture") for p in problems), problems
    assert any(p.startswith("  - js/modules/inv_loc_mgr.js (an error while it loads)")
               for p in load_error_problems(result))


def test_without_the_shortcut_shim_the_2026_08_drop_is_reported(page_scripts, load_dir):
    """The real precedent: without the queueing shim at the top of
    scripts.html, the modules that register their shortcuts at load read
    registerShortcut before shortcuts_registry.js defines it, and those
    shortcuts were silently missing from the ? overlay (fixed 2026-08-05)."""
    shim = [s for s in page_scripts if s["kind"] == "inline" and "window.__pendingShortcuts = []" in s["code"]]
    assert len(shim) == 1, shim
    result = run_page([s for s in page_scripts if s is not shim[0]], load_dir, "no-shim")
    readers = {r["reader"] for r in result["early_reads"] if r["name"] == "registerShortcut"}
    assert {"js/modules/inv_cmd.js", "js/modules/inv_wizard.js"} <= readers, result["early_reads"]
    assert {(r["name"], r["definer"]) for r in result["early_reads"]} == {
        ("registerShortcut", "js/modules/shortcuts_registry.js")}, result["early_reads"]


def test_a_window_read_of_a_top_level_const_is_reported(page_scripts, load_dir):
    """`state` is a top-level let in inv_core.js: window.state is undefined
    however late it is read."""
    fake = "FAKE script after inv_core.js reading window.state"
    result = run_page(with_fake(page_scripts, "if (window.state) {}", fake, after="js/modules/inv_core.js"),
                      load_dir, "fake-window-lexical")
    assert [(r["reader"], r["name"], r["definer"]) for r in result["late_reads"]] == [
        (fake, "state", "js/modules/inv_core.js")], result["late_reads"]
    assert result["early_reads"] == [], result["early_reads"]


def test_a_stub_copy_of_a_page_name_is_reported(page_scripts, load_dir):
    """A stand-in for showToast in the stub, as someone might add to get a
    script to load, is caught: inv_core.js sets showToast on window too."""
    stub = STUB_JS.replace("  g.navigator = {", "  g.showToast = noop;\n  g.navigator = {", 1)
    assert stub != STUB_JS
    result = run_page(page_scripts, load_dir, "stub-copy", stub=stub)
    assert [(o["name"], o["script"]) for o in result["stub_overlaps"]] == [("showToast", "js/modules/inv_core.js")]
    # And the copy did hide the name: with it, nothing is planted for showToast.
    assert "showToast" not in result["definers"]


# ---------------------------------------------------------------------------
# The template reader on made-up pages
# ---------------------------------------------------------------------------

def _templates(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / "templates" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root / "templates"


def test_the_reader_follows_includes_and_skips_what_never_runs(tmp_path):
    templates = _templates(tmp_path, {
        "page.html": (
            '<html><head>\n'                                                                    # 1
            '<script id="boot">\n'                                                              # 2
            '  var booted = 1;\n'                                                               # 3
            '</script>\n'                                                                       # 4
            "<!-- <script src=\"{{ url_for('static', filename='js/gone.js') }}\"></script> -->\n"  # 5
            "{# <script src=\"{{ url_for('static', filename='js/gone2.js') }}\"></script>\n"    # 6
            '   still the Jinja comment #}\n'                                                    # 7
            '</head><body>\n'                                                                   # 8
            '{%- include "parts/libs.html" -%}\n'                                               # 9
            '<script type="application/json" id="data">{"a": 1}</script>\n'                     # 10
            '<template><script>var inert = 1;</script></template>\n'                            # 11
            '<textarea><script>var text = 1;</script></textarea>\n'                             # 12
            '<script>\n'                                                                        # 13
            '  const FROM_SERVER = "{{ server_url }}";\n'                                       # 14
            "  window.flag = {{ 'true' if on\n"                                                 # 15
            "     else 'false' }};\n"                                                           # 16
            '  window.after = 1;\n'                                                              # 17
            '</script>\n'                                                                       # 18
            '</body></html>\n'),
        "parts/libs.html": (
            '<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>\n'
            "<script src=\"{{ url_for('static', filename='js/modules/a.js') }}?v=1.2\"></script>\n"),
    })
    scripts = read_page_scripts(templates, tmp_path / "static", "page.html")
    assert [s["name"] for s in scripts] == [
        "templates/page.html:2 (inline #boot)",
        "https://cdn.jsdelivr.net/npm/sweetalert2@11",
        "js/modules/a.js",
        "templates/page.html:13 (inline)",
    ]
    assert [s["kind"] for s in scripts] == ["inline", "cdn", "file", "inline"]
    assert scripts[1]["globals"] == list(CDN_GLOBALS["sweetalert2"])
    assert scripts[2]["where"] == "templates/parts/libs.html:2"
    assert scripts[2]["file"] == str(tmp_path / "static" / "js" / "modules" / "a.js")
    tail = scripts[3]
    assert "{{" not in tail["code"] and 'FROM_SERVER = "null"' in tail["code"] and "window.flag = null\n" in tail["code"]
    # Its first line is template line 13, and each later line keeps its number.
    assert tail["lineOffset"] == 12
    assert tail["code"].split("\n")[4] == "  window.after = 1;"


def test_a_failure_names_its_template_line(tmp_path):
    """Node's stack frames point at the template's own lines, and a promise
    rejected while a script loads is charged to that script."""
    templates = _templates(tmp_path, {"page.html": (
        "<p>\n"                                        # 1
        "</p>\n"                                       # 2
        "<script>\n"                                   # 3
        "  var fine = 1;\n"                            # 4
        "  null.boom;\n"                               # 5
        "</script>\n"                                  # 6
        "<script>\n"                                   # 7
        "  (async () => { undefined.later; })();\n"    # 8
        "</script>\n")})
    result = run_page(read_page_scripts(templates, tmp_path / "static", "page.html"), tmp_path, "made-up")
    assert [(e["script"], e["phase"]) for e in result["errors"]] == [
        ("templates/page.html:3 (inline)", "run"), ("templates/page.html:7 (inline)", "promise")], result["errors"]
    assert "templates/page.html:5:" in result["errors"][0]["at"], result["errors"][0]
    assert "templates/page.html:8:" in result["errors"][1]["at"], result["errors"][1]


@pytest.mark.parametrize("files,words", [
    pytest.param({"page.html": "{% if on %}\n<script>var a = 1;</script>\n{% endif %}\n"},
                 "sits inside {% if %} at templates/page.html:1", id="script-in-if"),
    pytest.param({"page.html": "{% for x in xs %}{% include 'part.html' %}{% endfor %}\n",
                  "part.html": "<script>var a = 1;</script>\n"},
                 "sits inside {% for %} at templates/page.html:1", id="include-in-for"),
    pytest.param({"page.html": "<script>\n{% if on %}var a = 1;{% endif %}\n</script>\n"},
                 "holds Jinja control flow", id="control-flow-in-inline"),
    pytest.param({"page.html": "<script defer src=\"{{ url_for('static', filename='js/a.js') }}\"></script>\n"},
                 "<script defer>", id="defer"),
    pytest.param({"page.html": "<script async src=\"{{ url_for('static', filename='js/a.js') }}\"></script>\n"},
                 "<script async>", id="async"),
    pytest.param({"page.html": '<script type="module">var a = 1;</script>\n'},
                 '<script type="module">', id="module"),
    pytest.param({"page.html": '<script src="https://cdn.example.test/lib/fancy-lib.min.js"></script>\n'},
                 "teach the canary what it defines", id="unknown-cdn"),
    pytest.param({"page.html": '<script src="{{ asset_url }}"></script>\n'},
                 "where this one points", id="src-from-a-variable"),
    pytest.param({"page.html": "{% extends 'base.html' %}\n"}, "{% extends %}", id="extends"),
])
def test_the_reader_refuses_what_it_cannot_model(tmp_path, files, words):
    templates = _templates(tmp_path, files)
    with pytest.raises(CanaryCannotRead) as raised:
        read_page_scripts(templates, tmp_path / "static", "page.html")
    assert words in str(raised.value), str(raised.value)
    assert _TEACH in str(raised.value), str(raised.value)
