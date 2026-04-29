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

    let ov = document.getElementById('fcc-legacy-picker-overlay');
    if (ov) ov.remove();

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

    ov = document.createElement('div');
    ov.id = 'fcc-legacy-picker-overlay';
    ov.style.cssText = 'position:fixed; inset:0; z-index:20000; background:rgba(0,0,0,0.85); display:flex; align-items:center; justify-content:center;';
    ov.innerHTML = `
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px; padding:20px 24px; max-width:600px; width:92%;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">⚠️ Multiple spools share Legacy ID ${escapeHtml(legacy_id || '?')}</div>
            <div style="color:#ffc; margin-bottom:14px;">
                ${candidates.length} spools are attached to the filament with this legacy ID. Pick the right one to continue, or queue a fresh <code>ID:</code>-format label for the chosen spool so future scans aren't ambiguous.
            </div>
            <select id="fcc-legacy-picker-sel" class="form-select form-select-sm bg-dark text-white border-secondary mb-3" size="${Math.min(6, candidates.length)}" style="width:100%;">${optsHtml}</select>
            <div style="display:flex; gap:10px; justify-content:flex-end; flex-wrap:wrap;">
                <button id="fcc-legacy-picker-cancel" class="btn btn-secondary btn-sm" style="min-width:100px;">Cancel</button>
                <button id="fcc-legacy-picker-print" class="btn btn-warning btn-sm" style="min-width:160px;">🖨️ Print new label</button>
                <button id="fcc-legacy-picker-use" class="btn btn-success btn-sm" style="min-width:140px;">✓ Use selected</button>
            </div>
        </div>
    `;
    document.body.appendChild(ov);

    let cleaned = false;
    const cleanup = () => {
        if (cleaned) return;
        cleaned = true;
        try { ov.remove(); } catch (_) { /* noop */ }
        document.removeEventListener('keydown', keyHandler, true);
    };

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

    const keyHandler = (e) => {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onCancelClick(); return; }
        if (e.key === 'Enter') {
            const active = document.activeElement;
            if (active && active.id === 'fcc-legacy-picker-print') { e.preventDefault(); e.stopPropagation(); onPrintClick(); }
            else if (active && active.id === 'fcc-legacy-picker-cancel') { e.preventDefault(); e.stopPropagation(); onCancelClick(); }
            else { e.preventDefault(); e.stopPropagation(); onUseClick(); }
        }
    };

    document.getElementById('fcc-legacy-picker-cancel').onclick = onCancelClick;
    document.getElementById('fcc-legacy-picker-print').onclick = onPrintClick;
    document.getElementById('fcc-legacy-picker-use').onclick = onUseClick;
    document.addEventListener('keydown', keyHandler, true);
    setTimeout(() => {
        try {
            const useBtn = document.getElementById('fcc-legacy-picker-use');
            if (useBtn) useBtn.focus();
        } catch (_) { /* noop */ }
    }, 0);
};
