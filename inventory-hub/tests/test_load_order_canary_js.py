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
     or an inline script with each {{ ... }} replaced by null. Along the way it
     builds the page's elements in document order (_Dom) and notes how many
     are parsed when each script runs: the stub answers document.body,
     getElementById and querySelector by that position, as a browser would.
  2. Pass 1 loads every script over a browser stub (STUB_JS) and records which
     script first defines each name: a new property of window (a function
     declaration, a var, a `window.X = ...`), or a new top-level const / let /
     class (those never land on window: V8 is asked which of the names the
     script's top-level declarations name, every declarator of each, resolve
     after the script that didn't before). Then it fires the DOMContentLoaded
     handlers and the load ones, as a browser does once every script has
     loaded: a name only a handler defines is filed under one definer past the
     last script, "(DOMContentLoaded / load handlers)".
  3. Pass 2 loads them again in a fresh context where each of those names is
     first planted on window as an accessor that records who read it and
     returns undefined. The defining script's own definition replaces it (a
     const / let / class shadows it), so a read recorded while an EARLIER
     script runs is an early read.
The stub runs only what runs at load: document.readyState is 'loading' while
the scripts run, fetch never answers, and of the events only DOMContentLoaded
and load fire, once, after every script (pass 1 only: pass 2 never fires them,
so a read inside a handler is never charged to anyone). Promise callbacks run
when each script ends, as at the browser's microtask checkpoint, and so do the
zero-delay timers it queued (setTimeout / setInterval with no delay or one
<= 0; an interval once; then up to two rounds of the ones they queue): while
the parser waits on the network for a later script (FCC sends every response
no-store) a browser runs them, so they count as that script's load. Longer
timers, animation frames and idle callbacks never fire. A throw in a handler
or a zero-delay timer is no load error (a browser would run it against the
page it then has), so it goes to the run's diagnostics, and what it defined
before it threw still counts; but every name it would set after the throw
goes unjudged, so on the page the diagnostics must be empty.

What it catches:
  - a script that throws while loading, a DOM error included (document.body
    read in a <head> script, an element looked up before the parser reached
    it);
  - a load-time read (window.X, a bare X, typeof X) of a name a later script
    defines, in a script's top-level code, anything that code calls, or a
    zero-delay timer it queues (wrapping an early read in setTimeout(..., 0) is
    no fix);
  - the same read of a name only a DOMContentLoaded or load handler defines (a
    provider moved into one: those run once every script has loaded);
  - a DOMContentLoaded / load handler or a zero-delay timer on the page that
    throws against the stub (most often a browser API the stub lacks), since
    every name it would set after the throwing line would go unjudged;
  - a load-time window.X read of a name that is only a top-level const / let /
    class (never on window, so always undefined), a script's read of one it
    declares itself included;
  - a script's load-time window.X read of a name it declares itself, made
    before a later script sets window.X: a script-scope alias (`const { X } =
    window;` or `const X = window.X;`, read while that declaration runs: the
    alias is undefined when it is taken) or any other such read (the bare X
    already holds the script's own value), each worded for what it is;
  - a file under static/js that the page doesn't load, or loads twice, and a
    page script missing from disk (a module split that forgets scripts.html);
  - template constructs it can't model (a <script> inside {% if %} / {% for %},
    Jinja control flow in an inline script, an async / defer / module script,
    a CDN library it doesn't know), which fail loudly with "teach the canary".

What it can't see:
  - code paths the stub's DOM doesn't take. It holds the templates' elements
    by position, but an id the templates don't have still gets a dummy
    element, as does one whose every element a script took out (an element a
    script builds is beyond a parse), and a query never finds an element a
    script built; a selector it can't read (a pseudo-class, + or ~) finds
    nothing; an element's text and inline style are empty; elements nest as
    their tags are written (no implied end tags), and one inside a Jinja
    block counts as there;
  - code paths of another window or visitor: matchMedia answers as the
    stub's 1600 x 1300 desktop window (width, height, orientation, a fine
    pointer with hover; any other feature never matches), and storage starts
    empty, as on a first visit;
  - reads inside handlers (a click, DOMContentLoaded, load): those run at
    call time, after every script has loaded, which is where this canary
    asks a read to move. That includes a DOMContentLoaded or load handler's
    read of a name a later handler defines (they run in the order added);
  - reads in a timer with a delay, an animation frame, an idle callback or a
    fetch callback queued at load. A browser may run those between scripts
    too (a fetch that answers while the parser waits for a later script), so
    one is no fix for an early read either, but the canary never runs them;
  - a name a zero-delay timer defines counts as defined when its script ends,
    although a browser may run the timer only after the next script loads;
  - a load-time use of a top-level `var X = window.X;` alias of a later
    script's name. A top-level var IS the window property, so the later
    script's assignment reaches it and a use at call time works; only a use
    while loading gets undefined, and the alias's own read counts as the
    script reading its own name;
  - a top-level const / let declarator the declaration scan misreads
    (DRIVER_JS's declaredNames says where it can go wrong: a regular
    expression taken for a division, a line break read as the statement's end,
    a declaration past MAX_DECLARATION_TOKENS, a non-ASCII name);
  - properties of shared objects: an initialisation such as `state.X = ...`
    moved to a later file while an earlier one reads state.X at load is not
    seen (only names on window and top-level declarations are planted);
  - an `'X' in window` / hasOwnProperty / getOwnPropertyDescriptor check of a
    name pass 2 planted: the accessor is there, so the check says "present"
    before the defining script has run. The check itself records nothing; a
    read of X the code then makes is reported, although a browser would have
    skipped it (FCC has no such check today).

When it fails:
  - an early read: move the read into a function that runs later (on
    DOMContentLoaded, or in a handler such as a click; a zero-delay timer is
    no fix), or load the defining script earlier in scripts.html. A name a
    handler defines: define it while its script loads, outside the handler.
    A window.X read of a name the script declares itself says what fits it
    (loading the setter earlier throws if the setter reads the script's own
    X).
    A deliberate, harmless early read (a guard meant to find nothing at load
    and retried later) goes in ALLOWED_EARLY_READS as (reader script, name):
    the reason, named as the failure names them. The list starts empty, an
    entry needs a reason, and an entry no longer read early fails too.
  - a throw: either a gap in the stub (a browser feature STUB_JS lacks: add a
    plain stand-in that does nothing, never one for an FCC name) or a real
    load-time error (it would throw in a browser too: fix the script). A DOM
    one (document.body in a <head> script, an element looked up by a script
    above it) is real: look the element up later, on DOMContentLoaded, or
    move the <script> below it.
  - a throw in a DOMContentLoaded / load handler or a zero-delay timer: the
    same two causes (add the stand-in, or fix the code). Until it runs to its
    end, every name it sets after the throwing line goes unjudged.
  - a CDN library it doesn't know: add a part of its URL to CDN_GLOBALS with
    every global the real bundle sets on window (its UMD line,
    `global.X = factory()`, or a top-level var), and a stand-in for each to
    STUB_JS's cdnStandIns.

Needs node on PATH. Without it every test here skips, saying the load-order
canary did NOT run, and the run's warnings summary carries one PytestWarning
(test_core1_return_ejectall_js.py's node check, imported here);
FCC_REQUIRE_NODE=1 makes a missing node a collection error instead.
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

# Its import does the node check once for every node-vm file: without node it
# warns (a PytestWarning in the run's summary), and FCC_REQUIRE_NODE=1 makes a
# missing node a collection error.
from test_core1_return_ejectall_js import NODE

pytestmark = pytest.mark.skipif(NODE is None, reason=(
    "node is not on PATH: the load-order canary (test_load_order_canary_js.py) did NOT run, so a script that "
    "reads while it loads a name a later script defines would go unseen. Install Node.js (see CLAUDE.md "
    "Testing), or set FCC_REQUIRE_NODE=1 to fail instead of skipping."))

HUB = Path(__file__).resolve().parent.parent
TEMPLATES = HUB / "templates"
STATIC = HUB / "static"
ENTRY = "dashboard.html"
SCRIPTS_HTML = "templates/components/scripts.html"
RESULT_MARK = "__FCC_LOAD_ORDER__"
# The definer of a name only a DOMContentLoaded or load handler defines: those
# run once every script has loaded, so it counts as defined after the last one.
HANDLERS = "(DOMContentLoaded / load handlers)"

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
_JINJA_STATEMENT = re.compile(r"\{%[-+]?\s*([A-Za-z_]\w*)(.*?)[-+]?%\}", re.S)  # {%- / {%+ trim marks too
_JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.S)
_INCLUDE_TARGET = re.compile(r"""\s*(['"])([^'"]+)\1""")
# A <script> inside these never runs at load: a <template>'s content is inert,
# and the others hold raw text.
_INERT = ("template", "textarea", "style", "title", "noscript")
# A comment, a Jinja statement, or a tag's start ("<", an optional "/", a name).
_TOKEN = re.compile(r"<!--|\{%|<(/?)([A-Za-z][^\s/>]*)", re.I)
# A whole tag, its quoted attribute values (which may hold a '>') included.
_TAG = re.compile(r"""<(/?)([A-Za-z][^\s/>]*)((?:[^>"']|"[^"]*"|'[^']*')*)>""")
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


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track",
         "wbr"}
_HEAD_ONLY = {"base", "link", "meta", "noscript", "style", "template", "title"}


class _Dom:
    """The page's elements as the browser's parser builds them, in document
    order, for the stub's DOM by position: spec["elements"] holds each one's
    tag, attributes ({{ ... }} in a value read as '') and parent's index.

    Simplified: tags nest as written (the templates close what they open, and
    an implied end tag, such as an unclosed <p>'s, isn't modelled); <html>,
    <head> and <body> are implied where the page leaves them out (only a tag
    opens the <body>, not text); a <script>'s own element is left out, and so
    is what a <template>, <textarea>, <style>, <title> or <noscript> holds;
    an element inside a Jinja block counts once, as written."""

    def __init__(self):
        self.spec = {"elements": [], "html": -1, "head": -1, "body": -1}
        self.open: list = []  # the open elements' indices, innermost last
        self.head_done = False

    def _add(self, tag: str, attrs: dict, parent: int) -> int:
        self.spec["elements"].append({"tag": tag, "attrs": attrs, "parent": parent})
        return len(self.spec["elements"]) - 1

    def _html(self, attrs=None) -> None:
        if self.spec["html"] < 0:
            self.spec["html"] = self._add("html", attrs or {}, -1)
            self.open = [self.spec["html"]]

    def _head(self, attrs=None) -> None:
        self._html()
        if self.spec["head"] < 0:
            self.spec["head"] = self._add("head", attrs or {}, self.spec["html"])
            self.open = [self.spec["html"], self.spec["head"]]

    def _body(self, attrs=None) -> None:
        if self.spec["body"] < 0:
            self._head()
            self.head_done = True
            self.spec["body"] = self._add("body", attrs or {}, self.spec["html"])
            self.open = [self.spec["html"], self.spec["body"]]

    def start(self, tag: str, attrs: dict, closed: bool) -> None:
        if tag == "html":
            self._html(attrs)
        elif tag == "head":
            if self.spec["body"] < 0:
                self._head(attrs)
        elif tag == "body":
            self._body(attrs)
        else:
            if self.spec["body"] < 0:
                if tag not in _HEAD_ONLY:
                    self._body()  # content: the <body> starts here
                else:
                    self._head()
                    if self.head_done:  # after </head>, the parser puts it back in <head>
                        self._add(tag, attrs, self.spec["head"])
                        return
            k = self._add(tag, attrs, self.open[-1])
            if not closed and tag not in _VOID:
                self.open.append(k)

    def end(self, tag: str) -> None:
        if tag == "head":
            if self.spec["head"] in self.open:
                del self.open[self.open.index(self.spec["head"]):]
            self.head_done = True
        elif tag not in ("html", "body"):
            for j in range(len(self.open) - 1, 0, -1):
                if self.spec["elements"][self.open[j]]["tag"] == tag:
                    del self.open[j:]
                    return

    def script_here(self) -> int:
        """How many elements are parsed when a <script> at this point runs."""
        if self.spec["head"] < 0:
            self._head()  # a script before any tag goes into an implied <head>
        return len(self.spec["elements"])


def _dom_attributes(raw: str) -> dict:
    return {name: _JINJA_EXPRESSION.sub("", value) if value else "" for name, value in _attributes(raw).items()}


def read_page_scripts(templates: Path = TEMPLATES, static: Path = STATIC, entry: str = ENTRY) -> list:
    """The page's <script>s in the order the browser runs them.

    Each is a dict: kind ("file", "cdn" or "inline"), name (how failures name
    it: "js/modules/inv_core.js", a CDN URL, "templates/components/
    scripts.html:18 (inline)"), where (the template line of its tag), and per
    kind file / globals / code, plus the filename and line offsets node gives
    its stack frames; dom (the page's elements, _Dom.spec, one dict all the
    scripts share) and dom_at (how many of them are parsed when it runs).
    Raises CanaryCannotRead on anything it can't model.
    """
    scripts: list = []
    _read_template(templates, static, entry, scripts, inside=None, chain=(), dom=_Dom())
    return scripts


def _read_template(templates: Path, static: Path, rel: str, scripts: list, inside, chain: tuple, dom: _Dom) -> None:
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
                _read_template(templates, static, target.group(2), scripts, opened, chain + (rel,), dom)
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
        closing, tag = m.group(1), m.group(2).lower()
        if tag != "script" or closing:
            whole = _TAG.match(text, m.start())
            if not whole:  # a '<' that opens no tag
                pos = m.end()
                continue
            pos = whole.end()
            if closing:
                dom.end(tag)
                continue
            raw = whole.group(3)
            dom.start(tag, _dom_attributes(raw), tag in _INERT or raw.rstrip().endswith("/"))
            if tag in _INERT:
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
        parsed = {"dom": dom.spec, "dom_at": dom.script_here()}
        if "src" in attrs:
            scripts.append(dict(_src_script((attrs["src"] or "").strip(), static, where), **parsed))
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
            **parsed,
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


