/* MODULE: WIZARD (Add Inventory) */
console.log("🚀 Loaded Module: WIZARD");

let wizardState = {
    mode: 'manual', // 'existing', 'external', 'manual'
    vendors: [],
    selectedFilamentId: null,
    externalMetaData: null,
    editSpoolId: null,
    returnToSpoolId: null, // Track which spool detail modal to re-open after wizard closes
    returnToFilamentId: null, // Track which filament detail modal to re-open after wizard closes
    isDirty: false,    // true when the user has modified any form field or chip
    forceClose: false  // set true to bypass the dirty guard when we want to programmatically close
};

// Empty-spool-weight inheritance helper (resolveEmptySpoolWeight) lives in
// modules/weight_utils.js — loaded before this module in scripts.html and
// exposed as window.resolveEmptySpoolWeight so the bare calls below resolve
// against the global. See weight_utils.js for the cascade rules.

// --- INHERITANCE BADGE FOR wiz-spool-empty_weight FIELD ---
// Phase 2 (Group 12): the input is now bound to <EmptyWeightField>
// (modules/empty_weight_field.js) so it shares the auto-clear-on-input
// behavior with Edit-Filament Specs and the post-archive prompt. The wizard
// keeps its imperative `wizardSetSpoolEmptyWeightInherited` API — that's
// what the three wizard open flows already call after running their own
// cascade resolution, and it stays the simplest direct-DOM path. The shared
// component only owns the listener that hides the badge as soon as the user
// types over the inherited value.
(function () {
    const inputEl = document.getElementById('wiz-spool-empty_weight');
    if (!inputEl || typeof window.bindEmptyWeightField !== 'function') return;
    window.bindEmptyWeightField({
        input: inputEl,
        badge: document.getElementById('wiz-spool-empty-inherited-badge'),
        sourceLabel: document.getElementById('wiz-spool-empty-inherited-source'),
        // No copyVendorBtn in the wizard — the wizard auto-prefills via the
        // cascade so the affordance is redundant. The Specs tab in the
        // edit-filament modal IS the surface that uses copyVendorBtn.
    });
})();

window.wizardSetSpoolEmptyWeightInherited = (value, source) => {
    const inputEl = document.getElementById('wiz-spool-empty_weight');
    const badge = document.getElementById('wiz-spool-empty-inherited-badge');
    const sourceEl = document.getElementById('wiz-spool-empty-inherited-source');
    if (!inputEl) return;
    inputEl.value = (value !== null && value !== undefined) ? value : '';
    if (badge && sourceEl && (source === 'filament' || source === 'vendor')) {
        sourceEl.textContent = source;
        badge.style.display = '';
    } else if (badge) {
        badge.style.display = 'none';
    }
};

window.wizardClearSpoolEmptyWeightBadge = () => {
    const badge = document.getElementById('wiz-spool-empty-inherited-badge');
    if (badge) badge.style.display = 'none';
};

// --- WIZARD CLOSE → RE-OPEN DETAIL MODAL ---
// Register immediately — this script loads after the DOM is fully parsed.
(function() {
    const wizEl = document.getElementById('wizardModal');
    if (wizEl) {
        wizEl.addEventListener('hidden.bs.modal', () => {
            // Filament takes priority (it's the parent context when editing spools from filament view)
            if (wizardState.returnToFilamentId) {
                const fid = wizardState.returnToFilamentId;
                wizardState.returnToFilamentId = null;
                wizardState.returnToSpoolId = null; // Clear spool too
                setTimeout(() => {
                    if (typeof openFilamentDetails === 'function') openFilamentDetails(fid);
                }, 200);
            } else if (wizardState.returnToSpoolId) {
                const sid = wizardState.returnToSpoolId;
                wizardState.returnToSpoolId = null;
                setTimeout(() => {
                    if (typeof openSpoolDetails === 'function') openSpoolDetails(sid);
                }, 200);
            }
        });
        console.log("✅ Wizard close → re-open detail modal listener registered.");

        // --- UNSAVED CHANGES GUARD ---
        // hide.bs.modal fires before the modal closes and supports preventDefault().
        wizEl.addEventListener('hide.bs.modal', (event) => {
            if (wizardState.forceClose) { wizardState.forceClose = false; return; }
            if (wizardState.isDirty) {
                event.preventDefault();
                // Group 10.8 — was nested Swal.fire; now routed through
                // mountOverlay so the .cmd-deck scrollbar-comp shift goes away
                // and the overlay survives Bootstrap's focus trap.
                const panelHtml = `
                    <div style="background:#1e1e1e; color:#fff; border:2px solid #dc3545; border-radius:8px; padding:20px 24px; max-width:460px; width:92%;">
                        <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">⚠️ Unsaved Changes</div>
                        <div style="color:#ffc; margin-bottom:16px;">You have unsaved changes. Discard them and close?</div>
                        <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                            <button id="fcc-wiz-dirty-cancel" class="btn btn-secondary btn-sm" style="min-width:120px;">Keep Editing</button>
                            <button id="fcc-wiz-dirty-confirm" class="btn btn-danger btn-sm" style="min-width:140px;">Discard &amp; Close</button>
                        </div>
                    </div>
                `;
                const handle = window.mountOverlay({
                    id: 'fcc-wiz-unsaved-changes',
                    content: panelHtml,
                    host: wizEl,
                    initialFocus: '#fcc-wiz-dirty-cancel',
                    // Escape = keep editing (default cleanup is sufficient).
                });
                handle.element.querySelector('#fcc-wiz-dirty-confirm')?.addEventListener('click', () => {
                    handle.cleanup();
                    wizardState.isDirty = false;
                    wizardState.forceClose = true;
                    window.modals.wizardModal.hide();
                });
                handle.element.querySelector('#fcc-wiz-dirty-cancel')?.addEventListener('click', () => handle.cleanup());
            }
        });

        // Track dirty state from any form input/change inside the wizard (delegated).
        // Also lift the post-success submit lock here: once the user edits anything
        // after a successful create, the wizard is fair game again. Without this,
        // a second click on Create would silently rebuild the same spools.
        const _onDirty = () => {
            wizardState.isDirty = true;
            if (wizardState.lockedAfterSuccess) {
                wizardState.lockedAfterSuccess = false;
                const submitBtn = document.getElementById('btn-wiz-submit');
                if (submitBtn) submitBtn.disabled = false;
                const msg = document.getElementById('wiz-status-msg');
                if (msg) msg.innerHTML = '';
            }
        };
        wizEl.addEventListener('input', _onDirty);
        wizEl.addEventListener('change', _onDirty);

        // Chip removal uses onclick="this.remove()" which bypasses input/change events.
        wizEl.addEventListener('click', (e) => {
            if (e.target.classList.contains('dynamic-chip')) wizardState.isDirty = true;
        });
    }
})();

window.openWizardModal = async () => {
    // L26 follow-up: close any open details modal before launching the
    // wizard. The 2026-04-29 lock-up Derek reproed was wizard-on-top-of-
    // details — the silent-refresh path's promise can land mid-wizard-
    // open and leave state.processing stuck true. Closing the siblings
    // first mirrors the details↔details pattern shipped 2026-05-12.
    if (typeof window.hideAllDetailsModals === 'function') {
        window.hideAllDetailsModals();
    }
    wizardReset();
    if (window.modals && window.modals.wizardModal) {
        window.modals.wizardModal.show();
    } else {
        const m = new bootstrap.Modal(document.getElementById('wizardModal'));
        if (!window.modals) window.modals = {};
        window.modals.wizardModal = m;
        m.show();
    }
    // Group 10.1 SC round-6: when the wizard launches on top of another
    // modal (spool/filament details), focus stays on the launching button
    // and Bootstrap's keyboard-dismiss handler (bound to the modal
    // element) never receives Escape until the user clicks the wizard
    // first. Force focus into the wizard after show finishes so Escape
    // works immediately.
    const _wizModalEl = document.getElementById('wizardModal');
    if (_wizModalEl) {
        const _focusFirst = () => {
            const focusables = _wizModalEl.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]),'
                + ' select:not([disabled]), textarea:not([disabled]),'
                + ' [tabindex]:not([tabindex="-1"])'
            );
            for (const el of focusables) {
                if (el.offsetParent !== null) { el.focus(); return; }
            }
            _wizModalEl.focus();
        };
        // shown.bs.modal fires once Bootstrap finishes its own focus
        // management — override after that so we win the focus war.
        _wizModalEl.addEventListener('shown.bs.modal', _focusFirst, { once: true });
    }
    await Promise.all([
        wizardFetchVendors(),
        wizardFetchLocations(),
        wizardFetchExtraFields(),
        wizardFetchMaterials()
    ]);
    if (window.wizardSyncSpoolRows) window.wizardSyncSpoolRows();
    if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('create');
};

// Group 10.1 (Session C) — applies the wizard's section-collapse defaults.
// Called from openWizardModal with 'create' (collapse all optional panels),
// and from each edit-context entry point (openEditWizard, openCloneWizard,
// openNewSpoolFromFilamentWizard) with 'edit' after the prefill chain has
// filled the form — sections with any user-entered data auto-expand so the
// user sees what's actually filled in without clicking each toggle.
window.wizardApplyCollapseDefaults = (context) => {
    if (!window.bootstrap || !window.bootstrap.Collapse) return;
    const hasAnyValue = (panelEl) => {
        if (!panelEl) return false;
        const inputs = panelEl.querySelectorAll('input, select, textarea');
        for (const el of inputs) {
            if (el.type === 'checkbox' || el.type === 'radio') {
                if (el.checked) return true;
            } else if ((el.value == null ? '' : String(el.value)).trim() !== '') {
                return true;
            }
        }
        return false;
    };
    // 'always-open' stays expanded in both contexts; 'optional' obeys the
    // create=collapsed / edit=smart-on-content rule.
    const sections = [
        // Group 10.1 SC round-6: Physical Specs is collapsible like the
        // others. Chip shows the defaults at a glance so user can verify
        // by expanding only when they need to deviate from 1.75mm / 1.24.
        ['wiz-fil-color-panel',      'optional'],
        ['wiz-fil-physical-panel',   'optional'],
        ['wiz-fil-temps-panel',      'optional'],
        ['wiz-fil-extras-panel',     'optional'],
        ['wiz-spool-weight-panel',   'optional'],
        ['wiz-spool-metadata-panel', 'optional'],
        ['wiz-spool-extras-panel',   'optional'],
    ];
    // Suppress the shown.bs.collapse scroll-into-view side effect while
    // we batch-apply panel state — otherwise an edit-mode wizard with
    // 5+ panels to expand cascades through scroll animations, jumping
    // the view around. The flag is cleared right after the loop.
    window._wizSuppressScroll = true;
    sections.forEach(([id, kind]) => {
        const panelEl = document.getElementById(id);
        if (!panelEl) return;
        const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
        let open;
        if (kind === 'always-open') {
            open = true;
        } else {
            // Both 'create' and 'edit' now default to collapsed for optional
            // panels. The summary chips show what's filled in already, so
            // the user can expand only what they actually want to change.
            // Smart-expand-on-edit was dropped per Session C round-4 feedback —
            // it caused too many panels to fan open at once, with cascading
            // scrolls. Chips give the at-a-glance view that auto-expand was
            // trying to provide.
            open = false;
        }
        // Apply state synchronously WITHOUT triggering Bootstrap's animation
        // (and thus without the shown/hidden events that would re-fire scroll
        // logic). Direct class manipulation matches what Bootstrap ends up
        // with after the transition finishes.
        panelEl.classList.remove('collapsing');
        if (open) {
            panelEl.classList.add('show');
            panelEl.style.height = '';
            if (btn) btn.setAttribute('aria-expanded', 'true');
        } else {
            panelEl.classList.remove('show');
            panelEl.style.height = '';
            if (btn) btn.setAttribute('aria-expanded', 'false');
        }
    });
    window._wizSuppressScroll = false;
    // Refresh summaries now that aria-expanded / .show are settled.
    if (window.wizardRefreshAllSectionSummaries) {
        window.wizardRefreshAllSectionSummaries();
    }
    // Reset the modal-body's scroll position to the top so the user always
    // lands at Step 1 regardless of how the previous session left it.
    const modalBody = document.querySelector('#wizardModal .modal-body');
    if (modalBody) modalBody.scrollTop = 0;
};

// Group 10.1 (Session C polish) — section-summary rendering for collapsed
// panels. The collapsed toggle button shows a compact preview of the
// section's values (color swatch + name, weight chain, price, etc.) so the
// user can see what's filled in without expanding. Templated on the
// printer-status toolhead card pattern (uses getFilamentStyle/makeSwatchHtml
// for color rendering so multi-color gradients render correctly).
//
// Also handles two related UX behaviors:
//   - Auto-scroll: on `shown.bs.collapse`, scrolls the section toggle into
//     view at the top of the modal-body so the user sees the section they
//     just opened.
//   - Clears the summary span when expanded; re-renders when collapsed.
const _wizEscape = (s) => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const _wizSectionSummarizers = {
    'wiz-fil-physical-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const dia = v('wiz-fil-diameter');
        const den = v('wiz-fil-density');
        const wt = v('wiz-fil-weight');
        const empty = v('wiz-fil-empty_weight');
        const parts = [];
        if (dia) parts.push(`${dia}mm Ø`);
        if (den) parts.push(`${den} g/cm³`);
        if (wt) parts.push(`${wt}g net`);
        if (empty) parts.push(`${empty}g tare`);
        return parts.join(' · ');
    },
    'wiz-fil-color-panel': () => {
        const name = (document.getElementById('wiz-fil-color_name')?.value || '').trim();
        const hex0 = (document.getElementById('wiz-fil-color_hex_0')?.value || '').trim();
        const extras = Array.from(document.querySelectorAll('#wiz-fil-color-extra-container input[type="text"]'))
            .map(el => (el.value || '').trim()).filter(Boolean);
        const allHexes = [hex0, ...extras].filter(h => h && h !== '#FFFFFF');
        if (!name && allHexes.length === 0) return '';
        const dir = document.getElementById('wiz-fil-color-direction')?.value || 'longitudinal';
        const colorStr = allHexes.length > 0 ? allHexes.join(',') : (hex0 || '#FFFFFF');
        const swatch = window.makeSwatchHtml
            ? window.makeSwatchHtml(colorStr, dir, { size: 16, marginRight: 6 })
            : '';
        const label = name || (allHexes[0] || hex0 || '');
        const hexTag = allHexes.length > 1
            ? ` <span class="font-monospace text-info ms-2">${allHexes.length} colors</span>`
            : (allHexes[0] ? ` <span class="font-monospace text-muted ms-2">${allHexes[0]}</span>` : '');
        return `<span class="d-inline-flex align-items-center">${swatch}<span class="text-light">${_wizEscape(label)}</span>${hexTag}</span>`;
    },
    'wiz-fil-temps-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const nMin = v('wiz-fil-settings_extruder_temp'), nMax = v('wiz-fil-nozzle_temp_max');
        const bMin = v('wiz-fil-settings_bed_temp'),     bMax = v('wiz-fil-bed_temp_max');
        const parts = [];
        if (nMin || nMax) parts.push(`Nozzle ${nMin || '?'}–${nMax || '?'}°`);
        if (bMin || bMax) parts.push(`Bed ${bMin || '?'}–${bMax || '?'}°`);
        return parts.join(' · ');
    },
    'wiz-fil-extras-panel': () => {
        const inputs = document.querySelectorAll('#wiz-fil-dynamic-extra-fields input, #wiz-fil-dynamic-extra-fields select, #wiz-fil-dynamic-extra-fields textarea');
        let filled = 0;
        inputs.forEach(el => {
            if (el.type === 'checkbox' || el.type === 'radio') { if (el.checked) filled++; }
            else if ((el.value || '').toString().trim() !== '') filled++;
        });
        return filled === 0 ? '' : `${filled} field${filled === 1 ? '' : 's'} set`;
    },
    'wiz-spool-weight-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const empty = v('wiz-spool-empty_weight');
        const initial = v('wiz-spool-initial_weight');
        const remaining = v('wiz-spool-remaining');
        const used = v('wiz-spool-used');
        const parts = [];
        if (remaining) parts.push(`<span class="text-success">${remaining}g left</span>`);
        if (used && used !== '0') parts.push(`${used}g used`);
        if (initial) parts.push(`net ${initial}g`);
        if (empty) parts.push(`tare ${empty}g`);
        return parts.join(' · ');
    },
    'wiz-spool-metadata-panel': () => {
        const v = (id) => (document.getElementById(id)?.value || '').trim();
        const price = v('wiz-spool-price');
        const comment = v('wiz-spool-comment');
        const url = v('wiz-spool-purchase_url');
        const archived = document.getElementById('wiz-spool-archived')?.checked;
        const parts = [];
        if (price) parts.push(`$${price}`);
        if (archived) parts.push('<span class="text-warning">archived</span>');
        if (url) parts.push('<span class="text-info">🔗 link</span>');
        if (comment) parts.push(`💬 ${_wizEscape(comment.slice(0, 28))}${comment.length > 28 ? '…' : ''}`);
        return parts.join(' · ');
    },
    'wiz-spool-extras-panel': () => {
        const inputs = document.querySelectorAll('#wiz-spool-dynamic-extra-fields input, #wiz-spool-dynamic-extra-fields select, #wiz-spool-dynamic-extra-fields textarea');
        let filled = 0;
        inputs.forEach(el => {
            if (el.type === 'checkbox' || el.type === 'radio') { if (el.checked) filled++; }
            else if ((el.value || '').toString().trim() !== '') filled++;
        });
        return filled === 0 ? '' : `${filled} field${filled === 1 ? '' : 's'} set`;
    },
    // Physical Specs is always-open; no summary needed.
};

window.wizardRefreshSectionSummary = (panelId) => {
    const gen = _wizSectionSummarizers[panelId];
    if (!gen) return;
    const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${panelId}"]`);
    if (!btn) return;
    const summarySpan = btn.querySelector('.fcc-wiz-section-summary');
    if (!summarySpan) return;
    // Chips render regardless of expanded state — they're a glance-able
    // summary of the section's values, so they should also be visible
    // while the user is editing (and confirm the values they just typed).
    const html = gen();
    summarySpan.innerHTML = html || '';
    summarySpan.style.display = html ? '' : 'none';
};

window.wizardRefreshAllSectionSummaries = () => {
    Object.keys(_wizSectionSummarizers).forEach(id => window.wizardRefreshSectionSummary(id));
};

// One-shot wiring at script load: every collapsible panel gets listeners
// for show/hide so summaries refresh and the modal scrolls to the toggle
// the user just clicked. Idempotent — runs once.
(function() {
    if (window._wizCollapseWired) return;
    window._wizCollapseWired = true;
    const panelIds = Object.keys(_wizSectionSummarizers);
    panelIds.forEach(id => {
        const panel = document.getElementById(id);
        if (!panel) return;
        // Bootstrap's default Enter/Space-clicks-focused-button behavior
        // doesn't reliably fire for these toggles, so we synthesize a click
        // on keydown. BUT the browser sometimes ALSO dispatches a native
        // click on keyup (Space) or independently (Enter), causing a
        // expand+collapse double-fire — user has to press twice to land
        // on "expanded". Fix: track the last keyboard-induced click and
        // suppress any native click that arrives within 300ms.
        const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
        if (btn) {
            let lastKbAt = 0;
            // Group 10.1 SC round-5: toggle Bootstrap's Collapse instance
            // directly instead of synthesizing btn.click(). The click()
            // path goes through Bootstrap's data-bs-toggle handler — and
            // the browser ALSO dispatches a native click on keyup (Space)
            // or shortly after (Enter), causing intermittent double-fire
            // even with the round-4 debounce. Going through the API
            // directly bypasses the click handler entirely; even if a
            // native click leaks through, Bootstrap's own _isTransitioning
            // lock blocks the redundant toggle.
            btn.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
                    e.preventDefault();
                    e.stopPropagation();
                    const now = Date.now();
                    if (now - lastKbAt < 400) return;
                    lastKbAt = now;
                    if (window.bootstrap && window.bootstrap.Collapse) {
                        bootstrap.Collapse.getOrCreateInstance(panel, { toggle: false }).toggle();
                    }
                }
            });
            // Backstop: drop any native click that arrives within 400ms of a
            // keyboard toggle. Covers the (rare) case where the browser's
            // synthesized click still reaches Bootstrap despite preventDefault.
            btn.addEventListener('click', (e) => {
                if (e.isTrusted && (Date.now() - lastKbAt < 400)) {
                    e.stopImmediatePropagation();
                    e.preventDefault();
                }
            }, true);
        }
        panel.addEventListener('shown.bs.collapse', (e) => {
            if (e.target !== panel) return;
            window.wizardRefreshSectionSummary(id);
            // Suppress when wizardApplyCollapseDefaults is batch-applying —
            // it sets state synchronously and doesn't need the scroll.
            if (window._wizSuppressScroll) return;
            // Smart-scroll: only scroll if the expansion pushed the panel's
            // bottom below the visible modal-body viewport. If the section
            // already fits entirely on screen, leave the user's scroll
            // position alone (per user feedback — only scroll if the
            // expansion would otherwise be invisible).
            const modalBody = document.querySelector('#wizardModal .modal-body');
            const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
            if (!modalBody || !btn) return;
            const modalRect = modalBody.getBoundingClientRect();
            const panelRect = panel.getBoundingClientRect();
            // Bottom-of-panel below bottom-of-modal? Or top-of-toggle
            // already above top-of-modal? Either way, scroll the toggle
            // to the top so the panel becomes fully visible.
            const overflowsBottom = panelRect.bottom > modalRect.bottom - 4;
            const togglesOffTop = btn.getBoundingClientRect().top < modalRect.top + 4;
            if (overflowsBottom || togglesOffTop) {
                btn.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        panel.addEventListener('hidden.bs.collapse', (e) => {
            if (e.target !== panel) return;
            window.wizardRefreshSectionSummary(id);
        });
    });
    // Refresh all CLOSED-section summaries on any input/change inside the
    // modal so collapsed sections stay accurate as the user types in
    // expanded ones (then re-collapses them).
    const wizEl = document.getElementById('wizardModal');
    if (wizEl) {
        const refreshAll = () => {
            panelIds.forEach(id => window.wizardRefreshSectionSummary(id));
        };
        wizEl.addEventListener('input', refreshAll);
        wizEl.addEventListener('change', refreshAll);
    }
})();

