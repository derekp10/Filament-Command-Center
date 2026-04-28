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
//     error,            // string | null  — input validation message
//   }
//
// Notes:
//   - Negative results clamp to 0 with capped='low' (e.g. additive past empty).
//   - Results > initial clamp to initial with capped='high' (matches the
//     "ALEX FIX" cap in spoolman_api.update_spool — preview shows what the
//     backend would actually persist).
//   - Returns error: 'invalid_value' for NaN / non-numeric input.
//   - Returns error: 'invalid_initial' if initial_weight is missing or <= 0.
//   - Gross mode with missing empty_spool_weight returns
//     `requires_empty: true` and `used_weight: null` so the caller can prompt.
function computeUsedWeight({
    mode,
    value,
    initial_weight,
    current_used = 0,
    empty_spool_weight = null,
} = {}) {
    const result = {
        used_weight: null,
        remaining: null,
        raw_used: null,
        capped: null,
        requires_empty: false,
        error: null,
    };

    const initial = Number(initial_weight);
    if (!(initial > 0)) {
        result.error = 'invalid_initial';
        return result;
    }

    const num = Number(value);
    if (value === null || value === undefined || value === '' || Number.isNaN(num)) {
        result.error = 'invalid_value';
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
function promptMissingEmptyWeight({
    vendor = '',
    material = '',
    color = '',
    color_hex = null,
    title = 'Empty spool weight is missing',
    helper = 'Place the empty spool on the scale and enter the reading. We’ll use it as the tare for this and future weigh-ins.',
    overlayId = 'fcc-missing-empty-weight-overlay',
} = {}) {
    return new Promise((resolve) => {
        const existing = document.getElementById(overlayId);
        if (existing) existing.remove();

        const swatch = color_hex
            ? `<span style="display:inline-block;width:14px;height:14px;background:#${String(color_hex).replace(/^#/,'')};border:1px solid #fff;border-radius:50%;vertical-align:middle;margin-right:6px;"></span>`
            : '';
        const ctxBits = [vendor, material, color].filter(Boolean).join(' • ');
        const ctxRow = ctxBits
            ? `<div style="margin:4px 0 14px 0; color:#bbb; font-size:0.9rem;">${swatch}${ctxBits}</div>`
            : '';

        const overlay = document.createElement('div');
        overlay.id = overlayId;
        overlay.style.cssText = (
            'position:fixed;inset:0;background:rgba(0,0,0,0.55);' +
            'display:flex;align-items:center;justify-content:center;' +
            'z-index:20000;'
        );
        overlay.innerHTML = `
            <div role="dialog" aria-modal="true" aria-labelledby="${overlayId}-title"
                 style="background:#1f2024;color:#eee;border:1px solid #555;
                        border-radius:8px;padding:18px 20px;min-width:320px;
                        max-width:480px;box-shadow:0 8px 32px rgba(0,0,0,0.6);">
                <div id="${overlayId}-title" style="font-weight:bold;font-size:1.05rem;margin-bottom:6px;">⚖️ ${title}</div>
                ${ctxRow}
                <div style="color:#bbb;font-size:0.88rem;line-height:1.4;margin-bottom:12px;">${helper}</div>
                <div class="input-group input-group-sm">
                    <input type="number" min="0" step="0.1" inputmode="decimal"
                           id="${overlayId}-input"
                           class="form-control bg-secondary text-light border-dark"
                           placeholder="Empty spool weight" autofocus>
                    <span class="input-group-text bg-dark text-light border-secondary">g</span>
                </div>
                <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;">
                    <button type="button" id="${overlayId}-cancel" class="btn btn-sm btn-secondary">Cancel</button>
                    <button type="button" id="${overlayId}-save" class="btn btn-sm btn-primary">Save &amp; Continue</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        const input = overlay.querySelector(`#${overlayId}-input`);
        const saveBtn = overlay.querySelector(`#${overlayId}-save`);
        const cancelBtn = overlay.querySelector(`#${overlayId}-cancel`);

        const cleanup = () => {
            document.removeEventListener('keydown', onKey, true);
            overlay.remove();
        };
        const submit = () => {
            const v = Number(input.value);
            if (!(v > 0)) { input.focus(); return; }
            cleanup();
            resolve(v);
        };
        const cancel = () => { cleanup(); resolve(null); };
        const onKey = (e) => {
            if (e.key === 'Enter') { e.preventDefault(); submit(); }
            else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
        };

        saveBtn.addEventListener('click', submit);
        cancelBtn.addEventListener('click', cancel);
        document.addEventListener('keydown', onKey, true);
        // Defer focus so the overlay paints before we steal focus.
        setTimeout(() => input.focus(), 0);
    });
}
window.promptMissingEmptyWeight = promptMissingEmptyWeight;
