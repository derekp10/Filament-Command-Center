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
the point, all in one tick, so the wait key N takes really is "more keys came";
the real keyboard where a browser's own press is what is tested (a synthetic Enter
clicks nothing), and on real timers where that wait itself is.

The sections from "the scans around an audit's end" on are Group 58's review, on the
same page: the real accumulator, a real keyboard, a real mouse.

RED on 39b0d1a unless a test says it pins what was already right; the review's say
what they were red on.
"""
from __future__ import annotations

import time

import pytest

import app as app_module
import state
from test_audit_panel_58_js import CANCEL, DONE, HUB, NOTICE, PANEL, PILL, TILE, _on_top, audit  # noqa: F401  (audit: the fixture)
from test_audit_session_58 import ROWS, add_spool, env, scan, session, start  # noqa: F401  (env: the fixture)
from test_scanner_safe_dialogs_61_js import MODULES, page61  # noqa: F401  (page61: the fixture)
from test_slow_scan_slash_js import _type

LABEL = "needs_label_print"
BODY = "#fcc-audit-panel-body"
STRIP = "#fcc-audit-last-found"
STATUS = STRIP + " [role=status]"
BUTTON = "#fcc-audit-panel-needlabel"
UNDO = "#fcc-audit-label-undo"
FOUND_URL = "/api/audit/found"
QUESTION = "#fcc-audit-done-question"
SHEET = QUESTION + " .fcc-apc-panel"
YES = QUESTION + " .fcc-apc-yes"
BACK = QUESTION + " .fcc-apc-no"
PARK_URL = "/api/audit/park"
UNDO_URL = "/api/audit/needs_label_undo"
HIDE = "#fcc-audit-panel-close"
LOOSE_BTN = "#fcc-audit-panel-loose"
PAST_N = 220            # NEED_LABEL_WAIT_MS (inv_cmd.js) and a little: a check that nothing was marked
PAST_A_DOUBLE_PRESS = 720                       # DOUBLE_PRESS_MS (inv_cmd.js) and a little


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
    page.wait_for_timeout(PAST_N)


SHORTCUTS = "#fcc-shortcuts-overlay"
# Bootstrap's own rules for the classes the list's markup leans on (no CDN here).
BOOTSTRAP_POSITION = """.position-fixed { position: fixed !important; } .top-0 { top: 0 !important; }
.start-0 { left: 0 !important; } .top-50 { top: 50% !important; } .start-50 { left: 50% !important; }
.translate-middle { transform: translate(-50%, -50%) !important; } .w-100 { width: 100% !important; }
.h-100 { height: 100% !important; }"""


def real_shortcut_list(page):
    """The ⌨️ list's own markup from dashboard.html and the real shortcuts_registry.js.
    Before an overlay mounts, as on the page: its capture-phase Escape runs first."""
    src = (HUB / "templates" / "dashboard.html").read_text(encoding="utf-8")
    start_at = src.index('<div id="fcc-shortcuts-overlay-backdrop"')
    page.add_style_tag(content=BOOTSTRAP_POSITION)
    page.evaluate("(markup) => document.body.insertAdjacentHTML('beforeend', markup)",
                  src[start_at:src.index("<!-- L184", start_at)])
    page.add_script_tag(content=(MODULES / "shortcuts_registry.js").read_text(encoding="utf-8"))


def show_shortcut_list(page):
    """A person's real ?. Its handler clears the scan buffer now and again a tick later
    (window.clearScanBuffer), and the browser may run the next key before that tick, so
    wait one timer turn: else a key typed next could be wiped (a sweep flake, 2026-11-02)."""
    page.keyboard.press("?")
    page.wait_for_function("(s) => document.querySelector(s).style.display === 'block'", arg=SHORTCUTS)
    page.evaluate("() => new Promise((done) => setTimeout(done, 0))")


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


def test_an_extra_says_so_and_where_fcc_has_it_then_its_label(live, env):
    """Finding 40. Its tile can be below the fold or under the strip, and a toast is under
    the panel, so all the person saw change was the count. RED on 1f8e03a."""
    two(env)
    add_spool(env, 200, "LR-MDB-2", container_slot="3")
    begin(live, env)
    scanned(live, "ID:200")
    strip_says(live, "Extra: FCC has #200 at LR-MDB-2 slot 3. No label was read for #200")
    scanned(live, "ID:200", "barcode")
    strip_says(live, "Extra: FCC has #200 at LR-MDB-2 slot 3. #200's label was read")


def test_a_spool_loaded_from_here_says_what_its_on_then_its_label(live, env):
    """RED on 1f8e03a."""
    two(env)
    add_spool(env, 242, "XL-1", physical_source="LR-MDB-1", physical_source_slot="4")
    begin(live, env)
    scanned(live, "ID:242")
    strip_says(live, "#242 is loaded on XL-1 from here. No label was read for #242")


def test_an_extra_spoolman_wouldnt_answer_for_reads_as_a_sentence(live, env):
    """`where` holds logic.AUDIT_WHERE_UNREAD, and FCC "has it at" no such place. RED on
    1f8e03a."""
    two(env)
    add_spool(env, 300, "LR-MDB-2")
    begin(live, env)
    env["fake"].down = True
    scanned(live, "ID:300")
    env["fake"].down = False
    assert session()["rows"]["300"]["where"] == "couldn't read where FCC has it"
    strip_says(live, "Extra: #300: couldn't read where FCC has it. No label was read for #300")
    assert "FCC has #300" not in live.text_content(STATUS)


@pytest.mark.parametrize("place, extra, words", [
    ("", {}, "Extra: FCC has #300 at Unassigned."),
    ("UNKNOWN", {"fcc_pre_audit_location": "LR-MDB-2:3@2026-11-01"},
     "Extra: FCC has #300 at Unknown (marked lost by the audit of LR-MDB-2 slot 3 on 2026-11-01)."),
    ("A<b>C", {}, "Extra: FCC has #300 at A<b>C."),
], ids=["unassigned", "lost-by-an-audit", "a-place-that-is-html"])
def test_each_place_an_extra_can_be_at_reads_as_a_sentence(live, env, place, extra, words):
    """RED on 1f8e03a."""
    two(env)
    add_spool(env, 300, place, **extra)
    begin(live, env)
    scanned(live, "ID:300")
    strip_says(live, words)


def test_a_spool_the_list_expected_says_only_its_label(live, env):
    """A pin: the kind's words are for a spool that isn't on the list."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    strip_says(live, "No label was read for #57")
    assert live.text_content(STATUS).strip() == "No label was read for #57"


