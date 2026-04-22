/* MODULE: LOCATION MANAGER (Gold Standard - Polished v31 - 0-Index Fix) */
console.log("🚀 Loaded Module: LOCATION MANAGER (Gold Standard v31)");

document.addEventListener('inventory:buffer-updated', () => {
    const modal = document.getElementById('manageModal');
    if (modal && modal.classList.contains('show')) {
        renderManagerNav();
        // Refresh to update Deposit button visibility
        const id = document.getElementById('manage-loc-id').value;
        if (id) refreshManageView(id);
    }
});

window.openLocationsModal = () => { modals.locMgrModal.show(); fetchLocations(); };

window.updateManageTitle = (loc, itemArray = null) => {
    let occHtml = ``;
    let occupancyStr = loc.Occupancy || '--';
    
    // [ALEX FIX] Real-time mathematical override for instantaneous title snappiness
    // Safely parse capacity. Arrays returned from /api/get_contents represent direct physical counts.
    if (itemArray !== null && loc['Max Spools']) {
        const capacity = parseInt(loc['Max Spools']);
        // Use realistic count ignoring virtual ghost spools? No, payload is physical items.
        occupancyStr = `${itemArray.length}/${capacity > 0 ? capacity : '--'}`;
    }

    if (occupancyStr !== '--') {
        const parts = occupancyStr.split('/');
        let occColor = '#fff';
        let isEmpty = parseInt(parts[0]) === 0;

        if (parts.length === 2 && !isNaN(parseInt(parts[0])) && !isNaN(parseInt(parts[1]))) {
            if (parseInt(parts[0]) >= parseInt(parts[1])) occColor = '#ff4444'; // Red if full
            else if (isEmpty) occColor = '#ffc107'; // Yellow if empty
        } else if (isEmpty) {
            occColor = '#ffc107';
        }
        
        let emptyWarn = '';
        if (occColor === '#ffc107') {
            emptyWarn = `<span class="text-pop ms-2" style="font-size:1.4rem; color:#ffc107; font-weight: 900; line-height: 1;">⚠️ EMPTY</span>`;
        }

        let occText = `${occupancyStr} Spools`;
        if (parts.length === 1 || isNaN(parseInt(parts[1]))) {
            occText = `Total Spools: ${parseInt(parts[0])}`;
        }

        occHtml = `<span class="text-pop ms-3" style="color:${occColor}; font-size:1.1rem; border-left: 2px solid #555; padding-left: 12px;">${occText}</span>${emptyWarn}`;
    }

    let badgeClass = 'bg-secondary';
    let badgeStyle = 'border:1px solid #555;';
    const t = loc.Type || '';
    if (t.includes('Dryer')) { badgeClass = 'bg-warning text-dark'; badgeStyle = 'border:1px solid #fff;'; }
    else if (t.includes('Storage')) { badgeClass = 'bg-primary'; badgeStyle = 'border:1px solid #88f;'; }
    else if (t.includes('MMU')) { badgeClass = 'bg-danger'; badgeStyle = 'border:1px solid #f88;'; }
    else if (t.includes('Shelf')) { badgeClass = 'bg-success'; badgeStyle = 'border:1px solid #8f8;'; }
    else if (t.includes('Cart')) { badgeClass = 'bg-info text-dark'; badgeStyle = 'border:1px solid #fff;'; }
    else if (t.includes('Printer') || t.includes('Toolhead')) { badgeClass = 'bg-dark'; badgeStyle = 'border:1px solid #f0f; background-color: #aa00ff !important; color: #fff;'; }
    else if (t.includes('Virtual')) { badgeClass = 'bg-light text-dark'; badgeStyle = 'border:1px solid #fff; box-shadow: 0 0 5px rgba(255,255,255,0.5);'; }
    
    const typeBadge = `<span class="badge ${badgeClass} ms-3 fs-6" style="box-shadow: 1px 1px 3px rgba(0,0,0,0.5); padding-top: 5px; ${badgeStyle}">${loc.Type}</span>`;

    document.getElementById('manageTitle').innerHTML = `<div class="d-flex align-items-center">📍 ${loc.LocationID} ${typeBadge} ${occHtml}</div>`;
};

