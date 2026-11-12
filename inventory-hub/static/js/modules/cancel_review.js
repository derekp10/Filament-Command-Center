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

    // Where FCC read the heads a card names, in words (hotfix 2026-11-11). The
    // server writes them on every card it builds from a read of the heads
    // (`heads_words`, from print_deduct._HEADS_WORDS, the one map its notes use
    // too), so the card and its notes say the same. A card from before carries
    // none: its heads were read when FCC logged the print.
    function headsWords(rec) {
        return Object.assign({ end: 'when FCC logged the print' }, (rec && rec.heads_words) || {});
    }
    function capFirst(s) {
        const t = String(s || '');
        return t.charAt(0).toUpperCase() + t.slice(1);
    }
    // A note under a line or a row, in a named size: what FCC saw on that head.
    function noteHtml(cls, color, text, icon) {
        if (!text) return '';
        return `<div class="${cls}" style="flex-basis:100%;color:${color};font-size:var(--fcc-fs-small);line-height:1.4;">${icon || ''}${esc(text)}</div>`;
    }

    // ----- Scope B (hotfix 2026-11-11): a head's spools as a set -------------
    // A head whose spool changed during the print shows every spool it had, under
    // one header. Split at the swaps FCC recorded, each is a row pre-filled with
    // its own stretch of the print ("start → 19%, ran out"); a head FCC couldn't
    // split, or saw no swap on, gives each spool its own empty grams box.
    function pctWords(f) {
        const n = Number(f);
        return Number.isFinite(n) ? `${Math.round(Math.max(0, Math.min(1, n)) * 100)}%` : '?';
    }
    // A split row's stretch of the print: `from` / `to` are the cuts, null for
    // the print's start and its end.
    function segmentHtml(segs) {
        if (!Array.isArray(segs) || !segs.length) return '';
        const parts = segs.map((sg) => {
            const from = sg.from == null ? 'start' : pctWords(sg.from);
            const to = sg.to == null ? 'end' : pctWords(sg.to);
            const out = sg.runout
                ? `, <span class="fcc-cr-seg-out" style="color:#ff8a65;font-weight:bold;">ran out</span>`
                : '';
            return `<span style="white-space:nowrap;">${esc(from)} → ${esc(to)}${out}</span>`;
        });
        return `<span class="fcc-cr-seg" title="The stretch of the print this spool printed, from the swaps FCC recorded"
                      style="margin-left:6px;color:#9aa;font-size:var(--fcc-fs-small);">${parts.join('; ')}</span>`;
    }
    // A set's count of the grams still to place, as its boxes are filled in.
    function setLeftWords(total, placed) {
        const t = fmtG(total);
        const p = Number(placed) || 0;
        if (p <= 0) return `${t} g to split`;
        const d = Math.round((Number(total) - p) * 100) / 100;
        if (d === 0) return `All ${t} g placed`;
        if (d > 0) return `${fmtG(d)} g of ${t} g still to place`;
        return `${fmtG(-d)} g more than the ${t} g FCC computed`;
    }
    function setBoxHtml(pos, toolhead, n, extra, inner, cls) {
        const where = toolhead ? `T${esc(pos)} · ${esc(toolhead)}` : `T${esc(pos)}`;
        return `
            <div class="fcc-cr-set ${cls}" data-pos="${esc(pos)}"
                 style="margin:8px 0 4px;padding:2px 0 0 10px;border-left:3px solid #5aa0d0;">
                <div class="fcc-cr-set-head"
                     style="display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px;padding:2px 0;
                            color:#e8e8e8;font-weight:bold;font-size:var(--fcc-fs-row);">
                    <span>${where} had ${esc(n)} spools this print</span>${extra || ''}
                </div>
                ${inner}
            </div>`;
    }
    // The order a split head's rows printed in: the start spool first.
    function firstCut(s) {
        const seg = Array.isArray(s.segments) && s.segments.length ? s.segments[0] : null;
        if (!seg) return 0;
        return seg.from == null ? -1 : (Number(seg.from) || 0);
    }
    // A card's rows: those of one head split at its recorded swaps sit together as
    // a set (a card from before the sets has no segments: grouped all the same).
    function rowsHtml(rec) {
        const spools = rec.spools || [];
        const split = {};
        spools.forEach((s) => {
            if (!s || !s.auto_split) return;
            const k = String(s.position);
            (split[k] = split[k] || []).push(s);
        });
        const drawn = new Set();
        return spools.map((s) => {
            const k = String(s && s.position);
            const set = s && s.auto_split ? split[k] : null;
            if (!set || set.length < 2) return spoolRowHtml(s, rec);
            if (drawn.has(k)) return '';
            drawn.add(k);
            const ordered = set.slice().sort((a, b) => firstCut(a) - firstCut(b));
            const sub = `<span class="fcc-cr-set-sub" style="font-weight:normal;color:#9aa;font-size:var(--fcc-fs-small);">split at the swaps FCC recorded</span>`;
            return setBoxHtml(k, set[0].toolhead, set.length, sub,
                ordered.map((x) => spoolRowHtml(x, rec)).join(''), 'fcc-cr-splitset');
        }).join('');
    }
    // One spool of a held set: its own empty grams box, and a picker on that spool
    // (it can still be pointed at another). `lineCls` makes it the card's ordinary
    // uncharged line (fcc-cr-unline, or fcc-cr-pickline on a no_spool card), so
    // Apply charges it by head and spool.
    function heldSetLineHtml(pos, e, lineCls, atEnd, words) {
        const line = `set:${pos}:${e.sid}`;
        const swatch = e.color && window.makeSwatchHtml
            ? window.makeSwatchHtml(e.color, 'longitudinal',
                { size: 16, borderColor: 'rgba(255,255,255,0.5)', marginRight: 0 })
            : '';
        const when = words[e.when] || words.end;
        const left = e.remaining == null ? '' : ` · ${fmt(e.remaining)}g left`;
        return `
            <div class="${lineCls} fcc-cr-setline" data-pos="${esc(pos)}" data-line="${esc(line)}" data-sid="${esc(e.sid)}"
                 style="display:flex;align-items:center;gap:8px;justify-content:space-between;flex-wrap:wrap;
                        padding:6px 0;border-bottom:1px solid #2b2c30;">
                <div style="min-width:0;flex:1;">
                    ${swatch}
                    <span style="color:#eee;">${esc(e.display || '#' + e.sid)}</span>
                    <span style="color:#9aa;font-size:var(--fcc-fs-small);">(${esc(when)}${esc(left)})</span>
                </div>
                <div class="input-group input-group-sm" style="width:132px;flex:none;">
                    <input type="number" class="fcc-cr-pgrams form-control bg-dark text-white border-secondary"
                           data-line="${esc(line)}" value="" step="0.01" min="0" autocomplete="off"
                           aria-label="Grams from spool #${esc(e.sid)}" style="font-size:1.05rem;" />
                    <span class="input-group-text bg-dark text-light border-secondary">g</span>
                </div>
                <div style="flex-basis:100%;display:flex;align-items:center;gap:6px;padding-left:24px;
                            color:#9aa;font-size:var(--fcc-fs-small);">
                    charge to: ${pickSelectHtml(line, e.sid, `this spool (#${e.sid})`, atEnd, words)}
                </div>
            </div>`;
    }
    // A held head shown as a set (the record's `unresolved_sets`), or '' when the
    // line has none: the card draws its single held line instead.
    function heldSetHtml(rec, pos, grams, lineCls, atEnd, words, notes) {
        const entries = (((rec.unresolved_sets || {})[pos]) || []).filter((e) => e && e.sid != null);
        if (entries.length < 2) return '';
        const head = atEnd.find((h) => String(h.position) === String(pos) && !h.when)
            || atEnd.find((h) => String(h.position) === String(pos));
        const left = `<span class="fcc-cr-set-left" data-total="${esc(fmtG(grams))}"
                            style="font-weight:normal;color:#e6c074;font-size:var(--fcc-fs-small);">${esc(setLeftWords(grams, 0))}</span>`;
        const lines = entries.map((e) => heldSetLineHtml(pos, e, lineCls, atEnd, words)).join('');
        return setBoxHtml(pos, head && head.toolhead, entries.length, left,
            lines + noteHtml('fcc-cr-line-note', '#e6c074', notes[pos]), 'fcc-cr-heldset');
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

    // ----- Scope D (hotfix 2026-11-11): the picker reads scans and lists the
    // scan buffer. Derek: "we have to manually key in the id on the spool, and
    // scanning it just inputs the ID:XX into the text box with an enter.
    // Scanning support might be a good idea here, as well as possibly listing
    // spools in the current buffer."
    //
    // What the "#ID" box holds, read as a spool: its number typed (42, #42) or
    // its label scanned (ID:42, or SPL:42), in any letter case, the spaces
    // around it ignored. A label read twice, or a key left in front of one, reads
    // as its last label. `why` says in plain words what it can't read. The
    // dashboard's scan accumulator leaves a text box's keys alone, so a scan
    // typed into the box reaches only the box.
    const BOX_HINT = "Type the spool's number, or scan its label.";
    function readSpoolBox(text) {
        const raw = String(text == null ? '' : text).trim();
        if (!raw) return { sid: null, why: '' };
        const m = /^#?\s*(\d+)$/.exec(raw) || /(?:ID|SPL)\s*:\s*(\d+)$/i.exec(raw);
        if (m) {
            const n = parseInt(m[1], 10);
            return n > 0 ? { sid: n, why: '' } : { sid: null, why: "There's no spool #0." };
        }
        const shown = raw.length > 24 ? `${raw.slice(0, 23)}…` : raw;
        if (/^LOC\s*:/i.test(raw)) return { sid: null, why: `"${shown}" is a location's label, not a spool's.` };
        if (/^FIL\s*:/i.test(raw)) return { sid: null, why: `"${shown}" is a filament's label, not a spool's.` };
        return { sid: null, why: `"${shown}" isn't a spool's number or label.` };
    }
    // The box's info line: what the box names, or why it names nothing (amber).
    function setBoxInfo(info, text, warn) {
        info.textContent = text || '';
        info.style.color = warn ? '#e6c074' : '#9aa';
    }
    // An Apply over a box it can't read says why on the card too: its toast is
    // drawn under the overlay.
    function sayBoxUnread(card, line) {
        const inp = card.querySelector(`.fcc-cr-other[data-line="${CSS.escape(String(line))}"]`);
        const info = card.querySelector(`.fcc-cr-other-info[data-line="${CSS.escape(String(line))}"]`);
        if (info) setBoxInfo(info, readSpoolBox(inp && inp.value).why || BOX_HINT, true);
    }

    // The spools in the scan buffer (state.heldSpools: scanned on the dashboard,
    // before the review opened or while it is open), read when a picker is drawn
    // or opened, never kept.
    function bufferSpools() {
        const st = (typeof state !== 'undefined') ? state : window.state;
        const held = st && Array.isArray(st.heldSpools) ? st.heldSpools : [];
        const seen = new Set();
        return held.filter((s) => {
            const sid = s && s.id != null ? String(s.id) : '';
            if (!/^\d+$/.test(sid) || Number(sid) <= 0 || seen.has(sid)) return false;
            seen.add(sid);
            return true;
        });
    }
    // A buffer spool as an option: its number and name, that it is archived (a
    // picked spool is charged what it has on record and stays archived), and its
    // grams left when known.
    function bufferOption(s) {
        const sid = String(s.id);
        const disp = String(s.display || '').trim();
        const named = disp.startsWith(`#${sid}`) && !/^\d/.test(disp.slice(sid.length + 1));
        const name = named ? disp : `#${sid}${disp ? ' ' + disp : ''}`;
        const g = s.remaining_weight;
        const known = g != null && g !== '' && Number.isFinite(Number(g));
        const bits = [];
        if (s.archived) bits.push('archived');
        if (known) bits.push(`${fmt(g)}g left`);
        return { value: sid, text: bits.length ? `${name} (${bits.join(', ')})` : name, remaining: known ? String(Number(g)) : '' };
    }
    // Every buffer spool the picker doesn't list already (`listed`: its own, the
    // heads' spools).
    function bufferOptions(listed) {
        return bufferSpools().filter((s) => !listed.has(String(s.id))).map(bufferOption);
    }
    const BUFFER_GROUP = 'In the scan buffer';
    function bufferGroupHtml(listed) {
        const opts = bufferOptions(listed);
        if (!opts.length) return '';
        return `<optgroup label="${esc(BUFFER_GROUP)}" class="fcc-cr-buffer">${opts.map((o) =>
            `<option value="${esc(o.value)}" data-remaining="${esc(o.remaining)}">${esc(o.text)}</option>`).join('')}</optgroup>`;
    }
    // Draws a picker's "In the scan buffer" group again from the buffer as it is
    // now, leaving out a spool the picker lists elsewhere (on a head drawn since,
    // say). A spool picked from it stays picked, and offered, after it leaves the
    // buffer: a pick never changes by itself. Answers whether it drew anything.
    function refreshBufferGroup(sel) {
        const old = sel.querySelector('.fcc-cr-buffer');
        const listed = new Set();
        Array.from(sel.querySelectorAll('option')).forEach((o) => {
            if (old && old.contains(o)) return;
            if (o.value && o.value !== 'other') listed.add(o.value);
        });
        const want = bufferOptions(listed);
        const pickedOpt = sel.selectedOptions && sel.selectedOptions[0];
        const picked = pickedOpt && old && old.contains(pickedOpt) ? pickedOpt.value : null;
        if (picked != null && !listed.has(picked) && !want.some((o) => o.value === picked)) {
            want.push({ value: picked, text: pickedOpt.textContent, remaining: pickedOpt.dataset.remaining || '' });
        }
        const was = old ? Array.from(old.querySelectorAll('option')) : [];
        const same = was.length === want.length && was.every((o, i) => o.value === want[i].value
            && o.textContent === want[i].text && (o.dataset.remaining || '') === want[i].remaining);
        if (same) return false;
        let group = null;
        if (want.length) {
            group = document.createElement('optgroup');
            group.setAttribute('label', BUFFER_GROUP);
            group.className = 'fcc-cr-buffer';
            want.forEach((o) => {
                const opt = document.createElement('option');
                opt.value = o.value;
                opt.dataset.remaining = o.remaining;
                opt.textContent = o.text;
                group.appendChild(opt);
            });
        }
        if (old) old.remove();
        if (group) sel.insertBefore(group, sel.querySelector('option[value="other"]'));
        if (picked != null) sel.value = picked;
        return true;
    }

    // `own` = the line's default spool (a row's sid), or null for a no_spool line.
    // `atEnd` is the heads the review recorded, and `words` (headsWords) say
    // when they were read: when the print ended for a card built from the
    // print-end read, else when FCC logged the print. A spool FCC's own record
    // names on a head during the print (`when`: start, during) has its own group,
    // and a head that held two spools at the end offers both (`sids`). Then the
    // scan buffer's spools (scope D), and any spool by its number or label.
    function pickSelectHtml(line, own, ownLabel, atEnd, words) {
        const w = words || headsWords(null);
        const first = own != null
            ? `<option value="${esc(own)}" selected>${esc(ownLabel)}</option>`
            : `<option value="" selected>— pick the spool it used —</option>`;
        const groups = { end: [], start: [], during: [] };
        const listed = new Set(own != null ? [String(own)] : []);
        (atEnd || []).forEach((h) => {
            const when = h.when === 'start' || h.when === 'during' ? h.when : 'end';
            const ids = h.sid != null ? [h.sid] : (Array.isArray(h.sids) ? h.sids : []);
            ids.forEach((sid) => {
                if (sid != null) listed.add(String(sid));
                if (sid == null || String(sid) === String(own)) return;
                // 43.2: a spool that ran out is still offered (it is charged what it
                // has left, 0 g for an empty one, and stays archived), but says so.
                groups[when].push(`<option value="${esc(sid)}">#${esc(sid)} — on ${esc(h.toolhead)} ${esc(w[when] || w.end)}${h.archived ? ' (ran out, archived)' : ''}</option>`);
            });
        });
        const group = (when, cls) => groups[when].length
            ? `<optgroup label="${esc(capFirst(w[when] || w.end))}" class="${cls}">${groups[when].join('')}</optgroup>`
            : '';
        // The #id box is text, not number: arrow keys on a number box step it
        // (an empty one to 1), and charging spool #1 by accident is a real write.
        // It takes a scanned label too (scope D, readSpoolBox).
        return `
            <select class="fcc-cr-pick form-select form-select-sm bg-dark text-light border-secondary"
                    data-line="${esc(line)}" data-own="${own == null ? '' : esc(own)}"
                    style="max-width:330px;font-size:0.92rem;">
                ${first}
                ${group('end', 'fcc-cr-ended')}${group('start', 'fcc-cr-started')}${group('during', 'fcc-cr-during')}
                ${bufferGroupHtml(listed)}
                <option value="other">Another spool by #ID…</option>
            </select>
            <input type="text" inputmode="numeric" class="fcc-cr-other form-control form-control-sm bg-dark text-white border-secondary"
                   data-line="${esc(line)}" placeholder="#id" autocomplete="off"
                   title="${esc(BOX_HINT)}" aria-label="The spool's number, or its label"
                   style="display:none;width:96px;font-size:0.92rem;" />
            <span class="fcc-cr-other-info" data-line="${esc(line)}" aria-live="polite"
                  style="color:#9aa;font-size:var(--fcc-fs-small);"></span>`;
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
            // Before the scan buffer's group (scope D), which then leaves these out.
            if (group.children.length) {
                sel.insertBefore(group, sel.querySelector('.fcc-cr-buffer') || sel.querySelector('option[value="other"]'));
            }
        });
    }

    // The spool a line will charge: the picker's choice, or what the #id box
    // names (a number or a scanned label, scope D).
    function pickedSid(card, line) {
        const sel = card.querySelector(`.fcc-cr-pick[data-line="${CSS.escape(line)}"]`);
        if (!sel) return null;
        if (sel.value === 'other') {
            const inp = card.querySelector(`.fcc-cr-other[data-line="${CSS.escape(line)}"]`);
            return readSpoolBox(inp && inp.value).sid;
        }
        const n = parseInt(sel.value, 10);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    function spoolRowHtml(s, rec) {
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
        // Scope B: a split row says its stretch of the print, a run-out included,
        // so its "ran out" badge would say it twice.
        const seg = segmentHtml(s.segments);
        const isRunout = !!s.runout && !seg;
        const ambBorder = amb ? 'border-left:3px solid #ffae42;padding-left:6px;' : '';
        const ambBadge = amb
            ? `<span title="This toolhead has more than one spool assigned — FCC can't tell which is loaded, so these grams weren't auto-deducted. Pick the real amount per spool."
                     style="margin-left:6px;font-size:var(--fcc-fs-label);font-weight:bold;color:#ffae42;
                            border:1px solid #ffae42;border-radius:4px;padding:0 4px;white-space:nowrap;">⚠️ ambiguous</span>`
            : '';
        // 43.1: a spool with no known capacity (neither it nor its filament has a
        // weight) reports remaining as null — say so rather than "0g left".
        const known = s.remaining_before != null;
        // 43.2: a write Spoolman reported as failed but may have landed. Apply
        // checks the spool's weight first, so it is never charged twice.
        const unconfirmed = s.unconfirmed_write
            ? `<span title="Spoolman reported this write as failed and FCC couldn't re-read the spool. Apply checks whether it landed first, so it is never charged twice."
                     style="margin-left:6px;font-size:var(--fcc-fs-label);font-weight:bold;color:#ffae42;
                            border:1px solid #ffae42;border-radius:4px;padding:0 4px;white-space:nowrap;">⚠️ unconfirmed write</span>`
            : '';
        return `
            <div class="fcc-cr-row" data-sid="${s.sid}"
                 style="display:flex;align-items:center;gap:8px;justify-content:space-between;flex-wrap:wrap;
                        padding:6px 0;border-bottom:1px solid #2b2c30;${ambBorder}">
                <div style="min-width:0;flex:1;">
                    ${swatch}
                    <span style="color:#eee;">${esc(s.display)}</span>${seg}${ambBadge}${unconfirmed}${isRunout ? `<span title="Ran out mid-print (sensor tripped) — charged its own segment up to the swap, plus the sensor-to-nozzle remnant when a per-printer path value is configured."
                     style="margin-left:6px;font-size:var(--fcc-fs-label);font-weight:bold;color:#ff8a65;
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
                    charge to: ${pickSelectHtml(s.sid, s.sid, `this spool (#${s.sid})`, rec && rec.heads_at_end, headsWords(rec))}
                </div>
                ${noteHtml('fcc-cr-row-note', '#7ec8ff', ((rec && rec.row_notes) || {})[String(s.sid)], 'ℹ️ ')}
            </div>`;
    }

    // Group 43.3: a no_spool review has grams per tool but no spool. One line per
    // tool the print used: its grams (nudgeable) and the picker.
    function noSpoolLinesHtml(rec) {
        const usage = rec.usage_map || {};
        const atEnd = Array.isArray(rec.heads_at_end) ? rec.heads_at_end : [];
        const words = headsWords(rec);
        const notes = rec.unresolved_notes || {};
        return Object.keys(usage).sort((a, b) => Number(a) - Number(b)).map((pos) => {
            // Scope B: a head whose spool changed during the print is a set.
            const set = heldSetHtml(rec, pos, usage[pos], 'fcc-cr-pickline', atEnd, words, notes);
            if (set) return set;
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
                    ${pickSelectHtml(pos, null, '', atEnd, words)}
                    ${noteHtml('fcc-cr-line-note', '#e6c074', notes[pos])}
                </div>`;
        }).join('');
    }

    // Group 43.4: the heads a partial review's print used that no row charges:
    // emptied mid-print, or (hotfix 2026-11-11) held because FCC can't vouch for
    // the spool on it, each with a note saying why. Each gets a picker like a
    // no_spool line; one left unpicked is reported as uncharged at Apply instead
    // of vanishing.
    function unresolvedLinesHtml(rec) {
        const un = rec.unresolved_usage || {};
        const keys = Object.keys(un).sort((a, b) => Number(a) - Number(b));
        if (!keys.length) return '';
        const atEnd = Array.isArray(rec.heads_at_end) ? rec.heads_at_end : [];
        const words = headsWords(rec);
        const notes = rec.unresolved_notes || {};
        const which = keys.length === 1 ? 'this head' : 'these heads';
        // "When the print ended" only where the heads were read then: each held
        // line says itself what FCC saw on it.
        const lead = keys.some((pos) => notes[pos])
            ? `⚠️ FCC isn't sure which spool printed on ${which}. Pick the spool it used, or leave it:
               its grams are then logged as uncharged.`
            : `⚠️ No spool was loaded on ${which} ${esc(words.end)}. Pick the spool it used, or leave it:
               its grams are then logged as uncharged.`;
        return `
            <div class="fcc-cr-unresolved-note" style="margin-top:8px;color:#e6c074;font-size:0.92rem;">
                ${lead}
            </div>` + keys.map((pos) => {
            // Scope B: a head whose spool changed during the print is a set.
            const set = heldSetHtml(rec, pos, un[pos], 'fcc-cr-unline', atEnd, words, notes);
            if (set) return set;
            const head = atEnd.find((h) => String(h.position) === String(pos));
            const where = head ? `T${esc(pos)} · ${esc(head.toolhead)}` : `T${esc(pos)}`;
            const line = `pos:${pos}`;
            return `
                <div class="fcc-cr-unline" data-pos="${esc(pos)}" data-line="${esc(line)}"
                     style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 0;border-bottom:1px solid #2b2c30;">
                    <span style="color:#eee;min-width:120px;">${where} used</span>
                    <div class="input-group input-group-sm" style="width:120px;flex:none;">
                        <input type="number" class="fcc-cr-pgrams form-control bg-dark text-white border-secondary"
                               data-line="${esc(line)}" value="${fmtG(un[pos])}" step="0.01" min="0"
                               autocomplete="off" style="font-size:1.05rem;" />
                        <span class="input-group-text bg-dark text-light border-secondary">g</span>
                    </div>
                    <span style="color:#9aa;">→</span>
                    ${pickSelectHtml(line, null, '', atEnd, words)}
                    ${noteHtml('fcc-cr-line-note', '#e6c074', notes[pos])}
                </div>`;
        }).join('');
    }

    // Group 43.2: grams an automatic deduct couldn't charge (a spool ran out
    // mid-print, a head had no spool, a write failed). Each head's line says why
    // and picks the spool that really took the rest: after a SpoolJoin runout,
    // the joined spool. The run-out spool is offered but not pre-picked: it is
    // archived, and charging it takes only what it has left (0 g when empty).
    // Whatever a pick can't take stays on the card.
    // FCC sees the spool's record, not the spool: "ran out" is the record hitting
    // 0 g, which may also mean the record was off (Derek: small spools often are).
    function shortfallReason(c, pos) {
        const head = c.toolhead || `T${pos}`;
        if (c.why === 'ran_out') return `#${c.sid}'s record hit 0 g on ${head}${c.archived ? ' (archived)' : ''}`;
        if (c.why === 'no_spool') return `no spool was loaded on ${head}`;
        if (c.why === 'two_spools') {
            const both = (c.sids || []).map((s) => `#${s}`).join(' and ');
            return `${head} had two spools${both ? ` (${both})` : ''}, so FCC charged neither`;
        }
        return c.sid != null ? `#${c.sid} on ${head} wasn't charged (Spoolman didn't answer)` : `${head} wasn't charged`;
    }

    function shortfallLinesHtml(rec) {
        const un = rec.unresolved_usage || {};
        const causes = rec.shortfall_causes || {};
        const atEnd = Array.isArray(rec.heads_at_end) ? rec.heads_at_end : [];
        const words = headsWords(rec);
        return Object.keys(un).sort((a, b) => Number(a) - Number(b)).map((pos) => {
            const c = causes[pos] || {};
            const head = c.toolhead || (atEnd.find((h) => String(h.position) === String(pos)) || {}).toolhead;
            const where = head ? `T${esc(pos)} · ${esc(head)}` : `T${esc(pos)}`;
            const own = (c.sid != null && !c.archived) ? c.sid : null;
            const ownLabel = own != null ? `#${own} — on ${head || 'T' + pos} ${words.end}` : '';
            const line = `pos:${pos}`;
            return `
                <div class="fcc-cr-unline fcc-cr-shortline" data-pos="${esc(pos)}" data-line="${esc(line)}"
                     style="padding:6px 0;border-bottom:1px solid #2b2c30;">
                    <div class="fcc-cr-why" style="color:#e6c074;font-size:0.9rem;margin-bottom:4px;">${esc(shortfallReason(c, pos))}</div>
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span style="color:#eee;min-width:120px;">${where} uncharged</span>
                        <div class="input-group input-group-sm" style="width:120px;flex:none;">
                            <input type="number" class="fcc-cr-pgrams form-control bg-dark text-white border-secondary"
                                   data-line="${esc(line)}" value="${fmtG(un[pos])}" step="0.01" min="0"
                                   autocomplete="off" style="font-size:1.05rem;" />
                            <span class="input-group-text bg-dark text-light border-secondary">g</span>
                        </div>
                        <span style="color:#9aa;">→</span>
                        ${pickSelectHtml(line, own, ownLabel, atEnd, words)}
                    </div>
                </div>`;
        }).join('');
    }

    function shortfallCardHtml(rec) {
        const total = fmtG(rec.total_grams);
        // A failed write's retry keeps its row (the picked spool) on the card.
        const rows = (rec.spools || []).map((s) => spoolRowHtml(s, rec)).join('');
        return `
            <div class="fcc-cr-card" data-printer="${esc(rec.printer_name)}" data-job="${esc(rec.job_id)}"
                 data-kind="shortfall" data-ambiguous="0" data-rev="${esc(rec.rev == null ? 0 : rec.rev)}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div style="font-weight:bold;color:#ffd27a;">⚖️ ${esc(rec.printer_name)} — ${total}g went to no spool</div>
                    <div style="color:#9aa;font-size:0.92rem;">${total}g uncharged</div>
                </div>
                <div style="color:#9aa;font-size:0.9rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                <div style="color:#e6c074;font-size:0.95rem;margin-bottom:10px;line-height:1.45;
                            background:#221d12;border:1px solid #3a2f17;border-radius:4px;padding:9px 11px;">
                    FCC charged what it could for this print, but <b>${total}g</b> went to no spool. If the
                    printer carried on from another spool (a <b>joined spool</b>), or you know where the
                    filament came from, <b>pick that spool</b> and <b>Apply</b>. A spool whose record is at
                    0 g takes nothing, and whatever a spool can't take stays on this card. If a record was
                    off (the spool still has filament), weigh that spool. Or <b>Discard</b> if you've already
                    weighed them.
                </div>
                ${rows}
                ${shortfallLinesHtml(rec)}
                <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px;">
                    <button type="button" class="btn btn-sm btn-outline-secondary fcc-cr-discard"
                            data-armed="0"
                            title="Permanently drop this review — these grams stay uncharged">🗑️ Discard</button>
                    <button type="button" class="btn btn-sm btn-success fw-bold fcc-cr-confirm">Apply to the picked spool(s)</button>
                </div>
            </div>`;
    }

    // Why a progress_unknown review couldn't measure its print (the record's
    // `unmeasured_reason`, print_deduct._UNMEASURED_WHY's keys; Group 56.3). A
    // record from before 56.3 has none and was always "replaced".
    function unmeasuredBanner(rec) {
        const weigh = `<b>Weigh the spool</b> and adjust it directly, or <b>Discard</b> this review.`;
        switch (rec.unmeasured_reason) {
            case 'no_footer':
                return `FCC couldn't measure how much filament this print used — <b>its file's
                   filament footer couldn't be read</b> (a file from another slicer, or a damaged
                   one), so nothing was deducted. ${weigh}`;
            case 'empty_footer':
                return `FCC couldn't measure how much filament this print used — <b>its file's
                   filament footer lists no filament</b>, so nothing was deducted. If it really
                   used none, <b>Discard</b> this review; otherwise <b>weigh the spool</b> and adjust
                   it directly.`;
            case 'unreadable_moves':
                return `FCC couldn't measure how much filament this print used — <b>it couldn't
                   read the moves in the print's file</b> (its footer lists filament, but FCC found
                   no extrusion it could count), so nothing was deducted. ${weigh}`;
            case 'no_download':
                return `FCC couldn't measure how much filament this print used — <b>it couldn't
                   download or read the print's file</b> from the printer (it may have been deleted,
                   or stayed locked on the printer's screen), so nothing was deducted. ${weigh}`;
            case 'unsampled':
                return `FCC couldn't measure how much filament this print used — <b>it ended before
                   FCC read its progress</b> (the printer reported none while FCC watched, or FCC
                   restarted during it). ${weigh}`;
            default:
                return `FCC couldn't measure how much filament this print used — it was <b>replaced
                   by a new print before a progress reading</b>. ${weigh}`;
        }
    }

    // Unresolved reviews (2026-06-13): usage couldn't be finalized at print-end.
    //   no_spool         — real grams computed, but NO spool was bound to the
    //                      toolhead. Apply RE-RESOLVES to whatever's bound now.
    //   progress_unknown — its usage is unmeasurable (unmeasuredBanner says why).
    //                      Weigh + adjust, or Discard.
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
        // Hotfix 2026-11-11: a card whose lines carry notes (built from the
        // print-end read) says each line's reason under it, and leads neutrally.
        const words = headsWords(rec);
        const noted = Object.keys(rec.unresolved_notes || {}).length > 0;
        const banner = isNoSpool && noted
            ? `FCC computed this print used <b>${total}g</b>, but isn't sure which spool it came from
               on the heads below. <b>Pick the spool each head used</b>, then <b>Apply</b>. Or
               <b>Discard</b> if you've already trued it up.`
            : isNoSpool
            ? `FCC computed this print used <b>${total}g</b>, but couldn't charge it: <b>no spool was
               loaded</b> on the head it was sliced for ${esc(words.end)} (or Spoolman rejected the write),
               so nothing was deducted. <b>Pick the spool it really used</b> for each tool — a print
               can run on a different head than it was sliced for — then <b>Apply</b>. Or
               <b>Discard</b> if you've already trued it up.`
            : unmeasuredBanner(rec);
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
        if (kind === 'shortfall') return shortfallCardHtml(rec);
        const rows = rowsHtml(rec);
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
        // Hotfix 2026-11-11: built from the print-end read, a changed head that no
        // split covers has no row: it is held below, offering every spool it had.
        const held = spoolChanged && !autoSplit && !!rec.heads_source;
        if (spoolChanged) {
            headerColor = '#ffb74d';
            header = `🔁 ${esc(rec.printer_name)} — spool changed mid-print`;
            banner = held
                ? `🔁 A spool feeding this print was <b>changed mid-print</b> at position(s)
               <b>${esc(changedPos)}</b>, so the slicer total was <b>NOT auto-applied</b>. FCC can't tell
               which spool printed there, so it charges neither by itself: each such head is listed
               below with every spool it had. <b>Pick the spool it used</b> (or weigh them and nudge
               the grams), then <b>Confirm</b>. Or <b>Discard</b>.`
                : autoSplit
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
                ${unresolvedLinesHtml(rec)}
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
                        min-width:min(27.5rem,94vw);max-width:42.5rem;width:94vw;font-size:1rem;
                        box-shadow:0 8px 32px rgba(0,0,0,0.6);">
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:14px 18px;border-bottom:1px solid #444;">
                    <div id="fcc-cr-title" style="font-weight:bold;font-size:1.18rem;">
                        🛑 Print Reviews <span id="fcc-cr-count" style="color:#9aa;font-weight:normal;font-size:0.95rem;"></span>
                    </div>
                    <button type="button" id="fcc-cr-close"
                        style="background:none;border:none;color:#aaa;font-size:1.4rem;line-height:1;cursor:pointer;"
                        aria-label="Close — reviews stay pending"
                        title="Close — every review stays pending for later">×</button>
                </div>
                <div style="padding:8px 18px 4px;color:#bbb;font-size:0.95rem;">
                    Nudge the grams or pick the spools on each card, then press its green button. <b>Closing keeps everything for later</b> — only <b>Discard</b> drops a review.
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
        // here for the badge-poll cadence). A count that changed on the open
        // widget lays its tiles out again. Since the count went onto the info
        // line under the name (2026-10-24) its width moves no tile, so this
        // finds the rows as they were; it costs one measure, and keeps them
        // right whatever the info line comes to hold.
        if (decoratePrinterStatus() && typeof window.balancePrinterStatusRows === 'function') {
            window.balancePrinterStatusRows();
        }
    }
    // Returns whether a count on the open widget's info lines changed.
    function decoratePrinterStatus() {
        const counts = {};
        _lastPending.forEach((r) => { counts[r.printer_name] = (counts[r.printer_name] || 0) + 1; });
        // Add/update/remove one "🛑 N" chip inside `host` for printer `name`.
        // Used on BOTH Print-Status surfaces so a review shows whether the widget
        // is expanded OR minimized. Returns whether it changed anything.
        const apply = (host, name) => {
            let chip = host.querySelector('.fcc-cr-chip');
            const n = counts[name] || 0;
            if (n > 0) {
                if (!chip) {
                    chip = document.createElement('span');
                    chip.className = 'fcc-cr-chip';
                    // Spacing and "never splits" are global.css's .fcc-cr-chip
                    // (the 🛑 and its count on one line, on both surfaces).
                    chip.style.cssText = 'cursor:pointer;font-size:var(--fcc-fs-label);font-weight:bold;color:#ffae42;';
                    chip.title = 'Cancelled-print partial deduct waiting for review — click to review';
                    chip.addEventListener('click', (ev) => { ev.stopPropagation(); openCancelReview(); });
                    host.appendChild(chip);
                }
                const text = `🛑 ${n}`;
                if (chip.textContent === text) return false;
                chip.textContent = text;
                return true;
            }
            if (!chip) return false;
            chip.remove();
            return true;
        };
        // Expanded view: in the printer's count slot on its info line, under
        // its name and after its state badge (Derek, 2026-10-24: "the printer
        // name, then under it, the status and review"). The slot keeps its
        // width with no reviews, so the counts line up down the page. Not
        // inside the name, which ends in "…" when the line is short and would
        // cut the count off, and whose wrapping used to leave the 🛑 on one
        // line and its count on the next. (`data-printer` holds the plain
        // name, attribute-escaped, so it reads back as the record's
        // printer_name, an apostrophe included.)
        let changed = false;
        document.querySelectorAll('.fcc-ps-row[data-printer]').forEach((row) => {
            const host = row.querySelector('.fcc-ps-count') || row.querySelector('.fcc-ps-info')
                || row.querySelector('.fcc-ps-name');
            if (host && apply(host, row.getAttribute('data-printer'))) changed = true;
        });
        // Minimized/collapsed view: onto each printer's group in the header chip
        // strip — the only thing visible when the widget is minimized (Derek
        // 2026-06-12, "in case the activity log isn't always visible").
        document.querySelectorAll('.fcc-ps-header-chips .fcc-ps-printer-group[data-printer]')
            .forEach((grp) => apply(grp, grp.getAttribute('data-printer')));
        return changed;
    }
    async function refreshBadge() {
        applyBadges(await fetchPending());
    }

    // The open review's scan-buffer listener (scope D), so a review opened again
    // over an open one leaves only its own listening.
    let _offBuffer = null;

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
        let offBuffer = null;
        const cleanup = () => { if (offBuffer) offBuffer(); if (handle) handle.cleanup(); refreshBadge(); };
        handle = window.mountOverlay({
            id: OVERLAY_ID,
            content: panelHtml(pending),
            focusGuard: true,
            // The first input of whichever card comes first: a grams box, a
            // no-spool / uncharged line's grams, or its picker (43.2).
            initialFocus: '.fcc-cr-grams, .fcc-cr-pgrams, .fcc-cr-pick',
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

        // Scope D: each picker's "In the scan buffer" group follows the buffer
        // (inv_cmd.js's renderBuffer announces every change) and the heads drawn
        // since, and is drawn again as the picker is opened. A spool picked from
        // the buffer previews its own grams left.
        function refreshPicker(sel) {
            if (!refreshBufferGroup(sel)) return;
            const opt = sel.selectedOptions && sel.selectedOptions[0];
            if (!opt || !opt.closest('.fcc-cr-buffer')) return;
            const card = sel.closest('.fcc-cr-card');
            if (card) setRowRemaining(card, sel.dataset.line, opt.dataset.remaining || '');
        }
        function refreshPickers(scope) {
            scope.querySelectorAll('.fcc-cr-pick').forEach(refreshPicker);
        }
        function withHeads(card, heads) {
            injectHeads(card, heads);
            refreshPickers(card);
        }
        const onBuffer = () => {
            if (!overlay.isConnected) { if (offBuffer) offBuffer(); return; }
            refreshPickers(body);
        };
        if (_offBuffer) _offBuffer();
        document.addEventListener('inventory:buffer-updated', onBuffer);
        offBuffer = () => {
            document.removeEventListener('inventory:buffer-updated', onBuffer);
            if (_offBuffer === offBuffer) _offBuffer = null;
        };
        _offBuffer = offBuffer;
        // A picker being opened (pressed, or reached by the keyboard) shows the
        // buffer as it is now. `focus`, not `focusin`: mountOverlay's focus guard
        // stops every focusin inside the overlay at the document.
        const pickerOpening = (e) => {
            const t = e.target;
            if (t && t.classList && t.classList.contains('fcc-cr-pick')) refreshPicker(t);
        };
        overlay.addEventListener('mousedown', pickerOpening);
        overlay.addEventListener('focus', pickerOpening, true);

        // 43.3: one candidates fetch per printer; the pickers fill in when it lands.
        const liveHeads = {};
        [...new Set(pending.map((r) => r.printer_name))].forEach((printer) => {
            fetchCandidates(printer).then((heads) => {
                liveHeads[printer] = heads;
                body.querySelectorAll('.fcc-cr-card').forEach((card) => {
                    if (card.dataset.printer === printer) withHeads(card, heads);
                });
            });
        });

        // After an Apply that didn't fully land, the server may have reshaped the
        // review (only the failed rows, a redirect's picked spools). Re-render the
        // card from what it stored, so the next Apply names rows the review still
        // has: a stale card's rows are refused as "not in this review".
        // `freshHeads`: re-read the printer's heads first. After an Apply that
        // emptied a spool (43.2), the cached list still offers it with its old
        // "Ng left".
        async function rerenderCard(card, freshHeads) {
            const printer = card.dataset.printer;
            const job = card.dataset.job;
            const rec = (await fetchPending()).find(
                (r) => String(r.printer_name) === printer && String(r.job_id) === job);
            if (!rec) { card.remove(); updateCount(); refreshBadge(); closeIfEmpty(); return; }
            if (freshHeads) liveHeads[printer] = await fetchCandidates(printer);
            const tmp = document.createElement('div');
            tmp.innerHTML = cardHtml(rec).trim();
            const fresh = tmp.firstElementChild;
            card.replaceWith(fresh);
            if (liveHeads[printer]) withHeads(fresh, liveHeads[printer]);
            const first = fresh.querySelector('.fcc-cr-pick, .fcc-cr-grams');
            if (first) { try { first.focus(); } catch (_) { /* noop */ } }
        }

        // 43.2: an Apply that couldn't place every gram opened an uncharged-grams
        // card; show it in this overlay, so the next pick is right there.
        async function showNewCard(printer, job) {
            const rec = (await fetchPending()).find(
                (r) => String(r.printer_name) === String(printer) && String(r.job_id) === String(job));
            if (!rec) return;
            const shown = Array.from(body.querySelectorAll('.fcc-cr-card')).some(
                (c) => c.dataset.printer === String(printer) && c.dataset.job === String(job));
            if (shown) return;
            liveHeads[printer] = await fetchCandidates(printer);
            const tmp = document.createElement('div');
            tmp.innerHTML = cardHtml(rec).trim();
            const fresh = tmp.firstElementChild;
            body.appendChild(fresh);
            withHeads(fresh, liveHeads[printer]);
            updateCount();
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

        // Scope B: a held set's count of the grams still to place follows its boxes.
        function updateSetLeft(input) {
            const box = input.closest && input.closest('.fcc-cr-heldset');
            const out = box && box.querySelector('.fcc-cr-set-left');
            if (!out) return;
            let placed = 0;
            box.querySelectorAll('.fcc-cr-pgrams').forEach((b) => {
                const g = parseFloat(b.value);
                if (g > 0) placed += g;
            });
            out.textContent = setLeftWords(Number(out.dataset.total), placed);
        }

        overlay.addEventListener('input', (e) => {
            if (!e.target.classList) return;
            if (e.target.classList.contains('fcc-cr-grams')) updatePreview(e.target);
            else if (e.target.classList.contains('fcc-cr-pgrams')) updateSetLeft(e.target);
        });

        // 43.3: the spool the #id box names is looked up, so the user sees what
        // it is before Apply. Scope D: the box reads a scanned label as well as a
        // number (readSpoolBox), and only its newest lookup paints, and only while
        // its line is still on "Another spool by #ID…": an older answer never
        // paints over a newer one, nor over a pick made since.
        async function lookUpBox(card, inp, force) {
            const line = inp.dataset.line;
            const info = card.querySelector(`.fcc-cr-other-info[data-line="${CSS.escape(String(line))}"]`);
            if (!info) return;
            const text = String(inp.value || '');
            // The same text read again (a scanner's second Enter, or the blur
            // after an Enter) looks nothing up again.
            if (!force && inp._fccLooked === text) return;
            inp._fccLooked = text;
            const seq = (inp._fccLook = (inp._fccLook || 0) + 1);
            const got = readSpoolBox(text);
            if (got.sid == null) {
                setBoxInfo(info, got.why || BOX_HINT, !!got.why);
                setRowRemaining(card, line, '');
                return;
            }
            const id = got.sid;
            setBoxInfo(info, '…');
            let r = null;
            try {
                // /api/spools/<id> answers {success, data: spool}; a spool it has no
                // record of answers 404 (or Spoolman's {message} as data, with no
                // id), and so does a Spoolman that didn't answer.
                r = await fetch(`/api/spools/${id}`);
            } catch (err) {
                if (inp._fccLook !== seq) return;
                inp._fccLooked = null;              // an Enter tries again
                setBoxInfo(info, `Couldn't look up #${id}: FCC didn't answer.`, true);
                setRowRemaining(card, line, '');
                return;
            }
            let j = null;
            if (r.ok) { try { j = await r.json(); } catch (_) { j = null; } }
            if (inp._fccLook !== seq) return;
            const s = j && j.success !== false ? j.data : null;
            if (!s || s.id == null || Number(s.id) !== id) {
                setBoxInfo(info, `FCC couldn't find spool #${id}.`, true);
                setRowRemaining(card, line, '');
                return;
            }
            const name = (s.filament && s.filament.name) || s.display || '';
            // 43.2 (Derek, 2026-10-13): an archived spool is charged what it
            // still has on record and stays archived; say how much that is.
            const left = s.remaining_weight == null ? '' : `${fmt(s.remaining_weight)}g left, `;
            setBoxInfo(info, s.archived
                ? `#${id} ${name} (archived, ${left}charged what it has, stays archived)`
                : `#${id} ${name}${s.location ? ` (${s.location})` : ''}`);
            setRowRemaining(card, line, s.remaining_weight == null ? '' : s.remaining_weight);
        }

        // 43.3: "Another spool by #ID…" reveals the #id box.
        overlay.addEventListener('change', (e) => {
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
                // Scope D: a lookup on its way paints nothing once the pick moved,
                // and coming back to the box reads what it holds again.
                if (other) { other._fccLook = (other._fccLook || 0) + 1; other._fccLooked = null; }
                const opt = t.selectedOptions && t.selectedOptions[0];
                const gramsInp = card.querySelector(`.fcc-cr-grams[data-sid="${CSS.escape(String(line))}"]`);
                if (gramsInp) {
                    if (t.value === t.dataset.own) setRowRemaining(card, line, gramsInp.dataset.ownRemaining);
                    else if (want) setRowRemaining(card, line, '');
                    else setRowRemaining(card, line, opt && opt.dataset.remaining !== undefined ? opt.dataset.remaining : '');
                }
                if (want && other) lookUpBox(card, other, true);
            } else if (t.classList.contains('fcc-cr-other')) {
                lookUpBox(card, t, false);
            }
        });
        // Scope D: an Enter in the #id box (a scanner ends every label with one,
        // and some send two) reads the box and nothing else: it never applies the
        // card or presses a button, and goes no further. Its text is left
        // selected, so the next scan replaces it instead of joining it. Every
        // other key is the box's own: the arrows move in it, and Escape closes
        // the review as everywhere on it (mountOverlay takes it first).
        overlay.addEventListener('keydown', (e) => {
            const t = e.target;
            if (e.key !== 'Enter' || e.isComposing || !t || !t.classList || !t.classList.contains('fcc-cr-other')) return;
            e.preventDefault();
            e.stopPropagation();
            const card = t.closest('.fcc-cr-card');
            if (card) lookUpBox(card, t, false);
            try { t.select(); } catch (_) { /* noop */ }
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
                        // A set's line (scope B) names its head in data-pos; a
                        // plain line's key is its head.
                        const pos = ln.dataset.pos != null ? ln.dataset.pos : line;
                        const sid = pickedSid(card, line);
                        const sel = ln.querySelector('.fcc-cr-pick');
                        // "Another spool by #ID…" with no valid #id was skipped, and
                        // the Apply then used up the whole review without it.
                        if (sel && sel.value === 'other' && sid == null) { noId = pos; sayBoxUnread(card, line); return; }
                        const g = parseFloat((ln.querySelector('.fcc-cr-pgrams') || {}).value);
                        if (sid && !Number.isNaN(g) && g > 0) charges.push({ position: Number(pos), sid, grams: g });
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
                        if (sid == null) { missing = true; sayBoxUnread(card, own); return; }
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
                    // 43.4: a head that had no spool, picked here, is charged by
                    // position; one left unpicked is reported as uncharged.
                    let unNoId = null;
                    card.querySelectorAll('.fcc-cr-unline').forEach((ln) => {
                        const line = ln.dataset.line;
                        const sel = ln.querySelector('.fcc-cr-pick');
                        const sid = pickedSid(card, line);
                        if (sel && sel.value === 'other' && sid == null) { unNoId = ln.dataset.pos; sayBoxUnread(card, line); return; }
                        const g = parseFloat((ln.querySelector('.fcc-cr-pgrams') || {}).value);
                        if (sid && !Number.isNaN(g) && g > 0) {
                            charges.push({ position: Number(ln.dataset.pos), sid, grams: g });
                            redirected = true;
                        }
                    });
                    if (unNoId != null) {
                        toast(`Type the #id of the spool T${unNoId} used (or pick one).`, 'warning', 7000);
                        return;
                    }
                    // 43.2: a shortfall card names no spool of its own, so an Apply
                    // with nothing picked would charge nothing (the server refuses it too).
                    if (card.dataset.kind === 'shortfall' && !redirected && !Object.keys(updates).length) {
                        toast('Pick the spool that took these grams (or Discard).', 'warning', 7000);
                        return;
                    }
                    if (redirected) payload.charges = charges; else payload.updates = updates;
                    // 43.2: the card's revision, so an Apply from a view opened before
                    // another Apply changed it is refused instead of charging again.
                    if (card.dataset.kind === 'shortfall') payload.rev = Number(card.dataset.rev || 0);
                }
                e.target.disabled = true;
                try {
                    const r = await fetch('/api/cancel_deduct/confirm', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    const d = await r.json();
                    const took = (d.applied || []).reduce((a, x) => a + (Number(x.grams) || 0), 0);
                    if (d.status === 'confirmed' && d.kept) {
                        // 43.2: the picks couldn't take everything (a run-out or
                        // near-empty spool); the rest stays on the card to pick again.
                        toast(`Charged ${fmtG(took)}g. ${fmtG(d.shortfall_g)}g still have no spool — pick another spool, or Discard.`, 'warning', 7000);
                        await rerenderCard(card, true);
                        refreshBadge();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                    } else if (d.status === 'confirmed') {
                        if (took > 0) toast(`Deducted from ${(d.applied || []).length} spool(s).`, 'success');
                        else toast('Nothing was charged: the spool picked has 0 g left on record.', 'warning', 7000);
                        if (d.shortfall_card) {
                            // 43.2: what the picked spools couldn't take is on a new card.
                            toast(`${fmtG(d.shortfall_g)}g couldn't be charged to the spool picked — they're on a new card: pick another spool, or Discard.`, 'warning', 7000);
                        } else if (Number(d.shortfall_g) > 0.05) {
                            // Partial-bind / clamp shortfall (no_spool re-resolve path): part of the
                            // computed usage couldn't be applied — surface it AT THE OVERLAY, not only
                            // in the Activity Log, so the user knows to weigh the still-short spool.
                            toast(`${fmtG(d.shortfall_g)}g couldn't be applied — weigh that spool to true up.`, 'warning', 7000);
                        }
                        if ((d.errors || []).length) toast(`${d.errors.length} spool(s) failed — check the log.`, 'error', 7000);
                        card.remove(); updateCount(); refreshBadge();
                        if (d.shortfall_card) await showNewCard(printer, d.shortfall_card);
                        closeIfEmpty();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                    } else if (d.stale) {
                        // 43.2: another Apply changed this card since it was shown.
                        toast(d.msg || 'This card changed — check it and Apply again.', 'warning', 7000);
                        await rerenderCard(card, true);
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
