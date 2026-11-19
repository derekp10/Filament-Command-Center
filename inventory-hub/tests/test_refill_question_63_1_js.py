"""Group 63.1, the page half: a refill after a toolhead asks where the spool goes,
hermetic.

Derek, 2026-11-18: *"I think if we ask on a spool correction that adds weight back,
to either place it back where it was (Possibly a toolhead) or just assign to the
room for now, or possibly scann/select a new location from a list"*, then *"only
after a tool head"*. The server moves such a spool nowhere and answers
`refill_ask` {place, room, held_by} (test_archive_note_refill_63_1,
test_one_spool_per_toolhead_42_3); window.askRefillPlace (inv_details.js) asks:
Back on the head (Force Location's move, window.fccForceMove, with
`expected_residents: []`; greyed out when another spool is there now), In its room
for now, Pick a place… (Force Location's list), or Leave it Unassigned (also
Escape and a bare CMD:CANCEL). A place's label scanned while it is open puts the
spool there; the answers that move take no click for 700 ms after it opens.

Every test is RED on e1b22f4 (the question is new). Harness: node's `vm`
(test_core1_return_ejectall_js.run_js), the stub mountOverlay wrapped to keep the
options it was given.
"""
from __future__ import annotations

import json

import pytest

from test_core1_return_ejectall_js import NODE, NODE_MISSING_MSG, run_js

needs_node = pytest.mark.skipif(NODE is None, reason=NODE_MISSING_MSG)

PRELUDE = r"""
// inv_core.js, when loaded, replaces the harness's fetchT with one that needs AbortSignal.
window.fetchT = (u, o) => window.fetch(u, o);
const __mounts = [];
const __stubMount = window.mountOverlay;
window.mountOverlay = (opts) => { const h = __stubMount(opts); __mounts.push({ opts, el: h.element }); return h; };
const last = () => __mounts[__mounts.length - 1];
const el = (sel) => last().el.querySelector(sel);
const posts = () => __rec.fetches.filter((f) => f.method === 'POST').map((f) => [f.url, f.body]);
const opened = [];
window.promptEditLocation = (sid, loc, o) => opened.push({ sid, loc, fromCard: !!(o && o.fromCard) });
window.__respond = (url) => {
    if (url === '/api/manage_contents') return { body: { status: 'success' } };
    if (url === '/api/locations') return { body: [] };
    return { body: {} };
};
"""


def _run(tmp_path, body, modules=("inv_details.js",)):
    res = run_js(tmp_path, list(modules), PRELUDE + body)
    assert res["unhandled"] == [], res
    return res


ASK = {"place": "XL-3", "room": "LR", "held_by": []}


@needs_node
def test_it_offers_the_head_the_room_a_pick_and_leaving_it_and_opens_on_leaving_it(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
const m = last();
return {{ id: m.opts.id, focus: m.opts.initialFocus, tier: m.opts.tier, html: m.el.innerHTML,
          q: (window._fccOpenMoveQuestions || []).length }};
""")
    assert res["id"] == "fcc-refill-place" and res["focus"] == "#fcc-refill-leave", res
    for words in ("#57 is back in stock: where does it go?", "It came off <strong>", "XL-3",
                  "Back on ", "In ", "LR", " for now", "Pick a place…", "Leave it Unassigned",
                  # PIN UPDATED DELIBERATELY (Group 63 review): Pick a place… now sits beside
                  # these words, under the answers that have a QR (attachConfirmQRs' alignTo).
                  "or scan the label of the place where it goes."):
        assert words in res["html"], (words, res["html"])
    assert 'id="fcc-refill-back" class="btn btn-success btn-sm fcc-refill-answer">' in res["html"], res["html"]
    assert res["q"] == 1, res


@needs_node
def test_back_on_the_head_moves_it_there_and_says_what_it_was_shown(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
el('#fcc-refill-back').onclick({{ type: 'click', detail: 1 }});
await __settle(80);
return {{ posts: posts(), toasts: __rec.toasts, q: (window._fccOpenMoveQuestions || []).length,
          closed: __rec.overlays[0].closed }};
""")
    assert res["posts"] == [["/api/manage_contents", {
        "action": "add", "location": "XL-3", "spool_id": "57", "origin": "manual_override",
        "confirmed_toolheads": [], "confirmed_fed_heads": [], "expected_residents": []}]], res
    assert [t["msg"] for t in res["toasts"]] == ["✅ #57 → XL-3"], res
    assert res["q"] == 0 and res["closed"] is True, res


@needs_node
def test_a_head_another_spool_is_on_now_is_greyed_out_with_the_reason(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(dict(ASK, held_by=[99]))});
return {{ html: last().el.innerHTML, back: typeof el('#fcc-refill-back').onclick }};
""")
    assert 'fcc-refill-answer" disabled aria-disabled="true">Back on ' in res["html"], res["html"]
    assert "XL-3 holds #99 now, so it can&#39;t go back on it." in res["html"], res["html"]
    assert res["back"] != "function", res


@needs_node
def test_an_unread_head_is_offered_and_says_it_will_be_checked(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(dict(ASK, held_by=None))});
return {{ html: last().el.innerHTML, back: typeof el('#fcc-refill-back').onclick }};
""")
    assert "FCC couldn&#39;t check XL-3 just now: it checks again if you pick it." in res["html"], res["html"]
    assert res["back"] == "function", res


