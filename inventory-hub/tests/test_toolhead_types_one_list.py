"""One toolhead-Type list for the page (Group 53.1).

The backend decides "is this row a toolhead?" with one list,
locations_db.TOOLHEAD_TYPES ('Tool Head', 'MMU Slot', 'No MMU Direct Load'), mostly
read as `str(row.get('Type', '')).strip() in TOOLHEAD_TYPES`, exact and
case-sensitive (the move engine's one-spool rule, logic._is_single_occupancy and
_holds_one_spool, and locations_db.validate_slot_targets compare it untrimmed).
The page had 16 checks of its own: hand-written copies of that list (two of them
lower-cased) and four substring tests ("tool" / "mmu" / "direct load"). They
agreed, but a new head Type would have had to be added to every copy, and a
missed copy is a real bug: a backend inline list that missed "No MMU Direct Load"
once put two spools on one head (test_toolhead_resident_eject_21_3.py). The
substring tests also made any custom Type holding one of those words a head
("Toolbox", "MMU Buffer", "Direct Load Rack": the location editor lets a person
add Types).

Now the page has one list, window.TOOLHEAD_TYPES, and two helpers,
window.isToolheadType(type) and window.isHeadOrPrinterType(type), in the
`@fcc-toolhead-types` block of inv_core.js. This file keeps it that way:

  1. the block's list is locations_db.TOOLHEAD_TYPES, and its 'Printer' is
     locations_db.PRINTER_ROW_TYPE;
  2. no other quoted copy of a toolhead Type: a string or template literal that
     IS one, in any case or spacing, in static/js or in a template's inline
     JavaScript <script>;
  3. no test of a Type for a head Type's words ("tool", "mmu", "direct load"),
     and nothing kept for one, in the same scripts (the marked block too):
       - any regex literal holding a word, however it is used: tested in place
         (/mmu/i.test(t)), kept in a const and tested later, or handed to
         .match(). A regex of the whole Types (/^(Tool Head|MMU Slot)$/) is a
         copy of the list, and is caught here;
       - a string or template literal that IS a word, in any case or spacing
         ('tool', 'MMU', 'direct load'): the words kept in a list;
       - a string holding '|' and a word ('tool|mmu', 'Tool Head|MMU Slot'): a
         regex's source, or a list to split;
       - a quoted first argument holding a word, of .includes / .indexOf /
         .lastIndexOf / .startsWith / .endsWith / .match / .matchAll / .search
         or RegExp() (type.includes('Toolbox')).
     A word counts at a word start only, a backslash escape before it reading
     as a break (/\\btool\\b/), and "tooltip" is no Type, so 'community' or a
     tooltip class name never trips it;
  4. the scanners catch what they should, on synthetic source;
  5. the helpers behave, in node, lifted out of inv_core.js on their own;
  6. the switched places behave, on the real modules in node.

A line that names a Type or a word on purpose and isn't an "is it a head?" check
(the location editor's Type list, a Type badge's colour, a regex that reads a
data-toolhead attribute) ends with `// toolhead-type-ok: <why>`; a marker with
no reason doesn't count.

Comments are skipped (the scanners read JavaScript through a small lexer that
knows strings, templates, regex literals and comments), and so are the vendor
bundles (*.min.js), which aren't FCC's code, and a template's <script> whose own
text a browser doesn't run as JavaScript: one with a src, or a type that is
neither a JavaScript MIME type nor module (a JSON or template block). A type is
read however it is written (quoted either way or bare, in any case).

What the rules don't see: a Type built from pieces none of which is a head Type
or a word ('No ' + 'MMU Direct Load'), or spelled another way ('Tool-Head'); a
Type inside a longer string (some HTML, a selector '[data-type="Tool Head"]') or
in a template's markup outside a <script> (an onclick attribute, an <option>); a
'|' list in a template literal that also holds a ${...}; a regex literal right
after ')', which the lexer reads as a division (if (ok) /mmu/i.test(t)); and
'head', 'slot' or 'direct' on their own (the slot picker's 'head' kind and FCC's
DIRECT spools would trip a rule that read them).
"""
from __future__ import annotations

import bisect
import json
import re
import subprocess
from pathlib import Path

import pytest

import locations_db
# Importing the shared node driver also warns once when node is missing (a
# PytestWarning in the run's summary), and with FCC_REQUIRE_NODE=1 fails this
# file's collection instead.
from test_core1_return_ejectall_js import (
    NODE, RESULT_MARK, TOOLHEAD_TYPES_BEGIN as BEGIN, TOOLHEAD_TYPES_END as END,
    run_js, toolhead_types_block)

# Only sections 5 and 6 need node; the source rules (1 to 4) run without it.
needs_node = pytest.mark.skipif(NODE is None, reason=(
    "node is not on PATH: the toolhead-Type canary's node checks (test_toolhead_types_one_list.py: "
    "the helpers, and the switched places on the real modules) did NOT run; its source rules "
    "did. Install Node.js (see CLAUDE.md Testing), or set FCC_REQUIRE_NODE=1 to fail instead "
    "of skipping."))

HUB = Path(__file__).resolve().parent.parent
JS_ROOT = HUB / "static" / "js"
TEMPLATES = HUB / "templates"
CORE_NAME = "static/js/modules/inv_core.js"
MARKER = "toolhead-type-ok:"

FIX = ("Use window.isToolheadType(type) (a Tool Head, MMU Slot or No MMU Direct Load row) or "
       "window.isHeadOrPrinterType(type) (those, or a Printer row) from inv_core.js, called when "
       "the code runs. For a line that isn't an \"is it a head?\" check (a Type list a person picks "
       "from, a badge colour, a regex that reads a data-toolhead attribute or an API path), end it "
       "with `// toolhead-type-ok: <why>`. A new head Type goes in locations_db.TOOLHEAD_TYPES and "
       "in inv_core.js's @fcc-toolhead-types block, nowhere else.")


# ---------------------------------------------------------------------------
# A small JavaScript lexer: where the strings, templates, regex literals and
# comments are. Everything else is code. It raises _Lost when a source ends
# inside a literal, so a lexer that lost its place says so instead of skipping
# the rest of a file.
# ---------------------------------------------------------------------------

class _Lost(Exception):
    def __init__(self, what: str, at: int):
        super().__init__(what)
        self.what, self.at = what, at


# After these words a '/' starts a regex literal; after any other word, a number,
# ')' or ']' it is a division.
_REGEX_AFTER_WORDS = frozenset({
    "return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void",
    "throw", "instanceof", "yield", "await"})
_WORD = re.compile(r"[A-Za-z0-9_$]+")


