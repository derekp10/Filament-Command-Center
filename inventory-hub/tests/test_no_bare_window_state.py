"""The page's `state` is never read as `window.state` alone (Group 64.2 (4), 2026-11-20).

inv_core.js declares the page's state with `let state = {...}` at the top of a
classic script: a script-global binding, shared by every script on the page, and
never a property of `window`. So `window.state` is undefined in the browser. The
node-vm harnesses put `state` on `globalThis` instead (their preludes), where
`window.state` finds it, so a module that reads `window.state` passes every
hermetic test and does nothing in the browser: the review card's picker scan read
its scan buffer that way, and only the browser check caught it.

Every module reads it by name, with the harness form as the fallback:
`(typeof state !== 'undefined') ? state : window.state`. This file fails on any
other `window.state` in the page's scripts. Offline, no browser.
"""
from __future__ import annotations

import re
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
FALLBACK = re.compile(r"""\(typeof state !== (['"])undefined\1\) \? state : window\.state""")
BARE = re.compile(r"window\.state\b")


def _page_sources():
    for p in sorted((HUB / "static" / "js").rglob("*.js")):
        yield p
    for p in sorted((HUB / "templates").rglob("*.html")):
        yield p


def test_the_pages_state_is_never_read_as_a_window_property_alone():
    bad = []
    for p in _page_sources():
        text = p.read_text(encoding="utf-8", errors="replace")
        allowed = {m.end() - len("window.state") for m in FALLBACK.finditer(text)}
        for m in BARE.finditer(text):
            if m.start() not in allowed:
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{p.relative_to(HUB)}:{line}")
    assert not bad, (
        "window.state is undefined in the browser (inv_core.js's `let state` is no window "
        "property); read it by name: (typeof state !== 'undefined') ? state : window.state. "
        f"Found: {bad}")


def test_the_canary_sees_a_bare_read():
    text = "const a = (typeof state !== 'undefined') ? state : window.state;\nconst b = window.state.x;\n"
    allowed = {m.end() - len("window.state") for m in FALLBACK.finditer(text)}
    bare = [m.start() for m in BARE.finditer(text) if m.start() not in allowed]
    assert len(bare) == 1 and text[bare[0]:].startswith("window.state.x")
