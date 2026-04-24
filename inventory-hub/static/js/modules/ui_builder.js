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
                const brand = d.brand || "Generic";
        const material = d.material || "PLA";
        const name = d.color_name || (item.display || "").replace(/#\d+/, '').trim();
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
        const archivedBadgeHTML = isArchived ? `<span class="badge text-bg-danger px-1 text-pop fcc-archived-badge">📦 ARCHIVED</span>` : '';

        // Core visual styles
        let styles;
        try {
            styles = getFilamentStyle(item.color, item.color_direction || 'longitudinal');
        } catch (e) {
            styles = { frame: '#' + (item.color || '555555'), inner: `rgba(0,0,0,0.6)`, border: '1px solid #333' };
        }

        // Setup outer container wrapping and specific interaction overrides (clicks / classes)
        let outerClasses = `fcc-spool-card mb-2 `;
        let actionTarget = '';
        let wrapperStyle = `background: ${styles.frame};`;
        
        let customInnerBg = `background: ${styles.inner};`;
        if (mode === 'search_result' || mode === 'loc_grid' || mode === 'loc_list' || mode === 'search' || mode === 'buffer') {
            // Flow the styles.frame background dynamically across the interior for rich inner gradients, stripping the harsh glossy halo
            customInnerBg = `background: linear-gradient(to bottom, rgba(30,30,30,0.95) 0%, rgba(5,5,5,0.1) 100%), ${styles.frame}; border-radius: 6px; padding: 0.5rem;`;
        }
        
        // Hazard striping & layout tweaks for states (GHOST / DEPLOYED)
        if (item.is_ghost) {
            outerClasses += 'is-ghost ';
            // Add hazard stripes for ghost items (Stacked strictly ON TOP of the inner glow gradient)
            customInnerBg = `border-top: 1px solid rgba(255,255,255,0.2); background: repeating-linear-gradient(45deg, rgba(0,0,0,0.8), rgba(0,0,0,0.8) 15px, rgba(0,0,0,0.3) 15px, rgba(0,0,0,0.3) 30px), linear-gradient(to bottom, rgba(30,30,30,0.95) 0%, rgba(5,5,5,0.1) 100%), ${styles.frame}; border-radius: 6px; box-shadow: inset 0 0 0 1px ${styles.frame} !important; padding: 0.5rem; background-size: cover;`;
        }

        // --- CONTEXT: ACTION BINDINGS & CLASSES ---
        let navActionsHTML = '';
        let locBadgeHTML = '';
        let row4FooterHTML = '';



        if (mode === 'search') {
            if (options.callbackFn) {
                // Return selection
                actionTarget = `${options.callbackFn}(${item.id}, '${item.type}')`;
            } else {
                if (isFil) actionTarget = `openFilamentDetails(${item.id})`;
                else if (window.processScan) actionTarget = `processScan('ID:${item.id}', 'search')`;
                else actionTarget = `openSpoolDetails(${item.id})`;
                
                // needs_label_print is surfaced from format_spool_display's details block.
                // Only render the ✅ when we have an explicit false — missing details
                // means we can't be sure, so stay quiet rather than over-promising.
                const labelFlagKnown = item.details && Object.prototype.hasOwnProperty.call(item.details, 'needs_label_print');
                const labelConfirmed = labelFlagKnown && item.details.needs_label_print === false;
                const labelStateIcon = !isFil && labelConfirmed
                    ? `<div class="fcc-card-label-ok" style="color:#33d17a; font-size:1.05rem; line-height:1; padding:2px 4px;" title="Label confirmed printed">✅</div>`
                    : '';

                // Add top-right fast-actions
                navActionsHTML = `
                    <div class="d-flex gap-3 align-items-center" style="z-index: 10; margin-right: 5px;">
                        ${!isFil && window.processScan ? `<div class="fcc-card-action-btn" onclick="event.stopPropagation(); processScan('ID:${item.id}', 'search')" title="Add to Buffer/Manage">📥</div>` : ''}
                        <div class="fcc-card-action-btn" onclick="event.stopPropagation(); ${isFil ? `openFilamentDetails(${item.id})` : `openSpoolDetails(${item.id})`}" title="View Details">🔍</div>
                        ${!isFil ? `<div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.openEditWizard(${item.id});" title="Edit Spool">✏️</div>` : ''}
                        ${!isFil && window.addToQueue ? `<div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');" title="Add to Print Queue">🖨️</div>` : ''}
                        ${labelStateIcon}
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
            // Unslotted items: primary card-body click = Pick Up (adds to buffer). Details stays on the 🔍 button.
            actionTarget = `ejectSpool(${item.id}, '${locId}', true)`;

            const printHoverClick = window.addToQueue ? `event.stopPropagation(); window.addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');` : '';
            
            // Add top-right fast-actions (Always attached for both ghosts and slotted array)
            navActionsHTML = `
                <div class="d-flex gap-3 align-items-center" style="z-index: 10; margin-right: 5px;">
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); openSpoolDetails(${item.id})" title="View Details">🔍</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); typeof openEditWizard !== 'undefined' && openEditWizard(${item.id});" title="Edit Spool">✏️</div>
                    <div class="fcc-card-action-btn" onclick="${printHoverClick}" title="Add to Print Queue">🖨️</div>
                </div>
            `;

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
                            <div class="badge-btn-gold btn-pick-bg px-4 fcc-btn-return" style="font-size: 1.2rem; border-radius: 6px;">↩️ RETURN SPOOL</div>
                        </div>
                    </div>`;
            } else {
                // Normal slotted item in List View

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
            
            const printHoverClick = typeof addToQueue !== 'undefined' ? `event.stopPropagation(); addToQueue({ id: ${item.id}, type: 'spool', display: '${safeDisplay}' }); showToast('Added to Print Queue');` : '';
            
            if (item.is_ghost) {
                // Small variant of deployed block (Return block)
                return `
                <div class="${outerClasses}" data-spool-id="${item.id}" style="${wrapperStyle} cursor:pointer;" onclick="${actionTarget}">
                    <div class="slot-inner-gold pt-2 pb-2" style="${customInnerBg}">
                        <div class="d-flex justify-content-between align-items-center w-100 px-1 mb-1">
                            <div class="slot-num-gold" style="font-size:0.9rem; color:#ccc;">SLOT ${options.slotNum}</div>
                            <div class="badge bg-warning text-dark">DEPLOYED</div>
                        </div>
                        
                        <div class="text-center mb-1 w-100">
                            <div style="font-size:0.8rem; color:#ccc; background: rgba(0,0,0,0.7); border-radius: 4px; display: inline-block; padding: 2px 6px;">CURRENTLY AT:</div>
                            <div class="text-pop" style="font-size:1.1rem; font-weight:900; color:#fff;">${item.deployed_to || "Unknown"}</div>
                        </div>
                        
                        <div class="slot-info-gold text-center w-100 mb-2 mt-1" style="background: rgba(0,0,0,0.7); border-radius: 5px; padding: 5px; border: 1px solid #444; cursor:pointer;" onclick="event.stopPropagation(); openSpoolDetails(${item.id})">
                            <div class="text-line-1" style="color: #aaa; font-size:0.9rem;">${info.line1} <span ${!isFil ? `style="float:right; color:#ddd; font-weight:bold; font-size:0.95rem; cursor:pointer;" onclick="event.stopPropagation(); if(window.openQuickWeigh) window.openQuickWeigh(${item.id})"` : `style="float:right; color:#ddd; font-weight:bold; font-size:0.95rem;"`}>${info.line4 ? '⚖️ ' + info.line4 : ''}</span></div>
                            <div class="text-line-2 text-pop" style="color:#fff; font-weight:bold; font-size:1.0rem;">${info.line2}</div>
                            <div class="text-line-3 text-pop" style="font-weight:bold; color: #fff; font-size:0.95rem;">${info.line3}</div>
                        </div>
                        
                        <div class="d-flex justify-content-around gap-1 mt-2 w-100 pt-2 border-top" style="border-color: rgba(255,255,255,0.2) !important;">
                            <div class="fcc-card-action-btn js-btn-pick" onclick="event.stopPropagation(); doAssign('${locId}', ${item.id}, ${options.slotNum})" title="Return Spool">↩️</div>
                            <div class="fcc-card-action-btn" onclick="event.stopPropagation(); openSpoolDetails(${item.id})" title="View Details">🔍</div>
                            <div class="fcc-card-action-btn" onclick="event.stopPropagation(); typeof openEditWizard !== 'undefined' && openEditWizard(${item.id});" title="Edit Spool">✏️</div>
                            <div class="fcc-card-action-btn" onclick="${printHoverClick}" title="Add to Print Queue">🖨️</div>
                            <div class="fcc-card-action-btn" onclick="event.stopPropagation(); ejectSpool(${item.id}, '${locId}', false)" title="Eject Spool">⏏️</div>
                        </div>
                    </div>
                </div>`;
            } else {
                return `
                <div class="${outerClasses}" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                    <div class="slot-inner-gold" style="${customInnerBg}">
                        <div class="d-flex justify-content-between align-items-center w-100 mb-1 px-1">
                            <div class="slot-num-gold" style="font-size:0.95rem;">SLOT ${options.slotNum}</div>
                            <div ${!isFil ? `style="color:#ddd; font-weight:bold; font-size:0.95rem; cursor:pointer;" onclick="event.stopPropagation(); if(window.openQuickWeigh) window.openQuickWeigh(${item.id})"` : `style="color:#ddd; font-weight:bold; font-size:0.95rem;"`}>${info.line4 ? '⚖️ ' + info.line4 : ''}</div>
                        </div>
                        
                        <div id="qr-slot-${options.slotNum}" class="bg-white p-1 rounded mb-2" style="border: 3px solid white;"></div>
                        
                        <div class="slot-info-gold w-100" style="cursor:pointer;" onclick="event.stopPropagation(); openSpoolDetails(${item.id})">
                            <div class="text-line-1" style="font-size:0.9rem;">${info.line1}</div>
                            <div class="text-line-2 text-pop" style="color:#fff; font-weight:bold; font-size:1.0rem;">${info.line2}</div>
                            <div class="text-line-3" style="font-size:0.95rem;">${info.line3}</div>
                        </div>
                        
                        <div class="d-flex justify-content-around gap-1 mt-2 w-100 pt-2 border-top" style="border-color: rgba(255,255,255,0.2) !important;">
                            <div class="fcc-card-action-btn js-btn-pick" onclick="event.stopPropagation(); ejectSpool(${item.id}, '${locId}', true)" title="Pick Up Spool">✋</div>
                            <div class="fcc-card-action-btn" onclick="event.stopPropagation(); openSpoolDetails(${item.id})" title="View Details">🔍</div>
                            <div class="fcc-card-action-btn" onclick="event.stopPropagation(); typeof openEditWizard !== 'undefined' && openEditWizard(${item.id});" title="Edit Spool">✏️</div>
                            <div class="fcc-card-action-btn" onclick="${printHoverClick}" title="Add to Print Queue">🖨️</div>
                            <div class="fcc-card-action-btn" onclick="event.stopPropagation(); ejectSpool(${item.id}, '${locId}', false)" title="Eject Spool">⏏️</div>
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
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); openSpoolDetails(${item.id})" title="View Details">🔍</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); typeof openEditWizard !== 'undefined' && openEditWizard(${item.id});" title="Edit Spool">✏️</div>
                    <div class="fcc-card-action-btn" onclick="${printHoverClick}" title="Add to Print Queue">🖨️</div>
                </div>
                <div class="d-flex align-items-center gap-2 ms-2 ps-2 border-start border-secondary">
                    <div id="qr-buf-${i}" class="bg-white p-1 rounded d-flex align-items-center justify-content-center" style="min-width: 74px; min-height: 74px;"></div>
                    <div class="fcc-btn-buffer-del" onclick="event.stopPropagation(); typeof removeBufferItem !== 'undefined' && removeBufferItem(${item.id})" title="Drop from Buffer">❌</div>
                </div>
            `;

            // Location badge — mirrors search mode, no SearchEngine offcanvas needed
            if (item.location) {
                const badgeClick = `event.stopPropagation(); if(window.openManage) window.openManage('${item.location}')`;
                if (item.is_ghost) {
                    locBadgeHTML = `<span class="badge bg-warning text-dark loc-badge-hover" onclick="${badgeClick}" style="cursor:pointer; font-size: 1.1rem;" title="Jump to Location">📍 Deployed: ${item.location}${item.slot ? ` (Slot ${item.slot})` : ''}</span>`;
                } else {
                    locBadgeHTML = `<span class="badge bg-info text-dark loc-badge-hover" onclick="${badgeClick}" style="cursor:pointer; font-size: 1.1rem;" title="Jump to Location">📍 ${item.location}</span>`;
                }
            } else {
                locBadgeHTML = `<span class="badge bg-secondary"><i class="bi bi-question-circle"></i> Unassigned</span>`;
            }
            // Simplified Buffer Row Layout (mostly standard 3-row but compressed)
        }
        else if (mode === 'buffer_nav') {
            // Highly specialized Nav item
            outerClasses += 'nav-card ';
            actionTarget = options.navAction || '';
            
            if (options.navDirection === 'prev') {
                return `
                <div class="fcc-spool-card nav-card" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                    <div class="fcc-spool-card-inner nav-inner" style="${customInnerBg} flex-direction: row !important; align-items: center !important;">
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
                <div class="fcc-spool-card nav-card" data-spool-id="${item.id}" style="${wrapperStyle}" onclick="${actionTarget}">
                    <div class="fcc-spool-card-inner nav-inner" style="${customInnerBg} flex-direction: row !important; align-items: center !important; justify-content: flex-end !important;">
                        <div style="text-align:right; margin-right: 15px;">
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
                <div class="fcc-spool-card-inner" style="${customInnerBg}">
                    
                    <!-- Row 1: Top Bar (ID/Badges, Nav Actions) -->
                    <div class="d-flex justify-content-between align-items-center mb-1 w-100">
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                            <div class="fcc-card-id-badge text-pop d-flex align-items-center gap-1 fs-5">
                                <span>${typeIcon}</span><span>#${item.id}</span>
                            </div>
                        </div>
                        <div class="d-flex align-items-center gap-2">
                            ${navActionsHTML}
                        </div>
                    </div>

                    <!-- Row 1.5: Location Badge (Dedicated Row) -->
                    ${locBadgeHTML ? `<div class="d-flex justify-content-start align-items-center mb-1 w-100 ps-1">${locBadgeHTML}</div>` : ''}

                    <!-- Row 2: Properties Stack (Material, Brand, Name) -->
                    <div class="d-flex flex-column justify-content-center text-start mx-0 mb-2 mt-1 w-100 ps-1 flex-grow-1">
                         <div class="fcc-card-material text-white-50 text-pop fw-bold" style="font-size: 0.95rem;">
                            ${item.details ? item.details.material || "PLA" : "PLA"}
                         </div>
                         <div class="fcc-card-brand text-light text-pop fw-bold pb-1" style="font-size: 0.95rem;">
                            ${item.details ? item.details.brand || "Generic" : "Generic"}
                         </div>
                         <div class="fcc-card-title text-pop" style="font-size: 1.25rem;">
                            ${info.line3}
                         </div>
                    </div>

                    <!-- Row 3: Metrics (Weight) -->
                    <div class="d-flex justify-content-between align-items-center mt-auto pt-1 w-100 ps-1">
                         <div class="d-flex flex-column gap-1">
                            ${archivedBadgeHTML}
                            <div class="fcc-subtext">${isFil ? '' : info.line1.includes('Legacy') ? info.line1.split(' ')[1] : ''}</div>
                         </div>
                         <div class="fcc-card-metric text-nowrap js-cmd-weight" ${!isFil ? `style="cursor:pointer;" onclick="event.stopPropagation(); if(window.openQuickWeigh) window.openQuickWeigh(${item.id})"` : ''}>
                            ${isFil ? `🧵 ${item.spools_count !== undefined && item.spools_count !== null ? item.spools_count : 0} Spool(s)` : `⚖️ ${(item.remaining_weight !== undefined && item.remaining_weight !== null ? Math.round(item.remaining_weight) + 'g' : (item.remaining != null && item.remaining !== '---' ? Math.round(item.remaining) + 'g' : '---'))}`}
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
