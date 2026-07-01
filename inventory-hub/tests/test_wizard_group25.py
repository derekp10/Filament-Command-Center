"""Group 25 — Wizard UX: Print/Queue affordances, Tab-confirm, spool-label parity.

All three items are pure-frontend inv_wizard.js. Driven through page.evaluate
against the shipped code, but isolated from the full wizard flow via the
extracted, testable helpers:
  - 25.3  window.wizardBuildFilamentLabelDiff(orig, fPayload)  — label-flag diff
  - 25.H  window.wizardRenderPostSaveQueueActions(mode, created, editSid) — chips
  - 25.I  window.wizardBindCombobox({...items})               — Tab confirms

Needs the running dev container (JS served live from the bind mount).
"""

from playwright.sync_api import Page


def _load(page: Page):
    page.goto("http://localhost:8000")
    page.wait_for_selector("#buffer-zone")
    page.wait_for_function(
        "() => typeof window.wizardBuildFilamentLabelDiff === 'function'"
        " && typeof window.wizardRenderPostSaveQueueActions === 'function'"
        " && typeof window.wizardBindCombobox === 'function'",
        timeout=8000,
    )


# --- 25.3 — wizardBuildFilamentLabelDiff (spool-label flag parity) ----------

def test_label_diff_flags_original_color_change(page: Page):
    """A manufacturer Color-NAME (original_color) change must land in
    changedExtras so _maybePromptLabelReprint fires flag_spool_labels — the
    parity gap the wizard previously had vs the primary Edit-Filament path."""
    _load(page)
    res = page.evaluate("""() => window.wizardBuildFilamentLabelDiff(
        {name: 'Black', material: 'PLA', extra: {original_color: '"Galaxy Black"'}},
        {name: 'Black', material: 'PLA', extra: {original_color: 'Nebula Blue'}}
    )""")
    assert res["changedExtras"].get("original_color") is True
    # name unchanged → not flagged as a native change
    assert "name" not in res["changedNative"]


def test_label_diff_ignores_quote_wrap_when_unchanged(page: Page):
    """Stored original_color is JSON-quote-wrapped ('"Galaxy Black"'); the form
    value is raw ('Galaxy Black'). An unchanged edit must NOT false-flag."""
    _load(page)
    res = page.evaluate("""() => window.wizardBuildFilamentLabelDiff(
        {name: 'Black', extra: {original_color: '"Galaxy Black"'}},
        {name: 'Black', extra: {original_color: 'Galaxy Black'}}
    )""")
    assert "original_color" not in res["changedExtras"]


def test_label_diff_skips_original_color_when_not_collected(page: Page):
    """If the wizard didn't collect original_color (key absent from the new
    extras), don't compare — a rendered-but-absent field would else false-flag."""
    _load(page)
    res = page.evaluate("""() => window.wizardBuildFilamentLabelDiff(
        {name: 'Black', extra: {original_color: '"Galaxy Black"'}},
        {name: 'Black', extra: {}}
    )""")
    assert "original_color" not in res["changedExtras"]


def test_label_diff_flags_cleared_original_color(page: Page):
    """Clearing the Color-name in edit mode sends the delete-sentinel; that IS a
    spool-label change and must flag."""
    _load(page)
    res = page.evaluate("""() => window.wizardBuildFilamentLabelDiff(
        {name: 'Black', extra: {original_color: '"Galaxy Black"'}},
        {name: 'Black', extra: {original_color: window.FCC_DELETE_EXTRA}}
    )""")
    assert res["changedExtras"].get("original_color") is True


def test_label_diff_flags_name_and_attributes(page: Page):
    """Sanity: the pre-existing native (name) + filament_attributes detections
    still work after the extraction."""
    _load(page)
    res = page.evaluate("""() => window.wizardBuildFilamentLabelDiff(
        {name: 'Black', material: 'PLA', extra: {filament_attributes: ['Matte']}},
        {name: 'Jet Black', material: 'PLA', extra: {filament_attributes: ['Matte', 'Carbon Fiber']}}
    )""")
    assert res["changedNative"].get("name") == "Jet Black"
    assert res["changedExtras"].get("filament_attributes") is True


