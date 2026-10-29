/* MODULE: TITLE BAR SETTINGS — the title bar's two per-browser settings
 * (Group 57.3; Derek, 2026-10-28: "a configure for that would also be nice
 * instead of hard coding it").
 *
 * Settings -> 🖥️ This Browser:
 *  - "Title bar buttons" ('fcc.titleBar.buttons'): Automatic (default) /
 *    Always words / Always icons. How 🏷️ Backlog, 🛒 Queue and ⚠️ Low stock
 *    are labelled. Automatic: their words while the bar has room, and only
 *    the icon and number when it hasn't (titlebar_fit.js takes that as its
 *    second step, after the spacing, so the version badge stays; below 992 px
 *    always). The other two keep one look. Low and Out keep their words in
 *    every look: they tell the two numbers apart.
 *  - "Low stock count" ('fcc.lowStock.count'): Low and Out (default) / One
 *    number. What the ⚠️ button shows: the two lists apart, in the Low stock
 *    window's own words and count pills ("Low [1] Out [11]"), or the two added
 *    up ("Low stock (12)", or "⚠️ 12" without the words). inv_stock.js paints
 *    both.
 *
 *  - dashboard.html's <head> applies both before the first paint (a tiny inline
 *    script, #fcc-title-bar-boot): data-fcc-tb-buttons (auto / words / icons)
 *    and data-fcc-low-count (both / one) on <html>. Keep its maps the same as
 *    PREFS below.
 *  - global.css turns the attributes into the look ("Title bar"), and
 *    titlebar_fit.js fits the bar again on a change (the `fcc:title-bar` event).
 *  - This module changes them LIVE: a pick in Settings applies and stores it,
 *    with no Save needed, as Text size does (text_size.js). Only a pick changes
 *    them: typed characters (a scan, while the select has the focus) never
 *    pick a choice.
 */
(function () {
    const PREFS = Object.freeze({
        buttons: Object.freeze({
            key: 'fcc.titleBar.buttons', label: 'Title bar buttons', def: 'Automatic', attr: 'data-fcc-tb-buttons',
            map: Object.freeze({ 'Automatic': 'auto', 'Always words': 'words', 'Always icons': 'icons' }),
        }),
        count: Object.freeze({
            key: 'fcc.lowStock.count', label: 'Low stock count', def: 'Low and Out', attr: 'data-fcc-low-count',
            map: Object.freeze({ 'Low and Out': 'both', 'One number': 'one' }),
        }),
    });
    const _known = (p, name) => typeof name === 'string' && Object.prototype.hasOwnProperty.call(p.map, name);

    // The stored choice's name; the default when none is stored, it is
    // unknown, or the browser won't let FCC read storage.
    function get(which) {
        const p = PREFS[which];
        if (!p) return null;
        try {
            const v = window.localStorage.getItem(p.key);
            return _known(p, v) ? v : p.def;
        } catch (e) { return p.def; }
    }

    // Show a choice without storing it.
    function apply(which, name) {
        const p = PREFS[which];
        if (!p) return null;
        const shown = _known(p, name) ? name : p.def;
        const value = p.map[shown];
        const root = document.documentElement;
        const was = root.getAttribute(p.attr);
        root.setAttribute(p.attr, value);
        if (was !== value) {
            try {
                document.dispatchEvent(new CustomEvent('fcc:title-bar', { detail: { pref: which, name: shown, value } }));
            } catch (e) { /* a listener's error is its own */ }
        }
        return value;
    }

    // Show a choice and keep it in this browser. Returns false when the browser
    // refused to store it (private mode, storage full or blocked): it still
    // shows until the page is reloaded.
    function set(which, name) {
        const p = PREFS[which];
        if (!p || !_known(p, name)) return false;
        apply(which, name);
        try { window.localStorage.setItem(p.key, name); return true; }
        catch (e) { return false; }
    }

    // Settings: the selects the renderer draws for the two fields (inv_settings.js,
    // from config_schema.py). Delegated, so it works on every redraw of the
    // Settings card; a mouse pick and the arrow keys both fire `change`.
    function _which(el) {
        if (!el || typeof el.matches !== 'function') return null;
        return Object.keys(PREFS).find((w) => el.matches('.cfgset-input[data-key="' + PREFS[w].key + '"]')) || null;
    }

    document.addEventListener('change', (e) => {
        const which = _which(e.target);
        if (!which) return;
        const name = e.target.value;
        if (!_known(PREFS[which], name)) return;
        const stored = set(which, name);
        // Stored already, so "Save settings" has nothing left to do for it.
        if (stored) e.target.dataset.initial = name;
        if (!stored && typeof window.showToast === 'function') {
            window.showToast(PREFS[which].label + ' changed, but this browser could not keep it (private mode or '
                + 'storage blocked): it goes back to ' + get(which) + ' when the page reloads.', 'warning', 7000);
        }
    });

    // A scan never picks a choice (text_size.js's rule): a scanner types into
    // whatever has the focus, and a select takes each character as type-ahead.
    // Not stopped, so the scan accumulator still reads the whole scan; the
    // arrow keys, Home / End and Page Up / Down still pick.
    document.addEventListener('keydown', (e) => {
        if (!_which(e.target)) return;
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        if (typeof e.key === 'string' && e.key.length === 1) e.preventDefault();
    }, true);

    // The <head> script normally did this already; this covers a page that was
    // built without it.
    Object.keys(PREFS).forEach((which) => {
        if (!document.documentElement.hasAttribute(PREFS[which].attr)) apply(which, get(which));
    });

    window.fccTitleBarPrefs = Object.freeze({ PREFS, get, set, apply });
})();
