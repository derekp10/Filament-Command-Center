/* MODULE: DETAILS (Spool & Filament Modals) */
console.log("🚀 Loaded Module: DETAILS");

const openSpoolDetails = (id, silent = false) => {
    if (!silent) setProcessing(true);
    fetch(`/api/spool_details?id=${id}`)
        .then(r => r.json())
        .then(d => {
            if (!silent) setProcessing(false);

            // --- NO WIGGLE CHECK ---
            const contentHash = JSON.stringify(d);
            if (silent && typeof state !== 'undefined' && state.lastSpoolDetailsHash === contentHash) return;
            if (typeof state !== 'undefined') state.lastSpoolDetailsHash = contentHash;
            // -----------------------

            if (!d || !d.id) { showToast("Details Data Missing!", "error"); return; }

            // --- 1. Basic Info ---
            const fil = d.filament || {}; // Safe access

            document.getElementById('detail-id').innerText = d.id;
            const archBadge = document.getElementById('detail-archived-badge');
            if (archBadge) {
                if (d.archived) archBadge.classList.remove('d-none');
                else archBadge.classList.add('d-none');
            }

            let locDisplay = d.location && d.location.trim() !== "" ? d.location : "Unassigned";
            if (locDisplay === "Unassigned" && d.extra?.physical_source) {
                locDisplay = `Deployed: ${d.extra.physical_source.replace(/"/g, '')}`;
            }
            const locBadge = document.getElementById('detail-location-badge');
            if (locBadge) {
                locBadge.innerText = locDisplay;
                if (locDisplay === "Unassigned") {
                    locBadge.className = "badge bg-secondary ms-2 me-1";
                    locBadge.style.cursor = "default";
                    locBadge.onclick = null;
                    locBadge.title = "";
                } else if (locDisplay.startsWith("Deployed:")) {
                    locBadge.className = "badge bg-warning text-dark ms-2 me-1";
                    locBadge.style.cursor = "default";
                    locBadge.onclick = null;
                    locBadge.title = "";
                } else {
                    // It's a normal location, make it clickable
                    locBadge.className = "badge bg-info text-dark ms-2 me-1";
                    locBadge.style.cursor = "pointer";
                    locBadge.title = "View Location Details";
                    locBadge.onclick = () => {
                        if (typeof modals !== 'undefined' && modals.spoolModal) modals.spoolModal.hide();
                        if (window.openManage) window.openManage(d.location);
                    };
                }
            }

            document.getElementById('detail-material').innerText = fil.material || "Unknown";
            document.getElementById('detail-vendor').innerText = fil.vendor?.name || "Unknown";
            document.getElementById('detail-weight').innerText = (fil.weight || 0) + "g";

            const used = d.used_weight !== null ? d.used_weight : 0;
            const rem = d.remaining_weight !== null ? d.remaining_weight : 0;
            document.getElementById('detail-used').innerText = Number(used).toFixed(1) + "g";
            document.getElementById('detail-remaining').innerText = Number(rem).toFixed(1) + "g";

            document.getElementById('detail-color-name').innerText = fil.name || "Unknown";
            document.getElementById('detail-hex').innerText = (fil.color_hex || "").toUpperCase();
            document.getElementById('detail-comment').value = d.comment || "";

            // --- 2. Swatch Logic (Robust V3) ---
            const swatch = document.getElementById('detail-swatch');
            if (swatch) {
                // Priority: Multi-Hex -> Single Hex -> Extra Multi -> Extra Original -> Fallback
                const rawColor = fil.multi_color_hexes
                    || fil.color_hex
                    || fil.extra?.multi_color_hexes
                    || fil.extra?.color_hex
                    || "333";

                const direction = fil.multi_color_direction || fil.extra?.multi_color_direction || 'longitudinal';
                console.log(`🎨 Spool #${d.id} Swatch Color:`, rawColor, "Direction:", direction);

                const styles = getFilamentStyle(rawColor, direction);
                swatch.style.background = styles.isSolid ? styles.base : styles.frame;
                if (styles.border) swatch.style.boxShadow = 'inset 0 0 0 2px #555';
                else swatch.style.boxShadow = '';
            }

            // --- 3. Link Logic ---
            const btnLink = document.getElementById('btn-open-spoolman');
            if (btnLink) {
                if (typeof SPOOLMAN_URL !== 'undefined' && SPOOLMAN_URL) {
                    const baseUrl = SPOOLMAN_URL.endsWith('/') ? SPOOLMAN_URL.slice(0, -1) : SPOOLMAN_URL;
                    btnLink.href = `${baseUrl}/spool/show/${d.id}`;
                } else btnLink.href = `/spool/show/${d.id}`;
            }

            // --- 4. Product Data Link ---
            const prodUrlContainer = document.getElementById('detail-product-url-container');
            const btnProdUrl = document.getElementById('detail-btn-product-url');

            if (prodUrlContainer && btnProdUrl) {
                let url = d.extra?.product_url || fil.extra?.product_url || "";

                // Cleanse the Spoolman JSON string quotes if they exist
                if (url.startsWith('"') && url.endsWith('"')) {
                    url = url.substring(1, url.length - 1);
                }

                if (url && url.startsWith('http')) {
                    btnProdUrl.href = url;
                    prodUrlContainer.classList.remove('d-none');
                } else {
                    prodUrlContainer.classList.add('d-none');
                    btnProdUrl.href = "#";
                }
            }

            // --- 5. Buy More Link (Spool) ---
            const btnBuyMore = document.getElementById('detail-btn-buy-more');
            if (btnBuyMore) {
                let pUrl = d.extra?.purchase_url || fil.extra?.purchase_url || "";
                if (pUrl.startsWith('"') && pUrl.endsWith('"')) pUrl = pUrl.substring(1, pUrl.length - 1);
                
                if (pUrl && pUrl.startsWith('http')) {
                    btnBuyMore.href = pUrl;
                    btnBuyMore.classList.remove('d-none');
                } else if (typeof BUY_MORE_URL_TEMPLATE !== 'undefined' && BUY_MORE_URL_TEMPLATE) {
                    const vendor = encodeURIComponent(fil.vendor?.name || "Generic");
                    const material = encodeURIComponent(fil.material || "PLA");
                    const color = encodeURIComponent(fil.extra?.original_color || fil.name || "");
                    const dynamicUrl = BUY_MORE_URL_TEMPLATE
                        .replace(/\{\{vendor\}\}/g, vendor)
                        .replace(/\{\{material\}\}/g, material)
                        .replace(/\{\{color\}\}/g, color);
                    btnBuyMore.href = dynamicUrl;
                    btnBuyMore.classList.remove('d-none');
                } else {
                    btnBuyMore.classList.add('d-none');
                }
            }

            // --- 6. Swatch Link Action ---
            const btnSwatch = document.getElementById('btn-spool-to-filament');
            if (btnSwatch) {
                if (d.filament) {
                    btnSwatch.onclick = () => { modals.spoolModal.hide(); openFilamentDetails(fil.id); };
                    btnSwatch.style.display = 'inline-block';
                } else btnSwatch.style.display = 'none';
            }

            if (!silent && modals.spoolModal) modals.spoolModal.show();
        })
        .catch(e => { if (!silent) setProcessing(false); console.error(e); showToast("Err: " + (e.message || "Catch Exception"), "error"); });
};

