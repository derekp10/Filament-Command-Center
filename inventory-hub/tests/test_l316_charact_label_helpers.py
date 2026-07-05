"""L316 characterization tests — pins pre-carve behavior of the pure label
helpers in app.py (~lines 429-545). Generated from the 2026-07-01 coverage
audit. Do not weaken these to make a refactor pass.

Covers, by DIRECT CALL (no Flask client, no mocks):
  clean_string, hex_to_rgb, get_smart_type, get_color_name, get_best_hex,
  sanitize_label_text, flatten_json.

These helpers compose the text/color columns of the label CSVs — which are
locked P-touch DATABASE sources feeding the .lbx templates — so their exact
output strings are a silent contract with physically printed labels. Every
quirk below is pinned deliberately: if a value looks wrong, the pin exists
so the modularization carve changes it consciously, not accidentally.

Emoji are written as \\u / \\U escapes in source so nothing non-cp1252 is
printed to the Windows console on failure diffs; the runtime strings are the
real emoji.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402


# ---------------------------------------------------------------------------
# clean_string — quote-strip passthrough
# ---------------------------------------------------------------------------

def test_clean_string_strips_wrapping_double_quotes():
    """Pins the basic contract: Spoolman extras arrive JSON-encoded, so a
    double-quote-wrapped value is unwrapped for label rendering."""
    assert app_module.clean_string('"x"') == 'x'
    # Repeated wrapping quotes are ALL stripped (str.strip semantics).
    assert app_module.clean_string('""x""') == 'x'


def test_clean_string_strips_wrapping_single_quotes():
    """Single-quote wrapping is stripped too (second strip pass)."""
    assert app_module.clean_string("'x'") == 'x'


def test_clean_string_strip_order_is_double_then_single():
    """Pins the two-pass strip ORDER: double quotes first, then single.
    Consequence: "'x'" (doubles outside) unwraps fully, but '"x"' (singles
    outside) leaves the inner double quotes intact — the first pass sees a
    leading single quote and strips nothing."""
    # chars: " ' x ' "  → fully unwrapped
    assert app_module.clean_string('"\'x\'"') == 'x'
    # chars: ' " x " '  → double quotes survive
    assert app_module.clean_string('\'"x"\'') == '"x"'


def test_clean_string_non_str_passthrough():
    """Non-strings are returned unchanged (not coerced)."""
    assert app_module.clean_string(42) == 42
    assert app_module.clean_string(None) is None
    lst = ['a']
    assert app_module.clean_string(lst) is lst


def test_clean_string_does_not_trim_whitespace():
    """Only quote characters are stripped — surrounding whitespace defeats
    the strip entirely (leading space shields the quote)."""
    assert app_module.clean_string(' "x" ') == ' "x" '


# ---------------------------------------------------------------------------
# hex_to_rgb — feeds the Red/Green/Blue CSV columns
# ---------------------------------------------------------------------------

def test_hex_to_rgb_valid_hex():
    """Happy path: 6 hex digits → int triple."""
    assert app_module.hex_to_rgb('AABBCC') == (170, 187, 204)


def test_hex_to_rgb_hash_prefix_and_lowercase():
    """'#' prefix is stripped and case is irrelevant."""
    assert app_module.hex_to_rgb('#aabbcc') == (170, 187, 204)


def test_hex_to_rgb_bad_input_returns_empty_string_triple():
    """Pins the quirky error contract: None / empty / short / non-hex input
    all return a TUPLE OF THREE EMPTY STRINGS (not None, not an exception) —
    downstream CSV rows get blank R/G/B cells."""
    assert app_module.hex_to_rgb(None) == ("", "", "")
    assert app_module.hex_to_rgb('') == ("", "", "")
    assert app_module.hex_to_rgb('ABC') == ("", "", "")       # len < 6
    assert app_module.hex_to_rgb('#ABC') == ("", "", "")      # len < 6 with '#'
    assert app_module.hex_to_rgb('ZZZZZZ') == ("", "", "")    # ValueError swallow


def test_hex_to_rgb_hash_stripped_before_length_guard():
    """28.A1 FIX — the '#' is stripped BEFORE the length guard, so a
    '#'-prefixed short hex is rejected to ('','','') instead of parsing the
    blue channel from a single digit. '#AABBC' → 5 payload digits → reject."""
    assert app_module.hex_to_rgb('#AABBC') == ("", "", "")


def test_hex_to_rgb_extra_trailing_chars_ignored():
    """Only the first 6 hex digits are read; trailing characters (e.g. an
    8-digit RGBA hex) are silently ignored."""
    assert app_module.hex_to_rgb('AABBCCDD') == (170, 187, 204)


# ---------------------------------------------------------------------------
# get_smart_type — composes the Type text on printed labels
# ---------------------------------------------------------------------------

def test_get_smart_type_json_string_attrs_prefix_material():
    """filament_attributes as a JSON-encoded string list is parsed, joined
    with single spaces, and prefixed to the quote-stripped material."""
    result = app_module.get_smart_type('"PLA"', {'filament_attributes': '["Matte","Silk"]'})
    assert result == 'Matte Silk PLA'


def test_get_smart_type_attr_order_preserved():
    """Attribute JOIN ORDER follows the stored list order — no sorting."""
    result = app_module.get_smart_type('PLA', {'filament_attributes': '["Silk","Matte"]'})
    assert result == 'Silk Matte PLA'


def test_get_smart_type_native_list_attrs_quote_stripped():
    """filament_attributes already a Python list is used as-is; each element
    is clean_string'd (JSON-quote residue removed)."""
    assert app_module.get_smart_type('PLA', {'filament_attributes': ['"CF"']}) == 'CF PLA'


