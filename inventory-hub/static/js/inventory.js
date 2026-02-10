/* * Filament Command Center - Inventory Logic
 * Version: v154.17 (Label Data Restore)
 */

const DASHBOARD_VERSION = "v154.17 (Label Data Restore)";
console.log("🚀 Filament Command Center Dashboard Loaded: " + DASHBOARD_VERSION);

// --- GLOBAL STATE ---
let wakeLock = null;
let modals = {}; 
let state = { 
    scanBuffer: "", 
    bufferTimeout: null, 
    heldSpools: [], 
    ejectMode: false, 
    dropMode: false, 
    lastScannedLoc: null, 
    pendingConfirm: null, 
    pendingSafety: null, 
    allLocations: [], 
    logsPaused: false, 
    currentGrid: {}, 
    processing: false, 
    modalCallbacks: [], 
    activeModal: null, 
    auditActive: false, 
    lastAuditState: null 
};

// --- INITIALIZATION ---
const requestWakeLock = async () => { 
    if ('wakeLock' in navigator) { 
        try { wakeLock = await navigator.wakeLock.request('screen'); } 
        catch (err) { console.log(err); } 
    } 
};

document.addEventListener('visibilitychange', async () => { 
    if (wakeLock !== null && document.visibilityState === 'visible') await requestWakeLock(); 
});
document.addEventListener('click', requestWakeLock, { once: true });
requestWakeLock();

document.addEventListener('DOMContentLoaded', () => {
    // Focus Guard Setup
    if (!document.getElementById('focus-guard')) {
        const fg = document.createElement('div');
        fg.id = 'focus-guard';
        fg.innerHTML = `<div class="focus-msg"><div><div style="font-size:5rem;">🚫</div><div style="font-size:3rem;color:#f44;font-weight:bold;">SCANNER PAUSED</div><div class="text-white">Click anywhere to resume</div></div></div>`;
        fg.onclick = () => { document.body.focus(); fg.style.display = 'none'; };
        document.body.appendChild(fg);
    }

    const vTag = document.querySelector('.version-tag');
    if(vTag) vTag.innerText = DASHBOARD_VERSION;

    // Bootstrap Modals
    ['locMgrModal', 'locModal', 'manageModal', 'confirmModal', 'actionModal', 'safetyModal', 'queueModal', 'spoolModal'].forEach(id => {
        const el = document.getElementById(id);
        if(el) modals[id] = new bootstrap.Modal(el);
    });
    
    // --- SMART STACKER LOGIC ---
    document.addEventListener('show.bs.modal', (event) => {
        const zIndex = 1050 + (10 * document.querySelectorAll('.modal.show').length);
        event.target.style.zIndex = zIndex;
        setTimeout(() => {
            const backdrops = document.querySelectorAll('.modal-backdrop');
            if(backdrops.length > 0) {
                const lastBackdrop = backdrops[backdrops.length - 1];
                lastBackdrop.style.zIndex = zIndex - 5;
            }
        }, 10);
    });

    // --- EVENT LISTENER FOR MANAGER ---
    const manageEl = document.getElementById('manageModal');
    if (manageEl) {
        manageEl.addEventListener('shown.bs.modal', () => {
            const id = document.getElementById('manage-loc-id').value;
            renderBuffer();
            refreshManageView(id); 
            generateSafeQR('qr-modal-done', 'CMD:DONE', 42);
        });
    }

    // Generate Deck QRs
    generateSafeQR('qr-undo', 'CMD:UNDO', 42);
    generateSafeQR('qr-clear', 'CMD:CLEAR', 42);
    generateSafeQR('qr-drop', 'CMD:DROP', 42);
    generateSafeQR('qr-eject', 'CMD:EJECT', 42); 
    generateSafeQR('qr-audit', 'CMD:AUDIT', 42);
    generateSafeQR('qr-locs', 'CMD:LOCATIONS', 42);

    const modalQRs = {'qr-safety-yes': 'CMD:CONFIRM', 'qr-safety-no': 'CMD:CANCEL', 'qr-confirm-yes': 'CMD:CONFIRM', 'qr-confirm-no': 'CMD:CANCEL'};
    for(const [id, txt] of Object.entries(modalQRs)) generateSafeQR(id, txt, 120);

    const locTable = document.getElementById('location-table');
    if(locTable) {
        locTable.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-manage');
            if (btn) openManage(btn.dataset.id);
            else if (e.target.closest('.btn-edit')) openEdit(e.target.closest('.btn-edit').dataset.id);
            else if (e.target.closest('.btn-delete')) deleteLoc(e.target.closest('.btn-delete').dataset.id);
        });
    }

    const manualInput = document.getElementById("manual-spool-id");
    if(manualInput) {
        manualInput.addEventListener("keydown", (e) => { 
            if (e.key === "Enter") { e.preventDefault(); manualAddSpool(); }
        });
    }
    
    // Wire up Spool Detail "Add to Queue" button
    const btnPrintAction = document.getElementById('btn-print-action');
    if (btnPrintAction) {
        btnPrintAction.onclick = () => {
            const idText = document.getElementById('detail-id').innerText;
            if (idText) {
                const spoolObj = {
                    id: parseInt(idText),
                    filament: {
                        name: document.getElementById('detail-color-name').innerText,
                        material: document.getElementById('detail-material').innerText,
                        vendor: { name: document.getElementById('detail-vendor').innerText },
                        color_hex: document.getElementById('detail-hex').innerText
                    }
                };
                addToQueue(spoolObj);
                modals.spoolModal.hide();
            }
        };
    }

    updateLogState(); 
    fetchLocations(); 
    updateQueueUI(); 
});