const openFilamentDetails = (fid, silent = false) => {
    if (!silent) setProcessing(true);
    // 1. Fetch Filament Details
    fetch(`/api/filament_details?id=${fid}`)
        .then(r => r.json())
        .then(d => {
            // --- NO WIGGLE CHECK (Info) ---
            const infoHash = JSON.stringify(d);
            let skipInfoRender = false;
            if (silent && typeof state !== 'undefined' && state.lastFilamentInfoHash === infoHash) {
                skipInfoRender = true;
            } else if (typeof state !== 'undefined') {
                state.lastFilamentInfoHash = infoHash;
            }
            // ------------------------------

            if (!d || !d.id) { if (!silent) setProcessing(false); showToast("Filament Data Missing!", "error"); return; }

            if (!skipInfoRender) {
                // --- Populate Basic Details ---
            document.getElementById('fil-detail-id').innerText = d.id;
            document.getElementById('fil-detail-vendor').innerText = d.vendor ? d.vendor.name : "Unknown";
            document.getElementById('fil-detail-material').innerText = d.material || "Unknown";
            document.getElementById('fil-detail-color-name').innerText = d.name || "Unknown";
            document.getElementById('fil-detail-hex').innerText = (d.color_hex || "").toUpperCase();

            document.getElementById('fil-detail-temp-nozzle').innerText = d.settings_extruder_temp ? `${d.settings_extruder_temp}°C` : "--";
            document.getElementById('fil-detail-temp-bed').innerText = d.settings_bed_temp ? `${d.settings_bed_temp}°C` : "--";
            document.getElementById('fil-detail-density').innerText = d.density ? `${d.density} g/cm³` : "--";
            document.getElementById('fil-detail-comment').value = d.comment || "";

            const swatch = document.getElementById('fil-detail-swatch');
            // [ALEX FIX] Gradient Swatch (Smart Field Selection)
            if (swatch) {
                // Check multi_color_hexes first, then fall back to standard color_hex
                const rawColor = d.multi_color_hexes || d.color_hex || "333";

                const direction = d.multi_color_direction || d.extra?.multi_color_direction || 'longitudinal';
                console.log("🎨 Filament Swatch Color:", rawColor, "Direction:", direction); // Debug
                const styles = getFilamentStyle(rawColor, direction);
                swatch.style.background = styles.isSolid ? styles.base : styles.frame;
                if (styles.border) swatch.style.boxShadow = 'inset 0 0 0 2px #555';
                else swatch.style.boxShadow = '';
            }

            // Link to Spoolman
            const btnLink = document.getElementById('btn-fil-open-spoolman');
            if (btnLink) {
                const baseUrl = (typeof SPOOLMAN_URL !== 'undefined' && SPOOLMAN_URL) ? SPOOLMAN_URL : "";
                btnLink.href = baseUrl ? `${baseUrl.replace(/\/$/, "")}/filament/show/${d.id}` : `/filament/show/${d.id}`;
            }

            // --- Buy More Link (Filament) ---
            const btnFilBuyMore = document.getElementById('fil-btn-buy-more');
            if (btnFilBuyMore) {
                let pUrl = d.extra?.purchase_url || "";
                if (pUrl.startsWith('"') && pUrl.endsWith('"')) pUrl = pUrl.substring(1, pUrl.length - 1);
                
                if (pUrl && pUrl.startsWith('http')) {
                    btnFilBuyMore.href = pUrl;
                    btnFilBuyMore.classList.remove('d-none');
                } else if (typeof BUY_MORE_URL_TEMPLATE !== 'undefined' && BUY_MORE_URL_TEMPLATE) {
                    const vendor = encodeURIComponent(d.vendor?.name || "Generic");
                    const material = encodeURIComponent(d.material || "PLA");
                    const color = encodeURIComponent(d.extra?.original_color || d.name || "");
                    const dynamicUrl = BUY_MORE_URL_TEMPLATE
                        .replace(/\{\{vendor\}\}/g, vendor)
                        .replace(/\{\{material\}\}/g, material)
                        .replace(/\{\{color\}\}/g, color);
                    btnFilBuyMore.href = dynamicUrl;
                    btnFilBuyMore.classList.remove('d-none');
                } else {
                    btnFilBuyMore.classList.add('d-none');
                }
            }

                // Action: Queue Swatch Label
                const btnQueueSwatch = document.getElementById('btn-fil-print-action');
                if (btnQueueSwatch) {
                    btnQueueSwatch.onclick = () => {
                        addToQueue({ id: d.id, type: 'filament', display: d.name });
                        showToast('Label added to print queue!', 'success');
                    };
                }

                // Action: New Spool from Filament Wizard
                const btnNewSpool = document.getElementById('btn-fil-new-spool');
                if (btnNewSpool) {
                    btnNewSpool.onclick = () => {
                        if (modals.filamentModal) modals.filamentModal.hide();
                        if (window.openNewSpoolFromFilamentWizard) window.openNewSpoolFromFilamentWizard(d.id);
                    };
                }

                // Edit Filament (direct filament-only edit — no spool coupling)
                const btnEditFil = document.getElementById('btn-fil-edit');
                if (btnEditFil) {
                    btnEditFil.onclick = () => {
                        if (window.openEditFilamentForm) window.openEditFilamentForm(d);
                    };
                }
            }

            // --- NEW: Fetch Associated Spools for this Filament ---
            const listContainer = document.getElementById('fil-spools-list');
            const countBadge = document.getElementById('fil-spool-count');
            const btnQueueAll = document.getElementById('btn-queue-all-spools');
            const btnBackfill = document.getElementById('btn-fil-backfill-weights');
            const backfillCountEl = document.getElementById('btn-fil-backfill-count');

            // Only run if the HTML element exists (safety check)
            if (listContainer) {
                if (!silent) listContainer.innerHTML = "<div class='p-2 text-light text-center small'>Checking inventory...</div>";

                const toggleArchived = document.getElementById('toggle-show-archived');
                const allowArchived = toggleArchived ? toggleArchived.checked : false;

                fetch(`/api/spools_by_filament?id=${fid}&allow_archived=${allowArchived}`)
                    .then(r => r.json())
                    .then(spools => {
                        // --- NO WIGGLE CHECK (Spools) ---
                        const spoolsHash = JSON.stringify(spools);
                        if (silent && typeof state !== 'undefined' && state.lastFilamentSpoolsHash === spoolsHash) {
                            if (!silent) setProcessing(false); 
                            return;
                        }
                        if (typeof state !== 'undefined') state.lastFilamentSpoolsHash = spoolsHash;
                        // --------------------------------

                        if (!silent) setProcessing(false); // Done loading
                        listContainer.innerHTML = "";

                        if (Array.isArray(spools) && spools.length > 0) {
                            if (countBadge) countBadge.innerText = spools.length;

                            // Render List
                            spools.forEach(s => {
                                const remaining = s.remaining_weight ? Math.round(s.remaining_weight) : 0;
                                let location = s.location || "Unassigned";
                                if (location === "Unassigned" && s.extra?.physical_source) {
                                    location = s.extra.physical_source.replace(/"/g, '');
                                }

                                const row = document.createElement('div');
                                row.className = "list-group-item bg-dark text-white border-secondary d-flex justify-content-between align-items-center p-2 small";

                                // Updated Layout with View Details, Add to Buffer, and Queue Buttons
                                row.innerHTML = `
                            <div class="d-flex align-items-center">
                                <span class="text-info fw-bold me-2">ID: ${s.id}</span> 
                                <span class="text-light me-2">|</span> 
                                <span>${remaining}g</span>
                            </div>
                            <div class="d-flex align-items-center">
                                <span class="badge bg-secondary me-2">${location}</span>
                                <button class="btn btn-sm btn-outline-warning py-0 px-2 me-1" 
                                    onclick="if(modals.filamentModal) modals.filamentModal.hide(); openSpoolDetails(${s.id});" 
                                    title="View Spool Details">
                                    🔍
                                </button>
                                <button class="btn btn-sm btn-outline-primary py-0 px-2 me-1" 
                                    onclick="window.openEditWizard(${s.id});" 
                                    title="Edit Spool">
                                    ✏️
                                </button>
                                <button class="btn btn-sm btn-outline-success py-0 px-2 me-1" 
                                    onclick="window.addSpoolToBuffer(${s.id})" 
                                    title="Add to Buffer">
                                    📥
                                </button>
                                <button class="btn btn-sm btn-outline-info py-0 px-2" 
                                    onclick="window.addToQueue({ id: ${s.id}, type: 'spool', display: '${d.name} (ID:${s.id})' }); showToast('Added to Queue');" 
                                    title="Send to Print Queue">
                                    🖨️
                                </button>
                            </div>
                        `;

                                listContainer.appendChild(row);
                            });

                            // Enable "Queue All" Button
                            if (btnQueueAll) {
                                btnQueueAll.style.display = 'block';
                                btnQueueAll.onclick = () => {
                                    let added = 0;
                                    spools.forEach(s => {
                                        // Prevent duplicates
                                        if (!window.labelQueue.find(q => q.id === s.id && q.type === 'spool')) {
                                            window.addToQueue({ id: s.id, type: 'spool', display: `${d.name} (ID:${s.id})` });
                                            added++;
                                        }
                                    });
                                    if (added > 0) {
                                        showToast(`Queued ${added} spools!`);
                                        // Open the queue to confirm, let it stack natively!
                                        window.openQueueModal();
                                    } else {
                                        showToast("All spools already in queue", "info");
                                    }
                                };
                            }

                            // Backfill prompt — surfaces only when this filament has at least one
                            // spool saved with an empty (null / <= 0) spool_weight AND an inheritable
                            // value exists on the filament or its vendor.
                            if (btnBackfill && backfillCountEl) {
                                const zeroSpools = spools.filter(s => {
                                    const w = s.spool_weight;
                                    return w === null || w === undefined || Number(w) <= 0;
                                });
                                const filWt = Number(d.spool_weight);
                                const vendorWt = d.vendor && d.vendor.empty_spool_weight != null
                                    ? Number(d.vendor.empty_spool_weight) : null;
                                const inheritable = (filWt > 0) || (vendorWt != null && vendorWt > 0);
                                if (zeroSpools.length > 0 && inheritable) {
                                    backfillCountEl.innerText = zeroSpools.length;
                                    btnBackfill.style.display = 'block';
                                    btnBackfill.onclick = () => {
                                        btnBackfill.disabled = true;
                                        fetch(`/api/backfill_spool_weights/${d.id}`, { method: 'POST' })
                                            .then(r => r.json().then(j => ({ ok: r.ok, j })))
                                            .then(({ ok, j }) => {
                                                if (ok && j.success) {
                                                    showToast(`Backfilled ${j.updated} spool${j.updated === 1 ? '' : 's'} to ${j.target_weight}g (from ${j.source}).`, 'success');
                                                    if (window.refreshFilamentSpools) window.refreshFilamentSpools();
                                                } else {
                                                    showToast(j.msg || 'Backfill failed.', 'error', 7000);
                                                }
                                            })
                                            .catch(err => {
                                                showToast(`Backfill error: ${err}`, 'error', 7000);
                                            })
                                            .finally(() => { btnBackfill.disabled = false; });
                                    };
                                } else {
                                    btnBackfill.style.display = 'none';
                                }
                            }
                        } else {
                            // No spools found
                            if (countBadge) countBadge.innerText = "0";
                            listContainer.innerHTML = "<div class='p-2 text-light text-center small'>No spools found.</div>";
                            if (btnQueueAll) btnQueueAll.style.display = 'none';
                            if (btnBackfill) btnBackfill.style.display = 'none';
                        }

                        if (!silent && modals.filamentModal) modals.filamentModal.show();
                    })
                    .catch(e => {
                        if (!silent) setProcessing(false);
                        listContainer.innerHTML = "<div class='text-danger small p-2'>Error loading spools</div>";
                        if (!silent && modals.filamentModal) modals.filamentModal.show();
                    });
            } else {
                // If HTML missing, just show modal normally
                if (!silent) setProcessing(false);
                if (!silent && modals.filamentModal) modals.filamentModal.show();
            }
        })
        .catch(e => { if (!silent) setProcessing(false); console.error(e); showToast("Connection/Data Error", "error"); });
};

const quickQueue = (id) => {
    fetch(`/api/spool_details?id=${id}`)
        .then(r => r.json())
        .then(d => {
            if (!d.id) return;
            addToQueue({ id: d.id, type: 'spool', display: d.filament?.name || "Unknown" });
        });
};

// --- SMART SYNC LISTENER ---
document.addEventListener('inventory:sync-pulse', () => {
    // 1. Sync Spool Modal
    const spoolModal = document.getElementById('spoolModal');
    if (spoolModal && spoolModal.classList.contains('show')) {
        const id = document.getElementById('detail-id').innerText;
        if (id) openSpoolDetails(id, true); // Silent Refresh
    }

    // 2. Sync Filament Modal
    const filModal = document.getElementById('filamentModal');
    if (filModal && filModal.classList.contains('show')) {
        const fid = document.getElementById('fil-detail-id').innerText;
        if (fid) openFilamentDetails(fid, true); // Silent Refresh
    }
});

// --- MANUAL LOCATION OVERRIDE ---
window.promptEditLocation = (spoolId, currentLoc) => {
    let defaultLoc = currentLoc || "Unassigned";
    if (defaultLoc.startsWith("Deployed: ")) defaultLoc = defaultLoc.replace("Deployed: ", "");
    if (defaultLoc === "Unassigned") defaultLoc = "";

    fetch('/api/locations')
        .then(r => r.json())
        .then(locs => {
            const validLocs = [{id: "", name: "-- Unassigned --"}];
            if (Array.isArray(locs)) {
                locs.forEach(l => {
                    const type = (l.Type || '').toLowerCase();
                    if (type.includes('mmu') || type.includes('tool') || type.includes('direct load') || type === 'virtual') return;
                    if (l.LocationID === 'Unassigned') return;
                    validLocs.push({id: l.LocationID, name: `${l.Name} (${l.LocationID})`});
                });
            }

            let listHtml = validLocs.map(l => `
                <div class="swal-loc-item p-2 border-bottom border-dark cursor-pointer text-light" data-id="${l.id}" style="transition:0.2s; ${l.id === defaultLoc ? 'background:#444;' : 'background:transparent;'}">
                    ${l.name}
                </div>
            `).join('');

            Swal.fire({
                target: document.getElementById('spoolModal') || document.body,
                title: 'Force Location Override',
                html: `
                    <div class="text-start">
                        <label class="form-label text-warning small mb-1">Search New Location</label>
                        <input type="text" id="swal-override-search" class="form-control bg-dark text-white border-warning mb-2" placeholder="Type to filter..." autocomplete="off">
                        <input type="hidden" id="swal-override-loc" value="${defaultLoc}">
                        <div id="swal-loc-list-container" class="border border-secondary rounded" style="max-height: 200px; overflow-y: auto; background: #111;">
                            ${listHtml}
                        </div>
                        <small class="text-light mt-2 d-block">
                            Bypasses scanning protocols to forcefully move the spool in the database.
                        </small>
                    </div>
                `,
                showCancelButton: true,
                confirmButtonColor: '#ffaa00',
                background: '#1e1e1e',
                color: '#fff',
                confirmButtonText: 'Force Move',
                allowEscapeKey: false,
                allowOutsideClick: false,
                didOpen: () => {
                    const popup = Swal.getPopup();
                    const searchInput = popup.querySelector('#swal-override-search');
                    const hiddenInput = popup.querySelector('#swal-override-loc');
                    const items = popup.querySelectorAll('.swal-loc-item');

                    // Auto-focus the search input
                    searchInput.focus();

                    // Inject kb-active style (scoped to popup, removed on close)
                    const styleTag = document.createElement('style');
                    styleTag.textContent = '.swal-loc-item.kb-active { background: #444 !important; }';
                    popup.appendChild(styleTag);

                    // Keyboard navigation helpers
                    let kbIndex = -1;
                    const getVisibleItems = () => Array.from(items).filter(i => i.style.display !== 'none');
                    const clearKbHighlight = () => {
                        items.forEach(i => i.classList.remove('kb-active'));
                        kbIndex = -1;
                    };
                    const applyKbHighlight = (visibleItems, index) => {
                        items.forEach(i => i.classList.remove('kb-active'));
                        if (index >= 0 && index < visibleItems.length) {
                            visibleItems[index].classList.add('kb-active');
                            const container = popup.querySelector('#swal-loc-list-container');
                            const itemRect = visibleItems[index].getBoundingClientRect();
                            const contRect = container.getBoundingClientRect();
                            if (itemRect.bottom > contRect.bottom) {
                                container.scrollTop += (itemRect.bottom - contRect.bottom);
                            } else if (itemRect.top < contRect.top) {
                                container.scrollTop -= (contRect.top - itemRect.top);
                            }
                        }
                    };

                    // Escape confirmation overlay (inline, avoids nested Swal z-index issues)
                    const overlay = document.createElement('div');
                    overlay.id = 'fcc-escape-confirm-overlay';
                    overlay.style.cssText = 'display:none; position:absolute; inset:0; z-index:10; background:rgba(0,0,0,0.85); border-radius:inherit; flex-direction:column; align-items:center; justify-content:center; gap:12px; padding:24px; text-align:center;';
                    overlay.innerHTML = `
                        <div style="font-size:1.2em; font-weight:bold; color:#fff;">Cancel Override?</div>
                        <div style="color:#ccc; font-size:0.9em;">Are you sure you want to close without saving?</div>
                        <div style="display:flex; gap:10px; margin-top:8px;">
                            <button id="fcc-escape-yes" class="btn btn-danger btn-sm" style="min-width:100px;">Yes, close</button>
                            <button id="fcc-escape-no" class="btn btn-secondary btn-sm" style="min-width:100px;">No, go back</button>
                        </div>
                    `;
                    popup.style.position = 'relative';
                    popup.appendChild(overlay);

                    let confirmShowing = false;
                    const showConfirmOverlay = () => {
                        confirmShowing = true;
                        overlay.style.display = 'flex';
                        popup.querySelector('#fcc-escape-no').focus();
                    };
                    const hideConfirmOverlay = () => {
                        confirmShowing = false;
                        overlay.style.display = 'none';
                        searchInput.focus();
                    };

                    const escYes = popup.querySelector('#fcc-escape-yes');
                    const escNo = popup.querySelector('#fcc-escape-no');
                    escYes.addEventListener('click', () => Swal.close());
                    escNo.addEventListener('click', () => hideConfirmOverlay());

                    // Arrow keys and Tab switch focus between Yes/No buttons
                    overlay.addEventListener('keydown', (e) => {
                        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Tab') {
                            e.preventDefault();
                            const target = document.activeElement === escYes ? escNo : escYes;
                            target.focus();
                        }
                    });

                    searchInput.addEventListener('input', (e) => {
                        const term = e.target.value.toLowerCase();
                        items.forEach(item => {
                            if (item.innerText.toLowerCase().includes(term)) item.style.display = 'block';
                            else item.style.display = 'none';
                        });
                        clearKbHighlight();
                    });

                    items.forEach(item => {
                        item.addEventListener('click', () => {
                            clearKbHighlight();
                            items.forEach(i => i.style.background = 'transparent');
                            item.style.background = '#444';
                            hiddenInput.value = item.getAttribute('data-id');
                        });
                        item.addEventListener('mouseenter', () => {
                            clearKbHighlight();
                            if(hiddenInput.value !== item.getAttribute('data-id')) item.style.background = '#222';
                        });
                        item.addEventListener('mouseleave', () => { if(hiddenInput.value !== item.getAttribute('data-id')) item.style.background = 'transparent'; });
                    });

                    // Keyboard navigation on search input
                    searchInput.addEventListener('keydown', (e) => {
                        if (confirmShowing) return;
                        const visible = getVisibleItems();

                        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                            if (!visible.length) return;
                            e.preventDefault();
                            if (e.key === 'ArrowDown') {
                                kbIndex = kbIndex + 1 >= visible.length ? 0 : kbIndex + 1;
                            } else {
                                kbIndex = kbIndex - 1 < 0 ? visible.length - 1 : kbIndex - 1;
                            }
                            applyKbHighlight(visible, kbIndex);
                            return;
                        }

                        if (e.key === 'Enter') {
                            e.preventDefault();
                            if (kbIndex >= 0 && kbIndex < visible.length) {
                                const target = visible[kbIndex];
                                items.forEach(i => i.style.background = 'transparent');
                                target.style.background = '#444';
                                hiddenInput.value = target.getAttribute('data-id');
                                clearKbHighlight();
                            }
                            return;
                        }
                    });

                    // Escape key — listen on window in capture phase so we win against
                    // SweetAlert2's focus-trap handler, which otherwise stops propagation
                    // between window and document when focus lands on overlay buttons.
                    // Bubble-phase listeners on the popup never see the second Escape in
                    // that state.
                    const escKeyHandler = (e) => {
                        if (e.key !== 'Escape') return;
                        e.preventDefault();
                        e.stopImmediatePropagation();
                        if (confirmShowing) {
                            hideConfirmOverlay();
                        } else {
                            showConfirmOverlay();
                        }
                    };
                    window.addEventListener('keydown', escKeyHandler, true);
                    popup.__fccEscCleanup = () => window.removeEventListener('keydown', escKeyHandler, true);

                    // Guard the Cancel button with the same confirmation
                    const cancelBtn = popup.querySelector('.swal2-cancel');
                    if (cancelBtn) {
                        cancelBtn.addEventListener('click', (e) => {
                            e.preventDefault();
                            e.stopImmediatePropagation();
                            showConfirmOverlay();
                        }, true);
                    }
                },
                willClose: () => {
                    // Detach the document-level Escape capture handler installed in didOpen.
                    const popup = Swal.getPopup();
                    if (popup && typeof popup.__fccEscCleanup === 'function') {
                        try { popup.__fccEscCleanup(); } catch (_) { /* noop */ }
                    }
                },
                preConfirm: () => {
                    const popup = Swal.getPopup();
                    const sel = popup ? popup.querySelector('#swal-override-loc') : null;
                    return sel ? sel.value : "";
                }
            }).then((result) => {
                if (result.isConfirmed) {
                    const newLoc = result.value;
                    
                    if (typeof setProcessing === 'function') setProcessing(true);
                    const payload = {
                        action: newLoc === "" ? 'force_unassign' : 'add',
                        location: newLoc,
                        spool_id: spoolId,
                        origin: 'manual_override'
                    };
                    
                    fetch('/api/manage_contents', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    })
                    .then(r => r.json())
                    .then(res => {
                        if (typeof setProcessing === 'function') setProcessing(false);
                        if(res.status === 'success' || res.success) {
                            showToast('Location updated via override', 'success');
                            document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));
                            openSpoolDetails(spoolId, true); 
                        } else {
                            showToast(res.msg || 'Override failed', 'error');
                        }
                    })
                    .catch(e => {
                        if (typeof setProcessing === 'function') setProcessing(false);
                        showToast('Override Network Error', 'error');
                    });
                }
            });
        });
};