// Group 10.1 (Session C polish) — Original Color routing. The
// `original_color` extra field is logically a Color field, not a Custom
// Filament Attribute. wizardFetchExtraFields normally renders it into
// `#wiz-fil-dynamic-extra-fields`; this helper moves it into the Color
// panel's dedicated slot if present. Called from wizardFetchExtraFields
// after the dynamic-extras grid is built.
window.wizardRelocateOriginalColorField = () => {
    const slot = document.getElementById('wiz-fil-original-color-slot');
    if (!slot) return;
    // Clear any prior render: wizardFetchExtraFields runs on every wizard
    // open AND on schema refresh, so without this the slot accumulated a
    // new copy each time (original_color appeared 2x, 3x, ... after
    // multiple opens in the same page session).
    slot.innerHTML = '';
    const extrasGrid = document.getElementById('wiz-fil-dynamic-extra-fields');
    if (!extrasGrid) return;
    const col = extrasGrid.querySelector('[data-extra-key="original_color"]');
    if (col && col.parentElement === extrasGrid) {
        slot.appendChild(col);
        col.className = 'col-md-12';
    }
};

// Group 10.1 (Session C polish) — TPU-only shore_hardness. Hide the
// shore_hardness extra unless the material is TPU-family. Wires a listener
// on the material input + an initial sync, and is re-run after every
// extras render. Material list as of 2026-05: TPU, TPE, TPC are the
// common shore-hardness-relevant flexibles.
const _TPU_FAMILY = ['TPU', 'TPE', 'TPC', 'FLEX'];
window.wizardApplyShoreHardnessGate = () => {
    const matEl = document.getElementById('wiz-fil-material');
    const target = document.querySelector('[data-extra-key="shore_hardness"]');
    if (!target) return;
    const mat = (matEl?.value || '').trim().toUpperCase();
    const isTpu = _TPU_FAMILY.some(prefix => mat.startsWith(prefix));
    target.style.display = isTpu ? '' : 'none';
};

(function() {
    if (window._wizTpuGateWired) return;
    window._wizTpuGateWired = true;
    const matEl = document.getElementById('wiz-fil-material');
    if (matEl) {
        ['input', 'change', 'blur'].forEach(evt => {
            matEl.addEventListener(evt, () => window.wizardApplyShoreHardnessGate());
        });
    }
})();

// Group 10.1 (Session C polish) — Expand / collapse all wizard sections.
// Bound to Shift+E / Shift+C while the wizard modal is open. Registered
// via the shortcuts registry so it appears in the global `?` overlay.
window.wizardExpandAllSections = () => {
    Object.keys(_wizSectionSummarizers).forEach(id => {
        const el = document.getElementById(id);
        if (!el || !window.bootstrap || !window.bootstrap.Collapse) return;
        bootstrap.Collapse.getOrCreateInstance(el, { toggle: false }).show();
    });
};
window.wizardCollapseAllSections = () => {
    Object.keys(_wizSectionSummarizers).forEach(id => {
        const el = document.getElementById(id);
        if (!el || !window.bootstrap || !window.bootstrap.Collapse) return;
        bootstrap.Collapse.getOrCreateInstance(el, { toggle: false }).hide();
    });
};

(function() {
    if (window._wizExpandShortcutWired) return;
    window._wizExpandShortcutWired = true;
    const wizEl = document.getElementById('wizardModal');
    if (!wizEl) return;
    // Modal-scoped capture listener: only fires when the wizard is shown.
    wizEl.addEventListener('keydown', (e) => {
        if (!wizEl.classList.contains('show')) return;
        // Skip if the user is typing into an input/textarea/select — Shift+E
        // is a perfectly valid character keystroke in those contexts.
        const tag = (document.activeElement?.tagName || '').toUpperCase();
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
        if (!e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
        if (e.key === 'E' || e.key === 'e') {
            e.preventDefault();
            window.wizardExpandAllSections();
        } else if (e.key === 'C' || e.key === 'c') {
            e.preventDefault();
            window.wizardCollapseAllSections();
        }
    });
    // Register with the shortcuts registry so the `?` overlay shows them.
    // The registry script (shortcuts_registry.js) is loaded AFTER this
    // wizard module in scripts.html, so window.registerShortcut may not
    // exist yet. Poll briefly until it shows up.
    const _registerWizardShortcuts = () => {
        if (typeof window.registerShortcut !== 'function') return false;
        window.registerShortcut({
            id: 'wizard-expand-all',
            scope: 'Wizard',
            keys: ['Shift', 'E'],
            description: 'Expand all collapsed sections in the wizard',
        });
        window.registerShortcut({
            id: 'wizard-collapse-all',
            scope: 'Wizard',
            keys: ['Shift', 'C'],
            description: 'Collapse all optional sections in the wizard',
        });
        return true;
    };
    if (!_registerWizardShortcuts()) {
        const start = Date.now();
        const tick = () => {
            if (_registerWizardShortcuts()) return;
            if (Date.now() - start > 5000) return;  // give up after 5s
            setTimeout(tick, 100);
        };
        setTimeout(tick, 100);
    }
})();

// Group 10.4 — populates the spool's purchase_url input with the smart-fallback
// pattern: if the spool already has its own URL, fill the input. If not, leave
// it empty and surface the filament-inherited URL as ghost placeholder text so
// the user can see what details modal will fall back to without unintentionally
// upgrading the inherited link to a spool-level override.
const wizardApplyPurchaseLinkFallback = (spoolUrl, filamentUrl) => {
    const el = document.getElementById('wiz-spool-purchase_url');
    if (!el) return;
    const stripQuotes = (s) => typeof s === 'string' ? s.replace(/^"|"$/g, '') : '';
    const sUrl = stripQuotes(spoolUrl).trim();
    const fUrl = stripQuotes(filamentUrl).trim();
    if (sUrl) {
        el.value = sUrl;
        el.placeholder = 'https://...';
    } else {
        el.value = '';
        if (fUrl) {
            const truncated = fUrl.length > 40 ? fUrl.slice(0, 37) + '…' : fUrl;
            el.placeholder = `${truncated} (inherited from filament)`;
        } else {
            el.placeholder = 'https://...';
        }
    }
};

// L351: same smart-fallback pattern as purchase_url, for the per-spool
// product_url input. Prefill the spool's OWN product_url; if it has none but
// the filament does, advertise the filament URL as ghost placeholder so saving
// without typing leaves the spool override blank (the details modal then falls
// back to the filament's value — inv_details.js:218).
const wizardApplyProductLinkFallback = (spoolUrl, filamentUrl) => {
    const el = document.getElementById('wiz-spool-product_url');
    if (!el) return;
    const stripQuotes = (s) => typeof s === 'string' ? s.replace(/^"|"$/g, '') : '';
    const sUrl = stripQuotes(spoolUrl).trim();
    const fUrl = stripQuotes(filamentUrl).trim();
    if (sUrl) {
        el.value = sUrl;
        el.placeholder = 'https://...';
    } else {
        el.value = '';
        if (fUrl) {
            const truncated = fUrl.length > 40 ? fUrl.slice(0, 37) + '…' : fUrl;
            el.placeholder = `${truncated} (inherited from filament)`;
        } else {
            el.placeholder = 'https://...';
        }
    }
};

// L349: cascade the filament's native price down to a new / cloned / edited
// spool that has none of its own (mirrors the empty-weight cascade). BLANK-GATED
// — only fills when the spool price field is empty AND the spool has no own
// price, so it NEVER overwrites an explicit spool price. `ownPrice` is the
// spool's own price (null for a brand-new spool); `filamentPrice` is the
// filament-level fallback.
window.wizardPrefillSpoolPrice = (ownPrice, filamentPrice) => {
    const el = document.getElementById('wiz-spool-price');
    if (!el) return;
    if (el.value !== '' && el.value != null) return;  // never clobber a typed/own value
    const v = (ownPrice != null) ? ownPrice : filamentPrice;
    if (v != null) el.value = v;
};

const wizardReset = () => {
    wizardState.mode = 'manual';
    wizardState.selectedFilamentId = null;
    wizardState.externalMetaData = null;
    wizardState.lockedAfterSuccess = false;

    // 17.3 follow-up: clear stale queue-label chips from the prior
    // success so a fresh wizard open doesn't show last-run's spool IDs.
    const _actionRow = document.getElementById('wiz-postcreate-actions');
    if (_actionRow) _actionRow.innerHTML = '';
    // Note: returnToSpoolId is NOT cleared here — it persists across reset so that
    // after a clone/edit completes, the original spool detail modal can re-open.

    // Clear Form. `input[type="url"]` was missing here, which caused
    // wiz-spool-purchase_url to bleed between wizard sessions (Group 10.4).
    document.querySelectorAll('#wizardModal input[type="text"], #wizardModal input[type="number"], #wizardModal input[type="url"]').forEach(i => i.value = '');
    document.querySelectorAll('#wizardModal input[type="checkbox"]').forEach(i => i.checked = false);
    // Reset the spool purchase_url placeholder to its static default — clone
    // and edit flows mutate it to advertise the inherited filament URL, and
    // we don't want that to bleed into the next session either.
    const purchUrlReset = document.getElementById('wiz-spool-purchase_url');
    if (purchUrlReset) purchUrlReset.placeholder = 'https://...';
    const productUrlReset = document.getElementById('wiz-spool-product_url');
    if (productUrlReset) productUrlReset.placeholder = 'https://...';
    document.querySelectorAll('#wizardModal select').forEach(i => i.selectedIndex = 0);
    if (window.wizardClearSpoolEmptyWeightBadge) window.wizardClearSpoolEmptyWeightBadge();

    // Reset Color UI
    document.getElementById('wiz-fil-color-extra-container').innerHTML = '';
    document.getElementById('wiz-fil-color_hex_0').value = '#FFFFFF';
    document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = '#FFFFFF';
    const dirEl = document.getElementById('wiz-fil-color-direction');
    if (dirEl) dirEl.value = 'longitudinal';
    const dirWrap = document.getElementById('wiz-fil-color-direction-wrapper');
    if (dirWrap) dirWrap.style.display = 'none';

    document.getElementById('wiz-spool-qty').value = 1;
    // Restore HTML factory defaults that the type=number bulk-wipe above
    // cleared. Without this, the Physical Specs chip has nothing to show
    // on a fresh wizard open even though the HTML <input value="..."> would
    // normally populate them. (Group 10.1 SC round-3 fix.)
    document.getElementById('wiz-fil-diameter').value = '1.75';
    document.getElementById('wiz-fil-density').value = '1.24';

    // Group 10.1 SC round-5: reset collapse-panel classes to HTML defaults
    // so prior-session expand/collapse state doesn't bleed into the new
    // modal session. Previously, pressing Shift+E to expand all sections
    // then closing the wizard left the .show classes on those panels;
    // re-opening flashed them visible until wizardApplyCollapseDefaults
    // ran (which is async, after Promise.all of fetches — ~500ms+ later).
    const _wizOptionalPanels = [
        'wiz-fil-color-panel', 'wiz-fil-physical-panel', 'wiz-fil-temps-panel',
        'wiz-fil-extras-panel', 'wiz-spool-weight-panel',
        'wiz-spool-metadata-panel', 'wiz-spool-extras-panel',
    ];
    _wizOptionalPanels.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.remove('show', 'collapsing');
            el.style.height = '';
            const btn = document.querySelector(`button.fcc-wiz-section-toggle[data-bs-target="#${id}"]`);
            if (btn) btn.setAttribute('aria-expanded', 'false');
        }
    });

    if (window.wizardResetSpoolRows) window.wizardResetSpoolRows();
    if (window.wizardClearFilamentMismatchPanel) window.wizardClearFilamentMismatchPanel();
    if (window.wizardClearDuplicatePicker) window.wizardClearDuplicatePicker();

    document.getElementById('wiz-spool-used').value = 0;
    
    wizardState.original_used_weight = 0;
    const usageContainer = document.getElementById('container-wiz-spool-recent-usage');
    if (usageContainer) usageContainer.style.display = 'none';
    const recentInput = document.getElementById('wiz-spool-recent-usage');
    if (recentInput) recentInput.value = '';

    // Reset Edit State button styles
    const submitBtn = document.getElementById('btn-wiz-submit');
    if (submitBtn) {
        submitBtn.innerText = "CREATE INVENTORY";
        submitBtn.classList.remove('btn-primary');
        submitBtn.classList.add('btn-success');
    }
    const step1 = document.getElementById('step-1-material');
    if (step1) step1.style.display = 'block';
    const qtyBox = document.getElementById('wiz-spool-qty');
    if (qtyBox && qtyBox.parentElement) qtyBox.parentElement.style.display = 'flex';

    // Reset View
    wizardSelectType('manual');
    document.getElementById('wiz-status-msg').innerText = "";
    // Reset vendor combobox (visible search field + hidden id).
    const vSearch = document.getElementById('wiz-fil-vendor-search');
    if (vSearch) vSearch.value = '';
    const vSel = document.getElementById('wiz-fil-vendor-sel');
    if (vSel) {
        vSel.value = '';
        // Non-bubbling so the dirty-flag tracker doesn't pick up this
        // programmatic reset (matches wizardComboboxSet's policy).
        vSel.dispatchEvent(new Event('change', { bubbles: false }));
    }
    // Reset location combobox too — its hidden id field is cleared by the select
    // loop above but the visible search text needs its own clear.
    const lSearch = document.getElementById('wiz-spool-location-search');
    if (lSearch) lSearch.value = '';
    wizardSetContextLabel();
    wizardState.isDirty = false;
};

// Paints three coordinated chips: an action word next to the wizard title plus
// bootstrap-badge Spool / Filament chips (also mirrored into the Step 2 and
// Step 3 section headers). Call with `{}` or no arg to clear.
//   wizardSetContextLabel({ action: 'Editing', spoolId: 42, filamentId: 7 })
//   wizardSetContextLabel({ action: 'New Spool for', filamentId: 7 })
//   wizardSetContextLabel()  // clears everything
window.wizardSetContextLabel = (ctx) => {
    ctx = ctx || {};
    const { action, spoolId, filamentId } = ctx;
    const title = document.getElementById('wiz-context-label');
    const step2Ctx = document.getElementById('wiz-step2-fil-context');
    const step2Badge = document.getElementById('wiz-step2-fil-badge');
    const step3Ctx = document.getElementById('wiz-step3-spl-context');
    const step3Badge = document.getElementById('wiz-step3-spl-badge');

    if (title) {
        const parts = [];
        if (action) {
            parts.push(`<span class="fw-semibold text-light" style="font-size: 0.9rem;">${action}</span>`);
        }
        if (spoolId != null && spoolId !== '') {
            parts.push(`<span class="badge text-bg-info" style="font-size: 0.85rem;">🧵 Spool #${spoolId}</span>`);
        }
        if (filamentId != null && filamentId !== '') {
            parts.push(`<span class="badge text-bg-warning text-dark" style="font-size: 0.85rem;">🧬 Filament #${filamentId}</span>`);
        }
        title.innerHTML = parts.join('');
    }

    // Bootstrap's `d-inline-flex` carries `!important`, so inline display:none
    // would lose to it. Toggle between `d-none` and `d-inline-flex` classes.
    if (step2Ctx && step2Badge) {
        if (filamentId != null && filamentId !== '') {
            step2Badge.textContent = `🧬 Filament #${filamentId}`;
            step2Ctx.classList.remove('d-none');
            step2Ctx.classList.add('d-inline-flex');
        } else {
            step2Badge.textContent = '';
            step2Ctx.classList.remove('d-inline-flex');
            step2Ctx.classList.add('d-none');
        }
    }

    if (step3Ctx && step3Badge) {
        if (spoolId != null && spoolId !== '') {
            step3Badge.textContent = `🧵 Spool #${spoolId}`;
            step3Ctx.classList.remove('d-none');
            step3Ctx.classList.add('d-inline-flex');
        } else {
            step3Badge.textContent = '';
            step3Ctx.classList.remove('d-inline-flex');
            step3Ctx.classList.add('d-none');
        }
    }
};

// Wires a text-input + hidden-value + dropdown triple into a keyboard-searchable
// combobox. Mirrors the material-autocomplete pattern (focus/blur/filter/keydown)
// so users get a compact, type-to-filter list with arrow + Enter nav instead of a
// native <select> that takes over the screen. `items` is [{value, label}].
// Re-binding an already-bound input replaces prior listeners via a reset flag.
window.wizardBindCombobox = ({ searchId, hiddenId, dropdownId, items, placeholder }) => {
    const search = document.getElementById(searchId);
    const hidden = document.getElementById(hiddenId);
    const dropdown = document.getElementById(dropdownId);
    if (!search || !hidden || !dropdown) return;

    // Replace the node with a clone to drop any previously-attached listeners,
    // then re-grab the fresh reference. This lets wizardBindCombobox be called
    // again (e.g. after wizardFetchVendors refreshes the list).
    const freshSearch = search.cloneNode(true);
    search.parentNode.replaceChild(freshSearch, search);

    if (placeholder) freshSearch.placeholder = placeholder;

    const escape = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));

    // Group 10.2/10.10: on focus (re-entry into an already-populated combobox)
    // render the FULL list and highlight the current selection — without this,
    // the typed query (which is the previously-selected label) filters the
    // list down to one item and the user has to delete text to see anything
    // else. When the user actually types, the input handler swaps to filtered
    // render. `forceAll=true` is passed by focus/keydown-when-closed paths.
    const render = (forceAll = false) => {
        const qs = forceAll ? '' : freshSearch.value.toLowerCase();
        const filtered = qs
            ? items.filter(it => (it.label || '').toLowerCase().includes(qs))
            : items;
        const currentVal = hidden.value;
        dropdown.innerHTML = filtered.map(it => {
            const selectedCls = (forceAll && currentVal && String(it.value) === String(currentVal))
                ? ' active bg-primary' : '';
            return `<div class="dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option${selectedCls}"
                  data-value="${escape(it.value)}"
                  data-label="${escape(it.label)}">${escape(it.label)}</div>`;
        }).join('');
        dropdown.querySelectorAll('.autocomplete-option').forEach(opt => {
            opt.addEventListener('mousedown', (e) => {
                e.preventDefault();
                freshSearch.value = opt.dataset.label;
                hidden.value = opt.dataset.value;
                dropdown.style.display = 'none';
                // Mirror native change so the wizard's dirty flag listener fires.
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });
        // If the currently-selected row is rendered, scroll it into view so the
        // user can see (and hit Enter to confirm) without scrolling manually.
        if (forceAll && currentVal) {
            const sel = dropdown.querySelector('.autocomplete-option.active');
            if (sel) {
                const dr = dropdown.getBoundingClientRect();
                const sr = sel.getBoundingClientRect();
                if (sr.bottom > dr.bottom) dropdown.scrollTop += (sr.bottom - dr.bottom);
                else if (sr.top < dr.top) dropdown.scrollTop -= (dr.top - sr.top);
            }
        }
    };

    freshSearch.addEventListener('focus', () => { render(true); dropdown.style.display = 'block'; });
    // Group 10.2/10.10: also handle click-while-already-focused. After
    // picking an option, mousedown.preventDefault keeps focus on the input,
    // so a subsequent click never fires `focus` again. Without this, the
    // user has to blur and re-focus to see the full list. Only re-opens the
    // dropdown when it's hidden — a click during active filtering shouldn't
    // wipe the typed query.
    freshSearch.addEventListener('click', () => {
        if (dropdown.style.display === 'none') {
            render(true);
            dropdown.style.display = 'block';
        }
    });
    freshSearch.addEventListener('blur', () => {
        // Short delay so mousedown on a list item can fire before we tear it down.
        setTimeout(() => { dropdown.style.display = 'none'; }, 150);
    });
    freshSearch.addEventListener('input', () => {
        render();
        // If typed text exactly matches a label, capture its value; otherwise clear
        // so partial typing doesn't leak a stale id into the form payload.
        const typed = freshSearch.value.trim().toLowerCase();
        const exact = items.find(it => (it.label || '').toLowerCase() === typed);
        hidden.value = exact ? exact.value : '';
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
        dropdown.style.display = 'block';
    });
    freshSearch.addEventListener('keydown', (e) => {
        if (dropdown.style.display === 'none') {
            if (e.key === 'ArrowDown') { render(true); dropdown.style.display = 'block'; }
            return;
        }
        const visible = Array.from(dropdown.children);
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!visible.length) return;
            e.preventDefault();
            let idx = visible.findIndex(el => el.classList.contains('active'));
            visible.forEach(el => el.classList.remove('active', 'bg-primary'));
            idx = e.key === 'ArrowDown'
                ? (idx + 1 >= visible.length ? 0 : idx + 1)
                : (idx - 1 < 0 ? visible.length - 1 : idx - 1);
            const next = visible[idx];
            next.classList.add('active', 'bg-primary');
            const dr = dropdown.getBoundingClientRect();
            const ir = next.getBoundingClientRect();
            if (ir.bottom > dr.bottom) dropdown.scrollTop += (ir.bottom - dr.bottom);
            else if (ir.top < dr.top) dropdown.scrollTop -= (dr.top - ir.top);
            return;
        }
        if (e.key === 'Enter') {
            e.preventDefault();
            const pick = visible.find(el => el.classList.contains('active')) || visible[0];
            if (pick) {
                freshSearch.value = pick.dataset.label;
                hidden.value = pick.dataset.value;
                dropdown.style.display = 'none';
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
            return;
        }
        if (e.key === 'Escape') {
            // Swallow Escape when the dropdown is open so it closes the
            // dropdown ONLY — without preventDefault + stopPropagation the
            // Escape bubbles to the wizard modal and Bootstrap dismisses it.
            // Matches inv_details.js combobox pattern.
            e.preventDefault();
            e.stopPropagation();
            dropdown.style.display = 'none';
        }
    });
};

// Sets the combobox's visible text + hidden id from a {value, label} pair.
// Pass null/undefined to clear. Used by edit/clone auto-fill paths.
window.wizardComboboxSet = (searchId, hiddenId, value, label) => {
    const s = document.getElementById(searchId);
    const h = document.getElementById(hiddenId);
    if (s) s.value = label || '';
    if (h) {
        h.value = value == null ? '' : value;
        // Fire a NON-BUBBLING change event so direct listeners (the vendor
        // edit-button visibility hook installed in wizardFetchVendors)
        // refresh — but the wizard-level dirty-flag tracker (which listens
        // on the wizardModal wrapper) does NOT mistake this programmatic
        // write for user input. Clone / edit / external-import auto-fill
        // all funnel through this function and the dirty-flag spuriously
        // flipping to true was making Cancel pop the unsaved-changes Swal.
        h.dispatchEvent(new Event('change', { bubbles: false }));
    }
};

window.wizardAutoUpdateDensity = () => {
    const matInput = document.getElementById('wiz-fil-material');
    const densInput = document.getElementById('wiz-fil-density');

    // Only auto-update if the user is typing a new material and hasn't manually overridden it, or if it's basically the default
    const val = (matInput.value || '').toUpperCase();

    let density = 1.24; // Default PLA
    if (val.includes('PETG') || val.includes('PET')) density = 1.27;
    else if (val.includes('ABS')) density = 1.04;
    else if (val.includes('ASA')) density = 1.07;
    else if (val.includes('TPU') || val.includes('TPE') || val.includes('FLEX')) density = 1.21;
    else if (val.includes('NYLON') || val.includes('PA')) density = 1.14;
    else if (val.includes('PC') || val.includes('POLYCARBONATE')) density = 1.20;
    else if (val.includes('HIPS')) density = 1.04;
    else if (val.includes('PVA')) density = 1.19;
    else if (val.includes('PVB')) density = 1.08;

    densInput.value = density.toFixed(2);
};

