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
(function () {
    const STEPS = ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-nover'];
    const WRAP = 'fcc-tb-wrap';
    const ONE_LINE = '(min-width: 992px)';
    let bar = null;
    let brand = null;
    let actions = null;
    let busy = false;

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
            const need = natural();
            for (const step of STEPS) {
                if (!cut(need)) return;
                bar.classList.add(step);
            }
            if (actions && overflowing()) {
                // On two lines the title has a line of its own, and the badge its
                // place beside it, as below 992 px.
                bar.classList.remove('fcc-tb-nover');
                bar.classList.add(WRAP);
            }
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
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit).catch(() => {});
    }

    window.fccFitTitleBar = fit;
    start();
})();
