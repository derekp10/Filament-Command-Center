/* MODULE: <WeightEntry> — shared used_weight entry component (Phase 2, Group 12) */
//
// Single-spool entry surface used by Quick-Weigh today and FilaBridge manual
// recovery / bulk weigh-out adoption to follow. Renders an inline overlay
// (NOT a nested Swal — see CLAUDE.md "No nested Swal.fire()") with:
//   - mode selector: Gross / Net / Additive / Set Used
//   - mode-aware input + formula hint
//   - live preview of the resulting used_weight + remaining
//   - tare context line (with source badge from the cascade resolver)
//   - optional Auto-archive toggle (Quick-Weigh has it; FilaBridge does not)
//   - keyboard nav: ←/→ to swap modes, Enter to submit, Escape to cancel
//
// Math comes from computeUsedWeight() / parseAdditiveInput() in weight_utils.js.
// On submit the component invokes the caller's onSubmit({...}) — it does NOT
// fetch or write. That keeps existing call paths (saveSpoolWeight,
// saveQuickWeigh, FilaBridge submit) authoritative for the actual write +
// event dispatch (inventory:sync-pulse, inventory:buffer-updated).
//
// Usage:
//   window.WeightEntry.openModal({
//       title: 'Quick Weigh',
//       spool: { id: 101, initial_weight: 1000, used_weight: 575,
//                display: 'CC3D - PLA - Crimson Red', color_hex: 'cc3300' },
//       empty_spool_weight: 220,
//       empty_source: 'filament',                  // optional badge
//       cascade: { spoolWt, filamentWt, vendor },  // for missing-tare prompt
//       defaultMode: 'additive',
//       availableModes: ['gross','net','additive','set_used'],
//       showAutoArchive: true,
//       autoArchiveDefault: true,
//       onSubmit: ({ used_weight, mode, raw_value, auto_archive }) => {...},
//       onCancel: () => {...},
//   });

