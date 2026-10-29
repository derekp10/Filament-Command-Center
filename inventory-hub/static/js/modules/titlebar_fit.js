/* MODULE: TITLE BAR FIT (Group 57 review, 2026-10-26) */
// The one-line title bar (992 px and up) gives way in steps when it runs out of
// room: the spacing tightens (fcc-tb-tight), Backlog, Queue and Low stock show
// their icon and number alone (fcc-tb-icons; only with Settings -> Title bar
// buttons on Automatic, titlebar_prefs.js), ADD INVENTORY reads ADD
// (fcc-tb-add), the version badge shows its date and time alone
// (fcc-tb-shortver: "2026-10-28 18:45", what Derek reads it for), and last the
// title shortens with "…" (its full text is its tooltip; global.css "Title
// bar"; the readability build, 2026-10-21). Group 57.3: the badge went as the
// third step until Derek, 2026-10-28, kept it ("I can check to see the last
// time I updated"); a second line in its place, tried first, squeezed the
// Buffer Zone under its floor on a small laptop at Large text. The steps used to come at fixed widths, set for the bar as it
// was. Since the ⚠️ Low stock count (Group 57.2) the bar holds three live
// counts (🏷️ Backlog, 🛒 Queue, ⚠️ Low stock) whose width changes with their
// numbers, so a fixed width came too late once a count grew: the title
// shortened at Standard on a 1600 px window as soon as the Queue reached 10.
// Here each step is taken only while the title is cut short, in that order,
// whatever the counts say: on load, on a resize, a Text size change, and
// whenever a button's text changes. The version badge never shrinks on this
// bar (global.css), so a cut title is the one sign that a step is due.
// The bar takes a second line only when the buttons run past its edge with
// every step taken (Extra Large in a window just over 992 px, with big
// counts), so ⚙️ Settings, the way back to a smaller Text size, never leaves
// the screen (round 2), or when the title is cut to nothing and the badge
// would run under the buttons (Extra Large in a window under about 1130 px;
// review of 57.3: the buttons still fitted, so the bar stayed on one line with
// the badge's date drawn under the Spoolman light); on two lines the badge is
// whole again. With Settings -> When the title bar is full on Take a second
// line (titlebar_prefs.js; Derek, 2026-10-29: "I like both, if we could option
// it"), the bar takes it as soon as the title would be cut with every step
// taken, and the title is never shortened.
// Below 992 px the buttons have a line of their own, and the spacing, icon and
// ADD steps are plain CSS: nothing here.
// Loaded right after the bar (dashboard.html), so it fits before the first paint.
// The first paint is fitted to the counts' placeholders, and the first
// heartbeat brings the counts about half a second later: at some widths that
// took a step (or gave one back) on every load, ADD INVENTORY reading ADD and
// every button moving 80 px (round 3). So the bar remembers the steps it took
// (localStorage `fcc.titleBar.fit`, by the window's width, the Text size and
// the title-bar settings, which change the width or the steps), and while a
// count is still on its placeholder (`data-count-pending`, dashboard.html;
// each count's painter removes it) it takes at least those, when all of them are
// the same as then. The placeholders are
// no wider than a count, so they never need a step the counts don't: a load
// whose counts take the steps they took last time doesn't move.
// The memo keeps a window per width and Text size (the newest MEMO_KEEP): with
// one, two FCC windows at different widths each took the other's, and a reload
// moved again (round 4). Written once the bar has kept its steps for a second
// (or as the page goes), so a window resized by dragging keeps one entry, for
// where it stopped, not one for every width it passed.
(function () {
    const WRAP = 'fcc-tb-wrap';
    // The title is cut with every step taken: the badge keeps a gap from the
    // Spoolman light (global.css; review of 57.3: it touched it). Only then, so
    // the gap never brings a step sooner (a margin at every width took ADD's
    // step on a 1600 px window at Large).
    const CUT = 'fcc-tb-cut';
    // Every class a fit may have set: they all come off before it measures.
    const ALL = ['fcc-tb-tight', 'fcc-tb-icons', 'fcc-tb-add', 'fcc-tb-shortver', CUT, WRAP];
    const ONE_LINE = '(min-width: 992px)';
    const MEMO = 'fcc.titleBar.fit';
    const MEMO_KEEP = 8;
    const REMEMBER_AFTER_MS = 1000;
    let bar = null;
    let brand = null;
    let badge = null;
    let actions = null;
    let busy = false;
    let memo = [];            // [{w, size, mode, level}], newest first, read once at the load
    let toRemember = null;    // {w, size, mode, level} waiting for REMEMBER_AFTER_MS
    let rememberTimer = null;

    const root = document.documentElement;
    const sizeName = () => root.getAttribute('data-fcc-text-size') || 'standard';
    // The title-bar settings (titlebar_prefs.js), as one memo key.
    const modeName = () => (root.getAttribute('data-fcc-tb-buttons') || 'auto') + '|'
        + (root.getAttribute('data-fcc-low-count') || 'both') + '|'
        + (root.getAttribute('data-fcc-tb-full') || 'shorten');
    // When the title bar is full: a second line rather than a shortened title.
    const wrapsWhenFull = () => root.getAttribute('data-fcc-tb-full') === 'wrap';
    // The steps, in their order: the icon step only with Automatic (Always
    // words and Always icons fix the look).
    const steps = () => ((root.getAttribute('data-fcc-tb-buttons') || 'auto') === 'auto'
        ? ['fcc-tb-tight', 'fcc-tb-icons', 'fcc-tb-add', 'fcc-tb-shortver']
        : ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-shortver']);

    // An entry from before Group 57.3 (no settings in it, and its steps
    // counted the badge's) is no use, and is dropped.
    function readMemo() {
        const ok = (m) => !!m && Number.isFinite(m.w) && typeof m.size === 'string' && typeof m.mode === 'string'
            && Number.isInteger(m.level);
        try {
            const m = JSON.parse(localStorage.getItem(MEMO) || 'null');
            if (Array.isArray(m)) return m.filter(ok).slice(0, MEMO_KEEP);
        } catch (_) { /* private window, blocked storage: no memo */ }
        return [];
    }

    // What's stored now (another FCC window may have written since this load),
    // with this window's entry first.
    function writeMemo() {
        clearTimeout(rememberTimer);
        rememberTimer = null;
        const m = toRemember;
        toRemember = null;
        if (!m) return;
        try {
            const rest = readMemo().filter((e) => !(e.w === m.w && e.size === m.size && e.mode === m.mode));
            const text = JSON.stringify([m, ...rest].slice(0, MEMO_KEEP));
            if (localStorage.getItem(MEMO) !== text) localStorage.setItem(MEMO, text);
        } catch (_) { /* noop */ }
    }

    function remember(level) {
        toRemember = { w: window.innerWidth, size: sizeName(), mode: modeName(), level };
        clearTimeout(rememberTimer);
        rememberTimer = setTimeout(writeMemo, REMEMBER_AFTER_MS);
    }

    // The steps to take at least: the remembered ones while a count is still
    // on its placeholder, at the width, Text size and settings they were
    // taken at.
    function floor() {
        if (!actions || !actions.querySelector('[data-count-pending]')) return 0;
        const w = window.innerWidth;
        const size = sizeName();
        const mode = modeName();
        const m = memo.find((e) => e.w === w && e.size === size && e.mode === mode);
        return m ? m.level : 0;
    }

    // The title's own width, below the pixel. scrollWidth and clientWidth are
    // whole numbers, and Chrome draws the "…" from 1/64 px over, so a title up
    // to about 1.5 px too wide read as fitting and stayed cut with a step still
    // to take ("Filament Command Cent…" at 1596 px; round 2). Measured on a
    // hidden copy with the title's own class (so its own font), out of the
    // flow, gone again before anything paints.
    function natural() {
        const probe = document.createElement('span');
        probe.className = brand.className;
        probe.setAttribute('aria-hidden', 'true');
        probe.style.cssText = 'position:absolute; left:0; top:0; visibility:hidden; pointer-events:none;'
            + ' white-space:nowrap; min-width:0; max-width:none;';
        probe.textContent = brand.textContent;
        brand.parentNode.appendChild(probe);
        const need = probe.getBoundingClientRect().width;
        probe.remove();
        return need;
    }

    // The title is cut: its text is wider than the room it has.
    const cut = (need) => brand.getBoundingClientRect().width < need - 0.01;

    // The buttons run past the bar's content edge.
    function overflowing() {
        const r = bar.getBoundingClientRect();
        const cs = getComputedStyle(bar);
        const edge = r.right - (parseFloat(cs.paddingRight) || 0) - (parseFloat(cs.borderRightWidth) || 0);
        return actions.getBoundingClientRect().right > edge + 0.5;
    }

    // The version badge runs under the buttons, its right margin counted (the
    // gap to the Spoolman light). The title's group may shrink to a stub and
    // the badge never shrinks, so with the title cut to nothing the badge
    // spilled out of its group while the buttons still fitted the bar.
    function crowded() {
        if (!badge || !actions) return false;
        const r = badge.getBoundingClientRect();
        if (!r.width) return false;
        const gap = parseFloat(getComputedStyle(badge).marginRight) || 0;
        return r.right + gap > actions.getBoundingClientRect().left + 0.5;
    }

    function fit() {
        if (!bar || !bar.isConnected || busy) return;
        busy = true;
        try {
            bar.classList.remove(...ALL);
            if (!window.matchMedia(ONE_LINE).matches) return;
            const least = floor();
            const pending = !!(actions && actions.querySelector('[data-count-pending]'));
            const need = natural();
            const order = steps();
            // Steps taken: 0 to order.length, and one more with the second line.
            let level = 0;
            for (const step of order) {
                if (level >= least && !cut(need)) break;
                bar.classList.add(step);
                level += 1;
            }
            if (level === order.length && cut(need)) bar.classList.add(CUT);
            if (level === order.length && actions
                && (least > order.length || overflowing() || crowded() || (wrapsWhenFull() && cut(need)))) {
                // On two lines the title has a line of its own, and the whole badge
                // its place beside it, as below 992 px: the badge never goes (57.3).
                bar.classList.remove('fcc-tb-shortver', CUT);
                bar.classList.add(WRAP);
                level += 1;
            }
            if (!pending) remember(level);
        } finally {
            busy = false;
        }
    }

    // L42: the version badge reads in local time (the container's clock is UTC),
    // with the commit when the server resolved one. Written here, before the
    // first fit, since round 2: scripts.html wrote it at DOMContentLoaded, after
    // the first paint, so the bar was fitted to the server's longer UTC text and
    // the buttons moved about 100 ms into every load. The UTC text stays the
    // tooltip.
    function localBadge() {
        const verEl = document.getElementById('fcc-build-version');
        if (!verEl) return;
        const pad = (n) => String(n).padStart(2, '0');
        const fmt = (unix) => {
            const d = new Date(unix * 1000);
            return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
        };
        const sha = (verEl.dataset.buildCommitSha || '').trim();
        const commitTs = parseInt(verEl.dataset.buildCommitTs || '0', 10);
        const mtime = parseFloat(verEl.dataset.buildMtime || '0');
        // The date and time in a span of their own, which the badge keeps when
        // the bar is short of room (fcc-tb-shortver, 57.3).
        const put = (lead, when) => {
            verEl.textContent = '';
            const a = document.createElement('span');
            a.className = 'fcc-ver-lead';
            a.textContent = lead;
            const b = document.createElement('span');
            b.className = 'fcc-ver-when';
            b.textContent = when;
            verEl.append(a, b);
        };
        if (sha && commitTs > 0) put(`commit ${sha} • `, fmt(commitTs));
        else if (sha) verEl.textContent = `commit ${sha}`;
        else if (mtime > 0) put('build ', fmt(mtime));
    }

    function start() {
        bar = document.querySelector('.fcc-titlebar');
        brand = bar ? bar.querySelector('.navbar-brand') : null;
        if (!bar || !brand) return;
        actions = bar.querySelector('.fcc-titlebar-actions');
        badge = document.getElementById('fcc-build-version');
        memo = readMemo();
        localBadge();
        fit();
        if (typeof ResizeObserver === 'function') {
            // A marker as wide as the bar and never any taller: the bar itself
            // grows a line when it wraps, and a fit that changes the size it
            // was called for makes Chrome report a ResizeObserver loop.
            const marker = document.createElement('div');
            marker.className = 'fcc-tb-marker';
            marker.setAttribute('aria-hidden', 'true');
            bar.appendChild(marker);
            new ResizeObserver(() => fit()).observe(marker);
        } else {
            window.addEventListener('resize', fit);
        }
        if (actions && typeof MutationObserver === 'function') {
            new MutationObserver(() => fit()).observe(actions, { childList: true, characterData: true, subtree: true });
        }
        document.addEventListener('fcc:text-size', fit);       // text_size.js, Settings -> This Browser
        document.addEventListener('fcc:title-bar', fit);       // titlebar_prefs.js, the same
        window.addEventListener('load', fit);
        window.addEventListener('pagehide', writeMemo);        // a reload within the second keeps it
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit).catch(() => {});
    }

    window.fccFitTitleBar = fit;
    start();
})();
