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


// --- Edit Filament (Bootstrap modal) ---
// Promoted from SweetAlert to a real Bootstrap modal on 2026-04-23 so multi-
// color filaments and the advanced-extras section no longer overflow the
// viewport. Uses tabs to keep each pane at a reasonable height, and the
// modal's scrollable body handles overflow at the viewport level.
//
// Same public API as the old Swal version: window.openEditFilamentForm(fil)
// opens the modal populated from the filament. Save fires a dirty-diff POST
// to /api/update_filament (plus a POST /api/vendors if a new vendor name
// was typed first).
window.openEditFilamentForm = (fil) => {
    if (!fil || !fil.id) { showToast('Missing filament data', 'error'); return; }

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
    let currentAttributes = '';
    const rawAttrs = rawExtra.filament_attributes;
    if (rawAttrs != null && rawAttrs !== '') {
        try {
            const parsed = typeof rawAttrs === 'string' ? JSON.parse(rawAttrs) : rawAttrs;
            currentAttributes = Array.isArray(parsed) ? parsed.join(', ') : String(parsed);
        } catch (_) {
            currentAttributes = String(rawAttrs).replace(/^"|"$/g, '');
        }
    }

    const modalEl = document.getElementById('editFilamentModal');
    if (!modalEl) { showToast('Edit Filament modal missing', 'error'); return; }
    const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);

    // --- Populate fields ---
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val == null ? '' : val; };
    modalEl.querySelector('#editFilamentModalLabel').innerText = `✏️ Edit Filament #${fil.id}`;
    setVal('editfil-name', fil.name || '');
    setVal('editfil-material', fil.material || 'PLA');
    setVal('editfil-spool-weight', fil.spool_weight != null ? fil.spool_weight : '');
    setVal('editfil-density', fil.density != null ? fil.density : '');
    setVal('editfil-diameter', fil.diameter != null ? fil.diameter : '');
    setVal('editfil-weight', fil.weight != null ? fil.weight : '');
    setVal('editfil-price', fil.price != null ? fil.price : '');
    setVal('editfil-nozzle', fil.settings_extruder_temp != null ? fil.settings_extruder_temp : '');
    setVal('editfil-bed', fil.settings_bed_temp != null ? fil.settings_bed_temp : '');
    setVal('editfil-comment', fil.comment || '');
    setVal('editfil-external-id', fil.external_id || '');
    setVal('editfil-vendor-name', currentVendorName);
    setVal('editfil-vendor-id', currentVendorId);
    setVal('editfil-product-url', currentProductUrl);
    setVal('editfil-purchase-url', currentPurchaseUrl);
    setVal('editfil-sheet-link', currentSheetLink);
    setVal('editfil-original-color', currentOriginalColor);
    setVal('editfil-attributes', currentAttributes);

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

    // --- Colors tab: primary picker + dynamic extras ---
    const picker = document.getElementById('editfil-color-picker');
    const hex = document.getElementById('editfil-color-hex');
    const primaryHex = currentColors[0] || '#000000';
    if (picker) picker.value = primaryHex;
    if (hex) hex.value = currentColors.length > 0 ? primaryHex : '';

    const wirePickerHexPair = (pickerEl, hexEl) => {
        if (!pickerEl || !hexEl) return;
        pickerEl.oninput = () => { hexEl.value = pickerEl.value; };
        hexEl.oninput = () => {
            const v = hexEl.value.trim();
            if (/^#[0-9a-fA-F]{6}$/.test(v)) pickerEl.value = v.toLowerCase();
        };
        hexEl.onblur = () => {
            const raw = hexEl.value.trim().replace(/^#/, '');
            if (raw === '') return;
            if (/^[0-9a-fA-F]{6}$/.test(raw)) {
                hexEl.value = `#${raw.toLowerCase()}`;
                pickerEl.value = `#${raw.toLowerCase()}`;
            }
        };
    };
    wirePickerHexPair(picker, hex);

    const extrasHost = document.getElementById('editfil-color-extras');
    const directionSel = document.getElementById('editfil-color-direction');
    const directionWrap = document.getElementById('editfil-direction-wrap');
    if (extrasHost) extrasHost.innerHTML = '';
    if (directionSel) directionSel.value = currentDirection;
    const refreshDirectionVisibility = () => {
        const extraCount = extrasHost ? extrasHost.querySelectorAll('.editfil-color-row').length : 0;
        if (directionWrap) directionWrap.style.display = extraCount > 0 ? 'block' : 'none';
    };
    const renumberRows = () => {
        // Primary is always slot 1. Extras get 2, 3, 4, ... in DOM order.
        const rows = extrasHost ? extrasHost.querySelectorAll('.editfil-color-row') : [];
        rows.forEach((r, i) => {
            const badge = r.querySelector('[data-role="num"]');
            if (badge) badge.innerText = String(i + 2);
        });
    };
    let colorRowSeq = 0;
    const addColorRow = (hexInit) => {
        const safeInit = hexInit || '#000000';
        colorRowSeq += 1;
        const idx = colorRowSeq;
        const row = document.createElement('div');
        row.className = 'd-flex align-items-center gap-2 mb-2 editfil-color-row';
        row.dataset.idx = String(idx);
        row.innerHTML = `
            <span class="badge bg-info text-dark" style="min-width:36px;" data-role="num">2</span>
            <input type="color" id="editfil-color-picker-${idx}" value="${safeInit}" class="form-control form-control-color bg-black border-secondary" style="width:50px; padding:2px;">
            <input type="text" id="editfil-color-hex-${idx}" class="form-control bg-black text-white border-secondary" value="${safeInit}" placeholder="#rrggbb" maxlength="7" style="flex:1;">
            <button type="button" class="btn btn-outline-danger btn-sm" title="Remove">🗑️</button>
        `;
        extrasHost.appendChild(row);
        wirePickerHexPair(
            row.querySelector(`#editfil-color-picker-${idx}`),
            row.querySelector(`#editfil-color-hex-${idx}`),
        );
        row.querySelector('button').onclick = () => {
            row.remove();
            renumberRows();
            refreshDirectionVisibility();
        };
        renumberRows();
        refreshDirectionVisibility();
    };
    currentColors.slice(1).forEach(hx => addColorRow(hx));
    const addBtn = document.getElementById('editfil-add-color');
    if (addBtn) addBtn.onclick = () => addColorRow('#000000');

    // --- Material + Vendor datalists ---
    // Material: browser-native autocomplete from known materials.
    fetch('/api/materials').then(r => r.json()).then(d => {
        const dl = document.getElementById('editfil-mat-dl');
        if (!dl || !d || !d.success) return;
        const mats = Array.isArray(d.materials) ? d.materials : [];
        dl.innerHTML = mats.map(m => `<option value="${esc(m)}"></option>`).join('');
    }).catch(() => {});

    // Vendor: datalist + hidden id + "+ NEW" badge when typed name is unknown.
    let vendorCache = [];
    const vendorNameEl = document.getElementById('editfil-vendor-name');
    const vendorIdEl = document.getElementById('editfil-vendor-id');
    const vendorDl = document.getElementById('editfil-vendor-dl');
    const vendorNewBadge = document.getElementById('editfil-vendor-new-badge');
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
    if (vendorNameEl) vendorNameEl.oninput = refreshVendorBadge;
    fetch('/api/vendors').then(r => r.json()).then(d => {
        if (!d || !d.success) return;
        vendorCache = d.vendors || [];
        if (vendorDl) {
            vendorDl.innerHTML = vendorCache.map(v => `<option value="${esc(v.name)}"></option>`).join('');
        }
        refreshVendorBadge();
    }).catch(() => {});

    // --- Save button handler ---
    // Replace the button to detach any prior click handler so repeated
    // openings don't stack. (The modal element is reused across calls.)
    const oldSaveBtn = document.getElementById('editfil-save');
    if (!oldSaveBtn) { showToast('Save button missing', 'error'); return; }
    const saveBtn = oldSaveBtn.cloneNode(true);
    oldSaveBtn.parentNode.replaceChild(saveBtn, oldSaveBtn);

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
        const showErr = (msg) => {
            const e = document.getElementById('editfil-error');
            if (e) { e.classList.remove('d-none'); e.innerText = msg; }
        };
        const clearErr = () => {
            const e = document.getElementById('editfil-error');
            if (e) { e.classList.add('d-none'); e.innerText = ''; }
        };
        clearErr();

        // Collect colors — primary + every extra.
        const primaryRaw = (val('editfil-color-hex') || '').trim().replace(/^#/, '');
        const extraEls = modalEl.querySelectorAll('#editfil-color-extras input[id^="editfil-color-hex-"]');
        const rawColors = [];
        if (primaryRaw !== '') rawColors.push(primaryRaw);
        extraEls.forEach(el => {
            const v = (el.value || '').trim().replace(/^#/, '');
            if (v !== '') rawColors.push(v);
        });
        for (const c of rawColors) {
            if (!/^[0-9a-fA-F]{6}$/.test(c)) {
                showErr(`Color must be a 6-digit hex (got "${c}").`);
                const colorsTabBtn = document.getElementById('editfil-tab-colors-btn');
                if (colorsTabBtn) bootstrap.Tab.getOrCreateInstance(colorsTabBtn).show();
                return;
            }
        }
        const normalizedColors = rawColors.map(c => c.toLowerCase());
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

        // Advanced-section extras. Spoolman PATCH replaces the entire `extra`
        // object, so MERGE with fil.extra — writing just our keys would wipe
        // physical_source, price_total, and anything else Spoolman set.
        const newProductUrl = (val('editfil-product-url') || '').trim();
        const newPurchaseUrl = (val('editfil-purchase-url') || '').trim();
        const newSheetLink = (val('editfil-sheet-link') || '').trim();
        const newOriginalColor = (val('editfil-original-color') || '').trim();
        const rawAttrsText = (val('editfil-attributes') || '').trim();
        const attrsArr = rawAttrsText
            ? rawAttrsText.split(',').map(t => t.trim()).filter(Boolean)
            : [];
        const dirtyExtras = {};
        if (newProductUrl !== unquoteExtra(rawExtra.product_url)) dirtyExtras.product_url = newProductUrl;
        if (newPurchaseUrl !== unquoteExtra(rawExtra.purchase_url)) dirtyExtras.purchase_url = newPurchaseUrl;
        if (newSheetLink !== unquoteExtra(rawExtra.sheet_link)) dirtyExtras.sheet_link = newSheetLink;
        if (newOriginalColor !== unquoteExtra(rawExtra.original_color)) dirtyExtras.original_color = newOriginalColor;
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

        // Assemble the full edit payload, then prune to a dirty-diff.
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
        const oldHex = (fil.color_hex || '').replace(/^#/, '').toLowerCase();
        const newHex = (data.color_hex || '').toLowerCase();
        if (oldHex !== newHex) changed.color_hex = data.color_hex;
        const oldMulti = String(fil.multi_color_hexes || '')
            .split(',').map(h => h.replace(/^#/, '').trim().toLowerCase())
            .filter(Boolean).join(',');
        const newMulti = String(data.multi_color_hexes || '').toLowerCase();
        if (oldMulti !== newMulti) changed.multi_color_hexes = data.multi_color_hexes;
        if (data.multi_color_direction != null) {
            const oldDir = String(fil.multi_color_direction
                || (fil.extra && fil.extra.multi_color_direction)
                || '').toLowerCase();
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

        if (Object.keys(changed).length === 0 && !pendingNewVendorName) {
            showToast('No changes to save.', 'info');
            bsModal.hide();
            return;
        }

        // Disable the button while the request is in flight so double-clicks
        // don't fire two PATCHes.
        saveBtn.disabled = true;
        try {
            if (pendingNewVendorName) {
                const vr = await fetch('/api/vendors', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: pendingNewVendorName }),
                });
                const vd = await vr.json();
                if (vd && vd.success && vd.vendor && vd.vendor.id != null) {
                    changed.vendor_id = Number(vd.vendor.id);
                } else {
                    showErr(`Couldn't create vendor "${pendingNewVendorName}": ${(vd && vd.msg) || 'unknown'}`);
                    return;
                }
            }
            const r = await fetch('/api/update_filament', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: fil.id, data: changed }),
            });
            const d = await r.json();
            if (d && d.success) {
                showToast(`Filament #${fil.id} updated.`, 'success');
                if (window.refreshFilamentSpools) window.refreshFilamentSpools();
                bsModal.hide();
            } else {
                showErr(`Update failed: ${d && d.msg ? d.msg : 'unknown'}`);
            }
        } catch (e) {
            showErr(`Update error: ${e.message || e}`);
        } finally {
            saveBtn.disabled = false;
        }
    };

    bsModal.show();
};
