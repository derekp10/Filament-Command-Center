/* MODULE: DETAILS (Spool & Filament Modals) */
console.log("🚀 Loaded Module: DETAILS");

const openSpoolDetails = (id) => {
    setProcessing(true);
    fetch(`/api/spool_details?id=${id}`)
    .then(r => r.json())
    .then(d => {
        setProcessing(false);
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
        
        if(modals.spoolModal) modals.spoolModal.show();
    })
    .catch(e => { setProcessing(false); console.error(e); showToast("Connection/Data Error", "error"); });
};

const openFilamentDetails = (fid) => {
    setProcessing(true);
    fetch(`/api/filament_details?id=${fid}`)
    .then(r => r.json())
    .then(d => {
        setProcessing(false);
        if (!d || !d.id) { showToast("Filament Data Missing!", "error"); return; }
        
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
        if(swatch) swatch.style.backgroundColor = "#" + (d.color_hex || "333");
        
        const btnLink = document.getElementById('btn-fil-open-spoolman');
        if (btnLink) {
            if (typeof SPOOLMAN_URL !== 'undefined' && SPOOLMAN_URL) {
                const baseUrl = SPOOLMAN_URL.endsWith('/') ? SPOOLMAN_URL.slice(0, -1) : SPOOLMAN_URL;
                btnLink.href = `${baseUrl}/filament/show/${d.id}`;
            } else btnLink.href = `/filament/show/${d.id}`;
        }
        
        if(modals.filamentModal) modals.filamentModal.show();
    })
    .catch(e => { setProcessing(false); console.error(e); showToast("Connection/Data Error", "error"); });
};

const quickQueue = (id) => {
    fetch(`/api/spool_details?id=${id}`)
    .then(r=>r.json())
    .then(d => {
        if(!d.id) return;
        addToQueue({ id: d.id, type: 'spool', display: d.filament?.name || "Unknown" });
    });
};