def _string_end(src: str, i: int) -> int:
    quote, j, n = src[i], i + 1, len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 3 if src.startswith("\r\n", j + 1) else 2
            continue
        if c == quote:
            return j + 1
        if c == "\n":
            raise _Lost("a string runs past the end of its line", i)
        j += 1
    raise _Lost("a string never closes", i)


def _regex_end(src: str, i: int):
    """The end of the regex literal at src[i] ('/'), or None when there is none on
    this line (then the '/' is a division)."""
    j, n, in_class = i + 1, len(src), False
    while j < n:
        c = src[j]
        if c in "\r\n":
            return None
        if c == "\\":
            j += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "/":
            j += 1
            while j < n and src[j].isalpha():
                j += 1
            return j
        j += 1
    return None


def _template(src: str, i: int, out: list) -> int:
    start, j, n = i, i + 1, len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            out.append(("tpl", start, j + 1))
            return j + 1
        if c == "$" and src.startswith("{", j + 1):
            j = _code(src, j + 2, out, nested=True)
            continue
        j += 1
    raise _Lost("a template literal never closes", start)


def _code(src: str, i: int, out: list, nested: bool = False) -> int:
    n, depth, regex_ok = len(src), 0, True
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(("comment", i, j))
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise _Lost("a /* comment never closes", i)
            out.append(("comment", i, j + 2))
            i = j + 2
        elif c in "'\"":
            j = _string_end(src, i)
            out.append(("str", i, j))
            i, regex_ok = j, False
        elif c == "`":
            i, regex_ok = _template(src, i, out), False
        elif c == "/":
            j = _regex_end(src, i) if regex_ok else None
            if j is None:
                i, regex_ok = i + 1, True
            else:
                out.append(("regex", i, j))
                i, regex_ok = j, False
        elif c == "{":
            i, depth, regex_ok = i + 1, depth + 1, True
        elif c == "}":
            if nested and depth == 0:
                return i + 1
            i, depth, regex_ok = i + 1, depth - 1, True
        else:
            m = _WORD.match(src, i)
            if m:
                regex_ok = m.group(0) in _REGEX_AFTER_WORDS
                i = m.end()
            else:
                regex_ok = c not in ")]"
                i += 1
    if nested:
        raise _Lost("a ${ in a template literal never closes", i)
    return i


class _Source:
    """One JavaScript source, lexed: its literals, its comments, and line lookup."""

    def __init__(self, name: str, text: str, first_line: int = 1):
        self.name, self.text, self.first_line = name, text, first_line
        self.line_starts = [0] + [k + 1 for k, ch in enumerate(text) if ch == "\n"]
        tokens: list = []
        try:
            _code(text, 0, tokens)
        except _Lost as lost:
            raise AssertionError(
                f"{self.where(lost.at)}: the toolhead-Type canary's lexer lost its place here "
                f"({lost.what}). Teach _code / _template in {Path(__file__).name} this construct "
                "rather than skipping the file.") from None
        self.tokens = sorted(tokens, key=lambda t: t[1])
        self.marked_lines = set()
        for kind, start, end in self.tokens:
            if kind != "comment":
                continue
            body = self.text[start:end]
            body = body[2:-2] if body.startswith("/*") else body[2:]
            at = body.find(MARKER)
            if at >= 0 and body[at + len(MARKER):].strip():
                self.marked_lines.add(self.line_of(start))

    def line_of(self, pos: int) -> int:
        return bisect.bisect_right(self.line_starts, pos) - 1 + self.first_line

    def line_text(self, line: int) -> str:
        k = line - self.first_line
        end = self.line_starts[k + 1] if k + 1 < len(self.line_starts) else len(self.text)
        return self.text[self.line_starts[k]:end].strip()

    def where(self, pos: int) -> str:
        return f"{self.name}:{self.line_of(pos)}"

    def report(self, positions) -> list:
        lines = sorted({self.line_of(p) for p in positions})
        return [f"{self.name}:{ln}: {self.line_text(ln)[:160]}" for ln in lines]

    def literals(self):
        """(kind, start, end, inner text) of every string, template and regex literal."""
        for kind, start, end in self.tokens:
            if kind == "comment":
                continue
            if kind == "regex":
                inner = self.text[start + 1:self.text.rindex("/", start + 1, end)]
            else:
                inner = self.text[start + 1:end - 1]
            yield kind, start, end, inner

    def block_span(self):
        """Inside inv_core.js's @fcc-toolhead-types block, or None. Only inv_core.js
        has one: a marked copy anywhere else is still a copy."""
        if not self.name.replace("\\", "/").endswith(CORE_NAME):
            return None
        begin = [m.end() for m in re.finditer(re.escape(BEGIN), self.text)]
        end = [m.start() for m in re.finditer(re.escape(END), self.text)]
        if len(begin) != 1 or len(end) != 1 or begin[0] > end[0]:
            return None
        return begin[0], end[0]


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


_HEAD_TYPES = frozenset(_norm(t) for t in locations_db.TOOLHEAD_TYPES)
# The old substring rule's words: a literal that IS one of them (in any case or
# spacing) has one use here, a test of a Type kept in a list.
_HEAD_WORDS = frozenset({"tool", "mmu", "direct load"})
# A head Type's own words, at a word start ("tooltip" is no Type). "direct" and
# "load" may have a little between them: a space, or a regex's \s* or .?.
_TYPE_WORDS = re.compile(r"\btool(?!tip)|\bmmu|\bdirect.{0,8}?load", re.IGNORECASE)
# A backslash escape and its letter (a regex's \b or \s, a string's \n, or the \\b
# a string holds for RegExp) are no part of a word: read as a space, the word
# after one still starts a word (/\btool\b/, new RegExp('\\bmmu')).
_ESCAPE = re.compile(r"\\+[A-Za-z]")
_TEST_CALL_BEFORE = re.compile(
    r"(?:\.(?:includes|indexOf|lastIndexOf|startsWith|endsWith|match|matchAll|search)|\bRegExp)"
    r"\s*\(\s*$")


def _holds_type_words(inner: str) -> bool:
    return bool(_TYPE_WORDS.search(inner) or _TYPE_WORDS.search(_ESCAPE.sub(" ", inner)))


def copies_of_the_list(name: str, text: str, first_line: int = 1) -> list:
    """Rule 2: every line of `text` (JavaScript, called `name`) holding a string or
    template literal that IS a toolhead Type in any case or spacing ('Tool Head',
    'mmu slot', `No MMU Direct Load`), outside inv_core.js's marked block, unless
    the line has a `toolhead-type-ok:` comment that gives a reason. A regex literal
    holding the Types is rule 3's."""
    src = _Source(name, text, first_line)
    span = src.block_span()
    hits = []
    for kind, start, _end, inner in src.literals():
        if kind == "regex" or _norm(inner) not in _HEAD_TYPES:
            continue
        if span and span[0] <= start < span[1]:
            continue
        if src.line_of(start) in src.marked_lines:
            continue
        hits.append(start)
    return src.report(hits)


