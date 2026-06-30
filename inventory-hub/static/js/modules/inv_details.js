/* MODULE: DETAILS (Spool & Filament Modals) */

// Module-scope helper: strip the JSON-quote wrapping Spoolman applies to
// text-typed extras (e.g. `'"Basic PLA"'` → `'Basic PLA'`). Shared by
// openSpoolDetails / openFilamentDetails populators, _editfilOpenModal
// (the Edit Filament form), and promptEditSlicerProfile.
const unquoteExtra = (v) => {
    if (v == null) return '';
    const s = String(v);
    if (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
    return s;
};

// Parse a Spoolman `filament_attributes` extra (JSON array, JSON-quoted
// string, or bare string) into a clean array of trimmed non-empty strings.
// Mirrors the parsing in _editfilOpenModal so the read-only detail modals and
// the Edit Filament form agree on shape.
const parseFilamentAttributes = (raw) => {
    if (raw == null || raw === '') return [];
    try {
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
        if (Array.isArray(parsed)) return parsed.map(String).map(s => s.trim()).filter(Boolean);
        if (parsed) return [String(parsed).trim()].filter(Boolean);
    } catch (_) {
        const fallback = String(raw).replace(/^"|"$/g, '').trim();
        if (fallback) return [fallback];
    }
    return [];
};

// Populate a read-only attribute chip row (shared by the Spool Details and
// Filament Details modals). Hides the wrapping row entirely when there are no
// attributes so the modal never shows a dangling "Attributes:" label.
const renderReadonlyAttributeChips = (rowId, hostId, attrs) => {
    const host = document.getElementById(hostId);
    const row = document.getElementById(rowId);
    if (!host) return;
    const list = Array.isArray(attrs) ? attrs : [];
    if (!list.length) {
        host.innerHTML = '';
        if (row) row.style.display = 'none';
        return;
    }
    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    host.innerHTML = list.map(a => `<span class="fcc-attr-chip">${esc(a)}</span>`).join('');
    if (row) row.style.display = 'flex';
};
console.log("🚀 Loaded Module: DETAILS");

// 8.3 — Hide a sibling details modal robustly. BS5's modal silently
// ignores .hide() while the modal is in mid-fade-in transition (its
// `_isTransitioning` flag short-circuits the call), so a single .hide()
// can leave the sibling visible if the user opens both back-to-back.
// Issue the hide immediately AND retry once after the fade should have
// settled (BS5 modal transition is 300ms; 400ms gives slack). Checks
// the DOM .show class rather than the private _isShown flag.
const _hideSiblingDetailsModal = (key) => {
    if (typeof modals === 'undefined' || !modals[key]) return;
    modals[key].hide();
    setTimeout(() => {
        const el = document.getElementById(key);
        if (el && el.classList.contains('show')) modals[key].hide();
    }, 400);
};
// L26 follow-up: expose so wizard entry points can close stacked
// details modals before launching, mirroring the details↔details pattern.
window.hideSiblingDetailsModal = _hideSiblingDetailsModal;
window.hideAllDetailsModals = () => {
    _hideSiblingDetailsModal('spoolModal');
    _hideSiblingDetailsModal('filamentModal');
};

const openSpoolDetails = (id, silent = false) => {
    // 8.3 — Prevent details-on-details stacking. A user-initiated open
    // forcibly closes the sibling details modal before this one shows;
    // silent=true (sync-pulse refresh) leaves visibility alone so it
    // only refreshes whichever modal is currently visible.
    if (!silent) _hideSiblingDetailsModal('filamentModal');
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
                const isUnknown = String(d.location || '').toUpperCase() === 'UNKNOWN';
                // 18.1 — Unknown bucket gets the yellow caution badge here too
                // so the Spool Details modal's location row matches the rest
                // of the UI (spool cards + Location Manager type badge). Was
                // previously rendering blue, which read as a normal location.
                if (isUnknown) {
                    locBadge.innerText = '❓ Unknown';
                    locBadge.className = "badge bg-warning text-dark ms-2 me-1";
                    locBadge.style.cursor = "pointer";
                    locBadge.title = "Physically lost — last known location unknown. Click to open the Unknown bucket.";
                    locBadge.onclick = () => {
                        if (typeof modals !== 'undefined' && modals.spoolModal) modals.spoolModal.hide();
                        if (window.openManage) window.openManage('UNKNOWN');
                    };
                } else {
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
            }

            document.getElementById('detail-material').innerText = fil.material || "Unknown";
            document.getElementById('detail-vendor').innerText = fil.vendor?.name || "Unknown";

            // Temperatures (sourced from the parent filament). Min/recommended
            // live on native Spoolman fields; max temps are text-typed extras.
            const filExtra = fil.extra || {};
            const writeSpoolTemp = (id, v) => {
                const el = document.getElementById(id);
                if (el) el.innerText = (v != null && v !== '') ? `${v}°C` : "--";
            };
            writeSpoolTemp('spool-detail-temp-nozzle',     fil.settings_extruder_temp);
            writeSpoolTemp('spool-detail-temp-nozzle-max', unquoteExtra(filExtra.nozzle_temp_max));
            writeSpoolTemp('spool-detail-temp-bed',        fil.settings_bed_temp);
            writeSpoolTemp('spool-detail-temp-bed-max',    unquoteExtra(filExtra.bed_temp_max));

            document.getElementById('detail-weight').innerText = (fil.weight || 0) + "g";

            const used = d.used_weight !== null ? d.used_weight : 0;
            const rem = d.remaining_weight !== null ? d.remaining_weight : 0;
            // PRECISE tier (buglist L51) — up to 1 decimal via the shared
            // formatter, so the Details modal agrees with the wizard/weigh-out
            // (was .toFixed(1), which forced a "850.0g" trailing zero).
            document.getElementById('detail-used').innerText = window.fmtGramsPrecise(used) + "g";
            document.getElementById('detail-remaining').innerText = window.fmtGramsPrecise(rem) + "g";

            document.getElementById('detail-color-name').innerText = fil.name || "Unknown";
            document.getElementById('detail-hex').innerText = (fil.color_hex || "").toUpperCase();
            document.getElementById('detail-comment').value = d.comment || "";

            // Filament attributes are a filament-level property; surface them
            // read-only on the spool modal too (inherited from the parent
            // filament's extra). Row hides itself when there are none.
            renderReadonlyAttributeChips(
                'spool-detail-attributes-row', 'spool-detail-attributes',
                parseFilamentAttributes(filExtra.filament_attributes));

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
    // 8.3 — see openSpoolDetails for rationale; mirrored sibling-close.
    if (!silent) _hideSiblingDetailsModal('spoolModal');
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
            // Stash vendor.id on the span's dataset so the ✏️ pencil next to
            // the brand text can read it without a re-fetch — same pattern
            // used by the slicer-profile pencil below (`dataset.value`).
            const fdVendorEl = document.getElementById('fil-detail-vendor');
            fdVendorEl.innerText = d.vendor ? d.vendor.name : "Unknown";
            fdVendorEl.dataset.vendorId = (d.vendor && d.vendor.id != null) ? String(d.vendor.id) : '';
            document.getElementById('fil-detail-material').innerText = d.material || "Unknown";
            document.getElementById('fil-detail-color-name').innerText = d.name || "Unknown";
            document.getElementById('fil-detail-hex').innerText = (d.color_hex || "").toUpperCase();

            document.getElementById('fil-detail-temp-nozzle').innerText = d.settings_extruder_temp ? `${d.settings_extruder_temp}°C` : "--";
            document.getElementById('fil-detail-temp-bed').innerText = d.settings_bed_temp ? `${d.settings_bed_temp}°C` : "--";
            // Max temps live in extras (text-typed, JSON-quoted on the wire).
            const fdExtra = d.extra || {};
            const fdNozzleMax = unquoteExtra(fdExtra.nozzle_temp_max);
            const fdBedMax = unquoteExtra(fdExtra.bed_temp_max);
            document.getElementById('fil-detail-temp-nozzle-max').innerText = fdNozzleMax ? `${fdNozzleMax}°C` : "--";
            document.getElementById('fil-detail-temp-bed-max').innerText = fdBedMax ? `${fdBedMax}°C` : "--";
            // Slicer profile fact card (read-only display + ✏️ pencil opens
            // promptEditSlicerProfile). Stash the raw value on dataset so the
            // edit dialog gets the actual current value, not the "--" sentinel.
            const fdSlicer = unquoteExtra(fdExtra.slicer_profile);
            const fdSlicerEl = document.getElementById('fil-detail-slicer-profile');
            if (fdSlicerEl) {
                fdSlicerEl.innerText = fdSlicer || "--";
                fdSlicerEl.dataset.value = fdSlicer;
            }
            document.getElementById('fil-detail-density').innerText = d.density ? `${d.density} g/cm³` : "--";

            // Group 17.5: surface the resolved Empty Spool Weight + inheritance
            // badge so the user doesn't have to open the Edit modal to find it.
            // Uses the canonical resolver in weight_utils.js (same cascade as
            // every other weight surface).
            const fdEmptyEl = document.getElementById('fil-detail-empty-spool-weight');
            const fdEmptySrcEl = document.getElementById('fil-detail-empty-spool-source');
            if (fdEmptyEl && typeof window.resolveEmptySpoolWeightSource === 'function') {
                const resolved = window.resolveEmptySpoolWeightSource({
                    spoolWt: null,  // filament-modal view — no per-spool override here
                    filamentWt: d.spool_weight,
                    vendor: d.vendor,
                });
                if (resolved.value == null) {
                    fdEmptyEl.innerText = "—";
                    if (fdEmptySrcEl) { fdEmptySrcEl.innerText = "not set"; fdEmptySrcEl.style.display = ''; }
                } else {
                    fdEmptyEl.innerText = `${resolved.value} g`;
                    if (fdEmptySrcEl) {
                        const label = resolved.source === 'filament' ? '↩ filament'
                            : resolved.source === 'vendor' ? '↩ vendor'
                            : resolved.source;
                        fdEmptySrcEl.innerText = label;
                        fdEmptySrcEl.style.display = '';
                    }
                }
            }
            // Group 17.1: surface swatch + label-confirmed status so users can
            // tell at a glance whether the filament has a printed sample and
            // whether the label has been physically confirmed via barcode scan.
            // Reads from existing extras (`sample_printed` for swatches,
            // `needs_label_print` tri-state for labels — false=confirmed,
            // true=needs print, null/missing=unknown).
            const fdSampleEl = document.getElementById('fil-detail-sample-status');
            if (fdSampleEl) {
                const rawSample = unquoteExtra(fdExtra.sample_printed);
                const sampleTruthy = rawSample === true || rawSample === 'true' || rawSample === 'True' || rawSample === 1 || rawSample === '1';
                const sampleFalsy = rawSample === false || rawSample === 'false' || rawSample === 'False' || rawSample === 0 || rawSample === '0';
                if (sampleTruthy) {
                    fdSampleEl.innerHTML = '<span class="badge bg-success">✅ Yes</span>';
                } else if (sampleFalsy) {
                    fdSampleEl.innerHTML = '<span class="badge bg-secondary">No</span>';
                } else {
                    fdSampleEl.innerHTML = '<span class="badge bg-dark border border-secondary text-muted">unknown</span>';
                }
                // Stash the tri-state so the ✏️ editor opens on the current value.
                fdSampleEl.dataset.value = sampleTruthy ? 'true' : (sampleFalsy ? 'false' : '');
            }
            const fdLabelEl = document.getElementById('fil-detail-label-status');
            if (fdLabelEl) {
                const rawLabel = unquoteExtra(fdExtra.needs_label_print);
                const needsPrint = rawLabel === true || rawLabel === 'true' || rawLabel === 'True';
                const confirmed = rawLabel === false || rawLabel === 'false' || rawLabel === 'False';
                if (confirmed) {
                    fdLabelEl.innerHTML = '<span class="badge bg-success">✅ Confirmed</span>';
                } else if (needsPrint) {
                    fdLabelEl.innerHTML = '<span class="badge bg-warning text-dark">🖨️ Needs print</span>';
                } else {
                    fdLabelEl.innerHTML = '<span class="badge bg-dark border border-secondary text-muted">unknown</span>';
                }
            }
            // Read-only filament attributes chip row (Derek 2026-05-28 — also
            // mirrored onto the Spool Details modal). Edited via the Edit
            // Filament form; this view is display-only.
            renderReadonlyAttributeChips(
                'fil-detail-attributes-row', 'fil-detail-attributes',
                parseFilamentAttributes(fdExtra.filament_attributes));

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
                                        // Group 17.2: don't auto-open the queue modal here.
                                        // Auto-opening interrupted users who wanted to keep
                                        // adding labels from other filaments/spools without
                                        // closing the queue panel each time. The toast carries
                                        // enough confirmation; the queue is reachable via the
                                        // existing top-bar button when the user actually wants it.
                                        showToast(`Queued ${added} label${added === 1 ? '' : 's'} — open Print Queue to review`, 'success', 4000);
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

// --- SLICER PROFILE EDIT (Filament Details Modal Pencil) ---
// Opens a Swal-style picker over the filament details modal so users can
// change the slicer_profile without leaving the fact-card view. Stacks
// inside #filamentModal via Swal `target` (same trick promptEditLocation
// uses for spoolModal). Sends a fully-merged extras dict to /api/update_filament
// so siblings (nozzle_temp_max, sheet_link, filament_attributes, etc.) are
// preserved — Spoolman replaces the whole `extra` dict on PATCH.
window.promptEditSlicerProfile = (filamentId, currentProfile) => {
    const escHtml = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    fetch('/api/external/fields')
        .then(r => r.json())
        .then(d => {
            if (!d || !d.success) {
                Swal.fire({
                    target: document.getElementById('filamentModal') || document.body,
                    icon: 'error',
                    title: 'Could not load profile choices',
                    background: '#1e1e1e', color: '#fff',
                });
                return;
            }
            const fields = (d.fields && d.fields.filament) || [];
            const slicerField = fields.find(f => f.key === 'slicer_profile');
            const choices = slicerField && Array.isArray(slicerField.choices) ? slicerField.choices : [];

            const items = [{ id: '', name: '-- (none) --' }, ...choices.map(c => ({ id: c, name: c }))];
            const listHtml = items.map(it => `
                <div class="swal-slicer-item p-2 border-bottom border-dark cursor-pointer text-light"
                     data-id="${escHtml(it.id)}"
                     style="transition:0.2s; ${it.id === currentProfile ? 'background:#444;' : 'background:transparent;'}">
                    ${escHtml(it.name)}
                </div>
            `).join('');

            Swal.fire({
                target: document.getElementById('filamentModal') || document.body,
                title: 'Change Slicer Profile',
                html: `
                    <div class="text-start">
                        <label class="form-label text-info small mb-1">Search Profiles</label>
                        <input type="text" id="swal-slicer-search" class="form-control bg-dark text-white border-info mb-2" placeholder="Type to filter..." autocomplete="off">
                        <input type="hidden" id="swal-slicer-value" value="${escHtml(currentProfile)}">
                        <div id="swal-slicer-list" class="border border-secondary rounded mb-2" style="max-height:200px;overflow-y:auto;background:#111;">
                            ${listHtml}
                        </div>
                        <label class="form-label text-info small mb-1">Or add a new profile</label>
                        <input type="text" id="swal-slicer-new" class="form-control bg-dark text-white border-info" placeholder="New profile name…" autocomplete="off">
                    </div>
                `,
                showCancelButton: true,
                confirmButtonColor: '#0dcaf0',
                background: '#1e1e1e',
                color: '#fff',
                confirmButtonText: 'Save',
                allowEscapeKey: true,
                allowOutsideClick: false,
                didOpen: () => {
                    const popup = Swal.getPopup();
                    const search = popup.querySelector('#swal-slicer-search');
                    const hidden = popup.querySelector('#swal-slicer-value');
                    const newInp = popup.querySelector('#swal-slicer-new');
                    const list   = popup.querySelector('#swal-slicer-list');
                    if (search) search.focus();

                    if (list) {
                        list.querySelectorAll('.swal-slicer-item').forEach(el => {
                            el.addEventListener('click', () => {
                                hidden.value = el.dataset.id;
                                if (newInp) newInp.value = '';
                                list.querySelectorAll('.swal-slicer-item').forEach(o => { o.style.background = 'transparent'; });
                                el.style.background = '#444';
                            });
                        });
                    }
                    if (search && list) {
                        search.addEventListener('input', () => {
                            const q = search.value.toLowerCase();
                            list.querySelectorAll('.swal-slicer-item').forEach(el => {
                                el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
                            });
                        });
                    }
                    if (newInp && list) {
                        newInp.addEventListener('input', () => {
                            if (newInp.value.trim()) {
                                hidden.value = '';
                                list.querySelectorAll('.swal-slicer-item').forEach(o => { o.style.background = 'transparent'; });
                            }
                        });
                    }
                },
                preConfirm: () => {
                    const popup = Swal.getPopup();
                    const newVal = (popup.querySelector('#swal-slicer-new')?.value || '').trim();
                    const selVal = popup.querySelector('#swal-slicer-value')?.value || '';
                    return { value: newVal || selVal, isNew: !!newVal };
                }
            }).then(result => {
                if (!result.isConfirmed) return;
                const { value: newProfile, isNew } = result.value;
                if (newProfile === currentProfile) return;

                fetch(`/api/filaments/${filamentId}`)
                    .then(r => r.json())
                    .then(res => {
                        const filament = res && res.data ? res.data : null;
                        const merged = { ...((filament && filament.extra) || {}) };
                        if (newProfile) merged.slicer_profile = `"${newProfile}"`;
                        else delete merged.slicer_profile;
                        return fetch('/api/update_filament', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ id: filamentId, data: { extra: merged } }),
                        }).then(r => r.json());
                    })
                    .then(saveRes => {
                        if (!saveRes || !saveRes.success) {
                            Swal.fire({
                                target: document.getElementById('filamentModal') || document.body,
                                icon: 'error',
                                title: 'Save failed',
                                text: (saveRes && saveRes.msg) || 'Spoolman rejected the update',
                                background: '#1e1e1e', color: '#fff',
                            });
                            return;
                        }
                        if (isNew && newProfile) {
                            fetch('/api/external/fields/add_choice', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ entity_type: 'filament', key: 'slicer_profile', new_choice: newProfile }),
                            }).catch(() => {});
                        }
                        if (typeof showToast === 'function') showToast('Slicer profile updated', 'success', 4000);
                        openFilamentDetails(filamentId, true);
                    })
                    .catch(err => {
                        Swal.fire({
                            target: document.getElementById('filamentModal') || document.body,
                            icon: 'error',
                            title: 'Save failed',
                            text: (err && err.message) || 'Network error',
                            background: '#1e1e1e', color: '#fff',
                        });
                    });
            });
        });
};

