/* MODULE: LOCATION MANAGER (Gold Standard - Polished v31 - 0-Index Fix) */
console.log("🚀 Loaded Module: LOCATION MANAGER (Gold Standard v31)");

document.addEventListener('inventory:buffer-updated', () => {
    const modal = document.getElementById('manageModal');
    if (modal && modal.classList.contains('show')) {
        renderManagerNav();
        // Refresh to update Deposit button visibility
        const id = document.getElementById('manage-loc-id').value;
        if (id) refreshManageView(id);
    }
});

window.openLocationsModal = () => { modals.locMgrModal.show(); fetchLocations(); };

window.updateManageTitle = (loc, itemArray = null) => {
    let occHtml = ``;
    let occupancyStr = loc.Occupancy || '--';
    
    // [ALEX FIX] Real-time mathematical override for instantaneous title snappiness
    // Safely parse capacity. Arrays returned from /api/get_contents represent direct physical counts.
    if (itemArray !== null && loc['Max Spools']) {
        const capacity = parseInt(loc['Max Spools']);
        // Use realistic count ignoring virtual ghost spools? No, payload is physical items.
        occupancyStr = `${itemArray.length}/${capacity > 0 ? capacity : '--'}`;
    }

    if (occupancyStr !== '--') {
        const parts = occupancyStr.split('/');
        let occColor = '#fff';
        let isEmpty = parseInt(parts[0]) === 0;

        if (parts.length === 2 && !isNaN(parseInt(parts[0])) && !isNaN(parseInt(parts[1]))) {
            if (parseInt(parts[0]) >= parseInt(parts[1])) occColor = '#ff4444'; // Red if full
            else if (isEmpty) occColor = '#ffc107'; // Yellow if empty
        } else if (isEmpty) {
            occColor = '#ffc107';
        }
        
        let emptyWarn = '';
        if (occColor === '#ffc107') {
            emptyWarn = `<span class="text-pop ms-2" style="font-size:1.4rem; color:#ffc107; font-weight: 900; line-height: 1;">⚠️ EMPTY</span>`;
        }

        let occText = `${occupancyStr} Spools`;
        if (parts.length === 1 || isNaN(parseInt(parts[1]))) {
            occText = `Total Spools: ${parseInt(parts[0])}`;
        }

        occHtml = `<span class="text-pop ms-3" style="color:${occColor}; font-size:1.1rem; border-left: 2px solid #555; padding-left: 12px;">${occText}</span>${emptyWarn}`;
    }

    let badgeClass = 'bg-secondary';
    let badgeStyle = 'border:1px solid #555;';
    const t = loc.Type || '';
    if (t.includes('Dryer')) { badgeClass = 'bg-warning text-dark'; badgeStyle = 'border:1px solid #fff;'; }
    else if (t.includes('Storage')) { badgeClass = 'bg-primary'; badgeStyle = 'border:1px solid #88f;'; }
    else if (t.includes('MMU')) { badgeClass = 'bg-danger'; badgeStyle = 'border:1px solid #f88;'; }
    else if (t.includes('Shelf')) { badgeClass = 'bg-success'; badgeStyle = 'border:1px solid #8f8;'; }
    else if (t.includes('Cart')) { badgeClass = 'bg-info text-dark'; badgeStyle = 'border:1px solid #fff;'; }
    else if (t.includes('Printer') || t.includes('Toolhead')) { badgeClass = 'bg-dark'; badgeStyle = 'border:1px solid #f0f; background-color: #aa00ff !important; color: #fff;'; }
    else if (t.includes('Virtual')) { badgeClass = 'bg-light text-dark'; badgeStyle = 'border:1px solid #fff; box-shadow: 0 0 5px rgba(255,255,255,0.5);'; }
    
    const typeBadge = `<span class="badge ${badgeClass} ms-3 fs-6" style="box-shadow: 1px 1px 3px rgba(0,0,0,0.5); padding-top: 5px; ${badgeStyle}">${loc.Type}</span>`;

    document.getElementById('manageTitle').innerHTML = `<div class="d-flex align-items-center">📍 ${loc.LocationID} ${typeBadge} ${occHtml}</div>`;
};