def substring_tests_of_a_type(name: str, text: str, first_line: int = 1) -> list:
    r"""Rule 3: every line testing a Type for a head Type's words ("tool", "mmu",
    "direct load"), or keeping them for such a test, anywhere (inv_core.js's marked
    block included), unless the line has a `toolhead-type-ok:` comment that gives a
    reason. It holds one of these:
      - any regex literal holding a word, however it is used: tested in place
        (/tool/i.test(t)), handed to t.match(/mmu/), or kept in a const or a list
        and tested later. A regex of the whole Types (/^(Tool Head|MMU Slot)$/) is
        a copy of the list, and is caught here;
      - a string or template literal that IS a word, in any case or spacing
        ('tool', ' MMU ', `Direct Load`): the words kept in a list;
      - a string holding '|' and a word ('tool|mmu', 'Tool Head|MMU Slot'): a
        regex's source, or a list to split. A template literal with a ${...} in
        it is a built string (a key, some HTML) and isn't read this way;
      - a quoted first argument holding a word, of .includes / .indexOf /
        .lastIndexOf / .startsWith / .endsWith / .match / .matchAll / .search or
        RegExp() (type.includes('Toolbox'), new RegExp('\\bmmu\\b')).
    A word counts at a word start only, a backslash escape before it reading as a
    break (/\btool\b/)."""
    src = _Source(name, text, first_line)
    hits = []
    for kind, start, _end, inner in src.literals():
        if src.line_of(start) in src.marked_lines or not _holds_type_words(inner):
            continue
        if (kind == "regex"
                or _norm(inner) in _HEAD_WORDS
                or ("|" in inner and not (kind == "tpl" and "${" in inner))
                or _TEST_CALL_BEFORE.search(src.text[max(0, start - 60):start])):
            hits.append(start)
    return src.report(hits)


_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
# One attribute of a tag: its name, then its value in double quotes, in single
# quotes or bare (HTML's three forms), or no value at all.
_ATTRIBUTE = re.compile(r"""([^\s"'=<>/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?""")
# The <script> types whose own text a browser runs as JavaScript: the HTML
# standard's JavaScript MIME types, and module. No type, or an empty one, is
# JavaScript too. A type is compared in lower case and by the part before any
# ';' (text/javascript; charset=utf-8 is read: its text is JavaScript). Any
# other type (application/json, text/template, importmap) is a block of data a
# browser never runs as JavaScript, so its text isn't read.
_JS_SCRIPT_TYPES = frozenset({
    "", "module", "application/ecmascript", "application/javascript", "application/x-ecmascript",
    "application/x-javascript", "text/ecmascript", "text/javascript", "text/javascript1.0",
    "text/javascript1.1", "text/javascript1.2", "text/javascript1.3", "text/javascript1.4",
    "text/javascript1.5", "text/jscript", "text/livescript", "text/x-ecmascript",
    "text/x-javascript"})


def _tag_attributes(raw: str) -> dict:
    """A tag's attributes, {name in lower case: value, or None when it has none}. A
    name given twice keeps its first value, as a browser does."""
    attrs: dict = {}
    for m in _ATTRIBUTE.finditer(raw):
        value = next((v for v in m.group(2, 3, 4) if v is not None), None)
        attrs.setdefault(m.group(1).lower(), value)
    return attrs


def _runs_its_text_as_javascript(attrs: dict) -> bool:
    """Whether a browser runs an inline <script>'s own text as JavaScript: never
    with a src (it runs that file), else with no type or a JavaScript one."""
    if "src" in attrs:
        return False
    kind = attrs.get("type") or ""
    return kind.split(";", 1)[0].strip().lower() in _JS_SCRIPT_TYPES


def frontend_sources():
    """(name, text, first line) of every page script: static/js/**/*.js (not the
    *.min.js vendor bundles) and, in templates/**/*.html, the text of every inline
    <script> a browser runs as JavaScript (no src; no type, a JavaScript type, or
    module)."""
    for path in sorted(JS_ROOT.rglob("*.js")):
        if path.name.endswith(".min.js"):
            continue
        yield path.relative_to(HUB).as_posix(), path.read_text(encoding="utf-8"), 1
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        for m in _SCRIPT.finditer(text):
            if not _runs_its_text_as_javascript(_tag_attributes(m.group(1))):
                continue
            yield (path.relative_to(HUB).as_posix(), m.group(2),
                   text.count("\n", 0, m.start(2)) + 1)


# ---------------------------------------------------------------------------
# 1. The page's list is the backend's.
# ---------------------------------------------------------------------------

def _block_literals(block: str) -> list:
    src = _Source(CORE_NAME + " (@fcc-toolhead-types)", block)
    return [(start, inner) for kind, start, _e, inner in src.literals() if kind != "regex"]


def test_the_page_list_is_the_backends_list():
    block = toolhead_types_block()
    m = re.search(r"window\.TOOLHEAD_TYPES\s*=\s*Object\.freeze\(\s*\[(.*?)\]\s*\)", block, re.DOTALL)
    assert m, ("inv_core.js's @fcc-toolhead-types block must set "
               "`window.TOOLHEAD_TYPES = Object.freeze([...])`, the page's one toolhead-Type list.")
    listed = [inner for start, inner in _block_literals(block) if m.start(1) <= start < m.end(1)]
    assert len(listed) == len(set(listed)), f"window.TOOLHEAD_TYPES names a Type twice: {listed}"
    assert set(listed) == set(locations_db.TOOLHEAD_TYPES), (
        f"window.TOOLHEAD_TYPES {sorted(listed)} isn't locations_db.TOOLHEAD_TYPES "
        f"{sorted(locations_db.TOOLHEAD_TYPES)}: the page and the backend would disagree on what "
        "is a toolhead. Change both together.")


def test_the_page_printer_type_is_the_backends():
    block = toolhead_types_block()
    m = re.search(r"window\.isHeadOrPrinterType\s*=(.*?)(?=window\.[A-Za-z_$]+\s*=|\Z)", block, re.DOTALL)
    assert m, "inv_core.js's @fcc-toolhead-types block must define window.isHeadOrPrinterType."
    named = [inner for start, inner in _block_literals(block)
             if m.start(1) <= start < m.end(1) and inner.strip()]
    assert named == [locations_db.PRINTER_ROW_TYPE], (
        f"window.isHeadOrPrinterType should name only locations_db.PRINTER_ROW_TYPE "
        f"({locations_db.PRINTER_ROW_TYPE!r}) besides the list; it names {named}.")


