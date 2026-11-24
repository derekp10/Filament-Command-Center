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

    // Group 64, Decision 1 (Derek, 2026-11-20): a spool that changed weight after its
    // print ended. FCC fills in 0 g when it weighed the spool after the end (the scale
    // counted the print already), else the print's grams; "both should be heavily
    // noted in the UI so its very clear" that charging may count the print twice.
    // The server writes the words (`words`: which spool, when, on which screen).
    function weighedHtml(w) {
        if (!w || !w.words) return '';
        // Group 64 fix review 2 (CX4): a spool weighed while off its head between two
        // swaps (FX5's mark, `back`) has only its stretch after going back on filled
        // in, the part the scale didn't count: never "0 g", and charging it is right.
        const head = w.back
            ? '⚠️ Weighed while off its head: only its stretch after going back on is filled in'
            : w.known_order
            ? '⚠️ Weighed after this print ended: 0 g filled in'
            : '⚠️ Changed weight after this print ended: check before you Apply';
        const tail = w.back
            ? "The grams filled in are the stretch the scale didn't count: type 0 only if it was weighed again after this print."
            : w.known_order
            ? 'Charging these grams would count the print twice: type them only if that weighing came before the print.'
            : 'Charging the grams filled in may count this print twice.';
        return `<div class="fcc-cr-weighed" role="note"
                     style="flex-basis:100%;margin:4px 0;padding:7px 10px;border:2px solid #ff7a59;border-radius:5px;
                            background:#2a1410;color:#ffd6c9;font-size:var(--fcc-fs-small);line-height:1.45;">
                    <b style="color:#ffb39e;">${esc(head)}</b><br>${esc(w.words)}. ${esc(tail)}</div>`;
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
    // `label` follows the head's name: " had 2 spools this print" only where FCC
    // knows they all printed there (a split, or a set whose spools the recorded
    // swaps account for), else ": FCC saw 2 spools on it" (review fix: a spool
    // seen only when the print ended may never have printed on that head).
    function setBoxHtml(pos, headName, label, extra, inner, cls) {
        const where = headName ? `T${pos} · ${headName}` : `T${pos}`;
        return `
            <div class="fcc-cr-set ${cls}" data-pos="${esc(pos)}" data-where="${esc(where)}"
                 style="margin:8px 0 4px;padding:2px 0 0 10px;border-left:3px solid #5aa0d0;">
                <div class="fcc-cr-set-head"
                     style="display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px;padding:2px 0;
                            color:#e8e8e8;font-weight:bold;font-size:var(--fcc-fs-row);">
                    <span>${esc(where)}${esc(label)}</span>${extra || ''}
                </div>
                ${inner}
            </div>`;
    }
    // Round 2's review: how many spools a card offers for a held head (a set's,
    // else every spool its head entries name), and the most rows its split gives
    // one head: the banners count them, as a head can have any number.
    function heldSpoolCount(rec, pos) {
        const ids = new Set();
        (((rec.unresolved_sets || {})[pos]) || []).forEach((e) => { if (e && e.sid != null) ids.add(String(e.sid)); });
        if (ids.size) return ids.size;
        (rec.heads_at_end || []).forEach((h) => {
            if (!h || String(h.position) !== String(pos)) return;
            (h.sid != null ? [h.sid] : (Array.isArray(h.sids) ? h.sids : [])).forEach((s) => {
                if (s != null) ids.add(String(s));
            });
        });
        return ids.size;
    }
    function splitMostRows(rec) {
        const n = {};
        (rec.spools || []).forEach((s) => {
            if (s && s.auto_split) n[String(s.position)] = (n[String(s.position)] || 0) + 1;
        });
        return Math.max(0, ...Object.values(n));
    }
    // Review fix: whether a card's held line is a set of spools (scope B), whose
    // Apply needs each spool's grams rather than one pick.
    function isSetLine(rec, pos) {
        const entries = ((rec && rec.unresolved_sets) || {})[pos];
        return Array.isArray(entries) && entries.filter((e) => e && e.sid != null).length >= 2;
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
            return setBoxHtml(k, set[0].toolhead, ` had ${set.length} spools this print`, sub,
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
                    <input type="number" class="fcc-cr-pgrams fcc-weight-box form-control bg-dark text-white border-secondary"
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
        // The recorded swaps account for every spool only when none was seen
        // just at the end (or anywhere else FCC can't place in the print).
        const accounted = entries.every((e) => e.when === 'start' || e.when === 'during');
        const label = accounted ? ` had ${entries.length} spools this print` : `: FCC saw ${entries.length} spools on it`;
        // Review fix: an Apply whose boxes don't add up to the set's grams says so
        // here, in the set (setsConfirmed). Round 2 (R1, Derek's picture check:
        // "the confirm looks exactly the same, I'm sure someone could misread
        // it"): an orange box, its words opening on a ⚠️, unlike the amber note
        // above it and the card's amber banner.
        const alert = `<div class="fcc-cr-set-alert" role="alert"
                            style="display:none;margin:6px 0 4px;padding:7px 10px;border-radius:4px;
                                   background:#3a1e08;border:1px solid #fd7e14;border-left:4px solid #fd7e14;
                                   color:#ffe0c2;font-weight:bold;font-size:var(--fcc-fs-row);line-height:1.4;"></div>`;
        return setBoxHtml(pos, head && head.toolhead, label, left,
            lines + noteHtml('fcc-cr-line-note', '#e6c074', notes[pos]) + alert, 'fcc-cr-heldset');
    }

    // Review fix (hotfix 2026-11-11): what stopped an Apply, said on the card
    // itself, above its buttons: the toast layer is drawn under the review panel.
    // Each card's line builder ends with it (noSpoolLinesHtml, unresolvedLinesHtml,
    // shortfallLinesHtml), so the card templates' button rows are untouched.
    const CARD_NOTICE = `<div class="fcc-cr-card-notice" role="alert"
            style="display:none;margin-top:8px;color:#e6c074;font-size:var(--fcc-fs-small);line-height:1.4;"></div>`;
    // `msg` is words, or a list of words and {head} pieces: a head's name drawn
    // bold, as the card's set headers draw theirs (round 2's picture check,
    // Derek, 2026-11-12: "there should be some bolding on T6, like there was on
    // the others, so that it reads as a toolhead, instead of perhaps another part
    // of the ui"). Text nodes only, never HTML: a head's name is the user's own.
    function sayOnCard(card, msg) {
        const n = card && card.querySelector('.fcc-cr-card-notice');
        if (!n) return;
        n.textContent = '';
        (Array.isArray(msg) ? msg : [msg]).forEach((p) => {
            if (p && typeof p === 'object') {
                const b = document.createElement('b');
                b.className = 'fcc-cr-notice-head';
                b.textContent = String(p.head == null ? '' : p.head);
                n.appendChild(b);
            } else if (p) {
                n.appendChild(document.createTextNode(String(p)));
            }
        });
        // Group 64 fix review 4 (UP2): a card kept as it was drawn, because FCC couldn't
        // read the review list again after its Apply, says so whatever else it says.
        if (card.dataset && card.dataset.stale === '1') {
            n.appendChild(document.createTextNode((n.textContent ? ' ' : '') + STALE_CARD_WORDS));
        }
        n.style.display = n.textContent ? '' : 'none';
    }
    const STALE_CARD_WORDS = "FCC couldn't read the review list just now, so this card may be out of date: "
        + 'Apply reads it again first, or close 🛑 Review and open it again.';
    // Group 64.2 (the look): a head's name in words the server sent (a refusal) is
    // bold, as on the card's own lines ("so that it reads as a toolhead", Derek,
    // 2026-11-12): the card's head names (`data-head-names`: every toolhead it names
    // and its T<n>) found standing whole in the words, longest first, become
    // sayOnCard's {head} pieces; "XL-1" in "XL-10" stays as it is.
    function cardHeadNames(rec) {
        const out = new Set();
        const add = (v) => { if (v != null && String(v).trim()) out.add(String(v).trim()); };
        (rec.heads_at_end || []).forEach((h) => { if (h) { add(h.toolhead); if (h.position != null) add(`T${h.position}`); } });
        (rec.spools || []).forEach((r) => { if (r) { add(r.toolhead); if (r.position != null) add(`T${r.position}`); } });
        Object.keys(rec.unresolved_usage || rec.usage_map || {}).forEach((k) => add(`T${k}`));
        Object.values(rec.shortfall_causes || {}).forEach((c) => { if (c) add(c.toolhead); });
        return Array.from(out);
    }
    function headPieces(card, msg) {
        const text = String(msg == null ? '' : msg);
        let names = [];
        try { names = JSON.parse((card && card.dataset && card.dataset.headNames) || '[]'); } catch (_) { names = []; }
        names = (Array.isArray(names) ? names : []).map(String).filter((n) => n).sort((a, b) => b.length - a.length);
        if (!text || !names.length) return text;
        // A name stands whole: no letter, digit or hyphen just before it, and no
        // letter or digit just after it, nor a hyphen and one ("HEAD" in "HEAD-70").
        const word = /[A-Za-z0-9]/;
        const goesOn = (j) => word.test(text[j] || '') || (text[j] === '-' && word.test(text[j + 1] || ''));
        const out = [];
        let i = 0;
        let plain = '';
        while (i < text.length) {
            const hit = names.find((n) => text.startsWith(n, i)
                && !(i > 0 && (word.test(text[i - 1]) || text[i - 1] === '-'))
                && !goesOn(i + n.length));
            if (hit) {
                if (plain) { out.push(plain); plain = ''; }
                out.push({ head: hit });
                i += hit.length;
            } else {
                plain += text[i];
                i += 1;
            }
        }
        if (plain) out.push(plain);
        return out.length === 1 && typeof out[0] === 'string' ? out[0] : out;
    }
    // Round 2 (R1, Derek's picture check, 2026-11-12): while the set check waits
    // for its second press, the card's button says what that press does, in
    // orange ("Just so the user is made aware that they are about to not perform
    // a deduct"). Dark words on orange (white on orange fails contrast), set as
    // Bootstrap's own button colours so it stays orange when pointed at, pressed
    // or reached by the keyboard, its focus ring too.
    const YES_STYLE = '--bs-btn-color:#000;--bs-btn-bg:#fd7e14;--bs-btn-border-color:#fd7e14;'
        + '--bs-btn-hover-color:#000;--bs-btn-hover-bg:#fd9137;--bs-btn-hover-border-color:#fd9137;'
        + '--bs-btn-active-color:#000;--bs-btn-active-bg:#fd9843;--bs-btn-active-border-color:#fd9843;'
        + '--bs-btn-disabled-color:#000;--bs-btn-disabled-bg:#fd7e14;--bs-btn-disabled-border-color:#fd7e14;'
        + '--bs-btn-focus-shadow-rgb:253,126,20;';
    // A waiting button's own words, classes and style, to give back (yesOff).
    const _ownLook = new WeakMap();
    // What a waiting card's line by the buttons said (sayOnCard's pieces), to
    // say again when a double click's second press clears it (setsConfirmed).
    const _askSaid = new WeakMap();
    function yesOn(btn, words) {
        if (!btn) return;
        if (!_ownLook.has(btn)) {
            _ownLook.set(btn, { text: btn.textContent, cls: btn.className, style: btn.getAttribute('style') });
        }
        const own = _ownLook.get(btn);
        btn.textContent = words;
        btn.className = own.cls;
        btn.classList.remove('btn-success');
        btn.classList.add('fcc-cr-yes');
        btn.setAttribute('style', (own.style ? `${own.style};` : '') + YES_STYLE);
    }
    function yesOff(btn) {
        const own = btn && _ownLook.get(btn);
        if (!own) return;
        _ownLook.delete(btn);
        btn.textContent = own.text;
        btn.className = own.cls;
        if (own.style == null) btn.removeAttribute('style'); else btn.setAttribute('style', own.style);
    }
    // Ends the set check's wait for a second press: the sets' words, and its line
    // by the buttons, go, and the button is its own again, so a "⚠️ Yes" never
    // stands over grams that changed since. The next press over a set that still
    // doesn't add up asks again (never going ahead on an ask nobody sees now).
    function endSetAsk(card) {
        if (!card) return;
        const asked = card.dataset.setAsked != null;
        delete card.dataset.setAsked;
        delete card.dataset.setAskedAt;
        _askSaid.delete(card);
        card.querySelectorAll('.fcc-cr-set-alert').forEach((a) => { a.textContent = ''; a.style.display = 'none'; });
        if (asked) sayOnCard(card, '');
        yesOff(card.querySelector('.fcc-cr-confirm'));
    }
    // A held set whose boxes don't add up to its grams (to 0.05 g), in words:
    // [{box, placed, short, words}], `short` being the grams not placed (below 0
    // when the boxes add up to more). One press used to close a set left empty
    // with its grams uncharged (its lines' pickers already name their spools, so
    // the card looked done), and a head's grams typed in both boxes were charged
    // twice. The words point at the button as it reads while the check waits
    // (round 2, R1): "⚠️ Yes", the same on every card.
    function setProblems(card) {
        const out = [];
        card.querySelectorAll('.fcc-cr-heldset').forEach((box) => {
            const left = box.querySelector('.fcc-cr-set-left');
            const total = Number(left && left.dataset.total);
            if (!Number.isFinite(total) || total <= 0) return;
            let placed = 0;
            box.querySelectorAll('.fcc-cr-pgrams').forEach((b) => {
                const g = parseFloat(b.value);
                if (g > 0) placed += g;
            });
            placed = Math.round(placed * 100) / 100;
            const d = Math.round((total - placed) * 100) / 100;
            if (Math.abs(d) <= 0.05) return;
            const where = box.dataset.where || `T${box.dataset.pos}`;
            const t = fmtG(total);
            let words;
            if (placed <= 0) {
                words = `${where}: none of its ${t} g are placed. Type the grams each spool used, or put them `
                    + 'all on one; or press ⚠️ Yes below to leave them uncharged.';
            } else if (d > 0) {
                words = `${where}: ${fmtG(d)} g of its ${t} g aren't placed. Press ⚠️ Yes below to leave them `
                    + 'uncharged.';
            } else {
                words = `${where}: its spools add up to ${fmtG(placed)} g, ${fmtG(-d)} g more than the ${t} g `
                    + 'FCC computed. Press ⚠️ Yes below to charge the spools as typed.';
            }
            out.push({ box, placed, short: d, words });
        });
        return out;
    }
    // Whether the ledger counts a card's ask as a total (the server's rule in
    // _lines_left_unplaced): a no_spool card's whole usage, or a review an earlier
    // Apply fixed (`requested_total`: a retry after a failed write, a card kept with
    // grams left). Group 64.2 (6).
    function askFixed(rec, kind) {
        return kind === 'no_spool' || (rec && rec.requested_total != null);
    }
    // Round 2's review: a held line that isn't a set and that a press charges
    // nothing to (no spool picked, or no grams) is left uncharged too, at its
    // record's grams, whatever its box shows: the server keeps them on the review
    // (a no_spool card counts its whole line), and the Activity Log names them.
    // Group 64.2 (6): where the ask is fixed (askFixed, the card's
    // data-ask-fixed), a picked line typed under FCC's figure leaves the grams it
    // was typed short of, as the ledger counts them, and one typed over makes up
    // for another line's (`grams` below 0); on any other card a picked line is
    // charged what its pick says. [{line, where, grams, picked}], for the set
    // check's Yes to count.
    function plainLinesLeft(card) {
        const fixed = card.dataset.askFixed === '1';
        const out = [];
        card.querySelectorAll('.fcc-cr-unline, .fcc-cr-pickline').forEach((ln) => {
            if (ln.classList.contains('fcc-cr-setline')) return;
            const box = ln.querySelector('.fcc-cr-pgrams');
            const held = Number(box && box.getAttribute('value'));
            if (!(held > 0)) return;
            const pos = ln.dataset.pos != null ? ln.dataset.pos : ln.dataset.line;
            const where = ln.dataset.where || `T${pos}`;
            const typed = parseFloat(box.value);
            if (pickedSid(card, ln.dataset.line) && typed > 0) {
                if (!fixed) return;
                const d = Math.round((held - typed) * 100) / 100;
                if (Math.abs(d) > 0.005) out.push({ line: ln.dataset.line, where, grams: d, picked: true });
                return;
            }
            out.push({ line: ln.dataset.line, where, grams: held, picked: false });
        });
        return out;
    }
    // "a", "a or b", "a, b or c" (or with "and"), as sayOnCard's pieces: each
    // head's name bold.
    function listHeads(wheres, conj) {
        const out = [];
        wheres.forEach((w, i) => {
            if (i) out.push(i === wheres.length - 1 ? conj : ', ');
            out.push({ head: w });
        });
        return out;
    }
    function orHeads(wheres) { return listHeads(wheres, ' or '); }
    // Whether an Apply may go ahead over the card's sets: at once when each is
    // placed exactly; else the first press says why in each set and on the card,
    // and a second press with the same grams goes ahead (Derek: more resistance on
    // a yes that is hard to undo, no typed words). While it waits, the button
    // says what that second press does (round 2, R1), counting the plain held
    // lines it leaves too (round 2's review).
    function setsConfirmed(card, ev) {
        const problems = setProblems(card);
        const plain = problems.length ? plainLinesLeft(card) : [];
        const sig = problems.map((p) => `${p.box.dataset.pos}=${p.placed}`)
            .concat(plain.map((l) => `${l.line}=${l.picked ? l.grams : 'left'}`)).join(';');
        // A double click's second press is no second press (Derek's rule for a
        // yes that is hard to undo): the second click of a double click, or any
        // press under 700 ms after the one that asked, does nothing, and what
        // the first press said stays up: the press's handler cleared the line by
        // the buttons, which comes back (round 2's review: at phone width the
        // panel scrolls the button back under the pointer for the second click).
        if (problems.length && card.dataset.setAsked === sig
                && ((ev && ev.detail > 1) || Date.now() - Number(card.dataset.setAskedAt || 0) < 700)) {
            sayOnCard(card, _askSaid.get(card) || '');
            return false;
        }
        // The second press goes out (or there is nothing left to ask): the button
        // is its own again before it does, whatever the answer. Grams other than
        // those asked about are asked about again.
        const asked = card.dataset.setAsked;
        endSetAsk(card);
        if (!problems.length || asked === sig) return true;
        card.dataset.setAsked = sig;
        card.dataset.setAskedAt = String(Date.now());
        problems.forEach((p) => {
            const a = p.box.querySelector('.fcc-cr-set-alert');
            if (a) { a.textContent = `⚠️ ${p.words}`; a.style.display = ''; }
        });
        const setShort = problems.filter((p) => p.short > 0).reduce((a, p) => a + p.short, 0);
        const setOver = problems.filter((p) => p.short < 0).reduce((a, p) => a - p.short, 0);
        const unpicked = plain.filter((l) => !l.picked);
        const pickedShort = plain.filter((l) => l.picked && l.grams > 0);
        const pickedOver = plain.filter((l) => l.picked && l.grams < 0);
        const plainG = unpicked.reduce((a, l) => a + l.grams, 0);
        const shortG = pickedShort.reduce((a, l) => a + l.grams, 0);
        const overG = pickedOver.reduce((a, l) => a - l.grams, 0);
        const short = Math.round((setShort + plainG + shortG) * 100) / 100;
        const over = Math.round((setOver + overG) * 100) / 100;
        // Held sets are among a card's last lines, just above its buttons, so one
        // set's words are said in the set alone: the card's notice said them again
        // a line or two below. Two or more sets get one line by the buttons, and so
        // do the plain held lines the press leaves (round 2's review), so every
        // gram the Yes names is said on the card.
        const does = !setOver ? 'leave them uncharged' : !setShort ? 'charge the spools as typed' : 'go ahead as typed';
        // Each line is a list of sayOnCard's pieces, the heads it names bold.
        const lines = [];
        if (problems.length > 1) {
            lines.push([`${problems.length} heads' grams don't add up, as each says above. Press ⚠️ Yes below to ${does}.`]);
        }
        if (unpicked.length) {
            lines.push(['⚠️ Yes below charges nothing to ', ...orHeads(unpicked.map((l) => l.where)),
                `, leaving ${unpicked.length === 1 ? 'its' : 'their'} ${fmtG(plainG)} g uncharged.`]);
        }
        if (pickedShort.length) {
            lines.push([`⚠️ Yes below charges ${fmtG(shortG)} g less than FCC worked out on `,
                ...listHeads(pickedShort.map((l) => l.where), ' and '), ', leaving them uncharged.']);
        }
        if (pickedOver.length) {
            lines.push([`⚠️ Yes below charges ${fmtG(overG)} g more than FCC worked out on `,
                ...listHeads(pickedOver.map((l) => l.where), ' and '), '.']);
        }
        const notice = lines.reduce((all, l) => (all.length ? all.concat(' ', l) : l), []);
        if (notice.length) _askSaid.set(card, notice);
        sayOnCard(card, notice);
        const btn = card.querySelector('.fcc-cr-confirm');
        yesOn(btn, !over ? `⚠️ Yes, leave ${fmtG(short)} g uncharged`
            : !short ? `⚠️ Yes, charge ${fmtG(over)} g more` : '⚠️ Yes, go ahead as typed');
        // The words make the card taller, and the panel scrolls: keep the button
        // just pressed in view, with what it said above it.
        if (btn && typeof btn.scrollIntoView === 'function') btn.scrollIntoView({ block: 'nearest' });
        return false;
    }

    // Group 64 fix review 3 (TP6): whether the last read of the list failed, which a
    // card's redraw must not take for "the card is gone" (Group 52: a read that failed
    // says so, never "empty").
    let pendingReadFailed = false;
    async function fetchPending() {
        try {
            const r = await fetch('/api/cancel_deduct/pending');
            if (!r.ok) { pendingReadFailed = true; return []; }
            const d = await r.json();
            pendingReadFailed = !Array.isArray(d.pending);
            return Array.isArray(d.pending) ? d.pending : [];
        } catch (e) {
            pendingReadFailed = true;
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
        const groups = { end: [], start: [], during: [], picked: [] };
        const listed = new Set(own != null ? [String(own)] : []);
        (atEnd || []).forEach((h) => {
            const when = ['start', 'during', 'picked'].includes(h.when) ? h.when : 'end';
            const ids = h.sid != null ? [h.sid] : (Array.isArray(h.sids) ? h.sids : []);
            ids.forEach((sid) => {
                if (sid != null) listed.add(String(sid));
                if (sid == null || String(sid) === String(own)) return;
                // 43.2: a spool that ran out is still offered (it is charged what it
                // has left, 0 g for an empty one, and stays archived), but says so;
                // Group 64.2 (8): among a head's several spools, only the one that ran
                // out (`archived_sids`).
                const ranOut = Array.isArray(h.archived_sids)
                    ? h.archived_sids.some((x) => String(x) === String(sid)) : !!h.archived;
                // Group 64.2 (7): a spool picked on an earlier Apply of the card is
                // offered as such, never as the spool on the head.
                const where = when === 'picked' ? `picked for ${esc(h.toolhead)} on this card`
                    : `on ${esc(h.toolhead)} ${esc(w[when] || w.end)}`;
                groups[when].push(`<option value="${esc(sid)}">#${esc(sid)} — ${where}${ranOut ? ' (ran out, archived)' : ''}</option>`);
            });
        });
        const group = (when, cls) => groups[when].length
            ? `<optgroup label="${esc(capFirst(when === 'picked' ? 'picked on this card' : (w[when] || w.end)))}" class="${cls}">${groups[when].join('')}</optgroup>`
            : '';
        // The #id box is text, not number: arrow keys on a number box step it
        // (an empty one to 1), and charging spool #1 by accident is a real write.
        // It takes a scanned label too (scope D, readSpoolBox).
        return `
            <select class="fcc-cr-pick form-select form-select-sm bg-dark text-light border-secondary"
                    data-line="${esc(line)}" data-own="${own == null ? '' : esc(own)}"
                    style="max-width:330px;font-size:0.92rem;">
                ${first}
                ${group('end', 'fcc-cr-ended')}${group('start', 'fcc-cr-started')}${group('during', 'fcc-cr-during')}${group('picked', 'fcc-cr-picked')}
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
        // Decision 1: a spool weighed (or changed) after the print ended.
        // Group 64 fix review 2 (CP4): a 43.6 retry row is a charge the person chose (its
        // write failed): drawn from its own grams, never as a hold, even on a record
        // that still carries the hold's mark.
        const weighed = s.weighed && s.weighed.words && s.attempt_used_before == null ? s.weighed : null;
        const boxValue = weighed && s.prefill != null ? s.prefill : s.grams;
        // Group 64 full review (WD6): a weighed row's box holds what FCC filled in (0 g
        // when the scale counted the print), so its preview is drawn from that, never
        // from the charge's `remaining_after`, which showed the spool losing the print.
        const after = !known ? null
            : (weighed ? Math.max(0, Number(s.remaining_before) - (Number(boxValue) || 0)) : s.remaining_after);
        return `
            <div class="fcc-cr-row" data-sid="${s.sid}"${weighed ? ' data-weighed="1"' : ''}
                 style="display:flex;align-items:center;gap:8px;justify-content:space-between;flex-wrap:wrap;
                        padding:6px 0;border-bottom:1px solid #2b2c30;${ambBorder}${weighed ? 'border-left:3px solid #ff7a59;padding-left:6px;' : ''}">
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
                    <input type="number" class="fcc-cr-grams fcc-weight-box form-control bg-dark text-white border-secondary"
                           data-sid="${s.sid}" data-remaining="${known ? s.remaining_before : ''}"
                           data-own-remaining="${known ? s.remaining_before : ''}"
                           value="${fmtG(boxValue)}" step="0.01" min="0" ${known ? `max="${fmt(s.remaining_before)}"` : ''}
                           autocomplete="off" style="font-size:1.05rem;" />
                    <span class="input-group-text bg-dark text-light border-secondary">g</span>
                </div>
                <div class="fcc-cr-preview" data-sid="${s.sid}"
                     style="width:104px;flex:none;text-align:right;color:#9fe0b0;font-size:0.95rem;">
                    → ${known ? `${fmt(after)}g` : '?'}
                </div>
                <div class="fcc-cr-redirect" style="flex-basis:100%;display:flex;align-items:center;gap:6px;
                            padding-left:24px;color:#9aa;font-size:0.88rem;">
                    charge to: ${pickSelectHtml(s.sid, s.sid, `this spool (#${s.sid})`, rec && rec.heads_at_end, headsWords(rec))}
                </div>
                ${weighedHtml(weighed)}
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
            // Escaped here. Its line draws it bold, as a set's header draws its
            // head (round 2's picture check: "so that it reads as a toolhead");
            // so do unresolvedLinesHtml's and shortfallLinesHtml's lines.
            const where = head ? `T${esc(pos)} · ${esc(head.toolhead)}` : `T${esc(pos)}`;
            return `
                <div class="fcc-cr-pickline" data-line="${esc(pos)}" data-where="${where}"
                     style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 0;border-bottom:1px solid #2b2c30;">
                    <span style="color:#eee;min-width:120px;"><b class="fcc-cr-line-head">${where}</b> used</span>
                    <div class="input-group input-group-sm" style="width:120px;flex:none;">
                        <input type="number" class="fcc-cr-pgrams fcc-weight-box form-control bg-dark text-white border-secondary"
                               data-line="${esc(pos)}" value="${fmtG(usage[pos])}" step="0.01" min="0"
                               autocomplete="off" style="font-size:1.05rem;" />
                        <span class="input-group-text bg-dark text-light border-secondary">g</span>
                    </div>
                    <span style="color:#9aa;">→</span>
                    ${pickSelectHtml(pos, null, '', atEnd, words)}
                    ${noteHtml('fcc-cr-line-note', '#e6c074', notes[pos])}
                </div>`;
        }).join('') + CARD_NOTICE;
    }

    // Group 43.4: the heads a partial review's print used that no row charges:
    // emptied mid-print, or (hotfix 2026-11-11) held because FCC can't vouch for
    // the spool on it, each with a note saying why. Each gets a picker like a
    // no_spool line; one left unpicked is reported as uncharged at Apply instead
    // of vanishing.
    function unresolvedLinesHtml(rec) {
        const un = rec.unresolved_usage || {};
        const keys = Object.keys(un).sort((a, b) => Number(a) - Number(b));
        if (!keys.length) return CARD_NOTICE;
        const atEnd = Array.isArray(rec.heads_at_end) ? rec.heads_at_end : [];
        const words = headsWords(rec);
        const notes = rec.unresolved_notes || {};
        const which = keys.length === 1 ? 'this head' : 'these heads';
        // Review fix: a line that is a set of spools asks for each one's grams.
        const sets = keys.filter((k) => isSetLine(rec, k)).length;
        const ask = !sets ? 'Pick the spool it used,'
            : sets === keys.length ? 'Type the grams each spool used (or put them all on one),'
            : 'Pick the spool each used (on a head with several spools, type the grams each one used),';
        // "When the print ended" only where the heads were read then: each held
        // line says itself what FCC saw on it.
        const lead = keys.some((pos) => notes[pos])
            ? `⚠️ FCC isn't sure which spool printed on ${which}. ${ask} or leave it:
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
                <div class="fcc-cr-unline" data-pos="${esc(pos)}" data-line="${esc(line)}" data-where="${where}"
                     style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 0;border-bottom:1px solid #2b2c30;">
                    <span style="color:#eee;min-width:120px;"><b class="fcc-cr-line-head">${where}</b> used</span>
                    <div class="input-group input-group-sm" style="width:120px;flex:none;">
                        <input type="number" class="fcc-cr-pgrams fcc-weight-box form-control bg-dark text-white border-secondary"
                               data-line="${esc(line)}" value="${fmtG(un[pos])}" step="0.01" min="0"
                               autocomplete="off" style="font-size:1.05rem;" />
                        <span class="input-group-text bg-dark text-light border-secondary">g</span>
                    </div>
                    <span style="color:#9aa;">→</span>
                    ${pickSelectHtml(line, null, '', atEnd, words)}
                    ${noteHtml('fcc-cr-line-note', '#e6c074', notes[pos])}
                </div>`;
        }).join('') + CARD_NOTICE;
    }

    // Group 43.2: grams an automatic deduct couldn't charge (a spool ran out
    // mid-print, a head had no spool, a write failed). Each head's line says why
    // and picks the spool that really took the rest: after a SpoolJoin runout,
    // the joined spool. The run-out spool is offered but not pre-picked: it is
    // archived, and charging it takes only what it has left (0 g when empty).
    // Whatever a pick can't take stays on the card.
    // FCC sees the spool's record, not the spool: "ran out" is the record hitting
    // 0 g, which may also mean the record was off (Derek: small spools often are).
    // Round 2 (R3): a head can have any number of spools: #1; #1 and #2; #1, #2 and #3.
    function spoolListWords(sids) {
        const ids = (sids || []).map((s) => `#${s}`);
        return ids.length > 1 ? `${ids.slice(0, -1).join(', ')} and ${ids[ids.length - 1]}` : ids.join('');
    }
    function shortfallReason(c, pos) {
        const head = c.toolhead || `T${pos}`;
        if (c.why === 'ran_out') {
            // Round 2 (R3): every spool of the head whose record hit 0 g (a head
            // split at its swaps can have several).
            const who = Array.isArray(c.sids) && c.sids.length > 1
                ? `the records of ${spoolListWords(c.sids)}` : `#${c.sid}'s record`;
            return `${who} hit 0 g on ${head}${c.archived ? ' (archived)' : ''}`;
        }
        if (c.why === 'no_spool') return `no spool was loaded on ${head}`;
        if (c.why === 'two_spools' && Array.isArray(c.mmu_shared) && c.mmu_shared.length) {
            // Group 64.6: MMU slots sharing one Position, each holding a spool.
            const slots = c.mmu_shared.length > 1
                ? `${c.mmu_shared.slice(0, -1).join(', ')} and ${c.mmu_shared[c.mmu_shared.length - 1]}`
                : c.mmu_shared.join('');
            return `MMU slots ${slots} share one Position and each held a spool `
                + `(${spoolListWords(c.sids)}), so FCC charged none of them: give each MMU slot its own `
                + `Position in Settings (slot 1 = Position 0, slot 2 = Position 1, …) so FCC can tell which printed`;
        }
        if (c.why === 'two_spools') {
            // Round 2 (R3): counted, as FCC's record can put more than two on a head.
            const n = (c.sids || []).length;
            const both = spoolListWords(c.sids);
            return `${head} had ${n > 2 ? `${n} spools` : 'two spools'}${both ? ` (${both})` : ''}, `
                + `so FCC charged ${n > 2 ? 'none of them' : 'neither'}`;
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
            // Decision 1: a spool weighed (or changed) after the print ended: its
            // grams filled in with what the server worked out (0 g, or the print's).
            const weighed = c.why === 'weighed';
            const fill = rec.shortfall_prefill || {};
            const boxValue = weighed && fill[pos] != null ? fill[pos] : un[pos];
            const why = weighed
                ? weighedHtml({ words: c.words, known_order: !!c.known_order })
                : `<div class="fcc-cr-why" style="color:#e6c074;font-size:0.9rem;margin-bottom:4px;">${esc(shortfallReason(c, pos))}</div>`;
            return `
                <div class="fcc-cr-unline fcc-cr-shortline" data-pos="${esc(pos)}" data-line="${esc(line)}"${weighed ? ' data-weighed="1"' : ''}
                     style="padding:6px 0;border-bottom:1px solid #2b2c30;">
                    ${why}
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                        <span style="color:#eee;min-width:120px;"><b class="fcc-cr-line-head">${where}</b> uncharged</span>
                        <div class="input-group input-group-sm" style="width:120px;flex:none;">
                            <input type="number" class="fcc-cr-pgrams fcc-weight-box form-control bg-dark text-white border-secondary"
                                   data-line="${esc(line)}" value="${fmtG(boxValue)}" step="0.01" min="0"
                                   autocomplete="off" style="font-size:1.05rem;" />
                            <span class="input-group-text bg-dark text-light border-secondary">g</span>
                        </div>
                        <span style="color:#9aa;">→</span>
                        ${pickSelectHtml(line, own, ownLabel, atEnd, words)}
                    </div>
                </div>`;
        }).join('') + CARD_NOTICE;
    }

    // Group 64 full review (WD1): what an uncharged-grams card says at its head. A
    // line FCC held on purpose (Decision 1: its spool weighed, or changed weight,
    // after the print ended) is no grams that "went to no spool": a card of only such
    // lines says why they are held, and a card with other lines too counts them apart.
    function shortfallHead(rec) {
        const un = rec.unresolved_usage || {};
        const causes = rec.shortfall_causes || {};
        const lines = Object.keys(un).filter((p) => (causes[p] || {}).why === 'weighed');
        // Group 64 fix review 2 (CP2 / CX3): a pick an Apply held stays on the card as a
        // row marked weighed (never a failed write's retry row): held grams on a known
        // spool, as a weighed line's are.
        const allRows = rec.spools || [];
        const rows = allRows.filter((s) => s && s.weighed && s.weighed.words && s.attempt_used_before == null);
        // Group 64 fix review 3 (TP4): a failed write's retry row is a spool already
        // picked, its write to be tried again: no grams that went to no spool.
        const retry = allRows.filter((s) => s && s.attempt_used_before != null);
        const heldG = lines.reduce((a, p) => a + (Number(un[p]) || 0), 0)
            + rows.reduce((a, s) => a + (Number(s.grams) || 0), 0);
        const retryG = retry.reduce((a, s) => a + (Number(s.grams) || 0), 0);
        const total = Number(rec.total_grams) || 0;
        // TP3: one spool named once (a held row and a held line of the same spool).
        const once = (xs) => xs.filter((x, i) => xs.findIndex((y) => String(y) === String(x)) === i);
        const sids = once(lines.map((p) => causes[p].sid).concat(rows.map((s) => s.sid)).filter((s) => s != null));
        const held = lines.concat(rows.map((s) => `row:${s.sid}`));
        return {
            held, heldG, otherG: Math.max(0, total - heldG - retryG), sids,
            retry, retryG, retryWho: spoolListWords(once(retry.map((s) => s.sid))),
            retryMany: once(retry.map((s) => s.sid)).length > 1,
            who: spoolListWords(sids), many: sids.length > 1,
            known: lines.every((p) => !!causes[p].known_order) && rows.every((s) => !!s.weighed.known_order),
            onlyHeld: held.length > 0 && lines.length === Object.keys(un).length && rows.length === allRows.length,
        };
    }
    function shortfallTitle(rec, h) {
        const total = fmtG(rec.total_grams);
        if (h.onlyHeld) {
            return `${fmtG(h.heldG)}g held: ${h.who} ${h.known ? (h.many ? 'were weighed' : 'was weighed')
                : 'changed weight'} after this print`;
        }
        if (!h.held.length && !h.retry.length) return `${total}g went to no spool`;
        const parts = [];
        if (h.otherG > 0.05) parts.push(`${fmtG(h.otherG)}g went to no spool`);
        if (h.held.length) parts.push(`${fmtG(h.heldG)}g held`);
        if (h.retry.length) parts.push(`${fmtG(h.retryG)}g to retry on ${h.retryWho}`);
        return parts.join('; ');
    }
    function shortfallBanner(rec, h) {
        const it = h.many ? 'them' : 'it';
        if (h.onlyHeld && h.known) {
            return `FCC held these grams instead of charging them: ${esc(h.who)} ${h.many ? 'were' : 'was'} weighed
                    on FCC after this print ended, so the scale already counted ${it}. <b>Apply</b> with the
                    0 g filled in to leave ${it} uncharged, or type the grams if that weighing came before the
                    print. Or <b>Discard</b>.`;
        }
        if (h.onlyHeld) {
            return `FCC held these grams instead of charging them: ${esc(h.who)} changed weight after this
                    print ended, and FCC can't tell whether the scale counted this print. Check each line, then
                    <b>Apply</b>: the grams filled in if the change came before the print, or 0 g if the scale
                    already counted it. Or <b>Discard</b>.`;
        }
        const parts = [];
        if (h.otherG > 0.05 || (!h.held.length && !h.retry.length)) {
            const g = (h.held.length || h.retry.length) ? fmtG(h.otherG) : fmtG(rec.total_grams);
            parts.push(`FCC charged what it could for this print, but <b>${g}g</b> went to no spool. If the
                    printer carried on from another spool (a <b>joined spool</b>), or you know where the
                    filament came from, <b>pick that spool</b> and <b>Apply</b>. A spool whose record is at
                    0 g takes nothing, and whatever a spool can't take stays on this card. If a record was
                    off (the spool still has filament), weigh that spool. Or <b>Discard</b> if you've already
                    weighed them.`);
        }
        if (h.retry.length) {
            // TP4: the spool is picked; its write is what failed. Fix review 4 (UP6): a
            // write FCC couldn't confirm (refused, or no answer), worded per count.
            parts.push(h.retryMany
                ? `The <b>${fmtG(h.retryG)}g</b> picked for ${esc(h.retryWho)} couldn't be confirmed as
                    written (Spoolman didn't take their writes, or didn't answer): <b>Apply</b> tries again,
                    and FCC first checks whether each landed.`
                : `The <b>${fmtG(h.retryG)}g</b> picked for ${esc(h.retryWho)} couldn't be confirmed as
                    written (Spoolman didn't take the write, or didn't answer): <b>Apply</b> tries again,
                    and FCC first checks whether it landed.`);
        }
        if (h.held.length) {
            parts.push(`The <b>${fmtG(h.heldG)}g</b> on ${esc(h.who)} ${h.many ? 'are' : 'is'} held, not charged:
               ${h.many ? 'they' : 'it'} ${h.known ? (h.many ? 'were weighed' : 'was weighed') : 'changed weight'}
               after this print ended, as ${h.many ? 'their lines say' : 'its line says'}.`);
        }
        return parts.join(' ');
    }
    // The picture walk (Derek, 2026-11-23, "12.4g unconfirmed"): a failed write's retry
    // row may have landed (FCC checks before it tries again), so the corner calls its
    // grams unconfirmed, never uncharged; a card with other grams too counts the two
    // apart, and a card with no retry row keeps "uncharged".
    function shortfallCorner(rec, h) {
        if (!h.retry.length) return `${fmtG(rec.total_grams)}g uncharged`;
        const rest = Math.max(0, (Number(rec.total_grams) || 0) - h.retryG);
        if (rest <= 0.05) return `${fmtG(h.retryG)}g unconfirmed`;
        return `${fmtG(rest)}g uncharged; ${fmtG(h.retryG)}g unconfirmed`;
    }

    function shortfallCardHtml(rec) {
        const head = shortfallHead(rec);
        // A failed write's retry keeps its row (the picked spool) on the card.
        const rows = (rec.spools || []).map((s) => spoolRowHtml(s, rec)).join('');
        return `
            <div class="fcc-cr-card" data-printer="${esc(rec.printer_name)}" data-job="${esc(rec.job_id)}"
                 data-kind="shortfall" data-ambiguous="0" data-rev="${esc(rec.rev == null ? 0 : rec.rev)}"
                 data-ask-fixed="${askFixed(rec, 'shortfall') ? '1' : '0'}"
                 data-head-names="${esc(JSON.stringify(cardHeadNames(rec)))}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div class="fcc-cr-short-title" style="font-weight:bold;color:#ffd27a;">⚖️ ${esc(rec.printer_name)} — ${esc(shortfallTitle(rec, head))}</div>
                    <div class="fcc-cr-short-total" style="color:#9aa;font-size:0.92rem;">${esc(shortfallCorner(rec, head))}</div>
                </div>
                <div style="color:#9aa;font-size:0.9rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                <div class="fcc-cr-short-banner" style="color:#e6c074;font-size:0.95rem;margin-bottom:10px;line-height:1.45;
                            background:#221d12;border:1px solid #3a2f17;border-radius:4px;padding:9px 11px;">
                    ${shortfallBanner(rec, head)}
                </div>
                ${rows}
                ${shortfallLinesHtml(rec)}
                <div style="display:flex;flex-direction:row-reverse;justify-content:flex-start;gap:8px;margin-top:10px;">
                    <button type="button" class="btn btn-sm btn-success fw-bold fcc-cr-confirm">Apply to the picked spool(s)</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary fcc-cr-discard"
                            data-armed="0"
                            title="Permanently drop this review — these grams stay uncharged">🗑️ Discard</button>
                </div>
            </div>`;
    }

    // Why a progress_unknown review couldn't measure its print (the record's
    // `unmeasured_reason`, print_deduct._UNMEASURED_WHY's keys; Group 56.3). A
    // record from before 56.3 has none and was always "replaced".
    // Group 65.1 (1) (Derek, 2026-11-09: "the 30% last seen is the real issue"): an end
    // FCC saw only after it lost sight of the print (a network drop, a power cut, FCC
    // restarting) says where FCC last saw the print and when it saw the printer again,
    // in the browser's clock, from the seconds the server stores (dev's container runs
    // on UTC, prod's on Pacific time). A card from before the release has no
    // `lost_contact` and keeps its look.
    const LOST_STATE_WORDS = {
        IDLE: 'idle', READY: 'idle', OPERATIONAL: 'idle', STOPPED: 'stopped', ERROR: 'showing an error',
        FINISHED: 'finished', PRINTING: 'printing another job', PAUSED: 'paused in another job',
        PAUSING: 'paused in another job', RESUMING: 'printing another job', ATTENTION: 'waiting at a prompt',
        BUSY: 'busy',
    };
    function clockAt(s) {
        const n = Number(s);
        if (s === null || s === undefined || s === '' || !Number.isFinite(n) || n <= 0) return '';
        const d = new Date(n * 1000);
        const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return d.toDateString() === new Date().toDateString()
            ? hm : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${hm}`;
    }
    function lostContactHtml(rec, mayHaveGoneFurther) {
        const lc = rec && rec.lost_contact;
        if (!lc || typeof lc !== 'object') return '';
        const pct = Math.round(Math.max(0, Math.min(1, Number(lc.progress) || 0)) * 100);
        const at = (s) => { const t = clockAt(s); return t ? ` (${t})` : ''; };
        const back = clockAt(lc.back_at);
        let words;
        if (lc.why === 'restart') {
            words = `FCC last saw this print at ~${pct}%${at(lc.seen_at)}, before FCC restarted${back ? ` at ${back}` : ''}.`;
        } else {
            const state = LOST_STATE_WORDS[String(lc.back_state || '').toUpperCase()] || 'again';
            const lost = `FCC lost contact with ${esc(rec.printer_name)} at ~${pct}%`
                + at(lc.lost_at != null ? lc.lost_at : lc.seen_at);
            words = mayHaveGoneFurther
                ? `${lost} and next saw it ${state}${back ? ` at ${back}` : ''}, so the print may have gone further.`
                : `${lost} and next saw it ${state}${back ? ` at ${back}` : ''}: it may have printed further before it was cancelled.`;
        }
        return `<div class="fcc-cr-lost" role="note"
                     style="color:#9fd3ff;font-size:0.95rem;margin-bottom:8px;line-height:1.45;">📡 ${words}</div>`;
    }

    // Group 65.1 (1b) (Derek, 2026-11-09: "we should have a charge the whole print, or a
    // way to change the percentage"): a card whose download kept its figures (an
    // ambiguous end, a cancel FCC saw after it lost contact, a restart's review) is
    // worked out again on the server at another basis. Charge the whole print only on a
    // ❓ card (`offerWhole`); the percentage on those and on a 🛑 card seen late. The box
    // is a weight box (a label scanned into it goes to the scan path); Enter in it works
    // it out and never applies. A card from before keeps its look.
    function hasFigures(rec) {
        return !!(rec && rec.figures && typeof rec.figures === 'object' && rec.figures.footer);
    }
    function basisPct(rec) {
        if (rec.basis === 'whole') return 100;
        if (typeof rec.basis === 'number') return rec.basis;
        // Group 65.1 (1c): an end FCC never sampled has no last percentage to offer.
        if (rec.kind === 'progress_unknown' || rec.unmeasured_was) return '';
        return Math.round((Number(rec.progress) || 0) * 1000) / 10;
    }
    // Group 65.1 (1c): figures for every percent, or only the footer (a file whose
    // moves FCC can't read: Charge the whole print only).
    function hasPercents(rec) {
        const b = rec && rec.figures && rec.figures.by_pct;
        return !!(b && typeof b === 'object' && Object.keys(b).length);
    }
    function basisWords(rec) {
        const seen = Math.round((Number(rec.seen_progress != null ? rec.seen_progress : rec.progress) || 0) * 100);
        if (rec.basis === 'whole') return `for the whole print (FCC last saw ~${seen}%)`;
        if (typeof rec.basis === 'number') return `at ${fmt(rec.basis)}% (FCC last saw ~${seen}%)`;
        return `at the last progress FCC saw (~${seen}%)`;
    }
    function basisHtml(rec, offerWhole) {
        if (!hasFigures(rec)) return '';
        const id = `fcc-cr-pct-${String(rec.printer_name)}-${String(rec.job_id)}`.replace(/[^A-Za-z0-9_-]/g, '-');
        const said = rec.basis === 'whole' ? 'Worked out for the whole print.'
            : (typeof rec.basis === 'number' ? `Worked out at ${fmt(rec.basis)}%.` : '');
        const pct = basisPct(rec);
        const box = !hasPercents(rec) ? '' : `
                <label for="${id}" style="color:#ddd;margin:0;">How far it got:</label>
                <div class="input-group input-group-sm" style="width:auto;flex:none;">
                    <input type="text" inputmode="decimal" id="${id}" autocomplete="off"
                           class="form-control bg-dark text-white border-secondary fcc-cr-pct fcc-weight-box"
                           value="${pct === '' ? '' : fmt(pct)}" style="width:4.5rem;" placeholder="e.g. 62" />
                    <span class="input-group-text bg-dark text-light border-secondary">%</span>
                </div>
                <button type="button" class="btn btn-sm btn-outline-info fcc-cr-workout">Work it out</button>`;
        return `
            <div class="fcc-cr-basis" style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 10px 0;">
                ${offerWhole ? `<button type="button" class="btn btn-sm btn-outline-info fcc-cr-whole">Charge the whole print</button>` : ''}
                ${box}
                ${said ? `<span class="fcc-cr-basis-said" style="color:#9fd3ff;">${said}</span>` : ''}
            </div>`;
    }

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
            case 'compute_failed':
                return `FCC couldn't measure how much filament this print used — <b>its deduct
                   kept failing</b> for the whole time FCC kept trying (the Activity Log has the
                   error), so nothing was deducted. ${weigh}`;
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
        // Group 43.3: no_spool names no spool, so the user picks one per tool. A
        // print sliced for one head can run on another (chosen on the printer),
        // which FCC can't see; the picker offers the spools that were on the
        // printer's heads when it ended, the spools on them now, or any #id.
        // Hotfix 2026-11-11: a card whose lines carry notes (built from the
        // print-end read) says each line's reason under it, and leads neutrally.
        const words = headsWords(rec);
        const noted = Object.keys(rec.unresolved_notes || {}).length > 0;
        // Review fix: such a card's heads may well have had a spool (one that
        // changed during the print), so its header says what its banner says.
        // Group 65.1 (1c): a "couldn't measure" card FCC read the file for afterwards has
        // figures; worked out, it is a card to pick on that says what it was worked out at.
        const fromUnmeasured = isNoSpool && !!rec.unmeasured_was;
        const header = fromUnmeasured
            ? `❓ ${esc(rec.printer_name)} — ${total}g ${rec.basis === 'whole' ? 'for the whole print'
                : `at ${fmt(rec.basis)}%`}, spools to pick`
            : isNoSpool
            ? `⚠️ ${esc(rec.printer_name)} — ${total}g computed, ${noted ? 'spool not certain' : 'no spool bound'}`
            : `❓ ${esc(rec.printer_name)} — couldn't measure usage`;
        // Review fix: a line that is a set of spools asks for each one's grams.
        const keys = Object.keys(rec.usage_map || {});
        const sets = keys.filter((k) => isSetLine(rec, k)).length;
        const ask = !sets ? `<b>Pick the spool each head used</b>`
            : sets === keys.length ? `<b>Type the grams each spool used</b> (or put them all on one)`
            : `<b>Pick the spool each head used</b> (on a head with several spools, <b>type the grams each
               one used</b>)`;
        const banner = fromUnmeasured
            ? `FCC couldn't tell how far this print got, so it's worked out
               ${rec.basis === 'whole' ? '<b>for the whole print</b>' : `at <b>${fmt(rec.basis)}%</b>`}:
               <b>${total}g</b>. FCC didn't read the heads when it ended, so ${ask.charAt(0) === '<'
                ? ask.replace('<b>Pick', '<b>pick').replace('<b>Type', '<b>type') : ask}, then <b>Apply</b>.
               You can work it out again above. Or <b>Discard</b> if you've already trued it up.`
            : !isNoSpool && hasFigures(rec)
            ? `${unmeasuredBanner(rec)} ${hasPercents(rec)
                ? `FCC read the print's file afterwards: press <b>Charge the whole print</b> if it finished, or
                   type how far it got and press <b>Work it out</b>, then pick the spool each head used.`
                : `FCC can't read this file's moves, but its slicer total is known: press <b>Charge the whole
                   print</b> if it finished, then pick the spool each head used.`}`
            : isNoSpool && noted
            ? `FCC computed this print used <b>${total}g</b>, but isn't sure which spool it came from
               on the heads below. ${ask}, then <b>Apply</b>. Or
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
                 data-rev="${esc(rec.rev == null ? 0 : rec.rev)}"
                 data-ask-fixed="${askFixed(rec, kind) ? '1' : '0'}"
                 data-head-names="${esc(JSON.stringify(cardHeadNames(rec)))}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div style="font-weight:bold;color:${isNoSpool ? '#ffd27a' : '#7ec8ff'};">${header}</div>
                    <div style="color:#9aa;font-size:0.92rem;">${isNoSpool ? total + 'g' : 'unmeasured'}</div>
                </div>
                <div style="color:#9aa;font-size:0.9rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                ${lostContactHtml(rec, !isNoSpool || !!rec.ambiguous)}
                <div style="color:#e6c074;font-size:0.95rem;margin-bottom:10px;line-height:1.45;
                            background:#221d12;border:1px solid #3a2f17;border-radius:4px;padding:9px 11px;">
                    ${banner}
                </div>
                ${isNoSpool ? basisHtml(rec, !!rec.ambiguous || fromUnmeasured) : basisHtml(rec, true)}
                ${lines}
                <div style="display:flex;flex-direction:row-reverse;justify-content:flex-start;gap:8px;margin-top:10px;">
                    ${applyBtn}
                    <button type="button" class="btn btn-sm btn-outline-secondary fcc-cr-discard"
                            data-armed="0"
                            title="Permanently drop this review — the spool is NOT deducted">🗑️ Discard</button>
                </div>
            </div>`;
    }

    function cardHtml(rec) {
        const kind = rec.kind || 'partial';
        const pct = Math.round((Number(rec.progress) || 0) * 100);
        if (kind === 'no_spool' || kind === 'progress_unknown') return unresolvedCardHtml(rec, kind);
        if (kind === 'shortfall') return shortfallCardHtml(rec);
        const rows = rowsHtml(rec);
        // Review fix: the header's total is the card's whole print, its rows and its
        // held lines, as the record's total and its Activity Log line say (a card
        // from before 43.4 has no held lines: its rows alone, as before).
        const heldKeys = Object.keys(rec.unresolved_usage || {});
        const heldG = heldKeys.reduce((a, k) => a + (Number(rec.unresolved_usage[k]) || 0), 0);
        const total = (rec.spools || []).reduce((a, s) => a + (Number(s.grams) || 0), 0) + heldG;
        // Review fix: a held line that is a set of spools asks for each one's grams,
        // and an auto-split card with a head still to fill in never says "Just Confirm".
        const heldSets = heldKeys.filter((k) => isSetLine(rec, k)).length;
        const pickWords = !heldSets ? `<b>Pick the spool it used</b> (or weigh them and nudge the grams)`
            : heldSets === heldKeys.length ? `<b>Type the grams each spool used</b> (or put them all on one)`
            : `<b>Pick the spool it used</b> (on a head with several spools, <b>type the grams each one used</b>)`;
        const confirmWords = heldKeys.length === 1
            ? `One head listed below still needs your grams: fill it in, then <b>Confirm</b>.`
            : heldKeys.length > 1
            ? `The ${heldKeys.length} heads listed below still need your grams: fill them in, then <b>Confirm</b>.`
            : `Just <b>Confirm</b>, or nudge if you weighed it.`;
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
        // Round 2's review: the words count the spools. A held head can list more
        // than two, and a head split at two swaps or more has more than one run-out
        // spool; one swap and two spools keep their words.
        const heldNone = held && heldKeys.some((k) => heldSpoolCount(rec, k) > 2) ? 'none of them' : 'neither';
        const cut = autoSplit && splitMostRows(rec) > 2
            ? { by: 'the swap points', rows: 'each run-out spool up to its swap, the next spool after it',
                own: "Each run-out spool's" }
            : { by: 'the swap point', rows: 'the run-out spool up to the swap, the replacement after it',
                own: "The run-out spool's" };
        if (spoolChanged) {
            headerColor = '#ffb74d';
            header = `🔁 ${esc(rec.printer_name)} — spool changed mid-print`;
            banner = held
                ? `🔁 A spool feeding this print was <b>changed mid-print</b> at position(s)
               <b>${esc(changedPos)}</b>, so the slicer total was <b>NOT auto-applied</b>. FCC can't tell
               which spool printed there, so it charges ${heldNone} by itself: each such head is listed
               below with every spool it had. ${pickWords}, then <b>Confirm</b>. Or <b>Discard</b>.`
                : autoSplit
                ? `🔁 A spool feeding this print was <b>changed mid-print</b> (a filament run-out
               or M600) at toolhead position(s) <b>${esc(changedPos)}</b>. FCC <b>auto-split</b>
               the slicer total by ${cut.by} — each row below is charged only <b>its own
               segment</b> (${cut.rows}), pre-filled.
               ${confirmWords} ${cut.own} sensor→nozzle
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
            const worked = rec.basis === 'whole' ? 'worked out for the whole print'
                : (typeof rec.basis === 'number' ? `worked out at ${fmt(rec.basis)}%` : '');
            header = ambiguous
                ? `❓ ${esc(rec.printer_name)} — ${worked || `ended at ~${pct}%`} (couldn't confirm: completed or cancelled?)`
                : `🛑 ${esc(rec.printer_name)} — ${worked || `cancelled at ~${pct}%`}`;
            banner = ambiguous && hasFigures(rec)
                ? `❓ FCC couldn't tell whether this print <b>finished</b> or was <b>cancelled</b> — it
                   reached idle without a clear cancel/finish signal. The grams below are worked out
                   ${esc(basisWords(rec))}. If it finished, press <b>Charge the whole print</b>; if you saw
                   how far it got, type that percentage and press <b>Work it out</b>. You can still nudge
                   each spool's grams. <b>Confirm</b> to deduct, or <b>Discard</b> if it was already handled.`
                : ambiguous
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
                 data-rev="${esc(rec.rev == null ? 0 : rec.rev)}"
                 data-ask-fixed="${askFixed(rec, kind) ? '1' : '0'}"
                 data-head-names="${esc(JSON.stringify(cardHeadNames(rec)))}"
                 style="border:1px solid #444;border-radius:6px;padding:10px 12px;margin-bottom:12px;background:#17181b;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
                    <div style="font-weight:bold;color:${headerColor};">${header}</div>
                    <div style="color:#9aa;font-size:0.92rem;">${fmtG(total)}g total</div>
                </div>
                <div style="color:#9aa;font-size:0.9rem;margin-bottom:8px;word-break:break-all;">${esc(rec.filename)}</div>
                ${lostContactHtml(rec, ambiguous)}
                <div style="color:#e6c074;font-size:0.95rem;margin-bottom:10px;line-height:1.45;
                            background:#221d12;border:1px solid #3a2f17;border-radius:4px;padding:9px 11px;">
                    ${banner}
                </div>
                ${(ambiguous || rec.lost_contact) ? basisHtml(rec, ambiguous) : ''}
                ${rows}
                ${unresolvedLinesHtml(rec)}
                <div style="display:flex;flex-direction:row-reverse;justify-content:flex-start;gap:8px;margin-top:10px;">
                    <button type="button" class="btn btn-sm btn-success fw-bold fcc-cr-confirm">Confirm deduct</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary fcc-cr-discard"
                            data-armed="0"
                            title="Permanently drop this review — the spool is NOT deducted">🗑️ Discard</button>
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
                <div id="fcc-cr-panel-notice" role="status" aria-live="polite"
                     style="display:none;margin:4px 18px 0;color:#e6c074;font-size:var(--fcc-fs-small);line-height:1.4;
                            background:#221d12;border:1px solid #3a2f17;border-radius:4px;padding:7px 10px;"></div>
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
        // 2026-06-12, "in case the activity log isn't always visible"). Since
        // Group 50.1 in the group's own count slot, after the printer's name and
        // state; a count that comes or goes measures the strip again (it may no
        // longer fit beside the title, or fit again).
        let stripChanged = false;
        document.querySelectorAll('.fcc-ps-header-chips .fcc-ps-printer-group[data-printer]').forEach((grp) => {
            const host = grp.querySelector('.fcc-ps-strip-count') || grp;
            if (apply(host, grp.getAttribute('data-printer'))) stripChanged = true;
        });
        if (stripChanged && typeof window.fitPrinterStatusStrip === 'function') window.fitPrinterStatusStrip();
        return changed;
    }
    async function refreshBadge() {
        const pending = await fetchPending();
        // Group 64 fix review 4 (UP7): a list FCC couldn't read keeps the last counts
        // (Group 52: a read that failed says so, never "empty"), the pill's tooltip
        // saying why, instead of hiding every 🛑 until a read works again.
        const badge = document.getElementById('cancel-review-badge');
        if (badge && badge.dataset.titleWas == null) badge.dataset.titleWas = badge.getAttribute('title') || '';
        if (pendingReadFailed) {
            if (badge) {
                badge.dataset.read = 'failed';
                badge.setAttribute('title', `${badge.dataset.titleWas} (FCC couldn't read the review list just now: `
                    + 'this count is from its last read)');
                // Derek, 2026-11-23 (the walk's sample (d)): the title bar counts' stale
                // look, a "?" after the count and a dashed edge (global.css), so the count
                // reads as possibly wrong; the tooltip still says why.
                if (!badge.querySelector('.fcc-cr-stale-mark')) {
                    const q = document.createElement('span');
                    q.className = 'fcc-cr-stale-mark';
                    q.setAttribute('aria-hidden', 'true');
                    q.textContent = '?';
                    badge.appendChild(q);
                }
            }
            return;
        }
        if (badge) {
            delete badge.dataset.read;
            badge.setAttribute('title', badge.dataset.titleWas);
            const q = badge.querySelector('.fcc-cr-stale-mark');
            if (q) q.remove();
        }
        applyBadges(pending);
    }

    // The open review's scan-buffer listener (scope D), so a review opened again
    // over an open one leaves only its own listening.
    let _offBuffer = null;

    // A scan read while the keyboard is in a grams box (where the review starts)
    // goes to the scan path, as it does from the rest of the card (hotfix
    // 2026-11-11: a label's digits were typed into the grams, "ID:229" making #42's
    // 30 g read 30229 g). Group 64.2 (11): the boxes are weight boxes
    // (`fcc-weight-box`), so inv_core.js's one weight capture serves them as every
    // other: a label from its ':' at any speed (a slower scanner's digits went into
    // the grams under the old field capture, which caught only a scan ending
    // within 150 ms), digits faster than a person types, the box put back as it
    // was before the scan with an `input` event, so its preview and its set's
    // count follow. Enter in a box still presses nothing.

    async function openCancelReview() {
        const pending = await fetchPending();
        if (!pending.length) {
            if (pendingReadFailed) {
                // Group 64 fix review 4 (UP7): a list FCC couldn't read is no "no reviews",
                // and the counts stay as they were.
                toast("FCC couldn't read the review list just now, so it can't be shown. Try again in a moment.",
                    'warning', 7000);
                return;
            }
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
            if (!rec && pendingReadFailed) {
                // TP6: the list couldn't be read: the card stays as it was drawn, its Apply
                // usable again (the server checks it: its revision, a row no longer on it,
                // a retry by its attempt), rather than taken off the panel while the server
                // still holds it.
                const btn = card.querySelector('.fcc-cr-confirm');
                if (btn) btn.disabled = false;
                // Group 64 fix review 4 (UP2): marked, so its words say it may be out of
                // date (sayOnCard) and its next Apply reads the list again first.
                card.dataset.stale = '1';
                return card;
            }
            if (!rec) { card.remove(); updateCount(); refreshBadge(); closeIfEmpty(); return null; }
            if (freshHeads) liveHeads[printer] = await fetchCandidates(printer);
            const tmp = document.createElement('div');
            tmp.innerHTML = cardHtml(rec).trim();
            const fresh = tmp.firstElementChild;
            card.replaceWith(fresh);
            if (liveHeads[printer]) withHeads(fresh, liveHeads[printer]);
            const first = fresh.querySelector('.fcc-cr-pick, .fcc-cr-grams');
            if (first) { try { first.focus(); } catch (_) { /* noop */ } }
            return fresh;
        }
        // Say on the card (review fix) and in a toast: the toast layer is drawn
        // under the review panel. A card drawn again is told on its new self.
        function tell(card, msg, type, dur) {
            sayOnCard(card, headPieces(card, msg));
            toast(msg, type || 'warning', dur || 7000);
        }

        // Group 65.1 (1b): work the card out again on the server, for the whole print or
        // at the percentage in its box, and draw it again as FCC holds it now (its
        // revision one up, so a view drawn before can't apply). Nothing is charged here.
        async function recompute(card, whole) {
            if (card.dataset.recomputing === '1') return;
            const box = card.querySelector('.fcc-cr-pct');
            const payload = { printer_name: card.dataset.printer, job_id: card.dataset.job,
                              rev: Number(card.dataset.rev || 0) };
            if (whole) {
                payload.whole = true;
            } else {
                const typed = box ? String(box.value).trim().replace(/\s*%$/, '') : '';
                const n = Number(typed);
                if (!typed || !Number.isFinite(n) || n < 0 || n > 100) {
                    tell(card, 'Type how far the print got, from 0 to 100 %, then press Work it out.');
                    if (box) { try { box.focus(); box.select(); } catch (_) { /* noop */ } }
                    return;
                }
                payload.percent = n;
            }
            card.dataset.recomputing = '1';
            const btns = Array.from(card.querySelectorAll('.fcc-cr-whole, .fcc-cr-workout, .fcc-cr-confirm'));
            btns.forEach((b) => { b.disabled = true; });
            let d = null;
            try {
                const r = await fetch('/api/cancel_deduct/recompute', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                d = await r.json();
            } catch (_) { d = null; }
            delete card.dataset.recomputing;
            if (d && d.status === 'already_handled') {
                await rerenderCard(card);
                toast('That card was already settled: nothing more to work out on it.', 'info');
                if (body.querySelector('.fcc-cr-card')) sayOnPanel('That card was already settled: nothing more to work out on it.');
                return;
            }
            if (d && (d.status === 'recomputed' || d.stale)) {
                const fresh = await rerenderCard(card);
                if (fresh) {
                    const back = fresh.querySelector(whole ? '.fcc-cr-whole' : '.fcc-cr-pct') || fresh.querySelector('.fcc-cr-pct');
                    if (back) { try { back.focus(); } catch (_) { /* noop */ } }
                    sayOnCard(fresh, d.stale ? (d.msg || 'This card changed since it was drawn: it is drawn again as it is now.')
                        : (whole ? 'Worked out for the whole print: check the grams, then Confirm.'
                            : `Worked out at ${fmt(payload.percent)}%: check the grams, then Confirm.`));
                }
                // The redraw put new buttons where the pointer is: a double click's second
                // press reaches nothing (Group 58's rule).
                if (typeof window.fccShieldNextPress === 'function') window.fccShieldNextPress();
                return;
            }
            btns.forEach((b) => { b.disabled = false; });
            tell(card, (d && d.msg) || "FCC didn't answer, so the card wasn't worked out again. Try again in a moment.");
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
        // Group 64 full review (PI1): a Confirm or a Discard takes its card away; when
        // another card keeps the panel up, its outcome is said here too, since the
        // toast layer is drawn under the panel. Cleared at the next press.
        function sayOnPanel(msg) {
            const n = overlay.querySelector('#fcc-cr-panel-notice');
            if (!n) return;
            n.textContent = msg || '';
            n.style.display = msg ? '' : 'none';
        }
        // A toast, and the same words kept for the panel's line.
        function toastAndKeep(said, msg, type, dur) {
            toast(msg, type, dur);
            said.push(msg);
        }

        // Scope B: a held set's count of the grams still to place follows its boxes.
        function updateSetLeft(input) {
            const box = input.closest && input.closest('.fcc-cr-heldset');
            const out = box && box.querySelector('.fcc-cr-set-left');
            if (!out) {
                // Round 2's review: a plain held line's grams count in the set
                // check's Yes when its press charges nothing there, so a change in
                // them ends its wait too.
                endSetAsk(input.closest && input.closest('.fcc-cr-card'));
                return;
            }
            let placed = 0;
            box.querySelectorAll('.fcc-cr-pgrams').forEach((b) => {
                const g = parseFloat(b.value);
                if (g > 0) placed += g;
            });
            out.textContent = setLeftWords(Number(out.dataset.total), placed);
            // Review fix: what an Apply said about the grams as they were goes once
            // they change (the next Apply checks them again). Round 2 (R1): every
            // set's words go, and the button says its own words again.
            endSetAsk(box.closest('.fcc-cr-card'));
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
                // Round 2's review: whether a plain held line is charged decides
                // what the set check's Yes leaves, so a new pick there ends its wait.
                const held = t.closest('.fcc-cr-unline, .fcc-cr-pickline');
                if (held && !held.classList.contains('fcc-cr-setline')) endSetAsk(card);
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
        // Group 64.2 (4): a scan with the keyboard on a picker (a closed <select>)
        // picks that spool on its line. The dashboard's scan accumulator reads a
        // select's keys (it skips only an INPUT's), so a label scanned there went to
        // the scan path (the spool joined the scan buffer), and the select's own
        // typeahead moved the pick with the label's letters. The scan's Enter, read
        // as a scan when the buffer looks like one (looksLikeScanPayload: a ':' or
        // '/' in it) or came as a scanner burst, never reaches the accumulator (this
        // capture runs before it), and the line takes the scanned spool, whatever
        // the typeahead did: the picker's own option for it when it lists it, else
        // "Another spool by #ID…" with the label in its box, looked up as a typed
        // number is. A person's typeahead moves the select as ever; their Enter
        // after it goes on, however soon it comes (Group 64 review, O1: "#2" and a
        // quick Enter was in flight, isScanInFlight's 500 ms, and moved the line to
        // spool #2: a bare in-flight test is never a scan here).
        // Group 64 fix review (FP1): when each key typed on a picker came, so a
        // bare-number label (an old label with no prefix, "57") read at a scanner's
        // pace is still a scan: it has no ':' or '/', and two digits are never a
        // scanner burst. A person's typeahead goes slower, and the picker's options
        // all start with '#', so digits alone jump nowhere anyway.
        const pickKeys = { el: null, at: [] };
        const PICK_SCAN_GAP_MS = 80;
        // Group 65.1 (1b): Enter in the percentage box works the card out again and never
        // applies it. A scan's Enter is the scan's (the weight capture sends a label on to
        // the scan path, and enterIsAScan says so for the Enter after it).
        overlay.addEventListener('keydown', (e) => {
            const t = e.target;
            if (e.key !== 'Enter' || e.isComposing || !t || !t.classList || !t.classList.contains('fcc-cr-pct')) return;
            if (typeof window.enterIsAScan === 'function' && window.enterIsAScan()) return;
            e.preventDefault();
            e.stopPropagation();
            if (e.repeat) return;
            const card = t.closest('.fcc-cr-card');
            if (card) recompute(card, false);
        });
        overlay.addEventListener('keydown', (e) => {
            const t = e.target;
            if (!t || !t.classList || !t.classList.contains('fcc-cr-pick') || e.key === 'Enter') return;
            const now = Date.now();
            if (e.key.length !== 1 || e.ctrlKey || e.metaKey || e.altKey) { pickKeys.el = null; pickKeys.at = []; return; }
            const last = pickKeys.at[pickKeys.at.length - 1];
            if (pickKeys.el !== t || (last != null && now - last > PICK_SCAN_GAP_MS)) { pickKeys.el = t; pickKeys.at = []; }
            pickKeys.at.push(now);
        }, true);
        const bareLabelAtScannerPace = (t, buf) => {
            const text = String(buf || '').trim();
            const keys = pickKeys.at;
            if (!/^#?\d+$/.test(text) || pickKeys.el !== t || keys.length !== text.length) return false;
            for (let i = 1; i < keys.length; i += 1) if (keys[i] - keys[i - 1] > PICK_SCAN_GAP_MS) return false;
            return Date.now() - keys[keys.length - 1] <= PICK_SCAN_GAP_MS;
        };
        overlay.addEventListener('keydown', (e) => {
            const t = e.target;
            if (e.key !== 'Enter' || e.isComposing || !t || !t.classList || !t.classList.contains('fcc-cr-pick')) return;
            // inv_core.js's `let state` is a script-global binding, not a window
            // property: read it by name, as the buffer list above does.
            const st = (typeof state !== 'undefined') ? state : window.state;
            const buf = st && typeof st.scanBuffer === 'string' ? st.scanBuffer : '';
            const bare = bareLabelAtScannerPace(t, buf);
            pickKeys.el = null; pickKeys.at = [];
            if (!buf.trim() || !((window.looksLikeScanPayload && window.looksLikeScanPayload(buf.trim()))
                    || (window.isScannerBurst && window.isScannerBurst()) || bare)) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (st) st.lastScanEnterAt = Date.now();     // as the accumulator marks a scan's Enter
            if (window.clearScanBuffer) window.clearScanBuffer();
            const card = t.closest('.fcc-cr-card');
            if (card) pickByScan(card, t, buf);
        }, true);
        // The scanned spool on the picker's line: its own option, or the #ID box.
        function pickByScan(card, sel, text) {
            const got = readSpoolBox(text);
            const own = got.sid != null && Array.from(sel.options || []).find((o) => o.value === String(got.sid));
            if (own) {
                sel.value = String(got.sid);
            } else {
                const box = card.querySelector(`.fcc-cr-other[data-line="${CSS.escape(String(sel.dataset.line))}"]`);
                if (!box) return;
                box.value = String(text).trim();
                sel.value = 'other';
            }
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
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
            btn.dataset.armedAt = '';
            btn.textContent = '🗑️ Discard';
            btn.classList.remove('btn-outline-danger');
            btn.classList.add('btn-outline-secondary');
        }

        // Leaving an armed Discard disarms it (Group 50 review).
        body.addEventListener('focusout', (e) => {
            const btn = e.target;
            if (btn && btn.classList && btn.classList.contains('fcc-cr-discard') && btn.dataset.armed === '1') disarmDiscard(btn);
        });

        body.addEventListener('click', async (e) => {
            const card = e.target.closest('.fcc-cr-card');
            if (!card) return;
            const printer = card.dataset.printer;
            const job = card.dataset.job;

            if (e.target.classList.contains('fcc-cr-whole') || e.target.classList.contains('fcc-cr-workout')) {
                // Group 65.1 (1b): a double click's second press works nothing out again
                // (a press from the keyboard has detail 0).
                if (e.detail > 1) return;
                sayOnPanel('');
                await recompute(card, e.target.classList.contains('fcc-cr-whole'));
                return;
            }

            if (e.target.classList.contains('fcc-cr-confirm')) {
                if (e.detail <= 1) sayOnPanel('');
                // Group 64 review (R1): a double click's second press is no Apply. Its
                // first applied this card and took it away, the next card slid up
                // under the pointer, and the second press applied that one, unread
                // (a press from the keyboard has detail 0).
                if (e.detail > 1) return;
                // Group 64 fix review 4 (UP2): a card kept as drawn after a list FCC couldn't
                // read is read again before anything is posted: drawn again as FCC holds it
                // (its next Apply posts what that shows), or still said to be unread. Posted
                // as drawn, a spool an earlier Apply had charged read as a failure.
                if (card.dataset.stale === '1') {
                    e.target.disabled = true;
                    const fresh = await rerenderCard(card, true);
                    if (fresh && fresh !== card) {
                        sayOnCard(fresh, 'Drawn again as FCC holds this card now: check it, then Apply.');
                    } else if (fresh) {
                        sayOnCard(card, '');
                        toast(STALE_CARD_WORDS, 'warning', 7000);
                    } else {
                        toast('That card was already settled: nothing more to apply on it.', 'info');
                        if (body.querySelector('.fcc-cr-card')) sayOnPanel('That card was already settled: nothing more to apply on it.');
                    }
                    return;
                }
                // 43.3: explicit picks become `charges`; a card whose rows all keep
                // their own spool still sends the old `updates` shape.
                const payload = { printer_name: printer, job_id: job };
                sayOnCard(card, '');
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
                    // Round 2's review: a press refused here ends the set check's
                    // wait first, so the button reads its own words again (the
                    // refusals name them) and no set's words promise a press that
                    // can't go ahead; the next press asks again.
                    if (noId != null) {
                        endSetAsk(card);
                        tell(card, `Type the #id of the spool T${noId} used (or pick one).`);
                        return;
                    }
                    if (!charges.length) {
                        // Review fix: a set's lines already name their spools, so
                        // what is missing there is each spool's grams.
                        const sets = Array.from(card.querySelectorAll('.fcc-cr-heldset'))
                            .map((b) => b.dataset.where || `T${b.dataset.pos}`);
                        const plain = card.querySelectorAll('.fcc-cr-pickline:not(.fcc-cr-setline)').length > 0;
                        endSetAsk(card);
                        tell(card, sets.length
                            ? `Type the grams each spool on ${sets.join(' and ')} used (or put them all on one)`
                              + `${plain ? ', and pick the spool each other head used' : ''}, then Apply. `
                              + `Or Discard the review.`
                            : 'Pick the spool this print used (or type its #id) first.');
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
                        endSetAsk(card);
                        tell(card, 'Type the #id of the spool to charge (or pick one).');
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
                        endSetAsk(card);
                        tell(card, `Type the #id of the spool T${unNoId} used (or pick one).`);
                        return;
                    }
                    // 43.2: a shortfall card names no spool of its own, so an Apply
                    // with nothing picked would charge nothing (the server refuses it too).
                    // Decision 1 (Group 64): a card whose every line is a spool weighed
                    // (or changed) after its print, each left at 0 g, settles with
                    // nothing charged: the scale counted the print.
                    // Group 64 review (O3): the lines left without a pick count, so a
                    // card with a pick for one line and a weighed line left at 0 g
                    // settles that line in the same Apply (settle_held beside the
                    // picks), instead of keeping it and asking for a spool for grams
                    // the scale already counted.
                    const shortLines = Array.from(card.querySelectorAll('.fcc-cr-shortline'));
                    const pickedPos = new Set(charges.filter((c) => c.position != null).map((c) => String(c.position)));
                    const leftLines = shortLines.filter((ln) => !pickedPos.has(String(ln.dataset.pos)));
                    // Group 64 full review (FX6): a pick an earlier Apply held stays on the
                    // card as a row marked weighed; left at 0 g it settles as such a line
                    // does (any other row, a failed write's retry, still needs its Apply).
                    const cardRows = Array.from(card.querySelectorAll('.fcc-cr-row'));
                    const rowsAt0 = cardRows.every((r) => r.dataset.weighed === '1'
                        && !(parseFloat((r.querySelector('.fcc-cr-grams') || {}).value) > 0));
                    const settleLeft = card.dataset.kind === 'shortfall' && (leftLines.length > 0 || cardRows.length > 0)
                        && rowsAt0
                        && leftLines.every((ln) => ln.dataset.weighed === '1'
                            && !(parseFloat((ln.querySelector('.fcc-cr-pgrams') || {}).value) > 0));
                    const settleHeld = settleLeft && !redirected && !Object.keys(updates).length;
                    if (settleHeld) {
                        payload.settle_held = true;
                        payload.charges = [];
                    } else if (card.dataset.kind === 'shortfall' && !redirected && !Object.keys(updates).length) {
                        endSetAsk(card);
                        tell(card, 'Pick the spool that took these grams (or Discard).');
                        return;
                    }
                    if (!settleHeld) { if (redirected) payload.charges = charges; else payload.updates = updates; }
                    if (settleLeft && redirected) payload.settle_held = true;
                }
                // 43.2: the card's revision, so an Apply from a view opened before
                // another Apply changed it is refused instead of charging again. Every
                // card since the Group 64 full review (FX7): a hold keeps a card too, and
                // a view drawn before it charged the held row's old grams on top.
                payload.rev = Number(card.dataset.rev || 0);
                // Review fix: a set whose boxes don't add up to its grams (left
                // empty, part placed, or over) is said in the set and on the card;
                // a second press with the same grams goes ahead (never a double
                // click's second press).
                if (!setsConfirmed(card, e)) return;
                // Group 64.2 (2): a set whose grams don't add up goes out only after
                // its question, and says what the person saw (the server checks it).
                const acked = setProblems(card);
                if (acked.length) {
                    payload.set_ack = {};
                    acked.forEach((p) => { payload.set_ack[String(p.box.dataset.pos)] = p.placed; });
                }
                e.target.disabled = true;
                try {
                    const r = await fetch('/api/cancel_deduct/confirm', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload),
                    });
                    const d = await r.json();
                    const took = (d.applied || []).reduce((a, x) => a + (Number(x.grams) || 0), 0);
                    // Group 64 review (O4 / Y2): the weighed spools this Apply left
                    // uncharged are said by name, in the words of what FCC knows
                    // (weighed on FCC after the print, or a change it can't place).
                    // Fix review 4 (US1 / US3): an Apply whose write failed settles them
                    // too, so they are said beside a hold or a failure as well.
                    const left = Array.isArray(d.left_weighed) ? d.left_weighed : [];
                    const leftG = left.reduce((a, l) => a + (Number(l.grams) || 0), 0);
                    const leftWho = spoolListWords(left.map((l) => l.sid));
                    const leftWords = !left.length ? ''
                        : (d.settled_unsure
                            ? `left ${fmtG(leftG)}g uncharged on ${leftWho} as set: `
                              + `${left.length > 1 ? 'their weights' : 'its weight'} changed after the print`
                            : `left ${fmtG(leftG)}g uncharged on ${leftWho}: `
                              + `${left.length > 1 ? 'they were' : 'it was'} weighed after the print`);
                    const leftTail = leftWords ? ` ${leftWords.charAt(0).toUpperCase()}${leftWords.slice(1)}.` : '';
                    // Fix review 4 (UP1): a refused write in words (spoolman_api.refusal_words),
                    // never Spoolman's raw answer; FCC's own sentences have no `words`.
                    const errWords = (x) => String((x && (x.words || x.error)) || 'failed');
                    if (d.status === 'confirmed' && d.kept) {
                        // 43.2: the picks couldn't take everything (a run-out or
                        // near-empty spool); the rest stays on the card to pick again.
                        // Group 64 fix review (FS2): the card's weighed lines (kept_weighed)
                        // wait at what it filled in; they are no grams with no spool.
                        const kw = Array.isArray(d.kept_weighed) ? d.kept_weighed : [];
                        const kwG = kw.reduce((a, l) => a + (Number(l.grams) || 0), 0);
                        const other = Math.max(0, (Number(d.shortfall_g) || 0) - kwG);
                        const parts = [`Charged ${fmtG(took)}g.`];
                        if (other > 0.05 || !kw.length) parts.push(`${fmtG(other)}g still have no spool — pick another spool, or Discard.`);
                        if (kw.length) {
                            parts.push(`${fmtG(kwG)}g on ${spoolListWords(kw.map((l) => l.sid))}, `
                                + (kw.every((l) => l.known_order)
                                    ? 'weighed after the print, stay on the card: Apply again to leave them uncharged, or Discard.'
                                    : 'whose weight changed after the print, stay on the card: check them, then Apply again or Discard.'));
                        }
                        const msg = parts.join(' ');
                        toast(msg, 'warning', 7000);
                        const kept = await rerenderCard(card, true);
                        sayOnCard(kept, headPieces(kept, msg));
                        refreshBadge();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                    } else if (Array.isArray(d.held) && d.held.length) {
                        // Group 64 full review: a spool weighed (or changed) after the
                        // card was shown is charged nothing; the card stays, its line
                        // marked and filled in again, for the person to look again. A
                        // hold with nothing else applied answers status 'error' (FX3: it
                        // read as a failed Apply); a write that failed beside it is said too.
                        const why = d.held.map((h) => h.words + '.').join(' ');
                        const heldSids = new Set(d.held.map((h) => String(h.sid)));
                        // Fix review 4 (UP2): a stale card's "not in this review" is no failure.
                        const failed = (d.errors || []).filter((x) => !heldSids.has(String(x.sid))
                            && x.error !== 'not in this review');
                        const failWords = failed.length ? ` ${failed.length} other spool(s) failed — check the log.` : '';
                        // Group 64 fix review 2 (CP5): the spools this Apply charged leave
                        // the redrawn card; the card's own line says so, as a kept card's does.
                        // Group 64 fix review 3 (TP7): a spool that took 0 g (its record at
                        // 0 g) is said as such, never named as charged.
                        const took0 = (d.applied || []).filter((a) => !(Number(a.grams) > 0));
                        const tookSome = (d.applied || []).filter((a) => Number(a.grams) > 0);
                        const chargedWords = (tookSome.length
                            ? `Charged ${fmtG(took)}g to ${spoolListWords(tookSome.map((a) => a.sid))}. ` : '')
                            + (took0.length === 1 ? `#${took0[0].sid}'s record was at 0 g, so nothing was charged to it. `
                                : took0.length ? `The records of ${spoolListWords(took0.map((a) => a.sid))} were at 0 g, so nothing was charged to them. ` : '');
                        toast(`${chargedWords}${why} Nothing was charged to it: check its line and Apply again.${failWords}${leftTail}`,
                            failed.length ? 'error' : 'warning', 7000);
                        const fresh = await rerenderCard(card, true);
                        sayOnCard(fresh, headPieces(fresh, `${chargedWords}${why} Nothing was charged to it: check its line and Apply again.${failWords}${leftTail}`));
                        refreshBadge();
                        document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                    } else if (d.status === 'confirmed') {
                        const said = [];
                        if (took > 0) {
                            toastAndKeep(said, `Deducted from ${(d.applied || []).length} spool(s)${leftWords ? `; ${leftWords}` : ''}.`, 'success');
                        } else if (leftWords) {
                            toastAndKeep(said, `${leftWords.charAt(0).toUpperCase()}${leftWords.slice(1)}.`, 'success');
                        } else if (d.settled_held) {
                            toastAndKeep(said, `Left ${fmtG(d.shortfall_g)}g uncharged: the spool was weighed after the print.`, 'success');
                        } else {
                            toastAndKeep(said, 'Nothing was charged: the spool picked has 0 g left on record.', 'warning', 7000);
                        }
                        if (d.shortfall_card) {
                            // 43.2: what the picked spools couldn't take is on a new card.
                            // Group 64 fix review 3 (TP8): the new card's own grams, never the
                            // weighed spools' named just above as left uncharged.
                            toastAndKeep(said, `${fmtG(d.shortfall_card_g != null ? d.shortfall_card_g : d.shortfall_g)}g couldn't be charged to the spool picked — they're on a new card: pick another spool, or Discard.`, 'warning', 7000);
                        }
                        // Fix review 4 (UP3): the rest of the shortfall (a head nobody picked)
                        // is said beside a new card too, less that card's own grams (an older
                        // FCC's answer, with no shortfall_card_g, says only the card's).
                        const unplaced = Number(d.shortfall_g) - (Number(d.left_in_shortfall_g) || 0)
                            - (d.shortfall_card ? (Number(d.shortfall_card_g) || 0) : 0);
                        if (!d.settled_held && (!d.shortfall_card || d.shortfall_card_g != null) && unplaced > 0.05) {
                            // A settle's grams were left on purpose (Group 64 review, Y2), and so
                            // were the weighed spools' named above (Group 64 fix review 2, CS4:
                            // said twice, once as left uncharged and once as "couldn't be applied").
                            // Partial-bind / clamp shortfall (no_spool re-resolve path): part of the
                            // computed usage couldn't be applied — surface it AT THE OVERLAY, not only
                            // in the Activity Log, so the user knows to weigh the still-short spool.
                            // Group 64 fix review 3 (TP1): the server says what of the shortfall
                            // the weighed spools account for (left_in_shortfall_g); on a card's
                            // first Apply a weighed row left at 0 g was never in it, and taking its
                            // grams off hid an unpicked head's.
                            toastAndKeep(said, `${fmtG(unplaced)}g couldn't be applied — weigh that spool to true up.`, 'warning', 7000);
                        }
                        // Group 64 fix review 2 (CP7): a write that failed on a spool of this
                        // card was re-queued by the server (a 43.6 retry row), so the card
                        // stays: drawn again with both outcomes on it. Only a stale card's
                        // "not in this review" leaves nothing to retry.
                        const retrying = (d.errors || []).filter((x) => x && x.error !== 'not in this review');
                        if (retrying.length) {
                            // Group 64 fix review 3 (TP2): each spool's own words (a write
                            // Spoolman refused, a weight that changed since the last try, a spool
                            // gone), never one sentence for all of them.
                            const why = retrying.map((x) => `#${x.sid} (${errWords(x).replace(/[.\s]+$/, '')})`).join('; ');
                            toastAndKeep(said, `Not charged: ${why}. The card stays: check it, then Apply again or Discard.`, 'error', 7000);
                            const fresh = await rerenderCard(card);
                            if (fresh) sayOnCard(fresh, headPieces(fresh, said.join(' ')));
                            // TP6: the list couldn't be read (the card is drawn again at the next
                            // open): the words go on the panel while another card keeps it up.
                            else if (body.querySelector('.fcc-cr-card')) sayOnPanel(said.join(' '));
                            refreshBadge();
                            document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                        } else {
                            // Fix review 4 (UP2): every error left here is a spool no longer on this
                            // card ("not in this review": an earlier Apply settled it), no failure.
                            const gone = (d.errors || []).filter((x) => x && x.error === 'not in this review');
                            if (gone.length) {
                                const them = gone.length > 1 ? 'them' : 'it';
                                toastAndKeep(said, `${spoolListWords(gone.map((x) => x.sid))} ${gone.length > 1 ? 'were' : 'was'} `
                                    + `no longer on this card (an earlier Apply settled ${them}): nothing more was charged to ${them}.`, 'info');
                            }
                            // R1: the card under the pointer goes, so the second press of a
                            // double click reaches nothing behind it.
                            if (window.fccShieldNextPress) window.fccShieldNextPress();
                            card.remove(); updateCount(); refreshBadge();
                            if (d.shortfall_card) await showNewCard(printer, d.shortfall_card);
                            // PI1: another card keeps the panel up: its words are said on it too.
                            if (body.querySelector('.fcc-cr-card')) sayOnPanel(said.join(' '));
                            closeIfEmpty();
                            document.dispatchEvent(new CustomEvent('inventory:sync-pulse', { detail: { source: 'cancel_review' } }));
                        }
                    } else if (d.stale) {
                        // 43.2: another Apply changed this card since it was shown.
                        const msg = d.msg || 'This card changed — check it and Apply again.';
                        toast(msg, 'warning', 7000);
                        const fresh = await rerenderCard(card, true);
                        sayOnCard(fresh, headPieces(fresh, msg));
                    } else if (d.status === 'already_handled') {
                        toast('Already handled elsewhere.', 'info');
                        if (window.fccShieldNextPress) window.fccShieldNextPress();
                        card.remove(); updateCount(); refreshBadge();
                        // Group 64 fix review 2 (CP3): said on the panel too, as a Discard's is.
                        if (body.querySelector('.fcc-cr-card')) sayOnPanel('Already handled elsewhere.');
                        closeIfEmpty();
                    } else if (d.status === 'still_no_spool' || d.status === 'manual_only') {
                        // Not applied, but the review is kept server-side — LEAVE the
                        // card so the user can bind a spool / weigh, then retry Apply.
                        e.target.disabled = false;
                        tell(card, d.msg || 'Not applied — still no spool bound.');
                    } else {
                        e.target.disabled = false;
                        const e0 = (d.errors || [])[0];
                        const why = (d.msg || (e0 ? errWords(e0) : '') || 'Confirm failed — check the log.') + leftTail;
                        tell(card, why, 'error');
                        // Writes that failed leave a reshaped review: show what it holds now.
                        if ((d.errors || []).length) {
                            const fresh = await rerenderCard(card);
                            sayOnCard(fresh, headPieces(fresh, why));
                        }
                    }
                } catch (err) {
                    e.target.disabled = false;
                    tell(card, 'Confirm failed.', 'error');
                }
            } else if (e.target.classList.contains('fcc-cr-discard')) {
                const btn = e.target;
                // PI1: a press clears the panel's last outcome (not a double press's second).
                if (!(btn.dataset.armed === '1' && Date.now() - Number(btn.dataset.armedAt || 0) < 700)) sayOnPanel('');
                // First click ARMS (no backend call); second click within 4s
                // discards. Guards an accidental click from a permanent drop.
                // A second press under 700 ms is a double press, not a decision
                // (Group 50 review; Derek: "I don't want an accidental double
                // press to mess things up"), by mouse, Enter or Space.
                if (btn.dataset.armed === '1' && Date.now() - Number(btn.dataset.armedAt || 0) < 700) return;
                if (btn.dataset.armed !== '1') {
                    body.querySelectorAll('.fcc-cr-discard[data-armed="1"]').forEach(disarmDiscard);
                    btn.dataset.armed = '1';
                    btn.dataset.armedAt = String(Date.now());
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
                        const words = d.status === 'dismissed' ? 'Review discarded (no deduct).' : 'Already handled elsewhere.';
                        toast(words, 'info');
                        // Group 64 fix review: the next card slides up under the pointer
                        // here too, as after Confirm (R1).
                        if (window.fccShieldNextPress) window.fccShieldNextPress();
                        card.remove(); updateCount(); refreshBadge();
                        if (body.querySelector('.fcc-cr-card')) sayOnPanel(words);     // PI1
                        closeIfEmpty();
                    } else {
                        btn.disabled = false; disarmDiscard(btn);
                        tell(card, d.msg || 'Discard failed — check the log.', 'error');
                    }
                } catch (err) {
                    btn.disabled = false; disarmDiscard(btn);
                    tell(card, 'Discard failed.', 'error');
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

// Group 64.4 (Derek, 2026-11-20: a way to recover once he has fixed what kept a print
// file from being read, or its deduct from working): the "↻ Try again now" button on
// the Activity Log line FCC writes the first time a queued print's file downloads but
// can't be read, or its deduct fails (print_deduct._fetch_retry_button). The line holds
// the button itself, as the take-off's "Take it off" (inv_weigh_out.js), so it is in
// #live-logs and in the 📡 pill's list alike: one delegated click posts
// /api/cancel_deduct/retry_fetch {printer_name, job_id} and toasts the answer's words,
// which the pill's list also shows on its own line (its overlay covers the toast layer).
// A press while one is out for that print asks nothing, nor does a double click's
// second (`detail` 2). The click is window.fccFetchRetryClick, so a hermetic harness
// can press it (tests/test_fetch_backoff_64_4_js.py).
(() => {
    const out = new Set();
    const say = (msg, ok, fromPill) => {
        showToast(msg, ok ? 'success' : 'warning', ok ? 4000 : 7000);
        if (fromPill && typeof window.logPillNotice === 'function') window.logPillNotice(msg);
    };
    window.fccFetchRetryClick = (e) => {
        const t = e.target && e.target.closest ? e.target : null;
        const btn = t ? t.closest('.fcc-fetch-retry-btn') : null;
        if (!btn || !btn.closest('#live-logs, #fcc-log-pill-overlay')) return;
        e.preventDefault();
        if (e.detail > 1) return;
        const printer = btn.getAttribute('data-fetch-printer') || '';
        const job = btn.getAttribute('data-fetch-job') || '';
        const key = `${printer}::${job}`;
        if (!printer || !job || out.has(key)) return;
        out.add(key);
        const fromPill = !!btn.closest('#fcc-log-pill-overlay');
        if (fromPill && typeof window.logPillNotice === 'function') window.logPillNotice('');
        (window.fetchT || fetch)('/api/cancel_deduct/retry_fetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ printer_name: printer, job_id: job }),
        })
            .then((r) => r.json())
            .then((res) => say(String((res && res.msg) || `FCC couldn't queue job ${job} again.`),
                               !!(res && res.success), fromPill),
                  () => say("FCC didn't answer, so nothing changed. Try again in a moment.",
                            false, fromPill))
            .catch((err) => console.error(err))
            .finally(() => out.delete(key));
    };
    document.addEventListener('click', (e) => window.fccFetchRetryClick(e));
})();
