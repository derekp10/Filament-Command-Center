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

    // ----- Group 43.3: pick the spool a review charges -----------------------
    // PrusaLink says nothing per slot, so FCC can't see that a print sliced for
    // T0 ran on T1 (Derek's job 1104/1105 case). Every review line gets a picker:
    // the spool the review expected (a row's own spool, or a head's spool at
    // print end), any spool on one of the printer's heads NOW (fetched once per
    // printer, injected when it arrives), or any spool by #id.
    async function fetchCandidates(printer) {
        try {
            const r = await fetch(`/api/cancel_deduct/candidates?printer_name=${encodeURIComponent(printer)}`);
            if (!r.ok) return [];
            const d = await r.json();
            return Array.isArray(d.heads) ? d.heads : [];
        } catch (e) {
            return [];
        }
    }

    // `own` = the line's default spool (a row's sid), or null for a no_spool line.
    // `atEnd` is the heads snapshot the review recorded. On the deferred-fetch
    // path that is when FCC logged the print, not the moment it ended, so the
    // label says that.
    function pickSelectHtml(line, own, ownLabel, atEnd) {
        const first = own != null
            ? `<option value="${esc(own)}" selected>${esc(ownLabel)}</option>`
            : `<option value="" selected>— pick the spool it used —</option>`;
        const ended = (atEnd || []).filter((h) => h.sid != null && String(h.sid) !== String(own))
            .map((h) => `<option value="${esc(h.sid)}">#${esc(h.sid)} — on ${esc(h.toolhead)} when FCC logged the print</option>`)
            .join('');
        // The #id box is text, not number: arrow keys on a number box step it
        // (an empty one to 1), and charging spool #1 by accident is a real write.
        return `
            <select class="fcc-cr-pick form-select form-select-sm bg-dark text-light border-secondary"
                    data-line="${esc(line)}" data-own="${own == null ? '' : esc(own)}"
                    style="max-width:330px;font-size:0.92rem;">
                ${first}
                ${ended ? `<optgroup label="When FCC logged the print" class="fcc-cr-ended">${ended}</optgroup>` : ''}
                <option value="other">Another spool by #ID…</option>
            </select>
            <input type="text" inputmode="numeric" class="fcc-cr-other form-control form-control-sm bg-dark text-white border-secondary"
                   data-line="${esc(line)}" placeholder="#id" autocomplete="off"
                   style="display:none;width:96px;font-size:0.92rem;" />
            <span class="fcc-cr-other-info" data-line="${esc(line)}" style="color:#9aa;font-size:0.85rem;"></span>`;
    }

    // Live heads arrive after render; add them to every picker on that printer's cards.
    function injectHeads(card, heads) {
        const usable = (heads || []).filter((h) => h.sid != null && !h.archived);
        if (!usable.length) return;
        card.querySelectorAll('.fcc-cr-pick').forEach((sel) => {
            if (sel.querySelector('.fcc-cr-now')) return;
            const group = document.createElement('optgroup');
            group.label = "On this printer's heads now";
            group.className = 'fcc-cr-now';
            usable.forEach((h) => {
                if (String(h.sid) === sel.dataset.own) return;
                const opt = document.createElement('option');
                opt.value = String(h.sid);
                opt.dataset.remaining = h.remaining == null ? '' : String(h.remaining);
                const left = h.remaining == null ? 'capacity unknown' : `${fmt(h.remaining)}g left`;
                opt.textContent = `${h.toolhead}: ${h.display || '#' + h.sid} (${left})`;
                group.appendChild(opt);
            });
            if (group.children.length) sel.insertBefore(group, sel.querySelector('option[value="other"]'));
        });
    }

    // The spool a line will charge: the picker's choice, or the typed #id.
    function pickedSid(card, line) {
        const sel = card.querySelector(`.fcc-cr-pick[data-line="${CSS.escape(line)}"]`);
        if (!sel) return null;
        if (sel.value === 'other') {
            const inp = card.querySelector(`.fcc-cr-other[data-line="${CSS.escape(line)}"]`);
            const v = String((inp && inp.value) || '').trim().replace(/^#/, '');
            const n = /^\d+$/.test(v) ? parseInt(v, 10) : NaN;
            return Number.isFinite(n) && n > 0 ? n : null;
        }
        const n = parseInt(sel.value, 10);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    function spoolRowHtml(s) {
        const swatch = window.makeSwatchHtml
            ? window.makeSwatchHtml(s.color, 'longitudinal',
                { size: 16, borderColor: 'rgba(255,255,255,0.5)', marginRight: 0 })
            : '';
        // 22.4 residual: a toolhead with 2+ distinct loaded spools is AMBIGUOUS —
        // the autonomous deduct SKIPS it (can't tell which spool is loaded), so its
        // grams weren't auto-deducted and it's surfaced here for the reviewer to
        // resolve. Without a per-row cue the reviewer sees two identical-looking rows
        // with no hint why. Flag the row (left border + badge) so the bad assignment
        // is visible. (Distinct from the card-level `rec.ambiguous` cancel-vs-completed
        // flag — this is a per-spool-row indicator.)
        const amb = !!s.ambiguous;
        const isRunout = !!s.runout;
        const ambBorder = amb ? 'border-left:3px solid #ffae42;padding-left:6px;' : '';
        const ambBadge = amb
            ? `<span title="This toolhead has more than one spool assigned — FCC can't tell which is loaded, so these grams weren't auto-deducted. Pick the real amount per spool."
                     style="margin-left:6px;font-size:0.74rem;font-weight:bold;color:#ffae42;
                            border:1px solid #ffae42;border-radius:4px;padding:0 4px;white-space:nowrap;">⚠️ ambiguous</span>`
            : '';
        // 43.1: a spool with no known capacity (neither it nor its filament has a
        // weight) reports remaining as null — say so rather than "0g left".
        const known = s.remaining_before != null;
        return `
            <div class="fcc-cr-row" data-sid="${s.sid}"
                 style="display:flex;align-items:center;gap:8px;justify-content:space-between;flex-wrap:wrap;
                        padding:6px 0;border-bottom:1px solid #2b2c30;${ambBorder}">
                <div style="min-width:0;flex:1;">
                    ${swatch}
                    <span style="color:#eee;">${esc(s.display)}</span>${ambBadge}${isRunout ? `<span title="Ran out mid-print (sensor tripped) — charged its own segment up to the swap, plus the sensor-to-nozzle remnant when a per-printer path value is configured."
                     style="margin-left:6px;font-size:0.74rem;font-weight:bold;color:#ff8a65;
                            border:1px solid #ff8a65;border-radius:4px;padding:0 4px;white-space:nowrap;">ran out</span>` : ''}
                    <span style="color:#9aa;font-size:0.92rem;">
                        (${esc(s.toolhead)} · ${known ? `${fmt(s.remaining_before)}g left` : 'capacity unknown'})
                    </span>
                </div>
                <div class="input-group input-group-sm" style="width:132px;flex:none;">
                    <input type="number" class="fcc-cr-grams form-control bg-dark text-white border-secondary"
                           data-sid="${s.sid}" data-remaining="${known ? s.remaining_before : ''}"
                           data-own-remaining="${known ? s.remaining_before : ''}"
                           value="${fmtG(s.grams)}" step="0.01" min="0" ${known ? `max="${fmt(s.remaining_before)}"` : ''}
                           autocomplete="off" style="font-size:1.05rem;" />
                    <span class="input-group-text bg-dark text-light border-secondary">g</span>
                </div>
                <div class="fcc-cr-preview" data-sid="${s.sid}"
                     style="width:104px;flex:none;text-align:right;color:#9fe0b0;font-size:0.95rem;">
                    → ${known ? `${fmt(s.remaining_after)}g` : '?'}
                </div>
                <div class="fcc-cr-redirect" style="flex-basis:100%;display:flex;align-items:center;gap:6px;
                            padding-left:24px;color:#9aa;font-size:0.88rem;">
                    charge to: ${pickSelectHtml(s.sid, s.sid, `this spool (#${s.sid})`, null)}
                </div>
            </div>`;
    }

    // Group 43.3: a no_spool review has grams per tool but no spool. One line per
    // tool the print used: its grams (nudgeable) and the picker.
    function noSpoolLinesHtml(rec) {
        const usage = rec.usage_map || {};
        const atEnd = Array.isArray(rec.heads_at_end) ? rec.heads_at_end : [];
        return Object.keys(usage).sort((a, b) => Number(a) - Number(b)).map((pos) => {
            const head = atEnd.find((h) => String(h.position) === String(pos));
            const where = head ? `T${esc(pos)} · ${esc(head.toolhead)}` : `T${esc(pos)}`;
            return `
                <div class="fcc-cr-pickline" data-line="${esc(pos)}"
                     style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 0;border-bottom:1px solid #2b2c30;">
                    <span style="color:#eee;min-width:120px;">${where} used</span>
                    <div class="input-group input-group-sm" style="width:120px;flex:none;">
                        <input type="number" class="fcc-cr-pgrams form-control bg-dark text-white border-secondary"
                               data-line="${esc(pos)}" value="${fmtG(usage[pos])}" step="0.01" min="0"
                               autocomplete="off" style="font-size:1.05rem;" />
                        <span class="input-group-text bg-dark text-light border-secondary">g</span>
                    </div>
                    <span style="color:#9aa;">→</span>
                    ${pickSelectHtml(pos, null, '', atEnd)}
                </div>`;
        }).join('');
    }

    // Unresolved reviews (2026-06-13): usage couldn't be finalized at print-end.
    //   no_spool         — real grams computed, but NO spool was bound to the
    //                      toolhead. Apply RE-RESOLVES to whatever's bound now.
    //   progress_unknown — the print was replaced before a progress reading, so
    //                      its usage is unmeasurable. Weigh + adjust, or Discard.
    // Neither carries per-spool nudge rows; both are non-destructive until acted on.
    function unresolvedCardHtml(rec, kind) {
        const total = fmtG(rec.total_grams);
        const isNoSpool = kind === 'no_spool';
        const header = isNoSpool
            ? `⚠️ ${esc(rec.printer_name)} — ${total}g computed, no spool bound`
            : `❓ ${esc(rec.printer_name)} — couldn't measure usage`;
        // Group 43.3: no_spool names no spool, so the user picks one per tool. A
        // print sliced for one head can run on another (chosen on the printer),
        // which FCC can't see; the picker offers the spools that were on the
        // printer's heads when it ended, the spools on them now, or any #id.
        const banner = isNoSpool
            ? `FCC computed this print used <b>${total}g</b>, but couldn't charge it: <b>no spool was
               loaded</b> on the head it was sliced for when it ended (or Spoolman rejected the write),
               so nothing was deducted. <b>Pick the spool it really used</b> for each tool — a print
               can run on a different head than it was sliced for — then <b>Apply</b>. Or
               <b>Discard</b> if you've already trued it up.`
            : `FCC couldn't measure how much filament this print used — it was <b>replaced by a new
               print before a progress reading</b>. <b>Weigh the spool</b> and adjust it directly, or
               <b>Discard</b> this review.`;
        const applyBtn = isNoSpool
            ? `<button type="button" class="btn btn-sm btn-success fw-bold fcc-cr-confirm">Apply to the picked spool(s)</button>`
            : '';
        const lines = isNoSpool ? noSpoolLinesHtml(rec) : '';
        return `
            <div class="fcc-cr-card" data-printer="${esc(rec.printer_name)}" data-job="${esc(rec.job_id)}"
                 data-kind="${esc(kind)}" data-ambiguous="${rec.ambiguous ? '1' : '0'}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div style="font-weight:bold;color:${isNoSpool ? '#ffd27a' : '#7ec8ff'};">${header}</div>
                    <div style="color:#9aa;font-size:0.92rem;">${isNoSpool ? total + 'g' : 'unmeasured'}</div>
                </div>
                <div style="color:#9aa;font-size:0.9rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                <div style="color:#e6c074;font-size:0.95rem;margin-bottom:10px;line-height:1.45;
                            background:#221d12;border:1px solid #3a2f17;border-radius:4px;padding:9px 11px;">
                    ${banner}
                </div>
                ${lines}
                <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px;">
                    <button type="button" class="btn btn-sm btn-outline-secondary fcc-cr-discard"
                            data-armed="0"
                            title="Permanently drop this review — the spool is NOT deducted">🗑️ Discard</button>
                    ${applyBtn}
                </div>
            </div>`;
    }

    function cardHtml(rec) {
        const kind = rec.kind || 'partial';
        const pct = Math.round((Number(rec.progress) || 0) * 100);
        if (kind === 'no_spool' || kind === 'progress_unknown') return unresolvedCardHtml(rec, kind);
        const rows = (rec.spools || []).map(spoolRowHtml).join('');
        const total = (rec.spools || []).reduce((a, s) => a + (Number(s.grams) || 0), 0);
        // spool_changed (22.3): a COMPLETED print whose toolhead spool changed
        // mid-print (run-out / M600 replace). The full footer was NOT auto-applied
        // (it would dump the whole tool's usage on the replacement + record 0g on
        // the run-out spool); the user splits the grams manually.
        const spoolChanged = kind === 'spool_changed';
        const changedPos = (rec.changed_positions || []).join(', ');
        // Ambiguous (2026-06-13): the print reached idle without an observed
        // terminal state, so FCC couldn't confirm cancel vs completion. Reword
        // the header + banner; the grams are computed at the last seen progress
        // (the confidence hint), nudgeable either way.
        const ambiguous = !spoolChanged && !!rec.ambiguous;
        let header, banner, headerColor;
        const autoSplit = spoolChanged && !!rec.auto_split;
        if (spoolChanged) {
            headerColor = '#ffb74d';
            header = `🔁 ${esc(rec.printer_name)} — spool changed mid-print`;
            banner = autoSplit
                ? `🔁 A spool feeding this print was <b>changed mid-print</b> (a filament run-out
               or M600) at toolhead position(s) <b>${esc(changedPos)}</b>. FCC <b>auto-split</b>
               the slicer total by the swap point — each row below is charged only <b>its own
               segment</b> (the run-out spool up to the swap, the replacement after it), pre-filled.
               Just <b>Confirm</b>, or nudge if you weighed it. The run-out spool's sensor→nozzle
               remnant is included when a per-printer path value is configured. Or <b>Discard</b>.`
                : `🔁 A spool feeding this print was <b>changed mid-print</b> (a filament
               run-out or M600) at toolhead position(s) <b>${esc(changedPos)}</b>, so the full
               slicer total was <b>NOT auto-applied</b> — it would charge the whole tool's usage
               to the <b>replacement</b> spool and leave the run-out spool at 0g. The rows below
               are the <b>replacement</b> spool(s) at completion: nudge each <b>down</b> to what
               it actually used, then weigh + true up the run-out spool separately (it isn't shown
               here once it left the toolhead). Confirm to deduct, or <b>Discard</b>.`;
        } else {
            headerColor = ambiguous ? '#7ec8ff' : '#ffd27a';
            header = ambiguous
                ? `❓ ${esc(rec.printer_name)} — ended at ~${pct}% (couldn't confirm: completed or cancelled?)`
                : `🛑 ${esc(rec.printer_name)} — cancelled at ~${pct}%`;
            banner = ambiguous
                ? `❓ FCC couldn't tell whether this print <b>finished</b> or was <b>cancelled</b> — it
                   reached idle without a clear cancel/finish signal (a fast restart, or the printer
                   power-cycled). The grams below are computed at the last seen progress (~${pct}%).
                   If it actually <b>finished</b>, nudge each spool up to the full amount; if it was
                   <b>cancelled earlier</b>, nudge down. Confirm to deduct, or <b>Discard</b> if it
                   was already handled.`
                : `⚠️ If you cancelled individual objects mid-print — a per-object / M486 cancel,
                   from the printer or Connect — these grams can read <b>high</b>: the gcode still
                   counts the skipped object's filament, which never left the spool. Nudge each
                   spool down to the real amount before confirming.`;
        }
        return `
            <div class="fcc-cr-card" data-printer="${esc(rec.printer_name)}" data-job="${esc(rec.job_id)}"
                 data-ambiguous="${ambiguous ? '1' : '0'}" data-kind="${esc(kind)}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div style="font-weight:bold;color:${headerColor};">${header}</div>
                    <div style="color:#9aa;font-size:0.92rem;">${fmtG(total)}g total</div>
                </div>
                <div style="color:#9aa;font-size:0.9rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                <div style="color:#e6c074;font-size:0.95rem;margin-bottom:10px;line-height:1.45;
                            background:#221d12;border:1px solid #3a2f17;border-radius:4px;padding:9px 11px;">
                    ${banner}
                </div>
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
                        min-width:440px;max-width:680px;width:94vw;font-size:1rem;
                        box-shadow:0 8px 32px rgba(0,0,0,0.6);">
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:14px 18px;border-bottom:1px solid #444;">
                    <div id="fcc-cr-title" style="font-weight:bold;font-size:1.18rem;">
                        🛑 Cancelled-Print Reviews <span id="fcc-cr-count" style="color:#9aa;font-weight:normal;font-size:0.95rem;"></span>
                    </div>
                    <button type="button" id="fcc-cr-close"
                        style="background:none;border:none;color:#aaa;font-size:1.4rem;line-height:1;cursor:pointer;"
                        aria-label="Close — reviews stay pending"
                        title="Close — every review stays pending for later">×</button>
                </div>
                <div style="padding:8px 18px 4px;color:#bbb;font-size:0.95rem;">
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

        // 43.3: one candidates fetch per printer; the pickers fill in when it lands.
        const liveHeads = {};
        [...new Set(pending.map((r) => r.printer_name))].forEach((printer) => {
            fetchCandidates(printer).then((heads) => {
                liveHeads[printer] = heads;
                body.querySelectorAll('.fcc-cr-card').forEach((card) => {
                    if (card.dataset.printer === printer) injectHeads(card, heads);
                });
            });
        });

        // After an Apply that didn't fully land, the server may have reshaped the
        // review (only the failed rows, a redirect's picked spools). Re-render the
        // card from what it stored, so the next Apply names rows the review still
        // has: a stale card's rows are refused as "not in this review".
        async function rerenderCard(card) {
            const printer = card.dataset.printer;
            const job = card.dataset.job;
            const rec = (await fetchPending()).find(
                (r) => String(r.printer_name) === printer && String(r.job_id) === job);
            if (!rec) { card.remove(); updateCount(); refreshBadge(); closeIfEmpty(); return; }
            const tmp = document.createElement('div');
            tmp.innerHTML = cardHtml(rec).trim();
            const fresh = tmp.firstElementChild;
            card.replaceWith(fresh);
            if (liveHeads[printer]) injectHeads(fresh, liveHeads[printer]);
        }

        // A redirected row's preview must use the PICKED spool's remaining, or a
        // near-empty target previews green and its clamp surprises the user.
        function setRowRemaining(card, line, remaining) {
            const inp = card.querySelector(`.fcc-cr-grams[data-sid="${CSS.escape(String(line))}"]`);
            if (!inp) return;
            const known = remaining !== '' && remaining != null && Number.isFinite(Number(remaining));
            inp.dataset.remaining = known ? String(remaining) : '';
            if (known) inp.max = fmt(Number(remaining)); else inp.removeAttribute('max');
            updatePreview(inp);
        }

        function updatePreview(input) {
            const sid = input.dataset.sid;
            const g = parseFloat(input.value);
            const prev = overlay.querySelector(`.fcc-cr-preview[data-sid="${sid}"]`);
            if (!prev) return;
            if (Number.isNaN(g)) { prev.textContent = '→ —'; prev.style.color = '#9aa'; return; }
            // 43.1: no known capacity, so no remaining to preview.
            if (input.dataset.remaining === '') { prev.textContent = '→ ?'; prev.style.color = '#9aa'; return; }
            const rem = parseFloat(input.dataset.remaining) || 0;
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
        // 43.3: "Another spool by #ID…" reveals the #id field; a typed id is
        // looked up so the user sees what it is before Apply.
        overlay.addEventListener('change', async (e) => {
            const t = e.target;
            const card = t.closest && t.closest('.fcc-cr-card');
            if (!card || !t.classList) return;
            const line = t.dataset.line;
            const other = card.querySelector(`.fcc-cr-other[data-line="${CSS.escape(String(line))}"]`);
            const info = card.querySelector(`.fcc-cr-other-info[data-line="${CSS.escape(String(line))}"]`);
            if (t.classList.contains('fcc-cr-pick')) {
                const want = t.value === 'other';
                // No focus move: arrow keys on a closed <select> fire `change` on
                // every step, and focus jumping to the #id box mid-way is a trap.
                if (other) other.style.display = want ? '' : 'none';
                if (info && !want) info.textContent = '';
                const opt = t.selectedOptions && t.selectedOptions[0];
                const gramsInp = card.querySelector(`.fcc-cr-grams[data-sid="${CSS.escape(String(line))}"]`);
                if (gramsInp) {
                    if (t.value === t.dataset.own) setRowRemaining(card, line, gramsInp.dataset.ownRemaining);
                    else if (want) setRowRemaining(card, line, '');
                    else setRowRemaining(card, line, opt && opt.dataset.remaining !== undefined ? opt.dataset.remaining : '');
                }
            } else if (t.classList.contains('fcc-cr-other') && info) {
                const v = String(t.value || '').trim().replace(/^#/, '');
                const id = /^\d+$/.test(v) ? parseInt(v, 10) : NaN;
                if (!Number.isFinite(id) || id <= 0) { info.textContent = v ? `"${v}" isn't a spool #id` : ''; return; }
                info.textContent = '…';
                try {
                    // /api/spools/<id> answers {success, data: spool}; a missing id
                    // answers 404 (or Spoolman's {message} as data, with no id).
                    const r = await fetch(`/api/spools/${id}`);
                    const j = r.ok ? await r.json() : null;
                    const s = j && j.success !== false ? j.data : null;
                    if (!s || s.id == null) { info.textContent = `#${id} not found`; return; }
                    const name = (s.filament && s.filament.name) || s.display || '';
                    info.textContent = s.archived
                        ? `#${id} ${name} is archived — pick another spool`
                        : `#${id} ${name}${s.location ? ` (${s.location})` : ''}`;
                    setRowRemaining(card, line, s.remaining_weight == null ? '' : s.remaining_weight);
                } catch (err) {
                    info.textContent = `couldn't look up #${id}`;
                }
            }
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
                // 43.3: explicit picks become `charges`; a card whose rows all keep
                // their own spool still sends the old `updates` shape.
                const payload = { printer_name: printer, job_id: job };
                if (card.dataset.kind === 'no_spool') {
                    const charges = [];
                    let noId = null;
                    card.querySelectorAll('.fcc-cr-pickline').forEach((ln) => {
                        const line = ln.dataset.line;
                        const sid = pickedSid(card, line);
                        const sel = ln.querySelector('.fcc-cr-pick');
                        // "Another spool by #ID…" with no valid #id was skipped, and
                        // the Apply then used up the whole review without it.
                        if (sel && sel.value === 'other' && sid == null) { noId = line; return; }
                        const g = parseFloat((ln.querySelector('.fcc-cr-pgrams') || {}).value);
                        if (sid && !Number.isNaN(g) && g > 0) charges.push({ position: Number(line), sid, grams: g });
                    });
                    if (noId != null) {
                        toast(`Type the #id of the spool T${noId} used (or pick one).`, 'warning', 7000);
                        return;
                    }
                    if (!charges.length) {
                        toast('Pick the spool this print used (or type its #id) first.', 'warning', 7000);
                        return;
                    }
                    payload.charges = charges;
                } else {
                    const updates = {};
                    const charges = [];
                    let redirected = false;
                    let missing = false;
                    card.querySelectorAll('.fcc-cr-grams').forEach((inp) => {
                        const own = inp.dataset.sid;
                        const g = parseFloat(inp.value);
                        const sid = card.querySelector(`.fcc-cr-pick[data-line="${CSS.escape(own)}"]`)
                            ? pickedSid(card, own) : Number(own);
                        if (sid == null) { missing = true; return; }
                        if (String(sid) !== String(own)) redirected = true;
                        if (!Number.isNaN(g) && g > 0) {
                            updates[own] = g;
                            charges.push({ row: Number(own), sid, grams: g });
                        }
                    });
                    if (missing) {
                        toast('Type the #id of the spool to charge (or pick one).', 'warning', 7000);
                        return;
                    }
                    if (redirected) payload.charges = charges; else payload.updates = updates;
                }
                e.target.disabled = true;
                try {
                    const r = await fetch('/api/cancel_deduct/confirm', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    const d = await r.json();
                    if (d.status === 'confirmed') {
                        toast(`Deducted from ${(d.applied || []).length} spool(s).`, 'success');
                        // Partial-bind / clamp shortfall (no_spool re-resolve path): part of the
                        // computed usage couldn't be applied — surface it AT THE OVERLAY, not only
                        // in the Activity Log, so the user knows to weigh the still-short spool.
                        if (Number(d.shortfall_g) > 0.05) toast(`${fmtG(d.shortfall_g)}g couldn't be applied — weigh that spool to true up.`, 'warning', 7000);
                        if ((d.errors || []).length) toast(`${d.errors.length} spool(s) failed — check the log.`, 'error', 7000);
                        card.remove(); updateCount(); refreshBadge(); closeIfEmpty();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                    } else if (d.status === 'already_handled') {
                        toast('Already handled elsewhere.', 'info');
                        card.remove(); updateCount(); refreshBadge(); closeIfEmpty();
                    } else if (d.status === 'still_no_spool' || d.status === 'manual_only') {
                        // Not applied, but the review is kept server-side — LEAVE the
                        // card so the user can bind a spool / weigh, then retry Apply.
                        e.target.disabled = false;
                        toast(d.msg || 'Not applied — still no spool bound.', 'warning', 7000);
                    } else {
                        e.target.disabled = false;
                        const why = d.msg || ((d.errors || [])[0] || {}).error;
                        toast(why || 'Confirm failed — check the log.', 'error', 7000);
                        // Writes that failed leave a reshaped review: show what it holds now.
                        if ((d.errors || []).length) await rerenderCard(card);
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
