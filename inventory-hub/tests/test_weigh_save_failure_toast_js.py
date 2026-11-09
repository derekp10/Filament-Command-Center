"""Group 54 review, R1-3 (2026-11-09): a weight the server refused says why, for
long enough to read, hermetic.

saveSpoolWeight (inv_weigh_out.js) is the page's only /api/spool/update caller:
a weigh-out row's save, the row's fallback when its details couldn't be read,
and the Quick-Weigh. When the write was refused it raised "Failed to update
weight" for showToast's default 2 s and never read the reason the route answers
({status: 'error', msg: 'Failed to update spool: <Spoolman's error>', error:
<Spoolman's error>}, the write-surface table's "surfaces LAST_SPOOLMAN_ERROR in
the error/msg response fields"); a save that got no answer it could read raised
"Error updating weight", 2 s too. CLAUDE.md asks 7 s at least for an error toast.
And nothing reached the Activity Log: the route logs a refused write only to
hub.log (state.logger), so a person who missed the toast had no record of it.

Now the toast is the route's `msg`, else its `error`, else "Failed to update
weight", and "Error updating weight" when no answer could be read, each for 7 s;
and the page writes the one Activity Log line (window.logClientEvent, ERROR),
naming the spool and saying what the toast said, escaped (the log is HTML).

Since review R4-2 the route puts `msg` in words ("Couldn't save Spool #57:
Spoolman didn't answer in time.", spoolman_api.refusal_words; pinned in
test_spool_update_refusal_words_54) and keeps the raw text in `error`. The page
shows whatever the route says, so the answers here keep the older shape too, and
test_the_log_line_keeps_the_raw_error_when_the_msg_doesnt_hold_it is the worded one.

Two harnesses: node's `vm` (test_core1_return_ejectall_js.run_js: showToast and
logClientEvent recorded with their arguments, so the 7 s is read exactly), and
the real weigh-out window in `isolated_page` (the real showToast and
logClientEvent: the words on screen, still up at 2.7 s, past the 2 s default and
its 300 ms fade, and the log line as posted).

Base proof (c2f4222): every test here is RED there.
"""
from __future__ import annotations

import json

import pytest

from test_auto_archive_switch_page_54_7_js import _open_list, _updates, weigh  # noqa: F401  (weigh: the fixture)
from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js
from test_quick_weigh_scan_js import press

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

# What the route answers for a write Spoolman refused (routes_inventory.api_spool_update).
SPOOLMAN_ERR = 'HTTP 422: {"detail": "used_weight <= initial_weight"}'
MSG = f"Failed to update spool: {SPOOLMAN_ERR}"


