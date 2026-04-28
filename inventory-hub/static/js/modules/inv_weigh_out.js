/* MODULE: BULK WEIGH-OUT */
console.log("⚖️ Loaded Module: BULK WEIGH-OUT");

let processedWeighIds = new Set();

// Phase 2 (Group 12): modal-level weigh-out mode. Defaults to 'net' so the
// historical "input is remaining filament weight" UX is preserved. Switching
// to gross / additive / set_used routes the row's input through
// computeUsedWeight() with the spool's resolved cascade (initial / used /
// empty_spool_weight). Stored on window so the unit-test harness can inspect.
window.weighOutMode = 'net';

// Per-spool details cache populated on modal open and on buffer-updated.
// Keyed by spool id. Each entry: { initial, used, empty, cascade, context, fetchedAt }.
const weighOutDetailsCache = new Map();
const MODE_HINTS = {
    gross: 'used = initial − (gross − empty_tare)',
    net: 'used = initial − net',
    additive: 'used = current_used + delta',
    set_used: 'used = value (override)',
};
const MODE_PLACEHOLDERS = {
    gross: 'scale w/ spool',
    net: 'remaining',
    additive: '+25 / -10',
    set_used: 'used',
};
const MODE_INPUT_TYPES = {
    gross: 'number',
    net: 'number',
    additive: 'text',
    set_used: 'number',
};

const fetchSpoolDetails = (id) => {
    return fetch(`/api/spool_details?id=${id}`)
        .then((r) => r.json())
        .then((d) => {
            if (!d || !d.id) return null;
            const cascade = {
                spoolWt: d.spool_weight,
                filamentWt: d.filament?.spool_weight,
                vendor: d.filament?.vendor,
            };
            const { value: empty } = window.resolveEmptySpoolWeightSource(cascade);
            const entry = {
                initial: Number(d.initial_weight) || Number(d.filament?.weight) || 0,
                used: Number(d.used_weight) || 0,
                empty,
                cascade,
                context: {
                    vendor: d.filament?.vendor?.name || '',
                    material: d.filament?.material || '',
                    color: d.filament?.name || '',
                    color_hex: d.filament?.color_hex || d.color_hex || null,
                },
                fetchedAt: Date.now(),
            };
            weighOutDetailsCache.set(d.id, entry);
            return entry;
        })
        .catch(() => null);
};

const refreshAllRowPreviews = () => {
    document.querySelectorAll('.weigh-row').forEach((row) => {
        const inp = row.querySelector('.weigh-input');
        if (inp) updateWeighRowPreview(inp);
    });
};

const setWeighOutMode = (mode) => {
    if (!['gross', 'net', 'additive', 'set_used'].includes(mode)) return;
    window.weighOutMode = mode;
    document.querySelectorAll('#weigh-out-mode [data-mode]').forEach((btn) => {
        const active = btn.dataset.mode === mode;
        btn.classList.toggle('btn-info', active);
        btn.classList.toggle('btn-outline-info', !active);
    });
    const hint = document.getElementById('weigh-out-mode-hint');
    if (hint) hint.innerText = MODE_HINTS[mode] || '';
    // Refresh placeholders + input types + previews on every visible row.
    document.querySelectorAll('.weigh-input').forEach((inp) => {
        inp.type = MODE_INPUT_TYPES[mode];
        inp.placeholder = MODE_PLACEHOLDERS[mode];
    });
    refreshAllRowPreviews();
};

window.openWeighOutModal = () => {
    // Sync UI to state.heldSpools but ignore processed ones for this session
    processedWeighIds.clear();
    renderWeighOutList();
    modals.weighOutModal.show();

    // Wire the mode selector exactly once per page lifetime.
    const modeBar = document.getElementById('weigh-out-mode');
    if (modeBar && !modeBar.dataset.fccBound) {
        modeBar.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-mode]');
            if (!btn) return;
            setWeighOutMode(btn.dataset.mode);
        });
        modeBar.dataset.fccBound = '1';
    }
    setWeighOutMode(window.weighOutMode || 'net');

    // Prefetch details for each held spool so previews can render eagerly.
    state.heldSpools
        .filter((s) => !processedWeighIds.has(s.id))
        .forEach((s) => {
            fetchSpoolDetails(s.id).then(() => {
                const inp = document.querySelector(`.weigh-input[data-id="${s.id}"]`);
                if (inp) updateWeighRowPreview(inp);
            });
        });

    // Auto-focus the first empty input after modal shown
    setTimeout(() => {
        const firstInput = document.querySelector('.weigh-input:not(:disabled)');
        if (firstInput) firstInput.focus();
    }, 500);
};