@pytest.mark.parametrize("size", ["standard", "large", "xlarge"])
def test_the_longest_line_stays_inside_the_strip_at_every_text_size(live, env, size):
    """A place with nowhere to break, at the sizes the text-size guard reads, on a small
    laptop: the line wraps inside the strip, and the button and its QR stay in view."""
    live.set_viewport_size({"width": 1366, "height": 768})
    live.evaluate("(s) => { document.documentElement.dataset.fccTextSize = s; }", size)
    two(env)
    add_spool(env, 300, "UNKNOWN", fcc_pre_audit_location=f"{'X' * 120}:3@2026-11-01")
    begin(live, env)
    scanned(live, "ID:300")
    strip_says(live, "Extra: FCC has #300 at Unknown (marked lost by the audit of XXX")
    boxes = live.evaluate("""([strip, status, body]) => {
        const box = (s) => document.querySelector(s).getBoundingClientRect();
        const b = document.querySelector(body);
        const line = document.querySelector(status).firstElementChild.getBoundingClientRect();
        return { line: [line.left, line.right], strip: [box(strip).left, box(strip).right],
                 widened: b.scrollWidth - b.clientWidth }; }""", [STRIP, STATUS, BODY])
    assert boxes["strip"][0] <= boxes["line"][0] and boxes["line"][1] <= boxes["strip"][1], boxes
    assert boxes["widened"] <= 0, boxes
    assert _on_top(live, BUTTON) and _on_top(live, "#fcc-audit-panel-qr-needlabel")


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
    live.wait_for_timeout(PAST_N)
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
    live.wait_for_timeout(PAST_N)
    assert sent(live)[before:] == ["loc:north"] and wire(env, 57) is None


def test_n_then_an_enter_before_its_wait_is_up_is_a_scan_of_n(live, env):
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    _type(live, "n", 1)
    live.wait_for_timeout(PAST_N)
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
    live.wait_for_timeout(PAST_N)
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
    live.wait_for_timeout(PAST_N)
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
    """The real list, opened by a real ?: test_audit_stacking_58_js.py has what follows."""
    real_shortcut_list(live)
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    show_shortcut_list(live)
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


def a_long_list(page, env, rows=30, found=True):
    """`rows` tiles on a small laptop, more than the panel shows, the view at the top of
    the list. `found`: the first of them scanned, so the strip is up."""
    ids = list(range(1000, 1000 + rows))
    for sid in ids:
        add_spool(env, sid, "LR-MDB-1")
    page.set_viewport_size({"width": 1366, "height": 768})
    begin(page, env)
    page.wait_for_selector(tile(ids[-1]))
    if found:
        scanned(page, f"ID:{ids[0]}")
        page.wait_for_selector(BUTTON)
    page.evaluate("(s) => { document.querySelector(s).scrollTop = 0; }", BODY)
    return ids


# The tile and its focus ring (2 px, 1 px out) inside the box the strip leaves.
RING_CLEAR = r"""([sel, body, strip]) => {
    const t = document.querySelector(sel).getBoundingClientRect();
    const b = document.querySelector(body).getBoundingClientRect();
    const s = document.querySelector(strip);
    const floor = s ? Math.min(b.bottom, s.getBoundingClientRect().top) : b.bottom;
    return t.top - 3 >= b.top && t.bottom + 3 <= floor;
}"""


def walked(page, key, steps):
    """Each tile `key` lands on, and whether it is seen: its centre can be hit, and the
    whole of it and its ring clear the strip and the body's top edge. A tile under the
    strip has the keyboard on it with no highlight or name to see."""
    seen = []
    for _ in range(steps):
        page.keyboard.press(key)
        sid = page.evaluate("document.activeElement.dataset.auditTile")
        seen.append((int(sid), _on_top(page, tile(sid)) and page.evaluate(RING_CLEAR, [tile(sid), BODY, STRIP])))
    return seen


@pytest.mark.parametrize("key", ["ArrowRight", "ArrowLeft"], ids=["forward", "back"])
def test_every_tile_the_arrows_reach_is_in_view(live, env, key):
    """Finding 37. A tile under the sticky strip is already inside the scrolling box, so
    neither focus() nor scrollIntoView moved it, and Enter or Space then found a spool
    nobody could see. Past the far end too, where the walk wraps. RED on 1f8e03a."""
    ids = a_long_list(live, env)
    seen = walked(live, key, len(ids) + 1)
    assert {sid for sid, _ in seen} == set(ids)
    assert [sid for sid, shown in seen if not shown] == []


@pytest.mark.parametrize("key, first", [("Tab", 0), ("Shift+Tab", -1)], ids=["forward", "back"])
def test_every_tile_tab_reaches_is_in_view(live, env, key, first):
    """The same gap for Tab, whose focus no key handler sees: a capture-phase `focus`
    listener, because mountOverlay's guard stops focusin at the document. RED on
    1f8e03a."""
    ids = a_long_list(live, env)
    live.focus(tile(ids[first]))
    seen = walked(live, key, len(ids) - 1)
    assert sorted(sid for sid, _ in seen) == sorted(set(ids) - {ids[first]})
    assert [sid for sid, shown in seen if not shown] == []


def test_on_a_window_too_short_for_a_sticky_strip_every_tile_still_shows(live, env):
    """Under 34rem the strip stays in the flow, below the tiles (global.css): only the
    body's edges are left to clear. A pin: the browser's own focus scroll does this."""
    ids = a_long_list(live, env)
    live.set_viewport_size({"width": 1366, "height": 500})
    assert live.evaluate("(s) => getComputedStyle(document.querySelector(s)).position", STRIP) == "static"
    seen = walked(live, "ArrowRight", len(ids))
    assert [sid for sid, shown in seen if not shown] == []


def test_a_strip_that_appears_doesnt_cover_the_keyboards_tile(live, env):
    """The first find draws the strip over the tiles, and the redraw keeps the keyboard
    on its tile. RED on 1f8e03a."""
    ids = a_long_list(live, env, found=False)
    box = live.evaluate("""(s) => { const b = document.querySelector(s).getBoundingClientRect();
        return { top: b.top, bottom: b.bottom }; }""", BODY)
    lowest = live.evaluate("""([sel, bottom]) => Array.from(document.querySelectorAll(sel))
        .filter((t) => t.getBoundingClientRect().bottom < bottom).pop().dataset.auditTile""",
                           [".fcc-audit-tile", box["bottom"]])
    live.focus(tile(lowest))
    scanned(live, f"ID:{ids[0]}")
    live.wait_for_selector(BUTTON)
    assert live.evaluate("document.activeElement.dataset.auditTile") == lowest
    assert _on_top(live, tile(lowest))


@pytest.mark.parametrize("edge", ["strip", "top"])
def test_a_click_on_a_tile_half_out_of_view_still_presses_it(live, env, edge):
    """A click's mousedown focuses the tile. Pressed this close to the edge, a tile scrolled
    clear of it leaves the pointer in the gap between tiles, the mouseup lands there, and
    the click reaches no tile. A pin: proved on a copy with no :focus-visible test in the
    panel's `focus` listener."""
    a_long_list(live, env)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    # A tile with 12 px of it showing, at the strip's top edge or the body's, and the
    # pointer 3 px from that edge.
    aim = live.evaluate("""([body, strip, edge]) => {
        const b = document.querySelector(body);
        const line = edge === 'strip' ? document.querySelector(strip).getBoundingClientRect().top
                                      : b.getBoundingClientRect().top;
        const tiles = Array.from(document.querySelectorAll('.fcc-audit-tile'));
        const t = tiles.find((el) => el.getBoundingClientRect().top > line + 200);
        const r = t.getBoundingClientRect();
        b.scrollTop += edge === 'strip' ? r.top + 12 - line : r.bottom - 12 - line;
        const now = t.getBoundingClientRect();
        return { id: t.dataset.auditTile, x: now.left + now.width / 2, line,
                 hit: edge === 'strip' ? now.top - line : now.bottom - line,
                 y: edge === 'strip' ? now.top + 9 : now.bottom - 9 }; }""", [BODY, STRIP, edge])
    assert aim["hit"] == pytest.approx(-12 if edge == "strip" else 12, abs=1)    # it really straddles the edge
    press(live, (aim["x"], aim["y"]))
    tile_says(live, aim["id"], "found, no label read")
    assert [b["id"] for b in sent(live, FOUND_URL)] == [int(aim["id"])]