// L17 — inline editor for the filament's "Swatch Printed" (sample_printed)
// status. Mirrors promptEditSlicerProfile: a Swal targeted at the filament
// modal, a sibling-preserving extras merge, then POST /api/update_filament.
// The scan pipeline only ever SETS sample_printed=true (on a FIL: label
// confirm, app.py); this Details-modal toggle is the only surface that can
// set it to false or clear it to "unknown" independently of a scan.
window.promptEditSampleStatus = (filamentId, currentValue) => {
    const cur = currentValue || '';
    const opts = [
        { id: 'true',  label: '✅ Yes — swatch printed' },
        { id: 'false', label: 'No — not printed' },
        { id: '',      label: '❔ Unknown / clear' },
    ];
    // Custom dark-themed list — NOT Swal's input:'radio', whose .swal2-radio
    // widget paints a white pill, leaving our white popup text white-on-white.
    // Mirrors promptEditSlicerProfile's theme-correct selection list.
    const listHtml = opts.map(o => `
        <div class="swal-sample-item p-2 border-bottom border-dark text-light"
             data-id="${o.id}"
             style="cursor:pointer; transition:0.2s; ${o.id === cur ? 'background:#444;' : 'background:transparent;'}">
            ${o.label}
        </div>
    `).join('');

    let docKeyHandler = null;  // document-level arrow-nav handler; removed on close

    Swal.fire({
        target: document.getElementById('filamentModal') || document.body,
        title: '🎨 Swatch Printed?',
        html: `
            <div class="text-start">
                <input type="hidden" id="swal-sample-value" value="${cur}">
                <div id="swal-sample-list" class="border border-secondary rounded" style="background:#111;">
                    ${listHtml}
                </div>
            </div>
        `,
        heightAuto: false,  // don't reflow <body> — was shifting the dashboard QR deck down
        showCancelButton: true,
        confirmButtonText: 'Save',
        confirmButtonColor: '#0dcaf0',
        background: '#1e1e1e',
        color: '#fff',
        allowEscapeKey: true,
        allowOutsideClick: false,
        didOpen: () => {
            const popup = Swal.getPopup();
            const hidden = popup.querySelector('#swal-sample-value');
            const list = popup.querySelector('#swal-sample-list');
            const items = list ? Array.from(list.querySelectorAll('.swal-sample-item')) : [];
            let idx = Math.max(0, items.findIndex(el => el.dataset.id === cur));
            const paint = () => {
                items.forEach((el, i) => { el.style.background = (i === idx) ? '#444' : 'transparent'; });
                if (items[idx]) hidden.value = items[idx].dataset.id;
            };
            paint();
            items.forEach((el, i) => el.addEventListener('click', () => { idx = i; paint(); }));
            // Keyboard nav (CLAUDE.md idiom): ↑/↓ move the highlight; Enter saves and
            // Escape cancels via Swal's own handlers. Listen on document, not the
            // popup — Swal parks focus outside our list, so a popup-scoped listener
            // never receives the keydown. Removed in didClose.
            docKeyHandler = (e) => {
                if (!items.length) return;
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    // Capture phase + stopImmediatePropagation so we beat Swal's own
                    // keydown handler, which otherwise moves focus between the
                    // confirm/cancel buttons and swallows the event before it bubbles.
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    idx = (idx + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
                    paint();
                }
            };
            document.addEventListener('keydown', docKeyHandler, true);
        },
        didClose: () => {
            if (docKeyHandler) document.removeEventListener('keydown', docKeyHandler, true);
        },
        preConfirm: () => {
            const popup = Swal.getPopup();
            return popup.querySelector('#swal-sample-value')?.value ?? '';
        },
    }).then(result => {
        if (!result.isConfirmed) return;
        const choice = result.value;                  // 'true' | 'false' | ''
        if (choice === (currentValue || '')) return;  // unchanged → no-op

        fetch(`/api/filaments/${filamentId}`)
            .then(r => r.json())
            .then(res => {
                const filament = res && res.data ? res.data : null;
                const merged = { ...((filament && filament.extra) || {}) };
                // Send a raw JS boolean — spoolman_api.update_filament normalizes
                // bools to the stored "true"/"false" form, matching the
                // label-confirm write path. Deleting the key clears it to the
                // "unknown" tri-state.
                if (choice === 'true') merged.sample_printed = true;
                else if (choice === 'false') merged.sample_printed = false;
                else delete merged.sample_printed;
                return fetch('/api/update_filament', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: filamentId, data: { extra: merged } }),
                }).then(r => r.json());
            })
            .then(saveRes => {
                if (!saveRes || !saveRes.success) {
                    Swal.fire({
                        target: document.getElementById('filamentModal') || document.body,
                        icon: 'error',
                        title: 'Save failed',
                        text: (saveRes && saveRes.msg) || 'Spoolman rejected the update',
                        background: '#1e1e1e', color: '#fff',
                    });
                    return;
                }
                if (typeof showToast === 'function') showToast('Swatch status updated', 'success', 4000);
                openFilamentDetails(filamentId, true);
            })
            .catch(err => {
                Swal.fire({
                    target: document.getElementById('filamentModal') || document.body,
                    icon: 'error',
                    title: 'Save failed',
                    text: (err && err.message) || 'Network error',
                    background: '#1e1e1e', color: '#fff',
                });
            });
    });
};

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
                    // L271 Phase 5: Wall Shelf/Row are structural grouping nodes, never spool targets.
                    if (type === 'wall shelf' || type === 'row') return;
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

                    // Escape confirmation overlay — Group 15: routed through
                    // window.mountOverlay (tier 'confirm' so it sits above the
                    // host Swal). The OLD implementation appended a div inside
                    // popup with z-index:10; the new version creates a
                    // full-screen confirm overlay on demand and cleans up via
                    // handle.cleanup(). Same #fcc-escape-confirm-overlay /
                    // #fcc-escape-yes / #fcc-escape-no IDs are preserved for
                    // existing tests + selectors.
                    let confirmHandle = null;
                    const hideConfirmOverlay = () => {
                        if (confirmHandle) {
                            try { confirmHandle.cleanup(); } catch (_) { /* noop */ }
                            confirmHandle = null;
                        }
                        if (searchInput) searchInput.focus();
                    };
                    const showConfirmOverlay = () => {
                        if (confirmHandle) return;
                        confirmHandle = window.mountOverlay({
                            id: 'fcc-escape-confirm-overlay',
                            tier: 'confirm',
                            focusGuard: true,
                            initialFocus: '#fcc-escape-no',
                            onEscape: hideConfirmOverlay,
                            content: `
                                <div style="background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px; padding:20px 24px; text-align:center;">
                                    <div style="font-size:1.2em; font-weight:bold; color:#fff; margin-bottom:6px;">Cancel Override?</div>
                                    <div style="color:#ccc; font-size:0.9em; margin-bottom:12px;">Are you sure you want to close without saving?</div>
                                    <div style="display:flex; gap:10px; margin-top:8px; justify-content:center;">
                                        <button id="fcc-escape-yes" class="btn btn-danger btn-sm" style="min-width:100px;">Yes, close</button>
                                        <button id="fcc-escape-no" class="btn btn-secondary btn-sm" style="min-width:100px;">No, go back</button>
                                    </div>
                                </div>
                            `,
                        });
                        const ov = confirmHandle.element;
                        const escYes = ov.querySelector('#fcc-escape-yes');
                        const escNo = ov.querySelector('#fcc-escape-no');
                        escYes.addEventListener('click', () => Swal.close());
                        escNo.addEventListener('click', hideConfirmOverlay);
                        // Arrow keys and Tab switch focus between Yes/No buttons
                        ov.addEventListener('keydown', (e) => {
                            if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Tab') {
                                e.preventDefault();
                                const target = document.activeElement === escYes ? escNo : escYes;
                                target.focus();
                            }
                        });
                    };
                    // Back-compat: existing keydown branches below still consult
                    // confirmShowing — read from the handle's existence.
                    const confirmShowing = () => confirmHandle !== null;

                    searchInput.addEventListener('input', (e) => {
                        const term = e.target.value.toLowerCase();
                        items.forEach(item => {
                            if (item.innerText.toLowerCase().includes(term)) item.style.display = 'block';
                            else item.style.display = 'none';
                        });
                        clearKbHighlight();
                    });

                    // Group 10.2/10.10 parity with wizardBindCombobox: if the
                    // user re-focuses the search input (e.g. after typing,
                    // clicking an item, then coming back to pick a different
                    // one), reveal the full list again — don't keep the prior
                    // filter applied to a no-longer-relevant query.
                    searchInput.addEventListener('focus', () => {
                        if (searchInput.value === '') return; // nothing to clear
                        searchInput.value = '';
                        items.forEach(item => { item.style.display = 'block'; });
                        clearKbHighlight();
                    });

                    items.forEach(item => {
                        item.addEventListener('click', () => {
                            clearKbHighlight();
                            items.forEach(i => i.style.background = 'transparent');
                            item.style.background = '#444';
                            hiddenInput.value = item.getAttribute('data-id');
                        });
                        // 21.5 — double-click commits the override in one gesture
                        // (mouse equivalent of arrow+Enter): select this entry,
                        // then trigger the same confirm path the Force button
                        // runs. preConfirm reads #swal-override-loc, which we set
                        // here first. Single-click + Force and keyboard nav are
                        // unchanged — dblclick is purely a shortcut on top.
                        item.addEventListener('dblclick', () => {
                            clearKbHighlight();
                            items.forEach(i => i.style.background = 'transparent');
                            item.style.background = '#444';
                            hiddenInput.value = item.getAttribute('data-id');
                            if (confirmShowing()) return; // don't commit while the cancel-confirm overlay is up
                            Swal.clickConfirm();
                        });
                        item.addEventListener('mouseenter', () => {
                            clearKbHighlight();
                            if(hiddenInput.value !== item.getAttribute('data-id')) item.style.background = '#222';
                        });
                        item.addEventListener('mouseleave', () => { if(hiddenInput.value !== item.getAttribute('data-id')) item.style.background = 'transparent'; });
                    });

                    // Keyboard navigation on search input
                    searchInput.addEventListener('keydown', (e) => {
                        if (confirmShowing()) return;
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
                    // that state. Group 15 — when the mountOverlay confirm is up,
                    // its own onEscape (document-capture) handles the close; we let
                    // the event through by returning early so mountOverlay sees it.
                    const escKeyHandler = (e) => {
                        if (e.key !== 'Escape') return;
                        // If the confirm overlay is already up, let mountOverlay's
                        // onEscape take it (it uses stopImmediatePropagation).
                        if (confirmShowing()) return;
                        e.preventDefault();
                        e.stopImmediatePropagation();
                        showConfirmOverlay();
                    };
                    window.addEventListener('keydown', escKeyHandler, true);
                    popup.__fccEscCleanup = () => {
                        window.removeEventListener('keydown', escKeyHandler, true);
                        if (confirmHandle) {
                            try { confirmHandle.cleanup(); } catch (_) { /* noop */ }
                            confirmHandle = null;
                        }
                    };

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
    // Group 6.1: stash the editing-target so the Import-from-External
    // panel (module-scoped functions appended at end of file) can read
    // the current filament state without requesting it via a prop chain.
    window._editfilState = { fil: fil, isCreate: isCreate };

    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    // unquoteExtra is now module-scoped at the top of this file; the local
    // closure copy was lifted so openSpoolDetails / openFilamentDetails /
    // promptEditSlicerProfile can share the same helper.
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
    const currentSlicerProfile = unquoteExtra(rawExtra.slicer_profile);
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

    // 23.2 — Reset the Import-from-External panel so the previous filament's
    // search/source/results/preview can't bleed into this edit (wrong-link risk).
    if (window.editfilExternalReset) window.editfilExternalReset();

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
                <input type="text" id="editfil-color-hex-${idx}" class="form-control bg-black text-white border-secondary" value="${hexInit}" placeholder="#rrggbb" maxlength="7" autocomplete="off" style="flex:1;">
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
    // Group 6.2: ✏️ pencil opens the Vendor Edit modal stacked over this one.
    // Visible only when an EXISTING vendor is selected (mirrors vendorInfoPill).
    const vendorEditBtn = document.getElementById('editfil-vendor-edit-btn');
    const refreshVendorBadge = () => {
        const typed = (vendorNameEl.value || '').trim();
        if (!typed) {
            vendorIdEl.value = '';
            vendorNewBadge.style.display = 'none';
            if (vendorInfoPill) vendorInfoPill.style.display = 'none';
            if (vendorEditBtn) vendorEditBtn.style.display = 'none';
            return;
        }
        const match = vendorCache.find(v => (v.name || '').toLowerCase() === typed.toLowerCase());
        if (match) {
            vendorIdEl.value = String(match.id);
            vendorNewBadge.style.display = 'none';
            if (vendorEditBtn) vendorEditBtn.style.display = 'inline-block';
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
            if (vendorEditBtn) vendorEditBtn.style.display = 'none';
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

    // Slicer profile (single-select choice field). Same fetch as attrChoices,
    // different shape — multi=False, so dropdown not chips.
    let slicerChoices = [];
    let slicerPendingNew = null; // Newly-typed name awaiting add_choice POST on save.

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
        let v = String(val || '').trim();
        if (!v) return;
        // Group 10.9 — same validation guards as the wizard's filament-attributes
        // path. `silent` is used when seeding existing chips on modal open;
        // those values are already canonical in Spoolman, so we bypass the gate.
        if (!silent && typeof window.validateNewChoice === 'function' && !attrChoices.includes(v)) {
            const result = window.validateNewChoice(v, attrChoices);
            if (!result.ok) {
                if (typeof showToast === 'function') {
                    showToast(result.error || 'Invalid attribute', 'warning', 5000);
                }
                return;
            }
            if (result.suggestion) {
                if (typeof showToast === 'function') {
                    showToast(`Did you mean "${result.suggestion}"? — pick it from the suggestions, or refine the typed value.`, 'info', 7000);
                }
                return;
            }
            v = result.canonical;
        }
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
    // Slicer profile dropdown — populated from /api/external/fields choices.
    // Empty option + existing choices + "+ Add new..." sentinel; current
    // value is pre-selected, or appended as an orphan option if the stored
    // value isn't (yet) in the registered choice list.
    const slicerSelect = document.getElementById('editfil-slicer-profile');
    const slicerNewInput = document.getElementById('editfil-slicer-profile-new');
    const renderSlicerSelect = () => {
        if (!slicerSelect) return;
        const opts = ['<option value="">(none)</option>'];
        for (const c of slicerChoices) {
            const sel = (c === currentSlicerProfile) ? ' selected' : '';
            opts.push(`<option value="${esc(c)}"${sel}>${esc(c)}</option>`);
        }
        const isOrphan = currentSlicerProfile && !slicerChoices.includes(currentSlicerProfile);
        if (isOrphan) {
            opts.push(`<option value="${esc(currentSlicerProfile)}" selected>${esc(currentSlicerProfile)}</option>`);
        }
        opts.push('<option value="__new__">+ Add new…</option>');
        slicerSelect.innerHTML = opts.join('');
    };
    if (slicerSelect && slicerNewInput) {
        slicerSelect.addEventListener('change', () => {
            if (slicerSelect.value === '__new__') {
                slicerNewInput.classList.remove('d-none');
                slicerNewInput.focus();
            } else {
                slicerNewInput.classList.add('d-none');
                slicerNewInput.value = '';
            }
        });
    }
    renderSlicerSelect();

    // Load known attribute choices (and slicer profile choices) from Spoolman's field schema.
    fetch('/api/external/fields').then(r => r.json()).then(d => {
        if (!d || !d.success) return;
        const filamentFields = (d.fields && d.fields.filament) || [];
        const attrField = filamentFields.find(f => f.key === 'filament_attributes');
        if (attrField && Array.isArray(attrField.choices)) {
            attrChoices = attrField.choices.slice();
            // Group 6.1: surface to module-scoped Import-from-External panel
            // so its computeFilamentBackfillDiff call can split material+attrs
            // properly (e.g. parser returns "PLA Silk" → base "PLA", attrs ["Silk"]).
            window._editfilAttrChoicesCache = attrChoices;
        }
        const slicerField = filamentFields.find(f => f.key === 'slicer_profile');
        if (slicerField && Array.isArray(slicerField.choices)) {
            slicerChoices = slicerField.choices.slice();
            renderSlicerSelect();
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
        // Slicer profile (single-select choice; "+ Add new…" sentinel routes
        // typed value through slicerNewInput and queues silent registration).
        let newSlicerProfile = '';
        if (slicerSelect) {
            newSlicerProfile = slicerSelect.value === '__new__'
                ? (slicerNewInput ? slicerNewInput.value.trim() : '')
                : slicerSelect.value;
        }
        if (newSlicerProfile !== currentSlicerProfile) dirtyExtras.slicer_profile = newSlicerProfile;
        if (slicerSelect && slicerSelect.value === '__new__' && newSlicerProfile && !slicerChoices.includes(newSlicerProfile)) {
            slicerPendingNew = newSlicerProfile;
        }
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
                        // 23.4 — send the delete-sentinel so the backend merge
                        // POPS the key. A client-side `delete` was lost: the
                        // backend re-merges against the live record, so an
                        // omitted key means "keep" and blanking silently no-op'd.
                        mergedExtra[k] = window.FCC_DELETE_EXTRA;
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
            if (slicerPendingNew) {
                fetch('/api/external/fields/add_choice', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ entity_type: 'filament', key: 'slicer_profile', new_choice: slicerPendingNew }),
                }).catch(() => {});
                slicerPendingNew = null;
            }

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
                // 23.3 — if this edit changed a field that PRINTS on the filament
                // swatch label, the physical sample is now stale. Nudge a reprint
                // (only when the label was previously CONFIRMED). Uses payload/
                // dirtyExtras (the change set) + rawExtra (the prior label state).
                if (!isCreate) {
                    const dispName = (payload && payload.name) || fil.name || `Filament #${fil.id}`;
                    _maybePromptLabelReprint(fil.id, dispName, payload, dirtyExtras, rawExtra);
                }
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

// 23.3 — Filament label-invalidation reprint nudge.
//
// WHICH fields print on the swatch label (and thus go stale when edited) was
// read directly from the current P-touch template `Spoolman Filament Lables.lbx`
// (the visible PLACED fields are Color/RGB, Brand, Type, Color-name — temps and
// density are in the DB connection but NOT placed, so they don't invalidate the
// swatch). Mapped back to editable filament fields:
//   color_hex / multi_color_hexes / multi_color_direction → the swatch + RGB text
//   name / extra.original_color                           → the "Color" name text
//   vendor_id                                             → Brand
//   material / extra.filament_attributes                  → Type (get_smart_type)
// (Derek 2026-06-29: filament label reprints on color/RGB, Name, Vendor,
// Material, Type. Spool-label propagation is a separate, deferred scope.)
const _LABEL_BEARING_NATIVE = {
    name: 'Name',
    material: 'Material',
    vendor_id: 'Vendor',
    color_hex: 'Color',
    multi_color_hexes: 'Color',
    multi_color_direction: 'Color',
};
const _LABEL_BEARING_EXTRA = {
    original_color: 'Color name',
    filament_attributes: 'Type',
};

const _maybePromptLabelReprint = (filId, displayName, changed, dirtyExtras, rawExtra) => {
    if (typeof window.mountOverlay !== 'function') return;
    // Only nudge when the printed label was previously CONFIRMED. Tri-state:
    // false = confirmed/printed (prompt), true = already needs print (no-op),
    // null/absent = unknown/never printed (don't nag a record with no label).
    const prior = unquoteExtra(rawExtra && rawExtra.needs_label_print);
    const wasConfirmed = prior === false || prior === 'false' || prior === 'False';
    if (!wasConfirmed) return;

    const has = (o, k) => !!o && Object.prototype.hasOwnProperty.call(o, k);
    // A bare multi_color_direction clear is the save handler's DEFENSIVE
    // single-color cleanup (changed.multi_color_direction = null when a stale
    // native direction lingers), NOT a real color edit. Only count it when an
    // actual hex change co-occurs — otherwise editing just a comment on such a
    // record would falsely claim "you changed Color".
    const dirOnly = has(changed, 'multi_color_direction')
        && !has(changed, 'color_hex') && !has(changed, 'multi_color_hexes');
    const labels = new Set();
    for (const k of Object.keys(_LABEL_BEARING_NATIVE)) {
        if (k === 'multi_color_direction' && dirOnly) continue;
        if (has(changed, k)) labels.add(_LABEL_BEARING_NATIVE[k]);
    }
    for (const k of Object.keys(_LABEL_BEARING_EXTRA)) {
        if (has(dirtyExtras, k)) labels.add(_LABEL_BEARING_EXTRA[k]);
    }
    if (labels.size === 0) return;
    _showLabelReprintPrompt(filId, displayName, [...labels]);
};

const _showLabelReprintPrompt = (filId, displayName, changedLabels) => {
    // Load order guarantees window.escHtml is defined (inv_core.js loads first),
    // but keep the fallback a true escaper so a future defer/module change can't
    // silently un-escape a user-controlled filament name.
    const esc = window.escHtml || ((s) => String(s == null ? '' : s)
        .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));
    const name = displayName || `Filament #${filId}`;
    const changedTxt = changedLabels.join(', ');
    const panel = document.createElement('div');
    panel.style.cssText = 'background:#1e1e1e; color:#fff; border:2px solid #ffc107; '
        + 'border-radius:10px; padding:22px 26px; max-width:460px; text-align:center; '
        + 'box-shadow:0 8px 32px rgba(0,0,0,0.6);';
    panel.innerHTML = `
        <div style="font-size:2em; line-height:1; margin-bottom:6px;">🏷️</div>
        <div style="font-size:1.15em; font-weight:bold; margin-bottom:8px;">Printed label is now out of date</div>
        <div style="color:#ccc; margin-bottom:18px; line-height:1.45;">
            You changed <span style="color:#ffc107; font-weight:bold;">${esc(changedTxt)}</span> on
            <span style="color:#fff; font-weight:bold;">${esc(name)}</span>.
            The printed swatch label no longer matches — reprint it and replace the sample.
        </div>
        <div style="display:flex; gap:10px; justify-content:center;">
            <button type="button" id="fcc-label-reprint-yes" class="btn btn-warning fw-bold">🖨️ Add to print queue</button>
            <button type="button" id="fcc-label-reprint-no" class="btn btn-outline-secondary">Later</button>
        </div>
    `;
    const handle = window.mountOverlay({
        id: 'fcc-label-reprint-prompt',
        content: panel,
        tier: 'standard',
        initialFocus: '#fcc-label-reprint-yes',
    });
    const yes = panel.querySelector('#fcc-label-reprint-yes');
    const no = panel.querySelector('#fcc-label-reprint-no');
    if (yes) yes.addEventListener('click', () => {
        // addToQueue both raises needs_label_print (surfaces the staleness in the
        // pending list + Details badge) AND queues the label for the P-touch batch.
        const queued = (typeof window.addToQueue === 'function')
            ? window.addToQueue({ id: filId, type: 'filament', display: `Filament #${filId}` })
            : false;
        if (window.showToast) {
            window.showToast(
                queued
                    ? `Queued label reprint for filament #${filId}`
                    : `Filament #${filId} is already in the print queue`,
                queued ? 'success' : 'info', 4000);
        }
        handle.cleanup();
    });
    if (no) no.addEventListener('click', () => handle.cleanup());
};

// 23.3 — exposed so the wizard's edit_spool path (which can also edit
// label-bearing filament fields) can reuse the exact same confirmation/field
// logic + mountOverlay prompt rather than re-implementing it.
window._maybePromptLabelReprint = _maybePromptLabelReprint;

window.openEditFilamentForm = (fil) => {
    if (!fil || !fil.id) { showToast('Missing filament data', 'error'); return; }
    _editfilOpenModal(fil);
};

window.openAddFilamentForm = () => {
    _editfilOpenModal(null);
};


// ----------------------------------------------------------------------
// Buried delete UI (gear-icon dropdown → inline overlay double-confirm).
// No nested Swal per CLAUDE.md project conventions.
// ----------------------------------------------------------------------

const FCC_DELETE_OVERLAY_BASE_STYLE =
    'position:absolute; inset:0; z-index:1100; ' +
    'background:rgba(0,0,0,0.92); border-radius:inherit; ' +
    'display:flex; flex-direction:column; align-items:center; justify-content:center; ' +
    'gap:14px; padding:32px; text-align:center;';

const _renderDeleteOverlay = (overlay, { title, body, requireText, confirmLabel, onConfirm }) => {
    overlay.style.cssText = FCC_DELETE_OVERLAY_BASE_STYLE;
    overlay.style.display = 'flex';
    const inputId = `${overlay.id}-input`;
    const errId = `${overlay.id}-err`;
    overlay.innerHTML = `
        <div style="font-size:1.3em; font-weight:bold; color:#ff8888;">${title}</div>
        <div style="color:#ddd; font-size:0.95em; max-width:480px;">${body}</div>
        ${requireText ? `
            <div style="display:flex; flex-direction:column; gap:6px; align-items:center;">
                <label for="${inputId}" style="color:#aaa; font-size:0.85em;">
                    Type <code style="color:#ffaa55;">${requireText}</code> to confirm:
                </label>
                <input id="${inputId}" type="text" autocomplete="off"
                    style="font-family:monospace; padding:6px 10px; min-width:240px; text-align:center; border:1px solid #555; border-radius:4px; background:#222; color:#fff;" />
                <div id="${errId}" style="color:#ff5555; font-size:0.8em; min-height:1em;"></div>
            </div>
        ` : ''}
        <div style="display:flex; gap:10px; margin-top:6px;">
            <button class="btn btn-danger fw-bold" data-fcc-delete-confirm style="min-width:140px;">${confirmLabel}</button>
            <button class="btn btn-secondary" data-fcc-delete-cancel style="min-width:120px;">Cancel</button>
        </div>
    `;
    const cancelBtn = overlay.querySelector('[data-fcc-delete-cancel]');
    const confirmBtn = overlay.querySelector('[data-fcc-delete-confirm]');
    const input = requireText ? overlay.querySelector(`#${inputId}`) : null;
    const errEl = requireText ? overlay.querySelector(`#${errId}`) : null;

    // Suspend Bootstrap's modal Escape dismiss while the overlay is showing,
    // so Escape only closes the overlay (not the underlying modal). Restored
    // in close() below.
    const modalElForKbd = overlay.closest('.modal');
    let bsModalInst = null;
    let bsModalKeyboardWas = null;
    if (modalElForKbd && typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        bsModalInst = bootstrap.Modal.getInstance(modalElForKbd);
        if (bsModalInst && bsModalInst._config) {
            bsModalKeyboardWas = bsModalInst._config.keyboard;
            bsModalInst._config.keyboard = false;
        }
    }
    const close = () => {
        overlay.style.display = 'none';
        overlay.innerHTML = '';
        if (bsModalInst && bsModalInst._config && bsModalKeyboardWas !== null) {
            bsModalInst._config.keyboard = bsModalKeyboardWas;
        }
    };
    cancelBtn.addEventListener('click', close);
    confirmBtn.addEventListener('click', async () => {
        if (requireText) {
            if ((input.value || '').trim() !== requireText) {
                if (errEl) errEl.textContent = `Doesn't match — type ${requireText} exactly.`;
                input.focus();
                input.select();
                return;
            }
        }
        confirmBtn.disabled = true;
        cancelBtn.disabled = true;
        // onConfirm is responsible for closing the overlay on completion.
        // Some callbacks re-render the overlay (Step 1 → Step 2 transition) —
        // auto-closing here would nuke the just-rendered next step.
        await onConfirm();
    });
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                confirmBtn.click();
            }
        });
        setTimeout(() => input.focus(), 0);
    } else {
        setTimeout(() => cancelBtn.focus(), 0);
    }
    // Escape on the overlay also cancels. Register on:
    //   1. The closest .modal element at capture phase — Bootstrap's modal
    //      keyboard handler is bound on the modal element itself, so this
    //      catches Escape before Bootstrap sees it.
    //   2. document as a fallback for keystrokes that arrive while focus is
    //      somehow outside the modal.
    // Both call stopImmediatePropagation so Bootstrap's modal-dismiss path
    // never runs while the overlay is showing.
    const modalEl = overlay.closest('.modal');
    const escHandler = (e) => {
        if (e.key !== 'Escape') return;
        if (overlay.style.display === 'none') return;
        e.stopImmediatePropagation();
        e.preventDefault();
        close();
        if (modalEl) modalEl.removeEventListener('keydown', escHandler, true);
        document.removeEventListener('keydown', escHandler, true);
    };
    if (modalEl) modalEl.addEventListener('keydown', escHandler, true);
    document.addEventListener('keydown', escHandler, true);
};