// --- CORE FUNCTIONS ---

const generateSafeQR = (elementId, text, size) => {
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            const el = document.getElementById(elementId);
            if (el) {
                el.innerHTML = "";
                try { 
                    new QRCode(el, { text: text, width: size, height: size, correctLevel: QRCode.CorrectLevel.L }); 
                } catch(e) {}
            }
        });
    });
};

const getHexDark = (hex, opacity=0.3) => {
    if (!hex) return 'rgba(0,0,0,0.5)';
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
    const r = parseInt(hex.substring(0,2), 16), g = parseInt(hex.substring(2,4), 16), b = parseInt(hex.substring(4,6), 16);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`; 
};

const getFilamentStyle = (colorStr) => {
    if (!colorStr) return { frame: '#333', inner: '#1a1a1a' };
    
    let colors = [];
    if (colorStr.includes(',')) {
        colors = colorStr.split(',').map(c => c.trim().startsWith('#') ? c.trim() : '#' + c.trim());
    } else {
        const hex = colorStr.startsWith('#') ? colorStr : '#' + colorStr;
        colors = [hex, hex];
    }

    const frameGrad = `linear-gradient(135deg, ${colors.join(', ')})`;
    let innerGrad;
    
    if (colors.length > 1 && colors[0] !== colors[1]) {
        const gradColors = colors.map(c => getHexDark(c, 0.8)); 
        innerGrad = `
            linear-gradient(to bottom, rgba(0,0,0,0.95) 30%, rgba(0,0,0,0.4) 100%), 
            linear-gradient(135deg, ${gradColors.join(', ')})
        `;
    } else {
        const lastColorDark = getHexDark(colors[0], 0.3);
        innerGrad = `linear-gradient(to bottom, rgba(0,0,0,0.95) 0%, ${lastColorDark} 100%)`;
    }
    
    return { frame: frameGrad, inner: innerGrad };
};

// --- INPUT HANDLING ---
window.addEventListener('blur', () => { const g = document.getElementById('focus-guard'); if(g) g.style.display = 'flex'; });
window.addEventListener('focus', () => { const g = document.getElementById('focus-guard'); if(g) g.style.display = 'none'; });

document.addEventListener('keydown', (e) => {
    const g = document.getElementById('focus-guard');
    if ((g && g.style.display === 'flex') || state.processing || e.target.tagName === 'INPUT') return;
    
    if (e.key === 'Enter') { 
        e.preventDefault(); 
        if (state.scanBuffer.length > 0) processScan(state.scanBuffer); 
        state.scanBuffer = ""; 
    }
    else if (e.key.length === 1) { 
        state.scanBuffer += e.key; 
        clearTimeout(state.bufferTimeout); 
        state.bufferTimeout = setTimeout(() => state.scanBuffer = "", 2000); 
    }
});

// --- UI HELPERS ---
const pauseLogs = (isPaused) => {
    state.logsPaused = isPaused;
    const el = document.getElementById('log-status');
    if (isPaused) { el.innerText = "PAUSED ⏸"; el.style.color = "#fc0"; el.classList.remove('text-muted'); } 
    else { el.innerText = "Auto-Refresh ON"; el.style.color = "#0f0"; el.classList.remove('text-muted'); }
};

const setProcessing = (s) => { 
    let ov = document.getElementById('processing-overlay');
    if (!ov) { ov = document.createElement('div'); ov.id = 'processing-overlay'; ov.style.cssText = "display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:9999;"; document.body.appendChild(ov); }
    state.processing = s; ov.style.display = s ? 'block' : 'none'; 
};

const showToast = (msg, type='info') => {
    let c = document.getElementById('toast-container');
    if (!c) { c = document.createElement('div'); c.id = 'toast-container'; document.body.appendChild(c); }
    const el = document.createElement('div'); el.className = 'toast-msg'; el.innerText = msg; el.style.borderColor = type==='error'?'#f44':(type==='warning'?'#fc0':'#00d4ff');
    c.appendChild(el); setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 500); }, 2000);
};

// --- LOGIC: BUFFER MANAGEMENT ---
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

// --- LOGIC: MODES ---
const toggleDropMode = () => { state.dropMode = !state.dropMode; state.ejectMode = false; updateDeckVisuals(); };
const toggleEjectMode = () => { state.ejectMode = !state.ejectMode; state.dropMode = false; updateDeckVisuals(); };
const toggleAudit = () => { 
    state.auditActive = !state.auditActive;
    updateLogState(true); 
    const cmd = state.auditActive ? "CMD:AUDIT" : "CMD:DONE";
    fetch('/api/identify_scan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: cmd}) });
};

const updateDeckVisuals = () => {
    const dropBtn = document.getElementById('btn-deck-drop');
    const ejectBtn = document.getElementById('btn-deck-eject');
    const bufCol = document.querySelector('.col-buffer');
    
    if(dropBtn) dropBtn.classList.remove('drop-mode-active');
    if(ejectBtn) ejectBtn.classList.remove('eject-mode-active');
    if(bufCol) bufCol.classList.remove('drop-mode-active', 'eject-mode-active');

    if (state.dropMode) {
        if(dropBtn) dropBtn.classList.add('drop-mode-active');
        if(bufCol) bufCol.classList.add('drop-mode-active');
        showToast("DROP MODE: Scan to delete", "warning");
    } else if (state.ejectMode) {
        if(ejectBtn) ejectBtn.classList.add('eject-mode-active');
        if(bufCol) bufCol.classList.add('eject-mode-active');
        showToast("EJECT MODE: Scan to remove spool", "warning");
    }
};

const nextBuffer = () => { if(state.heldSpools.length > 1) { state.heldSpools.push(state.heldSpools.shift()); renderBuffer(); } };
const prevBuffer = () => { if(state.heldSpools.length > 1) { state.heldSpools.unshift(state.heldSpools.pop()); renderBuffer(); } };

// --- RENDERING: BUFFER ---
const renderBuffer = () => {
    const z = document.getElementById('buffer-zone');
    const n = document.getElementById('buffer-nav-deck'); 
    
    if (state.heldSpools.length === 0) { 
        z.innerHTML = `<div class="buffer-empty-msg">Buffer Empty</div>`; 
        if(n) {
             n.style.display = 'none';
             n.innerHTML = "";
        }
        return; 
    }
    
    z.innerHTML = state.heldSpools.map((s, i) => {
        const styles = getFilamentStyle(s.color);
        const cleanText = (s.display||"").replace(/^#\d+\s*/, '').trim();
        
        return `
        <div class="cham-card buffer-item ${i===0?'active-item':''}" style="background: ${styles.frame};">
            <div class="cham-body buffer-inner" style="background: ${styles.inner};">
                <div class="cham-text-group">
                    <div class="cham-id-badge">#${s.id}</div>
                    <div class="cham-text">${cleanText}</div>
                </div>
                <div class="buffer-actions">
                    <div id="qr-buf-${i}" class="buffer-qr"></div>
                    <div class="btn-buffer-x" onclick="removeBufferItem(${s.id})">❌</div>
                </div>
            </div>
        </div>`;
    }).join('');
    
    state.heldSpools.forEach((s, i) => generateSafeQR(`qr-buf-${i}`, "ID:"+s.id, 74)); 

    if (n) {
        if (state.heldSpools.length > 1) {
            const nextSpool = state.heldSpools[1];
            const prevSpool = state.heldSpools[state.heldSpools.length - 1];
            const prevStyles = getFilamentStyle(prevSpool.color);
            const nextStyles = getFilamentStyle(nextSpool.color);
            
            n.style.display = 'flex';
            n.innerHTML = `
                <div class="cham-card nav-card" style="background: ${prevStyles.frame}" onclick="prevBuffer()">
                    <div class="cham-body nav-inner" style="background:${prevStyles.inner};">
                        <div id="qr-nav-prev" class="nav-qr"></div>
                        <div>
                            <div class="nav-label">◀ PREV</div>
                            <div class="nav-name">${prevSpool.display.replace(/^#\d+\s*/, '')}</div>
                        </div>
                    </div>
                </div>
                <div class="cham-card nav-card" style="background: ${nextStyles.frame}" onclick="nextBuffer()">
                    <div class="cham-body nav-inner" style="background:${nextStyles.inner};">
                        <div style="text-align:right;">
                            <div class="nav-label">NEXT ▶</div>
                            <div class="nav-name">${nextSpool.display.replace(/^#\d+\s*/, '')}</div>
                        </div>
                        <div id="qr-nav-next" class="nav-qr"></div>
                    </div>
                </div>
            `;
            generateSafeQR("qr-nav-prev", "CMD:PREV", 74);
            generateSafeQR("qr-nav-next", "CMD:NEXT", 74);
        } else {
            n.style.display = 'none';
        }
    }
};

// --- LOGIC: SCAN PROCESSING ---
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

    if (upper.startsWith('CMD:PRINT:')) { const parts = upper.split(':'); if(parts[2]) printLabel(parts[2]); return; }
    
    if (state.activeModal === 'safety') return upper.includes('CONFIRM') ? confirmSafety(true) : (upper.includes('CANCEL') ? confirmSafety(false) : null);
    if (state.activeModal === 'confirm') return upper.includes('CONFIRM') ? confirmAction(true) : (upper.includes('CANCEL') ? confirmAction(false) : null);
    if (state.activeModal === 'action') { if(upper.includes('CANCEL')) { closeModal('actionModal'); return; } if(upper.startsWith('CMD:MODAL:')) { closeModal('actionModal'); state.modalCallbacks[parseInt(upper.split(':')[2])](); return; } }
    
    if (upper.startsWith('CMD:TRASH:')) { const parts = upper.split(':'); if(parts[2] && document.getElementById('manageModal').classList.contains('show')) ejectSpool(parts[2], document.getElementById('manage-loc-id').value, false); return; }

    setProcessing(true);
    fetch('/api/identify_scan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text}) })
    .then(r=>r.json())
    .then(res => {
        setProcessing(false);
        if (res.type === 'command') {
            const cmds = { 'clear': requestClearBuffer, 'undo': triggerUndo, 'eject': toggleEjectMode, 'done': closeManage };
            if (cmds[res.cmd]) cmds[res.cmd](); 
            else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true); 
            else if (res.cmd === 'slot') handleSlotInteraction(res.value); 
            else if (res.cmd === 'ejectall') triggerEjectAll(document.getElementById('manage-loc-id').value);
        } else if (res.type === 'location') {
            if (state.lastScannedLoc === res.id) { state.heldSpools = []; renderBuffer(); openManage(res.id); state.lastScannedLoc = null; return; }
            if (state.heldSpools.length > 0) { performContextAssign(res.id); state.lastScannedLoc = null; return; }
            const locData = state.allLocations.find(l => l.LocationID === res.id);
            if ((!locData || parseInt(locData['Max Spools']) <= 1) && res.contents && res.contents.length > 0) { 
                const spool = res.contents[0]; 
                state.heldSpools.unshift({id: spool.id, display: spool.display, color: spool.color}); 
                renderBuffer(); 
                showToast("⚡ Quick Pick: #" + spool.id); 
                state.lastScannedLoc = res.id; 
                return; 
            }
            openManage(res.id); state.lastScannedLoc = res.id;
        } else if (res.type === 'spool') {
            if (state.dropMode) { removeBufferItem(res.id); return; }
            if (state.ejectMode) { ejectSpool(res.id, "Scan", false); toggleEjectMode(); return; } 
            
            state.lastScannedLoc = null; 
            if (!res.display) { showToast("Spool ID found but data missing!", "error"); return; }

            if (state.heldSpools.some(s=>s.id===res.id)) showToast("Already in Buffer", "warning");
            else { state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); renderBuffer(); }
        } else if (res.type === 'error') showToast(res.msg, 'error');
    })
    .catch((e)=>{ setProcessing(false); console.error(e); showToast("Scan Error", "error"); });
};

const performContextAssign = (tid) => {
    setProcessing(true); 
    fetch('/api/smart_move', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({location:tid, spools:[state.heldSpools[0].id]}) })
    .then(r=>r.json())
    .then(res=>{ 
        setProcessing(false); 
        if(res.status==='success') { 
            showToast("Assigned!", "success"); 
            state.heldSpools.shift(); 
            renderBuffer(); 
            if(document.getElementById('manage-loc-id').value===tid) refreshManageView(tid); 
        } else showToast(res.msg, 'error'); 
    })
    .catch(()=>setProcessing(false));
};

// --- LOGIC: MODALS & MANAGE ---
const closeModal = (id) => { modals[id].hide(); state.activeModal = null; };
const requestConfirmation = (msg, cb) => { document.getElementById('confirm-msg').innerText=msg; state.pendingConfirm=cb; modals.confirmModal.show(); state.activeModal = 'confirm'; };
const confirmAction = (y) => { closeModal('confirmModal'); if(y && state.pendingConfirm) state.pendingConfirm(); state.pendingConfirm=null; };
const promptSafety = (msg, cb) => { document.getElementById('safety-msg').innerText=msg; state.pendingSafety=cb; modals.safetyModal.show(); state.activeModal = 'safety'; };
const confirmSafety = (y) => { closeModal('safetyModal'); if(y && state.pendingSafety) state.pendingSafety(); state.pendingSafety=null; };

const openLocationsModal = () => { modals.locMgrModal.show(); fetchLocations(); };

const openManage = (id) => { 
    // REMOVED: The hide() call for locMgrModal. It stays open in the background now.
    document.getElementById('manageTitle').innerText=`Location Manager: ${id}`; 
    document.getElementById('manage-loc-id').value=id; 
    document.getElementById('manual-spool-id').value=""; 
    modals.manageModal.show(); 
    refreshManageView(id);
};

const closeManage = () => { modals.manageModal.hide(); fetchLocations(); };

const fetchLocations = () => { 
    fetch('/api/locations')
    .then(r=>r.json())
    .then(d => { 
        state.allLocations=d; 
        document.getElementById('loc-count').innerText = "Total Locations: " + d.length; 
        document.getElementById('location-table').innerHTML = d.map(l => `
            <tr>
                <td class="col-id">${l.LocationID}</td>
                <td class="col-name">${l.Name}</td>
                <td class="col-status">${l.Occupancy||''} <span class="badge bg-secondary">${l.Type}</span></td>
                <td class="col-actions">
                    <button class="btn btn-sm btn-outline-warning me-1 btn-edit" data-id="${l.LocationID}">✏️</button>
                    <button class="btn btn-sm btn-outline-danger me-1 btn-delete" data-id="${l.LocationID}">🗑️</button>
                    <button class="btn btn-sm btn-info btn-manage" data-id="${l.LocationID}">Manage</button>
                </td>
            </tr>`).join(''); 
    }); 
};

const refreshManageView = (id) => {
    const loc = state.allLocations.find(l=>l.LocationID==id); 
    if(!loc) return false;
    
    const isGrid = (loc.Type==='Dryer Box' || loc.Type==='MMU Slot') && parseInt(loc['Max Spools']) > 1;
    document.getElementById('manage-grid-view').style.display = isGrid ? 'block' : 'none';
    document.getElementById('manage-list-view').style.display = isGrid ? 'none' : 'block';
    
    fetch(`/api/get_contents?id=${id}`)
    .then(r=>r.json())
    .then(d => { 
        if(isGrid) renderGrid(d, parseInt(loc['Max Spools'])); 
        else renderList(d, id); 
        
        // Also update buffer nav deck since we are in manage mode
        renderBuffer();
    });
    return true;
};

// --- RENDERING: GRID & LIST ---
const renderGrid = (data, max) => {
    const grid=document.getElementById('slot-grid-container'), un=document.getElementById('unslotted-container');
    grid.innerHTML=""; un.innerHTML=""; state.currentGrid={};
    const unslotted=[];
    data.forEach(i => { if(i.slot && parseInt(i.slot)>0) state.currentGrid[i.slot]=i; else unslotted.push(i); });
    
    for(let i=1; i<=max; i++) {
        const item = state.currentGrid[i], div = document.createElement('div');
        
        if (item) {
            const styles = getFilamentStyle(item.color);
            div.className = "cham-card slot-btn full";
            div.style.background = styles.frame;
            div.innerHTML = `
                <div class="cham-body slot-inner" style="background:${styles.inner};">
                    <div class="slot-num">Slot ${i}</div>
                    <div id="qr-slot-${i}" class="bg-white p-1 rounded mb-2"></div>
                    <div class="slot-content cham-text" style="font-size:1.1rem; cursor:pointer;" onclick="event.stopPropagation(); openSpoolDetails(${item.id})">${item.display}</div>
                    <button class="btn btn-sm btn-light border-dark mt-2 fw-bold" onclick="event.stopPropagation(); printLabel(${item.id})">🖨️ LABEL</button>
                </div>`;
        } else {
            div.className = "slot-btn empty";
            div.innerHTML = `
                <div class="slot-num">Slot ${i}</div>
                <div id="qr-slot-${i}" class="bg-white p-1 rounded"></div>
                <div class="text-muted fs-4 mt-2">EMPTY</div>`;
        }
        div.onclick = () => handleSlotInteraction(i); 
        grid.appendChild(div);
        generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:"+i, 60);
    }
    if(unslotted.length>0) renderUnslotted(unslotted); 
    else un.style.display='none';
};

const renderList = (data, locId) => {
    const list = document.getElementById('manage-contents-list');
    const emptyMsg = document.getElementById('manage-empty-msg');
    
    // LOGIC: Toggle visibility based on data length
    if (data.length === 0) {
        list.innerHTML = "";
        if(emptyMsg) emptyMsg.style.display = 'flex'; 
    } else {
        if(emptyMsg) emptyMsg.style.display = 'none'; 
        list.innerHTML = data.map((s,i) => renderBadgeHTML(s, i, locId)).join('');
        data.forEach((s,i) => renderBadgeQRs(s, i));
        
        // FIX: Ensure Eject All QR is generated for List View
        generateSafeQR('qr-eject-all-list', 'CMD:EJECTALL', 56);
    }
};

const renderUnslotted = (items) => {
    const un = document.getElementById('unslotted-container');
    if (!un) return;
    un.style.display='block';
    
    let html = `<h4 class="text-info border-bottom border-secondary pb-2 mb-3">Unslotted Items</h4>`;
    html += items.map((s,i) => renderBadgeHTML(s, i, document.getElementById('manage-loc-id').value)).join('');
    
    html += `
        <div class="danger-zone">
            <h4 class="text-danger fw-bold mb-3">DANGER ZONE</h4>
            <div class="action-badge" style="border-color:#dc3545; display:inline-flex;" onclick="triggerEjectAll('${document.getElementById('manage-loc-id').value}')">
                <div id="qr-eject-all" class="badge-qr"></div>
                <button class="badge-btn btn-trash">EJECT ALL</button>
            </div>
        </div>`;
        
    un.innerHTML = html;
    items.forEach((s,i) => renderBadgeQRs(s, i));
    generateSafeQR("qr-eject-all", "CMD:EJECTALL", 56);
};

const renderBadgeHTML = (s, i, locId) => {
    const styles = getFilamentStyle(s.color);
    
    return `
    <div class="cham-card manage-list-item" style="background:${styles.frame}">
        <div class="cham-body" style="background: ${styles.inner}">
            <div class="cham-text-group" style="cursor:pointer;" onclick="openSpoolDetails(${s.id})">
                <div class="cham-id-badge">#${s.id}</div>
                <div class="cham-text">${s.display}</div>
            </div>
            <div class="cham-actions">
                <div class="action-badge" onclick="ejectSpool(${s.id}, '${locId}', true)">
                    <div id="qr-pick-${i}" class="badge-qr"></div>
                    <button class="badge-btn btn-pick">PICK</button>
                </div>
                <div class="action-badge" onclick="event.stopPropagation(); quickQueue(${s.id})">
                    <div id="qr-print-${i}" class="badge-qr"></div>
                    <button class="badge-btn btn-print">QUEUE</button>
                </div>
                <div class="action-badge" onclick="ejectSpool(${s.id}, '${locId}', false)">
                    <div id="qr-trash-${i}" class="badge-qr"></div>
                    <button class="badge-btn btn-trash">TRASH</button>
                </div>
            </div>
        </div>
    </div>`;
};

const renderBadgeQRs = (s, i) => {
    generateSafeQR(`qr-pick-${i}`, "ID:"+s.id, 56);
    generateSafeQR(`qr-print-${i}`, "CMD:PRINT:"+s.id, 56);
    generateSafeQR(`qr-trash-${i}`, "CMD:TRASH:"+s.id, 56);
};

// --- ROBUST OPEN SPOOL DETAILS FUNCTION ---
const openSpoolDetails = (id) => {
    setProcessing(true);
    fetch(`/api/spool_details?id=${id}`)
    .then(r => {
        if (!r.ok) throw new Error(`Server Error: ${r.status}`);
        return r.json();
    })
    .then(d => {
        setProcessing(false);
        if (!d || !d.id) { 
            showToast("Details Data Missing!", "error"); 
            return; 
        }
        
        document.getElementById('detail-id').innerText = d.id;
        document.getElementById('detail-material').innerText = d.filament?.material || "Unknown";
        document.getElementById('detail-vendor').innerText = d.filament?.vendor?.name || "Unknown";
        document.getElementById('detail-weight').innerText = (d.filament?.weight || 0) + "g";
        
        const used = d.used_weight !== null ? d.used_weight : 0;
        const rem = d.remaining_weight !== null ? d.remaining_weight : 0;
        document.getElementById('detail-used').innerText = Number(used).toFixed(1) + "g";
        document.getElementById('detail-remaining').innerText = Number(rem).toFixed(1) + "g";
        
        document.getElementById('detail-color-name').innerText = d.filament?.name || "Unknown";
        document.getElementById('detail-hex').innerText = (d.filament?.color_hex || "").toUpperCase();
        document.getElementById('detail-comment').value = d.comment || "";
        
        const swatch = document.getElementById('detail-swatch');
        if(swatch) swatch.style.backgroundColor = "#" + (d.filament?.color_hex || "333");
        
        // --- LINK FIX: NO HASH ---
        // Dynamically update the href of the "Open Spoolman" button
        // FIX: Removed the /#/ to match user's working example /spool/show/
        const btnLink = document.getElementById('btn-open-spoolman');
        if (btnLink) {
            if (typeof SPOOLMAN_URL !== 'undefined' && SPOOLMAN_URL) {
                // Ensure no double slashes if user config has trailing slash
                const baseUrl = SPOOLMAN_URL.endsWith('/') ? SPOOLMAN_URL.slice(0, -1) : SPOOLMAN_URL;
                btnLink.href = `${baseUrl}/spool/show/${d.id}`;
            } else {
                console.warn("SPOOLMAN_URL is undefined. Using relative path.");
                btnLink.href = `/spool/show/${d.id}`;
            }
        }
        
        if(modals.spoolModal) modals.spoolModal.show();
        else {
            const el = document.getElementById('spoolModal');
            if(el) { modals.spoolModal = new bootstrap.Modal(el); modals.spoolModal.show(); }
            else showToast("Modal HTML Missing!", "error");
        }
    })
    .catch(e => { 
        setProcessing(false); 
        console.error(e);
        showToast("Connection/Data Error", "error");
    });
};

const quickQueue = (id) => {
    fetch(`/api/spool_details?id=${id}`)
    .then(r=>r.json())
    .then(d => {
        if(!d.id) return;
        addToQueue({
            id: d.id,
            filament: {
                name: d.filament?.name,
                material: d.filament?.material,
                vendor: { name: d.filament?.vendor?.name },
                color_hex: d.filament?.color_hex
            }
        });
    });
};

// --- LOGIC: ACTIONS ---
const handleSlotInteraction = (slot) => {
    if(!document.getElementById('manageModal').classList.contains('show')) return;
    const locId = document.getElementById('manage-loc-id').value, item = state.currentGrid[slot];
    if (state.heldSpools.length > 0) {
        const newId = state.heldSpools[0].id;
        if(item) promptAction("Slot Occupied", `Swap/Overwrite Slot ${slot}?`, [
            {label:"Swap", action:()=>{state.heldSpools.shift(); state.heldSpools.push({id:item.id, display:item.display, color:item.color}); renderBuffer(); doAssign(locId, newId, slot);}}, 
            {label:"Overwrite", action:()=>{state.heldSpools.shift(); renderBuffer(); doAssign(locId, newId, slot);}}
        ]);
        else { state.heldSpools.shift(); renderBuffer(); doAssign(locId, newId, slot); }
    } else if(item) promptAction("Slot Action", `Manage ${item.display}`, [
        {label:"✋ Pick Up", action:()=>{state.heldSpools.unshift({id:item.id, display:item.display, color:item.color}); renderBuffer(); doEject(item.id, locId, false);}}, 
        {label:"🗑️ Eject", action:()=>{doEject(item.id, locId, false);}}, 
        {label:"🖨️ Details", action:()=>{openSpoolDetails(item.id);}}
    ]);
};

const promptAction = (t, m, btns) => {
    document.getElementById('action-title').innerText=t; 
    document.getElementById('action-msg').innerHTML=m; 
    state.modalCallbacks=[];
    document.getElementById('action-buttons').innerHTML = btns.map((b,i) => { 
        state.modalCallbacks.push(b.action); 
        return `<div class="modal-action-card" onclick="closeModal('actionModal');state.modalCallbacks[${i}]()"><div id="qr-act-${i}" class="bg-white p-1 rounded mb-2"></div><button class="btn btn-primary modal-action-btn">${b.label}</button></div>`; 
    }).join('');
    btns.forEach((_,i) => generateSafeQR(`qr-act-${i}`, `CMD:MODAL:${i}`, 100));
    modals.actionModal.show(); state.activeModal = 'action';
};

const doAssign = (loc, spool, slot) => { 
    setProcessing(true); 
    fetch('/api/manage_contents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'add', location:loc, spool_id:"ID:"+spool, slot})})
    .then(r=>r.json())
    .then(res=>{
        setProcessing(false); 
        if(res.status==='success') { showToast("Assigned"); refreshManageView(loc); } 
        else showToast(res.msg, 'error');
    })
    .catch(()=>setProcessing(false)); 
};

const ejectSpool = (sid, loc, pickup) => { 
    if(pickup) { 
        fetch('/api/identify_scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text:"ID:"+sid})})
        .then(r=>r.json())
        .then(res=>{ 
            if(res.type==='spool'){ 
                if(state.heldSpools.some(s=>s.id===res.id)) showToast("In Buffer"); 
                else { state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); renderBuffer(); } 
            } 
            doEject(sid, loc); 
        }); 
    } else { 
        if(loc!=="Scan") requestConfirmation(`Eject spool #${sid}?`, ()=>doEject(sid, loc)); 
        else doEject(sid, loc); 
    } 
};

const doEject = (sid, loc) => { 
    setProcessing(true); 
    fetch('/api/manage_contents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'remove', location:loc, spool_id:sid})})
    .then(r=>r.json())
    .then(()=>{ setProcessing(false); showToast("Ejected"); if(loc!=="Scan") refreshManageView(loc); })
    .catch(()=>setProcessing(false)); 
};

const manualAddSpool = () => {
    const val = document.getElementById('manual-spool-id').value.trim(); 
    if (!val) return; 
    setProcessing(true);
    fetch('/api/identify_scan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: val}) })
    .then(r => r.json())
    .then(res => {
        setProcessing(false); 
        document.getElementById('manual-spool-id').value = ""; 
        document.getElementById('manual-spool-id').focus();
        if (res.type === 'spool') { 
            if (state.heldSpools.some(s=>s.id===res.id)) showToast("Already in Buffer", "warning"); 
            else { state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); renderBuffer(); showToast("Added to Buffer"); }
        } else showToast(res.msg || "Invalid Code", 'warning');
    })
    .catch(() => setProcessing(false));
};

const triggerEjectAll = (loc) => promptSafety(`Nuke all unslotted in ${loc}?`, () => { 
    setProcessing(true); 
    fetch('/api/manage_contents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'clear_location', location:loc})})
    .then(r=>r.json())
    .then(()=>{setProcessing(false); refreshManageView(loc); showToast("Cleared!");}); 
});

const openEdit = (id) => { 
    const i=state.allLocations.find(l=>l.LocationID==id); 
    if(i){ 
        modals.locMgrModal.hide(); 
        document.getElementById('edit-original-id').value=id; 
        document.getElementById('edit-id').value=id; 
        document.getElementById('edit-name').value=i.Name; 
        document.getElementById('edit-type').value=i.Type; 
        document.getElementById('edit-max').value=i['Max Spools']; 
        modals.locModal.show(); 
    }
};

const closeEdit = () => { modals.locModal.hide(); modals.locMgrModal.show(); };

const saveLocation = () => { 
    fetch('/api/locations', {
        method:'POST', 
        headers:{'Content-Type':'application/json'}, 
        body:JSON.stringify({
            old_id:document.getElementById('edit-original-id').value, 
            new_data:{
                LocationID:document.getElementById('edit-id').value, 
                Name:document.getElementById('edit-name').value, 
                Type:document.getElementById('edit-type').value, 
                "Max Spools":document.getElementById('edit-max').value
            }
        })
    })
    .then(()=>{modals.locModal.hide(); modals.locMgrModal.show(); fetchLocations();}); 
};

const openAddModal = () => { 
    modals.locMgrModal.hide(); 
    document.getElementById('edit-original-id').value=""; 
    document.getElementById('edit-id').value=""; 
    document.getElementById('edit-name').value=""; 
    document.getElementById('edit-max').value="1"; 
    modals.locModal.show(); 
};

const deleteLoc = (id) => requestConfirmation(`Delete ${id}?`, () => fetch(`/api/locations?id=${id}`, {method:'DELETE'}).then(fetchLocations));

const triggerUndo = () => fetch('/api/undo', {method:'POST'}).then(updateLogState);

const hexToRgb = (hex) => { 
    if (!hex) return {r:'', g:'', b:''}; 
    hex = hex.replace('#', ''); 
    const i = parseInt(hex, 16); 
    return { r: (i >> 16) & 255, g: (i >> 8) & 255, b: i & 255 }; 
};

const printLabel = (sid) => {
    // This is the direct print command. 
    // If you want "Print Label" to go to Queue, call addToQueue instead.
    // For now, leaving as direct print per old logic.
    showToast("🖨️ Requesting Label..."); 
    setProcessing(true);

    fetch('/api/print_label', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: sid})
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
            } catch (err) {}
            const qrEl = document.getElementById('print-qr'); 
            if (qrEl) { 
                qrEl.innerHTML = ""; 
                new QRCode(qrEl, {text: `ID:${sid}`, width: 120, height: 120, correctLevel: QRCode.CorrectLevel.L}); 
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

const updateLogState = (force=false) => {
    if(!state.logsPaused || force) fetch('/api/logs').then(r=>r.json()).then(d=>{ 
        document.getElementById('live-logs').innerHTML = d.logs.map(l=>`<div class="log-${l.type}">[${l.time}] ${l.msg}</div>`).join(''); 
        const sSpool = document.getElementById('st-spoolman');
        const sFila = document.getElementById('st-filabridge');
        if(sSpool) sSpool.className = `status-dot ${d.status.spoolman?'status-on':'status-off'}`;
        if(sFila) sFila.className = `status-dot ${d.status.filabridge?'status-on':'status-off'}`;
        if (d.audit_active !== state.lastAuditState) {
            state.lastAuditState = d.audit_active;
            state.auditActive = d.audit_active; 
            const deckBtn = document.getElementById('btn-deck-audit');
            const lbl = document.getElementById('lbl-audit');
            const qrDiv = document.getElementById('qr-audit');
            if (state.auditActive) {
                if(deckBtn) deckBtn.classList.add('btn-audit-active'); 
                if(lbl) { lbl.innerText = "FINISH"; lbl.classList.add('label-active-audit'); }
                if(qrDiv) { qrDiv.innerHTML=""; generateSafeQR('qr-audit', "CMD:DONE", 42); }
            } else {
                if(deckBtn) deckBtn.classList.remove('btn-audit-active');
                if(lbl) { lbl.innerText = "AUDIT"; lbl.classList.remove('label-active-audit'); }
                if(qrDiv) { qrDiv.innerHTML=""; generateSafeQR('qr-audit', "CMD:AUDIT", 42); }
            }
        }
    });
};

/* --- PRINT QUEUE SYSTEM --- */
let labelQueue = [];

function updateQueueUI() {
    const btn = document.getElementById('btn-queue-count');
    if (btn) btn.innerText = `🛒 Queue (${labelQueue.length})`;
}

function addToQueue(spool) {
    if (labelQueue.find(s => s.id === spool.id)) {
        showToast("⚠️ Already in Queue", "warning");
        return;
    }
    labelQueue.push(spool);
    updateQueueUI();
    showToast(`Added to Print Queue (${labelQueue.length})`);
}

function openQueueModal() {
    const list = document.getElementById('queue-list-items');
    if (!list) return;
    list.innerHTML = "";
    if (labelQueue.length === 0) {
        list.innerHTML = "<li class='list-group-item'>Queue is empty</li>";
    } else {
        labelQueue.forEach((s, index) => {
            const name = s.filament ? s.filament.name : "Unknown";
            list.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <span>#${s.id} - ${name}</span>
                    <button class="btn btn-sm btn-outline-danger" onclick="removeFromQueue(${index})">❌</button>
                </li>`;
        });
    }
    
    // FIX: Use the existing modal instance instead of creating a new one
    if (modals.queueModal) {
        modals.queueModal.show();
    } else {
        // Self-heal if missing
        const el = document.getElementById('queueModal');
        if (el) {
            modals.queueModal = new bootstrap.Modal(el);
            modals.queueModal.show();
        } else {
            showToast("CRITICAL: Queue Modal Not Found", "error");
        }
    }
}

function removeFromQueue(index) {
    labelQueue.splice(index, 1);
    openQueueModal(); 
    updateQueueUI();
}

function clearQueue() {
    labelQueue = [];
    openQueueModal();
    updateQueueUI();
}

function printQueueBrowser() {
    const container = document.getElementById('printable-queue-container');
    if (!container) return;
    container.innerHTML = ""; 
    if (labelQueue.length === 0) return;
    
    labelQueue.forEach(spool => {
        const fil = spool.filament;
        const vid = spool.id;
        const hex = fil.color_hex || "000000";
        const rgb = hexToRgb(hex); // Uses the helper already in your file
        
        const wrap = document.createElement('div');
        wrap.className = 'print-job-item';
        const qrId = `qr-print-${vid}`;
        
        wrap.innerHTML = `
            <div class="label-box">
                <div class="label-qr" id="${qrId}"></div>
                <div class="label-data">
                    <div class="lbl-row"><div class="lbl-key">BRND</div><div class="lbl-val">${fil.vendor ? fil.vendor.name : 'Generic'}</div></div>
                    <div class="lbl-row"><div class="lbl-key">COLR</div><div class="lbl-val">${fil.name}</div></div>
                    <div class="lbl-row"><div class="lbl-key">MATL</div><div class="lbl-val">${fil.material}</div></div>
                    <div class="lbl-row"><div class="lbl-key">ID#</div><div class="lbl-val lbl-id">${vid}</div></div>
                    <div class="lbl-row"><div class="lbl-key">RGB</div><div class="lbl-val lbl-rgb">${rgb.r},${rgb.g},${rgb.b}</div></div>
                </div>
            </div>`;
            
        container.appendChild(wrap);
        // Generate high-resolution QR for the printer
        new QRCode(document.getElementById(qrId), {
            text: `ID:${vid}`, 
            width: 120, 
            height: 120, 
            correctLevel: QRCode.CorrectLevel.H 
        });
    });
    
    // Slight delay to allow QR codes to render before the print dialog pops up
    setTimeout(() => window.print(), 1000);
}

function printQueueCSV() {
    if (labelQueue.length === 0) return;
    const ids = labelQueue.map(s => s.id);
    fetch('/api/print_batch_csv', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ids: ids })
    })
    .then(r => r.json())
    .then(res => {
        if(res.success) {
            showToast("✅ Sent " + res.count + " labels to CSV!");
            clearQueue();
            if (modals.queueModal) modals.queueModal.hide();
        } else {
            showToast("Error: " + res.msg, "error");
        }
    });
}

setInterval(updateLogState, 2500);