window.wizardSelectType = (mode, skipSearch = false) => {
    wizardState.mode = mode;

    // Update active button styling
    document.querySelectorAll('.type-selector').forEach(el => el.classList.remove('wiz-active-card'));
    document.getElementById(`btn-type-${mode}`).classList.add('wiz-active-card');

    // Show/Hide Dynamic Areas
    const dynamicArea = document.getElementById('material-dynamic-area');
    const areaExt = document.getElementById('area-existing');
    const areaWeb = document.getElementById('area-external');
    const filConfig = document.getElementById('step-2-filament');
    const spoolConfig = document.getElementById('step-3-spool');

    spoolConfig.style.opacity = '1';
    spoolConfig.style.display = 'block';

    if (mode === 'manual') {
        dynamicArea.style.display = 'none';
        filConfig.style.display = 'block';
        document.getElementById('btn-wiz-submit').disabled = false;
    } else {
        dynamicArea.style.display = 'block';
        areaExt.style.display = (mode === 'existing') ? 'block' : 'none';
        areaWeb.style.display = (mode === 'external') ? 'block' : 'none';

        if (mode === 'existing') {
            filConfig.style.display = 'none';
            if (!skipSearch) wizardSearchExisting();
        } else {
            filConfig.style.display = 'block';
        }

        wizardValidateSubmit();
    }
};

window.wizardValidateSubmit = () => {
    const btn = document.getElementById('btn-wiz-submit');
    if (wizardState.lockedAfterSuccess) {
        btn.disabled = true;
        return;
    }
    if (wizardState.mode === 'existing' && !wizardState.selectedFilamentId) {
        btn.disabled = true;
    } else {
        btn.disabled = false;
    }
};

window.wizardCalcUsedWeight = () => {
    const scaleWt = parseFloat(document.getElementById('wiz-spool-scale').value);
    if (isNaN(scaleWt)) return;

    let emptyWt = parseFloat(document.getElementById('wiz-spool-empty_weight').value);
    if (isNaN(emptyWt)) {
        emptyWt = parseFloat(document.getElementById('wiz-fil-empty_weight').value) || 0;
    }

    let netWt = parseFloat(document.getElementById('wiz-spool-initial_weight').value);
    if (isNaN(netWt)) {
        netWt = parseFloat(document.getElementById('wiz-fil-weight').value);
        if (isNaN(netWt)) netWt = 1000; // standard assumption if completely hidden
    }

    let used = (netWt + emptyWt) - scaleWt;
    if (used < 0) used = 0;
    if (used > netWt) used = netWt; // [ALEX FIX] Spoolman crashes if used > initial_weight

    // buglist L51: 1-decimal (PRECISE tier) instead of .toFixed(0). The field
    // value is what gets PERSISTED to Spoolman on submit, so rounding to a
    // whole gram here silently lost the sub-gram tare component AND made `used`
    // (shown raw on edit-load) disagree with the rounded `remaining`. Deriving
    // both from the same exact `used` and trimming to 0.1g keeps them
    // reconciled (used + remaining == netWt).
    document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(used);
    document.getElementById('wiz-spool-remaining').value = window.fmtGramsPrecise(netWt - used);
};

window.wizardCalcUsedFromRemaining = () => {
    const remaining = parseFloat(document.getElementById('wiz-spool-remaining').value);
    if (isNaN(remaining)) return;
    
    let netWt = parseFloat(document.getElementById('wiz-spool-initial_weight').value);
    if (isNaN(netWt)) {
        netWt = parseFloat(document.getElementById('wiz-fil-weight').value) || 1000;
    }
    
    let used = netWt - remaining;
    if (used < 0) used = 0;
    if (used > netWt) used = netWt;

    document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(used);
    document.getElementById('wiz-spool-scale').value = '';
};

window.wizardCalcRemainingFromUsed = () => {
    const used = parseFloat(document.getElementById('wiz-spool-used').value);
    if (isNaN(used)) return;
    
    let netWt = parseFloat(document.getElementById('wiz-spool-initial_weight').value);
    if (isNaN(netWt)) {
        netWt = parseFloat(document.getElementById('wiz-fil-weight').value) || 1000;
    }
    
    let remaining = netWt - used;
    if (remaining < 0) remaining = 0;

    document.getElementById('wiz-spool-remaining').value = window.fmtGramsPrecise(remaining);
    document.getElementById('wiz-spool-scale').value = '';
};

window.wizardCalcFromRecentUsage = () => {
    let recent = parseFloat(document.getElementById('wiz-spool-recent-usage').value);
    if (isNaN(recent)) recent = 0;
    
    let baseUsed = wizardState.original_used_weight || 0;
    let newTotal = baseUsed + recent;
    if (newTotal < 0) newTotal = 0;

    document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(newTotal);
    window.wizardCalcRemainingFromUsed();
};

window.wizardClearScaleWeight = () => {
    document.getElementById('wiz-spool-scale').value = '';
    window.wizardCalcRemainingFromUsed();
};

// --- DATA FETCHERS ---
const wizardFetchMaterials = () => {
    return fetch('/api/filaments')
        .then(r => r.json())
        .then(d => {
            if (d.success && d.filaments) {
                // Cache the full filament list for the duplicate-detection check in
                // the per-spool Prusament scan flow (see findFilamentMatches).
                wizardState.allFilaments = d.filaments;
                const materials = [...new Set(d.filaments.map(f => f.material).filter(Boolean))].sort(function (a, b) {
                    return a.toLowerCase().localeCompare(b.toLowerCase());
                });
                wizardState.materials = materials;
                const dropdown = document.getElementById('dropdown-material');
                if (dropdown) {
                    dropdown.innerHTML = materials.map(m => 
                        `<div class="dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option" 
                              onmousedown="window.wizardMaterialSelect(event, '${m.replace(/'/g, "\\'")}')">${m}</div>`
                    ).join('');
                }
            }
        });
};

window.wizardMaterialFocus = () => {
    const dropdown = document.getElementById('dropdown-material');
    if (dropdown) {
        dropdown.style.display = 'block';
        if (window.wizardMaterialFilter) window.wizardMaterialFilter();
    }
};

window.wizardMaterialBlur = () => {
    setTimeout(() => {
        const dropdown = document.getElementById('dropdown-material');
        if (dropdown) dropdown.style.display = 'none';
    }, 150);
};

window.wizardMaterialFilter = () => {
    const input = document.getElementById('wiz-fil-material');
    const dropdown = document.getElementById('dropdown-material');
    if (!input || !dropdown) return;
    const qs = input.value.toLowerCase();
    
    let hasVisible = false;
    Array.from(dropdown.children).forEach(option => {
        option.classList.remove('active', 'bg-primary');
        if (option.innerText.toLowerCase().includes(qs)) {
            option.style.display = 'block';
            hasVisible = true;
        } else {
            option.style.display = 'none';
        }
    });
    dropdown.style.display = hasVisible ? 'block' : 'none';
};

window.wizardMaterialKeydown = (event) => {
    const input = document.getElementById('wiz-fil-material');
    const dropdown = document.getElementById('dropdown-material');
    if (!input || !dropdown || dropdown.style.display === 'none') {
        if (event.key === 'Enter') event.preventDefault();
        return;
    }

    // Escape closes the suggestion dropdown only — without stopPropagation it
    // bubbles to the wizard modal and Bootstrap dismisses the whole wizard,
    // discarding in-progress data. Matches inv_details.js combobox pattern.
    if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        dropdown.style.display = 'none';
        return;
    }

    let visibleOptions = Array.from(dropdown.children).filter(el => el.style.display !== 'none');

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!visibleOptions.length) return;
        event.preventDefault();

        let currentIndex = visibleOptions.findIndex(el => el.classList.contains('active'));
        visibleOptions.forEach(el => el.classList.remove('active', 'bg-primary'));

        if (event.key === 'ArrowDown') {
            currentIndex = currentIndex + 1 >= visibleOptions.length ? 0 : currentIndex + 1;
        } else {
            currentIndex = currentIndex - 1 < 0 ? visibleOptions.length - 1 : currentIndex - 1;
        }

        const nextActive = visibleOptions[currentIndex];
        nextActive.classList.add('active', 'bg-primary');

        const dropRect = dropdown.getBoundingClientRect();
        const itemRect = nextActive.getBoundingClientRect();
        if (itemRect.bottom > dropRect.bottom) {
            dropdown.scrollTop += (itemRect.bottom - dropRect.bottom);
        } else if (itemRect.top < dropRect.top) {
            dropdown.scrollTop -= (dropRect.top - itemRect.top);
        }
        return;
    }

    if (event.key === 'Enter') {
        event.preventDefault();
        if (visibleOptions.length > 0) {
            let selected = visibleOptions.find(el => el.classList.contains('active')) || visibleOptions[0];
            window.wizardMaterialSelect(event, selected.innerText);
        }
    }
};

window.wizardMaterialSelect = (event, value) => {
    event.preventDefault();
    const input = document.getElementById('wiz-fil-material');
    if (input) {
        input.value = value;
        input.focus();
        if (window.wizardAutoUpdateDensity) window.wizardAutoUpdateDensity();
    }
    const dropdown = document.getElementById('dropdown-material');
    if (dropdown) dropdown.style.display = 'none';
};

// --- DATA FETCHERS ---
const wizardFetchVendors = () => {
    return fetch('/api/external/vendors')
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                wizardState.vendors = d.vendors;
                const items = [{ value: '', label: '-- Generic --' }].concat(
                    d.vendors.map(v => ({ value: String(v.id), label: v.name }))
                );
                window.wizardBindCombobox({
                    searchId: 'wiz-fil-vendor-search',
                    hiddenId: 'wiz-fil-vendor-sel',
                    dropdownId: 'dropdown-vendor',
                    items,
                    placeholder: '-- Generic --'
                });
                // Group 6.2: show ✏️ (open Vendor Edit modal) only when an
                // existing vendor is selected; the ➕ (toggle add-new mode)
                // button stays visible always. wizardBindCombobox + the change
                // dispatch added to wizardComboboxSet both fire on the hidden
                // input, so a single listener covers user picks AND
                // programmatic writes (external import, edit-mode auto-fill,
                // clone). The hidden input survives wizardBindCombobox's clone
                // dance (only wiz-fil-vendor-search is cloned), so this
                // listener stays bound across re-fetches.
                _wizardBindVendorEditBtn();
            }
        });
};

const _wizardBindVendorEditBtn = () => {
    const hidden = document.getElementById('wiz-fil-vendor-sel');
    const editBtn = document.getElementById('wiz-fil-vendor-edit-btn');
    if (!hidden || !editBtn) return;
    const refresh = () => {
        editBtn.style.display = hidden.value ? 'inline-block' : 'none';
    };
    if (!hidden.dataset.editBtnBound) {
        hidden.addEventListener('change', refresh);
        hidden.dataset.editBtnBound = '1';
    }
    refresh();
};

// Push the vendor's empty_spool_weight into the wizard's filament empty-weight
// input when it's currently blank. wizardSetupFieldSync mirrors any input
// change into wiz-spool-empty_weight, so this single dispatch propagates all
// the way through to the spool field too. Skipped when the user has typed
// over the value already — never clobber user input.
const _wizardCascadeVendorEmptyWeight = (vendor) => {
    if (!vendor || vendor.empty_spool_weight == null || vendor.empty_spool_weight === '') return;
    const filEmptyEl = document.getElementById('wiz-fil-empty_weight');
    if (!filEmptyEl || filEmptyEl.value) return;
    filEmptyEl.value = String(vendor.empty_spool_weight);
    filEmptyEl.dispatchEvent(new Event('input', { bubbles: true }));
};

// `vendor:created` listener — the Vendor Edit modal's create mode dispatches
// this after a successful POST /api/vendors. The wizard refetches its
// dropdown source so the new vendor shows in the combobox, auto-selects it,
// AND propagates its empty_spool_weight into the filament/spool cascade so
// the user doesn't have to retype the weight they just set on the vendor.
// Skipped if the wizard isn't open.
document.addEventListener('vendor:created', (e) => {
    const v = e.detail && e.detail.vendor;
    if (!v || v.id == null) return;
    const wizModalEl = document.getElementById('wizardModal');
    const wizardOpen = wizModalEl && wizModalEl.classList.contains('show');
    if (!wizardOpen) return;
    wizardFetchVendors().then(() => {
        window.wizardComboboxSet(
            'wiz-fil-vendor-search', 'wiz-fil-vendor-sel',
            String(v.id), v.name || ''
        );
        _wizardCascadeVendorEmptyWeight(v);
    });
});

// `vendor:updated` listener — if the user edited the CURRENTLY-SELECTED
// vendor (e.g. changed its empty_spool_weight from inside the wizard), the
// stale value in wizardState.vendors would otherwise drive the cascade on
// the next spool step. Refetch + re-cascade so the wizard sees the updated
// data. Skipped when the wizard isn't open or a different vendor was edited.
document.addEventListener('vendor:updated', (e) => {
    const vid = e.detail && e.detail.id;
    const v = e.detail && e.detail.vendor;
    if (!vid || !v) return;
    const wizModalEl = document.getElementById('wizardModal');
    const wizardOpen = wizModalEl && wizModalEl.classList.contains('show');
    if (!wizardOpen) return;
    const selectedId = document.getElementById('wiz-fil-vendor-sel');
    if (!selectedId || selectedId.value !== String(vid)) return;
    wizardFetchVendors().then(() => {
        _wizardCascadeVendorEmptyWeight(v);
    });
});

const wizardFetchLocations = () => {
    return fetch('/api/locations')
        .then(r => r.json())
        .then(d => {
            if (!Array.isArray(d)) return;
            // Same filter the select used to apply: hide MMU/toolhead/direct-load
            // targets and the virtual "Unassigned" row (that's the empty-string default).
            const valid = d.filter(loc => {
                const type = (loc.Type || '').toLowerCase();
                if (type.includes('mmu') || type.includes('tool') || type.includes('direct load') || type === 'virtual') return false;
                // L271 Phase 5: Wall Shelf/Row are structural grouping nodes —
                // they nest children but never hold spools, so don't offer them
                // as spool-assignment targets (Section, the leaf, IS offered).
                if (type === 'wall shelf' || type === 'row') return false;
                if (loc.LocationID === 'Unassigned') return false;
                return true;
            });
            wizardState.locations = valid;
            // 13.4 — include LocationID in the visible label so typing a LOC
            // value (e.g. "LR-MDB-1") matches via wizardBindCombobox's
            // label-substring filter. Mirrors the force-location modal's
            // `Name (LocationID)` convention so the dashboard's location
            // pickers stay visually consistent.
            const items = [{ value: '', label: '-- Unassigned --' }].concat(
                valid.map(loc => ({
                    value: loc.LocationID,
                    label: loc.Name ? `${loc.Name} (${loc.LocationID})` : loc.LocationID,
                }))
            );
            window.wizardBindCombobox({
                searchId: 'wiz-spool-location-search',
                hiddenId: 'wiz-spool-location',
                dropdownId: 'dropdown-location',
                items,
                placeholder: 'Unassigned (default)'
            });
        });
};

const wizardFetchExtraFields = () => {
    return fetch('/api/external/fields')
        .then(r => r.json())
        .then(d => {
            if (d.success && d.fields) {
                wizardState.extraFields = d.fields;

                // --- FILAMENT CUSTOM FIELDS ---
                const fContainer = document.getElementById('wiz-fil-dynamic-extra-fields');
                fContainer.innerHTML = '';

                if (d.fields.filament) {
                    d.fields.filament.sort((a, b) => (a.order || 0) - (b.order || 0));
                    d.fields.filament.forEach(field => {
                        // Hide legacy/system fields, plus the two max-temp keys —
                        // those have dedicated static inputs (#wiz-fil-nozzle_temp_max
                        // and #wiz-fil-bed_temp_max) so a second dynamic input would
                        // race the static one on save and re-send a raw numeric value
                        // that Spoolman rejects.
                        // Group 10.4 — purchase_url is intentionally hidden from
                        // the wizard's filament tab. The user edits the spool's
                        // purchase_url instead, which falls back to the filament's
                        // value on read when blank (inv_details.js:168). To edit
                        // the filament-level value directly, use the Edit
                        // Filament modal.
                        //
                        // L144 / 17.1 round 2: `needs_label_print` UN-hidden so it
                        // surfaces alongside `sample_printed` as a boolean checkbox
                        // in the wizard's Filament Extras section. Both flags are
                        // already registered in setup_fields.py (filament_standards)
                        // so the dynamic-field renderer turns them into proper
                        // toggle inputs without bespoke per-field UI. The display
                        // side (badges on Filament Details modal) shipped in
                        // 17.1 round 1. `label_printed` (the legacy retired key)
                        // stays hidden — it's gone in M7+ data.
                        if (['sheet_link', 'price_total', 'spoolman_reprint', 'label_printed',
                             'nozzle_temp_max', 'bed_temp_max', 'purchase_url'].includes(field.key)) return;

                        let html = wizardGenerateFieldHTML(field, 'fil');
                        if (html) fContainer.innerHTML += html;
                    });
                }

                // --- SPOOL CUSTOM FIELDS ---
                const sContainer = document.getElementById('wiz-spool-dynamic-extra-fields');
                if (sContainer && d.fields.spool) {
                    sContainer.innerHTML = '';
                    d.fields.spool.sort((a, b) => (a.order || 0) - (b.order || 0));
                    d.fields.spool.forEach(field => {
                        if (['needs_label_print', 'physical_source', 'physical_source_slot', 'container_slot'].includes(field.key)) return;

                        // If Temp Resistance is still 'text' in Spoolman, hide it so they can change it to Choice later
                        if (field.key === 'spool_temp' && field.field_type === 'text') return;

                        let html = wizardGenerateFieldHTML(field, 'spool');
                        if (html) sContainer.innerHTML += html;
                    });
                }

                // 🌟 After DOM generation, initialize the live Sync Bindings
                wizardSetupFieldSync();
                // Group 10.1 Session C polish: move original_color into the
                // Color panel and hide shore_hardness unless material is TPU.
                if (window.wizardRelocateOriginalColorField) window.wizardRelocateOriginalColorField();
                if (window.wizardApplyShoreHardnessGate) window.wizardApplyShoreHardnessGate();
                if (window.wizardRefreshAllSectionSummaries) window.wizardRefreshAllSectionSummaries();
            }
        });
};

window.wizardSetupFieldSync = () => {
    // Empy weight static propagation
    const filEmptyWt = document.getElementById('wiz-fil-empty_weight');
    const spoolEmptyWt = document.getElementById('wiz-spool-empty_weight');
    if (filEmptyWt && spoolEmptyWt) {
        ['input', 'change'].forEach(evt => {
            filEmptyWt.addEventListener(evt, (e) => {
                spoolEmptyWt.value = e.target.value;
            });
        });
    }

    // Lock all auto-synced Spool fields on initial render
    document.querySelectorAll('.wizard-sync-btn.active-sync').forEach(btn => {
        const spoolKey = btn.getAttribute('data-sync-target');
        const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);
        if (targetEl) {
            targetEl.setAttribute('readonly', 'true');
            targetEl.style.opacity = '0.7';
        }
    });

    // Find all Filament inputs that could act as Sync Sources
    const sources = document.querySelectorAll('.sync-source-fil');

    sources.forEach(sourceEl => {
        // We listen to input (typing) and change (select dropdowns/checkboxes/chips)
        ['input', 'change'].forEach(evtType => {
            sourceEl.addEventListener(evtType, (e) => {
                const filKey = e.target.getAttribute('data-key');
                if (!filKey) return;

                // Find ALL active Spool sync buttons that are linked to this filament key
                const syncBtns = document.querySelectorAll('.wizard-sync-btn.active-sync');

                syncBtns.forEach(btn => {
                    const linkedTo = btn.getAttribute('data-linked-fil-key');
                    if (linkedTo === filKey) {
                        const spoolKey = btn.getAttribute('data-sync-target');
                        const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);
                        if (targetEl) {
                            // Mirror the value based on input type
                            if (e.target.type === 'checkbox') {
                                targetEl.checked = e.target.checked;
                            } else {
                                targetEl.value = e.target.value;
                            }
                        }
                    }
                });
            });
        });
    });
};

window.wizardToggleFieldSync = (spoolKey) => {
    const btn = document.querySelector(`.wizard-sync-btn[data-sync-target="${spoolKey}"]`);
    const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);

    if (!btn || !targetEl) return;

    let spoolName = spoolKey;
    if (wizardState.extraFields?.spool) {
        const schema = wizardState.extraFields.spool.find(f => f.key === spoolKey);
        if (schema) spoolName = schema.name;
    }

    if (btn.classList.contains('active-sync')) {
        // BREAK THE LINK
        btn.classList.remove('active-sync');
        btn.classList.replace('btn-outline-info', 'btn-outline-secondary');
        btn.innerText = '🔗';
        btn.style.opacity = '0.5';
        btn.title = "Unlinked. Click to sync with a Filament field.";

        targetEl.removeAttribute('readonly');
        targetEl.style.opacity = '1';

        showToast(`Unlinked ${spoolName}`, "info");
    } else {
        // RESTORE OR CREATE THE LINK
        const filKey = btn.getAttribute('data-linked-fil-key');
        if (!filKey) {
            // Prompt user to select a field
            window.wizardPromptFieldSync(spoolKey);
            return;
        }

        btn.classList.add('active-sync');
        btn.classList.replace('btn-outline-secondary', 'btn-outline-info');
        btn.innerText = '🔗';
        btn.style.opacity = '1';

        targetEl.setAttribute('readonly', 'true');
        targetEl.style.opacity = '0.7';

        // Find the source filament element to pull initial value
        const sourceEl = document.getElementById(`wiz_fil_ef_${filKey}`);
        if (sourceEl) {
            if (sourceEl.type === 'checkbox') targetEl.checked = sourceEl.checked;
            else targetEl.value = sourceEl.value;
        }

        let filName = filKey;
        if (wizardState.extraFields?.filament) {
            const schema = wizardState.extraFields.filament.find(f => f.key === filKey);
            if (schema) filName = schema.name;
        }

        btn.title = `Synced with Filament's ${filName}. Click to unlink.`;
        showToast(`Synced ${spoolName} with ${filName}`, "success");
    }
};