const _showDeleteSpoolFlow = (spoolId) => {
    const overlay = document.getElementById('fcc-spool-delete-overlay');
    if (!overlay || !spoolId) return;
    // Step 1 — broad warning, no type-to-confirm.
    _renderDeleteOverlay(overlay, {
        title: '⚠️ Delete this spool?',
        body: `This will permanently delete <strong>Spool #${spoolId}</strong> from Spoolman. This action cannot be undone.`,
        requireText: null,
        confirmLabel: 'Continue →',
        onConfirm: async () => {
            // Step 2 — type-the-id confirmation.
            _renderDeleteOverlay(overlay, {
                title: '🗑️ Final confirmation',
                body: `Type the spool ID to confirm permanent deletion of <strong>Spool #${spoolId}</strong>.`,
                requireText: String(spoolId),
                confirmLabel: 'Delete forever',
                onConfirm: async () => {
                    try {
                        const r = await fetch(`/api/spool/${spoolId}`, { method: 'DELETE' });
                        const j = await r.json().catch(() => ({}));
                        if (!r.ok || !j.success) {
                            const err = (j && j.error) || `HTTP ${r.status}`;
                            showToast(`Delete failed: ${err}`, 'error', 7000);
                            return;
                        }
                        showToast(`Spool #${spoolId} deleted`, 'success', 4000);
                        if (typeof modals !== 'undefined' && modals.spoolModal) modals.spoolModal.hide();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));
                    } catch (e) {
                        showToast(`Delete failed: ${e.message || e}`, 'error', 7000);
                    }
                },
            });
        },
    });
};