@needs_node
def test_in_the_room_for_now_moves_it_there(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
el('#fcc-refill-room').onclick({{ type: 'click', detail: 1 }});
await __settle(80);
return {{ posts: posts() }};
""")
    assert res["posts"] == [["/api/manage_contents", {
        "action": "add", "location": "LR", "spool_id": "57", "origin": "manual_override",
        "confirmed_toolheads": [], "confirmed_fed_heads": []}]], res


@needs_node
def test_with_no_room_there_is_no_room_answer(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(dict(ASK, room=""))});
return {{ html: last().el.innerHTML }};
""")
    assert "fcc-refill-room" not in res["html"], res["html"]


@needs_node
def test_pick_a_place_opens_force_locations_list(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
el('#fcc-refill-pick').onclick({{ type: 'click', detail: 1 }});
await __settle(20);
return {{ opened, posts: posts() }};
""")
    assert res["opened"] == [{"sid": "57", "loc": "", "fromCard": True}] and res["posts"] == [], res


@needs_node
@pytest.mark.parametrize("how", ["button", "escape", "cancel-scan"])
def test_leaving_it_unassigned_moves_nothing(tmp_path, how):
    act = {"button": "el('#fcc-refill-leave').onclick({ type: 'click', detail: 1 });",
           "escape": "last().opts.onEscape();",
           "cancel-scan": "window._fccOpenMoveQuestion.cancel();"}[how]
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
{act}
await __settle(20);
return {{ posts: posts(), toasts: __rec.toasts, q: (window._fccOpenMoveQuestions || []).length }};
""")
    assert res["posts"] == [] and res["q"] == 0, res
    assert [(t["msg"], t["type"]) for t in res["toasts"]] == [
        ("#57 stays Unassigned: scan it to where you put it.", "info")], res


@needs_node
@pytest.mark.parametrize("label, target, shown", [
    ("LOC:CR-SHELF-2", "CR-SHELF-2", None),
    ("LOC:DRYBOX-1:SLOT:2", "DRYBOX-1", None),
    ("LOC:XL-3", "XL-3", []),
], ids=["a-place", "a-slot-label-names-its-box", "its-own-head"])
def test_a_scanned_place_label_puts_it_there(tmp_path, label, target, shown):
    # (`label`, not `scan`: conftest's `scan` fixture is a container one, which --offline skips.)
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
const answered = window._fccOpenMoveQuestion.route({json.dumps(label)}, 'barcode');
await __settle(80);
return {{ answered, posts: posts() }};
""")
    body = {"action": "add", "location": target, "spool_id": "57", "origin": "manual_override",
            "confirmed_toolheads": [], "confirmed_fed_heads": []}
    if shown is not None:
        body["expected_residents"] = shown
    assert res["answered"] is True and res["posts"] == [["/api/manage_contents", body]], res


@needs_node
def test_any_other_scan_is_left_to_the_question_to_refuse(tmp_path):
    res = _run(tmp_path, f"""
await window.askRefillPlace(57, {json.dumps(ASK)});
return {{ answered: window._fccOpenMoveQuestion.route('ID:99', 'barcode'), posts: posts() }};
""")
    assert res["answered"] is False and res["posts"] == [], res


@needs_node
def test_the_answers_that_move_wait_out_a_double_click(tmp_path):
    """Group 62.3's rule: a click under 700 ms after it opens is a double click's
    second press, and moves nothing; a keyboard click (detail 0) and Leave it
    Unassigned don't wait."""
    res = _run(tmp_path, f"""
delete window.fccQuestionArmMs;
await window.askRefillPlace(57, {json.dumps(ASK)});
el('#fcc-refill-back').onclick({{ type: 'click', detail: 1 }});
el('#fcc-refill-room').onclick({{ type: 'click', detail: 1 }});
const early = posts().length;
el('#fcc-refill-room').onclick({{ type: 'click', detail: 0 }});
await __settle(80);
return {{ early, posts: posts() }};
""", modules=("inv_core.js", "inv_details.js"))
    assert res["early"] == 0, res
    assert [p[1]["location"] for p in res["posts"]] == ["LR"], res


# ---- the weigh save opens it --------------------------------------------------------------------------

SAVE = """
window.__respond = (url) => (url === '/api/spool/update'
    ? { body: { status: 'success', auto_archived: false, needs_empty_weight_prompt: false,
                location_now: '', refill_ask: { place: 'XL-3', room: 'LR', held_by: [] } } }
    : { body: {} });
const asked = [];
window.askRefillPlace = (sid, ask, o) => asked.push({ sid, ask, host: !!(o && o.host) });
window.saveSpoolWeight(57, null, { used_weight: 600 }, false, null, { archiveSwitch: true, empties: false, wasArchived: true });
await __settle(600);
return { asked, toasts: __rec.toasts };
"""


@needs_node
def test_a_weigh_save_that_refilled_after_a_head_asks(tmp_path):
    res = run_js(tmp_path, ["inv_weigh_out.js"], SAVE)
    assert res["unhandled"] == [], res
    assert res["asked"] == [{"sid": 57, "ask": {"place": "XL-3", "room": "LR", "held_by": []}, "host": False}], res