def test_a_long_name_stays_on_one_line_and_the_panel_doesnt_widen(live, env):
    add_spool(env, 57, "LR-MDB-1", name="A Very Long Colour Name " * 8)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(STRIP)
    boxes = live.evaluate("""([strip, panel]) => { const s = document.querySelector(strip).getBoundingClientRect();
        const p = document.querySelector(panel).querySelector('div').getBoundingClientRect();
        return { sr: s.right, pr: p.right }; }""", [STRIP, PANEL])
    assert boxes["sr"] <= boxes["pr"], boxes


# --- the scans around an audit's end (Group 58 review) --------------------------------
# A scan read during an audit waits in the queue while FCC is busy, and the queue used
# to send it on once the audit was over: the dim holds it for the whole park, and
# neither guard could see it (the page's location guard reads the flag as the answer
# lands, by which time the end has cleared it, and the server's "already finishing"
# never fired, because the scan never reached it).

BUFFERED = 7            # in the scan buffer, on the page and on the server
FLAGGED = 8             # flagged for a new label, and in nobody's buffer
# Each would act if it went out: a cart's own label files the whole buffer there, a slot
# label loads it, and a flagged spool's label outside an audit clears its flag.
LABELS = {"location": "LOC:CR-CT-1", "slot": "LOC:LR-MDB-2:SLOT:2", "flagged-label": f"ID:{FLAGGED}"}

# Answers one request's way: holds the park, and the moves go to the real routes.
WATCH_MOVES = r"""() => {
    window.__moves = [];
    const f = window.fetch;
    window.fetch = async (url, opts) => {
        const u = String(url);
        if (u.indexOf('/api/audit/park') !== -1 && window.__holdPark) {
            await new Promise((r) => { window.__parkGo = r; });
            return f(url, opts);
        }
        if (/\/api\/(smart_move|manage_contents)/.test(u)) {
            const text = await window.__fcc(u, 'POST', opts.body);
            window.__moves.push({ url: u, body: JSON.parse(opts.body) });
            return { ok: true, status: 200, json: async () => JSON.parse(text), text: async () => text };
        }
        return f(url, opts);
    };
}"""


def real_scan(page, text):
    """A scanner: the real keyboard, through the real accumulator."""
    page.keyboard.type(text, delay=2)
    page.keyboard.press("Enter")


def queued(page):
    return page.evaluate("state.scanQueue.map((q) => q.text)")


def at(env, sid):
    return env["fake"].records["spool"][sid]["location"]


def a_buffer(page, env):
    add_spool(env, BUFFERED, "CR-CT-1-R1", name="Held")
    add_spool(env, FLAGGED, "CR-CT-1-R2", name="Flagged", needs_label_print=True)
    state.GLOBAL_BUFFER.append({"id": BUFFERED, "display": "#7 Held"})
    page.evaluate(WATCH_MOVES)
    page.evaluate("""([rows, id]) => { state.allLocations = rows;
        state.heldSpools = [{ id, display: '#' + id + ' Held', color: '888888' }]; }""", [ROWS, BUFFERED])


def in_flight(page, text):
    """`text` out, with its answer held until window.__release(). Only its."""
    page.evaluate("() => { window.__held = true; }")
    real_scan(page, text)
    page.wait_for_function("() => typeof window.__release === 'function' && state.processing")
    page.evaluate("() => { window.__held = false; }")


def question_up(page):
    page.click(DONE)
    page.wait_for_selector(YES)


def to_the_park(page, env):
    """#57 found and #99 not: Done, Yes, and the park on its way."""
    two(env)
    begin(page, env)
    scanned(page, "ID:57")
    page.evaluate("() => { window.__holdPark = true; }")
    question_up(page)
    page.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    page.click(YES)
    page.wait_for_function("() => typeof window.__parkGo === 'function'")
    assert page.evaluate("state.processing") is True and page.evaluate("state.auditActive") is True


def during_the_park(page, env, label):
    to_the_park(page, env)
    real_scan(page, label)
    assert queued(page) == [label]
    page.evaluate("() => window.__parkGo()")


def after_a_nothing_to_park_done(page, env, label):
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    begin(page, env)
    scanned(page, "ID:57")
    in_flight(page, "CMD:DONE")
    real_scan(page, label)
    assert queued(page) == [label]
    page.evaluate("() => window.__release()")


def behind_a_cancel(page, env, label):
    """The panel stays pressable while a scan is answered, and Cancel goes straight
    out, the safe bail, so it leaves what is queued behind it."""
    two(env)
    begin(page, env)
    in_flight(page, "ID:57")
    real_scan(page, label)
    assert queued(page) == [label]
    page.click(CANCEL)
    page.wait_for_function("() => state.auditActive === false")
    page.evaluate("() => window.__release()")


ENDS = {"during-the-park": during_the_park, "after-a-nothing-to-park-done": after_a_nothing_to_park_done,
        "behind-a-cancel": behind_a_cancel}


@pytest.mark.parametrize("label", LABELS.values(), ids=LABELS.keys())
@pytest.mark.parametrize("end", ENDS.values(), ids=ENDS.keys())
def test_a_scan_read_as_an_audit_ends_never_runs_after_it(live, env, end, label):
    """Findings 22 and 36, and 30's Cancel half. RED on 8373ecd: the location label
    moved the buffered spool to the cart, the slot label loaded it into the slot, and
    the flagged label cleared the flag and joined the buffer, all after the audit."""
    a_buffer(live, env)
    end(live, env, label)
    live.wait_for_function("() => state.auditActive === false && !state.scanQueue.length && !state.processing")
    live.wait_for_timeout(120)              # a move's answer, if one had gone out
    assert label not in sent(live)
    assert live.evaluate("window.__moves") == []
    assert at(env, BUFFERED) == "CR-CT-1-R1" and wire(env, FLAGGED) == "true"
    assert live.evaluate("state.heldSpools.map((s) => s.id)") == [BUFFERED]
    assert [b["id"] for b in state.GLOBAL_BUFFER] == [BUFFERED]
    words = f"The audit has ended, so {label} did nothing. Scan it again if you meant it."
    assert {"msg": words, "kind": "warning"} in toasts(live)
    assert 7000 in live.evaluate("window.__toastMs")
    assert f"⚠️ {words}" in live.evaluate("window.__logs")


