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

        const setFromCascade = (cascade = {}) => {
            cachedVendor = cascade.vendor || null;
            const { value, source } = window.resolveEmptySpoolWeightSource({
                spoolWt: cascade.spoolWt,
                filamentWt: cascade.filamentWt,
                vendor: cascade.vendor,
            });
            input.value = (value !== null && value !== undefined) ? value : '';
            showBadge(source);
            updateCopyVendorEnabled();
        };

        const setValue = (v) => {
            input.value = (v === null || v === undefined) ? '' : v;
            clearBadge();
        };

        const updateCopyVendorEnabled = () => {
            if (!copyVendorBtn) return;
            const has = cachedVendor &&
                cachedVendor.empty_spool_weight !== null &&
                cachedVendor.empty_spool_weight !== undefined &&
                cachedVendor.empty_spool_weight !== '' &&
                Number(cachedVendor.empty_spool_weight) > 0;
            copyVendorBtn.disabled = !has;
            copyVendorBtn.classList.toggle('disabled', !has);
        };

        const onInput = () => {
            clearBadge();
            if (typeof onChange === 'function') onChange(input.value);
        };
        input.addEventListener('input', onInput);

        const onCopyVendor = () => {
            if (!cachedVendor || !cachedVendor.empty_spool_weight) return;
            input.value = cachedVendor.empty_spool_weight;
            clearBadge();
            if (typeof onChange === 'function') onChange(input.value);
        };
        if (copyVendorBtn) copyVendorBtn.addEventListener('click', onCopyVendor);

        const _teardown = () => {
            input.removeEventListener('input', onInput);
            if (copyVendorBtn) copyVendorBtn.removeEventListener('click', onCopyVendor);
        };

        const handle = {
            setFromCascade,
            setValue,
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
})();