// Also refresh the UI any time the buffer updates while the modal is open
document.addEventListener('inventory:buffer-updated', () => {
    const weighModalEl = document.getElementById('weighOutModal');
    if (weighModalEl && weighModalEl.classList.contains('show')) {
        renderWeighOutList();
        // New spools may have appeared — fetch details for any uncached.
        state.heldSpools.forEach((s) => {
            if (!processedWeighIds.has(s.id) && !weighOutDetailsCache.has(s.id)) {
                fetchSpoolDetails(s.id).then(() => {
                    const inp = document.querySelector(`.weigh-input[data-id="${s.id}"]`);
                    if (inp) updateWeighRowPreview(inp);
                });
            }
        });
    }
});

const renderWeighOutList = () => {
    const container = document.getElementById('weigh-out-list');
    const emptyMsg = document.getElementById('weigh-out-empty');
    const countBadge = document.getElementById('weigh-out-count');

    const activeSpools = state.heldSpools.filter(s => !processedWeighIds.has(s.id));

    countBadge.innerText = `${activeSpools.length} Spools Ready`;

    if (activeSpools.length === 0) {
        container.innerHTML = "";
        emptyMsg.style.display = "block";
        return;
    }

    emptyMsg.style.display = "none";

    const mode = window.weighOutMode || 'net';
    const inputType = MODE_INPUT_TYPES[mode];
    const placeholder = MODE_PLACEHOLDERS[mode];

    let html = "";
    activeSpools.forEach((spool) => {
        const styles = getFilamentStyle(spool.color, spool.color_direction || 'longitudinal');
        const nameParts = spool.display.split('-');
        let mainName = spool.display;
        if(nameParts.length > 2) {
            mainName = nameParts.slice(0, 2).join('-');
        }

        let currentWeightDisplay = spool.remaining_weight ? Math.round(spool.remaining_weight) : '';

        html += `
            <div class="card bg-dark border-secondary p-2 d-flex flex-row align-items-center gap-3 weigh-row" data-id="${spool.id}" style="border-left: 5px solid ${styles.frame};">
                <div style="width: 25px; height: 25px; border-radius: 5px; background: ${styles.inner}; border: 1px solid #555;"></div>
                <div class="flex-grow-1">
                    <div class="fw-bold text-light flex-wrap">ID:${spool.id} - ${mainName}</div>
                    <div class="small w-100 text-white-50 d-inline-block pb-1">Current: ${currentWeightDisplay ? currentWeightDisplay + 'g' : 'Unknown'}</div>
                    <div class="small text-info weigh-row-preview" data-id="${spool.id}" style="min-height:1em;"></div>
                </div>
                <div class="input-group" style="width: 150px;">
                    <input type="${inputType}" class="form-control bg-dark text-white border-secondary weigh-input"
                        data-id="${spool.id}" placeholder="${placeholder}"
                        oninput="window.updateWeighRowPreview(this)"
                        onkeydown="window.handleWeighInput(event, this)">
                    <span class="input-group-text bg-secondary text-light border-secondary">g</span>
                </div>
                <button class="btn btn-outline-success btn-sm weigh-save-btn" data-id="${spool.id}" onclick="window.saveWeighOutRow(${spool.id})">
                    💾
                </button>
            </div>
        `;
    });

    container.innerHTML = html;
};