window.wizardPromptFieldSync = (spoolKey) => {
    let inputOptions = {};
    if (wizardState.extraFields && wizardState.extraFields.filament) {
        wizardState.extraFields.filament.forEach(f => {
            inputOptions[f.key] = f.name;
        });
    }

    // Group 10.8 — was nested Swal.fire; now mountOverlay so it survives
    // Bootstrap's focus trap and doesn't shift the wizard scrollbar comp.
    const wizModalEl = document.getElementById('wizardModal');
    const optsHtml = Object.entries(inputOptions)
        .map(([k, v]) => `<option value="${String(k).replace(/"/g, '&quot;')}">${String(v).replace(/</g, '&lt;')}</option>`)
        .join('');
    const panelHtml = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #17a2b8; border-radius:8px; padding:20px 24px; max-width:520px; width:92%;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">🔗 Link Field</div>
            <div style="color:#ffc; margin-bottom:12px;">Select a Filament field to synchronize with this Spool field:</div>
            <select id="fcc-wiz-fieldsync-sel" class="form-select form-select-sm bg-dark text-white border-secondary mb-3" style="width:100%;">
                <option value="" disabled selected>-- Select a Field --</option>
                ${optsHtml}
            </select>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-fieldsync-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                <button id="fcc-wiz-fieldsync-confirm" class="btn btn-info btn-sm" style="min-width:120px;">Link</button>
            </div>
        </div>
    `;
    const handle = window.mountOverlay({
        id: 'fcc-wiz-fieldsync',
        content: panelHtml,
        host: wizModalEl,
        initialFocus: '#fcc-wiz-fieldsync-sel',
    });
    const sel = handle.element.querySelector('#fcc-wiz-fieldsync-sel');
    const commit = () => {
        const val = sel?.value;
        handle.cleanup();
        if (!val) return;
        const btn = document.querySelector(`.wizard-sync-btn[data-sync-target="${spoolKey}"]`);
        if (btn) {
            btn.setAttribute('data-linked-fil-key', val);
            window.wizardToggleFieldSync(spoolKey);
        }
    };
    handle.element.querySelector('#fcc-wiz-fieldsync-confirm')?.addEventListener('click', commit);
    handle.element.querySelector('#fcc-wiz-fieldsync-cancel')?.addEventListener('click', () => handle.cleanup());
    sel?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } });
};

const wizardGenerateFieldHTML = (field, entityType) => {
    let syncHtml = '';
    // If we're rendering a Spool field, check if a Filament field with the exact same key exists
    if (entityType === 'spool' && wizardState.extraFields?.filament) {
        const hasMatchingFilamentField = wizardState.extraFields.filament.some(f => f.key === field.key);
        if (hasMatchingFilamentField) {
            // Default to synced (active) state
            syncHtml = `<button type="button" class="btn btn-sm btn-outline-info p-0 ms-2 border-0 wizard-sync-btn active-sync" 
                            data-sync-target="${field.key}" 
                            data-linked-fil-key="${field.key}"
                            onclick="window.wizardToggleFieldSync('${field.key}')" 
                            title="Synced with Filament's ${field.name}. Click to unlink."
                            style="font-size: 0.8rem; line-height: 1;">🔗</button>`;
        } else {
            // Unsynced state, user can click to map it manually
            syncHtml = `<button type="button" class="btn btn-sm btn-outline-secondary p-0 ms-2 border-0 wizard-sync-btn" 
                            data-sync-target="${field.key}"
                            data-linked-fil-key=""
                            onclick="window.wizardToggleFieldSync('${field.key}')" 
                            title="Click to link this field to a Filament field."
                            style="font-size: 0.8rem; line-height: 1; opacity: 0.5;">🔗</button>`;
        }
    }

    // data-extra-key lets the Session-C polish hooks (TPU gate on
    // shore_hardness, original_color relocation into the Color panel) find
    // the wrapper without grepping the inner input id.
    let html = `<div class="col-md-6 mb-2" data-extra-key="${field.key}"><label class="form-label small text-secondary mb-1 d-flex align-items-center">${field.name}${syncHtml}</label>`;
    const dataClass = entityType === 'fil' ? 'dynamic-extra-field' : 'dynamic-extra-spool-field';
    // Add an ID for easy targeting by the sync logic
    const inputId = `wiz_${entityType}_ef_${field.key}`;

    if (field.field_type === 'choice' && field.multi_choice) {
        // Custom Searchable Tag/Chip System (Replaces Native Datalist).
        // Wrapped in a flex row so the ➕ "add new option" button sits to the
        // RIGHT of the chip box — parity with the single-choice path below,
        // which always had a ➕ while the multi-choice path was missing it (the
        // widget's own suggestion toast already told users to "use the ➕
        // button"). The ➕ opens wizardPromptNewChoice, which is multi-choice
        // aware: it drops a chip in place on success instead of refetching the
        // schema (a refetch would wipe the in-progress wizard DOM).
        html += `<div class="d-flex align-items-stretch gap-1">
                    <div class="position-relative wizard-chip-multiselect flex-grow-1" id="wizard-ms-${entityType}-${field.key}">
                    <div class="form-control bg-dark text-white border-secondary d-flex flex-wrap align-items-center gap-1 p-1" style="min-height: 38px; cursor: text;" onclick="document.getElementById('${inputId}').focus()">
                        <div class="chip-container d-flex flex-wrap gap-1" id="chip-container-${entityType}-${field.key}"></div>
                        <input type="text"
                               class="border-0 bg-transparent text-white flex-grow-1 chip-input sync-source-${entityType}"
                               id="${inputId}"
                               data-key="${field.key}"
                               placeholder="Search or type new..."
                               autocomplete="off"
                               style="outline: none; min-width: 120px;"
                               onfocus="wizardMultiselectFocus('${entityType}', '${field.key}')"
                               onblur="wizardMultiselectBlur('${entityType}', '${field.key}')"
                               oninput="wizardMultiselectFilter('${entityType}', '${field.key}')"
                               onkeydown="wizardMultiselectKeydown(event, '${entityType}', '${field.key}')">
                    </div>
                    <div class="autocomplete-dropdown position-absolute w-100 bg-dark border border-secondary rounded shadow-lg"
                         id="dropdown-${entityType}-${field.key}"
                         style="display: none; top: 100%; left: 0; z-index: 1050; max-height: 200px; overflow-y: auto;">`;

        // Populate the dropdown with initial options
        field.choices.forEach(c => {
            html += `<div class="dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option"
                          onmousedown="wizardMultiselectSelect(event, '${entityType}', '${field.key}', this.innerText)">${c}</div>`;
        });

        html += `   </div>
                    </div>
                    <button type="button" class="btn btn-outline-secondary wizard-multichoice-add"
                            onmousedown="event.preventDefault()"
                            onclick="wizardPromptNewChoice('${entityType}', '${field.key}')"
                            title="Add a new option to the Spoolman database"
                            aria-label="Add new option"
                            style="flex:0 0 auto;">➕</button>
                 </div>`;

    } else if (field.field_type === 'choice' && !field.multi_choice) {
        html += `<div class="input-group input-group-sm" style="position: relative; z-index: 1;">
                    <select class="form-select bg-dark text-white border-secondary ${dataClass} sync-source-${entityType}" data-key="${field.key}" id="${inputId}">
                        <option value="">-- None --</option>`;
        field.choices.forEach(c => {
            html += `<option value="${c}">${c}</option>`;
        });
        html += `   </select>
                    <button class="btn btn-outline-secondary" type="button" 
                            onclick="wizardPromptNewChoice('${entityType}', '${field.key}')" 
                            title="Add new option to Spoolman Database">➕</button>
                 </div>`;

    } else if (field.field_type === 'boolean') {
        html += `<div class="form-check mt-1">
                    <input class="form-check-input ${dataClass} sync-source-${entityType}" type="checkbox" data-key="${field.key}" id="${inputId}">
                    <label class="form-check-label text-white small" for="${inputId}">Enable</label>
                 </div>`;
    } else {
        // Standard text/number input
        html += `<input type="text" class="form-control bg-dark text-white border-secondary ${dataClass} sync-source-${entityType}" data-key="${field.key}" id="${inputId}" autocomplete="off">`;
    }

    html += `</div>`;
    return html;
};

window.wizardAddMultiChoiceChip = (entityType, key, directVal = null) => {
    const inputId = `wiz_${entityType}_ef_${key}`;
    const input = document.getElementById(inputId);
    if (!input) return;
    const rawVal = (directVal !== null ? directVal : input.value).trim();
    if (!rawVal) return;

    const container = document.getElementById(`chip-container-${entityType}-${key}`);
    const apiEntity = entityType === 'fil' ? 'filament' : 'spool';
    const schemas = wizardState.extraFields?.[apiEntity];
    const fieldObj = schemas?.find(f => f.key === key);
    const existingChoices = fieldObj?.choices || [];
    const isExistingExact = existingChoices.includes(rawVal);

    // Group 10.9 — gate new (unknown) values through validateNewChoice.
    // Direct picks from the dropdown bypass the gate (directVal !== null) so
    // existing-choice selections always go through unimpeded.
    let val = rawVal;
    if (directVal === null && !isExistingExact && typeof window.validateNewChoice === 'function') {
        const result = window.validateNewChoice(rawVal, existingChoices);
        if (!result.ok) {
            if (typeof showToast === 'function') {
                showToast(result.error || 'Invalid value', 'warning', 5000);
            }
            return;
        }
        if (result.suggestion) {
            // Silent path (blur/Enter on multiselect) — surface as toast and
            // refuse to commit; user can click the suggested existing choice
            // from the dropdown or use the +Add modal for explicit confirm.
            if (typeof showToast === 'function') {
                showToast(`Did you mean "${result.suggestion}"? — pick it from the list, or use the ➕ button to add "${result.canonical}" as a new value.`, 'info', 7000);
            }
            return;
        }
        val = result.canonical;
    }

    // Duplicate-chip guard after normalization.
    const escapedVal = CSS.escape(val);
    if (container.querySelector(`[data-value="${escapedVal}"]`)) {
        input.value = '';
        return;
    }
    wizardState.isDirty = true;

    const isKnown = existingChoices.includes(val) || isExistingExact;
    if (!isKnown) {
        // Silently push new choice to Spoolman backend config.
        fetch('/api/external/fields/add_choice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_type: apiEntity, key: key, new_choice: val })
        });
        // We do NOT call wizardFetchExtraFields() here because it would wipe the unsaved modal DOM. The chip is already visually rendering below!
    }

    // Append Chip visually
    const chipHtml = `<span class="badge rounded-pill text-bg-primary border border-primary cursor-pointer dynamic-chip"
                           onclick="this.remove()"
                           data-key="${key}"
                           data-selected="true"
                           data-value="${val}">${val} &times;</span>`;
    container.insertAdjacentHTML('beforeend', chipHtml);
    input.value = '';

    // Reset Filtering
    if (window.wizardMultiselectFilter) window.wizardMultiselectFilter(entityType, key);
};

// --- Group 10.5: when the user adds a new single-choice value (e.g. slicer
// profile) from inside the wizard, auto-select it on the currently-edited
// filament/spool so they don't have to re-pick it after the schema refresh.
// Also handles the "Use existing" branch from the suggestion swap (wasNew=false).
window.wizardOnNewChoiceAdded = (apiEntity, key, value, info) => {
    const entityPrefix = apiEntity === 'filament' ? 'fil' : 'spool';
    const inputId = `wiz_${entityPrefix}_ef_${key}`;
    const input = document.getElementById(inputId);
    if (!input) return;
    if (input.tagName === 'SELECT') {
        // wizardFetchExtraFields just re-rendered this select; the new value
        // is already in the option list. Pick it and trigger change so
        // dirty-tracking / sync handlers fire.
        input.value = value;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        wizardState.isDirty = true;
    } else if (input.tagName === 'INPUT' && info && info.wasNew) {
        // Multi-choice path (chips) — wizardAddMultiChoiceChip already handles
        // chip creation, so nothing to do here. Kept as a no-op branch for
        // future expansion.
    }
};

// --- Group 10.9: stateful content swaps inside the SAME add-new overlay.
// We avoid nested overlays because nested mountOverlay handles compete for
// Escape in capture-phase registration order (oldest wins), so the inner
// overlay can't reliably reclaim Escape. Swapping content inside the existing
// overlay sidesteps the race and keeps the workflow visually continuous.
// `wizardSwapNewChoiceTo*` are called by wizardPromptNewChoice's commit path.
window.wizardSwapNewChoiceToSuggestion = (handle, suggestion, canonical, fieldLabel, callbacks) => {
    const cb = callbacks || {};
    const safeSugg = String(suggestion).replace(/</g, '&lt;');
    const safeCanon = String(canonical).replace(/</g, '&lt;');
    const safeLabel = String(fieldLabel || 'value').replace(/</g, '&lt;');
    handle.element.dataset.stage = 'suggestion';
    handle.setContent(`
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px; padding:20px 24px; max-width:520px; width:92%;" data-stage-panel="suggestion">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:10px;">🤔 Did you mean <span style="color:#ffd700;">${safeSugg}</span>?</div>
            <div style="color:#ffc; margin-bottom:14px;">A similar ${safeLabel} already exists. Pick the existing one (recommended) or add "<strong>${safeCanon}</strong>" as a brand-new value.</div>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-sugg-add" class="btn btn-outline-warning btn-sm" style="min-width:160px;">Add "${safeCanon}" as new</button>
                <button id="fcc-wiz-sugg-use" class="btn btn-success btn-sm" style="min-width:160px;">Use "${safeSugg}"</button>
            </div>
        </div>
    `);
    handle.element.querySelector('#fcc-wiz-sugg-use')?.addEventListener('click', () => {
        handle.cleanup();
        if (typeof cb.useExisting === 'function') cb.useExisting();
    });
    handle.element.querySelector('#fcc-wiz-sugg-add')?.addEventListener('click', () => {
        if (typeof cb.addAnyway === 'function') cb.addAnyway();
    });
    setTimeout(() => handle.element.querySelector('#fcc-wiz-sugg-use')?.focus(), 0);
};

window.wizardSwapNewChoiceToConfirm = (handle, canonical, fieldLabel, onConfirm) => {
    const safeCanon = String(canonical).replace(/</g, '&lt;');
    const safeLabel = String(fieldLabel || 'value').replace(/</g, '&lt;');
    handle.element.dataset.stage = 'confirm';
    handle.setContent(`
        <div style="background:#1e1e1e; color:#fff; border:2px solid #dc3545; border-radius:8px; padding:20px 24px; max-width:520px; width:92%;" data-stage-panel="confirm">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:10px;">⚠️ Add permanent new ${safeLabel}?</div>
            <div style="color:#ffc; margin-bottom:14px;">Add "<strong>${safeCanon}</strong>" as a permanent new ${safeLabel}? Spoolman doesn't expose UI to remove choices once added.</div>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-addnew-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                <button id="fcc-wiz-addnew-confirm" class="btn btn-danger btn-sm" style="min-width:160px;">Add Permanently</button>
            </div>
        </div>
    `);
    handle.element.querySelector('#fcc-wiz-addnew-confirm')?.addEventListener('click', () => {
        if (typeof onConfirm === 'function') onConfirm();
    });
    handle.element.querySelector('#fcc-wiz-addnew-cancel')?.addEventListener('click', () => handle.cleanup());
    setTimeout(() => handle.element.querySelector('#fcc-wiz-addnew-cancel')?.focus(), 0);
};

// --- CHIP MULTISELECT LOGIC ---
window.wizardMultiselectFocus = (entityType, key) => {
    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
    if (dropdown) {
        dropdown.style.display = 'block';
        wizardMultiselectFilter(entityType, key); // Filter initial list
    }
};

window.wizardMultiselectBlur = (entityType, key) => {
    setTimeout(() => {
        const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
        if (dropdown) dropdown.style.display = 'none';

        // Auto-commit on blur if typed text exists
        const input = document.getElementById(`wiz_${entityType}_ef_${key}`);
        if (input && input.value.trim().length > 0) {
            wizardAddMultiChoiceChip(entityType, key);
        }
    }, 150); // Delay allows click event on dropdown to fire first
};

window.wizardMultiselectFilter = (entityType, key) => {
    const qs = document.getElementById(`wiz_${entityType}_ef_${key}`).value.toLowerCase();
    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
    if (!dropdown) return;

    let hasVisible = false;
    Array.from(dropdown.children).forEach(option => {
        option.classList.remove('active', 'bg-primary'); // Clear selections on filter
        if (option.innerText.toLowerCase().includes(qs)) {
            option.style.display = 'block';
            hasVisible = true;
        } else {
            option.style.display = 'none';
        }
    });

    dropdown.style.display = hasVisible ? 'block' : 'none';
};

window.wizardMultiselectKeydown = (event, entityType, key) => {
    const input = document.getElementById(`wiz_${entityType}_ef_${key}`);
    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
    if (!input) return;

    let visibleOptions = [];
    if (dropdown && dropdown.style.display !== 'none') {
        visibleOptions = Array.from(dropdown.children).filter(el => el.style.display !== 'none');
    }

    // Escape closes the multi-choice dropdown only (when open) — keep the
    // wizard modal open (Escape would otherwise bubble to Bootstrap's modal
    // dismiss and discard the wizard). Matches inv_details.js attribute picker.
    if (event.key === 'Escape' && dropdown && dropdown.style.display !== 'none') {
        event.preventDefault();
        event.stopPropagation();
        dropdown.style.display = 'none';
        return;
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        if (!visibleOptions.length) return;
        event.preventDefault();

        let currentIndex = visibleOptions.findIndex(el => el.classList.contains('active'));

        // Remove active class from all
        visibleOptions.forEach(el => el.classList.remove('active', 'bg-primary'));

        if (event.key === 'ArrowDown') {
            currentIndex = currentIndex + 1 >= visibleOptions.length ? 0 : currentIndex + 1;
        } else {
            currentIndex = currentIndex - 1 < 0 ? visibleOptions.length - 1 : currentIndex - 1;
        }

        const nextActive = visibleOptions[currentIndex];
        nextActive.classList.add('active', 'bg-primary');

        // Ensure visible in scroll view
        const dropRect = dropdown.getBoundingClientRect();
        const itemRect = nextActive.getBoundingClientRect();
        if (itemRect.bottom > dropRect.bottom) {
            dropdown.scrollTop += (itemRect.bottom - dropRect.bottom);
        } else if (itemRect.top < dropRect.top) {
            dropdown.scrollTop -= (dropRect.top - itemRect.top);
        }
        return;
    }

    if (event.key === 'Enter') {
        event.preventDefault(); // Prevent modal form submission on enter

        if (visibleOptions.length > 0) {
            // Find active option, if none, use first visible
            let selected = visibleOptions.find(el => el.classList.contains('active')) || visibleOptions[0];
            wizardAddMultiChoiceChip(entityType, key, selected.innerText);
            return;
        }
        wizardAddMultiChoiceChip(entityType, key); // Fallback to current text
    } else if (event.key === 'Backspace' && input.value === '') {
        // Find last chip and remove it
        const container = document.getElementById(`chip-container-${entityType}-${key}`);
        if (container && container.lastElementChild) {
            container.removeChild(container.lastElementChild);
        }
    }
};

window.wizardMultiselectSelect = (event, entityType, key, value) => {
    event.preventDefault(); // Prevent blur trigger
    wizardAddMultiChoiceChip(entityType, key, value);
    const input = document.getElementById(`wiz_${entityType}_ef_${key}`);
    if (input) input.focus(); // Keep focus after click
};

window.wizardPromptNewChoice = (entityType, key) => {
    // Determine the absolute entity mapping Spoolman uses ('filament' or 'spool')
    const apiEntity = entityType === 'fil' ? 'filament' : 'spool';

    // Multi-choice fields (e.g. filament_attributes) now expose a ➕ button too.
    // They render the chip widget, so the success path must drop a chip IN PLACE
    // rather than refetch the schema (wizardFetchExtraFields wipes the
    // in-progress wizard DOM). Pre-seed the overlay with whatever the user
    // already typed into the chip input, and clear that input so the pending
    // blur-commit (wizardMultiselectBlur) doesn't double-add the same value.
    const fieldDef = (wizardState.extraFields?.[apiEntity] || []).find((f) => f.key === key);
    const isMultiChoice = !!(fieldDef && fieldDef.multi_choice);
    let seedValue = '';
    if (isMultiChoice) {
        const chipInput = document.getElementById(`wiz_${entityType}_ef_${key}`);
        if (chipInput) { seedValue = (chipInput.value || '').trim(); chipInput.value = ''; }
    }

    // Group 10.8 — was nested Swal.fire; now mountOverlay.
    // Group 10.9 hooks `validateNewChoice` into the submit path for length /
    // punctuation / fuzzy-duplicate guards. Group 10.5 hooks the post-success
    // auto-assign for `slicer_profile`.
    const wizModalEl = document.getElementById('wizardModal');
    const existingChoices = (() => {
        const list = wizardState.extraFields?.[apiEntity] || [];
        const field = list.find((f) => f.key === key);
        const raw = field?.choices;
        if (Array.isArray(raw)) return raw;
        if (typeof raw === 'string') {
            try { const parsed = JSON.parse(raw); return Array.isArray(parsed) ? parsed : []; }
            catch (_) { return raw.replace(/[\[\]"]/g, '').split(',').map(s => s.trim()).filter(Boolean); }
        }
        return [];
    })();
    const fieldLabel = (() => {
        const list = wizardState.extraFields?.[apiEntity] || [];
        const field = list.find((f) => f.key === key);
        return field?.name || key;
    })();

    const panelHtml = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #28a745; border-radius:8px; padding:20px 24px; max-width:520px; width:92%;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">➕ Add New ${String(fieldLabel).replace(/</g, '&lt;')}</div>
            <div style="color:#ffc; margin-bottom:10px;">Enter the new value to permanently add it to the Spoolman database.</div>
            <input id="fcc-wiz-newchoice-input" type="text" class="form-control form-control-sm bg-dark text-white border-secondary mb-2" autocomplete="off" autocapitalize="off" spellcheck="false" />
            <div id="fcc-wiz-newchoice-preview" style="color:#9cf; font-size:0.85em; min-height:1.2em; margin-bottom:4px;"></div>
            <div id="fcc-wiz-newchoice-msg" style="color:#ff8080; font-size:0.9em; min-height:1.2em; margin-bottom:10px;"></div>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-wiz-newchoice-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                <button id="fcc-wiz-newchoice-confirm" class="btn btn-success btn-sm" style="min-width:120px;">Add Option</button>
            </div>
        </div>
    `;
    const handle = window.mountOverlay({
        id: 'fcc-wiz-newchoice',
        content: panelHtml,
        host: wizModalEl,
        initialFocus: '#fcc-wiz-newchoice-input',
    });
    handle.element.dataset.stage = 'input';
    const input = handle.element.querySelector('#fcc-wiz-newchoice-input');
    const preview = handle.element.querySelector('#fcc-wiz-newchoice-preview');
    const msg = handle.element.querySelector('#fcc-wiz-newchoice-msg');
    const confirmBtn = handle.element.querySelector('#fcc-wiz-newchoice-confirm');
    const cancelBtn = handle.element.querySelector('#fcc-wiz-newchoice-cancel');

    const validate = (raw) => {
        if (typeof window.validateNewChoice === 'function') {
            return window.validateNewChoice(raw, existingChoices);
        }
        // Fallback: legacy minimum (non-empty after trim).
        const t = String(raw || '').trim();
        return t ? { ok: true, canonical: t } : { ok: false, canonical: '', error: 'Cannot be empty' };
    };

    const renderPreview = () => {
        const v = validate(input.value);
        preview.textContent = v.canonical && v.canonical !== input.value
            ? `Stored as: ${v.canonical}`
            : '';
        msg.textContent = '';
    };
    input?.addEventListener('input', renderPreview);
    // Pre-fill from the chip input when the ➕ was clicked after typing.
    if (seedValue && input) { input.value = seedValue; renderPreview(); }

    const commit = async () => {
        if (!input || (confirmBtn && confirmBtn.disabled)) return;
        const v = validate(input.value);
        if (!v.ok) {
            const liveMsg = handle.element.querySelector('#fcc-wiz-newchoice-msg');
            if (liveMsg) liveMsg.textContent = v.error || 'Invalid value';
            return;
        }
        if (v.suggestion) {
            // 10.9 fuzzy-match path: swap the overlay's content to a
            // suggestion panel. Single overlay = Escape-race-free.
            window.wizardSwapNewChoiceToSuggestion?.(handle, v.suggestion, v.canonical, fieldLabel, {
                useExisting: () => {
                    if (typeof window.wizardOnNewChoiceAdded === 'function') {
                        window.wizardOnNewChoiceAdded(apiEntity, key, v.suggestion, { wasNew: false });
                    }
                },
                addAnyway: () => {
                    window.wizardSwapNewChoiceToConfirm?.(handle, v.canonical, fieldLabel,
                        () => doSubmitFromStage(v.canonical));
                },
            });
            return;
        }
        // 10.9 two-step confirm for clean new values:
        if (typeof window.wizardSwapNewChoiceToConfirm === 'function') {
            window.wizardSwapNewChoiceToConfirm(handle, v.canonical, fieldLabel,
                () => doSubmitFromStage(v.canonical));
        } else {
            doSubmit(v.canonical);
        }
    };

    // Stage-agnostic submit: disables whatever buttons currently exist on the
    // active panel (input / suggestion / confirm) and surfaces errors inline.
    const doSubmitFromStage = (canonical) => doSubmit(canonical);

    const doSubmit = (canonical) => {
        const buttons = handle.element.querySelectorAll('button');
        buttons.forEach(b => { b.disabled = true; });
        fetch('/api/external/fields/add_choice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_type: apiEntity, key: key, new_choice: canonical })
        })
            .then(r => r.json())
            .then(data => {
                if (!data.success) throw new Error(data.msg || 'Add failed');
                handle.cleanup();
                if (typeof showToast === 'function') {
                    showToast(`"${canonical}" added to the database.`, 'success', 3000);
                }
                if (isMultiChoice) {
                    // Multi-choice chip widget: do NOT refetch the schema —
                    // wizardFetchExtraFields wipes the in-progress wizard DOM.
                    // Register the new value in the live in-memory schema + the
                    // dropdown, then drop the chip in place.
                    if (fieldDef && Array.isArray(fieldDef.choices) && !fieldDef.choices.includes(canonical)) {
                        fieldDef.choices.push(canonical);
                    }
                    const dropdown = document.getElementById(`dropdown-${entityType}-${key}`);
                    if (dropdown && !Array.from(dropdown.children).some((o) => o.innerText === canonical)) {
                        const opt = document.createElement('div');
                        opt.className = 'dropdown-item text-white py-1 px-2 cursor-pointer autocomplete-option';
                        opt.setAttribute('onmousedown', `wizardMultiselectSelect(event, '${entityType}', '${key}', this.innerText)`);
                        opt.innerText = canonical;
                        dropdown.appendChild(opt);
                    }
                    // canonical is now a "known" choice, so the directVal path
                    // appends the chip and skips a duplicate add_choice POST.
                    if (typeof window.wizardAddMultiChoiceChip === 'function') {
                        window.wizardAddMultiChoiceChip(entityType, key, canonical);
                    }
                    return undefined;
                }
                // Single-choice (existing behavior): refresh the schema THEN
                // fire the auto-assign hook — the select gets re-rendered by
                // wizardFetchExtraFields, so we wait for the new <option> to
                // exist before selecting it (Group 10.5).
                return Promise.resolve(wizardFetchExtraFields()).then(() => {
                    if (typeof window.wizardOnNewChoiceAdded === 'function') {
                        window.wizardOnNewChoiceAdded(apiEntity, key, canonical, { wasNew: true });
                    }
                });
            })
            .catch(err => {
                buttons.forEach(b => { b.disabled = false; });
                if (typeof showToast === 'function') {
                    showToast(`Add failed: ${err.message || err}`, 'error', 7000);
                }
            });
    };

    confirmBtn?.addEventListener('click', commit);
    cancelBtn?.addEventListener('click', () => handle.cleanup());
    input?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); commit(); } });
};

