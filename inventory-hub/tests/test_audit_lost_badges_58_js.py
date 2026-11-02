"""Group 58, build spec section 8's page half: a spool an audit lost says so. Derek's
note: "if one is found, it's apparent that this was filed away because we didn't know
where it went". Unknown already is that list (his 18.1 pick), so there is no second
bucket: each spool in it says which audit lost it and when.

On the real modules under node's `vm`, fed what the REAL routes answer for a spool
the real park wrote (`lost`, over tests/spoolman_extra_fake.SpoolmanHTTPFake). The
server's half is tests/test_audit_lost_spools_58.py; a real spool on the real
dashboard, tests/test_audit_done_question_58_e2e.py.

RED on f59485a unless a test says it pins what was already right.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402
import state  # noqa: E402
import stock_report  # noqa: E402
from test_audit_session_58 import add_spool, env, park, scan, start  # noqa: E402,F401  (env: the fixture)
from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: E402,F401  (pytestmark: skip without node)
from test_head_load_confirm_js import PRELUDE, SCAN  # noqa: E402
from test_text_size_guard import SAMPLE_LOST, SAMPLE_LOST_DETAILS  # noqa: E402

WHERE = "LR-MDB-1 slot 2"
BY = f"the audit of {WHERE} on 2026-11-01"
BADGE = f"❓ Lost: {WHERE}"
TITLE = f"Marked lost by {BY}"
# The plain badge, as it was: an old spool at Unknown no audit lost.
PLAIN = ('<span class="badge bg-warning text-dark loc-badge-hover" onclick="%s" style="cursor:pointer; '
         'font-size: 1.1rem;" title="Physically lost — last known location unknown">❓ Unknown</span>')
SEARCH_CLICK = ("event.stopPropagation(); if(window.openManage) { window.openManage('UNKNOWN'); "
                "if(window.SearchEngine && window.SearchEngine.offcanvas){window.SearchEngine.offcanvas.hide();} }")
BUFFER_CLICK = "event.stopPropagation(); if(window.openManage) window.openManage('UNKNOWN')"
DETAILS = SCAN + ["inv_details.js"]

CARD_PRELUDE = r"""
const __plainTimeout = window.setTimeout;
window.setTimeout = (fn, ms, ...rest) => {
  if (fn && fn.name === 'dismiss') { const c = document.getElementById('toast-container').children; c[c.length - 1].ms = ms; }
  return __plainTimeout(fn, ms, ...rest);
};
const timed = () => (document.getElementById('toast-container').children || [])
  .map(c => ({ msg: c.innerText, type: String(c.className).replace('toast-msg toast-', ''), ms: c.ms }));
