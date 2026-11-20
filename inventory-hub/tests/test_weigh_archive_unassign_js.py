"""The weigh page after a save that archived a spool: no second request, and a word
when FCC couldn't take the spool off its place, hermetic.

History. Group 54 review R4-1 (2026-11-09): saveSpoolWeight (inv_weigh_out.js)
archived a spool weighed to 0 g ("Auto Archive & Eject if Empty") and then posted
/api/manage_contents force_unassign, with `confirm_active_print: true`, reading its
answer: when FCC couldn't read the spool before the save (review R1-1), that
request was what took it off its place. It logged a redundant "🗑️ Force
Unassigned" WARNING line on every weigh to empty (Group 54 review R5-5), and a tab
closed before it went left the spool archived on its head.

Groups 63.2 / 63.4 (2026-11-18): the take-off is the save's own. /api/spool/update
takes off a spool its write archived in place, from the record Spoolman answered
(test_archive_takeoff_63_2, test_archive_on_remaining_weight_54_6), and the page
posts nothing after the save. A take-off that failed comes back as `still_at`: FCC
wrote the spool down and keeps trying, and its WARNING line is the server's, so the
page raises a 7 s warning naming the place and logs nothing of its own. When the
archive also asks for the filament's empty weight, the prompt over the toast layer
gets the same sentence as its notice (review R5-1).

PINS UPDATED DELIBERATELY (63.2 / 63.4): this file pinned the force_unassign post,
its `confirm_active_print`, and the page's own WARNING line. The tests marked RED
fail on e1b22f4 (the branch's base).

Harness: node's `vm` (test_core1_return_ejectall_js.run_js), showToast and
logClientEvent recorded with their arguments.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

# The weigh save of #77 to 0 g with the switch on (the weigh-out list's Net row, or
# the Quick-Weigh): /api/spool/update answers UPDATE; any other request answers {}.
SAVE = """
const UPDATE = __UPDATE__;
window.__respond = (url) => {
    if (url === '/api/spool/update') return { body: UPDATE };
    return { body: {} };
};
window.saveSpoolWeight(77, 0, null, true, null, { archiveSwitch: true, empties: true, wasArchived: false });
await __settle(80);
return { toasts: __rec.toasts, logs: __rec.logs,
         posts: __rec.fetches.filter((f) => f.method === 'POST').map((f) => [f.url, f.body]) };
"""

ARCHIVED_OFF = {"status": "success", "auto_archived": True, "needs_empty_weight_prompt": False,
                "filament_id": None, "location_now": ""}
STILL_AT_XL1 = dict(ARCHIVED_OFF, location_now="XL-1", still_at="XL-1")
UPDATED = ("Updated Spool #77", "success", 2000)
SAID = "Spool #77 is archived but still at XL-1: FCC couldn't take it off there, and keeps trying."


def _save(tmp_path, update):
    res = run_js(tmp_path, ["inv_weigh_out.js"], SAVE.replace("__UPDATE__", json.dumps(update)))
    assert res["unhandled"] == [], res
    return res


def _toasts(res):
    return [(t["msg"], t["type"], t["duration"]) for t in res["toasts"]]


@needs_node
@pytest.mark.parametrize("update", [ARCHIVED_OFF, STILL_AT_XL1], ids=["taken-off", "still-at"])
def test_a_save_that_archived_posts_no_second_request(tmp_path, update):
    """RED: the save is the only request; the take-off is the route's (63.2 / 63.4).
    On the base the page posted force_unassign after every save that archived."""
    res = _save(tmp_path, update)
    assert res["posts"] == [["/api/spool/update", {"id": 77, "updates": {"remaining_weight": 0, "archived": True},
                                                   "auto_archive": True}]], res


@needs_node
def test_a_take_off_that_failed_is_said_and_the_server_keeps_the_line(tmp_path):
    """RED: `still_at` raises the 7 s warning naming the place; the WARNING line is
    the server's, so the page logs nothing. On the base the page read
    force_unassign's answer, and logged its own line."""
    res = _save(tmp_path, STILL_AT_XL1)
    assert _toasts(res) == [UPDATED, (SAID, "warning", 7000)], res
    assert res["logs"] == [], res


@needs_node
def test_a_place_in_the_warning_reads_as_typed(tmp_path):
    """The toast is text (showToast's innerText), so a free-text place reads as typed."""
    res = _save(tmp_path, dict(STILL_AT_XL1, location_now="Shelf <2> & Co", still_at="Shelf <2> & Co"))
    said = "Spool #77 is archived but still at Shelf <2> & Co: FCC couldn't take it off there, and keeps trying."
    assert _toasts(res) == [UPDATED, (said, "warning", 7000)], res


@needs_node
@pytest.mark.parametrize("update", [ARCHIVED_OFF, dict(ARCHIVED_OFF, still_at=""),
                                    dict(ARCHIVED_OFF, location_now="XL-1")],
                         ids=["off", "blank-still-at", "location-only"])
def test_control_a_spool_the_save_took_off_says_only_updated(tmp_path, update):
    """Control: no `still_at` (or a blank one) means the save took the spool off its
    place, so its toast is the only word and nothing is logged. `location_now`
    alone (an FCC from before 63.2) asks nothing of the page."""
    res = _save(tmp_path, update)
    assert _toasts(res) == [UPDATED], res
    assert res["logs"] == [], res


# ---- the empty-weight prompt says it too (review R5-1) ----------------------------------------------------

# The same save, with the archive answer asking for the filament's empty weight: the
# page opens showArchiveEmptyWeightPrompt 400 ms after the save, stubbed here to
# record what it was given.
PROMPT_SAVE = """
const UPDATE = __UPDATE__;
window.__respond = (url) => {
    if (url === '/api/spool/update') return { body: UPDATE };
    return { body: {} };
};
const prompts = [];
window.showArchiveEmptyWeightPrompt = (sid, fid, prefill, opts) => {
    prompts.push({ sid, fid, notice: (opts && opts.notice) === undefined ? 'undefined' : opts.notice });
};
window.saveSpoolWeight(77, 0, null, true, null, { archiveSwitch: true, empties: true, wasArchived: false });
await __settle(700);
return { toasts: __rec.toasts, prompts };
"""


def _prompt_save(tmp_path, update):
    res = run_js(tmp_path, ["inv_weigh_out.js"], PROMPT_SAVE.replace("__UPDATE__", json.dumps(update)))
    assert res["unhandled"] == [], res
    return res


@needs_node
def test_the_empty_weight_prompt_says_the_spool_is_still_on_its_place(tmp_path):
    """RED on e1b22f4 (the words and their source are new): the prompt that asks for
    the filament's empty weight opens over the toast layer, so it says the 7 s
    warning's sentence too."""
    res = _prompt_save(tmp_path, dict(STILL_AT_XL1, needs_empty_weight_prompt=True, filament_id=5))
    assert res["prompts"] == [{"sid": 77, "fid": 5, "notice": SAID}], res
    assert (SAID, "warning", 7000) in _toasts(res), res


@needs_node
def test_control_a_prompt_after_a_save_that_took_it_off_has_no_notice(tmp_path):
    res = _prompt_save(tmp_path, dict(ARCHIVED_OFF, needs_empty_weight_prompt=True, filament_id=5))
    assert [p["notice"] for p in res["prompts"]] in ([None], ["undefined"]), res