// --- COLOR GRADIENT LOGIC ---
window.wizardAddColorHex = () => {
    const container = document.getElementById('wiz-fil-color-extra-container');
    const idx = container.children.length + 1;
    const html = `
        <div class="input-group input-group-sm mb-1 mt-1">
            <input type="color" class="form-control form-control-color bg-dark border-secondary px-1" value="#000000" oninput="this.nextElementSibling.value = this.value.toUpperCase()">
            <input type="text" class="form-control bg-dark text-white border-secondary font-monospace pb-wiz-color" placeholder="#Hex" value="#000000" id="wiz-fil-color_hex_${idx}" autocomplete="off" oninput="this.previousElementSibling.value = (this.value.startsWith('#') ? this.value : '#' + this.value).padEnd(7, '0').substring(0,7)">
            <button class="btn btn-outline-danger" type="button" onclick="this.parentElement.remove(); if(document.getElementById('wiz-fil-color-extra-container').children.length === 0) { const w = document.getElementById('wiz-fil-color-direction-wrapper'); if (w) w.style.display='none'; }" title="Remove color">🗑️</button>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
    const dirWrap = document.getElementById('wiz-fil-color-direction-wrapper');
    if (dirWrap) dirWrap.style.display = 'block';
};

window.wizardPopulateColors = (hexString, direction) => {
    const container = document.getElementById('wiz-fil-color-extra-container');
    container.innerHTML = '';
    
    const dirEl = document.getElementById('wiz-fil-color-direction');
    if (dirEl) dirEl.value = direction || 'longitudinal';
    const dirWrap = document.getElementById('wiz-fil-color-direction-wrapper');
    if (dirWrap) dirWrap.style.display = 'none';

    if (!hexString) {
        document.getElementById('wiz-fil-color_hex_0').value = '#FFFFFF';
        document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = '#FFFFFF';
        return;
    }

    const hexes = hexString.split(',').map(h => h.trim().replace('#', '').toUpperCase()).filter(h => h.length >= 3);
    if (hexes.length === 0) {
        document.getElementById('wiz-fil-color_hex_0').value = '#FFFFFF';
        document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = '#FFFFFF';
        return;
    }

    // Set first hex
    document.getElementById('wiz-fil-color_hex_0').value = `#${hexes[0]}`;
    document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = `#${hexes[0]}`;

    // Add remaining hexes
    for (let i = 1; i < hexes.length; i++) {
        window.wizardAddColorHex();
        // wizardAddColorHex injects HTML inside container. Find the last added element.
        const inputs = container.querySelectorAll('input[type="text"]');
        if (inputs.length > 0) {
            const lastInput = inputs[inputs.length - 1];
            lastInput.value = `#${hexes[i]}`;
            lastInput.previousElementSibling.value = `#${hexes[i]}`;
        }
    }

    if (hexes.length > 1) {
        // wizardAddColorHex already shows the wrapper, but be defensive
        // in case populateColors is called without any wizardAddColorHex
        // invocation (e.g. legacy single-call paths).
        if (dirWrap) dirWrap.style.display = 'block';
    }
};

// --- EXISTING FILAMENT LOGIC ---
window.wizardSearchExisting = () => {
    // Basic frontend filter based on standard filament pool
    // In a production environment this should likely ping a dedicated /api/v1/filament?query endpoint
    const term = document.getElementById('wiz-search-existing').value.toLowerCase();
    const sel = document.getElementById('wiz-existing-results');
    sel.innerHTML = '<option disabled>Searching...</option>';

    fetch('/api/filaments')
        .then(r => r.json())
        .then(d => {
            sel.innerHTML = "";
            let count = 0;
            if (d.success && d.filaments) {
                const terms = term.split(' ').map(t => t.trim()).filter(t => t.length > 0);

                d.filaments.forEach(f => {
                    const name = `${f.vendor?.name || 'Generic'} ${f.material} - ${f.name || 'Unknown'}`;
                    const target = name.toLowerCase();
                    const isMatch = terms.length === 0 || terms.every(t => target.includes(t));

                    if (isMatch) {
                        sel.innerHTML += `<option value="${f.id}">${name} (ID: ${f.id})</option>`;
                        count++;
                    }
                });
                if (count === 0) sel.innerHTML = '<option disabled>No matches found</option>';
            } else {
                sel.innerHTML = '<option disabled>Error loading filaments</option>';
            }
        })
        .catch(e => {
            console.error("Filament fetch failed", e);
            sel.innerHTML = '<option disabled>Network Error</option>';
        });
};

window.wizardExistingSelected = () => {
    const sel = document.getElementById('wiz-existing-results');
    if (sel.value) {
        wizardState.selectedFilamentId = sel.value;
        document.getElementById('wiz-status-msg').innerHTML = `Selected Existing Filament ID: <strong>${sel.value}</strong>`;
        wizardValidateSubmit();
    }
};

window.wizardOpenGlobalSearch = () => {
    if (window.SearchEngine) {
        // Force the offcanvas search engine to look for Filaments if possible
        const filRadio = document.getElementById('searchTypeFilaments');
        if (filRadio) filRadio.checked = true;

        SearchEngine.open({
            mode: 'select',
            callback: (id, type) => {
                const processFilament = (filId, filData = null) => {
                    wizardState.selectedFilamentId = filId;

                    let displayString = `Filament ID: ${filId} (From Advanced Search)`;
                    if (filData) {
                        const vendor = filData.vendor ? filData.vendor.name : "Generic";
                        const mat = filData.material || "Unknown";
                        const name = filData.name || "Unnamed";
                        displayString = `${vendor} ${mat} - ${name} (ID: ${filId})`;
                        document.getElementById('wiz-status-msg').innerHTML = `Selected via Advanced Search: <strong>${displayString}</strong>`;
                    } else {
                        document.getElementById('wiz-status-msg').innerHTML = `Selected via Advanced Search (Filament ID: <strong>${filId}</strong>)`;
                    }

                    // Spoof the native select box so the UI knows
                    const sel = document.getElementById('wiz-existing-results');
                    sel.innerHTML = `<option value="${filId}" selected>${displayString}</option>`;
                    wizardValidateSubmit();
                };

                if (type === 'spool') {
                    // Extract filament ID from the spool
                    fetch(`/api/spools/${id}`)
                        .then(r => r.json())
                        .then(d => {
                            if (d.success && d.data && d.data.filament) {
                                processFilament(d.data.filament.id, d.data.filament);
                            } else {
                                alert("Could not resolve Filament from this Spool.");
                            }
                        });
                } else {
                    // Fetch full Filament details since we only have the ID from SearchEngine
                    fetch(`/api/filaments/${id}`)
                        .then(r => r.json())
                        .then(d => {
                            if (d.success && d.data) {
                                processFilament(id, d.data);
                            } else {
                                processFilament(id); // Fallback to raw ID
                            }
                        });
                }
            }
        });
    }
};

// --- EXTERNAL DATABASE LOGIC ---
window.wizardSearchExternal = (autoApplyIfSingle = false) => {
    let term = document.getElementById('wiz-search-external').value.trim();
    let source = document.getElementById('wiz-external-source').value;
    const sel = document.getElementById('wiz-external-results');

    // Auto-detect Prusament URLs
    if (term.includes('prusament.com/spool/')) {
        document.getElementById('wiz-external-source').value = 'prusament';
        source = 'prusament';
    }

    // Auto-detect Amazon URLs
    if (term.includes('amazon.com') || term.includes('/dp/')) {
        document.getElementById('wiz-external-source').value = 'amazon';
        source = 'amazon';
    }

    // Auto-detect 3D Filament Profiles URLs
    if (term.includes('3dfilamentprofiles.com')) {
        document.getElementById('wiz-external-source').value = '3dfp';
        source = '3dfp';
    }

    if (term.length < 2) return;

    sel.innerHTML = '<option disabled>Querying ' + source + '...</option>';
    document.getElementById('wiz-status-msg').innerText = "Fetching external templates...";

    fetch(`/api/external/search?source=${source}&q=${encodeURIComponent(term)}`)
        .then(r => r.json())
        .then(d => {
            sel.innerHTML = "";
            if (d.success && d.results.length > 0) {
                document.getElementById('wiz-status-msg').innerText = `Found ${d.results.length} templates.`;
                d.results.forEach(f => {
                    // Extract safe display name
                    const brand = f.manufacturer || f.vendor?.name || 'Generic';
                    const mat = f.material || '?';
                    const color = f.color_name || f.name || 'Unknown Color';
                    const wt = f.weight ? ` - ${f.weight}g` : '';
                    const diam = f.diameter || f.settings_extrusion_diameter ? ` (${f.diameter || f.settings_extrusion_diameter}mm)` : '';

                    const opt = document.createElement('option');
                    opt.value = JSON.stringify(f); // Store the full payload in the value
                    opt.innerText = `${brand} ${mat} - ${color}${wt}${diam}`;
                    sel.appendChild(opt);
                });
                // Auto-apply a lone result (e.g. a scanned/pasted Prusament URL
                // resolves to exactly one spool) so the form pre-populates without
                // a manual pick. Opt-in — the legacy "Import from External" button
                // calls wizardSearchExternal() with no arg, so it's unchanged.
                if (autoApplyIfSingle && d.results.length === 1 && typeof window.wizardExternalSelected === 'function') {
                    sel.selectedIndex = 0;
                    window.wizardExternalSelected();
                }
            } else {
                sel.innerHTML = '<option disabled>No external templates found.</option>';
                document.getElementById('wiz-status-msg').innerText = "Search returned 0 results.";
            }
        })
        .catch(e => {
            console.error("External DB fetch failed", e);
            sel.innerHTML = '<option disabled>Error fetching from database.</option>';
            document.getElementById('wiz-status-msg').innerText = "Network Error.";
        });
};

