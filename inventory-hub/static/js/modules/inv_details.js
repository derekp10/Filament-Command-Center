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
            }

            // --- NEW: Fetch Associated Spools for this Filament ---
            const listContainer = document.getElementById('fil-spools-list');
            const countBadge = document.getElementById('fil-spool-count');
            const btnQueueAll = document.getElementById('btn-queue-all-spools');

            // Only run if the HTML element exists (safety check)
            if (listContainer) {
                if (!silent) listContainer.innerHTML = "<div class='p-2 text-muted text-center small'>Checking inventory...</div>";

                fetch(`/api/spools_by_filament?id=${fid}`)
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
                                <span class="text-muted me-2">|</span> 
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
                            listContainer.innerHTML = "<div class='p-2 text-muted text-center small'>No active spools found.</div>";
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
            let optionsHtml = '<option value="">-- Unassigned --</option>';
            if (Array.isArray(locs)) {
                locs.forEach(l => {
                    const type = (l.Type || '').toLowerCase();
                    if (type.includes('mmu') || type.includes('tool') || type.includes('direct load') || type === 'virtual') return;
                    if (l.LocationID === 'Unassigned') return;
                    
                    const isSelected = l.LocationID === defaultLoc ? 'selected' : '';
                    optionsHtml += `<option value="${l.LocationID}" ${isSelected}>${l.Name} (${l.LocationID})</option>`;
                });
            }

            Swal.fire({
                target: document.getElementById('spoolModal') || document.body,
                title: 'Force Location Override',
                html: `
                    <div class="text-start">
                        <label class="form-label text-warning small mb-1">Select New Location</label>
                        <select id="swal-override-loc" class="form-select bg-dark text-white border-warning">
                            ${optionsHtml}
                        </select>
                        <small class="text-muted mt-2 d-block">
                            Bypasses scanning protocols to forcefully move the spool in the database.
                        </small>
                    </div>
                `,
                showCancelButton: true,
                confirmButtonColor: '#ffaa00',
                background: '#1e1e1e',
                color: '#fff',
                confirmButtonText: 'Force Move',
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