// --- PRE-FLIGHT PROTOCOL ---
window.openManage = (id) => {
    setProcessing(true);

    const loc = state.allLocations.find(l => l.LocationID == id);
    if (!loc) { setProcessing(false); return; }

    window.updateManageTitle(loc);
    document.getElementById('manage-loc-id').value = id;
    const input = document.getElementById('manual-spool-id');
    if (input) input.value = "";

    // 1. Wipe old data
    document.getElementById('slot-grid-container').innerHTML = '';
    document.getElementById('manage-contents-list').innerHTML = '';
    document.getElementById('unslotted-container').innerHTML = '';

    document.getElementById('manage-grid-view').style.display = 'none';
    document.getElementById('manage-list-view').style.display = 'none';



    const isGrid = (loc.Type === 'Dryer Box' || loc.Type === 'MMU Slot') && parseInt(loc['Max Spools']) > 1;

    fetch(`/api/get_contents?id=${id}`)
        .then(r => r.json())
        .then(d => {
            if (isGrid) {
                document.getElementById('manage-grid-view').style.display = 'block';
                document.getElementById('manage-list-view').style.display = 'none';
                renderGrid(d, parseInt(loc['Max Spools']));
            } else {
                document.getElementById('manage-grid-view').style.display = 'none';
                document.getElementById('manage-list-view').style.display = 'block';
                renderList(d, id);
            }

            renderManagerNav();
            // Phase 2: render the Slot → Toolhead Feeds section if applicable.
            if (window.renderFeedsSection) window.renderFeedsSection(loc);
            // Generate QR for specific location
            const safeId = String(id).replace(/['"]/g, '');
            generateSafeQR('manage-loc-qr-mini', 'LOC:' + safeId, 45);
            generateSafeQR('qr-modal-done', 'CMD:DONE', 58);

            // Prime the Hash to prevent "First Pulse Wiggle"
            const bufHash = state.heldSpools.map(s => s.id).join(',');
            state.lastLocRenderHash = `${JSON.stringify(d)}|${bufHash}`;

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

// ---------------------------------------------------------------------------
// Phase 2: Slot → Toolhead Feeds (Dryer Box only)
// ---------------------------------------------------------------------------

// Cached printer_map fetched from /api/printer_map. Shape:
//   { printers: { "🦝 XL": [{location_id, position}, ...] } }
state.printerMap = state.printerMap || null;

const fetchPrinterMap = () => {
    if (state.printerMap) return Promise.resolve(state.printerMap);
    return fetch('/api/printer_map')
        .then(r => r.json())
        .then(data => { state.printerMap = data.printers || {}; return state.printerMap; })
        .catch(e => { console.warn("printer_map fetch failed", e); return {}; });
};

const renderFeedsSection = (loc) => {
    const section = document.getElementById('manage-feeds-section');
    if (!section) return;

    if (loc.Type !== 'Dryer Box') {
        section.style.display = 'none';
        return;
    }
    section.style.display = 'block';

    // Start collapsed; user toggles open when they want to edit.
    document.getElementById('feeds-body').style.display = 'none';
    document.getElementById('feeds-toggle-btn').innerText = 'Show';
    document.getElementById('feeds-status').innerText = '';

    const maxSlots = parseInt(loc['Max Spools']) || 0;
    if (maxSlots <= 0) {
        document.getElementById('feeds-rows').innerHTML =
            '<div class="text-warning small">This location has Max Spools of 0 — no slots to bind.</div>';
        return;
    }

    Promise.all([
        fetchPrinterMap(),
        fetch(`/api/dryer_box/${encodeURIComponent(loc.LocationID)}/bindings`)
            .then(r => r.ok ? r.json() : { slot_targets: {} }),
    ]).then(([printers, bindingsResp]) => {
        const targets = bindingsResp.slot_targets || {};
        const rows = document.getElementById('feeds-rows');
        rows.innerHTML = '';
        for (let slot = 1; slot <= maxSlots; slot++) {
            const slotKey = String(slot);
            const currentTarget = (targets[slotKey] || '').toUpperCase();

            // Build dropdown: None + <optgroup per printer>
            let optsHtml = '<option value="">— None (staging / drying)</option>';
            Object.keys(printers).sort().forEach(printerName => {
                const entries = printers[printerName] || [];
                const optionLines = entries.map(e => {
                    const isSel = e.location_id.toUpperCase() === currentTarget;
                    return `<option value="${e.location_id}"${isSel ? ' selected' : ''}>${e.location_id} (pos ${e.position})</option>`;
                }).join('');
                if (optionLines) {
                    optsHtml += `<optgroup label="${printerName}">${optionLines}</optgroup>`;
                }
            });

            const rowHtml = `
                <div class="d-flex align-items-center gap-2 feeds-row" data-slot="${slot}">
                    <span class="badge bg-secondary" style="min-width: 60px;">Slot ${slot}</span>
                    <select class="form-select form-select-sm bg-black text-white border-secondary feeds-select"
                            data-slot="${slot}">${optsHtml}</select>
                </div>
            `;
            rows.insertAdjacentHTML('beforeend', rowHtml);
        }
    });
};

window.toggleFeedsSection = () => {
    const body = document.getElementById('feeds-body');
    const btn = document.getElementById('feeds-toggle-btn');
    if (!body || !btn) return;
    const hidden = body.style.display === 'none' || !body.style.display;
    body.style.display = hidden ? 'block' : 'none';
    btn.innerText = hidden ? 'Hide' : 'Show';
};

window.saveFeedsSection = () => {
    const locId = document.getElementById('manage-loc-id').value;
    if (!locId) return;
    const status = document.getElementById('feeds-status');
    status.className = 'small flex-grow-1 text-info';
    status.innerText = 'Saving…';

    // Collect slot_targets from all selects. Empty-string values map to None.
    const selects = document.querySelectorAll('#feeds-rows select.feeds-select');
    const slot_targets = {};
    selects.forEach(sel => {
        const slot = sel.dataset.slot;
        const val = sel.value;
        slot_targets[slot] = val || null;
    });

    fetch(`/api/dryer_box/${encodeURIComponent(locId)}/bindings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot_targets }),
    })
        .then(async r => ({ ok: r.ok, body: await r.json() }))
        .then(({ ok, body }) => {
            if (ok) {
                status.className = 'small flex-grow-1 text-success';
                status.innerText = `✅ Saved ${Object.keys(body.slot_targets || {}).length} binding(s)`;
                showToast(`🔗 Saved feeds for ${locId}`, 'success', 4000);
            } else {
                status.className = 'small flex-grow-1 text-danger';
                const errs = (body.errors || []).map(e => `Slot ${e.slot}: ${e.reason}`).join('; ');
                status.innerText = errs || body.error || 'Save failed';
                showToast(`❌ Feeds save rejected: ${errs || body.error}`, 'error', 8000);
            }
        })
        .catch(e => {
            console.error(e);
            status.className = 'small flex-grow-1 text-danger';
            status.innerText = 'Network error';
            showToast('Feeds save — network error', 'error', 7000);
        });
};

window.renderFeedsSection = renderFeedsSection;

window.refreshManageView = (id) => {
    const loc = state.allLocations.find(l => l.LocationID == id);
    if (!loc) return false;

    // Fetch data first (Don't touch DOM yet)
    fetch(`/api/get_contents?id=${id}`)
        .then(r => r.json())
        .then(d => {
            // --- NO WIGGLE CHECK ---
            // Create a signature of the Content + Buffer State
            const bufHash = state.heldSpools.map(s => s.id).join(',');
            const contentHash = JSON.stringify(d);
            const newHash = `${contentHash}|${bufHash}`;

            // If nothing changed, STOP. This eliminates the wiggle for 99% of sync pulses.
            if (state.lastLocRenderHash === newHash) return;
            state.lastLocRenderHash = newHash;
            // -----------------------

            // Data changed? Okay, render it.
            window.updateManageTitle(loc, d);
            renderManagerNav();
            const isGrid = (loc.Type === 'Dryer Box' || loc.Type === 'MMU Slot') && parseInt(loc['Max Spools']) > 1;
            if (isGrid) renderGrid(d, parseInt(loc['Max Spools']));
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
    const weight = d.weight ? `[${Math.round(d.weight)}g]` : "";

    return {
        line1: `#${item.id} ${legacy}`,
        line2: `${brand} ${material}`,
        line3: name,
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
        const curStyle = getFilamentStyle(curItem.color, curItem.color_direction || 'longitudinal');
        const curInfo = getRichInfo(curItem);
        let html = '';

        if (prevItem) {
            html += window.SpoolCardBuilder.buildCard(prevItem, 'buffer_nav', { navDirection: 'prev', navAction: 'window.prevBuffer()' });
        } else { html += `<div style="flex:1;"></div>`; }

        html += `
        <div class="cham-card nav-card nav-card-center" style="background: ${curStyle.frame}; ${curStyle.border ? 'box-shadow: inset 0 0 0 2px #555;' : ''}">
            <div class="fcc-spool-card-inner nav-inner" style="background:${curStyle.inner}; display:flex; flex-direction:column; justify-content:center; align-items:center; padding:10px; text-align:center; position:relative;">
                <div style="position:absolute; top:5px; right:5px; display:flex; gap:6px; z-index: 10;">
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.removeBufferItem(${curItem.id});" title="Drop from Buffer">❌</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); openSpoolDetails(${curItem.id});" title="View Details">🔍</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.openEditWizard(${curItem.id});" title="Edit Spool">✏️</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.addToQueue({ id: ${curItem.id}, type: 'spool', display: '${curItem.display ? curItem.display.replace(/[\'"]/g, '') : ''}' }); showToast('Added to Print Queue');" title="Add to Print Queue">🖨️</div>
                </div>
                <div class="nav-label">READY TO SLOT</div>
                ${(curItem.archived === true || String(curItem.archived).toLowerCase() === 'true') ? `<div class="badge text-bg-danger mb-2" style="font-size: 0.9rem;">📦 ARCHIVED</div>` : ''}
                <div class="id-badge-gold shadow-sm mb-2" style="font-size:1.4rem;">#${curItem.id}</div>
                <div class="nav-text-main" style="font-size:1.3rem; margin-bottom:5px;">${curInfo.line3}</div>
                <div class="text-pop" style="font-size:1.0rem; color:#fff; font-weight:bold;">${curInfo.line2}</div>
            </div>
        </div>`;

        if (nextItem) {
            html += window.SpoolCardBuilder.buildCard(nextItem, 'buffer_nav', { navDirection: 'next', navAction: 'window.nextBuffer()' });
        } else { html += `<div style="flex:1;"></div>`; }

        n.innerHTML = html;
        requestAnimationFrame(() => {
            if (prevItem) generateSafeQR("qr-nav-prev", "CMD:PREV", 50);
            if (nextItem) generateSafeQR("qr-nav-next", "CMD:NEXT", 50);
        });
    } else {
        n.style.display = 'none';
        n.innerHTML = "";
    }
};

window.handleLabelClick = (e, id, display) => {
    e.stopPropagation();
    window.addToQueue({ id: id, type: 'spool', display: display });
};

// --- YELLOW ZONE: SLOT GRID RENDERER ---
const renderGrid = (data, max) => {
    const grid = document.getElementById('slot-grid-container');
    const un = document.getElementById('unslotted-container');
    grid.innerHTML = ""; un.innerHTML = ""; state.currentGrid = {};
    const unslotted = [];

    data.forEach(i => {
        if (i.slot && parseInt(i.slot) > 0) state.currentGrid[i.slot] = i;
        else unslotted.push(i);
    });

    let gridHTML = "";
    for (let i = 1; i <= max; i++) {
        const item = state.currentGrid[i];
        if (item) {
            gridHTML += window.SpoolCardBuilder.buildCard(item, 'loc_grid', { slotNum: i, locId: document.getElementById('manage-loc-id').value });
        } else {
            // FIX: Removed opacity:0.5 from QR div to make it sharp and scannable
            gridHTML += `
                <div class="slot-btn empty" onclick="handleSlotInteraction(${i})">
                    <div class="slot-inner-gold">
                        <div class="slot-header"><div class="slot-num-gold" style="color:#555;">SLOT ${i}</div></div>
                        <div id="qr-slot-${i}" class="bg-white p-2 rounded mt-3 mb-3"></div>
                        <div class="fs-4 text-light fw-bold" style="margin-top:20px;">EMPTY</div>
                        <div style="height:35px;"></div>
                    </div>
                </div>`;
        }
    }
    grid.innerHTML = gridHTML;

    for (let i = 1; i <= max; i++) {
        const item = state.currentGrid[i];
        requestAnimationFrame(() => {
            if (item) generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:" + i, 90);
            else generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:" + i, 80);
        });
    }

    if (unslotted.length > 0) renderUnslotted(unslotted);
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
        const styles = getFilamentStyle(item.color, item.color_direction || 'longitudinal');

        if (emptyMsg) emptyMsg.style.display = 'none';

        const depositCard = document.createElement('div');
        depositCard.className = "cham-card manage-list-item";
        depositCard.style.cssText = `background:${styles.frame}; border: 2px dashed #fff; cursor: pointer; margin-bottom: 15px;`;
        depositCard.onclick = () => doAssign(locId, item.id, null);

        depositCard.innerHTML = `
            <div class="list-inner-gold" style="background: ${styles.inner}; justify-content: center; align-items: center; flex-direction: column; padding: 15px;">
                <div class="text-pop" style="font-size: 1.5rem; font-weight: 900; color: #fff; text-transform: uppercase;">
                    ⬇️ DEPOSIT HERE
                </div>
                <div id="qr-deposit-trigger" class="bg-white p-2 rounded mb-2 mt-2" style="box-shadow: 0 4px 10px rgba(0,0,0,0.5);"></div>
                
                <div class="text-pop-light" style="color: #fff; margin-top: 5px; font-weight: bold;">
                    #${item.id} - ${item.display}
                </div>
            </div>`;

        list.appendChild(depositCard);
    }
    else {
        if (data.length === 0) {
            if (emptyMsg) emptyMsg.style.display = 'block';
        } else {
            if (emptyMsg) emptyMsg.style.display = 'none';
        }
    }

    // 2. Existing Items
    if (data.length > 0) {
        const grouped = {};
        data.forEach(s => {
            const sLoc = s.location || "Unassigned";
            if (!grouped[sLoc]) grouped[sLoc] = [];
            grouped[sLoc].push(s);
        });

        const gKeys = Object.keys(grouped);
        // Ensure the root parent location comes first
        gKeys.sort((a,b) => {
            if (a.toLowerCase() === locId.toLowerCase()) return -1;
            if (b.toLowerCase() === locId.toLowerCase()) return 1;
            return a.localeCompare(b);
        });

        const reOrderedData = [];
        let flatIndex = 0;

        const borderColors = ['border-info', 'border-warning', 'border-success', 'border-danger', 'border-primary', 'border-secondary'];

        gKeys.forEach((gLoc, index) => {
            const isFloating = gLoc.toLowerCase() === locId.toLowerCase();
            const hideHeader = gKeys.length === 1 && isFloating;
            
            const groupWrapper = document.createElement('div');
            const bColor = borderColors[index % borderColors.length];
            
            if (!hideHeader) {
                groupWrapper.className = `p-2 mb-3 rounded border border-2 ${bColor} bg-dark`;
                groupWrapper.style.boxShadow = "inset 0 0 10px rgba(0,0,0,0.5)";
                
                const subHead = document.createElement('div');
                if (isFloating) {
                    subHead.className = `d-flex justify-content-between align-items-center border-bottom border-2 pb-2 mb-2 ${bColor}`;
                    subHead.innerHTML = `
                        <div class="d-flex align-items-center">
                            <span class="btn btn-sm btn-outline-light px-2 py-0 border-0 fs-5 me-2" onclick="this.parentElement.parentElement.nextElementSibling.classList.toggle('d-none'); this.innerText = this.innerText === '-' ? '+' : '-';">-</span>
                            <h5 class="text-light m-0 fw-bold" style="font-size:1.1rem;">☁️ Loose / Floating</h5>
                        </div>`;
                } else {
                    subHead.className = `d-flex justify-content-between align-items-center border-bottom border-2 pb-2 mb-2 ${bColor}`;
                    const isPrinter = gLoc.includes('PRINTER') || gLoc.includes('CORE') || gLoc.includes('XL') || gLoc.includes('MK');
                    const icon = isPrinter ? '🖨️' : '📦';
                    subHead.innerHTML = `
                         <div class="d-flex align-items-center">
                              <span class="btn btn-sm btn-outline-light px-2 py-0 border-0 fs-5 me-2" onclick="this.parentElement.parentElement.nextElementSibling.classList.toggle('d-none'); this.innerText = this.innerText === '-' ? '+' : '-';">-</span>
                              <h5 class="text-info m-0 fw-bold" style="font-size:1.1rem;">${icon} <span class="text-white">${gLoc}</span></h5>
                         </div>
                         <button class="btn btn-sm btn-outline-info py-0 px-2 fw-bold" onclick="openManage('${gLoc}')">Manage / View</button>`;
                }
                groupWrapper.appendChild(subHead);
            }
            
            const itemsContainer = document.createElement('div');
            itemsContainer.className = "d-flex flex-column gap-2 mt-2";

            grouped[gLoc].forEach(s => {
                reOrderedData.push(s);
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = renderBadgeHTML(s, flatIndex, locId);
                const el = tempDiv.firstElementChild;
                const btnLabel = el.querySelector('.js-btn-label');
                if (btnLabel) {
                    btnLabel.addEventListener('click', (e) => {
                        e.stopPropagation();
                        window.addToQueue({ id: s.id, type: 'spool', display: s.display });
                    });
                }
                itemsContainer.appendChild(el);
                flatIndex++;
            });
            
            if (!hideHeader) {
                groupWrapper.appendChild(itemsContainer);
                list.appendChild(groupWrapper);
            } else {
                // If it's just a single flat root location, just append items directly to avoid empty bounding box
                itemsContainer.childNodes.forEach(child => list.appendChild(child.cloneNode(true)));
            }
        });

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                reOrderedData.forEach((s, i) => renderBadgeQRs(s, i));
                generateSafeQR('qr-eject-all-list', 'CMD:EJECTALL', 56);

                if (document.getElementById('qr-deposit-trigger')) {
                    const safeId = String(locId).replace(/['"]/g, '');
                    generateSafeQR('qr-deposit-trigger', 'LOC:' + safeId, 85);
                }
            });
        });
    } else {
        requestAnimationFrame(() => {
            if (document.getElementById('qr-deposit-trigger')) {
                const safeId = String(locId).replace(/['"]/g, '');
                generateSafeQR('qr-deposit-trigger', 'LOC:' + safeId, 85);
            }
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
    items.forEach((s, i) => {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = renderBadgeHTML(s, i, document.getElementById('manage-loc-id').value);
        const el = tempDiv.firstElementChild;
        const btnLabel = el.querySelector('.js-btn-label');
        if (btnLabel) {
            btnLabel.addEventListener('click', (e) => {
                e.stopPropagation();
                window.addToQueue({ id: s.id, type: 'spool', display: s.display });
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
            items.forEach((s, i) => renderBadgeQRs(s, i));
            generateSafeQR("qr-eject-all", "CMD:EJECTALL", 65);
        });
    });
};

const renderBadgeHTML = (s, i, locId) => {
    return window.SpoolCardBuilder.buildCard(s, 'loc_list', { locId: locId, index: i });
};

const renderBadgeQRs = (s, i) => {
    generateSafeQR(`qr-pick-${i}`, "ID:" + s.id, 70);
    generateSafeQR(`qr-print-${i}`, "CMD:PRINT:" + s.id, 70);
    generateSafeQR(`qr-trash-${i}`, "CMD:TRASH:" + s.id, 70);
};

// --- INTERACTION ---
window.handleSlotInteraction = (slot) => {
    const locId = document.getElementById('manage-loc-id').value, item = state.currentGrid[slot];
    if (state.heldSpools.length > 0) {
        const newId = state.heldSpools[0].id;
        if (item) {
            promptAction("Slot Occupied", `Swap/Overwrite Slot ${slot}?`, [
                {
                    label: "Swap", action: () => {
                        let isFromBuf = true;
                        state.heldSpools.shift();
                        state.heldSpools.push({ id: item.id, display: item.display, color: item.color });
                        if (window.renderBuffer) window.renderBuffer();
                        renderManagerNav();
                        doAssign(locId, newId, slot, isFromBuf);
                    }
                },
                {
                    label: "Overwrite", action: () => {
                        let isFromBuf = true;
                        state.heldSpools.shift();
                        if (window.renderBuffer) window.renderBuffer();
                        renderManagerNav();
                        doAssign(locId, newId, slot, isFromBuf);
                    }
                },
                { label: "Cancel", action: () => { closeModal('actionModal'); } }
            ]);
        } else {
            let isFromBuf = true;
            state.heldSpools.shift();
            if (window.renderBuffer) window.renderBuffer();
            renderManagerNav();
            doAssign(locId, newId, slot, isFromBuf);
        }
    } else if (item) {
        promptAction("Slot Action", `Manage ${item.display}`, [
            {
                label: "✋ Pick Up", action: () => {
                    state.heldSpools.unshift({ id: item.id, display: item.display, color: item.color });
                    if (window.renderBuffer) window.renderBuffer();
                    renderManagerNav();
                    closeModal('actionModal');
                }
            },
            { label: "🗑️ Eject", action: () => { doEject(item.id, locId, false); } },
            { label: "🖨️ Details", action: () => { openSpoolDetails(item.id); } }
        ]);
    }
};

window.doAssign = (loc, spool, slot, isFromBufferFlag = null) => {
    setProcessing(true);

    // FIX: 0-based index correction for MMU/CORE slots
    let finalSlot = slot;
    if (slot !== null) {
        const locObj = state.allLocations.find(l => l.LocationID === loc);
        // If Type is 'MMU Slot', we assume backend expects 0-based indexing (0..N-1)
        // Frontend grid is 1-based (1..N). So we subtract 1.
        if (locObj && locObj.Type === 'MMU Slot') {
            finalSlot = parseInt(slot) - 1;
        }
    }

    const spoolIdStr = String(spool).replace("ID:", "");
    let isFromBuffer = isFromBufferFlag !== null ? isFromBufferFlag : false;
    if (isFromBufferFlag === null) {
        if (state.heldSpools.findIndex(s => String(s.id) === spoolIdStr) > -1) {
            isFromBuffer = true;
        }
    }

    if (isFromBuffer) {
        const spoolObj = state.heldSpools.find(s => String(s.id) === spoolIdStr);
        if (spoolObj && (spoolObj.archived === true || String(spoolObj.archived).toLowerCase() === 'true')) {
            showToast("Cannot assign an ARCHIVED spool to a location!", "error");
            setProcessing(false);
            return;
        }
    }

    fetch('/api/manage_contents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'add', location: loc, spool_id: "ID:" + spool, slot: finalSlot, origin: isFromBuffer ? 'buffer' : '' }) })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (res.status === 'success') {
                showToast("Assigned");

                // --- FIX: Remove the assigned spool from buffer ---
                const bufIdx = state.heldSpools.findIndex(s => String(s.id) === spoolIdStr);
                if (bufIdx > -1) {
                    state.heldSpools.splice(bufIdx, 1);
                    if (window.renderBuffer) window.renderBuffer();
                }

                if (window.fetchLocations) window.fetchLocations();
                refreshManageView(loc);
            }
            else showToast(res.msg, 'error');
        })
        .catch(() => setProcessing(false));
};

window.ejectSpool = (sid, loc, pickup) => {
    if (pickup) {
        fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: "ID:" + sid, source: 'keyboard' }) })
            .then(r => r.json())
            .then(res => {
                if (res.type === 'spool') {
                    if (state.heldSpools.some(s => s.id === res.id)) showToast("In Buffer");
                    else {
                        state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color });
                        if (window.renderBuffer) window.renderBuffer();
                        renderManagerNav();
                    }
                }
            });
    } else {
        if (loc !== "Scan") requestConfirmation(`Eject spool #${sid}?`, () => doEject(sid, loc));
        else doEject(sid, loc);
    }
};

