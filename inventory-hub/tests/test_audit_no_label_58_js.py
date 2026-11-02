"""Group 58.2's page half on a real DOM and the REAL routes, hermetic.

The real overlay_mount.js, inv_core.js, inv_cmd.js, the real scan accumulator and
global.css, in `isolated_page` (no route to any network), so it runs under --offline.
Every call the panel makes goes through an exposed binding to the REAL Flask routes,
on the real session, with the real update_spool over
tests/spoolman_extra_fake.SpoolmanHTTPFake (the `live` fixture): nothing the page
hears is a copy of an answer, and a mark is read back from the record it wrote.

test_audit_no_label_58.py has the server's rules; test_audit_no_label_58_e2e.py the
real dashboard, with Bootstrap and real QR codes.

Keys go on a fake clock (test_slow_scan_slash_js.TYPE_JS) where a scanner's speed is
the point, all in one tick, so the 50 ms key N waits really is "more keys came";
the real keyboard where a browser's own press is what is tested (a synthetic Enter
clicks nothing).

RED on 39b0d1a unless a test says it pins what was already right.
"""
from __future__ import annotations

import pytest

import app as app_module
from test_audit_panel_58_js import DONE, NOTICE, PANEL, _on_top, audit  # noqa: F401  (audit: the fixture)
from test_audit_session_58 import add_spool, env, scan, session, start  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import page61  # noqa: F401  (page61: the fixture)
from test_slow_scan_slash_js import _type

LABEL = "needs_label_print"
BODY = "#fcc-audit-panel-body"
STRIP = "#fcc-audit-last-found"
STATUS = STRIP + " [role=status]"
BUTTON = "#fcc-audit-panel-needlabel"
UNDO = "#fcc-audit-label-undo"
FOUND_URL = "/api/audit/found"
QUESTION = "#fcc-audit-done-question"


def tile(sid):
    return f"[data-audit-tile='{sid}']"


FCC_ROUTES = r"""() => {
    window.closeAuditPanel();
    window.__sent = [];
    window.__qrs = [];
    window.QRCode = function (el, o) { window.__qrs.push(o.text); el.textContent = 'QR'; };
    window.QRCode.CorrectLevel = { L: 1 };
    window.__toastMs = [];
    const plainTimeout = window.setTimeout;
    window.setTimeout = (fn, ms, ...rest) => {
        if (fn && fn.name === 'dismiss') window.__toastMs.push(ms);
        return plainTimeout(fn, ms, ...rest);
    };
    const plain = window.fetch;
    window.fetch = async (url, opts) => {
        const u = String(url);
        if (!/\/api\/(identify_scan|audit)/.test(u)) return plain(url, opts);
        if (window.__noAnswer) throw new TypeError('Failed to fetch');
        if (window.__noPoll && u.indexOf('/api/audit_session') !== -1) return new Promise(() => {});
        const body = opts && opts.body ? opts.body : null;
        if (body) window.__sent.push({ url: u, body: JSON.parse(body) });
        if (window.__held && u.indexOf('/api/identify_scan') !== -1) {
            await new Promise((resolve) => { window.__release = resolve; });
        }
        const text = await window.__fcc(u, (opts && opts.method) || 'GET', body);
        return { ok: true, status: 200, json: async () => JSON.parse(text), text: async () => text };
    };
}"""


@pytest.fixture
def live(env, audit):
    """`audit`'s page with its session sample gone: the real routes answer it."""
    client = app_module.app.test_client()

    def answer(url, method, body):
        res = client.open(url, method=method, data=body, content_type="application/json")
        return res.get_data(as_text=True)
    audit.expose_function("__fcc", answer)
    audit.evaluate(FCC_ROUTES)
    return audit


def begin(page, env, place="LR-MDB-1"):
    """The audit started on the real session, and its panel up on the page."""
    start(env, place)
    page.evaluate("() => { state.auditActive = true; window.openAuditPanel(); }")
    page.wait_for_selector(DONE)