// Compute used_weight for a row given the modal-level mode + the cached
// spool details + the row's typed input. Returns the computeUsedWeight
// result object (or null when details aren't loaded yet / input is empty).
const computeRowResult = (id, rawInputValue) => {
    const details = weighOutDetailsCache.get(Number(id));
    if (!details) return null;
    const mode = window.weighOutMode || 'net';
    let value;
    if (mode === 'additive') {
        const parsed = window.parseAdditiveInput(rawInputValue);
        value = parsed.value;
    } else {
        if (rawInputValue === '' || rawInputValue === null || rawInputValue === undefined) return null;
        value = Number(rawInputValue);
    }
    if (value === null || Number.isNaN(value)) return null;
    return window.computeUsedWeight({
        mode,
        value,
        initial_weight: details.initial,
        current_used: details.used,
        empty_spool_weight: details.empty,
    });
};

// Live mini-preview under each row. Mirrors the WeightEntry overlay's
// preview semantics so users see the same numbers regardless of surface.
window.updateWeighRowPreview = (inputEl) => {
    if (!inputEl) return;
    const id = inputEl.dataset.id;
    const previewEl = document.querySelector(`.weigh-row-preview[data-id="${id}"]`);
    if (!previewEl) return;
    const raw = inputEl.value;
    if (raw === '' || raw === '+' || raw === '-') {
        previewEl.innerText = '';
        return;
    }
    const r = computeRowResult(id, raw);
    if (!r) {
        previewEl.innerText = ''; // details still loading
        return;
    }
    if (r.error) {
        previewEl.innerHTML = `<span style="color:#f88;">Invalid input</span>`;
        return;
    }
    if (r.requires_empty) {
        previewEl.innerHTML = `<span style="color:#f5b342;">⚠ missing tare — Save will prompt</span>`;
        return;
    }
    let cap = '';
    if (r.capped === 'high') cap = ' <span style="color:#f5b342;">(capped)</span>';
    else if (r.capped === 'low') cap = ' <span style="color:#f5b342;">(clamped to 0)</span>';
    previewEl.innerHTML = `→ used <strong>${Math.round(r.used_weight)}g</strong> · remaining <strong>${Math.round(r.remaining)}g</strong>${cap}`;
};

window.handleWeighInput = (e, inputEl) => {
    // If enter pressed, trigger save
    if (e.key === 'Enter') {
        e.preventDefault();
        const sid = inputEl.dataset.id;
        const weight = inputEl.value;
        if (weight !== '') {
            window.saveWeighOutRow(sid);
        } else {
            // Just skip to next if empty
            focusNextInput(inputEl);
        }
    }
};

// New per-row save path that runs the typed value through computeUsedWeight
// before handing off to saveSpoolWeight (which still owns the actual write,
// auto-archive flag, force-unassign chain, and sync-pulse dispatch).
window.saveWeighOutRow = async (idStr) => {
    const id = Number(idStr);
    const inputEl = document.querySelector(`.weigh-input[data-id="${id}"]`);
    if (!inputEl) return;
    const raw = inputEl.value;
    if (raw === '' || raw === '+' || raw === '-') return;

    let details = weighOutDetailsCache.get(id);
    if (!details) details = await fetchSpoolDetails(id);
    if (!details) {
        // Fallback: backend treats `newWeight` as remaining_weight.
        window.saveSpoolWeight(id, raw);
        return;
    }

    let r = computeRowResult(id, raw);
    if (!r || r.error) {
        showToast('Could not compute used weight', 'error');
        return;
    }
    if (r.requires_empty) {
        // Gross + missing tare. Use the shared inline overlay so the user
        // can fill it in without leaving the bulk flow.
        const tare = await window.promptMissingEmptyWeight(details.context || {});
        if (tare === null) return;
        details.empty = Number(tare);
        weighOutDetailsCache.set(id, details);
        r = computeRowResult(id, raw);
        if (!r || r.error || r.requires_empty) {
            showToast('Could not compute used weight', 'error');
            return;
        }
    }

    // Hand off to saveSpoolWeight with a precomputed used_weight payload.
    // saveSpoolWeight's auto-archive check inspects remaining_weight, but
    // we're submitting used_weight — so compute the auto-archive verdict
    // locally and pass it explicitly via the 4th arg.
    const remainingAfter = Math.max(0, details.initial - r.used_weight);
    const autoToggle = document.getElementById('weigh-auto-archive');
    const autoArchive = !!(autoToggle && autoToggle.checked && remainingAfter <= 0);
    window.saveSpoolWeight(id, null, { used_weight: r.used_weight }, autoArchive);
};

