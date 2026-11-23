/* MODULE: WEIGHT UTILITIES (Shared) */
//
// Phase 1 extracted the empty-spool-weight cascade. Phase 2 adds the
// `computeUsedWeight` math helper (used by <WeightEntry>) and the shared
// `promptMissingEmptyWeight` inline overlay (used everywhere a write needs a
// resolved tare and the cascade comes back empty).
//
// Empty-spool-weight inheritance: Spool > Filament > Vendor (manufacturer).
// Treats null / undefined / '' / 0 as "unset" so the next level in the chain
// wins. A vendor value entered in Spoolman flows down and auto-populates blank
// spool and filament fields instead of surfacing as 0.

function resolveEmptySpoolWeight({ spoolWt, filamentWt, vendor } = {}) {
    const has = (v) => v !== null && v !== undefined && v !== '' && Number(v) > 0;
    if (has(spoolWt)) return Number(spoolWt);
    if (has(filamentWt)) return Number(filamentWt);
    if (vendor && has(vendor.empty_spool_weight)) return Number(vendor.empty_spool_weight);
    return null;
}
window.resolveEmptySpoolWeight = resolveEmptySpoolWeight;

// Same cascade as resolveEmptySpoolWeight but also reports which level in the
// chain produced the value. Returned source is one of 'spool', 'filament',
// 'vendor', or null. Use this when the UI needs to badge an inherited value.
function resolveEmptySpoolWeightSource({ spoolWt, filamentWt, vendor } = {}) {
    const has = (v) => v !== null && v !== undefined && v !== '' && Number(v) > 0;
    if (has(spoolWt)) return { value: Number(spoolWt), source: 'spool' };
    if (has(filamentWt)) return { value: Number(filamentWt), source: 'filament' };
    if (vendor && has(vendor.empty_spool_weight)) {
        return { value: Number(vendor.empty_spool_weight), source: 'vendor' };
    }
    return { value: null, source: null };
}
window.resolveEmptySpoolWeightSource = resolveEmptySpoolWeightSource;

// --- Canonical weight display formatters (buglist line 51) --------------------
//
// Inconsistent rounding across surfaces made a sub-gram measurement variance
// LOOK like a ~1g bug (e.g. a card showed a whole gram while the wizard showed
// `used` raw next to a rounded `remaining`, so the two stopped reconciling).
// Data is ALWAYS stored exact — these are DISPLAY-ONLY and split into two tiers
// by Derek's decision (2026-06-03):
//
//   GLANCE  — spool cards, search results, buffer, quick-swap grid, printer-
//             status widget: WHOLE grams. Low visual noise for at-a-glance
//             "does this spool fit my print?" scanning.
//   PRECISE — Spool Details modal, Add/Edit wizard weight fields, weigh-out
//             modal, <WeightEntry>: up to 1 decimal (the realistic resolution
//             of a whole-gram scale + a fractional empty-spool tare). Trailing
//             ".0" is trimmed so a whole value still reads "850", not "850.0".
//
// The scale only reads whole grams, so the 0.x always originates in the tare
// arithmetic; preserving 1 decimal keeps `used + remaining == initial` and
// stops the surprise 1g jumps without forcing decimals onto the scan surfaces.
// Note: guard null/undefined/'' explicitly — Number(null) and Number('') both
// coerce to 0, which would render a missing weight as a misleading "0". A real
// numeric 0 (e.g. an empty spool) still formats as "0".
function fmtGramsGlance(v) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    return String(Math.round(n));
}
function fmtGramsPrecise(v) {
    if (v === null || v === undefined || v === '') return '';
    const n = Number(v);
    if (!isFinite(n)) return '';
    return String(Math.round(n * 10) / 10);
}
window.fmtGramsGlance = fmtGramsGlance;
window.fmtGramsPrecise = fmtGramsPrecise;