window.doEject = (sid, loc, isConfirmed = false) => {
    setProcessing(true);
    fetch('/api/manage_contents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'remove', location: loc, spool_id: sid, confirmed: isConfirmed }) })
        .then(r => r.json())
        .then((res) => {
            setProcessing(false);
            
            if (res.require_confirm) {
                requestConfirmation(res.msg || `True Unassign spool #${sid}? It is currently floating in a room.`, () => {
                    window.doEject(sid, loc, true);
                });
                return;
            }
            if (!res.success) {
                showToast(res.msg || "Failed to eject spool", "error");
                return;
            }
            
            showToast("Ejected");
            if (loc !== "Scan") {
                // [ALEX FIX] Force a re-render by clearing the hash. 
                // This ensures the UI updates to "Empty" even if the API data is cached/similar.
                state.lastLocRenderHash = null;
                if (window.fetchLocations) window.fetchLocations();
                refreshManageView(loc);
            }
        })
        .catch(() => setProcessing(false));
};

window.manualAddSpool = () => {
    const val = document.getElementById('manual-spool-id').value.trim();
    if (!val) return;
    setProcessing(true);
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: val, source: 'keyboard' }) })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            document.getElementById('manual-spool-id').value = "";
            document.getElementById('manual-spool-id').focus();
            if (res.type === 'spool') {
                if (state.heldSpools.some(s => s.id === res.id)) showToast("Already in Buffer", "warning");
                else {
                    state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color });
                    if (window.renderBuffer) window.renderBuffer();
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
    fetch('/api/manage_contents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'clear_location', location: loc }) })
        .then(r => r.json())
        .then(() => { setProcessing(false); if(window.fetchLocations) window.fetchLocations(); refreshManageView(loc); showToast("Cleared!"); });
});