# ---------------------------------------------------------------------------
# 2-3. No other copy, no substring test, in the real tree.
# ---------------------------------------------------------------------------

def test_no_other_copy_of_the_toolhead_type_list():
    hits = [h for name, text, first in frontend_sources() for h in copies_of_the_list(name, text, first)]
    assert not hits, (
        f"{len(hits)} line(s) name a toolhead Type (a string or template literal that is one, in "
        "any case or spacing) outside inv_core.js's @fcc-toolhead-types block:\n  "
        + "\n  ".join(hits) + "\n" + FIX)


def test_no_substring_test_of_a_location_type():
    hits = [h for name, text, first in frontend_sources()
            for h in substring_tests_of_a_type(name, text, first)]
    assert not hits, (
        f"{len(hits)} line(s) test a Type for a toolhead Type's words (\"tool\", \"mmu\", \"direct "
        "load\") or keep them for such a test: a regex literal holding one, however it is used "
        "(tested in place, kept in a const, handed to .match()), a quoted word on its own (a words "
        "list), a string joining them with '|', or a quoted first argument holding one of .includes "
        "/ .indexOf / .lastIndexOf / .startsWith / .endsWith / .match / .matchAll / .search / "
        "RegExp(). A test for the words also makes any custom Type holding them "
        "(\"Toolbox\", \"MMU Buffer\") a head, and a regex of the whole Types is a copy of the "
        "list:\n  " + "\n  ".join(hits) + "\n" + FIX)


def test_the_scan_reads_every_page_script():
    """The scan sees the modules and the inline scripts, not an empty tree."""
    names = {name for name, _t, _f in frontend_sources()}
    for must in (CORE_NAME, "static/js/modules/inv_cmd.js", "static/js/modules/inv_loc_mgr.js",
                 "templates/dashboard.html", "templates/components/scripts.html"):
        assert must in names, f"{must} wasn't scanned: {sorted(names)}"
    assert not any(n.endswith(".min.js") for n in names)


DO_ASSIGN = "static/js/modules/inv_loc_mgr.js"
DO_ASSIGN_CHECK = "const isToolheadTarget = !!locObjCheck && window.isHeadOrPrinterType(locObjCheck.Type);"


@pytest.mark.parametrize("kept,check", [
    ("const HEAD_RE = /tool|mmu|direct load|printer/i;",
     "const isToolheadTarget = !!locObjCheck && HEAD_RE.test(locObjCheck.Type);"),
    ("const HEAD_WORDS = ['tool', 'mmu', 'direct load', 'printer'];",
     "const isToolheadTarget = !!locObjCheck && HEAD_WORDS.some((w) => "
     "String(locObjCheck.Type).toLowerCase().includes(w));"),
], ids=["hoisted-regex", "words-list"])
def test_doassigns_head_check_written_the_old_way_is_caught(kept, check):
    """The review's proof on a real module (r2-4 / r5-2): doAssign's head check in
    inv_loc_mgr.js, a daily move path, written as the old substring rule again,
    its regex or its words kept in a const above it. The canary names the line."""
    lines = (HUB / DO_ASSIGN).read_text(encoding="utf-8").split("\n")
    at = [i for i, ln in enumerate(lines) if ln.strip() == DO_ASSIGN_CHECK]
    assert len(at) == 1, (
        f"{DO_ASSIGN} should hold doAssign's head check `{DO_ASSIGN_CHECK}` once; found {len(at)}. "
        "This proof writes that check the old way and expects the canary to name its line: point "
        "DO_ASSIGN_CHECK at the check's new text, or at another line that calls "
        "window.isHeadOrPrinterType.")
    i = at[0]
    indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
    lines[i:i + 1] = [indent + kept, indent + check]
    text = "\n".join(lines)
    hits = copies_of_the_list(DO_ASSIGN, text) + substring_tests_of_a_type(DO_ASSIGN, text)
    assert hits == [f"{DO_ASSIGN}:{i + 1}: {kept}"], hits


# ---------------------------------------------------------------------------
# 4. The scanners catch what they should (synthetic source).
# ---------------------------------------------------------------------------

M = "static/js/modules/fake.js"


@pytest.mark.parametrize("line", [
    "const HEADS = ['Tool Head', 'MMU Slot'];",
    'if (x.Type === "No MMU Direct Load") go();',
    "const t = `Tool Head`;",
    "const set = new Set(['tool head', 'mmu slot', 'no mmu direct load']);",
    "switch (row.Type) { case 'MMU Slot': go(); }",
    "const ws = ' Tool  Head ';",
], ids=["inline-list", "equality", "backtick", "lower-case", "switch", "spacing"])
def test_a_copy_is_caught(line):
    assert copies_of_the_list(M, "const a = 1;\n" + line + "\n") == [f"{M}:2: {line}"]


@pytest.mark.parametrize("line", [
    "if (type.indexOf('mmu') >= 0) go();",
    "if (/tool/i.test(t)) go();",
    "const h = type.includes('tool') || type.includes('direct load');",
    'if (t.startsWith("MMU")) go();',
    "if (t.match(/direct\\s*load/i)) go();",
    "const r = new RegExp('Tool', 'i');",
    "if (t.search(`mmu`) >= 0) go();",
    # Kept in a const and used later (Group 53's review, r2-4 / r5-2): the list as
    # a regex, the same lower-cased for match(), the old substring rule's regex,
    # and its words in a list. The line reported is the literal's, not the use's.
    "const HEAD_RE = /^(Tool Head|MMU Slot|No MMU Direct Load)$/;\nif (HEAD_RE.test(row.Type)) go();",
    "const HEAD_RE = /^(tool head|mmu slot|no mmu direct load)$/i;\nconst m = String(t).match(HEAD_RE);",
    "const HEAD_RE = /tool|mmu|direct load/i;\nconst isHead = HEAD_RE.test(t);",
    "const isHead = ['tool', 'mmu', 'direct load'].some((w) => type.toLowerCase().includes(w));",
    "const HEAD_WORDS = ['Tool', ' MMU ', 'Direct  Load'];\nconst isHead = HEAD_WORDS.some((w) => t.includes(w));",
    "const HEADS = [/^tool head$/i, /^mmu slot$/i];\nconst isHead = HEADS.some((re) => re.test(t));",
    # A backslash escape before a word (a regex's \b, the \\b a string holds for
    # RegExp) still leaves the word at a word start.
    "const HEAD_RE = /\\btool\\b|\\bmmu\\b|\\bdirect\\s*load\\b/i;\nconst isHead = HEAD_RE.test(t);",
    "const r = new RegExp('\\\\bmmu\\\\b', 'i');",
    # A string joining the words or the Types with '|': a regex's source, or a list to split.
    "const HEAD_SRC = 'tool|mmu|direct load';\nconst isHead = new RegExp(HEAD_SRC, 'i').test(t);",
    "const isHead = 'Tool Head|MMU Slot|No MMU Direct Load'.split('|').includes(row.Type);",
    # A Type built from pieces, one of them a word on its own.
    "if (row.Type === 'Tool' + ' Head') go();",
    "if (type.includes ('toolhead')) go();",
], ids=["indexOf", "regex-test", "includes", "startsWith", "match-regex", "RegExp", "search-backtick",
        "hoisted-regex-of-the-list", "hoisted-lower-case-regex-match", "hoisted-substring-regex",
        "words-list", "hoisted-words-list", "list-of-regexes", "escaped-word-starts",
        "RegExp-of-escaped-words", "joined-regex-source", "joined-list-split", "type-from-pieces",
        "space-before-paren"])