// --- PRE-FLIGHT PROTOCOL ---
window.openManage = (id) => {
    setProcessing(true);

    const loc = state.allLocations.find(l => l.LocationID == id);
    if (!loc) { setProcessing(false); return; }

    window.updateManageTitle(loc);
    document.getElementById('manage-loc-id').value = id;
    const input = document.getElementById('manual-spool-id');
    if (input) input.value = "";

    // 1. Wipe old data
    document.getElementById('slot-grid-container').innerHTML = '';
    document.getElementById('manage-contents-list').innerHTML = '';
    document.getElementById('unslotted-container').innerHTML = '';

    document.getElementById('manage-grid-view').style.display = 'none';
    document.getElementById('manage-list-view').style.display = 'none';



    const isGrid = (loc.Type === 'Dryer Box' || loc.Type === 'MMU Slot') && parseInt(loc['Max Spools']) > 1;

    fetch(`/api/get_contents?id=${id}`)
        .then(r => r.json())
        .then(d => {
            if (isGrid) {
                document.getElementById('manage-grid-view').style.display = 'block';
                document.getElementById('manage-list-view').style.display = 'none';
                renderGrid(d, parseInt(loc['Max Spools']));
            } else {
                document.getElementById('manage-grid-view').style.display = 'none';
                document.getElementById('manage-list-view').style.display = 'block';
                renderList(d, id);
            }

            renderManagerNav();
            // Phase 2: render the Slot → Toolhead Feeds section if applicable.
            if (window.renderFeedsSection) window.renderFeedsSection(loc);
            // Phase 3: render the Quick-Swap grid if this is a toolhead.
            if (window.renderQuickSwapSection) window.renderQuickSwapSection(loc);
            // Generate QR for specific location
            const safeId = String(id).replace(/['"]/g, '');
            generateSafeQR('manage-loc-qr-mini', 'LOC:' + safeId, 45);
            generateSafeQR('qr-modal-done', 'CMD:DONE', 58);

            // Prime the Hash to prevent "First Pulse Wiggle"
            const bufHash = state.heldSpools.map(s => s.id).join(',');
            state.lastLocRenderHash = `${JSON.stringify(d)}|${bufHash}`;

            setProcessing(false);
            modals.manageModal.show();
        })
        .catch(e => {
            console.error(e);
            setProcessing(false);
            showToast("Failed to load location data", "error");
        });
};

// Breadcrumb for chained manage views. When the user clicks e.g. "Edit Full
// Bindings" from a toolhead, openManage re-renders onto the dryer box but the
// user's mental model is "I went deeper into a flow" — closeManage should
// pop back to the toolhead, not drop to the locations list.
//
// Stack discipline:
// - Push only when we're navigating inside an already-open manage modal.
//   Pushing on a fresh open from the locations list would mistakenly
//   resurrect whatever location the user was looking at last session.
// - On a real close (empty stack), clear the manage-loc-id value so the
//   NEXT fresh open has no stale previous to push onto the stack.
window.manageNavStack = window.manageNavStack || [];
window._fccPoppingBreadcrumb = false;

(function _installManageBreadcrumb() {
    const original = window.openManage;
    if (!original || original._fcc_wrapped) return;
    const wrapped = (id) => {
        if (!window._fccPoppingBreadcrumb) {
            const modalEl = document.getElementById('manageModal');
            const modalOpen = !!(modalEl && modalEl.classList.contains('show'));
            const prev = document.getElementById('manage-loc-id');
            const prevId = prev ? prev.value : '';
            // Only push when we're *already inside* the manage modal and
            // navigating to a different location. First-opens from the
            // locations list must NOT push — otherwise closing the modal
            // after the next unrelated open would re-surface a stale view.
            if (modalOpen && prevId && String(prevId) !== String(id)) {
                window.manageNavStack.push(prevId);
            }
        }
        return original(id);
    };
    wrapped._fcc_wrapped = true;
    window.openManage = wrapped;
})();

window.closeManage = () => {
    if (window.manageNavStack && window.manageNavStack.length > 0) {
        const back = window.manageNavStack.pop();
        if (back) {
            window._fccPoppingBreadcrumb = true;
            try { window.openManage(back); }
            finally { window._fccPoppingBreadcrumb = false; }
            return;
        }
    }
    // Real close: reset breadcrumb state so the NEXT fresh open doesn't
    // inherit a stale previous id.
    window.manageNavStack = [];
    const prev = document.getElementById('manage-loc-id');
    if (prev) prev.value = '';
    modals.manageModal.hide();
    fetchLocations();
};

// Bootstrap's own dismiss paths bypass closeManage entirely, which is
// a problem when we're mid-breadcrumb: a naive close wipes the stack
// and drops the user out to the locations list instead of popping back
// to the previous view.
//
// Strategy:
// - For Escape specifically, intercept at the modal element (capture
//   phase, before Bootstrap's handler) and route through closeManage so
//   the breadcrumb pops exactly like the X button would.
// - For ANY other hide path (backdrop click if enabled, programmatic
//   .hide(), the final .hide() inside closeManage itself), listen for
//   hidden.bs.modal and do the state cleanup. Respect the pop flag so
//   we don't wipe state mid-pop.
document.addEventListener('DOMContentLoaded', () => {
    const modalEl = document.getElementById('manageModal');
    if (!modalEl) return;

    // Document-level Escape handler for the manage-modal flow and a
    // fallback dismisser for other visible Bootstrap modals.
    //
    // Why this exists: Bootstrap 5 attaches its own keyboard-dismiss
    // handler to each modal element, but when modals are stacked (user
    // opens Location List → clicks into a Toolhead/manage modal on top),
    // closing the top one doesn't always restore focus cleanly to the
    // modal beneath. Subsequent Escape presses fire on <body> and
    // Bootstrap's per-modal handler never sees them, so the user gets
    // stuck on the locations list with no keyboard way out.
    //
    // Strategy:
    //   - If manageModal is showing, preempt Bootstrap and route through
    //     closeManage so the breadcrumb pops instead of wiping.
    //   - Otherwise, dismiss the topmost visible Bootstrap modal as a
    //     fallback. This keeps Escape working across the whole stack.
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;

        // Overlays carve-out: if an inline overlay is visible anywhere,
        // let its own listener handle Escape first.
        const confirmOv = document.getElementById('fcc-quickswap-confirm-overlay');
        if (confirmOv && confirmOv.style.display === 'block') return;
        const pickerOv = document.getElementById('fcc-bind-picker-overlay');
        if (pickerOv && pickerOv.style.display === 'block') return;
        const shortcutsOv = document.getElementById('fcc-shortcuts-overlay');
        if (shortcutsOv && shortcutsOv.style.display === 'block') return;
        // Input carve-out: native clear/blur wins inside editable fields.
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable)) return;

        // Manage-modal priority path: breadcrumb pop or close.
        if (modalEl.classList.contains('show')) {
            e.preventDefault();
            e.stopImmediatePropagation();
            window.closeManage();
            return;
        }

        // Fallback: dismiss the topmost visible Bootstrap modal. This
        // covers locMgrModal / locModal / any other stacked modal whose
        // own keyboard handler may have lost focus tracking.
        const shown = Array.from(document.querySelectorAll('.modal.show'));
        if (shown.length === 0) return;
        const topmost = shown.reduce((a, b) => {
            const za = parseInt(getComputedStyle(a).zIndex || '0', 10) || 0;
            const zb = parseInt(getComputedStyle(b).zIndex || '0', 10) || 0;
            return zb > za ? b : a;
        });
        // Respect any modal that has opted out of keyboard dismissal.
        if (topmost.getAttribute('data-bs-keyboard') === 'false') return;
        const inst = (window.bootstrap && window.bootstrap.Modal)
            ? window.bootstrap.Modal.getInstance(topmost)
            : null;
        if (!inst) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        inst.hide();
    }, true);

    modalEl.addEventListener('hidden.bs.modal', () => {
        // If we're mid-breadcrumb-pop, openManage is about to re-render
        // the previous view. Don't wipe state — the pop flow manages it.
        if (window._fccPoppingBreadcrumb) return;

        // Clear breadcrumb state so the next fresh open doesn't inherit
        // stale context.
        window.manageNavStack = [];
        const prev = document.getElementById('manage-loc-id');
        if (prev) prev.value = '';
        // Dismiss any inline overlays that live inside the manage modal.
        if (window.closeQuickswapConfirm) {
            try { window.closeQuickswapConfirm(); } catch (e) { /* noop */ }
        }
        if (window.closeBindSlotPicker) {
            try { window.closeBindSlotPicker(); } catch (e) { /* noop */ }
        }
    });
});

