"""Group 62.4: every overlay keeps Tab inside it, or says whose handler does, offline.

mountOverlay's `trapTab` keeps Tab and Shift+Tab inside the overlay on top. It was
opt-in, and 24 of its 29 callers didn't pass it, so Tab walked out of Bulk Move's panel,
the empty-weight prompt and the other large overlays onto the page behind, where nothing
can be pressed and nobody sees the focus. It is the default now. An overlay that cycles
Tab itself on the document must opt out (`trapTab: false`), or one Tab moves the focus
twice: mountOverlay's handler stops only propagation, so a handler of its own on the
document still runs. Such a call says so with an `// own-tab:` comment naming its
handler, inside the call.

Red when:
- overlay_mount.js no longer makes trapTab the default;
- a `mountOverlay({` call in static/js passes `trapTab: false` with no `// own-tab:`
  comment inside the call (add the comment, naming the handler that cycles Tab, or drop
  the opt-out);
- a call can't be read (its closing `});` not found at its own indentation): teach the
  canary, or format the call as the others are.

What it can't see: a handler of its own that cycles Tab on an overlay that didn't opt out
(it is caught by its own tests: one Tab moving one step, as
test_question_keys_and_tab_62_4_js.py pins for the four that cycle Tab today), and a
mount by another name.
"""
from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "static" / "js"
MOUNT = JS / "modules" / "overlay_mount.js"
CALL = re.compile(r"mountOverlay\(\{")


def _calls(src: str, name: str) -> list[tuple[int, str]]:
    """(line number, text) of each `mountOverlay({ … })` call in `src`: from its line to
    the next line holding only `});` at the same indentation."""
    lines = src.replace("\r\n", "\n").split("\n")
    out = []
    for i, line in enumerate(lines):
        if not CALL.search(line) or line.lstrip().startswith("//"):
            continue
        indent = line[:len(line) - len(line.lstrip())]
        end = next((j for j in range(i + 1, min(i + 400, len(lines)))
                    if re.fullmatch(re.escape(indent) + r"\}\);\s*(//.*)?", lines[j])), None)
        assert end is not None, (f"{name}:{i + 1}: couldn't find this mountOverlay call's closing `}});` "
                                 "at its own indentation: format it as the others are, or teach the canary")
        out.append((i + 1, "\n".join(lines[i:end + 1])))
    return out


def _offenders(src: str, name: str) -> list[str]:
    return [f"{name}:{n}" for n, text in _calls(src, name)
            if re.search(r"\btrapTab\s*:\s*false\b", text) and "// own-tab:" not in text]


def test_trap_tab_is_the_default():
    src = MOUNT.read_text(encoding="utf-8")
    assert re.search(r"const trapTab = o\.trapTab !== false;", src), (
        "overlay_mount.js: trapTab is no longer the default (`const trapTab = o.trapTab !== false;`)")


def test_every_opt_out_names_the_handler_that_cycles_tab():
    files = sorted(JS.rglob("*.js"))
    assert files, JS
    calls = 0
    offenders = []
    for path in files:
        src = path.read_text(encoding="utf-8")
        name = str(path.relative_to(JS)).replace("\\", "/")
        calls += len(_calls(src, name))
        offenders += _offenders(src, name)
    assert calls >= 25, f"read only {calls} mountOverlay calls under static/js: is the canary still reading them?"
    assert not offenders, (
        "These mountOverlay calls pass `trapTab: false` with no `// own-tab:` comment saying which "
        f"handler of their own cycles Tab: {offenders}. Add the comment inside the call, or drop the "
        "opt-out (trapTab is the default: Tab stays inside the overlay on top).")


def test_the_canary_sees_what_it_should():
    """Its own reading, on a sample: an opt-out with no comment is red; with the comment,
    a default call, and a call mentioned in a comment are not."""
    sample = "\n".join([
        "    const a = window.mountOverlay({",
        "        id: 'a',",
        "        trapTab: false,",
        "    });",
        "    const b = window.mountOverlay({",
        "        id: 'b',",
        "        // own-tab: b's keydown handler cycles Tab",
        "        trapTab: false,",
        "    });",
        "    const c = window.mountOverlay({ id: 'c',",
        "        content: `<div>${x}</div>`,",
        "    });",
        "    // window.mountOverlay({ trapTab: false })",
    ])
    assert [n for n, _ in _calls(sample, "s.js")] == [1, 5, 10]
    assert _offenders(sample, "s.js") == ["s.js:1"]
