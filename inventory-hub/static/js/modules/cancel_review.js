/* MODULE: Cancelled-Print Review — preview-and-confirm partial deduct (slice 5) */
//
// FilaBridge absorption design §9.7. When the live-pulse detector catches a
// cancelled print it computes the per-tool partial deduct but does NOT auto-
// write it; it stashes a pending record and raises a "🛑 Review" affordance.
// This overlay lists EVERY pending review (several cancels stack up — same or
// different printers — and persist server-side across restarts), shows each
// spool's computed grams (nudgeable, 2-decimal) with a live "→ remaining"
// preview, and lets Derek Confirm (apply) or Discard (drop) — automating the
// manual Connect-reading he does today.
//
// UX contract (slice 5.1, after Derek's 2026-06-12 feedback):
//   • Closing the overlay (× or "Close — keep for later" or Escape) is
//     NON-destructive: every un-actioned review stays pending.
//   • Discard is the ONLY destructive path and needs a two-click confirm, so an
//     accidental click can't silently drop a real deduct.
//   • A persistent badge (activity-log header + Print-Status widget) surfaces
//     the pending count so a review is reachable long after its log line
//     scrolled off.
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
    // remaining/large weights — 1 decimal is plenty.
    function fmt(v) {
        const n = Number(v);
        return Number.isFinite(n) ? Math.round(n * 10) / 10 : 0;
    }
    // partial-deduct grams — small (<1 g common), so keep 2 decimals: a 0.97 g
    // cancel must NOT read as "1 g" (Derek 2026-06-12).
    function fmtG(v) {
        const n = Number(v);
        return Number.isFinite(n) ? Math.round(n * 100) / 100 : 0;
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
                <div class="input-group input-group-sm" style="width:132px;flex:none;">
                    <input type="number" class="fcc-cr-grams form-control bg-dark text-white border-secondary"
                           data-sid="${s.sid}" data-remaining="${s.remaining_before}"
                           value="${fmtG(s.grams)}" step="0.01" min="0" max="${fmt(s.remaining_before)}"
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
        const total = (rec.spools || []).reduce((a, s) => a + (Number(s.grams) || 0), 0);
        return `
            <div class="fcc-cr-card" data-printer="${esc(rec.printer_name)}" data-job="${esc(rec.job_id)}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div style="font-weight:bold;color:#ffd27a;">🛑 ${esc(rec.printer_name)} — cancelled at ~${pct}%</div>
                    <div style="color:#9aa;font-size:0.8rem;">${fmtG(total)}g total</div>
                </div>
                <div style="color:#9aa;font-size:0.78rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                ${rows}
                <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px;">
                    <button type="button" class="btn btn-sm btn-outline-secondary fcc-cr-discard"
                            data-armed="0"
                            title="Permanently drop this review — the spool is NOT deducted">🗑️ Discard</button>
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
                        🛑 Cancelled-Print Reviews <span id="fcc-cr-count" style="color:#9aa;font-weight:normal;font-size:0.85rem;"></span>
                    </div>
                    <button type="button" id="fcc-cr-close"
                        style="background:none;border:none;color:#aaa;font-size:1.4rem;line-height:1;cursor:pointer;"
                        aria-label="Close — reviews stay pending"
                        title="Close — every review stays pending for later">×</button>
                </div>
                <div style="padding:8px 18px 4px;color:#bbb;font-size:0.82rem;">
                    Nudge each spool's grams if needed, then <b>Confirm</b>. <b>Closing keeps everything for later</b> — only <b>Discard</b> drops a review.
                </div>
                <div id="fcc-cr-body" style="padding:8px 18px 14px;max-height:60vh;overflow:auto;">
                    ${cards}
                </div>
                <div style="display:flex;justify-content:flex-end;padding:10px 18px 14px;border-top:1px solid #444;">
                    <button type="button" id="fcc-cr-close-keep" class="btn btn-sm btn-outline-info">Close — keep for later</button>
                </div>
            </div>`;
    }

    // ----- persistent indicators: activity-log header pill + Print-Status badge
    let _lastPending = [];
    function applyBadges(pending) {
        _lastPending = pending;
        const n = pending.length;
        // (a) activity-log header pill
        const badge = document.getElementById('cancel-review-badge');
        if (badge) {
            if (n > 0) {
                badge.textContent = `🛑 ${n} review${n === 1 ? '' : 's'}`;
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }
        }
        // (b) per-printer chips inside the Print-Status widget. The widget
        // re-renders on each pulse, so we (re)inject after render keyed on the
        // printer name carried on each card. Hook is window.cancelReviewDecorate
        // — inv_printer_status.js calls it after it paints (and we also run it
        // here for the badge-poll cadence).
        decoratePrinterStatus();
    }
    function decoratePrinterStatus() {
        const counts = {};
        _lastPending.forEach((r) => { counts[r.printer_name] = (counts[r.printer_name] || 0) + 1; });
        // Add/update/remove one "🛑 N" chip inside `host` for printer `name`.
        // Used on BOTH Print-Status surfaces so a review shows whether the widget
        // is expanded OR minimized.
        const apply = (host, name) => {
            let chip = host.querySelector('.fcc-cr-chip');
            const n = counts[name] || 0;
            if (n > 0) {
                if (!chip) {
                    chip = document.createElement('span');
                    chip.className = 'fcc-cr-chip';
                    chip.style.cssText = 'cursor:pointer;margin-left:6px;font-size:0.78rem;font-weight:bold;color:#ffae42;';
                    chip.title = 'Cancelled-print partial deduct waiting for review — click to review';
                    chip.addEventListener('click', (ev) => { ev.stopPropagation(); openCancelReview(); });
                    host.appendChild(chip);
                }
                chip.textContent = `🛑 ${n}`;
            } else if (chip) {
                chip.remove();
            }
        };
        // Expanded view: next to the printer name. (`data-printer` entity-decodes
        // to the real name in the DOM, matching the record's printer_name.)
        document.querySelectorAll('.fcc-ps-row[data-printer]').forEach((row) => {
            const nameEl = row.querySelector('.fcc-ps-name');
            if (nameEl) apply(nameEl, row.getAttribute('data-printer'));
        });
        // Minimized/collapsed view: onto each printer's group in the header chip
        // strip — the only thing visible when the widget is minimized (Derek
        // 2026-06-12, "in case the activity log isn't always visible").
        document.querySelectorAll('.fcc-ps-header-chips .fcc-ps-printer-group[data-printer]')
            .forEach((grp) => apply(grp, grp.getAttribute('data-printer')));
    }
    async function refreshBadge() {
        applyBadges(await fetchPending());
    }

    async function openCancelReview() {
        const pending = await fetchPending();
        if (!pending.length) {
            toast('No pending cancel reviews.', 'info');
            applyBadges(pending);
            return;
        }

        // Pre-define cleanup so onEscape doesn't close over an unassigned handle
        // (matches the inv_quickswap.js reference pattern). Closing is always
        // non-destructive — refreshBadge keeps the indicators in sync.
        let handle = null;
        const cleanup = () => { if (handle) handle.cleanup(); refreshBadge(); };
        handle = window.mountOverlay({
            id: OVERLAY_ID,
            content: panelHtml(pending),
            focusGuard: true,
            initialFocus: '.fcc-cr-grams',
            onEscape: cleanup,
        });
        const overlay = handle.element;
        const body = overlay.querySelector('#fcc-cr-body');
        const countEl = overlay.querySelector('#fcc-cr-count');

        function updateCount() {
            const n = body.querySelectorAll('.fcc-cr-card').length;
            if (countEl) countEl.textContent = n > 1 ? `(${n})` : '';
        }
        updateCount();

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
            if (!body.querySelector('.fcc-cr-card')) cleanup();
        }

        overlay.addEventListener('input', (e) => {
            if (e.target.classList && e.target.classList.contains('fcc-cr-grams')) updatePreview(e.target);
        });
        // Both close affordances are non-destructive (reviews stay pending).
        overlay.querySelector('#fcc-cr-close').addEventListener('click', cleanup);
        overlay.querySelector('#fcc-cr-close-keep').addEventListener('click', cleanup);

        function disarmDiscard(btn) {
            btn.dataset.armed = '0';
            btn.textContent = '🗑️ Discard';
            btn.classList.remove('btn-outline-danger');
            btn.classList.add('btn-outline-secondary');
        }

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
                        card.remove(); updateCount(); refreshBadge(); closeIfEmpty();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                    } else if (d.status === 'already_handled') {
                        toast('Already handled elsewhere.', 'info');
                        card.remove(); updateCount(); refreshBadge(); closeIfEmpty();
                    } else {
                        e.target.disabled = false;
                        toast(d.msg || 'Confirm failed — check the log.', 'error', 7000);
                    }
                } catch (err) {
                    e.target.disabled = false;
                    toast('Confirm failed.', 'error', 7000);
                }
            } else if (e.target.classList.contains('fcc-cr-discard')) {
                const btn = e.target;
                // First click ARMS (no backend call); second click within 4s
                // discards. Guards an accidental click from a permanent drop.
                if (btn.dataset.armed !== '1') {
                    body.querySelectorAll('.fcc-cr-discard[data-armed="1"]').forEach(disarmDiscard);
                    btn.dataset.armed = '1';
                    btn.textContent = '⚠️ Confirm discard';
                    btn.classList.remove('btn-outline-secondary');
                    btn.classList.add('btn-outline-danger');
                    setTimeout(() => { if (btn.dataset.armed === '1') disarmDiscard(btn); }, 4000);
                    return;
                }
                btn.disabled = true;
                try {
                    const r = await fetch('/api/cancel_deduct/dismiss', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ printer_name: printer, job_id: job }),
                    });
                    const d = await r.json();
                    if (d.status === 'dismissed' || d.status === 'already_handled') {
                        toast(d.status === 'dismissed' ? 'Review discarded (no deduct).' : 'Already handled elsewhere.', 'info');
                        card.remove(); updateCount(); refreshBadge(); closeIfEmpty();
                    } else {
                        btn.disabled = false; disarmDiscard(btn);
                        toast(d.msg || 'Discard failed — check the log.', 'error', 7000);
                    }
                } catch (err) {
                    btn.disabled = false; disarmDiscard(btn);
                    toast('Discard failed.', 'error', 7000);
                }
            }
        });
    }

    // Accepts an optional meta string (from the activity-log button) but always
    // shows ALL pending reviews — robust even if the clicked line scrolled off.
    window.openCancelReview = openCancelReview;
    window.refreshCancelReviewBadge = refreshBadge;
    // inv_printer_status.js calls this after it re-renders, so per-printer chips
    // survive the widget repaint without a fresh fetch.
    window.cancelReviewDecorate = decoratePrinterStatus;

    // Keep the indicators live: on load, on a slow poll, and after every sync
    // pulse (a confirm/deduct fires one). Cheap — one tiny GET.
    function startBadge() {
        refreshBadge();
        setInterval(refreshBadge, 20000);
        document.addEventListener('inventory:sync-pulse', refreshBadge);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startBadge);
    } else {
        startBadge();
    }
})();