// ---------------------------------------------------------------------------
// Phase 2: Slot → Toolhead Feeds (Dryer Box only)
// ---------------------------------------------------------------------------

// Cached printer_map fetched from /api/printer_map. Shape:
//   { printers: { "🦝 XL": [{location_id, position}, ...] } }
state.printerMap = state.printerMap || null;

const fetchPrinterMap = () => {
    if (state.printerMap) return Promise.resolve(state.printerMap);
    return fetch('/api/printer_map')
        .then(r => r.json())
        .then(data => { state.printerMap = data.printers || {}; return state.printerMap; })
        .catch(e => { console.warn("printer_map fetch failed", e); return {}; });
};

// Render a searchable combobox backed by a native <select> so existing
// save logic (reading .feeds-select.value) keeps working. The text input
// filters a dropdown list; Arrow/Enter/Escape drive selection; clicking
// outside closes the list. Options are labeled "XL-1 — Toolhead 1 on 🦝 XL"
// (no more cryptic "pos #").
const buildFeedsCombobox = (slot, printers, currentTarget) => {
    const comboId = `feeds-combo-${slot}`;
    const optionList = [
        { value: '', label: '— None (staging / drying)', search: 'none staging drying' }
    ];
    Object.keys(printers).sort().forEach(printerName => {
        (printers[printerName] || []).forEach(e => {
            const human = `${e.location_id} — Toolhead ${e.position + 1} on ${printerName}`;
            optionList.push({
                value: e.location_id,
                label: human,
                search: `${e.location_id} ${printerName} toolhead ${e.position + 1}`.toLowerCase(),
                printer: printerName,
            });
        });
    });

    // Preserve a hidden <select> so window.saveFeedsSection keeps working.
    const selOpts = optionList.map(o => {
        const sel = o.value.toUpperCase() === currentTarget ? ' selected' : '';
        return `<option value="${o.value}"${sel}>${o.label}</option>`;
    }).join('');

    const currentLabel = (optionList.find(o => o.value.toUpperCase() === currentTarget)
        || optionList[0]).label;

    return `
        <div class="d-flex align-items-center gap-2 feeds-row" data-slot="${slot}">
            <span class="badge bg-info text-dark fw-bold px-2 py-2"
                  style="min-width:72px; font-size:1rem;">Slot ${slot}</span>
            <div class="feeds-combo position-relative flex-grow-1" data-slot="${slot}" id="${comboId}">
                <input type="text" class="form-control bg-black text-white border-info fw-bold feeds-combo-input"
                    data-slot="${slot}"
                    value="${currentLabel.replace(/"/g, '&quot;')}"
                    style="font-size:1.05rem;"
                    placeholder="Search toolheads…" autocomplete="off">
                <div class="feeds-combo-list position-absolute w-100 bg-dark border border-info rounded mt-1 shadow"
                     data-slot="${slot}"
                     style="display:none; z-index:1050; max-height:260px; overflow-y:auto;">
                </div>
                <select class="feeds-select d-none" data-slot="${slot}">${selOpts}</select>
            </div>
        </div>`;
};

const _comboHydrate = (slot, printers) => {
    const host = document.getElementById(`feeds-combo-${slot}`);
    if (!host) return;
    const input = host.querySelector('.feeds-combo-input');
    const list = host.querySelector('.feeds-combo-list');
    const sel = host.querySelector('.feeds-select');

    const _options = () => {
        const opts = [
            { value: '', label: '— None (staging / drying)', search: 'none staging drying' }
        ];
        Object.keys(printers).sort().forEach(printerName => {
            (printers[printerName] || []).forEach(e => {
                opts.push({
                    value: e.location_id,
                    label: `${e.location_id} — Toolhead ${e.position + 1} on ${printerName}`,
                    search: `${e.location_id} ${printerName} toolhead ${e.position + 1}`.toLowerCase(),
                });
            });
        });
        return opts;
    };

    const options = _options();

    const open = () => { list.style.display = 'block'; };
    const close = () => { list.style.display = 'none'; clearKb(); };
    const clearKb = () => list.querySelectorAll('.kb-active').forEach(el => el.classList.remove('kb-active'));

    const filter = (q) => {
        const needle = (q || '').trim().toLowerCase();
        const matches = !needle ? options : options.filter(o => o.search.includes(needle));
        list.innerHTML = matches.map(o => `
            <div class="feeds-combo-item px-3 py-2 text-light fw-bold" data-value="${o.value}"
                 style="cursor:pointer; font-size:1rem;">${o.label}</div>`).join('');
        Array.from(list.querySelectorAll('.feeds-combo-item')).forEach(el => {
            el.addEventListener('click', () => pick(el.dataset.value, el.innerText));
            el.addEventListener('mouseenter', () => { clearKb(); el.classList.add('kb-active'); });
        });
        if (!matches.length) {
            list.innerHTML = '<div class="text-warning px-3 py-2 small">No matches</div>';
        }
    };

    const pick = (value, label) => {
        sel.value = value;
        input.value = label;
        close();
    };

    input.addEventListener('focus', () => { filter(''); open(); });
    input.addEventListener('input', () => { filter(input.value); open(); });
    input.addEventListener('keydown', (e) => {
        if (list.style.display === 'none') return;
        const items = Array.from(list.querySelectorAll('.feeds-combo-item'));
        if (!items.length) return;
        const idx = items.findIndex(el => el.classList.contains('kb-active'));
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            clearKb();
            items[(idx + 1) % items.length].classList.add('kb-active');
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            clearKb();
            items[(idx - 1 + items.length) % items.length].classList.add('kb-active');
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const target = idx >= 0 ? items[idx] : items[0];
            pick(target.dataset.value, target.innerText);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            close();
            input.blur();
        }
    });
    // Click outside closes.
    document.addEventListener('click', (e) => {
        if (!host.contains(e.target)) close();
    });
};