def test_scanned_again_after_the_audit_it_acts(live, env):
    """"Scan it again if you meant it": the drop leaves no second-read memory. A pin:
    proved on a copy that notes the dropped label as read."""
    a_buffer(live, env)
    during_the_park(live, env, "LOC:CR-CT-1")
    live.wait_for_function("() => state.auditActive === false && !state.scanQueue.length && !state.processing")
    real_scan(live, "LOC:CR-CT-1")
    live.wait_for_function("() => window.__moves.length > 0")
    assert at(env, BUFFERED) == "CR-CT-1"


def test_a_scan_read_during_a_park_that_was_refused_still_counts(live, env):
    """The audit runs on, so the scan is the audit's. A pin: proved on a copy that
    drops whatever it held during a park."""
    a_buffer(live, env)
    to_the_park(live, env)
    real_scan(live, "ID:99")
    env["fake"].list_reads_fail = True      # Done's plan can't be read again: nothing moves
    live.evaluate("() => window.__parkGo()")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Try Done again')", arg=NOTICE)
    env["fake"].list_reads_fail = False
    live.wait_for_function("() => !state.scanQueue.length && !state.processing")
    live.wait_for_function("() => state.auditRequestsOut === 0")
    assert sent(live)[-1] == "ID:99" and 99 in session()["scanned_items"]
    assert live.evaluate("state.auditActive") is True


def test_cmd_audit_read_during_the_park_starts_the_next_audit(live, env):
    """Its one exemption. A pin of what the drop leaves alone: proved on a copy with no
    exemption."""
    a_buffer(live, env)
    during_the_park(live, env, "CMD:AUDIT")
    live.wait_for_function("() => state.auditActive === true && !state.scanQueue.length && !state.processing")
    live.wait_for_function("() => state.auditRequestsOut === 0")
    assert sent(live)[-1] == "CMD:AUDIT" and session()["active"] is True
    assert live.is_visible(PANEL)


def test_a_slot_label_the_page_sent_after_an_idle_end_loads_nothing(live, env):
    """The stamp on the wire: the page hasn't heard the audit ended (a hidden panel has
    no poll), so nothing here can stop it, and the server does. RED on 8373ecd: the
    buffered spool went into the slot."""
    a_buffer(live, env)
    two(env)
    begin(live, env)
    live.click(HIDE)
    live.wait_for_selector(PANEL, state="detached")
    state.reset_audit()                     # the watchdog's end, as far as this page knows
    real_scan(live, "LOC:LR-MDB-2:SLOT:2")
    words = "The audit has ended, so LOC:LR-MDB-2:SLOT:2 did nothing. Scan it again if you meant it."
    live.wait_for_function("(w) => Array.from(document.querySelectorAll('#toast-container .toast-msg'))"
                           ".some((e) => e.innerText === w)", arg=words)
    assert at(env, BUFFERED) == "CR-CT-1-R1" and [b["id"] for b in state.GLOBAL_BUFFER] == [BUFFERED]
    assert live.evaluate("state.heldSpools.map((s) => s.id)") == [BUFFERED]


# --- Done, in its turn ---------------------------------------------------------------

def three(env):
    two(env)
    add_spool(env, 134, "LR-MDB-1", container_slot="3")


def buttons_down(page):
    return page.evaluate("""([d, c]) => [document.querySelector(d).disabled, document.querySelector(c).disabled]""",
                         [DONE, CANCEL])


@pytest.mark.parametrize("press", ["click", "space"])
def test_done_takes_its_turn_behind_the_scans_already_read(live, env, press):
    """Findings 29, 30 and 38. One scan in flight, one queued. Enter on Done is already
    held there (personMayPress); a click and a Space weren't. RED on 8373ecd: CMD:DONE
    went out ahead of ID:99, the question listed #99 as not scanned and refused its
    scan, and a Yes parked the spool in the person's hand."""
    three(env)
    begin(live, env)
    live.wait_for_selector(DONE)
    if press == "space":
        live.focus(DONE)
    in_flight(live, "ID:57")
    real_scan(live, "ID:99")
    assert queued(live) == ["ID:99"]
    if press == "click":
        live.click(DONE)
    else:
        live.keyboard.press(" ")
    assert queued(live) == ["ID:99", "CMD:DONE"]
    assert buttons_down(live) == [True, True]
    live.evaluate("() => window.__release()")
    live.wait_for_selector(SHEET)
    assert sent(live) == ["ID:57", "ID:99", "CMD:DONE"]
    text = live.text_content(SHEET)
    assert "#134" in text and "#57" not in text and "#99" not in text
    assert "(Ignored" not in text


def test_a_second_press_of_a_queued_done_queues_nothing(live, env):
    """The buttons stay down until it has gone out and been answered: the answer to the
    scan ahead of it mustn't let them up. RED on 8373ecd, where Done went straight out."""
    three(env)
    begin(live, env)
    live.wait_for_selector(DONE)
    in_flight(live, "ID:57")
    real_scan(live, "ID:99")
    live.click(DONE)
    live.evaluate("() => { window.__held = true; window.__release(); }")     # ID:57's answer
    live.wait_for_function("() => state.scanQueue.map((q) => q.text).join() === 'CMD:DONE'")
    assert buttons_down(live) == [True, True]
    live.click(DONE, force=True)
    assert queued(live) == ["CMD:DONE"]
    live.evaluate("() => { window.__held = false; window.__release(); }")    # ID:99's
    live.wait_for_selector(SHEET)
    assert sent(live).count("CMD:DONE") == 1 and live.locator(SHEET).count() == 1


def test_a_queued_done_the_audit_outlived_frees_the_buttons(live, env):
    """Dropped, it has no answer to come. A scanned Cancel ahead of it ends the audit, and
    the next audit's Done still has to be pressable. RED on 8373ecd, where Done went
    straight out."""
    three(env)
    begin(live, env)
    live.wait_for_selector(DONE)
    in_flight(live, "ID:57")
    real_scan(live, "CMD:CANCEL")
    live.click(DONE)
    assert queued(live) == ["CMD:CANCEL", "CMD:DONE"]
    live.evaluate("() => window.__release()")
    live.wait_for_function("() => state.auditActive === false && !state.scanQueue.length && !state.processing")
    assert "CMD:DONE" not in sent(live)
    assert any("so CMD:DONE did nothing" in t["msg"] for t in toasts(live))
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    begin(live, env)
    live.wait_for_selector(DONE)
    assert buttons_down(live) == [False, False]