// Parse the +/- prefix delta syntax used by Additive mode. Accepts:
//   "+50"  -> { value: 50, sign: '+' }
//   "-20"  -> { value: -20, sign: '-' }
//   "50"   -> { value: 50, sign: null }   (bare number, treated as positive)
//   ""     -> { value: null, sign: null } (empty string is "no input")
//   "abc"  -> { value: NaN, sign: null }  (caller decides how to handle)
function parseAdditiveInput(raw) {
    if (raw === null || raw === undefined) return { value: null, sign: null };
    const str = String(raw).trim();
    if (str === '' || str === '+' || str === '-') return { value: null, sign: null };
    const sign = (str[0] === '+' || str[0] === '-') ? str[0] : null;
    const num = Number(str);
    return { value: num, sign };
}
window.parseAdditiveInput = parseAdditiveInput;

// Pure function — given a mode + the user's input value + the spool's current
// state, return what should be written to `used_weight` along with a preview
// payload the UI can display before submit.
//
// Modes:
//   'gross'    — value is total scale reading (spool + remaining filament).
//                Requires `empty_spool_weight`. Computes:
//                    used = initial - (gross - empty)
//   'net'      — value is filament-only weight remaining. Computes:
//                    used = initial - net
//   'additive' — value is signed delta (e.g. +50 / -20). Computes:
//                    used = current_used + delta
//   'set_used' — value IS the target used_weight. Computes:
//                    used = value
//
// Returns:
//   {
//     used_weight,      // number | null  — clamped to [0, initial_weight]
//     remaining,        // number | null  — initial - used
//     raw_used,         // number | null  — pre-clamp value (for explanatory UI)
//     capped,           // 'high' | 'low' | null — direction of any clamp
//     requires_empty,   // boolean        — gross mode w/ no resolved tare
//     derived_initial,  // number | null  — set only in the unknown-initial path
//     error,            // string | null  — input validation message
//   }
//
// Notes:
//   - Negative results clamp to 0 with capped='low' (e.g. additive past empty).
//   - Results > initial clamp to initial with capped='high' (matches the
//     "ALEX FIX" cap in spoolman_api.update_spool — preview shows what the
//     backend would actually persist).
//   - Returns error: 'invalid_value' for NaN / non-numeric input.
//   - Returns error: 'invalid_initial' if initial_weight is missing or <= 0,
//     UNLESS `allow_unknown_initial` is true (31.1 — the wizard's
//     catalog-a-spool case). With no known original net, gross/net modes then
//     treat what's on the spool NOW as its full capacity: remaining = the
//     available filament (gross − tare, or the net value directly), used = 0,
//     and `derived_initial` carries that capacity back to the caller so it can
//     seed initial_weight. additive/set_used still require a known initial.
//   - Gross mode with missing empty_spool_weight returns
//     `requires_empty: true` and `used_weight: null` so the caller can prompt.
function computeUsedWeight({
    mode,
    value,
    initial_weight,
    current_used = 0,
    empty_spool_weight = null,
    allow_unknown_initial = false,
} = {}) {
    const result = {
        used_weight: null,
        remaining: null,
        raw_used: null,
        capped: null,
        requires_empty: false,
        derived_initial: null,
        error: null,
    };

    const initial = Number(initial_weight);
    const initialKnown = initial > 0;
    if (!initialKnown && !allow_unknown_initial) {
        result.error = 'invalid_initial';
        return result;
    }

    const num = Number(value);
    if (value === null || value === undefined || value === '' || Number.isNaN(num)) {
        result.error = 'invalid_value';
        return result;
    }

    // 31.1 — unknown-original-net path. Derive the spool's available filament
    // directly (no original capacity needed) and treat it as a full spool.
    if (!initialKnown) {
        let remaining;
        if (mode === 'gross') {
            const tare = Number(empty_spool_weight);
            if (!(tare > 0)) {
                result.requires_empty = true;
                return result;
            }
            remaining = num - tare;          // available = gross − tare
        } else if (mode === 'net') {
            remaining = num;                 // value IS the available filament
        } else {
            // additive / set_used are meaningless without a known initial.
            result.error = 'invalid_initial';
            return result;
        }
        if (remaining < 0) { remaining = 0; result.capped = 'low'; }
        result.derived_initial = remaining;  // seeds the new spool's net capacity
        result.raw_used = 0;
        result.used_weight = 0;
        result.remaining = remaining;
        return result;
    }

    let raw;
    switch (mode) {
        case 'gross': {
            const tare = Number(empty_spool_weight);
            if (!(tare > 0)) {
                result.requires_empty = true;
                return result;
            }
            raw = initial - (num - tare);
            break;
        }
        case 'net':
            raw = initial - num;
            break;
        case 'additive':
            raw = Number(current_used) + num;
            break;
        case 'set_used':
            raw = num;
            break;
        default:
            result.error = 'invalid_mode';
            return result;
    }

    result.raw_used = raw;
    let used = raw;
    if (used < 0) {
        used = 0;
        result.capped = 'low';
    } else if (used > initial) {
        used = initial;
        result.capped = 'high';
    }
    result.used_weight = used;
    result.remaining = initial - used;
    return result;
}
window.computeUsedWeight = computeUsedWeight;

