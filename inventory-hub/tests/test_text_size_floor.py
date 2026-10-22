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

The ALLOWED list is short on purpose; each entry says why.

HEAD proof (dev 6e6bdd4 / c7dafaa, before the change; a throwaway worktree
with only this file copied in): RED. 77 hand-typed sizes under 13.6 px in 18
files, 46 of them under 12.8 px, the smallest `0.6rem` (9.6 px, the collapsed
IDLE / PRINTING); and no named sizes in global.css. The parametrized checks of
the scanner itself pass there too.
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

# A font size, wherever it is written: a CSS declaration or an inline style
# (`font-size: 0.7rem`), the `font` shorthand, a JS style property
# (`el.style.fontSize = '11px'`, `{ fontSize: '0.7rem' }`) or setProperty.
DECL = re.compile(
    r"""(?:font-size\s*:\s*|fontSize\s*[:=]\s*['"`]|setProperty\(\s*['"]font-size['"]\s*,\s*['"])"""
    r"""(?P<v>[^;"'`}\n]+)""", re.I)
SHORTHAND = re.compile(r"""(?<![-\w])font\s*:\s*(?P<v>[^;"'`}\n]+)""", re.I)
SIZE = re.compile(r"(?P<n>\d*\.?\d+)\s*(?P<u>rem|em|px|pt|%)(?![\w-])", re.I)
KEYWORDS = {"xx-small": 9.0, "x-small": 10.0, "small": 13.0, "smaller": 13.3}


def size_px(value: str):
    """The px a hand-typed size comes to at a 16 px root and parent, or None
    when the value is a name (var(--fcc-fs-…)) or isn't a plain size."""
    v = value.strip().lower().replace("!important", "").strip()
    if "var(--fcc-fs-" in v:
        return None
    if v in KEYWORDS:
        return KEYWORDS[v]
    m = SIZE.fullmatch(v)
    if not m:
        return None
    n, u = float(m.group("n")), m.group("u").lower()
    return {"rem": n * 16, "em": n * 16, "px": n, "pt": n * 4 / 3, "%": n * 16 / 100}[u]


def shorthand_px(value: str):
    """The size in a `font:` shorthand ("bold 0.7rem/1.2 'Segoe UI'")."""
    if "var(--fcc-fs-" in value.lower():
        return None
    m = SIZE.search(value.split("/")[0])
    return size_px(m.group(0)) if m else None


def offenders_in(text: str):
    """[(line number, the size as written, px)] under the floor in `text`."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in DECL.finditer(line):
            px = size_px(m.group("v"))
            if px is not None and px < FLOOR_PX - 0.01:
                out.append((i, m.group("v").strip(), round(px, 2)))
        for m in SHORTHAND.finditer(line):
            px = shorthand_px(m.group("v"))
            if px is not None and px < FLOOR_PX - 0.01:
                out.append((i, m.group("v").strip(), round(px, 2)))
    return out


def test_no_hand_typed_font_size_is_under_the_floor():
    found = []
    for path in SOURCES:
        rel = path.relative_to(HUB).as_posix()
        if rel in ALLOWED:
            continue
        for line, value, px in offenders_in(path.read_text(encoding="utf-8")):
            found.append(f"{rel}:{line}  font size {value!r} = {px} px")
    assert not found, (
        f"{len(found)} hand-typed font size(s) under {FLOOR_PX} px. Use a named size instead: "
        "var(--fcc-fs-label) for a label in a pill or box (12.8 px), var(--fcc-fs-small) for "
        "text you read (13.6 px), var(--fcc-fs-row) for list rows (14.4 px):\n  " + "\n  ".join(found))


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
])
def test_the_check_catches_every_way_of_writing_a_size(snippet, px):
    found = offenders_in(snippet)
    assert [f[2] for f in found] == [px], (snippet, found)


@pytest.mark.parametrize("snippet", [
    ".x { font-size: var(--fcc-fs-label); }",
    '<div style="font-size:var(--fcc-fs-small);">',
    ".badge { --bs-badge-font-size: max(var(--fcc-fs-label), 0.75em); }",
    ".x { font-size: 0.85rem; }",
    ".x { font-size: 0.9em; }",
    ".x { font-size: 14px; }",
    ".x { font-size: 1.1rem !important; }",
    "el.style.fontSize = '1rem';",
    ".x { font-weight: bold; line-height: 0.7rem; }",
])
def test_the_check_leaves_named_and_big_enough_sizes_alone(snippet):
    assert offenders_in(snippet) == [], snippet
