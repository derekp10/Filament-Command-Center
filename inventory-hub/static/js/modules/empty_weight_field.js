/* MODULE: <EmptyWeightField> — shared component for setting empty_spool_weight */
//
// Phase 2 component (Group 12). Attaches to an EXISTING input element and
// owns:
//   - Initial value population from the Spool > Filament > Vendor cascade
//     (via window.resolveEmptySpoolWeightSource from weight_utils.js)
//   - "↩ from filament/vendor" inheritance badge that clears when the user
//     types a value
//   - Optional "⇩ Copy Vendor Weight" affordance that fills the input from
//     the vendor's empty_spool_weight
//
// The component does NOT submit. The caller still owns the form / save flow.
// This is what unifies the wizard, edit-filament Specs, and post-archive
// prompt surfaces — each one has a different containing form, but the
// inheritance / badge / copy-vendor behavior is identical.
//
// Group 66.1 / 66.7: it also knows whether the box shows a value it only
// inherits. It remembers what its last draw put in the box (`drawn`: the source
// and the text) and whether a person changed it since (`touched`: their input, Use
// Vendor, setValue; and a box whose text no longer is the drawn text, which catches
// code that writes .value directly):
//   - inherited(): 'filament' / 'vendor' while the box still shows what it inherits,
//     untouched; else null. A caller's Save leaves such a value out: it is the
//     filament's (or the vendor's), not this record's own (66.7: Edit Filament wrote
//     its vendor's weight as the filament's own at EVERY Save).
//   - setVendor(v): the vendor this record has now (66.1: a vendor saved or picked
//     while the window is open). Use Vendor follows it, and an untouched box that
//     shows what it inherits (or nothing) is drawn again from it; an own value, a
//     typed one and Use Vendor's stay. It fires no input and no onChange (code, not
//     the person).
//   - source(): what the last draw showed ('spool' = the record's own, 'filament',
//     'vendor', or null), and isTouched().
//
// Usage:
//   const field = window.bindEmptyWeightField({
//     input: document.getElementById('wiz-spool-empty_weight'),
//     badge: document.getElementById('wiz-spool-empty-inherited-badge'),
//     sourceLabel: document.getElementById('wiz-spool-empty-inherited-source'),
//     copyVendorBtn: document.getElementById('wiz-spool-empty-copy-vendor'),
//     onChange: (v) => wizardCalcUsedWeight(),
//   });
//   field.setFromCascade({ spoolWt, filamentWt, vendor });
//   const v = field.getValue();
//
// Idempotent: calling bindEmptyWeightField on the same input twice replaces
// the prior listeners (avoids handler stacking when a modal is re-opened).