def test_get_smart_type_bad_json_swallowed():
    """A non-JSON attrs string must not raise — JSONDecodeError is swallowed
    and the material alone is returned."""
    assert app_module.get_smart_type('PLA', {'filament_attributes': 'not-json'}) == 'PLA'


def test_get_smart_type_non_list_json_guard():
    """Valid JSON that is not a list (dict here) is discarded by the
    isinstance guard — material alone."""
    assert app_module.get_smart_type('PLA', {'filament_attributes': '{"a": 1}'}) == 'PLA'


def test_get_smart_type_missing_attrs_key_defaults_empty():
    """Absent filament_attributes key defaults to '[]' → material alone."""
    assert app_module.get_smart_type('PLA', {}) == 'PLA'


def test_get_smart_type_none_material_yields_empty_string():
    """material=None coerces to '' via the `or \"\"` — returns '' (str, not None)."""
    assert app_module.get_smart_type(None, {}) == ''


def test_get_smart_type_falsy_attrs_filtered():
    """Empty-string / None entries in the attrs list are filtered before the
    join (the `if a` in the comprehension)."""
    result = app_module.get_smart_type('PETG', {'filament_attributes': ['', None, 'Silk']})
    assert result == 'Silk PETG'


def test_get_smart_type_attrs_without_material_no_trailing_space():
    """28.A2 FIX — with attrs present but material None/empty, only the non-empty
    parts are joined, so there is NO trailing space: 'Matte' (not 'Matte ')."""
    assert app_module.get_smart_type(None, {'filament_attributes': '["Matte"]'}) == 'Matte'


# ---------------------------------------------------------------------------
# get_color_name — the Group 25 original_color label-parity promise
# ---------------------------------------------------------------------------

def test_get_color_name_prefers_original_color_quote_stripped():
    """extra.original_color wins over the filament name, and is
    clean_string'd (JSON-quote residue removed)."""
    item = {'extra': {'original_color': '"Galaxy Black"'}, 'name': 'ignored'}
    assert app_module.get_color_name(item) == 'Galaxy Black'


def test_get_color_name_empty_original_color_falls_to_name():
    """A PRESENT-but-empty original_color falls through to the name (the
    truthiness check after clean_string)."""
    assert app_module.get_color_name({'extra': {'original_color': ''}, 'name': 'Fallback'}) == 'Fallback'


def test_get_color_name_quoted_empty_original_color_falls_to_name():
    """'\"\"' (a JSON-encoded empty string) clean_strips to '' and also falls
    through — quote-strip happens BEFORE the truthiness test."""
    assert app_module.get_color_name({'extra': {'original_color': '""'}, 'name': 'Fallback'}) == 'Fallback'


def test_get_color_name_unknown_fallback():
    """No original_color and no name → literal 'Unknown'."""
    assert app_module.get_color_name({'extra': {}}) == 'Unknown'
    assert app_module.get_color_name({}) == 'Unknown'