window.printCurrentLocationLabel = () => {
    const locId = document.getElementById('manage-loc-id').value;
    if (!locId) return;
    window.addToQueue({ id: locId, type: 'location', display: `Location: ${locId}` });
};

window.openEdit = (id) => {
    const i = state.allLocations.find(l => l.LocationID == id);
    if (i) {
        modals.locMgrModal.hide();
        document.getElementById('edit-original-id').value = id;
        document.getElementById('edit-id').value = id;
        document.getElementById('edit-name').value = i.Name;
        document.getElementById('edit-type').value = i.Type;
        document.getElementById('edit-max').value = i['Max Spools'];
        modals.locModal.show();
    }
};

window.closeEdit = () => { modals.locModal.hide(); modals.locMgrModal.show(); };

window.saveLocation = () => {
    fetch('/api/locations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            old_id: document.getElementById('edit-original-id').value,
            new_data: {
                LocationID: document.getElementById('edit-id').value,
                Name: document.getElementById('edit-name').value,
                Type: document.getElementById('edit-type').value,
                "Max Spools": document.getElementById('edit-max').value
            }
        })
    })
        .then(() => { modals.locModal.hide(); modals.locMgrModal.show(); fetchLocations(); });
};

window.openAddModal = () => {
    modals.locMgrModal.hide();
    document.getElementById('edit-original-id').value = "";
    document.getElementById('edit-id').value = "";
    document.getElementById('edit-name').value = "";
    document.getElementById('edit-max').value = "1";
    modals.locModal.show();
};

window.deleteLoc = (id) => requestConfirmation(`Delete ${id}?`, () => fetch(`/api/locations?id=${id}`, { method: 'DELETE' }).then(fetchLocations));