// Inline overlay (NOT a Swal — per CLAUDE.md "no nested Swal.fire()") that
// asks the user for an empty-spool-weight when the cascade comes back empty.
// Returns a Promise<number|null> — number on save, null on cancel.
//
// Used by:
//   - Post-archive flow when filament + vendor both lack spool_weight
//   - <WeightEntry> Gross mode when Spool > Filament > Vendor cascade fails
//
// Context block shows vendor / material / color so the user has enough to
// recognize the spool without leaving the active flow.
// Resolution sentinel returned when the user clicks Skip. Callers that pass
// `allowSkip: true` must check for this value to distinguish "no tare, treat
// input as Net for this submission" from a real numeric tare.
//
// Group 63.7: the words say what the question does. It asks for what the spool
// weighs empty (an empty spool of the same kind on the scale, or the maker's
// figure: the spool being weighed still has filament on it), and says the weight
// is kept as this spool's own: its callers save it as the spool's spool_weight
// with the reading (the Quick-Weigh, the weigh-out list) or put it in the spool's
// box (the wizard). Skip says it saves the number as the filament left (Net),
// which is what it does. The box is a text box read strictly as grams (63.9(b),
// window.parseGramsReading): "0.2 kg", "7 oz" or "167,5" is refused in words, with
// no unit conversion. `prefill` / `offer` (63.9(a)): a figure worked out for a new
// spool (gross less its net) and its words, never saved unasked. Since Derek's
// option 2 (2026-11-19, review round 4) the box opens empty and the figure is a
// button beside its words, "Use about 245 g", which puts it in the box (selected,
// so Enter saves it and a figure typed over it replaces it): filled in and
// selected, one Enter took it for a part-used spool with nothing used on record,
// recording it as full (the K05 fix had selected it; a figure typed over it was
// joined to it, 250245 g). `maxTare`
// (window.tareCeiling, from the Gross reading) refuses, in words, an empty weight
// the spool on the scale can't have. Derek's picture walk (2026-11-18): Skip on one line ("Skip: save as
// filament left", its longer words in its title), and the offer worded as an
// estimate (newSpoolTareOfferWords: "some brands aren't 100% exact on the 1kg
// filament (prusament will have more sometimes)"); and at its second look
// (2026-11-19) its buttons centred, "so there isn't so much space to the left of
// cancel" (they wrap, still centred, on a narrow window).
const PROMPT_SKIP_TARE = 'skip';

// The words beside a new spool's offered empty weight (Group 63.9(a)): the reading
// less the net on its label, which a maker's extra filament makes read high. Derek,
// 2026-11-19 (Group 63 review, round 4, his option 2): the figure is a button of its
// own ("Use about 245 g", promptMissingEmptyWeight), and the words say it holds only
// for a new, full spool: "nothing used" is no proof a spool is full (every new record
// in the wizard has nothing used, and a filament's net can be wrong), and for a
// part-used one it reads low. `offer` is the figure (the button shows it).
const newSpoolTareOfferWords = (reading, net, offer) => {
    const g = (n) => `${typeof window.fmtGramsPrecise === 'function' ? window.fmtGramsPrecise(Number(n)) : n} g`;
    return `If this spool is new and full: ${g(reading)} on the scale less the ${g(net)} its label says `
        + "(a maker's extra filament makes it read high).";
};
window.newSpoolTareOfferWords = newSpoolTareOfferWords;

