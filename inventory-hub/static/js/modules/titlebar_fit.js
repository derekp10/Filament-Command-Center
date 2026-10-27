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
// Below 992 px the buttons have a line of their own and the first two steps
// are plain CSS: nothing here.
// Loaded right after the bar (dashboard.html), so it fits before the first paint.
(function () {
    const STEPS = ['fcc-tb-tight', 'fcc-tb-add', 'fcc-tb-nover'];
    const ONE_LINE = '(min-width: 992px)';
    let bar = null;
    let brand = null;
    let busy = false;

    // The title is cut: its text is wider than the room it has.
    const cut = () => brand.scrollWidth > brand.clientWidth + 1;

    function fit() {
        if (!bar || !bar.isConnected || busy) return;
        busy = true;
        try {
            bar.classList.remove(...STEPS);
            if (!window.matchMedia(ONE_LINE).matches) return;
            for (const step of STEPS) {
                if (!cut()) break;
                bar.classList.add(step);
            }
        } finally {
            busy = false;
        }
    }

    function start() {
        bar = document.querySelector('.fcc-titlebar');
        brand = bar ? bar.querySelector('.navbar-brand') : null;
        if (!bar || !brand) return;
        fit();
        if (typeof ResizeObserver === 'function') new ResizeObserver(() => fit()).observe(bar);
        else window.addEventListener('resize', fit);
        const actions = bar.querySelector('.fcc-titlebar-actions');
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