// Group 11.2 — Merge duplicate filaments. Routes the user through a
// target-picker → preview-and-confirm flow, then POSTs to the merge
// endpoint that re-parents all child spools and deletes the source.
// Routed through window.mountOverlay() per project convention so it
// composes correctly with the filament details modal underneath.
const _showMergeFilamentFlow = async (sourceFilamentId) => {
    const srcId = String(sourceFilamentId || '').trim();
    if (!srcId) return;
    const filamentModalEl = document.getElementById('filamentModal');

    // Fetch the full filament list + the source's own details up front. Two
    // round-trips because the list endpoint doesn't return nested vendor
    // labels in the same shape as filament_details, and we want the source
    // label in the picker / confirm prompt to read identically to what the
    // user sees on the details modal title.
    let allFilaments = [];
    let srcSpoolCount = 0;
    try {
        const [filRes, spoolRes] = await Promise.all([
            fetch('/api/filaments'),
            fetch(`/api/spools_by_filament?id=${encodeURIComponent(srcId)}&allow_archived=true`),
        ]);
        const filJson = await filRes.json();
        if (filJson && filJson.success && Array.isArray(filJson.filaments)) {
            allFilaments = filJson.filaments;
        }
        const spoolsJson = await spoolRes.json();
        if (Array.isArray(spoolsJson)) srcSpoolCount = spoolsJson.length;
    } catch (e) {
        showToast(`Could not load filament list: ${e.message || e}`, 'error', 7000);
        return;
    }

    const fmtFilament = (f) => {
        const id = f && f.id != null ? `#${f.id}` : '#?';
        const brand = (f && (f.vendor && f.vendor.name)) || 'Generic';
        const mat = (f && f.material) || '?';
        const name = (f && f.name) || '';
        return `${id} — ${brand} ${mat}${name ? ' ' + name : ''}`;
    };

    const srcFilament = allFilaments.find(f => String(f.id) === srcId);
    const srcLabel = srcFilament ? fmtFilament(srcFilament) : `#${srcId}`;

    // Eligible targets = everything except the source itself. Sort by id
    // descending so the most recently created filaments (the more likely
    // "canonical" version of a duplicate pair) bubble to the top.
    const targets = allFilaments
        .filter(f => String(f.id) !== srcId)
        .sort((a, b) => (b.id || 0) - (a.id || 0));

    if (!targets.length) {
        showToast('No other filaments exist to merge into.', 'warning', 5000);
        return;
    }

    const datalistOpts = targets.map(f => {
        // <option value="#42 — Hatchbox PLA Galaxy Black"> — datalist matches
        // against the visible value, so the prefix #id makes id-search fast.
        return `<option value="${fmtFilament(f).replace(/"/g, '&quot;')}"></option>`;
    }).join('');

    const inputId = 'fcc-merge-target-input';
    const errId = 'fcc-merge-target-err';
    const datalistId = 'fcc-merge-target-list';
    const continueBtnId = 'fcc-merge-continue';
    const cancelBtnId = 'fcc-merge-cancel';

    const pickerHtml = `
        <div style="background:#222; color:#fff; border:1px solid #555; border-radius:8px;
                    padding:20px 22px; min-width:420px; max-width:560px;
                    box-shadow:0 8px 32px rgba(0,0,0,0.55);">
            <h5 style="margin:0 0 8px; color:#5dd0ff;">🔗 Merge filament</h5>
            <div style="color:#ccc; font-size:0.9em; margin-bottom:12px;">
                Re-parent all spools from <strong>${srcLabel}</strong>
                (<strong>${srcSpoolCount}</strong> spool${srcSpoolCount === 1 ? '' : 's'},
                incl. archived) onto another filament, then delete this filament.
            </div>
            <label for="${inputId}" style="display:block; font-size:0.85em; color:#aaa; margin-bottom:4px;">
                Target filament (start typing brand / material / color or <code>#id</code>):
            </label>
            <input id="${inputId}" type="text" list="${datalistId}" autocomplete="off"
                placeholder="e.g. #42 or Hatchbox PLA"
                style="width:100%; padding:8px 10px; background:#111; color:#fff;
                       border:1px solid #555; border-radius:4px; font-family:monospace;" />
            <datalist id="${datalistId}">${datalistOpts}</datalist>
            <div id="${errId}" style="color:#ff5555; font-size:0.85em; min-height:1.1em; margin-top:6px;"></div>
            <div style="display:flex; gap:10px; justify-content:flex-end; margin-top:14px;">
                <button id="${cancelBtnId}" class="btn btn-secondary" style="min-width:110px;">Cancel</button>
                <button id="${continueBtnId}" class="btn btn-primary fw-bold" style="min-width:140px;">Continue →</button>
            </div>
        </div>
    `;

    const handle = window.mountOverlay({
        id: 'fcc-merge-filament-overlay',
        content: pickerHtml,
        tier: 'standard',
        host: filamentModalEl,
        initialFocus: `#${inputId}`,
        // Datalist <select> dropdowns sometimes get pointer-events trapped by
        // the host modal; occlude them so the picker stays interactive.
        occlude: ['.fcc-offcanvas-search'],
    });

    const input = handle.panel.querySelector(`#${inputId}`);
    const errEl = handle.panel.querySelector(`#${errId}`);
    const continueBtn = handle.panel.querySelector(`#${continueBtnId}`);
    const cancelBtn = handle.panel.querySelector(`#${cancelBtnId}`);

    const resolveTarget = () => {
        const raw = (input.value || '').trim();
        if (!raw) return null;
        // Allow direct "#42" or "42" entry
        const idMatch = raw.match(/^#?(\d+)\b/);
        if (idMatch) {
            const idNum = parseInt(idMatch[1], 10);
            return targets.find(f => f.id === idNum) || null;
        }
        // Otherwise match against the exact rendered label (the datalist
        // option the user picked).
        return targets.find(f => fmtFilament(f) === raw) || null;
    };

    cancelBtn.addEventListener('click', () => handle.cleanup());
    continueBtn.addEventListener('click', () => {
        const tgt = resolveTarget();
        if (!tgt) {
            errEl.textContent = 'Pick a filament from the list (or type its #id).';
            input.focus();
            return;
        }
        if (String(tgt.id) === srcId) {
            errEl.textContent = "Target can't be the same filament.";
            return;
        }
        _showMergeConfirmStep(srcId, srcLabel, tgt, srcSpoolCount, filamentModalEl);
        handle.cleanup();
    });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            continueBtn.click();
        }
    });
};