window.refreshFilamentSpools = () => {
    const fidEl = document.getElementById('fil-detail-id');
    if (fidEl && fidEl.innerText) {
        // Clear caches so it forces a re-render
        if (typeof state !== 'undefined') {
            state.lastFilamentInfoHash = null;
            state.lastFilamentSpoolsHash = null;
        }
        openFilamentDetails(fidEl.innerText, false);
    }
};


// --- Archive-Empty-Weight Prompt -------------------------------------------
// Fires after a spool auto-archives (remaining weight hit 0) when the parent
// filament has no empty_spool_weight recorded. Walks the user through weighing
// the now-empty spool so all future spools of this filament inherit the value.
//
// Option-B from the backlog: a dedicated modal, bigger affordance than a
// toast, with explicit "Save" / "Later" / "Cancel" paths.
window.showArchiveEmptyWeightPrompt = async (spoolId, filamentId) => {
    if (!filamentId) return;
    let fil;
    try {
        const r = await fetch(`/api/filament_details?id=${filamentId}`);
        fil = await r.json();
    } catch (e) {
        console.warn("Could not fetch filament for empty-weight prompt", e);
        return;
    }
    if (!fil || !fil.id) return;

    const vendorName = (fil.vendor && fil.vendor.name) ? fil.vendor.name : 'Unknown';
    const material = fil.material || 'Unknown';
    const colorName = fil.name || 'Unknown';

    const result = await Swal.fire({
        target: document.body,
        title: '📦 Spool archived — weigh the empty?',
        html: `
            <div class="text-start">
                <p class="text-light mb-2">
                    Spool <strong>#${spoolId}</strong> just hit 0g and was auto-archived.
                    Its filament <strong>#${fil.id}</strong>
                    (<em>${vendorName} ${material}, ${colorName}</em>)
                    has no recorded <strong>empty spool weight</strong>.
                </p>
                <p class="text-light small mb-3">
                    Put the now-empty spool on your scale and enter the measured weight below.
                    The value will be saved to the filament, so every future spool of this filament
                    inherits it automatically.
                </p>
                <label class="form-label text-warning small mb-1">Empty spool weight (g)</label>
                <input type="number" step="0.1" min="0" id="fcc-archive-empty-wt"
                    class="form-control bg-dark text-white border-warning" autocomplete="off"
                    placeholder="e.g. 167">
                <small class="text-secondary d-block mt-2">
                    Tap <strong>Later</strong> to dismiss without saving — you can enter the weight
                    any time from the Filament Details modal.
                </small>
            </div>
        `,
        background: '#1e1e1e',
        color: '#fff',
        showCancelButton: true,
        showDenyButton: true,
        confirmButtonText: 'Save weight',
        denyButtonText: 'Later',
        cancelButtonText: 'Cancel',
        confirmButtonColor: '#ffc107',
        denyButtonColor: '#6c757d',
        allowEscapeKey: true,
        focusConfirm: false,
        didOpen: () => {
            const wtEl = Swal.getPopup().querySelector('#fcc-archive-empty-wt');
            if (wtEl) {
                wtEl.focus();
                // L46: Swal2 doesn't auto-bind Enter to confirm when preConfirm
                // is wired up — surface our own keydown handler so the user
                // can submit by pressing Enter from the input.
                wtEl.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        Swal.clickConfirm();
                    }
                });
            }
        },
        preConfirm: () => {
            const raw = Swal.getPopup().querySelector('#fcc-archive-empty-wt')?.value;
            if (raw === '' || raw == null) {
                Swal.showValidationMessage('Enter a weight or tap Later.');
                return false;
            }
            const n = Number(raw);
            if (!Number.isFinite(n) || n <= 0) {
                Swal.showValidationMessage('Weight must be a positive number.');
                return false;
            }
            return n;
        },
    });

    if (!result.isConfirmed) return;  // Later / Cancel / Escape — all no-op

    const weight = result.value;
    try {
        const r = await fetch('/api/update_filament', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: fil.id, data: { spool_weight: weight } }),
        });
        const d = await r.json();
        if (d && d.success) {
            showToast(`Saved ${weight}g as Filament #${fil.id} empty weight.`, 'success');
        } else {
            showToast(`Save failed: ${d && d.msg ? d.msg : 'unknown'}`, 'error', 7000);
        }
    } catch (e) {
        showToast(`Save error: ${e.message || e}`, 'error', 7000);
    }
};

