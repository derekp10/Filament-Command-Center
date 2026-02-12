/* MODULE: LOCATION MANAGER (Gold Standard - Polished v4 - Clean Events) */
console.log("🚀 Loaded Module: LOCATION MANAGER (Gold Standard v4)");

// --- EVENT LISTENER FOR BUFFER UPDATES ---
// This listens for the clean event from inv_cmd.js instead of patching functions.
document.addEventListener('inventory:buffer-updated', () => {
    // Only update if the manager modal is actually visible
    const modal = document.getElementById('manageModal');
    if (modal && modal.classList.contains('show')) {
        renderManagerNav();
    }
});

window.openLocationsModal = () => { modals.locMgrModal.show(); fetchLocations(); };

window.openManage = (id) => { 
    document.getElementById('manageTitle').innerText=`Location Manager: ${id}`; 
    document.getElementById('manage-loc-id').value=id; 
    const input = document.getElementById('manual-spool-id');
    if(input) input.value=""; 
    
    modals.manageModal.show(); 
    refreshManageView(id);
    
    // Generate Done QR (Size 50 to match action badges)
    generateSafeQR('qr-modal-done', 'CMD:DONE', 50);
};

window.closeManage = () => { modals.manageModal.hide(); fetchLocations(); };

window.refreshManageView = (id) => {
    renderManagerNav();

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
    });
    return true;
};

