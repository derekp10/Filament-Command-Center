"""Unit-style coverage for the per-spool Prusament scan helpers in
inv_wizard.js. Driven through page.evaluate so we exercise the actual
shipped code, but with no UI interaction — these isolate the JS helpers
from the broader wizard flow so regressions in the helpers surface fast
without a full E2E walk.

Pinned behaviors here are the ones the user has tripped over in real use:
- empty/null color_name must not false-positive the matcher
- multi-match must sort by id ascending (oldest wins, no picker)
- per-spool extras must be wrapped in literal quotes for Spoolman
- post-success lock must hold across a wizardSyncSpoolRows call (the
  bug where row reset re-armed submit by re-running wizardValidateSubmit)
"""

from playwright.sync_api import Page, expect


def _open_wizard_no_fetches(page: Page):
    """Goto the dashboard and open the wizard, but stub /api/filaments so the
    matcher tests can supply their own filament list per case."""
    page.route("**/api/filaments", lambda route, req: route.fulfill(
        status=200, content_type="application/json",
        body='{"success": true, "filaments": []}',
    ))
    page.goto("http://localhost:8000")
    page.get_by_role("button", name="ADD INVENTORY").click()
    expect(page.locator("#wizardModal")).to_be_visible()


# --- findFilamentMatches ---------------------------------------------------

def test_find_filament_matches_empty_list_returns_no_matches(page: Page):
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Galaxy Black'
        });
    }""")
    assert matches == []


def test_find_filament_matches_exact_color_name_field(page: Page):
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 5, name: 'something', color_name: 'Galaxy Black', material: 'PLA', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Galaxy Black'
        });
    }""")
    assert len(matches) == 1
    assert matches[0]['id'] == 5


def test_find_filament_matches_substring_in_name(page: Page):
    """The user's real-world case: filament 157 stored as 'Silver (Pearl Mouse)'
    with no color_name field, scanned color_name = 'Pearl Mouse'."""
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 157, name: 'Silver (Pearl Mouse)', color_name: null, material: 'PLA', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Pearl Mouse'
        });
    }""")
    assert len(matches) == 1
    assert matches[0]['id'] == 157


def test_find_filament_matches_null_color_name_does_not_false_positive(page: Page):
    """Regression: if the third matcher rule (parsedColor.includes(fColorName))
    runs without a truthy guard, an empty fColorName matches every filament
    because every string contains the empty string. This was the bug that
    made the picker fire spuriously."""
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            // Should NOT match: vendor right, material right, but color is unrelated
            {id: 117, name: 'White (Pearl White)', color_name: null, material: 'PLA', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Galaxy Black'
        });
    }""")
    assert matches == []


def test_find_filament_matches_different_vendor_no_match(page: Page):
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 1, name: 'Galaxy Black', material: 'PLA', vendor: {name: 'Polymaker'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Galaxy Black'
        });
    }""")
    assert matches == []


def test_find_filament_matches_different_material_no_match(page: Page):
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 1, name: 'Galaxy Black', material: 'PETG', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Galaxy Black'
        });
    }""")
    assert matches == []


