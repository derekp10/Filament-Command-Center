/* MODULE: Cancelled-Print Review — preview-and-confirm partial deduct (slice 5) */
//
// FilaBridge absorption design §9.7. When the live-pulse detector catches a
// cancelled print it computes the per-tool partial deduct but does NOT auto-
// write it; it stashes a pending record and raises a "🛑 Review" button on the
// activity-log line. This overlay lists every pending review, shows each spool's
// computed grams (nudgeable) with a live "→ remaining" preview, and lets Derek
// Confirm (apply) or Dismiss (drop) — automating the manual Connect-reading he
// does today.
//
// Inline overlay routes through window.mountOverlay (CLAUDE.md "Inline overlays
// MUST route through mountOverlay" — NOT a nested Swal). The backend owns the
// write; this component only collects the nudged grams and POSTs.

(function () {
    const OVERLAY_ID = 'fcc-cancel-review-overlay';

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function fmt(v) {
        const n = Number(v);
        return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
    }
    function toast(msg, type, dur) {
        if (window.showToast) window.showToast(msg, type, dur);
    }

    async function fetchPending() {
        try {
            const r = await fetch('/api/cancel_deduct/pending');
            if (!r.ok) return [];
            const d = await r.json();
            return Array.isArray(d.pending) ? d.pending : [];
        } catch (e) {
            return [];
        }
    }

    function spoolRowHtml(s) {
        const swatch = window.makeSwatchHtml
            ? window.makeSwatchHtml(s.color, 'longitudinal',
                { size: 16, borderColor: 'rgba(255,255,255,0.5)', marginRight: 0 })
            : '';
        return `
            <div class="fcc-cr-row" data-sid="${s.sid}"
                 style="display:flex;align-items:center;gap:8px;justify-content:space-between;
                        padding:6px 0;border-bottom:1px solid #2b2c30;">
                <div style="min-width:0;flex:1;">
                    ${swatch}
                    <span style="color:#eee;">${esc(s.display)}</span>
                    <span style="color:#9aa;font-size:0.8rem;">
                        (${esc(s.toolhead)} · ${fmt(s.remaining_before)}g left)
                    </span>
                </div>
                <div class="input-group input-group-sm" style="width:128px;flex:none;">
                    <input type="number" class="fcc-cr-grams form-control bg-dark text-white border-secondary"
                           data-sid="${s.sid}" data-remaining="${s.remaining_before}"
                           value="${fmt(s.grams)}" step="0.1" min="0" max="${fmt(s.remaining_before)}"
                           autocomplete="off" style="font-size:0.95rem;" />
                    <span class="input-group-text bg-dark text-light border-secondary">g</span>
                </div>
                <div class="fcc-cr-preview" data-sid="${s.sid}"
                     style="width:96px;flex:none;text-align:right;color:#9fe0b0;font-size:0.82rem;">
                    → ${fmt(s.remaining_after)}g
                </div>
            </div>`;
    }

    function cardHtml(rec) {
        const pct = Math.round((Number(rec.progress) || 0) * 100);
        const rows = (rec.spools || []).map(spoolRowHtml).join('');
        return `
            <div class="fcc-cr-card" data-printer="${esc(rec.printer_name)}" data-job="${esc(rec.job_id)}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div style="font-weight:bold;color:#ffd27a;">🛑 ${esc(rec.printer_name)} — cancelled at ~${pct}%</div>
                    <div style="color:#9aa;font-size:0.8rem;">${esc(rec.total_grams)}g total</div>
                </div>
                <div style="color:#9aa;font-size:0.78rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                ${rows}
                <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px;">
                    <button type="button" class="btn btn-sm btn-outline-secondary fcc-cr-dismiss">Dismiss (no deduct)</button>
                    <button type="button" class="btn btn-sm btn-success fw-bold fcc-cr-confirm">Confirm deduct</button>
                </div>
            </div>`;
    }

    function panelHtml(pending) {
        const cards = pending.map(cardHtml).join('');
        return `
            <div role="dialog" aria-modal="true" aria-labelledby="fcc-cr-title"
                 style="background:#1f2024;color:#eee;border:1px solid #555;border-radius:8px;
                        min-width:420px;max-width:640px;width:94vw;
                        box-shadow:0 8px 32px rgba(0,0,0,0.6);">
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:14px 18px;border-bottom:1px solid #444;">
                    <div id="fcc-cr-title" style="font-weight:bold;font-size:1.05rem;">
                        🛑 Cancelled-Print Review
                    </div>
                    <button type="button" id="fcc-cr-close"
                        style="background:none;border:none;color:#aaa;font-size:1.4rem;line-height:1;cursor:pointer;"
                        aria-label="Close">×</button>
                </div>
                <div style="padding:8px 18px 4px;color:#bbb;font-size:0.82rem;">
                    Review each spool's computed partial deduct. Nudge the grams if needed, then Confirm — or Dismiss to skip.
                </div>
                <div id="fcc-cr-body" style="padding:8px 18px 14px;max-height:64vh;overflow:auto;">
                    ${cards}
                </div>
            </div>`;
    }

    async function openCancelReview() {
        const pending = await fetchPending();
        if (!pending.length) {
            toast('No pending cancel reviews.', 'info');
            return;
        }

        // Pre-define cleanup so onEscape doesn't close over an unassigned handle
        // (matches the inv_quickswap.js reference pattern).
        let handle = null;
        const cleanup = () => { if (handle) handle.cleanup(); };
        handle = window.mountOverlay({
            id: OVERLAY_ID,
            content: panelHtml(pending),
            focusGuard: true,
            initialFocus: '.fcc-cr-grams',
            onEscape: cleanup,
        });
        const overlay = handle.element;
        const body = overlay.querySelector('#fcc-cr-body');

        function updatePreview(input) {
            const sid = input.dataset.sid;
            const rem = parseFloat(input.dataset.remaining) || 0;
            const g = parseFloat(input.value);
            const prev = overlay.querySelector(`.fcc-cr-preview[data-sid="${sid}"]`);
            if (!prev) return;
            if (Number.isNaN(g)) { prev.textContent = '→ —'; prev.style.color = '#9aa'; return; }
            // Amber-warn when the nudge would empty the spool (deduct clamps to
            // remaining on confirm — flag it so an over-nudge isn't a surprise).
            const over = g > rem;
            prev.textContent = `${over ? '⚠️ ' : ''}→ ${fmt(Math.max(0, rem - g))}g`;
            prev.style.color = over ? '#ffc107' : '#9fe0b0';
        }
        function closeIfEmpty() {
            if (!body.querySelector('.fcc-cr-card')) handle.cleanup();
        }

        overlay.addEventListener('input', (e) => {
            if (e.target.classList && e.target.classList.contains('fcc-cr-grams')) updatePreview(e.target);
        });
        overlay.querySelector('#fcc-cr-close').addEventListener('click', () => handle.cleanup());

        body.addEventListener('click', async (e) => {
            const card = e.target.closest('.fcc-cr-card');
            if (!card) return;
            const printer = card.dataset.printer;
            const job = card.dataset.job;

            if (e.target.classList.contains('fcc-cr-confirm')) {
                const updates = {};
                card.querySelectorAll('.fcc-cr-grams').forEach((inp) => {
                    const g = parseFloat(inp.value);
                    if (!Number.isNaN(g) && g > 0) updates[inp.dataset.sid] = g;
                });
                e.target.disabled = true;
                try {
                    const r = await fetch('/api/cancel_deduct/confirm', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ printer_name: printer, job_id: job, updates }),
                    });
                    const d = await r.json();
                    if (d.status === 'confirmed') {
                        toast(`Deducted from ${(d.applied || []).length} spool(s).`, 'success');
                        if ((d.errors || []).length) toast(`${d.errors.length} spool(s) failed — check the log.`, 'error', 7000);
                        card.remove(); closeIfEmpty();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                    } else if (d.status === 'already_handled') {
                        toast('Already handled elsewhere.', 'info');
                        card.remove(); closeIfEmpty();
                    } else {
                        e.target.disabled = false;
                        toast(d.msg || 'Confirm failed — check the log.', 'error', 7000);
                    }
                } catch (err) {
                    e.target.disabled = false;
                    toast('Confirm failed.', 'error', 7000);
                }
            } else if (e.target.classList.contains('fcc-cr-dismiss')) {
                e.target.disabled = true;
                try {
                    const r = await fetch('/api/cancel_deduct/dismiss', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ printer_name: printer, job_id: job }),
                    });
                    const d = await r.json();
                    if (d.status === 'dismissed') {
                        toast('Review dismissed (no deduct).', 'info');
                        card.remove(); closeIfEmpty();
                    } else if (d.status === 'already_handled') {
                        toast('Already handled elsewhere.', 'info');
                        card.remove(); closeIfEmpty();
                    } else {
                        e.target.disabled = false;
                        toast(d.msg || 'Dismiss failed — check the log.', 'error', 7000);
                    }
                } catch (err) {
                    e.target.disabled = false;
                    toast('Dismiss failed.', 'error', 7000);
                }
            }
        });
    }

    // Accepts an optional meta string (from the activity-log button) but always
    // shows ALL pending reviews — robust even if the clicked line scrolled off.
    window.openCancelReview = openCancelReview;
})();
