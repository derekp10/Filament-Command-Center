"""Group 48.4 — the wizard fills a blank Slicer Profile, under node's `vm`: the
REAL inv_core.js + inv_wizard.js with a stub page.

Derek, 2026-10-19: for Prusament, "source that from the site"; for the rest,
"this stuff is hard to fill out for manual adds" (his Jayo filaments use the
Sunlu profile). So: a lookup's `slicer_profile` first (his own spelling when it
is already a choice, else a new choice that Save adds first), else the profile
most of his own filaments with the same brand + base material use (a tie fills
nothing and names both). Only ever into a blank field while a NEW filament is
made; never over a profile someone set; nothing written before Save.

Base proof (52741e6): none of these functions exist there, so every test fails.
"""
from __future__ import annotations

import json

from test_core1_return_ejectall_js import pytestmark, run_js  # noqa: F401  (pytestmark: skip without node)

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
sel.value = {json.dumps(current)};
const note = () => document.getElementById('wiz-fil-profile-note').textContent;
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


# ---- 2. his own filaments ----------------------------------------------------------------------

def test_his_own_filaments_suggest_their_most_used_profile(tmp_path):
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Jayo'); field('wiz-fil-material', 'PLA');
const s = window.wizardSuggestSlicerProfile({});
return { s, value: sel.value, note: note() };
""", mode="manual")
    assert res["value"] == "Sunlu PLA + 2.0" and res["s"]["isNew"] is False, res
    assert res["note"] == "🎚️ Suggested: Sunlu PLA + 2.0 (2 of your Jayo PLA filaments use it).", res["note"]


def test_a_tie_fills_nothing_and_names_both(tmp_path):
    tie = [_fil("Jayo", "PLA", "Sunlu PLA + 2.0"), _fil("Jayo", "PLA", "Generic PLA")]
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Jayo'); field('wiz-fil-material', 'PLA');
const s = window.wizardSuggestSlicerProfile({});
return { s, value: sel.value, note: note() };
""", mode="manual", filaments=tie)
    assert res["s"] is None and res["value"] == "", res
    assert res["note"] == "🎚️ Your Jayo PLA filaments use Sunlu PLA + 2.0 and Generic PLA equally: pick one.", res


def test_attributes_dont_split_the_base_material(tmp_path):
    """A typed "Matte PLA" counts his "PLA" filaments (Matte is an attribute)."""
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'jayo'); field('wiz-fil-material', 'Matte PLA');
return { s: window.wizardSuggestSlicerProfile({}), value: sel.value };
""", mode="manual")
    assert res["value"] == "Sunlu PLA + 2.0", res


def test_no_match_fills_nothing(tmp_path):
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Elegoo'); field('wiz-fil-material', 'PLA');
return { s: window.wizardSuggestSlicerProfile({}), value: sel.value, note: note() };
""", mode="manual")
    assert res["s"] is None and res["value"] == "" and res["note"] == "", res


def test_a_brand_change_replaces_only_its_own_suggestion(tmp_path):
    res = _run(tmp_path, """
field('wiz-fil-vendor-search', 'Jayo'); field('wiz-fil-material', 'PLA');
window.wizardSuggestSlicerProfile({});
const first = sel.value;
field('wiz-fil-vendor-search', 'Elegoo');
window.wizardSuggestSlicerProfile({});
return { first, after: sel.value };
""", mode="manual")
    assert res == {"first": "Sunlu PLA + 2.0", "after": "", "unhandled": []}, res


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
