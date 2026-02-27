/* MODULE: WIZARD (Add Inventory) */
console.log("🚀 Loaded Module: WIZARD");

let wizardState = {
    mode: 'manual', // 'existing', 'external', 'manual'
    vendors: [],
    selectedFilamentId: null,
    externalMetaData: null
};

window.openWizardModal = () => {
    wizardReset();
    if (window.modals && window.modals.wizardModal) {
        window.modals.wizardModal.show();
    } else {
        const m = new bootstrap.Modal(document.getElementById('wizardModal'));
        if (!window.modals) window.modals = {};
        window.modals.wizardModal = m;
        m.show();
    }
    wizardFetchVendors();
    wizardFetchLocations();
    wizardFetchExtraFields();
};

const wizardReset = () => {
    wizardState.mode = 'manual';
    wizardState.selectedFilamentId = null;
    wizardState.externalMetaData = null;

    // Clear Form
    document.querySelectorAll('#wizardModal input[type="text"], #wizardModal input[type="number"]').forEach(i => i.value = '');
    document.querySelectorAll('#wizardModal input[type="checkbox"]').forEach(i => i.checked = false);
    document.querySelectorAll('#wizardModal select').forEach(i => i.selectedIndex = 0);

    // Reset Color UI
    document.getElementById('wiz-fil-color-extra-container').innerHTML = '';
    document.getElementById('wiz-fil-color_hex_0').value = '#FFFFFF';
    document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = '#FFFFFF';

    document.getElementById('wiz-spool-qty').value = 1;

    document.getElementById('wiz-spool-used').value = 0;

    // Reset View
    wizardSelectType('manual');
    document.getElementById('wiz-status-msg').innerText = "";
    document.getElementById('wiz-fil-vendor-sel').style.display = 'block';
    document.getElementById('wiz-fil-vendor-new').style.display = 'none';
};

window.wizardAutoUpdateDensity = () => {
    const matInput = document.getElementById('wiz-fil-material');
    const densInput = document.getElementById('wiz-fil-density');

    // Only auto-update if the user is typing a new material and hasn't manually overridden it, or if it's basically the default
    const val = (matInput.value || '').toUpperCase();

    let density = 1.24; // Default PLA
    if (val.includes('PETG') || val.includes('PET')) density = 1.27;
    else if (val.includes('ABS')) density = 1.04;
    else if (val.includes('ASA')) density = 1.07;
    else if (val.includes('TPU') || val.includes('TPE') || val.includes('FLEX')) density = 1.21;
    else if (val.includes('NYLON') || val.includes('PA')) density = 1.14;
    else if (val.includes('PC') || val.includes('POLYCARBONATE')) density = 1.20;
    else if (val.includes('HIPS')) density = 1.04;
    else if (val.includes('PVA')) density = 1.19;
    else if (val.includes('PVB')) density = 1.08;

    densInput.value = density.toFixed(2);
};

window.wizardSelectType = (mode) => {
    wizardState.mode = mode;

    // Update active button styling
    document.querySelectorAll('.type-selector').forEach(el => el.classList.remove('border-primary', 'bg-primary-subtle'));
    document.getElementById(`btn-type-${mode}`).classList.add('border-primary', 'bg-primary-subtle');

    // Show/Hide Dynamic Areas
    const dynamicArea = document.getElementById('material-dynamic-area');
    const areaExt = document.getElementById('area-existing');
    const areaWeb = document.getElementById('area-external');
    const filConfig = document.getElementById('step-2-filament');
    const spoolConfig = document.getElementById('step-3-spool');

    spoolConfig.style.opacity = '1';
    spoolConfig.style.display = 'block';

    if (mode === 'manual') {
        dynamicArea.style.display = 'none';
        filConfig.style.display = 'block';
        document.getElementById('btn-wiz-submit').disabled = false;
    } else {
        dynamicArea.style.display = 'block';
        areaExt.style.display = (mode === 'existing') ? 'block' : 'none';
        areaWeb.style.display = (mode === 'external') ? 'block' : 'none';

        if (mode === 'existing') {
            filConfig.style.display = 'none';
            wizardSearchExisting();
        } else {
            filConfig.style.display = 'block';
        }

        wizardValidateSubmit();
    }
};

window.wizardValidateSubmit = () => {
    const btn = document.getElementById('btn-wiz-submit');
    if (wizardState.mode === 'existing' && !wizardState.selectedFilamentId) {
        btn.disabled = true;
    } else {
        btn.disabled = false;
    }
};

