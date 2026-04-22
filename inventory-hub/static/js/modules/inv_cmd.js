/* MODULE: COMMAND CENTER (Dashboard & Buffer) - Polished v2 */
console.log("🚀 Loaded Module: COMMAND CENTER");

// --- BUFFER UI ---
const renderBuffer = () => {
    const z = document.getElementById('buffer-zone');
    const n = document.getElementById('buffer-nav-deck');

    // 1. Render Dashboard Buffer Zone
    if (z) {
        if (state.heldSpools.length === 0) {
            z.innerHTML = `<div class="buffer-empty-msg">Buffer Empty</div>`;
        } else {
            z.innerHTML = state.heldSpools.map((s, i) => {
                return window.SpoolCardBuilder.buildCard(s, 'buffer', { isFirst: i === 0, index: i });
            }).join('');

            state.heldSpools.forEach((s, i) => generateSafeQR(`qr-buf-${i}`, "ID:" + s.id, 74));
        }
    }

    // 2. Render Dashboard Nav Deck (If present on Dashboard)
    if (n) {
        if (state.heldSpools.length > 1) {
            const nextSpool = state.heldSpools[1];
            const prevSpool = state.heldSpools[state.heldSpools.length - 1];
            const prevStyles = getFilamentStyle(prevSpool.color, prevSpool.color_direction || 'longitudinal');
            const nextStyles = getFilamentStyle(nextSpool.color, nextSpool.color_direction || 'longitudinal');

            n.style.display = 'flex';
            n.innerHTML = 
                window.SpoolCardBuilder.buildCard(prevSpool, 'buffer_nav', { navDirection: 'prev', navAction: 'window.prevBuffer()' }) + 
                window.SpoolCardBuilder.buildCard(nextSpool, 'buffer_nav', { navDirection: 'next', navAction: 'window.nextBuffer()' });
            generateSafeQR("qr-nav-prev", "CMD:PREV", 74);
            generateSafeQR("qr-nav-next", "CMD:NEXT", 74);
        } else { n.style.display = 'none'; }
    }

    // 3. Dispatch Event for Location Manager
    document.dispatchEvent(new CustomEvent('inventory:buffer-updated', { detail: { spools: state.heldSpools } }));

    // 4. Save state if not currently syncing from server
    if (!window.isBufferSyncing) persistBuffer();
};

const removeBufferItem = (id) => {
    const idx = state.heldSpools.findIndex(s => s.id == id);
    if (idx > -1) {
        state.heldSpools.splice(idx, 1);
        renderBuffer();
        showToast("Item Dropped 🗑️");
        if (state.dropMode && state.heldSpools.length === 0) toggleDropMode();
    } else { showToast("Item not in buffer", "warning"); }
};

const requestClearBuffer = () => { if (state.heldSpools.length === 0) return; requestConfirmation("Clear entire Buffer?", clearBuffer); };
const clearBuffer = () => { state.heldSpools = []; renderBuffer(); showToast("Buffer Cleared"); };
const nextBuffer = () => { if (state.heldSpools.length > 1) { state.heldSpools.push(state.heldSpools.shift()); renderBuffer(); } };
const prevBuffer = () => { if (state.heldSpools.length > 1) { state.heldSpools.unshift(state.heldSpools.pop()); renderBuffer(); } };

// --- MODES ---
const toggleDropMode = () => { state.dropMode = !state.dropMode; state.ejectMode = false; updateDeckVisuals(); };
const toggleEjectMode = () => { state.ejectMode = !state.ejectMode; state.dropMode = false; updateDeckVisuals(); };
window.resetCommandModes = () => { state.dropMode = false; state.ejectMode = false; updateDeckVisuals(); };
const toggleAudit = () => {
    state.auditActive = !state.auditActive;
    updateLogState(true);
    const cmd = state.auditActive ? "CMD:AUDIT" : "CMD:DONE";
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: cmd }) });
};

