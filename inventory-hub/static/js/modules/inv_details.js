/* MODULE: DETAILS (Spool & Filament Modals) */
console.log("🚀 Loaded Module: DETAILS");

const openSpoolDetails = (id, silent=false) => {
    if(!silent) setProcessing(true);
    fetch(`/api/spool_details?id=${id}`)
    .then(r => r.json())
    .then(d => {
        if(!silent) setProcessing(false);
        if (!d || !d.id) { showToast("Details Data Missing!", "error"); return; }
        
        // Fill Modal
        document.getElementById('detail-id').innerText = d.id;
        document.getElementById('detail-material').innerText = d.filament?.material || "Unknown";
        document.getElementById('detail-vendor').innerText = d.filament?.vendor?.name || "Unknown";
        document.getElementById('detail-weight').innerText = (d.filament?.weight || 0) + "g";
        
        const used = d.used_weight !== null ? d.used_weight : 0;
        const rem = d.remaining_weight !== null ? d.remaining_weight : 0;
        document.getElementById('detail-used').innerText = Number(used).toFixed(1) + "g";
        document.getElementById('detail-remaining').innerText = Number(rem).toFixed(1) + "g";
        
        document.getElementById('detail-color-name').innerText = d.filament?.name || "Unknown";
        document.getElementById('detail-hex').innerText = (d.filament?.color_hex || "").toUpperCase();
        document.getElementById('detail-comment').value = d.comment || "";
        
        const swatch = document.getElementById('detail-swatch');
        if(swatch) swatch.style.backgroundColor = "#" + (d.filament?.color_hex || "333");
        
        // Link Logic
        const btnLink = document.getElementById('btn-open-spoolman');
        if (btnLink) {
            if (typeof SPOOLMAN_URL !== 'undefined' && SPOOLMAN_URL) {
                const baseUrl = SPOOLMAN_URL.endsWith('/') ? SPOOLMAN_URL.slice(0, -1) : SPOOLMAN_URL;
                btnLink.href = `${baseUrl}/spool/show/${d.id}`;
            } else btnLink.href = `/spool/show/${d.id}`;
        }
        
        // Swatch Link
        const btnSwatch = document.getElementById('btn-spool-to-filament');
        if (btnSwatch) {
            if(d.filament) {
                btnSwatch.onclick = () => { modals.spoolModal.hide(); openFilamentDetails(d.filament.id); };
                btnSwatch.style.display = 'inline-block';
            } else btnSwatch.style.display = 'none';
        }
        
        // [ALEX FIX] Use Shared Gradient Style
        if(swatch) {
            // We use 'background' (not backgroundColor) to support gradients
            const styles = getFilamentStyle(d.filament?.color_hex || "333");
            swatch.style.background = styles.frame;
        }
        
        if(!silent && modals.spoolModal) modals.spoolModal.show();
    })
    .catch(e => { if(!silent) setProcessing(false); console.error(e); showToast("Connection/Data Error", "error"); });
};

