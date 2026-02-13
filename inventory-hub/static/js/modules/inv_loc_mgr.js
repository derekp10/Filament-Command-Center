/* MODULE: LOCATION MANAGER (Gold Standard - Polished v27 - Deposit Fix) */
console.log("🚀 Loaded Module: LOCATION MANAGER (Gold Standard v27)");

document.addEventListener('inventory:buffer-updated', () => {
    const modal = document.getElementById('manageModal');
    if (modal && modal.classList.contains('show')) {
        renderManagerNav();
        // Refresh view to toggle Deposit button visibility
        const id = document.getElementById('manage-loc-id').value;
        if(id) refreshManageView(id);
    }
});

window.openLocationsModal = () => { modals.locMgrModal.show(); fetchLocations(); };

// --- PRE-FLIGHT PROTOCOL ---
window.openManage = (id) => { 
    setProcessing(true);

    document.getElementById('manageTitle').innerText=`Location Manager: ${id}`; 
    document.getElementById('manage-loc-id').value=id; 
    const input = document.getElementById('manual-spool-id');
    if(input) input.value=""; 
    
    // 1. Wipe old data
    document.getElementById('slot-grid-container').innerHTML = '';
    document.getElementById('manage-contents-list').innerHTML = '';
    document.getElementById('unslotted-container').innerHTML = '';
    
    document.getElementById('manage-grid-view').style.display = 'none';
    document.getElementById('manage-list-view').style.display = 'none';
    
    const loc = state.allLocations.find(l=>l.LocationID==id);
    if(!loc) { setProcessing(false); return; }

    const isGrid = (loc.Type==='Dryer Box' || loc.Type==='MMU Slot') && parseInt(loc['Max Spools']) > 1;

    fetch(`/api/get_contents?id=${id}`)
    .then(r=>r.json())
    .then(d => {
        if(isGrid) {
            document.getElementById('manage-grid-view').style.display = 'block';
            document.getElementById('manage-list-view').style.display = 'none';
            renderGrid(d, parseInt(loc['Max Spools']));
        } else {
            document.getElementById('manage-grid-view').style.display = 'none';
            document.getElementById('manage-list-view').style.display = 'block';
            renderList(d, id);
        }
        
        renderManagerNav();
        generateSafeQR('qr-modal-done', 'CMD:DONE', 58);

        setProcessing(false);
        modals.manageModal.show();
    })
    .catch(e => {
        console.error(e);
        setProcessing(false);
        showToast("Failed to load location data", "error");
    });
};

window.closeManage = () => { modals.manageModal.hide(); fetchLocations(); };

