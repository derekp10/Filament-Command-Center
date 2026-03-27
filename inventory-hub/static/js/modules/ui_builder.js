/**
 * SpoolCardBuilder - Global Unified Component
 * Generates Spool and Filament cards matching the "Search Function Gold Standard".
 * Adaptable to Buffer, Location Managers (List & Grid), and custom contexts.
 */
const SpoolCardBuilder = {

    /**
     * Reusable formatter for rich data extraction.
     */
    getRichInfo(item) {
        const d = item.details || {};
        const legacy = d.external_id ? `[Legacy: ${d.external_id}]` : "";
        const isArch = (item.archived === true || String(item.archived).toLowerCase() === 'true');
        const archivedBadge = isArch ? ` <span class="badge text-bg-danger position-relative ms-1 px-1" style="font-size: 0.65rem; top: -2px;">📦 ARCHIVED</span>` : "";
        const brand = d.brand || "Generic";
        const material = d.material || "PLA";
        const name = (d.color_name || (item.display || "").replace(/#\d+/, '').trim()) + archivedBadge;
        const weight = d.weight ? `[${Math.round(d.weight)}g]` : "";

        return {
            line1: `#${item.id} ${legacy}`,
            line2: `${brand} ${material}`,
            line3: name,
            line4: weight
        };
    },

    /**
     * Builds the unified 3-Row (+ optional 4th action row) HTML structure.
     * @param {Object} item Spool/Filament data object
     * @param {String} mode Context: 'search', 'loc_list', 'loc_grid', 'buffer', 'buffer_nav'
     * @param {Object} options Additional overrides (index, locId, callback, interactiveCursor, etc.)
     */
    buildCard(item, mode = 'search', options = {}) {
        const i = typeof options.index !== 'undefined' ? options.index : Math.floor(Math.random() * 10000);
        const locId = options.locId || '';
        const isFil = item.type === 'filament';
        const typeIcon = isFil ? '🧬' : '🧵';
        const safeDisplay = item.display ? item.display.replace(/"/g, '&quot;').replace(/'/g, '&#39;') : '';
        const info = this.getRichInfo(item);
        // Compute archived badge for Row 3 (weight row, left side)
        const isArchived = (item.archived === true || String(item.archived).toLowerCase() === 'true');
        const archivedBadgeHTML = isArchived ? `<span class="badge text-bg-danger px-2 py-1" style="font-size: 0.8rem; letter-spacing: 0.02em;">📦 ARCHIVED</span>` : '';

        // Core visual styles
        let styles;
        try {
            styles = getFilamentStyle(item.color);
        } catch (e) {
            styles = { frame: '#' + (item.color || '555555'), inner: `rgba(0,0,0,0.6)`, border: '1px solid #333' };
        }

        // Setup outer container wrapping and specific interaction overrides (clicks / classes)
        let outerClasses = 'cham-card mb-2 ';
        let actionTarget = '';
        let wrapperStyle = `background: ${styles.frame}; border: ${styles.border || '1px solid #333'}; cursor:pointer;`;
        
        let customInnerBg = `background: ${styles.inner};`;
        
        // Hazard striping & layout tweaks for Location Manager specific states (GHOST / DEPLOYED)
        if (item.is_ghost) {
            wrapperStyle += ` border: 2px dashed ${styles.frame}; background: #111;`;
            customInnerBg = `background: repeating-linear-gradient(45deg, rgba(0,0,0,0.8), rgba(0,0,0,0.8) 15px, rgba(0,0,0,0.3) 15px, rgba(0,0,0,0.3) 30px), ${styles.frame}; background-size: cover;`;
        }

        // --- CONTEXT: ACTION BINDINGS & CLASSES ---
        let navActionsHTML = '';
        let locBadgeHTML = '';
        let row4FooterHTML = '';

        const btnStyle = "font-size: 1.4rem; cursor:pointer; line-height: 1; transition: transform 0.2s; display: inline-block;";
        const hoverOn = "this.style.transform='scale(1.2)'";
        const hoverOff = "this.style.transform='scale(1)'";

        if (mode === 'search') {
            if (options.callbackFn) {
                // Return selection
                actionTarget = `${options.callbackFn}(${item.id}, '${item.type}')`;
            } else {
                if (isFil) actionTarget = `openFilamentDetails(${item.id})`;
                else if (window.processScan) actionTarget = `processScan('ID:${item.id}', 'search')`;
                else actionTarget = `openSpoolDetails(${item.id})`;
                
                // Add top-right fast-actions
                navActionsHTML = `
                    <div class="d-flex gap-3 align-items-center" style="z-index: 10; margin-right: 5px;">
                        ${!isFil && window.processScan ? `<div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); processScan('ID:${item.id}', 'search')" title="Add to Buffer/Manage">📥</div>` : ''}
                        <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); ${isFil ? `openFilamentDetails(${item.id})` : `openSpoolDetails(${item.id})`}" title="View Details">🔍</div>
                        ${!isFil ? `<div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); window.openEditWizard(${item.id});" title="Edit Spool">✏️</div>` : ''}
                        ${!isFil && window.addToQueue ? `<div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); window.addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');" title="Add to Print Queue">🖨️</div>` : ''}
                    </div>
                `;
            }

            // Standard Location Badge
            if (isFil) {
                locBadgeHTML = `<span class="badge bg-secondary"><i class="bi bi-box"></i> Filament Template</span>`;
                item.remaining = '---'; 
            } else if (item.location) {
                const badgeClick = `event.stopPropagation(); if(window.openManage) { window.openManage('${item.location}'); if(window.SearchEngine && window.SearchEngine.offcanvas){window.SearchEngine.offcanvas.hide();} }`;
                if (item.is_ghost) locBadgeHTML = `<span class="badge bg-warning text-dark loc-badge-hover" onclick="${badgeClick}" style="cursor:pointer; font-size: 1.1rem;" title="Jump to Location">📍 Deployed: ${item.location} (Slot ${item.slot})</span>`;
                else locBadgeHTML = `<span class="badge bg-info text-dark loc-badge-hover" onclick="${badgeClick}" style="cursor:pointer; font-size: 1.1rem;" title="Jump to Location">📍 ${item.location}</span>`;
            } else {
                locBadgeHTML = `<span class="badge bg-secondary"><i class="bi bi-question-circle"></i> Unassigned</span>`;
            }
        } 
        else if (mode === 'loc_list') {
            outerClasses += 'manage-list-item js-spool-card'; // Add classes needed by Location Manager tests/logic
            wrapperStyle += ` margin-bottom: 10px;`;
            actionTarget = `openSpoolDetails(${item.id})`;

            // Location manager list doesn't strictly need the location badge on every item since we are IN the location.
            if (item.is_ghost) {
                locBadgeHTML = `
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge bg-warning text-dark">DEPLOYED</span>
                        <div class="text-white" style="font-size:0.9rem; background: rgba(0,0,0,0.7); padding: 2px 6px; border-radius: 4px;">
                            <span style="color:#aaa;">Currently at:</span> <strong style="color:#fff;">${item.deployed_to || "Unknown"}</strong>
                        </div>
                    </div>`;
                
                // For deployed items, we swap out the bottom action row completely for a thick RETURN button overlay.
                row4FooterHTML = `
                    <div class="d-flex justify-content-center mt-3 pt-3 border-top border-secondary">
                        <div class="action-badge" style="flex: 0 0 auto; height: fit-content; width: auto; margin: auto;" onclick="event.stopPropagation(); doAssign('${locId}', ${item.id}, '${item.slot || ''}')">
                            <div class="badge-btn-gold btn-pick-bg px-4" style="background: #ffc107; color:#000; box-shadow: 0 4px 6px rgba(0,0,0,0.5); font-size: 1.2rem; font-weight: bold; border-radius: 6px;">↩️ RETURN SPOOL</div>
                        </div>
                    </div>`;
            } else {
                // Normal slotted item in List View
                const printHoverClick = window.addToQueue ? `event.stopPropagation(); window.addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');` : '';
                
                // Add top-right fast-actions (Keep Edit & View Details)
                navActionsHTML = `
                    <div class="d-flex gap-3 align-items-center" style="z-index: 10; margin-right: 5px;">
                        <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); openSpoolDetails(${item.id})" title="View Details">🔍</div>
                        <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); window.openEditWizard(${item.id});" title="Edit Spool">✏️</div>
                        <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="${printHoverClick}" title="Add to Print Queue">🖨️</div>
                    </div>
                `;

                // Add Row 4 for Physical QR scanning + large button interactions.
                row4FooterHTML = `
                    <div class="d-flex justify-content-around flex-wrap mt-2 pt-2 border-top border-secondary" style="background: rgba(0,0,0,0.2); border-radius: 0 0 6px 6px;">
                        <div class="action-badge mb-1" onclick="event.stopPropagation(); ejectSpool(${item.id}, '${locId}', true)">
                            <div id="qr-pick-${i}" class="badge-qr"></div>
                            <div class="badge-btn-gold btn-pick-bg pb-1 px-2 rounded" style="font-size: 0.9rem;">✋ PICK</div>
                        </div>
                        <div class="action-badge mb-1 js-btn-label" onclick="${printHoverClick}">
                            <div id="qr-print-${i}" class="badge-qr"></div>
                            <div class="badge-btn-gold btn-print-bg pb-1 px-2 rounded" style="font-size: 0.9rem;">🖨️ LABEL</div>
                        </div>
                        <div class="action-badge mb-1" onclick="event.stopPropagation(); ejectSpool(${item.id}, '${locId}', false)">
                            <div id="qr-trash-${i}" class="badge-qr"></div>
                            <div class="badge-btn-gold btn-trash-bg pb-1 px-2 rounded" style="font-size: 0.9rem;">${(!item.slot || locId === 'unassigned') ? '⏏️ EJECT' : '🗑️ TRASH'}</div>
                        </div>
                    </div>
                `;
            }
        } 
        else if (mode === 'loc_grid') {
            // Loc Grid is significantly smaller and more square. We adapt it to a stacked block but share aesthetics.
            outerClasses += 'slot-btn full ';
            actionTarget = `handleSlotInteraction(${options.slotNum})`;
            
            if (item.is_ghost) {
                // Small variant of deployed block (Return block)
                wrapperStyle = `background: #111; border: 3px dashed ${styles.frame}; cursor:pointer;`;
                return `
                <div class="${outerClasses}" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                    <div class="slot-inner-gold pt-1" style="${customInnerBg}">
                        <div class="d-flex flex-column align-items-center mb-1">
                            <div class="slot-num-gold" style="color:#ccc;">SLOT ${options.slotNum}</div>
                            <div class="badge bg-warning text-dark mt-1">DEPLOYED</div>
                        </div>
                        <div class="text-center mt-2 mb-2">
                            <div style="font-size:0.8rem; color:#ccc; background: rgba(0,0,0,0.7); border-radius: 4px; display: inline-block; padding: 2px 6px;">CURRENTLY AT:</div>
                            <div class="text-pop" style="font-size:1.1rem; font-weight:900; color:#fff;">${item.deployed_to || "Unknown"}</div>
                        </div>
                        <div class="slot-info-gold text-center" style="background: rgba(0,0,0,0.7); border-radius: 5px; padding: 5px; margin: 0 5px; border: 1px solid #444;">
                            <div class="text-line-1" style="color: #aaa;">${info.line1}</div>
                            <div class="text-line-3" style="font-weight:bold; color: #fff;">${info.line3}</div>
                        </div>
                        <div class="d-grid gap-2 mt-auto pb-2 px-2 pt-2">
                            <button class="btn btn-sm" style="background-color: #ffc107; color: #000; font-weight: bold; border: 2px solid #b38600; box-shadow: 0 4px 6px rgba(0,0,0,0.5);" onclick="event.stopPropagation(); doAssign('${locId}', ${item.id}, ${options.slotNum})">
                                ↩️ RETURN
                            </button>
                        </div>
                    </div>
                </div>`;
            } else {
                return `
                <div class="${outerClasses}" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                    <div class="slot-inner-gold" style="${customInnerBg}">
                        <div class="slot-header"><div class="slot-num-gold">SLOT ${options.slotNum}</div></div>
                        <div id="qr-slot-${options.slotNum}" class="bg-white p-1 rounded" style="border: 3px solid white;"></div>
                        <div class="slot-info-gold" style="cursor:pointer;" onclick="event.stopPropagation(); openSpoolDetails(${item.id})">
                            <div class="text-line-1">${info.line1}</div>
                            <div class="text-line-2 text-pop" style="color:#fff; font-weight:bold;">${info.line2}</div>
                            <div class="text-line-3">${info.line3}</div>
                            <div class="text-line-4">${info.line4}</div>
                        </div>
                        <div class="btn-label-compact js-btn-label" onclick="event.stopPropagation(); window.addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');">
                            <span style="font-size:1.2rem;">📷</span> LABEL
                        </div>
                    </div>
                </div>`;
            }
        }
        else if (mode === 'buffer') {
            outerClasses += `buffer-item ${options.isFirst ? 'active-item' : ''} `;
            actionTarget = `openSpoolDetails(${item.id})`;
            
            const printHoverClick = typeof addToQueue !== 'undefined' ? `event.stopPropagation(); addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');` : '';
            
            navActionsHTML = `
                <div class="d-flex gap-3 align-items-center" style="z-index: 10; margin-right: 5px;">
                    <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); openSpoolDetails(${item.id})" title="View Details">🔍</div>
                    <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="event.stopPropagation(); typeof openEditWizard !== 'undefined' && openEditWizard(${item.id});" title="Edit Spool">✏️</div>
                    <div style="${btnStyle}" onmouseover="${hoverOn}" onmouseout="${hoverOff}" onclick="${printHoverClick}" title="Add to Print Queue">🖨️</div>
                </div>
                <div class="d-flex align-items-center gap-2 ms-2 ps-2 border-start border-secondary">
                    <div id="qr-buf-${i}" class="bg-white p-1 rounded d-flex align-items-center justify-content-center" style="min-width: 74px; min-height: 74px;"></div>
                    <div style="font-size: 1.8rem; cursor:pointer; color: #ff4444;" onmouseover="this.style.color='#fff'" onmouseout="this.style.color='#ff4444'" onclick="event.stopPropagation(); typeof removeBufferItem !== 'undefined' && removeBufferItem(${item.id})" title="Drop from Buffer">❌</div>
                </div>
            `;
            // Simplified Buffer Row Layout (mostly standard 3-row but compressed)
        }
        else if (mode === 'buffer_nav') {
            // Highly specialized Nav item
            outerClasses += 'nav-card ';
            actionTarget = options.navAction || '';
            
            if (options.navDirection === 'prev') {
                return `
                <div class="cham-card nav-card" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                    <div class="cham-body nav-inner" style="${customInnerBg}">
                        <div id="qr-nav-prev" class="nav-qr"></div>
                        <div>
                            <div class="nav-label text-pop" style="color: #fff; font-weight: 900;">◀ PREV</div>
                            <div class="nav-name text-pop" style="color: #fff; font-weight: 800;">
                                ${(item.display_short || item.display).replace(/^#\d+\s*/, '')}
                            </div>
                        </div>
                    </div>
                </div>`;
            } else {
                return `
                <div class="cham-card nav-card" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                    <div class="cham-body nav-inner" style="${customInnerBg}">
                        <div style="text-align:right;">
                            <div class="nav-label text-pop" style="color: #fff; font-weight: 900;">NEXT ▶</div>
                            <div class="nav-name text-pop" style="color: #fff; font-weight: 800;">
                                ${(item.display_short || item.display).replace(/^#\d+\s*/, '')}
                            </div>
                        </div>
                        <div id="qr-nav-next" class="nav-qr"></div>
                    </div>
                </div>`;
            }
        }

        // --- CORE UNIFIED RENDER PROTOCOL (Search, Loc_List, Buffer) ---
        return `
            <div class="${outerClasses}" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                <div class="cham-body p-2" style="${customInnerBg} display: flex; flex-direction: column; align-items: stretch;">
                    
                    <!-- Row 1: Top Bar (ID/Badges, Nav Actions) -->
                    <div class="d-flex justify-content-between align-items-center mb-1 w-100">
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                            <div class="text-pop d-flex align-items-center gap-1 fs-5 shadow-sm" style="font-family:monospace; color:#fff; background: rgba(0,0,0,0.5); padding: 2px 6px; border-radius: 6px;">
                                <span>${typeIcon}</span><span>#${item.id}</span>
                            </div>
                            <div class="text-white-50 ms-1 d-none d-sm-block" style="font-size: 0.9rem; font-weight: bold;">
                                ${info.line2} <!-- Brand & Material -->
                            </div>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            ${locBadgeHTML}
                            ${navActionsHTML}
                        </div>
                    </div>

                    <!-- Row 2: Display Name -->
                    <div class="d-flex justify-content-start text-start my-2 w-100 ps-1 flex-grow-1">
                         <div class="text-pop cham-text" style="font-weight:900; color:#fff; font-size:1.4rem; line-height: 1.2; word-break: break-all; min-height: 1.8rem;">
                            ${item.display_short || item.display}
                         </div>
                    </div>

                    <!-- Row 3: Metrics (Weight) -->
                    <div class="d-flex justify-content-between align-items-center mt-auto pt-1 w-100 ps-1">
                         <div class="d-flex flex-column gap-1">
                            ${archivedBadgeHTML}
                            <div class="text-white-50" style="font-size: 0.85rem;">${isFil ? '' : info.line1.includes('Legacy') ? info.line1.split(' ')[1] : ''}</div>
                         </div>
                         <div class="text-pop text-nowrap js-cmd-weight" style="font-weight:bold; color:#fff; font-size: 1.2rem;">
                            ⚖️ ${isFil ? '---' : (item.remaining_weight !== undefined && item.remaining_weight !== null ? Math.round(item.remaining_weight) + 'g' : (item.remaining || '---'))}
                         </div>
                    </div>

                    <!-- Row 4: Action Footer (Location Manager Specific) -->
                    ${row4FooterHTML}
                </div>
            </div>
        `;
    }
};

window.SpoolCardBuilder = SpoolCardBuilder;