def test_find_filament_matches_sorts_by_id_ascending(page: Page):
    """Multi-match: oldest (lowest id) wins. No picker is shown — matches[0]
    is the canonical filament. User's real bug: with [157, 192] both fuzzy-
    matching 'Pearl Mouse', the wizard must auto-switch to 157, not 192."""
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 192, name: 'Pearl Mouse', color_name: null, material: 'PLA', vendor: {name: 'Prusament'}},
            {id: 157, name: 'Silver (Pearl Mouse)', color_name: null, material: 'PLA', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Pearl Mouse'
        });
    }""")
    assert [m['id'] for m in matches] == [157, 192]


# --- splitMaterialAndAttributes -------------------------------------------

def test_split_material_simple_base_only(page: Page):
    _open_wizard_no_fetches(page)
    result = page.evaluate("""() => window.splitMaterialAndAttributes('PLA', ['Carbon Fiber', 'Blend', 'Silk'])""")
    assert result == {'base': 'PLA', 'attrs': []}


def test_split_material_pulls_multi_word_attribute_first(page: Page):
    """'Carbon Fiber' must be matched as a phrase before any single-word
    attribute steals one of its tokens. Greedy longest-first sort handles
    this — 'Carbon Fiber' (12 chars) is checked before 'Blend' (5)."""
    _open_wizard_no_fetches(page)
    result = page.evaluate("""() => window.splitMaterialAndAttributes(
        'PC Blend Carbon Fiber',
        ['Carbon Fiber', 'Blend', 'Silk', 'Matte', 'Glass Fiber']
    )""")
    assert result['base'] == 'PC'
    assert sorted(result['attrs']) == ['Blend', 'Carbon Fiber']


def test_split_material_word_boundary_does_not_partial_match(page: Page):
    """'PE' must NOT pull from 'PETG' just because PE is a substring.
    Word-boundary regex protects against the substring trap."""
    _open_wizard_no_fetches(page)
    result = page.evaluate("""() => window.splitMaterialAndAttributes(
        'PETG Matte', ['PE', 'Matte']
    )""")
    # PE is a known attribute (hypothetically) but should not pull from PETG.
    assert result['base'] == 'PETG'
    assert result['attrs'] == ['Matte']


def test_split_material_falls_back_when_no_known_list(page: Page):
    _open_wizard_no_fetches(page)
    result = page.evaluate("""() => window.splitMaterialAndAttributes('PC Blend Carbon Fiber', [])""")
    assert result == {'base': 'PC Blend Carbon Fiber', 'attrs': []}


def test_split_material_handles_hyphenated_attribute(page: Page):
    """Spoolman has both 'Carbon Fiber' and 'Carbon-Fiber' in the canonical
    choices list. Either spelling in the parser output should map to the
    matching choice."""
    _open_wizard_no_fetches(page)
    result = page.evaluate("""() => window.splitMaterialAndAttributes(
        'PC Carbon-Fiber', ['Carbon-Fiber', 'Carbon Fiber']
    )""")
    assert result['base'] == 'PC'
    assert result['attrs'] == ['Carbon-Fiber']


def test_split_material_case_insensitive_match_preserves_canonical_casing(page: Page):
    _open_wizard_no_fetches(page)
    result = page.evaluate("""() => window.splitMaterialAndAttributes(
        'pla galaxy', ['Galaxy', 'Carbon Fiber']
    )""")
    assert result['base'] == 'pla'
    assert result['attrs'] == ['Galaxy']  # canonical casing wins


# --- attribute-aware matcher ----------------------------------------------

def test_find_filament_matches_attribute_aware_pc_blend(page: Page):
    """The user's real bug: filament 122 stored as material='PC' got
    duplicated when the parser returned 'PC Blend Carbon Fiber' because
    materials didn't strict-match. With known attributes loaded, the
    parser side is split to base='PC' and matches stored 'PC' directly."""
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.extraFields = {filament: [
            {key: 'filament_attributes', choices: ['Carbon Fiber', 'Blend', 'Matte']}
        ]};
        wizardState.allFilaments = [
            {id: 122, name: 'Black (Carbon Fiber)', color_name: null, material: 'PC', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PC Blend Carbon Fiber', color_name: 'Black'
        });
    }""")
    assert len(matches) == 1
    assert matches[0]['id'] == 122


def test_find_filament_matches_token_subset_material(page: Page):
    """Real-world: filament 122 stored with material='PC', Prusament parser
    returns 'PC Blend Carbon Fiber'. Strict equality missed the match and
    a duplicate filament got created. Token-subset match handles this."""
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 122, name: 'Black (Carbon Fiber)', color_name: null, material: 'PC', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PC Blend Carbon Fiber', color_name: 'Black'
        });
    }""")
    assert len(matches) == 1
    assert matches[0]['id'] == 122


def test_find_filament_matches_token_match_does_not_substring_trap(page: Page):
    """Token-subset must respect word boundaries — 'PE' must NOT match
    'PETG' just because PE is a substring of PETG. Tokenizer split keeps
    them as distinct tokens."""
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 1, name: 'Galaxy Black', color_name: null, material: 'PETG', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PE', color_name: 'Galaxy Black'
        });
    }""")
    assert matches == [], "PE must not match PETG"