window.refreshManageView = (id) => {
    renderManagerNav();
    const loc = state.allLocations.find(l=>l.LocationID==id); 
    if(!loc) return false;
    
    const isGrid = (loc.Type==='Dryer Box' || loc.Type==='MMU Slot') && parseInt(loc['Max Spools']) > 1;
    
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

// --- RED ZONE: NAV DECK ---
const renderManagerNav = () => {
    const n = document.getElementById('loc-mgr-nav-deck');
    if (!n) return;

    if (state.heldSpools.length > 0) {
        n.style.display = 'flex';
        const curItem = state.heldSpools[0];
        const prevItem = state.heldSpools.length > 1 ? state.heldSpools[state.heldSpools.length - 1] : null;
        const nextItem = state.heldSpools.length > 1 ? state.heldSpools[1] : null;
        const curStyle = getFilamentStyle(curItem.color);
        const curInfo = getRichInfo(curItem);
        let html = '';

        if (prevItem) {
            const prevStyle = getFilamentStyle(prevItem.color);
            const prevInfo = getRichInfo(prevItem);
            html += `
            <div class="cham-card nav-card" style="background: ${prevStyle.frame};" onclick="prevBuffer();">
                <div class="cham-body nav-inner" style="background:${prevStyle.inner}; display:flex; align-items:center; padding:5px 10px;">
                    <div id="qr-nav-prev" class="nav-qr me-2"></div>
                    <div>
                        <div class="nav-label text-start">◀ PREV</div>
                        <div class="nav-text-main" style="font-size:0.9rem;">#${prevItem.id}<br>${prevInfo.line3}</div>
                    </div>
                </div>
            </div>`;
        } else { html += `<div style="flex:1;"></div>`; }

        html += `
        <div class="cham-card nav-card nav-card-center" style="background: ${curStyle.frame};">
            <div class="cham-body nav-inner" style="background:${curStyle.inner}; display:flex; flex-direction:column; justify-content:center; align-items:center; padding:10px; text-align:center;">
                <div class="nav-label">READY TO SLOT</div>
                <div class="id-badge-gold shadow-sm mb-2" style="font-size:1.4rem;">#${curItem.id}</div>
                <div class="nav-text-main" style="font-size:1.3rem; margin-bottom:5px;">${curInfo.line3}</div>
                <div style="font-size:1.0rem; color:#fff; font-weight:bold; text-shadow: 2px 2px 4px #000;">${curInfo.line2}</div>
            </div>
        </div>`;

        if (nextItem) {
            const nextStyle = getFilamentStyle(nextItem.color);
            const nextInfo = getRichInfo(nextItem);
            html += `
            <div class="cham-card nav-card" style="background: ${nextStyle.frame};" onclick="nextBuffer();">
                <div class="cham-body nav-inner" style="background:${nextStyle.inner}; display:flex; align-items:center; justify-content:flex-end; padding:5px 10px;">
                    <div style="text-align:right;">
                        <div class="nav-label">NEXT ▶</div>
                        <div class="nav-text-main" style="font-size:0.9rem;">#${nextItem.id}<br>${nextInfo.line3}</div>
                    </div>
                    <div id="qr-nav-next" class="nav-qr ms-2"></div>
                </div>
            </div>`;
        } else { html += `<div style="flex:1;"></div>`; }

        n.innerHTML = html;
        requestAnimationFrame(() => {
            if(prevItem) generateSafeQR("qr-nav-prev", "CMD:PREV", 50);
            if(nextItem) generateSafeQR("qr-nav-next", "CMD:NEXT", 50);
        });
    } else {
        n.style.display = 'none';
        n.innerHTML = "";
    }
};

window.handleLabelClick = (e, id, display) => {
    e.stopPropagation(); 
    window.addToQueue({id: id, type: 'spool', display: display});
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
        div.className = item ? "cham-card slot-btn full" : "slot-btn empty";
        div.onclick = () => handleSlotInteraction(i);

        if (item) {
            const styles = getFilamentStyle(item.color);
            const info = getRichInfo(item);
            div.style.background = styles.frame;
            
            div.innerHTML = `
                <div class="slot-inner-gold" style="background:${styles.inner};">
                    <div class="slot-header"><div class="slot-num-gold">SLOT ${i}</div></div>
                    <div id="qr-slot-${i}" class="bg-white p-1 rounded" style="border: 3px solid white;"></div>
                    <div class="slot-info-gold" style="cursor:pointer;" onclick="event.stopPropagation(); openSpoolDetails(${item.id})">
                        <div class="text-line-1">${info.line1}</div>
                        <div class="text-line-2" style="color:#fff; font-weight:bold; text-shadow: 2px 2px 4px #000;">${info.line2}</div>
                        <div class="text-line-3">${info.line3}</div>
                        <div class="text-line-4">${info.line4}</div>
                    </div>
                    <div class="btn-label-compact js-btn-label">
                        <span style="font-size:1.2rem;">📷</span> LABEL
                    </div>
                </div>`;
                
            const btn = div.querySelector('.js-btn-label');
            if (btn) {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation(); 
                    window.addToQueue({id: item.id, type: 'spool', display: item.display});
                });
            }
        } else {
            div.innerHTML = `
                <div class="slot-inner-gold">
                    <div class="slot-header"><div class="slot-num-gold" style="color:#555;">SLOT ${i}</div></div>
                    <div id="qr-slot-${i}" class="bg-white p-2 rounded mt-3 mb-3" style="opacity:0.5;"></div>
                    <div class="fs-4 text-muted fw-bold" style="margin-top:20px;">EMPTY</div>
                    <div style="height:35px;"></div>
                </div>`;
        }
        
        grid.appendChild(div);
        
        requestAnimationFrame(() => {
            if (item) generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:"+i, 90); 
            else generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:"+i, 80);
        });
    }
    
    if(unslotted.length > 0) renderUnslotted(unslotted); 
    else un.style.display = 'none';
};

