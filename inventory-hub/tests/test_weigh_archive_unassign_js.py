"""Group 54 review R4-1 (2026-11-09): the weigh page's own unassign after an archive
answers the print question itself, and says when the spool is still on its place,
hermetic.

saveSpoolWeight (inv_weigh_out.js) archives a spool weighed to 0 g ("Auto Archive
& Eject if Empty") and then posts /api/manage_contents force_unassign. When FCC
read the spool, update_spool's archive edge has already taken it off its place,
with no print question (a spool weighed empty is in the person's hand, not
feeding a head), and the request finds it Unassigned. Since review R1-1 the edge
doesn't run on a spool FCC couldn't read: the write archives it where it is, and
this request is what takes it off. On a printing head force_unassign asks first
(`require_confirm`), and the page read nothing back: `.then(() => finalize())`
toasted "Updated Spool #57" and left an archived spool on the head, which every
in-stock reader shows as empty, its single-slot box still bound to it.

Now the request carries `confirm_active_print: true`, the answer the archive edge
gives in the same case, and the page reads its answer: one that doesn't say
`success` while the save's answer had the spool on a place (`location_now`, the
route's, review R4-1) raises a 7 s warning naming that place and writes one
WARNING Activity Log line with the reason, escaped. A spool the archive already
took off its place (`location_now` '') needs no warning whatever the request
answers. The server half, the route's `location_now` and force_unassign taking an
unread spool off a printing head, is pinned in test_archive_on_remaining_weight_54_6.

Harness: node's `vm` (test_core1_return_ejectall_js.run_js), showToast and
logClientEvent recorded with their arguments.

Base proof (01ef59e): every test marked RED fails there; the controls pass.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

# The weigh save of #77 to 0 g with the switch on (the weigh-out list's Net row, or
# the Quick-Weigh): /api/spool/update answers UPDATE, force_unassign answers OFF,
# or fails with no answer ('no-answer').
SAVE = """
const UPDATE = __UPDATE__;
const OFF = __OFF__;
const orig = globalThis.fetch;
globalThis.fetch = (url, opts) => {
    if (String(url) === '/api/manage_contents' && OFF === 'no-answer') {
        __rec.fetches.push({ url: String(url), method: 'POST', body: JSON.parse(opts.body) });
        return Promise.reject(new TypeError('Failed to fetch'));
    }
    return orig(url, opts);
};
window.__respond = (url) => {
    if (url === '/api/spool/update') return { body: UPDATE };
    if (url === '/api/manage_contents') return { body: OFF };
    return { body: {} };
};
window.saveSpoolWeight(77, 0, null, true, null, { archiveSwitch: true, empties: true, wasArchived: false });
await __settle(80);
return { toasts: __rec.toasts, logs: __rec.logs,
         posts: __rec.fetches.filter((f) => f.method === 'POST').map((f) => [f.url, f.body]) };
"""

ARCHIVED_AT_XL1 = {"status": "success", "auto_archived": True, "needs_empty_weight_prompt": False,
                   "filament_id": None, "location_now": "XL-1"}
ARCHIVED_OFF = dict(ARCHIVED_AT_XL1, location_now="")
UPDATED = ("Updated Spool #77", "success", 2000)


def _save(tmp_path, update, off):
    res = run_js(tmp_path, ["inv_weigh_out.js"],
                 SAVE.replace("__UPDATE__", json.dumps(update)).replace("__OFF__", json.dumps(off)))
    assert res["unhandled"] == [], res
    assert [p[0] for p in res["posts"]] == ["/api/spool/update", "/api/manage_contents"], res
    return res


def _toasts(res):
    return [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]]


def _esc(text):
    """window.escHtml's rule (the page's own fallback with no inv_core.js loaded)."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


@needs_node
def test_the_archives_unassign_answers_the_print_question_itself(tmp_path):
    """RED: the request after the archive carries `confirm_active_print: true`, so a
    printing head doesn't stop it (the archive edge never asks on the same weigh).
    On the base the body had no such key, and a printing head answered a question
    nobody read."""
    res = _save(tmp_path, ARCHIVED_AT_XL1, {"success": True})
    assert res["posts"][0][1] == {"id": 77, "updates": {"remaining_weight": 0, "archived": True},
                                  "auto_archive": True}, res
    assert res["posts"][1][1] == {"action": "force_unassign", "spool_id": 77, "location": "",
                                  "confirm_active_print": True}, res