def test_find_filament_matches_token_match_pla_galaxy(page: Page):
    """Symmetric case to the PC one: parser returns just 'PLA' but stored
    filament is 'PLA Galaxy'. Tokenize → {pla} ⊆ {pla, galaxy} → match."""
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 5, name: 'Bright Yellow', color_name: null, material: 'PLA Galaxy', vendor: {name: 'Prusament'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'Bright Yellow'
        });
    }""")
    assert len(matches) == 1
    assert matches[0]['id'] == 5


def test_find_filament_matches_case_insensitive(page: Page):
    _open_wizard_no_fetches(page)
    matches = page.evaluate("""() => {
        wizardState.allFilaments = [
            {id: 1, name: 'Silver (PEARL MOUSE)', color_name: null, material: 'pla', vendor: {name: 'PRUSAMENT'}}
        ];
        return window.findFilamentMatches({
            vendor: {name: 'Prusament'}, material: 'PLA', color_name: 'pearl mouse'
        });
    }""")
    assert len(matches) == 1


# --- extractSpoolFieldsFromTemplate ---------------------------------------

def test_extract_spool_fields_basic_mapping(page: Page):
    _open_wizard_no_fetches(page)
    override = page.evaluate("""() => window.extractSpoolFieldsFromTemplate({
        weight: 998,
        spool_weight: 215,
        external_link: 'https://prusament.com/spool/1/aaa/',
        extra: {
            prusament_manufacturing_date: '2026-03-12',
            prusament_length_m: 330
        }
    })""")
    assert override['initial_weight'] == 998
    assert override['spool_weight'] == 215


def test_extract_spool_fields_product_url_goes_into_extras_unwrapped(page: Page):
    """Regression: Spoolman has NO native product_url on Spool — it's a
    registered extra. Sending it at top-level made Spoolman silently drop
    it. Must land at extras['product_url'] AS-IS (not literal-quote-wrapped)
    because product_url is in JSON_STRING_FIELDS and sanitize_outbound_data
    wraps it via json.dumps. Pre-wrapping here would double-wrap and the
    literal quote chars would leak into the UI on read-back."""
    _open_wizard_no_fetches(page)
    override = page.evaluate("""() => window.extractSpoolFieldsFromTemplate({
        external_link: 'https://prusament.com/spool/1/aaa/'
    })""")
    assert 'product_url' not in override, "must NOT be top-level — Spoolman drops it"
    assert override['extra']['product_url'] == 'https://prusament.com/spool/1/aaa/'
    # purchase_url falls back to the per-spool URL only when the parser
    # didn't surface a canonical store link. With purchase_link present,
    # that wins instead.
    assert override['extra']['purchase_url'] == 'https://prusament.com/spool/1/aaa/'

    with_store = page.evaluate("""() => window.extractSpoolFieldsFromTemplate({
        external_link: 'https://prusament.com/spool/1/aaa/',
        purchase_link: 'https://www.prusa3d.com/product/prusament-pla-pearl-mouse-1kg/'
    })""")
    assert with_store['extra']['product_url'] == 'https://prusament.com/spool/1/aaa/'
    assert with_store['extra']['purchase_url'] == 'https://www.prusa3d.com/product/prusament-pla-pearl-mouse-1kg/'


def test_extract_spool_fields_wraps_extras_in_literal_quotes(page: Page):
    """Spoolman text-type extras must arrive as JSON-quoted strings.
    Without the wrap, sanitize_outbound_data's json.loads('330') round-
    trips to int 330 and Spoolman 400s with 'Value is not a string.'
    This was the bug that silently failed every spool create."""
    _open_wizard_no_fetches(page)
    override = page.evaluate("""() => window.extractSpoolFieldsFromTemplate({
        extra: {
            prusament_manufacturing_date: '2026-03-12',
            prusament_length_m: 330
        }
    })""")
    assert override['extra']['prusament_manufacturing_date'] == '"2026-03-12"'
    assert override['extra']['prusament_length_m'] == '"330"'


def test_extract_spool_fields_omits_empty_extras(page: Page):
    """No url and no prusament-specific data → no `extra` key on the
    override at all, so we don't accidentally clobber wizard-wide extras
    like needs_label_print on the backend merge step."""
    _open_wizard_no_fetches(page)
    override = page.evaluate("""() => window.extractSpoolFieldsFromTemplate({
        weight: 1000
    })""")
    assert 'extra' not in override
    assert override['initial_weight'] == 1000


def test_extract_spool_fields_skips_zero_spool_weight(page: Page):
    """Some Prusament responses come back with spool_weight=0. Treat as
    'not provided' so the row override doesn't squash the filament-level
    default with 0."""
    _open_wizard_no_fetches(page)
    override = page.evaluate("""() => window.extractSpoolFieldsFromTemplate({
        weight: 1000,
        spool_weight: 0
    })""")
    assert 'spool_weight' not in override


# --- wizardResetSpoolRows / lock interaction ------------------------------

def test_badge_update_does_not_destroy_url_inputs(page: Page):
    """Real-world: rapid blind-scanning of multiple Prusament boxes used to
    fail because each status transition (pending → ok) called
    wizardRenderSpoolRows which blew away the entire rows container via
    innerHTML. The user's in-flight typing into row 2 was lost mid-scan
    when row 1's fetch completed. Badge-only updates must preserve the
    input element references and any text the user has typed."""
    _open_wizard_no_fetches(page)
    state = page.evaluate("""() => {
        document.getElementById('wiz-spool-qty').value = 3;
        window.wizardSyncSpoolRows();
        // Capture the row 2 input node BEFORE any badge updates.
        const beforeNode = document.querySelector("[data-spool-row-idx='1'] input[type='url']");
        // Pretend the user is mid-typing into row 2.
        beforeNode.value = 'https://prusament.com/spool/9/zzz';
        // Fire a status update on row 0 — this is what used to nuke row 2.
        wizardState.spoolRows[0].status = 'pending';
        window.wizardRenderSpoolRowBadge(0);
        wizardState.spoolRows[0].status = 'ok';
        wizardState.spoolRows[0].override = {initial_weight: 998};
        window.wizardRenderSpoolRowBadge(0);
        const afterNode = document.querySelector("[data-spool-row-idx='1'] input[type='url']");
        return {
            sameNode: beforeNode === afterNode,
            preservedValue: afterNode.value,
            row0BadgeText: document.querySelector("[data-spool-row-idx='0'] .badge").innerText
        };
    }""")
    assert state['sameNode'] is True, "row 2's input element must NOT be re-created"
    assert state['preservedValue'] == 'https://prusament.com/spool/9/zzz'
    assert '✓' in state['row0BadgeText']


def test_badge_update_handles_error_state_outline(page: Page):
    _open_wizard_no_fetches(page)
    classes = page.evaluate("""() => {
        document.getElementById('wiz-spool-qty').value = 1;
        window.wizardSyncSpoolRows();
        wizardState.spoolRows[0].status = 'error';
        wizardState.spoolRows[0].errorMsg = 'bad url';
        window.wizardRenderSpoolRowBadge(0);
        const row = document.querySelector("[data-spool-row-idx='0']");
        return Array.from(row.classList);
    }""")
    assert 'border-danger' in classes
    assert 'border' in classes


def test_reset_spool_rows_clears_state_and_re_renders(page: Page):
    _open_wizard_no_fetches(page)
    state = page.evaluate("""() => {
        // Seed: one row marked as ok with an override.
        wizardState.spoolRows = [
            {idx: 0, url: 'x', status: 'ok', errorMsg: '', override: {initial_weight: 999}}
        ];
        wizardState.filamentLockedFromScan = true;
        document.getElementById('wiz-spool-qty').value = 3;
        window.wizardResetSpoolRows();
        return {
            rowCount: wizardState.spoolRows.length,
            firstStatus: wizardState.spoolRows[0] && wizardState.spoolRows[0].status,
            firstUrl: wizardState.spoolRows[0] && wizardState.spoolRows[0].url,
            locked: wizardState.filamentLockedFromScan,
            domRows: document.querySelectorAll('[data-spool-row-idx]').length
        };
    }""")
    # Row count follows current quantity (3), all empty.
    assert state['rowCount'] == 3
    assert state['firstStatus'] == 'empty'
    assert state['firstUrl'] == ''
    assert state['locked'] is False
    assert state['domRows'] == 3


def test_post_success_lock_survives_row_resync(page: Page):
    """Regression for the bug the user just hit: wizardResetSpoolRows
    triggers wizardSyncSpoolRows → wizardUpdateSubmitGate →
    wizardValidateSubmit, which used to unconditionally re-enable
    the submit button. The lock must hold."""
    _open_wizard_no_fetches(page)
    disabled = page.evaluate("""() => {
        wizardState.lockedAfterSuccess = true;
        wizardState.mode = 'manual';
        // Force the same call chain the post-success path runs.
        document.getElementById('wiz-spool-qty').value = 1;
        window.wizardResetSpoolRows();
        return document.getElementById('btn-wiz-submit').disabled;
    }""")
    assert disabled is True


def test_lock_clears_on_dirty_input_event(page: Page):
    _open_wizard_no_fetches(page)
    state = page.evaluate("""() => {
        wizardState.lockedAfterSuccess = true;
        document.getElementById('btn-wiz-submit').disabled = true;
        // Simulate an input event from inside the wizard.
        const inp = document.getElementById('wiz-spool-qty');
        inp.value = 2;
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        return {
            locked: wizardState.lockedAfterSuccess,
            disabled: document.getElementById('btn-wiz-submit').disabled
        };
    }""")
    assert state['locked'] is False
    assert state['disabled'] is False


# --- computeFilamentBackfillDiff (filament-from-scan backfill) ------------

def test_backfill_diff_silent_fills_when_existing_is_unset(page: Page):
    """Existing filament has nulls/missing fields the parser knows. Those
    should land in the silent diff so applyFilamentBackfillSilent can
    PATCH them in without prompting."""
    _open_wizard_no_fetches(page)
    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {
            id: 122, material: 'PC', name: 'Black (Carbon Fiber)',
            density: null, diameter: null,
            settings_extruder_temp: null, settings_bed_temp: null,
            spool_weight: 0, weight: 0, color_hex: '2B2B2B',
            extra: {filament_attributes: ['Carbon Fiber']}
        },
        {
            material: 'PC Blend Carbon Fiber', color_name: 'Black',
            color_hex: '2B2B2B', density: 1.18, diameter: 1.75,
            weight: 800, spool_weight: 215,
            settings_extruder_temp: 215, settings_bed_temp: 60,
            extra: {nozzle_temp_max: '"225"', bed_temp_max: '"60"'}
        },
        ['Carbon Fiber', 'Blend']
    )""")
    s = diff['silent']
    assert s.get('diameter') == 1.75
    assert s.get('density') == 1.18
    assert s.get('weight') == 800
    assert s.get('spool_weight') == 215
    assert s.get('settings_extruder_temp') == 215
    assert s.get('settings_bed_temp') == 60
    assert s.get('extra.nozzle_temp_max') == '"225"'
    assert s.get('extra.bed_temp_max') == '"60"'
    # filament_attributes set-union: existing kept, parser-implied added.
    assert sorted(s.get('extra.filament_attributes', [])) == ['Blend', 'Carbon Fiber']
    assert s.get('extra.original_color') == '"Black"'
    # No mismatches because everything was unset OR equal.
    assert diff['mismatches'] == []