// --- GREEN ZONE: LIST RENDERER ---
const renderList = (data, locId) => {
    const list = document.getElementById('manage-contents-list');
    const emptyMsg = document.getElementById('manage-empty-msg');
    
    list.innerHTML = "";
    
    // 1. DEPOSIT CARD
    if (state.heldSpools.length > 0) {
        const item = state.heldSpools[0];
        const styles = getFilamentStyle(item.color);
        
        if(emptyMsg) emptyMsg.style.display = 'none';
        
        const depositCard = document.createElement('div');
        depositCard.className = "cham-card manage-list-item";
        depositCard.style.cssText = `background:${styles.frame}; border: 2px dashed #fff; cursor: pointer; margin-bottom: 15px;`;
        depositCard.onclick = () => doAssign(locId, item.id, null); 
        
        depositCard.innerHTML = `
            <div class="list-inner-gold" style="background: ${styles.inner}; justify-content: center; flex-direction: column; padding: 15px;">
                <div style="font-size: 1.5rem; font-weight: 900; color: #fff; text-shadow: 2px 2px 4px #000; text-transform: uppercase;">
                    ⬇️ DEPOSIT HERE
                </div>
                <div style="color: #fff; text-shadow: 1px 1px 3px #000; margin-top: 5px; font-weight: bold;">
                    #${item.id} - ${item.display}
                </div>
            </div>`;
            
        list.appendChild(depositCard);
    } 
    else {
        if (data.length === 0) {
            if(emptyMsg) emptyMsg.style.display = 'block'; 
        } else {
            if(emptyMsg) emptyMsg.style.display = 'none'; 
        }
    }

    // 2. Existing Items
    if (data.length > 0) {
        data.forEach((s,i) => {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = renderBadgeHTML(s, i, locId);
            const el = tempDiv.firstElementChild;
            const btnLabel = el.querySelector('.js-btn-label');
            if (btnLabel) {
                btnLabel.addEventListener('click', (e) => {
                    e.stopPropagation();
                    window.addToQueue({id: s.id, type: 'spool', display: s.display});
                });
            }
            list.appendChild(el);
        });
        
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                data.forEach((s,i) => renderBadgeQRs(s, i));
                generateSafeQR('qr-eject-all-list', 'CMD:EJECTALL', 56);
            });
        });
    }
};

