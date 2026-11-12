"""The 🛑 Review's spool picker reads scans and lists the scan buffer (hotfix
2026-11-11, scope D).

Derek: "we have to manually key in the id on the spool, and scanning it just
inputs the ID:XX into the text box with an enter. Scanning support might be a
good idea here, as well as possibly listing spools in the current buffer."

Runs the REAL overlay_mount.js and cancel_review.js under node's `vm`, no browser
and no container. The shared driver's stub (test_core1_return_ejectall_js.py)
drops every listener, so it can't press a key or pick an option; this file brings
a small DOM of its own: an HTML parser, selectors (descendant and child, ids,
classes, attributes, CSS.escape's escapes), events with capture and bubble
phases, focus, and <select> / <option> selectedness as a browser keeps it.
The dashboard's scan accumulator (templates/components/scripts.html) is not
loaded: it ignores every key whose target is an INPUT (main's line 267, dev's
too), so a scan typed into the box reaches only the box; what this file pins is
what the box then does with it.

Pinned:
  - the "#ID" box reads a spool's number typed (42, #42) or its label scanned
    (ID:42, SPL:42), in any letter case, spaces around it ignored; a label read
    twice, or a key left in front of one, reads as its last label; it shows the
    spool in its info line, and Apply charges that spool;
  - an Enter in the box (a scanner sends one, some send two) only reads the box:
    nothing is applied, nothing is pressed, the Enter goes no further, the text
    stays whole and is selected, so the next scan replaces it;
  - what the box can't read says so in its info line in plain words (a location's
    label, a filament's label, anything else, #0, an empty box), and is never
    looked up; a spool FCC can't find, or a lookup FCC didn't answer, says so too,
    and an Apply over a box it can't read says why on the card (its toast is
    under the overlay);
  - an older lookup never paints over a newer one, nor over a pick made since;
  - every picker lists the spools in the scan buffer (`state.heldSpools`) under
    "In the scan buffer": number, name, grams left when known, archived said;
    never a spool the picker lists already; drawn again when the buffer changes,
    when the printer's heads arrive and when the picker is opened; a spool picked
    from it stays picked after it leaves the buffer; the list goes with the
    review;
  - the box's keys are the card's: Escape closes the review (nothing posted),
    the arrows move in the box;
  - the box's words are readable on the card and use a named size.

The browser contrast case is tests/test_contrast_guard.py's
test_review_picker_box_words_are_readable; this file checks the colours offline.

HEAD proof: run on 8b387b4 (scope B, before scope D), every test here fails but
test_keys_in_the_box_behave_as_on_the_rest_of_the_card, which pins what the
card's keys already did (the arrows are the box's, Escape closes the review).
"""
from __future__ import annotations

import json
import re
import subprocess

from test_core1_return_ejectall_js import MODULES, NODE, RESULT_MARK, pytestmark  # noqa: F401  (skip without node)

CARD_BG = "#17181b"
WORDS = {"end": "when the print ended", "start": "when the print started", "during": "during the print"}