const renderFeedsSection = (loc) => {
    const section = document.getElementById('manage-feeds-section');
    if (!section) return;

    if (loc.Type !== 'Dryer Box') {
        section.style.display = 'none';
        return;
    }
    section.style.display = 'block';

    document.getElementById('feeds-body').style.display = 'none';
    document.getElementById('feeds-toggle-btn').innerText = 'Show';
    document.getElementById('feeds-status').innerText = '';

    const maxSlots = parseInt(loc['Max Spools']) || 0;
    if (maxSlots <= 0) {
        document.getElementById('feeds-rows').innerHTML =
            '<div class="text-warning fw-bold" style="font-size:1rem;">This location has Max Spools of 0 — no slots to bind.</div>';
        return;
    }

    Promise.all([
        fetchPrinterMap(),
        fetch(`/api/dryer_box/${encodeURIComponent(loc.LocationID)}/bindings`)
            .then(r => r.ok ? r.json() : { slot_targets: {} }),
    ]).then(([printers, bindingsResp]) => {
        const targets = bindingsResp.slot_targets || {};
        const rows = document.getElementById('feeds-rows');
        rows.innerHTML = '';
        for (let slot = 1; slot <= maxSlots; slot++) {
            const currentTarget = (targets[String(slot)] || '').toUpperCase();
            rows.insertAdjacentHTML('beforeend', buildFeedsCombobox(slot, printers, currentTarget));
        }
        for (let slot = 1; slot <= maxSlots; slot++) {
            _comboHydrate(slot, printers);
        }

        // One-shot: if the user came here via "Edit Full Bindings" from a
        // toolhead, auto-expand the Feeds body and scroll it into view so
        // they don't have to click Show and hunt for it.
        if (window._fccAutoExpandFeeds) {
            window._fccAutoExpandFeeds = false;
            const body = document.getElementById('feeds-body');
            const btn = document.getElementById('feeds-toggle-btn');
            if (body) body.style.display = 'block';
            if (btn) btn.innerText = 'Hide';
            // Let the layout settle before scrolling so the target has its
            // final height.
            requestAnimationFrame(() => {
                const anchor = document.getElementById('manage-feeds-section');
                if (anchor && anchor.scrollIntoView) {
                    anchor.scrollIntoView({ block: 'start', behavior: 'smooth' });
                }
            });
        }
    });
};

window.toggleFeedsSection = () => {
    const body = document.getElementById('feeds-body');
    const btn = document.getElementById('feeds-toggle-btn');
    if (!body || !btn) return;
    const hidden = body.style.display === 'none' || !body.style.display;
    body.style.display = hidden ? 'block' : 'none';
    btn.innerText = hidden ? 'Hide' : 'Show';
};

window.saveFeedsSection = () => {
    const locId = document.getElementById('manage-loc-id').value;
    if (!locId) return;
    const status = document.getElementById('feeds-status');
    status.className = 'flex-grow-1 fw-bold text-info';
    status.style.fontSize = '1rem';
    status.innerText = 'Saving…';

    // Collect slot_targets from all hidden <select> elements inside the
    // combobox wrappers. Empty-string values map to None.
    const selects = document.querySelectorAll('#feeds-rows select.feeds-select');
    const slot_targets = {};
    selects.forEach(sel => {
        const slot = sel.dataset.slot;
        const val = sel.value;
        slot_targets[slot] = val || null;
    });

    fetch(`/api/dryer_box/${encodeURIComponent(locId)}/bindings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot_targets }),
    })
        .then(async r => ({ ok: r.ok, body: await r.json() }))
        .then(({ ok, body }) => {
            if (ok) {
                const count = Object.keys(body.slot_targets || {}).length;
                const warnings = body.warnings || [];
                if (warnings.length) {
                    status.className = 'flex-grow-1 fw-bold text-warning';
                    const wTxt = warnings.map(w => `⚠️ Slot ${w.slot} → ${w.target}: ${w.reason}`).join('\n');
                    status.innerText = `Saved ${count} binding(s) — ${warnings.length} warning(s)\n${wTxt}`;
                    showToast(`⚠️ Feeds saved with ${warnings.length} warning(s) — see log`, 'warning', 5000);
                } else {
                    status.className = 'flex-grow-1 fw-bold text-success';
                    status.innerText = `✅ Saved ${count} binding(s)`;
                    showToast(`🔗 Saved feeds for ${locId}`, 'success', 2500);
                }
            } else {
                status.className = 'flex-grow-1 fw-bold text-danger';
                const errs = (body.errors || []).map(e => `Slot ${e.slot}: ${e.reason}`).join('; ');
                status.innerText = errs || body.error || 'Save failed';
                showToast(`❌ Feeds save rejected: ${errs || body.error}`, 'error', 5000);
            }
        })
        .catch(e => {
            console.error(e);
            status.className = 'flex-grow-1 fw-bold text-danger';
            status.innerText = 'Network error';
            showToast('Feeds save — network error', 'error', 5000);
            if (window.logClientEvent) window.logClientEvent(
                `❌ Feeds save network error for ${locId}: ${e && e.message ? e.message : 'connection failed'}`,
                'ERROR'
            );
        });
};

window.renderFeedsSection = renderFeedsSection;

window.refreshManageView = (id) => {
    const loc = state.allLocations.find(l => l.LocationID == id);
    if (!loc) return false;

    // Fetch data first (Don't touch DOM yet)
    fetch(`/api/get_contents?id=${id}`)
        .then(r => r.json())
        .then(d => {
            // --- NO WIGGLE CHECK ---
            // Create a signature of the Content + Buffer State
            const bufHash = state.heldSpools.map(s => s.id).join(',');
            const contentHash = JSON.stringify(d);
            const newHash = `${contentHash}|${bufHash}`;

            // If nothing changed, STOP. This eliminates the wiggle for 99% of sync pulses.
            if (state.lastLocRenderHash === newHash) return;
            state.lastLocRenderHash = newHash;
            // -----------------------

            // Data changed? Okay, render it.
            window.updateManageTitle(loc, d);
            renderManagerNav();
            const isGrid = (loc.Type === 'Dryer Box' || loc.Type === 'MMU Slot') && parseInt(loc['Max Spools']) > 1;
            if (isGrid) renderGrid(d, parseInt(loc['Max Spools']));
            else renderList(d, id);
        });
    return true;
};

// --- HELPER: FORMAT RICH TEXT ---
const getRichInfo = (item) => {
    const d = item.details || {};
    const legacy = d.external_id ? `[Legacy: ${d.external_id}]` : "";
    const brand = d.brand || "Generic";
    const material = d.material || "PLA";
    const name = d.color_name || item.display.replace(/#\d+/, '').trim();
    const weight = d.weight ? `[${Math.round(d.weight)}g]` : "";

    return {
        line1: `#${item.id} ${legacy}`,
        line2: `${brand} ${material}`,
        line3: name,
        line4: weight
    };
};