def test_backfill_diff_mismatch_when_values_differ(page: Page):
    """Existing has non-zero, non-null values that disagree with the
    parser. Those land in the mismatch list (not silent) so the user
    decides per-field whether to upgrade."""
    _open_wizard_no_fetches(page)
    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {
            id: 122, material: 'PC', density: 1.20, diameter: 1.75,
            spool_weight: 215, weight: 865, color_hex: '2B2B2B',
            settings_extruder_temp: 240, settings_bed_temp: 90,
            extra: {nozzle_temp_max: '"260"', bed_temp_max: '"100"'}
        },
        {
            material: 'PC Blend Carbon Fiber', color_name: 'Black',
            color_hex: '868463', density: 1.18, diameter: 1.75,
            weight: 800, spool_weight: 248,
            settings_extruder_temp: 215, settings_bed_temp: 60,
            extra: {nozzle_temp_max: '"225"', bed_temp_max: '"60"'}
        },
        ['Carbon Fiber', 'Blend']
    )""")
    keys = {m['key']: m for m in diff['mismatches']}
    # weight differs by 65g — over the 10g threshold.
    assert 'weight' in keys
    # spool_weight differs by 33g — should hint NFC in the renderer.
    assert 'spool_weight' in keys
    assert keys['spool_weight']['kind'] == 'spool_weight'
    # color_hex always lands in mismatch when both sides set + differ.
    assert 'color_hex' in keys
    assert keys['color_hex']['kind'] == 'color'
    # Temps differ → mismatch.
    assert 'settings_extruder_temp' in keys
    assert 'settings_bed_temp' in keys
    assert 'extra.nozzle_temp_max' in keys
    assert 'extra.bed_temp_max' in keys
    # density differs by 0.02 (under 0.05 threshold) → NOT a mismatch.
    assert 'density' not in keys
    # diameter equal → not a mismatch.
    assert 'diameter' not in keys


def test_backfill_diff_material_never_silent_overwrites(page: Page):
    """When the parser splits to a base that equals the stored material,
    no mismatch and no silent change. When base differs, mismatch only —
    never silently overwrite the user's curated material field."""
    _open_wizard_no_fetches(page)
    same = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PC', extra: {}},
        {material: 'PC Blend Carbon Fiber', extra: {}},
        ['Carbon Fiber', 'Blend']
    )""")
    assert 'material' not in same['silent']
    assert not any(m['key'] == 'material' for m in same['mismatches'])

    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PETG', extra: {}},
        {material: 'PC Blend Carbon Fiber', extra: {}},
        ['Carbon Fiber', 'Blend']
    )""")
    assert 'material' not in diff['silent']
    assert any(m['key'] == 'material' for m in diff['mismatches'])