window.wizardCalcUsedWeight = () => {
    const scaleWt = parseFloat(document.getElementById('wiz-spool-scale').value);
    if (isNaN(scaleWt)) return;

    let emptyWt = parseFloat(document.getElementById('wiz-spool-empty_weight').value);
    if (isNaN(emptyWt)) {
        emptyWt = parseFloat(document.getElementById('wiz-fil-empty_weight').value) || 0;
    }

    let netWt = parseFloat(document.getElementById('wiz-spool-initial_weight').value);
    if (isNaN(netWt)) {
        netWt = parseFloat(document.getElementById('wiz-fil-weight').value);
        if (isNaN(netWt)) netWt = 1000; // standard assumption if completely hidden
    }

    let used = (netWt + emptyWt) - scaleWt;
    if (used < 0) used = 0;

    document.getElementById('wiz-spool-used').value = used.toFixed(0);
};

window.wizardClearScaleWeight = () => {
    document.getElementById('wiz-spool-scale').value = '';
};

// --- DATA FETCHERS ---
const wizardFetchVendors = () => {
    fetch('/api/external/vendors')
        .then(r => r.json())
        .then(d => {
            if (d.success) {
                wizardState.vendors = d.vendors;
                const sel = document.getElementById('wiz-fil-vendor-sel');
                sel.innerHTML = '<option value="">-- Generic --</option>';
                d.vendors.forEach(v => {
                    sel.innerHTML += `<option value="${v.id}">${v.name}</option>`;
                });
            }
        });
};

const wizardFetchLocations = () => {
    fetch('/api/locations')
        .then(r => r.json())
        .then(d => {
            if (Array.isArray(d)) {
                const sel = document.getElementById('wiz-spool-location');
                sel.innerHTML = '<option value="">-- Unassigned --</option>';
                d.forEach(loc => {
                    const type = (loc.Type || '').toLowerCase();
                    if (type.includes('mmu') || type.includes('tool') || type.includes('direct load') || type === 'virtual') return;
                    if (loc.LocationID === 'Unassigned') return;
                    sel.innerHTML += `<option value="${loc.LocationID}">${loc.Name}</option>`;
                });
            }
        });
};

const wizardFetchExtraFields = () => {
    fetch('/api/external/fields')
        .then(r => r.json())
        .then(d => {
            if (d.success && d.fields) {
                wizardState.extraFields = d.fields;

                // --- FILAMENT CUSTOM FIELDS ---
                const fContainer = document.getElementById('wiz-fil-dynamic-extra-fields');
                fContainer.innerHTML = '';

                if (d.fields.filament) {
                    d.fields.filament.sort((a, b) => (a.order || 0) - (b.order || 0));
                    d.fields.filament.forEach(field => {
                        // Hide legacy/system fields
                        if (['sheet_link', 'price_total', 'spoolman_reprint', 'label_printed', 'needs_label_print'].includes(field.key)) return;

                        let html = wizardGenerateFieldHTML(field, 'fil');
                        if (html) fContainer.innerHTML += html;
                    });
                }

                // --- SPOOL CUSTOM FIELDS ---
                const sContainer = document.getElementById('wiz-spool-dynamic-extra-fields');
                if (sContainer && d.fields.spool) {
                    sContainer.innerHTML = '';
                    d.fields.spool.sort((a, b) => (a.order || 0) - (b.order || 0));
                    d.fields.spool.forEach(field => {
                        if (['label_printed', 'needs_label_print', 'physical_source', 'physical_source_slot', 'container_slot'].includes(field.key)) return;

                        // If Temp Resistance is still 'text' in Spoolman, hide it so they can change it to Choice later
                        if (field.key === 'spool_temp' && field.field_type === 'text') return;

                        let html = wizardGenerateFieldHTML(field, 'spool');
                        if (html) sContainer.innerHTML += html;
                    });
                }

                // 🌟 After DOM generation, initialize the live Sync Bindings
                wizardSetupFieldSync();
            }
        });
};