def test_get_color_name_missing_extra_key_uses_name():
    """No extra dict at all → name fallback (extra defaults to {})."""
    assert app_module.get_color_name({'name': 'NoExtra'}) == 'NoExtra'


def test_get_color_name_name_fallback_quote_stripped():
    """28.A3 FIX — the name FALLBACK is now clean_string'd too (symmetry with
    the original_color path), so a JSON-quoted name loses its literal quotes
    on the label."""
    assert app_module.get_color_name({'extra': {}, 'name': '"Quoted"'}) == 'Quoted'


# ---------------------------------------------------------------------------
# get_best_hex — picks the hex driving the label color chip / RGB columns
# ---------------------------------------------------------------------------

def test_get_best_hex_top_level_multi_first_segment():
    """Top-level multi_color_hexes wins over color_hex; only the FIRST
    comma-segment is used."""
    item = {'multi_color_hexes': 'FF0000,00FF00', 'color_hex': 'AAAAAA'}
    assert app_module.get_best_hex(item) == 'FF0000'


def test_get_best_hex_extra_lookup_with_strip():
    """multi_color_hexes is also found under extra (fallback lookup), and the
    first segment is whitespace-stripped."""
    item = {'extra': {'multi_color_hexes': ' 112233 ,445566'}}
    assert app_module.get_best_hex(item) == '112233'


def test_get_best_hex_top_level_wins_over_extra():
    """When both exist, the top-level value shadows extra (the `or`)."""
    item = {'multi_color_hexes': '111111', 'extra': {'multi_color_hexes': '222222'}}
    assert app_module.get_best_hex(item) == '111111'


def test_get_best_hex_empty_top_level_falls_to_extra():
    """A falsy (empty-string) top-level value falls through to extra — `or`
    semantics, not key-presence semantics."""
    item = {'multi_color_hexes': '', 'extra': {'multi_color_hexes': 'ABCDEF'}}
    assert app_module.get_best_hex(item) == 'ABCDEF'


def test_get_best_hex_empty_first_segment_uses_next_segment():
    """28.A4 FIX — an empty FIRST segment (',445566') is skipped and the valid
    second segment is used, rather than abandoning multi_color_hexes for
    color_hex."""
    item = {'multi_color_hexes': ',445566', 'color_hex': 'AAAAAA'}
    assert app_module.get_best_hex(item) == '445566'


def test_get_best_hex_empty_input_returns_empty_string():
    """Nothing set anywhere → '' (color_hex default), never None."""
    assert app_module.get_best_hex({}) == ''
    assert app_module.get_best_hex({'extra': {}}) == ''


def test_get_best_hex_plain_color_hex_passthrough():
    """No multi anywhere → color_hex verbatim."""
    assert app_module.get_best_hex({'color_hex': 'BBEE00'}) == 'BBEE00'


# ---------------------------------------------------------------------------
# sanitize_label_text — THE emoji→ASCII word map (its reason to exist).
# P-touch printers can't render emoji, so location names like the raccoon
# fleet prefix must become words before hitting the CSV.
# ---------------------------------------------------------------------------

def test_sanitize_label_text_full_emoji_word_map():
    """Pins every entry of the translation map in one pass:
    raccoon→Raccoon, bolt→Bolt, fire→Fire, package→Box, warning+VS16→Warn."""
    assert app_module.sanitize_label_text('\U0001f99d XL') == 'Raccoon XL'
    assert app_module.sanitize_label_text('\u26a1 fast') == 'Bolt fast'
    assert app_module.sanitize_label_text('\U0001f525 hot end') == 'Fire hot end'
    assert app_module.sanitize_label_text('\U0001f4e6 storage') == 'Box storage'
    # The Warn map key is U+26A0 U+FE0F — WITH the VS16 variation selector.
    assert app_module.sanitize_label_text('\u26a0\ufe0f hot') == 'Warn hot'


def test_sanitize_label_text_multi_emoji_replaces_all():
    """Multiple map hits in one string are all replaced (sequential
    str.replace over the whole map)."""
    combo = '\U0001f99d\u26a1\U0001f525\U0001f4e6\u26a0\ufe0f'
    assert app_module.sanitize_label_text(combo) == 'RaccoonBoltFireBoxWarn'


