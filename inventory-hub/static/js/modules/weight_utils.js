/* MODULE: WEIGHT UTILITIES (Shared) */
//
// Phase 1 home for shared weight helpers. Phase 2 will grow this into the
// unified weight-entry component (gross/net/additive/delta modes, missing-
// empty-weight prompt, mode toggle) reused across every weight surface.
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
