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
    locSortBy: 'LocationID',
    locSortDir: 1,

    // Modals
    modalCallbacks: [],
    activeModal: null,
    pendingConfirm: null,
    pendingSafety: null
};

// --- INITIALIZATION HELPERS ---
const acquireLock = async () => {
    if ('wakeLock' in navigator) {
        try {
            wakeLock = await navigator.wakeLock.request('screen');
            console.log("🔌 Native WakeLock acquired.");
        } catch (err) {
            console.log("Native WakeLock failed.", err);
        }
    }
};

let noSleepInstance = null;
const enableWakeLocks = async () => {
    await acquireLock(); // Fire native lock again now that we have a gesture!
    if (window.NoSleep && !noSleepInstance) {
        noSleepInstance = new window.NoSleep();
        noSleepInstance.enable();
        console.log("🎬 NoSleep.js armed via user interaction.");
    }
};

const requestWakeLock = async () => {
    // 1. Try to acquire immediately (works on some mobile browsers without gesture)
    await acquireLock();

    // 2. Setup NoSleep.js fallback AND Native WakeLock via explicit user interaction.
    // Modern desktop browsers (Chrome/Edge on laptops) strictly block both WakeLock and Autoplay Video (NoSleep) 
    // unless the user has physically clicked the page first.
    const firstInteract = async () => {
        await enableWakeLocks();
        // We only need to catch the *first* interaction to bypass the security wall.
        document.removeEventListener('click', firstInteract, false);
        document.removeEventListener('touchstart', firstInteract, false);
        document.removeEventListener('keydown', firstInteract, false);
    };

    document.addEventListener('click', firstInteract, false);
    document.addEventListener('touchstart', firstInteract, false);
    document.addEventListener('keydown', firstInteract, false);
};

// --- UI HELPERS ---
const showToast = (msg, type = 'info', duration = 2000) => {
    let c = document.getElementById('toast-container');
    if (!c) { c = document.createElement('div'); c.id = 'toast-container'; document.body.appendChild(c); }
    const el = document.createElement('div');
    el.className = 'toast-msg toast-' + type;
    el.innerText = msg;
    const borderByType = { error: '#f44', warning: '#fc0', success: '#0f0', info: '#00d4ff' };
    el.style.borderColor = borderByType[type] || borderByType.info;
    c.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 500); }, duration);
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
        if (isPaused) { el.innerText = "PAUSED ⏸"; el.style.color = "#fc0"; el.classList.remove('text-light'); }
        else { el.innerText = "Auto-Refresh ON"; el.style.color = "#0f0"; el.classList.remove('text-light'); }
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
                } catch (e) { }
            }
        });
    });
};