// Step 2 of the merge flow — type-CONFIRM gate + actual POST. Split out so
// the picker overlay can fully cleanup before the confirm overlay mounts
// (no nested overlays, no state held across steps).
const _showMergeConfirmStep = (srcId, srcLabel, target, spoolCount, hostModalEl) => {
    const tgtLabel = (() => {
        const id = `#${target.id}`;
        const brand = (target.vendor && target.vendor.name) || 'Generic';
        const mat = target.material || '?';
        const name = target.name || '';
        return `${id} — ${brand} ${mat}${name ? ' ' + name : ''}`;
    })();

    const confirmInputId = 'fcc-merge-confirm-input';
    const errId = 'fcc-merge-confirm-err';
    const cancelBtnId = 'fcc-merge-confirm-cancel';
    const goBtnId = 'fcc-merge-confirm-go';

    const html = `
        <div style="background:#222; color:#fff; border:1px solid #ff9955; border-radius:8px;
                    padding:20px 22px; min-width:420px; max-width:560px;
                    box-shadow:0 8px 32px rgba(0,0,0,0.55);">
            <h5 style="margin:0 0 8px; color:#ffaa55;">⚠️ Confirm merge</h5>
            <div style="color:#ddd; font-size:0.92em; margin-bottom:10px;">
                <strong>${spoolCount}</strong> spool${spoolCount === 1 ? '' : 's'}
                (including archived) will move from
                <div style="margin:6px 0;">
                    <span style="color:#ff8866;">${srcLabel}</span><br>
                    <span style="color:#aaa;">→</span>
                    <span style="color:#88ffaa;">${tgtLabel}</span>
                </div>
                Then <strong>${srcLabel}</strong> will be <strong>permanently deleted</strong>.
                This cannot be undone.
            </div>
            <label for="${confirmInputId}" style="display:block; font-size:0.85em; color:#aaa; margin-bottom:4px;">
                Type <code style="color:#ffaa55;">MERGE</code> to confirm:
            </label>
            <input id="${confirmInputId}" type="text" autocomplete="off"
                style="width:100%; padding:8px 10px; background:#111; color:#fff;
                       border:1px solid #555; border-radius:4px;
                       font-family:monospace; text-align:center;" />
            <div id="${errId}" style="color:#ff5555; font-size:0.85em; min-height:1.1em; margin-top:6px;"></div>
            <div style="display:flex; gap:10px; justify-content:flex-end; margin-top:14px;">
                <button id="${cancelBtnId}" class="btn btn-secondary" style="min-width:110px;">Cancel</button>
                <button id="${goBtnId}" class="btn btn-danger fw-bold" style="min-width:160px;">Merge forever</button>
            </div>
        </div>
    `;

    const handle = window.mountOverlay({
        id: 'fcc-merge-confirm-overlay',
        content: html,
        tier: 'confirm',
        host: hostModalEl,
        initialFocus: `#${confirmInputId}`,
    });

    const input = handle.panel.querySelector(`#${confirmInputId}`);
    const errEl = handle.panel.querySelector(`#${errId}`);
    const goBtn = handle.panel.querySelector(`#${goBtnId}`);
    const cancelBtn = handle.panel.querySelector(`#${cancelBtnId}`);

    cancelBtn.addEventListener('click', () => handle.cleanup());
    goBtn.addEventListener('click', async () => {
        if ((input.value || '').trim() !== 'MERGE') {
            errEl.textContent = "Type MERGE exactly to confirm.";
            input.focus();
            input.select();
            return;
        }
        goBtn.disabled = true;
        cancelBtn.disabled = true;
        try {
            const r = await fetch(`/api/filament/${srcId}/merge_into/${target.id}`, {
                method: 'POST',
            });
            const j = await r.json().catch(() => ({}));
            if (!r.ok || !j.success) {
                const err = (j && j.error) || `HTTP ${r.status}`;
                showToast(`Merge failed: ${err}`, 'error', 7000);
                goBtn.disabled = false;
                cancelBtn.disabled = false;
                return;
            }
            const n = (j.reparented_spool_ids || []).length;
            showToast(
                `Merged ${srcLabel} → ${tgtLabel} (${n} spool${n === 1 ? '' : 's'} re-parented)`,
                'success', 4000,
            );
            handle.cleanup();
            if (typeof modals !== 'undefined' && modals.filamentModal) modals.filamentModal.hide();
            document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));
        } catch (e) {
            showToast(`Merge failed: ${e.message || e}`, 'error', 7000);
            goBtn.disabled = false;
            cancelBtn.disabled = false;
        }
    });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            goBtn.click();
        }
    });
};

