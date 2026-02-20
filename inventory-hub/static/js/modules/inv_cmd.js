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
                const styles = getFilamentStyle(s.color);
                const cleanText = (s.display || "").replace(/^#\d+\s*/, '').trim();
                return `
                <div class="cham-card buffer-item ${i === 0 ? 'active-item' : ''}" style="background: ${styles.frame};">
                    <div class="cham-body buffer-inner" style="background: ${styles.inner};">
                        <div class="cham-text-group" onclick="openSpoolDetails(${s.id})" style="cursor:pointer">
                            <div class="cham-id-badge" style="color: #fff; text-shadow: 2px 2px 4px #000;">#${s.id}</div>
                            <div class="cham-text" style="color: #fff; text-shadow: 2px 2px 4px #000; font-weight: 800;">${cleanText}</div>
                        </div>
                        <div class="buffer-actions">
                            <div id="qr-buf-${i}" class="buffer-qr"></div>
                            <div class="btn-buffer-x" onclick="window.removeBufferItem(${s.id})">❌</div>
                        </div>
                    </div>
                </div>`;
            }).join('');

            state.heldSpools.forEach((s, i) => generateSafeQR(`qr-buf-${i}`, "ID:" + s.id, 74));
        }
    }

    // 2. Render Dashboard Nav Deck (If present on Dashboard)
    if (n) {
        if (state.heldSpools.length > 1) {
            const nextSpool = state.heldSpools[1];
            const prevSpool = state.heldSpools[state.heldSpools.length - 1];
            const prevStyles = getFilamentStyle(prevSpool.color);
            const nextStyles = getFilamentStyle(nextSpool.color);

            n.style.display = 'flex';
            n.innerHTML = `
                <div class="cham-card nav-card" style="background: ${prevStyles.frame}" onclick="window.prevBuffer()">
                    <div class="cham-body nav-inner" style="background:${prevStyles.inner};">
                        <div id="qr-nav-prev" class="nav-qr"></div>
                        <div>
                            <div class="nav-label" style="color: #fff; text-shadow: 2px 2px 4px #000; font-weight: 900;">◀ PREV</div>
                            <div class="nav-name" style="color: #fff; text-shadow: 2px 2px 4px #000; font-weight: 800;">
                                ${prevSpool.display.replace(/^#\d+\s*/, '')}
                            </div>
                        </div>
                    </div>
                </div>
                <div class="cham-card nav-card" style="background: ${nextStyles.frame}" onclick="window.nextBuffer()">
                    <div class="cham-body nav-inner" style="background:${nextStyles.inner};">
                        <div style="text-align:right;">
                            <div class="nav-label" style="color: #fff; text-shadow: 2px 2px 4px #000; font-weight: 900;">NEXT ▶</div>
                            <div class="nav-name" style="color: #fff; text-shadow: 2px 2px 4px #000; font-weight: 800;">
                                ${nextSpool.display.replace(/^#\d+\s*/, '')}
                            </div>
                        </div>
                        <div id="qr-nav-next" class="nav-qr"></div>
                    </div>
                </div>
            `;
            generateSafeQR("qr-nav-prev", "CMD:PREV", 74);
            generateSafeQR("qr-nav-next", "CMD:NEXT", 74);
        } else { n.style.display = 'none'; }
    }

    // 3. Dispatch Event for Location Manager
    document.dispatchEvent(new CustomEvent('inventory:buffer-updated', { detail: { spools: state.heldSpools } }));
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
const processScan = (text) => {
    const upper = text.toUpperCase();
    if (upper === 'CMD:AUDIT') { toggleAudit(); return; }
    if (upper === 'CMD:LOCATIONS') { openLocationsModal(); return; }
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
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
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
                if (state.heldSpools.length > 0) {
                    // Scenario A: Buffer Full -> Drop item INTO the slot
                    performContextAssign(res.location, res.slot);
                    state.lastScannedLoc = null;
                } else {
                    // Scenario B: Buffer Empty -> Pick item UP from the slot
                    // [ALEX FIX] Fetch contents to interact with the specific slot
                    fetch(`/api/get_contents?id=${res.location}`)
                        .then(r => r.json())
                        .then(items => {
                            // Find the item in that slot (Loose equality for string/int safety)
                            const item = items.find(i => String(i.slot) === String(res.slot));

                            if (item) {
                                // 1. Spool Found: Pick it up!
                                if (state.heldSpools.some(s => s.id === item.id)) {
                                    showToast("Already in Buffer", "warning");
                                } else {
                                    state.heldSpools.unshift({ id: item.id, display: item.display, color: item.color });
                                    renderBuffer();
                                    showToast(`Picked up #${item.id} from Slot ${res.slot}`);
                                    // Optional: If you want to see the manager too, uncomment next line:
                                    // openManage(res.location); 
                                }
                            } else {
                                // 2. Slot Empty: Open the Location Manager so you can see/act
                                showToast(`Slot ${res.slot} is empty`);
                                openManage(res.location);
                            }
                        })
                        .catch(e => {
                            console.error(e);
                            showToast("Error looking up slot", "error");
                        });
                }
            } else if (res.type === 'location') {
                if (state.lastScannedLoc === res.id) { state.heldSpools = []; renderBuffer(); openManage(res.id); state.lastScannedLoc = null; return; }
                if (state.heldSpools.length > 0) { performContextAssign(res.id); state.lastScannedLoc = null; return; }
                const locData = state.allLocations.find(l => l.LocationID === res.id);
                if ((!locData || parseInt(locData['Max Spools']) <= 1) && res.contents && res.contents.length > 0) {
                    const spool = res.contents[0];
                    state.heldSpools.unshift({ id: spool.id, display: spool.display, color: spool.color });
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
                else { state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color }); renderBuffer(); }
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
            } else showToast(res.msg, 'error');
        })
        .catch(() => setProcessing(false));
};

const triggerUndo = () => fetch('/api/undo', { method: 'POST' }).then(() => { updateLogState(); loadBuffer(); });

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
const _origRenderBuffer = window.renderBuffer;
window.renderBuffer = () => {
    _origRenderBuffer(); // Update UI
    persistBuffer();     // Save State
};

/* --- PERSISTENCE LAYER: BUFFER (V3 Polling) --- */
const persistBuffer = () => {
    fetch('/api/state/buffer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ buffer: state.heldSpools })
    }).catch(e => console.warn("Buffer Save Failed", e));
};

const loadBuffer = () => {
    fetch('/api/state/buffer')
        .then(r => r.json())
        .then(data => {
            if (Array.isArray(data)) {
                // SMART SYNC: Compare to see if we need to update
                const currentStr = JSON.stringify(state.heldSpools);
                const serverStr = JSON.stringify(data);

                if (currentStr !== serverStr) {
                    console.log("🔄 Syncing Buffer from Server...");
                    state.heldSpools = data;
                    // Update UI
                    if (window.renderBuffer) window.renderBuffer();
                }
            }
        })
        .catch(e => console.warn("Buffer Load Failed", e));
};

// Listen for local updates
document.addEventListener('inventory:buffer-updated', persistBuffer);

// Heartbeat (Checks every 2 seconds)
setInterval(loadBuffer, 2000);

// Initial Load
document.addEventListener('DOMContentLoaded', loadBuffer);

window.addSpoolToBuffer = (id) => {
    // [ALEX FIX] Reuse the Scanner Logic! 
    // Instead of manually fetching and building the object, we just tell the 
    // scanner router that this ID was "scanned". This ensures consistent behavior 
    // and data formatting between physical scans and UI clicks.
    console.log(`📥 Simulating Scan for Spool #${id}`);
    processScan(id.toString());
};