def test_a_substring_test_is_caught(line):
    first = line.split("\n")[0]
    assert substring_tests_of_a_type(M, "let a;\n" + line + "\n") == [f"{M}:2: {first}"]


@pytest.mark.parametrize("line", [
    "const HEADS = ['Tool Head', 'MMU Slot']; // toolhead-type-ok: the Type dropdown's options",
    "if (/tool/i.test(t)) go(); /* toolhead-type-ok: a badge colour only */",
    "if (type.indexOf('mmu') >= 0) go(); // toolhead-type-ok:look only",
])
def test_a_line_with_a_reason_passes(line):
    text = "let a;\n" + line + "\n"
    assert copies_of_the_list(M, text) == [] and substring_tests_of_a_type(M, text) == []


@pytest.mark.parametrize("marker", ["// toolhead-type-ok:", "// toolhead-type-ok:   ",
                                    "/* toolhead-type-ok: */", "// toolhead-type-ok"])
def test_a_marker_with_no_reason_does_not_count(marker):
    copy = f"const HEADS = ['Tool Head']; {marker}"
    test = f"if (/mmu/i.test(t)) go(); {marker}"
    assert copies_of_the_list(M, copy + "\n") == [f"{M}:1: {copy.strip()}"]
    assert substring_tests_of_a_type(M, test + "\n") == [f"{M}:1: {test.strip()}"]


def test_the_marked_block_is_allowed_in_inv_core_only():
    block = (f"let before = 1;\n{BEGIN}\nwindow.TOOLHEAD_TYPES = Object.freeze(['Tool Head', 'MMU Slot', "
             f"'No MMU Direct Load']);\n{END}\nconst after = 'MMU Slot';\n")
    assert copies_of_the_list(CORE_NAME, block) == [f"{CORE_NAME}:5: const after = 'MMU Slot';"]
    # The same marked block anywhere else is a copy.
    assert len(copies_of_the_list(M, block)) == 2


def test_the_marked_block_allows_no_substring_test():
    """The block may hold the list, never the old substring rule: a helper written
    as a regex of the words is caught there too."""
    helper = "window.isToolheadType = (type) => /tool|mmu|direct load/i.test(String(type));"
    block = (f"{BEGIN}\nwindow.TOOLHEAD_TYPES = Object.freeze(['Tool Head', 'MMU Slot', "
             f"'No MMU Direct Load']);\n{helper}\n{END}\n")
    assert copies_of_the_list(CORE_NAME, block) == []
    assert substring_tests_of_a_type(CORE_NAME, block) == [f"{CORE_NAME}:3: {helper}"]


@pytest.mark.parametrize("text", [
    "// a 'Tool Head' row, or an 'MMU Slot'\n",
    "/* type.includes('mmu') was the old test */\n",
    "toast('Open a Tool Head first');\n",
    "el.classList.contains('tooltip'); x.includes('tooltip'); y.indexOf('community');\n",
    "const what = feeds.kind === 'toolhead' ? 'a toolhead' : 'a slot';\n",
    "if (type.includes(word)) go();\n",
    # A division read as a regex would hold "mmu" and be caught.
    "const r = a / b / c; const s = tool / mmu / 2;\n",
    "const re = /['\"]/g; const q = \"it's a Tool Head\";\n",
    "const html = `<b>${row.Type === x ? 'a' : 'b'}</b> tool`;\n",
    "const r = /tooltip|community/i; const k = 'tooltip|x';\n",
    "const key = `${th.toolhead}|${slot}`;\n",
    "const label = 'Tool 3'; showToast('Pick a tool first');\n",
    "const kind = 'toolhead'; const cls = 'mmu-grid'; el.matches('.mmu-grid');\n",
], ids=["comment", "block-comment", "prose", "tooltip-community", "feed-kind", "variable",
        "division", "quote-in-regex", "template-expression", "tooltip-regex", "template-key",
        "a-word-in-words", "longer-words"])
def test_unrelated_code_passes(text):
    assert copies_of_the_list(M, text) == [] and substring_tests_of_a_type(M, text) == []


def test_a_literal_inside_a_template_expression_is_still_read():
    text = "const html = `<div>${row.Type === 'Tool Head' ? `${t.includes('mmu')}` : ''}</div>`;\n"
    assert copies_of_the_list(M, text) == [f"{M}:1: {text.strip()}"]
    assert substring_tests_of_a_type(M, text) == [f"{M}:1: {text.strip()}"]


def test_an_inline_script_reports_the_template_line():
    assert copies_of_the_list("templates/x.html", "\n\nif (t === 'MMU Slot') go();\n", first_line=40) \
        == ["templates/x.html:42: if (t === 'MMU Slot') go();"]


def _page_sources(tmp_path, monkeypatch, html: str) -> list:
    """frontend_sources() over a tree holding one template, templates/page.html."""
    (tmp_path / "static" / "js").mkdir(parents=True)
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "page.html").write_text(html, encoding="utf-8")
    # frontend_sources() reads its roots from this module's globals when it runs.
    monkeypatch.setitem(globals(), "HUB", tmp_path)
    monkeypatch.setitem(globals(), "JS_ROOT", tmp_path / "static" / "js")
    monkeypatch.setitem(globals(), "TEMPLATES", tmp_path / "templates")
    return list(frontend_sources())


def _page_hits(sources) -> list:
    return [h for name, text, first in sources
            for h in copies_of_the_list(name, text, first) + substring_tests_of_a_type(name, text, first)]


