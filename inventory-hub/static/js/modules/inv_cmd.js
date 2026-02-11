/* MODULE: COMMAND CENTER (Dashboard & Buffer) */
console.log("🚀 Loaded Module: COMMAND CENTER");

// --- BUFFER UI ---
const renderBuffer = () => {
    const z = document.getElementById('buffer-zone');
    const n = document.getElementById('buffer-nav-deck'); 
    
    // Check if elements exist (in case we are on a page without buffer)
    if (!z) return;

    if (state.heldSpools.length === 0) { 
        z.innerHTML = `<div class="buffer-empty-msg">Buffer Empty</div>`; 
        if(n) { n.style.display = 'none'; n.innerHTML = ""; }
        return; 
    }
    
    z.innerHTML = state.heldSpools.map((s, i) => {
        const styles = getFilamentStyle(s.color);
        const cleanText = (s.display||"").replace(/^#\d+\s*/, '').trim();
        return `
        <div class="cham-card buffer-item ${i===0?'active-item':''}" style="background: ${styles.frame};">
            <div class="cham-body buffer-inner" style="background: ${styles.inner};">
                <div class="cham-text-group" onclick="openSpoolDetails(${s.id})" style="cursor:pointer">
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
        } else { n.style.display = 'none'; }
    }
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
const nextBuffer = () => { if(state.heldSpools.length > 1) { state.heldSpools.push(state.heldSpools.shift()); renderBuffer(); } };
const prevBuffer = () => { if(state.heldSpools.length > 1) { state.heldSpools.unshift(state.heldSpools.pop()); renderBuffer(); } };

// --- MODES ---
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

// Global hook for audit visuals
window.updateAuditVisuals = () => {
    const deckBtn = document.getElementById('btn-deck-audit');
    const lbl = document.getElementById('lbl-audit');
    const qrDiv = document.getElementById('qr-audit');
    if (state.auditActive) {
        if(deckBtn) deckBtn.classList.add('btn-audit-active'); 
        if(lbl) { lbl.innerText = "FINISH"; lbl.classList.add('label-active-audit'); }
        if(qrDiv) { qrDiv.innerHTML=""; generateSafeQR('qr-audit', "CMD:DONE", 85); }
    } else {
        if(deckBtn) deckBtn.classList.remove('btn-audit-active');
        if(lbl) { lbl.innerText = "AUDIT"; lbl.classList.remove('label-active-audit'); }
        if(qrDiv) { qrDiv.innerHTML=""; generateSafeQR('qr-audit', "CMD:AUDIT", 85); }
    }
};

// --- SCAN ROUTER ---
const processScan = (text) => {
    const upper = text.toUpperCase();
    
    // Command Routing
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
    if (upper.startsWith('CMD:TRASH:')) { const parts = upper.split(':'); if(parts[2] && document.getElementById('manageModal').classList.contains('show')) ejectSpool(parts[2], document.getElementById('manage-loc-id').value, false); return; }
    
    // Modal Intercepts
    if (state.activeModal === 'safety') return upper.includes('CONFIRM') ? confirmSafety(true) : (upper.includes('CANCEL') ? confirmSafety(false) : null);
    if (state.activeModal === 'confirm') return upper.includes('CONFIRM') ? confirmAction(true) : (upper.includes('CANCEL') ? confirmAction(false) : null);
    if (state.activeModal === 'action') { if(upper.includes('CANCEL')) { closeModal('actionModal'); return; } if(upper.startsWith('CMD:MODAL:')) { closeModal('actionModal'); state.modalCallbacks[parseInt(upper.split(':')[2])](); return; } }

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
            // Location Logic
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
            // Spool Logic
            if (state.dropMode) { removeBufferItem(res.id); return; }
            if (state.ejectMode) { ejectSpool(res.id, "Scan", false); return; } 
            
            state.lastScannedLoc = null;
            if (!res.display) { showToast("Spool ID found but data missing!", "error"); return; }
            if (state.heldSpools.some(s=>s.id===res.id)) showToast("Already in Buffer", "warning");
            else { state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); renderBuffer(); }
        } else if (res.type === 'filament') {
            openFilamentDetails(res.id);
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

const triggerUndo = () => fetch('/api/undo', {method:'POST'}).then(updateLogState);

const printLabel = (sid) => {
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