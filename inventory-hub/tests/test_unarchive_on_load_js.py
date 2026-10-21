"""The browser half of "an archived spool with filament on record is un-archived
to load it" (Derek, 2026-10-20), under node's `vm`: the REAL inv_core.js (and
inv_quickswap.js for the tap).

window.noteUnarchived warns once per un-archived spool, 7 s, whichever shape the
door's answer has (`unarchived` at the top for /api/smart_move and
manage_contents add, on `smart_move` for a slot scan and Quick-Swap, on
`location_result` for the wizard). takeIntoBuffer calls it, so every door that
completes a move warns; the Quick-Swap tap, which takes nothing into the buffer,
calls it itself.

Base proof (dev 2ec9f46): noteUnarchived doesn't exist there, so every test fails.
"""
from __future__ import annotations

import json
from pathlib import Path

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE, QS

MODULES = Path(__file__).resolve().parent.parent / "static" / "js" / "modules"
U = [{"id": 57, "left_g": 300.0, "head": "XL-1"}]
WARN = "⚠️ #57 was archived with 300 g left on its record: FCC un-archived it to load it onto XL-1. Weigh it if that's off."


def _js(v):
    return json.dumps(v)


def _run(tmp_path, modules, body):
    res = run_js(tmp_path, modules, PRELUDE + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def test_every_answer_shape_warns_once(tmp_path):
    res = _run(tmp_path, ["inv_core.js"], f"""
const top = {{ status: 'success', failures: {{}}, unarchived: {_js(U)} }};
window.takeIntoBuffer(top);
window.takeIntoBuffer(top);          // the same answer again: no second warning
const a = toasts().length;
window.takeIntoBuffer({{ action: 'assignment_done', smart_move: {{ unarchived: {_js(U)} }} }});
const b = toasts().length;
window.takeIntoBuffer({{ success: true, location_result: {{ unarchived: {_js(U)} }} }});
const c = toasts().length;
window.takeIntoBuffer({{ status: 'success', failures: {{}} }});   // nothing un-archived
return {{ a, b, c, d: toasts().length, all: toasts() }};
""")
    assert (res["a"], res["b"], res["c"], res["d"]) == (1, 2, 3, 3), res
    assert res["all"][0] == {"msg": WARN, "type": "warning"}, res["all"]


def test_the_quickswap_tap_warns_too(tmp_path):
    done = {"action": "quickswap_done", "moved": 57, "toolhead": "XL-1", "box": "LR-MDB-1", "slot": "1",
            "smart_move": {"status": "success", "failures": {}, "unarchived": U}}
    res = _run(tmp_path, QS, f"""
window.attachConfirmQRs = null;
answerWith('/api/quickswap', [{_js(done)}]);
const card = {{ dataset: {{ box: 'LR-MDB-1', slot: '1', toolhead: 'XL-1', spoolId: '57', spoolLabel: '#57' }},
               hasAttribute: () => false, querySelector: () => null }};
window.quickSwapTap(card);
await __settle(150);
const yes = (__overlayEls[__overlayEls.length - 1] || {{ querySelector: () => null }}).querySelector('#fcc-quickswap-yes');
if (yes && yes.onclick) yes.onclick();
await __settle(200);
return {{ toasts: toasts() }};
""")
    assert {"msg": WARN, "type": "warning"} in res["toasts"], res["toasts"]


def test_the_warning_is_a_seven_second_one():
    """inv_core.js's toast draws into the page (no duration to read under vm)."""
    src = (MODULES / "inv_core.js").read_text(encoding="utf-8")
    body = src[src.index("window.noteUnarchived = "):src.index("window.takeIntoBuffer = ")]
    assert "'warning', 7000" in body, body
    tib = src[src.index("window.takeIntoBuffer = "):]
    assert "window.noteUnarchived(a)" in tib[:400], tib[:400]