window.saveSpoolWeight = (idStr, newWeight, updatesObj = null, autoArchiveOpts = null) => {
    let updates = updatesObj || {};
    if (newWeight !== null && newWeight !== "" && !isNaN(newWeight)) {
        updates.remaining_weight = parseFloat(newWeight);
    }

    if (Object.keys(updates).length === 0) return;

    const id = parseInt(idStr, 10);
    
    // Check auto archive for the bulk weigh out modal specifically.
    // When a caller passes autoArchiveOpts explicitly (true/false), it owns
    // the decision — phase-2 used_weight flows pre-compute the verdict and
    // pass it in. When autoArchiveOpts is null, fall back to the modal-level
    // toggle + remaining_weight check (legacy bulk-weigh-out behavior).
    const autoToggle = document.getElementById('weigh-auto-archive');
    let shouldArchive = false;
    if (autoArchiveOpts !== null) {
        shouldArchive = !!autoArchiveOpts;
    } else if (autoToggle && autoToggle.checked && updates.remaining_weight !== undefined && updates.remaining_weight <= 0) {
        shouldArchive = true;
    }

    if (shouldArchive) {
        updates.archived = true;
    }

    setProcessing(true);
    
    // Find the input element to provide visual feedback
    const rowEl = document.querySelector(`.weigh-row[data-id="${id}"]`);
    const inputEl = document.querySelector(`.weigh-input[data-id="${id}"]`);
    const btnEl = document.querySelector(`.weigh-save-btn[data-id="${id}"]`);
    
    if (inputEl) inputEl.disabled = true;
    if (btnEl) {
        btnEl.disabled = true;
        btnEl.innerText = "⏳";
    }

    fetch(`/api/spool/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            id: id,
            updates: updates
        })
    })
    .then(r => r.json())
    .then(res => {
        if (res.status === 'success') {
            const finalize = () => {
                setProcessing(false);
                showToast(`Updated Spool #${id}`, 'success');
                // Spool just auto-archived (weight hit 0) AND its filament
                // has no empty_spool_weight yet — prompt the user to weigh
                // the now-empty spool. Fires after the toast so it doesn't
                // stack on top of weigh-out success feedback.
                if (res && res.needs_empty_weight_prompt && res.filament_id && window.showArchiveEmptyWeightPrompt) {
                    setTimeout(() => window.showArchiveEmptyWeightPrompt(id, res.filament_id), 400);
                }
                
                // Visual feedback that it's done
                if (rowEl) {
                    rowEl.style.transition = 'opacity 0.3s';
                    rowEl.style.opacity = '0';
                    setTimeout(() => {
                        processedWeighIds.add(id);
                        renderWeighOutList();
                    }, 300);
                } else {
                    processedWeighIds.add(id);
                }
                if (btnEl) btnEl.innerText = "✅";
                
                // Also update the state buffer locally
                const s = state.heldSpools.find(x => x.id == id);
                if(s) {
                    if (updates.remaining_weight !== undefined) s.remaining_weight = parseFloat(updates.remaining_weight);
                    if (updates.archived) s.archived = true;
                    // Trigger instant local UI render so cards don't have to wait for the next heartbeat
                    if (window.renderBuffer) window.renderBuffer();
                }
                // Dispatch sync pulse to update other parts of the dashboard natively
                document.dispatchEvent(new CustomEvent('inventory:sync-pulse', {
                    detail: {
                        updatedSpool: {
                            id: id,
                            updates: updates
                        }
                    }
                }));
            };

            if (updates.archived) {
                fetch('/api/manage_contents', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'force_unassign', spool_id: id, location: '' })
                }).then(() => finalize()).catch(() => finalize());
            } else {
                finalize();
            }
            
        } else {
            setProcessing(false);
            showToast("Failed to update weight", "error");
            if (inputEl) inputEl.disabled = false;
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerText = "💾";
            }
        }
    })
    .catch(e => {
        setProcessing(false);
        console.error("Weigh update failed", e);
        showToast("Error updating weight", "error");
        if (inputEl) inputEl.disabled = false;
        if (btnEl) {
            btnEl.disabled = false;
            btnEl.innerText = "💾";
        }
    });

    // Move to the next input immediately so the user can keep working while it saves
    if (inputEl) focusNextInput(inputEl);
};

