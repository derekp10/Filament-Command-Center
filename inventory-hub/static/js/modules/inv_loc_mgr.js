/* MODULE: LOCATION MANAGER (Restored Layout v153.75) */
console.log("🚀 Loaded Module: LOCATION MANAGER (Restored)");

const openLocationsModal = () => { modals.locMgrModal.show(); fetchLocations(); };

const openManage = (id) => { 
    document.getElementById('manageTitle').innerText=`Location Manager: ${id}`; 
    document.getElementById('manage-loc-id').value=id; 
    const input = document.getElementById('manual-spool-id');
    if(input) input.value=""; 
    
    modals.manageModal.show(); 
    
    // IMPORTANT: Trigger buffer render so the Nav Deck appears immediately
    if(window.renderBuffer) window.renderBuffer();
    
    refreshManageView(id);
};

const closeManage = () => { modals.manageModal.hide(); fetchLocations(); };

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
        
        // Ensure Nav Deck updates if we have items in buffer
        if(window.renderBuffer) window.renderBuffer();
    });
    return true;
};

// --- RESTORED RENDERERS (Matches Screenshot) ---
const renderGrid = (data, max) => {
    const grid = document.getElementById('slot-grid-container');
    const un = document.getElementById('unslotted-container');
    
    grid.innerHTML = ""; 
    un.innerHTML = ""; 
    state.currentGrid = {};
    
    const unslotted = [];
    data.forEach(i => { 
        if(i.slot && parseInt(i.slot) > 0) state.currentGrid[i.slot] = i; 
        else unslotted.push(i); 
    });
    
    for(let i=1; i<=max; i++) {
        const item = state.currentGrid[i];
        const div = document.createElement('div');
        
        if (item) {
            // Occupied Slot - The "Dark Card" look from screenshot
            const styles = getFilamentStyle(item.color);
            div.className = "cham-card slot-btn full";
            div.style.background = styles.frame; // Gradient Border
            
            // Extract details safely
            const d = item.details || {};
            const mat = d.material || "";
            const weight = d.weight ? `[${Math.round(d.weight)}g]` : "";
            const brand = d.brand || "";
            const name = d.color_name || item.display;

            div.innerHTML = `
                <div class="cham-body slot-inner" style="background:${styles.inner}; padding: 10px; display:flex; flex-direction:column; justify-content:space-between; height:100%;">
                    <div class="d-flex justify-content-between w-100 align-items-center mb-1">
                        <div class="slot-num badge bg-white text-dark border border-secondary fw-bold">SLOT ${i}</div>
                    </div>
                    
                    <div id="qr-slot-${i}" class="bg-white p-1 rounded mb-2" style="border: 4px solid white; align-self:center;"></div>
                    
                    <div class="slot-content text-center" style="cursor:pointer; line-height:1.2;" onclick="event.stopPropagation(); openSpoolDetails(${item.id})">
                        <div style="font-size:0.9rem; font-weight:bold; color:#fff;">#${item.id} [Legacy: ${d.external_id || '?'}]</div>
                        <div style="font-size:0.85rem; color:#ccc;">${brand} ${mat}</div>
                        <div style="font-size:1.0rem; font-weight:bold; color:#fff; margin: 2px 0;">"${name}"</div>
                        <div style="font-size:0.9rem; color:#00d4ff;">${weight}</div>
                    </div>

                    <button class="btn btn-light border-dark mt-2 fw-bold py-1 w-100" style="font-size:0.8rem; text-transform:uppercase;" onclick="event.stopPropagation(); printLabel(${item.id})">🖨️ LABEL</button>
                </div>`;
        } else {
            // Empty Slot
            div.className = "slot-btn empty";
            div.innerHTML = `
                <div class="slot-num text-muted fw-bold mb-3">SLOT ${i}</div>
                <div id="qr-slot-${i}" class="bg-white p-2 rounded" style="opacity:0.8;"></div>
                <div class="text-muted fs-4 mt-3">EMPTY</div>`;
        }
        
        div.onclick = () => handleSlotInteraction(i); 
        grid.appendChild(div);
        
        // Generate QR (Size 75 matches the large QRs in screenshot)
        generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:"+i, 75); 
    }

    if(unslotted.length > 0) renderUnslotted(unslotted); 
    else un.style.display = 'none';
};

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
        
        // Eject All for List View
        generateSafeQR('qr-eject-all-list', 'CMD:EJECTALL', 56);
    }
};