window.wizardSetupFieldSync = () => {
    // Empy weight static propagation
    const filEmptyWt = document.getElementById('wiz-fil-empty_weight');
    const spoolEmptyWt = document.getElementById('wiz-spool-empty_weight');
    if (filEmptyWt && spoolEmptyWt) {
        ['input', 'change'].forEach(evt => {
            filEmptyWt.addEventListener(evt, (e) => {
                spoolEmptyWt.value = e.target.value;
            });
        });
    }

    // Lock all auto-synced Spool fields on initial render
    document.querySelectorAll('.wizard-sync-btn.active-sync').forEach(btn => {
        const spoolKey = btn.getAttribute('data-sync-target');
        const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);
        if (targetEl) {
            targetEl.setAttribute('readonly', 'true');
            targetEl.style.opacity = '0.7';
        }
    });

    // Find all Filament inputs that could act as Sync Sources
    const sources = document.querySelectorAll('.sync-source-fil');

    sources.forEach(sourceEl => {
        // We listen to input (typing) and change (select dropdowns/checkboxes/chips)
        ['input', 'change'].forEach(evtType => {
            sourceEl.addEventListener(evtType, (e) => {
                const filKey = e.target.getAttribute('data-key');
                if (!filKey) return;

                // Find ALL active Spool sync buttons that are linked to this filament key
                const syncBtns = document.querySelectorAll('.wizard-sync-btn.active-sync');

                syncBtns.forEach(btn => {
                    const linkedTo = btn.getAttribute('data-linked-fil-key');
                    if (linkedTo === filKey) {
                        const spoolKey = btn.getAttribute('data-sync-target');
                        const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);
                        if (targetEl) {
                            // Mirror the value based on input type
                            if (e.target.type === 'checkbox') {
                                targetEl.checked = e.target.checked;
                            } else {
                                targetEl.value = e.target.value;
                            }
                        }
                    }
                });
            });
        });
    });
};

window.wizardToggleFieldSync = (spoolKey) => {
    const btn = document.querySelector(`.wizard-sync-btn[data-sync-target="${spoolKey}"]`);
    const targetEl = document.getElementById(`wiz_spool_ef_${spoolKey}`);

    if (!btn || !targetEl) return;

    let spoolName = spoolKey;
    if (wizardState.extraFields?.spool) {
        const schema = wizardState.extraFields.spool.find(f => f.key === spoolKey);
        if (schema) spoolName = schema.name;
    }

    if (btn.classList.contains('active-sync')) {
        // BREAK THE LINK
        btn.classList.remove('active-sync');
        btn.classList.replace('btn-outline-info', 'btn-outline-secondary');
        btn.innerText = '🔗';
        btn.style.opacity = '0.5';
        btn.title = "Unlinked. Click to sync with a Filament field.";

        targetEl.removeAttribute('readonly');
        targetEl.style.opacity = '1';

        showToast(`Unlinked ${spoolName}`, "info");
    } else {
        // RESTORE OR CREATE THE LINK
        const filKey = btn.getAttribute('data-linked-fil-key');
        if (!filKey) {
            // Prompt user to select a field
            window.wizardPromptFieldSync(spoolKey);
            return;
        }

        btn.classList.add('active-sync');
        btn.classList.replace('btn-outline-secondary', 'btn-outline-info');
        btn.innerText = '🔗';
        btn.style.opacity = '1';

        targetEl.setAttribute('readonly', 'true');
        targetEl.style.opacity = '0.7';

        // Find the source filament element to pull initial value
        const sourceEl = document.getElementById(`wiz_fil_ef_${filKey}`);
        if (sourceEl) {
            if (sourceEl.type === 'checkbox') targetEl.checked = sourceEl.checked;
            else targetEl.value = sourceEl.value;
        }

        let filName = filKey;
        if (wizardState.extraFields?.filament) {
            const schema = wizardState.extraFields.filament.find(f => f.key === filKey);
            if (schema) filName = schema.name;
        }

        btn.title = `Synced with Filament's ${filName}. Click to unlink.`;
        showToast(`Synced ${spoolName} with ${filName}`, "success");
    }
};

window.wizardPromptFieldSync = (spoolKey) => {
    let inputOptions = {};
    if (wizardState.extraFields && wizardState.extraFields.filament) {
        wizardState.extraFields.filament.forEach(f => {
            inputOptions[f.key] = f.name;
        });
    }

    Swal.fire({
        target: document.getElementById('wizardModal') || document.body,
        title: 'Link Field',
        text: 'Select a Filament field to synchronize with this Spool field:',
        input: 'select',
        inputOptions: inputOptions,
        inputPlaceholder: '-- Select a Field --',
        showCancelButton: true,
        background: '#1e1e1e',
        color: '#fff',
        customClass: {
            input: 'bg-dark text-white border-secondary'
        }
    }).then((result) => {
        if (result.isConfirmed && result.value) {
            const btn = document.querySelector(`.wizard-sync-btn[data-sync-target="${spoolKey}"]`);
            if (btn) {
                btn.setAttribute('data-linked-fil-key', result.value);
                // Call toggle to actually enable it
                window.wizardToggleFieldSync(spoolKey);
            }
        }
    });
};