// --- HELPER: FORMAT RICH TEXT ---
const getRichInfo = (item) => {
    const d = item.details || {};
    const legacy = d.external_id ? `[Legacy: ${d.external_id}]` : "";
    const brand = d.brand || "Generic";
    const material = d.material || "PLA";
    const name = d.color_name || item.display.replace(/#\d+/, '').trim();
    const qName = name.startsWith('"') ? name : `"${name}"`; 
    const weight = d.weight ? `[${Math.round(d.weight)}g]` : "";
    
    return {
        line1: `#${item.id} ${legacy}`,
        line2: `${brand} ${material}`,
        line3: qName,
        line4: weight
    };
};

// --- RED ZONE: NAV DECK RENDERER ---
const renderManagerNav = () => {
    // UPDATED ID: Matches the renamed container in HTML to avoid conflict
    const n = document.getElementById('loc-mgr-nav-deck');
    if (!n) return;

    if (state.heldSpools.length > 1) {
        n.style.display = 'flex';
        
        const prevItem = state.heldSpools[state.heldSpools.length - 1];
        const prevStyle = getFilamentStyle(prevItem.color);
        const prevInfo = getRichInfo(prevItem);

        const nextItem = state.heldSpools[1];
        const nextStyle = getFilamentStyle(nextItem.color);
        const nextInfo = getRichInfo(nextItem);

        n.innerHTML = `
            <div class="cham-card nav-card" style="background: ${prevStyle.frame};" onclick="prevBuffer();">
                <div class="cham-body nav-inner" style="background:${prevStyle.inner}; display:flex; align-items:center; padding:10px;">
                    <div id="qr-nav-prev" class="nav-qr me-3"></div>
                    <div style="flex-grow:1;">
                        <div class="nav-label text-start">◀ PREV</div>
                        <div class="nav-text-main">
                            ${prevInfo.line1}<br>${prevInfo.line2}<br>${prevInfo.line3}<br><span style="color:#00d4ff">${prevInfo.line4}</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="cham-card nav-card" style="background: ${nextStyle.frame};" onclick="nextBuffer();">
                <div class="cham-body nav-inner" style="background:${nextStyle.inner}; display:flex; align-items:center; padding:10px;">
                    <div style="flex-grow:1; text-align:right;">
                        <div class="nav-label">NEXT ▶</div>
                        <div class="nav-text-main">
                            ${nextInfo.line1}<br>${nextInfo.line2}<br>${nextInfo.line3}<br><span style="color:#00d4ff">${nextInfo.line4}</span>
                        </div>
                    </div>
                    <div id="qr-nav-next" class="nav-qr ms-3"></div>
                </div>
            </div>
        `;
        generateSafeQR("qr-nav-prev", "CMD:PREV", 60);
        generateSafeQR("qr-nav-next", "CMD:NEXT", 60);
    } else {
        n.style.display = 'none';
        n.innerHTML = "";
    }
};

// --- YELLOW ZONE: SLOT GRID RENDERER ---
const renderGrid = (data, max) => {
    const grid = document.getElementById('slot-grid-container');
    const un = document.getElementById('unslotted-container');
    grid.innerHTML = ""; un.innerHTML = ""; state.currentGrid = {};
    const unslotted = [];
    
    data.forEach(i => { 
        if(i.slot && parseInt(i.slot) > 0) state.currentGrid[i.slot] = i; 
        else unslotted.push(i); 
    });
    
    for(let i=1; i<=max; i++) {
        const item = state.currentGrid[i];
        const div = document.createElement('div');
        div.className = "cham-card slot-btn full";
        
        if (item) {
            const styles = getFilamentStyle(item.color);
            const info = getRichInfo(item);
            
            // Frame Color as Background
            div.style.background = styles.frame;
            
            div.innerHTML = `
                <div class="slot-inner-gold" style="background:${styles.inner};">
                    <div class="slot-header">
                        <div class="slot-num-gold">SLOT ${i}</div>
                    </div>
                    
                    <div id="qr-slot-${i}" class="bg-white p-1 rounded" style="border: 3px solid white;"></div>
                    
                    <div class="slot-info-gold" style="cursor:pointer;" onclick="event.stopPropagation(); openSpoolDetails(${item.id})">
                        <div class="text-line-1">${info.line1}</div>
                        <div class="text-line-2">${info.line2}</div>
                        <div class="text-line-3">${info.line3}</div>
                        <div class="text-line-4">${info.line4}</div>
                    </div>

                    <div class="btn-label-compact" onclick="event.stopPropagation(); printLabel(${item.id})">
                        <span style="font-size:1.2rem;">📷</span> LABEL
                    </div>
                </div>`;
        } else {
            div.className = "slot-btn empty";
            div.style.justifyContent = 'center';
            div.innerHTML = `
                <div class="slot-num-gold" style="color:#555;">SLOT ${i}</div>
                <div id="qr-slot-${i}" class="bg-white p-2 rounded mt-3 mb-3" style="opacity:0.5;"></div>
                <div class="fs-4 text-muted fw-bold">EMPTY</div>`;
        }
        
        div.onclick = () => handleSlotInteraction(i); 
        grid.appendChild(div);
        
        if (item) generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:"+i, 90); 
        else generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:"+i, 80);
    }
    
    if(unslotted.length > 0) renderUnslotted(unslotted); 
    else un.style.display = 'none';
};

// --- GREEN ZONE: UNSLOTTED / LIST RENDERER ---
const renderList = (data, locId) => {
    const list = document.getElementById('manage-contents-list');
    const emptyMsg = document.getElementById('manage-empty-msg');
    
    if (data.length === 0) {
        list.innerHTML = "";
        if(emptyMsg) emptyMsg.style.display = 'block'; 
    } else {
        if(emptyMsg) emptyMsg.style.display = 'none'; 
        list.innerHTML = data.map((s,i) => renderBadgeHTML(s, i, locId)).join('');
        data.forEach((s,i) => renderBadgeQRs(s, i));
        generateSafeQR('qr-eject-all-list', 'CMD:EJECTALL', 56);
    }
};

const renderUnslotted = (items) => {
    const un = document.getElementById('unslotted-container');
    if (!un) return;
    un.style.display = 'block';
    
    let html = `<h4 class="text-info border-bottom border-secondary pb-2 mb-3 mt-4">Unslotted Items</h4>`;
    html += items.map((s,i) => renderBadgeHTML(s, i, document.getElementById('manage-loc-id').value)).join('');
    
    // REDESIGNED EJECT ALL CARD
    html += `
        <div class="danger-zone mt-4 pt-3 border-top border-danger">
            <div class="cham-card manage-list-item" style="border-color:#dc3545; background:#300;">
                <div class="eject-card-inner" onclick="triggerEjectAll('${document.getElementById('manage-loc-id').value}')" style="cursor:pointer;">
                    
                    <div class="eject-label-text">
                        <span style="font-size:3rem; vertical-align:middle;">☢️</span> 
                        DANGER ZONE
                    </div>

                    <div class="action-badge" style="border-color:#dc3545; background:#1f1f1f;">
                        <div id="qr-eject-all" class="badge-qr"></div>
                        <div class="badge-btn-gold text-white bg-danger mt-1 rounded">EJECT ALL</div>
                    </div>

                </div>
            </div>
        </div>`;
    
    un.innerHTML = html;
    items.forEach((s,i) => renderBadgeQRs(s, i));
    generateSafeQR("qr-eject-all", "CMD:EJECTALL", 65);
};

const renderBadgeHTML = (s, i, locId) => {
    const styles = getFilamentStyle(s.color);
    const info = getRichInfo(s);

    return `
    <div class="cham-card manage-list-item" style="background:${styles.frame}">
        <div class="list-inner-gold" style="background: ${styles.inner};">
            
            <div class="list-left" style="cursor:pointer;" onclick="openSpoolDetails(${s.id})">
                <div class="id-badge-gold">#${s.id}</div>
                <div class="d-flex flex-column text-white">
                     <div class="text-line-1">${info.line1}</div>
                     <div class="text-line-3" style="font-size:1.1rem;">${info.line2} ${info.line3}</div>
                     <div class="text-line-4">${info.line4}</div>
                </div>
            </div>

            <div class="action-group-gold">
                <div class="action-badge" onclick="ejectSpool(${s.id}, '${locId}', true)">
                    <div id="qr-pick-${i}" class="badge-qr"></div>
                    <div class="badge-btn-gold btn-pick-bg">PICK</div>
                </div>
                <div class="action-badge" onclick="event.stopPropagation(); quickQueue(${s.id})">
                    <div id="qr-print-${i}" class="badge-qr"></div>
                    <div class="badge-btn-gold btn-print-bg">QUEUE</div>
                </div>
                <div class="action-badge" onclick="ejectSpool(${s.id}, '${locId}', false)">
                    <div id="qr-trash-${i}" class="badge-qr"></div>
                    <div class="badge-btn-gold btn-trash-bg">TRASH</div>
                </div>
            </div>

        </div>
    </div>`;
};

const renderBadgeQRs = (s, i) => {
    generateSafeQR(`qr-pick-${i}`, "ID:"+s.id, 50);
    generateSafeQR(`qr-print-${i}`, "CMD:PRINT:"+s.id, 50);
    generateSafeQR(`qr-trash-${i}`, "CMD:TRASH:"+s.id, 50);
};

// --- INTERACTION (Global) ---
window.handleSlotInteraction = (slot) => {
    const locId = document.getElementById('manage-loc-id').value, item = state.currentGrid[slot];
    if (state.heldSpools.length > 0) {
        const newId = state.heldSpools[0].id;
        if(item) promptAction("Slot Occupied", `Swap/Overwrite Slot ${slot}?`, [
            {label:"Swap", action:()=>{
                state.heldSpools.shift(); 
                state.heldSpools.push({id:item.id, display:item.display, color:item.color}); 
                if(window.renderBuffer) window.renderBuffer(); 
                // Note: The event listener will handle the redraw, but we can double tap safely
                renderManagerNav();
                doAssign(locId, newId, slot);
            }}, 
            {label:"Overwrite", action:()=>{
                state.heldSpools.shift(); 
                if(window.renderBuffer) window.renderBuffer(); 
                renderManagerNav();
                doAssign(locId, newId, slot);
            }}
        ]);
        else { 
            state.heldSpools.shift(); 
            if(window.renderBuffer) window.renderBuffer(); 
            renderManagerNav();
            doAssign(locId, newId, slot); 
        }
    } else if(item) promptAction("Slot Action", `Manage ${item.display}`, [
        {label:"✋ Pick Up", action:()=>{
            state.heldSpools.unshift({id:item.id, display:item.display, color:item.color}); 
            if(window.renderBuffer) window.renderBuffer(); 
            renderManagerNav();
            doEject(item.id, locId, false);
        }}, 
        {label:"🗑️ Eject", action:()=>{doEject(item.id, locId, false);}}, 
        {label:"🖨️ Details", action:()=>{openSpoolDetails(item.id);}}
    ]);
};

window.doAssign = (loc, spool, slot) => { 
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

window.ejectSpool = (sid, loc, pickup) => { 
    if(pickup) { 
        fetch('/api/identify_scan', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text:"ID:"+sid})})
        .then(r=>r.json())
        .then(res=>{ 
            if(res.type==='spool'){ 
                if(state.heldSpools.some(s=>s.id===res.id)) showToast("In Buffer"); 
                else { 
                    state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); 
                    if(window.renderBuffer) window.renderBuffer(); 
                    renderManagerNav();
                } 
            } 
            doEject(sid, loc); 
        }); 
    } else { 
        if(loc!=="Scan") requestConfirmation(`Eject spool #${sid}?`, ()=>doEject(sid, loc)); 
        else doEject(sid, loc); 
    } 
};