def test_sanitize_label_text_bare_warning_sign_now_mapped():
    """28.A5 FIX \u2014 the map keys are bare base code points matched in both bare
    and emoji-presentation form, so a BARE U+26A0 warning sign is now mapped to
    'Warn' instead of passing through un-translated."""
    assert app_module.sanitize_label_text('\u26a0 hot') == 'Warn hot'


def test_sanitize_label_text_bolt_with_vs16_no_stray_selector():
    """28.A5 FIX — the emoji-presentation form (base + U+FE0F) is replaced as a
    unit, so an emoji-presentation bolt (U+26A1 U+FE0F) becomes 'Bolt' with NO
    stray invisible VS16 left behind in the label CSV."""
    assert app_module.sanitize_label_text('\u26a1\ufe0f go') == 'Bolt go'


def test_sanitize_label_text_unknown_emoji_passthrough():
    """Emoji not in the map are NOT stripped — they pass through verbatim
    (the map is a translation table, not an ASCII filter)."""
    assert app_module.sanitize_label_text('\U0001f680 launch') == '\U0001f680 launch'


def test_sanitize_label_text_non_str_coerced_to_str():
    """Non-string input is str()-coerced, not rejected."""
    assert app_module.sanitize_label_text(42) == '42'
    assert app_module.sanitize_label_text(None) == 'None'
    assert app_module.sanitize_label_text(1.5) == '1.5'


# ---------------------------------------------------------------------------
# flatten_json — generates the extra CSV column names appended to label
# exports. Key mangling IS the column-name contract with the .lbx templates.
# ---------------------------------------------------------------------------

def test_flatten_json_nested_dict_and_list_key_mangling():
    """Pins the exact key set: dict keys joined with '_', list indices
    interleaved ('a_b_0_c' style), trailing underscore trimmed."""
    result = app_module.flatten_json(
        {'id': 1, 'filament': {'vendor': {'name': 'Acme'}, 'tags': ['a', 'b']}}
    )
    assert result == {
        'id': 1,
        'filament_vendor_name': 'Acme',
        'filament_tags_0': 'a',
        'filament_tags_1': 'b',
    }


def test_flatten_json_scalar_input_yields_value_key():
    """28.A6 FIX — a bare scalar gets a 'value' header (not an empty-string key
    that would become a blank CSV column header)."""
    assert app_module.flatten_json('x') == {'value': 'x'}


def test_flatten_json_empty_containers_preserve_nested_column():
    """28.A7 FIX — a NESTED empty dict/list is preserved as an empty-string
    column instead of vanishing (no silent loss). A TOP-LEVEL empty container
    has no key, so it still yields {}."""
    assert app_module.flatten_json({}) == {}
    assert app_module.flatten_json([]) == {}
    # ...but a nested empty list keeps its column (empty value, not dropped).
    assert app_module.flatten_json({'a': [], 'b': 1}) == {'a': '', 'b': 1}


def test_flatten_json_top_level_list_indices():
    """A top-level list is indexed from 0; scalar elements get the bare
    index as their key."""
    assert app_module.flatten_json([{'x': 1}, 'y']) == {'0_x': 1, '1': 'y'}


def test_flatten_json_list_of_dicts():
    """List-of-dicts interleaves index between the parent and child keys."""
    assert app_module.flatten_json({'a': [{'b': 1}, {'b': 2}]}) == {'a_0_b': 1, 'a_1_b': 2}


def test_flatten_json_mangled_key_collision_disambiguated():
    """28.A7 FIX — 'a_b' as a literal key and {'a': {'b': ...}} mangle to the
    SAME output key; instead of the later entry silently overwriting the
    earlier one, the collision is disambiguated with a '__N' suffix so both
    values survive (order-preserving: the first writer keeps the base key)."""
    assert app_module.flatten_json({'a_b': 1, 'a': {'b': 2}}) == {'a_b': 1, 'a_b__2': 2}
    assert app_module.flatten_json({'a': {'b': 2}, 'a_b': 1}) == {'a_b': 2, 'a_b__2': 1}


def test_flatten_json_none_value_preserved():
    """None is a scalar — kept as the value, not dropped or stringified."""
    assert app_module.flatten_json({'k': None}) == {'k': None}