# The DOM. `prelude` runs inside the vm context, so every object it builds
# belongs to the modules' realm.
DRIVER_JS = r"""
const vm = require('vm');
const fs = require('fs');
const MODULE_PATHS = __MODULE_PATHS__;

function prelude() {
  globalThis.window = globalThis;
  globalThis.self = globalThis;
  const rec = globalThis.__rec = { toasts: [], fetches: [], errors: [] };

  const VOID = new Set(['INPUT', 'BR', 'IMG', 'HR', 'META', 'LINK', 'AREA', 'BASE', 'COL', 'EMBED', 'SOURCE', 'TRACK', 'WBR']);
  const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };
  const decode = (t) => String(t).replace(/&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z]+);/g, (m, g) => {
    if (g[0] === '#') return String.fromCodePoint(g[1] === 'x' || g[1] === 'X' ? parseInt(g.slice(2), 16) : parseInt(g.slice(1), 10));
    return Object.prototype.hasOwnProperty.call(ENT, g) ? ENT[g] : m;
  });
  const escText = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const escAttr = (t) => escText(t).replace(/"/g, '&quot;');
  const camel = (p) => String(p).trim().replace(/-([a-z])/g, (m, c) => c.toUpperCase());
  const kebab = (p) => String(p).replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());

  // ----- events ------------------------------------------------------------
  class Event {
    constructor(type, init) {
      const o = init || {};
      this.type = type; this.bubbles = !!o.bubbles; this.cancelable = !!o.cancelable;
      this.defaultPrevented = false; this.target = null; this.currentTarget = null;
      this._stop = false; this._stopNow = false;
    }
    preventDefault() { if (this.cancelable) this.defaultPrevented = true; }
    stopPropagation() { this._stop = true; }
    stopImmediatePropagation() { this._stop = true; this._stopNow = true; }
  }
  class CustomEvent extends Event { constructor(t, o) { super(t, o); this.detail = o && o.detail; } }
  class KeyboardEvent extends Event {
    constructor(t, o) {
      super(t, o); const x = o || {};
      this.key = x.key || ''; this.code = x.code || '';
      this.ctrlKey = !!x.ctrlKey; this.altKey = !!x.altKey; this.metaKey = !!x.metaKey; this.shiftKey = !!x.shiftKey;
      this.repeat = !!x.repeat; this.isComposing = !!x.isComposing;
    }
  }
  class MouseEvent extends Event { constructor(t, o) { super(t, o); this.detail = (o && o.detail) || 1; this.button = 0; } }
  Object.assign(globalThis, { Event, CustomEvent, KeyboardEvent, MouseEvent, FocusEvent: Event, InputEvent: Event });

  const listen = (obj) => {
    obj._ls = [];
    obj.addEventListener = function (type, fn, opts) {
      if (typeof fn !== 'function' && !(fn && fn.handleEvent)) return;
      const capture = typeof opts === 'boolean' ? opts : !!(opts && opts.capture);
      if (this._ls.some((l) => l.type === type && l.fn === fn && l.capture === capture)) return;
      this._ls.push({ type, fn, capture, once: !!(opts && opts.once) });
    };
    obj.removeEventListener = function (type, fn, opts) {
      const capture = typeof opts === 'boolean' ? opts : !!(opts && opts.capture);
      this._ls = this._ls.filter((l) => !(l.type === type && l.fn === fn && l.capture === capture));
    };
    obj.dispatchEvent = function (ev) { return dispatch(this, ev); };
  };
  function invoke(node, ev, phase) {
    ev.currentTarget = node;
    for (const l of node._ls.slice()) {
      if (l.type !== ev.type) continue;
      if (phase === 'capture' && !l.capture) continue;
      if (phase === 'bubble' && l.capture) continue;
      if (!node._ls.includes(l)) continue;
      if (l.once) node.removeEventListener(l.type, l.fn, l.capture);
      try { if (typeof l.fn === 'function') l.fn.call(node, ev); else l.fn.handleEvent(ev); }
      catch (e) { rec.errors.push(String((e && e.stack) || e)); }
      if (ev._stopNow) return;
    }
  }
  function dispatch(target, ev) {
    const path = [];
    for (let n = target; n; n = n.parentNode) path.push(n);
    if (path[path.length - 1] === globalThis.document) path.push(globalThis);
    ev.target = target;
    for (let i = path.length - 1; i >= 1 && !ev._stop; i--) invoke(path[i], ev, 'capture');
    if (!ev._stop) invoke(path[0], ev, 'target');
    if (ev.bubbles) for (let i = 1; i < path.length && !ev._stop; i++) invoke(path[i], ev, 'bubble');
    ev.currentTarget = null;
    return !ev.defaultPrevented;
  }

  // ----- selectors ---------------------------------------------------------
  function readEsc(s, i) {             // s[i] is a backslash: [char, next index]
    const hex = /^[0-9a-fA-F]{1,6}/.exec(s.slice(i + 1));
    if (hex) {
      let j = i + 1 + hex[0].length;
      if (s[j] === ' ') j++;
      return [String.fromCodePoint(parseInt(hex[0], 16)), j];
    }
    return [s[i + 1], i + 2];
  }
  function readIdent(s, i) {
    let out = '';
    while (i < s.length) {
      if (s[i] === '\\') { const [c, j] = readEsc(s, i); out += c; i = j; continue; }
      if (/[A-Za-z0-9_\-]/.test(s[i]) || s.charCodeAt(i) >= 0x80) { out += s[i++]; continue; }
      break;
    }
    return [out, i];
  }
  function readString(s, i) {          // s[i] is the quote
    const q = s[i]; i++; let out = '';
    while (i < s.length && s[i] !== q) {
      if (s[i] === '\\') { const [c, j] = readEsc(s, i); out += c; i = j; continue; }
      out += s[i++];
    }
    return [out, i + 1];
  }
  const _selCache = new Map();
  function parseSel(sel) {
    const src = String(sel).trim();
    if (_selCache.has(src)) return _selCache.get(src);
    const list = []; let parts = []; let comp = null; let comb = ' '; let i = 0;
    const flush = () => { if (comp) { parts.push({ comb, comp }); comp = null; comb = ' '; } };
    const ensure = () => (comp = comp || { tag: null, id: null, classes: [], attrs: [], nots: [] });
    while (i < src.length) {
      const c = src[i];
      if (c === ',') { flush(); list.push(parts); parts = []; comb = ' '; i++; continue; }
      if (/\s/.test(c)) { flush(); i++; continue; }
      if (c === '>') { flush(); comb = '>'; i++; continue; }
      if (c === '#') { const [v, j] = readIdent(src, i + 1); ensure().id = v; i = j; continue; }
      if (c === '.') { const [v, j] = readIdent(src, i + 1); ensure().classes.push(v); i = j; continue; }
      if (c === '*') { ensure().tag = '*'; i++; continue; }
      if (c === '[') {
        let j = i + 1; while (/\s/.test(src[j])) j++;
        const [name, k] = readIdent(src, j); j = k; while (/\s/.test(src[j])) j++;
        let op = null; let value = null;
        if (src[j] !== ']') {
          op = src[j] === '=' ? '=' : src.slice(j, j + 2); j += op.length; while (/\s/.test(src[j])) j++;
          if (src[j] === '"' || src[j] === "'") { const [v, n] = readString(src, j); value = v; j = n; }
          else { const [v, n] = readIdent(src, j); value = v; j = n; }
          while (/\s/.test(src[j])) j++;
        }
        if (src[j] !== ']') throw new Error('selector not supported: ' + sel);
        ensure().attrs.push({ name: name.toLowerCase(), op, value });
        i = j + 1; continue;
      }
      if (c === ':') {
        if (src.startsWith(':not(', i)) {
          let depth = 1; let j = i + 5;
          while (j < src.length && depth) { if (src[j] === '(') depth++; else if (src[j] === ')') depth--; j++; }
          ensure().nots.push(parseSel(src.slice(i + 5, j - 1)));
          i = j; continue;
        }
        throw new Error('selector not supported: ' + sel);
      }
      if (/[A-Za-z]/.test(c)) { const [v, j] = readIdent(src, i); ensure().tag = v.toUpperCase(); i = j; continue; }
      throw new Error('selector not supported: ' + sel);
    }
    flush(); list.push(parts);
    _selCache.set(src, list);
    return list;
  }
  function matchCompound(el, comp) {
    if (!el || el.nodeType !== 1) return false;
    if (comp.tag && comp.tag !== '*' && el.tagName !== comp.tag) return false;
    if (comp.id !== null && el.getAttribute('id') !== comp.id) return false;
    for (const c of comp.classes) if (!el.classList.contains(c)) return false;
    for (const a of comp.attrs) {
      const v = el.getAttribute(a.name);
      if (v === null) return false;
      if (a.op === '=' && v !== a.value) return false;
      if (a.op === '^=' && !v.startsWith(a.value)) return false;
      if (a.op === '$=' && !v.endsWith(a.value)) return false;
      if (a.op === '*=' && !v.includes(a.value)) return false;
      if (a.op === '~=' && !v.split(/\s+/).includes(a.value)) return false;
    }
    for (const n of comp.nots) if (matchList(el, n)) return false;
    return true;
  }
  function matchParts(el, parts, k) {
    if (!matchCompound(el, parts[k].comp)) return false;
    if (k === 0) return true;
    if (parts[k].comb === '>') return matchParts(el.parentNode, parts, k - 1);
    for (let p = el.parentNode; p && p.nodeType === 1; p = p.parentNode) if (matchParts(p, parts, k - 1)) return true;
    return false;
  }
  function matchList(el, list) { return list.some((parts) => matchParts(el, parts, parts.length - 1)); }

  // ----- nodes -------------------------------------------------------------
  class Text {
    constructor(t) { this.nodeType = 3; this.data = String(t); this.parentNode = null; }
    get textContent() { return this.data; }
    set textContent(v) { this.data = String(v); }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  }
  function serialize(n) {
    if (n.nodeType === 3) return escText(n.data);
    const tag = n.tagName.toLowerCase();
    const attrs = Array.from(n._attrs).map(([k, v]) => ` ${k}="${escAttr(v)}"`).join('');
    if (VOID.has(n.tagName)) return `<${tag}${attrs}>`;
    return `<${tag}${attrs}>${n.childNodes.map(serialize).join('')}</${tag}>`;
  }
  function parseInto(html, parent) {
    const s = String(html); const stack = [parent]; let i = 0;
    const top = () => stack[stack.length - 1];
    while (i < s.length) {
      if (s[i] === '<' && s.startsWith('<!--', i)) { const e = s.indexOf('-->', i + 4); i = e < 0 ? s.length : e + 3; continue; }
      if (s[i] === '<' && s[i + 1] === '/') {
        const e = s.indexOf('>', i); const name = s.slice(i + 2, e).trim().toUpperCase();
        for (let k = stack.length - 1; k > 0; k--) if (stack[k].tagName === name) { stack.length = k; break; }
        i = e + 1; continue;
      }
      if (s[i] === '<' && /[A-Za-z]/.test(s[i + 1] || '')) {
        let j = i + 1; let name = '';
        while (j < s.length && /[A-Za-z0-9\-]/.test(s[j])) name += s[j++];
        const el = new Element(name); let selfClose = false;
        while (j < s.length) {
          while (j < s.length && /\s/.test(s[j])) j++;
          if (s[j] === '>') { j++; break; }
          if (s[j] === '/' && s[j + 1] === '>') { selfClose = true; j += 2; break; }
          let an = '';
          while (j < s.length && !/[\s=>]/.test(s[j]) && !(s[j] === '/' && s[j + 1] === '>')) an += s[j++];
          while (j < s.length && /\s/.test(s[j])) j++;
          let av = '';
          if (s[j] === '=') {
            j++; while (j < s.length && /\s/.test(s[j])) j++;
            if (s[j] === '"' || s[j] === "'") { const q = s[j]; const e = s.indexOf(q, j + 1); av = s.slice(j + 1, e); j = e + 1; }
            else { while (j < s.length && !/[\s>]/.test(s[j])) av += s[j++]; }
          }
          if (an) el._attrs.set(an.toLowerCase(), decode(av)); else j++;
        }
        top().appendChild(el);
        if (!selfClose && !VOID.has(el.tagName)) stack.push(el);
        i = j; continue;
      }
      let e = s.indexOf('<', i + 1); if (e < 0) e = s.length;
      top().appendChild(new Text(decode(s.slice(i, e))));
      i = e;
    }
  }
  function parseStyle(text, st) {
    String(text || '').split(';').forEach((d) => {
      const k = d.indexOf(':'); if (k < 0) return;
      const p = d.slice(0, k).trim(); if (p) st[camel(p)] = d.slice(k + 1).trim();
    });
  }

  class Element {
    constructor(tag) {
      this.nodeType = 1; this.tagName = String(tag).toUpperCase(); this.nodeName = this.tagName;
      this.parentNode = null; this.childNodes = []; this._attrs = new Map(); this._style = null;
      this._value = null; this._sel = null; this._disabled = null; this._none = false;
      this.selectionStart = 0; this.selectionEnd = 0;
      listen(this);
      const self = this;
      this.dataset = new Proxy({}, {
        get: (t, p) => (typeof p === 'string' && self.hasAttribute('data-' + kebab(p)) ? self.getAttribute('data-' + kebab(p)) : undefined),
        set: (t, p, v) => { self.setAttribute('data-' + kebab(p), String(v)); return true; },
        has: (t, p) => self.hasAttribute('data-' + kebab(String(p))),
        deleteProperty: (t, p) => { self.removeAttribute('data-' + kebab(String(p))); return true; },
      });
      this.classList = {
        _all: () => (self.getAttribute('class') || '').split(/\s+/).filter(Boolean),
        contains: (c) => self.classList._all().includes(c),
        add: (...cs) => { const a = self.classList._all(); cs.forEach((c) => { if (!a.includes(c)) a.push(c); }); self.setAttribute('class', a.join(' ')); },
        remove: (...cs) => { self.setAttribute('class', self.classList._all().filter((c) => !cs.includes(c)).join(' ')); },
        toggle: (c, force) => { const on = force === undefined ? !self.classList.contains(c) : !!force; if (on) self.classList.add(c); else self.classList.remove(c); return on; },
      };
    }
    getAttribute(k) { k = String(k).toLowerCase(); return this._attrs.has(k) ? this._attrs.get(k) : null; }
    setAttribute(k, v) { k = String(k).toLowerCase(); this._attrs.set(k, String(v)); if (k === 'style') this._style = null; }
    hasAttribute(k) { return this._attrs.has(String(k).toLowerCase()); }
    removeAttribute(k) { k = String(k).toLowerCase(); this._attrs.delete(k); if (k === 'style') this._style = null; }
    get id() { return this.getAttribute('id') || ''; }
    set id(v) { this.setAttribute('id', v); }
    get className() { return this.getAttribute('class') || ''; }
    set className(v) { this.setAttribute('class', v); }
    get style() {
      if (!this._style) {
        const st = {};
        Object.defineProperty(st, 'cssText', {
          enumerable: false,
          get: () => Object.keys(st).map((k) => `${kebab(k)}: ${st[k]}`).join('; '),
          set: (v) => { Object.keys(st).forEach((k) => { delete st[k]; }); parseStyle(v, st); },
        });
        Object.defineProperty(st, 'setProperty', { enumerable: false, value: (p, v) => { st[camel(p)] = String(v); } });
        Object.defineProperty(st, 'getPropertyValue', { enumerable: false, value: (p) => st[camel(p)] || '' });
        parseStyle(this.getAttribute('style'), st);
        this._style = st;
      }
      return this._style;
    }
    get children() { return this.childNodes.filter((n) => n.nodeType === 1); }
    get firstElementChild() { return this.children[0] || null; }
    get lastElementChild() { const c = this.children; return c[c.length - 1] || null; }
    get firstChild() { return this.childNodes[0] || null; }
    get parentElement() { return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null; }
    get isConnected() { for (let n = this; n; n = n.parentNode) if (n === globalThis.document) return true; return false; }
    get ownerDocument() { return globalThis.document; }
    get content() { return this; }                       // <template>
    _touch() { for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (n.tagName === 'SELECT') n._none = false; }
    appendChild(n) { return this.insertBefore(n, null); }
    insertBefore(n, ref) {
      if (n.nodeType === 11) { n.childNodes.slice().forEach((c) => this.insertBefore(c, ref)); return n; }
      if (ref && ref.parentNode !== this) throw new Error('NotFoundError: insertBefore: the reference node is not a child');
      if (n.parentNode) n.parentNode.removeChild(n);
      const i = ref ? this.childNodes.indexOf(ref) : -1;
      if (i < 0) this.childNodes.push(n); else this.childNodes.splice(i, 0, n);
      n.parentNode = this; this._touch(); return n;
    }
    removeChild(n) {
      const i = this.childNodes.indexOf(n);
      if (i >= 0) { this.childNodes.splice(i, 1); n.parentNode = null; this._touch(); }
      return n;
    }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    replaceWith(n) { const p = this.parentNode; if (!p) return; p.insertBefore(n, this); p.removeChild(this); }
    append(...ns) { ns.forEach((n) => this.appendChild(typeof n === 'string' ? new Text(n) : n)); }
    contains(n) { for (; n; n = n.parentNode) if (n === this) return true; return false; }
    get textContent() { return this.childNodes.map((n) => n.textContent).join(''); }
    set textContent(v) {
      this.childNodes.forEach((n) => { n.parentNode = null; }); this.childNodes = [];
      const s = String(v == null ? '' : v); if (s) this.appendChild(new Text(s)); this._touch();
    }
    get innerText() { return this.textContent; }
    set innerText(v) { this.textContent = v; }
    get innerHTML() { return this.childNodes.map(serialize).join(''); }
    set innerHTML(h) {
      this.childNodes.forEach((n) => { n.parentNode = null; }); this.childNodes = [];
      parseInto(h == null ? '' : h, this); this._touch();
    }
    get outerHTML() { return serialize(this); }
    get value() {
      if (this.tagName === 'SELECT') { const o = this._selectedOption(); return o ? o.value : ''; }
      if (this.tagName === 'OPTION') return this.hasAttribute('value') ? this.getAttribute('value') : this.textContent.replace(/\s+/g, ' ').trim();
      if (this._value !== null) return this._value;
      return this.getAttribute('value') || '';
    }
    set value(v) {
      if (this.tagName === 'SELECT') {
        const opts = this.options; let hit = null;
        for (const o of opts) if (o.value === String(v)) { hit = o; break; }
        opts.forEach((o) => { o._sel = (o === hit); });
        this._none = !hit; return;
      }
      if (this.tagName === 'OPTION') { this.setAttribute('value', v); return; }
      this._value = String(v == null ? '' : v);
      this.selectionStart = this.selectionEnd = this._value.length;
    }
    get options() { return this.querySelectorAll('option'); }
    get selected() { return this._sel !== null ? this._sel : this.hasAttribute('selected'); }
    set selected(v) {
      if (v) { const s = this.closest('select'); if (s) { s.options.forEach((o) => { o._sel = false; }); s._none = false; } }
      this._sel = !!v;
    }
    _selectedOption() {
      if (this._none) return null;
      const opts = this.options; let pick = null;
      for (const o of opts) if (o.selected) pick = o;
      return pick || opts[0] || null;
    }
    get selectedOptions() { const o = this._selectedOption(); return o ? [o] : []; }
    get selectedIndex() { const o = this._selectedOption(); return o ? this.options.indexOf(o) : -1; }
    get disabled() { return this._disabled !== null ? this._disabled : this.hasAttribute('disabled'); }
    set disabled(v) { this._disabled = !!v; }
    querySelectorAll(sel) {
      const list = parseSel(sel); const out = [];
      const walk = (n) => { for (const c of n.childNodes) { if (c.nodeType !== 1) continue; if (matchList(c, list)) out.push(c); walk(c); } };
      walk(this); return out;
    }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    matches(sel) { return matchList(this, parseSel(sel)); }
    closest(sel) { const list = parseSel(sel); for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (matchList(n, list)) return n; return null; }
    focus() {
      const d = globalThis.document; if (d.activeElement === this) return;
      const prev = d.activeElement; d.activeElement = this;
      if (prev && prev !== d.body && prev.nodeType === 1) { prev.dispatchEvent(new Event('blur')); prev.dispatchEvent(new Event('focusout', { bubbles: true })); }
      this.dispatchEvent(new Event('focus')); this.dispatchEvent(new Event('focusin', { bubbles: true }));
    }
    blur() {
      const d = globalThis.document; if (d.activeElement !== this) return;
      d.activeElement = d.body; this.dispatchEvent(new Event('blur')); this.dispatchEvent(new Event('focusout', { bubbles: true }));
    }
    click() { if (this.disabled) return; this.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })); }
    select() { this.selectionStart = 0; this.selectionEnd = this.value.length; }
    scrollIntoView() {}
    getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
    getClientRects() { return []; }
  }
  globalThis.Element = Element; globalThis.HTMLElement = Element; globalThis.Node = Element; globalThis.Text = Text;

  class Document {
    constructor() {
      this.nodeType = 9; this.parentNode = null; this.childNodes = []; listen(this);
      this.documentElement = new Element('html'); this.documentElement.parentNode = this; this.childNodes.push(this.documentElement);
      this.head = new Element('head'); this.body = new Element('body');
      this.documentElement.appendChild(this.head); this.documentElement.appendChild(this.body);
      this.activeElement = this.body; this.readyState = 'complete';
    }
    createElement(t) { return new Element(t); }
    createTextNode(t) { return new Text(t); }
    createDocumentFragment() { const f = new Element('#fragment'); f.nodeType = 11; return f; }
    getElementById(id) { return this.documentElement.querySelectorAll('[id]').find((e) => e.getAttribute('id') === String(id)) || null; }
    querySelectorAll(s) { const out = this.documentElement.querySelectorAll(s); return this.documentElement.matches(s) ? [this.documentElement].concat(out) : out; }
    querySelector(s) { return this.querySelectorAll(s)[0] || null; }
    contains(n) { for (; n; n = n.parentNode) if (n === this) return true; return false; }
  }
  globalThis.document = new Document();
  listen(globalThis);

  globalThis.CSS = { escape(value) {
    const s = String(value); let out = ''; const first = s.charCodeAt(0);
    for (let i = 0; i < s.length; i++) {
      const c = s.charCodeAt(i);
      if (c === 0) { out += '�'; continue; }
      if ((c >= 1 && c <= 31) || c === 127 || (i === 0 && c >= 48 && c <= 57) || (i === 1 && c >= 48 && c <= 57 && first === 45)) { out += '\\' + c.toString(16) + ' '; continue; }
      if (i === 0 && s.length === 1 && c === 45) { out += '\\' + s[i]; continue; }
      if (c >= 128 || c === 45 || c === 95 || (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122)) { out += s[i]; continue; }
      out += '\\' + s[i];
    }
    return out;
  } };

  globalThis.state = { heldSpools: [] };
  globalThis.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
  globalThis.navigator = {};
  globalThis.location = { href: 'http://fcc.test/', pathname: '/', search: '' };
  globalThis.setInterval = () => 0;
  globalThis.clearInterval = () => {};
  globalThis.requestAnimationFrame = (f) => setTimeout(f, 0);
  globalThis.showToast = (msg, type = 'info', duration = 2000) => { rec.toasts.push({ msg: String(msg), type, duration }); };
  globalThis.__respond = () => null;
  globalThis.fetch = (url, opts) => {
    const o = opts || {}; const u = String(url); const method = String(o.method || 'GET').toUpperCase();
    let body = null; if (o.body) { try { body = JSON.parse(o.body); } catch (e) { body = o.body; } }
    rec.fetches.push({ url: u, method, body });
    const r = globalThis.__respond(u, method, body) || {};
    const status = r.status || 200; const payload = r.body === undefined ? {} : r.body;
    const answer = () => (r.fail ? Promise.reject(new TypeError('Failed to fetch')) : Promise.resolve({
      ok: status < 400, status,
      json: () => Promise.resolve(JSON.parse(JSON.stringify(payload))),
      text: () => Promise.resolve(JSON.stringify(payload)),
    }));
    if (r.wait) return r.wait.then(answer);               // answered when the scenario says
    return r.delay ? new Promise((res) => setTimeout(res, r.delay)).then(answer) : answer();
  };

  // ----- what a scenario uses ----------------------------------------------
  globalThis.settle = (ms) => new Promise((r) => setTimeout(r, ms == null ? 30 : ms));
  globalThis.key = (el, k, extra) => {
    const ev = new KeyboardEvent('keydown', Object.assign({ key: k, bubbles: true, cancelable: true }, extra || {}));
    el.dispatchEvent(ev); return ev;
  };
  globalThis.fire = (el, type) => { const ev = new Event(type, { bubbles: true, cancelable: true }); el.dispatchEvent(ev); return ev; };
  globalThis.cardOf = (job) => document.querySelector(`.fcc-cr-card[data-job="${CSS.escape(job)}"]`);
  globalThis.lineOf = (card, line) => {
    const q = (cls) => card.querySelector(`.${cls}[data-line="${CSS.escape(String(line))}"]`);
    return { sel: q('fcc-cr-pick'), box: q('fcc-cr-other'), info: q('fcc-cr-other-info') };
  };
  // A person's pick: the value, then the browser's `change`.
  globalThis.pickIn = (sel, value) => { sel.value = value; fire(sel, 'change'); };
  // What a picker offers, group by group, in order.
  globalThis.groupsOf = (sel) => sel.children.map((c) => (c.tagName === 'OPTGROUP'
    ? { group: c.getAttribute('label'), cls: c.className, options: c.children.map((o) => ({ value: o.value, text: o.textContent, remaining: o.getAttribute('data-remaining') })) }
    : { option: c.value, text: c.textContent }));
  globalThis.posts = (prefix) => rec.fetches.filter((f) => f.method === 'POST' && f.url.startsWith(prefix)).map((f) => f.body);
  globalThis.gets = (prefix) => rec.fetches.filter((f) => f.method === 'GET' && f.url.startsWith(prefix)).map((f) => f.url);
  globalThis.infoOf = (info) => ({ text: info.textContent, color: info.style.color || '' });
}

(async () => {
  const unhandled = [];
  process.on('unhandledRejection', (e) => unhandled.push(String((e && e.stack) || e)));
  const ctx = vm.createContext({ console, setTimeout, clearTimeout });
  vm.runInContext('(' + prelude.toString() + ')()', ctx, { filename: 'prelude.js' });
  for (const p of MODULE_PATHS) vm.runInContext(fs.readFileSync(p, 'utf8'), ctx, { filename: p });
  const result = await vm.runInContext('(async () => {\n' + __SCENARIO__ + '\n})()', ctx, { filename: 'scenario.js' });
  console.log('__FCC_RESULT__' + JSON.stringify({ result, unhandled, errors: ctx.__rec.errors }));
  process.exit(0);
})().catch((e) => {
  console.error((e && e.stack) || e);
  process.exit(3);
});
"""