// --- Edit Filament / Add Filament (Bootstrap modal) ---
// openEditFilamentForm(fil) opens the modal in edit mode. openAddFilamentForm()
// opens the same modal in create mode (no pre-filled fil, Save POSTs
// /api/create_filament instead of /api/update_filament).
//
// 2026-04-23 iteration on the Bootstrap-modal rewrite: added max-temp
// fields (nozzle/bed high, stored in extras), up/down sort buttons for
// color rows, chip-picker for filament_attributes matching the wizard,
// "+ NEW" badge on material, and Add-mode entry point.
const _editfilOpenModal = (fil) => {
    const isCreate = !fil || !fil.id;
    fil = fil || {};

    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const unquoteExtra = (v) => {
        if (v == null) return '';
        const s = String(v);
        if (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
        return s;
    };
    const parseHexList = (val) => {
        if (!val) return [];
        return String(val)
            .split(',')
            .map(h => h.replace(/^#/, '').trim().toLowerCase())
            .filter(h => /^[0-9a-fA-F]{6}$/.test(h))
            .map(h => `#${h}`);
    };

    // --- Snapshot original values for the dirty-diff ---
    const multiHexList = parseHexList(fil.multi_color_hexes);
    const singleHexList = parseHexList(fil.color_hex);
    const currentColors = multiHexList.length > 0 ? multiHexList : singleHexList;
    const currentDirection = String(fil.multi_color_direction
        || (fil.extra && fil.extra.multi_color_direction)
        || 'longitudinal').toLowerCase();
    const currentVendorId = fil.vendor && fil.vendor.id != null ? String(fil.vendor.id) : '';
    const currentVendorName = fil.vendor && fil.vendor.name ? fil.vendor.name : '';
    const rawExtra = fil.extra || {};
    const currentProductUrl = unquoteExtra(rawExtra.product_url);
    const currentPurchaseUrl = unquoteExtra(rawExtra.purchase_url);
    const currentSheetLink = unquoteExtra(rawExtra.sheet_link);
    const currentOriginalColor = unquoteExtra(rawExtra.original_color);
    const currentNozzleMax = unquoteExtra(rawExtra.nozzle_temp_max);
    const currentBedMax = unquoteExtra(rawExtra.bed_temp_max);
    let currentAttributes = [];
    const rawAttrs = rawExtra.filament_attributes;
    if (rawAttrs != null && rawAttrs !== '') {
        try {
            const parsed = typeof rawAttrs === 'string' ? JSON.parse(rawAttrs) : rawAttrs;
            if (Array.isArray(parsed)) {
                currentAttributes = parsed.map(String).map(s => s.trim()).filter(Boolean);
            } else if (parsed) {
                currentAttributes = [String(parsed)];
            }
        } catch (_) {
            const fallback = String(rawAttrs).replace(/^"|"$/g, '').trim();
            if (fallback) currentAttributes = [fallback];
        }
    }

    const modalEl = document.getElementById('editFilamentModal');
    if (!modalEl) { showToast('Edit Filament modal missing', 'error'); return; }
    const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);

    // --- Populate fields ---
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val == null ? '' : val; };
    const title = isCreate ? '➕ Add Filament' : `✏️ Edit Filament #${fil.id}`;
    modalEl.querySelector('#editFilamentModalLabel').innerText = title;
    setVal('editfil-name', fil.name || '');
    setVal('editfil-material', fil.material || (isCreate ? '' : 'PLA'));
    setVal('editfil-spool-weight', fil.spool_weight != null ? fil.spool_weight : '');
    setVal('editfil-density', fil.density != null ? fil.density : '');
    setVal('editfil-diameter', fil.diameter != null ? fil.diameter : '');
    setVal('editfil-weight', fil.weight != null ? fil.weight : '');
    setVal('editfil-price', fil.price != null ? fil.price : '');
    setVal('editfil-nozzle', fil.settings_extruder_temp != null ? fil.settings_extruder_temp : '');
    setVal('editfil-bed', fil.settings_bed_temp != null ? fil.settings_bed_temp : '');
    setVal('editfil-nozzle-max', currentNozzleMax);
    setVal('editfil-bed-max', currentBedMax);
    setVal('editfil-comment', fil.comment || '');
    setVal('editfil-external-id', fil.external_id || '');
    setVal('editfil-vendor-name', currentVendorName);
    setVal('editfil-vendor-id', currentVendorId);
    setVal('editfil-product-url', currentProductUrl);
    setVal('editfil-purchase-url', currentPurchaseUrl);
    setVal('editfil-sheet-link', currentSheetLink);
    setVal('editfil-original-color', currentOriginalColor);

    // Update Save button label + data attribute (consumed by the save handler below).
    const rawSaveBtn = document.getElementById('editfil-save');
    if (rawSaveBtn) {
        rawSaveBtn.innerHTML = isCreate ? '➕ Create' : '💾 Save';
        rawSaveBtn.dataset.mode = isCreate ? 'create' : 'edit';
    }

    // Vendor empty_spool_weight hint (shown as small muted text next to the label).
    const vendorWt = fil.vendor && fil.vendor.empty_spool_weight
        ? Number(fil.vendor.empty_spool_weight) : null;
    const vendorWtHint = document.getElementById('editfil-vendor-wt-hint');
    if (vendorWtHint) vendorWtHint.innerText = vendorWt ? `(vendor: ${vendorWt}g)` : '';
    const spoolWtEl = document.getElementById('editfil-spool-weight');
    if (spoolWtEl) spoolWtEl.placeholder = vendorWt ? String(vendorWt) : '';

    // Reset any prior error banner + default-tab selection.
    const errEl = document.getElementById('editfil-error');
    if (errEl) { errEl.classList.add('d-none'); errEl.innerText = ''; }
    const basicTabBtn = document.getElementById('editfil-tab-basic-btn');
    if (basicTabBtn) bootstrap.Tab.getOrCreateInstance(basicTabBtn).show();

    // --- Colors tab: primary picker + dynamic extras w/ reorder ---
    const picker = document.getElementById('editfil-color-picker');
    const hex = document.getElementById('editfil-color-hex');
    const primaryHex = currentColors[0] || '#000000';
    if (picker) picker.value = primaryHex;
    if (hex) hex.value = currentColors.length > 0 ? primaryHex : '';

    const wirePickerHexPair = (pickerEl, hexEl) => {
        if (!pickerEl || !hexEl) return;
        // Normalize the text-field to "#rrggbb" and push to picker.
        // Called from blur + keydown-Enter + keydown-Tab so any of those
        // exit-the-input actions commit the typed hex immediately.
        const commitHex = () => {
            const raw = hexEl.value.trim().replace(/^#/, '');
            if (raw === '') return;
            if (/^[0-9a-fA-F]{6}$/.test(raw)) {
                hexEl.value = `#${raw.toLowerCase()}`;
                pickerEl.value = `#${raw.toLowerCase()}`;
            }
        };
        pickerEl.oninput = () => { hexEl.value = pickerEl.value; };
        hexEl.oninput = () => {
            const v = hexEl.value.trim();
            if (/^#[0-9a-fA-F]{6}$/.test(v)) pickerEl.value = v.toLowerCase();
        };
        hexEl.onblur = commitHex;
        hexEl.onkeydown = (e) => {
            // Enter + Tab both "leave" the input and should commit the hex
            // to the picker. Enter also swallows (so the modal doesn't
            // submit if some future Save-on-Enter handler is added).
            if (e.key === 'Enter') {
                e.preventDefault();
                commitHex();
            } else if (e.key === 'Tab') {
                commitHex();
                // Let the Tab propagate so focus moves to the next field.
            }
        };
    };
    wirePickerHexPair(picker, hex);

    const extrasHost = document.getElementById('editfil-color-extras');
    const directionSel = document.getElementById('editfil-color-direction');
    const directionWrap = document.getElementById('editfil-direction-wrap');
    const primaryRow = document.getElementById('editfil-color-row-primary');
    if (extrasHost) extrasHost.innerHTML = '';
    if (directionSel) directionSel.value = currentDirection;

    // All rows (primary + extras) live in this array so reorder is just
    // index arithmetic over the array and a re-render.
    const colorRowsState = [{ isPrimary: true, hex: primaryHex, hasValue: currentColors.length > 0 }];
    currentColors.slice(1).forEach(hx => colorRowsState.push({ isPrimary: false, hex: hx, hasValue: true }));

    const refreshDirectionVisibility = () => {
        if (directionWrap) directionWrap.style.display = colorRowsState.length >= 2 ? 'block' : 'none';
    };

    // Extras-row HTML template. Primary row stays in the static template and
    // is rebuilt in-place (preserving its id for backward compatibility with
    // callers that reference #editfil-color-hex directly).
    let extraRowSeq = 0;
    const renderExtras = () => {
        extrasHost.innerHTML = '';
        for (let i = 1; i < colorRowsState.length; i++) {
            const idx = ++extraRowSeq;
            const hexInit = colorRowsState[i].hex || '#000000';
            const row = document.createElement('div');
            row.className = 'd-flex align-items-center gap-2 mb-2 editfil-color-row';
            row.dataset.position = String(i);
            row.innerHTML = `
                <span class="badge bg-info text-dark" style="min-width:36px;" data-role="num">${i + 1}</span>
                <input type="color" id="editfil-color-picker-${idx}" value="${hexInit}" class="form-control form-control-color bg-black border-secondary" style="width:50px; padding:2px;">
                <input type="text" id="editfil-color-hex-${idx}" class="form-control bg-black text-white border-secondary" value="${hexInit}" placeholder="#rrggbb" maxlength="7" style="flex:1;">
                <button type="button" class="btn btn-outline-secondary btn-sm" data-role="up" title="Move up">▲</button>
                <button type="button" class="btn btn-outline-secondary btn-sm" data-role="down" title="Move down">▼</button>
                <button type="button" class="btn btn-outline-danger btn-sm" data-role="remove" title="Remove">🗑️</button>
            `;
            extrasHost.appendChild(row);
            wirePickerHexPair(
                row.querySelector(`#editfil-color-picker-${idx}`),
                row.querySelector(`#editfil-color-hex-${idx}`),
            );
            // Keep state synced so reorder operates on up-to-date values.
            const hexInput = row.querySelector(`#editfil-color-hex-${idx}`);
            hexInput.addEventListener('input', () => { colorRowsState[i].hex = hexInput.value; });
            row.querySelector('[data-role="remove"]').onclick = () => {
                captureCurrentValues();
                colorRowsState.splice(i, 1);
                renderExtras();
                refreshDirectionVisibility();
            };
            row.querySelector('[data-role="up"]').onclick = () => {
                if (i <= 1) return; // Can't move above primary via this button.
                captureCurrentValues();
                const tmp = colorRowsState[i];
                colorRowsState[i] = colorRowsState[i - 1];
                colorRowsState[i - 1] = tmp;
                // If we swapped an extra into the primary slot, the primary
                // row's value must update too.
                syncPrimaryToState();
                renderExtras();
                refreshDirectionVisibility();
            };
            row.querySelector('[data-role="down"]').onclick = () => {
                if (i >= colorRowsState.length - 1) return;
                captureCurrentValues();
                const tmp = colorRowsState[i];
                colorRowsState[i] = colorRowsState[i + 1];
                colorRowsState[i + 1] = tmp;
                renderExtras();
                refreshDirectionVisibility();
            };
            // Disable arrow buttons at array edges.
            if (i === 1) row.querySelector('[data-role="up"]').disabled = false;
            if (i === colorRowsState.length - 1) row.querySelector('[data-role="down"]').disabled = true;
        }
        // Wire primary row's down arrow (up is always disabled on row 0).
        if (primaryRow) {
            const down = primaryRow.querySelector('[data-role="down"]');
            if (down) {
                down.disabled = colorRowsState.length < 2;
                down.onclick = () => {
                    if (colorRowsState.length < 2) return;
                    captureCurrentValues();
                    const tmp = colorRowsState[0];
                    colorRowsState[0] = colorRowsState[1];
                    colorRowsState[1] = tmp;
                    syncPrimaryToState();
                    renderExtras();
                    refreshDirectionVisibility();
                };
            }
        }
    };
    const captureCurrentValues = () => {
        // Pull the latest values from the DOM into colorRowsState so reorder
        // preserves whatever the user has typed since the last render. Use
        // the DOM value verbatim (including empty string) so clearing the
        // primary hex lets the save handler pass color_hex='' through the
        // dirty-diff. The earlier `|| fallback` clobbered empty values
        // with the initial placeholder and caused no-op color_hex writes.
        if (hex) colorRowsState[0].hex = hex.value;
        const extraHexes = extrasHost.querySelectorAll('input[id^="editfil-color-hex-"]');
        extraHexes.forEach((el, i) => {
            if (colorRowsState[i + 1]) colorRowsState[i + 1].hex = el.value;
        });
    };
    const syncPrimaryToState = () => {
        if (hex) hex.value = colorRowsState[0].hex || '';
        if (picker && /^#[0-9a-fA-F]{6}$/.test(colorRowsState[0].hex || '')) {
            picker.value = colorRowsState[0].hex.toLowerCase();
        }
    };
    renderExtras();
    refreshDirectionVisibility();

    const addBtn = document.getElementById('editfil-add-color');
    if (addBtn) addBtn.onclick = () => {
        captureCurrentValues();
        colorRowsState.push({ isPrimary: false, hex: '#000000', hasValue: true });
        renderExtras();
        refreshDirectionVisibility();
    };

    // --- Generic custom-combobox helper ---
    // Replaces the earlier <input list=""> datalist approach. Datalists can't
    // be styled (the browser native dropdown ignored our dark theme) and
    // different browsers show them inconsistently. This helper matches the
    // Add/Edit wizard's custom dropdown pattern: input + absolute-positioned
    // list + keyboard nav (ArrowUp/Down/Enter) + click-to-select.
    //
    //   opts: {
    //     inputId: 'editfil-material',
    //     dropdownId: 'editfil-material-dropdown',
    //     getItems: () => [{value, label}],            // always-fresh item source
    //     onSelect: ({value, label}) => void,          // called on click/Enter
    //     onInput: () => void,                          // called on any keystroke
    //     newHintText: (typed) => 'Press Enter to add "<typed>"' | null
    //   }
    const bindComboDropdown = (opts) => {
        const input = document.getElementById(opts.inputId);
        const dropdown = document.getElementById(opts.dropdownId);
        if (!input || !dropdown) return;

        const render = () => {
            const qs = (input.value || '').toLowerCase();
            const items = opts.getItems() || [];
            const filtered = qs
                ? items.filter(it => String(it.label).toLowerCase().includes(qs))
                : items;
            const rows = filtered.map(it =>
                `<div class="dropdown-item" data-value="${esc(it.value)}" data-label="${esc(it.label)}">${esc(it.label)}</div>`
            );
            const hint = typeof opts.newHintText === 'function' ? opts.newHintText(input.value) : null;
            if (hint) rows.push(`<div class="dropdown-item new-hint" data-new="1">${esc(hint)}</div>`);
            if (rows.length === 0) {
                dropdown.style.display = 'none';
                return;
            }
            dropdown.innerHTML = rows.join('');
            dropdown.style.display = 'block';
            dropdown.querySelectorAll('[data-value]').forEach(el => {
                el.onmousedown = (e) => {
                    e.preventDefault();
                    input.value = el.dataset.label;
                    if (opts.onSelect) opts.onSelect({ value: el.dataset.value, label: el.dataset.label });
                    dropdown.style.display = 'none';
                };
            });
        };
        input.addEventListener('focus', render);
        input.addEventListener('input', () => {
            render();
            if (opts.onInput) opts.onInput();
        });
        input.addEventListener('blur', () => {
            setTimeout(() => { dropdown.style.display = 'none'; }, 150);
        });
        input.addEventListener('keydown', (e) => {
            const visible = dropdown.style.display !== 'none';
            if (e.key === 'Escape' && visible) {
                // Swallow Escape when the dropdown is open so it closes the
                // dropdown only (not the whole Bootstrap modal).
                e.preventDefault();
                e.stopPropagation();
                dropdown.style.display = 'none';
                return;
            }
            if (!visible) {
                if (e.key === 'ArrowDown') render();
                return;
            }
            const items = Array.from(dropdown.querySelectorAll('.dropdown-item'));
            if (!items.length) return;
            let idx = items.findIndex(el => el.classList.contains('active'));
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                items.forEach(el => el.classList.remove('active'));
                if (e.key === 'ArrowDown') idx = idx + 1 >= items.length ? 0 : idx + 1;
                else idx = idx - 1 < 0 ? items.length - 1 : idx - 1;
                items[idx].classList.add('active');
                items[idx].scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter') {
                e.preventDefault();
                const target = items.find(el => el.classList.contains('active')) || items[0];
                if (target && target.dataset.value !== undefined) {
                    input.value = target.dataset.label;
                    if (opts.onSelect) opts.onSelect({ value: target.dataset.value, label: target.dataset.label });
                } else if (target && target.dataset.new) {
                    // User wants to commit whatever they typed as a new value.
                    if (opts.onSelect) opts.onSelect({ value: '', label: input.value, isNew: true });
                }
                dropdown.style.display = 'none';
            }
        });
    };

    // --- Material combobox + "+ NEW" badge ---
    const materialEl = document.getElementById('editfil-material');
    const materialNewBadge = document.getElementById('editfil-material-new-badge');
    let materialCache = [];
    const refreshMaterialBadge = () => {
        const typed = (materialEl.value || '').trim();
        if (!typed) { materialNewBadge.style.display = 'none'; return; }
        const known = materialCache.some(m => m.toLowerCase() === typed.toLowerCase());
        materialNewBadge.style.display = known ? 'none' : 'inline-block';
    };
    bindComboDropdown({
        inputId: 'editfil-material',
        dropdownId: 'editfil-material-dropdown',
        getItems: () => materialCache.map(m => ({ value: m, label: m })),
        onSelect: () => refreshMaterialBadge(),
        onInput: () => refreshMaterialBadge(),
        newHintText: (typed) => {
            const t = (typed || '').trim();
            if (!t) return null;
            if (materialCache.some(m => m.toLowerCase() === t.toLowerCase())) return null;
            return `+ Add "${t}" as a new material`;
        },
    });
    fetch('/api/materials').then(r => r.json()).then(d => {
        if (!d || !d.success) return;
        materialCache = Array.isArray(d.materials) ? d.materials : [];
        refreshMaterialBadge();
    }).catch(() => {});

    // --- Vendor combobox + hidden id + "+ NEW" badge ---
    let vendorCache = [];
    const vendorNameEl = document.getElementById('editfil-vendor-name');
    const vendorIdEl = document.getElementById('editfil-vendor-id');
    const vendorNewBadge = document.getElementById('editfil-vendor-new-badge');
    const vendorInfoPill = document.getElementById('editfil-vendor-info');
    const refreshVendorBadge = () => {
        const typed = (vendorNameEl.value || '').trim();
        if (!typed) {
            vendorIdEl.value = '';
            vendorNewBadge.style.display = 'none';
            if (vendorInfoPill) vendorInfoPill.style.display = 'none';
            return;
        }
        const match = vendorCache.find(v => (v.name || '').toLowerCase() === typed.toLowerCase());
        if (match) {
            vendorIdEl.value = String(match.id);
            vendorNewBadge.style.display = 'none';
            // Surface the vendor's data so the user knows what Spoolman has on
            // file. Empty-spool weight is the most useful; extras (if any)
            // are shown in the tooltip.
            if (vendorInfoPill) {
                const wt = match.empty_spool_weight != null ? Number(match.empty_spool_weight) : null;
                const bits = [];
                if (wt) bits.push(`${wt}g empty`);
                const extras = match.extra || {};
                const extraKeys = Object.keys(extras).filter(k => extras[k] != null && extras[k] !== '');
                if (extraKeys.length > 0) bits.push(`${extraKeys.length} extra${extraKeys.length === 1 ? '' : 's'}`);
                const summary = bits.length > 0 ? `ⓘ ${bits.join(' · ')}` : 'ⓘ vendor';
                vendorInfoPill.innerText = summary;
                const tooltip = wt ? `Default empty-spool weight: ${wt}g` : 'Existing vendor';
                const extraLines = extraKeys.map(k => {
                    const v = extras[k];
                    const str = typeof v === 'string' ? v.replace(/^"|"$/g, '') : JSON.stringify(v);
                    return `${k}: ${str}`;
                });
                vendorInfoPill.title = [tooltip, ...extraLines].join('\n');
                vendorInfoPill.style.display = 'inline-block';
            }
        } else {
            vendorIdEl.value = '';
            vendorNewBadge.style.display = 'inline-block';
            if (vendorInfoPill) vendorInfoPill.style.display = 'none';
        }
    };
    bindComboDropdown({
        inputId: 'editfil-vendor-name',
        dropdownId: 'editfil-vendor-dropdown',
        getItems: () => vendorCache.map(v => ({ value: String(v.id), label: v.name })),
        onSelect: ({ value, label, isNew }) => {
            if (isNew) {
                vendorIdEl.value = '';
            } else {
                vendorIdEl.value = value;
            }
            refreshVendorBadge();
        },
        onInput: () => refreshVendorBadge(),
        newHintText: (typed) => {
            const t = (typed || '').trim();
            if (!t) return null;
            if (vendorCache.some(v => (v.name || '').toLowerCase() === t.toLowerCase())) return null;
            return `+ Create vendor "${t}"`;
        },
    });
    fetch('/api/vendors').then(r => r.json()).then(d => {
        if (!d || !d.success) return;
        vendorCache = d.vendors || [];
        refreshVendorBadge();
    }).catch(() => {});

    // --- Empty-Spool-Wt: bind <EmptyWeightField> on the Specs tab ---
    // Phase 2 (Group 12): the input + copy-vendor affordance is now owned by
    // the shared component (modules/empty_weight_field.js). Binding here
    // wires the auto-clear-on-input behavior (matches the wizard's badge
    // semantics) and routes the "⇩ Copy Vendor Weight" click through the
    // component's `copyVendorBtn` handle. Idempotent — re-opening this modal
    // replaces prior listeners cleanly.
    if (typeof window.bindEmptyWeightField === 'function' && spoolWtEl) {
        const field = window.bindEmptyWeightField({
            input: spoolWtEl,
            copyVendorBtn: document.getElementById('editfil-copy-vendor-wt'),
        });
        if (field) {
            field.setFromCascade({
                spoolWt: fil.spool_weight,
                vendor: fil.vendor,
            });
            // The Specs surface lets the user override the resolved value at
            // any time; the component already clears the (currently absent)
            // badge on input. setFromCascade also drives the copy-vendor
            // button's visibility from the cached vendor value.
        }
    }

    // --- Filament Attributes chip picker (matches wizard UX) ---
    const attrChipsHost = document.getElementById('editfil-attr-chips');
    const attrInput = document.getElementById('editfil-attr-input');
    const attrDropdown = document.getElementById('editfil-attr-dropdown');
    let attrChoices = []; // Full list of known attributes from Spoolman's field schema.
    let attrSelected = currentAttributes.slice(); // Current chips.
    let attrPendingNew = []; // Locally-added names awaiting silent Spoolman-choice registration on save.

    const renderAttrChips = () => {
        if (!attrChipsHost) return;
        attrChipsHost.innerHTML = attrSelected.map((v, i) => `
            <span class="editfil-chip" data-value="${esc(v)}">
                ${esc(v)}
                <span class="chip-x" data-idx="${i}">×</span>
            </span>
        `).join('');
        attrChipsHost.querySelectorAll('.chip-x').forEach(x => {
            x.onclick = (e) => {
                e.stopPropagation();
                const idx = Number(x.dataset.idx);
                attrSelected.splice(idx, 1);
                renderAttrChips();
            };
        });
    };
    const renderAttrDropdown = () => {
        if (!attrDropdown) return;
        const qs = (attrInput.value || '').toLowerCase();
        const filtered = attrChoices
            .filter(c => !attrSelected.includes(c))
            .filter(c => !qs || c.toLowerCase().includes(qs));
        if (filtered.length === 0 && !qs) {
            attrDropdown.style.display = 'none';
            return;
        }
        attrDropdown.innerHTML = filtered.map(c =>
            `<div class="dropdown-item" data-value="${esc(c)}">${esc(c)}</div>`
        ).join('') || `<div class="dropdown-item text-muted">Press Enter to add "${esc(attrInput.value)}" as a new tag</div>`;
        attrDropdown.style.display = 'block';
        attrDropdown.querySelectorAll('[data-value]').forEach(item => {
            item.onmousedown = (e) => {
                e.preventDefault();
                addAttrChip(item.dataset.value);
            };
        });
    };
    const addAttrChip = (val, { silent = false } = {}) => {
        const v = String(val || '').trim();
        if (!v) return;
        if (attrSelected.includes(v)) return;
        attrSelected.push(v);
        const known = attrChoices.includes(v);
        if (!known && !silent) attrPendingNew.push(v);
        attrInput.value = '';
        renderAttrChips();
        renderAttrDropdown();
    };
    if (attrInput) {
        attrInput.onfocus = () => renderAttrDropdown();
        attrInput.oninput = () => renderAttrDropdown();
        attrInput.onblur = () => setTimeout(() => { if (attrDropdown) attrDropdown.style.display = 'none'; }, 150);
        attrInput.onkeydown = (e) => {
            if (e.key === 'Escape' && attrDropdown && attrDropdown.style.display !== 'none') {
                // Close the dropdown list only — don't let Bootstrap's
                // modal-dismiss handler see the Escape and close the
                // whole modal. Matches the wizard's attribute chip picker.
                e.preventDefault();
                e.stopPropagation();
                attrDropdown.style.display = 'none';
                return;
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                if (attrInput.value.trim()) addAttrChip(attrInput.value);
            } else if (e.key === 'Backspace' && !attrInput.value && attrSelected.length > 0) {
                attrSelected.pop();
                renderAttrChips();
            }
        };
    }
    // Load known attribute choices from Spoolman's field schema.
    fetch('/api/external/fields').then(r => r.json()).then(d => {
        if (!d || !d.success) return;
        const filamentFields = (d.fields && d.fields.filament) || [];
        const attrField = filamentFields.find(f => f.key === 'filament_attributes');
        if (attrField && Array.isArray(attrField.choices)) {
            attrChoices = attrField.choices.slice();
        }
    }).catch(() => {});
    renderAttrChips();

    // --- Save button handler ---
    // Clone-replace to drop any prior handler (modal is reused across calls).
    const oldSaveBtn = document.getElementById('editfil-save');
    if (!oldSaveBtn) { showToast('Save button missing', 'error'); return; }
    const saveBtn = oldSaveBtn.cloneNode(true);
    oldSaveBtn.parentNode.replaceChild(saveBtn, oldSaveBtn);
    saveBtn.dataset.mode = isCreate ? 'create' : 'edit';

    saveBtn.onclick = async () => {
        const val = (id) => { const el = document.getElementById(id); return el ? el.value : ''; };
        const numOrNull = (id) => {
            const v = val(id);
            if (v === '' || v == null) return null;
            const n = Number(v);
            return Number.isFinite(n) ? n : null;
        };
        const intOrNull = (id) => {
            const n = numOrNull(id);
            return n == null ? null : Math.round(n);
        };
        const showErr = (msg, tabId = null) => {
            const e = document.getElementById('editfil-error');
            if (e) { e.classList.remove('d-none'); e.innerText = msg; }
            if (tabId) {
                const btn = document.getElementById(tabId);
                if (btn) bootstrap.Tab.getOrCreateInstance(btn).show();
            }
        };
        const clearErr = () => {
            const e = document.getElementById('editfil-error');
            if (e) { e.classList.add('d-none'); e.innerText = ''; }
        };
        clearErr();

        // Colors: capture + validate.
        captureCurrentValues();
        const rawColors = [];
        for (const row of colorRowsState) {
            const rawHex = String(row.hex || '').trim().replace(/^#/, '');
            if (rawHex === '') continue;
            if (!/^[0-9a-fA-F]{6}$/.test(rawHex)) {
                showErr(`Color must be a 6-digit hex (got "${rawHex}").`, 'editfil-tab-colors-btn');
                return;
            }
            rawColors.push(rawHex.toLowerCase());
        }
        let colorHex = null;
        let multiColorHexes = null;
        let multiDirection = null;
        if (rawColors.length === 0) {
            // No colors at all — clear both fields.
            colorHex = '';
            multiColorHexes = '';
        } else if (rawColors.length === 1) {
            // Single color — use color_hex, clear multi.
            colorHex = rawColors[0];
            multiColorHexes = '';
        } else {
            // 2+ colors — Spoolman REJECTS (HTTP 422) if both color_hex and
            // multi_color_hexes are set ("Cannot specify both"). Use
            // multi_color_hexes and force color_hex to empty. The first
            // hex in the CSV is still the "primary" for display purposes.
            colorHex = '';
            multiColorHexes = rawColors.join(',');
            multiDirection = (val('editfil-color-direction') || 'longitudinal').toLowerCase();
        }

        // Vendor resolution: known-name → hidden id; new-name → POST /api/vendors.
        const vendorTyped = (val('editfil-vendor-name') || '').trim();
        const vendorIdRaw = val('editfil-vendor-id');
        let vendorId;
        let pendingNewVendorName = null;
        if (!vendorTyped) {
            vendorId = null;
        } else if (vendorIdRaw) {
            vendorId = Number(vendorIdRaw);
        } else {
            vendorId = undefined;
            pendingNewVendorName = vendorTyped;
        }

        // Advanced-section extras merge.
        const newProductUrl = (val('editfil-product-url') || '').trim();
        const newPurchaseUrl = (val('editfil-purchase-url') || '').trim();
        const newSheetLink = (val('editfil-sheet-link') || '').trim();
        const newOriginalColor = (val('editfil-original-color') || '').trim();
        // If the user had typed something in the attribute input without
        // committing it as a chip, commit it now so it's not silently lost.
        if (attrInput && attrInput.value && attrInput.value.trim()) {
            addAttrChip(attrInput.value);
        }
        const attrsArr = attrSelected.slice();
        const newNozzleMax = val('editfil-nozzle-max');
        const newBedMax = val('editfil-bed-max');

        const dirtyExtras = {};
        if (newProductUrl !== unquoteExtra(rawExtra.product_url)) dirtyExtras.product_url = newProductUrl;
        if (newPurchaseUrl !== unquoteExtra(rawExtra.purchase_url)) dirtyExtras.purchase_url = newPurchaseUrl;
        if (newSheetLink !== unquoteExtra(rawExtra.sheet_link)) dirtyExtras.sheet_link = newSheetLink;
        if (newOriginalColor !== unquoteExtra(rawExtra.original_color)) dirtyExtras.original_color = newOriginalColor;
        if (newNozzleMax !== unquoteExtra(rawExtra.nozzle_temp_max)) dirtyExtras.nozzle_temp_max = newNozzleMax;
        if (newBedMax !== unquoteExtra(rawExtra.bed_temp_max)) dirtyExtras.bed_temp_max = newBedMax;
        const prevAttrsArr = (() => {
            try {
                const p = typeof rawExtra.filament_attributes === 'string'
                    ? JSON.parse(rawExtra.filament_attributes)
                    : rawExtra.filament_attributes;
                return Array.isArray(p) ? p.map(String).map(s => s.trim()).filter(Boolean) : [];
            } catch (_) { return []; }
        })();
        if (JSON.stringify(attrsArr) !== JSON.stringify(prevAttrsArr)) {
            dirtyExtras.filament_attributes = attrsArr;
        }

        // Required-field guards in Add mode — Spoolman insists on material.
        if (isCreate && !(val('editfil-material') || '').trim()) {
            showErr('Material is required to create a filament.', 'editfil-tab-basic-btn');
            return;
        }

        const data = {
            name: (val('editfil-name') || '').trim() || null,
            material: (val('editfil-material') || '').trim() || null,
            vendor_id: vendorId,
            color_hex: colorHex,
            multi_color_hexes: multiColorHexes,
            multi_color_direction: multiDirection,
            spool_weight: numOrNull('editfil-spool-weight'),
            density: numOrNull('editfil-density'),
            diameter: numOrNull('editfil-diameter'),
            weight: numOrNull('editfil-weight'),
            price: numOrNull('editfil-price'),
            external_id: (val('editfil-external-id') || '').trim(),
            settings_extruder_temp: intOrNull('editfil-nozzle'),
            settings_bed_temp: intOrNull('editfil-bed'),
            comment: val('editfil-comment') || '',
        };

        let payload;
        if (isCreate) {
            // Full payload on create — no dirty-diff (there's nothing to diff against).
            const cleanExtras = {};
            for (const [k, v] of Object.entries(dirtyExtras)) {
                if (k === 'filament_attributes') cleanExtras[k] = JSON.stringify(v);
                else if (v !== '' && v != null) cleanExtras[k] = `"${String(v)}"`;
            }
            payload = { ...data };
            if (Object.keys(cleanExtras).length > 0) payload.extra = cleanExtras;
        } else {
            const same = (a, b) => {
                if (a == null && (b == null || b === '')) return true;
                if (b == null && (a == null || a === '')) return true;
                return String(a) === String(b);
            };
            const changed = {};
            if (!same(data.name, fil.name)) changed.name = data.name;
            if (!same(data.material, fil.material)) changed.material = data.material;
            const oldVendorId = fil.vendor && fil.vendor.id != null ? fil.vendor.id : null;
            if (pendingNewVendorName == null && !same(data.vendor_id, oldVendorId)) {
                changed.vendor_id = data.vendor_id;
            }
            // Color-field tri-state (Spoolman's invariants, verified 2026-04-23
            // against live 0.23.1 schema):
            //   - color_hex SET, multi_color_hexes EMPTY, multi_color_direction EMPTY → single
            //   - color_hex EMPTY, multi_color_hexes SET, multi_color_direction SET → multi
            //   - mixing the two columns triggers HTTP 422 ("Cannot specify both…",
            //     "Single-color filament must not have direction set",
            //     "Multi-color filament must have direction set").
            //
            // Strategy: figure out which mode we're emitting, then send a body
            // that's internally consistent. When transitioning out of multi
            // mode we also have to actively CLEAR the dangling multi fields
            // (Spoolman keeps stale values otherwise, which makes the next
            // single-color save fail validation on the merged state).
            const oldHex = (fil.color_hex || '').replace(/^#/, '').toLowerCase();
            const newHex = (data.color_hex || '').toLowerCase();
            const oldMulti = String(fil.multi_color_hexes || '')
                .split(',').map(h => h.replace(/^#/, '').trim().toLowerCase())
                .filter(Boolean).join(',');
            const newMulti = String(data.multi_color_hexes || '').toLowerCase();
            const oldDir = String(fil.multi_color_direction || '').toLowerCase();
            const newDir = data.multi_color_direction || 'longitudinal';
            const emittingMulti = newMulti.length > 0;
            const wasMulti = oldMulti.length > 0;

            if (emittingMulti) {
                // Multi mode. Hexes + direction always travel together (any
                // change to either forces both into the body, since Spoolman
                // validates: "Multi-color filament must have direction set").
                // Never send color_hex in this branch — Spoolman: "Cannot
                // specify both color_hex and multi_color_hexes".
                if (oldMulti !== newMulti || oldDir !== newDir) {
                    changed.multi_color_hexes = data.multi_color_hexes;
                    changed.multi_color_direction = newDir;
                }
            } else {
                // Single-color (or no-color) mode. Emit color_hex if changed.
                if (oldHex !== newHex) changed.color_hex = data.color_hex;
                // Going multi → single: clear the dangling multi fields so
                // Spoolman's merged state becomes a valid single-color row.
                // Without this clear, the NEXT save would hit "Single-color
                // filament must not have multi_color_direction set" because
                // the stale direction value still lives in the DB.
                if (wasMulti) changed.multi_color_hexes = '';
                if (oldDir) changed.multi_color_direction = null;
            }
            if (!same(data.spool_weight, fil.spool_weight)) changed.spool_weight = data.spool_weight;
            if (!same(data.density, fil.density)) changed.density = data.density;
            if (!same(data.diameter, fil.diameter)) changed.diameter = data.diameter;
            if (!same(data.weight, fil.weight)) changed.weight = data.weight;
            if (!same(data.price, fil.price)) changed.price = data.price;
            if (!same(data.external_id, fil.external_id)) changed.external_id = data.external_id;
            if (!same(data.settings_extruder_temp, fil.settings_extruder_temp))
                changed.settings_extruder_temp = data.settings_extruder_temp;
            if (!same(data.settings_bed_temp, fil.settings_bed_temp))
                changed.settings_bed_temp = data.settings_bed_temp;
            if (!same(data.comment, fil.comment)) changed.comment = data.comment;

            if (Object.keys(dirtyExtras).length > 0) {
                const mergedExtra = { ...(fil.extra || {}) };
                for (const [k, v] of Object.entries(dirtyExtras)) {
                    if (k === 'filament_attributes') {
                        mergedExtra[k] = JSON.stringify(v);
                    } else if (v === '' || v == null) {
                        delete mergedExtra[k];
                    } else {
                        mergedExtra[k] = `"${String(v)}"`;
                    }
                }
                changed.extra = mergedExtra;
            }
            payload = changed;
            if (Object.keys(payload).length === 0 && !pendingNewVendorName) {
                showToast('No changes to save.', 'info');
                bsModal.hide();
                return;
            }
        }

        saveBtn.disabled = true;
        try {
            // Register newly-typed filament_attribute tags with Spoolman's schema
            // so future modals show them in the dropdown. Fire-and-forget;
            // we don't want a schema-update failure to block the main save.
            attrPendingNew.forEach(tag => {
                fetch('/api/external/fields/add_choice', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ entity_type: 'filament', key: 'filament_attributes', new_choice: tag }),
                }).catch(() => {});
            });
            attrPendingNew = [];

            if (pendingNewVendorName) {
                const vr = await fetch('/api/vendors', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: pendingNewVendorName }),
                });
                const vd = await vr.json();
                if (vd && vd.success && vd.vendor && vd.vendor.id != null) {
                    payload.vendor_id = Number(vd.vendor.id);
                } else {
                    showErr(`Couldn't create vendor "${pendingNewVendorName}": ${(vd && vd.msg) || 'unknown'}`, 'editfil-tab-basic-btn');
                    return;
                }
            }

            const url = isCreate ? '/api/create_filament' : '/api/update_filament';
            const body = isCreate ? { data: payload } : { id: fil.id, data: payload };
            const r = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const d = await r.json();
            if (d && d.success) {
                const newId = (d.filament && d.filament.id) || (isCreate ? '?' : fil.id);
                showToast(isCreate ? `Filament #${newId} created.` : `Filament #${fil.id} updated.`, 'success');
                if (window.refreshFilamentSpools) window.refreshFilamentSpools();
                if (isCreate && window.fetchLocations) window.fetchLocations();
                bsModal.hide();
            } else {
                showErr(`${isCreate ? 'Create' : 'Update'} failed: ${d && d.msg ? d.msg : 'unknown'}`);
            }
        } catch (e) {
            showErr(`${isCreate ? 'Create' : 'Update'} error: ${e.message || e}`);
        } finally {
            saveBtn.disabled = false;
        }
    };

    // --- Escape-with-unsaved-changes guard ---
    // Tracks whether the user has modified ANY input since open. Compared to
    // a DOM snapshot at show-time so arbitrary input changes (text + hex +
    // chips + color rows) all mark the form dirty. Escape pops a small
    // confirm overlay instead of dismissing the modal outright.
    const snapshotFormState = () => {
        // Hash every input/textarea/select value + the chip set + color rows.
        const parts = [];
        modalEl.querySelectorAll('input, textarea, select').forEach(el => {
            parts.push(`${el.id || el.name}=${el.value}`);
        });
        parts.push('chips=' + attrSelected.join(','));
        return parts.join('|');
    };
    let baselineState = '';
    // Install a capture-phase keydown listener on the modal so we see Escape
    // before Bootstrap's built-in dismiss handler. When the form is dirty,
    // swallow the original Escape and show a confirm overlay.
    const escGuardHandler = (e) => {
        if (e.key !== 'Escape') return;
        // If any combobox/chip dropdown has its own Escape handler active,
        // let those fire first (they stopPropagation when visible).
        // By the time this bubble-phase handler sees Escape, we know no
        // dropdown was open.
        if (snapshotFormState() === baselineState) return; // Clean — let Bootstrap close.
        e.preventDefault();
        e.stopPropagation();
        _editfilShowEscapeConfirm(bsModal);
    };
    modalEl.addEventListener('keydown', escGuardHandler);
    // Re-snapshot when the modal finishes opening (after we populate fields).
    modalEl.addEventListener('shown.bs.modal', () => { baselineState = snapshotFormState(); }, { once: true });
    modalEl.addEventListener('hidden.bs.modal', () => {
        modalEl.removeEventListener('keydown', escGuardHandler);
    }, { once: true });

    bsModal.show();
};

