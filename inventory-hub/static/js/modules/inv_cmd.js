/* MODULE: COMMAND CENTER (Dashboard & Buffer) - Polished v2 */
console.log("🚀 Loaded Module: COMMAND CENTER");

// Surface filabridge write failures (desync risk) as a warning toast.
// Works for both shapes returned by the backend: a bare move_result
// (/api/smart_move) and a wrapper like { smart_move: move_result }
// (/api/quickswap, /api/quickswap/return, identify_scan). A failed write
// already writes an Activity Log entry on the backend; the toast is the
// "happened now" flash so a blind-scanning user notices before scanning again.
window.maybeWarnFilabridge = function (body) {
    if (!body || typeof body !== 'object') return false;
    const mv = body.smart_move || body;
    if (!mv || typeof mv !== 'object') return false;
    if (mv.filabridge_ok === false) {
        const detail = mv.filabridge_detail || 'see Activity Log';
        showToast(`⚠️ Filabridge desync: ${detail}`, 'warning', 7000);
        return true;
    }
    return false;
};

// --- BUFFER UI ---
const renderBuffer = () => {
    const z = document.getElementById('buffer-zone');
    const n = document.getElementById('buffer-nav-deck');

    // 1. Render Dashboard Buffer Zone
    if (z) {
        if (state.heldSpools.length === 0) {
            z.innerHTML = `<div class="buffer-empty-msg">Buffer Empty</div>`;
        } else {
            z.innerHTML = state.heldSpools.map((s, i) => {
                return window.SpoolCardBuilder.buildCard(s, 'buffer', { isFirst: i === 0, index: i });
            }).join('');

            state.heldSpools.forEach((s, i) => generateSafeQR(`qr-buf-${i}`, "ID:" + s.id, 74));
        }
    }

    // 2. Render Dashboard Nav Deck (If present on Dashboard)
    if (n) {
        if (state.heldSpools.length > 1) {
            const nextSpool = state.heldSpools[1];
            const prevSpool = state.heldSpools[state.heldSpools.length - 1];
            const prevStyles = getFilamentStyle(prevSpool.color, prevSpool.color_direction || 'longitudinal');
            const nextStyles = getFilamentStyle(nextSpool.color, nextSpool.color_direction || 'longitudinal');

            n.style.display = 'flex';
            n.innerHTML = 
                window.SpoolCardBuilder.buildCard(prevSpool, 'buffer_nav', { navDirection: 'prev', navAction: 'window.prevBuffer()' }) + 
                window.SpoolCardBuilder.buildCard(nextSpool, 'buffer_nav', { navDirection: 'next', navAction: 'window.nextBuffer()' });
            generateSafeQR("qr-nav-prev", "CMD:PREV", 74);
            generateSafeQR("qr-nav-next", "CMD:NEXT", 74);
        } else { n.style.display = 'none'; }
    }

    // 3. Dispatch Event for Location Manager
    document.dispatchEvent(new CustomEvent('inventory:buffer-updated', { detail: { spools: state.heldSpools } }));

    // 4. Save state if not currently syncing from server.
    //    Track local-change timestamp so a concurrent loadBuffer can skip its overwrite,
    //    and queue a retry persist if a sync is currently holding the lock.
    if (window.suppressBufferDirty) {
        // Server-driven render — neither dirty nor persist.
    } else if (!window.isBufferSyncing) {
        window.lastLocalBufferChange = Date.now();
        persistBuffer();
    } else {
        window.lastLocalBufferChange = Date.now();
        window.pendingPersist = true;
    }
};

const removeBufferItem = (id) => {
    const idx = state.heldSpools.findIndex(s => s.id == id);
    if (idx > -1) {
        state.heldSpools.splice(idx, 1);
        renderBuffer();
        showToast("Item Dropped 🗑️");
        if (state.dropMode && state.heldSpools.length === 0) toggleDropMode();
    } else { showToast("Item not in buffer", "warning"); }
};

const requestClearBuffer = () => { if (state.heldSpools.length === 0) return; requestConfirmation("Clear entire Buffer?", clearBuffer); };
const clearBuffer = () => { state.heldSpools = []; renderBuffer(); showToast("Buffer Cleared"); };
const nextBuffer = () => { if (state.heldSpools.length > 1) { state.heldSpools.push(state.heldSpools.shift()); renderBuffer(); } };
const prevBuffer = () => { if (state.heldSpools.length > 1) { state.heldSpools.unshift(state.heldSpools.pop()); renderBuffer(); } };

// --- MODES ---
const toggleDropMode = () => { state.dropMode = !state.dropMode; state.ejectMode = false; updateDeckVisuals(); };
const toggleEjectMode = () => { state.ejectMode = !state.ejectMode; state.dropMode = false; updateDeckVisuals(); };
window.resetCommandModes = () => { state.dropMode = false; state.ejectMode = false; updateDeckVisuals(); };
const toggleAudit = () => {
    // 18.2 Part B — the deck-button toggle is the user's SAFE bail. When
    // turning audit off via the button, send CMD:CANCEL (no moves) rather
    // than CMD:DONE (which auto-parks missing spools at UNKNOWN). The
    // panel's explicit "✅ Done & Auto-Park" button is the path for the
    // destructive commit; toggle stays purely additive/reversible.
    // Derek 2026-05-16: previously clicking the deck button while audit
    // was active triggered CMD:DONE and force-moved unscanned spools to
    // UNKNOWN, with no way to bail short of refresh.
    state.auditActive = !state.auditActive;
    updateLogState(true);
    const cmd = state.auditActive ? "CMD:AUDIT" : "CMD:CANCEL";
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: cmd }) });
};

// Explicit commit path — exposed for the panel button. Mirrors the
// CMD:DONE scan: closes audit, missing spools get auto-parked to UNKNOWN.
window.commitAuditWithAutoPark = () => {
    state.auditActive = false;
    updateLogState(true);
    fetch('/api/identify_scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'CMD:DONE' }),
    });
};