const _showDeleteFilamentFlow = (filamentId, childSpoolCount) => {
    const overlay = document.getElementById('fcc-filament-delete-overlay');
    if (!overlay || !filamentId) return;
    const cascadeNote = childSpoolCount > 0
        ? `<div style="color:#ffaa55; font-weight:bold;">⚠️ This filament has ${childSpoolCount} spool${childSpoolCount === 1 ? '' : 's'}. Deleting it will also permanently delete ${childSpoolCount === 1 ? 'that spool' : 'all of them'}.</div>`
        : '';
    _renderDeleteOverlay(overlay, {
        title: '⚠️ Delete this filament?',
        body: `${cascadeNote}<div style="margin-top:8px;">This will permanently delete <strong>Filament #${filamentId}</strong> from Spoolman. This action cannot be undone.</div>`,
        requireText: null,
        confirmLabel: 'Continue →',
        onConfirm: async () => {
            const requireText = childSpoolCount > 0 ? 'CONFIRM' : String(filamentId);
            _renderDeleteOverlay(overlay, {
                title: '🗑️ Final confirmation',
                body: childSpoolCount > 0
                    ? `Cascade delete will remove <strong>Filament #${filamentId}</strong> and its <strong>${childSpoolCount}</strong> child spool${childSpoolCount === 1 ? '' : 's'}.`
                    : `Type the filament ID to confirm permanent deletion of <strong>Filament #${filamentId}</strong>.`,
                requireText,
                confirmLabel: 'Delete forever',
                onConfirm: async () => {
                    try {
                        const r = await fetch(`/api/filament/${filamentId}`, { method: 'DELETE' });
                        const j = await r.json().catch(() => ({}));
                        if (!r.ok || !j.success) {
                            const err = (j && j.error) || `HTTP ${r.status}`;
                            showToast(`Delete failed: ${err}`, 'error', 7000);
                            return;
                        }
                        const cascade = (j.deleted_spool_ids || []).length;
                        const msg = cascade > 0
                            ? `Filament #${filamentId} deleted (${cascade} child spool${cascade === 1 ? '' : 's'} too)`
                            : `Filament #${filamentId} deleted`;
                        showToast(msg, 'success', 4000);
                        if (typeof modals !== 'undefined' && modals.filamentModal) modals.filamentModal.hide();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse'));
                    } catch (e) {
                        showToast(`Delete failed: ${e.message || e}`, 'error', 7000);
                    }
                },
            });
        },
    });
};

document.addEventListener('DOMContentLoaded', () => {
    const spoolDel = document.getElementById('btn-spool-delete');
    if (spoolDel) {
        spoolDel.addEventListener('click', () => {
            const sid = (document.getElementById('detail-id') || {}).innerText;
            if (sid) _showDeleteSpoolFlow(sid);
        });
    }
    const filMerge = document.getElementById('btn-fil-merge');
    if (filMerge) {
        filMerge.addEventListener('click', () => {
            const fidEl = document.getElementById('fil-detail-id');
            const fid = fidEl ? (fidEl.innerText || '').trim() : '';
            if (!fid) return;
            _showMergeFilamentFlow(fid);
        });
    }
    const filDel = document.getElementById('btn-fil-delete');
    if (filDel) {
        filDel.addEventListener('click', async () => {
            const fidEl = document.getElementById('fil-detail-id');
            const fid = fidEl ? (fidEl.innerText || '').trim() : '';
            if (!fid) return;
            // Get the truthful child-spool count (including archived) so
            // the cascade prompt reflects what the backend will actually
            // delete — not what the "show archived" toggle is currently
            // showing.
            let childCount = 0;
            try {
                const r = await fetch(`/api/spools_by_filament?id=${fid}&allow_archived=true`);
                const spools = await r.json();
                if (Array.isArray(spools)) childCount = spools.length;
            } catch (_e) {
                // If the count fetch fails, fall back to the visible badge — the
                // server will still cascade correctly, the prompt's number is
                // just informational.
                const countEl = document.getElementById('fil-spool-count');
                childCount = countEl ? parseInt(countEl.innerText || '0', 10) || 0 : 0;
            }
            _showDeleteFilamentFlow(fid, childCount);
        });
    }
    // Hide overlays when their parent modal closes (prevents stranded
    // overlay state if the user ⛶ closes the modal mid-flow).
    // Also re-implement Escape-to-close on the modal here, since the modals
    // ship with `data-bs-keyboard="false"` to keep Bootstrap from racing
    // the delete overlay's own Escape handler. When no overlay is showing,
    // Escape on the modal closes it (preserves the prior UX).
    ['spoolModal', 'filamentModal'].forEach((mid) => {
        const m = document.getElementById(mid);
        if (!m) return;
        const overlayId = mid === 'spoolModal' ? 'fcc-spool-delete-overlay' : 'fcc-filament-delete-overlay';
        m.addEventListener('hidden.bs.modal', () => {
            const ov = document.getElementById(overlayId);
            if (ov) {
                ov.style.display = 'none';
                ov.innerHTML = '';
            }
        });
        m.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            const ov = document.getElementById(overlayId);
            if (ov && ov.style.display !== 'none') return; // overlay's own handler runs
            if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                const inst = bootstrap.Modal.getInstance(m);
                if (inst) inst.hide();
            }
        });
    });
});


// ============================================================================
// Group 6.2 — Vendor / Manufacturer Edit Modal V1
// ============================================================================
// Two entry points: pencil next to fil-detail-vendor (Filament Details modal),
// pencil next to editfil-vendor-info (Edit Filament modal — stacks over).
// V1 fields: name (native), comment (native, labeled "Notes"), website (extra).
//
// Save uses PATCH /api/vendors/<id> which calls update_vendor_or_raise — the
// activity log + toast contract is honored on both success and rejection.
// On success we dispatch a `vendor:updated` CustomEvent so any open Filament
// Details / Edit Filament modal can refresh the vendor name/info pill without
// a full re-fetch path.