const renderUnslotted = (items) => {
    const un = document.getElementById('unslotted-container');
    if (!un) return;
    un.style.display = 'block';
    
    let html = `<h4 class="text-info border-bottom border-secondary pb-2 mb-3 mt-4">Unslotted Items</h4>`;
    html += items.map((s,i) => renderBadgeHTML(s, i, document.getElementById('manage-loc-id').value)).join('');
    
    html += `
        <div class="danger-zone mt-4 pt-3 border-top border-danger">
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
    // Screenshot style for horizontal items
    const d = s.details || {};
    const legacyText = d.external_id ? `[Legacy: ${d.external_id}]` : "";
    const weightText = d.weight ? `[${Math.round(d.weight)}g]` : "";

    return `
    <div class="cham-card manage-list-item mb-2" style="background:${styles.frame}">
        <div class="cham-body" style="background: ${styles.inner}; display:flex; justify-content:space-between; align-items:center; padding:5px 10px;">
            <div class="cham-text-group d-flex align-items-center" style="cursor:pointer; overflow:hidden;" onclick="openSpoolDetails(${s.id})">
                <div class="cham-id-badge me-3" style="font-size:1.2rem;">#${s.id}</div>
                <div class="d-flex flex-column text-white">
                     <div style="font-weight:bold; font-size:1.1rem;">${legacyText} ${s.display}</div>
                     <div class="small" style="color:#ccc;">${weightText}</div>
                </div>
            </div>
            <div class="cham-actions d-flex gap-2">
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

// --- INTERACTION ---
const handleSlotInteraction = (slot) => {
    const locId = document.getElementById('manage-loc-id').value, item = state.currentGrid[slot];
    if (state.heldSpools.length > 0) {
        const newId = state.heldSpools[0].id;
        if(item) promptAction("Slot Occupied", `Swap/Overwrite Slot ${slot}?`, [
            {label:"Swap", action:()=>{
                state.heldSpools.shift(); 
                state.heldSpools.push({id:item.id, display:item.display, color:item.color}); 
                if(window.renderBuffer) window.renderBuffer(); 
                doAssign(locId, newId, slot);
            }}, 
            {label:"Overwrite", action:()=>{
                state.heldSpools.shift(); 
                if(window.renderBuffer) window.renderBuffer(); 
                doAssign(locId, newId, slot);
            }}
        ]);
        else { 
            state.heldSpools.shift(); 
            if(window.renderBuffer) window.renderBuffer(); 
            doAssign(locId, newId, slot); 
        }
    } else if(item) promptAction("Slot Action", `Manage ${item.display}`, [
        {label:"✋ Pick Up", action:()=>{
            state.heldSpools.unshift({id:item.id, display:item.display, color:item.color}); 
            if(window.renderBuffer) window.renderBuffer(); 
            doEject(item.id, locId, false);
        }}, 
        {label:"🗑️ Eject", action:()=>{doEject(item.id, locId, false);}}, 
        {label:"🖨️ Details", action:()=>{openSpoolDetails(item.id);}}
    ]);
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
                else { 
                    state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); 
                    if(window.renderBuffer) window.renderBuffer(); 
                } 
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
            else { 
                state.heldSpools.unshift({id:res.id, display:res.display, color:res.color}); 
                if(window.renderBuffer) window.renderBuffer(); 
                showToast("Added to Buffer"); 
            }
        } else if (res.type === 'filament') openFilamentDetails(res.id);
        else showToast(res.msg || "Invalid Code", 'warning');
    })
    .catch(() => setProcessing(false));
};

const triggerEjectAll = (loc) => promptSafety(`Nuke all unslotted in ${loc}?`, () => { 
    setProcessing(true); 
    fetch('/api/manage_contents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'clear_location', location:loc})})
    .then(r=>r.json())
    .then(()=>{setProcessing(false); refreshManageView(loc); showToast("Cleared!");}); 
});

const printCurrentLocationLabel = () => {
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

// CRUD
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