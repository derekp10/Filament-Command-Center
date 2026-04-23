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
                        } else {
                            // No spools found
                            if (countBadge) countBadge.innerText = "0";
                            listContainer.innerHTML = "<div class='p-2 text-light text-center small'>No spools found.</div>";
                            if (btnQueueAll) btnQueueAll.style.display = 'none';
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
            if (wtEl) wtEl.focus();
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

// --- Edit Filament (direct, filament-only) ---
// Opens a Swal form over the Filament Details modal (Bootstrap, not Swal, so
// no nested-Swal footgun). Only the commonly-edited, filament-level fields
// are exposed here.
window.openEditFilamentForm = (fil) => {
    if (!fil || !fil.id) { showToast('Missing filament data', 'error'); return; }

    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    const currentName = esc(fil.name || '');
    const currentMaterial = esc(fil.material || 'PLA');
    const currentSpoolWt = fil.spool_weight != null ? fil.spool_weight : '';
    const currentDensity = fil.density != null ? fil.density : '';
    const currentDiameter = fil.diameter != null ? fil.diameter : '';
    const currentWeight = fil.weight != null ? fil.weight : '';
    const currentPrice = fil.price != null ? fil.price : '';
    const currentExternalId = esc(fil.external_id || '');
    const currentNozzle = fil.settings_extruder_temp != null ? fil.settings_extruder_temp : '';
    const currentBed = fil.settings_bed_temp != null ? fil.settings_bed_temp : '';
    const currentComment = esc(fil.comment || '');
    const currentVendorId = fil.vendor && fil.vendor.id != null ? String(fil.vendor.id) : '';
    const currentVendorName = esc(fil.vendor && fil.vendor.name ? fil.vendor.name : '');

    // Spoolman stores extra-field string values wrapped in literal quotes
    // (e.g. `"https://..."`). Strip them for display so the user edits the
    // inner value directly.
    const unquoteExtra = (v) => {
        if (v == null) return '';
        const s = String(v);
        if (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
        return s;
    };
    const rawExtra = fil.extra || {};
    const currentProductUrl = esc(unquoteExtra(rawExtra.product_url));
    const currentPurchaseUrl = esc(unquoteExtra(rawExtra.purchase_url));
    const currentSheetLink = esc(unquoteExtra(rawExtra.sheet_link));
    const currentOriginalColor = esc(unquoteExtra(rawExtra.original_color));

    // filament_attributes is a JSON-encoded list (e.g. '["Silk","Matte"]').
    // Render as a comma-separated string for a simple freeform editor; on
    // save we'll serialize back to a JSON array.
    let currentAttributes = '';
    const rawAttrs = rawExtra.filament_attributes;
    if (rawAttrs != null && rawAttrs !== '') {
        try {
            const parsed = typeof rawAttrs === 'string' ? JSON.parse(rawAttrs) : rawAttrs;
            if (Array.isArray(parsed)) currentAttributes = parsed.join(', ');
            else currentAttributes = String(parsed);
        } catch (_) {
            currentAttributes = String(rawAttrs).replace(/^"|"$/g, '');
        }
    }
    currentAttributes = esc(currentAttributes);
    // color_hex handling: Spoolman stores either a single 6-char hex, OR a comma-
    // separated list via `multi_color_hexes` extra. Parse both into a unified
    // array of normalized '#rrggbb' strings that the form can manage uniformly.
    const parseHexList = (val) => {
        if (!val) return [];
        return String(val)
            .split(',')
            .map(h => h.replace(/^#/, '').trim().toLowerCase())
            .filter(h => /^[0-9a-fA-F]{6}$/.test(h))
            .map(h => `#${h}`);
    };
    const multiHexList = parseHexList(fil.multi_color_hexes);
    const singleHexList = parseHexList(fil.color_hex);
    const currentColors = multiHexList.length > 0 ? multiHexList : singleHexList;
    const currentDirection = String(fil.multi_color_direction || (fil.extra && fil.extra.multi_color_direction) || 'longitudinal').toLowerCase();
    // Primary color for backwards-compat with the existing first-slot UI.
    const currentColorHex = currentColors[0] || '#000000';
    const hasColorHex = currentColors.length > 0;

    // Vendor's inherited empty_spool_weight surfaces as placeholder text so the
    // user sees the fallback value that would apply if this field is left blank.
    const vendorWt = fil.vendor && fil.vendor.empty_spool_weight
        ? Number(fil.vendor.empty_spool_weight) : null;
    const vendorWtHint = vendorWt ? ` (vendor: ${vendorWt}g)` : '';

    // Target the filament modal when it's actually shown so the Swal sits over it;
    // otherwise fall back to body (hidden modal keeps Swal from laying out).
    const filModalEl = document.getElementById('filamentModal');
    const filModalShown = filModalEl && filModalEl.classList.contains('show');
    Swal.fire({
        target: filModalShown ? filModalEl : document.body,
        title: `✏️ Edit Filament #${fil.id}`,
        html: `
            <div class="text-start">
                <div class="mb-2">
                    <label class="form-label text-light small mb-1">Color Name</label>
                    <input type="text" id="edit-fil-name" class="form-control bg-dark text-white border-secondary" value="${currentName}" autocomplete="off">
                </div>
                <div class="mb-2">
                    <label class="form-label text-light small mb-1">Material</label>
                    <input type="text" id="edit-fil-material" list="edit-fil-materials-dl" class="form-control bg-dark text-white border-secondary" value="${currentMaterial}" autocomplete="off" placeholder="PLA, PETG, ABS...">
                    <datalist id="edit-fil-materials-dl"></datalist>
                </div>
                <div class="row g-2">
                    <div class="col-8">
                        <label class="form-label text-light small mb-1">
                            Vendor
                            <span id="edit-fil-vendor-new-badge" class="badge bg-success ms-1" style="display:none; font-size:0.7rem;">+ NEW</span>
                        </label>
                        <input type="text" id="edit-fil-vendor-name" list="edit-fil-vendors-dl" class="form-control bg-dark text-white border-secondary" value="${currentVendorName}" autocomplete="off" placeholder="-- Generic --">
                        <datalist id="edit-fil-vendors-dl"></datalist>
                        <input type="hidden" id="edit-fil-vendor-id" value="${currentVendorId}">
                    </div>
                    <div class="col-4">
                        <label class="form-label text-light small mb-1">
                            Color(s)
                            <button type="button" id="edit-fil-add-color" class="btn btn-sm btn-outline-info ms-1 py-0 px-1" style="font-size:0.75rem;" title="Add another color">+</button>
                        </label>
                        <div class="d-flex align-items-center gap-1 mb-1">
                            <input type="color" id="edit-fil-color-picker" value="${currentColorHex}" class="form-control form-control-color bg-dark border-secondary" style="width:40px;padding:2px;">
                            <input type="text" id="edit-fil-color-hex" class="form-control bg-dark text-white border-secondary" value="${hasColorHex ? currentColorHex : ''}" placeholder="#rrggbb" maxlength="7" style="flex:1;">
                        </div>
                        <div id="edit-fil-color-extras"></div>
                        <select id="edit-fil-color-direction" class="form-select form-select-sm bg-dark text-white border-secondary mt-1" style="display:${currentColors.length > 1 ? 'block' : 'none'};">
                            <option value="longitudinal"${currentDirection === 'longitudinal' ? ' selected' : ''}>Longitudinal (length-wise)</option>
                            <option value="coaxial"${currentDirection === 'coaxial' ? ' selected' : ''}>Coaxial (radial)</option>
                        </select>
                    </div>
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-6">
                        <label class="form-label text-light small mb-1">Empty Spool Wt (g)${vendorWtHint}</label>
                        <input type="number" step="0.1" id="edit-fil-spool-weight" class="form-control bg-dark text-white border-secondary" value="${currentSpoolWt}" placeholder="${vendorWt || ''}" autocomplete="off">
                    </div>
                    <div class="col-6">
                        <label class="form-label text-light small mb-1">Density (g/cm³)</label>
                        <input type="number" step="0.01" id="edit-fil-density" class="form-control bg-dark text-white border-secondary" value="${currentDensity}" autocomplete="off">
                    </div>
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-6">
                        <label class="form-label text-light small mb-1">🔥 Nozzle (°C)</label>
                        <input type="number" id="edit-fil-nozzle" class="form-control bg-dark text-white border-secondary" value="${currentNozzle}" autocomplete="off">
                    </div>
                    <div class="col-6">
                        <label class="form-label text-light small mb-1">🛏️ Bed (°C)</label>
                        <input type="number" id="edit-fil-bed" class="form-control bg-dark text-white border-secondary" value="${currentBed}" autocomplete="off">
                    </div>
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-4">
                        <label class="form-label text-light small mb-1">Diameter (mm)</label>
                        <input type="number" step="0.01" id="edit-fil-diameter" class="form-control bg-dark text-white border-secondary" value="${currentDiameter}" placeholder="1.75" autocomplete="off">
                    </div>
                    <div class="col-4">
                        <label class="form-label text-light small mb-1">Net Weight (g)</label>
                        <input type="number" step="1" id="edit-fil-weight" class="form-control bg-dark text-white border-secondary" value="${currentWeight}" placeholder="1000" autocomplete="off">
                    </div>
                    <div class="col-4">
                        <label class="form-label text-light small mb-1">Price ($)</label>
                        <input type="number" step="0.01" id="edit-fil-price" class="form-control bg-dark text-white border-secondary" value="${currentPrice}" placeholder="0.00" autocomplete="off">
                    </div>
                </div>
                <div class="mt-2">
                    <label class="form-label text-light small mb-1">Notes</label>
                    <textarea id="edit-fil-comment" rows="2" class="form-control bg-dark text-white border-secondary">${currentComment}</textarea>
                </div>

                <!-- Advanced: URLs, tags, legacy ID. Collapsed by default to
                     keep the form scannable; the user expands only when editing
                     these less-common fields. Uses native <details> so no JS
                     wiring is required for the open/close behavior. -->
                <details class="mt-3 border-top border-secondary pt-2">
                    <summary class="text-info fw-bold" style="cursor:pointer; user-select:none;">
                        ⚙️ Advanced (URLs, tags, legacy ID)
                    </summary>
                    <div class="mt-2">
                        <div class="mb-2">
                            <label class="form-label text-light small mb-1">Original Color Name</label>
                            <input type="text" id="edit-fil-original-color" class="form-control bg-dark text-white border-secondary" value="${currentOriginalColor}" placeholder="e.g. Silk Gold" autocomplete="off">
                        </div>
                        <div class="mb-2">
                            <label class="form-label text-light small mb-1">Filament Attributes</label>
                            <input type="text" id="edit-fil-attributes" class="form-control bg-dark text-white border-secondary" value="${currentAttributes}" placeholder="Silk, Matte, Carbon Fiber...  (comma-separated)" autocomplete="off">
                            <div class="form-text text-muted" style="font-size:0.8rem;">Comma-separated tags. Stored in Spoolman as a JSON array.</div>
                        </div>
                        <div class="mb-2">
                            <label class="form-label text-light small mb-1">Product URL</label>
                            <input type="url" id="edit-fil-product-url" class="form-control bg-dark text-white border-secondary" value="${currentProductUrl}" placeholder="https://..." autocomplete="off">
                        </div>
                        <div class="mb-2">
                            <label class="form-label text-light small mb-1">Purchase URL</label>
                            <input type="url" id="edit-fil-purchase-url" class="form-control bg-dark text-white border-secondary" value="${currentPurchaseUrl}" placeholder="https://..." autocomplete="off">
                        </div>
                        <div class="mb-2">
                            <label class="form-label text-light small mb-1">Sheet / Reference Link</label>
                            <input type="url" id="edit-fil-sheet-link" class="form-control bg-dark text-white border-secondary" value="${currentSheetLink}" placeholder="https://..." autocomplete="off">
                        </div>
                        <div class="mb-1">
                            <label class="form-label text-light small mb-1">Legacy / External ID</label>
                            <input type="text" id="edit-fil-external-id" class="form-control bg-dark text-white border-secondary" value="${currentExternalId}" placeholder="(optional)" autocomplete="off">
                        </div>
                    </div>
                </details>
            </div>
        `,
        background: '#1e1e1e',
        color: '#fff',
        showCancelButton: true,
        confirmButtonColor: '#ffc107',
        confirmButtonText: 'Save',
        focusConfirm: false,
        didOpen: () => {
            const popup = Swal.getPopup();
            const nameEl = popup.querySelector('#edit-fil-name');
            if (nameEl) nameEl.focus();

            // Populate vendor datalist and wire the searchable input. Typing a
            // name that matches an existing vendor sets the hidden vendor-id;
            // typing a name that doesn't match sets vendor-id='' and shows a
            // "+ NEW" badge so the user knows we're about to create a vendor.
            const vendorNameEl = popup.querySelector('#edit-fil-vendor-name');
            const vendorIdEl = popup.querySelector('#edit-fil-vendor-id');
            const vendorDl = popup.querySelector('#edit-fil-vendors-dl');
            const vendorNewBadge = popup.querySelector('#edit-fil-vendor-new-badge');
            // Cache the fetched vendors list so the input handler can look up IDs.
            let vendorCache = [];
            const refreshVendorBadge = () => {
                const typed = (vendorNameEl.value || '').trim();
                if (!typed) {
                    vendorIdEl.value = '';
                    vendorNewBadge.style.display = 'none';
                    return;
                }
                const match = vendorCache.find(v => (v.name || '').toLowerCase() === typed.toLowerCase());
                if (match) {
                    vendorIdEl.value = String(match.id);
                    vendorNewBadge.style.display = 'none';
                } else {
                    vendorIdEl.value = '';
                    vendorNewBadge.style.display = 'inline-block';
                }
            };
            fetch('/api/vendors')
                .then((r) => r.json())
                .then((d) => {
                    if (!d || !d.success) return;
                    vendorCache = d.vendors || [];
                    vendorDl.innerHTML = vendorCache
                        .map(v => `<option value="${esc(v.name)}"></option>`)
                        .join('');
                    refreshVendorBadge();
                })
                .catch(() => { /* fail open — user can still type a new name */ });
            if (vendorNameEl) vendorNameEl.addEventListener('input', refreshVendorBadge);

            // Populate material datalist. No hidden id needed — Spoolman's
            // material is a free-text field, the datalist just offers known
            // values as autocomplete hints.
            fetch('/api/materials')
                .then((r) => r.json())
                .then((d) => {
                    const dl = popup.querySelector('#edit-fil-materials-dl');
                    if (!dl || !d || !d.success) return;
                    const mats = Array.isArray(d.materials) ? d.materials : [];
                    dl.innerHTML = mats
                        .map(m => `<option value="${esc(m)}"></option>`)
                        .join('');
                })
                .catch(() => { /* non-fatal */ });

            // --- Color pickers -------------------------------------------------
            // Helper: wire a (picker, hex) input pair so changes in one mirror the
            // other, with hex-format validation on blur. Used for the primary
            // color and every extra-color row added via the + button.
            const wirePickerHexPair = (pickerEl, hexEl) => {
                if (!pickerEl || !hexEl) return;
                pickerEl.addEventListener('input', () => { hexEl.value = pickerEl.value; });
                hexEl.addEventListener('input', () => {
                    const v = hexEl.value.trim();
                    if (/^#[0-9a-fA-F]{6}$/.test(v)) pickerEl.value = v.toLowerCase();
                });
                hexEl.addEventListener('blur', () => {
                    const raw = hexEl.value.trim().replace(/^#/, '');
                    if (raw === '') return;
                    if (/^[0-9a-fA-F]{6}$/.test(raw)) {
                        hexEl.value = `#${raw.toLowerCase()}`;
                        pickerEl.value = `#${raw.toLowerCase()}`;
                    }
                });
            };

            wirePickerHexPair(
                popup.querySelector('#edit-fil-color-picker'),
                popup.querySelector('#edit-fil-color-hex'),
            );

            // Multi-color: add-row button appends (picker, hex, remove) triples.
            // We count rows so each row gets a unique id. Color-direction select
            // shows up only when >=2 colors exist.
            const extrasHost = popup.querySelector('#edit-fil-color-extras');
            const directionSel = popup.querySelector('#edit-fil-color-direction');
            let colorRowSeq = 0;

            const refreshDirectionVisibility = () => {
                const extraRows = extrasHost ? extrasHost.querySelectorAll('.edit-fil-color-row').length : 0;
                if (directionSel) directionSel.style.display = extraRows > 0 ? 'block' : 'none';
            };

            const addColorRow = (hexInit = '#000000') => {
                colorRowSeq += 1;
                const idx = colorRowSeq;
                const row = document.createElement('div');
                row.className = 'd-flex align-items-center gap-1 mb-1 edit-fil-color-row';
                row.dataset.idx = String(idx);
                row.innerHTML = `
                    <input type="color" id="edit-fil-color-picker-${idx}" value="${hexInit}" class="form-control form-control-color bg-dark border-secondary" style="width:40px;padding:2px;">
                    <input type="text" id="edit-fil-color-hex-${idx}" class="form-control bg-dark text-white border-secondary" value="${hexInit}" placeholder="#rrggbb" maxlength="7" style="flex:1;">
                    <button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" style="font-size:0.85rem;" title="Remove">🗑️</button>
                `;
                extrasHost.appendChild(row);
                wirePickerHexPair(
                    row.querySelector(`#edit-fil-color-picker-${idx}`),
                    row.querySelector(`#edit-fil-color-hex-${idx}`),
                );
                row.querySelector('button').addEventListener('click', () => {
                    row.remove();
                    refreshDirectionVisibility();
                });
                refreshDirectionVisibility();
            };

            // Seed extras with the filament's existing additional colors (idx 1+).
            // currentColors is captured from the enclosing function scope.
            currentColors.slice(1).forEach(hx => addColorRow(hx));

            const addBtn = popup.querySelector('#edit-fil-add-color');
            if (addBtn) addBtn.addEventListener('click', () => addColorRow('#000000'));
        },
        preConfirm: () => {
            const val = (id) => Swal.getPopup().querySelector(id)?.value;
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
            // Vendor handling:
            //   - Hidden vendor_id is set when the typed name matches an existing
            //     vendor (handled by refreshVendorBadge on input).
            //   - Empty name → null vendor_id (generic).
            //   - Typed name with no match → pendingNewVendorName, resolved to
            //     a real vendor_id by the .then() handler BEFORE POSTing the
            //     filament update.
            const vendorTyped = (val('#edit-fil-vendor-name') || '').trim();
            const vendorIdRaw = val('#edit-fil-vendor-id');
            let vendorId;
            let pendingNewVendorName = null;
            if (!vendorTyped) {
                vendorId = null;
            } else if (vendorIdRaw) {
                vendorId = Number(vendorIdRaw);
            } else {
                // New vendor — we'll create it in the .then() handler.
                vendorId = undefined; // sentinel: "TBD, create then patch"
                pendingNewVendorName = vendorTyped;
            }

            // Colors: collect the primary + every extra row. Validate each hex;
            // any invalid input blocks the save with a validation message.
            const popup = Swal.getPopup();
            const primaryRaw = (val('#edit-fil-color-hex') || '').trim().replace(/^#/, '');
            const extraEls = popup.querySelectorAll('#edit-fil-color-extras input[id^="edit-fil-color-hex-"]');
            const rawColors = [];
            if (primaryRaw !== '') rawColors.push(primaryRaw);
            extraEls.forEach(el => {
                const v = (el.value || '').trim().replace(/^#/, '');
                if (v !== '') rawColors.push(v);
            });
            for (const c of rawColors) {
                if (!/^[0-9a-fA-F]{6}$/.test(c)) {
                    Swal.showValidationMessage(`Color must be a 6-digit hex (got "${c}").`);
                    return false;
                }
            }
            const normalizedColors = rawColors.map(c => c.toLowerCase());
            // Spoolman stores single color in `color_hex` and multi-color gradients
            // in `multi_color_hexes` (comma-separated). Match that layout:
            //   - 0 colors  → clear both
            //   - 1 color   → set color_hex, clear multi
            //   - 2+ colors → set multi_color_hexes + direction, leave color_hex as first
            let colorHex = null;
            let multiColorHexes = null;
            let multiDirection = null;
            if (normalizedColors.length === 0) {
                colorHex = '';
                multiColorHexes = '';
            } else if (normalizedColors.length === 1) {
                colorHex = normalizedColors[0];
                multiColorHexes = '';
            } else {
                colorHex = normalizedColors[0];
                multiColorHexes = normalizedColors.join(',');
                multiDirection = (val('#edit-fil-color-direction') || 'longitudinal').toLowerCase();
            }

            // Advanced-section extras. Spoolman PATCH replaces the entire
            // `extra` object, so we must MERGE with the filament's existing
            // extras before sending — writing just our keys would wipe
            // physical_source, price_total, and anything else Spoolman set.
            const newProductUrl = (val('#edit-fil-product-url') || '').trim();
            const newPurchaseUrl = (val('#edit-fil-purchase-url') || '').trim();
            const newSheetLink = (val('#edit-fil-sheet-link') || '').trim();
            const newOriginalColor = (val('#edit-fil-original-color') || '').trim();
            const rawAttrsText = (val('#edit-fil-attributes') || '').trim();
            // Parse comma-separated tags into an array; empty string → empty array.
            const attrsArr = rawAttrsText
                ? rawAttrsText.split(',').map(t => t.trim()).filter(Boolean)
                : [];

            // Detect which extra fields changed so we know whether to include
            // the merged extra object in the PATCH. If nothing extra changed,
            // we skip `extra` entirely and leave everything else alone.
            const extraChanges = {};
            if (newProductUrl !== unquoteExtra(rawExtra.product_url)) extraChanges.product_url = newProductUrl;
            if (newPurchaseUrl !== unquoteExtra(rawExtra.purchase_url)) extraChanges.purchase_url = newPurchaseUrl;
            if (newSheetLink !== unquoteExtra(rawExtra.sheet_link)) extraChanges.sheet_link = newSheetLink;
            if (newOriginalColor !== unquoteExtra(rawExtra.original_color)) extraChanges.original_color = newOriginalColor;
            // filament_attributes: compare rendered arrays so order changes
            // register but a trailing-space-only edit doesn't.
            const prevAttrsArr = (() => {
                try {
                    const p = typeof rawExtra.filament_attributes === 'string'
                        ? JSON.parse(rawExtra.filament_attributes)
                        : rawExtra.filament_attributes;
                    return Array.isArray(p) ? p.map(String).map(s => s.trim()).filter(Boolean) : [];
                } catch (_) { return []; }
            })();
            if (JSON.stringify(attrsArr) !== JSON.stringify(prevAttrsArr)) {
                extraChanges.filament_attributes = attrsArr;
            }

            const data = {
                name: (val('#edit-fil-name') || '').trim() || null,
                material: (val('#edit-fil-material') || '').trim() || null,
                vendor_id: vendorId,
                color_hex: colorHex,
                multi_color_hexes: multiColorHexes,
                multi_color_direction: multiDirection,
                spool_weight: numOrNull('#edit-fil-spool-weight'),
                density: numOrNull('#edit-fil-density'),
                diameter: numOrNull('#edit-fil-diameter'),
                weight: numOrNull('#edit-fil-weight'),
                price: numOrNull('#edit-fil-price'),
                external_id: (val('#edit-fil-external-id') || '').trim(),
                settings_extruder_temp: intOrNull('#edit-fil-nozzle'),
                settings_bed_temp: intOrNull('#edit-fil-bed'),
                comment: val('#edit-fil-comment') || '',
                // These two ride along so the .then() handler can surface them
                // as dirty-diff entries + resolve the pending-new-vendor case.
                _extraChanges: extraChanges,
                _pendingNewVendorName: pendingNewVendorName,
            };
            // Strip unchanged fields so we don't POST no-ops. This matches the
            // edit_spool_wizard dirty-diff convention and keeps Activity Log
            // messages accurate ("edited: spool_weight" vs "edited: 7 fields").
            const changed = {};
            const same = (a, b) => {
                if (a == null && (b == null || b === '')) return true;
                if (b == null && (a == null || a === '')) return true;
                return String(a) === String(b);
            };
            if (!same(data.name, fil.name)) changed.name = data.name;
            if (!same(data.material, fil.material)) changed.material = data.material;
            // vendor_id: compare numeric ID against the nested vendor object's id.
            const oldVendorId = fil.vendor && fil.vendor.id != null ? fil.vendor.id : null;
            if (!same(data.vendor_id, oldVendorId)) changed.vendor_id = data.vendor_id;
            // color_hex: normalize both sides to lowercase-no-hash for comparison.
            const oldHex = (fil.color_hex || '').replace(/^#/, '').toLowerCase();
            const newHex = (data.color_hex || '').toLowerCase();
            if (oldHex !== newHex) changed.color_hex = data.color_hex;
            // Multi-color fields: compare normalized lowercase CSVs. Only include
            // direction in the diff when the CSV actually has 2+ entries.
            const oldMulti = String(fil.multi_color_hexes || '')
                .split(',').map(h => h.replace(/^#/, '').trim().toLowerCase())
                .filter(Boolean).join(',');
            const newMulti = String(data.multi_color_hexes || '').toLowerCase();
            if (oldMulti !== newMulti) changed.multi_color_hexes = data.multi_color_hexes;
            if (data.multi_color_direction != null) {
                const oldDir = String(fil.multi_color_direction || (fil.extra && fil.extra.multi_color_direction) || '').toLowerCase();
                if (oldDir !== data.multi_color_direction) {
                    changed.multi_color_direction = data.multi_color_direction;
                }
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

            // Extra-fields merge. If any advanced field changed, build a NEW
            // extra object that preserves every pre-existing key and only
            // overrides the ones we touched. Spoolman replaces extra wholesale
            // on PATCH, so skipping this merge would silently delete keys.
            const dirtyExtras = data._extraChanges || {};
            if (Object.keys(dirtyExtras).length > 0) {
                const mergedExtra = { ...(fil.extra || {}) };
                for (const [k, v] of Object.entries(dirtyExtras)) {
                    if (k === 'filament_attributes') {
                        // Spoolman's field schema stores this as a JSON-encoded string.
                        mergedExtra[k] = JSON.stringify(v);
                    } else if (v === '' || v == null) {
                        // Clearing a URL/original_color etc. → remove the key entirely.
                        delete mergedExtra[k];
                    } else {
                        // Spoolman's "string extras" convention is quote-wrapped.
                        mergedExtra[k] = `"${String(v)}"`;
                    }
                }
                changed.extra = mergedExtra;
            }

            // Carry the pending-new-vendor name forward for the .then() handler.
            // It's not a field Spoolman cares about, just a hint for our caller.
            if (data._pendingNewVendorName) {
                changed.__pendingNewVendorName = data._pendingNewVendorName;
            }
            return changed;
        },
    }).then(async (res) => {
        if (!res.isConfirmed) return;
        const dirty = res.value || {};
        // Pull the vendor-pending hint off before length-checking — it's internal,
        // not a real dirty-diff entry.
        const pendingNewVendor = dirty.__pendingNewVendorName;
        delete dirty.__pendingNewVendorName;

        if (Object.keys(dirty).length === 0 && !pendingNewVendor) {
            showToast('No changes to save.', 'info');
            return;
        }

        // If the user typed a new vendor name, create it first so we have a real
        // vendor_id to PATCH onto the filament. Failure here aborts the update
        // entirely — rather than silently drop the vendor change.
        if (pendingNewVendor) {
            try {
                const vr = await fetch('/api/vendors', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: pendingNewVendor }),
                });
                const vd = await vr.json();
                if (vd && vd.success && vd.vendor && vd.vendor.id != null) {
                    dirty.vendor_id = Number(vd.vendor.id);
                } else {
                    showToast(
                        `Couldn't create vendor "${pendingNewVendor}": ${(vd && vd.msg) || 'unknown'}`,
                        'error', 7000,
                    );
                    return;
                }
            } catch (e) {
                showToast(`Vendor create error: ${e.message || e}`, 'error', 7000);
                return;
            }
        }

        try {
            const r = await fetch('/api/update_filament', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: fil.id, data: dirty }),
            });
            const d = await r.json();
            if (d && d.success) {
                showToast(`Filament #${fil.id} updated.`, 'success');
                if (window.refreshFilamentSpools) window.refreshFilamentSpools();
            } else {
                showToast(`Update failed: ${d && d.msg ? d.msg : 'unknown'}`, 'error', 7000);
            }
        } catch (e) {
            showToast(`Update error: ${e.message || e}`, 'error', 7000);
        }
    });
};