// The heaviest empty weight a Gross reading allows (Group 63 review, round 2: the
// first rule, "at or above the reading", refused an empty spool's own reading, the
// one figure an empty spool on the scale has). A spool may be empty on the scale,
// its own reading or the maker's figure a little above being its empty weight, so
// only a figure far above the reading is refused (one typed onto the end of
// another, "250245"). Two kinds of spool can't be empty there, so for them a figure
// at or above the reading is refused (`below`: the empty weight must be less than
// `max`):
//   - a spool FCC has nothing used from whose reading is above its net: the scale
//     holds more than its filament, which no empty spool weighs. Review round 3:
//     round 2 allowed it at most the reading less 85% of its net, as if a spool with
//     nothing used were full, and refused the true empty weight of a part-used spool
//     being catalogued (the wizard's Weigh from Scale has nothing used for a new
//     record) or of one under a filament whose net is wrong, calling it new;
//   - `opts.unknownNet` (the wizard with no net known: what is on the spool is the
//     reading less its empty weight, kept as its total): a figure at or above the
//     reading wrote a total of 0 g into the form (round 3; round 1 refused it).
// {max, below, why, next}, or null: `next`, the sentence after why saying what to do
// (the prompt's "Check the number." when absent). Round 4: for a spool with nothing
// used, "this spool's 100 g of filament" is FCC's record, not what is on the scale,
// and an empty spool FCC never charged (its own spool heavier than its net, a small
// sample) is refused there, so the words say how to record one empty.
const tareCeiling = (reading, initial, used, opts) => {
    const r = Number(reading), net = Number(initial), u = Number(used);
    if (!(r > 0)) return null;
    const g = (n) => (typeof window.fmtGramsPrecise === 'function' ? window.fmtGramsPrecise(n) : n);
    if (opts && opts.unknownNet) {
        return { max: r, below: true, why: `it must be less than the ${g(r)} g on the scale, which is the spool with its filament` };
    }
    if (u === 0 && net > 0 && r > net) {
        return { max: r, below: true,
                 why: `it must be less than the ${g(r)} g on the scale, which is more than the ${g(net)} g of filament FCC has on this spool`,
                 next: 'If the spool on the scale is empty, Cancel and weigh it in Net as 0; otherwise check the number.' };
    }
    return { max: Math.round((r + 100) * 10) / 10, below: false, why: `the spool on the scale weighs ${g(r)} g` };
};
window.tareCeiling = tareCeiling;

