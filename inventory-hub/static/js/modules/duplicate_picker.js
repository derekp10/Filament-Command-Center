/* MODULE: DUPLICATE PICKER (legacy ID disambiguation) */
console.log("🚀 Loaded Module: DUPLICATE PICKER");

// window.showLegacySpoolPicker(payload, opts)
//
// payload: { legacy_id: string, candidates: [{id, remaining_weight, location,
//            archived, filament_id, filament_name, material, vendor_name,
//            color_hex, display}, ...] }
// opts.onSelect(spoolId): called when the user picks a spool with "✓ Use selected".
// opts.onAbort(): called when the user cancels OR queues a label (no further
//                 scan flow — the re-labeling route disambiguates from here).
//
// Inline overlay (no nested Swal — see CLAUDE.md "Project Conventions").
// Keyboard: Enter activates focused button (defaults to "Use selected"),
// Escape cancels.
window.showLegacySpoolPicker = (payload, opts = {}) => {
    const { legacy_id, candidates = [] } = payload || {};
    const onSelect = typeof opts.onSelect === 'function' ? opts.onSelect : () => { };
    const onAbort = typeof opts.onAbort === 'function' ? opts.onAbort : () => { };

    if (!Array.isArray(candidates) || candidates.length === 0) {
        onAbort();
        return;
    }

    const escapeHtml = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

    const optsHtml = candidates.map((c) => {
        const w = (c.remaining_weight != null) ? `${Math.round(c.remaining_weight)}g` : '?g';
        const loc = c.location || 'Unassigned';
        const arch = c.archived ? ' [ARCHIVED]' : '';
        const vendor = (c.vendor_name || '').trim();
        const mat = (c.material || '').trim();
        const name = (c.filament_name || '').trim();
        const headline = [vendor, mat, name].filter(Boolean).join(' ');
        const label = `#${c.id} — ${headline} (${w} @ ${loc})${arch}`;
        return `<option value="${c.id}">${escapeHtml(label)}</option>`;
    }).join('');

    // Group 17.4: derive a fallback parent-filament id for the "Add new" path.
    // All candidates share the same filament (legacy id resolves at the filament
    // level), so pulling from the first one is safe; null-guard for callers
    // that built the candidate list without filament metadata.
    const parentFilamentId = (() => {
        for (const c of candidates) {
            const v = parseInt(c.filament_id, 10);
            if (Number.isFinite(v)) return v;
        }
        return null;
    })();

    const panelHtml = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px; padding:20px 24px; max-width:600px; width:92%;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">⚠️ Multiple spools share Legacy ID ${escapeHtml(legacy_id || '?')}</div>
            <div style="color:#ffc; margin-bottom:14px;">
                ${candidates.length} spools are attached to the filament with this legacy ID. Pick the right one to continue, queue a fresh <code>ID:</code>-format label for the chosen spool, or add a new spool on this filament if none on the list is the right one.
            </div>
            <select id="fcc-legacy-picker-sel" class="form-select form-select-sm bg-dark text-white border-secondary mb-3" size="${Math.min(6, candidates.length)}" style="width:100%;">${optsHtml}</select>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-legacy-picker-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                ${parentFilamentId != null
                    ? `<button id="fcc-legacy-picker-addnew" class="btn btn-outline-info btn-sm" style="min-width:140px;">➕ Add new spool</button>`
                    : ''}
                <button id="fcc-legacy-picker-print" class="btn btn-warning btn-sm" style="min-width:160px;">🖨️ Print new label</button>
                <button id="fcc-legacy-picker-use" class="btn btn-success btn-sm" style="min-width:140px;">✓ Use selected</button>
            </div>
        </div>
    `;

    let cleaned = false;
    const cleanup = () => {
        if (cleaned) return;
        cleaned = true;
        document.removeEventListener('keydown', keyHandler, true);
        try { handle.cleanup(); } catch (_) { /* noop */ }
    };

    const handle = window.mountOverlay({
        id: 'fcc-legacy-picker-overlay',
        content: panelHtml,
        focusGuard: true,
        initialFocus: '#fcc-legacy-picker-use',
        onEscape: () => { cleanup(); onAbort(); },
    });
    const ov = handle.element;

    const sel = () => document.getElementById('fcc-legacy-picker-sel');
    const chosenId = () => {
        const v = sel()?.value;
        const n = parseInt(v, 10);
        return Number.isFinite(n) ? n : null;
    };
    const chosenCandidate = () => {
        const id = chosenId();
        return id == null ? null : (candidates.find(c => c.id === id) || null);
    };

    const onUseClick = () => {
        const id = chosenId();
        cleanup();
        if (id != null) onSelect(id);
        else onAbort();
    };

    const onPrintClick = () => {
        const c = chosenCandidate();
        cleanup();
        if (!c) { onAbort(); return; }
        if (window.addToQueue) {
            const ok = window.addToQueue({
                id: c.id,
                type: 'spool',
                display: c.display || `#${c.id}`,
            });
            if (window.showToast) {
                if (ok) window.showToast(`Added Spool #${c.id} to Print Queue`, 'success', 4000);
                else window.showToast('Label already in queue', 'info', 4000);
            }
        }
        // Re-labeling is the disambiguation route — don't continue the
        // original scan flow (the legacy id is still ambiguous until the
        // user prints + verifies the new ID:NNN label).
        onAbort();
    };

    const onCancelClick = () => { cleanup(); onAbort(); };

    // Group 17.4: route the "Add new spool" affordance through the existing
    // openNewSpoolFromFilamentWizard flow so the user lands in the wizard with
    // the parent filament pre-selected. We abort the original scan flow
    // (legacy id is still ambiguous until the new spool gets its own ID:NNN
    // label printed + verified) — same posture as the "Print new label" path.
    const onAddNewClick = () => {
        cleanup();
        if (parentFilamentId != null && typeof window.openNewSpoolFromFilamentWizard === 'function') {
            window.openNewSpoolFromFilamentWizard(parentFilamentId);
        } else if (window.showToast) {
            window.showToast('Add-new path unavailable (missing filament id)', 'error', 5000);
        }
        onAbort();
    };

    const keyHandler = (e) => {
        // Escape is owned by mountOverlay's onEscape.
        if (e.key === 'Enter') {
            const active = document.activeElement;
            if (active && active.id === 'fcc-legacy-picker-print') { e.preventDefault(); e.stopPropagation(); onPrintClick(); }
            else if (active && active.id === 'fcc-legacy-picker-cancel') { e.preventDefault(); e.stopPropagation(); onCancelClick(); }
            else if (active && active.id === 'fcc-legacy-picker-addnew') { e.preventDefault(); e.stopPropagation(); onAddNewClick(); }
            else { e.preventDefault(); e.stopPropagation(); onUseClick(); }
        }
    };

    ov.querySelector('#fcc-legacy-picker-cancel').onclick = onCancelClick;
    ov.querySelector('#fcc-legacy-picker-print').onclick = onPrintClick;
    ov.querySelector('#fcc-legacy-picker-use').onclick = onUseClick;
    const addNewBtn = ov.querySelector('#fcc-legacy-picker-addnew');
    if (addNewBtn) addNewBtn.onclick = onAddNewClick;
    document.addEventListener('keydown', keyHandler, true);
    // Initial focus on the "Use selected" button is handled by mountOverlay's
    // initialFocus option.
};