def _pinned(name: str, today: str) -> str:
    """What a proof that names today's home of an FCC name says when it fails."""
    return (f"This proof names where {name} is defined today ({today}). If a module split moved it, point the "
            f"proof at the file that defines it now (or, if nothing does, at another name a later script defines).")


def _pinned_readers(name: str, readers) -> str:
    """What a proof that names today's load-time readers of a name says when it fails."""
    return (f"This proof names the scripts that read {name} while they load today ({', '.join(readers)}). If a "
            f"module split moved those reads, point the proof at the scripts that read it while they load now.")


def with_fake(scripts: list, code: str, name: str, *, before: str = None, after: str = None) -> list:
    """The page plus one fake inline script, right before or right after a
    named one: next to that one's tag, so it sees the elements that one sees."""
    at = _index(scripts, before) if before else _index(scripts, after) + 1
    beside = scripts[at] if before else scripts[at - 1]
    fake = {"kind": "inline", "name": name, "where": name, "code": code, "filename": name,
            "lineOffset": 0, "columnOffset": 0}
    if "dom_at" in beside:
        fake["dom_at"] = beside["dom_at"]
    return scripts[:at] + [fake] + scripts[at:]


def with_moved(scripts: list, name: str, *, before: str) -> list:
    """The page with one script moved to right before another, where it sees
    the elements that one sees."""
    moving = scripts[_index(scripts, name)]
    rest = [s for s in scripts if s is not moving]
    at = _index(rest, before)
    if "dom_at" in rest[at]:
        moving = dict(moving, dom_at=rest[at]["dom_at"])
    return rest[:at] + [moving] + rest[at:]


# ---------------------------------------------------------------------------
# The browser stub. It runs inside the vm context (its objects belong to the
# page's realm) and returns the hook the driver works it with: CDN globals,
# the page's elements and how many are parsed, the zero-delay timers, the
# DOMContentLoaded / load listeners. Only a stand-in for the browser goes here:
# a stand-in for one of FCC's own names would hide every early read of it
# (test_the_stub_stands_in_only_for_the_browser).
# ---------------------------------------------------------------------------