// --- RED ZONE: NAV DECK ---
const renderManagerNav = () => {
    const n = document.getElementById('loc-mgr-nav-deck');
    if (!n) return;

    if (state.heldSpools.length > 0) {
        n.style.display = 'flex';
        const curItem = state.heldSpools[0];
        const prevItem = state.heldSpools.length > 1 ? state.heldSpools[state.heldSpools.length - 1] : null;
        const nextItem = state.heldSpools.length > 1 ? state.heldSpools[1] : null;
        const curStyle = getFilamentStyle(curItem.color, curItem.color_direction || 'longitudinal');
        const curInfo = getRichInfo(curItem);
        let html = '';

        if (prevItem) {
            html += window.SpoolCardBuilder.buildCard(prevItem, 'buffer_nav', { navDirection: 'prev', navAction: 'window.prevBuffer()' });
        } else { html += `<div style="flex:1;"></div>`; }

        html += `
        <div class="cham-card nav-card nav-card-center" style="background: ${curStyle.frame}; ${curStyle.border ? 'box-shadow: inset 0 0 0 2px #555;' : ''}">
            <div class="fcc-spool-card-inner nav-inner" style="background:${curStyle.inner}; display:flex; flex-direction:column; justify-content:center; align-items:center; padding:10px; text-align:center; position:relative;">
                <div style="position:absolute; top:5px; right:5px; display:flex; gap:6px; z-index: 10;">
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.removeBufferItem(${curItem.id});" title="Drop from Buffer">❌</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); openSpoolDetails(${curItem.id});" title="View Details">🔍</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.openEditWizard(${curItem.id});" title="Edit Spool">✏️</div>
                    <div class="fcc-card-action-btn" onclick="event.stopPropagation(); window.addToQueue({ id: ${curItem.id}, type: 'spool', display: '${curItem.display ? curItem.display.replace(/[\'"]/g, '') : ''}' }); showToast('Added to Print Queue');" title="Add to Print Queue">🖨️</div>
                </div>
                <div class="nav-label">READY TO SLOT</div>
                ${(curItem.archived === true || String(curItem.archived).toLowerCase() === 'true') ? `<div class="badge text-bg-danger mb-2" style="font-size: 0.9rem;">📦 ARCHIVED</div>` : ''}
                <div class="id-badge-gold shadow-sm mb-2" style="font-size:1.4rem;">#${curItem.id}</div>
                <div class="nav-text-main" style="font-size:1.3rem; margin-bottom:5px;">${curInfo.line3}</div>
                <div class="text-pop" style="font-size:1.0rem; color:#fff; font-weight:bold;">${curInfo.line2}</div>
            </div>
        </div>`;

        if (nextItem) {
            html += window.SpoolCardBuilder.buildCard(nextItem, 'buffer_nav', { navDirection: 'next', navAction: 'window.nextBuffer()' });
        } else { html += `<div style="flex:1;"></div>`; }

        n.innerHTML = html;
        requestAnimationFrame(() => {
            if (prevItem) generateSafeQR("qr-nav-prev", "CMD:PREV", 50);
            if (nextItem) generateSafeQR("qr-nav-next", "CMD:NEXT", 50);
        });
    } else {
        n.style.display = 'none';
        n.innerHTML = "";
    }
};

window.handleLabelClick = (e, id, display) => {
    e.stopPropagation();
    window.addToQueue({ id: id, type: 'spool', display: display });
};

// --- YELLOW ZONE: SLOT GRID RENDERER ---
const renderGrid = (data, max) => {
    const grid = document.getElementById('slot-grid-container');
    const un = document.getElementById('unslotted-container');
    grid.innerHTML = ""; un.innerHTML = ""; state.currentGrid = {};
    const unslotted = [];

    data.forEach(i => {
        if (i.slot && parseInt(i.slot) > 0) state.currentGrid[i.slot] = i;
        else unslotted.push(i);
    });

    let gridHTML = "";
    for (let i = 1; i <= max; i++) {
        const item = state.currentGrid[i];
        if (item) {
            gridHTML += window.SpoolCardBuilder.buildCard(item, 'loc_grid', { slotNum: i, locId: document.getElementById('manage-loc-id').value });
        } else {
            // FIX: Removed opacity:0.5 from QR div to make it sharp and scannable
            gridHTML += `
                <div class="slot-btn empty" onclick="handleSlotInteraction(${i})">
                    <div class="slot-inner-gold">
                        <div class="slot-header"><div class="slot-num-gold" style="color:#555;">SLOT ${i}</div></div>
                        <div id="qr-slot-${i}" class="bg-white p-2 rounded mt-3 mb-3"></div>
                        <div class="fs-4 text-light fw-bold" style="margin-top:20px;">EMPTY</div>
                        <div style="height:35px;"></div>
                    </div>
                </div>`;
        }
    }
    grid.innerHTML = gridHTML;

    for (let i = 1; i <= max; i++) {
        const item = state.currentGrid[i];
        requestAnimationFrame(() => {
            if (item) generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:" + i, 90);
            else generateSafeQR(`qr-slot-${i}`, "CMD:SLOT:" + i, 80);
        });
    }

    if (unslotted.length > 0) renderUnslotted(unslotted);
    else un.style.display = 'none';
};

