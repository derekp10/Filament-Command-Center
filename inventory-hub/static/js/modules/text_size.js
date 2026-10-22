/* MODULE: TEXT SIZE — the per-browser Text size (Derek, 2026-10-21).
 *
 * Settings -> 🖥️ This Browser -> "Text size": Small / Standard (default) /
 * Large / Extra Large, stored in this browser's localStorage under
 * 'fcc.textSize' (the display name; an absent or unknown value is Standard).
 *
 *  - dashboard.html's <head> applies the stored size before the first paint:
 *    a tiny inline script (#fcc-text-size-boot) sets data-fcc-text-size on
 *    <html>. Keep its name -> attribute map the same as SIZES below.
 *  - global.css turns the attribute into sizes: Small gives the named sizes
 *    (--fcc-fs-label / -small / -row) the compact values FCC had before the
 *    readability rule, Large and Extra Large grow the root (18 / 20 px), so
 *    every rem size grows together.
 *  - This module changes it LIVE: picking a size in Settings applies it at
 *    once and stores it, with no Save needed (the generic settings renderer,
 *    inv_settings.js, draws the select from config_schema.py's Field).
 *
 * A change fires `fcc:text-size` on document ({detail: {name, size}}) for
 * anything that measures text and wants to measure again.
 */
(function () {
    const KEY = 'fcc.textSize';
    const DEFAULT = 'Standard';
    // display name (stored, shown in Settings) -> data-fcc-text-size value
    const SIZES = Object.freeze({
        'Small': 'small',
        'Standard': 'standard',
        'Large': 'large',
        'Extra Large': 'xlarge',
    });
    const _known = (name) => typeof name === 'string' && Object.prototype.hasOwnProperty.call(SIZES, name);

    // The stored size's display name; Standard when none is stored, it is
    // unknown, or the browser won't let FCC read storage.
    function get() {
        try {
            const v = window.localStorage.getItem(KEY);
            return _known(v) ? v : DEFAULT;
        } catch (e) { return DEFAULT; }
    }

    // Show a size without storing it.
    function apply(name) {
        const size = _known(name) ? SIZES[name] : SIZES[DEFAULT];
        const root = document.documentElement;
        const was = root.getAttribute('data-fcc-text-size');
        root.setAttribute('data-fcc-text-size', size);
        if (was !== size) {
            try {
                document.dispatchEvent(new CustomEvent('fcc:text-size', { detail: { name: _known(name) ? name : DEFAULT, size } }));
            } catch (e) { /* a listener's error is its own */ }
        }
        return size;
    }

    // Show a size and keep it in this browser. Returns false when the browser
    // refused to store it (private mode, storage full or blocked): the size
    // still shows until the page is reloaded.
    function set(name) {
        if (!_known(name)) return false;
        apply(name);
        try { window.localStorage.setItem(KEY, name); return true; }
        catch (e) { return false; }
    }

    // Settings: the select the renderer draws for the 'fcc.textSize' field.
    // Delegated, so it works on every redraw of the Settings card; a mouse
    // pick and the keyboard (arrow keys on the focused select) both fire
    // `change`.
    document.addEventListener('change', (e) => {
        const el = e.target;
        if (!el || typeof el.matches !== 'function' || !el.matches('.cfgset-input[data-key="' + KEY + '"]')) return;
        const name = el.value;
        if (!_known(name)) return;
        const stored = set(name);
        // Stored already, so "Save settings" has nothing left to do for it.
        if (stored) el.dataset.initial = name;
        if (!stored && typeof window.showToast === 'function') {
            window.showToast('Text size changed, but this browser could not keep it (private mode or storage '
                + 'blocked): it goes back to ' + get() + ' when the page reloads.', 'warning', 7000);
        }
    });

    // The <head> script normally did this already; this covers a page that
    // was built without it.
    if (!document.documentElement.hasAttribute('data-fcc-text-size')) apply(get());

    window.fccTextSize = Object.freeze({ KEY, DEFAULT, SIZES, get, set, apply });
})();