const updateDeckVisuals = () => {
    const dropBtn = document.getElementById('btn-deck-drop');
    const ejectBtn = document.getElementById('btn-deck-eject');
    const bufCol = document.querySelector('.col-buffer');

    if (dropBtn) dropBtn.classList.remove('drop-mode-active');
    if (ejectBtn) ejectBtn.classList.remove('eject-mode-active');
    if (bufCol) bufCol.classList.remove('drop-mode-active', 'eject-mode-active');

    if (state.dropMode) {
        if (dropBtn) dropBtn.classList.add('drop-mode-active');
        if (bufCol) bufCol.classList.add('drop-mode-active');
        showToast("DROP MODE: Scan to delete", "warning");
    } else if (state.ejectMode) {
        if (ejectBtn) ejectBtn.classList.add('eject-mode-active');
        if (bufCol) bufCol.classList.add('eject-mode-active');
        showToast("EJECT MODE: Scan to remove spool", "warning");
    }
};

window.updateAuditVisuals = () => {
    const deckBtn = document.getElementById('btn-deck-audit');
    const lbl = document.getElementById('lbl-audit');
    const qrDiv = document.getElementById('qr-audit');
    if (state.auditActive) {
        if (deckBtn) deckBtn.classList.add('btn-audit-active');
        if (lbl) { lbl.innerText = "FINISH"; lbl.classList.add('label-active-audit'); }
        if (qrDiv) { qrDiv.innerHTML = ""; generateSafeQR('qr-audit', "CMD:DONE", 85); }
        // 18.2 Part B — auto-open the visual audit panel when an audit
        // session is detected. Activity Log entries continue to fire too;
        // the panel is additive, not a replacement (Derek 2026-05-15:
        // "I still like the idea of having the activity log reference").
        if (typeof window.openAuditPanel === 'function') window.openAuditPanel();
    } else {
        if (deckBtn) deckBtn.classList.remove('btn-audit-active');
        if (lbl) { lbl.innerText = "AUDIT"; lbl.classList.remove('label-active-audit'); }
        if (qrDiv) { qrDiv.innerHTML = ""; generateSafeQR('qr-audit', "CMD:AUDIT", 85); }
        if (typeof window.closeAuditPanel === 'function') window.closeAuditPanel();
    }
};