def two(env):
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    add_spool(env, 99, "LR-MDB-1", container_slot="2")


def wire(env, sid):
    return env["fake"].extra("spool", sid).get(LABEL)


def sent(page, url="/api/identify_scan"):
    return [(p["body"].get("text") if "text" in p["body"] else p["body"])
            for p in page.evaluate("window.__sent") if p["url"] == url]


def scanned(page, text, source="keyboard"):
    """A scan through the page's own path, answered and drawn."""
    page.evaluate("([t, s]) => { window.processScan(t, s); }", [text, source])
    page.wait_for_function("() => !state.processing")


def strip_says(page, words):
    page.wait_for_function("([sel, w]) => { const el = document.querySelector(sel); return !!el && el.textContent.includes(w); }",
                           arg=[STATUS, words])


def tile_says(page, sid, words):
    page.wait_for_function("([sel, w]) => { const el = document.querySelector(sel); return !!el && el.textContent.includes(w); }",
                           arg=[tile(sid), words])


def toasts(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))
        .map((e) => ({ msg: e.innerText, kind: e.className.replace('toast-msg toast-', '') }))""")


def key_n(page):
    """A person's N, then the wait the panel gives a scan to go on."""
    _type(page, "n", 1, enter=False)
    page.wait_for_timeout(120)


# --- the strip ------------------------------------------------------------------------

def test_with_nothing_found_there_is_no_strip(live, env):
    """A pin: no base has a strip. Proved on a copy that draws one for no spool."""
    two(env)
    begin(live, env)
    assert not live.locator(STRIP).count()