# --- 25.H — wizardRenderPostSaveQueueActions (Queue All + edit chip) --------

def _ensure_action_row(page: Page):
    """The #wiz-postcreate-actions row lives in the wizard modal template (in the
    DOM even while hidden); create it if a bare page ever lacks it."""
    page.evaluate(
        """() => {
            if (!document.getElementById('wiz-postcreate-actions')) {
                const d = document.createElement('div');
                d.id = 'wiz-postcreate-actions';
                document.body.appendChild(d);
            }
        }"""
    )


def test_queue_actions_multi_create_shows_queue_all(page: Page):
    _load(page)
    _ensure_action_row(page)
    counts = page.evaluate(
        """() => {
            window.labelQueue = [];
            window.wizardRenderPostSaveQueueActions('manual', [101, 102, 103], null);
            const row = document.getElementById('wiz-postcreate-actions');
            return {
                chips: row.querySelectorAll('.fcc-wiz-queue-label').length,
                all: row.querySelectorAll('.fcc-wiz-queue-all').length,
                allText: (row.querySelector('.fcc-wiz-queue-all') || {}).innerText || ''
            };
        }"""
    )
    assert counts["chips"] == 3
    assert counts["all"] == 1
    assert "Queue All (3)" in counts["allText"]


def test_queue_actions_single_create_no_queue_all(page: Page):
    _load(page)
    _ensure_action_row(page)
    counts = page.evaluate(
        """() => {
            window.labelQueue = [];
            window.wizardRenderPostSaveQueueActions('manual', [101], null);
            const row = document.getElementById('wiz-postcreate-actions');
            return {
                chips: row.querySelectorAll('.fcc-wiz-queue-label').length,
                all: row.querySelectorAll('.fcc-wiz-queue-all').length
            };
        }"""
    )
    assert counts["chips"] == 1
    assert counts["all"] == 0


def test_queue_actions_edit_mode_shows_chip(page: Page):
    """Previously edit_spool rendered NO queue button; now it gets a chip for
    the edited spool (and no Queue All)."""
    _load(page)
    _ensure_action_row(page)
    counts = page.evaluate(
        """() => {
            window.labelQueue = [];
            window.wizardRenderPostSaveQueueActions('edit_spool', null, 55);
            const row = document.getElementById('wiz-postcreate-actions');
            const chip = row.querySelector('.fcc-wiz-queue-label');
            return {
                chips: row.querySelectorAll('.fcc-wiz-queue-label').length,
                all: row.querySelectorAll('.fcc-wiz-queue-all').length,
                chipText: chip ? chip.innerText : ''
            };
        }"""
    )
    assert counts["chips"] == 1
    assert counts["all"] == 0
    assert "55" in counts["chipText"]


def test_queue_all_queues_each_and_dedups(page: Page):
    """Clicking Queue All calls addToQueue once per not-yet-queued spool
    (dedups against a pre-populated labelQueue) and turns green."""
    _load(page)
    _ensure_action_row(page)
    res = page.evaluate(
        """() => {
            window.__queued = [];
            window.labelQueue = [{ id: 102, type: 'spool' }];  // 102 already queued
            window.addToQueue = (item) => { window.__queued.push(item.id); window.labelQueue.push(item); return true; };
            window.wizardRenderPostSaveQueueActions('manual', [101, 102, 103], null);
            const all = document.getElementById('wiz-postcreate-actions').querySelector('.fcc-wiz-queue-all');
            all.click();
            return {
                queued: window.__queued,
                allDisabled: all.disabled,
                allGreen: all.classList.contains('btn-success')
            };
        }"""
    )
    assert res["queued"] == [101, 103], "102 was already queued → not re-added"
    assert res["allDisabled"] is True
    assert res["allGreen"] is True


# --- 25.I — combobox Tab confirms the highlighted item ----------------------