// --- 18.2 Part B — VISUAL AUDIT PANEL --------------------------------------
// Lives as a mountOverlay (tier 'standard') so it sits above any modal
// stack. Polls /api/audit_session every 2s while audit is active so the
// found/missing tiles tick as the user scans. Closes automatically when
// the audit ends (CMD:DONE / CMD:CANCEL).
(function () {
    let _handle = null;
    let _pollTimer = null;
    // 2026-05-16 — every-2s flicker fix: hash-skip the body innerHTML
    // rewrite when the audit payload hasn't actually changed. Same pattern
    // as updateLogState's lastLogHash. Without this the tile grid + the
    // two QR codes got destroyed and re-created on every tick even when
    // no scan had landed; Derek saw the panel "redraw" every 2-3s.
    let _lastRenderHash = null;
    const _escapeHtml = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const _renderTile = (row, kind) => {
        // kind: 'found' (green check), 'missing' (gray ?), 'rogue' (yellow !)
        const swatchBg = (typeof window.makeSwatchHtml === 'function')
            ? window.makeSwatchHtml(row.color, row.color_direction, { size: 28, borderColor: '#444' })
            : `<span style="display:inline-block;width:28px;height:28px;background:#${row.color || '333'};border-radius:4px;"></span>`;
        const weight = row.remaining_weight != null ? `${Math.round(row.remaining_weight)}g` : '';
        const slot = row.slot ? ` (slot ${_escapeHtml(row.slot)})` : '';
        const badge = kind === 'found'
            ? '<span style="color:#0f0; font-weight:bold;">✅ scanned</span>'
            : (kind === 'rogue'
                ? '<span style="color:#fc0; font-weight:bold;">⚠️ rogue</span>'
                : '<span style="color:rgba(255,255,255,0.7);">⬜ not scanned</span>');
        const border = kind === 'found' ? '#0f0' : (kind === 'rogue' ? '#fc0' : '#555');
        const bg = kind === 'found' ? '#0a2a0a' : (kind === 'rogue' ? '#2a2410' : '#1a1a1a');
        return `
            <div style="display:flex; align-items:center; gap:10px; padding:8px;
                        background:${bg}; border:1px solid ${border}; border-radius:6px;">
                ${swatchBg}
                <div style="flex:1; min-width:0;">
                    <div class="text-truncate" style="color:#fff; font-weight:600; font-size:0.9rem;"
                         title="${_escapeHtml(row.display)}">#${row.id} ${_escapeHtml(row.display)}</div>
                    <div style="font-size:0.75rem; color:rgba(255,255,255,0.75);">${_escapeHtml(weight)}${_escapeHtml(slot)}</div>
                </div>
                <div style="font-size:0.8rem;">${badge}</div>
            </div>
        `;
    };

    const _render = (data) => {
        if (!_handle) return;
        const root = _handle.element;
        const body = root.querySelector('#fcc-audit-panel-body');
        if (!body) return;
        // Hash-skip when payload is unchanged so the 2s poll stops
        // re-rendering the tile grid (and re-generating QR codes) every
        // tick. Derek 2026-05-16 visible-flicker fix.
        const hash = JSON.stringify(data);
        if (hash === _lastRenderHash) return;
        _lastRenderHash = hash;
        const s = data.stats || { total_expected: 0, found: 0, missing: 0, rogue: 0 };
        const expectedTiles = (data.expected || []).map(r => _renderTile(r, r.found ? 'found' : 'missing')).join('');
        const rogueTiles = (data.rogue || []).map(r => _renderTile(r, 'rogue')).join('');
        const loc = _escapeHtml(data.location_id || '(scan a location to start)');
        body.innerHTML = `
            <div style="margin-bottom:10px; font-size:0.95rem;">
                Auditing <b style="color:#0ff;">${loc}</b> —
                <span style="color:#0f0; font-weight:bold;">${s.found}/${s.total_expected}</span> found,
                <span style="color:rgba(255,255,255,0.75); font-weight:bold;">${s.missing}</span> missing,
                <span style="color:#fc0; font-weight:bold;">${s.rogue}</span> rogue
            </div>
            ${data.expected && data.expected.length ? `
                <div style="font-weight:bold; color:#0ff; margin-bottom:6px;">Expected here</div>
                <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:6px; margin-bottom:12px;">
                    ${expectedTiles}
                </div>
            ` : `<div class="small" style="color:rgba(255,255,255,0.7);">Scan a location's QR to populate the expected list.</div>`}
            ${data.rogue && data.rogue.length ? `
                <div style="font-weight:bold; color:#fc0; margin-bottom:6px;">Rogue (scanned but expected elsewhere)</div>
                <div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:6px;">
                    ${rogueTiles}
                </div>
            ` : ''}
            <!-- 18.2 Part B follow-up: surface DONE + CANCEL as explicit
                 click-targets AND QR codes so the user has both keyboard/
                 mouse and scanner exits. Without these the only way out
                 was the deck button (used to auto-DONE; now CANCEL-only). -->
            <div class="d-flex justify-content-between align-items-stretch gap-3 mt-3 pt-3 border-top border-secondary">
                <div style="flex:1; text-align:center;">
                    <button class="btn btn-success fw-bold w-100 mb-2"
                            onclick="window.commitAuditWithAutoPark && window.commitAuditWithAutoPark()">
                        ✅ Done &amp; Auto-Park
                    </button>
                    <div id="fcc-audit-panel-qr-done" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color: rgba(255,255,255,0.75);">
                        Missing spools <b style="color:#fc0;">→ ❓ Unknown</b>
                    </div>
                </div>
                <div style="flex:1; text-align:center;">
                    <button class="btn btn-outline-danger fw-bold w-100 mb-2"
                            onclick="if (typeof toggleAudit==='function') toggleAudit(); else window.closeAuditPanel();">
                        ❌ Cancel Audit
                    </button>
                    <div id="fcc-audit-panel-qr-cancel" style="display:inline-block; background:#fff; padding:4px; border-radius:4px;"></div>
                    <div class="small mt-1" style="color: rgba(255,255,255,0.75);">
                        Bail without moving anything
                    </div>
                </div>
            </div>
        `;
        // Generate QR codes after the placeholders are in the DOM.
        // `generateSafeQR` is a script-scope const in inv_core.js — accessible
        // by bare name (not on window). The wrong `window.generateSafeQR`
        // guard previously silently dropped these calls, which is why no
        // QR rendered (Derek 2026-05-16).
        if (typeof generateSafeQR === 'function') {
            generateSafeQR('fcc-audit-panel-qr-done', 'CMD:DONE', 90);
            generateSafeQR('fcc-audit-panel-qr-cancel', 'CMD:CANCEL', 90);
        }
    };

    const _poll = async () => {
        try {
            const r = await fetch('/api/audit_session');
            const d = await r.json();
            if (!d || !d.active) {
                window.closeAuditPanel();
                return;
            }
            _render(d);
        } catch (e) { /* network hiccup — try again next tick */ }
    };

    window.openAuditPanel = () => {
        if (_handle) return;  // idempotent
        if (typeof window.mountOverlay !== 'function') return;
        _lastRenderHash = null;  // force first render after open
        const content = `
            <div style="background:#1e1e1e; color:#fff; border:2px solid #ff00ff;
                        border-radius:8px; padding:14px 16px;
                        width:min(820px,94vw); max-height:80vh; display:flex; flex-direction:column;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div style="font-weight:bold; font-size:1.15em; color:#ff7eff;">
                        🕵️‍♀️ Audit in Progress
                    </div>
                    <button id="fcc-audit-panel-close" class="btn btn-sm btn-outline-light"
                            title="Hide the panel (audit stays active; reopen via the AUDIT deck button while running)">Hide</button>
                </div>
                <div id="fcc-audit-panel-body" style="overflow-y:auto; flex:1 1 auto;">
                    <div class="small" style="color:rgba(255,255,255,0.7);">Loading audit state…</div>
                </div>
            </div>
        `;
        _handle = window.mountOverlay({
            id: 'fcc-audit-panel-overlay',
            content,
            tier: 'standard',
            backdrop: true,
            backdropDismiss: false,  // Audit is in progress; Hide is the explicit dismiss
            onEscape: () => window.closeAuditPanel(),
        });
        const closeBtn = _handle.element.querySelector('#fcc-audit-panel-close');
        if (closeBtn) closeBtn.onclick = () => window.closeAuditPanel();
        // Initial render + start the 2s poll.
        _poll();
        _pollTimer = setInterval(_poll, 2000);
    };

    window.closeAuditPanel = () => {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
        if (_handle) { try { _handle.cleanup(); } catch (_) { /* noop */ } _handle = null; }
    };
})();

// --- Prusament matched-scan overlay (Stage 2c) -----------------------------
// Shown after a Prusament QR matches an existing spool: summarizes the blank
// temps the backend backfilled, lets the user accept Prusament's CURRENT spec
// for any temps that DIFFER (writes them via /api/update_filament), and offers
// to queue the spool's label. Built on mountOverlay per project convention
// (z-index / focus-guard / escape are handled there).
window.promptPrusamentMatched = (res) => {
    if (typeof window.mountOverlay !== 'function') {
        showToast(`✅ Matched ${res.filament_name || 'filament'}`, 'success', 4000);
        return;
    }
    const sid = res.spool_id, fid = res.filament_id;
    const name = res.filament_name || 'filament';
    const filled = res.filled || [];
    const conflicts = res.conflicts || [];
    const LABELS = {
        settings_extruder_temp: 'Nozzle (min)', nozzle_temp_max: 'Nozzle (max)',
        settings_bed_temp: 'Bed (min)', bed_temp_max: 'Bed (max)',
    };
    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const filledHtml = filled.length
        ? `<div class="text-success small mb-2">🌡️ Backfilled: ${filled.map(f => esc(LABELS[f] || f)).join(', ')}</div>`
        : `<div class="text-muted small mb-2">Temps already current — nothing to backfill.</div>`;

    const conflictHtml = conflicts.length ? `
        <div class="border border-warning rounded p-2 mb-2" style="background:#2a2a2a;">
            <div class="text-warning small mb-1">⚠️ Prusament's current spec differs from your saved temps:</div>
            ${conflicts.map(c => `
                <div class="d-flex justify-content-between small text-light">
                    <span>${esc(c.label || LABELS[c.field] || c.field)}</span>
                    <span><span style="color:#adb5bd;">${esc(c.current)}°C</span> &rarr; <span class="text-info fw-bold">${esc(c.scanned)}°C</span></span>
                </div>`).join('')}
            <button id="pm-update-temps" class="btn btn-sm btn-warning w-100 mt-2">Update to Prusament's spec</button>
        </div>` : '';

    const content = `
        <div class="p-3" style="max-width:420px; background:#1e1e1e; color:#fff; border:1px solid #444; border-radius:8px;">
            <h6 class="text-info mb-1">🎯 Matched Prusament spool</h6>
            <div class="mb-2"><strong>${esc(name)}</strong> <span class="text-muted">— Spool #${esc(sid)}</span></div>
            ${filledHtml}
            ${conflictHtml}
            <div class="d-flex gap-2 mt-2">
                <button id="pm-queue-label" class="btn btn-sm btn-outline-info flex-fill">🏷️ Queue label</button>
                <button id="pm-done" class="btn btn-sm btn-secondary flex-fill">Done</button>
            </div>
        </div>`;

    const handle = window.mountOverlay({
        id: 'fcc-prusament-matched-overlay',
        content,
        tier: 'standard',
        backdrop: true,
        initialFocus: '#pm-done',
        onEscape: () => { try { handle.cleanup(); } catch (_) { /* noop */ } },
    });
    const ov = handle.element;
    const close = () => { try { handle.cleanup(); } catch (_) { /* noop */ } };

    const doneBtn = ov.querySelector('#pm-done');
    if (doneBtn) doneBtn.onclick = close;

    const queueBtn = ov.querySelector('#pm-queue-label');
    if (queueBtn) queueBtn.onclick = () => {
        if (typeof window.addToQueueWithToast === 'function') {
            window.addToQueueWithToast({ id: sid, type: 'spool', display: name });
        }
        close();
    };

    const updateBtn = ov.querySelector('#pm-update-temps');
    if (updateBtn) updateBtn.onclick = () => {
        const data = { extra: {} };
        conflicts.forEach(c => {
            if (c.native) data[c.field] = Number(c.scanned);
            else data.extra[c.field] = String(c.scanned);
        });
        if (!Object.keys(data.extra).length) delete data.extra;
        updateBtn.disabled = true;
        updateBtn.textContent = 'Updating…';
        fetch('/api/update_filament', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: fid, data }),
        }).then(r => r.json()).then(d => {
            if (d && d.success) {
                showToast(`🌡️ Updated ${conflicts.length} temp(s) on ${name} to Prusament's spec`, 'success', 4000);
                close();
            } else {
                showToast((d && d.msg) || 'Temp update rejected', 'error', 7000);
                updateBtn.disabled = false;
                updateBtn.textContent = "Update to Prusament's spec";
            }
        }).catch(() => {
            showToast('Temp update failed (network)', 'error', 7000);
            updateBtn.disabled = false;
            updateBtn.textContent = "Update to Prusament's spec";
        });
    };
};

