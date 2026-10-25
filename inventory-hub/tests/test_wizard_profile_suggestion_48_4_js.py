"""Group 48.4 — the wizard fills a blank Slicer Profile, under node's `vm`: the
REAL inv_core.js + inv_wizard.js with a stub page.

Derek, 2026-10-19: for Prusament, "source that from the site". So a lookup's
`slicer_profile` (the Prusament spool page's product line) fills a blank field
while a NEW filament is made: his own spelling when it is already a choice, else
a new choice that Save adds first; never over a profile someone set; nothing
written before Save. Derek, 2026-10-20: "Don't guess" — the first build also
suggested the profile most of his own filaments with the same brand + material
use; that is gone (a confirmed name only), and a brand or material change after
a lookup clears the name it gave.

Base proof (52741e6): none of these functions exist there, so every test fails;
the no-guess tests fail on 2ec9f46 (it guessed there).
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark  # noqa: F401  (pytestmark: skip without node)
# The node driver that also records document listeners, so a test can fire the
# wizard's own 'change' listener as a browser would.
from test_spoolman_read_load_52_js import run as run_js

MODULES = ["inv_core.js", "inv_wizard.js"]
CHOICES = ["Prusament PLA", "Prusament PLA Blend", "Sunlu PLA + 2.0", "Generic PLA"]


def _fil(vendor, material, profile):
    return {"vendor": {"name": vendor}, "material": material,
            "extra": {"slicer_profile": json.dumps(profile)} if profile else {}}


OWN = [_fil("Jayo", "PLA", "Sunlu PLA + 2.0"), _fil("Jayo", "PLA", "Sunlu PLA + 2.0"),
       _fil("Jayo", "PLA", "Generic PLA"), _fil("Sunlu", "PLA", "Generic PLA"), _fil("Jayo", "PETG", "Generic PETG"),
       _fil("Jayo", "PLA", None)]


def _run(tmp_path, body, mode="external", filaments=OWN, current=""):
    res = run_js(tmp_path, MODULES, f"""
window.fetchT = (u, o) => window.fetch(u, o);
globalThis.CSS = globalThis.CSS || {{ escape: (s) => String(s) }};
// inv_core.js's showToast writes the toast into #toast-container.
const toasts = () => (document.getElementById('toast-container').children || [])
  .map(c => ({{ msg: c.innerText, type: String(c.className).replace('toast-msg toast-', '') }}));
wizardState.mode = {json.dumps(mode)};
wizardState.extraFields = {{ filament: [
  {{ key: 'slicer_profile', field_type: 'choice', multi_choice: false, choices: {json.dumps(CHOICES)} }},
  {{ key: 'filament_attributes', field_type: 'choice', multi_choice: true, choices: ['Blend', 'Matte', 'Carbon Fiber'] }},
] }};
wizardState.allFilaments = {json.dumps(filaments)};
const sel = document.getElementById('wiz_fil_ef_slicer_profile');
// The stub select keeps what it is given in `children`: list them as a real
// select's `options`, and let an option's remove() take it out.
Object.defineProperty(sel, 'options', {{ get: () => sel.children }});
const __append = sel.appendChild.bind(sel);
sel.appendChild = (c) => {{ c.remove = () => {{ sel.children = sel.children.filter(x => x !== c); }}; return __append(c); }};
sel.value = {json.dumps(current)};
const note = () => document.getElementById('wiz-fil-profile-note').textContent;
const change = (el) => ((globalThis.__docListeners || {{}}).change || []).forEach(fn => fn({{ target: el }}));
const field = (id, v) => {{ document.getElementById(id).value = v; }};
{body}
""")
    assert res["unhandled"] == [], res["unhandled"]
    return res


# ---- 1. a lookup names it (the Prusament spool page) -------------------------------------------

def test_a_known_profile_from_the_lookup_takes_his_own_spelling(tmp_path):
    res = _run(tmp_path, """
const s = window.wizardSuggestSlicerProfile({ lookup: 'prusament pla blend', source: 'prusament.com' });
return { s, value: sel.value, note: note() };
""")
    assert res["value"] == "Prusament PLA Blend" and res["s"]["isNew"] is False, res
    assert res["note"] == "🎚️ From prusament.com: Prusament PLA Blend.", res["note"]


def test_a_new_variant_from_the_lookup_is_offered_as_a_new_choice(tmp_path):
    res = _run(tmp_path, """