STUB_JS = r"""
(function () {
  'use strict';
  const g = globalThis;
  const noop = () => {};
  const never = () => new Promise(noop);
  g.window = g; g.self = g; g.top = g; g.parent = g; g.frames = g;

  // DOMContentLoaded listeners (on document or window) and load listeners (on
  // window) are kept: the driver fires them once every script has loaded.
  // Every other listener is dropped, as those events never fire.
  let runningNow = '';
  const readyListeners = [];
  const listen = (target) => (type, fn) => {
    const t = String(type);
    if (fn == null || !(t === 'DOMContentLoaded' || (t === 'load' && target === 'window'))) return;
    if (readyListeners.some((r) => !r.removed && r.target === target && r.type === t && r.fn === fn)) return;
    readyListeners.push({ target, type: t, fn, by: runningNow, stack: new Error().stack, removed: false });
  };
  const unlisten = (target) => (type, fn) => {
    for (const r of readyListeners) if (r.target === target && r.type === String(type) && r.fn === fn) r.removed = true;
  };

  const rect = () => ({ top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0 });
  const styleDecl = () => new Proxy({ setProperty: noop, removeProperty: () => '', getPropertyValue: () => '', cssText: '' }, {
    get: (t, k) => (k in t ? t[k] : ''), set: (t, k, v) => { t[k] = v; return true; },
  });

  // The page's DOM by position (setPage / parsed, from the driver): an element
  // of the templates is there once the parser has reached it, which is the
  // running script's tag.
  let page = null;  // { recs, ids: Map(id -> [index]), end: one past each one's last descendant, html, head, body }
  let parsedUpTo = Infinity;

  // An element's state (tag, id, classes, attributes) lives in a record the
  // query engine reads too. A page element's comes from the templates; any
  // other's from what scripts set. A page element sits where the templates put
  // it (parentK) unless a script took it out (gone) or put it elsewhere
  // (parent); an element a script built sits where a script put it, if anywhere.
  const recOf = new WeakMap();
  const newRec = (tag, k) => ({ tag: String(tag || 'div').toLowerCase(), id: '', cls: new Set(), attrs: new Map(), k,
                               parentK: -1, pageKids: [], kids: [], parent: null, gone: false, el: null, html: '', text: '' });
  const setClasses = (rec, text) => { rec.cls.clear(); for (const c of String(text || '').split(/\s+/)) if (c) rec.cls.add(c); };
  const classList = (rec) => ({
    add: (...c) => c.forEach((x) => rec.cls.add(String(x))),
    remove: (...c) => c.forEach((x) => rec.cls.delete(String(x))),
    contains: (c) => rec.cls.has(String(c)),
    toggle: (c, force) => {
      const x = String(c);
      const on = force === undefined ? !rec.cls.has(x) : !!force;
      if (on) rec.cls.add(x); else rec.cls.delete(x);
      return on;
    },
    replace: (a, b) => { if (!rec.cls.delete(String(a))) return false; rec.cls.add(String(b)); return true; },
    forEach: (fn) => rec.cls.forEach(fn), item: (i) => (Array.from(rec.cls)[i] ?? null),
    get length() { return rec.cls.size; }, get value() { return Array.from(rec.cls).join(' '); },
  });
  const camel = (s) => s.replace(/-([a-z])/g, (m, c) => c.toUpperCase());
  const kebab = (s) => 'data-' + String(s).replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());
  // dataset is a view of the data-* attributes, as in a browser.
  const dataset = (rec) => new Proxy({}, {
    get: (t, k) => (typeof k === 'string' ? rec.attrs.get(kebab(k)) : undefined),
    set: (t, k, v) => { rec.attrs.set(kebab(k), String(v)); return true; },
    deleteProperty: (t, k) => { rec.attrs.delete(kebab(k)); return true; },
    has: (t, k) => typeof k === 'string' && rec.attrs.has(kebab(k)),
    ownKeys: () => Array.from(rec.attrs.keys()).filter((a) => a.startsWith('data-')).map((a) => camel(a.slice(5))),
    getOwnPropertyDescriptor: (t, k) => (typeof k === 'string' && rec.attrs.has(kebab(k))
      ? { value: rec.attrs.get(kebab(k)), writable: true, enumerable: true, configurable: true } : undefined),
  });
  const FLAGS = new Map([['checked', 'checked'], ['disabled', 'disabled'], ['hidden', 'hidden'], ['selected', 'selected'],
                         ['required', 'required'], ['readonly', 'readOnly'], ['multiple', 'multiple']]);
  const TEXTS = new Set(['type', 'name', 'title', 'href', 'src', 'value', 'placeholder']);
  // An attribute's mirror on the element's own properties (null: it went).
  const reflect = (el, rec, a, v) => {
    if (a === 'id') rec.id = v === null ? '' : v;
    else if (a === 'class') setClasses(rec, v);
    else if (FLAGS.has(a)) el[FLAGS.get(a)] = v !== null;
    else if (a === 'tabindex') el.tabIndex = v === null ? -1 : (parseInt(v, 10) || 0);
    else if (TEXTS.has(a)) el[a] = v === null ? '' : v;
  };
  const parentRec = (rec) => rec.parent || (rec.k >= 0 && !rec.gone && rec.parentK >= 0 ? page.recs[rec.parentK] : null);
  const elOf = (rec) => rec.el || makeEl(rec.tag, '', rec);
  // An element's children: a page element's from the templates (parsed, still
  // in place), then those scripts put in.
  const kidsOf = (rec) => {
    const out = [];
    if (rec.k >= 0) {
      for (const k of rec.pageKids) { const r = page.recs[k]; if (k < parsedUpTo && !r.gone && !r.parent) out.push(elOf(r)); }
    }
    return out.concat(rec.kids);
  };
  const connected = (rec) => {
    for (let r = rec, n = 0; r && n < 100000; n++) {
      if (r.k >= 0 && !r.parent) {
        if (r.gone || r.k >= parsedUpTo) return false;
        if (r.parentK < 0) return true;  // <html>
        r = page.recs[r.parentK];
      } else {
        r = r.parent;
      }
    }
    return false;
  };
  const takeOut = (r) => {
    if (r.parent) { const a = r.parent.kids; const j = a.indexOf(r.el); if (j >= 0) a.splice(j, 1); r.parent = null; }
    if (r.k >= 0) r.gone = true;
  };
  const adopt = (rec, child, first) => {
    const r = recOf.get(child);
    if (r) takeOut(r);
    if (first) rec.kids.unshift(child); else rec.kids.push(child);
    if (r) r.parent = rec;
  };
  const clearKids = (rec) => {
    for (const c of rec.kids.splice(0)) { const r = recOf.get(c); if (r) r.parent = null; }
    if (rec.k >= 0) for (const k of rec.pageKids) if (k < parsedUpTo && !page.recs[k].parent) page.recs[k].gone = true;
  };
  const sibling = (el, rec, step) => {
    const p = parentRec(rec);
    const a = p ? kidsOf(p) : [];
    const j = a.indexOf(el);
    return j < 0 ? null : (a[j + step] || null);
  };
  const makeEl = (tag, id, rec) => {
    rec = rec || newRec(tag, -1);
    const name = rec.tag.toUpperCase();
    const el = {
      tagName: name, nodeName: name, nodeType: 1,
      outerHTML: '', value: '', type: '', name: '', title: '', placeholder: '', href: '', src: '',
      checked: false, disabled: false, hidden: false, selected: false, required: false, readOnly: false, multiple: false,
      tabIndex: -1, style: styleDecl(), dataset: dataset(rec), classList: classList(rec), options: [], selectedOptions: [], files: [],
      offsetWidth: 0, offsetHeight: 0, offsetTop: 0, offsetLeft: 0, offsetParent: null,
      clientWidth: 0, clientHeight: 0, scrollWidth: 0, scrollHeight: 0, scrollTop: 0, scrollLeft: 0,
      selectionStart: 0, selectionEnd: 0, selectedIndex: -1,
      appendChild(c) { adopt(rec, c); return c; }, append(...c) { c.forEach((x) => adopt(rec, x)); },
      prepend(...c) { c.slice().reverse().forEach((x) => adopt(rec, x, true)); },
      removeChild(c) { const r = recOf.get(c); if (r) takeOut(r); return c; },
      replaceChild(c, old) { const r = recOf.get(old); if (r) takeOut(r); adopt(rec, c); return old; },
      insertBefore(c) { adopt(rec, c); return c; },
      insertAdjacentHTML: noop, insertAdjacentElement: (p, e) => e, insertAdjacentText: noop,
      remove() { takeOut(rec); }, replaceWith() { takeOut(rec); }, before: noop, after: noop,
      replaceChildren(...c) { clearKids(rec); c.forEach((x) => adopt(rec, x)); },
      cloneNode() { const copy = makeEl(rec.tag); for (const [a, v] of rec.attrs) copy.setAttribute(a, v); return copy; },
      setAttribute(a, v) { const n = String(a).toLowerCase(); const s = String(v); rec.attrs.set(n, s); reflect(el, rec, n, s); },
      getAttribute(a) { const n = String(a).toLowerCase(); return rec.attrs.has(n) ? rec.attrs.get(n) : null; },
      hasAttribute(a) { return rec.attrs.has(String(a).toLowerCase()); },
      removeAttribute(a) { const n = String(a).toLowerCase(); rec.attrs.delete(n); reflect(el, rec, n, null); },
      toggleAttribute(a, force) {
        const on = force === undefined ? !el.hasAttribute(a) : !!force;
        if (on) el.setAttribute(a, ''); else el.removeAttribute(a);
        return on;
      },
      getAttributeNames: () => Array.from(rec.attrs.keys()),
      addEventListener: noop, removeEventListener: noop, dispatchEvent: () => true,
      querySelector: (s) => query(s, rec, true), querySelectorAll: (s) => query(s, rec, false),
      getElementsByTagName: (t) => query(String(t), rec, false),
      getElementsByClassName: (c) => query(classSelector(c), rec, false),
      closest: (s) => closestOf(rec, s), matches: (s) => matchesSelector(rec, s),
      contains: (o) => { for (let r = recOf.get(o); r; r = parentRec(r)) if (r === rec) return true; return false; },
      hasChildNodes: () => kidsOf(rec).length > 0,
      focus: noop, blur: noop, click: noop, select: noop, setSelectionRange: noop,
      scrollIntoView: noop, scrollTo: noop, scrollBy: noop,
      getBoundingClientRect: rect, getClientRects: () => [],
      animate: () => ({ finished: Promise.resolve(), cancel: noop }),
      showModal: noop, show: noop, close: noop, attachShadow: () => makeEl('#shadow'),
      checkValidity: () => true, reportValidity: () => true, setCustomValidity: noop,
    };
    const read = (get) => ({ get, enumerable: true, configurable: true });
    const kept = (get, set) => ({ get, set, enumerable: true, configurable: true });
    Object.defineProperties(el, {
      id: kept(() => rec.id, (v) => { rec.id = String(v); }),
      className: kept(() => Array.from(rec.cls).join(' '), (v) => setClasses(rec, v)),
      innerHTML: kept(() => rec.html, (v) => { clearKids(rec); rec.html = String(v); }),
      innerText: kept(() => rec.text, (v) => { clearKids(rec); rec.text = String(v); }),
      textContent: kept(() => rec.text, (v) => { clearKids(rec); rec.text = String(v); }),
      parentNode: read(() => {
        const p = parentRec(rec);
        return p ? elOf(p) : (rec.k >= 0 && !rec.gone && rec.parentK < 0 ? g.document : null);
      }),
      parentElement: read(() => { const p = parentRec(rec); return p ? elOf(p) : null; }),
      ownerDocument: read(() => g.document),
      isConnected: read(() => connected(rec)),
      children: read(() => kidsOf(rec)), childNodes: read(() => kidsOf(rec)),
      childElementCount: read(() => kidsOf(rec).length),
      firstChild: read(() => kidsOf(rec)[0] || null), firstElementChild: read(() => kidsOf(rec)[0] || null),
      lastChild: read(() => kidsOf(rec).slice(-1)[0] || null), lastElementChild: read(() => kidsOf(rec).slice(-1)[0] || null),
      nextSibling: read(() => sibling(el, rec, 1)), nextElementSibling: read(() => sibling(el, rec, 1)),
      previousSibling: read(() => sibling(el, rec, -1)), previousElementSibling: read(() => sibling(el, rec, -1)),
    });
    if (id) rec.id = String(id);
    rec.el = el;
    recOf.set(el, rec);
    for (const [a, v] of rec.attrs) reflect(el, rec, a, v);
    return el;
  };

  // What the stub reads of a selector: a list of chains of compound selectors
  // (a type or *, #id, .class, [attr], [attr="v"] with = ~= ^= $= *= |=)
  // joined by a space (a descendant) or > (a child). Anything else (a
  // pseudo-class, + or ~, a namespace) can't be read, and the query keeps the
  // answer it always had: nothing.
  const SEL_TAG = /^(\*|[A-Za-z][\w-]*)/;
  const SEL_ID = /^#([\w-]+)/;
  const SEL_CLASS = /^\.([\w-]+)/;
  const SEL_ATTR = /^\[\s*([\w-]+)\s*(?:([~|^$*]?=)\s*(?:"([^"]*)"|'([^']*)'|([\w-]+))\s*)?\]/;
  const SEL_JOIN = /^\s*>\s*|^\s+/;
  const selectors = new Map();
  const splitList = (s) => {
    const out = [];
    let depth = 0, quote = '', start = 0;
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if (quote) { if (c === '\\') i += 1; else if (c === quote) quote = ''; continue; }
      if (c === '"' || c === "'") quote = c;
      else if (c === '[' || c === '(') depth += 1;
      else if (c === ']' || c === ')') depth -= 1;
      else if (c === ',' && depth === 0) { out.push(s.slice(start, i)); start = i + 1; }
    }
    out.push(s.slice(start));
    return out;
  };
  const parseChain = (s) => {
    const chain = [];
    let rest = s;
    while (rest) {
      let m;
      if (chain.length) {
        if (!(m = SEL_JOIN.exec(rest))) return null;
        chain.push(m[0].includes('>') ? '>' : ' ');
        rest = rest.slice(m[0].length);
      }
      const c = { tag: null, id: null, classes: [], attrs: [] };
      let any = false;
      if ((m = SEL_TAG.exec(rest))) { if (m[1] !== '*') c.tag = m[1].toLowerCase(); rest = rest.slice(m[0].length); any = true; }
      for (;;) {
        if ((m = SEL_ID.exec(rest))) c.id = m[1];
        else if ((m = SEL_CLASS.exec(rest))) c.classes.push(m[1]);
        else if ((m = SEL_ATTR.exec(rest))) c.attrs.push({ name: m[1].toLowerCase(), op: m[2] || '', value: m[3] ?? m[4] ?? m[5] ?? '' });
        else break;
        rest = rest.slice(m[0].length);
        any = true;
      }
      if (!any) return null;
      chain.push(c);
    }
    return chain.length ? chain : null;
  };
  const parseSelector = (text) => {
    const key = String(text);
    if (!selectors.has(key)) {
      const chains = splitList(key).map((part) => parseChain(part.trim()));
      selectors.set(key, chains.length && chains.every(Boolean) ? chains : null);
    }
    return selectors.get(key);
  };
  const matchCompound = (c, rec) => {
    if ((c.tag && rec.tag !== c.tag) || (c.id !== null && rec.id !== c.id)) return false;
    for (const x of c.classes) if (!rec.cls.has(x)) return false;
    for (const a of c.attrs) {
      const v = rec.attrs.get(a.name);
      const w = a.value;
      if (v === undefined || (a.op === '=' && v !== w) || (a.op === '~=' && !v.split(/\s+/).includes(w))
          || (a.op === '^=' && !(w && v.startsWith(w))) || (a.op === '$=' && !(w && v.endsWith(w)))
          || (a.op === '*=' && !(w && v.includes(w))) || (a.op === '|=' && v !== w && !v.startsWith(w + '-'))) return false;
    }
    return true;
  };
  const matchUp = (chain, j, rec) => {
    if (j < 0) return true;
    for (let p = parentRec(rec); p; p = parentRec(p)) {
      if (matchCompound(chain[j], p) && matchUp(chain, j - 2, p)) return true;
      if (chain[j + 1] === '>') return false;
    }
    return false;
  };
  const matchChain = (chain, rec) => matchCompound(chain[chain.length - 1], rec) && matchUp(chain, chain.length - 3, rec);
  const matchesSelector = (rec, s) => { const list = parseSelector(s); return !!list && list.some((ch) => matchChain(ch, rec)); };
  const closestOf = (rec, s) => {
    const list = parseSelector(s);
    for (let r = rec; list && r; r = parentRec(r)) if (list.some((ch) => matchChain(ch, r))) return elOf(r);
    return null;
  };
  const classSelector = (names) => String(names).trim().split(/\s+/).filter(Boolean).map((n) => '.' + n).join('') || ':none';
  // The page's elements a query finds, in document order: those parsed by now
  // and still in place, in the whole page (document's) or under an element
  // (its own). What a script built, and anything under it, is never found.
  const query = (s, scope, one) => {
    const list = page && (!scope || scope.k >= 0) ? parseSelector(s) : null;
    const out = [];
    if (list) {
      const to = Math.min(scope ? page.end[scope.k] : page.recs.length, parsedUpTo);
      for (let k = scope ? scope.k + 1 : 0; k < to; k++) {
        const rec = page.recs[k];
        if (!list.some((ch) => matchChain(ch, rec)) || !connected(rec)) continue;
        if (one) return elOf(rec);
        out.push(elOf(rec));
      }
    }
    return one ? null : out;
  };

  // matchMedia answers as the window the stub describes (innerWidth and
  // innerHeight: 1600 x 1300, the visual baselines' viewport, a desktop):
  // width and height and their min- / max- forms in px, em or rem,
  // orientation, a fine pointer that can hover. Any other feature (range
  // syntax, prefers-*) never matches.
  const mediaLength = (v) => {
    const m = /^(-?\d*\.?\d+)(px|em|rem)?$/.exec(String(v).trim());
    return m ? parseFloat(m[1]) * (m[2] && m[2] !== 'px' ? 16 : 1) : NaN;
  };
  const mediaFeature = (text) => {
    const m = /^\(\s*([a-z-]+)\s*(?::\s*(.+?))?\s*\)$/.exec(text);
    if (!m) return false;
    const [, feature, value] = m;
    const dim = /^(min-|max-)?(width|height|device-width|device-height)$/.exec(feature);
    if (dim) {
      const have = { width: g.innerWidth, height: g.innerHeight, 'device-width': g.screen.width,
                     'device-height': g.screen.height }[dim[2]];
      if (value === undefined) return have > 0;
      const want = mediaLength(value);
      if (Number.isNaN(want)) return false;
      return dim[1] === 'min-' ? have >= want : dim[1] === 'max-' ? have <= want : have === want;
    }
    if (feature === 'orientation') return value === (g.innerWidth >= g.innerHeight ? 'landscape' : 'portrait');
    if (feature === 'pointer' || feature === 'any-pointer') return value === undefined || value === 'fine';
    if (feature === 'hover' || feature === 'any-hover') return value === undefined || value === 'hover';
    return false;
  };
  const mediaMatches = (text) => {
    const all = String(text).trim().toLowerCase();
    return !all || all.split(',').some((one) => {
      let q = one.trim();
      const not = q.startsWith('not ');
      if (not) q = q.slice(4).trim();
      if (q.startsWith('only ')) q = q.slice(5).trim();
      const ok = q.split(/\s+and\s+/).every((p) => p === 'all' || p === 'screen' || mediaFeature(p));
      return not ? !ok : ok;
    });
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

  // The document. With the page's elements (setPage): <body> once the parser
  // has reached it (null in a <head> script), an element of the templates once
  // it is parsed, by id or by a selector the stub reads. An id the templates
  // don't have still gets a dummy element (one a script builds is beyond a
  // parse), and so does one whose every element a script took out. Without
  // them (a list of scripts made by hand): a dummy for every id, and a body.
  const byId = new Map();
  const without = { body: makeEl('body'), head: makeEl('head'), html: makeEl('html') };
  const pageEl = (k) => elOf(page.recs[k]);
  g.document = {
    nodeType: 9, defaultView: g, currentScript: null,
    get body() { return page ? (page.body >= 0 && page.body < parsedUpTo ? pageEl(page.body) : null) : without.body; },
    get head() { return page ? (page.head >= 0 ? pageEl(page.head) : null) : without.head; },
    get documentElement() { return page ? (page.html >= 0 ? pageEl(page.html) : null) : without.html; },
    get activeElement() { return g.document.body || g.document.documentElement; },
    readyState: 'loading', visibilityState: 'visible', hidden: false,
    title: '', cookie: '', referrer: '', URL: 'http://fcc.test/', characterSet: 'UTF-8',
    fonts: { ready: never(), check: () => true, addEventListener: noop, removeEventListener: noop },
    getElementById(id) {
      const s = String(id);
      const where = page ? page.ids.get(s) : null;
      if (where) {
        let below = false;
        for (const k of where) {
          if (page.recs[k].id !== s) continue;  // a script changed it
          if (k >= parsedUpTo) below = true;
          else if (connected(page.recs[k])) return pageEl(k);
        }
        if (below) return null;  // not parsed yet: below the running script
      }
      if (!byId.has(s)) byId.set(s, makeEl('div', s));
      return byId.get(s);
    },
    createElement: (tag) => makeEl(tag), createElementNS: (ns, tag) => makeEl(tag),
    createTextNode: (t) => ({ nodeType: 3, textContent: String(t), data: String(t) }),
    createComment: () => ({ nodeType: 8 }), createDocumentFragment: () => makeEl('#fragment'),
    createTreeWalker: () => ({ nextNode: () => null, currentNode: null }),
    createRange: () => ({ selectNodeContents: noop, collapse: noop, setStart: noop, setEnd: noop, getBoundingClientRect: rect }),
    createEvent: () => ({ initEvent: noop }),
    querySelector: (s) => query(s, null, true), querySelectorAll: (s) => query(s, null, false),
    getElementsByTagName: (t) => query(String(t), null, false),
    getElementsByClassName: (c) => query(classSelector(c), null, false),
    getElementsByName: (n) => query('[name="' + String(n).replace(/["\\]/g, '') + '"]', null, false),
    addEventListener: listen('document'), removeEventListener: unlisten('document'), dispatchEvent: () => true,
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

  // A zero-delay setTimeout or setInterval (no delay, or one <= 0) is kept
  // for the driver, which runs it right after the script that queued it and
  // that script's microtasks: a browser may run it there, before a later
  // script loads (FCC sends every response no-store, so the parser waits on
  // the network at each script). An interval runs once. Longer timers,
  // animation frames and idle callbacks never fire, and fetch never answers.
  // A microtask runs when the script that queued it ends (the context's
  // microtaskMode), as in a browser.
  let timerId = 0;
  const zeroTimers = [];
  const queueTimer = (fn, ms, args) => {
    const id = ++timerId;
    if (typeof fn === 'function' && !(Number(ms) > 0)) zeroTimers.push({ id, fn, args });
    return id;
  };
  const clearTimer = (id) => { const k = zeroTimers.findIndex((t) => t.id === id); if (k >= 0) zeroTimers.splice(k, 1); };
  Object.assign(g, {
    setTimeout: (fn, ms, ...args) => queueTimer(fn, ms, args), clearTimeout: clearTimer,
    setInterval: (fn, ms, ...args) => queueTimer(fn, ms, args), clearInterval: clearTimer,
    requestAnimationFrame: () => ++timerId, cancelAnimationFrame: noop,
    requestIdleCallback: () => ++timerId, cancelIdleCallback: noop,
    queueMicrotask: (fn) => { Promise.resolve().then(fn); },
    fetch: never,
    performance: { now: () => 0, timeOrigin: 0, mark: noop, measure: noop, getEntriesByName: () => [], getEntriesByType: () => [] },
    alert: noop, confirm: () => false, prompt: () => null, open: () => null, print: noop, focus: noop, blur: noop,
    close: noop, stop: noop, scroll: noop, scrollTo: noop, scrollBy: noop, postMessage: noop,
    getSelection: () => null, getComputedStyle: () => styleDecl(),
    matchMedia: (q) => ({ matches: mediaMatches(q), media: String(q), onchange: null, addEventListener: noop,
                          removeEventListener: noop, addListener: noop, removeListener: noop }),
    addEventListener: listen('window'), removeEventListener: unlisten('window'), dispatchEvent: () => true,
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
    // What the driver tells the stub: what is running now (a listener added
    // is stamped with it), and the document's readyState.
    running(label) { runningNow = String(label); },
    readyState(state) { g.document.readyState = state; },
    // The zero-delay timers queued since the last call, in order.
    takeTimers() { return zeroTimers.splice(0); },
    // The page's elements (read_page_scripts' dom: each one's tag, attributes
    // and parent's index, in document order), then how many are parsed now.
    setPage(spec) {
      const recs = spec.elements.map((e, k) => {
        const rec = newRec(e.tag, k);
        rec.parentK = e.parent;
        for (const [a, v] of Object.entries(e.attrs || {})) {
          rec.attrs.set(a, v);
          if (a === 'id') rec.id = v; else if (a === 'class') setClasses(rec, v);
        }
        return rec;
      });
      const ids = new Map();
      for (const rec of recs) {
        if (rec.parentK >= 0) recs[rec.parentK].pageKids.push(rec.k);
        if (rec.id) { if (!ids.has(rec.id)) ids.set(rec.id, []); ids.get(rec.id).push(rec.k); }
      }
      const end = new Array(recs.length);
      for (let k = recs.length - 1; k >= 0; k--) {
        const kids = recs[k].pageKids;
        end[k] = kids.length ? end[kids[kids.length - 1]] : k + 1;
      }
      page = { recs, ids, end, html: spec.html, head: spec.head, body: spec.body };
      parsedUpTo = 0;
    },
    parsed(n) { if (typeof n === 'number' && n > parsedUpTo) parsedUpTo = n; },
    parsedAll() { parsedUpTo = Infinity; },
    // The live listeners for DOMContentLoaded (document's, then window's, as
    // the event bubbles) or load (window's, then window.onload), in order.
    readyListeners(type) {
      const out = [];
      for (const target of (type === 'DOMContentLoaded' ? ['document', 'window'] : ['window'])) {
        for (const r of readyListeners) if (r.target === target && r.type === type) out.push(r);
      }
      if (type === 'load' && typeof g.onload === 'function') {
        out.push({ target: 'window', type, fn: g.onload, by: 'window.onload', stack: '', removed: false });
      }
      return out;
    },
    fire(r) {
      const target = r.target === 'window' ? g : g.document;
      const event = new Event(r.type, { bubbles: r.type === 'DOMContentLoaded', target: g.document, currentTarget: target });
      if (typeof r.fn === 'function') r.fn.call(target, event);
      else if (r.fn && typeof r.fn.handleEvent === 'function') r.fn.handleEvent(event);
    },
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
const scripts = page.scripts || [];
const tick = () => new Promise((resolve) => setImmediate(resolve));
// The definer past the last script: the DOMContentLoaded and load handlers.
const HANDLERS = '__HANDLERS__';
const named = (i) => (i < scripts.length ? scripts[i].name : HANDLERS);
// Runs nothing, so a microtask queued by a context function the driver
// called (a handler, a timer) runs now: a vm context with microtaskMode
// 'afterEvaluate' runs its microtasks only after code it evaluates.
const CHECKPOINT = new vm.Script('void 0', { filename: 'load-order-checkpoint.js' });

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
  if (page.dom) stub.setPage(page.dom);
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

let current = -1;     // the script running now; pass 2 charges every read to it
let inTimer = false;  // running one of its zero-delay timers
let sink = null;      // where a promise rejected now is filed: { list, script, phase }
process.on('unhandledRejection', (reason) => {
  if (sink) sink.list.push(Object.assign({ script: sink.script, phase: sink.phase }, describe(reason, 'promise')));
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

// Loads script i over the page parsed above its tag, waits a turn so a
// promise it rejected is reported while it is still the script charged, then
// runs the zero-delay timers it queued.
async function load(env, i, errors, diagnostics) {
  current = i;
  sink = { list: errors, script: scripts[i].name, phase: 'promise' };
  env.stub.running(scripts[i].name);
  env.stub.parsed(scripts[i].dom_at);  // the page above its tag
  runOne(env, i, errors);
  await tick();
  await fireTimers(env, i, diagnostics);
  current = -1;
  sink = null;
}

const TIMER_ROUNDS = 3;  // a script's own zero-delay timers, then two rounds of the ones they queue
const TIMER_CAP = 100;   // timers run after one script, at most
// Runs the zero-delay timers script i queued, as a browser may before the
// next script loads, each charged to script i (with the microtasks it
// queues). A throw in one is a diagnostic, not a load error.
async function fireTimers(env, i, diagnostics) {
  let fired = 0;
  for (let round = 0; round < TIMER_ROUNDS; round++) {
    const batch = env.stub.takeTimers();
    if (!batch.length) break;
    sink = { list: diagnostics, script: scripts[i].name, phase: 'timer' };
    for (const t of batch.slice(0, TIMER_CAP - fired)) {
      fired += 1;
      inTimer = true;
      try { t.fn.apply(undefined, t.args); } catch (e) {
        diagnostics.push(Object.assign({ script: scripts[i].name, phase: 'timer' }, describe(e, 'run')));
      }
      CHECKPOINT.runInContext(env.ctx);
      inTimer = false;
    }
    await tick();
  }
  env.stub.takeTimers();  // past the caps: never run
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
// The names V8 is asked about (resolvable below): every name a const / let /
// class at the source's top level declares. Each declarator of a statement
// (`let a = 1, b = 2;`), every name in a destructuring pattern (a default
// value's names with them: an extra name costs only a probe), and a class's
// name. The source is read as tokens, so a comma or bracket inside a string,
// template literal (its ${...} too), comment or regular expression starts no
// declarator. Where the scan can still go wrong, a later declarator is missed:
// a '/' is taken for a regular expression only where an expression may start
// (after a punctuator other than ) ] }, or a keyword such as return: the usual
// rule of thumb); a line break ends a declaration unless the line before it
// ends, or the next begins, with an operator, a comma or a bracket (automatic
// semicolon insertion, roughly); a declaration is followed for at most
// MAX_DECLARATION_TOKENS tokens; and only plain ASCII names are taken.
const MAX_DECLARATION_TOKENS = 20000;
const REGEX_AFTER_WORD = new Set(['return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void', 'throw',
                                  'case', 'do', 'else', 'yield', 'await']);
const isIdStart = (c) => (c >= 97 && c <= 122) || (c >= 65 && c <= 90) || c === 36 || c === 95 || c > 127;
const isIdPart = (c) => isIdStart(c) || (c >= 48 && c <= 57);
const isLineBreak = (c) => c === 10 || c === 13 || c === 0x2028 || c === 0x2029;
const isBlank = (c) => c === 32 || c === 9 || c === 11 || c === 12 || c === 0xa0 || c === 0xfeff;
// Reads src from i as tokens ({t: 'id' | 'p' (one punctuator character) |
// 'lit', v, nl: a line break before it, s / e: where it starts and ends in
// src}) into toks (null: only skip them), to the end, or with closeBrace to
// just past the } that closes a ${. Returns where it stopped.
function lexInto(src, i, toks, closeBrace) {
  const n = src.length;
  let depth = 0;
  let nl = false;
  let prev = null;
  const push = (t, v, s, e) => { prev = { t, v, nl, s, e }; if (toks) toks.push(prev); nl = false; };
  while (i < n) {
    const c = src.charCodeAt(i);
    const s = i;
    if (isLineBreak(c)) { nl = true; i += 1; continue; }
    if (isBlank(c)) { i += 1; continue; }
    if (c === 47) {  // '/'
      const d = src.charCodeAt(i + 1);
      if (d === 47) { while (i < n && !isLineBreak(src.charCodeAt(i))) i += 1; continue; }
      if (d === 42) {
        const close = src.indexOf('*/', i + 2);
        const end = close < 0 ? n : close + 2;
        for (let j = i; j < end; j++) if (isLineBreak(src.charCodeAt(j))) { nl = true; break; }
        i = end;
        continue;
      }
      if (!prev || (prev.t === 'p' && !')]}'.includes(prev.v)) || (prev.t === 'id' && REGEX_AFTER_WORD.has(prev.v))) {
        i = skipRegex(src, i);
        push('lit', '', s, i);
        continue;
      }
    }
    if (c === 39 || c === 34) { i = skipQuoted(src, i); push('lit', '', s, i); continue; }
    if (c === 96) { i = skipTemplate(src, i); push('lit', '', s, i); continue; }
    if (isIdStart(c)) {
      let j = i + 1;
      while (j < n && isIdPart(src.charCodeAt(j))) j += 1;
      push('id', src.slice(i, j), s, j);
      i = j;
      continue;
    }
    if (c >= 48 && c <= 57) {
      let j = i + 1;
      while (j < n && (isIdPart(src.charCodeAt(j)) || src.charCodeAt(j) === 46)) j += 1;
      push('lit', '', s, j);
      i = j;
      continue;
    }
    if (closeBrace) {
      if (c === 123) depth += 1;
      else if (c === 125 && depth-- === 0) return i + 1;
    }
    push('p', src[i], s, i + 1);
    i += 1;
  }
  return n;
}
function skipQuoted(src, i) {
  const q = src.charCodeAt(i);
  for (let j = i + 1; j < src.length; j++) {
    const c = src.charCodeAt(j);
    if (c === 92) { j += 1; continue; }
    if (c === q) return j + 1;
    if (c === 10 || c === 13) return j;  // never closed: its line ends it
  }
  return src.length;
}
function skipTemplate(src, i) {
  for (let j = i + 1; j < src.length; j++) {
    const c = src.charCodeAt(j);
    if (c === 92) { j += 1; continue; }
    if (c === 96) return j + 1;
    if (c === 36 && src.charCodeAt(j + 1) === 123) j = lexInto(src, j + 2, null, true) - 1;
  }
  return src.length;
}
function skipRegex(src, i) {
  let inClass = false;
  for (let j = i + 1; j < src.length; j++) {
    const c = src.charCodeAt(j);
    if (c === 92) { j += 1; continue; }
    if (c === 10 || c === 13) return j;  // no closing '/' on its line: not one after all
    if (inClass) { if (c === 93) inClass = false; continue; }
    if (c === 91) { inClass = true; continue; }
    if (c === 47) { j += 1; while (j < src.length && isIdPart(src.charCodeAt(j))) j += 1; return j; }
  }
  return src.length;
}
// After these a line break doesn't end a declaration, nor before these: the
// expression goes on.
const GOES_ON_AFTER = new Set([',', '=', '+', '-', '*', '/', '%', '&', '|', '^', '!', '~', '?', ':', '<', '>', '.', '(', '[', '{']);
const GOES_ON_BEFORE = new Set([',', '=', '+', '-', '*', '/', '%', '&', '|', '^', '?', ':', '<', '>', '.', '(', '[', ')', ']', '}']);
// The names a const / let starting at toks[k] declares, one per declarator.
// Returns where its statement ends in the source (just past its last token,
// its ';' included), or -1 when it is not a declaration.
function declarators(toks, k, add) {
  let depth = 0;
  let binding = true;  // the next token starts a declarator
  const stop = Math.min(toks.length, k + MAX_DECLARATION_TOKENS);
  for (; k < stop; k++) {
    const t = toks[k];
    if (binding) {
      binding = false;
      if (t.t === 'id') { add(t.v); continue; }
      if (t.t === 'p' && (t.v === '[' || t.v === '{')) {  // a destructuring pattern: every name in it
        for (let d = 0; k < stop; k++) {
          const u = toks[k];
          if (u.t === 'p' && '([{'.includes(u.v)) d += 1;
          else if (u.t === 'p' && ')]}'.includes(u.v)) { if (--d === 0) break; }
          else if (u.t === 'id') add(u.v);
        }
        continue;
      }
      return -1;  // not a declaration (`let` as a name)
    }
    if (t.nl && depth === 0) {
      const p = toks[k - 1];
      if (!(p.t === 'p' && GOES_ON_AFTER.has(p.v)) && !(t.t === 'p' && GOES_ON_BEFORE.has(t.v))) return p.e;
    }
    if (t.t !== 'p') continue;
    if ('([{'.includes(t.v)) depth += 1;
    else if (')]}'.includes(t.v)) { if (--depth < 0) return toks[k - 1].e; }
    else if (depth === 0 && t.v === ';') return t.e;
    else if (depth === 0 && t.v === ',') binding = true;
  }
  return toks[Math.min(k, toks.length) - 1].e;
}
// Only a declaration outside every bracket can be top-level, so only those
// are probed (probing every name declared anywhere took most of a load).
// If the script's brackets don't balance as read, the scan has misread
// something, and every declaration's names are probed instead. Also notes
// where the const / let statement declaring each top-level name starts and
// ends in the source (spans: name -> [start, end)), so a script's own read of
// a name can be placed inside its declaration or not (none when unbalanced).
function declarations(src) {
  const top = new Set();
  const all = new Set();
  const spans = new Map();
  const ok = (n) => /^[A-Za-z_$][\w$]*$/.test(n) && !RESERVED.has(n) && !n.startsWith('__fccProbe');
  const toks = [];
  lexInto(src, 0, toks, false);
  const open = [];  // the brackets open here, innermost last
  let balanced = true;
  for (let k = 0; k < toks.length; k++) {
    const t = toks[k];
    if (t.t === 'p') {
      const closes = ')]}'.indexOf(t.v);
      if ('([{'.includes(t.v)) open.push(t.v);
      else if (closes >= 0 && open.pop() !== '([{'[closes]) balanced = false;
      continue;
    }
    if (t.t !== 'id' || (t.v !== 'const' && t.v !== 'let' && t.v !== 'class')) continue;
    const before = toks[k - 1];
    if (before && before.t === 'p' && before.v === '.') continue;  // a property named so
    const atTop = open.length === 0;
    const names = [];
    const add = (n) => { if (ok(n)) { all.add(n); if (atTop) { top.add(n); names.push(n); } } };
    if (t.v === 'class') {
      const next = toks[k + 1];
      if (next && next.t === 'id' && next.v !== 'extends') add(next.v);
      continue;
    }
    const end = declarators(toks, k + 1, add);
    if (end >= 0) for (const n of names) if (!spans.has(n)) spans.set(n, [t.s, end]);
  }
  const sure = balanced && open.length === 0;
  return { names: sure ? top : all, spans: sure ? spans : new Map() };
}
const declaredNames = (src) => declarations(src).names;
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
  const diagnostics = [];  // throws the stub can't vouch for: in a zero-delay timer or a DOMContentLoaded / load handler
  const definers = new Map();
  const lexical = new Set();
  const onWindowLater = new Map();  // a top-level const / let name a later script also sets on window
  const handlerOf = new Map();      // a name the handlers put on window -> the handler that did
  const stubNames = new Set(Object.getOwnPropertyNames(env.sandbox));
  const overlaps = [];
  const overlapping = new Set();
  // Files the window names that appeared between two snapshots under definer
  // i; returns the ones it filed.
  const fileNew = (before, after, i) => {
    const filed = [];
    for (const [name, value] of after) {
      if (!before.has(name)) {
        if (!definers.has(name)) { definers.set(name, i); filed.push(name); }
        else if (lexical.has(name) && !onWindowLater.has(name)) { onWindowLater.set(name, i); filed.push(name); }
      } else if (stubNames.has(name) && !Object.is(before.get(name), value) && !overlapping.has(name)) {
        overlapping.add(name);
        overlaps.push({ name, script: named(i), how: 'sets it on window' });
      }
    }
    return filed;
  };
  const spans = [];  // per script: where each top-level const / let name's declaration is
  let before = ownValues(env.sandbox);
  for (let i = 0; i < scripts.length; i++) {
    const src = sources[i];
    const declared = typeof src === 'string' ? declarations(src) : { names: new Set(), spans: new Map() };
    const names = declared.names;
    spans.push(declared.spans);
    const resolvedBefore = resolvable(env, names);
    await load(env, i, errors, diagnostics);
    const after = ownValues(env.sandbox);
    fileNew(before, after, i);
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
  // The DOMContentLoaded handlers, then the load ones, as the browser fires
  // them once every script has loaded: a name only they define is defined
  // after every script (definer HANDLERS, past the last). A throw in one is a
  // diagnostic, not a load error (they run against a stub that can't model
  // the page they would see), and what it defined before it threw stays.
  const H = scripts.length;
  env.stub.running(HANDLERS);
  env.stub.parsedAll();  // the whole page is parsed by DOMContentLoaded
  for (const [state, type] of [['interactive', 'DOMContentLoaded'], ['complete', 'load']]) {
    env.stub.readyState(state);
    for (const r of env.stub.readyListeners(type)) {
      if (r.removed) continue;
      const where = `the ${type} handler added at ${pageFrame(framesOf(r.stack)) || r.by}`;
      sink = { list: diagnostics, script: where, phase: 'handler' };
      try { env.stub.fire(r); } catch (e) { diagnostics.push(Object.assign({ script: where, phase: 'handler' }, describe(e, 'run'))); }
      CHECKPOINT.runInContext(env.ctx);
      await tick();
      sink = null;
      const after = ownValues(env.sandbox);
      for (const name of fileNew(before, after, H)) handlerOf.set(name, where);
      before = after;
    }
  }
  return { errors, diagnostics, definers, lexical, onWindowLater, handlerOf, overlaps, spans };
}

// Pass 2: every defined name planted on window, each read charged to the
// script running when it happens, with the line it was read at. A script's
// read of a name it defines itself also keeps the outermost frame of the
// page's own code under it (the whole stack is taken for those), which says
// whether the read was made while the statement declaring the name ran.
async function pass2(definers) {
  const env = freshContext();
  const errors = [];
  const reads = [];
  for (const [name] of definers) {
    if (Object.prototype.hasOwnProperty.call(env.sandbox, name)) continue;
    Object.defineProperty(env.sandbox, name, {
      configurable: true, enumerable: false,
      get() {
        if (current < 0) return undefined;
        const own = definers.get(name) === current;
        const limit = Error.stackTraceLimit;
        if (own) Error.stackTraceLimit = Infinity;
        const frames = framesOf(new Error().stack).filter((f) => PAGE_FILES.has(frameFile(f)));
        Error.stackTraceLimit = limit;
        reads.push([name, current, frames[0] || '', inTimer, own ? frames[frames.length - 1] || '' : '']);
        return undefined;
      },
      set(value) { Object.defineProperty(env.sandbox, name, { value, writable: true, configurable: true, enumerable: true }); },
    });
  }
  for (let i = 0; i < scripts.length; i++) await load(env, i, errors, []);
  return { errors, reads };
}

// Where offset `at` of script s's source is in its stack frames: the line
// (lineOffset added) and the column, both from 1 (columnOffset added on its
// first line only, as V8 does).
function lineCol(src, at, s) {
  let line = 0;
  let start = 0;
  for (let j = 0; j < at; j++) {
    const c = src.charCodeAt(j);
    if (c === 10 || c === 0x2028 || c === 0x2029 || (c === 13 && src.charCodeAt(j + 1) !== 10)) { line += 1; start = j + 1; }
  }
  return [line + 1 + (s.lineOffset || 0), at - start + 1 + (line === 0 ? (s.columnOffset || 0) : 0)];
}
// Whether a read of name by script i was made while the top-level statement
// declaring it ran: the outermost frame of the page's own code under the read
// (the script's top-level code, or a timer) sits inside that statement, and it
// wasn't a timer's. So `const { X } = window;`, `let X = window.X || null;`
// and `const X = (() => window.X)();` are; `X();` on a later line, calling a
// function the declaration made, and a read on a later line are not.
function inItsDeclaration(spans, i, name, outer, timer) {
  const s = scripts[i];
  const src = sources[i];
  const span = spans[i] && spans[i].get(name);
  const m = /\(?([^()]+?):(\d+):(\d+)\)?$/.exec(outer || '');
  if (timer || !span || !m || typeof src !== 'string' || m[1] !== (s.filename || s.name)) return false;
  const at = [Number(m[2]), Number(m[3])];
  const before = (a, b) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);
  return !before(at, lineCol(src, span[0], s)) && before(at, lineCol(src, span[1], s));
}

(async () => {
  if (page.declared) {  // the declaration scan alone, on the sources given (its own test)
    console.log('__RESULT_MARK__' + JSON.stringify(page.declared.map((src) => [...declaredNames(src)].sort())));
    return;
  }
  const one = await pass1();
  const two = await pass2(one.definers);
  const early = [];
  const late = [];
  const seen = new Set();
  let selfReads = 0;
  for (const [name, reader, at, timer, outer] of two.reads) {
    let definer = one.definers.get(name);
    let lexical = one.lexical.has(name);
    const own = reader === definer;
    let alias = false;
    let taken = false;
    if (own) {
      // A script reading a name it defines on window reads its own name.
      // One it declares as a top-level const / let / class is different: its
      // bare reads hit its own binding, so a read that reaches the planted
      // name is a window.X read, and X is never a window property unless a
      // later script sets it there. With no such script, the read is always
      // undefined: a late read below (reader === definer). With one, it is
      // early against that script, and if it was made while X's declaration
      // ran, that declaration took an alias of window.X, undefined when taken
      // (`const { X } = window;`).
      if (!lexical) { selfReads += 1; continue; }
      const setter = one.onWindowLater.get(name);
      if (setter !== undefined) {
        if (reader >= setter) { selfReads += 1; continue; }
        definer = setter;
        lexical = false;
        alias = true;
        taken = inItsDeclaration(one.spans, reader, name, outer, timer);
      }
    }
    // Past its definer, a planted name is read only off window, and only one
    // that is a top-level const / let / class there is still planted. If a
    // later script sets it on window, the read is early against that script.
    if (reader > definer) {
      if (!lexical) continue;
      const setter = one.onWindowLater.get(name);
      if (setter !== undefined) {
        if (reader >= setter) { selfReads += 1; continue; }
        definer = setter;
        lexical = false;
      }
    }
    const key = reader + ' ' + name;
    if (seen.has(key)) continue;
    seen.add(key);
    const read = { reader: named(reader), name, definer: named(definer), lexical, alias, taken, own, at, timer,
                   handler: definer === scripts.length ? (one.handlerOf.get(name) || '') : '' };
    (reader < definer ? early : late).push(read);
  }
  const definers = {};
  for (const [name, i] of one.definers) definers[name] = named(i);
  console.log('__RESULT_MARK__' + JSON.stringify({
    order: scripts.map((s) => s.name),
    errors: one.errors,
    errors_pass2: two.errors,
    diagnostics: one.diagnostics,
    early_reads: early,
    late_reads: late,
    reads_recorded: two.reads.length,
    self_reads: selfReads,
    definers,
    lexical: [...one.lexical],
    handler_definers: Object.fromEntries(one.handlerOf),
    stub_overlaps: one.overlaps,
  }));
})().catch((e) => { console.error((e && e.stack) || e); process.exitCode = 3; });
""".replace("__RESULT_MARK__", RESULT_MARK).replace("__HANDLERS__", HANDLERS)


