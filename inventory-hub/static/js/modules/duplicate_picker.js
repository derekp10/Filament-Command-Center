/* MODULE: DUPLICATE PICKER (legacy ID disambiguation) */
console.log("🚀 Loaded Module: DUPLICATE PICKER");

// window.showLegacySpoolPicker(payload, opts)
//
// payload: { legacy_id: string, candidates: [{id, remaining_weight, location,
//            archived, filament_id, filament_name, material, vendor_name,
//            color_hex, display}, ...] }
// opts.onSelect(spoolId, source): called when the user picks a spool with
//                 "✓ Use selected" (source 'keyboard': a pick from the list is
//                 no label scan), or scans a listed spool's own label (an
//                 ID:<n> label keeps the scan's own source; an SPL:<n> or a
//                 bare number goes as 'keyboard', since only a scanned ID:
//                 label verifies a spool's printed label, as outside the
//                 picker).
// opts.onAbort(): called when the user cancels OR queues a label (no further
//                 scan flow — the re-labeling route disambiguates from here).
//
// Inline overlay (no nested Swal — see CLAUDE.md "Project Conventions").
// Keyboard: Enter activates focused button (defaults to "Use selected"),
// Escape cancels.
// Scans (Group 61; Derek, 2026-10-29: "hold until answered … or if the ID
// matches a spool for the group, than maybe select that spool"): a scan never
// presses a button here. Its Enter and any Space inside it are the scan's, so
// the scan reaches processScan, which brings it to this open question: a
// listed spool's own label (ID:<n>, SPL:<n>, or the bare number the scan path
// reads as a spool id first) picks that spool, CMD:CANCEL cancels, and any
// other scan is refused with a note and does nothing. Before, its Enter
// pressed "Use selected" (the first spool joined the buffer) and the scan's
// own text stayed in the scan buffer, glued to the next scan ("ID:57ID:58").
// A person who types in the list to jump to a spool ("#135": every option
// starts with its number) and presses Enter picks the spool the list jumped
// to (Group 61 review: it was refused as a scan of "#135").
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
        <div style="background:#1e1e1e; color:#fff; border:2px solid #ffaa00; border-radius:8px; padding:20px 24px; max-width:37.5rem; width:92%;">
            <div style="font-size:1.2em; font-weight:bold; margin-bottom:8px;">⚠️ Multiple spools share Legacy ID ${escapeHtml(legacy_id || '?')}</div>
            <div style="color:#ffc; margin-bottom:14px;">
                ${candidates.length} spools are attached to the filament with this legacy ID. Pick the right one to continue, queue a fresh <code style="color:#ffaa55;">ID:</code>-format label for the chosen spool, or add a new spool on this filament if none on the list is the right one.
            </div>
            <div id="fcc-legacy-picker-flash" role="alert" style="color:#ffc107; min-height:1.5em; margin-bottom:8px;"></div>
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
    let question = null;
    const cleanup = () => {
        if (cleaned) return;
        cleaned = true;
        document.removeEventListener('keydown', keyHandler, true);
        // It holds scans off no longer (processScan reads the open questions).
        if (question) {
            const open = (window._fccOpenMoveQuestions || []).filter(q => q !== question);
            window._fccOpenMoveQuestions = open;
            window._fccOpenMoveQuestion = open.length ? open[open.length - 1] : null;
        }
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
        if (id != null) onSelect(id, 'keyboard');
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
        // A Space inside a scan (a location id may hold one) never presses the
        // focused button; the scan accumulator still reads it.
        if (e.key === ' ' && window.scanIsArriving && window.scanIsArriving()) { e.preventDefault(); return; }
        if (e.key === 'Enter') {
            const active = document.activeElement;
            // A scan's Enter is the scan's: the accumulator sends it to
            // processScan, which brings it back here as an answer or refuses it.
            // Not keys a person typed in the list to jump to the spool it now
            // shows (the start of its text, "#135").
            const st = (typeof state !== 'undefined') ? state : window.state;
            const typed = (st && typeof st.scanBuffer === 'string' ? st.scanBuffer : '').trim().toLowerCase();
            const shown = active && active.id === 'fcc-legacy-picker-sel' && active.options[active.selectedIndex];
            const jumped = !!(typed && shown && !(window.isScannerBurst && window.isScannerBurst())
                && String(shown.textContent || '').trim().toLowerCase().startsWith(typed));
            if (!jumped && (window.enterIsAScan ? window.enterIsAScan() : (window.isScanInFlight && window.isScanInFlight()))) return;
            e.preventDefault(); e.stopPropagation();
            // A person's Enter: a key they left in the scan buffer goes with it.
            if (window.clearScanBuffer) window.clearScanBuffer();
            if (active && active.id === 'fcc-legacy-picker-print') onPrintClick();
            else if (active && active.id === 'fcc-legacy-picker-cancel') onCancelClick();
            else if (active && active.id === 'fcc-legacy-picker-addnew') onAddNewClick();
            else onUseClick();
        }
    };

    // The open question processScan brings every scan to while the picker is
    // up (the move questions' registry, inv_cmd.js).
    const flash = (msg) => { const f = ov.querySelector('#fcc-legacy-picker-flash'); if (f) f.textContent = msg; };
    const refuse = (text, why) => {
        flash(why);
        if (window.showToast) window.showToast(why, 'warning', 7000);
        // The Activity Log draws its lines as HTML: the scan's text is escaped.
        const esc = window.escHtml || ((s) => s);
        if (window.logClientEvent) window.logClientEvent(`⚠️ Scan "${esc(String(text).trim())}" ignored: ${esc(why)}`, 'WARNING');
        return 'refused';
    };
    const legacyUp = String(legacy_id == null ? '' : legacy_id).trim().toUpperCase();
    question = {
        title: `Multiple spools share Legacy ID ${legacy_id || '?'}`,
        element: ov,
        hint: 'Answer the question on screen first: pick a spool (or scan its own label), print a new label, add a new spool, or Cancel',
        cancel: () => onCancelClick(),
        flash,
        route: (text, source) => {
            const t = String(text == null ? '' : text).trim().toUpperCase();
            const m = /(?:ID|SPL):(\d+)$/.exec(t) || /^#?(\d+)$/.exec(t);
            const id = m ? parseInt(m[1], 10) : null;
            if (m && candidates.some(c => c.id === id)) {
                cleanup();
                // Only a scanned ID: label verifies a spool's printed label (the
                // server's rule, routes_scan.py): an SPL: label or a bare number
                // goes out as no label scan, as it does outside the picker.
                onSelect(id, /(?:^|[^A-Z])ID:\d+$/.test(t) ? (source || 'keyboard') : 'keyboard');
                return true;
            }
            // The legacy label this question is about, read again (a scanner's
            // double read): it is no spool number.
            const leg = /(?:LEGACY|LEG|OLD):(.+)$/.exec(t);
            if (legacyUp && ((leg && leg[1].trim() === legacyUp) || (!leg && t === legacyUp))) {
                return refuse(text, `That is legacy label ${legacy_id}, which this question is about: pick one of the spools listed, print a new label, add a new spool, or Cancel`);
            }
            if (!m) return false;
            return refuse(text, `#${id} isn't one of the spools listed: pick one of them, print a new label, add a new spool, or Cancel`);
        },
    };
    window._fccOpenMoveQuestions = (window._fccOpenMoveQuestions || []).concat([question]);
    window._fccOpenMoveQuestion = question;

    ov.querySelector('#fcc-legacy-picker-cancel').onclick = onCancelClick;
    ov.querySelector('#fcc-legacy-picker-print').onclick = onPrintClick;
    ov.querySelector('#fcc-legacy-picker-use').onclick = onUseClick;
    const addNewBtn = ov.querySelector('#fcc-legacy-picker-addnew');
    if (addNewBtn) addNewBtn.onclick = onAddNewClick;
    document.addEventListener('keydown', keyHandler, true);
    // Initial focus on the "Use selected" button is handled by mountOverlay's
    // initialFocus option.
};