def run(tmp_path, scenario: str, data: dict) -> dict:
    """Runs `scenario` (the body of an async function) after the modules load,
    with `__DATA__` replaced by `data` as JSON."""
    body = scenario.replace("__DATA__", json.dumps(data))
    driver = (DRIVER_JS
              .replace("__MODULE_PATHS__", json.dumps([str(MODULES / m) for m in ("overlay_mount.js", "cancel_review.js")]))
              .replace("__SCENARIO__", json.dumps(body)))
    script = tmp_path / "driver.js"
    script.write_text(driver, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and lines, (
        f"node driver failed (rc={proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    out = json.loads(lines[-1][len(RESULT_MARK):])
    assert out["unhandled"] == [], out["unhandled"]
    assert out["errors"] == [], out["errors"]
    return out["result"]


# --------------------------------------------------------------------------- #
# The reviews (made-up printers, heads and spools).

HEADS = [{"toolhead": "HEAD-5", "position": 4, "sid": 229, "sids": [229]},
         {"toolhead": "HEAD-7", "position": 6, "sid": 243, "sids": [243]}]


def _base(job, kind, **extra):
    rec = {"printer_name": "TESTER", "job_id": job, "filename": "/usb/F.BGC", "progress": 0.42,
           "total_grams": 84.28, "spools": [], "ambiguous": False, "kind": kind,
           "heads_source": "print_end", "heads_words": WORDS}
    rec.update(extra)
    return rec


def _row(sid, toolhead, pos, grams, remaining=300.0):
    return {"sid": sid, "toolhead": toolhead, "position": pos, "grams": grams, "current_used": 700.0,
            "initial_weight": 1000.0, "remaining_before": remaining, "remaining_after": remaining - grams,
            "display": f"#{sid} Test Spool", "color": "ff0000", "ambiguous": False}


NO_SPOOL = _base("ns", "no_spool", usage_map={"4": 84.28},
                 heads_at_end=[{"toolhead": "HEAD-5", "position": 4, "sid": 229, "sids": [229]}])
PARTIAL = _base("p", "partial", spools=[_row(243, "HEAD-7", 6, 75.32)], unresolved_usage={"4": 8.96},
                heads_at_end=HEADS + [{"toolhead": "HEAD-5", "position": 4, "sid": 42, "when": "start"}],
                unresolved_notes={"4": "HEAD-5 had #42 when the print started and #229 when the print ended."})
SHORTFALL = _base("s#shortfall", "shortfall", rev=0, unresolved_usage={"0": 3.0},
                  shortfall_causes={"0": {"why": "not_charged", "sid": 5, "toolhead": "HEAD-1", "archived": False}},
                  heads_at_end=[{"toolhead": "HEAD-1", "position": 0, "sid": 5, "sids": [5]}])
HELD_SET = _base("set", "partial", unresolved_usage={"4": 84.28},
                 heads_at_end=[{"toolhead": "HEAD-5", "position": 4, "sid": 229, "sids": [229]},
                               {"toolhead": "HEAD-5", "position": 4, "sid": 42, "when": "start"}],
                 unresolved_sets={"4": [{"sid": 42, "when": "start", "display": "#42 Test", "remaining": 12.5},
                                        {"sid": 229, "when": "end", "display": "#229 Test", "remaining": 800.0}]},
                 unresolved_notes={"4": "FCC saw #42 when the print started and #229 when the print ended."})

# /api/spools/<id>: {success, data} as routes_inventory.api_get_spool answers.
SPOOLS = {
    "42": {"body": {"success": True, "data": {"id": 42, "filament": {"name": "Galaxy Black"},
                                              "location": "SHELF-2", "remaining_weight": 120.5}}},
    "43": {"body": {"success": True, "data": {"id": 43, "filament": {"name": "Signal Red"},
                                              "location": "SHELF-3", "remaining_weight": 55.0}}},
    "57": {"body": {"success": True, "data": {"id": 57, "filament": {"name": "Ocean Blue"},
                                              "location": "", "remaining_weight": 412.4}}},
}

RESPOND_JS = r"""
const D = __DATA__;
window.__respond = (url, method) => {
  if (url.startsWith('/api/cancel_deduct/pending')) return { body: { pending: D.pending } };
  if (url.startsWith('/api/cancel_deduct/candidates')) {
    // D.holdHeads: the printer's heads come only once the scenario calls __releaseHeads().
    const wait = D.holdHeads ? new Promise((res) => { window.__releaseHeads = res; }) : null;
    return { body: { heads: D.heads || [] }, wait };
  }
  if (url.startsWith('/api/cancel_deduct/confirm')) return { body: { status: 'error', msg: 'stub: nothing applied' } };
  if (url.startsWith('/api/spools/')) {
    const id = url.split('/').pop();
    if ((D.fail || []).includes(id)) return { fail: true };
    const hit = (D.spools || {})[id];
    if (!hit) return { status: 404, body: { success: false, msg: 'Spool not found' } };
    return Object.assign({ delay: (D.delays || {})[id] || 0 }, hit);
  }
  return { body: {} };
};
state.heldSpools = D.buffer || [];
await window.openCancelReview();
await settle(40);
"""


def _scenario(body: str) -> str:
    return RESPOND_JS + body


# --------------------------------------------------------------------------- #

FORMS = ["42", "#42", "# 42", "  42  ", "ID:42", "id:42", "Id: 42", "SPL:42", "spl:42", " ID:42 ",
         # A scanner's double read glued together, and a key left in front: the last label.
         "ID:41ID:42", "qID:42"]

BOX_FORMS_JS = r"""
const c = cardOf('ns');
const { sel, box, info } = lineOf(c, '4');
pickIn(sel, 'other');
const out = [];
for (const text of D.forms) {
  const before = window.__rec.fetches.length;
  box.focus();
  box.value = text;
  key(box, 'Enter');
  await settle(20);
  out.push({ text, looked: window.__rec.fetches.slice(before).map((f) => f.url), info: info.textContent });
}
// A person who types and moves on (the browser's `change` on blur) is read the same way.
box.value = 'SPL:43';
fire(box, 'change');
await settle(20);
const changed = info.textContent;
// Apply charges the spool the box names.
box.value = 'ID:42';
key(box, 'Enter');
await settle(20);
c.querySelector('.fcc-cr-confirm').click();
await settle(30);
// The same on a shortfall card's line and a held set's line.
const elsewhere = [];
for (const [job, line] of [['s#shortfall', 'pos:0'], ['set', 'set:4:42']]) {
  const l = lineOf(cardOf(job), line);
  pickIn(l.sel, 'other');
  l.box.value = 'ID:57';
  key(l.box, 'Enter');
  await settle(20);
  elsewhere.push({ job, info: l.info.textContent });
}
return { out, changed, confirms: posts('/api/cancel_deduct/confirm'), elsewhere };
"""


def test_the_id_box_reads_a_number_or_a_spool_label_in_every_form(tmp_path):
    res = run(tmp_path, _scenario(BOX_FORMS_JS),
              {"pending": [NO_SPOOL, SHORTFALL, HELD_SET], "spools": SPOOLS, "forms": FORMS})
    for got in res["out"]:
        assert got["looked"] == ["/api/spools/42"], got
        assert got["info"] == "#42 Galaxy Black (SHELF-2)", got
    assert res["changed"] == "#43 Signal Red (SHELF-3)", res["changed"]
    assert res["confirms"] == [{"printer_name": "TESTER", "job_id": "ns",
                                "charges": [{"position": 4, "sid": 42, "grams": 84.28}]}], res["confirms"]
    assert res["elsewhere"] == [{"job": "s#shortfall", "info": "#57 Ocean Blue"},
                                {"job": "set", "info": "#57 Ocean Blue"}], res["elsewhere"]


ENTER_JS = r"""
const c = cardOf('p');
const { sel, box, info } = lineOf(c, '243');
pickIn(sel, 'other');
const grams = c.querySelector('.fcc-cr-grams');
const gramsBefore = grams.value;
// What else would hear the Enter: the page (a bubble listener on the document,
// where the dashboard's own key handlers sit) and any press.
const heard = [];
document.addEventListener('keydown', (e) => heard.push(e.key));
const pressed = [];
document.addEventListener('click', (e) => pressed.push(e.target.className || e.target.tagName), true);
box.focus();
box.value = 'ID:42';                       // what the scanner typed
const ev = key(box, 'Enter');
await settle(30);
const first = { prevented: ev.defaultPrevented, heard: heard.slice(), info: info.textContent,
                value: box.value, selected: [box.selectionStart, box.selectionEnd] };
// A scanner set to send CR LF sends a second Enter: nothing more happens.
const ev2 = key(box, 'Enter');
await settle(30);
return {
  first,
  second: { prevented: ev2.defaultPrevented, heard: heard.slice() },
  looked: gets('/api/spools/'),
  pressed,
  posted: window.__rec.fetches.filter((f) => f.method === 'POST').map((f) => f.url),
  open: !!document.getElementById('fcc-cancel-review-overlay'),
  focus: document.activeElement === box,
  grams: [gramsBefore, grams.value],
  remaining: grams.dataset.remaining,
};
"""


def test_an_enter_in_the_box_only_reads_it(tmp_path):
    res = run(tmp_path, _scenario(ENTER_JS), {"pending": [PARTIAL], "spools": SPOOLS})
    first = res["first"]
    assert first["prevented"] is True, first
    assert first["heard"] == [], "the Enter went past the box"
    assert first["info"] == "#42 Galaxy Black (SHELF-2)", first
    assert first["value"] == "ID:42", "the scan stays whole in the box"
    assert first["selected"] == [0, 5], "the next scan replaces it"
    assert res["second"] == {"prevented": True, "heard": []}, res["second"]
    assert res["looked"] == ["/api/spools/42"], "a second Enter looks up nothing more"
    assert res["pressed"] == [] and res["posted"] == [], (res["pressed"], res["posted"])
    assert res["open"] and res["focus"], res
    assert res["grams"] == ["75.32", "75.32"], res["grams"]
    assert res["remaining"] == "120.5", "the row's preview follows the spool the box names"


UNREAD_JS = r"""
const c = cardOf('ns');
const { sel, box, info } = lineOf(c, '4');
pickIn(sel, 'other');
const said = () => ({ said: info.textContent, color: info.style.color || '' });
const shown = said();                      // the box appears with its hint
const out = [];
for (const text of D.unread) {
  box.value = text;
  key(box, 'Enter');
  await settle(20);
  out.push(Object.assign({ input: text }, said()));
}
const lookedForUnread = gets('/api/spools/');
// A spool FCC can't find, and a lookup FCC got no answer to (Enter again tries again).
box.value = '999'; key(box, 'Enter'); await settle(20);
const missing = said();
box.value = '77'; key(box, 'Enter'); await settle(20);
const failed = said();
key(box, 'Enter'); await settle(20);
const retried = gets('/api/spools/77').length;
// Apply over a box it can't read: nothing posted, and the card says why there
// (a toast is drawn under the overlay).
box.value = 'LOC:SHELF-1';
c.querySelector('.fcc-cr-confirm').click();
await settle(30);
return { shown, out, lookedForUnread, missing, failed, retried, afterApply: said(),
         posted: posts('/api/cancel_deduct/confirm'), toasts: window.__rec.toasts };
"""

HINT = "Type the spool's number, or scan its label."
UNREAD = {
    "LOC:SHELF-1": "\"LOC:SHELF-1\" is a location's label, not a spool's.",
    "loc:shelf-1": "\"loc:shelf-1\" is a location's label, not a spool's.",
    "FIL:12": "\"FIL:12\" is a filament's label, not a spool's.",
    "abc": "\"abc\" isn't a spool's number or label.",
    "ID:": "\"ID:\" isn't a spool's number or label.",
    "ID:0": "There's no spool #0.",
    "0": "There's no spool #0.",
    "https://example.com/spool/123/": "\"https://example.com/spo…\" isn't a spool's number or label.",
    "": HINT,
}
AMBER = "#e6c074"
MUTED = "#9aa"


def test_a_box_it_cannot_read_says_so_in_plain_words(tmp_path):
    res = run(tmp_path, _scenario(UNREAD_JS),
              {"pending": [NO_SPOOL], "spools": SPOOLS, "unread": list(UNREAD), "fail": ["77"]})
    assert res["shown"] == {"said": HINT, "color": MUTED}, res["shown"]
    for got in res["out"]:
        colour = MUTED if got["input"] == "" else AMBER
        assert (got["said"], got["color"]) == (UNREAD[got["input"]], colour), got
    assert res["lookedForUnread"] == [], "nothing it can't read is looked up"
    assert res["missing"] == {"said": "FCC couldn't find spool #999.", "color": AMBER}, res["missing"]
    assert res["failed"] == {"said": "Couldn't look up #77: FCC didn't answer.", "color": AMBER}, res["failed"]
    assert res["retried"] == 2, "an Enter after a lookup FCC didn't answer tries again"
    assert res["posted"] == [], res["posted"]
    assert res["afterApply"] == {"said": UNREAD["LOC:SHELF-1"], "color": AMBER}, res["afterApply"]
    warned = [t["msg"] for t in res["toasts"] if t["type"] == "warning"]
    assert any("#id" in m and "T4" in m for m in warned), warned


STALE_JS = r"""
const c = cardOf('p');
const { sel, box, info } = lineOf(c, '243');
const grams = c.querySelector('.fcc-cr-grams');
pickIn(sel, 'other');
box.value = '42'; key(box, 'Enter');       // its answer comes 120 ms later
await settle(10);
box.value = '43'; key(box, 'Enter');       // answered at once
await settle(200);
const newest = { info: info.textContent, remaining: grams.dataset.remaining };
// A pick made while a lookup is on its way: the late answer paints nothing.
box.value = '42'; key(box, 'Enter');
await settle(10);
pickIn(sel, '243');                        // back to the row's own spool
await settle(200);
return { newest, afterPick: { info: info.textContent, remaining: grams.dataset.remaining,
                              value: sel.value, box: box.style.display } };
"""


def test_an_older_answer_never_paints_over_a_newer_one(tmp_path):
    res = run(tmp_path, _scenario(STALE_JS), {"pending": [PARTIAL], "spools": SPOOLS, "delays": {"42": 120}})
    assert res["newest"] == {"info": "#43 Signal Red (SHELF-3)", "remaining": "55"}, res["newest"]
    assert res["afterPick"] == {"info": "", "remaining": "300", "value": "243", "box": "none"}, res["afterPick"]


BUFFER = [
    {"id": 57, "display": "#57 Brand PLA (Ocean Blue)", "remaining_weight": 412.4},
    {"id": 42, "display": "#42 Brand PETG (Red)", "remaining_weight": None, "archived": True},
    {"id": 229, "display": "#229 Brand PLA (Black)", "remaining_weight": 500},
    {"id": 300, "remaining_weight": 0},
]
OPT = {
    "57": {"value": "57", "text": "#57 Brand PLA (Ocean Blue) (412.4g left)", "remaining": "412.4"},
    "42": {"value": "42", "text": "#42 Brand PETG (Red) (archived)", "remaining": ""},
    "229": {"value": "229", "text": "#229 Brand PLA (Black) (500g left)", "remaining": "500"},
    "300": {"value": "300", "text": "#300 (0g left)", "remaining": "0"},
}

BUFFER_JS = r"""
const lines = { ns: ['4'], p: ['243', 'pos:4'], 's#shortfall': ['pos:0'], set: ['set:4:42', 'set:4:229'] };
const drawn = {};
for (const [job, ls] of Object.entries(lines)) {
  for (const l of ls) drawn[`${job} ${l}`] = groupsOf(lineOf(cardOf(job), l).sel);
}
// Picking a spool from the buffer: the row's preview reads its grams left, and
// Apply charges it.
const c = cardOf('p');
const { sel } = lineOf(c, '243');
pickIn(sel, '57');
const remaining = c.querySelector('.fcc-cr-grams').dataset.remaining;
c.querySelector('.fcc-cr-confirm').click();
await settle(30);
return { drawn, remaining, confirms: posts('/api/cancel_deduct/confirm') };
"""


def _buffer_group(groups):
    found = [g for g in groups if g.get("cls") == "fcc-cr-buffer"]
    assert len(found) <= 1, groups
    return found[0] if found else None


def test_every_picker_lists_the_scan_buffer(tmp_path):
    res = run(tmp_path, _scenario(BUFFER_JS),
              {"pending": [NO_SPOOL, PARTIAL, SHORTFALL, HELD_SET], "spools": SPOOLS, "buffer": BUFFER})
    # Never a spool the picker lists already (its own, or one on its heads).
    want = {"ns 4": ["57", "42", "300"], "p 243": ["57", "300"], "p pos:4": ["57", "300"],
            "s#shortfall pos:0": ["57", "42", "229", "300"],
            "set set:4:42": ["57", "300"], "set set:4:229": ["57", "300"]}
    for line, sids in want.items():
        group = _buffer_group(res["drawn"][line])
        assert group is not None, (line, res["drawn"][line])
        assert group["group"] == "In the scan buffer", group
        assert group["options"] == [OPT[s] for s in sids], (line, group["options"])
    # After the heads' groups, just before "Another spool by #ID…".
    row = res["drawn"]["p 243"]
    assert [g.get("cls") or g.get("option") for g in row] == [
        "243", "fcc-cr-ended", "fcc-cr-started", "fcc-cr-buffer", "other"], row
    assert res["remaining"] == "412.4", res["remaining"]
    assert res["confirms"] == [{"printer_name": "TESTER", "job_id": "p",
                                "charges": [{"row": 243, "sid": 57, "grams": 75.32}]}], res["confirms"]


FOLLOWS_JS = r"""
const buffered = (job, line) => {
  const g = groupsOf(lineOf(cardOf(job), line).sel).find((x) => x.cls === 'fcc-cr-buffer');
  return g ? g.options.map((o) => o.value) : [];
};
const changed = () => document.dispatchEvent(new CustomEvent('inventory:buffer-updated', { detail: { spools: state.heldSpools } }));
const steps = {};
steps.opened = { row: buffered('p', '243'), line: buffered('ns', '4') };
const lineSel = lineOf(cardOf('ns'), '4').sel;
pickIn(lineSel, '57');
// A spool scanned into the buffer while the review is open.
state.heldSpools = [D.b57, D.b300];
changed();
steps.added = { row: buffered('p', '243'), line: buffered('ns', '4'), picked: lineSel.value };
// The picked spool leaves the buffer: it stays picked on its line, and goes from the others.
state.heldSpools = [D.b300];
changed();
steps.left = { row: buffered('p', '243'), line: buffered('ns', '4'), picked: lineSel.value };
// The printer's heads arrive (the spool on HEAD-9 is in the buffer too): listed once, under its head.
window.__releaseHeads();
await settle(30);
const lineGroups = groupsOf(lineSel);
steps.heads = { row: buffered('p', '243'), line: buffered('ns', '4'), picked: lineSel.value,
                order: lineGroups.map((g) => g.cls || g.option),
                now: (lineGroups.find((g) => g.cls === 'fcc-cr-now') || { options: [] }).options.map((o) => o.value) };
// A buffer change the review wasn't told of: a picker being opened draws it.
state.heldSpools = [D.b300, D.b777];
const rowSel = lineOf(cardOf('p'), '243').sel;
const shortSel = lineOf(cardOf('s#shortfall'), 'pos:0').sel;
const quiet = { row: buffered('p', '243'), short: buffered('s#shortfall', 'pos:0') };
fire(rowSel, 'mousedown');
shortSel.focus();
steps.opening = { quiet, row: buffered('p', '243'), short: buffered('s#shortfall', 'pos:0'),
                  untouched: buffered('ns', '4') };
// An empty buffer: no group, but a spool picked from it stays.
state.heldSpools = [];
changed();
steps.empty = { row: buffered('p', '243'), line: buffered('ns', '4'), picked: lineSel.value };
// Apply charges the spool picked from the buffer.
cardOf('ns').querySelector('.fcc-cr-confirm').click();
await settle(30);
steps.confirms = posts('/api/cancel_deduct/confirm');
// The list goes with the review.
const listening = () => document._ls.filter((l) => l.type === 'inventory:buffer-updated').length;
steps.listening = listening();
key(rowSel, 'Escape');
await settle(10);
steps.closed = { open: !!document.getElementById('fcc-cancel-review-overlay'), listening: listening() };
changed();
return steps;
"""


def test_the_buffer_list_follows_the_buffer(tmp_path):
    b57, b300 = BUFFER[0], BUFFER[3]
    b777 = {"id": 777, "display": "#777 Late Scan", "remaining_weight": 10}
    res = run(tmp_path, _scenario(FOLLOWS_JS),
              {"pending": [NO_SPOOL, PARTIAL, SHORTFALL], "spools": SPOOLS, "buffer": [b57],
               "b57": b57, "b300": b300, "b777": b777, "holdHeads": True,
               "heads": [{"toolhead": "HEAD-9", "position": 8, "sid": 300, "display": "#300 Test", "remaining": 0}]})
    assert res["opened"] == {"row": ["57"], "line": ["57"]}, res["opened"]
    assert res["added"] == {"row": ["57", "300"], "line": ["57", "300"], "picked": "57"}, res["added"]
    left = res["left"]
    assert left["row"] == ["300"] and sorted(left["line"]) == ["300", "57"] and left["picked"] == "57", left
    heads = res["heads"]
    assert heads["row"] == [] and heads["line"] == ["57"] and heads["picked"] == "57", heads
    assert heads["now"] == ["300"], heads
    assert heads["order"] == ["", "fcc-cr-ended", "fcc-cr-now", "fcc-cr-buffer", "other"], heads
    # #300 is under HEAD-9 now on every picker; #777 joined the buffer unannounced:
    # each picker shows it once opened (pressed, or reached by the keyboard), and
    # one nobody opened shows it at the next buffer change.
    opening = res["opening"]
    assert opening["quiet"] == {"row": [], "short": []}, opening
    assert opening["row"] == ["777"] and opening["short"] == ["777"], opening
    assert opening["untouched"] == ["57"], opening
    assert res["empty"] == {"row": [], "line": ["57"], "picked": "57"}, res["empty"]
    assert res["confirms"] == [{"printer_name": "TESTER", "job_id": "ns",
                                "charges": [{"position": 4, "sid": 57, "grams": 84.28}]}], res["confirms"]
    assert res["listening"] == 1, res["listening"]
    assert res["closed"] == {"open": False, "listening": 0}, res["closed"]


KEYS_JS = r"""
const c = cardOf('ns');
const { sel, box } = lineOf(c, '4');
pickIn(sel, 'other');
box.focus();
box.value = 'ID:42';
const heard = [];
document.addEventListener('keydown', (e) => heard.push(e.key));
const arrows = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End']
  .map((k) => ({ k, prevented: key(box, k).defaultPrevented }));
// An Enter on the picker itself is the browser's: the review takes no part in it.
const onPicker = key(sel, 'Enter').defaultPrevented;
const heardBefore = heard.slice();
const esc = key(box, 'Escape');
await settle(20);
return { arrows, onPicker, heard: heardBefore, escPrevented: esc.defaultPrevented,
         open: !!document.getElementById('fcc-cancel-review-overlay'),
         posted: window.__rec.fetches.filter((f) => f.method === 'POST').map((f) => f.url) };
"""


def test_keys_in_the_box_behave_as_on_the_rest_of_the_card(tmp_path):
    res = run(tmp_path, _scenario(KEYS_JS), {"pending": [NO_SPOOL], "spools": SPOOLS})
    assert all(not a["prevented"] for a in res["arrows"]), res["arrows"]
    assert res["onPicker"] is False
    assert res["heard"] == ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "Enter"], res["heard"]
    # Escape closes the review, as everywhere on it; every review stays pending.
    assert res["escPrevented"] is True and res["open"] is False, res
    assert res["posted"] == [], res["posted"]


def _lum(hexcol):
    hexcol = hexcol.lstrip("#")
    if len(hexcol) == 3:
        hexcol = "".join(c * 2 for c in hexcol)
    chans = []
    for i in (0, 2, 4):
        c = int(hexcol[i:i + 2], 16) / 255
        chans.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]


def _contrast(fg, bg=CARD_BG):
    a, b = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


READ_JS = r"""
const { info } = lineOf(cardOf('ns'), '4');
return { style: info.getAttribute('style') || '' };
"""


def test_the_box_words_are_readable_and_use_a_named_size(tmp_path):
    """The browser contrast guard can't run offline: this checks the colours the
    box's words are drawn in against the card, and their size."""
    res = run(tmp_path, _scenario(READ_JS), {"pending": [NO_SPOOL], "spools": SPOOLS})
    assert re.search(r"font-size:\s*var\(--fcc-fs-small\)", res["style"]), res["style"]
    for colour in (MUTED, AMBER):
        assert _contrast(colour) >= 4.5, (colour, _contrast(colour))