function promptMissingEmptyWeight({
    vendor = '',
    material = '',
    color = '',
    color_hex = null,
    title = 'Empty spool weight is missing',
    helper = 'Enter what this spool weighs empty: weigh an empty spool of the same kind, or use the maker’s figure. FCC keeps it as this spool’s own empty weight, so it isn’t asked again.',
    overlayId = 'fcc-missing-empty-weight-overlay',
    allowSkip = false,
    // The weigh-out list's: a spool scanned over the prompt cancels it (Group
    // 57 review, round 8: that spool's reading went in this box as the tare),
    // after this is called to say so.
    onScanDismiss = null,
    // The weigh-out list's too: true while it is answering a scan, and Save
    // waits until it has (round 9: the scanned spool's reading and Enter,
    // typed before the answer, were saved as this spool's tare).
    scanPending = null,
    // Group 63.9(a): a figure to fill in (grams), and the words that say where it
    // came from ("1245 g on the scale − 1000 g of filament = 245 g").
    prefill = null,
    offer = '',
    // Group 63 review (K05, round 2): the heaviest empty weight the Gross reading
    // allows (window.tareCeiling) and why, in words; a heavier one is refused, and
    // with `maxTareBelow` (round 3) one as heavy too. `maxTareNext` (round 4): the
    // sentence after why, saying what to do ("Check the number." when left out).
    maxTare = null,
    maxTareWhy = '',
    maxTareBelow = false,
    maxTareNext = '',
} = {}) {
    return new Promise((resolve) => {
        const swatch = color_hex
            ? `<span style="display:inline-block;width:14px;height:14px;background:#${String(color_hex).replace(/^#/,'')};border:1px solid #fff;border-radius:50%;vertical-align:middle;margin-right:6px;"></span>`
            : '';
        const ctxBits = [vendor, material, color].filter(Boolean).join(' • ');
        const ctxRow = ctxBits
            ? `<div style="margin:4px 0 14px 0; color:#bbb; font-size:var(--fcc-fs-row);">${swatch}${ctxBits}</div>`
            : '';

        // Nested-prompt support: if WeightEntry is open, mount this prompt on
        // the CONFIRM tier so it sits above the WeightEntry overlay.
        const tier = document.getElementById('fcc-weight-entry-overlay') ? 'confirm' : 'standard';

        const esc = (v) => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        // Derek's option 2 (2026-11-19): the offered figure is a button beside its
        // words, and the box opens empty, so nothing is taken by an Enter that didn't
        // mean it (filled in and selected, one Enter recorded a part-used spool with
        // nothing used on record as full).
        const pre = Number(prefill);
        const offered = (prefill !== null && Number.isFinite(pre) && pre > 0) ? pre : null;
        const grams = (n) => `${typeof window.fmtGramsPrecise === 'function' ? window.fmtGramsPrecise(n) : n} g`;
        const offerRow = (offered !== null && offer)
            ? `<div id="${overlayId}-offer-row" style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:8px;">
                   <button type="button" id="${overlayId}-use-offer" class="btn btn-sm btn-outline-info" style="white-space:nowrap;">Use about ${esc(grams(offered))}</button>
                   <span id="${overlayId}-offer" style="color:#9fe7ff;font-size:var(--fcc-fs-small);flex:1 1 12rem;">${esc(offer)}</span>
               </div>`
            : '';

        // data-fcc-weight-keys: a weight key typed on its buttons goes into its
        // box (inv_core.js's weight capture; Group 57 review, round 7).
        const panelHtml = `
            <div role="dialog" aria-modal="true" aria-labelledby="${overlayId}-title" data-fcc-weight-keys
                 style="background:#1f2024;color:#eee;border:1px solid #555;
                        border-radius:8px;padding:18px 20px;min-width:320px;
                        max-width:480px;box-shadow:0 8px 32px rgba(0,0,0,0.6);">
                <div id="${overlayId}-title" style="font-weight:bold;font-size:1.05rem;margin-bottom:6px;">⚖️ ${title}</div>
                ${ctxRow}
                <div style="color:#bbb;font-size:var(--fcc-fs-small);line-height:1.4;margin-bottom:12px;">${helper}</div>
                <div id="${overlayId}-addons" style="color:#bbb;font-size:var(--fcc-fs-small);line-height:1.4;margin:-6px 0 12px 0;">Take off any clip, cap or edge guards first: FCC counts them as filament.</div>
                <div class="input-group input-group-sm">
                    <input type="text" inputmode="decimal" autocomplete="off"
                           id="${overlayId}-input"
                           class="form-control bg-secondary text-light border-dark fcc-weight-box"
                           placeholder="Empty spool weight">
                    <span class="input-group-text bg-dark text-light border-secondary">g</span>
                </div>
                ${offerRow}
                <div id="${overlayId}-err" role="alert" style="color:#ff8a8a;font-size:var(--fcc-fs-small);margin-top:4px;"></div>
                <div class="fcc-missing-tare-buttons" style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:14px;">
                    <button type="button" id="${overlayId}-cancel" class="btn btn-sm btn-secondary">Cancel</button>
                    ${allowSkip ? `<button type="button" id="${overlayId}-skip" class="btn btn-sm btn-warning" style="white-space:nowrap;"
                        title="No empty weight is kept: the number you typed is saved as the filament left on the spool, as Net does.">Skip: save as filament left</button>` : ''}
                    <button type="button" id="${overlayId}-save" class="btn btn-sm btn-primary">Save &amp; Continue</button>
                </div>
            </div>
        `;

        let resolved = false;
        const finish = (value) => {
            if (resolved) return;
            resolved = true;
            document.removeEventListener('keydown', onKey, true);
            handle.cleanup();
            resolve(value);
        };
        const submit = () => {
            if (typeof scanPending === 'function' && scanPending()) {
                showToast('A scan is still being read: press Enter again in a moment', 'info', 4000);
                return;
            }
            const raw = String(input.value == null ? '' : input.value).trim();
            const v = typeof window.parseGramsReading === 'function' ? window.parseGramsReading(raw) : Number(raw);
            if (raw !== '' && Number.isNaN(v)) {
                if (errEl) errEl.textContent = `"${raw}" is not a weight in grams: type grams only, like 167 or 167.5`;
                input.focus();
                return;
            }
            if (!(v > 0)) { input.focus(); return; }
            const most = Number(maxTare);
            if (maxTare !== null && Number.isFinite(most) && (maxTareBelow ? v >= most : v > most)) {
                const g = (n) => `${typeof window.fmtGramsPrecise === 'function' ? window.fmtGramsPrecise(n) : n} g`;
                if (errEl) errEl.textContent = maxTareWhy
                    ? `${g(v)} can't be its empty weight: ${maxTareWhy}. ${maxTareNext || 'Check the number.'}`
                    : `${g(v)} can't be its empty weight: check the number.`;
                input.focus();
                try { input.select(); } catch (_) { /* nothing to select */ }
                return;
            }
            finish(v);
        };
        const cancel = () => finish(null);
        const skip = () => finish(PROMPT_SKIP_TARE);
        const onKey = (e) => {
            // Escape routes through mountOverlay's onEscape; only Enter here,
            // and only while this prompt is on top.
            if (e.key !== 'Enter' || (window.isTopOverlay && !window.isTopOverlay(handle.element))) return;
            // A scan's Enter is the scan's (Group 57 review, round 6: a label
            // scanned into the box was saved as the tare). One scanned into the
            // box (a weight box, fcc-weight-box) is inv_core.js's weight
            // capture's, which takes its Enter first; one typed with the focus
            // on a button went to the scan accumulator.
            if (e.target !== input && window.enterIsAScan && window.enterIsAScan()) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (window.clearScanBuffer) window.clearScanBuffer();
            // Enter answers the button it is on: Cancel cancels, Skip skips, and the
            // offer puts its figure in the box.
            if (e.target === cancelBtn) cancel();
            else if (skipBtn && e.target === skipBtn) skip();
            else if (useBtn && e.target === useBtn) useOffer();
            else submit();
        };

        const handle = window.mountOverlay({
            id: overlayId,
            content: panelHtml,
            tier,
            focusGuard: true,
            initialFocus: `#${overlayId}-input`,
            onEscape: cancel,
        });
        const overlay = handle.element;
        if (typeof onScanDismiss === 'function') {
            overlay.fccDismissForScan = () => { if (!resolved) onScanDismiss(); cancel(); };
        }

        const input = overlay.querySelector(`#${overlayId}-input`);
        const saveBtn = overlay.querySelector(`#${overlayId}-save`);
        const cancelBtn = overlay.querySelector(`#${overlayId}-cancel`);
        const skipBtn = overlay.querySelector(`#${overlayId}-skip`);
        const errEl = overlay.querySelector(`#${overlayId}-err`);
        // The offer's button puts its figure in the box, selected, so Enter (or Save)
        // saves it and a figure typed over it replaces it (K05). It opens from the
        // Enter that saved the reading with its box empty, so a double press's second
        // Enter takes nothing (review round 4: filled in, it took the figure unread).
        const useBtn = overlay.querySelector(`#${overlayId}-use-offer`);
        const useOffer = () => {
            if (!input || offered === null || resolved) return;
            input.value = String(offered);
            if (errEl) errEl.textContent = '';
            input.focus();
            try { input.select(); } catch (_) { /* nothing to select */ }
        };
        if (input && errEl) input.addEventListener('input', () => { errEl.textContent = ''; });

        saveBtn.addEventListener('click', submit);
        cancelBtn.addEventListener('click', cancel);
        if (skipBtn) skipBtn.addEventListener('click', skip);
        if (useBtn) useBtn.addEventListener('click', useOffer);
        document.addEventListener('keydown', onKey, true);
    });
}
window.promptMissingEmptyWeight = promptMissingEmptyWeight;
window.PROMPT_SKIP_TARE = PROMPT_SKIP_TARE;