const renderUnslotted = (items) => {
    const un = document.getElementById('unslotted-container');
    if (!un) return;
    un.style.display = 'block';
    
    let html = `<h4 class="text-info border-bottom border-secondary pb-2 mb-3 mt-4">Unslotted Items</h4>`;
    un.innerHTML = html;
    
    const itemContainer = document.createElement('div');
    items.forEach((s,i) => {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = renderBadgeHTML(s, i, document.getElementById('manage-loc-id').value);
        const el = tempDiv.firstElementChild;
        const btnLabel = el.querySelector('.js-btn-label');
        if (btnLabel) {
            btnLabel.addEventListener('click', (e) => {
                e.stopPropagation();
                window.addToQueue({id: s.id, type: 'spool', display: s.display});
            });
        }
        itemContainer.appendChild(el);
    });
    
    un.appendChild(itemContainer);
    
    const dangerDiv = document.createElement('div');
    dangerDiv.className = "danger-zone mt-4 pt-3 border-top border-danger";
    dangerDiv.innerHTML = `
        <div class="cham-card manage-list-item" style="border-color:#dc3545; background:#300;">
            <div class="eject-card-inner">
                <div class="eject-label-text"><span style="font-size:3rem; vertical-align:middle;">☢️</span> DANGER ZONE</div>
                <div class="action-badge" style="border-color:#dc3545; background:#1f1f1f;" onclick="triggerEjectAll(document.getElementById('manage-loc-id').value)">
                    <div id="qr-eject-all" class="qr-bg-white"></div>
                    <div class="badge-btn-gold text-white bg-danger mt-1 rounded">EJECT ALL</div>
                </div>
            </div>
        </div>`;
    un.appendChild(dangerDiv);
    
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            items.forEach((s,i) => renderBadgeQRs(s, i));
            generateSafeQR("qr-eject-all", "CMD:EJECTALL", 65);
        });
    });
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
                     <div class="text-line-2" style="color:#fff; font-weight:bold; text-shadow: 2px 2px 4px #000;">${info.line2}</div>
                     <div class="text-line-3">${info.line3}</div>
                     <div class="text-line-4">${info.line4}</div>
                </div>
            </div>
            <div class="action-group-gold">
                <div class="action-badge" onclick="ejectSpool(${s.id}, '${locId}', true)">
                    <div id="qr-pick-${i}" class="badge-qr"></div>
                    <div class="badge-btn-gold btn-pick-bg">PICK</div>
                </div>
                <div class="action-badge js-btn-label">
                    <div id="qr-print-${i}" class="badge-qr"></div>
                    <div class="badge-btn-gold btn-print-bg">LABEL</div>
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

// --- INTERACTION ---
window.handleSlotInteraction = (slot) => {
    const locId = document.getElementById('manage-loc-id').value, item = state.currentGrid[slot];
    if (state.heldSpools.length > 0) {
        const newId = state.heldSpools[0].id;
        if(item) {
            promptAction("Slot Occupied", `Swap/Overwrite Slot ${slot}?`, [
                {label:"Swap", action:()=>{
                    state.heldSpools.shift(); 
                    state.heldSpools.push({id:item.id, display:item.display, color:item.color}); 
                    if(window.renderBuffer) window.renderBuffer(); 
                    renderManagerNav();
                    doAssign(locId, newId, slot);
                }}, 
                {label:"Overwrite", action:()=>{
                    state.heldSpools.shift(); 
                    if(window.renderBuffer) window.renderBuffer(); 
                    renderManagerNav();
                    doAssign(locId, newId, slot);
                }},
                {label:"Cancel", action:()=>{ closeModal('actionModal'); }}
            ]);
        } else { 
            state.heldSpools.shift(); 
            if(window.renderBuffer) window.renderBuffer(); 
            renderManagerNav();
            doAssign(locId, newId, slot); 
        }
    } else if(item) {
        promptAction("Slot Action", `Manage ${item.display}`, [
            {label:"✋ Pick Up", action:()=>{
                state.heldSpools.unshift({id:item.id, display:item.display, color:item.color}); 
                if(window.renderBuffer) window.renderBuffer(); 
                renderManagerNav();
                doEject(item.id, locId, false);
            }}, 
            {label:"🗑️ Eject", action:()=>{doEject(item.id, locId, false);}}, 
            {label:"🖨️ Details", action:()=>{openSpoolDetails(item.id);}}
        ]);
    }
};

window.doAssign = (loc, spool, slot) => { 
    setProcessing(true); 
    fetch('/api/manage_contents', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'add', location:loc, spool_id:"ID:"+spool, slot})})
    .then(r=>r.json())
    .then(res=>{
        setProcessing(false); 
        if(res.status==='success') { 
            showToast("Assigned");
            
            // --- FIX: Remove the assigned spool from buffer ---
            // If the spool ID matches something in the buffer, nuke it
            const spoolIdStr = String(spool).replace("ID:", "");
            const bufIdx = state.heldSpools.findIndex(s => String(s.id) === spoolIdStr);
            if (bufIdx > -1) {
                state.heldSpools.splice(bufIdx, 1);
                // Update global UI
                if(window.renderBuffer) window.renderBuffer();
            }
            
            refreshManageView(loc); 
        } 
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
    window.addToQueue({ id: locId, type: 'location', display: `Location: ${locId}` });
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