// Filament-level fill — material/color/temps/vendor/template weights.
// Extracted from wizardExternalSelected so the per-spool scan flow can call
// just the spool half without re-touching Step 2.
window.applyFilamentFieldsFromTemplate = (temp) => {
    wizardState.externalMetaData = temp;

    // Split the parser's "full" material string ("PC Blend Carbon Fiber")
    // into a base material ("PC") + canonical filament_attributes
    // (["Blend", "Carbon Fiber"]). Spoolman's filtering only works on the
    // native material field, so the base is what should land there;
    // modifiers ride along as multi-choice extras for downstream display
    // and to satisfy the duplicate-detection matcher.
    const known = _knownFilamentAttributes();
    const split = window.splitMaterialAndAttributes(temp.material || '', known);
    document.getElementById('wiz-fil-material').value = split.base || temp.material || '';

    // Replace any existing chips for filament_attributes with the parsed
    // set. Keeps applyFilamentFieldsFromTemplate idempotent — calling it
    // again with different scan data fully replaces the form state instead
    // of accumulating attrs from prior scans.
    const chipContainer = document.getElementById('chip-container-fil-filament_attributes');
    if (chipContainer) {
        chipContainer.querySelectorAll('.dynamic-chip[data-key="filament_attributes"]').forEach(c => c.remove());
    }
    if (window.wizardAddMultiChoiceChip) {
        split.attrs.forEach(attr => {
            window.wizardAddMultiChoiceChip('fil', 'filament_attributes', attr);
        });
    }

    document.getElementById('wiz-fil-color_name').value = temp.color_name || temp.name || '';

    let colorPayload = temp.multi_color_hexes || temp.color_hexes || temp.color_hex || 'FFFFFF';
    let colorDirection = temp.multi_color_direction || 'longitudinal';
    if (window.wizardPopulateColors) window.wizardPopulateColors(colorPayload, colorDirection);

    document.getElementById('wiz-fil-diameter').value = temp.diameter || temp.settings_extrusion_diameter || 1.75;
    document.getElementById('wiz-fil-density').value = temp.density || temp.settings_density || 1.24;
    document.getElementById('wiz-fil-weight').value = temp.weight || 1000;
    document.getElementById('wiz-fil-empty_weight').value = temp.spool_weight || '';

    if (document.getElementById('wiz-fil-settings_extruder_temp')) {
        document.getElementById('wiz-fil-settings_extruder_temp').value = temp.settings_extruder_temp || '';
    }
    if (document.getElementById('wiz-fil-settings_bed_temp')) {
        document.getElementById('wiz-fil-settings_bed_temp').value = temp.settings_bed_temp || '';
    }
    if (document.getElementById('wiz-fil-nozzle_temp_max')) {
        const nozMax = (temp.extra && temp.extra.nozzle_temp_max) || temp.nozzle_temp_max || '';
        document.getElementById('wiz-fil-nozzle_temp_max').value = nozMax;
    }
    if (document.getElementById('wiz-fil-bed_temp_max')) {
        const bedMax = (temp.extra && temp.extra.bed_temp_max) || temp.bed_temp_max || '';
        document.getElementById('wiz-fil-bed_temp_max').value = bedMax;
    }

    // The wizard's filament extras (product_url, purchase_url) are rendered
    // by wizardFetchExtraFields as dynamic inputs with IDs of the shape
    // wiz_fil_ef_<key> (underscores). Writing to legacy `wiz-fil-product_url`
    // (hyphens) was a no-op — the static element has been gone for ages and
    // the wizardSubmit collector at line ~1610 only picks up `.dynamic-extra-field`
    // values. Hit the dynamic IDs directly so the URL actually rides along
    // when the wizard saves.
    if (temp.external_link) {
        const filUrlNode = document.getElementById('wiz_fil_ef_product_url');
        if (filUrlNode) filUrlNode.value = temp.external_link;
        // L351: also preload the spool's OWN product_url input so the scraped
        // product link is visible + editable per-spool (parity with the
        // purchase_url preload below).
        const spProductNode = document.getElementById('wiz-spool-product_url');
        if (spProductNode) { spProductNode.value = temp.external_link; spProductNode.placeholder = 'https://...'; }
    }
    if (temp.purchase_link) {
        // Group 10.4 — purchase_url is no longer rendered on the filament
        // tab. Preload the spool's purchase_url input instead so the user
        // sees the parser-scraped URL and can edit / clear it before save.
        // (The filament-side silent fill on save in computeFilamentSilentExtras
        // also handles the filament-level persist; this just adds the UI side.)
        const spPurchaseNode = document.getElementById('wiz-spool-purchase_url');
        if (spPurchaseNode) {
            spPurchaseNode.value = temp.purchase_link;
            spPurchaseNode.placeholder = 'https://...';
        }
    }

    const vName = temp.manufacturer || temp.vendor?.name;
    if (vName) {
        const match = (wizardState.vendors || []).find(v => (v.name || '').toLowerCase() === vName.toLowerCase());
        if (match) {
            window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', String(match.id), match.name);
        } else {
            // Parser returned a vendor we don't have yet. Leave the name in the
            // search input so the user can either pick a close match from the
            // dropdown or click ➕ (the create button pre-fills from this
            // input's value). The legacy add-new toggle path was retired
            // with the Group 6.2 cleanup.
            const searchEl = document.getElementById('wiz-fil-vendor-search');
            if (searchEl) searchEl.value = vName;
            const hidden = document.getElementById('wiz-fil-vendor-sel');
            if (hidden) {
                hidden.value = '';
                hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    }
};

// Spool-level extract — returns the per-spool override dict the wizard
// will merge onto each created spool. Does NOT touch the DOM.
window.extractSpoolFieldsFromTemplate = (temp) => {
    const override = { extra: {} };
    if (temp.weight !== undefined && temp.weight !== null && !Number.isNaN(Number(temp.weight))) {
        override.initial_weight = Number(temp.weight);
    }
    if (temp.spool_weight !== undefined && temp.spool_weight !== null && Number(temp.spool_weight) > 0) {
        override.spool_weight = Number(temp.spool_weight);
    }
    // Spoolman text-type extras must arrive as JSON-quoted strings (e.g. the
    // 5 bytes `"348"` including literal quote chars). sanitize_outbound_data
    // runs json.loads on each value and `"348"` parses as the integer 348,
    // which Spoolman then rejects with "Value is not a string." Wrap in
    // literal quotes here, matching the inv_details.js Edit Filament pattern
    // and the nozzle_temp_max handling in wizardSubmit at line ~1493.
    if (temp.external_link) {
        // product_url is a Spoolman *extra* on Spool, not a native field —
        // sending it at top-level made Spoolman silently drop it. Send the
        // raw URL — sanitize_outbound_data wraps JSON_STRING_FIELDS (which
        // includes product_url and purchase_url) via json.dumps for us.
        // Pre-wrapping here would double-wrap and the literal quote chars
        // would leak into the UI on read-back.
        override.extra.product_url = temp.external_link;
    }
    // purchase_url is the canonical Prusa3D storefront link — scraped by
    // the parser from a "Buy now" link on the spool page. Falls back to
    // the per-spool URL only when the scrape didn't find anything, so
    // the field is never blank for a successful Prusament scan.
    if (temp.purchase_link) {
        override.extra.purchase_url = temp.purchase_link;
    } else if (temp.external_link) {
        override.extra.purchase_url = temp.external_link;
    }
    const mfgDate = temp.extra && temp.extra.prusament_manufacturing_date;
    if (mfgDate) override.extra.prusament_manufacturing_date = `"${mfgDate}"`;
    const lengthM = temp.extra && temp.extra.prusament_length_m;
    if (lengthM !== undefined && lengthM !== null && lengthM !== '') {
        override.extra.prusament_length_m = `"${lengthM}"`;
    }
    if (Object.keys(override.extra).length === 0) delete override.extra;
    return override;
};

window.wizardExternalSelected = () => {
    const sel = document.getElementById('wiz-external-results');
    if (sel.value) {
        try {
            const temp = JSON.parse(sel.value);

            // Same duplicate-detect + auto-switch + backfill flow used by
            // the per-spool Prusament scan. Without this, a user who hit
            // the legacy Step-2 "Import from External" button instead of
            // the Step-3 row scan would skip every safeguard we added —
            // duplicate filaments would still get created, existing
            // filaments wouldn't get their missing fields filled in.
            //
            // The gate accepts BOTH 'manual' (fresh wizard, user typing a
            // new filament) AND 'external' (the user clicked "Import from
            // External Database" — which sets mode='external' via
            // wizardSelectType). Both paths land here and both can lead
            // to a duplicate-filament create if we don't run the matcher.
            const canMatch = (wizardState.mode === 'manual' || wizardState.mode === 'external');
            if (!wizardState.filamentLockedFromScan && canMatch) {
                const matches = window.findFilamentMatches(temp);
                if (matches.length === 0) {
                    window.applyFilamentFieldsFromTemplate(temp);
                } else if (matches.definitive) {
                    window.wizardAutoSwitchToExisting(matches[0], temp);
                } else {
                    // Multiple basic-gate matches with no Tier-1 product-ID
                    // disambiguator — defer to the user via the picker.
                    window.wizardRenderDuplicatePicker(matches, temp);
                }
                wizardState.filamentLockedFromScan = true;
            } else {
                window.applyFilamentFieldsFromTemplate(temp);
            }

            // Legacy "Import from External" button also drops the source URL into
            // the Spool's product_url field as a default for non-per-spool flows.
            if (temp.external_link) {
                const spoolUrlNode = document.getElementById('wiz-spool-product_url');
                if (spoolUrlNode) spoolUrlNode.value = temp.external_link;
            }

            wizardValidateSubmit();
        } catch (e) { console.error("Could not parse external data payload", e); }
    }
};

window.wizardSubmit = async () => {
    document.getElementById('btn-wiz-submit').disabled = true;
    const msg = document.getElementById('wiz-status-msg');
    msg.innerText = "Processing...";

    const getVal = (id) => {
        const el = document.getElementById(id);
        if (!el) throw new Error(`Missing DOM Element: ${id}`);
        return el.value;
    };

    try {
        const qty = parseInt(getVal('wiz-spool-qty')) || 1;

        // Construct Spool Payload
        let sp_payload = {
            used_weight: getVal('wiz-spool-used') !== "" ? parseFloat(getVal('wiz-spool-used')) : 0,
            spool_weight: getVal('wiz-spool-empty_weight') !== "" ? parseFloat(getVal('wiz-spool-empty_weight')) : null,
            initial_weight: getVal('wiz-spool-initial_weight') !== "" ? parseFloat(getVal('wiz-spool-initial_weight')) : null,
            location: getVal('wiz-spool-location') || '',
            comment: getVal('wiz-spool-comment') || '',
            price: getVal('wiz-spool-price') !== "" ? parseFloat(getVal('wiz-spool-price')) : null,
            archived: document.getElementById('wiz-spool-archived')?.checked || false,
            extra: {}
        };

        // Purchase Link (Spool Extra)
        const purchaseUrl = document.getElementById('wiz-spool-purchase_url')?.value?.trim();
        if (purchaseUrl) sp_payload.extra.purchase_url = purchaseUrl;

        // Product Link (Spool Extra). L351 — gated on a truthy typed value, so an
        // empty input never clobbers a product_url supplied by a Prusament-scan
        // override or inherited via the filament fallback (ghost placeholder).
        const productUrl = document.getElementById('wiz-spool-product_url')?.value?.trim();
        if (productUrl) sp_payload.extra.product_url = productUrl;

        // Extract Dynamic Spool Fields
        document.querySelectorAll('.dynamic-extra-spool-field').forEach(el => {
            const key = el.getAttribute('data-key');
            if (!key) return;
            if (el.type === 'checkbox') {
                sp_payload.extra[key] = el.checked;
            } else if (el.value) {
                sp_payload.extra[key] = el.value;
            }
        });

        Object.keys(sp_payload).forEach(k => { if (sp_payload[k] === undefined || sp_payload[k] === null || Number.isNaN(sp_payload[k])) delete sp_payload[k]; });

        let f_payload = null;
        let target_fid = null;

        if (wizardState.mode === 'existing') {
            target_fid = wizardState.selectedFilamentId;
        } else {
            if (wizardState.mode === 'edit_spool') {
                target_fid = wizardState.selectedFilamentId; // Pass through ID so backend knows which Filament to update
            }
            // Hex Parsing for Multiple Colors
            const colorInputs = Array.from(document.querySelectorAll('input[id^="wiz-fil-color_hex_"]'));
            const colors = colorInputs.map(i => i.value.replace('#', '').toUpperCase()).filter(c => c.length === 6);

            f_payload = {
                name: getVal('wiz-fil-color_name') || 'Unknown',
                material: getVal('wiz-fil-material') || 'PLA',
                weight: getVal('wiz-fil-weight') !== "" ? parseFloat(getVal('wiz-fil-weight')) : 1000,
                spool_weight: getVal('wiz-fil-empty_weight') !== "" ? parseFloat(getVal('wiz-fil-empty_weight')) : null,
                diameter: getVal('wiz-fil-diameter') !== "" ? parseFloat(getVal('wiz-fil-diameter')) : 1.75,
                density: getVal('wiz-fil-density') !== "" ? parseFloat(getVal('wiz-fil-density')) : 1.24,
                color_hex: colors.length > 0 ? colors[0] : 'FFFFFF',
                settings_extruder_temp: getVal('wiz-fil-settings_extruder_temp') !== "" ? parseInt(getVal('wiz-fil-settings_extruder_temp')) : null,
                settings_bed_temp: getVal('wiz-fil-settings_bed_temp') !== "" ? parseInt(getVal('wiz-fil-settings_bed_temp')) : null,
                extra: {}
            };

            // Spoolman extras of type "text" must arrive as JSON-quoted strings
            // (`"245"` — 5 bytes including literal quote chars). spoolman_api's
            // sanitize_outbound_data runs json.loads on each value: a raw "245"
            // parses as the integer 245 and Spoolman rejects with
            // "Value is not a string." Match the Edit Filament pattern at
            // inv_details.js:1617 by wrapping in literal quotes.
            if (getVal('wiz-fil-nozzle_temp_max') !== "") {
                f_payload.extra.nozzle_temp_max = `"${getVal('wiz-fil-nozzle_temp_max')}"`;
            }
            if (getVal('wiz-fil-bed_temp_max') !== "") {
                f_payload.extra.bed_temp_max = `"${getVal('wiz-fil-bed_temp_max')}"`;
            }

            // Cross-Inherit empty-spool-weight along the chain: Spool → Filament → Vendor.
            // Resolves the selected vendor from wizardState so a manufacturer-level weight
            // flows down even when both Filament and Spool fields are left blank.
            {
                const selectedVendorId = document.getElementById('wiz-fil-vendor-sel')?.value;
                const vendor = selectedVendorId
                    ? (wizardState.vendors || []).find(v => String(v.id) === String(selectedVendorId))
                    : null;
                const resolved = resolveEmptySpoolWeight({
                    spoolWt: sp_payload.spool_weight,
                    filamentWt: f_payload.spool_weight,
                    vendor,
                });
                if (resolved !== null) {
                    if (sp_payload.spool_weight === null) sp_payload.spool_weight = resolved;
                    if (f_payload.spool_weight === null) f_payload.spool_weight = resolved;
                }
            }

            // Note: Spoolman 0.19.1 natively supports `multi_color_hexes` 
            if (colors.length > 1) {
                f_payload.multi_color_direction = document.getElementById('wiz-fil-color-direction').value;
                f_payload.multi_color_hexes = colors.join(',');
                delete f_payload.color_hex; // FATAL ERROR PREVENTION: Spoolman schema prevents both
            } else {
                f_payload.multi_color_hexes = null;
                f_payload.multi_color_direction = null;
            }
            // Extract Custom Dynamic Fields (Standard and Checkboxes)
            document.querySelectorAll('.dynamic-extra-field').forEach(el => {
                const key = el.getAttribute('data-key');
                if (!key) return;

                if (el.type === 'checkbox') {
                    f_payload.extra[key] = el.checked;
                } else if (el.value) {
                    f_payload.extra[key] = el.value;
                }
            });

            // Extract Custom Dynamic Fields (Chips)
            document.querySelectorAll('.dynamic-chip[data-selected="true"]').forEach(el => {
                const key = el.getAttribute('data-key');
                const val = el.getAttribute('data-value');
                if (!key || !val) return;

                if (!f_payload.extra[key]) f_payload.extra[key] = [];
                f_payload.extra[key].push(val);
            });

            // Vendor selection. The ➕ button now opens the Vendor Edit modal
            // in create mode and auto-selects the new vendor on save, so by the
            // time the user reaches submit there's always either a real
            // vendor_id selected or nothing (deliberate Generic). The legacy
            // extras.external_vendor_name path was retired in Group 6.2.
            if (getVal('wiz-fil-vendor-sel')) {
                f_payload.vendor_id = parseInt(getVal('wiz-fil-vendor-sel'));
            }

            if (wizardState.mode === 'external' && wizardState.externalMetaData) {
                const t = wizardState.externalMetaData;
                if (t.extruder_temp && !getVal('wiz-fil-settings_extruder_temp')) f_payload.settings_extruder_temp = t.extruder_temp;
                if (t.bed_temp && !getVal('wiz-fil-settings_bed_temp')) f_payload.settings_bed_temp = t.bed_temp;
                const extNozMax = (t.extra && t.extra.nozzle_temp_max) || t.nozzle_temp_max;
                const extBedMax = (t.extra && t.extra.bed_temp_max) || t.bed_temp_max;
                if (extNozMax && !getVal('wiz-fil-nozzle_temp_max')) f_payload.extra.nozzle_temp_max = `"${String(extNozMax)}"`;
                if (extBedMax && !getVal('wiz-fil-bed_temp_max')) f_payload.extra.bed_temp_max = `"${String(extBedMax)}"`;
                if (t.article_number) f_payload.article_number = t.article_number;
            }

            Object.keys(f_payload).forEach(k => { 
                if (f_payload[k] === undefined || Number.isNaN(f_payload[k])) delete f_payload[k]; 
                else if (f_payload[k] === null && k !== 'multi_color_hexes' && k !== 'multi_color_direction') delete f_payload[k];
            });
        }

        // Per-spool overrides from the Step-3 Prusament scan rows. When at least
        // one row scanned successfully, the backend uses the override list to drive
        // the spool count + per-spool field merge instead of `quantity`.
        let spool_overrides = null;
        if (wizardState.spoolRows && wizardState.spoolRows.length > 0) {
            const blocking = wizardState.spoolRows.some(r => r.status === 'pending' || r.status === 'error');
            if (blocking) {
                msg.innerHTML = '<span class="text-danger fw-bold">⚠ One or more spool scans failed or are still loading. Fix or clear them before creating.</span>';
                document.getElementById('btn-wiz-submit').disabled = false;
                return;
            }
            const anyOk = wizardState.spoolRows.some(r => r.status === 'ok');
            if (anyOk && wizardState.mode !== 'edit_spool') {
                spool_overrides = wizardState.spoolRows.map(r => r.override || {});
            }
        }

        const payload = {
            spool_id: wizardState.editSpoolId, // Used by Edit router
            filament_id: target_fid,
            filament_data: f_payload,
            spool_data: sp_payload,
            quantity: qty
        };
        if (spool_overrides) payload.spool_overrides = spool_overrides;

        const endpoint = wizardState.mode === 'edit_spool' ? '/api/edit_spool_wizard' : '/api/create_inventory_wizard';

        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.success) {
            wizardState.isDirty = false;
            msg.innerHTML = `<span class="text-success fw-bold">Success! ${wizardState.mode === 'edit_spool' ? 'Spool Updated' : 'Spool(s) Generated'}.</span>`;
            // 17.3 follow-up: render queue-label chips into the dedicated
            // `wiz-postcreate-actions` row in the modal footer (alongside
            // Cancel + Create Inventory) so subsequent status-message
            // overwrites — like the post-success "Make a change to add
            // more..." auto-prompt three seconds later — can't clobber
            // them before the user gets a chance to click. Only fires
            // on create (edit-spool mode doesn't carry created_spools).
            const actionRow = document.getElementById('wiz-postcreate-actions');
            if (actionRow) actionRow.innerHTML = '';
            if (actionRow && wizardState.mode !== 'edit_spool' && Array.isArray(data.created_spools) && data.created_spools.length) {
                const labelEl = document.createElement('span');
                labelEl.className = 'small text-light fw-bold me-2';
                labelEl.innerText = 'Queue label:';
                actionRow.appendChild(labelEl);
                data.created_spools.forEach(sid => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'btn btn-sm btn-outline-info fw-bold fcc-wiz-queue-label';
                    btn.dataset.spoolId = String(sid);
                    btn.title = `Queue a print label for Spool #${sid}`;
                    btn.innerText = `🖨️ #${sid}`;
                    btn.addEventListener('click', (ev) => {
                        ev.preventDefault();
                        if (!sid || typeof window.addToQueue !== 'function') return;
                        if (Array.isArray(window.labelQueue) && window.labelQueue.find(q => q.id === sid && q.type === 'spool')) {
                            if (typeof showToast === 'function') showToast(`Spool #${sid} already in queue`, 'info', 2000);
                            return;
                        }
                        window.addToQueue({ id: sid, type: 'spool', display: `Spool #${sid}` });
                        if (typeof showToast === 'function') showToast(`Queued label for Spool #${sid}`, 'success', 2500);
                        btn.classList.remove('btn-outline-info');
                        btn.classList.add('btn-success');
                        btn.disabled = true;
                    });
                    actionRow.appendChild(btn);
                });
            }
            document.dispatchEvent(new CustomEvent('inventory:sync-pulse')); // Instantly trigger UI rebinding across all open panels

            // Reset Weigh-Out Protocol tracking on save so subsequent saves don't double-dip
            if (wizardState.mode === 'edit_spool') {
                const recentInput = document.getElementById('wiz-spool-recent-usage');
                if (recentInput && recentInput.value) {
                    recentInput.value = '';
                    wizardState.original_used_weight = parseFloat(document.getElementById('wiz-spool-used').value) || 0;
                    
                    // Visual feedback flash (accounting for Bootstrap !important classes)
                    const remInput = document.getElementById('wiz-spool-remaining');
                    if (remInput) {
                        remInput.style.transition = "background-color 0.4s ease-out";
                        remInput.classList.remove('bg-dark');
                        remInput.classList.add('bg-success', 'text-white');
                        setTimeout(() => { 
                            remInput.classList.remove('bg-success', 'text-white');
                            remInput.classList.add('bg-dark'); 
                        }, 800);
                    }
                }
            }

            // Keep modal open across all modes so user can rapidly create subsequent items —
            // but don't let them accidentally re-submit the same spools. After a non-edit
            // success, clear the per-spool scan URLs + reset bulk quantity to 1 + leave
            // submit disabled until the user makes a change. The existing input/change
            // listener flips lockedAfterSuccess off and re-enables submit on next edit.
            if (wizardState.mode !== 'edit_spool') {
                wizardState.lockedAfterSuccess = true;
                // Reset quantity FIRST so the row reset rebuilds at the new size.
                // Reversed order rebuilt rows at the OLD count and left submit
                // enabled because the row sync re-ran wizardValidateSubmit.
                const qtyEl = document.getElementById('wiz-spool-qty');
                if (qtyEl) qtyEl.value = 1;
                if (window.wizardResetSpoolRows) window.wizardResetSpoolRows();
                setTimeout(() => {
                    if (wizardState.lockedAfterSuccess) {
                        msg.innerHTML = `<span class="text-info">Make a change to add more — submit is locked until you scan, edit, or pick a new filament.</span>`;
                    }
                }, 3000);
                // Submit stays disabled. The dirty-listener below re-enables it when
                // the user edits any field in the wizard.
            } else {
                setTimeout(() => {
                    msg.innerHTML = "";
                    document.getElementById('btn-wiz-submit').disabled = false;
                }, 3000);
            }

        } else {
            msg.innerHTML = `<span class="text-danger">Error: ${data.msg}</span>`;
            document.getElementById('btn-wiz-submit').disabled = false;
        }
    } catch (e) {
        console.error("Wizard Submit Error:", e);
        msg.innerHTML = `<span class="text-danger">Frontend Error: ${e.message}</span>`;
        document.getElementById('btn-wiz-submit').disabled = false;
    }
};

// --- SPOOL CLONE LOGIC ---
window.openCloneWizard = async (spoolId) => {
    // Group 10.11: source-aware return-id — only set when an actual details
    // modal is visible at launch. Clone launched from search/grid/loc-mgr
    // leaves return-ids null so the wizard closes silently on cancel rather
    // than popping an unexpected details modal.
    const filModal = document.getElementById('filamentModal');
    const spoolModal = document.getElementById('spoolModal');
    const filVisible = filModal && filModal.classList.contains('show');
    const spoolVisible = spoolModal && spoolModal.classList.contains('show');
    if (filVisible) {
        const fid = document.getElementById('fil-detail-id')?.innerText;
        if (fid) {
            wizardState.returnToFilamentId = fid;
            wizardState.returnToSpoolId = null;
        }
    } else if (spoolVisible) {
        wizardState.returnToSpoolId = spoolId;
        wizardState.returnToFilamentId = null;
    } else {
        wizardState.returnToSpoolId = null;
        wizardState.returnToFilamentId = null;
    }

    // Reset and Open Wizard (Wait for Extrad fields DOM injection!)
    await openWizardModal();
    wizardSetContextLabel({ action: 'Cloning', spoolId });

    // Temporarily disable submit while fetching clone data
    document.getElementById('btn-wiz-submit').disabled = true;
    document.getElementById('wiz-status-msg').innerHTML = '<span class="text-warning">Cloning spool data...</span>';

    // Fetch Spool data to clone
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            if (!d || !d.filament) {
                document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to fetch clone data.</span>';
                return;
            }

            // Switch to Existing Filament Mode without wiping
            wizardSelectType('existing', true);

            // Inject Filament into Dropdown & Auto-Select
            const f = d.filament;
            wizardSetContextLabel({ action: 'Cloning from', spoolId, filamentId: f.id });
            const name = `${f.vendor?.name || 'Generic'} ${f.material} - ${f.name || 'Unknown'}`;
            const sel = document.getElementById('wiz-existing-results');
            sel.innerHTML = `<option value="${f.id}" selected>${name} (ID: ${f.id})</option>`;
            wizardExistingSelected();

            // Pre-fill Spool parameters that usually carry over when cloning
            {
                const locId = d.location || "";
                const locRec = (wizardState.locations || []).find(l => l.LocationID === locId);
                window.wizardComboboxSet(
                    'wiz-spool-location-search', 'wiz-spool-location', locId,
                    locRec ? (locRec.Name ? `${locRec.Name} (${locRec.LocationID})` : locRec.LocationID) : locId
                );
            }
            // Spool Weight: walk Spool → Filament → Vendor so a clone picks up whichever level is populated.
            {
                const { value, source } = resolveEmptySpoolWeightSource({
                    spoolWt: d.spool_weight,
                    filamentWt: d.filament?.spool_weight,
                    vendor: d.filament?.vendor,
                });
                window.wizardSetSpoolEmptyWeightInherited(value, source);
            }
            document.getElementById('wiz-spool-used').value = 0; // Fresh spool is usually 0
            document.getElementById('wiz-spool-comment').value = d.comment || "";
            // Price & Purchase Link
            window.wizardPrefillSpoolPrice(d.price, d.filament && d.filament.price);
            // Group 10.4 smart fallback: only prefill with the spool's OWN
            // purchase_url. If the spool has none but the filament does,
            // surface the filament URL as ghost placeholder text — saving
            // without typing leaves the spool override blank so the details
            // modal continues to fall back to the filament's value.
            wizardApplyPurchaseLinkFallback(d.extra?.purchase_url, d.filament?.extra?.purchase_url);
            wizardApplyProductLinkFallback(d.extra?.product_url, d.filament?.extra?.product_url);
            if (document.getElementById('wiz-spool-archived')) {
                document.getElementById('wiz-spool-archived').checked = false;
            }
            window.wizardCalcRemainingFromUsed();

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">Wizard successfully pre-filled from Spool #${spoolId}.</span>`;
            if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('edit');
        })
        .catch(err => {
            console.error("Clone Wizard Error:", err);
            document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to connect for clone.</span>';
            document.getElementById('btn-wiz-submit').disabled = false;
        });
};

// --- NEW SPOOL FROM FILAMENT LOGIC ---
window.openNewSpoolFromFilamentWizard = async (filamentId) => {
    // Track filament for re-opening detail modal after wizard closes
    wizardState.returnToFilamentId = filamentId;
    wizardState.returnToSpoolId = null;

    // Reset and Open Wizard (Wait for Extra fields DOM injection!)
    await openWizardModal();
    wizardSetContextLabel({ action: 'New Spool for', filamentId });

    // Temporarily disable submit while fetching data
    document.getElementById('btn-wiz-submit').disabled = true;
    document.getElementById('wiz-status-msg').innerHTML = '<span class="text-warning">Loading filament data...</span>';

    fetch(`/api/filament_details?id=${filamentId}`)
        .then(r => r.json())
        .then(d => {
            if (!d || !d.id) {
                document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to fetch filament data.</span>';
                return;
            }

            // Switch to Existing Filament Mode without wiping
            wizardSelectType('existing', true);

            // Inject Filament into Dropdown & Auto-Select
            const name = `${d.vendor?.name || 'Generic'} ${d.material} - ${d.name || 'Unknown'}`;
            const sel = document.getElementById('wiz-existing-results');
            sel.innerHTML = `<option value="${d.id}" selected>${name} (ID: ${d.id})</option>`;
            wizardExistingSelected();

            // Smart defaults for fresh spool
            document.getElementById('wiz-spool-used').value = 0;
            if (document.getElementById('wiz-spool-archived')) {
                document.getElementById('wiz-spool-archived').checked = false;
            }

            // L34: pre-fill spool empty-weight from filament/vendor cascade on
            // open. New spools have no spool_weight of their own yet, so the
            // resolved source will be 'filament' or 'vendor' — show the badge
            // so the user knows where the value came from.
            {
                const { value, source } = resolveEmptySpoolWeightSource({
                    filamentWt: d.spool_weight,
                    vendor: d.vendor,
                });
                window.wizardSetSpoolEmptyWeightInherited(value, source);
            }
            // L349: a brand-new spool has no price of its own — inherit the
            // filament's (d is the filament here, so d.price is the fallback).
            window.wizardPrefillSpoolPrice(null, d.price);
            // L351: show the filament's product link as inherited ghost text.
            wizardApplyProductLinkFallback(null, d.extra?.product_url);

            window.wizardCalcRemainingFromUsed();

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">Wizard successfully pre-filled from Filament #${filamentId}.</span>`;
            if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('edit');
        })
        .catch(err => {
            console.error("New Spool from Filament Wizard Error:", err);
            document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to connect.</span>';
            document.getElementById('btn-wiz-submit').disabled = false;
        });
};