// --- SCAN ROUTER ---
const processScan = (text, source = 'keyboard') => {
    const upper = text.toUpperCase();
    // Active-dialog confirm-by-scan (registered via window.attachConfirmQRs).
    // Must run BEFORE the regular CMD: branches so a CMD:CONFIRM:<sid> scan
    // routes to the dialog's callback instead of hitting the backend or the
    // generic CMD-routes below. Returns true on a matched session — fall
    // through to the rest of the dispatch otherwise.
    if (window.routeConfirmScan && window.routeConfirmScan(text)) return;

    if (upper === 'CMD:AUDIT') { toggleAudit(); return; }
    if (upper === 'CMD:LOCATIONS') { openLocationsModal(); return; }
    if (upper === 'CMD:WEIGH') { window.openWeighOutModal(); return; }
    if (upper === 'CMD:DROP') { toggleDropMode(); return; }
    if (upper === 'CMD:EJECT') { toggleEjectMode(); return; }
    if (upper === 'CMD:EJECTALL') { triggerEjectAll(document.getElementById('manage-loc-id').value); return; }
    if (upper === 'CMD:UNDO') { triggerUndo(); return; }
    if (upper === 'CMD:CLEAR') { requestClearBuffer(); return; }
    if (upper === 'CMD:PREV') { prevBuffer(); return; }
    if (upper === 'CMD:NEXT') { nextBuffer(); return; }
    if (upper.startsWith('CMD:PRINT:')) { const parts = upper.split(':'); if (parts[2]) window.printLabel(parts[2]); return; }
    if (upper.startsWith('CMD:TRASH:')) { const parts = upper.split(':'); if (parts[2] && document.getElementById('manageModal').classList.contains('show')) ejectSpool(parts[2], document.getElementById('manage-loc-id').value, false); return; }

    if (state.activeModal === 'safety') return upper.includes('CONFIRM') ? confirmSafety(true) : (upper.includes('CANCEL') ? confirmSafety(false) : null);
    if (state.activeModal === 'confirm') return upper.includes('CONFIRM') ? confirmAction(true) : (upper.includes('CANCEL') ? confirmAction(false) : null);
    if (state.activeModal === 'action') { if (upper.includes('CANCEL')) { closeModal('actionModal'); return; } if (upper.startsWith('CMD:MODAL:')) { closeModal('actionModal'); state.modalCallbacks[parseInt(upper.split(':')[2])](); return; } }

    setProcessing(true);
    fetch('/api/identify_scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text, source: source }) })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            window.maybeWarnFilabridge(res);
            if (res.type === 'command') {
                const cmds = { 'clear': requestClearBuffer, 'undo': triggerUndo, 'eject': toggleEjectMode, 'done': closeManage };
                if (cmds[res.cmd]) cmds[res.cmd]();
                else if (res.cmd === 'confirm' && state.pendingConfirm) confirmAction(true);
                else if (res.cmd === 'slot') handleSlotInteraction(res.value);
                else if (res.cmd === 'ejectall') triggerEjectAll(document.getElementById('manage-loc-id').value);
            } else if (res.type === 'assignment') {
                // Backend now handles the load when the buffer is non-empty.
                // We switch on `action` and let the backend's Activity Log
                // cover success/error cases; the frontend only handles the
                // no-buffer fallback (treat as a slot pickup).
                state.lastScannedLoc = null;
                if (res.action === 'assignment_done' || res.action === 'assignment_partial') {
                    // Backend already moved the spool and logged it. Mirror by
                    // dropping the moved id out of heldSpools so the UI matches.
                    const movedId = res.moved;
                    if (movedId != null) {
                        state.heldSpools = state.heldSpools.filter(s => s.id !== movedId);
                        renderBuffer();
                    }
                    const extraMsg = res.action === 'assignment_partial'
                        ? ` (${res.remaining_buffer} still in buffer)`
                        : '';
                    showToast(
                        `✅ Loaded #${movedId} into ${res.location}:${res.slot}${extraMsg}`,
                        res.action === 'assignment_partial' ? 'info' : 'success',
                        res.action === 'assignment_partial' ? 5000 : 4000
                    );
                    document.dispatchEvent(new CustomEvent('inventory:locations-changed'));
                } else if (res.action === 'assignment_no_buffer') {
                    // Buffer Empty → treat as pickup: read slot contents and
                    // put the spool in the buffer. Log explicitly on success
                    // so the user's Activity Log reflects what happened.
                    fetch(`/api/get_contents?id=${res.location}`)
                        .then(r => r.json())
                        .then(items => {
                            const item = items.find(i => String(i.slot) === String(res.slot));
                            if (item) {
                                if (state.heldSpools.some(s => s.id === item.id)) {
                                    showToast("Already in Buffer", "warning", 3500);
                                } else {
                                    state.heldSpools.unshift({ id: item.id, display: item.display, color: item.color, color_direction: item.color_direction, remaining_weight: item.remaining_weight, details: item.details, archived: item.archived });
                                    renderBuffer();
                                    showToast(`✋ Picked up #${item.id} from ${res.location}:SLOT:${res.slot}`, 'success', 2500);
                                    fetch('/api/log_event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ msg: `✋ Pickup: Spool #${item.id} from <b>${res.location}:SLOT:${res.slot}</b>`, level: 'INFO' }) });
                                }
                            } else {
                                showToast(`Slot ${res.slot} on ${res.location} is empty — opening manager`, 'info', 3000);
                                if (window.logClientEvent) window.logClientEvent(
                                    `⚠️ Slot scan ${res.location}:SLOT:${res.slot} — slot is empty (opened manager)`,
                                    'WARNING'
                                );
                                openManage(res.location);
                            }
                        })
                        .catch(e => {
                            console.error(e);
                            showToast("Error looking up slot", "error", 5000);
                            if (window.logClientEvent) window.logClientEvent(
                                `❌ Slot pickup failed for ${res.location}:SLOT:${res.slot}: ${e && e.message ? e.message : 'network error'}`,
                                'ERROR'
                            );
                        });
                } else if (res.action === 'assignment_bad_slot') {
                    const limit = res.max_slots != null ? ` (has ${res.max_slots} slots)` : '';
                    showToast(`❌ Slot ${res.slot} invalid for ${res.location}${limit}`, 'error', 5000);
                } else if (res.action === 'assignment_bad_target') {
                    showToast(`❌ ${res.location} isn't a valid load target`, 'error', 5000);
                } else {
                    // Unknown action code — shouldn't happen, but surface it.
                    showToast(`Unknown assignment result: ${res.action || 'none'}`, 'warning', 4000);
                    if (window.logClientEvent) window.logClientEvent(
                        `⚠️ Unknown assignment action from backend: ${res.action || 'none'}`,
                        'WARNING'
                    );
                }
            } else if (res.type === 'location') {
                if (!text.toUpperCase().startsWith('LOC:')) {
                    const msg = "⚠️ Legacy Location Label Scanned! Features may be limited. Print a new LOC: label when possible.";
                    showToast(msg, "warning", 3500);
                    fetch('/api/log_event', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({msg: "SCAN LOG: Legacy Location Barcode Scanned (" + text + ")", level: "WARNING"}) });
                }
                if (state.lastScannedLoc === res.id) { state.heldSpools = []; renderBuffer(); openManage(res.id); state.lastScannedLoc = null; return; }
                if (state.heldSpools.length > 0) {
                    // L124 fix: a toolhead / single-spool location can only hold
                    // one spool. Bulk-assigning the entire buffer to a toolhead
                    // sent every spool's Spoolman location to that toolhead,
                    // which broke filabridge's one-spool-one-toolhead invariant
                    // AND made all the buffered spools appear loaded on the
                    // printer. Detect single-occupancy targets up-front and
                    // pass only the topmost spool; keep the rest in the buffer
                    // so the user can scan their next destination.
                    const locData = state.allLocations.find(l => l.LocationID === res.id);
                    const locType = (locData && locData.Type) ? String(locData.Type).toLowerCase() : '';
                    const isSingleSpoolType = locType.includes('tool') || locType.includes('mmu') || locType.includes('direct load');
                    let maxSpools = 0;
                    if (locData) {
                        const raw = parseInt(locData['Max Spools'], 10);
                        if (!isNaN(raw)) maxSpools = raw;
                    }
                    const singleOccupancy = isSingleSpoolType || (maxSpools > 0 && maxSpools <= 1);
                    if (singleOccupancy && state.heldSpools.length > 1) {
                        const top = state.heldSpools[0];
                        showToast(`Toolhead holds 1 spool — assigning #${top.id}; ${state.heldSpools.length - 1} stays in buffer`, "info", 5000);
                        performContextAssign(res.id, null, false, [top.id]);
                    } else {
                        performContextAssign(res.id);
                    }
                    state.lastScannedLoc = null;
                    return;
                }
                const locData = state.allLocations.find(l => l.LocationID === res.id);
                if ((!locData || parseInt(locData['Max Spools']) <= 1) && res.contents && res.contents.length > 0) {
                    const spool = res.contents[0];
                    state.heldSpools.unshift({ id: spool.id, display: spool.display, color: spool.color, color_direction: spool.color_direction, remaining_weight: spool.remaining_weight, details: spool.details, archived: spool.archived, location: spool.location, is_ghost: spool.is_ghost, slot: spool.slot, deployed_to: spool.deployed_to });
                    renderBuffer();
                    showToast("⚡ Quick Pick: #" + spool.id);
                    state.lastScannedLoc = res.id;
                    return;
                }
                openManage(res.id); state.lastScannedLoc = res.id;
            } else if (res.type === 'spool') {
                if (state.dropMode) { removeBufferItem(res.id); return; }
                if (state.ejectMode) { ejectSpool(res.id, "Scan", false); return; }

                state.lastScannedLoc = null;
                if (!res.display) { showToast("Spool ID found but data missing!", "error"); return; }
                // L128 follow-up (2026-05-15): the "already verified"
                // toast was MORE noisy than the log line it replaced —
                // reverted to writing to Activity Log only. The
                // label_already_verified flag is still emitted for any
                // future surface that needs it; we just don't toast.
                if (state.heldSpools.some(s => s.id === res.id)) showToast("Already in Buffer", "warning");
                else { state.heldSpools.unshift({ id: res.id, display: res.display, color: res.color, color_direction: res.color_direction, remaining_weight: res.remaining_weight, details: res.details, archived: res.archived, location: res.location, is_ghost: res.is_ghost, slot: res.slot, deployed_to: res.deployed_to }); renderBuffer(); }
            } else if (res.type === 'ambiguous') {
                // Item 3.6 — backend found multiple spools attached to this
                // legacy id. Prompt the user to disambiguate. "Use selected"
                // re-routes through processScan with explicit ID:NNN so the
                // normal spool path runs (label-verify, buffer add, etc.).
                // "Print new label" is handled inside the picker module.
                if (typeof window.showLegacySpoolPicker === 'function') {
                    window.showLegacySpoolPicker(res, {
                        onSelect: (sid) => { processScan(`ID:${sid}`, 'barcode'); },
                        onAbort: () => { /* user cancelled or chose to re-print */ },
                    });
                } else {
                    // Fallback: log and bail rather than silently auto-pick.
                    console.warn("[inv_cmd] showLegacySpoolPicker missing; ambiguous scan dropped");
                    showToast(`Multiple spools share legacy ID ${res.legacy_id} — open Backlog to print fresh labels`, "warning", 6000);
                }
            } else if (res.type === 'filament') {
                // L128 follow-up (2026-05-15): see spool branch — reverted
                // to Activity Log only; no per-scan toast.
                openFilamentDetails(res.id);
            } else if (res.type === 'prusament_matched') {
                // Matched an existing spool: the backend already backfilled blank
                // temps. The overlay summarizes that, resolves any differing-temp
                // conflicts (Update to Prusament's spec), and offers queue-label.
                if (res.status === 'error') {
                    showToast(res.msg || 'Prusament temp backfill failed', 'error', 7000);
                } else if (typeof window.promptPrusamentMatched === 'function') {
                    window.promptPrusamentMatched(res);
                } else {
                    showToast(`✅ Matched ${res.filament_name || 'filament'}`, 'success', 4000);
                }
            } else if (res.type === 'prusament_new') {
                // No existing spool matched — onboard by opening the Add wizard
                // pre-filled from the scanned URL (reuses the wizard's external
                // import: set the query, then trigger the search).
                showToast('🆕 New Prusament spool — opening the Add wizard to onboard it', 'info', 4500);
                if (typeof window.openWizardModal === 'function') {
                    Promise.resolve(window.openWizardModal()).then(() => {
                        const q = document.getElementById('wiz-search-external');
                        if (q) {
                            q.value = res.url || '';
                            if (typeof window.wizardSearchExternal === 'function') window.wizardSearchExternal(true);
                        }
                    });
                }
            } else if (res.type === 'error') showToast(res.msg, 'error');
        })
        .catch((e) => { setProcessing(false); console.error(e); showToast("Scan Error", "error"); });
};