const focusNextInput = (currentInput) => {
    const inputs = Array.from(document.querySelectorAll('.weigh-input:not(:disabled)'));
    const currentIndex = inputs.indexOf(currentInput);
    if (currentIndex > -1 && currentIndex + 1 < inputs.length) {
        inputs[currentIndex + 1].focus();
    }
};

// Expose process scan specific to weigh out to capture commands if we want,
// but the global processScan handles adding items to state.heldSpools, which triggers the buffer-updated listener!

// Quick-Weigh — Phase 2 (Group 12) is now backed by <WeightEntry>
// (modules/weight_entry.js). The legacy #quickWeighModal markup is retained
// as a no-op placeholder until bulk weigh-out and FilaBridge manual recovery
// also migrate; at that point the markup can be deleted in one sweep.
//
// The new component is an inline overlay (no nested Bootstrap modal stacking,
// no Swal). On submit we hand off to saveSpoolWeight() unchanged so the
// auto-archive + force-unassign chain and inventory:sync-pulse / buffer-updated
// dispatches continue to flow through the same authoritative call path.
window.openQuickWeigh = (spoolId) => {
    setProcessing(true);
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            setProcessing(false);
            if (!d || !d.id) { showToast("Spool Not Found", "error"); return; }

            const initial = Number(d.initial_weight) || Number(d.filament?.weight) || 0;
            const used = Number(d.used_weight) || 0;
            const cascade = {
                spoolWt: d.spool_weight,
                filamentWt: d.filament?.spool_weight,
                vendor: d.filament?.vendor,
            };
            const { value: empty, source: emptySource } = window.resolveEmptySpoolWeightSource(cascade);
            const display = d.filament
                ? [d.filament.vendor?.name, d.filament.material, d.filament.name]
                    .filter(Boolean).join(' - ') || (d.filament.name || 'Unknown')
                : 'Unknown';
            const colorHex = d.filament?.color_hex || d.color_hex || null;

            window.WeightEntry.openModal({
                title: 'Quick Weigh',
                spool: { id: d.id, initial_weight: initial, used_weight: used,
                         display, color_hex: colorHex },
                empty_spool_weight: empty,
                empty_source: emptySource,
                cascade,
                context: {
                    vendor: d.filament?.vendor?.name || '',
                    material: d.filament?.material || '',
                    color: d.filament?.name || '',
                    color_hex: colorHex,
                },
                defaultMode: 'additive',
                availableModes: ['gross', 'net', 'additive', 'set_used'],
                showAutoArchive: true,
                autoArchiveDefault: true,
                onSubmit: (payload) => {
                    const updates = { used_weight: payload.used_weight };
                    // Used == initial means remaining hits zero; auto-archive
                    // gate matches the legacy behavior (auto-archive only when
                    // the toggle is on AND the spool emptied).
                    const autoArchive = !!payload.auto_archive &&
                        Math.max(0, initial - payload.used_weight) <= 0;
                    window.saveSpoolWeight(d.id, null, updates, autoArchive);
                },
            });
        })
        .catch(e => {
            setProcessing(false);
            console.error(e);
            showToast("Network Error", "error");
        });
};

// Backwards-compatible no-op kept so the legacy #quickWeighModal "Save Update"
// button (markup retained until other surfaces migrate) doesn't throw if
// somehow invoked during the transition. The new <WeightEntry> overlay
// submits via its own onSubmit handler.
window.saveQuickWeigh = () => { /* deprecated — superseded by <WeightEntry>.openModal */ };