const wizardGenerateFieldHTML = (field, entityType) => {
    let syncHtml = '';
    // If we're rendering a Spool field, check if a Filament field with the exact same key exists
    if (entityType === 'spool' && wizardState.extraFields?.filament) {
        const hasMatchingFilamentField = wizardState.extraFields.filament.some(f => f.key === field.key);
        if (hasMatchingFilamentField) {
            // Default to synced (active) state
            syncHtml = `<button type="button" class="btn btn-sm btn-outline-info p-0 ms-2 border-0 wizard-sync-btn active-sync" 
                            data-sync-target="${field.key}" 
                            data-linked-fil-key="${field.key}"
                            onclick="window.wizardToggleFieldSync('${field.key}')" 
                            title="Synced with Filament's ${field.name}. Click to unlink."
                            style="font-size: 0.8rem; line-height: 1;">🔗</button>`;
        } else {
            // Unsynced state, user can click to map it manually
            syncHtml = `<button type="button" class="btn btn-sm btn-outline-secondary p-0 ms-2 border-0 wizard-sync-btn" 
                            data-sync-target="${field.key}"
                            data-linked-fil-key=""
                            onclick="window.wizardToggleFieldSync('${field.key}')" 
                            title="Click to link this field to a Filament field."
                            style="font-size: 0.8rem; line-height: 1; opacity: 0.5;">🔗</button>`;
        }
    }

    let html = `<div class="col-md-6 mb-2"><label class="form-label small text-secondary mb-1 d-flex align-items-center">${field.name}${syncHtml}</label>`;
    const dataClass = entityType === 'fil' ? 'dynamic-extra-field' : 'dynamic-extra-spool-field';
    // Add an ID for easy targeting by the sync logic
    const inputId = `wiz_${entityType}_ef_${field.key}`;

    if (field.field_type === 'choice' && field.multi_choice) {
        // Searchable Datalist Chip System
        html += `<div class="d-flex flex-wrap gap-1 mb-1 chip-container" id="chip-container-${entityType}-${field.key}"></div>
                 <div class="input-group input-group-sm">
                    <input type="text" class="form-control bg-dark text-white border-secondary sync-source-${entityType}" list="dl_${entityType}_${field.key}" id="${inputId}" data-key="${field.key}" placeholder="Search or type new..." onkeydown="if(event.key === 'Enter') { event.preventDefault(); wizardAddMultiChoiceChip('${entityType}', '${field.key}'); }">
                    <datalist id="dl_${entityType}_${field.key}">`;
        field.choices.forEach(c => { html += `<option value="${c}">`; });
        html += `   </datalist>
                    <button class="btn btn-outline-secondary px-3" type="button" 
                            onclick="wizardAddMultiChoiceChip('${entityType}', '${field.key}')" 
                            title="Add attribute">Add</button>
                 </div>`;

    } else if (field.field_type === 'choice' && !field.multi_choice) {
        html += `<div class="input-group input-group-sm" style="position: relative; z-index: 1;">
                    <select class="form-select bg-dark text-white border-secondary ${dataClass} sync-source-${entityType}" data-key="${field.key}" id="${inputId}">
                        <option value="">-- None --</option>`;
        field.choices.forEach(c => {
            html += `<option value="${c}">${c}</option>`;
        });
        html += `   </select>
                    <button class="btn btn-outline-secondary" type="button" 
                            onclick="wizardPromptNewChoice('${entityType}', '${field.key}')" 
                            title="Add new option to Spoolman Database">➕</button>
                 </div>`;

    } else if (field.field_type === 'boolean') {
        html += `<div class="form-check mt-1">
                    <input class="form-check-input ${dataClass} sync-source-${entityType}" type="checkbox" data-key="${field.key}" id="${inputId}">
                    <label class="form-check-label text-white small" for="${inputId}">Enable</label>
                 </div>`;
    } else {
        // Standard text/number input
        html += `<input type="text" class="form-control bg-dark text-white border-secondary ${dataClass} sync-source-${entityType}" data-key="${field.key}" id="${inputId}">`;
    }

    html += `</div>`;
    return html;
};

window.wizardAddMultiChoiceChip = (entityType, key) => {
    const input = document.getElementById(`ef_input_${key}`);
    const val = input.value.trim();
    if (!val) return;

    const container = document.getElementById(`chip-container-${key}`);
    // Check if chip is already in the list to prevent duplicates
    const escapedVal = CSS.escape(val);
    if (container.querySelector(`[data-value="${escapedVal}"]`)) {
        input.value = '';
        return;
    }

    // Check if it's a known choice, or if we need to silently permanently add it to the Spoolman DB
    let isKnown = false;
    const schemas = wizardState.extraFields[entityType === 'fil' ? 'filament' : 'spool'];
    if (schemas) {
        const fieldObj = schemas.find(f => f.key === key);
        if (fieldObj && fieldObj.choices.includes(val)) isKnown = true;
    }

    if (!isKnown) {
        // Silently push new choice to Spoolman backend config
        fetch('/api/external/fields/add_choice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_type: entityType === 'fil' ? 'filament' : 'spool', key: key, new_choice: val })
        });
        // We do NOT call wizardFetchExtraFields() here because it would wipe the unsaved modal DOM. The chip is already visually rendering below!
    }

    // Append Chip visually
    const chipHtml = `<span class="badge rounded-pill text-bg-primary border border-primary cursor-pointer dynamic-chip" 
                           onclick="this.remove()" 
                           data-key="${key}" 
                           data-selected="true"
                           data-value="${val}">${val} &times;</span>`;
    container.insertAdjacentHTML('beforeend', chipHtml);
    input.value = '';
};