// Inline confirm overlay for "bulk assign into an active toolhead" — same
// visual pattern as Location Manager's _confirmActivePrintAssign (no nested
// Swal). Mounts into body so it floats above the scan UI and any open modal.
const _confirmActivePrintScan = ({ tid, slot, stateInfo, onConfirm }) => {
    // L122 fix: previously rolled its own overlay (createElement +
    // appendChild + document keydown). Migrated to window.mountOverlay()
    // so it inherits the canonical z-index ladder, focus guard, and
    // host-close discipline documented in CLAUDE.md "Project Conventions".
    // The previous implementation could end up blocked/hidden behind
    // certain modal stacks (the buglist L122 symptom: "confirm change
    // modal is being blocked, canceled, or hidden").
    const escapeHtml = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    const content = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ff8800; border-radius:8px; padding:20px 24px; max-width:460px; text-align:center;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">⚠️ ${escapeHtml(stateInfo.printer_name)} is ${escapeHtml(stateInfo.state)}</div>
            <div style="color:#ffc; margin-bottom:14px;">
                Assigning the buffered spool(s) to <b>${escapeHtml(tid)}</b> will disrupt the active print. Continue anyway?
            </div>
            <div style="display:flex; gap:10px; justify-content:center;">
                <button id="fcc-aps-yes" class="btn btn-warning btn-sm" style="min-width:120px;">Continue Anyway</button>
                <button id="fcc-aps-no" class="btn btn-secondary btn-sm" style="min-width:120px;">Cancel</button>
            </div>
        </div>
    `;
    let handle = null;
    let qrSession = null;
    const cleanup = () => {
        if (handle) { try { handle.cleanup(); } catch (_) { /* noop */ } handle = null; }
        if (qrSession) { try { qrSession.cleanup(); } catch (_) { /* noop */ } qrSession = null; }
    };
    const proceed = () => { cleanup(); onConfirm(); };
    handle = window.mountOverlay({
        id: 'fcc-active-print-scan-overlay',
        content,
        tier: 'confirm',
        initialFocus: '#fcc-aps-yes',
        onEscape: cleanup,
    });
    const ov = handle.element;
    const yesBtn = ov.querySelector('#fcc-aps-yes');
    const noBtn = ov.querySelector('#fcc-aps-no');
    if (yesBtn) yesBtn.onclick = proceed;
    if (noBtn) noBtn.onclick = cleanup;
    // Keyboard contract (matches _confirmActivePrintAssign in inv_loc_mgr):
    // Enter activates the focused button (Yes/No); Tab cycles between
    // them; Escape always cancels (owned by mountOverlay's onEscape).
    const keyHandler = (e) => {
        if (e.key === 'Enter') {
            const active = document.activeElement;
            if (active === yesBtn) { e.preventDefault(); e.stopPropagation(); proceed(); }
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
    ov.addEventListener('keydown', keyHandler, true);
    if (window.attachConfirmQRs && ov) {
        qrSession = window.attachConfirmQRs({
            host: ov,
            onConfirm: proceed,
            onCancel: cleanup,
            theme: 'warning',
        });
    }
};

const performContextAssign = (tid, slot = null, confirmActivePrint = false, spoolIdsOverride = null) => {
    setProcessing(true);
    // L124: callers can pass an explicit `spoolIdsOverride` subset (e.g. the
    // single topmost id when the target is a toolhead) so the rest of the
    // buffer stays untouched. Default = entire buffer (the legacy bulk-assign
    // behavior).
    const spoolIds = Array.isArray(spoolIdsOverride) && spoolIdsOverride.length
        ? spoolIdsOverride.slice()
        : state.heldSpools.map(s => s.id);
    const payload = {
        location: tid,
        spools: spoolIds,
        slot: slot,
        origin: 'buffer',
        confirm_active_print: confirmActivePrint,
    };

    fetch('/api/smart_move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            window.maybeWarnFilabridge(res);
            // Backend safety net: target is an active toolhead. Prompt the
            // user and retry with confirmActivePrint=true on approval.
            if (res.status === 'requires_confirm' && res.confirm_type === 'active_print') {
                _confirmActivePrintScan({
                    tid, slot,
                    stateInfo: res.active_print || { printer_name: tid, state: 'ACTIVE' },
                    onConfirm: () => performContextAssign(tid, slot, true, spoolIdsOverride),
                });
                return;
            }
            if (res.status === 'success') {
                const movedCount = spoolIds.length;
                showToast("Assigned " + movedCount + " item" + (movedCount === 1 ? '' : 's') + "!", "success");
                // Drop only the spools we actually moved; preserve the rest.
                const movedSet = new Set(spoolIds.map(String));
                state.heldSpools = state.heldSpools.filter(s => !movedSet.has(String(s.id)));
                renderBuffer();
                if (document.getElementById('manage-loc-id').value === tid) refreshManageView(tid);
                if (window.fetchLocations) window.fetchLocations();
            } else showToast(res.msg, 'error');
        })
        .catch(() => setProcessing(false));
};

const triggerUndo = () => fetch('/api/undo', { method: 'POST' }).then(() => { updateLogState(); loadBuffer(); if(window.fetchLocations) window.fetchLocations(); });

const printLabel = (sid) => {
    showToast("🖨️ Requesting Label...");
    setProcessing(true);
    fetch('/api/print_label', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: sid })
    })
        .then(r => r.json())
        .then(res => {
            setProcessing(false);
            if (!res.success) { showToast(res.msg || "Print Failed", "error"); return; }
            if (res.method === 'csv') { showToast(res.msg, "success"); return; }
            if (res.method === 'browser') {
                const data = res.data;
                if (!data || !data.filament) { showToast("Invalid Data", "error"); return; }
                const fil = data.filament;
                const extra = fil.extra || {};
                const colorHex = fil.color_hex || '000000';
                const rgb = hexToRgb(colorHex);
                let typeStr = fil.material || "Unknown";
                try {
                    let attrs = (typeof extra.filament_attributes === 'string') ? JSON.parse(extra.filament_attributes) : extra.filament_attributes;
                    if (Array.isArray(attrs) && attrs.length > 0) typeStr = attrs.join(' ') + ' ' + typeStr;
                } catch (err) { }
                const qrEl = document.getElementById('print-qr');
                if (qrEl) {
                    qrEl.innerHTML = "";
                    new QRCode(qrEl, { text: `ID:${sid}`, width: 120, height: 120, correctLevel: QRCode.CorrectLevel.L });
                }
                document.getElementById('lbl-brand').innerText = fil.vendor ? fil.vendor.name : "Generic";
                document.getElementById('lbl-color').innerText = extra.original_color ? extra.original_color.replace(/"/g, '') : fil.name;
                document.getElementById('lbl-type').innerText = typeStr;
                document.getElementById('lbl-hex').innerText = colorHex.toUpperCase();
                document.getElementById('lbl-id').innerText = sid;
                document.getElementById('lbl-rgb').innerText = `${rgb.r},${rgb.g},${rgb.b}`;
                setTimeout(() => window.print(), 500);
            }
        })
        .catch(e => { setProcessing(false); console.error(e); showToast("Connection Error", "error"); });
};

// EXPOSE GLOBALLY FOR LOC MANAGER
window.printLabel = printLabel;
window.renderBuffer = renderBuffer;
window.prevBuffer = prevBuffer;
window.nextBuffer = nextBuffer;
window.removeBufferItem = removeBufferItem;

// Hook into the render function to trigger saves automatically
window.isBufferSyncing = false; // Mutex for sync

/* --- PERSISTENCE LAYER: BUFFER (V3 Polling) --- */
const persistBuffer = () => {
    fetch('/api/state/buffer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ buffer: state.heldSpools })
    }).catch(e => console.warn("Buffer Save Failed", e));
};

const loadBuffer = () => {
    // L28 polling guard: bail if a previous tick is still in flight.
    // isBufferSyncing was already used to block persistBuffer uploads
    // during a sync; reusing it here also gates the next poll from
    // piling up on top of an in-flight one — under a slow backend,
    // unguarded 2s ticks were a major contributor to socket-buffer
    // exhaustion (net::ERR_NO_BUFFER_SPACE).
    if (window.isBufferSyncing) return;
    window.isBufferSyncing = true; // Block uploads
    fetch('/api/state/buffer')
        .then(r => r.json())
        .then(data => {
            if (Array.isArray(data)) {
                const currentStr = JSON.stringify(state.heldSpools);
                const serverStr = JSON.stringify(data);

                if (currentStr !== serverStr) {
                    // Grace window: a user-driven mutation in the last 3s wins over the server payload.
                    // Without this, manual entries (and barcode scans) added during an in-flight sync
                    // get wiped before persistBuffer lands.
                    const localAge = Date.now() - (window.lastLocalBufferChange || 0);
                    if (localAge < 3000) {
                        console.log(`⏸️ Skipping server overwrite — local change ${localAge}ms ago`);
                        window.pendingPersist = true;
                    } else {
                        console.log("🔄 Syncing Buffer from Server...");
                        window.suppressBufferDirty = true;
                        state.heldSpools = data;
                        if (window.renderBuffer) window.renderBuffer();
                        window.suppressBufferDirty = false;
                        // [ALEX FIX] Trigger a proactive backfill sync since old DB state didn't track remaining_weight
                        setTimeout(liveRefreshBuffer, 500);
                    }
                }
            }
            window.isBufferSyncing = false; // Unblock
            if (window.pendingPersist) {
                window.pendingPersist = false;
                persistBuffer();
            }
        })
        .catch(e => {
            console.warn("Buffer Load Failed", e);
            window.isBufferSyncing = false;
            if (window.pendingPersist) {
                window.pendingPersist = false;
                persistBuffer();
            }
        });
};

// --- LIVE REFRESH POLLING ---
// L28 polling guard: see updateLogState for rationale.
let _liveRefreshInflight = false;
// L206: render path extracted so the bulk-pulse dispatcher can hand
// a spools_refresh payload (same {id: data} shape that /api/spools/refresh
// returns) directly into the diff/update loop without another fetch.
const _renderSpoolsRefreshPayload = (data) => {
    if (!data || typeof data !== 'object') return;
    let changed = false;
    state.heldSpools.forEach(s => {
        const fresh = data[s.id];
        if (!fresh) return;
        // Diff covers every field the buffer card actually renders. Pre-2026-04-28
        // this list excluded location / is_ghost / slot / deployed_to, so a backend-
        // driven location move (Location Manager, Quick-Swap, force-unassign,
        // auto-archive-on-empty) would correctly update `archived` and the weight,
        // but leave the location badge stale until the user navigated away and
        // back — root cause of buglist L24 / L40.
        if (fresh.display !== s.display ||
            fresh.color !== s.color ||
            fresh.color_direction !== s.color_direction ||
            fresh.remaining_weight !== s.remaining_weight ||
            !s.details ||
            fresh.archived !== s.archived ||
            fresh.location !== s.location ||
            fresh.is_ghost !== s.is_ghost ||
            fresh.slot !== s.slot ||
            fresh.deployed_to !== s.deployed_to) {
            s.display = fresh.display;
            s.color = fresh.color;
            s.color_direction = fresh.color_direction;
            s.remaining_weight = fresh.remaining_weight;
            s.details = fresh.details;
            s.archived = fresh.archived;
            s.location = fresh.location;
            s.is_ghost = fresh.is_ghost;
            s.slot = fresh.slot;
            s.deployed_to = fresh.deployed_to;
            changed = true;
        }
    });
    if (changed && window.renderBuffer) window.renderBuffer();
};
window._renderSpoolsRefreshPayload = _renderSpoolsRefreshPayload;

const liveRefreshBuffer = () => {
    if (!state.heldSpools || state.heldSpools.length === 0) return;
    if (_liveRefreshInflight) return;

    const spoolIds = state.heldSpools.map(s => s.id);

    _liveRefreshInflight = true;
    fetch('/api/spools/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spools: spoolIds })
    })
        .then(r => r.json())
        .then(_renderSpoolsRefreshPayload)
        .catch(e => console.warn("Live Refresh Buffer Failed", e))
        .finally(() => { _liveRefreshInflight = false; });
};
window.liveRefreshBuffer = liveRefreshBuffer;

// L206: the dashboard_pulse heartbeat already refreshes buffer cards via
// its spools_refresh section; skip the duplicate /api/spools/refresh fetch
// when this event came from that source. Other dispatchers (wizard save,
// weigh-out, details modal saves) still trigger a fresh fetch.
document.addEventListener('inventory:sync-pulse', (e) => {
    if (e && e.detail && e.detail.source === 'dashboard_pulse') return;
    liveRefreshBuffer();
});

// Heartbeat (Checks every 2 seconds)
setInterval(loadBuffer, 2000);

// Initial Load
document.addEventListener('DOMContentLoaded', loadBuffer);

window.addSpoolToBuffer = (id) => {
    // [ALEX FIX] Reuse the Scanner Logic! 
    // Instead of manually fetching and building the object, we just tell the 
    // scanner router that this ID was "scanned". This ensures consistent behavior 
    // and data formatting between physical scans and UI clicks.
    // Must prefix with ID: so the Python backend doesn't think it's a legacy barcode
    console.log(`📥 Simulating Scan for Spool #${id}`);
    processScan('ID:' + id.toString());
};

window.processScan = processScan;