// --- GREEN ZONE: LIST RENDERER ---
const renderList = (data, locId) => {
    const list = document.getElementById('manage-contents-list');
    const emptyMsg = document.getElementById('manage-empty-msg');

    list.innerHTML = "";

    // 1. DEPOSIT CARD
    if (state.heldSpools.length > 0) {
        const item = state.heldSpools[0];
        const styles = getFilamentStyle(item.color, item.color_direction || 'longitudinal');

        if (emptyMsg) emptyMsg.style.display = 'none';

        const depositCard = document.createElement('div');
        depositCard.className = "cham-card manage-list-item";
        depositCard.style.cssText = `background:${styles.frame}; border: 2px dashed #fff; cursor: pointer; margin-bottom: 15px;`;
        depositCard.onclick = () => doAssign(locId, item.id, null);

        depositCard.innerHTML = `
            <div class="list-inner-gold" style="background: ${styles.inner}; justify-content: center; align-items: center; flex-direction: column; padding: 15px;">
                <div class="text-pop" style="font-size: 1.5rem; font-weight: 900; color: #fff; text-transform: uppercase;">
                    ⬇️ DEPOSIT HERE
                </div>
                <div id="qr-deposit-trigger" class="bg-white p-2 rounded mb-2 mt-2" style="box-shadow: 0 4px 10px rgba(0,0,0,0.5);"></div>
                
                <div class="text-pop-light" style="color: #fff; margin-top: 5px; font-weight: bold;">
                    #${item.id} - ${item.display}
                </div>
            </div>`;

        list.appendChild(depositCard);
    }
    else {
        if (data.length === 0) {
            if (emptyMsg) emptyMsg.style.display = 'block';
        } else {
            if (emptyMsg) emptyMsg.style.display = 'none';
        }
    }

    // 2. Existing Items
    if (data.length > 0) {
        const grouped = {};
        data.forEach(s => {
            const sLoc = s.location || "Unassigned";
            if (!grouped[sLoc]) grouped[sLoc] = [];
            grouped[sLoc].push(s);
        });

        const gKeys = Object.keys(grouped);
        // Ensure the root parent location comes first
        gKeys.sort((a,b) => {
            if (a.toLowerCase() === locId.toLowerCase()) return -1;
            if (b.toLowerCase() === locId.toLowerCase()) return 1;
            return a.localeCompare(b);
        });

        const reOrderedData = [];
        let flatIndex = 0;

        const borderColors = ['border-info', 'border-warning', 'border-success', 'border-danger', 'border-primary', 'border-secondary'];

        gKeys.forEach((gLoc, index) => {
            const isFloating = gLoc.toLowerCase() === locId.toLowerCase();
            const hideHeader = gKeys.length === 1 && isFloating;
            
            const groupWrapper = document.createElement('div');
            const bColor = borderColors[index % borderColors.length];
            
            if (!hideHeader) {
                groupWrapper.className = `p-2 mb-3 rounded border border-2 ${bColor} bg-dark`;
                groupWrapper.style.boxShadow = "inset 0 0 10px rgba(0,0,0,0.5)";
                
                const subHead = document.createElement('div');
                if (isFloating) {
                    subHead.className = `d-flex justify-content-between align-items-center border-bottom border-2 pb-2 mb-2 ${bColor}`;
                    subHead.innerHTML = `
                        <div class="d-flex align-items-center">
                            <span class="btn btn-sm btn-outline-light px-2 py-0 border-0 fs-5 me-2" onclick="this.parentElement.parentElement.nextElementSibling.classList.toggle('d-none'); this.innerText = this.innerText === '-' ? '+' : '-';">-</span>
                            <h5 class="text-light m-0 fw-bold" style="font-size:1.1rem;">☁️ Loose / Floating</h5>
                        </div>`;
                } else {
                    subHead.className = `d-flex justify-content-between align-items-center border-bottom border-2 pb-2 mb-2 ${bColor}`;
                    const isPrinter = gLoc.includes('PRINTER') || gLoc.includes('CORE') || gLoc.includes('XL') || gLoc.includes('MK');
                    const icon = isPrinter ? '🖨️' : '📦';
                    subHead.innerHTML = `
                         <div class="d-flex align-items-center">
                              <span class="btn btn-sm btn-outline-light px-2 py-0 border-0 fs-5 me-2" onclick="this.parentElement.parentElement.nextElementSibling.classList.toggle('d-none'); this.innerText = this.innerText === '-' ? '+' : '-';">-</span>
                              <h5 class="text-info m-0 fw-bold" style="font-size:1.1rem;">${icon} <span class="text-white">${gLoc}</span></h5>
                         </div>
                         <button class="btn btn-sm btn-outline-info py-0 px-2 fw-bold" onclick="openManage('${gLoc}')">Manage / View</button>`;
                }
                groupWrapper.appendChild(subHead);
            }
            
            const itemsContainer = document.createElement('div');
            itemsContainer.className = "d-flex flex-column gap-2 mt-2";

            grouped[gLoc].forEach(s => {
                reOrderedData.push(s);
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = renderBadgeHTML(s, flatIndex, locId);
                const el = tempDiv.firstElementChild;
                const btnLabel = el.querySelector('.js-btn-label');
                if (btnLabel) {
                    btnLabel.addEventListener('click', (e) => {
                        e.stopPropagation();
                        window.addToQueue({ id: s.id, type: 'spool', display: s.display });
                    });
                }
                itemsContainer.appendChild(el);
                flatIndex++;
            });
            
            if (!hideHeader) {
                groupWrapper.appendChild(itemsContainer);
                list.appendChild(groupWrapper);
            } else {
                // If it's just a single flat root location, just append items directly to avoid empty bounding box
                itemsContainer.childNodes.forEach(child => list.appendChild(child.cloneNode(true)));
            }
        });

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                reOrderedData.forEach((s, i) => renderBadgeQRs(s, i));
                generateSafeQR('qr-eject-all-list', 'CMD:EJECTALL', 56);

                if (document.getElementById('qr-deposit-trigger')) {
                    const safeId = String(locId).replace(/['"]/g, '');
                    generateSafeQR('qr-deposit-trigger', 'LOC:' + safeId, 85);
                }
            });
        });
    } else {
        requestAnimationFrame(() => {
            if (document.getElementById('qr-deposit-trigger')) {
                const safeId = String(locId).replace(/['"]/g, '');
                generateSafeQR('qr-deposit-trigger', 'LOC:' + safeId, 85);
            }
        });
    }

};

const renderUnslotted = (items) => {
    const un = document.getElementById('unslotted-container');
    if (!un) return;
    un.style.display = 'block';

    let html = `<h4 class="text-info border-bottom border-secondary pb-2 mb-3 mt-4">Unslotted Items</h4>`;
    un.innerHTML = html;

    const itemContainer = document.createElement('div');
    items.forEach((s, i) => {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = renderBadgeHTML(s, i, document.getElementById('manage-loc-id').value);
        const el = tempDiv.firstElementChild;
        const btnLabel = el.querySelector('.js-btn-label');
        if (btnLabel) {
            btnLabel.addEventListener('click', (e) => {
                e.stopPropagation();
                window.addToQueue({ id: s.id, type: 'spool', display: s.display });
            });
        }
        itemContainer.appendChild(el);
    });

    un.appendChild(itemContainer);

    const dangerDiv = document.createElement('div');
    dangerDiv.className = "danger-zone mt-4 pt-3 border-top border-danger";
    dangerDiv.innerHTML = `
        <div class="cham-card manage-list-item" style="border-color:#dc3545; background:#300;">
            <div class="eject-card-inner">
                <div class="eject-label-text"><span style="font-size:3rem; vertical-align:middle;">☢️</span> DANGER ZONE</div>
                <div class="action-badge" style="border-color:#dc3545; background:#1f1f1f;" onclick="triggerEjectAll(document.getElementById('manage-loc-id').value)">
                    <div id="qr-eject-all" class="qr-bg-white"></div>
                    <div class="badge-btn-gold text-white bg-danger mt-1 rounded">EJECT ALL</div>
                </div>
            </div>
        </div>`;
    un.appendChild(dangerDiv);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            items.forEach((s, i) => renderBadgeQRs(s, i));
            generateSafeQR("qr-eject-all", "CMD:EJECTALL", 65);
        });
    });
};