const card = (item, mode, opts) => SpoolCardBuilder.buildCard(item, mode, opts || {});
"""


def _js(tmp_path, body, modules=SCAN, **values):
    head = "".join(f"const {name} = {json.dumps(value)};\n" for name, value in values.items())
    res = run_js(tmp_path, modules, PRELUDE + CARD_PRELUDE + head + body)
    assert res["unhandled"] == [], res["unhandled"]
    return res


@pytest.fixture
def lost(env, monkeypatch):
    """#99 parked by a real audit of LR-MDB-1 on 2026-11-01, from slot 2. #400 at
    Unknown by hand, no note. #401 with an older FCC's bare note. Then what each route
    answers for them."""
    monkeypatch.setattr(state, "UNDO_STACK", [])
    monkeypatch.setattr(stock_report, "_server_day", lambda: "2026-11-02")
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 99, "LR-MDB-1", container_slot="2")
    start(env, "LR-MDB-1")
    scan(env, "ID:57")
    assert park(env, today="2026-11-01")["parked"] == [99]
    add_spool(env, 400, "UNKNOWN")
    add_spool(env, 401, "UNKNOWN", fcc_pre_audit_location="LR-CT-1")
    client = app_module.app.test_client()
    return {
        "scan": scan(env, "ID:99", source="keyboard"),
        "scan_plain": scan(env, "ID:400", source="keyboard"),
        "scan_old": scan(env, "ID:401", source="keyboard"),
        "details": client.get("/api/spool_details?id=99").get_json(),
        "details_plain": client.get("/api/spool_details?id=400").get_json(),
        "details_old": client.get("/api/spool_details?id=401").get_json(),
        "contents": client.get("/api/get_contents?id=UNKNOWN").get_json(),
    }


def _row(lost, sid):
    return next(r for r in lost["contents"] if r["id"] == sid)


def test_the_routes_really_answer_what_the_cards_read(lost):
    """Pins what was right on the server, or a badge could read a key nobody sends."""
    assert lost["scan"]["details"]["lost_from"] == {"place": "LR-MDB-1", "slot": "2", "on": "2026-11-01"}
    assert lost["scan"]["location"] == "UNKNOWN"
    assert lost["scan_plain"]["details"]["lost_from"] is None
    assert lost["details"]["lost_from"]["on"] == "2026-11-01" and "lost_from" not in lost["details_plain"]
    assert _row(lost, 99)["details"]["lost_from"]["slot"] == "2"


def test_the_guards_samples_are_the_routes_shape(lost):
    """The contrast and text-size guards draw these on the real dashboard."""
    assert set(SAMPLE_LOST) <= set(lost["scan"]) and set(SAMPLE_LOST["details"]) == set(lost["scan"]["details"])
    assert set(SAMPLE_LOST_DETAILS) - {"initial_weight", "used_weight", "comment"} <= set(lost["details"])


# --- the cards ---------------------------------------------------------------------

def test_the_search_card_says_who_lost_it(tmp_path, lost):
    res = _js(tmp_path, """
return { html: card(Object.assign({}, ROW, { type: 'spool' }), 'search') };
""", ROW=_row(lost, 99))
    want = (f'<span class="badge bg-warning text-dark loc-badge-hover" onclick="{SEARCH_CLICK}" '
            f'style="cursor:pointer; font-size: 1.1rem;" title="{TITLE}">{BADGE}</span>')
    assert want in res["html"]         # its look kept, and it still opens the Unknown list
    assert "❓ Unknown" not in res["html"]


def test_the_buffer_card_says_who_lost_it(tmp_path, lost):
    res = _js(tmp_path, """
return { html: card(SPOOL, 'buffer', { index: 0, isFirst: true }) };
""", SPOOL=lost["scan"])
    want = (f'<span class="badge bg-warning text-dark loc-badge-hover" onclick="{BUFFER_CLICK}" '
            f'style="cursor:pointer; font-size: 1.1rem;" title="{TITLE}">{BADGE}</span>')
    assert want in res["html"]


def test_each_spool_in_the_unknown_list_says_so_too(tmp_path, lost):
    """The list the Location Manager draws for Unknown: its cards have no location
    badge, being in the place, and this list is the one spec section 8 is about. A
    card there opens nothing from its badge: it is already in that list."""
    res = _js(tmp_path, """
return { lost: card(LOST, 'loc_list', { locId: 'UNKNOWN', index: 0 }),
         plain: card(PLAIN_ROW, 'loc_list', { locId: 'UNKNOWN', index: 1 }) };
""", LOST=_row(lost, 99), PLAIN_ROW=_row(lost, 400))
    assert f'title="{TITLE}">{BADGE}</span>' in res["lost"] and "cursor:default" in res["lost"]
    assert "❓" not in res["plain"]    # no note, no badge: the list says Unknown already


@pytest.mark.parametrize("mode, click, opts", [("search", SEARCH_CLICK, {}), ("buffer", BUFFER_CLICK, {"index": 0})])
def test_a_spool_no_audit_lost_keeps_the_plain_badge(tmp_path, lost, mode, click, opts):
    """Pins what was right, to the byte: an old spool at Unknown."""
    res = _js(tmp_path, """