def test_the_strip_names_the_spool_above_done_and_cancel(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(STRIP)
    text = live.text_content(STRIP)
    assert "Last found" in text and "#57 Some Brand PLA (Red)" in text
    assert live.get_attribute(STATUS, "role") == "status"
    assert live.is_visible(BUTTON) and "Needs a label" in live.text_content(BUTTON)
    above = live.evaluate("""([strip, done]) => document.querySelector(strip).getBoundingClientRect().bottom
        <= document.querySelector(done).getBoundingClientRect().top""", [STRIP, DONE])
    assert above is True


def test_a_rescan_moves_the_strip_back(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    scanned(live, "ID:99")
    strip_says(live, "#99")
    scanned(live, "ID:57")
    strip_says(live, "#57")


def test_the_qr_under_the_button_holds_the_command_and_undo_has_none(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_function("() => window.__qrs.includes('CMD:NEEDLABEL')")
    below = live.evaluate("""([btn, qr]) => { const b = document.querySelector(btn).getBoundingClientRect();
        const q = document.querySelector(qr).getBoundingClientRect();
        return q.top >= b.bottom && q.left < b.right && q.right > b.left; }""", [BUTTON, "#fcc-audit-panel-qr-needlabel"])
    assert below is True
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    strip_qrs = live.evaluate("(s) => document.querySelector(s).querySelectorAll('[id*=qr]').length", STRIP)
    assert strip_qrs == 1                    # "undo that" has no QR: a double read can't toggle it


# --- the nudge and the tile's words ---------------------------------------------------

def test_a_find_with_no_label_read_is_nudged_and_writes_nothing(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57", "keyboard")
    strip_says(live, "No label was read for #57")
    tile_says(live, 57, "found, no label read")
    assert wire(env, 57) is None and env["fake"].patches == []


def test_a_label_read_isnt_nudged(live, env):
    two(env)
    begin(live, env)
    _type(live, "ID:57", 1)                  # the real accumulator: a scanner's speed
    strip_says(live, "#57's label was read")
    assert "No label was read" not in live.text_content(STRIP)
    assert "✅ scanned" in live.text_content(tile(57))
    assert "no label read" not in live.text_content(tile(57))
    assert wire(env, 57) == "false"


def test_a_scanners_label_read_is_what_went_out(live, env):
    """Pins the accumulator's `source` the label check trusts. Proved on a copy that
    calls every scan a person's."""
    two(env)
    begin(live, env)
    _type(live, "ID:57", 1)
    live.wait_for_function("() => window.__sent.length > 0")
    assert live.evaluate("window.__sent[0].body.source") == "barcode"


def test_a_slow_typed_id_is_not_a_label_read(live, env):
    two(env)
    begin(live, env)
    _type(live, "ID:57", 200)
    strip_says(live, "No label was read for #57")
    assert wire(env, 57) is None


def test_a_flag_a_label_read_left_up_is_said_on_the_strip_and_the_tile(live, env):
    add_spool(env, 57, "LR-MDB-1", needs_label_print=True)
    begin(live, env)
    _type(live, "ID:57", 1)
    strip_says(live, "#57 is still flagged for a new label")
    tile_says(live, 57, "needs a label")
    assert "✅ scanned" in live.text_content(tile(57))
    assert wire(env, 57) == "true"


def test_a_tile_says_label_status_unknown_when_the_check_failed(live, env):
    two(env)
    begin(live, env)
    env["fake"].fields["spool"] = [f for f in env["fake"].fields["spool"] if f["key"] != LABEL]   # Spoolman refuses
    _type(live, "ID:57", 1)
    tile_says(live, 57, "label status unknown")
    strip_says(live, "couldn't confirm it")


def test_a_spool_with_no_status_says_nothing_until_it_is_found(live, env):
    """Most spools have no status (dev: 175 of 237), so a word on every tile is noise,
    as the grey chip would have been on the search cards (58.5)."""
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    text = live.text_content(tile(57))
    assert "label" not in text.lower() and "not scanned" in text


def test_a_flag_shows_before_the_scan_too(live, env):
    add_spool(env, 57, "LR-MDB-1", needs_label_print=True)
    begin(live, env)
    tile_says(live, 57, "needs a label")


def test_a_failed_label_check_is_said_on_the_panel_and_a_good_scan_clears_it(live, env):
    two(env)
    begin(live, env)
    fields = env["fake"].fields["spool"]
    env["fake"].fields["spool"] = [f for f in fields if f["key"] != LABEL]
    _type(live, "ID:57", 1)
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes(\"couldn't be confirmed\")", arg=NOTICE)
    assert any("couldn't be confirmed" in t["msg"] and t["kind"] == "warning" for t in toasts(live))
    assert 7000 in live.evaluate("window.__toastMs")
    env["fake"].fields["spool"] = fields
    scanned(live, "ID:99")
    live.wait_for_function("(s) => !document.querySelector(s).textContent", arg=NOTICE)


# --- marking ---------------------------------------------------------------------------

def test_the_button_marks_the_last_found_and_undo_that_appears(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    strip_says(live, "#57 is marked: it needs a label")
    tile_says(live, 57, "needs a label")
    assert wire(env, 57) == "true"
    assert live.evaluate("window.__sent[window.__sent.length - 1].body.source") == "keyboard"


def test_a_mark_toasts_for_four_seconds(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    assert {"msg": "#57 is marked: it needs a label.", "kind": "success"} in toasts(live)
    assert live.evaluate("window.__toastMs")[-1] == 4000


def test_the_qr_read_twice_is_one_write(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    _type(live, "CMD:NEEDLABEL", 1)
    live.wait_for_selector(UNDO)
    env["fake"].patches.clear()
    _type(live, "CMD:NEEDLABEL", 1)
    live.wait_for_function("""() => Array.from(document.querySelectorAll('#toast-container .toast-msg'))
        .some((e) => e.innerText.includes('already flagged'))""")
    assert env["fake"].patches == [] and wire(env, 57) == "true"
    assert live.is_visible(UNDO)
    assert {"msg": "#57 is already flagged for a new label.", "kind": "info"} in toasts(live)


def test_nothing_found_is_refused_on_the_panel(live, env):
    two(env)
    begin(live, env)
    _type(live, "CMD:NEEDLABEL", 1)
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Nothing has been found yet')", arg=NOTICE)
    assert live.evaluate("window.__toastMs")[-1] == 7000


def test_the_button_says_so_under_a_gating_dialog(live, env):
    """processScan stops a scan under one without a word, as window.auditDone knows."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.evaluate("() => { state.activeModal = 'confirm'; }")
    live.click(BUTTON)
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('A dialog behind this panel')", arg=NOTICE)
    assert wire(env, 57) is None
    live.evaluate("() => { state.activeModal = null; }")


def test_undo_that_puts_a_missing_status_back_and_the_keyboard_on_the_button(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.focus(BUTTON)
    live.keyboard.press("Enter")
    live.wait_for_selector(UNDO)
    live.focus(UNDO)
    live.keyboard.press("Enter")
    live.wait_for_selector(UNDO, state="detached")
    strip_says(live, "No label was read for #57")
    assert LABEL not in env["fake"].extra("spool", 57)
    assert live.evaluate("document.activeElement.id") == BUTTON[1:]
    assert {"msg": "Undone: #57 has no label status again.", "kind": "success"} in toasts(live)


def test_a_double_press_of_undo_that_is_one_request(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    live.evaluate("(s) => { const b = document.querySelector(s); b.click(); b.click(); }", UNDO)
    live.wait_for_selector(UNDO, state="detached")
    assert len(sent(live, "/api/audit/needs_label_undo")) == 1


def test_a_refused_undo_says_why_on_the_panel(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    env["fake"].down = True
    live.click(UNDO)
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('its mark stands')", arg=NOTICE)
    assert live.is_enabled(UNDO)             # it can be pressed again


# --- key N -----------------------------------------------------------------------------

def test_n_marks_the_last_spool_found(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    key_n(live)
    live.wait_for_selector(UNDO)
    assert wire(env, 57) == "true"
    assert live.evaluate("state.scanBuffer") == ""       # it doesn't sit in front of the next scan


def test_a_capslock_n_marks_too(live, env):
    """Shift held is a scanner's capital; no Shift is a person's key, whichever case."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.evaluate("""() => { document.body.dispatchEvent(new KeyboardEvent('keydown',
        { key: 'N', bubbles: true, cancelable: true })); }""")
    live.wait_for_selector(UNDO)


@pytest.mark.parametrize("text, ms", [
    ("nook-1", 1), ("nook-1", 26),          # an old bare location label that starts with an N
    ("NOOK-1", 1),                           # a scanner's capital: Shift is down
    ("loc:north", 1), ("loc:north", 26), ("loc:north", 150),     # an N past the label's ':'
    ("LOC:NORTH", 26),
])
def test_n_inside_a_scan_marks_nothing_and_leaves_the_scan_whole(live, env, text, ms):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    before = len(sent(live))
    _type(live, text, ms)
    live.wait_for_function("(n) => window.__sent.filter((p) => p.url.indexOf('identify_scan') !== -1).length > n", arg=before)
    live.wait_for_timeout(120)
    assert sent(live)[before:] == [text]
    assert wire(env, 57) is None


def test_a_stall_before_an_n_in_a_label_marks_nothing(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    before = len(sent(live))
    _type(live, "loc:north", 1, pauses={4: 900})     # a whole label's own pause, right before the 'n'
    live.wait_for_function("(n) => window.__sent.filter((p) => p.url.indexOf('identify_scan') !== -1).length > n", arg=before)
    live.wait_for_timeout(120)
    assert sent(live)[before:] == ["loc:north"] and wire(env, 57) is None


def test_n_then_an_enter_under_50_ms_is_a_scan_of_n(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    _type(live, "n", 1)
    live.wait_for_timeout(120)
    assert wire(env, 57) is None


def test_keys_a_person_left_dont_hold_n_off(live, env):
    """The rule of Group 57's round 5: only what looks like a scan holds a key off."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    _type(live, "x", 1, enter=False)
    live.evaluate("() => { window.__T += 700; }")
    key_n(live)
    live.wait_for_selector(UNDO)
    assert live.evaluate("state.scanBuffer") == ""


def test_held_n_marks_once(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.keyboard.down("n")
    live.keyboard.down("n")
    live.keyboard.down("n")
    live.keyboard.up("n")
    live.wait_for_selector(UNDO)
    live.wait_for_timeout(120)
    assert sent(live).count("CMD:NEEDLABEL") == 1
    assert live.evaluate("state.scanBuffer") == ""


@pytest.mark.parametrize("mod", ["ctrlKey", "altKey", "metaKey", "shiftKey"])
def test_n_with_a_modifier_is_not_the_key(live, env, mod):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.evaluate("""(mod) => { document.body.dispatchEvent(new KeyboardEvent('keydown',
        { key: 'n', [mod]: true, bubbles: true, cancelable: true })); }""", mod)
    live.wait_for_timeout(120)
    assert wire(env, 57) is None


def test_n_under_dones_question_marks_nothing(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.click(DONE)
    live.wait_for_selector(QUESTION)
    key_n(live)
    assert wire(env, 57) is None


def test_n_under_the_shortcut_list_marks_nothing(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.evaluate("() => document.body.insertAdjacentHTML('beforeend', '<div id=\"fcc-shortcuts-overlay\">the list</div>')")
    key_n(live)
    assert wire(env, 57) is None


def test_n_with_the_panel_hidden_marks_nothing(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.click("#fcc-audit-panel-close")
    live.wait_for_selector(PANEL, state="detached")
    key_n(live)
    assert wire(env, 57) is None


def test_n_typed_into_a_box_behind_the_panel_marks_nothing(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.evaluate("() => document.getElementById('edit-name').focus()")
    key_n(live)
    assert wire(env, 57) is None


def test_n_behind_a_scan_still_answered_marks_that_scans_spool(live, env):
    """The strip still shows #57. The person typed #99 and pressed N: it goes out
    behind the scan, so it marks #99. Sent at once it reached the server first."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.evaluate("() => { window.__held = true; window.processScan('ID:99', 'keyboard'); }")
    live.wait_for_function("() => typeof window.__release === 'function' && state.processing")
    key_n(live)
    assert sent(live).count("CMD:NEEDLABEL") == 0        # waiting its turn
    live.evaluate("() => { window.__held = false; window.__release(); }")
    live.wait_for_selector(UNDO, timeout=5000)
    assert wire(env, 99) == "true" and wire(env, 57) is None
    assert sent(live)[-2:] == ["ID:99", "CMD:NEEDLABEL"]


# --- a tile's press --------------------------------------------------------------------

def test_a_press_finds_a_spool_and_makes_it_the_last_found(live, env):
    two(env)
    begin(live, env)
    live.click(tile(57))
    strip_says(live, "No label was read for #57")
    tile_says(live, 57, "found, no label read")
    assert session()["scanned_items"] == [57]
    assert env["fake"].patches == []
    assert live.get_attribute(tile(57), "aria-pressed") == "true"


def test_a_second_press_unfinds_it(live, env):
    two(env)
    begin(live, env)
    live.click(tile(57))
    tile_says(live, 57, "found, no label read")
    live.wait_for_timeout(750)               # past a double press
    live.click(tile(57))
    tile_says(live, 57, "not scanned")
    assert session()["scanned_items"] == []
    live.wait_for_selector(STRIP, state="detached")
    assert live.get_attribute(tile(57), "aria-pressed") == "false"


def test_a_double_press_is_one_press(live, env):
    """Discard's rule on the 🛑 review: a second press under 700 ms does nothing."""
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    live.evaluate("(s) => { const t = document.querySelector(s); t.click(); t.click(); }", tile(57))
    tile_says(live, 57, "found, no label read")
    live.wait_for_timeout(120)
    assert [(b["id"], b["found"]) for b in sent(live, FOUND_URL)] == [(57, True)]


def test_a_scan_never_unfinds(live, env):
    two(env)
    begin(live, env)
    live.click(tile(57))
    tile_says(live, 57, "found, no label read")
    live.focus(tile(57))
    scanned(live, "ID:57")
    scanned(live, "ID:57")
    _type(live, "ID:57", 1)                  # with the focus on the tile, its Enter the scan's
    live.wait_for_function("() => window.__sent.length >= 4")
    live.wait_for_timeout(120)
    assert session()["scanned_items"] == [57]
    assert len(sent(live, FOUND_URL)) == 1


def test_a_label_read_after_a_press_turns_the_tile(live, env):
    two(env)
    begin(live, env)
    live.click(tile(57))
    tile_says(live, 57, "found, no label read")
    _type(live, "ID:57", 1)
    tile_says(live, 57, "✅ scanned")
    assert wire(env, 57) == "false"


def test_a_real_enter_presses_a_tile_once_and_a_held_one_does_nothing_more(live, env):
    two(env)
    begin(live, env)
    live.focus(tile(57))
    live.keyboard.down("Enter")
    live.keyboard.down("Enter")
    live.keyboard.down("Enter")
    live.keyboard.up("Enter")
    tile_says(live, 57, "found, no label read")
    assert [b["found"] for b in sent(live, FOUND_URL)] == [True]


def test_space_presses_a_tile(live, env):
    two(env)
    begin(live, env)
    live.focus(tile(99))
    live.keyboard.press(" ")
    tile_says(live, 99, "found, no label read")


def test_a_scans_enter_on_a_tile_presses_nothing(live, env):
    """Pins Group 50.6's rule on the new buttons."""
    two(env)
    begin(live, env)
    live.focus(tile(57))
    live.keyboard.type("ID:99", delay=0)
    live.keyboard.press("Enter")
    live.wait_for_function("() => window.__sent.length >= 1")
    live.wait_for_timeout(120)
    assert sent(live, FOUND_URL) == [] and sent(live) == ["ID:99"]


def test_extra_and_loaded_tiles_arent_buttons(live, env):
    two(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    begin(live, env)
    scanned(live, "ID:200")
    scanned(live, "ID:242")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Loaded from here')", arg=BODY)
    assert live.evaluate("() => Array.from(document.querySelectorAll('button[data-audit-tile]')).map((b) => b.dataset.auditTile)") == ["57", "99"]
    text = live.text_content(BODY)
    assert text.count("found, no label read") == 2         # the Extra and the loaded spool


def test_a_press_after_the_audit_ended_says_so_on_the_panel(live, env):
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    live.evaluate("() => { window.__noPoll = true; }")       # the panel hasn't heard
    scan(env, "CMD:CANCEL")
    live.evaluate("(s) => { document.querySelector(s).click(); }", tile(57))
    live.wait_for_function("() => document.querySelectorAll('#toast-container .toast-msg').length > 0")
    assert {"msg": "That audit has already ended.", "kind": "error"} in toasts(live)
    assert live.evaluate("window.__toastMs")[-1] == 7000


def test_a_press_with_no_answer_says_so(live, env):
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    live.evaluate("() => { window.__noAnswer = true; }")
    live.click(tile(57))
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes(\"FCC didn't answer\")", arg=NOTICE)
    assert session()["scanned_items"] == []


# --- the keyboard ----------------------------------------------------------------------

def test_the_arrows_move_between_the_tiles_and_wrap(live, env):
    two(env)
    add_spool(env, 134, "LR-MDB-1", container_slot="3")
    begin(live, env)
    live.wait_for_selector(tile(134))

    def at():
        return live.evaluate("document.activeElement.dataset.auditTile")

    live.keyboard.press("ArrowRight")
    assert at() == "57"
    assert live.evaluate("document.querySelectorAll('.fcc-audit-tile.kb-active').length") == 1
    live.keyboard.press("ArrowDown")
    assert at() == "99"
    live.keyboard.press("ArrowRight")
    assert at() == "134"
    live.keyboard.press("ArrowRight")
    assert at() == "57"
    live.keyboard.press("ArrowLeft")
    assert at() == "134"
    live.keyboard.press("ArrowUp")
    assert at() == "99"
    assert live.evaluate("document.querySelectorAll('.fcc-audit-tile.kb-active').length") == 1


def test_the_arrows_then_enter_press_the_tile(live, env):
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    live.keyboard.press("ArrowRight")
    live.keyboard.press("Enter")
    tile_says(live, 57, "found, no label read")


def test_a_tile_keeps_the_keyboard_through_a_redraw(live, env):
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(57))
    live.keyboard.press("ArrowRight")
    live.keyboard.press("ArrowRight")
    scanned(live, "ID:57")
    strip_says(live, "#57")
    assert live.evaluate("document.activeElement.dataset.auditTile") == "99"


def test_the_arrows_leave_a_question_alone(live, env):
    """A pin: no base moves anything on an arrow. Proved on a copy that takes out the
    "only while the panel is on top" test."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.click(DONE)
    live.wait_for_selector(QUESTION)
    live.keyboard.press("ArrowRight")
    assert live.evaluate("document.activeElement.dataset.auditTile || ''") == ""


def test_the_button_keeps_the_keyboard_through_a_redraw(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.focus(BUTTON)
    scanned(live, "ID:99")
    strip_says(live, "#99")
    assert live.evaluate("document.activeElement.id") == BUTTON[1:]


# --- on screen -------------------------------------------------------------------------

@pytest.mark.parametrize("height", [1300, 768])
def test_the_strip_stays_in_view_however_long_the_list_is(live, env, height):
    """It is what N and the button act on, and a person looks for it right after a
    scan, so it can't scroll away with the tiles below."""
    live.set_viewport_size({"width": 1366, "height": height})
    for sid in range(1000, 1060):
        add_spool(env, sid, "LR-MDB-1")
    begin(live, env)
    scanned(live, "ID:1000")
    live.wait_for_selector(BUTTON)
    assert live.evaluate("(s) => { const b = document.querySelector(s); return b.scrollHeight > b.clientHeight; }", BODY)
    live.evaluate("(s) => { document.querySelector(s).scrollTop = 0; }", BODY)
    assert _on_top(live, BUTTON) and _on_top(live, "#fcc-audit-panel-qr-needlabel")


def test_a_tile_the_arrows_reach_isnt_under_the_strip(live, env):
    live.set_viewport_size({"width": 1366, "height": 768})
    for sid in range(1000, 1060):
        add_spool(env, sid, "LR-MDB-1")
    begin(live, env)
    scanned(live, "ID:1000")
    live.wait_for_selector(BUTTON)
    live.evaluate("(s) => { document.querySelector(s).scrollTop = 0; }", BODY)
    for _ in range(30):
        live.keyboard.press("ArrowRight")
    assert live.evaluate("document.activeElement.dataset.auditTile") == "1029"
    assert _on_top(live, tile(1029))


def test_a_long_name_stays_on_one_line_and_the_panel_doesnt_widen(live, env):
    add_spool(env, 57, "LR-MDB-1", name="A Very Long Colour Name " * 8)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(STRIP)
    boxes = live.evaluate("""([strip, panel]) => { const s = document.querySelector(strip).getBoundingClientRect();
        const p = document.querySelector(panel).querySelector('div').getBoundingClientRect();
        return { sr: s.right, pr: p.right }; }""", [STRIP, PANEL])
    assert boxes["sr"] <= boxes["pr"], boxes