def test_backfill_diff_filament_attributes_handles_string_form(page: Page):
    """Real-world: /api/filaments doesn't run parse_inbound_data, so the
    JS receives `filament_attributes` as a JSON-encoded STRING (e.g.
    '["Carbon Fiber"]') instead of an array. The matcher and diff must
    transparently parse this so the user's "Blend" can be added to the
    existing ["Carbon Fiber"] without missing a beat."""
    _open_wizard_no_fetches(page)
    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 122, material: 'PC', extra: {filament_attributes: '["Carbon Fiber"]'}},
        {material: 'PC Blend Carbon Fiber', extra: {}},
        ['Carbon Fiber', 'Blend']
    )""")
    attrs = diff['silent']['extra.filament_attributes']
    assert sorted(attrs) == ['Blend', 'Carbon Fiber']


def test_backfill_diff_filament_attributes_set_union_no_remove(page: Page):
    """Existing attrs must always be preserved. Parser-implied attrs that
    aren't already there get added. If the parser doesn't imply any new
    attrs, no silent update for the field at all."""
    _open_wizard_no_fetches(page)
    no_change = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PC', extra: {filament_attributes: ['Carbon Fiber', 'Blend']}},
        {material: 'PC Blend Carbon Fiber', extra: {}},
        ['Carbon Fiber', 'Blend']
    )""")
    assert 'extra.filament_attributes' not in no_change['silent']

    additive = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PC', extra: {filament_attributes: ['Custom User Attr']}},
        {material: 'PC Blend Carbon Fiber', extra: {}},
        ['Carbon Fiber', 'Blend']
    )""")
    attrs = additive['silent']['extra.filament_attributes']
    assert 'Custom User Attr' in attrs, 'must preserve user-only attrs'
    assert 'Blend' in attrs
    assert 'Carbon Fiber' in attrs


def test_backfill_diff_original_color_always_overwrites(page: Page):
    """original_color is the manufacturer-side name slot. Whenever the
    parser provides one and it differs from what's stored, replace it.
    This is *not* fill-if-empty — the parser is authoritative for this
    field by design (user's color_name stays the filter-friendly value)."""
    _open_wizard_no_fetches(page)
    overwrite = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PLA', extra: {original_color: '"Black"'}},
        {material: 'PLA', color_name: 'Pearl Mouse', extra: {}},
        []
    )""")
    assert overwrite['silent']['extra.original_color'] == '"Pearl Mouse"'

    # Same value already stored → no-op (don't fire a useless PATCH).
    no_change = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PLA', extra: {original_color: '"Pearl Mouse"'}},
        {material: 'PLA', color_name: 'Pearl Mouse', extra: {}},
        []
    )""")
    assert 'extra.original_color' not in no_change['silent']