return { html: card(Object.assign({ type: 'spool' }, ROW), MODE, OPTS) };
""", ROW=lost["scan_plain"], MODE=mode, OPTS=opts)
    assert PLAIN % click in res["html"]


def test_a_record_with_no_key_at_all_keeps_the_plain_badge(tmp_path):
    """A card a page holds from before this release: a buffer entry saved with the
    old details. Pins what was right."""
    res = _js(tmp_path, """
return { html: card({ id: 5, type: 'spool', location: 'UNKNOWN', display: '#5', details: { brand: 'x' } }, 'buffer', { index: 0 }),
         bare: card({ id: 6, type: 'spool', location: 'unknown', display: '#6' }, 'buffer', { index: 1 }) };
""")
    assert PLAIN % BUFFER_CLICK in res["html"] and "❓ Unknown" in res["bare"]


def test_an_older_bare_note_names_the_place_and_no_day(tmp_path, lost):
    """An FCC before this group wrote the bare place. `slot` and `on` are both ''."""
    assert lost["scan_old"]["details"]["lost_from"] == {"place": "LR-CT-1", "slot": "", "on": ""}
    res = _js(tmp_path, """
return { html: card(SPOOL, 'buffer', { index: 0 }) };
""", SPOOL=lost["scan_old"])
    assert 'title="Marked lost by the audit of LR-CT-1">❓ Lost: LR-CT-1</span>' in res["html"]


def test_a_note_with_a_day_and_no_slot_reads_right(tmp_path):
    res = _js(tmp_path, """
return { w: window.auditLostWords({ place: 'LR-CT-1', slot: '', on: '2026-11-01' }),
         none: [window.auditLostWords(null), window.auditLostWords(undefined), window.auditLostWords({})] };
""")
    assert res["w"] == {"where": "LR-CT-1", "by": "the audit of LR-CT-1 on 2026-11-01"}
    assert res["none"] == [None, None, None]


def test_a_place_with_odd_characters_can_break_nothing(tmp_path):
    """A LocationID comes from locations.json, and the card is HTML."""
    res = _js(tmp_path, """
const lost = { place: 'A"><img src=x onerror=alert(1)>', slot: '', on: '' };
return { html: card({ id: 5, type: 'spool', location: 'UNKNOWN', details: { lost_from: lost } }, 'buffer', { index: 0 }) };
""")
    assert "<img" not in res["html"] and "&lt;img" in res["html"]


def test_a_filament_search_row_shows_no_badge(tmp_path):
    """Pins what was right: filament rows have no such key, and no location."""
    res = _js(tmp_path, """
return { html: card({ id: 5, type: 'filament', display: 'x', details: { brand: 'y' } }, 'search') };
""")
    assert "Filament Template" in res["html"] and "❓" not in res["html"]


# --- the spool window ----------------------------------------------------------------

_OPEN = r"""
window.__extra = (url) => (url.startsWith('/api/spool_details') ? { body: DETAILS } : null);
const badge = document.getElementById('detail-location-badge');
openSpoolDetails(DETAILS.id);
await __settle(60);
return { text: badge.innerHTML ? badge.innerHTML.replace(/<[^>]+>/g, '') : badge.innerText, html: badge.innerHTML,
         cls: badge.className, title: badge.title, click: typeof badge.onclick };