const updateDeckVisuals = () => {
    const dropBtn = document.getElementById('btn-deck-drop');
    const ejectBtn = document.getElementById('btn-deck-eject');
    const bufCol = document.querySelector('.col-buffer');

    if (dropBtn) dropBtn.classList.remove('drop-mode-active');
    if (ejectBtn) ejectBtn.classList.remove('eject-mode-active');
    if (bufCol) bufCol.classList.remove('drop-mode-active', 'eject-mode-active');

    if (state.dropMode) {
        if (dropBtn) dropBtn.classList.add('drop-mode-active');
        if (bufCol) bufCol.classList.add('drop-mode-active');
        showToast("DROP MODE: Scan to delete", "warning");
    } else if (state.ejectMode) {
        if (ejectBtn) ejectBtn.classList.add('eject-mode-active');
        if (bufCol) bufCol.classList.add('eject-mode-active');
        showToast("EJECT MODE: Scan to remove spool", "warning");
    }
};

window.updateAuditVisuals = () => {
    const deckBtn = document.getElementById('btn-deck-audit');
    const lbl = document.getElementById('lbl-audit');
    const qrDiv = document.getElementById('qr-audit');
    if (state.auditActive) {
        if (deckBtn) deckBtn.classList.add('btn-audit-active');
        if (lbl) { lbl.innerText = "FINISH"; lbl.classList.add('label-active-audit'); }
        if (qrDiv) { qrDiv.innerHTML = ""; generateSafeQR('qr-audit', "CMD:DONE", 85); }
    } else {
        if (deckBtn) deckBtn.classList.remove('btn-audit-active');
        if (lbl) { lbl.innerText = "AUDIT"; lbl.classList.remove('label-active-audit'); }
        if (qrDiv) { qrDiv.innerHTML = ""; generateSafeQR('qr-audit', "CMD:AUDIT", 85); }
    }
};

