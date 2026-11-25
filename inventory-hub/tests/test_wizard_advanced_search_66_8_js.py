"""Group 66.8 (ii): the wizard's 🔍 Advanced Search says what happened, in the page's words.

A pick made through the search panel (SearchEngine's select mode) had four faults:
  - a spool whose filament couldn't be read raised the browser's own alert();
  - neither read had a catch: a fetch that failed was an unhandled rejection, and the
    pick was silently lost;
  - the filament's vendor, material and name went into the status line and the list's
    option as HTML, unescaped (CLAUDE.md: Spoolman's free text in the page is text);
  - the panel said "Select a spool to insert it into the form." though the wizard had
    switched it to Filaments;
and a 404 or 5xx body that FCC's route hands on as data read as the filament ("Generic
Unknown - Unnamed (ID: 7)"), and an answer landing after a newer pick, or after the
wizard was reset, still changed the form.

Now: a spool is used only when the answer is that spool with its filament, and anything
else is refused in words (the status line and a 7 s toast), never an alert; a filament
is used when the answer is that filament, and otherwise stays picked by its id, as
Group 54.8 pins (test_a_filament_fcc_couldnt_read_shows_nothing_of_the_old_ones), with
honest words; names go in as text; a stale answer changes nothing; the panel's words
come from the caller, by the type checked.

Hermetic: the wizard on the Group 58.5 harness (SearchEngine stood in for, to drive the
pick), and the real search panel (inv_search.js, offcanvas_search.html) with a stand-in
Offcanvas, in `isolated_page`, so it runs under --offline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from test_wizard_label_status_58_5 import wizard  # noqa: F401  (the fixture)

HUB = Path(__file__).resolve().parent.parent
MODULES = HUB / "static" / "js" / "modules"
SEARCH_HTML = HUB / "templates" / "components" / "offcanvas_search.html"

ODD = {"id": 7, "name": "<b>Odd</b> & Co", "material": "PLA", "vendor": {"id": 2, "name": "<i>V</i>"},
       "extra": {}, "spool_weight": None, "price": None}


def _arm(page):
    """Stand in for the search panel (the pick is driven by hand), and record alerts and
    toasts."""
    page.evaluate("""() => {
        window.__alerts = []; window.alert = (m) => window.__alerts.push(String(m));
        window.__toasts = []; window.showToast = (m, t, d) => window.__toasts.push({ m: String(m), t, d });
        window.SearchEngine = { open: (o) => { window.__searchOpts = o; } };
    }""")
    page.evaluate("() => window.openWizardModal()")
    page.wait_for_function("() => typeof wizardState !== 'undefined' && wizardState.mode === 'manual'")
    page.evaluate("() => wizardSelectType('existing', true)")
    page.locator("#area-existing button", has_text="Advanced Search").click()
    page.wait_for_function("() => !!window.__searchOpts")


def _pick(page, id_, type_, wait=100):
    page.evaluate("([i, t]) => window.__searchOpts.callback(i, t)", [id_, type_])
    page.wait_for_timeout(wait)


def _status(page):
    return page.evaluate("() => document.getElementById('wiz-status-msg').innerHTML")


def _errors(page):
    return page.evaluate("window.__errors")


def test_the_wizard_asks_the_panel_for_filaments_in_its_own_words(wizard):  # noqa: F811
    """RED on the base: no type and no prompts (the wizard ticked the radio itself, and
    the panel said "spool")."""
    _arm(wizard)
    opts = wizard.evaluate("() => ({ type: window.__searchOpts.type, prompts: window.__searchOpts.prompts })")
    assert opts["type"] == "filament"
    assert opts["prompts"]["filament"] and opts["prompts"]["spool"]


def test_a_spool_whose_filament_cant_be_read_is_refused_in_words(wizard):  # noqa: F811
    """RED on the base: the browser's alert()."""
    wizard.evaluate("() => { window.__answers['/api/spools/57'] = { success: false, msg: 'Spool not found' }; }")
    _arm(wizard)
    _pick(wizard, 57, "spool")
    assert wizard.evaluate("window.__alerts") == []
    assert wizard.evaluate("() => wizardState.selectedFilamentId") is None
    assert "Couldn't read spool #57's filament" in _status(wizard)
    toasts = wizard.evaluate("window.__toasts")
    assert toasts and toasts[-1]["t"] == "warning" and toasts[-1]["d"] == 7000, toasts
    assert _errors(wizard) == []