// --- SPOOL EDIT LOGIC ---
window.openEditWizard = async (spoolId) => {
    // Group 10.11: only re-open a details modal on cancel/close if one was
    // ACTUALLY visible at launch. Previously the `else` branch set
    // returnToSpoolId unconditionally — so launching the wizard from the
    // search FAB or Location Manager (no details modal open) still popped the
    // spool details modal on cancel. Now we leave both return-ids null when
    // there's no source details modal to return to.
    const filModal = document.getElementById('filamentModal');
    const spoolModal = document.getElementById('spoolModal');
    const filVisible = filModal && filModal.classList.contains('show');
    const spoolVisible = spoolModal && spoolModal.classList.contains('show');
    if (filVisible) {
        const fid = document.getElementById('fil-detail-id')?.innerText;
        if (fid) {
            wizardState.returnToFilamentId = fid;
            wizardState.returnToSpoolId = null;
        }
    } else if (spoolVisible) {
        wizardState.returnToSpoolId = spoolId;
        wizardState.returnToFilamentId = null;
    } else {
        wizardState.returnToSpoolId = null;
        wizardState.returnToFilamentId = null;
    }

    // Reset and Open Wizard (Wait for dynamically mapped DOM structures first!)
    await openWizardModal();
    wizardSetContextLabel({ action: 'Editing', spoolId });

    // Temporarily disable submit while fetching edit data
    document.getElementById('btn-wiz-submit').disabled = true;
    document.getElementById('wiz-status-msg').innerHTML = '<span class="text-warning">Loading spool data for edit...</span>';

    // Change Button Text
    const submitBtn = document.getElementById('btn-wiz-submit');
    submitBtn.innerText = "SAVE CHANGES";
    submitBtn.classList.replace('btn-success', 'btn-primary');

    // Fetch Spool data to edit
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            if (!d || !d.filament) {
                document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to fetch spool data.</span>';
                return;
            }

            // Custom UI State for Edit
            wizardState.mode = 'edit_spool';
            wizardState.editSpoolId = spoolId;
            wizardState.selectedFilamentId = d.filament.id;
            wizardSetContextLabel({ action: 'Editing', spoolId, filamentId: d.filament.id });

            // Hide Step 1 completely
            const step1 = document.getElementById('step-1-material');
            if (step1) step1.style.display = 'none';
            // Show Step 2 and Step 3
            document.getElementById('step-2-filament').style.display = 'block';
            document.getElementById('step-3-spool').style.display = 'block';
            document.getElementById('step-3-spool').style.opacity = '1';

            // Hide the Bulk Quantity box
            const qtyBox = document.getElementById('wiz-spool-qty');
            if (qtyBox && qtyBox.parentElement) qtyBox.parentElement.style.display = 'none';
            if (qtyBox) qtyBox.value = 1;

            const f = d.filament;
            // Pre-fill Filament
            if (f.vendor) {
                const match = (wizardState.vendors || []).find(v => (v.name || '').toLowerCase() === (f.vendor.name || '').toLowerCase());
                if (match) {
                    window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', String(match.id), match.name);
                } else {
                    // Vendor on the source record isn't in the local cache.
                    // Leave the name in the search box so the user can either
                    // pick a close match or click ➕ to create. (Legacy
                    // add-new toggle was retired with Group 6.2 cleanup.)
                    const searchEl = document.getElementById('wiz-fil-vendor-search');
                    if (searchEl) searchEl.value = f.vendor.name || '';
                    window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '', f.vendor.name || '');
                }
            } else {
                window.wizardComboboxSet('wiz-fil-vendor-search', 'wiz-fil-vendor-sel', '', '');
            }

            document.getElementById('wiz-fil-material').value = f.material || '';
            document.getElementById('wiz-fil-color_name').value = f.name || '';
            
            let colorPayload = f.multi_color_hexes || (f.extra && f.extra.color_hexes) || f.color_hex || 'FFFFFF';
            let colorDirection = f.multi_color_direction || (f.extra && f.extra.multi_color_direction) || 'longitudinal';
            if (window.wizardPopulateColors) window.wizardPopulateColors(colorPayload, colorDirection);
            
            document.getElementById('wiz-fil-diameter').value = f.diameter || 1.75;
            document.getElementById('wiz-fil-density').value = f.density || 1.24;
            document.getElementById('wiz-fil-weight').value = f.weight || 1000;
            {
                // Inherit empty-spool-weight from the vendor if the filament's own value is blank/0.
                const resolved = resolveEmptySpoolWeight({ filamentWt: f.spool_weight, vendor: f.vendor });
                document.getElementById('wiz-fil-empty_weight').value = resolved !== null ? resolved : '';
            }

            // Map Temperatures
            if (document.getElementById('wiz-fil-settings_extruder_temp')) {
                document.getElementById('wiz-fil-settings_extruder_temp').value = f.settings_extruder_temp || '';
            }
            if (document.getElementById('wiz-fil-settings_bed_temp')) {
                document.getElementById('wiz-fil-settings_bed_temp').value = f.settings_bed_temp || '';
            }
            if (document.getElementById('wiz-fil-nozzle_temp_max')) {
                const nozMax = f.extra && f.extra.nozzle_temp_max;
                document.getElementById('wiz-fil-nozzle_temp_max').value = typeof nozMax === 'string' ? nozMax.replace(/^"|"$/g, '') : (nozMax || '');
            }
            if (document.getElementById('wiz-fil-bed_temp_max')) {
                const bedMax = f.extra && f.extra.bed_temp_max;
                document.getElementById('wiz-fil-bed_temp_max').value = typeof bedMax === 'string' ? bedMax.replace(/^"|"$/g, '') : (bedMax || '');
            }

            // Filament Extra
            if (f.extra) {
                Object.entries(f.extra).forEach(([k, v]) => {
                    const input = document.getElementById(`wiz_fil_ef_${k}`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = v === true || v === 'true';
                        } else if (input.classList.contains('sync-source-fil') && document.getElementById(`chip-container-fil-${k}`)) {
                            // Populate chips (Coerce strings to Arrays if necessary)
                            let parsedArr = [];
                            if (Array.isArray(v)) {
                                parsedArr = v;
                            } else if (typeof v === 'string') {
                                if (v.startsWith('[') && v.endsWith(']')) {
                                    try { parsedArr = JSON.parse(v); } catch (e) { parsedArr = [v]; }
                                } else {
                                    parsedArr = v.split(',').map(s => s.trim()).filter(s => s);
                                }
                            } else {
                                parsedArr = [v];
                            }

                            const cContainer = document.getElementById(`chip-container-fil-${k}`);
                            cContainer.innerHTML = '';
                            parsedArr.forEach(val => {
                                const chipHtml = `<span class="badge rounded-pill text-bg-primary border border-primary cursor-pointer dynamic-chip" 
                                                       onclick="this.remove()" data-key="${k}" data-selected="true" data-value="${val}">${val} &times;</span>`;
                                cContainer.insertAdjacentHTML('beforeend', chipHtml);
                            });
                        } else {
                            input.value = v;
                        }
                    }
                });
            }

            // Pre-fill Spool
            {
                const locId = d.location || "";
                const locRec = (wizardState.locations || []).find(l => l.LocationID === locId);
                window.wizardComboboxSet(
                    'wiz-spool-location-search', 'wiz-spool-location', locId,
                    locRec ? (locRec.Name ? `${locRec.Name} (${locRec.LocationID})` : locRec.LocationID) : locId
                );
            }
            {
                // Walk the chain: spool → filament → vendor. A blank spool inherits
                // from its filament, then its manufacturer's empty_spool_weight.
                const { value, source } = resolveEmptySpoolWeightSource({
                    spoolWt: d.spool_weight,
                    filamentWt: d.filament?.spool_weight,
                    vendor: d.filament?.vendor,
                });
                window.wizardSetSpoolEmptyWeightInherited(value, source);
            }
            document.getElementById('wiz-spool-initial_weight').value = d.initial_weight !== null ? d.initial_weight : "";
            // buglist L51: format the prefilled used to the PRECISE tier so it
            // (a) doesn't show float noise like "150.40000001" and (b) reconciles
            // with the remaining field derived by wizardCalcRemainingFromUsed below.
            document.getElementById('wiz-spool-used').value = window.fmtGramsPrecise(d.used_weight || 0);
            
            // WEIGH-OUT PROTOCOL: Store original value and show input
            wizardState.original_used_weight = d.used_weight || 0;
            const usageContainer = document.getElementById('container-wiz-spool-recent-usage');
            if (usageContainer) usageContainer.style.display = 'block';

            document.getElementById('wiz-spool-comment').value = d.comment || "";
            // Price & Purchase Link
            window.wizardPrefillSpoolPrice(d.price, d.filament && d.filament.price);
            // Group 10.4 smart fallback (same as clone path above).
            wizardApplyPurchaseLinkFallback(d.extra?.purchase_url, d.filament?.extra?.purchase_url);
            wizardApplyProductLinkFallback(d.extra?.product_url, d.filament?.extra?.product_url);
            if (document.getElementById('wiz-spool-archived')) {
                document.getElementById('wiz-spool-archived').checked = d.archived || false;
            }
            window.wizardCalcRemainingFromUsed();

            // Spool Extra
            if (d.extra) {
                Object.entries(d.extra).forEach(([k, v]) => {
                    const input = document.getElementById(`wiz_spool_ef_${k}`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = v === true || v === 'true';
                        } else {
                            input.value = v;
                        }
                    }
                });
            }

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">Editing Spool #${spoolId}.</span>`;
            submitBtn.disabled = false;
            if (window.wizardApplyCollapseDefaults) window.wizardApplyCollapseDefaults('edit');
        })
        .catch(err => {
            console.error("Edit Wizard Error:", err);
            document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to connect for edit.</span>';
            submitBtn.disabled = false;
        });
};

// --- PER-SPOOL PRUSAMENT SCAN (Step 3) ---
// One row per spool, driven by `wiz-spool-qty`. Each row holds an optional
// Prusament URL; a successful scan provides per-spool overrides that ride
// alongside spool_data when the wizard submits. The first scan in `manual`
// mode also fills Step 2 (filament template) — unless a matching filament
// already exists in Spoolman, in which case the wizard auto-switches into
// `existing` mode against the match. Failed scans block submit until cleared.

wizardState.spoolRows = [];
wizardState.filamentLockedFromScan = false;

const _normalizeStr = (s) => (s || '').toString().trim().toLowerCase();

// Pull the canonical filament_attributes choice list from the cached
// Spoolman field config. Returns [] when the wizard's extraFields
// fetch hasn't completed yet — callers fall back gracefully.
const _knownFilamentAttributes = () => {
    const fields = wizardState.extraFields && wizardState.extraFields.filament;
    if (!fields) return [];
    const fa = fields.find(f => f.key === 'filament_attributes');
    return (fa && fa.choices) || [];
};

// Split a Prusament-style "full" material string ("PC Blend Carbon Fiber")
// into a base material and a list of attributes. Greedy longest-first
// match against the canonical Spoolman filament_attributes choices so
// multi-word attrs like "Carbon Fiber" win over their substrings.
// Word-boundary aware so the match is exact ("PE" won't pull from
// "PETG"). Anything left after attrs are stripped is the base material.
window.splitMaterialAndAttributes = (rawMaterial, knownAttrs) => {
    if (!rawMaterial) return { base: '', attrs: [] };
    const list = Array.isArray(knownAttrs) ? knownAttrs : [];
    if (list.length === 0) return { base: rawMaterial.trim(), attrs: [] };
    const sorted = [...list].sort((a, b) => b.length - a.length);
    let remaining = ` ${rawMaterial} `;
    const matched = [];
    for (const attr of sorted) {
        const escaped = attr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp(`(^|[^A-Za-z0-9])${escaped}(?=$|[^A-Za-z0-9])`, 'i');
        if (re.test(remaining)) {
            remaining = remaining.replace(re, '$1 ');
            matched.push(attr);
        }
    }
    const base = remaining.trim().replace(/\s+/g, ' ');
    return { base, attrs: matched };
};

// Material match strategy, in order of preference:
//   1. Strip known attributes off the parser side, exact-match the
//      remaining base against stored material. This is the right answer
//      whenever extraFields is loaded — handles "PC Blend Carbon Fiber"
//      vs stored "PC".
//   2. Token-subset fallback when the canonical attribute list isn't
//      available yet (wizard race or older deployment). Word-aware so
//      "PE" still won't match "PETG".
const _materialMatches = (storedMat, parsedMat) => {
    if (!storedMat || !parsedMat) return false;
    if (storedMat === parsedMat) return true;
    const known = _knownFilamentAttributes().map(_normalizeStr);
    if (known.length > 0) {
        const split = window.splitMaterialAndAttributes(parsedMat, known);
        if (_normalizeStr(split.base) === storedMat) return true;
        // And the reverse — stored side may itself be a "full" string on
        // older filaments that pre-date the base/attrs split convention.
        const splitStored = window.splitMaterialAndAttributes(storedMat, known);
        if (_normalizeStr(splitStored.base) === _normalizeStr(split.base)
                && splitStored.base) {
            return true;
        }
    }
    // Token-subset fallback (race / no canonical list available).
    const tokens = (s) => new Set(s.split(/[\s\-_,;()/]+/).filter(Boolean));
    const a = tokens(storedMat);
    const b = tokens(parsedMat);
    if (a.size === 0 || b.size === 0) return false;
    const [smaller, larger] = a.size <= b.size ? [a, b] : [b, a];
    for (const t of smaller) {
        if (!larger.has(t)) return false;
    }
    return true;
};

// Pull the Prusament product ID out of a /spool/<product_id>/<serial> URL.
// Strips any wrapping JSON-encoded quote chars first since /api/filaments
// doesn't run parse_inbound_data — text-type extras arrive as `"https://..."`
// (literal quote chars). Same product, different physical box = same id.
const _extractPrusamentProductId = (url) => {
    if (!url) return null;
    const s = String(url).replace(/^"|"$/g, '');
    const m = s.match(/prusament\.com\/spool\/(\d+)/i);
    return m ? m[1] : null;
};

// Returns the matched filament list (sorted with the best pick at [0]).
// The array carries an extra `.definitive` property:
//   true  — single match OR a Tier-1 product-ID winner; caller should
//           silently auto-switch.
//   false — multiple candidates, ambiguous; caller should surface the
//           duplicate picker so the user decides rather than gambling
//           on lowest-id.
// Returning an array keeps backward compatibility with existing
// `matches.length` / `matches[0]` consumers; the property is read by
// the new picker-aware callers.
window.findFilamentMatches = (temp) => {
    const _wrap = (arr, definitive) => {
        arr.definitive = definitive;
        return arr;
    };
    const all = wizardState.allFilaments || [];
    const vName = _normalizeStr((temp.vendor && temp.vendor.name) || temp.manufacturer);
    const mat = _normalizeStr(temp.material);
    const parsedColor = _normalizeStr(temp.color_name || temp.name);
    if (!vName || !mat || !parsedColor) return _wrap([], true);
    const matches = all.filter(f => {
        const fv = _normalizeStr(f.vendor && f.vendor.name);
        const fm = _normalizeStr(f.material);
        if (fv !== vName) return false;
        if (!_materialMatches(fm, mat)) return false;
        // Fuzzy color match: a Prusament filament might be stored with no
        // dedicated color_name (just a `name` like "Silver (Pearl Mouse)"),
        // while the scan returns color_name "Pearl Mouse". Accept any of:
        //   1. exact equality on the filament's color_name field
        //   2. parsed color appears anywhere in the filament's name
        //   3. filament's color_name appears in the parsed color (only when
        //      color_name is non-empty — the truthy guard prevents the
        //      empty-string substring trap from matching everything)
        const fColorName = _normalizeStr(f.color_name);
        const fName = _normalizeStr(f.name);
        if (fColorName && fColorName === parsedColor) return true;
        if (fName && fName.includes(parsedColor)) return true;
        if (fColorName && parsedColor.includes(fColorName)) return true;
        return false;
    });
    if (matches.length === 0) return _wrap([], true);
    if (matches.length === 1) return _wrap(matches, true);
    // Tier 1: prefer candidates already tagged with the SAME Prusament
    // product ID as the scan. Same /spool/<id>/ in both URLs means
    // "same product, different physical box" — the strongest possible
    // identity signal. Without this, two Prusament PC Black filaments
    // (one tagged from a prior scan, one a stray duplicate) would tie
    // on the basic gate and we'd silently pick the wrong one.
    const parsedProductId = _extractPrusamentProductId(temp.external_link);
    if (parsedProductId) {
        const tier1 = matches.filter(f => {
            const fpid = _extractPrusamentProductId((f.extra || {}).product_url);
            return fpid === parsedProductId;
        });
        if (tier1.length >= 1) {
            tier1.sort((a, b) => Number(a.id) - Number(b.id));
            // Definitive even when multiple tier1 hits — those are literal
            // duplicates of the same canonical product (same product_url),
            // oldest-wins is the right call within that subset.
            return _wrap(tier1, true);
        }
    }
    // Multiple basic-gate matches with no Tier-1 disambiguation = truly
    // ambiguous. Caller should surface the picker so the user decides
    // rather than gambling on lowest-id. We still sort lowest-id-first
    // so [0] is a sensible default if the caller chooses not to prompt.
    matches.sort((a, b) => Number(a.id) - Number(b.id));
    return _wrap(matches, false);
};

window.wizardSyncSpoolRows = () => {
    const qtyInput = document.getElementById('wiz-spool-qty');
    const qty = Math.max(1, parseInt(qtyInput && qtyInput.value) || 1);
    while (wizardState.spoolRows.length < qty) {
        wizardState.spoolRows.push({
            idx: wizardState.spoolRows.length,
            url: '',
            status: 'empty',
            errorMsg: '',
            override: null,
        });
    }
    if (wizardState.spoolRows.length > qty) {
        wizardState.spoolRows = wizardState.spoolRows.slice(0, qty);
    }
    wizardState.spoolRows.forEach((r, i) => { r.idx = i; });
    window.wizardRenderSpoolRows();
    window.wizardUpdateSubmitGate();
};

// Build the badge HTML for a single row — pure function, no DOM access.
// Error badges double as a click-to-clear affordance: the user can tap
// the red badge to reset the row in one click instead of selecting all
// the failed URL text and deleting. Useful when a hardware QR scanner
// caught the wrong barcode or got interrupted mid-stream.
const _spoolRowBadgeHtml = (row) => {
    if (row.status === 'pending') {
        return `<span class="badge bg-secondary">⏳ Scanning…</span>`;
    }
    if (row.status === 'ok') {
        const o = row.override || {};
        const parts = [];
        if (o.initial_weight !== undefined) parts.push(`${o.initial_weight}g`);
        if (o.spool_weight !== undefined) parts.push(`${o.spool_weight}g empty`);
        if (o.extra && o.extra.prusament_manufacturing_date) {
            // Strip the literal-quote wrapper for display.
            parts.push(String(o.extra.prusament_manufacturing_date).replace(/^"|"$/g, ''));
        }
        return `<span class="badge bg-success">✓ ${parts.join(' · ') || 'Scanned'}</span>`;
    }
    if (row.status === 'error') {
        return `<span class="badge bg-danger" role="button" style="cursor: pointer;"
                       title="Click to clear this row and retry"
                       onclick="window.wizardScanSpoolRow(${row.idx}, '')">✗ ${row.errorMsg || 'Scan failed'} ✕</span>`;
    }
    return '';
};

// "Clear this row" button — sits between the URL input and the status
// badge. Only relevant when the row has a value to clear (status is
// 'ok' or 'error'); hidden in 'empty' or 'pending' states.
const _spoolRowClearBtnHtml = (row) => {
    const visible = (row.status === 'ok' || row.status === 'error');
    const display = visible ? '' : 'display: none;';
    return `<button type="button" class="btn btn-sm btn-link p-0 px-1 text-secondary wiz-row-clear-btn"
                    style="font-size: 1.1em; line-height: 1; ${display}"
                    title="Clear this row"
                    onclick="window.wizardScanSpoolRow(${row.idx}, '')">✕</button>`;
};

const _spoolRowSummaryHtml = () => {
    const okCount = wizardState.spoolRows.filter(r => r.status === 'ok').length;
    const total = wizardState.spoolRows.length;
    const errCount = wizardState.spoolRows.filter(r => r.status === 'error').length;
    if (errCount > 0) {
        return `<span class="text-danger fw-bold">⚠ ${errCount} of ${total} spool scans failed — fix or clear before creating.</span>`;
    }
    return `${okCount} of ${total} spools have scan data — others use defaults above.`;
};

// Update only the changed row's badge + outline class. Critically does NOT
// touch the URL input or any neighbor row. Without this, every status
// transition (pending → ok) used to blow away the entire rows container
// via innerHTML, destroying any input the user was actively typing into
// in another row — broke rapid-fire blind scanning of multiple boxes.
window.wizardRenderSpoolRowBadge = (idx) => {
    const row = wizardState.spoolRows[idx];
    if (!row) return;
    const rowEl = document.querySelector(`[data-spool-row-idx="${idx}"]`);
    if (rowEl) {
        // Replace just the trailing badge span (last child) to avoid touching
        // siblings (label, input, clear button). If no badge yet, append one.
        const lastChild = rowEl.lastElementChild;
        if (lastChild && lastChild.classList && lastChild.classList.contains('badge')) {
            lastChild.outerHTML = _spoolRowBadgeHtml(row) || '';
        } else {
            rowEl.insertAdjacentHTML('beforeend', _spoolRowBadgeHtml(row));
        }
        // Toggle the clear-row × button visibility based on whether the row
        // currently has a value worth clearing. Don't replace the element —
        // just flip its display so any focus state stays intact.
        const clearBtn = rowEl.querySelector('.wiz-row-clear-btn');
        if (clearBtn) {
            const visible = (row.status === 'ok' || row.status === 'error');
            clearBtn.style.display = visible ? '' : 'none';
        }
        // Outline class for error state.
        rowEl.classList.toggle('border', row.status === 'error');
        rowEl.classList.toggle('border-danger', row.status === 'error');
        rowEl.classList.toggle('rounded', row.status === 'error');
        rowEl.classList.toggle('p-1', row.status === 'error');
    }
    const summary = document.getElementById('wiz-spool-rows-summary');
    if (summary) summary.innerHTML = _spoolRowSummaryHtml();
};

// Full re-render — only used when the row count changes (qty change or
// reset). Blows away inputs, so do not call this on a status transition.
window.wizardRenderSpoolRows = () => {
    const container = document.getElementById('wiz-spool-rows-container');
    if (!container) return;
    const summary = document.getElementById('wiz-spool-rows-summary');

    container.innerHTML = wizardState.spoolRows.map(row => {
        const rowCls = row.status === 'error' ? 'border border-danger rounded p-1' : '';
        const valAttr = row.url ? `value="${row.url.replace(/"/g, '&quot;')}"` : '';
        return `
        <div class="d-flex align-items-center gap-2 mb-1 ${rowCls}" data-spool-row-idx="${row.idx}">
            <span class="text-secondary small" style="min-width: 64px;">Spool ${row.idx + 1}</span>
            <input type="url" class="form-control form-control-sm bg-dark text-white border-secondary"
                placeholder="📷 Scan/paste Prusament URL — optional"
                ${valAttr}
                onblur="window.wizardScanSpoolRow(${row.idx}, this.value)"
                onkeydown="if (event.key === 'Enter') { event.preventDefault(); this.blur(); }">
            ${_spoolRowClearBtnHtml(row)}
            ${_spoolRowBadgeHtml(row)}
        </div>`;
    }).join('');

    if (summary) summary.innerHTML = _spoolRowSummaryHtml();
};