@pytest.mark.parametrize("tag", [
    '<script type="text/javascript">', "<script type='application/javascript'>",
    "<script type=text/javascript>", '<script defer TYPE="Module">', '<script type="">',
    '<script type="text/javascript; charset=utf-8">', '<script data-src="boot.js">',
], ids=["double-quoted", "single-quoted", "unquoted", "module-any-case", "empty", "parameters",
        "data-src"])
def test_an_inline_script_a_browser_runs_is_scanned(tmp_path, monkeypatch, tag):
    """A <script> whose own text a browser runs as JavaScript is read, however its
    type is written (the review of Group 53, r2-5: any quoted type was skipped)."""
    page = f"<div>\n{tag}\nif (row.Type === 'Tool Head') go();\nif (t.includes('mmu')) go();\n</script>\n"
    assert _page_hits(_page_sources(tmp_path, monkeypatch, page)) == [
        "templates/page.html:3: if (row.Type === 'Tool Head') go();",
        "templates/page.html:4: if (t.includes('mmu')) go();"]


@pytest.mark.parametrize("tag", [
    '<script type="application/json">', "<script type='text/template'>",
    "<script type=text/x-template>", '<script type="importmap">', '<script src="/static/js/app.js">',
    "<script SRC='x.js' type=\"module\">",
], ids=["json", "template", "x-template-unquoted", "importmap", "src", "src-any-case"])
def test_a_script_a_browser_does_not_run_as_javascript_is_not_read(tmp_path, monkeypatch, tag):
    """A data block or a template isn't JavaScript (read as JavaScript, its
    apostrophe would lose the lexer), and a script with a src runs that file, not
    its own text. The plain <script> after it is still read."""
    page = (f"{tag}\n<option>Tool Head</option> it's {{\"type\": \"MMU Slot\"}}\n</script>\n"
            "<script>\nconst ok = 1;\n</script>\n")
    sources = _page_sources(tmp_path, monkeypatch, page)
    assert [(name, first) for name, _text, first in sources] == [("templates/page.html", 4)]
    assert _page_hits(sources) == []


def test_a_source_the_lexer_cannot_read_fails_loudly():
    with pytest.raises(AssertionError, match=r"fake\.js:2: .*lost its place"):
        copies_of_the_list(M, "let a;\nconst s = 'never closed;\n")


# ---------------------------------------------------------------------------
# 5. The helpers behave (node, the block on its own in a fresh context).
# ---------------------------------------------------------------------------

HELPERS_DRIVER = r"""
const vm = require('vm');
const BLOCK = __BLOCK__;
const VALUES = __VALUES__;
const ctx = vm.createContext({});
vm.runInContext('globalThis.window = globalThis;', ctx);
const before = new Set(vm.runInContext('Object.keys(globalThis)', ctx));
// Twice, as a page whose harness lifted it and then loaded inv_core.js would: a
// top-level const / let / class in the block would throw here (and on the page, a
// name another module also declares kills that whole module).
vm.runInContext(BLOCK, ctx, { filename: 'inv_core.js (@fcc-toolhead-types)' });
vm.runInContext(BLOCK, ctx, { filename: 'inv_core.js (@fcc-toolhead-types), again' });
const added = vm.runInContext('Object.keys(globalThis)', ctx).filter(k => !before.has(k)).sort();
ctx.__values = VALUES;
const out = vm.runInContext(`(() => {
  const vals = globalThis.__values;
  const rows = vals.map(v => [JSON.stringify(v), window.isToolheadType(v), window.isHeadOrPrinterType(v)]);
  rows.push(['undefined', window.isToolheadType(undefined), window.isHeadOrPrinterType(undefined)]);
  rows.push(['(no argument)', window.isToolheadType(), window.isHeadOrPrinterType()]);
  let threw = null;
  try { window.TOOLHEAD_TYPES.push('Toolbox'); } catch (e) { threw = String(e.name); }
  return { list: Array.from(window.TOOLHEAD_TYPES), frozen: Object.isFrozen(window.TOOLHEAD_TYPES),
           isArray: Array.isArray(window.TOOLHEAD_TYPES), pushThrew: threw,
           listAfterPush: Array.from(window.TOOLHEAD_TYPES), rows };
})()`, ctx);
console.log('__FCC_RESULT__' + JSON.stringify(Object.assign(out, { added })));
"""

VALUES = ["Tool Head", "MMU Slot", "No MMU Direct Load", " Tool Head ", "\tMMU Slot\n",
          "Printer", " Printer ", "printer", "PRINTER", "Room", "Toolbox", "MMU Buffer",
          "Direct Load Rack", "tool head", "TOOL HEAD", "Tool  Head", "", "   ", None, 42, True]


