"""No hand-typed font size under the floor (readability rule, Derek 2026-10-21).

Offline, no browser: reads every stylesheet, frontend module and template and
fails on a font size typed by hand under 13.6 px, the floor for text you read.
Small text uses a named size from global.css instead (`--fcc-fs-label`
12.8 px for a label in a pill or box, `--fcc-fs-small` 13.6 px, `--fcc-fs-row`
14.4 px; DESIGN.md "Typography"): the per-browser Text size setting gives the
names other values, so a hand-typed size would not follow it, and the browser
guard (test_text_size_guard.py) can tell a label from read text only by its
name. A size is read at a 16 px root and a 16 px parent: `0.8em` is 12.8 px,
and smaller still inside small text.

A size the check can't read is a failure too ("use a named size"): a named
size is written bare, `var(--fcc-fs-small)`, or as `max(var(--fcc-fs-small),
…)` (never under the name); calc(), min(), clamp(), any other var() and a
template literal's `${…}` can each come out under the floor, and the check
would never know (readability review, 2026-10-21: twelve such forms passed).
Comments are not read (`0.7rem /* why */` is 0.7rem), a value may sit on the
next line, and JS writes it many ways: `el.style.fontSize = …`, `{ fontSize:
… }`, `el.style.font = …`, `{ font: … }`, `el.style['font-size'] = …`,
`setProperty('font-size', …)`, `$(el).css('font-size', …)`. A custom property
whose name ends in `font-size` (Bootstrap's `--bs-badge-font-size`) is a font
size. And the three names are set only in global.css (its :root and the Small
text size): set anywhere else, one would shrink every label under it.

One layout check rides along, because the sizes scale it: a min-width of 20rem
or more (400 px at Extra Large) is capped by the screen, `min(…rem, 92vw)`, or
a dialog is wider than a phone and cut on both sides (Quick Weigh, the
Activity Log, the Quick-Swap confirm and both merge pickers were, in the
review; the browser proof is test_text_size_setting_e2e.py).

The ALLOWED list is short on purpose; each entry says why.

HEAD proof (dev 6e6bdd4 / c7dafaa, before the change; a throwaway worktree
with only this file copied in): RED. 77 hand-typed sizes under 13.6 px in 18
files, 46 of them under 12.8 px, the smallest `0.6rem` (9.6 px, the collapsed
IDLE / PRINTING); and no named sizes in global.css. The parametrized checks of
the scanner itself pass there too.
Review proof (feat/readability-2026-10-21 4729579, the scanner before the
review fix, run on this file's tables): 17 of the 18 new snippets came back []
(RED); the 18th, `--bs-badge-font-size`, it caught only by matching inside the
name. It also failed a size written in a comment, and had no check for a named
size set outside global.css. Today's tree is clean under both scanners.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parent.parent
FLOOR_PX = 13.6

SOURCES = (sorted((HUB / "static" / "css").glob("*.css"))
           + sorted((HUB / "static" / "js" / "modules").glob("*.js"))
           + sorted((HUB / "templates").rglob("*.html")))

# (path relative to inventory-hub, why its small sizes are not screen text)
ALLOWED = {
    "templates/components/label_spool.html":
        "the printed spool label: sized in pt for the physical P-touch label, never read on screen",
}

USE_A_NAME = "use a named size"

# A /* … */ comment (CSS, JS, a <style> or <script> block). Replaced by its own
# line breaks, so the line numbers in a failure stay right.
COMMENT = re.compile(r"/\*.*?\*/", re.S)

# Where a font size is written. The value starts after the colon, `=` or comma;
# in CSS it may be on the next line. A JS form is judged when its value is a
# string (`el.style.fontSize = cs.fontSize` copies a size, it doesn't set one).
SITE = re.compile(
    r"""(?:(?<![\w-])(?:--[\w-]*-)?font-size\s*:\s*"""            # CSS, an inline style; --bs-badge-font-size
    r"""|['"`]font-size['"`]\s*:\s*['"`]"""                       # { 'font-size': '…' }
    r"""|(?<![\w-])fontSize\s*[:=]\s*['"`]"""                     # el.style.fontSize = '…', { fontSize: '…' }
    r"""|setProperty\(\s*['"`]font-size['"`]\s*,\s*['"`]"""       # el.style.setProperty('font-size', '…')
    r"""|\[\s*['"`]font-size['"`]\s*\]\s*=\s*['"`]"""             # el.style['font-size'] = '…'
    r"""|\.css\(\s*['"`]font-size['"`]\s*,\s*['"`])"""            # $(el).css('font-size', '…')
    r"""(?P<v>[^;"'`}\n]*)""", re.I)
# The `font` shorthand: CSS `font: bold 0.7rem/1.2 …`, JS `{ font: '…' }` and
# `el.style.font = '…'` (never font-family / font-weight: the [:=] must follow).
SHORTHAND = re.compile(r"""(?<![\w-])font\s*[:=]\s*['"`]?(?P<v>[^;"'`}\n]*)""", re.I)

SIZE = re.compile(r"(?P<n>\d*\.?\d+)\s*(?P<u>rem|em|px|pt|%)(?![\w-])", re.I)
NAME = r"var\(\s*--fcc-fs-(?:label|small|row)\s*\)"
NAMED = re.compile(NAME, re.I)
# max() with a name is never under that name, whatever else it holds.
MAX_NAMED = re.compile(r"max\(\s*" + NAME + r"\s*,.*\)", re.I)
KEYWORDS = {"xx-small": 9.0, "x-small": 10.0, "small": 13.0, "smaller": 13.3}
FINE_KEYWORDS = {"inherit", "initial", "unset", "revert", "revert-layer", "medium", "large", "x-large",
                 "xx-large", "xxx-large", "larger"}
UNREADABLE = re.compile(r"\$\{|\b(?:calc|min|clamp|var|env|attr)\(", re.I)
# A named size set anywhere: CSS / an inline style, or JS setProperty.
NAME_SET = re.compile(r"""--fcc-fs-(?:label|small|row)\s*:|setProperty\(\s*['"`]--fcc-fs-""", re.I)


def _plain(value: str) -> str:
    return value.strip().lower().replace("!important", "").strip()


def size_px(value: str):
    """(px, None) for a hand-typed size, at a 16 px root and parent;
    (None, None) for a named size or a keyword that is big enough;
    (None, USE_A_NAME) for anything the check can't size."""
    v = _plain(value)
    if NAMED.fullmatch(v) or MAX_NAMED.fullmatch(v):
        return None, None
    if not v or UNREADABLE.search(v):
        return None, USE_A_NAME
    if v in KEYWORDS:
        return KEYWORDS[v], None
    if v in FINE_KEYWORDS:
        return None, None
    m = SIZE.fullmatch(v)
    if not m:
        return None, USE_A_NAME
    n, u = float(m.group("n")), m.group("u").lower()
    return {"rem": n * 16, "em": n * 16, "px": n, "pt": n * 4 / 3, "%": n * 16 / 100}[u], None


def shorthand_px(value: str):
    """The size in a `font:` shorthand ("bold 0.7rem/1.2 'Segoe UI'"), as
    size_px() answers it. A shorthand with no size at all (a system font,
    `inherit`) has nothing to judge."""
    v = _plain(value)
    if NAMED.search(v):
        if UNREADABLE.search(NAMED.sub("", v)) and not MAX_NAMED.search(v):
            return None, USE_A_NAME
        return None, None
    if UNREADABLE.search(v):
        return None, USE_A_NAME
    m = SIZE.search(v.split("/")[0])
    if m:
        return size_px(m.group(0))
    kw = next((k for k in KEYWORDS if re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", v)), None)
    return (KEYWORDS[kw], None) if kw else (None, None)


def strip_comments(text: str) -> str:
    return COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def offenders_in(text: str):
    """[(line number, the size as written, px or None)] in `text`: px for a
    hand-typed size under the floor, None for a size the check can't read."""
    text = strip_comments(text)
    out = []
    for pattern, judge in ((SITE, size_px), (SHORTHAND, shorthand_px)):
        for m in pattern.finditer(text):
            value = m.group("v")
            px, why = judge(value)
            line = text.count("\n", 0, m.start("v")) + 1
            if why:
                out.append((line, value.strip(), None))
            elif px is not None and px < FLOOR_PX - 0.01:
                out.append((line, value.strip(), round(px, 2)))
    return sorted(out, key=lambda o: o[0])


def name_sets_in(text: str):
    """[line numbers] where `text` sets one of the three named sizes."""
    text = strip_comments(text)
    return [text.count("\n", 0, m.start()) + 1 for m in NAME_SET.finditer(text)]


def test_no_hand_typed_font_size_is_under_the_floor():
    found = []
    for path in SOURCES:
        rel = path.relative_to(HUB).as_posix()
        if rel in ALLOWED:
            continue
        for line, value, px in offenders_in(path.read_text(encoding="utf-8")):
            if px is None:
                found.append(f"{rel}:{line}  font size {value!r}: the check can't read it, {USE_A_NAME}")
            else:
                found.append(f"{rel}:{line}  font size {value!r} = {px} px")
    assert not found, (
        f"{len(found)} font size(s) under {FLOOR_PX} px or unreadable. Use a named size instead: "
        "var(--fcc-fs-label) for a label in a pill or box (12.8 px), var(--fcc-fs-small) for "
        "text you read (13.6 px), var(--fcc-fs-row) for list rows (14.4 px), or max() of one:\n  "
        + "\n  ".join(found))


def test_every_allowed_file_still_exists():
    """An allowance for a file that is gone would hide nothing but rot."""
    for rel in ALLOWED:
        assert (HUB / rel).is_file(), rel


def test_the_named_sizes_are_defined_once_in_global_css():
    """The three names on :root, at the Standard size, and Bootstrap's badge and
    small text held to the rule (max() keeps a badge in a heading bigger)."""
    css = (HUB / "static" / "css" / "global.css").read_text(encoding="utf-8")
    root = re.search(r":root\s*\{([^}]*)\}", css)
    assert root, "global.css has no :root block"
    names = dict(re.findall(r"(--fcc-fs-[a-z]+)\s*:\s*([^;]+);", root.group(1)))
    assert names == {"--fcc-fs-label": "0.8rem", "--fcc-fs-small": "0.85rem", "--fcc-fs-row": "0.9rem"}, names
    # Set twice: on :root (Standard) and for the Small text size, nowhere else
    # (Large and Extra Large grow the root instead; test_text_size_setting_js.py
    # pins the values).
    small = re.search(r':root\[data-fcc-text-size="small"\]\s*\{([^}]*)\}', css)
    for name in ("--fcc-fs-label", "--fcc-fs-small", "--fcc-fs-row"):
        assert len(re.findall(re.escape(name) + r"\s*:", css)) == 2 and small and name in small.group(1), (
            f"{name} is set somewhere other than :root and the Small text size")
    assert re.search(r"\.badge\s*\{\s*--bs-badge-font-size:\s*max\(var\(--fcc-fs-label\),\s*0\.75em\);", css)
    assert re.search(r"\.small,\s*small,[^{]*\{\s*font-size:\s*max\(var\(--fcc-fs-small\),\s*0\.875em\);", css)


def test_the_named_sizes_are_set_nowhere_else():
    """A template, a module's CSS string, an inline style or a setProperty()
    that sets --fcc-fs-label (or -small / -row) shrinks every label under it,
    and the floor check reads only the names' uses. global.css sets each name
    twice (its :root and the Small text size; the test above pins where)."""
    found = []
    for path in SOURCES:
        rel = path.relative_to(HUB).as_posix()
        lines = name_sets_in(path.read_text(encoding="utf-8"))
        if rel == "static/css/global.css":
            assert len(lines) == 6, f"global.css sets the named sizes {len(lines)} times (lines {lines}), not 6"
            continue
        found += [f"{rel}:{ln}" for ln in lines]
    assert not found, "named sizes set outside global.css (set them only there):\n  " + "\n  ".join(found)


# A min-width this wide in rem is 400 px or more at Extra Large: a phone's
# whole screen. Uncapped, it beats a max-width in vw and a panel is cut on both
# sides where nothing scrolls (readability review, 2026-10-21: Quick Weigh,
# the Activity Log, the Quick-Swap confirm and both merge pickers).
WIDE_REM = 20
MIN_WIDTH = re.compile(r"""(?<![\w-])min-width\s*:\s*(?P<v>[^;"'`}\n]+)""", re.I)


def wide_min_widths_in(text: str):
    """[(line number, the min-width as written)]: a plain rem min-width of
    WIDE_REM or more, not capped by the screen (min(…, …vw))."""
    text = strip_comments(text)
    out = []
    for m in MIN_WIDTH.finditer(text):
        v = _plain(m.group("v"))
        n = re.fullmatch(r"(\d*\.?\d+)rem", v)
        if n and float(n.group(1)) >= WIDE_REM:
            out.append((text.count("\n", 0, m.start("v")) + 1, m.group("v").strip()))
    return out


def test_a_wide_min_width_is_capped_by_the_screen():
    found = []
    for path in SOURCES:
        rel = path.relative_to(HUB).as_posix()
        found += [f"{rel}:{ln}  min-width {v!r}" for ln, v in wide_min_widths_in(path.read_text(encoding="utf-8"))]
    assert not found, (
        f"min-widths of {WIDE_REM}rem or more with no cap (a phone at Extra Large cuts the panel on both sides); "
        "write min(<size>rem, 92vw):\n  " + "\n  ".join(found))


@pytest.mark.parametrize("snippet, n", [
    ("border-radius:8px;padding:0;min-width:23.75rem;", 1),
    ('style="min-width:26.25rem; max-width:33.75rem;"', 1),
    ("min-width:min(23.75rem,92vw);", 0),
    ("min-width:15rem;", 0),
    ("min-width: 120px;", 0),
])
def test_the_min_width_check(snippet, n):
    assert len(wide_min_widths_in(snippet)) == n, snippet


@pytest.mark.parametrize("snippet, px", [
    (".x { font-size: 0.7rem; }", 11.2),
    (".x { font-size:0.65rem !important; }", 10.4),
    ('<div style="font-size:0.72rem; color:#fff;">', 11.52),
    ("<span style='font-size: 11px'>", 11.0),
    ("${P} .tag { padding:0 7px; font-size:.8em; }", 12.8),
    (".lbl { font-size: 7pt; }", 9.33),
    ("el.style.fontSize = '0.75rem';", 12.0),
    ("Object.assign(el.style, { fontSize: '12px' });", 12.0),
    ("el.style.setProperty('font-size', '0.6rem');", 9.6),
    (".x { font: bold 0.7rem/1.2 'Segoe UI'; }", 11.2),
    (".x { font-size: x-small; }", 10.0),
    # Readability review (2026-10-21): forms the first scanner missed.
    (".x { font-size: 0.6rem /* why */; }", 9.6),
    (".x {\n    font-size:\n        0.6rem;\n}", 9.6),
    ("el.style.font = 'bold 0.6rem Segoe UI';", 9.6),
    ("Object.assign(el.style, { font: 'bold 0.6rem Segoe UI' });", 9.6),
    ("el.style['font-size'] = '0.6rem';", 9.6),
    ("$(el).css('font-size', '0.6rem');", 9.6),
    ("const s = { 'font-size': '0.6rem' };", 9.6),
    (".fcc-x .badge { --bs-badge-font-size: 0.6rem; }", 9.6),
])
def test_the_check_catches_every_way_of_writing_a_size(snippet, px):
    found = offenders_in(snippet)
    assert [f[2] for f in found] == [px], (snippet, found)


@pytest.mark.parametrize("snippet", [
    "<span style=\"font-size:min(var(--fcc-fs-small), 0.6rem)\">",
    ".x { font-size: calc(var(--fcc-fs-label) * .7); }",
    "`<span style=\"font-size:${compact ? '0.7rem' : '1rem'}\">`",
    ".x { font-size: calc(0.5rem + 2px); }",
    ".x { font-size: clamp(0.6rem, 1vw, 1rem); }",
    ".x { --chip: .6rem; } .x span { font-size: var(--chip); }",
    "el.style.fontSize = `${n}px`;",
    "el.style.font = `bold ${n}px Segoe UI`;",
    ".x { font: bold calc(var(--fcc-fs-small) - 2px) 'Segoe UI'; }",
    ".x { font-size: ; }",
])
def test_a_size_the_check_cannot_read_is_a_failure(snippet):
    """'use a named size': each of these can come out under the floor."""
    found = offenders_in(snippet)
    assert [f[2] for f in found] == [None], (snippet, found)


@pytest.mark.parametrize("snippet", [
    ".x { font-size: var(--fcc-fs-label); }",
    '<div style="font-size:var(--fcc-fs-small);">',
    ".badge { --bs-badge-font-size: max(var(--fcc-fs-label), 0.75em); }",
    ".x { font-size: max(var(--fcc-fs-small), 0.875em); }",
    ".x { font-size: 0.85rem; }",
    ".x { font-size: 0.9em; }",
    ".x { font-size: 14px; }",
    ".x { font-size: 1.1rem !important; }",
    ".x { font-size: inherit; }",
    ".x { font-size: larger; }",
    "el.style.fontSize = '1rem';",
    ".x { font-weight: bold; line-height: 0.7rem; }",
    ".x { font-family: 'Segoe UI'; font-weight: 700; }",
    ".x { font: inherit; }",
    ".x { font: bold var(--fcc-fs-small) 'Segoe UI'; }",
    "/* .x { font-size: 0.6rem; } was too small */ .x { font-size: 1rem; }",
    "@font-face { font-family: X; }",
])
def test_the_check_leaves_named_and_big_enough_sizes_alone(snippet):
    assert offenders_in(snippet) == [], snippet


@pytest.mark.parametrize("snippet, n", [
    (":root { --fcc-fs-label: .6rem; }", 1),
    ('<div style="--fcc-fs-small: 0.6rem;">', 1),
    ("el.style.setProperty('--fcc-fs-row', '0.6rem');", 1),
    (".x { font-size: var(--fcc-fs-label); }", 0),
    ("/* --fcc-fs-label: 0.8rem is the label size */", 0),
])
def test_the_check_finds_a_named_size_set_anywhere(snippet, n):
    assert len(name_sets_in(snippet)) == n, snippet