// --- SCAN ROUTER ---
const processScan = (text, source = 'keyboard') => {
    const upper = text.toUpperCase();
    if (upper === 'CMD:AUDIT') { toggleAudit(); return; }
    if (upper === 'CMD:LOCATIONS') { openLocationsModal(); return; }
    if (upper === 'CMD:WEIGH') { window.openWeighOutModal(); return; }
    if (upper === 'CMD:DROP') { toggleDropMode(); return; }
    if (upper === 'CMD:EJECT') { toggleEjectMode(); return; }
    if (upper === 'CMD:EJECTALL') { triggerEjectAll(document.getElementById('manage-loc-id').value); return; }
    if (upper === 'CMD:UNDO') { triggerUndo(); return; }
    if (upper === 'CMD:CLEAR') { requestClearBuffer(); return; }
    if (upper === 'CMD:PREV') { prevBuffer(); return; }
    if (upper === 'CMD:NEXT') { nextBuffer(); return; }
    if (upper.startsWith('CMD:PRINT:')) { const parts = upper.split(':'); if (parts[2]) window.printLabel(parts[2]); return; }
    if (upper.startsWith('CMD:TRASH:')) { const parts = upper.split(':'); if (parts[2] && document.getElementById('manageModal').classList.contains('show')) ejectSpool(parts[2], document.getElementById('manage-loc-id').value, false); return; }

    if (state.activeModal === 'safety') return upper.includes('CONFIRM') ? confirmSafety(true) : (upper.includes('CANCEL') ? confirmSafety(false) : null);
    if (state.activeModal === 'confirm') return upper.includes('CONFIRM') ? confirmAction(true) : (upper.includes('CANCEL') ? confirmAction(false) : null);
    if (state.activeModal === 'action') { if (upper.includes('CANCEL')) { closeModal('actionModal'); return; } if (upper.startsWith('CMD:MODAL:')) { closeModal('actionModal'); state.modalCallbacks[parseInt(upper.split(':')[2])](); return; } }

    setProcessing(true);
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text, source: source }) })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (res.type === 'command') {
                const cmds = { 'clear': requestClearBuffer, 'undo': triggerUndo, 'eject': toggleEjectMode, 'done': closeManage };
                if (cmds[res.cmd]) cmds[res.cmd]();
                else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true);
                else if (res.cmd === 'slot') handleSlotInteraction(res.value);
                else if (res.cmd === 'ejectall') triggerEjectAll(document.getElementById('manage-loc-id').value);
            } else if (res.type === 'assignment') {
                // Backend now handles the load when the buffer is non-empty.
                // We switch on `action` and let the backend's Activity Log
                // cover success/error cases; the frontend only handles the
                // no-buffer fallback (treat as a slot pickup).
                state.lastScannedLoc = null;
                if (res.action === 'assignment_done' || res.action === 'assignment_partial') {
                    // Backend already moved the spool and logged it. Mirror by
                    // dropping the moved id out of heldSpools so the UI matches.
                    const movedId = res.moved;
                    if (movedId != null) {
                        state.heldSpools = state.heldSpools.filter(s => s.id !== movedId);
                        renderBuffer();
                    }
                    const extraMsg = res.action === 'assignment_partial'
                        ? ` (${res.remaining_buffer} still in buffer)`
                        : '';
                    showToast(
                        `✅ Loaded #${movedId} into ${res.location}:${res.slot}${extraMsg}`,
                        res.action === 'assignment_partial' ? 'info' : 'success',
                        res.action === 'assignment_partial' ? 5000 : 4000
                    );
                    document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                } else if (res.action === 'assignment_no_buffer') {
                    // Buffer Empty → treat as pickup: read slot contents and
                    // put the spool in the buffer. Log explicitly on success
                    // so the user's Activity Log reflects what happened.
                    fetch(`/api/get_contents?id=${res.location}`)
                        .then(r => r.json())
                        .then(items => {
                            const item = items.find(i => String(i.slot) === String(res.slot));
                            if (item) {
                                if (state.heldSpools.some(s => s.id === item.id)) {
                                    showToast("Already in Buffer", "warning", 3500);
                                } else {
                                    state.heldSpools.unshift({ id: item.id, display: item.display, color: item.color, color_direction: item.color_direction, remaining_weight: item.remaining_weight, details: item.details, archived: item.archived });
                                    renderBuffer();
                                    showToast(`✋ Picked up #${item.id} from ${res.location}:SLOT:${res.slot}`, 'success', 2500);
                                    fetch('/api/log_event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msg: `✋ Pickup: Spool #${item.id} from <b>${res.location}:SLOT:${res.slot}</b>`, level: 'INFO' }) });
                                }
                            } else {
                                showToast(`Slot ${res.slot} on ${res.location} is empty — opening manager`, 'info', 3000);
                                if (window.logClientEvent) window.logClientEvent(
                                    `⚠️ Slot scan ${res.location}:SLOT:${res.slot} — slot is empty (opened manager)`,
                                    'WARNING'
                                );
                                openManage(res.location);
                            }
                        })
                        .catch(e => {
                            console.error(e);
                            showToast("Error looking up slot", "error", 5000);
                            if (window.logClientEvent) window.logClientEvent(
                                `❌ Slot pickup failed for ${res.location}:SLOT:${res.slot}: ${e && e.message ? e.message : 'network error'}`,
                                'ERROR'
                            );
                        });
                } else if (res.action === 'assignment_bad_slot') {
                    const limit = res.max_slots != null ? ` (has ${res.max_slots} slots)` : '';
                    showToast(`❌ Slot ${res.slot} invalid for ${res.location}${limit}`, 'error', 5000);
                } else if (res.action === 'assignment_bad_target') {
                    showToast(`❌ ${res.location} isn't a valid load target`, 'error', 5000);
                } else {
                    // Unknown action code — shouldn't happen, but surface it.
                    showToast(`Unknown assignment result: ${res.action || 'none'}`, 'warning', 4000);
                    if (window.logClientEvent) window.logClientEvent(
                        `⚠️ Unknown assignment action from backend: ${res.action || 'none'}`,
                        'WARNING'
                    );
                }
            } else if (res.type === 'location') {
                if (!text.toUpperCase().startsWith('LOC:')) {
                    const msg = "⚠️ Legacy Location Label Scanned! Features may be limited. Print a new LOC: label when possible.";
                    showToast(msg, "warning", 3500);
                    fetch('/api/log_event', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg: "SCAN LOG: Legacy Location Barcode Scanned (" + text + ")", level: "WARNING"}) });
                }
                if (state.lastScannedLoc === res.id) { state.heldSpools = []; renderBuffer(); openManage(res.id); state.lastScannedLoc = null; return; }
                if (state.heldSpools.length > 0) { performContextAssign(res.id); state.lastScannedLoc = null; return; }
                const locData = state.allLocations.find(l => l.LocationID === res.id);
                if ((!locData || parseInt(locData['Max Spools']) <= 1) && res.contents && res.contents.length > 0) {
                    const spool = res.contents[0];
                    state.heldSpools.unshift({ id: spool.id, display: spool.display, color: spool.color, color_direction: spool.color_direction, remaining_weight: spool.remaining_weight, details: spool.details, archived: spool.archived, location: spool.location, is_ghost: spool.is_ghost, slot: spool.slot, deployed_to: spool.deployed_to });
                    renderBuffer();
                    showToast("⚡ Quick Pick: #" + spool.id);
                    state.lastScannedLoc = res.id;
                    return;
                }
                openManage(res.id); state.lastScannedLoc = res.id;
            } else if (res.type === 'spool') {
                if (state.dropMode) { removeBufferItem(res.id); return; }
                if (state.ejectMode) { ejectSpool(res.id, "Scan", false); return; }

                state.lastScannedLoc = null;
                if (!res.display) { showToast("Spool ID found but data missing!", "error"); return; }
                if (state.heldSpools.some(s => s.id === res.id)) showToast("Already in Buffer", "warning");
                else { state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color, color_direction: res.color_direction, remaining_weight: res.remaining_weight, details: res.details, archived: res.archived, location: res.location, is_ghost: res.is_ghost, slot: res.slot, deployed_to: res.deployed_to }); renderBuffer(); }
            } else if (res.type === 'filament') {
                openFilamentDetails(res.id);
            } else if (res.type === 'error') showToast(res.msg, 'error');
        })
        .catch((e) => { setProcessing(false); console.error(e); showToast("Scan Error", "error"); });
};

