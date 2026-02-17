/* MODULE: CORE (State & Helpers) */
console.log("🚀 Loaded Module: CORE");

// --- GLOBAL STATE ---
let wakeLock = null;
let modals = {}; 
let state = { 
    // Core
    scanBuffer: "", 
    bufferTimeout: null, 
    processing: false, 
    logsPaused: false,
    allLocations: [], 
    
    // Command Center / Buffer
    heldSpools: [], 
    ejectMode: false, 
    dropMode: false, 
    lastScannedLoc: null, 
    auditActive: false, 
    lastAuditState: null,
    
    // Manager
    currentGrid: {}, 
    
    // Modals
    modalCallbacks: [], 
    activeModal: null, 
    pendingConfirm: null, 
    pendingSafety: null
};

// --- INITIALIZATION HELPERS ---
const requestWakeLock = async () => { 
    if ('wakeLock' in navigator) { 
        try { wakeLock = await navigator.wakeLock.request('screen'); } 
        catch (err) { console.log(err); } 
    } 
};

// --- UI HELPERS ---
const showToast = (msg, type='info') => {
    let c = document.getElementById('toast-container');
    if (!c) { c = document.createElement('div'); c.id = 'toast-container'; document.body.appendChild(c); }
    const el = document.createElement('div'); el.className = 'toast-msg'; el.innerText = msg; el.style.borderColor = type==='error'?'#f44':(type==='warning'?'#fc0':'#00d4ff');
    c.appendChild(el); setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 500); }, 2000);
};

const setProcessing = (s) => { 
    let ov = document.getElementById('processing-overlay');
    if (!ov) { ov = document.createElement('div'); ov.id = 'processing-overlay'; ov.style.cssText = "display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:9999;"; document.body.appendChild(ov); }
    state.processing = s; ov.style.display = s ? 'block' : 'none'; 
};

const pauseLogs = (isPaused) => {
    state.logsPaused = isPaused;
    const el = document.getElementById('log-status');
    if (el) {
        if (isPaused) { el.innerText = "PAUSED ⏸"; el.style.color = "#fc0"; el.classList.remove('text-muted'); } 
        else { el.innerText = "Auto-Refresh ON"; el.style.color = "#0f0"; el.classList.remove('text-muted'); }
    }
};

// --- GRAPHICS HELPERS ---
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