def test_a_queued_done_stopped_short_of_the_server_frees_the_buttons(live, env):
    """An open question holds it off and says why, so no answer comes: a press behind
    the scanned Done that opened it. RED on 8373ecd, where Done went straight out."""
    three(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(DONE)
    in_flight(live, "CMD:DONE")             # opens the question once it is answered
    live.click(DONE)
    assert queued(live) == ["CMD:DONE"] and buttons_down(live) == [True, True]
    live.evaluate("() => window.__release()")
    live.wait_for_selector(SHEET)
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('(Ignored: CMD:DONE)')", arg=SHEET)
    assert sent(live).count("CMD:DONE") == 1
    assert buttons_down(live) == [False, False]


def test_a_keyboard_on_done_comes_back_after_its_turn(live, env):
    """A disabled button drops the focus, and it comes back with the answer: here the
    refusal of a Done that waited its turn. RED on 8373ecd, where Done went straight out
    and the plan it read found nothing wrong."""
    three(env)
    begin(live, env)
    live.wait_for_selector(DONE)
    live.focus(DONE)
    in_flight(live, "ID:57")
    live.keyboard.press(" ")
    env["fake"].list_reads_fail = True      # Done's answer: "try again"
    live.evaluate("() => window.__release()")
    live.wait_for_function("(s) => document.querySelector(s).textContent.includes('Try Done again')", arg=NOTICE)
    env["fake"].list_reads_fail = False
    live.wait_for_function("(s) => !document.querySelector(s).disabled", arg=DONE)
    assert live.evaluate("document.activeElement.id") == DONE[1:]


# --- a double click ---------------------------------------------------------------------
# With no Bootstrap here the sizes where a question's button really lies over the
# panel's can't be met, so a test lays one over the other; the real sizes are
# test_audit_done_question_58_e2e.py's, on the real dashboard.

LAY_OVER = r"""([top, under]) => {
    const r = document.querySelector(under).getBoundingClientRect();
    const st = document.createElement('style');
    st.textContent = `${top} { position: fixed !important; margin: 0 !important; left: ${r.left}px !important;
        top: ${r.top}px !important; width: ${r.width}px !important; height: ${r.height}px !important; }`;
    document.head.appendChild(st);
    return [r.left + r.width / 2, r.top + r.height / 2];
}"""
HIT = r"""([x, y]) => { const e = document.elementFromPoint(x, y);
    const b = e && e.closest('button');
    return b ? (b.id || b.dataset.auditTile || b.className) : (e && (e.id || e.tagName)); }"""


def lay_over(page, top, under):
    """`top` will open exactly over `under`. Answers the middle of them."""
    return page.evaluate(LAY_OVER, [top, under])


def press(page, at_xy, second=False):
    """One press of a real mouse; `second`: a double click's."""
    page.mouse.move(*at_xy)
    page.mouse.down(click_count=2 if second else 1)
    page.mouse.up(click_count=2 if second else 1)


def test_a_double_click_on_done_answers_no_question(live, env):
    """Finding 34. The question opens with Park under the pointer, and the second click
    answered it: every spool parked, and nobody had read a word. RED on 8373ecd: #99
    went to Unknown."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(DONE)
    xy = lay_over(live, YES, DONE)
    press(live, xy)
    live.wait_for_selector(YES)
    assert "fcc-apc-yes" in live.evaluate(HIT, xy)
    press(live, xy, second=True)
    live.wait_for_timeout(150)
    assert live.is_visible(YES) and sent(live, PARK_URL) == [] and at(env, 99) == "LR-MDB-1"
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    press(live, xy)                         # a person who has read it
    live.wait_for_selector(PANEL, state="detached")
    assert len(sent(live, PARK_URL)) == 1 and at(env, 99) == "UNKNOWN"


UNDER_BACK = {"cancel-audit": (CANCEL, CANCEL[1:]), "a-tile": (tile(99), "99"), "done": (DONE, DONE[1:]),
              "needs-a-label": (BUTTON, BUTTON[1:]), "undo-that": (UNDO, UNDO[1:]), "hide": (HIDE, HIDE[1:]),
              "loose-spools": (LOOSE_BTN, LOOSE_BTN[1:])}


@pytest.mark.parametrize("under, hit", UNDER_BACK.values(), ids=UNDER_BACK.keys())
def test_a_double_click_on_back_changes_nothing_under_it(live, env, under, hit):
    """Findings 35 and 26. The question closes on the first click, and the second lands
    on the panel. RED on 8373ecd: Cancel Audit ended the audit, a tile found a spool
    nobody touched, and each of the others did what it does."""
    three(env)
    live.evaluate("() => { window.__loose = 0; window.openLooseList = () => { window.__loose += 1; return null; }; }")
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    env["fake"].patches.clear()
    xy = lay_over(live, BACK, under)
    question_up(live)
    live.wait_for_selector(BACK)
    # A person's press on Back. Under 700 ms after Done's, at its spot ("done"), it is
    # Done's own double click, which reaches nothing (the re-review's shield).
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    press(live, xy)
    live.wait_for_selector(QUESTION, state="detached")
    assert live.evaluate(HIT, xy) == hit
    before = (sent(live), sent(live, FOUND_URL), sent(live, UNDO_URL), list(session()["scanned_items"]))
    press(live, xy, second=True)
    live.wait_for_timeout(150)
    assert (sent(live), sent(live, FOUND_URL), sent(live, UNDO_URL), list(session()["scanned_items"])) == before
    assert env["fake"].patches == [] and session()["active"] is True
    assert live.is_visible(DONE) and not live.locator(QUESTION).count()
    assert live.evaluate("window.__loose") == 0


def test_the_panel_takes_clicks_again_once_a_double_press_is_past(live, env):
    """A press after it is meant. A pin: proved on a copy that never lifts the shield."""
    three(env)
    begin(live, env)
    live.wait_for_selector(tile(99))
    xy = lay_over(live, BACK, tile(99))
    question_up(live)
    live.wait_for_selector(BACK)
    press(live, xy)
    live.wait_for_selector(QUESTION, state="detached")
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    press(live, xy)
    tile_says(live, 99, "found, no label read")


def test_a_double_click_on_back_that_brings_a_hidden_panel_back_lands_on_nothing(live, env):
    """The panel opens under the pointer, so the guard has to come with it. RED on
    8373ecd: the second click cancelled the audit it had just shown."""
    three(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    xy = lay_over(live, BACK, CANCEL)
    live.click(HIDE)
    live.wait_for_selector(PANEL, state="detached")
    scanned(live, "CMD:DONE")
    live.wait_for_selector(BACK)
    press(live, xy)
    live.wait_for_selector(QUESTION, state="detached")
    live.wait_for_selector(CANCEL)
    assert live.evaluate(HIT, xy) == CANCEL[1:]
    press(live, xy, second=True)
    live.wait_for_timeout(150)
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True
    assert live.is_visible(PANEL)


# --- a double click whose first press takes the panel away, or brings it (re-review) ------
# The panel's root is gone by the second press, or wasn't there for the first, so no shield
# on it could help. Under the panel here is a button of the test's own that counts every
# event reaching it, where the deck, the buffer or a pill would be on the page.
# test_audit_double_click_58_e2e.py has every control at the real sizes, on the real page.

BEHIND = r"""(sel) => {
    const r = document.querySelector(sel).getBoundingClientRect();
    const b = document.createElement('button');
    b.type = 'button';
    b.id = 'fcc-test-behind';
    b.textContent = 'behind';
    b.style.cssText = `position:fixed; margin:0; left:${r.left}px; top:${r.top}px;
        width:${r.width}px; height:${r.height}px; z-index:5;`;
    window.__behind = [];
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(
        (t) => b.addEventListener(t, () => window.__behind.push(t)));
    document.body.appendChild(b);
    return [r.left + r.width / 2, r.top + r.height / 2];
}"""
DOUBLE_CLICK_S = 0.68      # the shield's 700 ms, and a little room


def behind(page, sel):
    """A button of the test's own under `sel`, below the panel. Answers its middle."""
    return page.evaluate(BEHIND, sel)


def double_click(page, xy, then=None, state="visible"):
    """A real double click at `xy`: two presses of the real mouse, the second a double
    click's. `then`: a selector to wait for between them (`state`), so the first press's
    effect is on screen, as with a quick answer; else a person's 120 ms."""
    started = time.monotonic()
    press(page, xy)
    if then:
        page.wait_for_selector(then, state=state, timeout=650)
    else:
        page.wait_for_timeout(120)
    assert time.monotonic() - started < DOUBLE_CLICK_S, "the first press took too long to be a double click's"
    press(page, xy, second=True)


def reached(page):
    return {"behind": page.evaluate("window.__behind"),
            "focus": page.evaluate("document.activeElement.id || document.activeElement.tagName")}


TAKES_IT_AWAY = {"cancel-audit": CANCEL, "done-with-nothing-to-park": DONE, "hide": HIDE}


@pytest.mark.parametrize("button", TAKES_IT_AWAY.values(), ids=TAKES_IT_AWAY.keys())
def test_a_double_click_that_takes_the_panel_away_reaches_nothing_under_it(live, env, button):
    """Re-review finding 6. The panel goes with the first click, and the second landed on
    the page: on the real one, the deck under Done armed Drop mode, and under Cancel Audit
    Eject mode or a new audit. RED on 681232a: the button under it took the click and the
    keyboard."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")     # one, found: Done parks nothing
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(STRIP)
    xy = behind(live, button)
    double_click(live, xy, then=PANEL, state="detached")
    live.wait_for_timeout(150)
    assert reached(live) == {"behind": [], "focus": "BODY"}
    ended = {CANCEL: "CMD:CANCEL", DONE: "CMD:DONE"}.get(button)
    assert sent(live) == ["ID:57"] + ([ended] if ended else [])
    assert session()["active"] is (button == HIDE)


def test_a_double_click_on_park_that_answers_fast_reaches_nothing_under_the_panel(live, env):
    """Re-review finding 6's park: the question and the panel both go before the second
    click when FCC answers quickly. RED on 681232a."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    question_up(live)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)              # its yes takes a click now
    xy = behind(live, YES)
    double_click(live, xy, then=PANEL, state="detached")
    live.wait_for_timeout(150)
    assert reached(live) == {"behind": [], "focus": "BODY"}
    assert len(sent(live, PARK_URL)) == 1 and at(env, 99) == "UNKNOWN"


BRINGS_IT_UP = {"deck-tile": TILE, "pill": PILL}


@pytest.mark.parametrize("opener", BRINGS_IT_UP.values(), ids=BRINGS_IT_UP.keys())
def test_a_double_click_that_brings_the_panel_up_presses_nothing_on_it(live, env, opener):
    """Re-review finding 7. With the panel hidden the first click shows it (Decision 5),
    and its Cancel Audit can lie under the second: the audit ended and every find went
    with it. Laid over here; the real band is the e2e sweep's. RED on 681232a."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.evaluate("window.closeAuditPanel()")              # hidden, by no press
    live.wait_for_selector(PANEL, state="detached")
    xy = lay_over(live, CANCEL, opener)
    double_click(live, xy, then=CANCEL)
    live.wait_for_timeout(150)
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True
    assert live.is_visible(PANEL) and live.evaluate(HIT, xy) == CANCEL[1:]


def test_a_double_click_on_a_tile_finds_it_once_and_marks_nothing(live, env):
    """Re-review finding 8. The first find brings the Last found strip up over the tiles,
    and its Needs a label lay under the second click: the flag went up on a spool nobody
    asked about. The keyboard stays on the tile, as a single click leaves it. RED on
    681232a."""
    two(env)
    begin(live, env)
    live.wait_for_selector(tile(99))
    xy = lay_over(live, BUTTON, tile(99))
    double_click(live, xy, then=BUTTON)
    live.wait_for_timeout(150)
    assert [p["id"] for p in sent(live, FOUND_URL)] == [99]
    assert "CMD:NEEDLABEL" not in sent(live) and wire(env, 99) is None
    assert live.evaluate("document.activeElement.dataset.auditTile") == "99"


def test_a_double_click_on_needs_a_label_marks_once(live, env):
    """Its own double press, as a tile's: the second asked again, and was told the spool is
    already marked. RED on 681232a: two marks went out."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    xy = live.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); "
                       "return [r.left + r.width / 2, r.top + r.height / 2]; }", BUTTON)
    double_click(live, xy, then=UNDO)
    live.wait_for_timeout(150)
    live.wait_for_function("() => !state.processing && !state.scanQueue.length")
    assert sent(live).count("CMD:NEEDLABEL") == 1 and wire(env, 57) == "true"