const s = window.wizardSuggestSlicerProfile({ lookup: 'Prusament PETG', source: 'prusament.com' });
return { s, value: sel.value, note: note(), added: sel.children.map(o => [o.value, o.textContent]) };
""")
    assert res["value"] == "Prusament PETG" and res["s"]["isNew"] is True, res
    assert res["added"] == [["Prusament PETG", "Prusament PETG (new, from prusament.com)"]], res["added"]
    assert "isn't in your profile list yet: Save adds it" in res["note"], res["note"]


def test_the_import_path_applies_the_lookup(tmp_path):
    """applyFilamentFieldsFromTemplate (every external result) passes the
    parser's slicer_profile on. (The colour pickers need a real page: stubbed.)"""
    res = _run(tmp_path, """
window.wizardPopulateColors = () => {};
window.applyFilamentFieldsFromTemplate({ name: 'Prusament PLA Blend Oh My Gold 1kg', material: 'PLA Blend',
  color_name: 'Oh My Gold', vendor: { name: 'Prusament' }, color_hex: 'daa900',
  slicer_profile: 'Prusament PLA Blend', slicer_profile_source: 'prusament.com' });
return { value: sel.value, note: note() };
""")
    assert res["value"] == "Prusament PLA Blend" and "prusament.com" in res["note"], res


# ---- 2. never a guess (Derek, 2026-10-20) ------------------------------------------------------

def test_with_no_lookup_nothing_is_guessed_from_his_filaments(tmp_path):
    """Two of his Jayo PLA filaments use the Sunlu profile: the first build put
    it in a new Jayo PLA's field. RED on 2ec9f46."""
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Jayo'); field('wiz-fil-material', 'PLA');
const s = window.wizardSuggestSlicerProfile({});
change(document.getElementById('wiz-fil-material'));
return { s, value: sel.value, note: note() };
""", mode="manual")
    assert res["s"] is None and res["value"] == "" and res["note"] == "", res


def test_a_brand_or_material_change_clears_the_lookups_name(tmp_path):
    """The name was confirmed for the lookup's filament; on another material it
    is cleared, with a note. RED on 2ec9f46 (it guessed again instead)."""
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Prusament'); field('wiz-fil-material', 'PLA');
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PLA Blend', source: 'prusament.com' });
const first = sel.value;
field('wiz-fil-material', 'PETG');
change(document.getElementById('wiz-fil-material'));
return { first, after: sel.value, note: note(), suggestion: wizardState.profileSuggestion };
""")
    assert res["first"] == "Prusament PLA Blend" and res["after"] == "" and res["suggestion"] is None, res
    assert res["note"] == ("🎚️ The brand or material changed after prusament.com named Prusament PLA Blend, "
                           "so FCC cleared it: pick a profile."), res["note"]


def test_a_change_event_that_changes_nothing_keeps_the_lookups_name(tmp_path):
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Prusament'); field('wiz-fil-material', 'PLA');
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PLA Blend', source: 'prusament.com' });
change(document.getElementById('wiz-fil-vendor-sel'));
return { value: sel.value, note: note() };
""")
    assert res["value"] == "Prusament PLA Blend", res
    assert res["note"] == "🎚️ From prusament.com: Prusament PLA Blend.", res


def test_a_profile_the_user_picked_is_kept_through_a_material_change(tmp_path):
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Prusament'); field('wiz-fil-material', 'PLA');
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PLA Blend', source: 'prusament.com' });
sel.value = 'Generic PLA'; change(sel);
field('wiz-fil-material', 'PETG');
change(document.getElementById('wiz-fil-material'));
return { value: sel.value };
""")
    assert res["value"] == "Generic PLA", res


# ---- never over a profile someone set ----------------------------------------------------------

def test_a_profile_already_set_is_never_replaced(tmp_path):
    res = _run(tmp_path, """
const a = window.wizardSuggestSlicerProfile({ lookup: 'Prusament PETG', source: 'prusament.com' });
return { a, value: sel.value, added: sel.children.length };
""", current="Generic PLA")
    assert res["a"] is None and res["value"] == "Generic PLA" and res["added"] == 0, res


def test_the_users_own_pick_is_never_replaced(tmp_path):
    res = _run(tmp_path, """
sel.dataset.fccUserSet = '1';
return { a: window.wizardSuggestSlicerProfile({ lookup: 'Prusament PLA', source: 'prusament.com' }), value: sel.value };
""")
    assert res["a"] is None and res["value"] == "", res


def test_an_existing_filament_is_never_given_a_profile(tmp_path):
    res = _run(tmp_path, """
return { a: window.wizardSuggestSlicerProfile({ lookup: 'Prusament PLA', source: 'prusament.com' }), value: sel.value };
""", mode="existing")
    assert res["a"] is None and res["value"] == "", res


# ---- Save adds a new choice first --------------------------------------------------------------