def test_backfill_diff_color_hex_never_silent(page: Page):
    """color_hex is user-calibrated. Even when existing is set and the
    parser disagrees, never silently overwrite — always mismatch panel."""
    _open_wizard_no_fetches(page)
    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PLA', color_hex: '111111', extra: {}},
        {material: 'PLA', color_hex: '222222', extra: {}},
        []
    )""")
    assert 'color_hex' not in diff['silent']
    assert any(m['key'] == 'color_hex' and m['kind'] == 'color' for m in diff['mismatches'])


def test_backfill_diff_skips_spool_only_extras(page: Page):
    """prusament_manufacturing_date and prusament_length_m describe a
    specific box, not a filament product. They MUST never appear in
    the filament backfill diff — they belong on the spool record."""
    _open_wizard_no_fetches(page)
    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PLA', extra: {}},
        {material: 'PLA', extra: {
            prusament_manufacturing_date: '2026-03-12',
            prusament_length_m: 330
        }},
        []
    )""")
    assert 'extra.prusament_manufacturing_date' not in diff['silent']
    assert 'extra.prusament_length_m' not in diff['silent']
    assert not any('prusament' in m['key'] for m in diff['mismatches'])


def test_backfill_diff_color_name_never_appears(page: Page):
    """color_name is the user's filter-friendly base color (e.g. 'Black')
    and intentionally differs from the manufacturer's name (e.g. 'Pearl
    Mouse'). The parser's color_name flows into extra.original_color, never
    into a top-level mismatch row."""
    _open_wizard_no_fetches(page)
    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {id: 1, material: 'PLA', color_name: 'Black', name: 'Black (Pearl Mouse)', extra: {}},
        {material: 'PLA', color_name: 'Pearl Mouse', name: 'Prusament PLA Pearl Mouse', extra: {}},
        []
    )""")
    assert 'color_name' not in diff['silent']
    assert 'name' not in diff['silent']
    assert not any(m['key'] in ('color_name', 'name') for m in diff['mismatches'])
    # But original_color does flow.
    assert diff['silent'].get('extra.original_color') == '"Pearl Mouse"'


def test_backfill_diff_no_change_when_existing_complete(page: Page):
    _open_wizard_no_fetches(page)
    diff = page.evaluate("""() => window.computeFilamentBackfillDiff(
        {
            id: 1, material: 'PLA', density: 1.24, diameter: 1.75,
            weight: 1000, spool_weight: 215,
            settings_extruder_temp: 215, settings_bed_temp: 60,
            color_hex: 'AAAAAA',
            extra: {
                filament_attributes: ['Carbon Fiber', 'Blend'],
                nozzle_temp_max: '"225"', bed_temp_max: '"60"',
                original_color: '"Pearl Mouse"'
            }
        },
        {
            material: 'PLA Blend Carbon Fiber', color_name: 'Pearl Mouse',
            color_hex: 'AAAAAA', density: 1.24, diameter: 1.75,
            weight: 1000, spool_weight: 215,
            settings_extruder_temp: 215, settings_bed_temp: 60,
            extra: {nozzle_temp_max: '"225"', bed_temp_max: '"60"'}
        },
        ['Carbon Fiber', 'Blend']
    )""")
    assert diff['silent'] == {}
    assert diff['mismatches'] == []


def test_wizard_reset_clears_post_success_lock(page: Page):
    """Opening a fresh wizard must not inherit a post-success lock from
    the previous session — otherwise the user opens, clicks Manual,
    fills a form, and the submit button is mysteriously dead."""
    _open_wizard_no_fetches(page)
    locked = page.evaluate("""() => {
        wizardState.lockedAfterSuccess = true;
        // wizardReset is the function called at the top of openWizardModal.
        // It's not exposed on window, but openWizardModal triggers it.
        return new Promise(async (resolve) => {
            await window.openWizardModal();
            resolve(wizardState.lockedAfterSuccess);
        });
    }""")
    assert locked is False