window.wizardPromptNewChoice = (entityType, key) => {
    // Determine the absolute entity mapping Spoolman uses ('filament' or 'spool')
    const apiEntity = entityType === 'fil' ? 'filament' : 'spool';

    Swal.fire({
        target: document.getElementById('wizardModal') || document.body,
        title: 'Add New Option',
        text: 'Enter the new value to permanently add it to the Spoolman database.',
        input: 'text',
        inputAttributes: { autocapitalize: 'off', required: 'true' },
        showCancelButton: true,
        confirmButtonText: 'Add Option',
        confirmButtonColor: '#28a745',
        background: '#1e1e1e',
        color: '#fff',
        showLoaderOnConfirm: true,
        preConfirm: (newChoice) => {
            if (!newChoice.trim()) return Swal.showValidationMessage("Cannot be empty");
            return fetch('/api/external/fields/add_choice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entity_type: apiEntity, key: key, new_choice: newChoice.trim() })
            })
                .then(response => response.json())
                .then(data => {
                    if (!data.success) throw new Error(data.msg);
                    return newChoice.trim();
                })
                .catch(error => {
                    Swal.showValidationMessage(`Request failed: ${error}`);
                });
        },
        allowOutsideClick: () => !Swal.isLoading()
    }).then((result) => {
        if (result.isConfirmed) {
            Swal.fire({
                icon: 'success',
                title: 'Added!',
                text: `"${result.value}" has been added to the database.`,
                timer: 1500,
                showConfirmButton: false,
                background: '#1e1e1e',
                color: '#fff'
            });
            // Instantly refresh the schema arrays to pull down the newly added entry into the UI!
            wizardFetchExtraFields();
        }
    });
};