window.wizardUpdateSubmitGate = () => {
    const submitBtn = document.getElementById('btn-wiz-submit');
    if (!submitBtn) return;
    const blocking = wizardState.spoolRows.some(r => r.status === 'pending' || r.status === 'error');
    if (blocking) {
        submitBtn.disabled = true;
    } else {
        // Defer to wizardValidateSubmit's own logic (existing-mode + selection check).
        wizardValidateSubmit();
    }
};

window.wizardScanSpoolRow = async (idx, rawUrl) => {
    const row = wizardState.spoolRows[idx];
    if (!row) return;
    const url = (rawUrl || '').trim();
    row.url = url;

    if (!url) {
        row.status = 'empty';
        row.errorMsg = '';
        row.override = null;
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
        return;
    }

    if (!url.includes('prusament.com/spool/')) {
        row.status = 'error';
        row.errorMsg = 'Not a Prusament URL';
        row.override = null;
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
        return;
    }

    // EAGER FOCUS ADVANCE — before the slow fetch begins, hop focus to
    // the next still-empty row. Hardware QR scanners send Enter at the
    // end of the scan, which blurs row N; the very next keystroke from
    // the scanner for row N+1 arrives within milliseconds. If we wait
    // until the fetch resolves to advance focus, those early keystrokes
    // land on document.body or wherever and get lost — the user sees
    // a partial URL on row N+1, or worse, the global scan handler picks
    // up the URL prefix and 400s with "Unknown/Invalid Link". Move
    // focus NOW so the scanner's row N+1 stream has a target.
    const eagerNext = wizardState.spoolRows.find(r => r.idx > idx && r.status === 'empty');
    if (eagerNext) {
        const eagerInput = document.querySelector(
            `[data-spool-row-idx="${eagerNext.idx}"] input[type='url']`
        );
        if (eagerInput) eagerInput.focus();
    }

    row.status = 'pending';
    row.errorMsg = '';
    window.wizardRenderSpoolRowBadge(idx);
    window.wizardUpdateSubmitGate();

    try {
        const r = await fetch(`/api/external/search?source=prusament&q=${encodeURIComponent(url)}`);
        const data = await r.json();
        if (!data.success || !data.results || data.results.length === 0) {
            row.status = 'error';
            row.errorMsg = 'Prusament URL not recognized';
            row.override = null;
            window.wizardRenderSpoolRowBadge(idx);
            window.wizardUpdateSubmitGate();
            return;
        }

        const temp = data.results[0];
        row.override = window.extractSpoolFieldsFromTemplate(temp);
        row.status = 'ok';
        row.errorMsg = '';

        // First successful scan in the session: maybe fill Step 2. If any
        // existing filament fuzzy-matches AND the matcher is confident
        // (single match OR Tier-1 product-ID winner), silently auto-switch.
        // If multiple basic-gate matches are ambiguous, surface the picker
        // so the user picks (or chooses "Create new"). Gate accepts both
        // 'manual' and 'external' (Import from External Database) since
        // both paths can result in a fresh filament create.
        const canMatch = (wizardState.mode === 'manual' || wizardState.mode === 'external');
        if (!wizardState.filamentLockedFromScan && canMatch) {
            const matches = window.findFilamentMatches(temp);
            if (matches.length === 0) {
                window.applyFilamentFieldsFromTemplate(temp);
            } else if (matches.definitive) {
                window.wizardAutoSwitchToExisting(matches[0], temp);
            } else {
                window.wizardRenderDuplicatePicker(matches, temp);
            }
            wizardState.filamentLockedFromScan = true;
        }

        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
        // Note: focus-next is no longer fired here — done eagerly before
        // the fetch above so the QR scanner's next-box stream has a
        // landing target as soon as possible. Firing it again here
        // would steal focus from a user who's already typing into row N+2.
    } catch (e) {
        console.error('wizardScanSpoolRow error', e);
        row.status = 'error';
        row.errorMsg = 'Network error';
        row.override = null;
        window.wizardRenderSpoolRowBadge(idx);
        window.wizardUpdateSubmitGate();
    }
};

window.wizardAutoSwitchToExisting = (filament, parsedTemplate) => {
    window.wizardSelectType('existing', true);
    const sel = document.getElementById('wiz-existing-results');
    if (sel) {
        const name = `${filament.vendor?.name || 'Generic'} ${filament.material} - ${filament.name || 'Unknown'}`;
        sel.innerHTML = `<option value="${filament.id}" selected>${name} (ID: ${filament.id})</option>`;
        window.wizardExistingSelected();
    }
    const msg = document.getElementById('wiz-status-msg');
    if (msg) {
        msg.innerHTML = `<span class="text-success">✅ Recognized existing Prusament Filament #${filament.id} — switched to new-spool mode.</span>`;
    }
    // Opportunistic backfill: silently fill any field the existing record
    // is missing, surface mismatches as an opt-in panel. Skipped when the
    // caller didn't pass the parser template (e.g. clone flow).
    if (parsedTemplate && window.computeFilamentBackfillDiff) {
        const known = _knownFilamentAttributes();
        const diff = window.computeFilamentBackfillDiff(filament, parsedTemplate, known);
        if (diff.silent && Object.keys(diff.silent).length > 0) {
            window.applyFilamentBackfillSilent(filament.id, diff.silent);
        }
        if (diff.mismatches && diff.mismatches.length > 0) {
            window.wizardRenderFilamentMismatchPanel(filament.id, diff.mismatches);
        } else {
            window.wizardClearFilamentMismatchPanel();
        }
    }
};

// Treat null / undefined / '' / 0 (numeric only) all as "unset" so the
// backfill detector can fairly say "this slot is empty, fill it." Matches
// the inv_details.js Edit Filament dirty-diff `same()` helper convention.
const _isUnset = (v) => v === null || v === undefined || v === '' || v === 0 || v === '0';

const _normalizeFilamentAttrs = (raw) => {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw.map(String);
    if (typeof raw === 'string') {
        try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed.map(String) : [];
        } catch (e) {
            return [];
        }
    }
    return [];
};

// Pure function — given an existing filament record and a fresh parser
// template, decide what to silently backfill vs surface as a mismatch
// for opt-in. See plan: "Backfill Existing Filament From Prusament Scan
// Data" for the field-by-field rule table this implements.
window.computeFilamentBackfillDiff = (existing, parsedTemplate, knownAttrs) => {
    const out = { silent: {}, mismatches: [] };
    if (!existing || !parsedTemplate) return out;
    const ex = existing;
    const tp = parsedTemplate;

    // Native scalar fields with simple "fill if unset, mismatch if differs"
    // semantics. Each entry: [key, parsed value, mismatch threshold (number),
    // human label, kind hint for renderer].
    const tempExtra = (tp.extra || {});
    const exExtra = (ex.extra || {});

    const split = (window.splitMaterialAndAttributes || ((m) => ({ base: m, attrs: [] })))(
        tp.material || '', knownAttrs || []
    );
    const parsedBase = split.base || tp.material || '';

    const pushMismatch = (key, label, stored, scanned, kind) => {
        out.mismatches.push({ key, label, stored, scanned, kind });
    };

    // material: never silent. Mismatch only when parsed-base differs from
    // the user's stored value (the common case — user keeps "PC", parser
    // returned "PC Blend Carbon Fiber" → base "PC" → no mismatch).
    if (parsedBase && ex.material && parsedBase !== ex.material) {
        pushMismatch('material', 'Material', ex.material, parsedBase, 'text');
    } else if (parsedBase && _isUnset(ex.material)) {
        out.silent.material = parsedBase;
    }

    // diameter / density / weight / spool_weight — fill when unset,
    // mismatch when meaningfully different.
    const numericFields = [
        ['diameter', 'Diameter (mm)', 0.05],
        ['density', 'Density (g/cm³)', 0.05],
        ['weight', 'Weight (g)', 10],
        ['spool_weight', 'Spool weight (g)', 5],
    ];
    for (const [key, label, threshold] of numericFields) {
        const stored = ex[key];
        const scanned = tp[key];
        if (_isUnset(scanned)) continue;
        if (_isUnset(stored)) {
            out.silent[key] = scanned;
        } else if (Math.abs(Number(stored) - Number(scanned)) > threshold) {
            const kind = (key === 'spool_weight') ? 'spool_weight' : 'number';
            pushMismatch(key, label, Number(stored), Number(scanned), kind);
        }
    }

    // settings_extruder_temp / settings_bed_temp — fill if unset, mismatch
    // if differs (no threshold; temps are integers in Spoolman).
    const tempFields = [
        ['settings_extruder_temp', 'Extruder Temp Min (°C)'],
        ['settings_bed_temp', 'Bed Temp Min (°C)'],
    ];
    for (const [key, label] of tempFields) {
        const stored = ex[key];
        const scanned = tp[key];
        if (_isUnset(scanned)) continue;
        if (_isUnset(stored)) {
            out.silent[key] = scanned;
        } else if (Number(stored) !== Number(scanned)) {
            pushMismatch(key, label, Number(stored), Number(scanned), 'number');
        }
    }

    // color_hex — never silent. Mismatch only with a 'color' kind hint so
    // the renderer can show swatches.
    if (tp.color_hex && ex.color_hex
            && String(tp.color_hex).replace('#', '').toLowerCase() !== String(ex.color_hex).replace('#', '').toLowerCase()) {
        pushMismatch('color_hex', 'Color hex',
            String(ex.color_hex).replace('#', ''),
            String(tp.color_hex).replace('#', ''),
            'color');
    } else if (tp.color_hex && _isUnset(ex.color_hex)) {
        out.silent.color_hex = String(tp.color_hex).replace('#', '');
    }

    // Extras (text-type max-temps): JSON-quote-wrap before sending so the
    // backend's sanitize_outbound_data doesn't reject "225" as an int.
    const extraTextFields = [
        ['nozzle_temp_max', 'Nozzle Temp Max (°C)'],
        ['bed_temp_max', 'Bed Temp Max (°C)'],
    ];
    for (const [key, label] of extraTextFields) {
        const stored = exExtra[key];
        const scanned = tempExtra[key];
        if (_isUnset(scanned)) continue;
        // The parser sometimes returns these wrapped (`'"225"'`) and
        // sometimes raw ('225'). Normalize for comparison.
        const unwrap = (v) => {
            if (v === null || v === undefined) return v;
            const s = String(v);
            return s.replace(/^"|"$/g, '');
        };
        const storedNorm = unwrap(stored);
        const scannedNorm = unwrap(scanned);
        if (_isUnset(storedNorm)) {
            out.silent['extra.' + key] = `"${scannedNorm}"`;
        } else if (storedNorm !== scannedNorm) {
            pushMismatch('extra.' + key, label, storedNorm, scannedNorm, 'number');
        }
    }

    // filament_attributes — set-union, only ever ADD missing canonical
    // attrs (never remove existing). Drives the user's PC → PC + "Blend"
    // upgrade silently after a scan that splits to ["Blend", "Carbon Fiber"].
    const exAttrs = _normalizeFilamentAttrs(exExtra.filament_attributes);
    const exAttrsLc = new Set(exAttrs.map(s => s.toLowerCase()));
    const newAttrs = (split.attrs || []).filter(a => !exAttrsLc.has(a.toLowerCase()));
    if (newAttrs.length > 0) {
        out.silent['extra.filament_attributes'] = [...exAttrs, ...newAttrs];
    }

    // product_url + purchase_url — silent fill when the existing record
    // has no value. Tagging the filament with the canonical Prusament
    // product link makes the matcher's Tier-1 product-ID rule work on
    // future scans (otherwise the matcher would only have name + material
    // + color to disambiguate, which is fuzzy when the user has
    // accidental duplicates). Sent RAW — both keys are in
    // spoolman_api.JSON_STRING_FIELDS so sanitize_outbound_data wraps
    // them via json.dumps. Pre-wrapping would double-wrap.
    const _isSetUrl = (v) => v !== null && v !== undefined && String(v).replace(/^"|"$/g, '') !== '';
    if (tp.external_link && !_isSetUrl(exExtra.product_url)) {
        out.silent['extra.product_url'] = tp.external_link;
    }
    if ((tp.purchase_link || tp.external_link) && !_isSetUrl(exExtra.purchase_url)) {
        out.silent['extra.purchase_url'] = tp.purchase_link || tp.external_link;
    }

    // original_color — silent overwrite when the parser has a value.
    // This field's whole purpose is to capture the manufacturer's name
    // for the filament (e.g. "Pearl Mouse"), distinct from the user's
    // filter-friendly color_name ("Black"). The parser's color_name is
    // the authoritative source by definition, so prefer it whenever
    // present. Only skip the silent update when the values already match
    // (avoid a no-op PATCH).
    //
    // CRITICAL: original_color is in spoolman_api.JSON_STRING_FIELDS, so
    // sanitize_outbound_data wraps the value via json.dumps before send.
    // Pre-wrapping here would double-wrap and the literal quote chars
    // would leak in — every subsequent scan would compare "X" ≠ X and
    // add ANOTHER layer of quotes. Acceptable canonical forms for the
    // RAW value (as served by /api/filaments without parse_inbound_data,
    // OR by /api/filaments/<id> WITH parse_inbound_data) are exactly two:
    // the JSON-quoted form `"X"` and the raw unwrapped `X`. Anything
    // else means an earlier buggy version corrupted the field — fire
    // an update with the clean value to repair it (sanitize wraps once
    // and we're back to canonical).
    const exOrigColor = exExtra.original_color;
    const scannedOrigColor = tp.color_name;
    if (scannedOrigColor) {
        const acceptable = [scannedOrigColor, `"${scannedOrigColor}"`];
        if (!acceptable.includes(exOrigColor)) {
            out.silent['extra.original_color'] = scannedOrigColor;
        }
    }

    return out;
};

// Apply a silent backfill diff against an existing filament. Splits any
// "extra.<key>" entries in the diff into a nested {extra: {...}} dict
// since /api/update_filament expects the same shape Spoolman uses.
window.applyFilamentBackfillSilent = async (existingId, silentDiff, opts = {}) => {
    if (!silentDiff || Object.keys(silentDiff).length === 0) return null;
    const data = {};
    for (const [k, v] of Object.entries(silentDiff)) {
        if (k.startsWith('extra.')) {
            if (!data.extra) data.extra = {};
            data.extra[k.slice(6)] = v;
        } else {
            data[k] = v;
        }
    }
    try {
        const res = await fetch('/api/update_filament', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: existingId, data }),
        });
        const body = await res.json();
        if (!body.success) {
            console.error('backfill update rejected', body);
            return body;
        }
        // Refresh wizardState.allFilaments so a follow-up scan in the
        // same session sees the upgraded record (otherwise the next
        // computeFilamentBackfillDiff would think the same fields are
        // still missing).
        if (Array.isArray(wizardState.allFilaments)) {
            const idx = wizardState.allFilaments.findIndex(f => String(f.id) === String(existingId));
            if (idx >= 0 && body.filament) {
                wizardState.allFilaments[idx] = body.filament;
            }
        }
        if (!opts.suppressBanner) {
            const msg = document.getElementById('wiz-status-msg');
            if (msg) {
                const summary = Object.keys(silentDiff).map(k => k.replace(/^extra\./, '')).join(', ');
                msg.innerHTML = `<span class="text-success">✨ Updated existing Filament #${existingId} from scan: ${summary}.</span>`;
            }
        }
        return body;
    } catch (e) {
        console.error('backfill fetch failed', e);
        return null;
    }
};

const _formatSpoolWeightHint = (stored, scanned) => {
    // Heuristic: NFC Prusament spools are roughly 30-50g heavier than
    // legacy plastic. Hint only when the SCAN reports a heavier tare
    // than what's stored — i.e. the user is being offered an upgrade
    // from legacy to NFC. Earlier the hint fired in both directions,
    // which incorrectly tagged a lighter (older) replacement as NFC.
    const delta = Number(scanned) - Number(stored);
    if (delta >= 25 && delta <= 75) return ' (NFC?)';
    return '';
};

window.wizardRenderFilamentMismatchPanel = (existingId, mismatches) => {
    const host = document.getElementById('wiz-fil-mismatch-panel');
    if (!host) return;
    if (!mismatches || mismatches.length === 0) {
        host.innerHTML = '';
        host.style.display = 'none';
        return;
    }
    const rowsHtml = mismatches.map((m, i) => {
        const swatch = (val) => `<span style="display:inline-block;width:14px;height:14px;background:#${String(val).replace('#','')};border:1px solid #555;vertical-align:middle;margin-left:4px;"></span>`;
        const storedDisplay = m.kind === 'color'
            ? `#${m.stored}${swatch(m.stored)}`
            : escapeHtml(String(m.stored));
        let scannedDisplay = m.kind === 'color'
            ? `#${m.scanned}${swatch(m.scanned)}`
            : escapeHtml(String(m.scanned));
        if (m.kind === 'spool_weight') {
            scannedDisplay += `<span class="text-warning small">${_formatSpoolWeightHint(m.stored, m.scanned)}</span>`;
        }
        return `
            <tr data-mismatch-row="${i}" data-mismatch-key="${escapeHtml(m.key)}">
                <td class="text-secondary small">${escapeHtml(m.label)}</td>
                <td class="font-monospace">${storedDisplay}</td>
                <td class="font-monospace">${scannedDisplay}</td>
                <td>
                    <button type="button" class="btn btn-sm btn-outline-warning"
                        onclick="window.wizardApplyMismatchRow(${existingId}, ${i})">Use Scanned</button>
                </td>
            </tr>`;
    }).join('');
    host.innerHTML = `
        <div class="alert alert-warning my-2">
            <div class="mb-2"><strong>⚠ Scan data differs from Filament #${existingId}</strong> — pick what to keep:</div>
            <table class="table table-sm table-dark mb-2" style="font-size: 0.9em;">
                <thead><tr><th>Field</th><th>Stored</th><th>Scanned</th><th></th></tr></thead>
                <tbody id="wiz-fil-mismatch-rows">${rowsHtml}</tbody>
            </table>
            <button type="button" class="btn btn-sm btn-secondary"
                onclick="window.wizardClearFilamentMismatchPanel()">Dismiss</button>
        </div>
    `;
    host.style.display = 'block';
    wizardState._mismatches = mismatches;
};

window.wizardApplyMismatchRow = async (existingId, rowIdx) => {
    const list = wizardState._mismatches || [];
    const m = list[rowIdx];
    if (!m) return;
    const diff = {};
    if (m.key.startsWith('extra.')) {
        // Wrap text-type extras for sanitize_outbound_data.
        diff[m.key] = `"${m.scanned}"`;
    } else {
        diff[m.key] = m.scanned;
    }
    const res = await window.applyFilamentBackfillSilent(existingId, diff, { suppressBanner: true });
    if (res && res.success) {
        const tr = document.querySelector(`#wiz-fil-mismatch-rows tr[data-mismatch-row="${rowIdx}"]`);
        if (tr) {
            tr.innerHTML = `<td colspan="4" class="text-success small">✓ Updated ${escapeHtml(m.label)} → ${escapeHtml(String(m.scanned))}</td>`;
        }
    }
};

window.wizardClearFilamentMismatchPanel = () => {
    const host = document.getElementById('wiz-fil-mismatch-panel');
    if (host) {
        host.innerHTML = '';
        host.style.display = 'none';
    }
    wizardState._mismatches = null;
};

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

// --- Duplicate-filament picker (ambiguous matcher result) ---------------
// Reinstated after the user's request: when findFilamentMatches returns
// `definitive: false` (multiple basic-gate candidates with no Tier-1
// product-ID winner), defer to the user instead of silently picking
// lowest-id. The user explicitly wanted: "fall back to letting the user
// decide if we can't after all the matching attempts."
window.wizardRenderDuplicatePicker = (candidates, parsedTemplate) => {
    const host = document.getElementById('wiz-duplicate-picker');
    if (!host) return;
    if (!candidates || candidates.length === 0) {
        host.innerHTML = '';
        host.style.display = 'none';
        return;
    }
    const opts = candidates.map(f => {
        const v = (f.vendor && f.vendor.name) || 'Generic';
        const m = f.material || '?';
        const c = f.color_name || f.name || 'Unknown';
        return `<option value="${escapeHtml(String(f.id))}">${escapeHtml(`${v} ${m} - ${c} (ID: ${f.id})`)}</option>`;
    }).join('');
    host.innerHTML = `
        <div class="alert alert-warning d-flex flex-column gap-2 my-2">
            <div><strong>⚠ Multiple existing filaments match this scan</strong> — pick the right one to use, or create a fresh filament if none of these is correct:</div>
            <div class="d-flex gap-2 align-items-center flex-wrap">
                <select class="form-select form-select-sm bg-dark text-white border-secondary flex-grow-1" id="wiz-duplicate-picker-sel" style="min-width: 200px;">${opts}</select>
                <button type="button" class="btn btn-sm btn-success" onclick="window.wizardDuplicatePickerConfirm()">✓ Use selected</button>
                <button type="button" class="btn btn-sm btn-warning" onclick="window.wizardDuplicatePickerDismiss()">+ Create new filament</button>
            </div>
        </div>
    `;
    host.style.display = 'block';
    // Stash both candidates and parser template; confirm/dismiss both
    // need to know which template to feed downstream.
    wizardState._dupPicker = { candidates, parsedTemplate };
};

window.wizardDuplicatePickerConfirm = () => {
    const sel = document.getElementById('wiz-duplicate-picker-sel');
    const stash = wizardState._dupPicker || {};
    if (!sel || !stash.candidates) {
        window.wizardClearDuplicatePicker();
        return;
    }
    const id = sel.value;
    const match = stash.candidates.find(f => String(f.id) === String(id));
    if (match) {
        window.wizardAutoSwitchToExisting(match, stash.parsedTemplate);
    }
    window.wizardClearDuplicatePicker();
};

window.wizardDuplicatePickerDismiss = () => {
    const stash = wizardState._dupPicker || {};
    if (stash.parsedTemplate) {
        // User chose to create new — fill Step 2 from the parser template
        // so the wizard can proceed in manual create mode.
        window.applyFilamentFieldsFromTemplate(stash.parsedTemplate);
    }
    window.wizardClearDuplicatePicker();
};

window.wizardClearDuplicatePicker = () => {
    const host = document.getElementById('wiz-duplicate-picker');
    if (host) {
        host.innerHTML = '';
        host.style.display = 'none';
    }
    wizardState._dupPicker = null;
};

window.wizardResetSpoolRows = () => {
    wizardState.spoolRows = [];
    wizardState.filamentLockedFromScan = false;
    window.wizardSyncSpoolRows();
};