const renderBadgeHTML = (s, i, locId) => {
    return window.SpoolCardBuilder.buildCard(s, 'loc_list', { locId: locId, index: i });
};

const renderBadgeQRs = (s, i) => {
    generateSafeQR(`qr-pick-${i}`, "ID:" + s.id, 70);
    generateSafeQR(`qr-print-${i}`, "CMD:PRINT:" + s.id, 70);
    generateSafeQR(`qr-trash-${i}`, "CMD:TRASH:" + s.id, 70);
};

// --- INTERACTION ---
window.handleSlotInteraction = (slot) => {
    const locId = document.getElementById('manage-loc-id').value, item = state.currentGrid[slot];
    if (state.heldSpools.length > 0) {
        const newId = state.heldSpools[0].id;
        if (item) {
            promptAction("Slot Occupied", `Swap/Overwrite Slot ${slot}?`, [
                {
                    label: "Swap", action: () => {
                        let isFromBuf = true;
                        state.heldSpools.shift();
                        state.heldSpools.push({ id: item.id, display: item.display, color: item.color });
                        if (window.renderBuffer) window.renderBuffer();
                        renderManagerNav();
                        doAssign(locId, newId, slot, isFromBuf);
                    }
                },
                {
                    label: "Overwrite", action: () => {
                        let isFromBuf = true;
                        state.heldSpools.shift();
                        if (window.renderBuffer) window.renderBuffer();
                        renderManagerNav();
                        doAssign(locId, newId, slot, isFromBuf);
                    }
                },
                { label: "Cancel", action: () => { closeModal('actionModal'); } }
            ]);
        } else {
            let isFromBuf = true;
            state.heldSpools.shift();
            if (window.renderBuffer) window.renderBuffer();
            renderManagerNav();
            doAssign(locId, newId, slot, isFromBuf);
        }
    } else if (item) {
        promptAction("Slot Action", `Manage ${item.display}`, [
            {
                label: "✋ Pick Up", action: () => {
                    state.heldSpools.unshift({ id: item.id, display: item.display, color: item.color });
                    if (window.renderBuffer) window.renderBuffer();
                    renderManagerNav();
                    closeModal('actionModal');
                }
            },
            { label: "🗑️ Eject", action: () => { doEject(item.id, locId, false); } },
            { label: "🖨️ Details", action: () => { openSpoolDetails(item.id); } }
        ]);
    }
};