@pytest.mark.parametrize("answer", ["__reject__", {"success": True, "data": {"message": "Internal"}}])
def test_a_spool_read_that_fails_or_is_another_record_is_refused(wizard, answer):  # noqa: F811
    """A fetch that fails (RED on the base: an unhandled rejection, nothing said) and a
    5xx body handed on as data (RED: alert())."""
    wizard.evaluate("(a) => { window.__answers['/api/spools/57'] = a; }", answer)
    _arm(wizard)
    _pick(wizard, 57, "spool")
    assert wizard.evaluate("window.__alerts") == []
    assert wizard.evaluate("() => wizardState.selectedFilamentId") is None
    assert "Couldn't read spool #57's filament" in _status(wizard)
    assert _errors(wizard) == []


def test_a_spools_filament_is_picked_with_its_name_as_text(wizard):  # noqa: F811
    """RED on the base: the vendor's <i> and the name's <b> became real elements in the
    status line and the option."""
    wizard.evaluate("(f) => { window.__answers['/api/spools/57'] = { success: true, data: { id: 57, filament: f } }; }", ODD)
    _arm(wizard)
    _pick(wizard, 57, "spool")
    assert str(wizard.evaluate("() => wizardState.selectedFilamentId")) == "7"
    got = wizard.evaluate("""() => ({
        tags: document.querySelectorAll('#wiz-status-msg b, #wiz-status-msg i, #wiz-existing-results b, #wiz-existing-results i').length,
        status: document.getElementById('wiz-status-msg').textContent,
        option: document.querySelector('#wiz-existing-results option').textContent,
        value: document.getElementById('wiz-existing-results').value })""")
    assert got["tags"] == 0, got
    assert "<i>V</i> PLA - <b>Odd</b> & Co (ID: 7)" in got["status"]
    assert got["option"] == "<i>V</i> PLA - <b>Odd</b> & Co (ID: 7)"
    assert got["value"] == "7"


@pytest.mark.parametrize("answer", [
    "__reject__",                                           # RED: an unhandled rejection
    {"success": True, "data": {"message": "Internal"}},     # RED: "Generic Unknown - Unnamed"
    {"success": False, "msg": "Filament not found"},        # the 54.8 path: words now say so
])
def test_a_filament_it_cant_read_stays_picked_by_its_id_in_honest_words(wizard, answer):  # noqa: F811
    wizard.evaluate("(a) => { window.__answers['/api/filaments/9'] = a; }", answer)
    _arm(wizard)
    _pick(wizard, 9, "filament")
    assert str(wizard.evaluate("() => wizardState.selectedFilamentId")) == "9"
    status = _status(wizard)
    assert "couldn't read its details" in status, status
    assert "Generic Unknown" not in status
    assert wizard.evaluate("() => document.querySelector('#wiz-existing-results option').textContent") == "Filament #9"
    assert _errors(wizard) == []


def test_a_filament_read_is_used(wizard):  # noqa: F811
    """Control: a good read picks the filament and names it."""
    wizard.evaluate("(f) => { window.__answers['/api/filaments/7'] = { success: true, data: f }; }", ODD)
    _arm(wizard)
    _pick(wizard, 7, "filament")
    assert str(wizard.evaluate("() => wizardState.selectedFilamentId")) == "7"
    assert "Odd" in wizard.evaluate("() => document.getElementById('wiz-status-msg').textContent")