// --- COLOR GRADIENT LOGIC ---
window.wizardAddColorHex = () => {
    const container = document.getElementById('wiz-fil-color-extra-container');
    const idx = container.children.length + 1;
    const html = `
        <div class="input-group input-group-sm mb-1 mt-1">
            <input type="color" class="form-control form-control-color bg-dark border-secondary px-1" value="#000000" oninput="this.nextElementSibling.value = this.value.toUpperCase()">
            <input type="text" class="form-control bg-dark text-white border-secondary font-monospace" placeholder="#Hex" value="#000000" id="wiz-fil-color_hex_${idx}" oninput="this.previousElementSibling.value = (this.value.startsWith('#') ? this.value : '#' + this.value).padEnd(7, '0').substring(0,7)">
            <button class="btn btn-outline-danger" type="button" onclick="this.parentElement.remove(); if(document.getElementById('wiz-fil-color-extra-container').children.length === 0) document.getElementById('wiz-fil-color-direction').style.display='none';" title="Remove color">🗑️</button>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
    document.getElementById('wiz-fil-color-direction').style.display = 'block';
};

// --- EXISTING FILAMENT LOGIC ---
window.wizardSearchExisting = () => {
    // Basic frontend filter based on standard filament pool
    // In a production environment this should likely ping a dedicated /api/v1/filament?query endpoint
    const term = document.getElementById('wiz-search-existing').value.toLowerCase();
    const sel = document.getElementById('wiz-existing-results');
    sel.innerHTML = '<option disabled>Searching...</option>';

    fetch('/api/filaments')
        .then(r => r.json())
        .then(d => {
            sel.innerHTML = "";
            let count = 0;
            if (d.success && d.filaments) {
                const terms = term.split(' ').map(t => t.trim()).filter(t => t.length > 0);

                d.filaments.forEach(f => {
                    const name = `${f.vendor?.name || 'Generic'} ${f.material} - ${f.name || 'Unknown'}`;
                    const target = name.toLowerCase();
                    const isMatch = terms.length === 0 || terms.every(t => target.includes(t));

                    if (isMatch) {
                        sel.innerHTML += `<option value="${f.id}">${name} (ID: ${f.id})</option>`;
                        count++;
                    }
                });
                if (count === 0) sel.innerHTML = '<option disabled>No matches found</option>';
            } else {
                sel.innerHTML = '<option disabled>Error loading filaments</option>';
            }
        })
        .catch(e => {
            console.error("Filament fetch failed", e);
            sel.innerHTML = '<option disabled>Network Error</option>';
        });
};

window.wizardExistingSelected = () => {
    const sel = document.getElementById('wiz-existing-results');
    if (sel.value) {
        wizardState.selectedFilamentId = sel.value;
        document.getElementById('wiz-status-msg').innerHTML = `Selected Existing Filament ID: <strong>${sel.value}</strong>`;
        wizardValidateSubmit();
    }
};

// --- EXTERNAL DATABASE LOGIC ---
window.wizardSearchExternal = () => {
    let term = document.getElementById('wiz-search-external').value.trim();
    let source = document.getElementById('wiz-external-source').value;
    const sel = document.getElementById('wiz-external-results');

    // Auto-detect Prusament URLs
    if (term.includes('prusament.com/spool/')) {
        document.getElementById('wiz-external-source').value = 'prusament';
        source = 'prusament';
    }

    if (term.length < 2) return;

    sel.innerHTML = '<option disabled>Querying ' + source + '...</option>';
    document.getElementById('wiz-status-msg').innerText = "Fetching external templates...";

    fetch(`/api/external/search?source=${source}&q=${encodeURIComponent(term)}`)
        .then(r => r.json())
        .then(d => {
            sel.innerHTML = "";
            if (d.success && d.results.length > 0) {
                document.getElementById('wiz-status-msg').innerText = `Found ${d.results.length} templates.`;
                d.results.forEach(f => {
                    // Extract safe display name
                    const brand = f.manufacturer || f.vendor?.name || 'Generic';
                    const mat = f.material || '?';
                    const color = f.color_name || f.name || 'Unknown Color';
                    const wt = f.weight ? ` - ${f.weight}g` : '';
                    const diam = f.diameter || f.settings_extrusion_diameter ? ` (${f.diameter || f.settings_extrusion_diameter}mm)` : '';

                    const opt = document.createElement('option');
                    opt.value = JSON.stringify(f); // Store the full payload in the value
                    opt.innerText = `${brand} ${mat} - ${color}${wt}${diam}`;
                    sel.appendChild(opt);
                });
            } else {
                sel.innerHTML = '<option disabled>No external templates found.</option>';
                document.getElementById('wiz-status-msg').innerText = "Search returned 0 results.";
            }
        })
        .catch(e => {
            console.error("External DB fetch failed", e);
            sel.innerHTML = '<option disabled>Error fetching from database.</option>';
            document.getElementById('wiz-status-msg').innerText = "Network Error.";
        });
};

window.wizardExternalSelected = () => {
    const sel = document.getElementById('wiz-external-results');
    if (sel.value) {
        try {
            const temp = JSON.parse(sel.value);
            wizardState.externalMetaData = temp; // Save for hidden Extra params

            // Auto-fill Step 2 Manual Form!
            document.getElementById('wiz-fil-material').value = temp.material || '';
            document.getElementById('wiz-fil-color_name').value = temp.color_name || temp.name || '';
            document.getElementById('wiz-fil-color_hex_0').value = `#${temp.color_hex || 'FFFFFF'}`;
            document.getElementById('wiz-fil-color_hex_0').previousElementSibling.value = `#${temp.color_hex || 'FFFFFF'}`;
            document.getElementById('wiz-fil-diameter').value = temp.diameter || temp.settings_extrusion_diameter || 1.75;
            document.getElementById('wiz-fil-density').value = temp.density || temp.settings_density || 1.24;
            document.getElementById('wiz-fil-weight').value = temp.weight || 1000;
            document.getElementById('wiz-fil-empty_weight').value = temp.spool_weight || '';

            // Map Temperatures
            if (document.getElementById('wiz-fil-settings_extruder_temp')) {
                document.getElementById('wiz-fil-settings_extruder_temp').value = temp.settings_extruder_temp || '';
            }
            if (document.getElementById('wiz-fil-settings_bed_temp')) {
                document.getElementById('wiz-fil-settings_bed_temp').value = temp.settings_bed_temp || '';
            }

            // Map the API source link into the Product URL field specifically for the Spool if applicable
            if (temp.external_link) {
                const spoolUrlNode = document.getElementById('wiz-spool-product_url');
                const filUrlNode = document.getElementById('wiz-fil-product_url');
                if (spoolUrlNode) spoolUrlNode.value = temp.external_link;
                if (filUrlNode) filUrlNode.value = temp.external_link;
            }

            // Map Vendor
            const vName = temp.manufacturer || temp.vendor?.name;
            if (vName) {
                // Try to find in existing options
                const vSel = document.getElementById('wiz-fil-vendor-sel');
                let found = false;
                for (let i = 0; i < vSel.options.length; i++) {
                    if (vSel.options[i].text.toLowerCase() === vName.toLowerCase()) {
                        vSel.selectedIndex = i;
                        document.getElementById('wiz-fil-vendor-sel').style.display = 'block';
                        document.getElementById('wiz-fil-vendor-new').style.display = 'none';
                        found = true; break;
                    }
                }
                if (!found) {
                    // Force the new vendor text field
                    document.getElementById('wiz-fil-vendor-sel').style.display = 'none';
                    document.getElementById('wiz-fil-vendor-new').style.display = 'block';
                    document.getElementById('wiz-fil-vendor-new').value = vName;
                }
            }

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">✅ Auto-filled from template!</span>`;
            wizardValidateSubmit();

        } catch (e) { console.error("Could not parse external data payload", e); }
    }
};