def _run_helpers(tmp_path) -> dict:
    driver = (HELPERS_DRIVER.replace("__BLOCK__", json.dumps(toolhead_types_block()))
              .replace("__VALUES__", json.dumps(VALUES)))
    script = tmp_path / "helpers.js"
    script.write_text(driver, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(RESULT_MARK)]
    assert proc.returncode == 0 and lines, (
        f"node failed (rc={proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(lines[-1][len(RESULT_MARK):])


@needs_node
def test_the_helpers_behave(tmp_path):
    out = _run_helpers(tmp_path)
    # Only the three window properties: nothing else leaks onto the page.
    assert out["added"] == ["TOOLHEAD_TYPES", "isHeadOrPrinterType", "isToolheadType"], out["added"]
    assert out["isArray"] and out["frozen"], out
    assert sorted(out["list"]) == sorted(locations_db.TOOLHEAD_TYPES), out["list"]
    assert out["pushThrew"] == "TypeError" and out["listAfterPush"] == out["list"], (
        f"a caller could change the page's list: {out}")
    got = {label: (head, head_or_printer) for label, head, head_or_printer in out["rows"]}
    # A head: exact and case-sensitive once trimmed, as most backend reads go.
    head = {'"Tool Head"', '"MMU Slot"', '"No MMU Direct Load"', '" Tool Head "', '"\\tMMU Slot\\n"'}
    printer = {'"Printer"', '" Printer "'}
    for label, (is_head, is_head_or_printer) in got.items():
        assert is_head is (label in head), f"isToolheadType({label}) is {is_head}"
        assert is_head_or_printer is (label in head or label in printer), (
            f"isHeadOrPrinterType({label}) is {is_head_or_printer}")
    assert len(got) == len(VALUES) + 2


@needs_node
def test_the_shared_node_driver_gives_every_module_the_helpers(tmp_path):
    """tests/test_core1_return_ejectall_js.run_js lifts the block before any module
    loads (as the page loads inv_core.js first), so a harness that loads a module
    without inv_core.js still finds the helpers."""
    res = run_js(tmp_path, [], "return { list: Array.from(window.TOOLHEAD_TYPES || []), "
                               "head: typeof window.isToolheadType === 'function' && window.isToolheadType('MMU Slot'), "
                               "printer: typeof window.isHeadOrPrinterType === 'function' "
                               "&& window.isHeadOrPrinterType('Printer') };")
    assert sorted(res["list"]) == sorted(locations_db.TOOLHEAD_TYPES) and res["head"] and res["printer"], res


# ---------------------------------------------------------------------------
# 6. The switched places, on the real modules.
# ---------------------------------------------------------------------------

def _row(lid, typ, max_spools=None, **more):
    row = {"LocationID": lid, "Name": f"{lid} ({typ})", "Type": typ}
    if max_spools is not None:
        row["Max Spools"] = max_spools
    row.update(more)
    return row


ROWS = [
    _row("XL", "Printer", toolheads=[{"location_id": "XL-1", "position": 0},
                                     {"location_id": "XL-2", "position": 1}]),
    _row("XL-1", "Tool Head"),
    _row("XL-2", "Tool Head", "1"),
    _row("MMU-1", "MMU Slot"),
    _row("DL-1", "No MMU Direct Load"),
    _row("CORE1", "Printer", toolheads=[{"location_id": "CORE1", "position": 0}]),
    # Custom Types holding a head Type's words: never heads.
    _row("TB-1", "Toolbox", "5"),
    _row("MB-1", "MMU Buffer", "3"),
    _row("DLR-1", "Direct Load Rack", "2"),
    _row("LR-MDB-1", "Dryer Box", "4"),
    _row("PM-DB-1", "Dryer Box", "1"),
    _row("C-1", "Cart"),
    _row("SH-1", "Shelf", "1"),
]
HEADS = {"XL-1", "XL-2", "MMU-1", "DL-1"}
PRINTERS = {"XL", "CORE1"}
ALL = [r["LocationID"] for r in ROWS]


def _scenario(body: str) -> str:
    return "const rows = " + json.dumps(ROWS) + ";\nstate.allLocations = rows;\n" + body


CMD = ["inv_core.js", "ui_builder.js", "inv_cmd.js"]
LOC_MGR = ["inv_core.js", "ui_builder.js", "inv_loc_mgr.js"]


@needs_node
def test_eject_modes_head_check(tmp_path):
    """inv_cmd.js's _isSingleHeadRow: a toolhead label in eject mode ejects its spool."""
    res = run_js(tmp_path, CMD, _scenario("""
const got = {};
for (const r of rows) got[r.LocationID] = _isSingleHeadRow(r, r.LocationID.toUpperCase());
return { got };"""))
    assert res["unhandled"] == [], res["unhandled"]
    # CORE1: a Printer row that is its own only head.
    assert res["got"] == {lid: lid in HEADS or lid == "CORE1" for lid in ALL}, res["got"]


@needs_node
def test_an_empty_buffer_location_scan_grabs_only_a_one_spool_places_spool(tmp_path):
    """inv_cmd.js's _quickPickItem (item F): a head, a printer that is its own head
    and a one-spool place grab their direct spool; every other place opens its view
    (null). A custom "Toolbox" holding 5 used to grab its spool, as a head."""
    res = run_js(tmp_path, CMD, _scenario("""
const got = {};
for (const r of rows) {
  const res = { id: r.LocationID, contents: [
    { id: 900, display: '#900', location: 'LR-MDB-1', is_ghost: true, deployed_to: r.LocationID },
    { id: 7, display: '#7', location: r.LocationID, is_ghost: false }] };
  const item = _quickPickItem(r, res);
  got[r.LocationID] = item ? item.id : null;
}
return { got };"""))
    assert res["unhandled"] == [], res["unhandled"]
    grabs = HEADS | {"CORE1", "SH-1", "PM-DB-1"}
    assert res["got"] == {lid: (7 if lid in grabs else None) for lid in ALL}, res["got"]


@needs_node
def test_record_it_as_coming_from_asks_only_for_a_spool_from_no_box(tmp_path):
    """inv_cmd.js's _askRecordSource (the Printer picker, Group 40.5): a spool from
    another head, a printer row, Unknown or Unassigned is asked about (with no free
    feed slot, the answer is '' at once); one from a place keeps its trail."""
    res = run_js(tmp_path, CMD, _scenario("""
const got = {};
for (const from of ['XL-2', 'MMU-1', 'DL-1', 'XL', 'UNKNOWN', '', 'TB-1', 'MB-1', 'LR-MDB-1', 'C-1']) {
  const v = await _askRecordSource({ spool_location: from, head: 'XL-1', feeds: [] }, 57, null);
  got[from || '(unassigned)'] = v === undefined ? 'not asked' : v;
}
return { got };"""))
    assert res["unhandled"] == [], res["unhandled"]
    asked = {"XL-2", "MMU-1", "DL-1", "XL", "UNKNOWN", "(unassigned)"}
    assert res["got"] == {k: ("" if k in asked else "not asked") for k in res["got"]}, res["got"]
    assert len(res["got"]) == 10


BUFFER_SCAN = """
window.fetchT = (u, o) => window.fetch(u, o);   // inv_core.js's own needs AbortSignal
state.heldSpools = [{ id: 1, display: '#1' }, { id: 2, display: '#2' }];
window.__respond = (url, method, body) => {
  if (url === '/api/identify_scan') return { body: { type: 'location', id: __TARGET__, contents: [] } };
  if (url === '/api/smart_move') return { body: { status: 'error', msg: 'stub', failures: [] } };
  return { body: {} };
};
processScan('LOC:' + __TARGET__, 'barcode');
await __settle(300);
return { moves: __rec.fetches.filter(f => f.url === '/api/smart_move').map(f => f.body.spools) };
"""


@needs_node
@pytest.mark.parametrize("target,spools", [
    ("XL-1", [1]), ("MMU-1", [1]), ("DL-1", [1]),
    ("TB-1", [1, 2]), ("MB-1", [1, 2]), ("DLR-1", [1, 2]), ("C-1", [1, 2]),
])
def test_a_buffer_scanned_onto_a_head_sends_only_its_top_spool(tmp_path, target, spools):
    """inv_cmd.js's location scan with a buffer (L124): a head takes the buffer's top
    spool and the rest stay; any other place takes the whole buffer. The heads here
    have no Max Spools, so only the Type decides."""
    res = run_js(tmp_path, CMD, _scenario(BUFFER_SCAN.replace("__TARGET__", json.dumps(target))))
    assert res["unhandled"] == [], res["unhandled"]
    assert res["moves"] == [spools], res


@needs_node
def test_the_location_managers_head_checks(tmp_path):
    """inv_loc_mgr.js: _isOneSpoolHeadRow (the two-spools banner), _isPrinterTopologyType
    (a saved Printer or head drops the cached printer map), _ownHeadOf (the head a
    buffered spool leaves) and the title's "Move all →" (never on a one-spool place)."""
    res = run_js(tmp_path, LOC_MGR, _scenario("""
const oneSpool = {}, own = {}, moveAll = {};
for (const r of rows) {
  oneSpool[r.LocationID] = _isOneSpoolHeadRow(r, r.LocationID.toUpperCase());
  state.heldSpools = [{ id: 5, location: r.LocationID, is_ghost: false }];
  own[r.LocationID] = _ownHeadOf('5');
  window.updateManageTitle(r);
  moveAll[r.LocationID] = /Move all/.test(document.getElementById('manageTitle').innerHTML);
}
const topo = {};
for (const t of ['Printer', 'Tool Head', 'MMU Slot', 'No MMU Direct Load', 'Toolbox', 'MMU Buffer',
                 'printer', 'Dryer Box', '', null]) topo[String(t)] = _isPrinterTopologyType(t);
return { oneSpool, own, moveAll, topo };"""))
    assert res["unhandled"] == [], res["unhandled"]
    assert res["oneSpool"] == {lid: lid in HEADS or lid == "CORE1" for lid in ALL}, res["oneSpool"]
    assert res["own"] == {lid: (lid if lid in HEADS | PRINTERS else None) for lid in ALL}, res["own"]
    assert res["moveAll"] == {lid: lid not in HEADS | PRINTERS for lid in ALL}, res["moveAll"]
    assert res["topo"] == {"Printer": True, "Tool Head": True, "MMU Slot": True, "No MMU Direct Load": True,
                           "Toolbox": False, "MMU Buffer": False, "printer": False, "Dryer Box": False,
                           "": False, "null": False}, res["topo"]


LIST_ROWS = ROWS + [_row("V-1", "Virtual"), _row("WS-1", "Wall Shelf"), _row("R-1", "Row"),
                    _row("Unassigned", "Storage")]
# Never offered by Force Location or the wizard: heads, virtual rows, structural
# groupings and the Unassigned row (which is the empty choice).
NOT_OFFERED = HEADS | {"V-1", "WS-1", "R-1", "Unassigned"}
OFFERED = [r["LocationID"] for r in LIST_ROWS if r["LocationID"] not in NOT_OFFERED]


@needs_node
def test_force_location_offers_a_custom_type_but_never_a_head(tmp_path):
    """inv_details.js's Force Location list (promptEditLocation). A custom "Toolbox",
    "MMU Buffer" or "Direct Load Rack" was hidden as a head."""
    res = run_js(tmp_path, ["inv_core.js", "ui_builder.js", "inv_details.js"], """
const rows = """ + json.dumps(LIST_ROWS) + """;
window.__respond = (url) => (url === '/api/locations' ? { body: rows } : { body: {} });
let html = null;
globalThis.Swal = { fire: (o) => { html = o.html; return Promise.resolve({ isConfirmed: false }); },
                    getPopup: () => null, close: () => {}, clickConfirm: () => {} };
window.promptEditLocation('57', 'LR-MDB-1');
await __settle(200);
return { ids: [...String(html).matchAll(/class="swal-loc-item[^"]*" data-id="([^"]*)"/g)].map(m => m[1]) };""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["ids"] == [""] + OFFERED, res["ids"]


@needs_node
def test_the_wizards_location_list_offers_a_custom_type_but_never_a_head(tmp_path):
    """inv_wizard.js: wizardFetchLocations (the Location field's list; a custom Type
    with a head's word was hidden) and wizardIsHeadOrPrinterRow (a clone of a spool
    on a head or a Printer row starts Unassigned, Group 40.7)."""
    rows = LIST_ROWS + [_row("P2", "printer")]
    res = run_js(tmp_path, ["inv_core.js", "inv_wizard.js"], """
const rows = """ + json.dumps(rows) + """;
window.__respond = (url) => (url === '/api/locations' ? { body: rows } : { body: {} });
let combo = null;
window.wizardBindCombobox = (o) => { combo = o; };
window.wizardWatchLocationPick = () => {};
await wizardFetchLocations();
const heads = {};
for (const r of rows) heads[r.LocationID] = window.wizardIsHeadOrPrinterRow(r.LocationID, rows);
heads['XL-9 (listed by no row)'] = window.wizardIsHeadOrPrinterRow('XL-9', rows.concat([
  { LocationID: 'XL9P', Type: 'Printer', toolheads: [{ location_id: 'XL-9', position: 0 }] }]));
return { locations: wizardState.locations.map(l => l.LocationID),
         items: combo ? combo.items.map(i => i.value) : null, heads };""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["locations"] == OFFERED + ["P2"], res["locations"]
    assert res["items"] == [""] + OFFERED + ["P2"], res["items"]
    # "printer" in any case is still a Printer here, as before.
    expect = {r["LocationID"]: r["LocationID"] in HEADS | PRINTERS | {"P2"} for r in rows}
    expect["XL-9 (listed by no row)"] = True
    assert res["heads"] == expect, res["heads"]


@needs_node
def test_the_locations_table_never_offers_add_child_on_printer_topology(tmp_path):
    """inv_core.js's Locations table: ➕ Add child is never on a Printer or a head (the
    printer map owns those), and is on a custom Type with a head's word."""
    res = run_js(tmp_path, ["inv_core.js"], """
const rows = """ + json.dumps(ROWS) + """;
state.locSortBy = 'LocationID'; state.locSortDir = 1;
window._renderLocationsPayload(JSON.parse(JSON.stringify(rows)), { ok: true });
const html = String(document.getElementById('location-table').innerHTML);
return { addChild: [...html.matchAll(/btn-add-child" data-id="([^"]*)"/g)].map(m => m[1]).sort() };""")
    assert res["unhandled"] == [], res["unhandled"]
    assert res["addChild"] == sorted(set(ALL) - HEADS - PRINTERS), res["addChild"]


@needs_node
def test_the_quick_swap_grid_shows_on_a_head_or_printer_only(tmp_path):
    """inv_quickswap.js's renderQuickSwapSection."""
    res = run_js(tmp_path, ["inv_quickswap.js"], _scenario("""
state.printerMap = {};
const shown = {};
for (const r of rows) {
  window.renderQuickSwapSection(r);
  shown[r.LocationID] = document.getElementById('manage-quickswap-section').style.display;
}
await __settle(100);
return { shown };"""))
    assert res["unhandled"] == [], res["unhandled"]
    assert res["shown"] =={lid: ("block" if lid in HEADS | PRINTERS else "none") for lid in ALL}, res["shown"]