def _esc(text):
    """window.escHtml's rule, for the Activity Log line's text."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


# The save, with /api/spool/update answering `answer` (a refusal), or `kind`:
# 'no-answer' (the request failed: FCC down, the network) or 'not-json' (an error
# page, which r.json() can't read).
SAVE = """
const answer = __ANSWER__;
const KIND = __KIND__;
const orig = globalThis.fetch;
globalThis.fetch = (url, opts) => {
    if (String(url) !== '/api/spool/update') return orig(url, opts);
    __rec.fetches.push({ url: String(url), method: 'POST', body: JSON.parse(opts.body) });
    if (KIND === 'no-answer') return Promise.reject(new TypeError('Failed to fetch'));
    if (KIND === 'not-json') {
        return Promise.resolve({ ok: false, status: 500,
            json: () => Promise.reject(new SyntaxError("Unexpected token '<' in JSON at position 0")) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(answer) });
};
window.saveSpoolWeight(77, null, { used_weight: 960 }, false);
await __settle(80);
return { toasts: __rec.toasts, logs: __rec.logs,
         saves: __rec.fetches.filter((f) => f.url === '/api/spool/update').length };
"""


def _save(tmp_path, answer=None, kind="answer"):
    res = run_js(tmp_path, ["inv_weigh_out.js"],
                 SAVE.replace("__ANSWER__", json.dumps(answer)).replace("__KIND__", json.dumps(kind)))
    assert res["unhandled"] == [] and res["saves"] == 1, res
    return res


@needs_node
@pytest.mark.parametrize("answer, said", [
    ({"status": "error", "msg": MSG, "error": SPOOLMAN_ERR}, MSG),
    ({"status": "error", "error": SPOOLMAN_ERR}, SPOOLMAN_ERR),
    ({"status": "error"}, "Failed to update weight"),
], ids=["msg", "error-only", "no-reason"])
def test_a_refused_weight_says_the_servers_reason_for_7_seconds(tmp_path, answer, said):
    """RED: the toast is the route's `msg` (else its `error`, else "Failed to update
    weight"), an error toast for 7 s, and one Activity Log line (ERROR) names the
    spool and says the same, escaped. On the base: "Failed to update weight" for
    2 s whatever the route said, and no log line."""
    res = _save(tmp_path, answer)
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [(said, "error", 7000)], res
    assert res["logs"] == [{"msg": f"❌ Spool #77: {_esc(said)}", "level": "ERROR"}], res


@needs_node
def test_the_log_line_keeps_the_raw_error_when_the_msg_doesnt_hold_it(tmp_path):
    """RED: a route that words its `msg` for a person (as spoolman_api.refusal_words
    would) and keeps Spoolman's raw text in `error`: the toast shows the words,
    and the Activity Log line keeps the raw text after them, as CLAUDE.md asks of
    a log line. On the base: "Failed to update weight", no log line."""
    res = _save(tmp_path, {"status": "error", "msg": "Couldn't save the weight: Spoolman didn't answer in time.",
                           "error": "Read timed out. (read timeout=15)"})
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [
        ("Couldn't save the weight: Spoolman didn't answer in time.", "error", 7000)], res
    assert res["logs"] == [{"msg": "❌ Spool #77: " + _esc("Couldn't save the weight: Spoolman didn't answer in time."
                                                         " (Read timed out. (read timeout=15))"),
                            "level": "ERROR"}], res


@needs_node
@pytest.mark.parametrize("kind, why", [
    ("no-answer", "Failed to fetch"),
    ("not-json", "Unexpected token '<' in JSON at position 0"),
], ids=["no-answer", "not-json"])
def test_a_save_with_no_answer_it_can_read_says_so_for_7_seconds(tmp_path, kind, why):
    """RED: "Error updating weight" stays up 7 s (it was 2 s), and the Activity Log
    line says it with what went wrong, escaped. On the base: 2 s, no log line."""
    res = _save(tmp_path, kind=kind)
    assert [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]] == [
        ("Error updating weight", "error", 7000)], res
    assert res["logs"] == [{"msg": f"❌ Spool #77: Error updating weight ({_esc(why)})", "level": "ERROR"}], res


# The real page: /api/spool/update answers the refusal; every other request is the
# weigh-out harness's own stub (test_weigh_out_scan_focus_js.STUBS), which records
# each POST in window.__posts, /api/log_event's among them.
REFUSE = """(answer) => {
    const orig = window.fetch;
    window.fetch = (url, opts) => {
        if (!String(url).includes('/api/spool/update')) return orig(url, opts);
        window.__posts.push({ url: String(url), body: JSON.parse(opts.body) });
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(answer) });
    };
}"""


def _toasts(page):
    return page.evaluate("() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                         ".map((t) => t.innerText)")


def test_a_refused_row_save_shows_the_servers_words_on_the_page(weigh):
    """RED: #57's reading saved from its weigh-out row and refused by the server:
    the toast on screen reads the route's words as text (its '<' and quotes
    whole) and is still up 2.7 s later, past the 2 s default and its fade; the
    Activity Log line is posted, escaped; and #57's box is open again with its
    reading, for another try (a control). On the base: "Failed to update weight",
    gone after 2.3 s, and no log line."""
    page = weigh
    page.evaluate(REFUSE, {"status": "error", "msg": MSG, "error": SPOOLMAN_ERR})
    _open_list(page)
    press(page, "425", 150)
    page.wait_for_function("() => window.__posts.some((p) => p.url === '/api/spool/update')", timeout=5000)
    page.wait_for_function("() => document.querySelector('#toast-container .toast-msg.toast-error')", timeout=5000)
    assert _updates(page) == [{"id": 57, "updates": {"used_weight": 325}, "auto_archive": True}]
    assert _toasts(page) == [MSG], _toasts(page)
    page.wait_for_timeout(2700)
    assert _toasts(page) == [MSG], "the error toast must still be up after 2.7 s"
    logs = page.evaluate("() => window.__posts.filter((p) => p.url === '/api/log_event').map((p) => p.body)")
    assert logs == [{"msg": f"❌ Spool #57: {_esc(MSG)}", "level": "ERROR"}], logs
    box = page.evaluate("() => { const b = document.querySelector('.weigh-input[data-id=\"57\"]');"
                        " return [b.disabled, b.value]; }")
    assert box == [False, "425"], box
    assert page.evaluate("() => window.__errors") == []