const performContextAssign = (tid, slot = null) => {
    setProcessing(true);
    // [ALEX FIX] Bulk Assign: Send ALL held spools, not just the first one
    const payload = {
        location: tid,
        spools: state.heldSpools.map(s => s.id),
        slot: slot,
        origin: 'buffer'
    };

    fetch('/api/smart_move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (res.status === 'success') {
                showToast("Assigned " + state.heldSpools.length + " items!", "success");
                // [ALEX FIX] Clear entire buffer after bulk move
                state.heldSpools = [];
                renderBuffer();
                if (document.getElementById('manage-loc-id').value === tid) refreshManageView(tid);
                if (window.fetchLocations) window.fetchLocations();
            } else showToast(res.msg, 'error');
        })
        .catch(() => setProcessing(false));
};

const triggerUndo = () => fetch('/api/undo', { method: 'POST' }).then(() => { updateLogState(); loadBuffer(); if(window.fetchLocations) window.fetchLocations(); });

const printLabel = (sid) => {
    showToast("🖨️ Requesting Label...");
    setProcessing(true);
    fetch('/api/print_label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: sid })
    })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (!res.success) { showToast(res.msg || "Print Failed", "error"); return; }
            if (res.method === 'csv') { showToast(res.msg, "success"); return; }
            if (res.method === 'browser') {
                const data = res.data;
                if (!data || !data.filament) { showToast("Invalid Data", "error"); return; }
                const fil = data.filament;
                const extra = fil.extra || {};
                const colorHex = fil.color_hex || '000000';
                const rgb = hexToRgb(colorHex);
                let typeStr = fil.material || "Unknown";
                try {
                    let attrs = (typeof extra.filament_attributes === 'string') ? JSON.parse(extra.filament_attributes) : extra.filament_attributes;
                    if (Array.isArray(attrs) && attrs.length > 0) typeStr = attrs.join(' ') + ' ' + typeStr;
                } catch (err) { }
                const qrEl = document.getElementById('print-qr');
                if (qrEl) {
                    qrEl.innerHTML = "";
                    new QRCode(qrEl, { text: `ID:${sid}`, width: 120, height: 120, correctLevel: QRCode.CorrectLevel.L });
                }
                document.getElementById('lbl-brand').innerText = fil.vendor ? fil.vendor.name : "Generic";
                document.getElementById('lbl-color').innerText = extra.original_color ? extra.original_color.replace(/"/g, '') : fil.name;
                document.getElementById('lbl-type').innerText = typeStr;
                document.getElementById('lbl-hex').innerText = colorHex.toUpperCase();
                document.getElementById('lbl-id').innerText = sid;
                document.getElementById('lbl-rgb').innerText = `${rgb.r},${rgb.g},${rgb.b}`;
                setTimeout(() => window.print(), 500);
            }
        })
        .catch(e => { setProcessing(false); console.error(e); showToast("Connection Error", "error"); });
};