UNDER_BACK_KEYS = {"cancel-audit": CANCEL, "a-tile": tile(99)}


@pytest.mark.parametrize("under", UNDER_BACK_KEYS.values(), ids=UNDER_BACK_KEYS.keys())
def test_a_double_click_on_back_leaves_the_keyboard_on_done(live, env, under):
    """Re-review finding 9. The second click was stopped, but its mousedown had already put
    the keyboard on what lay under Back, with no ring to say so: a person's Enter then
    ended the audit, or found a spool nobody touched. Back gives Done the keyboard, and
    Enter asks again. RED on 681232a."""
    three(env)
    begin(live, env)
    live.wait_for_selector(tile(99))
    xy = lay_over(live, BACK, under)
    question_up(live)
    live.wait_for_selector(BACK)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)              # a person's press on Back
    double_click(live, xy, then=QUESTION, state="detached")
    live.wait_for_timeout(150)
    assert live.evaluate("document.activeElement.id") == DONE[1:]
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    live.keyboard.press("Enter")
    live.wait_for_selector(QUESTION)
    assert "CMD:CANCEL" not in sent(live) and sent(live, FOUND_URL) == [] and session()["active"] is True


def test_a_double_click_on_back_that_brings_the_panel_back_leaves_the_keyboard_on_done(live, env):
    """Finding 9's hidden panel: Back brings it up under the pointer, its Cancel Audit took
    the second mousedown, and the keyboard stayed there once the panel drew. RED on
    681232a."""
    three(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    xy = lay_over(live, BACK, CANCEL)       # where Cancel Audit will be, measured while it is up
    live.evaluate("window.closeAuditPanel()")
    live.wait_for_selector(PANEL, state="detached")
    scanned(live, "CMD:DONE")
    live.wait_for_selector(BACK)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    double_click(live, xy, then=CANCEL)
    live.wait_for_timeout(150)
    assert "CMD:CANCEL" not in sent(live) and session()["active"] is True
    live.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=DONE)