window.doAssign = (loc, spool, slot, isFromBufferFlag = null) => {
    setProcessing(true);

    // FIX: 0-based index correction for MMU/CORE slots
    let finalSlot = slot;
    if (slot !== null) {
        const locObj = state.allLocations.find(l => l.LocationID === loc);
        // If Type is 'MMU Slot', we assume backend expects 0-based indexing (0..N-1)
        // Frontend grid is 1-based (1..N). So we subtract 1.
        if (locObj && locObj.Type === 'MMU Slot') {
            finalSlot = parseInt(slot) - 1;
        }
    }

    const spoolIdStr = String(spool).replace("ID:", "");
    let isFromBuffer = isFromBufferFlag !== null ? isFromBufferFlag : false;
    if (isFromBufferFlag === null) {
        if (state.heldSpools.findIndex(s => String(s.id) === spoolIdStr) > -1) {
            isFromBuffer = true;
        }
    }

    if (isFromBuffer) {
        const spoolObj = state.heldSpools.find(s => String(s.id) === spoolIdStr);
        if (spoolObj && (spoolObj.archived === true || String(spoolObj.archived).toLowerCase() === 'true')) {
            showToast("Cannot assign an ARCHIVED spool to a location!", "error");
            setProcessing(false);
            return;
        }
    }

    fetch('/api/manage_contents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'add', location: loc, spool_id: "ID:" + spool, slot: finalSlot, origin: isFromBuffer ? 'buffer' : '' }) })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (res.status === 'success') {
                showToast("Assigned");

                // --- FIX: Remove the assigned spool from buffer ---
                const bufIdx = state.heldSpools.findIndex(s => String(s.id) === spoolIdStr);
                if (bufIdx > -1) {
                    state.heldSpools.splice(bufIdx, 1);
                    if (window.renderBuffer) window.renderBuffer();
                }

                if (window.fetchLocations) window.fetchLocations();
                refreshManageView(loc);
            }
            else showToast(res.msg, 'error');
        })
        .catch(() => setProcessing(false));
};

window.ejectSpool = (sid, loc, pickup) => {
    if (pickup) {
        fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: "ID:" + sid, source: 'keyboard' }) })
            .then(r => r.json())
            .then(res => {
                if (res.type === 'spool') {
                    if (state.heldSpools.some(s => s.id === res.id)) showToast("In Buffer");
                    else {
                        state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color });
                        if (window.renderBuffer) window.renderBuffer();
                        renderManagerNav();
                    }
                }
            });
    } else {
        if (loc !== "Scan") requestConfirmation(`Eject spool #${sid}?`, () => doEject(sid, loc));
        else doEject(sid, loc);
    }
};

window.doEject = (sid, loc, isConfirmed = false) => {
    setProcessing(true);
    fetch('/api/manage_contents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'remove', location: loc, spool_id: sid, confirmed: isConfirmed }) })
        .then(r => r.json())
        .then((res) => {
            setProcessing(false);
            
            if (res.require_confirm) {
                requestConfirmation(res.msg || `True Unassign spool #${sid}? It is currently floating in a room.`, () => {
                    window.doEject(sid, loc, true);
                });
                return;
            }
            if (!res.success) {
                showToast(res.msg || "Failed to eject spool", "error");
                return;
            }
            
            showToast("Ejected");
            if (loc !== "Scan") {
                // [ALEX FIX] Force a re-render by clearing the hash. 
                // This ensures the UI updates to "Empty" even if the API data is cached/similar.
                state.lastLocRenderHash = null;
                if (window.fetchLocations) window.fetchLocations();
                refreshManageView(loc);
            }
        })
        .catch(() => setProcessing(false));
};

window.manualAddSpool = () => {
    const val = document.getElementById('manual-spool-id').value.trim();
    if (!val) return;
    setProcessing(true);
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: val, source: 'keyboard' }) })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            document.getElementById('manual-spool-id').value = "";
            document.getElementById('manual-spool-id').focus();
            if (res.type === 'spool') {
                if (state.heldSpools.some(s => s.id === res.id)) showToast("Already in Buffer", "warning");
                else {
                    state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color });
                    if (window.renderBuffer) window.renderBuffer();
                    renderManagerNav();
                    showToast("Added to Buffer");
                }
            } else if (res.type === 'filament') openFilamentDetails(res.id);
            else showToast(res.msg || "Invalid Code", 'warning');
        })
        .catch(() => setProcessing(false));
};

window.triggerEjectAll = (loc) => promptSafety(`Nuke all unslotted in ${loc}?`, () => {
    setProcessing(true);
    fetch('/api/manage_contents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'clear_location', location: loc }) })
        .then(r => r.json())
        .then(() => { setProcessing(false); if(window.fetchLocations) window.fetchLocations(); refreshManageView(loc); showToast("Cleared!"); });
});

window.printCurrentLocationLabel = () => {
    const locId = document.getElementById('manage-loc-id').value;
    if (!locId) return;
    window.addToQueue({ id: locId, type: 'location', display: `Location: ${locId}` });
};

window.openEdit = (id) => {
    const i = state.allLocations.find(l => l.LocationID == id);
    if (i) {
        modals.locMgrModal.hide();
        document.getElementById('edit-original-id').value = id;
        document.getElementById('edit-id').value = id;
        document.getElementById('edit-name').value = i.Name;
        document.getElementById('edit-type').value = i.Type;
        document.getElementById('edit-max').value = i['Max Spools'];
        modals.locModal.show();
    }
};

window.closeEdit = () => { modals.locModal.hide(); modals.locMgrModal.show(); };

window.saveLocation = () => {
    fetch('/api/locations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            old_id: document.getElementById('edit-original-id').value,
            new_data: {
                LocationID: document.getElementById('edit-id').value,
                Name: document.getElementById('edit-name').value,
                Type: document.getElementById('edit-type').value,
                "Max Spools": document.getElementById('edit-max').value
            }
        })
    })
        .then(() => { modals.locModal.hide(); modals.locMgrModal.show(); fetchLocations(); });
};

window.openAddModal = () => {
    modals.locMgrModal.hide();
    document.getElementById('edit-original-id').value = "";
    document.getElementById('edit-id').value = "";
    document.getElementById('edit-name').value = "";
    document.getElementById('edit-max').value = "1";
    modals.locModal.show();
};

window.deleteLoc = (id) => requestConfirmation(`Delete ${id}?`, () => fetch(`/api/locations?id=${id}`, { method: 'DELETE' }).then(fetchLocations));