def _bind_test_combobox(page: Page):
    """Inject a controlled combobox triple and bind it with known items."""
    page.evaluate(
        """() => {
            document.getElementById('g25-cb-wrap')?.remove();
            const wrap = document.createElement('div');
            wrap.id = 'g25-cb-wrap';
            wrap.innerHTML = `
                <input id="g25-search" type="text" autocomplete="off">
                <input id="g25-hidden" type="hidden">
                <div id="g25-drop" style="display:none"></div>`;
            document.body.appendChild(wrap);
            window.wizardBindCombobox({
                searchId: 'g25-search', hiddenId: 'g25-hidden', dropdownId: 'g25-drop',
                items: [{ value: '10', label: 'Apple' }, { value: '20', label: 'Banana' }]
            });
        }"""
    )


def test_combobox_tab_confirms_partial_match(page: Page):
    """Typing a partial match then Tab confirms the single visible option into
    the hidden field (Enter's behavior, but Tab also advances focus)."""
    _load(page)
    _bind_test_combobox(page)
    res = page.evaluate(
        """() => {
            const s = document.getElementById('g25-search');
            const h = document.getElementById('g25-hidden');
            const d = document.getElementById('g25-drop');
            s.focus();                                   // opens + renders all
            s.value = 'ban';
            s.dispatchEvent(new Event('input', { bubbles: true }));  // filter → Banana; hidden cleared (no exact match)
            const beforeTab = h.value;
            s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
            return { beforeTab, after: h.value, dropHidden: d.style.display === 'none' };
        }"""
    )
    assert res["beforeTab"] == "", "partial match must not leak a value before Tab"
    assert res["after"] == "20", "Tab confirms the visible Banana option"
    assert res["dropHidden"] is True


def test_combobox_tab_confirms_highlighted_item(page: Page):
    """ArrowDown highlights the first item; Tab confirms THAT highlighted item."""
    _load(page)
    _bind_test_combobox(page)
    res = page.evaluate(
        """() => {
            const s = document.getElementById('g25-search');
            const h = document.getElementById('g25-hidden');
            s.focus();  // opens with full list
            s.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));  // highlight Apple
            s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
            return { after: h.value };
        }"""
    )
    assert res["after"] == "10", "Tab confirms the ArrowDown-highlighted Apple"


def test_combobox_tab_through_untouched_does_not_confirm_or_dirty(page: Page):
    """Review fix — tabbing THROUGH an untouched combobox (dropdown auto-opened
    on focus, nothing typed or highlighted) must NOT write visible[0]'s label
    into the box and must NOT fire a bubbling change (which would spuriously flip
    the wizard's dirty flag → false 'Unsaved Changes' prompt)."""
    _load(page)
    _bind_test_combobox(page)
    res = page.evaluate(
        """() => {
            const s = document.getElementById('g25-search');
            const h = document.getElementById('g25-hidden');
            let changes = 0;
            h.addEventListener('change', () => changes++);
            s.focus();  // opens the full list, nothing highlighted (no prior value)
            s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
            return { search: s.value, hidden: h.value, changes };
        }"""
    )
    assert res["search"] == "", "untouched box must not get the sentinel/first label"
    assert res["hidden"] == "", "no value confirmed on a pass-through Tab"
    assert res["changes"] == 0, "no spurious change event (would flip isDirty)"


def test_combobox_tab_prefilled_unchanged_fires_no_change(page: Page):
    """Review fix — tabbing through a combobox whose value is already selected
    (and unchanged) must not re-dispatch change (no spurious dirty flip)."""
    _load(page)
    _bind_test_combobox(page)
    res = page.evaluate(
        """() => {
            const s = document.getElementById('g25-search');
            const h = document.getElementById('g25-hidden');
            // Pre-select Apple (as a prior confirm would have).
            h.value = '10';
            s.value = 'Apple';
            let changes = 0;
            h.addEventListener('change', () => changes++);
            s.focus();  // re-opens; render highlights the current selection (Apple)
            s.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
            return { hidden: h.value, changes };
        }"""
    )
    assert res["hidden"] == "10", "unchanged selection preserved"
    assert res["changes"] == 0, "no change event when the value didn't change"