// EXPOSE GLOBALLY FOR LOC MANAGER
window.printLabel = printLabel;
window.renderBuffer = renderBuffer;
window.prevBuffer = prevBuffer;
window.nextBuffer = nextBuffer;
window.removeBufferItem = removeBufferItem;

// Hook into the render function to trigger saves automatically
window.isBufferSyncing = false; // Mutex for sync

/* --- PERSISTENCE LAYER: BUFFER (V3 Polling) --- */
const persistBuffer = () => {
    fetch('/api/state/buffer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ buffer: state.heldSpools })
    }).catch(e => console.warn("Buffer Save Failed", e));
};

const loadBuffer = () => {
    window.isBufferSyncing = true; // Block uploads
    fetch('/api/state/buffer')
        .then(r => r.json())
        .then(data => {
            if (Array.isArray(data)) {
                const currentStr = JSON.stringify(state.heldSpools);
                const serverStr = JSON.stringify(data);

                if (currentStr !== serverStr) {
                    console.log("🔄 Syncing Buffer from Server...");
                    state.heldSpools = data;
                    if (window.renderBuffer) window.renderBuffer();
                    // [ALEX FIX] Trigger a proactive backfill sync since old DB state didn't track remaining_weight
                    setTimeout(liveRefreshBuffer, 500);
                }
            }
            window.isBufferSyncing = false; // Unblock
        })
        .catch(e => {
            console.warn("Buffer Load Failed", e);
            window.isBufferSyncing = false;
        });
};

// --- LIVE REFRESH POLLING ---
const liveRefreshBuffer = () => {
    if (!state.heldSpools || state.heldSpools.length === 0) return;

    // Only fetch if we are actually looking at the dashboard
    // No need to spam Spoolman if the user is in the Location Manager or elsewhere
    // Wait, the user specifically wants the buffer updated in the background even if they are in Manager, 
    // because the Manager uses the global buffer.
    const spoolIds = state.heldSpools.map(s => s.id);

    fetch('/api/spools/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spools: spoolIds })
    })
        .then(r => r.json())
        .then(data => {
            let changed = false;
            state.heldSpools.forEach(s => {
                const fresh = data[s.id];
                if (fresh && (fresh.display !== s.display || fresh.color !== s.color || fresh.remaining_weight !== s.remaining_weight || fresh.color_direction !== s.color_direction || !s.details || fresh.archived !== s.archived)) {
                    s.display = fresh.display;
                    s.color = fresh.color;
                    s.color_direction = fresh.color_direction;
                    s.remaining_weight = fresh.remaining_weight;
                    s.details = fresh.details;
                    s.archived = fresh.archived;
                    changed = true;
                }
            });
            if (changed) {
                if (window.renderBuffer) window.renderBuffer();
            }
        })
        .catch(e => console.warn("Live Refresh Buffer Failed", e));
};

document.addEventListener('inventory:sync-pulse', liveRefreshBuffer);

// Heartbeat (Checks every 2 seconds)
setInterval(loadBuffer, 2000);

// Initial Load
document.addEventListener('DOMContentLoaded', loadBuffer);

window.addSpoolToBuffer = (id) => {
    // [ALEX FIX] Reuse the Scanner Logic! 
    // Instead of manually fetching and building the object, we just tell the 
    // scanner router that this ID was "scanned". This ensures consistent behavior 
    // and data formatting between physical scans and UI clicks.
    // Must prefix with ID: so the Python backend doesn't think it's a legacy barcode
    console.log(`📥 Simulating Scan for Spool #${id}`);
    processScan('ID:' + id.toString());
};

window.processScan = processScan;