(function () {
    const HANDLE_KEY = '__fccEmptyWeightField';

    function bindEmptyWeightField(options = {}) {
        let { input, badge = null, sourceLabel = null, copyVendorBtn = null,
              onChange = null } = options;

        if (typeof input === 'string') input = document.getElementById(input);
        if (typeof badge === 'string') badge = document.getElementById(badge);
        if (typeof sourceLabel === 'string') sourceLabel = document.getElementById(sourceLabel);
        if (typeof copyVendorBtn === 'string') copyVendorBtn = document.getElementById(copyVendorBtn);

        if (!input) return null;

        // Tear down any prior binding so re-binding is safe.
        const prior = input[HANDLE_KEY];
        if (prior && typeof prior._teardown === 'function') prior._teardown();

        let cachedVendor = null;  // remembered for the Copy-Vendor button
        let cascade = null;       // the {spoolWt, filamentWt} last given to setFromCascade
        let drawn = { source: null, text: input.value };   // what the last draw put in the box
        let touched = false;      // a person's input, Use Vendor or setValue since the last draw
        // Torn down (the box bound again, a window opened anew): this handle writes nothing
        // more into the box it shares with the new binding (review round 2 of Group 66,
        // Q1-07: an earlier Edit Filament open's late vendor read redrew the next open's box
        // through it, and that Save wrote the old vendor's weight as the filament's own).
        let dead = false;

        const showBadge = (source) => {
            if (!badge) return;
            if (source === 'filament' || source === 'vendor') {
                if (sourceLabel) sourceLabel.textContent = source;
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }
        };

        const clearBadge = () => { if (badge) badge.style.display = 'none'; };

        // Draw the box from the cascade and the vendor it has now.
        const draw = () => {
            if (dead) return;
            const { value, source } = window.resolveEmptySpoolWeightSource({
                spoolWt: cascade ? cascade.spoolWt : null,
                filamentWt: cascade ? cascade.filamentWt : null,
                vendor: cachedVendor,
            });
            input.value = (value !== null && value !== undefined) ? value : '';
            drawn = { source: input.value === '' ? null : source, text: input.value };
            touched = false;
            showBadge(drawn.source);
        };

        const setFromCascade = (c = {}) => {
            if (dead) return;
            cachedVendor = c.vendor || null;
            cascade = { spoolWt: c.spoolWt, filamentWt: c.filamentWt };
            draw();
            updateCopyVendorEnabled();
        };

        const isTouched = () => touched || input.value !== drawn.text;

        const inherited = () => (!isTouched() && (drawn.source === 'filament' || drawn.source === 'vendor'))
            ? drawn.source : null;

        const setVendor = (v) => {
            if (dead) return;
            cachedVendor = v || null;
            updateCopyVendorEnabled();
            if (cascade && !isTouched() && drawn.source !== 'spool') draw();
        };

        const setValue = (v) => {
            if (dead) return;
            input.value = (v === null || v === undefined) ? '' : v;
            touched = true;
            clearBadge();
        };

        const updateCopyVendorEnabled = () => {
            if (!copyVendorBtn || dead) return;
            const has = cachedVendor &&
                cachedVendor.empty_spool_weight !== null &&
                cachedVendor.empty_spool_weight !== undefined &&
                cachedVendor.empty_spool_weight !== '' &&
                Number(cachedVendor.empty_spool_weight) > 0;
            // Hide rather than disable — matches the existing edit-filament
            // Specs tab affordance ("⇩ Copy" button only appears when the
            // vendor has a value worth copying).
            copyVendorBtn.style.display = has ? '' : 'none';
            if (has) {
                copyVendorBtn.title = `Copy vendor default empty-spool weight (${cachedVendor.empty_spool_weight}g)`;
            }
        };

        const onInput = () => {
            touched = true;
            clearBadge();
            if (typeof onChange === 'function') onChange(input.value);
        };
        input.addEventListener('input', onInput);

        const onCopyVendor = () => {
            if (!cachedVendor || !cachedVendor.empty_spool_weight) return;
            input.value = cachedVendor.empty_spool_weight;
            touched = true;
            clearBadge();
            if (typeof onChange === 'function') onChange(input.value);
        };
        if (copyVendorBtn) copyVendorBtn.addEventListener('click', onCopyVendor);

        const _teardown = () => {
            dead = true;
            input.removeEventListener('input', onInput);
            if (copyVendorBtn) copyVendorBtn.removeEventListener('click', onCopyVendor);
        };

        const handle = {
            setFromCascade,
            setValue,
            setVendor,
            inherited,
            isTouched,
            source: () => drawn.source,
            getValue: () => input.value,
            clearBadge,
            focus: () => input.focus(),
            input,
            _teardown,
        };
        input[HANDLE_KEY] = handle;
        return handle;
    }

    window.bindEmptyWeightField = bindEmptyWeightField;
    // The binding on a box (a test seam, and a reader outside the binder's closure).
    // Read at run time only (the load-order canary).
    window.emptyWeightFieldOf = (el) => {
        const box = typeof el === 'string' ? document.getElementById(el) : el;
        return (box && box[HANDLE_KEY]) || null;
    };
})();