def test_save_adds_a_new_suggested_choice_before_the_filament(tmp_path):
    res = _run(tmp_path, """
window.__respond = (url) => url === '/api/external/fields/add_choice' ? { body: { success: true } } : null;
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PETG', source: 'prusament.com' });
const ok = await window.wizardCommitSuggestedChoices({ extra: { slicer_profile: 'Prusament PETG' } });
const again = await window.wizardCommitSuggestedChoices({ extra: { slicer_profile: 'Prusament PETG' } });
return { ok, again, posts: __rec.fetches.filter(f => f.method === 'POST').map(f => [f.url, f.body]) };
""")
    assert res["ok"] is True and res["again"] is True, res
    assert res["posts"] == [["/api/external/fields/add_choice",
                             {"entity_type": "filament", "key": "slicer_profile", "new_choice": "Prusament PETG"}]], res


def test_a_failed_add_stops_the_save_and_says_why(tmp_path):
    res = _run(tmp_path, """
window.__respond = (url) => url === '/api/external/fields/add_choice'
  ? { status: 502, body: { success: false, msg: 'Spoolman timed out' } } : null;
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PETG', source: 'prusament.com' });
const ok = await window.wizardCommitSuggestedChoices({ extra: { slicer_profile: 'Prusament PETG' } });
return { ok, toasts: toasts(), status: document.getElementById('wiz-status-msg').innerText };
""")
    assert res["ok"] is False, res
    [toast] = res["toasts"]
    assert toast["type"] == "error" and "Spoolman timed out" in toast["msg"], toast
    assert "so nothing was saved" in res["status"], res["status"]


def test_nothing_is_added_for_a_known_choice_or_a_changed_field(tmp_path):
    res = _run(tmp_path, """
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PLA', source: 'prusament.com' });
const known = await window.wizardCommitSuggestedChoices({ extra: { slicer_profile: 'Prusament PLA' } });
window.wizardSuggestSlicerProfile({});
wizardState.profileSuggestion = { value: 'Prusament PETG', isNew: true };
const other = await window.wizardCommitSuggestedChoices({ extra: { slicer_profile: 'Generic PLA' } });
return { known, other, posts: __rec.fetches.filter(f => f.method === 'POST').length };
""")
    assert res["known"] is True and res["other"] is True and res["posts"] == 0, res


# ---- review browser-3: a "(new, …)" option outlives its suggestion ---------------------------

def test_a_new_profile_picked_again_by_hand_is_still_added_at_save(tmp_path):
    """Picking another profile drops the suggestion (the user's own pick is
    never replaced); picking the offered "(new, from prusament.com)" option
    again sent a value Spoolman doesn't know, with nothing added first, and
    every Save failed. RED on a5d8cb8."""
    res = _run(tmp_path, """
window.__respond = (url) => url === '/api/external/fields/add_choice' ? { body: { success: true } } : null;
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PETG', source: 'prusament.com' });
sel.value = 'Generic PLA'; change(sel);
sel.value = 'Prusament PETG'; change(sel);
const ok = await window.wizardCommitSuggestedChoices({ extra: { slicer_profile: sel.value } });
return { ok, suggestion: wizardState.profileSuggestion,
         adds: __rec.fetches.filter(f => f.url === '/api/external/fields/add_choice').map(f => f.body),
         choices: wizardState.extraFields.filament[0].choices, options: sel.children.map(o => o.textContent) };
""")
    assert res["suggestion"] is None, res          # the re-pick was the user's own
    assert res["ok"] is True, res
    assert res["adds"] == [{"entity_type": "filament", "key": "slicer_profile", "new_choice": "Prusament PETG"}], res
    assert "Prusament PETG" in res["choices"], res
    assert res["options"] == ["Prusament PETG"], res   # an ordinary choice now


def test_a_suggestion_that_no_longer_applies_takes_its_new_option_along(tmp_path):
    """A material change with nothing to suggest blanks the field it filled;
    its "(new, …)" option used to stay in the list. RED on a5d8cb8."""
    res = _run(tmp_path, """
window.wizardSuggestSlicerProfile({ lookup: 'Prusament PETG', source: 'prusament.com' });
const before = sel.children.map(o => o.textContent);
field('wiz-fil-vendor-search', 'Nobody'); field('wiz-fil-material', 'ASA');
change(document.getElementById('wiz-fil-material'));
return { before, value: sel.value, after: sel.children.map(o => o.textContent) };
""")
    assert res["before"] == ["Prusament PETG (new, from prusament.com)"], res
    assert res["value"] == "" and res["after"] == [], res


def test_control_a_value_fcc_never_offered_is_left_to_spoolman(tmp_path):
    """Control: only an option FCC offered as new is added; anything else that
    isn't a choice goes to Spoolman as it is (no add_choice)."""
    res = _run(tmp_path, """
const ok = await window.wizardCommitSuggestedChoices({ extra: { slicer_profile: 'Someone Else PLA' } });
return { ok, posts: __rec.fetches.filter(f => f.method === 'POST').length };
""")
    assert res["ok"] is True and res["posts"] == 0, res
