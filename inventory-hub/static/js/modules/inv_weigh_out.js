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

window.openQuickWeigh = (spoolId) => {
    setProcessing(true);
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            setProcessing(false);
            if (!d || !d.id) { showToast("Spool Not Found", "error"); return; }
            
            const rem = d.remaining_weight !== null ? Math.round(d.remaining_weight) : 0;
            const initial = d.initial_weight || d.filament?.weight || 1000;
            const empty = d.empty_weight !== null ? d.empty_weight : (d.filament?.spool_weight || 0);

            let safeName = d.filament?.name || 'Unknown';
            
            document.getElementById('qw-spool-id').value = d.id;
            document.getElementById('qw-title').innerText = `ID: ${d.id} - ${safeName}`;
            document.getElementById('qw-meta-initial').innerText = `${initial}g`;
            document.getElementById('qw-meta-initial-val').value = initial;
            document.getElementById('qw-meta-empty').innerText = empty > 0 ? `${empty}g` : 'Unknown';
            
            let elRem = document.getElementById('qw-remaining');
            const newRem = elRem.cloneNode(true);
            elRem.parentNode.replaceChild(newRem, elRem);
            
            let elDeduct = document.getElementById('qw-deduct');
            const newDeduct = elDeduct.cloneNode(true);
            elDeduct.parentNode.replaceChild(newDeduct, elDeduct);

            newRem.value = rem;
            newDeduct.value = "";
            document.getElementById('qw-auto-archive').checked = true;
            
            const originalRem = rem;
            newDeduct.addEventListener('input', () => {
                let v = newDeduct.value.trim();
                if (v === "" || v === "+" || v === "-") {
                    newRem.value = originalRem;
                    return;
                }
                
                let isAdd = v.startsWith('+');
                let amount = parseFloat(v);
                
                if (!isNaN(amount)) {
                    let nr = originalRem;
                    if (isAdd) {
                        nr = originalRem + Math.abs(amount); 
                    } else {
                        // Whether they type 25 or -25, we treat it as a deduction of Mat.abs(25) = 25.
                        nr = originalRem - Math.abs(amount);
                    }
                    newRem.value = nr >= 0 ? nr : 0;
                } else {
                    newRem.value = originalRem;
                }
            });

            const handleEnter = (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    window.saveQuickWeigh();
                }
            };
            
            newRem.addEventListener('keydown', handleEnter);
            newDeduct.addEventListener('keydown', handleEnter);

            // Defeat Bootstrap Focus Trapping on Nested Modals
            document.querySelectorAll('.modal.show:not(#quickWeighModal)').forEach(m => {
                m.removeAttribute('tabindex');
                m.setAttribute('data-fcc-restored-tabindex', 'true');
            });

            // If modals object doesn't have it explicitly bound, cache it
            if (!window.qwModalInstance) {
                window.qwModalInstance = new bootstrap.Modal(document.getElementById('quickWeighModal'), {
                    focus: true,
                    backdrop: 'static'
                });
                document.getElementById('quickWeighModal').addEventListener('shown.bs.modal', () => {
                    document.getElementById('qw-deduct').focus();
                });
                document.getElementById('quickWeighModal').addEventListener('hidden.bs.modal', () => {
                    document.querySelectorAll('[data-fcc-restored-tabindex="true"]').forEach(m => {
                        m.setAttribute('tabindex', '-1');
                        m.removeAttribute('data-fcc-restored-tabindex');
                        // Optional: Reset focus to the parent modal if needed
                        m.focus();
                    });
                });
            }
            
            window.qwModalInstance.show();
        })
        .catch(e => {
            setProcessing(false);
            console.error(e);
            showToast("Network Error", "error");
        });
};

window.saveQuickWeigh = () => {
    const sid = document.getElementById('qw-spool-id').value;
    const rem = document.getElementById('qw-remaining').value;
    const isAutoArchive = document.getElementById('qw-auto-archive').checked;
    
    if (!sid) return;
    
    const updates = {};
    if (rem !== "") updates.remaining_weight = parseFloat(rem);
    
    let autoArchive = false;
    if (updates.remaining_weight !== undefined && updates.remaining_weight <= 0 && isAutoArchive) {
        autoArchive = true;
    }
    
    if (window.qwModalInstance) window.qwModalInstance.hide();
    
    window.saveSpoolWeight(sid, null, updates, autoArchive);
};