"""


def test_the_spool_window_says_it_in_words_for_a_screen_with_no_hover(tmp_path, lost):
    res = _js(tmp_path, _OPEN, modules=DETAILS, DETAILS=lost["details"])
    assert res["text"] == f"❓ Marked lost by {BY}"
    assert res["cls"].split()[:3] == ["badge", "bg-warning", "text-dark"]       # the yellow it had
    assert "text-wrap" in res["cls"]                                            # a sentence, on a narrow window
    assert res["click"] == "function"
    # A line may break after any hyphen, and "LR-" over "MDB-1 slot 2" reads as nothing.
    assert '<span class="fcc-keep-whole">LR-MDB-1</span>' in res["html"]
    assert '<span class="fcc-keep-whole">slot 2</span>' in res["html"]


def test_the_spool_window_of_a_spool_no_audit_lost_is_as_it_was(tmp_path, lost):
    """Pins what was right."""
    res = _js(tmp_path, _OPEN, modules=DETAILS, DETAILS=lost["details_plain"])
    assert res["text"] == "❓ Unknown" and res["cls"] == "badge bg-warning text-dark ms-2 me-1"


def test_an_older_note_reads_right_in_the_spool_window(tmp_path, lost):
    res = _js(tmp_path, _OPEN, modules=DETAILS, DETAILS=lost["details_old"])
    assert res["text"] == "❓ Marked lost by the audit of LR-CT-1"


@pytest.mark.parametrize("badge", ["❓ Unknown", f"❓ Marked lost by {BY}"])
def test_the_spool_windows_pencil_opens_on_unknown_never_on_the_badges_words(tmp_path, badge):
    """Its ✏️ hands over the badge's text. RED on f59485a: "❓ Unknown" became the
    default, and a Force Move with no pick wrote those words to the spool as its
    location. A badge holding a sentence would have written the sentence."""
    res = _js(tmp_path, """
let fired = null;
window.Swal = { fire: (o) => { fired = o; return new Promise(() => {}); } };
window.__respond = (url) => (url === '/api/locations'
  ? { body: [{ LocationID: 'UNKNOWN', Name: 'Unknown', Type: 'Unknown' }] } : { body: [] });
window.promptEditLocation(99, BADGE);
await __settle(40);
return { html: fired.html };
""", modules=DETAILS, BADGE=badge)
    assert 'id="swal-override-loc" value="UNKNOWN"' in res["html"]
    assert "background:#444" in res["html"]            # the list shows where it is now


# --- a scan of one -------------------------------------------------------------------

_SCAN = r"""
answerWith('/api/identify_scan', [SPOOL]);
state.heldSpools = [];
window.processScan('ID:' + SPOOL.id, 'barcode');
await __settle(60);
return { toasts: timed(), held: state.heldSpools.map(s => s.id), logs: posts('/api/log_event').length };
"""


def test_a_scan_of_a_lost_spool_says_it_turned_up_for_7_seconds(tmp_path, lost):
    res = _js(tmp_path, _SCAN, SPOOL=lost["scan"])
    assert res["toasts"] == [{"msg": lost["scan"]["lost_msg"], "type": "warning", "ms": 7000}]
    assert res["toasts"][0]["msg"] == f"#99 turned up. It was marked lost by {BY}. Scan where it goes."
    assert res["held"] == [99]         # it joins the buffer, so the next scan says where it goes
    assert res["logs"] == 0            # the server has logged it


def test_a_scan_of_a_spool_no_audit_lost_says_nothing_new(tmp_path, lost):
    """Pins what was right."""
    res = _js(tmp_path, _SCAN, SPOOL=lost["scan_plain"])
    assert res["toasts"] == [] and res["held"] == [400]


@pytest.mark.parametrize("mode", ["dropMode", "ejectMode"])
def test_a_mode_acts_on_the_spool_and_it_still_says_so(tmp_path, lost, mode):
    """Drop and eject return early, and the person holding it should still hear."""
    res = _js(tmp_path, """
window.ejectSpool = () => {};
window.removeBufferItem = () => {};
answerWith('/api/identify_scan', [SPOOL]);
state[MODE] = true;
window.processScan('ID:' + SPOOL.id, 'barcode');
await __settle(60);
return { toasts: timed().filter(t => t.msg === SPOOL.lost_msg) };
""", SPOOL=lost["scan"], MODE=mode)
    assert res["toasts"] == [{"msg": lost["scan"]["lost_msg"], "type": "warning", "ms": 7000}]