window.wizardToggleVendorMode = () => {
    const sel = document.getElementById('wiz-fil-vendor-sel');
    const txt = document.getElementById('wiz-fil-vendor-new');
    if (sel.style.display !== 'none') {
        sel.style.display = 'none';
        txt.style.display = 'block';
        txt.focus();
    } else {
        txt.style.display = 'none';
        sel.style.display = 'block';
    }
};

window.wizardSubmit = async () => {
    document.getElementById('btn-wiz-submit').disabled = true;
    const msg = document.getElementById('wiz-status-msg');
    msg.innerText = "Processing...";

    const getVal = (id) => {
        const el = document.getElementById(id);
        if (!el) throw new Error(`Missing DOM Element: ${id}`);
        return el.value;
    };

    try {
        const qty = parseInt(getVal('wiz-spool-qty')) || 1;

        // Construct Spool Payload
        let sp_payload = {
            used_weight: parseFloat(getVal('wiz-spool-used')) || 0,
            empty_weight: parseFloat(getVal('wiz-spool-empty_weight')) || null,
            initial_weight: parseFloat(getVal('wiz-spool-initial_weight')) || null,
            location: getVal('wiz-spool-location') || '',
            comment: getVal('wiz-spool-comment') || '',
            extra: {}
        };

        // Extract Dynamic Spool Fields
        document.querySelectorAll('.dynamic-extra-spool-field').forEach(el => {
            const key = el.getAttribute('data-key');
            if (!key) return;
            if (el.type === 'checkbox') {
                sp_payload.extra[key] = el.checked;
            } else if (el.value) {
                sp_payload.extra[key] = el.value;
            }
        });

        Object.keys(sp_payload).forEach(k => sp_payload[k] == null && delete sp_payload[k]);

        let f_payload = null;
        let target_fid = null;

        if (wizardState.mode === 'existing') {
            target_fid = wizardState.selectedFilamentId;
        } else {
            // Hex Parsing for Multiple Colors
            const colorInputs = Array.from(document.querySelectorAll('input[id^="wiz-fil-color_hex_"]'));
            const colors = colorInputs.map(i => i.value.replace('#', '').toUpperCase()).filter(c => c.length === 6);

            f_payload = {
                name: getVal('wiz-fil-color_name') || 'Unknown',
                material: getVal('wiz-fil-material') || 'PLA',
                weight: parseFloat(getVal('wiz-fil-weight')) || 1000,
                spool_weight: parseFloat(getVal('wiz-fil-empty_weight')) || null,
                diameter: parseFloat(getVal('wiz-fil-diameter')) || 1.75,
                density: parseFloat(getVal('wiz-fil-density')) || 1.24,
                color_hex: colors.length > 0 ? colors[0] : 'FFFFFF',
                extra: {}
            };

            // Cross-Inherit Empty Weight to Spool if left blank in Step 3
            if (sp_payload.empty_weight === null && f_payload.spool_weight !== null) {
                sp_payload.empty_weight = f_payload.spool_weight;
            }

            // Note: Spoolman stores gradient sequences directly in DB or via 'color_hexes' comma-separated depending on fork.
            // Spoolman 0.19.1 natively supports `color_hex` as string, and `multi_color_hexes` / `color_hexes` in recent forks.
            // Let's pass the array into extra in case the user wants gradient rendering strings
            if (colors.length > 1) {
                f_payload.extra['color_hexes'] = colors.join(','); // Standard gradient payload
                f_payload.multi_color_direction = document.getElementById('wiz-fil-color-direction').value;
                f_payload.multi_color_hexes = colors.join(',');
            }
            // Extract Custom Dynamic Fields (Standard and Checkboxes)
            document.querySelectorAll('.dynamic-extra-field').forEach(el => {
                const key = el.getAttribute('data-key');
                if (!key) return;

                if (el.type === 'checkbox') {
                    f_payload.extra[key] = el.checked;
                } else if (el.value) {
                    f_payload.extra[key] = el.value;
                }
            });

            // Extract Custom Dynamic Fields (Chips)
            document.querySelectorAll('.dynamic-chip[data-selected="true"]').forEach(el => {
                const key = el.getAttribute('data-key');
                const val = el.getAttribute('data-value');
                if (!key || !val) return;

                if (!f_payload.extra[key]) f_payload.extra[key] = [];
                f_payload.extra[key].push(val);
            });

            const isNewVendor = document.getElementById('wiz-fil-vendor-sel').style.display === 'none';
            if (!isNewVendor && getVal('wiz-fil-vendor-sel')) {
                f_payload.vendor_id = parseInt(getVal('wiz-fil-vendor-sel'));
            } else if (isNewVendor && getVal('wiz-fil-vendor-new')) {
                f_payload.extra['external_vendor_name'] = getVal('wiz-fil-vendor-new');
            }

            if (wizardState.mode === 'external' && wizardState.externalMetaData) {
                const t = wizardState.externalMetaData;
                if (t.extruder_temp) f_payload.settings_extruder_temp = t.extruder_temp;
                if (t.bed_temp) f_payload.settings_bed_temp = t.bed_temp;
                if (t.article_number) f_payload.article_number = t.article_number;
            }

            Object.keys(f_payload).forEach(k => f_payload[k] == null && delete f_payload[k]);
        }

        const payload = {
            filament_id: target_fid,
            filament_data: f_payload,
            spool_data: sp_payload,
            quantity: qty
        };

        const res = await fetch('/api/create_inventory_wizard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.success) {
            msg.innerHTML = `<span class="text-success fw-bold">Success! Spool(s) Generated.</span>`;

            // Keep modal open across all modes so user can rapidly create subsequent items.
            setTimeout(() => {
                msg.innerHTML = "";
                document.getElementById('btn-wiz-submit').disabled = false;
            }, 3000);

        } else {
            msg.innerHTML = `<span class="text-danger">Error: ${data.msg}</span>`;
            document.getElementById('btn-wiz-submit').disabled = false;
        }
    } catch (e) {
        console.error("Wizard Submit Error:", e);
        msg.innerHTML = `<span class="text-danger">Frontend Error: ${e.message}</span>`;
        document.getElementById('btn-wiz-submit').disabled = false;
    }
};