def test_a_key_press_right_after_the_panel_goes_still_presses(live, env):
    """The shield takes a pointer's second press only: a click from the keyboard (detail 0)
    is no double click, and Space or Enter on what has the keyboard does what it says. A
    pin: proved on a copy whose shield takes the keyboard's click too."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    begin(live, env)
    xy = behind(live, HIDE)
    press(live, xy)                                         # Hide
    live.wait_for_selector(PANEL, state="detached")
    live.focus("#fcc-test-behind")
    live.keyboard.press("Enter")
    assert live.evaluate("window.__behind") == ["click"]


def test_a_press_elsewhere_right_after_the_panel_goes_still_presses(live, env):
    """A person's next press at another spot is no double click, however soon. A pin:
    proved on a copy that takes the next press wherever it lands."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    begin(live, env)
    hide = live.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); "
                         "return [r.left + r.width / 2, r.top + r.height / 2]; }", HIDE)
    press(live, hide)
    live.wait_for_selector(PANEL, state="detached")
    live.click(TILE)                                        # the deck tile: shows the panel
    live.wait_for_selector(PANEL)


def test_a_touch_double_tap_is_a_double_click_too(live, env):
    """A finger's two taps arrive as two presses and two clicks, and the shield takes the
    second. Real touches, through the browser's own touch emulation. RED on 681232a."""
    add_spool(env, 57, "LR-MDB-1", container_slot="1")
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(STRIP)
    xy = behind(live, CANCEL)
    cdp = live.context.new_cdp_session(live)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 1})

    def tap():
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": xy[0], "y": xy[1]}]})
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    started = time.monotonic()
    tap()
    live.wait_for_selector(PANEL, state="detached", timeout=650)
    assert time.monotonic() - started < DOUBLE_CLICK_S
    tap()
    live.wait_for_timeout(200)
    assert live.evaluate("window.__behind") == []
    assert sent(live) == ["ID:57", "CMD:CANCEL"] and session()["active"] is False


def hide_then_ask(page, env):
    """The panel hidden, and Done's question up from a scan, as the Location Manager's QR
    or the FINISH tile's asks it."""
    three(env)
    begin(page, env)
    scanned(page, "ID:57")
    page.wait_for_selector(BUTTON)
    page.click(HIDE)
    page.wait_for_selector(PANEL, state="detached")
    scanned(page, "CMD:DONE")
    page.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=BACK)


# The panel's polls wait until window.__letPollsGo(): it mounts with no Done to focus.
HOLD_POLLS = r"""() => {
    const plain = window.fetchT;
    let go;
    const held = new Promise((resolve) => { go = resolve; });
    window.__letPollsGo = go;
    window.fetchT = (u, o, ms) => (String(u).indexOf('/api/audit_session') !== -1
        ? held.then(() => plain(u, o, ms)) : plain(u, o, ms));
}"""


@pytest.mark.parametrize("answer", ["Enter", "Escape", "click"])
def test_back_with_the_panel_hidden_hands_the_keyboard_to_done(live, env, answer):
    """Finding 41. A panel brought back mounts empty, and its body comes with the first
    poll, so there was no Done to focus: the keyboard fell to the page, and Enter did
    nothing. RED on 1f8e03a."""
    hide_then_ask(live, env)
    if answer == "click":
        live.click(BACK)
    else:
        live.keyboard.press(answer)
    live.wait_for_selector(QUESTION, state="detached")
    live.wait_for_selector(DONE)
    live.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=DONE)
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    live.keyboard.press("Enter")
    live.wait_for_selector(QUESTION)


def test_done_leaves_a_keyboard_that_moved_on_while_the_panel_drew(live, env):
    """The person has gone somewhere on the panel since: Done doesn't take the focus. A pin
    of the test in _render: proved on a copy without it."""
    hide_then_ask(live, env)
    live.evaluate(HOLD_POLLS)
    live.keyboard.press("Enter")
    live.wait_for_selector(HIDE)
    live.keyboard.press("Tab")                  # the panel's trap: its first control
    assert live.evaluate("document.activeElement.id") == LOOSE_BTN[1:]
    live.evaluate("window.__letPollsGo()")
    live.wait_for_selector(DONE)
    assert live.evaluate("document.activeElement.id") == LOOSE_BTN[1:]


def test_a_panel_hidden_again_before_it_drew_forgets_the_keyboard(live, env):
    """Hide has the last word: the next time the panel comes up, nothing is owed to Done.
    A pin of the flag's reset: proved on a copy without it."""
    hide_then_ask(live, env)
    live.evaluate(HOLD_POLLS)
    live.keyboard.press("Enter")
    live.wait_for_selector(HIDE)
    live.evaluate("window.closeAuditPanel()")
    live.wait_for_selector(PANEL, state="detached")
    live.evaluate("() => { window.openAuditPanel(); window.__letPollsGo(); }")
    live.wait_for_selector(DONE)
    live.wait_for_timeout(100)
    assert live.evaluate("document.activeElement.id") != DONE[1:]


def test_a_double_enter_on_back_doesnt_ask_again(live, env):
    """The keyboard lands on Done when the question goes, so the second Enter pressed it
    and the question came straight back. The panel's guard covers a button's click
    however it was pressed. RED on 8373ecd."""
    three(env)
    begin(live, env)
    live.wait_for_selector(DONE)
    live.focus(DONE)
    live.keyboard.press("Enter")
    live.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=BACK)
    live.keyboard.press("Enter")
    live.wait_for_selector(QUESTION, state="detached")
    live.wait_for_function("(s) => document.activeElement === document.querySelector(s)", arg=DONE)
    live.keyboard.press("Enter")
    live.wait_for_timeout(150)
    assert sent(live).count("CMD:DONE") == 1 and not live.locator(QUESTION).count()


def test_a_scan_of_back_doesnt_stop_a_scan(live, env):
    """A scan is no click: what the guard stops is the second click of a double click.
    A pin: proved on a copy that gates scans on it too."""
    three(env)
    begin(live, env)
    question_up(live)
    live.wait_for_timeout(50)
    live.keyboard.type("CMD:CANCEL", delay=2)
    live.keyboard.press("Enter")
    live.wait_for_selector(QUESTION, state="detached")
    real_scan(live, "ID:57")
    live.wait_for_function("() => window.__sent.filter((p) => p.body.text === 'ID:57').length === 1")
    live.wait_for_function("() => !state.processing")
    assert 57 in session()["scanned_items"]


# --- "undo that" ------------------------------------------------------------------------

def marked(page, env):
    """#57 found and marked, the keyboard on "undo that"."""
    two(env)
    begin(page, env)
    scanned(page, "ID:57")
    page.wait_for_selector(BUTTON)
    page.click(BUTTON)
    page.wait_for_selector(UNDO)
    page.focus(UNDO)


def test_a_double_enter_on_undo_that_doesnt_mark_it_again(live, env):
    """Findings 23 and 44, on a real clock. The keyboard lands on Needs a label when
    "undo that" leaves, as the pin above says, and the second Enter pressed it. RED on
    8373ecd: the mark was back, the undo undone."""
    marked(live, env)
    live.keyboard.press("Enter")
    live.wait_for_selector(UNDO, state="detached")
    assert live.evaluate("document.activeElement.id") == BUTTON[1:]
    live.keyboard.press("Enter")
    live.wait_for_timeout(150)
    assert sent(live).count("CMD:NEEDLABEL") == 1
    assert LABEL not in env["fake"].extra("spool", 57)