const getHexDark = (hex, opacity = 0.3) => {
    if (!hex) return 'rgba(0,0,0,0.5)';
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    const r = parseInt(hex.substring(0, 2), 16), g = parseInt(hex.substring(2, 4), 16), b = parseInt(hex.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
};


/* [Search Anchor] */
const getFilamentStyle = (colorStr, direction = 'longitudinal') => {
    // [ALEX FIX] Robust Color Parsing (Shared by Buffer & Modals)
    if (!colorStr) colorStr = "333";

    // 1. Scrub the input (remove quotes, extra spaces)
    let cleanStr = colorStr.toString().replace(/['"]/g, '').trim();
    if (!cleanStr) cleanStr = "333";

    let colors = [];

    // 2. Handle Lists (JSON or CSV)
    if (cleanStr.startsWith('[')) {
        try { colors = JSON.parse(cleanStr); }
        catch (e) { colors = [cleanStr]; }
    } else {
        colors = cleanStr.split(',').map(c => c.trim());
    }

    // 3. Normalize Hex Codes
    colors = colors.map(c => {
        // If it's already a valid hex format like #FFF or #112233, keep it
        // Otherwise, strip non-hex chars and add hash
        if (c.startsWith('#') && (c.length === 4 || c.length === 7)) return c;
        let hex = c.replace(/[^a-fA-F0-9]/g, '');
        return hex ? '#' + hex : '#333';
    });

    // Save full colors before capping for coaxial rendering
    const fullColors = [...colors];

    // No artificial limit! Let linear-gradient sweep display all assigned colors

    // 4. Force at least 2 colors for interpolation
    const isSolid = colors.length === 1 || (colors.length > 1 && colors[0] === colors[1]);
    if (colors.length === 1) colors.push(colors[0]);

    // 5. Generate Physical Frame Gradients (Buttons)
    let frameGrad;
    let innerGrad;

    if (direction === 'coaxial' && !isSolid) {
        if (fullColors.length === 1) fullColors.push(fullColors[0]);
        const sliceSize = 100.0 / fullColors.length;
        const conicStops = fullColors.map((c, i) => `${c} ${i === 0 ? "0%" : (i * sliceSize).toFixed(2) + "%"} ${((i + 1) * sliceSize).toFixed(2) + "%"}`).join(', ');
        frameGrad = `conic-gradient(${conicStops})`;
        
        const darkStops = fullColors.map((c, i) => `${getHexDark(c, 0.8)} ${i === 0 ? "0%" : (i * sliceSize).toFixed(2) + "%"} ${((i + 1) * sliceSize).toFixed(2) + "%"}`).join(', ');
        innerGrad = `linear-gradient(to bottom, rgba(0,0,0,0.95) 30%, rgba(0,0,0,0.4) 100%), conic-gradient(${darkStops})`;
    } else {
        if (isSolid) {
            let hex = colors[0].replace('#', '');
            if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
            const r = parseInt(hex.substring(0, 2), 16) || 0;
            const g = parseInt(hex.substring(2, 4), 16) || 0;
            const b = parseInt(hex.substring(4, 6), 16) || 0;
            // Smoothly fade the base color into partial transparency to create a deeply rich vibrant bottom
            frameGrad = `linear-gradient(to bottom, rgba(${r},${g},${b},1) 0%, rgba(${r},${g},${b},0.6) 100%)`;
            innerGrad = `linear-gradient(to bottom, rgba(${r},${g},${b},0.4) 0%, rgba(${r},${g},${b},0.1) 100%)`;
        } else {
            // Multi-color filaments use a diagonal stripe or sweep to showcase all components
            frameGrad = `linear-gradient(135deg, ${colors.join(', ')})`;
            const gradColors = colors.map(c => getHexDark(c, 0.8));
            innerGrad = `linear-gradient(to bottom, rgba(0,0,0,0.95) 30%, rgba(0,0,0,0.4) 100%), linear-gradient(135deg, ${gradColors.join(', ')})`;
        }
    }

    // 6. Black border fix & Texture
    let borderStyle = "";
    if (colors.length > 0) {
        let isAllDark = true;
        for (let c of colors) {
            let hex = c.replace('#', '');
            if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
            const r = parseInt(hex.substring(0, 2), 16), g = parseInt(hex.substring(2, 4), 16), b = parseInt(hex.substring(4, 6), 16);
            if (r > 55 || g > 55 || b > 55) { isAllDark = false; break; }
        }
        if (isAllDark) {
            borderStyle = true; // Boolean flag legacy passthrough
            // Explicit override for pure black colors to guarantee contrast rim (fades #555 to deep black)
            frameGrad = `linear-gradient(to bottom, #555555 0%, #1a1a1a 100%)`;
            innerGrad = `linear-gradient(to bottom, rgba(30,30,30,0.95) 0%, rgba(5,5,5,0.9) 100%)`;
        }
    }

    return { frame: frameGrad, inner: innerGrad, border: borderStyle, base: colors[0], isSolid: isSolid };
};

const hexToRgb = (hex) => {
    if (!hex) return { r: '', g: '', b: '' };
    hex = hex.replace('#', '');
    const i = parseInt(hex, 16);
    return { r: (i >> 16) & 255, g: (i >> 8) & 255, b: i & 255 };
};

// --- DATA FETCHERS ---
const fetchLocations = () => {
    fetch('/api/locations')
        .then(r => r.json())
        .then(d => {
            // [ALEX FIX] Ensure Unassigned is in the list
            let hasUnassigned = d.some(l => l.LocationID === 'Unassigned');
            if(!hasUnassigned) {
                d.unshift({
                    LocationID: 'Unassigned',
                    Name: 'Unassigned Spools',
                    Type: 'Virtual',
                    Occupancy: '--'
                });
            }

            // Apply Sort
            d.sort((a, b) => {
                // Ensure Unassigned is always solidly at the top
                if (a.LocationID === 'Unassigned') return -1;
                if (b.LocationID === 'Unassigned') return 1;

                let valA = a[state.locSortBy] || '';
                let valB = b[state.locSortBy] || '';

                if (state.locSortBy === 'Occupancy') {
                    const parseOcc = (v) => {
                        if (!v || v === '--') return -1;
                        if (typeof v === 'string') {
                            const firstPart = v.split('/')[0];
                            return parseInt(firstPart) || 0;
                        }
                        return v;
                    };
                    valA = parseOcc(valA);
                    valB = parseOcc(valB);
                } else if (state.locSortBy === 'LocationID') {
                    // Extract tree root for parent-child grouping
                    let rootA = (a.LocationID || '').split('-')[0];
                    let rootB = (b.LocationID || '').split('-')[0];
                    let typeA = '';
                    let typeB = '';
                    
                    const rootAItem = d.find(l => l.LocationID === rootA);
                    if (rootAItem) typeA = rootAItem.Type || '';
                    const rootBItem = d.find(l => l.LocationID === rootB);
                    if (rootBItem) typeB = rootBItem.Type || '';

                    let isAPrinter = typeA.includes('Printer');
                    let isBPrinter = typeB.includes('Printer');

                    if (isAPrinter !== isBPrinter) {
                        return (isAPrinter ? -1 : 1) * state.locSortDir;
                    }

                    if (typeof valA === 'string') valA = valA.toLowerCase();
                    if (typeof valB === 'string') valB = valB.toLowerCase();
                } else {
                    if (typeof valA === 'string') valA = valA.toLowerCase();
                    if (typeof valB === 'string') valB = valB.toLowerCase();
                }
                
                if (valA < valB) return -1 * state.locSortDir;
                if (valA > valB) return 1 * state.locSortDir;
                return 0;
            });

            const finalList = d;
            state.allLocations = finalList;

            // --- NO WIGGLE CHECK ---
            const contentHash = JSON.stringify(finalList) + "|" + state.locSortBy + "|" + state.locSortDir;
            if (state.lastLocationsHash === contentHash) return;
            state.lastLocationsHash = contentHash;
            // -----------------------

            // 2. Update Total Count with Pop Style
            const countEl = document.getElementById('loc-count');
            // Subtract 1 for Unassigned so it doesn't inflate the Physical box count
            if (countEl) countEl.innerText = "Total Locations: " + (finalList.length > 0 ? finalList.length - 1 : 0);

            const table = document.getElementById('location-table');
            if (table) {
                table.innerHTML = finalList.map(l => {
                    // 3. Status Pop Logic (Red/Green/White)
                    let statusHtml = '';
                    let occColor = '#fff'; // Default White (Under Capacity)

                    if (l.Occupancy && l.Occupancy !== '--') {
                        const parts = l.Occupancy.split('/');
                        if (parts.length === 2) {
                            const cur = parseInt(parts[0]);
                            const max = parseInt(parts[1]);

                            if (!isNaN(cur) && !isNaN(max)) {
                                if (cur >= max) occColor = '#ff4444';      // Red (Full or Overfilled)
                                else if (cur === 0) occColor = '#ffc107'; // Yellow (Empty)
                                else occColor = '#fff'; // White (Default)
                            }
                        }
                        // GOLD STANDARD: High Contrast Pop
                        statusHtml = `<div class="d-flex align-items-center"><span class="text-pop" style="font-weight:900; font-size:1.1rem; color:${occColor};">${l.Occupancy}</span>`;
                        if (occColor === '#ffc107') {
                            statusHtml += `<span class="text-pop" title="Empty Capacity" style="font-size:1.3rem; margin-left: 6px; line-height: 1;">⚠️</span>`;
                        }
                        statusHtml += `</div>`;
                    } else {
                        statusHtml = `<span style="color:#666; font-style:italic; font-weight:bold;">--</span>`;
                    }

                    // 4. Type Badge (Rainbow Logic + Visible Virtual)
                    let badgeClass = 'bg-secondary';
                    let badgeStyle = 'border:1px solid #555;';

                    // Color Mapping
                    const t = l.Type || '';
                    if (t.includes('Dryer')) { badgeClass = 'bg-warning text-dark'; badgeStyle = 'border:1px solid #fff;'; }
                    else if (t.includes('Storage')) { badgeClass = 'bg-primary'; badgeStyle = 'border:1px solid #88f;'; }
                    else if (t.includes('MMU')) { badgeClass = 'bg-danger'; badgeStyle = 'border:1px solid #f88;'; }
                    else if (t.includes('Shelf')) { badgeClass = 'bg-success'; badgeStyle = 'border:1px solid #8f8;'; }
                    else if (t.includes('Cart')) { badgeClass = 'bg-info text-dark'; badgeStyle = 'border:1px solid #fff;'; }
                    else if (t.includes('Printer') || t.includes('Toolhead')) { badgeClass = 'bg-dark'; badgeStyle = 'border:1px solid #f0f; background-color: #aa00ff !important; color: #fff;'; }
                    else if (t.includes('Room')) { badgeClass = 'bg-light text-dark'; badgeStyle = 'border:1px solid #fff; box-shadow: 0 0 5px rgba(255,255,255,0.5);'; }
                    // [ALEX FIX] Ghostly, Hollow Look for Virtual
                    else if (t.includes('Virtual')) { badgeClass = 'bg-transparent text-light'; badgeStyle = 'border:2px dashed #aaa; box-shadow: inset 0 0 5px rgba(255,255,255,0.2);'; }

                    const typeBadge = `<span class="badge ${badgeClass}" style="box-shadow: 1px 1px 3px rgba(0,0,0,0.5); ${badgeStyle}">${l.Type}</span>`;

                    let indent = '';
                    let parentId = l.LocationID.includes('-') ? l.LocationID.split('-')[0] : l.LocationID;
                    let isChild = false;
                    let hasChildren = false;

                    if (state.locSortBy === 'LocationID') {
                        isChild = l.LocationID.includes('-') && !['TST','TEST','PM','PJ'].includes(parentId);
                        if (isChild) {
                            indent = '<span style="display:inline-block; width: 20px; border-left: 2px solid #555; border-bottom: 2px solid #555; height: 16px; margin-right: 8px; margin-bottom: 6px; margin-left: 10px;"></span>';
                        } else {
                            hasChildren = finalList.some(c => c.LocationID !== l.LocationID && c.LocationID.startsWith(l.LocationID + '-'));
                            if (hasChildren && !['TST','TEST','PM','PJ'].includes(l.LocationID)) {
                                indent = `<span onclick="window.toggleLocNode('${l.LocationID}', this)" style="cursor:pointer; font-family: monospace; border: 1px solid #555; border-radius: 3px; padding: 0 4px; margin-right: 6px; color:#aaa; background:#222; user-select:none; font-size:1rem; box-shadow:inset 0 0 3px #000;" class="text-pop-light">-</span>`;
                            }
                        }
                    }

                    const rowClass = isChild ? `loc-child-of-${parentId}` : '';

                    return `
                <tr class="${rowClass}" id="loc-row-${l.LocationID}">
                    <td class="col-id" style="font-weight:bold; color:#00d4ff; font-size:1.1rem; white-space: nowrap;">${indent}${l.LocationID}</td>
                    <td class="col-name text-pop-light" style="font-weight:800; font-size:1.1rem; color:#fff;">${l.Name}</td>
                    <td class="col-type">${typeBadge}</td>
                    <td class="col-status">${statusHtml}</td>
                    <td class="col-actions text-end" style="white-space: nowrap;">
                        <button class="btn btn-sm btn-outline-light me-1 btn-qr" onclick="window.showGlobalQrModal('${l.LocationID}')" title="Show QR">📱 QR</button>
                        ${l.Type !== 'Virtual' ? `
                        <button class="btn btn-sm btn-outline-warning me-1 btn-edit" data-id="${l.LocationID}">✏️</button>
                        <button class="btn btn-sm btn-outline-danger me-1 btn-delete" data-id="${l.LocationID}">🗑️</button>
                        ` : ''}
                        <button class="btn btn-sm btn-info btn-manage fw-bold" data-id="${l.LocationID}">Manage</button>
                    </td>
                </tr>`;
                }).join('');
            }
        });
};
window.fetchLocations = fetchLocations;

window.sortLocations = (col) => {
    if (state.locSortBy === col) {
        state.locSortDir *= -1;
    } else {
        state.locSortBy = col;
        state.locSortDir = 1;
    }
    state.lastLocationsHash = null; // Force DOM re-render
    fetchLocations();
};

window.toggleLocNode = (parentId, btnEl) => {
    const isExpanded = btnEl.innerText === '-';
    // Use .startsWith on ID rather than explicit classes to support deeper nesting dynamically
    // Actually our loc-child-of class is perfect as it targets immediate children implicitly
    const rows = document.querySelectorAll(`.loc-child-of-${parentId}`);
    rows.forEach(r => {
        r.style.display = isExpanded ? 'none' : '';
    });
    btnEl.innerText = isExpanded ? '+' : '-';
    if(isExpanded) {
        btnEl.style.color = '#fff';
        btnEl.style.background = '#444';
    } else {
        btnEl.style.color = '#aaa';
        btnEl.style.background = '#222';
    }
};

window.showGlobalQrModal = (locId) => {
    if (!locId) return;
    const safeStr = String(locId).replace(/['"]/g, '');
    generateSafeQR('loc-qr-view-container', "LOC:" + safeStr, 200);
    const labelEl = document.getElementById('loc-qr-view-label');
    if (labelEl) labelEl.innerText = "LOC:" + safeStr;
    
    if (!modals.locQrViewModal) {
        const el = document.getElementById('locQrViewModal');
        if(el) modals.locQrViewModal = new bootstrap.Modal(el);
    }
    if (modals.locQrViewModal) modals.locQrViewModal.show();
};

const updateLogState = (force = false) => {
    if (!state.logsPaused || force) fetch('/api/logs').then(r => r.json()).then(d => {
        // --- NO WIGGLE CHECK ---
        const contentHash = JSON.stringify(d);
        if (!force && state.lastLogHash === contentHash) return;
        state.lastLogHash = contentHash;
        // -----------------------

        const logsEl = document.getElementById('live-logs');
        if (logsEl) {
            logsEl.innerHTML = d.logs.map(l => {
                let extraHtml = '';
                let extraClass = '';
                if (l.meta && l.meta.type === 'filabridge_error') {
                    const dataStr = encodeURIComponent(JSON.stringify(l.meta));
                    extraClass = ' filabridge-error-log';
                    extraHtml = `<button class="btn btn-sm btn-outline-warning ms-2 py-0 px-1" onclick="window.openFilaBridgeRecovery('${dataStr}')">💊 Fix</button>`;
                }
                return `<div class="log-${l.type}${extraClass}">[${l.time}] ${l.msg}${extraHtml}</div>`;
            }).join('');
        }

        const sSpool = document.getElementById('st-spoolman');
        const sFila = document.getElementById('st-filabridge');
        if (sSpool) sSpool.className = `status-dot ${d.status.spoolman ? 'status-on' : 'status-off'}`;
        if (sFila) sFila.className = `status-dot ${d.status.filabridge ? 'status-on' : 'status-off'}`;

        if (d.audit_active !== state.lastAuditState) {
            state.lastAuditState = d.audit_active;
            state.auditActive = d.audit_active;
            // Audit Visuals are handled in Command Center Module
            if (window.updateAuditVisuals) window.updateAuditVisuals();
        }
    });
};

// --- MODAL HELPERS ---
const closeModal = (id) => { if (modals[id]) modals[id].hide(); state.activeModal = null; };
const requestConfirmation = (msg, cb) => { document.getElementById('confirm-msg').innerText = msg; state.pendingConfirm = cb; modals.confirmModal.show(); state.activeModal = 'confirm'; };
const confirmAction = (y) => { closeModal('confirmModal'); if (y && state.pendingConfirm) state.pendingConfirm(); state.pendingConfirm = null; };
const promptSafety = (msg, cb) => { document.getElementById('safety-msg').innerText = msg; state.pendingSafety = cb; modals.safetyModal.show(); state.activeModal = 'safety'; };
const confirmSafety = (y) => { closeModal('safetyModal'); if (y && state.pendingSafety) state.pendingSafety(); state.pendingSafety = null; };
const promptAction = (t, m, btns) => {
    document.getElementById('action-title').innerText = t;
    document.getElementById('action-msg').innerHTML = m;
    state.modalCallbacks = [];
    document.getElementById('action-buttons').innerHTML = btns.map((b, i) => {
        state.modalCallbacks.push(b.action);
        return `<div class="modal-action-card" onclick="closeModal('actionModal');state.modalCallbacks[${i}]()"><div id="qr-act-${i}" class="bg-white p-1 rounded mb-2"></div><button class="btn btn-primary modal-action-btn">${b.label}</button></div>`;
    }).join('');
    btns.forEach((_, i) => generateSafeQR(`qr-act-${i}`, `CMD:MODAL:${i}`, 100));
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

        // 2.5. Refresh Location Manager Modal contents if open
        const manageModal = document.getElementById('manageModal');
        if (manageModal && manageModal.classList.contains('show')) {
            const manageLocId = document.getElementById('manage-loc-id');
            if (manageLocId && manageLocId.value && typeof window.refreshManageView === 'function') {
                window.refreshManageView(manageLocId.value);
            }
        }

        // 3. Broadcast Pulse for other modules (like Location Manager)
        document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));

    }, 5000); // 5 Second Heartbeat
};

// --- GLOBAL MODAL / WINDOW MANAGER ---
document.addEventListener('DOMContentLoaded', () => {
    // Start Heartbeat
    window.startSmartSync();
    
    // Initialize Wake Lock Handlers
    requestWakeLock();

    // 1. When a modal starts showing
    document.addEventListener('show.bs.modal', function (event) {
        // Auto-collapse Search Offcanvas if open to reduce clicks
        const offcanvasEl = document.getElementById('offcanvasSearch');
        if (offcanvasEl && offcanvasEl.classList.contains('show')) {
            const os = bootstrap.Offcanvas.getInstance(offcanvasEl);
            if (os) os.hide();
        }

        // Calculate and apply stacking z-index for the modal wrapper
        const openModals = document.querySelectorAll('.modal.show').length;
        // BS5 default modal z-index is 1055. Add 10 per subsequent tier.
        const newModalZ = 1055 + (openModals * 10);
        event.target.style.setProperty('z-index', newModalZ, 'important');
    });

    // 2. When modal finishes animating (backdrop is strictly in the DOM)
    document.addEventListener('shown.bs.modal', function () {
        // Find the last added backdrop and stack it purely behind our new modal
        const backdrops = document.querySelectorAll('.modal-backdrop');
        if (backdrops.length > 0) {
            const baseBackdropZIndex = 1050; // BS5 default backdrop z-index
            const newBackdropZ = baseBackdropZIndex + ((backdrops.length - 1) * 10);
            backdrops[backdrops.length - 1].style.setProperty('z-index', newBackdropZ, 'important');
        }
    });

    // 3. When a modal finishes hiding
    document.addEventListener('hidden.bs.modal', function () {
        // Bootstrap aggressively strips '.modal-open' from body when *any* modal hides.
        // We must forcefully restore it if there are other modals still 'underneath' it.
        if (document.querySelectorAll('.modal.show').length > 0) {
            document.body.classList.add('modal-open');
        }
    });
});

// [Code Guardian] Wake Lock Persistence
document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible') {
        await acquireLock();
    }
});