def test_an_older_answer_landing_late_changes_nothing(wizard):  # noqa: F811
    """Two picks; the first one's answer lands last. RED on the base: the older answer
    won and replaced the newer pick."""
    wizard.evaluate("""(f) => {
        window.__answers['/api/filaments/7'] = '__hold__';
        window.__answers['/api/filaments/8'] = { success: true, data: Object.assign({}, f, { id: 8, name: 'Newer' }) };
    }""", ODD)
    _hold(wizard)
    _arm(wizard)
    _pick(wizard, 7, "filament", wait=20)
    _pick(wizard, 8, "filament")
    assert str(wizard.evaluate("() => wizardState.selectedFilamentId")) == "8"
    wizard.evaluate("(f) => window.__held['/api/filaments/7']({ success: true, data: f })", ODD)
    wizard.wait_for_timeout(100)
    assert str(wizard.evaluate("() => wizardState.selectedFilamentId")) == "8"
    assert "Newer" in wizard.evaluate("() => document.getElementById('wiz-status-msg').textContent")


def _hold(page):
    """The 58.5 fetch stub knows no held answers: wrap it so '__hold__' waits for
    window.__held[path](body)."""
    page.evaluate("""() => {
        const orig = window.fetch;
        window.fetch = function (url, opts) {
            const path = String(url).split('?')[0];
            if (window.__answers[path] !== '__hold__') return orig(url, opts);
            return new Promise((resolve) => {
                (window.__held = window.__held || {})[path] = (b) => {
                    const t = JSON.stringify(b);
                    resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(t)) });
                };
            });
        };
    }""")


# --- The real search panel: its words in select mode ------------------------------------

PANEL_PRELUDE = r"""
window.__errors = [];
window.addEventListener('error', (e) => window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection', (e) => window.__errors.push(String(e.reason)));
window.fetch = () => Promise.resolve({ ok: true, status: 200,
    json: () => Promise.resolve({ success: true, materials: [], results: [] }) });
class FakeOffcanvas {
    constructor(el) { this.el = el; }
    static getInstance(el) { return new FakeOffcanvas(el); }
    static getOrCreateInstance(el) { return new FakeOffcanvas(el); }
    show() { this.el.classList.add('show'); }
    hide() { this.el.classList.remove('show'); this.el.dispatchEvent(new Event('hidden.bs.offcanvas')); }
}
window.bootstrap = { Offcanvas: FakeOffcanvas };
window.rgbText = () => '';
"""


@pytest.fixture
def panel(isolated_page):
    page = isolated_page
    page.set_content('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                     + SEARCH_HTML.read_text(encoding="utf-8") + '</body></html>')
    page.add_script_tag(content=PANEL_PRELUDE)
    page.add_script_tag(content=(MODULES / "inv_search.js").read_text(encoding="utf-8"))
    return page


def _context(page):
    return page.evaluate("() => document.getElementById('global-search-context').innerText")


def test_the_panel_says_filament_when_it_picks_a_filament(panel):
    """RED on the base: "Select a spool to insert it into the form." with Filaments
    checked."""
    panel.evaluate("""() => window.SearchEngine.open({ mode: 'select', type: 'filament',
        prompts: { filament: 'Pick a filament to use it in the form.', spool: 'Pick a spool to use its filament in the form.' },
        callback: () => {} })""")
    assert panel.evaluate("() => document.getElementById('searchTypeFilaments').checked") is True
    assert _context(panel) == "Pick a filament to use it in the form."
    # Switched to Spools, its words follow.
    panel.locator("label[for='searchTypeSpools']").click()
    panel.wait_for_timeout(50)
    assert _context(panel) == "Pick a spool to use its filament in the form."
    assert panel.evaluate("window.__errors") == []


def test_a_caller_with_no_prompts_keeps_the_panels_own_words(panel):
    """A pin (test_search_e2e.py): a select with no type or prompts says what it said."""
    panel.evaluate("() => window.SearchEngine.open({ callback: () => {} })")
    assert _context(panel) == "Select a spool to insert it into the form."
    # The prompts are the caller's: a later caller with none gets the panel's own.
    panel.evaluate("() => window.SearchEngine.offcanvas.hide()")
    panel.evaluate("""() => window.SearchEngine.open({ type: 'filament', callback: () => {} })""")
    assert _context(panel) == "Select a filament to insert it into the form."