@needs_node
@pytest.mark.parametrize("off, why", [
    ({"success": False, "msg": "DB Update Failed"}, "DB Update Failed"),
    ("no-answer", "Failed to fetch"),
    ({"success": False, "require_confirm": True, "confirm_type": "active_print",
      "msg": "XL is PRINTING — force-unassigning from this toolhead will disrupt the print."},
     "XL is PRINTING — force-unassigning from this toolhead will disrupt the print."),
], ids=["refused", "no-answer", "asks"])
def test_an_unassign_that_fails_says_where_the_spool_still_is(tmp_path, off, why):
    """RED: the weight saved, so "Updated Spool #77" stands, and a 7 s warning says
    the spool is archived but still at XL-1; one WARNING line in the Activity Log
    says the same with the reason. On the base: "Updated Spool #77" alone, nothing
    logged, and the spool left archived on its head."""
    res = _save(tmp_path, ARCHIVED_AT_XL1, off)
    said = "Spool #77 is archived but still at XL-1: FCC couldn't take it off there."
    assert _toasts(res) == [UPDATED, (said, "warning", 7000)], res
    assert res["logs"] == [{"msg": "⚠️ " + _esc(f"{said[:-1]} ({why})"), "level": "WARNING"}], res


@needs_node
def test_a_place_in_the_warning_is_escaped_in_the_log(tmp_path):
    """RED: a Spoolman location is free text, and the Activity Log is HTML: the
    place is escaped in the log line (the toast is text, so it reads as typed)."""
    res = _save(tmp_path, dict(ARCHIVED_AT_XL1, location_now="Shelf <2> & Co"),
                {"success": False, "msg": "DB Update Failed"})
    said = "Spool #77 is archived but still at Shelf <2> & Co: FCC couldn't take it off there."
    assert _toasts(res) == [UPDATED, (said, "warning", 7000)], res
    assert res["logs"] == [{"msg": "⚠️ Spool #77 is archived but still at Shelf &lt;2&gt; &amp; Co: "
                                   "FCC couldn&#39;t take it off there (DB Update Failed)", "level": "WARNING"}], res


@needs_node
def test_with_no_place_named_the_warning_says_its_place(tmp_path):
    """RED: an answer naming no place (an FCC from before review R4-1) and a request
    that fails: the warning can't name the place, so it says "its place"."""
    update = {k: v for k, v in ARCHIVED_AT_XL1.items() if k != "location_now"}
    res = _save(tmp_path, update, {"success": False, "msg": "DB Update Failed"})
    said = "Spool #77 is archived, but FCC couldn't take it off its place."
    assert _toasts(res) == [UPDATED, (said, "warning", 7000)], res
    assert res["logs"] == [{"msg": "⚠️ " + _esc(f"{said[:-1]} (DB Update Failed)"), "level": "WARNING"}], res


@needs_node
def test_control_an_unassign_that_lands_says_only_updated(tmp_path):
    """Control (green on the base too): the request lands, so the save's own toast
    is the only word, and nothing is logged by the page."""
    res = _save(tmp_path, ARCHIVED_AT_XL1, {"success": True})
    assert _toasts(res) == [UPDATED], res
    assert res["logs"] == [], res


@needs_node
@pytest.mark.parametrize("off", [{"success": False, "msg": "DB Update Failed"}, "no-answer"],
                         ids=["refused", "no-answer"])
def test_control_a_spool_the_archive_took_off_already_needs_no_warning(tmp_path, off):
    """Control (green on the base too): the save's answer has the spool Unassigned
    (the archive edge took it off its place), so a request that then fails changes
    nothing a person needs to know: no warning, no line."""
    res = _save(tmp_path, ARCHIVED_OFF, off)
    assert _toasts(res) == [UPDATED], res
    assert res["logs"] == [], res