// Open in create-mode: vendoredit-id stays empty so vendorEditSave POSTs
// instead of PATCHes, and vendor:created is dispatched on success. Callers
// pass an optional prefill object: { name?, website?, comment? }.
window.openVendorCreateModal = (prefill) => {
    const errEl = document.getElementById('vendoredit-error');
    if (errEl) { errEl.classList.add('d-none'); errEl.innerText = ''; }
    document.getElementById('vendoredit-id').value = '';
    const p = prefill || {};
    document.getElementById('vendoredit-name').value = p.name || '';
    document.getElementById('vendoredit-website').value = p.website || '';
    document.getElementById('vendoredit-empty-weight').value = '';
    document.getElementById('vendoredit-external-id').value = '';
    document.getElementById('vendoredit-comment').value = p.comment || '';
    const titleEl = document.getElementById('vendorEditModalLabel');
    if (titleEl) titleEl.innerText = '➕ Add Manufacturer';
    const regEl = document.getElementById('vendoredit-registered');
    if (regEl) regEl.innerText = '';

    const modalEl = document.getElementById('vendorEditModal');
    if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
    // Focus the name field so a one-tap name + Enter shortcut works.
    setTimeout(() => {
        const n = document.getElementById('vendoredit-name');
        if (n) n.focus();
    }, 100);
};

window.openVendorEditModal = (vendorId) => {
    const vid = vendorId == null ? '' : String(vendorId).trim();
    if (!vid) {
        showToast('No manufacturer to edit.', 'warning', 4000);
        return;
    }
    const titleEl = document.getElementById('vendorEditModalLabel');
    if (titleEl) titleEl.innerText = '✏️ Edit Manufacturer';
    const errEl = document.getElementById('vendoredit-error');
    if (errEl) { errEl.classList.add('d-none'); errEl.innerText = ''; }
    document.getElementById('vendoredit-id').value = vid;
    document.getElementById('vendoredit-name').value = '';
    document.getElementById('vendoredit-website').value = '';
    document.getElementById('vendoredit-empty-weight').value = '';
    document.getElementById('vendoredit-external-id').value = '';
    document.getElementById('vendoredit-comment').value = '';
    const regEl = document.getElementById('vendoredit-registered');
    if (regEl) regEl.innerText = '';

    fetch('/api/vendors')
        .then(r => r.json())
        .then(d => {
            if (!d || !d.success) throw new Error(d && d.msg ? d.msg : 'Vendor lookup failed');
            const v = (d.vendors || []).find(x => String(x.id) === vid);
            if (!v) throw new Error(`Vendor #${vid} not found.`);
            document.getElementById('vendoredit-name').value = v.name || '';
            document.getElementById('vendoredit-comment').value = v.comment || '';
            document.getElementById('vendoredit-external-id').value = v.external_id || '';
            // empty_spool_weight is a number on the wire; render the raw value
            // so the user sees the same string they'll be editing. Empty/null
            // → empty input (the user can clear it back to null on save).
            const wt = v.empty_spool_weight;
            document.getElementById('vendoredit-empty-weight').value =
                (wt == null || wt === '') ? '' : String(wt);
            const ex = v.extra || {};
            // Website is stored as `extra.website`. Spoolman serves text-type
            // extras as JSON-encoded strings (`'"https://..."'`); strip the
            // wrapping quotes for the UI input. unquoteExtra is module-scoped.
            const site = (typeof unquoteExtra === 'function') ? unquoteExtra(ex.website) : (ex.website || '');
            document.getElementById('vendoredit-website').value = site || '';
            // Read-only "member since" footer — Spoolman exposes `registered`
            // as an ISO timestamp; show only the date portion. Skipped if the
            // payload is missing it (Spoolman versions before 0.20).
            if (regEl && v.registered) {
                regEl.innerText = `Registered ${String(v.registered).slice(0, 10)}`;
            }

            const modalEl = document.getElementById('vendorEditModal');
            if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                const inst = bootstrap.Modal.getOrCreateInstance(modalEl);
                inst.show();
            }
        })
        .catch(e => {
            showToast(`Failed to open manufacturer: ${e.message || e}`, 'error', 7000);
        });
};

window.vendorEditSave = () => {
    const vid = document.getElementById('vendoredit-id').value;
    const name = document.getElementById('vendoredit-name').value.trim();
    const website = document.getElementById('vendoredit-website').value.trim();
    const externalId = document.getElementById('vendoredit-external-id').value.trim();
    const emptyWtRaw = document.getElementById('vendoredit-empty-weight').value.trim();
    const comment = document.getElementById('vendoredit-comment').value;
    const errEl = document.getElementById('vendoredit-error');
    const showErr = (msg) => {
        if (errEl) { errEl.classList.remove('d-none'); errEl.innerText = msg; }
        showToast(msg, 'error', 7000);
    };
    // Empty vid is legitimate — that's create mode (openVendorCreateModal).
    // Edit mode never opens with an empty vid (openVendorEditModal rejects),
    // so we don't need to guard against missing-id in this path anymore.
    if (!name) { showErr('Name is required.'); return; }

    // empty_spool_weight is a Spoolman number field. Empty input → null
    // (user is clearing the value). Non-numeric → reject up-front so the
    // user sees a clear message instead of a Spoolman 422.
    let emptyWt = null;
    if (emptyWtRaw !== '') {
        const n = Number(emptyWtRaw);
        if (!Number.isFinite(n) || n < 0) {
            showErr('Empty Spool Weight must be a non-negative number.');
            return;
        }
        emptyWt = n;
    }

    // Build payload: native fields top-level, website wrapped for the
    // text-type extras contract (JSON_STRING_FIELDS). Backend's
    // sanitize_outbound_data + _merge_extras_with_existing handle the rest.
    // No `vid` means we're in create mode (opened via openVendorCreateModal).
    // POST /api/vendors → returns the new vendor body → dispatch
    // `vendor:created` so listeners (e.g. the wizard's vendor combobox) can
    // refetch the vendor list and auto-select the new entry.
    const isCreate = !vid;

    const data = {
        name: name,
        comment: comment,
        external_id: externalId,
        empty_spool_weight: emptyWt,
    };
    // 23.4 — on EDIT (PATCH) a blanked website sends the delete-sentinel so the
    // backend merge POPS it; an empty string would persist a literal '""'
    // instead of clearing. On CREATE there's nothing to delete, so a blank
    // stays an empty string.
    data.extra = { website: website ? `"${website}"` : (isCreate ? '' : window.FCC_DELETE_EXTRA) };

    const url = isCreate ? '/api/vendors' : `/api/vendors/${encodeURIComponent(vid)}`;
    const method = isCreate ? 'POST' : 'PATCH';
    fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data }),
    })
        .then(r => r.json().then(j => ({ ok: r.ok, body: j })))
        .then(({ ok, body }) => {
            if (!ok || !body.success) {
                throw new Error(body && body.msg ? body.msg : 'Spoolman rejected the request');
            }
            const v = body.vendor || null;
            if (isCreate) {
                showToast(`Manufacturer created.`, 'success', 4000);
                document.dispatchEvent(new CustomEvent('vendor:created', {
                    detail: { id: v && v.id != null ? String(v.id) : '', vendor: v },
                }));
            } else {
                showToast(`Manufacturer updated.`, 'success', 4000);
                document.dispatchEvent(new CustomEvent('vendor:updated', {
                    detail: { id: vid, vendor: v },
                }));
            }
            const modalEl = document.getElementById('vendorEditModal');
            if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
                const inst = bootstrap.Modal.getInstance(modalEl);
                if (inst) inst.hide();
            }
        })
        .catch(e => {
            showErr(e.message || String(e));
        });
};