// Inline confirm overlay for "close without saving?" Mounts inside the
// modal so it stacks above the modal's own backdrop and shares its z-index.
// No nested Swal per project convention — just a dark-backdrop div with
// Yes/No buttons that resolve to close-anyway or dismiss-the-overlay.
const _editfilShowEscapeConfirm = (bsModal) => {
    const modalEl = document.getElementById('editFilamentModal');
    if (!modalEl) return;
    // Avoid stacking multiples if the user mashes Escape.
    let ov = document.getElementById('editfil-esc-confirm');
    if (ov) ov.remove();
    ov = document.createElement('div');
    ov.id = 'editfil-esc-confirm';
    ov.style.cssText = 'position:absolute; inset:0; z-index:20000; background:rgba(0,0,0,0.85); display:flex; align-items:center; justify-content:center;';
    ov.innerHTML = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ff8800; border-radius:8px; padding:20px 24px; max-width:420px; text-align:center;">
            <div style="font-size:1.1em; font-weight:bold; margin-bottom:8px;">Close without saving?</div>
            <div style="color:#ffc; margin-bottom:14px;">You have unsaved changes to this filament. Leave anyway?</div>
            <div style="display:flex; gap:10px; justify-content:center;">
                <button id="editfil-esc-yes" class="btn btn-danger btn-sm" style="min-width:120px;">Close Anyway</button>
                <button id="editfil-esc-no" class="btn btn-secondary btn-sm" style="min-width:120px;">Keep Editing</button>
            </div>
        </div>
    `;
    // Use the modal dialog as the mount point so the overlay sits inside
    // the modal's position:relative parent and inherits its stacking.
    const dialog = modalEl.querySelector('.modal-content') || modalEl;
    dialog.style.position = 'relative';
    dialog.appendChild(ov);
    const cleanup = () => { try { ov.remove(); } catch (_) { /* noop */ } document.removeEventListener('keydown', keyHandler, true); };
    // Enter activates the focused button. "Keep Editing" is focused by
    // default (the SAFE choice — don't lose edits on stray Enter), so
    // Enter dismisses just the overlay. Tab moves focus to "Close Anyway";
    // Enter there confirms losing the edits. Escape unconditionally
    // cancels the overlay. Tab is trapped inside the two buttons so it
    // can't escape to the page (or browser chrome) behind.
    const keyHandler = (e) => {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cleanup(); return; }
        const yesBtn = document.getElementById('editfil-esc-yes');
        const noBtn = document.getElementById('editfil-esc-no');
        if (e.key === 'Enter') {
            const active = document.activeElement;
            if (active === yesBtn) { e.preventDefault(); e.stopPropagation(); cleanup(); bsModal.hide(); }
            else if (active === noBtn) { e.preventDefault(); e.stopPropagation(); cleanup(); }
            return;
        }
        if (e.key === 'Tab') {
            const focusables = [yesBtn, noBtn].filter(Boolean);
            if (focusables.length === 0) return;
            const active = document.activeElement;
            const idx = focusables.indexOf(active);
            if (idx === -1) {
                e.preventDefault(); e.stopPropagation();
                focusables[e.shiftKey ? focusables.length - 1 : 0].focus();
                return;
            }
            if (e.shiftKey && idx === 0) {
                e.preventDefault(); e.stopPropagation();
                focusables[focusables.length - 1].focus();
            } else if (!e.shiftKey && idx === focusables.length - 1) {
                e.preventDefault(); e.stopPropagation();
                focusables[0].focus();
            }
        }
    };
    document.getElementById('editfil-esc-no').onclick = cleanup;
    document.getElementById('editfil-esc-yes').onclick = () => { cleanup(); bsModal.hide(); };
    document.addEventListener('keydown', keyHandler, true);
    document.getElementById('editfil-esc-no').focus();
};

window.openEditFilamentForm = (fil) => {
    if (!fil || !fil.id) { showToast('Missing filament data', 'error'); return; }
    _editfilOpenModal(fil);
};

window.openAddFilamentForm = () => {
    _editfilOpenModal(null);
};