def _run_driver(payload: dict, work: Path, label: str):
    page = work / f"{label}.json"
    page.write_text(json.dumps(payload), encoding="utf-8")
    driver = work / "load_order_driver.js"
    driver.write_text(DRIVER_JS, encoding="utf-8")
    proc = subprocess.run([NODE, str(driver), str(page)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and lines, (
        f"the load-order driver failed (rc={proc.returncode})\n"
        f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}")
    return json.loads(lines[-1][len(RESULT_MARK):])


def run_page(scripts: list, work: Path, label: str, stub: str = STUB_JS) -> dict:
    """Loads `scripts` in order under node, both passes, and returns the driver's result."""
    doms = {id(s["dom"]): s["dom"] for s in scripts if s.get("dom") is not None}
    assert len(doms) <= 1, "these scripts come from more than one page (read_page_scripts): run one page at a time"
    return _run_driver({"stub": stub, "dom": next(iter(doms.values()), None),
                        "scripts": [{k: v for k, v in s.items() if k != "dom"} for s in scripts]}, work, label)


def declared_names(sources: list, work: Path) -> list:
    """For each source, the names the declaration scan (DRIVER_JS's declaredNames) lists."""
    return _run_driver({"stub": STUB_JS, "declared": sources}, work, "declared-names")


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
        name, reader, definer = r["name"], r["reader"], r["definer"]
        if r.get("alias"):  # the reader declares the name itself, so the read reached it off window
            text = f"  - {reader} reads window.{name} while it loads{_at(r)}, but {definer} sets window.{name} later."
        else:
            text = f"  - {reader} reads {name} while it loads{_at(r)}, but {name} is defined later, by {definer}."
        if r.get("timer"):
            text += (" (In a zero-delay timer it queued: a browser may run that while it waits for a later "
                     "script, so a timer is no fix.)")
        if r.get("handler"):
            text = (f"{text[:-1]}: {r['handler']} sets it, and those handlers run once every script has loaded. "
                    f"Define {name} while its script loads, outside the handler, or read it only once the "
                    f"handlers have run.")
        ran = "those handlers have run" if r.get("handler") else f"{definer} has run"
        if r.get("alias") and r.get("taken"):
            text += (f" ({reader} declares {name} itself, as a top-level const / let taken from window.{name} "
                     f"while that declaration runs: the alias is undefined when it is taken. Read "
                     f"window.{name} where it is used instead, or take it from window only once {ran}.)")
        elif r.get("alias"):
            text += (f" ({reader} declares {name} itself and reads window.{name} before {definer} sets it: read "
                     f"the bare {name} while it loads, or window.{name} only once {ran}.)")
        if r["lexical"]:
            text += (f" (If that read is window.{r['name']}, loading earlier won't help: {r['name']} is a "
                     f"top-level const / let / class there, never a window property. Read it bare, or have "
                     f"{r['definer']} also set window.{r['name']}.)")
        out.append(text)
    return out


def diagnostic_problems(result: dict) -> list:
    """The throws in the run's diagnostics: a DOMContentLoaded / load handler
    or a zero-delay timer (a script's, or one a handler queued) that stopped
    part way."""
    out = []
    for d in result.get("diagnostics", []):
        where = d["script"]
        if d["phase"] == "timer" and not where.startswith("a zero-delay timer"):
            where = f"a zero-delay timer {where} queued while it loaded"
        text = f"  - {where} threw: {d['message']}"
        if d.get("at"):
            text += f"\n      at {d['at']}"
        out.append(text)
    return out


# What a throw in a handler or a zero-delay timer costs, and what to do.
_UNJUDGED = (
    "Until each runs to its end, every name it sets after the throwing line goes unjudged: it never enters the "
    "definer map, so a load-time read of it is never reported. Most often the stub lacks a browser API the code "
    "uses (an undefined property of window, document or an element): add a plain stand-in for it that does "
    "nothing to STUB_JS in tests/test_load_order_canary_js.py, never one for an FCC name. If it would throw in "
    "a browser too, it is a real error: fix the handler or timer.")


def _thrown(result: dict) -> str:
    """For a message about a name a handler defines: what threw in this run."""
    problems = diagnostic_problems(result)
    if not problems:
        return "No handler or zero-delay timer threw in this run."
    return "These threw in this run, and a name set after the throw is never defined:\n" + "\n".join(problems)


def late_read_problems(result: dict) -> list:
    out = []
    for r in result["late_reads"]:
        if r.get("own"):  # the script declares the name itself
            out.append(f"  - {r['reader']} reads window.{r['name']} while it loads{_at(r)}, but {r['name']} is its "
                       f"own top-level const / let / class, which never becomes a window property, so the read is "
                       f"always undefined. Read it bare ({r['name']}), or set window.{r['name']} = {r['name']} "
                       f"before that read.")
            continue
        out.append(f"  - {r['reader']} reads window.{r['name']} while it loads{_at(r)}, but {r['name']} is a "
                   f"top-level const / let / class in {r['definer']}, which never becomes a window property, so "
                   f"the read is always undefined. Read it bare ({r['name']}), or have {r['definer']} also set "
                   f"window.{r['name']}.")
    return out


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
        "error (it would throw in a browser too: fix the script). A TypeError on null from document.body or an "
        "element lookup is real: the stub's DOM holds the templates' elements by position, so the script ran in "
        "<head> or above that element; look it up later (on DOMContentLoaded) or move the <script> below it. "
        "Until it loads, the early-read check can't see past the throw.")


def test_every_inline_script_parses_with_its_server_values_as_null(page_scripts, page_load):
    """The canary runs an inline script with each {{ ... }} replaced by null;
    that must leave it valid JavaScript, or nothing after the broken line is
    checked. (Today the last script's server values are in `= {{ ... }};`
    and inside a string, both fine as null.)"""
    inline = [s for s in page_scripts if s["kind"] == "inline"]
    assert any("= null;" in s["code"] for s in inline), (
        "No inline script on the page assigns a {{ ... }} server value any more, so this check guards "
        "nothing as written: point the line above at an inline script that still holds one, or drop it.")
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
        "click; a zero-delay timer is no fix), or load the defining script earlier in "
        "templates/components/scripts.html (a line about a name the script declares itself says what fits "
        "it). If the early read "
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


def test_every_handler_and_zero_delay_timer_runs_to_its_end(page_load):
    """A DOMContentLoaded / load handler or a zero-delay timer that throws
    against the stub isn't a load error (in a browser it would run later, on
    the page it would see), but it stops there: every name it would set after
    the throwing line never enters the definer map, so a load-time read of
    that name goes unjudged (review finding ra-3). On today's page every one
    runs to its end."""
    problems = diagnostic_problems(page_load)
    assert not problems, (
        "These DOMContentLoaded / load handlers or zero-delay timers threw while the canary ran them:\n"
        + "\n".join(problems) + "\n" + _UNJUDGED)


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
    # const + window.showToast = ...
    assert d.get("showToast") == "js/modules/inv_core.js", (_pinned("showToast", "js/modules/inv_core.js"),
                                                            d.get("showToast"))
    # window.X = ... in an IIFE
    assert d.get("openSlotPicker") == "js/modules/slot_picker.js", (
        _pinned("openSlotPicker", "js/modules/slot_picker.js"), d.get("openSlotPicker"))
    # registerShortcut is first defined by the queueing shim near the top of
    # scripts.html, not by shortcuts_registry.js, which replaces it later.
    shim = [s["name"] for s in page_scripts
            if s["kind"] == "inline" and "window.__pendingShortcuts = []" in s["code"]]
    assert len(shim) == 1 and shim[0].startswith(SCRIPTS_HTML + ":"), (
        f"This proof looks for the shortcut queueing shim (`window.__pendingShortcuts = []`) in one inline "
        f"script of {SCRIPTS_HTML}: if it moved or changed, point the proof at it.", shim)
    assert d.get("registerShortcut") == shim[0], (_pinned("registerShortcut", f"the queueing shim, {shim[0]}"),
                                                  d.get("registerShortcut"))
    # A top-level let (never on window), and an indented const in an inline
    # script, which a column-0 search for declarations would miss.
    assert d.get("state") == "js/modules/inv_core.js" and "state" in lexical, (
        _pinned("state", "js/modules/inv_core.js, as a top-level let"), d.get("state"))
    tail = [s["name"] for s in page_scripts if s["kind"] == "inline" and "const SPOOLMAN_URL" in s["code"]]
    assert len(tail) == 1 and tail[0].startswith("templates/dashboard.html:"), (
        _pinned("SPOOLMAN_URL", "an inline script of templates/dashboard.html, as a const"), tail)
    assert d.get("SPOOLMAN_URL") == tail[0] and "SPOOLMAN_URL" in lexical, (
        _pinned("SPOOLMAN_URL", f"{tail[0]}, as a const"), d.get("SPOOLMAN_URL"))
    # A name a DOMContentLoaded handler defines (scripts.html's last script
    # sets these two in its handler) is defined after every script.
    # (A string message: pytest cuts a tuple's repr short, and this one must
    # show what threw.)
    for name in ("personMayPress", "sendInScanOrder"):
        assert d.get(name) == HANDLERS, (
            f"{_thrown(page_load)}\n{_pinned(name, 'a DOMContentLoaded handler')} In this run its definer is "
            f"{d.get(name)!r}.")
        assert page_load["handler_definers"][name].startswith(
            f"the DOMContentLoaded handler added at {SCRIPTS_HTML}:"), (
            f"{_thrown(page_load)}\n{_pinned(name, f'the DOMContentLoaded handler in {SCRIPTS_HTML}')} In this "
            f"run it is set by {page_load['handler_definers'][name]!r}.")
    # Each CDN library defines what the real bundle defines.
    for part, names in CDN_GLOBALS.items():
        cdn = [s["name"] for s in page_scripts if s["kind"] == "cdn" and part in s["name"]]
        assert len(cdn) == 1, (
            f"CDN_GLOBALS lists {part!r}, which names {len(cdn)} of the page's CDN scripts: if the page no longer "
            f"loads that library, take it out of CDN_GLOBALS (and its stand-ins out of STUB_JS).", cdn)
        assert {n: d.get(n) for n in names} == {n: cdn[0] for n in names}, (
            f"{cdn[0]} should define {list(names)} (CDN_GLOBALS): a stand-in in STUB_JS is missing, or a page "
            f"script defines one of them first.", {n: d.get(n) for n in names})
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
    assert _early(result) == {(fake, "openSlotPicker", "js/modules/slot_picker.js")}, (
        _pinned("openSlotPicker", "js/modules/slot_picker.js"), result["early_reads"])
    assert result["early_reads"][0]["at"].startswith(fake + ":1:"), result["early_reads"]
    problems = early_read_problems(result, ALLOWED_EARLY_READS)
    assert len(problems) == 1 and fake in problems[0] and "js/modules/slot_picker.js" in problems[0], problems
    assert result["errors"] == [], result["errors"]


def test_a_bare_typeof_before_its_definer_is_reported(page_scripts, load_dir):
    fake = "FAKE script before inv_core.js testing typeof processScan"
    result = run_page(with_fake(page_scripts, "if (typeof processScan === 'function') {}", fake,
                                before="js/modules/inv_core.js"), load_dir, "fake-typeof")
    assert _early(result) == {(fake, "processScan", "js/modules/inv_cmd.js")}, (
        _pinned("processScan", "js/modules/inv_cmd.js"), result["early_reads"])
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
    assert _early(before) == {(fake, "mountOverlay", "js/modules/overlay_mount.js")}, (
        _pinned("mountOverlay", "js/modules/overlay_mount.js"), before["early_reads"])


def test_moving_inv_core_late_is_reported(page_scripts, load_dir):
    """The real reorder: inv_core.js loaded just before titlebar_prefs.js."""
    result = run_page(with_moved(page_scripts, "js/modules/inv_core.js", before="js/modules/titlebar_prefs.js"),
                      load_dir, "inv-core-late")
    early = _early(result)
    readers = _pinned_readers("installFieldScanCapture and state (both inv_core.js's)",
                              ["js/modules/inv_stock.js", "js/modules/inv_loc_mgr.js"])
    assert ("js/modules/inv_stock.js", "installFieldScanCapture", "js/modules/inv_core.js") in early, (readers, early)
    assert ("js/modules/inv_loc_mgr.js", "state", "js/modules/inv_core.js") in early, (readers, early)
    at = {(r["reader"], r["name"]): r["at"] for r in result["early_reads"]}
    assert "(js/modules/inv_stock.js:" in at["js/modules/inv_stock.js", "installFieldScanCapture"], at
    assert at["js/modules/inv_loc_mgr.js", "state"].startswith("js/modules/inv_loc_mgr.js:"), at
    errors = [e for e in result["errors"] if e["script"] == "js/modules/inv_loc_mgr.js"]
    assert errors and errors[0]["message"] == "ReferenceError: state is not defined", (readers, result["errors"])
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
    assert {"js/modules/inv_cmd.js", "js/modules/inv_wizard.js"} <= readers, (
        _pinned_readers("registerShortcut", ["js/modules/inv_cmd.js", "js/modules/inv_wizard.js"]),
        result["early_reads"])
    assert {(r["name"], r["definer"]) for r in result["early_reads"]} == {
        ("registerShortcut", "js/modules/shortcuts_registry.js")}, (
        _pinned("registerShortcut (without the shim)", "js/modules/shortcuts_registry.js"), result["early_reads"])


def test_a_window_read_of_a_top_level_const_is_reported(page_scripts, load_dir):
    """`state` is a top-level let in inv_core.js: window.state is undefined
    however late it is read."""
    fake = "FAKE script after inv_core.js reading window.state"
    result = run_page(with_fake(page_scripts, "if (window.state) {}", fake, after="js/modules/inv_core.js"),
                      load_dir, "fake-window-lexical")
    assert [(r["reader"], r["name"], r["definer"]) for r in result["late_reads"]] == [
        (fake, "state", "js/modules/inv_core.js")], (
        _pinned("state", "js/modules/inv_core.js, as a top-level let"), result["late_reads"])
    assert result["early_reads"] == [], result["early_reads"]


def test_a_scripts_window_read_of_its_own_top_level_const_is_reported(page_scripts, load_dir):
    """A script's own window.X read of a top-level const / let / class it
    declares itself, when no later script sets window.X, is always undefined:
    the name never becomes a window property (review finding ra-2: it was
    counted as the script reading its own name, and never reported). The
    finding's own shape, a copy of inv_core.js reading window.state at its
    end, and fakes with names of their own: a let, a class, and a const read
    in a zero-delay timer the script queues."""
    module = "js/modules/inv_core.js"
    src = (STATIC / module).read_text(encoding="utf-8")
    assert re.search(r"^let state\b", src, re.M), (
        _pinned("state", f"{module}, as a top-level let"), "no top-level `let state` in it")
    copy = load_dir / "own_inv_core.js"
    copy.write_text(src + "\nif (window.state && window.state.heldSpools) { window.__fakeRestore = 1; }\n",
                    encoding="utf-8")
    page = [dict(s, file=str(copy)) if s["name"] == module else s for s in page_scripts]
    fakes = {
        "FAKE own let read off window": ("let fakeOwnLet = 1;\nif (window.fakeOwnLet) {}", "fakeOwnLet"),
        "FAKE own class read off window": ("class FakeOwnClass {}\nif (window.FakeOwnClass) {}", "FakeOwnClass"),
        "FAKE own const read off window in a zero-delay timer": (
            "const fakeOwnTimed = 1;\nsetTimeout(() => { if (window.fakeOwnTimed) {} }, 0);", "fakeOwnTimed"),
    }
    for fake, (code, _) in fakes.items():
        page = with_fake(page, code, fake, after="js/modules/titlebar_prefs.js")
    result = run_page(page, load_dir, "fake-own-lexical")
    expected = {(module, "state", module)} | {(fake, name, fake) for fake, (_, name) in fakes.items()}
    assert {(r["reader"], r["name"], r["definer"]) for r in result["late_reads"]} == expected, (
        _pinned("state", f"{module}, as a top-level let"), result["late_reads"])
    assert result["early_reads"] == [] and result["errors"] == [], result
    at = {r["name"]: r["at"] for r in result["late_reads"]}
    assert at["state"].startswith(module + ":"), at
    assert at["fakeOwnLet"].startswith("FAKE own let read off window:2:"), at
    problems = late_read_problems(result)
    assert len(problems) == 4, problems
    for p in problems:
        assert "its own top-level const / let / class" in p and "always undefined" in p, p
    words = [p for p in problems if " reads window.state " in p]
    assert len(words) == 1 and "Read it bare (state)" in words[0], problems


def test_a_window_read_before_a_later_script_puts_the_const_on_window_is_early(page_scripts, load_dir):
    """When a later script does set window.state, a window.state read before it
    is an early read against that script, not one that is always undefined."""
    reader = "FAKE script after inv_core.js reading window.state"
    setter = "FAKE script after it setting window.state = state"
    page = with_fake(page_scripts, "if (window.state) {}", reader, after="js/modules/inv_core.js")
    page = with_fake(page, "window.state = state;", setter, after=reader)
    result = run_page(page, load_dir, "fake-window-lexical-set-later")
    assert _early(result) == {(reader, "state", setter)}, (
        _pinned("state", "js/modules/inv_core.js, as a top-level let"), result["early_reads"])
    assert result["late_reads"] == [] and result["errors"] == [], result


def test_a_script_scope_alias_of_a_later_scripts_name_is_reported(page_scripts, load_dir):
    """`const { openSlotPicker } = window;` at the top of a script that loads
    before slot_picker.js leaves the alias undefined for good: the script
    declares the name itself, and read window.openSlotPicker before
    slot_picker.js put it there. Its own read is early against slot_picker.js,
    not a self-read (review finding r2-2)."""
    fake = "FAKE script before slot_picker.js aliasing openSlotPicker at script scope"
    result = run_page(with_fake(page_scripts, "const { openSlotPicker } = window;", fake,
                                before="js/modules/slot_picker.js"), load_dir, "fake-alias")
    assert _early(result) == {(fake, "openSlotPicker", "js/modules/slot_picker.js")}, (
        _pinned("openSlotPicker", "js/modules/slot_picker.js"), result["early_reads"])
    assert result["early_reads"][0]["at"].startswith(fake + ":1:"), result["early_reads"]
    problems = early_read_problems(result, ALLOWED_EARLY_READS)
    assert len(problems) == 1 and "declares openSlotPicker itself" in problems[0], problems
    assert "taken from window.openSlotPicker" in problems[0], problems
    assert result["errors"] == [] and result["late_reads"] == [], result


def test_an_own_read_of_a_name_a_later_script_puts_on_window_says_what_it_is(page_scripts, load_dir):
    """A script that declares X itself and reads window.X before a later
    script sets it reads too early either way, but what is true differs
    (review finding ra-6). Read while X's own declaration runs (destructuring,
    an initializer, an IIFE in one), it takes an alias of window.X that is
    undefined when it is taken; a later assignment may refresh it. Read
    anywhere else (the script's own value read back off window, a function it
    declares, called later), the bare X already holds the script's own value.
    Neither is fixed by loading the setter earlier: a setter that reads the
    script's binding (`window.X = X;`) would then throw."""
    setter = "FAKE setter after the readers"
    readers = {  # fake -> (code, name, read while its declaration runs)
        "FAKE own value read off window": (
            "let fakeShared = { ready: true };\nif (window.fakeShared && window.fakeShared.ready) {}",
            "fakeShared", False),
        "FAKE alias refreshed on DOMContentLoaded": (
            "let fakeAlias = window.fakeAlias;\n"
            "document.addEventListener('DOMContentLoaded', () => { fakeAlias = window.fakeAlias; });",
            "fakeAlias", True),
        "FAKE destructured alias": ("const { fakeDestructured } = window;", "fakeDestructured", True),
        "FAKE alias from an IIFE": ("const fakeIife = (() => window.fakeIife)();", "fakeIife", True),
        "FAKE function called later": ("const fakeLater = () => window.fakeLater;\nfakeLater();", "fakeLater", False),
    }
    page, last = page_scripts, "js/modules/titlebar_prefs.js"
    for fake, (code, _, _) in readers.items():
        page, last = with_fake(page, code, fake, after=last), fake
    page = with_fake(page, "window.fakeShared = fakeShared;\nwindow.fakeAlias = 1;\nwindow.fakeDestructured = 1;\n"
                           "window.fakeIife = 1;\nwindow.fakeLater = 1;", setter, after=last)
    result = run_page(page, load_dir, "fake-own-reads")
    assert _early(result) == {(fake, name, setter) for fake, (_, name, _) in readers.items()}, result["early_reads"]
    assert result["errors"] == [] and result["late_reads"] == [], result
    problems = {r["reader"]: p for r, p in zip(result["early_reads"], early_read_problems(result, {}))}
    for fake, (_, name, taken) in readers.items():
        p = problems[fake]
        assert f"reads window.{name} while it loads" in p and f"declares {name} itself" in p, p
        assert "for good" not in p and "earlier" not in p, p
        if taken:
            assert f"taken from window.{name}" in p and f"Read window.{name} where it is used" in p, p
        else:
            assert "taken from" not in p, p
            assert (f"read the bare {name} while it loads, or window.{name} only once {setter} has run" in p), p


def test_an_alias_in_a_real_module_is_reported(page_scripts, load_dir):
    """The finding's own shape, on a copy of inv_cmd.js (which loads before
    slot_picker.js): a script-scope `const { openSlotPicker } = window;` with
    its uses made bare. In a browser a Dryer Box or Printer-row scan would skip
    the slot picker for good, and its open would throw."""
    module, provider = "js/modules/inv_cmd.js", "js/modules/slot_picker.js"
    src = (STATIC / module).read_text(encoding="utf-8")
    assert "window.openSlotPicker" in src and _index(page_scripts, module) < _index(page_scripts, provider), (
        f"{module} no longer reads window.openSlotPicker, or no longer loads before {provider}: point this proof "
        f"at a module that reads a later script's window name.")
    copy = load_dir / "alias_inv_cmd.js"
    copy.write_text("const { openSlotPicker } = window;\n" + src.replace("window.openSlotPicker", "openSlotPicker"),
                    encoding="utf-8")
    page = [dict(s, file=str(copy)) if s["name"] == module else s for s in page_scripts]
    result = run_page(page, load_dir, "alias-inv-cmd")
    assert _early(result) == {(module, "openSlotPicker", provider)}, result["early_reads"]
    assert result["early_reads"][0]["at"].startswith(module + ":1:"), result["early_reads"]


def test_a_provider_moved_into_a_dom_ready_handler_is_reported(page_scripts, load_dir):
    """A copy of empty_weight_field.js that sets window.bindEmptyWeightField in
    a DOMContentLoaded handler instead of at load: inv_wizard.js, which binds
    the wizard's empty-weight field once while it loads, would then find
    nothing and bind nothing, silently (review findings r2-1 / r5-1). The
    handlers run once every script has loaded, so a name only a handler
    defines is defined after every script."""
    module, reader = "js/modules/empty_weight_field.js", "js/modules/inv_wizard.js"
    line = "    window.bindEmptyWeightField = bindEmptyWeightField;\n"
    src = (STATIC / module).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert src.count(line) == 1 and _index(page_scripts, module) < _index(page_scripts, reader), (
        f"{module} no longer sets window.bindEmptyWeightField at load in one line, or {reader} no longer loads "
        f"after it: point this proof at another provider whose name a later script reads while it loads.")
    copy = load_dir / "dcl_empty_weight_field.js"
    copy.write_text(src.replace(line, "    document.addEventListener('DOMContentLoaded', () => {\n"
                                      "        window.bindEmptyWeightField = bindEmptyWeightField;\n"
                                      "    });\n"), encoding="utf-8")
    page = [dict(s, file=str(copy)) if s["name"] == module else s for s in page_scripts]
    result = run_page(page, load_dir, "dcl-provider")
    assert _early(result) == {(reader, "bindEmptyWeightField", HANDLERS)}, result["early_reads"]
    read = result["early_reads"][0]
    assert f"{reader}:81:" in read["at"], (
        "inv_wizard.js reads window.bindEmptyWeightField on its line 81 today: if that line moved, update the "
        "line number here.", read)
    problems = early_read_problems(result, ALLOWED_EARLY_READS)
    assert len(problems) == 1 and HANDLERS in problems[0], problems
    assert f"the DOMContentLoaded handler added at {module}:" in problems[0], problems
    assert result["errors"] == [], result["errors"]


def test_a_name_only_a_handler_defines_is_defined_after_every_script(page_scripts, load_dir):
    """Fakes, each with a name of its own: a load-time read of personMayPress
    (scripts.html's last script defines it in its DOMContentLoaded handler) is
    early; a read inside a DOMContentLoaded handler is call time and stays
    quiet; a handler that throws is a diagnostic, not a load error, and the
    name it defined before it threw still counts; a window load listener is
    a handler too."""
    may_press = "FAKE before inv_core.js reading window.personMayPress at load"
    in_handler = "FAKE before inv_core.js reading window.openSlotPicker in a DOMContentLoaded handler"
    thrower = "FAKE after titlebar_prefs.js: a DOMContentLoaded handler that defines fakeReady, then throws"
    on_load = "FAKE after titlebar_prefs.js: a window load listener that defines fakeLoaded"
    reader = "FAKE before inv_core.js reading fakeReady and fakeLoaded at load"
    page = with_fake(page_scripts, "if (window.personMayPress) {}", may_press, before="js/modules/inv_core.js")
    page = with_fake(page, "document.addEventListener('DOMContentLoaded', () => { if (window.openSlotPicker) {} });",
                     in_handler, before="js/modules/inv_core.js")
    page = with_fake(page, "if (window.fakeReady || window.fakeLoaded) {}", reader, before="js/modules/inv_core.js")
    page = with_fake(page, "document.addEventListener('DOMContentLoaded', () => {\n"
                           "  window.fakeReady = function () {};\n"
                           "  null.boom;\n"
                           "});", thrower, after="js/modules/titlebar_prefs.js")
    page = with_fake(page, "window.addEventListener('load', function () { window.fakeLoaded = 1; });", on_load,
                     after=thrower)
    result = run_page(page, load_dir, "fake-handlers")
    assert _early(result) == {(may_press, "personMayPress", HANDLERS), (reader, "fakeReady", HANDLERS),
                              (reader, "fakeLoaded", HANDLERS)}, f"{_thrown(result)}\n{result['early_reads']}"
    assert result["errors"] == [], result["errors"]
    thrown = [d for d in result["diagnostics"] if d["phase"] == "handler" and thrower in d["script"]]
    assert len(thrown) == 1 and "TypeError" in thrown[0]["message"], result["diagnostics"]
    assert result["handler_definers"]["fakeLoaded"].startswith(f"the load handler added at {on_load}:1:"), (
        result["handler_definers"])


def test_a_handler_that_throws_against_the_stub_is_reported(page_scripts, load_dir):
    """scripts.html's last script defines personMayPress and sendInScanOrder
    in its DOMContentLoaded handler. An edit that calls, near the top of that
    handler, a browser API the stub lacks (window.visualViewport, which every
    browser FCC targets has) stops the handler there against the stub, and
    both names drop out of the definer map, so a load-time read of either
    would go unjudged (review finding ra-3). The real-page test reports it
    and says what to do, and the instrument test's handler proof shows what
    threw instead of blaming a module split."""
    opener = "document.addEventListener('DOMContentLoaded', () => {"
    target = [s for s in page_scripts if s["kind"] == "inline" and "window.personMayPress = personMayPress" in s["code"]]
    assert len(target) == 1 and target[0]["code"].count(opener) == 1, (
        _pinned("personMayPress", f"the DOMContentLoaded handler in {SCRIPTS_HTML}"), [s["name"] for s in target])
    # On the opener's own line, so every line keeps its number.
    edited = dict(target[0], code=target[0]["code"].replace(
        opener, opener + " window.visualViewport.addEventListener('resize', () => {});", 1))
    page = [edited if s is target[0] else s for s in page_scripts]
    result = run_page(page, load_dir, "handler-throws")
    assert result["errors"] == [], result["errors"]
    assert "personMayPress" not in result["definers"] and "sendInScanOrder" not in result["definers"], (
        "the handler threw before it set them, so neither may be defined", result["handler_definers"])
    problems = diagnostic_problems(result)
    assert len(problems) == 1 and f"the DOMContentLoaded handler added at {SCRIPTS_HTML}:" in problems[0], problems
    assert "TypeError" in problems[0], problems
    thrown = problems[0].splitlines()[0].strip()  # pytest indents a message's later lines
    with pytest.raises(AssertionError) as red:
        test_every_handler_and_zero_delay_timer_runs_to_its_end(result)
    assert thrown in str(red.value), str(red.value)
    assert "add a plain stand-in for it" in str(red.value) and "goes unjudged" in str(red.value), str(red.value)
    with pytest.raises(AssertionError) as red:
        test_the_instrument_sees_each_kind_of_definition(page, result)
    assert thrown in str(red.value), str(red.value)


def test_a_zero_delay_timer_queued_at_load_reads_at_load(page_scripts, load_dir):
    """`setTimeout(() => { if (window.X) {} }, 0)` is no fix for an early read:
    while the parser waits on the network for a later script (FCC sends every
    response no-store), the browser runs the timer, and X may not be there yet
    (review findings r2-7 / r5-6). Its read is charged to the script that
    queued it. And the timer model, on a fake with names of its own: a
    zero-delay timer or interval runs right after its script (an interval
    once), a timer one queues runs too, a cleared one never does, nor one with
    a delay; a throw in one is a diagnostic, not a load error."""
    reader = "FAKE before inv_core.js reading window.openSlotPicker in a zero-delay timer"
    model = "FAKE after titlebar_prefs.js queueing timers"
    page = with_fake(page_scripts, "setTimeout(() => { if (window.openSlotPicker) {} }, 0);", reader,
                     before="js/modules/inv_core.js")
    page = with_fake(page, "(function () {\n"
                           "  setTimeout(function () { null.boom; });\n"
                           "  clearTimeout(setTimeout(() => { window.fakeCleared = 1; }, 0));\n"
                           "  setInterval(() => { window.fakeInterval = 1; }, 0);\n"
                           "  setTimeout(() => { setTimeout(() => { window.fakeNested = 1; }); }, -5);\n"
                           "  setTimeout(() => { window.fakeDelayed = 1; }, 10);\n"
                           "})();", model, after="js/modules/titlebar_prefs.js")
    result = run_page(page, load_dir, "fake-timers")
    assert _early(result) == {(reader, "openSlotPicker", "js/modules/slot_picker.js")}, (
        _pinned("openSlotPicker", "js/modules/slot_picker.js"), result["early_reads"])
    assert result["early_reads"][0]["at"].startswith(reader + ":1:"), result["early_reads"]
    problems = early_read_problems(result, ALLOWED_EARLY_READS)
    assert len(problems) == 1 and "a timer is no fix" in problems[0], problems
    assert result["errors"] == [], result["errors"]
    defined = result["definers"]
    assert defined.get("fakeInterval") == model and defined.get("fakeNested") == model, defined
    assert "fakeCleared" not in defined and "fakeDelayed" not in defined, defined
    thrown = [d for d in result["diagnostics"] if d["phase"] == "timer"]
    assert len(thrown) == 1 and thrown[0]["script"] == model and "TypeError" in thrown[0]["message"], (
        result["diagnostics"])


def test_titlebar_fit_takes_its_real_load_path(page_scripts, load_dir):
    """titlebar_fit.js, the one FCC module before inv_core.js, fits the title
    bar while it loads: the bar sits above its <script>. With a DOM that never
    found the bar, start() returned at once and a read there of a later
    script's name was never seen (review finding r2-3). A copy whose fit()
    reads, at the top of its try (the reviewer's mutation), window.
    fccTitleBarPrefs (titlebar_prefs.js), and at its last line window.
    fccTextSize (text_size.js): the last is reached only if matchMedia said
    one line, floor() read the count placeholders and natural() measured the
    title in its parent."""
    module = "js/modules/titlebar_fit.js"
    reads = {  # a line of fit() -> the read put before it
        "            bar.classList.remove(...ALL);\n":
            ("fccTitleBarPrefs", "js/modules/titlebar_prefs.js",
             "            const fakePrefs = window.fccTitleBarPrefs ? window.fccTitleBarPrefs.get() : null;\n"),
        "            if (!pending) remember(level);\n":
            ("fccTextSize", "js/modules/text_size.js", "            const fakeSize = window.fccTextSize;\n"),
    }
    src = (STATIC / module).read_text(encoding="utf-8")
    for line, (name, provider, read) in reads.items():
        assert src.count(line) == 1, (
            f"{module} no longer has the line {line.strip()!r}: point this proof at a line fit() runs at load.")
        src = src.replace(line, read + line)
    copy = load_dir / "tbfit.js"
    copy.write_text(src, encoding="utf-8")
    page = [dict(s, file=str(copy)) if s["name"] == module else s for s in page_scripts]
    result = run_page(page, load_dir, "tbfit")
    assert _early(result) == {(module, name, provider) for name, provider, _ in reads.values()}, (
        _pinned("fccTitleBarPrefs and fccTextSize", "titlebar_prefs.js and text_size.js"), result["early_reads"])
    assert all("fit (" + module in r["at"] for r in result["early_reads"]), result["early_reads"]
    assert result["errors"] == [], result["errors"]


def test_a_script_sees_only_the_page_above_it(page_scripts, load_dir):
    """While a <head> script runs, document.body is null, and an element below
    a script's tag isn't there yet: both throw in a browser, and now in the
    canary (review finding r2-3). The same lookup once the element is parsed
    is fine."""
    boot = "templates/dashboard.html:25 (inline #fcc-title-bar-boot)"
    in_head = "FAKE <head> script using document.body"
    too_early = "FAKE <head> script looking up #fcc-shortcuts-overlay"
    after_it = "FAKE script after #fcc-shortcuts-overlay looking it up"
    lookup = "document.getElementById('fcc-shortcuts-overlay').addEventListener('click', function () {});"
    page = with_fake(page_scripts, "document.body.classList.add('fake');", in_head, after=boot)
    page = with_fake(page, lookup, too_early, after=in_head)
    page = with_fake(page, lookup, after_it, before="js/NoSleep.min.js")
    result = run_page(page, load_dir, "fake-dom-position")
    assert [(e["script"], e["phase"]) for e in result["errors"]] == [(in_head, "run"), (too_early, "run")], (
        result["errors"])
    assert all(e["message"].startswith("TypeError: Cannot read properties of null") for e in result["errors"]), (
        result["errors"])


def test_the_dom_by_position_on_a_made_up_page(tmp_path):
    """The positional DOM, checked from inside the page's own scripts (each
    throws if an answer is wrong): what a <head> script sees, ids and simple
    selectors by position, an element's own queries, a selector the stub can't
    read, a removed element, an id the templates lack, and matchMedia."""
    templates = _templates(tmp_path, {"page.html": (
        "<!DOCTYPE html>\n<html><head>\n<script>\n(function () {\n"
        "  if (document.body !== null) throw new Error('a <head> script saw a body');\n"
        "  if (document.getElementById('top') !== null) throw new Error('#top before the parser reached it');\n"
        "  if (!document.head || !document.documentElement) throw new Error('no <head> or <html>');\n"
        "  if (!document.getElementById('built-by-a-script')) throw new Error('an id the page lacks lost its dummy');\n"
        "})();\n</script>\n</head>\n<body>\n"
        "<div id=\"top\" class=\"bar main\" data-kind=\"x\">\n"
        "  <span class=\"brand\">FCC</span>\n"
        "  <p><button class=\"go\" type=\"button\" data-bs-target=\"#panel\">Go</button></p>\n"
        "</div>\n"
        "<script>\n(function () {\n"
        "  const top = document.getElementById('top');\n"
        "  if (!top || !top.isConnected || top.parentNode !== document.body) throw new Error('#top');\n"
        "  if (document.querySelector('.bar') !== top || document.querySelector('div.main.bar') !== top) throw new Error('classes');\n"
        "  const brand = top.querySelector('.brand');\n"
        "  if (!brand || brand.parentNode !== top || brand.closest('.bar') !== top) throw new Error('descendant');\n"
        "  if (!document.querySelector('#top > p > button.go[data-bs-target=\"#panel\"]')) throw new Error('child, attribute');\n"
        "  if (document.querySelector('#top > button') !== null) throw new Error('a grandchild matched >');\n"
        "  if (document.querySelectorAll('#top span, #top button').length !== 2) throw new Error('a selector list');\n"
        "  if (top.dataset.kind !== 'x' || top.className !== 'bar main') throw new Error('attributes');\n"
        "  top.dataset.fresh = 'y';\n"
        "  delete top.dataset.kind;\n"
        "  if (!document.querySelector('[data-fresh=\"y\"]') || document.querySelector('[data-kind]')) throw new Error('dataset');\n"
        "  if (document.getElementById('below') !== null || document.querySelector('#below')) throw new Error('#below early');\n"
        "  if (document.querySelector('button:hover') !== null) throw new Error('an unreadable selector found something');\n"
        "  if (!matchMedia('(min-width: 992px)').matches || matchMedia('(max-width: 600px)').matches) throw new Error('media');\n"
        "  brand.remove();\n"
        "  if (top.querySelector('.brand') !== null) throw new Error('a removed element was found');\n"
        "})();\n</script>\n"
        "<template><div id=\"inert\"></div></template>\n"
        "<div id=\"below\"></div>\n"
        "<script>\n(function () {\n"
        "  if (!document.getElementById('below')) throw new Error('#below once parsed');\n"
        "})();\n</script>\n"
        "</body></html>\n")})
    scripts = read_page_scripts(templates, tmp_path / "static", "page.html")
    ats = [s["dom_at"] for s in scripts]
    assert len(ats) == 3 and ats[0] < ats[1] < ats[2], ats
    result = run_page(scripts, tmp_path, "made-up-dom")
    assert result["errors"] == [], result["errors"]


def test_every_declarator_of_a_top_level_let_is_a_definer(page_scripts, load_dir):
    """`let a = ..., b = ...;` declares both names: a `typeof` of the second
    before its script is an early read, as one of the first is (review finding
    r2-6: only the first declarator used to be a definer)."""
    definer = "FAKE definer after titlebar_prefs.js: let fakeFirst = ..., fakeSecond = ..."
    reader = "FAKE reader before inv_core.js: typeof fakeSecond"
    page = with_fake(page_scripts, "let fakeFirst = function () {}, fakeSecond = function () {};", definer,
                     after="js/modules/titlebar_prefs.js")
    page = with_fake(page, "if (typeof fakeSecond === 'function') {}", reader, before="js/modules/inv_core.js")
    result = run_page(page, load_dir, "fake-second-declarator")
    assert _early(result) == {(reader, "fakeSecond", definer)}, result["early_reads"]
    assert result["definers"].get("fakeFirst") == definer and {"fakeFirst", "fakeSecond"} <= set(result["lexical"])
    assert result["errors"] == [], result["errors"]


# (source, names the declaration scan must find, names it must not)
DECLARATION_SHAPES = [
    ("let a1 = 1, b1 = 2;", {"a1", "b1"}, set()),
    ("const c1 = f(1, 2), d1 = [3, 4], e1 = { x: 1, y: 2 }, g1 = function () { return 1, 2; };",
     {"c1", "d1", "e1", "g1"}, {"x", "y"}),
    ("const { k1, l1: m1 = n(1, 2), ...o1 } = p, [q1, , r1 = 's,t'] = u;", {"k1", "m1", "o1", "q1", "r1"}, {"p"}),
    ("const v1 = 'a, w1 = 1', x1 = `${y1, 1}, z1 = 2`, aa1 = /, bb1 = [,]/g, cc1 = 1;",
     {"v1", "x1", "aa1", "cc1"}, {"w1", "y1", "z1", "bb1"}),
    ("let dd1 = cond\n  ? 1\n  : 2,\n  ee1 = 3\nfoo(ff1, gg1);", {"dd1", "ee1"}, {"ff1", "gg1"}),
    ("let hh1 = 1 // , ii1 = 2\n, jj1 = 3; /* , kk1 = 4 */", {"hh1", "jj1"}, {"ii1", "kk1"}),
    ("obj.let = 1; const ll1 = 1; class Mm1 extends Nn1 {}", {"ll1", "Mm1"}, {"Nn1"}),
    # Only a declaration outside every bracket can be top-level.
    ("for (const [oo1, pp1] of xs) {} function f() { const rr1 = 1; } { let ss1; } let qq1 = 1",
     {"qq1"}, {"oo1", "pp1", "rr1", "ss1"}),
    # Brackets that don't balance as read: every declaration's names, to be safe.
    ("function f() { const tt1 = 1; let uu1 = 1", {"tt1", "uu1"}, set()),
    ("function f() { const vv1 = 1; ) let ww1 = 1", {"vv1", "ww1"}, set()),
]


def test_an_own_reads_place_is_found_through_line_offsets_and_crlf(tmp_path):
    """Whether an own read sat in its declaration is told from stack frames,
    which count a template's lines from the template's top, add the column of
    the <script> tag's end on the script's first line only, and count a CRLF
    as one line end. On a made-up page: an inline script whose alias is on its
    first line, after the tag (its read ends that statement, so only the tag's
    column puts it inside), and whose own-value read is two lines down; and a
    file with CRLF line ends holding the same two shapes lower down."""
    templates = _templates(tmp_path, {"page.html": (
        "<html><head></head><body>\n<p>x</p>\n"
        "<script>  let fakeA = window.fakeA;\n  let fakeSecond = 1;\n  if (window.fakeSecond) {}\n</script>\n"
        "<script src=\"{{ url_for('static', filename='js/crlf.js') }}\"></script>\n"
        "<script>window.fakeA = 1; window.fakeSecond = fakeSecond;\n"
        "  window.fakeCrlfAlias = 1; window.fakeCrlfOwn = fakeCrlfOwn;</script>\n"
        "</body></html>\n")})
    js = tmp_path / "static" / "js"
    js.mkdir(parents=True)
    (js / "crlf.js").write_bytes(b"// CRLF line ends\r\nvar pad = 1;\r\nlet fakeCrlfAlias = window.fakeCrlfAlias;\r\n"
                                 b"let fakeCrlfOwn = 2;\r\nif (window.fakeCrlfOwn) {}\r\n")
    scripts = read_page_scripts(templates, tmp_path / "static", "page.html")
    result = run_page(scripts, tmp_path, "made-up-own-reads")
    assert result["errors"] == [], result["errors"]
    first, setter = scripts[0]["name"], scripts[2]["name"]
    got = {(r["reader"], r["name"], r["definer"], r["taken"]) for r in result["early_reads"]}
    assert got == {(first, "fakeA", setter, True), (first, "fakeSecond", setter, False),
                   ("js/crlf.js", "fakeCrlfAlias", setter, True), ("js/crlf.js", "fakeCrlfOwn", setter, False)}, (
        result["early_reads"])


def test_the_declaration_scan_finds_every_declarator_and_skips_literals(load_dir):
    """The scan (DRIVER_JS's declaredNames) lists the names V8 is then asked
    about. Over-inclusion costs a probe; a miss hides a definer. A comma inside
    a string, template literal, comment or regular expression starts no
    declarator, and a line break ends a declaration only where JavaScript's
    automatic semicolon insertion would."""
    found = declared_names([src for src, _, _ in DECLARATION_SHAPES], load_dir)
    for (src, must, must_not), names in zip(DECLARATION_SHAPES, found):
        assert must <= set(names), f"{src!r}: missed {sorted(must - set(names))} (found {names})"
        assert not (must_not & set(names)), f"{src!r}: took {sorted(must_not & set(names))} for declared names"


def test_a_stub_copy_of_a_page_name_is_reported(page_scripts, load_dir):
    """A stand-in for showToast in the stub, as someone might add to get a
    script to load, is caught: inv_core.js sets showToast on window too."""
    stub = STUB_JS.replace("  g.navigator = {", "  g.showToast = noop;\n  g.navigator = {", 1)
    assert stub != STUB_JS
    result = run_page(page_scripts, load_dir, "stub-copy", stub=stub)
    assert [(o["name"], o["script"]) for o in result["stub_overlaps"]] == [("showToast", "js/modules/inv_core.js")], (
        _pinned("showToast", "js/modules/inv_core.js"), result["stub_overlaps"])
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
    pytest.param({"page.html": "{%+ if on +%}\n<script>var a = 1;</script>\n{%- endif -%}\n"},
                 "sits inside {% if %} at templates/page.html:1", id="script-in-if-with-trim-marks"),
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
