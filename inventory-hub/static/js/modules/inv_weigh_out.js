/* MODULE: BULK WEIGH-OUT */
console.log("⚖️ Loaded Module: BULK WEIGH-OUT");

let processedWeighIds = new Set();

window.openWeighOutModal = () => {
    // Sync UI to state.heldSpools but ignore processed ones for this session
    processedWeighIds.clear();
    renderWeighOutList();
    modals.weighOutModal.show();
    
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

    let html = "";
    activeSpools.forEach((spool, index) => {
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
                </div>
                <div class="input-group" style="width: 150px;">
                    <input type="number" class="form-control bg-dark text-white border-secondary weigh-input" 
                        data-id="${spool.id}" placeholder="${currentWeightDisplay}" 
                        onkeydown="window.handleWeighInput(event, this)">
                    <span class="input-group-text bg-secondary text-light border-secondary">g</span>
                </div>
                <button class="btn btn-outline-success btn-sm weigh-save-btn" data-id="${spool.id}" onclick="window.saveSpoolWeight(${spool.id}, this.previousElementSibling.querySelector('input').value)">
                    💾
                </button>
            </div>
        `;
    });

    container.innerHTML = html;
};

window.handleWeighInput = (e, inputEl) => {
    // If enter pressed, trigger save
    if (e.key === 'Enter') {
        e.preventDefault();
        const sid = inputEl.dataset.id;
        const weight = inputEl.value;
        if (weight !== '') {
            window.saveSpoolWeight(sid, weight);
        } else {
            // Just skip to next if empty
            focusNextInput(inputEl);
        }
    }
};

window.saveSpoolWeight = (idStr, newWeight, updatesObj = null, autoArchiveOpts = null) => {
    let updates = updatesObj || {};
    if (newWeight !== null && newWeight !== "" && !isNaN(newWeight)) {
        updates.remaining_weight = parseFloat(newWeight);
    }

    if (Object.keys(updates).length === 0) return;

    const id = parseInt(idStr, 10);
    
    // Check auto archive for the bulk weigh out modal specifically
    const autoToggle = document.getElementById('weigh-auto-archive');
    let shouldArchive = false;
    if (autoArchiveOpts !== null) {
        shouldArchive = autoArchiveOpts;
    } else if (autoToggle && autoToggle.checked && updates.remaining_weight !== undefined && updates.remaining_weight <= 0) {
        shouldArchive = true;
    }
    
    if (shouldArchive && updates.remaining_weight !== undefined && updates.remaining_weight <= 0) {
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