/* [Search Anchor] */
const getFilamentStyle = (colorStr) => {
    // [ALEX FIX] Robust Color Parsing (Shared by Buffer & Modals)
    if (!colorStr) colorStr = "333";
    
    // 1. Scrub the input (remove quotes, extra spaces)
    let cleanStr = colorStr.toString().replace(/['"]/g, '').trim();
    if (!cleanStr) cleanStr = "333";

    let colors = [];
    
    // 2. Handle Lists (JSON or CSV)
    if (cleanStr.startsWith('[')) {
        try { colors = JSON.parse(cleanStr); } 
        catch(e) { colors = [cleanStr]; }
    } else {
        colors = cleanStr.split(',').map(c => c.trim());
    }

    // 3. Normalize Hex Codes
    colors = colors.map(c => {
        // If it's already a valid hex format like #FFF or #112233, keep it
        // Otherwise, strip non-hex chars and add hash
        if(c.startsWith('#') && (c.length === 4 || c.length === 7)) return c;
        let hex = c.replace(/[^a-fA-F0-9]/g, '');
        return hex ? '#' + hex : '#333';
    });
    
    // 4. Force at least 2 colors for a gradient
    if (colors.length === 1) colors.push(colors[0]);

    // 5. Generate Gradients
    const frameGrad = `linear-gradient(135deg, ${colors.join(', ')})`;
    
    let innerGrad;
    if (colors.length > 1 && colors[0] !== colors[1]) {
        // Multi-color inner: transparent dark overlay + colors
        const gradColors = colors.map(c => getHexDark(c, 0.8)); 
        innerGrad = `linear-gradient(to bottom, rgba(0,0,0,0.95) 30%, rgba(0,0,0,0.4) 100%), linear-gradient(135deg, ${gradColors.join(', ')})`;
    } else {
        // Single-color inner: simple fade to black
        const lastColorDark = getHexDark(colors[0], 0.3);
        innerGrad = `linear-gradient(to bottom, rgba(0,0,0,0.95) 0%, ${lastColorDark} 100%)`;
    }
    return { frame: frameGrad, inner: innerGrad };
};

const hexToRgb = (hex) => { 
    if (!hex) return {r:'', g:'', b:''}; 
    hex = hex.replace('#', ''); 
    const i = parseInt(hex, 16); 
    return { r: (i >> 16) & 255, g: (i >> 8) & 255, b: i & 255 }; 
};

// --- DATA FETCHERS ---
const fetchLocations = () => { 
    fetch('/api/locations')
    .then(r=>r.json())
    .then(d => { 
        state.allLocations=d; 
        const countEl = document.getElementById('loc-count');
        if(countEl) countEl.innerText = "Total Locations: " + d.length; 
        
        const table = document.getElementById('location-table');
        if(table) {
            table.innerHTML = d.map(l => `
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
        }
    }); 
};

const updateLogState = (force=false) => {
    if(!state.logsPaused || force) fetch('/api/logs').then(r=>r.json()).then(d=>{ 
        const logsEl = document.getElementById('live-logs');
        if(logsEl) logsEl.innerHTML = d.logs.map(l=>`<div class="log-${l.type}">[${l.time}] ${l.msg}</div>`).join(''); 
        
        const sSpool = document.getElementById('st-spoolman');
        const sFila = document.getElementById('st-filabridge');
        if(sSpool) sSpool.className = `status-dot ${d.status.spoolman?'status-on':'status-off'}`;
        if(sFila) sFila.className = `status-dot ${d.status.filabridge?'status-on':'status-off'}`;
        
        if (d.audit_active !== state.lastAuditState) {
            state.lastAuditState = d.audit_active;
            state.auditActive = d.audit_active; 
            // Audit Visuals are handled in Command Center Module
            if(window.updateAuditVisuals) window.updateAuditVisuals();
        }
    });
};

// --- MODAL HELPERS ---
const closeModal = (id) => { if(modals[id]) modals[id].hide(); state.activeModal = null; };
const requestConfirmation = (msg, cb) => { document.getElementById('confirm-msg').innerText=msg; state.pendingConfirm=cb; modals.confirmModal.show(); state.activeModal = 'confirm'; };
const confirmAction = (y) => { closeModal('confirmModal'); if(y && state.pendingConfirm) state.pendingConfirm(); state.pendingConfirm=null; };
const promptSafety = (msg, cb) => { document.getElementById('safety-msg').innerText=msg; state.pendingSafety=cb; modals.safetyModal.show(); state.activeModal = 'safety'; };
const confirmSafety = (y) => { closeModal('safetyModal'); if(y && state.pendingSafety) state.pendingSafety(); state.pendingSafety=null; };
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

// --- SMART SYNC PROTOCOL (Heartbeat) ---
window.startSmartSync = () => {
    if (window._smartSyncRunning) return;
    window._smartSyncRunning = true;
    console.log("🔄 Smart Sync Protocol Initiated (5s Interval)");
    
    setInterval(() => {
        // 1. Refresh Logs & System Status (Spoolman/Filabridge connectivity)
        if (!state.logsPaused) updateLogState();

        // 2. Refresh Location List if Visible (Modal Open)
        // We check offsetParent to determine if the table is actually visible to the user
        const locTable = document.getElementById('location-table');
        if (locTable && locTable.offsetParent !== null) {
            fetchLocations();
        }

        // 3. Broadcast Pulse for other modules (like Location Manager)
        document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));

    }, 5000); // 5 Second Heartbeat
};

// Auto-start the heartbeat
document.addEventListener('DOMContentLoaded', window.startSmartSync);

// [Code Guardian] Wake Lock Persistence
document.addEventListener('visibilitychange', async () => {
    if (wakeLock !== null && document.visibilityState === 'visible') {
        await requestWakeLock();
    }
});