// `vendor:updated` listener — refresh visible vendor surfaces.
//   Filament Details modal: brand text on fil-detail-vendor (if its vendorId
//     dataset matches the edited id).
//   Edit Filament modal: vendor combobox name + info-pill tooltip (refetch
//     /api/vendors so the combobox cache is current; the existing
//     refreshVendorBadge closure inside _editfilOpenModal is not reachable
//     from here, so we re-trigger it indirectly by setting the input value).
document.addEventListener('vendor:updated', (e) => {
    const vid = e.detail && e.detail.id;
    if (!vid) return;
    const v = e.detail.vendor;

    const brandEl = document.getElementById('fil-detail-vendor');
    if (brandEl && brandEl.dataset.vendorId === String(vid) && v) {
        brandEl.innerText = v.name || brandEl.innerText;
    }

    // Edit Filament modal — only act when it's actually open, otherwise we'd
    // touch stale DOM left over from a previous edit session.
    const editModal = document.getElementById('editFilamentModal');
    if (editModal && editModal.classList.contains('show') && v) {
        const nameInput = document.getElementById('editfil-vendor-name');
        const idInput = document.getElementById('editfil-vendor-id');
        if (nameInput && idInput && idInput.value === String(vid)) {
            nameInput.value = v.name || nameInput.value;
            // Fire input event so bindComboDropdown's onInput handler
            // re-runs refreshVendorBadge → re-renders the info pill.
            nameInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }
});


// ============================================================================
// Group 6.1 — External Import Panel for Edit Filament Modal
// ============================================================================
// Reuses the wizard's GET /api/external/search backend (external_parsers.py)
// and window.computeFilamentBackfillDiff (defined in inv_wizard.js — loaded
// alongside this module). Renders a per-field checkbox preview classifying
// each parser-supplied value as silent_fill (current empty) or mismatch
// (would overwrite). Apply Selected writes form values only — the user
// clicks the modal's main Save button to persist.

(() => {
    // Maps from computeFilamentBackfillDiff keys to the matching
    // #editfil-* form input IDs. Keys prefixed `extra.` write into the
    // corresponding extra-field input that the Specs / Advanced tabs
    // expose. Missing keys (not in this map) are silently skipped.
    const FIELD_TO_INPUT_ID = {
        'material': 'editfil-material',
        'diameter': 'editfil-diameter',
        'density': 'editfil-density',
        'weight': 'editfil-weight',
        'spool_weight': 'editfil-spool-weight',
        'settings_extruder_temp': 'editfil-nozzle',
        'settings_bed_temp': 'editfil-bed',
        // 23.1 — color_hex now applies into the primary color-hex input
        // (apply special-cases it to drive the picker via a synthetic input
        // event). product_url/purchase_url ride the existing extra.* branch's
        // target inputs; apply special-cases their VALUE source because the
        // diff derives them from external_link/purchase_link, not extra.*.
        'color_hex': 'editfil-color-hex',
        'extra.product_url': 'editfil-product-url',
        'extra.purchase_url': 'editfil-purchase-url',
        'extra.nozzle_temp_max': 'editfil-nozzle-max',
        'extra.bed_temp_max': 'editfil-bed-max',
    };

    // Display labels for the preview rows. computeFilamentBackfillDiff
    // already supplies these for mismatches; silent fills don't, so we
    // resolve from this table.
    const FIELD_LABEL = {
        'material': 'Material',
        'diameter': 'Diameter (mm)',
        'density': 'Density (g/cm³)',
        'weight': 'Weight (g)',
        'spool_weight': 'Spool weight (g)',
        'settings_extruder_temp': 'Extruder Temp Min (°C)',
        'settings_bed_temp': 'Bed Temp Min (°C)',
        'color_hex': 'Color hex',
        'extra.product_url': 'Product URL',
        'extra.purchase_url': 'Purchase URL',
        'extra.nozzle_temp_max': 'Nozzle Temp Max (°C)',
        'extra.bed_temp_max': 'Bed Temp Max (°C)',
    };

    const ALL_FIELD_KEYS = Object.keys(FIELD_LABEL);

    // Module-scoped stash for the currently-previewed parser template so
    // Apply Selected can read it without re-parsing the JSON string.
    const importState = { template: null, results: [] };

    const $ = (id) => document.getElementById(id);
    const escHtml = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

    const setStatus = (msg) => {
        const el = $('editfil-external-status');
        if (el) el.innerText = msg || '';
    };

    const hidePreview = () => {
        const p = $('editfil-external-preview');
        if (p) p.classList.add('d-none');
        const rows = $('editfil-external-preview-rows');
        if (rows) rows.innerHTML = '';
        importState.template = null;
    };

    window.editfilExternalCancelPreview = hidePreview;

    // 23.2 — Reset the entire Import-from-External panel so each edit starts
    // clean. The Edit/Add-Filament modal reuses one set of inputs across every
    // filament, and importState persists at module scope, so without this the
    // previous edit's typed query, picked source, multi-result list, and
    // previewed template all survive into the NEXT filament's edit — risking
    // "Apply Selected" writing a stale parser's values onto the wrong filament.
    // Called from _editfilOpenModal on every open (idempotent against abnormal
    // closes), mirroring wizardReset discipline. hidePreview() already nulls
    // importState.template + clears the preview rows; this additionally wipes
    // importState.results, the query text, the source select, and the results
    // picker.
    window.editfilExternalReset = () => {
        hidePreview();
        importState.results = [];
        const queryEl = $('editfil-external-query');
        if (queryEl) queryEl.value = '';
        const sourceEl = $('editfil-external-source');
        if (sourceEl) sourceEl.selectedIndex = 0;
        const resultsEl = $('editfil-external-results');
        if (resultsEl) { resultsEl.innerHTML = ''; resultsEl.classList.add('d-none'); }
        setStatus('');
    };

    window.editfilExternalSearch = () => {
        const sourceEl = $('editfil-external-source');
        const queryEl = $('editfil-external-query');
        const resultsEl = $('editfil-external-results');
        if (!sourceEl || !queryEl || !resultsEl) return;
        let source = sourceEl.value;
        let term = (queryEl.value || '').trim();
        if (term.length < 2) { setStatus('Enter at least 2 characters or paste a URL.'); return; }

        // URL auto-detect mirrors wizardSearchExternal (inv_wizard.js:1338).
        // Lets the user paste any supported URL into the same input without
        // needing to switch the source dropdown first.
        if (term.includes('prusament.com/spool/')) {
            sourceEl.value = 'prusament'; source = 'prusament';
        } else if (term.includes('amazon.com') || term.includes('/dp/')) {
            sourceEl.value = 'amazon'; source = 'amazon';
        } else if (term.includes('3dfilamentprofiles.com')) {
            sourceEl.value = '3dfp'; source = '3dfp';
        }

        hidePreview();
        resultsEl.classList.add('d-none');
        resultsEl.innerHTML = '';
        setStatus(`Querying ${source}…`);

        fetch(`/api/external/search?source=${encodeURIComponent(source)}&q=${encodeURIComponent(term)}`)
            .then(r => r.json())
            .then(d => {
                if (!d || !d.success) throw new Error(d && d.msg ? d.msg : 'Search failed');
                const results = d.results || [];
                importState.results = results;
                if (results.length === 0) {
                    setStatus('No templates found.');
                    return;
                }
                if (results.length === 1) {
                    setStatus('1 template found — preview below.');
                    window.editfilExternalRenderPreview(results[0]);
                    return;
                }
                // Multi-result: populate the picker and let the user choose.
                resultsEl.innerHTML = '';
                results.forEach((f, i) => {
                    const brand = (f.vendor && f.vendor.name) || f.manufacturer || 'Generic';
                    const mat = f.material || '?';
                    const color = f.color_name || f.name || 'Unknown';
                    const wt = f.weight ? ` - ${f.weight}g` : '';
                    const opt = document.createElement('option');
                    opt.value = String(i);
                    opt.innerText = `${brand} ${mat} - ${color}${wt}`;
                    resultsEl.appendChild(opt);
                });
                resultsEl.classList.remove('d-none');
                setStatus(`${results.length} templates — pick one to preview.`);
            })
            .catch(e => {
                setStatus(`Error: ${e.message || e}`);
            });
    };

    window.editfilExternalSelected = () => {
        const sel = $('editfil-external-results');
        if (!sel) return;
        const idx = Number(sel.value);
        const tpl = importState.results[idx];
        if (tpl) window.editfilExternalRenderPreview(tpl);
    };

    window.editfilExternalRenderPreview = (template) => {
        if (!template) { hidePreview(); return; }
        importState.template = template;
        const rowsHost = $('editfil-external-preview-rows');
        const previewEl = $('editfil-external-preview');
        if (!rowsHost || !previewEl) return;

        const fil = (window._editfilState && window._editfilState.fil) || {};
        // Need the Filament Attributes set for splitMaterialAndAttributes.
        const knownAttrs = (window._editfilAttrChoicesCache) || [];

        if (typeof window.computeFilamentBackfillDiff !== 'function') {
            rowsHost.innerHTML = '<div class="text-warning small">Diff helper not available — wizard module may not be loaded.</div>';
            previewEl.classList.remove('d-none');
            return;
        }

        const diff = window.computeFilamentBackfillDiff(fil, template, knownAttrs);
        // Build a uniform row list across silent fills and mismatches so the
        // user can opt out of either category. Default-check silent fills,
        // default-uncheck mismatches (per spec — opt-in to overwrites).
        const rows = [];
        for (const key of ALL_FIELD_KEYS) {
            if (diff.silent && Object.prototype.hasOwnProperty.call(diff.silent, key)) {
                rows.push({
                    key,
                    label: FIELD_LABEL[key] || key,
                    stored: '(empty)',
                    scanned: diff.silent[key],
                    kind: 'silent',
                    defaultChecked: true,
                });
            }
        }
        for (const m of (diff.mismatches || [])) {
            rows.push({
                key: m.key,
                label: m.label || FIELD_LABEL[m.key] || m.key,
                stored: m.stored,
                scanned: m.scanned,
                kind: 'mismatch',
                defaultChecked: false,
            });
        }

        if (rows.length === 0) {
            rowsHost.innerHTML = '<div class="text-success small">All fields already match — nothing to import.</div>';
            previewEl.classList.remove('d-none');
            return;
        }

        rowsHost.innerHTML = rows.map((r, i) => {
            const tag = r.kind === 'silent'
                ? '<span class="badge bg-success text-dark">fill</span>'
                : '<span class="badge bg-warning text-dark">overwrite</span>';
            const arrow = r.kind === 'silent'
                ? `<span class="text-light">${escHtml(r.scanned)}</span>`
                : `<span class="text-muted">${escHtml(r.stored)}</span> → <span class="text-light">${escHtml(r.scanned)}</span>`;
            const inputId = FIELD_TO_INPUT_ID[r.key];
            const disabled = (inputId === null) ? 'disabled' : '';
            const note = (inputId === null) ? ' <span class="small text-muted">(not yet supported)</span>' : '';
            return `
                <label class="d-flex align-items-center gap-2 small ${disabled ? 'text-muted' : 'text-light'}">
                    <input type="checkbox" class="form-check-input editfil-import-row" data-key="${escHtml(r.key)}" ${r.defaultChecked && !disabled ? 'checked' : ''} ${disabled}>
                    ${tag}
                    <span class="fw-bold">${escHtml(r.label)}</span>
                    ${arrow}${note}
                </label>
            `;
        }).join('');

        previewEl.classList.remove('d-none');
    };

    window.editfilExternalApplySelected = () => {
        if (!importState.template) {
            showToast('Nothing to apply.', 'warning', 4000);
            return;
        }
        const checks = document.querySelectorAll('.editfil-import-row:checked');
        if (checks.length === 0) {
            showToast('No fields selected.', 'warning', 4000);
            return;
        }
        const tpl = importState.template;
        let applied = 0;
        checks.forEach(cb => {
            const key = cb.dataset.key;
            const inputId = FIELD_TO_INPUT_ID[key];
            if (!inputId) return;  // unmapped key — skip
            const inputEl = document.getElementById(inputId);
            if (!inputEl) return;

            // 23.1 — color_hex: normalize to #rrggbb and drive the hex input
            // via a synthetic 'input' event so the bound color-picker stays in
            // sync (a bare .value set wouldn't fire the picker's oninput). The
            // save handler's captureCurrentValues() then reads editfil-color-hex.
            if (key === 'color_hex') {
                let hx = String(tpl.color_hex == null ? '' : tpl.color_hex)
                    .trim().replace(/^#/, '').toLowerCase();
                if (/^[0-9a-f]{3}$/.test(hx)) hx = hx.split('').map(c => c + c).join('');  // #fff → ffffff
                if (!/^[0-9a-f]{6}$/.test(hx)) {
                    // Don't silently drop a row the user explicitly checked —
                    // tell them why the parser's color couldn't be applied.
                    if (window.showToast) window.showToast(`Skipped color: "${tpl.color_hex}" isn't a 6-digit hex.`, 'warning', 4000);
                    return;
                }
                inputEl.value = `#${hx}`;
                inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                applied++;
                return;
            }

            // 23.1 — product_url / purchase_url: computeFilamentBackfillDiff
            // derives these from tpl.external_link / tpl.purchase_link (NOT
            // tpl.extra.*), so read the SAME source the preview row showed
            // rather than the (empty) extra key the generic branch would read.
            if (key === 'extra.product_url' || key === 'extra.purchase_url') {
                const url = (key === 'extra.product_url')
                    ? (tpl.external_link || '')
                    : (tpl.purchase_link || tpl.external_link || '');
                inputEl.value = String(url);
                applied++;
                return;
            }

            let val;
            if (key.startsWith('extra.')) {
                const ek = key.slice('extra.'.length);
                const raw = (tpl.extra || {})[ek];
                // Strip JSON wrapping the parser might have applied so the
                // input shows a plain value. The save handler re-quotes via
                // the standard dirtyExtras path.
                val = (raw == null) ? '' : String(raw).replace(/^"|"$/g, '');
            } else {
                val = tpl[key];
                if (val == null) val = '';
            }
            inputEl.value = String(val);
            applied++;
        });
        showToast(`Applied ${applied} field${applied === 1 ? '' : 's'}. Click Save to persist.`, 'success', 4000);
        hidePreview();
    };
})();
