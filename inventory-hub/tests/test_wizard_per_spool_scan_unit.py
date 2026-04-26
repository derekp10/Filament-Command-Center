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
    # purchase_url mirrored from external_link too — the parser doesn't
    # surface a separate canonical store URL yet, so this is the best
    # default we can offer to populate the Spool's Purchase Link field.
    assert override['extra']['purchase_url'] == 'https://prusament.com/spool/1/aaa/'


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