window.doEject = (sid, loc) => { 
    setProcessing(true); 
    fetch('/api/manage_contents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'remove', location:loc, spool_id:sid})})
    .then(r=>r.json())
    .then(()=>{ setProcessing(false); showToast("Ejected"); if(loc!=="Scan") refreshManageView(loc); })
    .catch(()=>setProcessing(false)); 
};

window.manualAddSpool = () => {
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
            else { 
                state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); 
                if(window.renderBuffer) window.renderBuffer(); 
                renderManagerNav();
                showToast("Added to Buffer"); 
            }
        } else if (res.type === 'filament') openFilamentDetails(res.id);
        else showToast(res.msg || "Invalid Code", 'warning');
    })
    .catch(() => setProcessing(false));
};

window.triggerEjectAll = (loc) => promptSafety(`Nuke all unslotted in ${loc}?`, () => { 
    setProcessing(true); 
    fetch('/api/manage_contents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'clear_location', location:loc})})
    .then(r=>r.json())
    .then(()=>{setProcessing(false); refreshManageView(loc); showToast("Cleared!");}); 
});

window.printCurrentLocationLabel = () => {
    const locId = document.getElementById('manage-loc-id').value;
    if(!locId) return;
    setProcessing(true);
    fetch('/api/print_location_label', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: locId})
    })
    .then(r => r.json())
    .then(res => {
        setProcessing(false);
        if(res.success) showToast(res.msg, "success");
        else showToast(res.msg, "error");
    })
    .catch(() => { setProcessing(false); showToast("Connection Error", "error"); });
};

window.openEdit = (id) => { 
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

window.closeEdit = () => { modals.locModal.hide(); modals.locMgrModal.show(); };

window.saveLocation = () => { 
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

window.openAddModal = () => { 
    modals.locMgrModal.hide(); 
    document.getElementById('edit-original-id').value=""; 
    document.getElementById('edit-id').value=""; 
    document.getElementById('edit-name').value=""; 
    document.getElementById('edit-max').value="1"; 
    modals.locModal.show(); 
};

window.deleteLoc = (id) => requestConfirmation(`Delete ${id}?`, () => fetch(`/api/locations?id=${id}`, {method:'DELETE'}).then(fetchLocations));