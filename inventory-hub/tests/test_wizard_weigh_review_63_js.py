"""Group 63 review: the wizard's Location field and Scale note, and a spool whose own
total is 0 g, hermetic (node's `vm`, the real modules over the stub DOM).

  - K01 / K02: an Edit Spool Save whose own write moved the spool (a refill off the
    head it was archived on, or back to its note's place) answers `location_now`,
    and the Location field shows it, so the next Save (it sends the field) moves
    nothing; where the refill question's move landed goes in the field too;
  - C4: a filament write refused after the spool's landed still asks the refill
    question, and the field and the Archived box follow what the spool's write did;
  - K37: the Scale box's "enter the spool's empty weight first" note goes with its
    reading, and the used weight is worked out once the empty weight arrives;
  - K38: a spool whose own total is 0 g reads 0 g (the server's rule, not its
    filament's 1000 g), and the Quick-Weigh says to set its total first instead of
    opening on figures every save of which the server refuses.

Every test is RED on 8153b81 (the group's head before the review's fixes) unless its
docstring says control.
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE
from test_wizard_location_save_js import WIZARD

ASK = {"place": "XL-1", "room": "LR", "held_by": []}
ASKED = r"""
const asked = [];
window.askRefillPlace = (sid, ask, o) => { asked.push(sid); window.__moved = o && o.onMoved; return Promise.resolve(null); };
const where = () => ({ field: document.getElementById('wiz-spool-location').value,
                       state: wizardState.editSpoolLocation });
"""


def _wizard(tmp_path, body):
    # weight_utils.js: the used weight is written with window.fmtGramsPrecise, as on the page.
    res = run_js(tmp_path, ["inv_core.js", "weight_utils.js", "inv_wizard.js"], PRELUDE + WIZARD + ASKED + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


def test_the_location_field_shows_where_the_saves_own_write_left_the_spool(tmp_path):
    """K01 / K02. #57 was archived ON XL-1; weighed back, the server took it off and
    asks where it goes. The field shows Unassigned at once, and the head the question
    put it back on once it lands. RED on 8153b81: the field kept XL-1 (no
    location_now was read), and the next Save loaded #57 back onto XL-1."""
    res = _wizard(tmp_path, f"""
editing(57, 'XL-1');
answerFor({{ '/api/edit_spool_wizard': [{json.dumps({
        "success": True, "spool_id": 57, "archived_now": False, "location_now": "",
        "location_where": "Unassigned", "refill_ask": ASK})}] }});
await window.wizardSubmit();
await __settle(100);
const after = where();
if (window.__moved) window.__moved('XL-2');
return {{ asked, after, moved: where() }};
""")
    assert res["asked"] == [57], res
    assert res["after"] == {"field": "", "state": ""}, res
    assert res["moved"] == {"field": "XL-2", "state": "XL-2"}, res


def test_a_refused_filament_write_still_asks_where_the_spool_goes(tmp_path):
    """C4. The spool's write landed (back in stock, Unassigned, its note used up) and
    the filament's was refused: the question is still asked, and the field and the
    Archived box follow the spool. RED on 8153b81: an error line only, nothing asked."""
    res = _wizard(tmp_path, f"""
editing(57, 'XL-1');
document.getElementById('wiz-spool-archived').checked = true;
answerFor({{ '/api/edit_spool_wizard': [{json.dumps({
        "success": False, "spool_saved": True, "msg": "Spool saved, but filament update rejected: locked",
        "error": "locked", "archived_now": False, "location_now": "", "location_where": "Unassigned",
        "refill_ask": ASK})}] }});
await window.wizardSubmit();
await __settle(100);
return {{ asked, where: where(), archived: document.getElementById('wiz-spool-archived').checked }};
""")
    assert res["asked"] == [57] and res["where"] == {"field": "", "state": ""}, res
    assert res["archived"] is False, res


def test_the_scale_note_goes_with_its_reading_and_waits_for_the_empty_weight(tmp_path):
    """K37. RED on 8153b81: Clear emptied the Scale box but left "enter the spool's
    empty weight first" up, and an empty weight arriving from the filament worked
    nothing out."""
    res = _wizard(tmp_path, r"""
const note = document.getElementById('wiz-spool-scale-note');
field('wiz-spool-initial_weight', '1000');
field('wiz-spool-scale', '1245');
window.wizardCalcUsedWeight();
const first = { text: note.textContent, shown: note.style.display !== 'none' };
window.wizardClearScaleWeight();
const cleared = { text: note.textContent, shown: note.style.display !== 'none' };
field('wiz-spool-scale', '1245');
window.wizardCalcUsedWeight();
window.wizardSetSpoolEmptyWeightInherited(245, 'filament');
return { first, cleared, after: { text: note.textContent, shown: note.style.display !== 'none' },
         used: document.getElementById('wiz-spool-used').value };
""")
    assert res["first"]["shown"] and res["first"]["text"].startswith("Enter the spool's empty weight first"), res
    assert res["cleared"] == {"text": "", "shown": False}, res
    assert res["after"] == {"text": "", "shown": False} and res["used"] == "0", res


QW = r"""
const opened = [];
window.WeightEntry = { openModal: (o) => opened.push(o.spool.initial_weight) };
"""


def _quick(tmp_path, spool):
    res = run_js(tmp_path, ["weight_utils.js", "inv_weigh_out.js"], QW + f"""
window.__respond = (url) => (url.startsWith('/api/spool_details') ? {{ body: {json.dumps(spool)} }} : {{ body: {{}} }});
window.openQuickWeigh(57);
await __settle(80);
return {{ opened, toasts: __rec.toasts.map((t) => t.msg) }};
""")
    assert res["unhandled"] == [], res
    return res


def test_a_spool_whose_own_total_is_0_g_isnt_weighed_until_it_has_one(tmp_path):
    """K38. RED on 8153b81: its own 0 read as its filament's 1000 g, so the window
    opened, and every save was refused as "changed since" (the server reads 0)."""
    res = _quick(tmp_path, {"id": 57, "initial_weight": 0, "used_weight": 0, "filament": {"weight": 1000}})
    assert res["opened"] == [], res
    assert res["toasts"] == ["#57's total weight is 0 g in Spoolman: set its total in Edit Spool first, "
                             "then weigh it"], res


def test_control_a_spool_with_no_total_of_its_own_uses_its_filaments(tmp_path):
    res = _quick(tmp_path, {"id": 57, "initial_weight": None, "used_weight": 0, "filament": {"weight": 1000}})
    assert res["opened"] == [1000], res