const openFilamentDetails = (fid, silent=false) => {
    if(!silent) setProcessing(true);
    // 1. Fetch Filament Details
    fetch(`/api/filament_details?id=${fid}`)
    .then(r => r.json())
    .then(d => {
        if (!d || !d.id) { if(!silent) setProcessing(false); showToast("Filament Data Missing!", "error"); return; }
        
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
        // [ALEX FIX] Use Shared Gradient Style
        if(swatch) {
            const styles = getFilamentStyle(d.color_hex || "333");
            swatch.style.background = styles.frame;
        }
        
        // Link to Spoolman
        const btnLink = document.getElementById('btn-fil-open-spoolman');
        if (btnLink) {
            const baseUrl = (typeof SPOOLMAN_URL !== 'undefined' && SPOOLMAN_URL) ? SPOOLMAN_URL : "";
            btnLink.href = baseUrl ? `${baseUrl.replace(/\/$/, "")}/filament/show/${d.id}` : `/filament/show/${d.id}`;
        }

        // Action: Queue Swatch Label
        const btnQueueSwatch = document.getElementById('btn-fil-print-action');
        if(btnQueueSwatch) {
            btnQueueSwatch.onclick = () => {
                addToQueue({ id: d.id, type: 'filament', display: d.name });
            };
        }

        // --- NEW: Fetch Associated Spools for this Filament ---
        const listContainer = document.getElementById('fil-spools-list');
        const countBadge = document.getElementById('fil-spool-count');
        const btnQueueAll = document.getElementById('btn-queue-all-spools');
        
        // Only run if the HTML element exists (safety check)
        if(listContainer) {
            if(!silent) listContainer.innerHTML = "<div class='p-2 text-muted text-center small'>Checking inventory...</div>";
            
            fetch(`/api/spools_by_filament?id=${fid}`)
            .then(r => r.json())
            .then(spools => {
                if(!silent) setProcessing(false); // Done loading
                listContainer.innerHTML = "";
                
                if (Array.isArray(spools) && spools.length > 0) {
                    if(countBadge) countBadge.innerText = spools.length;
                    
                    // Render List
                    spools.forEach(s => {
                        const remaining = s.remaining_weight ? Math.round(s.remaining_weight) : 0;
                        const location = s.extra?.location || "No Loc"; 
                        
                        const row = document.createElement('div');
                        row.className = "list-group-item bg-dark text-white border-secondary d-flex justify-content-between align-items-center p-2 small";
                        
                        // Updated Layout with "Add to Buffer" Button
                        row.innerHTML = `
                            <div class="d-flex align-items-center">
                                <span class="text-info fw-bold me-2">ID: ${s.id}</span> 
                                <span class="text-muted me-2">|</span> 
                                <span>${remaining}g</span>
                            </div>
                            <div class="d-flex align-items-center">
                                <span class="badge bg-secondary me-2">${location}</span>
                                <button class="btn btn-sm btn-outline-success py-0 px-2" 
                                    onclick="window.addSpoolToBuffer(${s.id})" 
                                    title="Add to Buffer">
                                    📥
                                </button>
                            </div>
                        `;
                        
                        listContainer.appendChild(row);
                    });

                    // Enable "Queue All" Button
                    if(btnQueueAll) {
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
                            if(added > 0) {
                                showToast(`Queued ${added} spools!`);
                                // Close this modal and open the queue to confirm
                                if(modals.filamentModal) modals.filamentModal.hide();
                                setTimeout(() => window.openQueueModal(), 300);
                            } else {
                                showToast("All spools already in queue", "info");
                            }
                        };
                    }
                } else {
                    // No spools found
                    if(countBadge) countBadge.innerText = "0";
                    listContainer.innerHTML = "<div class='p-2 text-muted text-center small'>No active spools found.</div>";
                    if(btnQueueAll) btnQueueAll.style.display = 'none';
                }
                
                if(!silent && modals.filamentModal) modals.filamentModal.show();
            })
            .catch(e => {
                if(!silent) setProcessing(false);
                listContainer.innerHTML = "<div class='text-danger small p-2'>Error loading spools</div>";
                if(!silent && modals.filamentModal) modals.filamentModal.show();
            });
        } else {
            // If HTML missing, just show modal normally
            if(!silent) setProcessing(false);
            if(!silent && modals.filamentModal) modals.filamentModal.show();
        }
    })
    .catch(e => { if(!silent) setProcessing(false); console.error(e); showToast("Connection/Data Error", "error"); });
};

const quickQueue = (id) => {
    fetch(`/api/spool_details?id=${id}`)
    .then(r=>r.json())
    .then(d => {
        if(!d.id) return;
        addToQueue({ id: d.id, type: 'spool', display: d.filament?.name || "Unknown" });
    });
};

// --- SMART SYNC LISTENER ---
document.addEventListener('inventory:sync-pulse', () => {
    // 1. Sync Spool Modal
    const spoolModal = document.getElementById('spoolModal');
    if (spoolModal && spoolModal.classList.contains('show')) {
        const id = document.getElementById('detail-id').innerText;
        if(id) openSpoolDetails(id, true); // Silent Refresh
    }
    
    // 2. Sync Filament Modal
    const filModal = document.getElementById('filamentModal');
    if (filModal && filModal.classList.contains('show')) {
        const fid = document.getElementById('fil-detail-id').innerText;
        if(fid) openFilamentDetails(fid, true); // Silent Refresh
    }
});