// --- SPOOL CLONE LOGIC ---
window.openCloneWizard = (spoolId) => {
    // Hide Spool Modal or Backlog Modal if open
    const smEl = document.getElementById('spoolModal');
    if (smEl) {
        const sm = bootstrap.Modal.getInstance(smEl) || new bootstrap.Modal(smEl);
        sm.hide();
    }
    const bmEl = document.getElementById('backlogModal');
    if (bmEl) {
        const bm = bootstrap.Modal.getInstance(bmEl) || new bootstrap.Modal(bmEl);
        bm.hide();
    }

    // Reset and Open Wizard
    openWizardModal();

    // Temporarily disable submit while fetching clone data
    document.getElementById('btn-wiz-submit').disabled = true;
    document.getElementById('wiz-status-msg').innerHTML = '<span class="text-warning">Cloning spool data...</span>';

    // Fetch Spool data to clone
    fetch(`/api/spool_details?id=${spoolId}`)
        .then(r => r.json())
        .then(d => {
            if (!d || !d.filament) {
                document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to fetch clone data.</span>';
                return;
            }

            // Switch to Existing Filament Mode
            wizardSelectType('existing');

            // Inject Filament into Dropdown & Auto-Select
            const f = d.filament;
            const name = `${f.vendor?.name || 'Generic'} ${f.material} - ${f.name || 'Unknown'}`;
            const sel = document.getElementById('wiz-existing-results');
            sel.innerHTML = `<option value="${f.id}" selected>${name} (ID: ${f.id})</option>`;
            wizardExistingSelected();

            // Pre-fill Spool parameters that usually carry over when cloning
            document.getElementById('wiz-spool-location').value = d.location || "";
            document.getElementById('wiz-spool-empty_weight').value = d.spool_weight !== null ? d.spool_weight : "";
            document.getElementById('wiz-spool-used').value = 0; // Fresh spool is usually 0
            document.getElementById('wiz-spool-comment').value = d.comment || "";

            document.getElementById('wiz-status-msg').innerHTML = `<span class="text-success">Wizard successfully pre-filled from Spool #${spoolId}.</span>`;
        })
        .catch(err => {
            console.error("Clone Wizard Error:", err);
            document.getElementById('wiz-status-msg').innerHTML = '<span class="text-danger">Failed to connect for clone.</span>';
            document.getElementById('btn-wiz-submit').disabled = false;
        });
};