def test_the_button_is_itself_again_once_a_double_press_is_past(live, env):
    """A second Enter meant as one marks. A pin: proved on a copy that never lifts it."""
    marked(live, env)
    live.keyboard.press("Enter")
    live.wait_for_selector(UNDO, state="detached")
    live.wait_for_timeout(PAST_A_DOUBLE_PRESS)
    live.keyboard.press("Enter")
    live.wait_for_selector(UNDO)
    assert wire(env, 57) == "true"


def test_a_second_press_of_undo_that_before_the_redraw_is_no_refusal(live, env):
    """Between its answer and the redraw the button is still there, and a second Enter
    asked the server to undo what it had just undone. RED on 8373ecd: "wasn't marked in
    this audit: nothing to undo", on a press that had worked."""
    marked(live, env)
    live.evaluate("""() => { const f = window.fetch;
        window.fetch = async (url, opts) => {
            if (String(url).indexOf('/api/audit_session') !== -1 && window.__slowPoll) {
                await new Promise((r) => setTimeout(r, 400));
            }
            return f(url, opts);
        }; window.__slowPoll = true; }""")
    live.keyboard.press("Enter")
    live.wait_for_function("() => window.__sent.filter((p) => p.url.indexOf('needs_label_undo') !== -1).length === 1")
    live.wait_for_timeout(100)              # answered, not redrawn
    assert live.is_visible(UNDO)
    live.keyboard.press("Enter")
    live.wait_for_selector(UNDO, state="detached")
    assert len(sent(live, UNDO_URL)) == 1 and not live.text_content(NOTICE)


def test_a_poll_that_beats_the_undos_own_answer_doesnt_free_the_button(live, env):
    """The server has undone it, a poll has redrawn the strip, and the keyboard is on
    Needs a label with the answer still on its way, so there is no answer to time from.
    RED on 8373ecd: the second Enter put the mark back."""
    marked(live, env)
    live.evaluate("""() => { const f = window.fetch;
        window.fetch = async (url, opts) => {
            const answer = await f(url, opts);
            if (String(url).indexOf('needs_label_undo') !== -1) await new Promise((r) => { window.__undoAnswer = r; });
            return answer;
        }; }""")
    live.keyboard.press("Enter")
    live.wait_for_function("() => typeof window.__undoAnswer === 'function'")
    live.evaluate("() => window.refreshAuditSession()")
    live.wait_for_selector(UNDO, state="detached")
    assert live.evaluate("document.activeElement.id") == BUTTON[1:]
    live.keyboard.press("Enter")
    live.wait_for_timeout(150)
    live.evaluate("() => window.__undoAnswer()")
    assert sent(live).count("CMD:NEEDLABEL") == 1
    assert LABEL not in env["fake"].extra("spool", 57)


def test_a_scan_landing_on_undo_that_leaves_the_next_spool_alone(live, env):
    """The strip moves to the scanned spool, and the keyboard fell to Needs a label, now
    for that spool: an Enter meant for #57 marked #99. RED on 8373ecd."""
    marked(live, env)
    scanned(live, "ID:99")
    strip_says(live, "#99")
    assert live.evaluate("document.activeElement.id") != BUTTON[1:]
    live.wait_for_timeout(150)
    live.keyboard.press("Enter")
    live.wait_for_timeout(150)
    assert wire(env, 99) is None and wire(env, 57) == "true"
    assert sent(live).count("CMD:NEEDLABEL") == 1


def test_a_scan_landing_on_undo_that_doesnt_hand_it_to_the_next_mark(live, env):
    """The strip moves to a spool with a mark of its own, which has an "undo that" too:
    the same id, so the keyboard stayed on it, and an Enter meant for #99 undid #57's
    mark. RED on 8373ecd."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    scanned(live, "ID:99")
    strip_says(live, "#99")
    live.wait_for_selector(BUTTON)
    live.click(BUTTON)
    live.wait_for_selector(UNDO)
    live.focus(UNDO)
    scanned(live, "ID:57")
    strip_says(live, "#57")
    assert live.evaluate("document.activeElement.id") != UNDO[1:]
    live.wait_for_timeout(150)
    live.keyboard.press("Enter")
    live.wait_for_timeout(150)
    assert sent(live, UNDO_URL) == [] and wire(env, 57) == "true" and wire(env, 99) == "true"


def test_the_keys_still_work_with_the_focus_gone(live, env):
    """"Nothing focused is fine": N and the arrows answer on the panel. A pin of the
    two listeners, whatever has the focus: proved on a copy that asks for a focused
    button."""
    marked(live, env)
    scanned(live, "ID:99")
    strip_says(live, "#99")
    live.keyboard.press("n")
    live.wait_for_selector(UNDO)
    assert wire(env, 99) == "true"
    live.keyboard.press("ArrowRight")
    assert live.evaluate("document.activeElement.dataset.auditTile") == "57"


def test_undo_that_left_alone_is_said_on_the_panel(live, env):
    """Finding 32's page half. A status newer than the mark stands (a Backlog's Mark
    Printed), and the answer is a success, so the panel just dropped "undo that", which
    read as an undo that worked. The toast layer is under the panel. RED on 8373ecd."""
    marked(live, env)
    env["fake"].records["spool"][57]["extra"][LABEL] = "false"
    live.keyboard.press("Enter")
    words = "#57's label status has changed since it was marked, so it was left as it is."
    live.wait_for_function("([s, w]) => document.querySelector(s).textContent === w", arg=[NOTICE, words])
    assert _on_top(live, NOTICE)
    assert {"msg": words, "kind": "success"} in toasts(live)
    assert wire(env, 57) == "false"


def test_an_undo_that_worked_clears_the_panels_notice(live, env):
    """A pin: proved on a copy that says every success there."""
    marked(live, env)
    live.evaluate("() => window.auditPanelNotice('An old refusal')")
    live.keyboard.press("Enter")
    live.wait_for_selector(UNDO, state="detached")
    assert live.text_content(NOTICE) == ""


# --- key N, on real timers ---------------------------------------------------------------

@pytest.mark.parametrize("ms", [60, 100])
def test_a_slow_scanners_label_starting_with_an_n_goes_out_whole(live, env, ms):
    """Finding 28, on real timers (the fake clock runs every key in one tick, so it
    can't meet the timer). N waits out the accumulator's burst figure. RED on 8373ecd:
    the 50 ms wait sent CMD:NEEDLABEL, wrote the flag on #57 and left "ook-1"."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    before = len(sent(live))
    live.keyboard.type("nook-1", delay=ms)
    live.keyboard.press("Enter")
    live.wait_for_function("(n) => window.__sent.filter((p) => p.url.indexOf('identify_scan') !== -1).length > n", arg=before)
    live.wait_for_timeout(PAST_N)
    assert sent(live)[before:] == ["nook-1"]
    assert wire(env, 57) is None


def test_a_persons_n_still_marks_on_real_timers(live, env):
    """A pin: proved on a copy whose wait never ends."""
    two(env)
    begin(live, env)
    scanned(live, "ID:57")
    live.wait_for_selector(BUTTON)
    live.keyboard.press("n")
    live.wait_for_selector(UNDO)
    assert wire(env, 57) == "true" and live.evaluate("state.scanBuffer") == ""
