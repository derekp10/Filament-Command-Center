/* MODULE: TITLE BAR FIT (Group 57 review, 2026-10-26) */
// The one-line title bar (992 px and up) gives way in steps when it runs out of
// room: the spacing tightens (fcc-tb-tight), ADD INVENTORY reads ADD
// (fcc-tb-add), the version badge goes (fcc-tb-nover), and last the title
// shortens with "…" (global.css "Title bar"; the readability build,
// 2026-10-21). The steps used to come at fixed widths, set for the bar as it
// was. Since the ⚠️ Low stock count (Group 57.2) the bar holds three live
// counts (🏷️ Backlog, 🛒 Queue, ⚠️ Low stock) whose width changes with their
// numbers, so a fixed width came too late once a count grew: the title
// shortened at Standard on a 1600 px window as soon as the Queue reached 10.
// Here each step is taken only while the title is cut short, in that order,
// whatever the counts say: on load, on a resize, a Text size change, and
// whenever a button's text changes. The version badge never shrinks on this
// bar (global.css), so a cut title is the one sign that a step is due.
// If the buttons still run past the bar's edge with every step taken (Extra
// Large in a window just over 992 px, with big counts), the bar takes a
// second line, as it does below 992 px (fcc-tb-wrap), so ⚙️ Settings, the way
// back to a smaller Text size, never leaves the screen (round 2).
// Below 992 px the buttons have a line of their own and the first two steps
// are plain CSS: nothing here.
// Loaded right after the bar (dashboard.html), so it fits before the first paint.
// The first paint is fitted to the counts' placeholders, and the first
// heartbeat brings the counts about half a second later: at some widths that
// took a step (or gave one back) on every load, ADD INVENTORY reading ADD and
// every button moving 80 px (round 3). So the bar remembers the steps it took
// (localStorage `fcc.titleBar.fit`, by the window's width and the Text size),
// and while a count is still on its placeholder (`data-count-pending`,
// dashboard.html; each count's painter removes it) it takes at least those,
// when the width and the Text size are the same as then. The placeholders are
// no wider than a count, so they never need a step the counts don't: a load
// whose counts take the steps they took last time doesn't move.
// The memo keeps a window per width and Text size (the newest MEMO_KEEP): with
// one, two FCC windows at different widths each took the other's, and a reload
// moved again (round 4). Written once the bar has kept its steps for a second
// (or as the page goes), so a window resized by dragging keeps one entry, for
// where it stopped, not one for every width it passed.
(function () {
    const STEPS = ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-nover'];
    const WRAP = 'fcc-tb-wrap';
    const ONE_LINE = '(min-width: 992px)';
    const MEMO = 'fcc.titleBar.fit';
    const MEMO_KEEP = 8;
    const REMEMBER_AFTER_MS = 1000;
    let bar = null;
    let brand = null;
    let actions = null;
    let busy = false;
    let memo = [];            // [{w, size, level}], newest first, read once at the load
    let toRemember = null;    // {w, size, level} waiting for REMEMBER_AFTER_MS
    let rememberTimer = null;

    const sizeName = () => document.documentElement.getAttribute('data-fcc-text-size') || 'standard';

    function readMemo() {
        const ok = (m) => !!m && Number.isFinite(m.w) && typeof m.size === 'string' && Number.isInteger(m.level);
        try {
            const m = JSON.parse(localStorage.getItem(MEMO) || 'null');
            if (Array.isArray(m)) return m.filter(ok).slice(0, MEMO_KEEP);
            if (ok(m)) return [m];                         // round 3's one window
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
            const rest = readMemo().filter((e) => !(e.w === m.w && e.size === m.size));
            const text = JSON.stringify([m, ...rest].slice(0, MEMO_KEEP));
            if (localStorage.getItem(MEMO) !== text) localStorage.setItem(MEMO, text);
        } catch (_) { /* noop */ }
    }

    function remember(level) {
        toRemember = { w: window.innerWidth, size: sizeName(), level };
        clearTimeout(rememberTimer);
        rememberTimer = setTimeout(writeMemo, REMEMBER_AFTER_MS);
    }

    // The steps to take at least: the remembered ones while a count is still
    // on its placeholder, at the width and Text size they were taken at.
    function floor() {
        if (!actions || !actions.querySelector('[data-count-pending]')) return 0;
        const w = window.innerWidth;
        const size = sizeName();
        const m = memo.find((e) => e.w === w && e.size === size);
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

    function fit() {
        if (!bar || !bar.isConnected || busy) return;
        busy = true;
        try {
            bar.classList.remove(...STEPS, WRAP);
            if (!window.matchMedia(ONE_LINE).matches) return;
            const least = floor();
            const pending = !!(actions && actions.querySelector('[data-count-pending]'));
            const need = natural();
            // Steps taken: 0 to 3, and 4 with the second line (in nover's place).
            let level = 0;
            for (const step of STEPS) {
                if (level >= least && !cut(need)) break;
                bar.classList.add(step);
                level += 1;
            }
            if (level === STEPS.length && actions && (least > STEPS.length || overflowing())) {
                // On two lines the title has a line of its own, and the badge its
                // place beside it, as below 992 px.
                bar.classList.remove('fcc-tb-nover');
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
        if (sha) {
            let label = `commit ${sha}`;
            if (commitTs > 0) label += ` • ${fmt(commitTs)}`;
            verEl.textContent = label;
        } else if (mtime > 0) {
            verEl.textContent = `build ${fmt(mtime)}`;
        }
    }

    function start() {
        bar = document.querySelector('.fcc-titlebar');
        brand = bar ? bar.querySelector('.navbar-brand') : null;
        if (!bar || !brand) return;
        actions = bar.querySelector('.fcc-titlebar-actions');
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
        window.addEventListener('load', fit);
        window.addEventListener('pagehide', writeMemo);        // a reload within the second keeps it
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit).catch(() => {});
    }

    window.fccFitTitleBar = fit;
    start();
})();