(function () {
    const OVERLAY_ID = 'fcc-weight-entry-overlay';
    // 13.9 — user preference shortcut, persisted client-side until the
    // Config system (Feature-Buglist.md L9) lands and absorbs it.
    const DEFAULT_MODE_KEY = 'fcc.weighEntry.defaultMode';

    function readStoredDefaultMode(availableModes) {
        try {
            const v = window.localStorage.getItem(DEFAULT_MODE_KEY);
            return (v && availableModes.includes(v)) ? v : null;
        } catch (e) { return null; }
    }
    function writeStoredDefaultMode(modeName) {
        try { window.localStorage.setItem(DEFAULT_MODE_KEY, modeName); }
        catch (e) { /* private mode / quota — ignore */ }
    }

    const MODE_DEFS = {
        gross: {
            label: 'Gross',
            inputLabel: 'Scale reading WITH spool',
            placeholder: 'e.g. 645',
            inputType: 'number',
            inputmode: 'decimal',
            hint: 'used = initial − (gross − empty_tare)',
        },
        net: {
            label: 'Net',
            inputLabel: 'Filament remaining (no spool)',
            placeholder: 'e.g. 425',
            inputType: 'number',
            inputmode: 'decimal',
            hint: 'used = initial − net',
        },
        additive: {
            label: 'Additive',
            inputLabel: 'Delta consumed (e.g. +50, -20)',
            placeholder: '+25 or -10',
            inputType: 'text',
            inputmode: 'decimal',
            hint: 'used = current_used + delta',
        },
        set_used: {
            label: 'Set Used',
            inputLabel: 'Target used weight',
            placeholder: 'e.g. 575',
            inputType: 'number',
            inputmode: 'decimal',
            hint: 'used = value (override)',
        },
    };

    function fmtG(v) {
        if (v === null || v === undefined || Number.isNaN(v)) return '—';
        return `${Math.round(v * 10) / 10}g`;
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    async function openModal(options = {}) {
        const {
            title = 'Weigh',
            spool = {},
            empty_spool_weight = null,
            empty_source = null,
            cascade = null,
            context = null,
            defaultMode = 'additive',
            availableModes = ['gross', 'net', 'additive', 'set_used'],
            showAutoArchive = false,
            autoArchiveDefault = true,
            // 31.1 — the wizard opens this to catalog a spool of unknown
            // original net weight: gross/net then yield the available filament
            // directly (gross − tare) and report it via payload.derived_initial.
            allowUnknownInitial = false,
            onSubmit = null,
            onCancel = null,
        } = options;

        const initial = Number(spool.initial_weight) || 0;
        const initialKnown = initial > 0;
        const currentUsed = Number(spool.used_weight) || 0;
        let currentEmpty = (empty_spool_weight !== null && empty_spool_weight !== '' &&
                             Number(empty_spool_weight) > 0) ? Number(empty_spool_weight) : null;
        let currentSource = empty_source;
        // 13.9 — Stored preference wins over caller's defaultMode so the
        // user's "Set as default" choice persists across sessions and
        // surfaces (Quick-Weigh today; later FilaBridge / bulk weigh-out).
        const storedDefault = readStoredDefaultMode(availableModes);
        const seedMode = storedDefault
            || (availableModes.includes(defaultMode) ? defaultMode : availableModes[0]);
        let mode = seedMode;

        const swatch = spool.color_hex
            ? `<span style="display:inline-block;width:14px;height:14px;background:#${String(spool.color_hex).replace(/^#/,'')};border:1px solid #fff;border-radius:50%;vertical-align:middle;margin-right:6px;"></span>`
            : '';
        const headerDisplay = spool.display
            ? `${swatch}#${escapeHtml(spool.id || '?')} <span style="color:#bbb;">${escapeHtml(spool.display)}</span>`
            : `#${escapeHtml(spool.id || '?')}`;

        const tabsHtml = availableModes.map((m) => {
            const def = MODE_DEFS[m];
            if (!def) return '';
            const active = (m === mode);
            return `<button type="button" data-mode="${m}"
                class="fcc-we-tab btn btn-sm ${active ? 'btn-info' : 'btn-outline-info'}"
                style="margin-right:4px;">${escapeHtml(def.label)}</button>`;
        }).join('');

        const autoArchiveHtml = showAutoArchive
            ? `<div class="form-check form-switch mt-3 pt-2 border-top border-secondary">
                 <input class="form-check-input" type="checkbox" id="fcc-we-auto-archive" ${autoArchiveDefault ? 'checked' : ''}>
                 <label class="form-check-label text-light" for="fcc-we-auto-archive">Auto Archive &amp; Eject if Empty (0g)</label>
               </div>`
            : '';

        const panelHtml = `
            <div role="dialog" aria-modal="true" aria-labelledby="fcc-we-title"
                 style="background:#1f2024;color:#eee;border:1px solid #555;
                        border-radius:8px;padding:0;min-width:380px;
                        max-width:520px;width:92vw;
                        box-shadow:0 8px 32px rgba(0,0,0,0.6);">
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:14px 18px;border-bottom:1px solid #444;">
                    <div id="fcc-we-title" style="font-weight:bold;font-size:1.05rem;">⚖️ ${escapeHtml(title)}</div>
                    <button type="button" id="fcc-we-close"
                        style="background:none;border:none;color:#aaa;font-size:1.4rem;line-height:1;cursor:pointer;"
                        aria-label="Close">×</button>
                </div>
                <div style="padding:14px 18px;">
                    <div style="margin-bottom:10px;">${headerDisplay}</div>
                    <div id="fcc-we-meta" style="color:#bbb;font-size:0.88rem;margin-bottom:12px;line-height:1.5;">
                        <span>Empty spool tare: <strong id="fcc-we-tare-val" style="color:#eee;">${currentEmpty !== null ? fmtG(currentEmpty) : 'unknown'}</strong>
                            <span id="fcc-we-tare-badge" style="display:${(currentSource === 'filament' || currentSource === 'vendor') ? '' : 'none'};
                                margin-left:6px;font-size:0.78rem;
                                background:#264b5d;color:#9fd6e6;border-radius:4px;padding:1px 6px;"
                                title="Inherited via Spool > Filament > Vendor cascade.">
                                ↩ from <span id="fcc-we-tare-source">${escapeHtml(currentSource || '')}</span>
                            </span>
                        </span><br>
                        <span>Initial weight: <strong style="color:#eee;">${initialKnown ? fmtG(initial) : 'unknown — set from what’s on the spool'}</strong>
                              &nbsp;·&nbsp; Currently used: <strong style="color:#eee;">${fmtG(currentUsed)}</strong></span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <span style="color:#bbb;font-size:0.82rem;">Mode</span>
                        <button type="button" id="fcc-we-set-default"
                                class="btn btn-link btn-sm p-0"
                                style="color:#9fd6e6;font-size:0.78rem;text-decoration:none;"
                                title="Use the current mode as the default the next time this overlay opens. Shortcut: D">
                            Set as default
                        </button>
                    </div>
                    <div id="fcc-we-tabs" style="margin-bottom:12px;">${tabsHtml}</div>

                    <label id="fcc-we-input-label" for="fcc-we-input"
                           class="form-label small text-light mb-1"></label>
                    <div class="input-group input-group-sm" style="margin-bottom:6px;">
                        <input id="fcc-we-input" class="form-control bg-dark text-white border-secondary"
                               style="font-size:1.15rem;"
                               autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" />
                        <span class="input-group-text bg-dark text-light border-secondary">g</span>
                    </div>
                    <div id="fcc-we-hint" style="color:#888;font-size:0.78rem;margin-bottom:12px;
                                                  font-family:'JetBrains Mono','Cascadia Code','Consolas',monospace;"></div>

                    <div id="fcc-we-preview"
                         style="background:#0f1014;border:1px solid #333;border-radius:6px;
                                padding:8px 12px;font-size:0.92rem;color:#cfd;
                                margin-bottom:6px;">Enter a value to preview…</div>
                    <div id="fcc-we-warn" style="color:#f5b342;font-size:0.82rem;min-height:1em;"></div>
                    ${autoArchiveHtml}
                </div>
                <div style="display:flex;justify-content:space-between;gap:8px;
                            padding:12px 18px;border-top:1px solid #444;">
                    <button type="button" id="fcc-we-cancel" class="btn btn-sm btn-secondary">Cancel</button>
                    <button type="button" id="fcc-we-save" class="btn btn-sm btn-success fw-bold">Save Update</button>
                </div>
            </div>
        `;
        // Group 15 — canonical mountOverlay() owns the document.body mount,
        // z-index ladder, and the capture-phase focusGuard that defeats
        // Bootstrap's `_enforceFocus` (13.1 lesson, commit 89c6f39). Escape
        // routes through onEscape so callers don't have to special-case it.
        const overlayHandle = window.mountOverlay({
            id: OVERLAY_ID,
            content: panelHtml,
            focusGuard: true,
            initialFocus: '#fcc-we-input',
            onEscape: () => attemptCancel(),
        });
        const overlay = overlayHandle.element;

        const inputEl = overlay.querySelector('#fcc-we-input');
        const labelEl = overlay.querySelector('#fcc-we-input-label');
        const hintEl = overlay.querySelector('#fcc-we-hint');
        const previewEl = overlay.querySelector('#fcc-we-preview');
        const warnEl = overlay.querySelector('#fcc-we-warn');
        const tabsEl = overlay.querySelector('#fcc-we-tabs');
        const tareValEl = overlay.querySelector('#fcc-we-tare-val');
        const tareBadgeEl = overlay.querySelector('#fcc-we-tare-badge');
        const tareSourceEl = overlay.querySelector('#fcc-we-tare-source');
        const saveBtn = overlay.querySelector('#fcc-we-save');
        const cancelBtn = overlay.querySelector('#fcc-we-cancel');
        const closeBtn = overlay.querySelector('#fcc-we-close');
        const autoArchiveEl = overlay.querySelector('#fcc-we-auto-archive');
        const setDefaultBtn = overlay.querySelector('#fcc-we-set-default');

        function persistCurrentModeAsDefault() {
            writeStoredDefaultMode(mode);
            // Quick visual confirmation that the click registered.
            const original = setDefaultBtn.textContent;
            setDefaultBtn.textContent = `✓ ${MODE_DEFS[mode].label} is default`;
            setDefaultBtn.disabled = true;
            setTimeout(() => {
                setDefaultBtn.textContent = original;
                setDefaultBtn.disabled = false;
            }, 1200);
        }

        function applyMode(newMode) {
            if (!availableModes.includes(newMode)) return;
            mode = newMode;
            const def = MODE_DEFS[mode];
            inputEl.type = def.inputType;
            inputEl.placeholder = def.placeholder;
            inputEl.setAttribute('inputmode', def.inputmode);
            labelEl.textContent = def.inputLabel;
            hintEl.textContent = def.hint;
            // Preserve typed value across mode switches; recompute preview.
            tabsEl.querySelectorAll('.fcc-we-tab').forEach((btn) => {
                const active = btn.dataset.mode === mode;
                btn.classList.toggle('btn-info', active);
                btn.classList.toggle('btn-outline-info', !active);
            });
            updatePreview();
            inputEl.focus();
        }

        function getNumericValue() {
            const raw = inputEl.value;
            if (mode === 'additive') {
                const parsed = window.parseAdditiveInput(raw);
                return parsed.value;
            }
            if (raw === null || raw === undefined || String(raw).trim() === '') return null;
            const n = Number(raw);
            return Number.isNaN(n) ? null : n;
        }

        function updatePreview() {
            const v = getNumericValue();
            if (v === null || v === undefined) {
                previewEl.textContent = 'Enter a value to preview…';
                previewEl.style.color = '#cfd';
                warnEl.textContent = '';
                return;
            }
            const r = window.computeUsedWeight({
                mode,
                value: v,
                initial_weight: initial,
                current_used: currentUsed,
                empty_spool_weight: currentEmpty,
                allow_unknown_initial: allowUnknownInitial,
            });
            if (r.error) {
                previewEl.textContent = `Invalid input (${r.error}).`;
                previewEl.style.color = '#f88';
                warnEl.textContent = '';
                return;
            }
            if (r.requires_empty) {
                previewEl.textContent = 'Empty-spool weight is missing — we’ll ask you for it on Save.';
                previewEl.style.color = '#f5b342';
                warnEl.textContent = '';
                return;
            }
            if (r.derived_initial !== null && r.derived_initial !== undefined) {
                // 31.1 — unknown-original-net: what's on the spool now becomes
                // its full capacity, so the meaningful number is available.
                previewEl.innerHTML = `Available on spool <strong>${fmtG(r.remaining)}</strong> ` +
                    `&nbsp;·&nbsp; recorded as a full <strong>${fmtG(r.derived_initial)}</strong> spool (used 0)`;
                previewEl.style.color = '#cfd';
                // Mode-aware clamp note — 'low' can come from Net (negative
                // value) too, not just Gross-below-tare.
                warnEl.textContent = (r.capped === 'low')
                    ? (mode === 'gross'
                        ? '⚠ Gross is below the empty-spool weight — clamped to 0.'
                        : '⚠ Value clamped to 0 (cannot go negative).')
                    : '';
                return;
            }
            previewEl.innerHTML = `Initial <strong>${fmtG(initial)}</strong> &nbsp;→&nbsp; ` +
                `Used <strong>${fmtG(r.used_weight)}</strong> &nbsp;·&nbsp; ` +
                `Remaining <strong>${fmtG(r.remaining)}</strong>`;
            previewEl.style.color = '#cfd';
            if (r.capped === 'high') warnEl.textContent = '⚠ Value clamped to initial_weight.';
            else if (r.capped === 'low') warnEl.textContent = '⚠ Value clamped to 0 (cannot go negative).';
            else warnEl.textContent = '';
        }

        async function attemptSave() {
            const v = getNumericValue();
            if (v === null || v === undefined) {
                inputEl.focus();
                warnEl.textContent = 'Enter a value first.';
                return;
            }
            let r = window.computeUsedWeight({
                mode,
                value: v,
                initial_weight: initial,
                current_used: currentUsed,
                empty_spool_weight: currentEmpty,
                allow_unknown_initial: allowUnknownInitial,
            });
            if (r.error) { warnEl.textContent = `Invalid input (${r.error}).`; return; }
            if (r.requires_empty) {
                // Mode is gross + tare is unset — shared prompt.
                // allowSkip lets the user submit their input as Net (treat
                // the typed value as filament remaining) without persisting a
                // tare. 13.7 — see Feature-Buglist.md.
                // 31.1 review fix: NEVER offer Skip when the original net is
                // unknown. Skip downgrades gross→net, i.e. reinterprets the
                // typed value as filament remaining; with no known capacity to
                // reconcile against, a gross reading (which INCLUDES the spool
                // tare) would be recorded as the spool's full net — overstating
                // filament by exactly the tare. Force a real tare entry instead.
                const promptCtx = context || {};
                const tare = await window.promptMissingEmptyWeight({
                    vendor: promptCtx.vendor || '',
                    material: promptCtx.material || '',
                    color: promptCtx.color || '',
                    color_hex: promptCtx.color_hex || spool.color_hex || null,
                    allowSkip: !allowUnknownInitial,
                });
                if (tare === null) return;  // user cancelled
                let effectiveMode = mode;
                if (tare === window.PROMPT_SKIP_TARE) {
                    // Downgrade Gross → Net for this submission only. No tare
                    // is persisted; the typed value is treated as filament
                    // remaining (used = initial − net).
                    effectiveMode = 'net';
                } else {
                    currentEmpty = Number(tare);
                    tareValEl.textContent = fmtG(currentEmpty);
                    if (tareBadgeEl) tareBadgeEl.style.display = 'none';
                }
                // Re-resolve.
                r = window.computeUsedWeight({
                    mode: effectiveMode,
                    value: v,
                    initial_weight: initial,
                    current_used: currentUsed,
                    empty_spool_weight: currentEmpty,
                    allow_unknown_initial: allowUnknownInitial,
                });
                if (r.error || r.requires_empty) {
                    warnEl.textContent = 'Could not compute used_weight.';
                    return;
                }
                // Report the mode that actually computed used_weight so the
                // caller's payload reflects the Skip downgrade.
                mode = effectiveMode;
            }

            const payload = {
                used_weight: r.used_weight,
                remaining: r.remaining,
                mode,
                raw_value: inputEl.value,
                value: v,
                empty_spool_weight: currentEmpty,
                auto_archive: autoArchiveEl ? autoArchiveEl.checked : false,
                capped: r.capped,
                // 31.1 — present only on the unknown-original-net path; carries
                // the derived spool capacity so the caller seeds initial_weight.
                derived_initial: r.derived_initial,
            };
            cleanup();
            if (typeof onSubmit === 'function') onSubmit(payload);
        }

        function attemptCancel() {
            cleanup();
            if (typeof onCancel === 'function') onCancel();
        }

        function cleanup() {
            document.removeEventListener('keydown', onKey, true);
            overlayHandle.cleanup();
        }

        function onKey(e) {
            // Escape is owned by mountOverlay's onEscape — see openModal caller.
            if (e.key === 'Enter') {
                if (e.target && e.target.classList && e.target.classList.contains('fcc-we-tab')) return;
                e.preventDefault();
                attemptSave();
            } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                if (e.target === inputEl) return; // don't steal cursor nav inside input
                e.preventDefault();
                const idx = availableModes.indexOf(mode);
                const next = (e.key === 'ArrowRight')
                    ? availableModes[(idx + 1) % availableModes.length]
                    : availableModes[(idx - 1 + availableModes.length) % availableModes.length];
                applyMode(next);
            } else if ((e.key === 'd' || e.key === 'D') && !e.ctrlKey && !e.metaKey && !e.altKey) {
                // 13.9 — bind D to "Set current mode as default". The value
                // input takes most chars but its inputmode is decimal-only,
                // so D is unused there; still, don't hijack when focus is on
                // the input mid-edit.
                if (e.target === inputEl) return;
                e.preventDefault();
                persistCurrentModeAsDefault();
            }
        }

        tabsEl.addEventListener('click', (e) => {
            const btn = e.target.closest('.fcc-we-tab');
            if (!btn) return;
            applyMode(btn.dataset.mode);
        });
        inputEl.addEventListener('input', updatePreview);
        saveBtn.addEventListener('click', attemptSave);
        cancelBtn.addEventListener('click', attemptCancel);
        closeBtn.addEventListener('click', attemptCancel);
        setDefaultBtn.addEventListener('click', persistCurrentModeAsDefault);
        document.addEventListener('keydown', onKey, true);

        applyMode(mode);
        // Initial focus is handled by mountOverlay's initialFocus option.
    }

    window.WeightEntry = { openModal };
})();
